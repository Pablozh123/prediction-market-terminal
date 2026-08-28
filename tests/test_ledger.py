import contextlib
import importlib.util
import io
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
import pandas as pd

from app import ledger
from app.quant import wilson_interval as quant_wilson

REPO_ROOT = Path(__file__).resolve().parents[1]


def make_signal(title, market_key="0x" + "a" * 64, outcome="Yes", price=0.25, **extra):
    row = {
        "signal_type": "Fast mover",
        "severity": "warning",
        "time": pd.Timestamp("2026-07-16 09:30:00", tz="UTC"),
        "platform": "Polymarket",
        "title": title,
        "category": "Politics",
        "outcome": outcome,
        "price": price,
        "value": 0.05,
        "reason": "1h move +5.0c",
        "volume": 120_000.0,
        "liquidity": 40_000.0,
        "spread": 0.02,
        "change_1h": 0.05,
        "market_key": market_key,
        "wallet": "",
        "trader": "",
        "notional": 0.0,
        "url": "https://example.com/m",
    }
    row.update(extra)
    return row


def condition_id(letter):
    return "0x" + (letter * 64).lower()


class CanonicalJsonTests(unittest.TestCase):
    def test_canonical_form_is_pinned(self):
        payload = {"b": float("nan"), "a": 1.5, "c": "x", "d": None}
        self.assertEqual(ledger.canonical_payload_json(payload), '{"a":1.5,"b":null,"c":"x","d":null}')

    def test_nan_variants_and_key_order_hash_identically(self):
        base = {"a": 1.5, "spread": float("nan"), "change_1h": None, "t": pd.Timestamp("2026-07-16 09:30:00", tz="UTC")}
        shuffled = {"t": pd.Timestamp("2026-07-16 09:30:00", tz="UTC"), "change_1h": float("nan"), "spread": np.nan, "a": np.float64(1.5)}
        self.assertEqual(ledger.payload_hash_for(base), ledger.payload_hash_for(shuffled))

    def test_numpy_and_nat_values_normalize(self):
        self.assertEqual(ledger.canonical_payload_json({"n": np.int64(5)}), '{"n":5}')
        self.assertEqual(ledger.canonical_payload_json({"t": pd.NaT}), '{"t":null}')
        self.assertEqual(
            ledger.canonical_payload_json({"t": pd.Timestamp("2026-07-16 09:30:00", tz="UTC")}),
            '{"t":"2026-07-16 09:30:00+00:00"}',
        )
        self.assertEqual(ledger.canonical_payload_json({"v": np.inf}), '{"v":null}')

    def test_signal_row_hash_survives_dataframe_round_trip(self):
        raw = make_signal("Round trip", spread=float("nan"), change_1h=None)
        frame_row = pd.DataFrame([raw]).iloc[0]
        self.assertEqual(
            ledger.payload_hash_for(raw),
            ledger.payload_hash_for({str(k): v for k, v in frame_row.items()}),
        )

    def test_payload_hash_matches_across_process_starts(self):
        script = (
            "import sys, pandas as pd\n"
            f"sys.path.insert(0, {str(REPO_ROOT)!r})\n"
            "from app import ledger\n"
            "row = pd.DataFrame([{'title': 'Cross process', 'spread': float('nan'),"
            " 'time': pd.Timestamp('2026-07-16 09:30:00', tz='UTC'), 'price': 0.25}]).iloc[0]\n"
            "print(ledger.payload_hash_for({str(k): v for k, v in row.items()}), end='')\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", script], capture_output=True, text=True, timeout=120, check=True
        )
        row = pd.DataFrame(
            [{"title": "Cross process", "spread": float("nan"), "time": pd.Timestamp("2026-07-16 09:30:00", tz="UTC"), "price": 0.25}]
        ).iloc[0]
        self.assertEqual(result.stdout, ledger.payload_hash_for({str(k): v for k, v in row.items()}))


class ModeledPnlTests(unittest.TestCase):
    def test_won_and_lost_per_100(self):
        self.assertAlmostEqual(ledger.modeled_pnl_per_100(0.25, "won"), 300.0)
        self.assertAlmostEqual(ledger.modeled_pnl_per_100(0.2, "won"), 400.0)
        self.assertEqual(ledger.modeled_pnl_per_100(0.8, "lost"), -100.0)

    def test_degenerate_inputs_have_no_pnl(self):
        self.assertIsNone(ledger.modeled_pnl_per_100(None, "won"))
        self.assertIsNone(ledger.modeled_pnl_per_100(float("nan"), "won"))
        self.assertIsNone(ledger.modeled_pnl_per_100(0.0, "won"))
        self.assertIsNone(ledger.modeled_pnl_per_100(1.0, "won"))
        self.assertIsNone(ledger.modeled_pnl_per_100(0.5, "voided"))
        self.assertIsNone(ledger.modeled_pnl_per_100(0.5, "unknown"))


class EmitChainTests(unittest.TestCase):
    def setUp(self):
        self.conn = ledger.init_ledger(":memory:")
        self.addCleanup(self.conn.close)

    def _emit(self, titles):
        frame = pd.DataFrame([make_signal(t, market_key=condition_id("a")) for t in titles])
        return ledger.emit_signals(self.conn, frame)

    def test_emit_builds_chain_and_second_run_is_idempotent(self):
        frame = pd.DataFrame([make_signal(f"Signal {i}") for i in range(3)])
        self.assertEqual(ledger.emit_signals(self.conn, frame), 3)
        rows = self.conn.execute("SELECT * FROM signals_emitted ORDER BY id").fetchall()
        self.assertEqual(rows[0]["prev_hash"], ledger.GENESIS_HASH)
        self.assertEqual(rows[1]["prev_hash"], rows[0]["payload_hash"])
        self.assertEqual(rows[2]["prev_hash"], rows[1]["payload_hash"])
        for row in rows:
            self.assertEqual(
                row["row_hash"],
                ledger.row_hash_for(row["payload_hash"], row["prev_hash"], row["emitted_at"], row["methodology_version"]),
            )
            self.assertEqual(row["methodology_version"], ledger.METHODOLOGY_VERSION)
        self.assertEqual(ledger.verify_chain(self.conn), (True, 3))
        self.assertEqual(ledger.emit_signals(self.conn, frame), 0)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) AS n FROM signals_emitted").fetchone()["n"], 3)

    def test_duplicate_rows_within_one_batch_write_once(self):
        frame = pd.DataFrame([make_signal("Twin"), make_signal("Twin")])
        self.assertEqual(ledger.emit_signals(self.conn, frame), 1)

    def test_empty_frame_writes_nothing(self):
        self.assertEqual(ledger.emit_signals(self.conn, pd.DataFrame()), 0)

    def test_emit_extracts_columns_and_normalizes_platform(self):
        frame = pd.DataFrame([make_signal("Cols", price=float("nan"))])
        ledger.emit_signals(self.conn, frame)
        row = self.conn.execute("SELECT * FROM signals_emitted").fetchone()
        self.assertEqual(row["signal_type"], "Fast mover")
        self.assertEqual(row["platform"], "polymarket")
        self.assertEqual(row["outcome"], "Yes")
        self.assertIsNone(row["price_at_emit"])
        self.assertIn('"spread":0.02', row["payload_json"])

    def test_verify_chain_detects_tampered_middle_payload(self):
        self._emit(["One", "Two", "Three"])
        self.conn.execute("UPDATE signals_emitted SET payload_json = '{\"tampered\":true}' WHERE id = 2")
        self.conn.commit()
        ok, checked = ledger.verify_chain(self.conn)
        self.assertFalse(ok)
        self.assertEqual(checked, 2)
        self.assertFalse(ledger.ledger_aggregates(self.conn)["chain_ok"])

    def test_verify_chain_detects_consistent_middle_row_rewrite(self):
        self._emit(["One", "Two", "Three"])
        row = self.conn.execute("SELECT * FROM signals_emitted WHERE id = 2").fetchone()
        forged_json = '{"forged":true}'
        forged_payload_hash = ledger.payload_hash_for({"forged": True})
        forged_row_hash = ledger.row_hash_for(forged_payload_hash, row["prev_hash"], row["emitted_at"], row["methodology_version"])
        self.conn.execute(
            "UPDATE signals_emitted SET payload_json = ?, payload_hash = ?, row_hash = ? WHERE id = 2",
            (forged_json, forged_payload_hash, forged_row_hash),
        )
        self.conn.commit()
        ok, checked = ledger.verify_chain(self.conn)
        self.assertFalse(ok)
        self.assertEqual(checked, 3)

    def test_hash_reproducible_across_connections(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "ledger.sqlite"
            frame = pd.DataFrame([make_signal("Persist A", spread=float("nan")), make_signal("Persist B")])
            first = ledger.init_ledger(db_path)
            try:
                self.assertEqual(ledger.emit_signals(first, frame), 2)
            finally:
                first.close()
            second = ledger.init_ledger(db_path)
            try:
                self.assertEqual(ledger.emit_signals(second, frame), 0)
                self.assertEqual(ledger.verify_chain(second), (True, 2))
                self.assertEqual(second.execute("SELECT COUNT(*) AS n FROM signals_emitted").fetchone()["n"], 2)
            finally:
                second.close()


class ResolveTests(unittest.TestCase):
    def setUp(self):
        self.conn = ledger.init_ledger(":memory:")
        self.addCleanup(self.conn.close)
        frame = pd.DataFrame(
            [
                make_signal("Winner", market_key=condition_id("a"), outcome="Yes", price=0.25),
                make_signal("Loser", market_key=condition_id("b"), outcome="Yes", price=0.5),
                make_signal("Voided", market_key=condition_id("c"), outcome="Yes", price=0.6),
                make_signal("Still open", market_key=condition_id("d"), outcome="Yes", price=0.4),
                make_signal("Odd outcome", market_key=condition_id("e"), outcome="Maybe", price=0.3),
                make_signal("No outcome", market_key=condition_id("f"), outcome=""),
            ]
        )
        ledger.emit_signals(self.conn, frame)
        self.fetch_map = {
            condition_id("a"): {"status": "resolved", "outcome_prices": {"yes": 1.0, "no": 0.0}, "source": "polymarket_gamma"},
            condition_id("b"): {"status": "resolved", "outcome_prices": {"yes": 0.0, "no": 1.0}, "source": "polymarket_gamma"},
            condition_id("c"): {"status": "voided", "outcome_prices": {"yes": 0.5, "no": 0.5}, "source": "polymarket_gamma"},
            condition_id("e"): {"status": "resolved", "outcome_prices": {"yes": 1.0, "no": 0.0}, "source": "polymarket_gamma"},
        }

    def _resolve(self):
        return ledger.resolve_pending(self.conn, lambda keys: {k: v for k, v in self.fetch_map.items() if k in keys})

    def _results(self):
        return {
            str(r["market_key"]): r
            for r in self.conn.execute(
                """
                SELECT e.market_key, s.outcome_result, s.price_at_resolution, s.pnl_modeled, s.resolution_hash,
                       s.resolved_at, e.row_hash
                FROM signals_resolved s JOIN signals_emitted e ON e.id = s.signal_id
                """
            )
        }

    def test_resolves_won_lost_voided_and_unknown(self):
        self.assertEqual(self._resolve(), 4)
        results = self._results()
        self.assertEqual(results[condition_id("a")]["outcome_result"], "won")
        self.assertAlmostEqual(results[condition_id("a")]["pnl_modeled"], 300.0)
        self.assertEqual(results[condition_id("b")]["outcome_result"], "lost")
        self.assertAlmostEqual(results[condition_id("b")]["pnl_modeled"], -100.0)
        self.assertEqual(results[condition_id("c")]["outcome_result"], "voided")
        self.assertIsNone(results[condition_id("c")]["pnl_modeled"])
        self.assertEqual(results[condition_id("e")]["outcome_result"], "unknown")
        self.assertIsNone(results[condition_id("e")]["pnl_modeled"])
        for row in results.values():
            self.assertEqual(
                row["resolution_hash"],
                ledger.resolution_hash_for(
                    int(
                        self.conn.execute(
                            "SELECT id FROM signals_emitted WHERE market_key = ?", (row["market_key"],)
                        ).fetchone()["id"]
                    ),
                    row["outcome_result"],
                    row["price_at_resolution"],
                    row["resolved_at"],
                    row["row_hash"],
                ),
            )

    def test_second_resolution_run_writes_nothing_new(self):
        self.assertEqual(self._resolve(), 4)
        self.assertEqual(self._resolve(), 0)

    def test_voided_and_unknown_stay_out_of_hit_rate_denominator(self):
        self._resolve()
        stats = ledger.ledger_aggregates(self.conn)
        self.assertEqual(stats["decisive"], 2)
        self.assertAlmostEqual(stats["hit_rate"], 0.5)
        self.assertAlmostEqual(stats["pnl_modeled_sum"], 200.0)

    def test_aggregates_are_consistent(self):
        self._resolve()
        stats = ledger.ledger_aggregates(self.conn)
        self.assertEqual(stats["emitted"], 6)
        self.assertEqual(stats["resolvable"], 5)
        self.assertEqual(stats["not_resolvable"], 1)
        self.assertEqual(stats["resolved"], 4)
        self.assertEqual(stats["pending"], 1)
        self.assertEqual(stats["emitted"], stats["resolved"] + stats["pending"] + stats["not_resolvable"])
        self.assertTrue(stats["chain_ok"])
        self.assertEqual(stats["chain_checked"], 6)
        self.assertIsNotNone(stats["first_emit"])
        self.assertIsNotNone(stats["last_emit"])

    def test_empty_ledger_aggregates(self):
        empty = ledger.init_ledger(":memory:")
        try:
            stats = ledger.ledger_aggregates(empty)
        finally:
            empty.close()
        self.assertEqual(stats["emitted"], 0)
        self.assertIsNone(stats["hit_rate"])
        self.assertEqual(stats["pnl_modeled_sum"], 0.0)
        self.assertTrue(stats["chain_ok"])
        self.assertEqual(stats["decisive_units"], 0)
        self.assertIsNone(stats["hit_rate_units"])
        self.assertEqual(stats["hit_rate_ci95"], [None, None])
        self.assertIsNone(stats["repeat_factor"])

    def test_units_equal_rows_when_every_market_fired_once(self):
        self._resolve()
        stats = ledger.ledger_aggregates(self.conn)
        self.assertEqual(stats["decisive_units"], stats["decisive"])
        self.assertAlmostEqual(stats["repeat_factor"], 1.0)
        self.assertAlmostEqual(stats["hit_rate_units"], stats["hit_rate"])


class RepeatedSignalTests(unittest.TestCase):
    """Ein Markt loest viele Signale aus, aber nur EINE Aufloesung.

    Fuenf Regeln auf demselben Markt und Ausgang, der Markt gewinnt: die
    Trefferquote je Signalzeile steht bei 100 Prozent auf n=5, obwohl genau
    ein Ausgang beobachtet wurde. Das Intervall muss an der Eins haengen.
    """

    def setUp(self):
        self.conn = ledger.init_ledger(":memory:")
        self.addCleanup(self.conn.close)
        rows = [
            make_signal("same market", market_key=condition_id("a"), outcome="Yes",
                        price=0.25, signal_type=typ, value=float(i))
            for i, typ in enumerate(
                ["Fast mover", "Tight spread", "Volume anomaly", "Ending soon", "Watched market"]
            )
        ]
        rows.append(make_signal("other market", market_key=condition_id("b"), outcome="Yes", price=0.5))
        ledger.emit_signals(self.conn, pd.DataFrame(rows))
        ledger.resolve_pending(
            self.conn,
            lambda keys: {
                condition_id("a"): {"status": "resolved", "outcome_prices": {"yes": 1.0, "no": 0.0}, "source": "gamma"},
                condition_id("b"): {"status": "resolved", "outcome_prices": {"yes": 0.0, "no": 1.0}, "source": "gamma"},
            },
        )

    def test_signal_rows_and_independent_outcomes_are_reported_apart(self):
        stats = ledger.ledger_aggregates(self.conn)
        self.assertEqual(stats["decisive"], 6)
        self.assertEqual(stats["decisive_units"], 2)
        self.assertAlmostEqual(stats["repeat_factor"], 3.0)
        # Je Signalzeile 5 von 6, je unabhaengigem Ausgang 1 von 2.
        self.assertAlmostEqual(stats["hit_rate"], 5 / 6)
        self.assertAlmostEqual(stats["hit_rate_units"], 0.5)

    def test_interval_uses_the_independent_count(self):
        stats = ledger.ledger_aggregates(self.conn)
        low, high = stats["hit_rate_ci95"]
        # Wilson auf 1/2, nicht auf 5/6: das Intervall deckt fast alles ab.
        self.assertAlmostEqual((low, high), quant_wilson(1, 2))
        self.assertLess(low, 0.2)
        self.assertGreater(high, 0.8)

    def test_units_carry_their_outcome(self):
        units = dict(ledger.decisive_units(self.conn))
        self.assertEqual(len(units), 2)
        self.assertTrue(units[condition_id("a") + "|Yes"])
        self.assertFalse(units[condition_id("b") + "|Yes"])


class ResolutionMapTests(unittest.TestCase):
    def test_gamma_payloads_map_to_contract(self):
        raw = [
            {"conditionId": condition_id("a"), "closed": True, "outcomes": '["Yes","No"]', "outcomePrices": '["1","0"]'},
            {"conditionId": condition_id("b"), "closed": True, "outcomes": ["Yes", "No"], "outcomePrices": ["0.5", "0.5"]},
            {"conditionId": condition_id("c"), "closed": False, "outcomes": '["Yes","No"]', "outcomePrices": '["0.9","0.1"]'},
            {"conditionId": condition_id("d"), "closed": True, "outcomes": '["Yes","No"]', "outcomePrices": '["0.7","0.3"]'},
            {"conditionId": condition_id("e"), "closed": True, "umaResolutionStatus": "cancelled", "outcomes": '["Yes","No"]', "outcomePrices": '["0.99","0.01"]'},
            {"closed": True},
        ]
        mapping = ledger.polymarket_resolution_map(raw)
        self.assertEqual(len(mapping), 5)
        self.assertEqual(mapping[condition_id("a")]["status"], "resolved")
        self.assertEqual(mapping[condition_id("a")]["outcome_prices"], {"yes": 1.0, "no": 0.0})
        self.assertEqual(mapping[condition_id("a")]["source"], "polymarket_gamma")
        self.assertEqual(mapping[condition_id("b")]["status"], "voided")
        self.assertEqual(mapping[condition_id("c")]["status"], "open")
        self.assertEqual(mapping[condition_id("d")]["status"], "open")
        self.assertEqual(mapping[condition_id("e")]["status"], "voided")


class SafeEmitTests(unittest.TestCase):
    def test_safe_emit_reports_unwritable_db_without_raising(self):
        with tempfile.TemporaryDirectory() as tmp:
            blocker = Path(tmp) / "blocker.txt"
            blocker.write_text("occupied", encoding="utf-8")
            bad_path = blocker / "ledger.sqlite"
            written, error = ledger.safe_emit_signals(pd.DataFrame([make_signal("Blocked")]), bad_path)
        self.assertEqual(written, 0)
        self.assertIn("ledger open failed", error)

    def test_safe_emit_writes_when_path_is_fine(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "ledger.sqlite"
            written, error = ledger.safe_emit_signals(pd.DataFrame([make_signal("Fine")]), db_path)
            self.assertEqual((written, error), (1, ""))


def load_scanner_module():
    script = REPO_ROOT / "scripts" / "run_alert_scanner.py"
    spec = importlib.util.spec_from_file_location("run_alert_scanner_under_test", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ScannerLedgerIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = load_scanner_module()

    @staticmethod
    def settings():
        return {
            "market_sample": 10,
            "trade_sample": 10,
            "alert_min_move_cents": 3.0,
            "whale_threshold": 1000.0,
            "alert_holder_checks": 0,
            "telegram_bot_token": "token",
            "telegram_chat_id": "chat",
        }

    @staticmethod
    def whale_trades(count):
        rows = []
        for index in range(count):
            rows.append(
                {
                    "platform": "Polymarket",
                    "time": pd.Timestamp("2026-07-16 10:00:00", tz="UTC"),
                    "title": f"Whale market {index}",
                    "outcome": "Yes",
                    "price": 0.42,
                    "notional": 50_000.0,
                    "side": "BUY",
                    "market_key": "0x" + f"{index:x}".rjust(64, "0"),
                    "wallet": "0x" + "1" * 40,
                    "trader": "Tester",
                    "url": "https://example.com/t",
                }
            )
        return pd.DataFrame(rows)

    def run_scan(self, tmp, ledger_path, trades, max_messages=10):
        rules_path = Path(tmp) / "rules.json"
        rules_path.write_text(json.dumps([{"name": "Whale watch", "signal_type": "Whale print", "active": True}]), encoding="utf-8")
        sent_messages = []

        def fake_send(token, chat_id, text):
            sent_messages.append(text)
            return True, "ok"

        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(self.mod, "RULES_PATH", rules_path))
            stack.enter_context(mock.patch.object(self.mod, "STATE_PATH", Path(tmp) / "state.json"))
            stack.enter_context(mock.patch.object(self.mod, "LEDGER_DB_PATH", Path(ledger_path)))
            stack.enter_context(mock.patch.object(self.mod, "MAX_MESSAGES_PER_SCAN", max_messages))
            stack.enter_context(mock.patch.object(self.mod.md, "get_polymarket_markets", lambda limit=250, **kw: pd.DataFrame()))
            stack.enter_context(mock.patch.object(self.mod.md, "get_polymarket_trades", lambda limit=250, **kw: trades.copy()))
            stack.enter_context(mock.patch.object(self.mod.notify, "send_telegram", fake_send))
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                hits, sent = self.mod.scan_once(self.settings())
        return hits, sent, sent_messages, stderr.getvalue()

    @staticmethod
    def ledger_row_count(ledger_path):
        if not Path(ledger_path).exists():
            return 0
        conn = sqlite3.connect(ledger_path)
        try:
            return int(conn.execute("SELECT COUNT(*) FROM signals_emitted").fetchone()[0])
        finally:
            conn.close()

    def test_scan_logs_all_new_hits_beyond_message_cap(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger_path = Path(tmp) / "ledger.sqlite"
            hits, sent, messages, _ = self.run_scan(tmp, ledger_path, self.whale_trades(3), max_messages=2)
            self.assertEqual((hits, sent), (3, 2))
            self.assertEqual(len(messages), 2)
            self.assertEqual(self.ledger_row_count(ledger_path), 3)
            conn = ledger.init_ledger(ledger_path)
            try:
                self.assertEqual(ledger.verify_chain(conn), (True, 3))
            finally:
                conn.close()
            state = json.loads((Path(tmp) / "state.json").read_text(encoding="utf-8"))
            self.assertEqual(state["last_ledger_written"], 3)

    def test_second_scan_adds_no_ledger_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger_path = Path(tmp) / "ledger.sqlite"
            trades = self.whale_trades(2)
            first = self.run_scan(tmp, ledger_path, trades)
            self.assertEqual((first[0], first[1]), (2, 2))
            second = self.run_scan(tmp, ledger_path, trades)
            self.assertEqual((second[0], second[1]), (2, 0))
            self.assertEqual(self.ledger_row_count(ledger_path), 2)
            state = json.loads((Path(tmp) / "state.json").read_text(encoding="utf-8"))
            self.assertEqual(state["last_ledger_written"], 0)

    def test_scan_survives_unwritable_ledger(self):
        with tempfile.TemporaryDirectory() as tmp:
            blocker = Path(tmp) / "blocker.txt"
            blocker.write_text("occupied", encoding="utf-8")
            bad_path = blocker / "ledger.sqlite"
            hits, sent, messages, stderr_text = self.run_scan(tmp, bad_path, self.whale_trades(1))
            self.assertEqual((hits, sent), (1, 1))
            self.assertEqual(len(messages), 1)
            self.assertIn("ledger open failed", stderr_text)
            state = json.loads((Path(tmp) / "state.json").read_text(encoding="utf-8"))
            self.assertEqual(state["last_ledger_written"], 0)
            self.assertEqual(len(state["seen"]), 1)


class ScannerDeliveryLogTests(unittest.TestCase):
    """Der Scan schreibt auf, was rausging -- nicht nur, was er gemessen hat.

    Vorher gab es dafuer zwei Zahlen im JSON-Zustand, ``last_hits`` und
    ``last_sent``, die jeder Scan ueberschreibt. Ein Fehlversand ging nach
    stderr und war weg.
    """

    @classmethod
    def setUpClass(cls):
        cls.mod = load_scanner_module()

    @staticmethod
    def settings():
        return {
            "market_sample": 10,
            "trade_sample": 10,
            "alert_min_move_cents": 3.0,
            "whale_threshold": 1000.0,
            "alert_holder_checks": 0,
            "telegram_bot_token": "token",
            "telegram_chat_id": "-4711234567",
        }

    @staticmethod
    def whale_trade(index=0):
        return {
            "platform": "Polymarket",
            "time": pd.Timestamp("2026-07-16 10:00:00", tz="UTC"),
            "title": f"Whale market {index}",
            "outcome": "Yes",
            "price": 0.42,
            "notional": 50_000.0,
            "side": "BUY",
            "market_key": "0x" + f"{index:x}".rjust(64, "0"),
            "wallet": "0x" + "1" * 40,
            "trader": "Tester",
            "transaction_hash": f"0xtx{index}",
            "url": "https://example.com/t",
        }

    @staticmethod
    def fast_mover(updated_at):
        return {
            "platform": "Polymarket",
            "title": "Fed cuts in March",
            "market_key": condition_id("f"),
            "category": "Macro",
            "yes_price": 0.55,
            "volume_1h": 1_000.0,
            "volume_24h": 24_000.0,
            "activity_volume": 24_000.0,
            "liquidity": 50_000.0,
            "spread": 0.05,
            "change_1h": 0.08,
            "updated_at": updated_at,
            "url": "https://example.com/m",
        }

    def run_scan(self, tmp, ledger_path, *, trades=None, markets=None, rule, ok=True,
                 max_messages=10):
        rules_path = Path(tmp) / "rules.json"
        rules_path.write_text(json.dumps([rule]), encoding="utf-8")
        gesendet = []

        def fake_send(token, chat_id, text):
            gesendet.append(text)
            return (True, "ok") if ok else (False, "HTTP 429: Too Many Requests")

        leer = pd.DataFrame()
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(self.mod, "RULES_PATH", rules_path))
            stack.enter_context(mock.patch.object(self.mod, "STATE_PATH", Path(tmp) / "state.json"))
            stack.enter_context(mock.patch.object(self.mod, "LEDGER_DB_PATH", Path(ledger_path)))
            stack.enter_context(mock.patch.object(self.mod, "MAX_MESSAGES_PER_SCAN", max_messages))
            stack.enter_context(mock.patch.object(
                self.mod.md, "get_polymarket_markets",
                lambda limit=250, **kw: (pd.DataFrame(markets) if markets else leer.copy())))
            stack.enter_context(mock.patch.object(
                self.mod.md, "get_polymarket_trades",
                lambda limit=250, **kw: (pd.DataFrame(trades) if trades else leer.copy())))
            stack.enter_context(mock.patch.object(self.mod.notify, "send_telegram", fake_send))
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                hits, sent = self.mod.scan_once(self.settings())
        state = json.loads((Path(tmp) / "state.json").read_text(encoding="utf-8"))
        return hits, sent, gesendet, state, stderr.getvalue()

    @staticmethod
    def zustellungen(ledger_path):
        conn = ledger.init_ledger(ledger_path)
        try:
            return ledger.delivery_rows(conn), ledger.delivery_aggregates(conn)
        finally:
            conn.close()

    WHALE_RULE = {"name": "Whale watch", "signal_type": "Whale print", "active": True}
    MOVER_RULE = {"name": "Movers", "signal_type": "Fast mover", "active": True}

    def test_jede_zustellung_steht_im_protokoll(self):
        with tempfile.TemporaryDirectory() as tmp:
            pfad = Path(tmp) / "ledger.sqlite"
            hits, sent, nachrichten, state, _ = self.run_scan(
                tmp, pfad, trades=[self.whale_trade(i) for i in range(3)],
                rule=self.WHALE_RULE, max_messages=2)
            self.assertEqual((hits, sent), (3, 2))
            zeilen, zahlen = self.zustellungen(pfad)
            # Drei Treffer, zwei Versuche: der dritte lag ueber dem Cap und
            # wurde nicht versucht, also steht er auch nicht als Zustellung da.
            self.assertEqual(len(zeilen), 2)
            self.assertEqual(zahlen["attempts"], 2)
            self.assertEqual(zahlen["sent"], 2)
            self.assertEqual(state["last_deferred"], 1)
            self.assertEqual(state["last_attempted"], 2)
            self.assertEqual(state["last_delivery_logged"], 2)
            self.assertTrue(zahlen["chain_ok"])
            for zeile in zeilen:
                self.assertEqual(zeile["channel"], "telegram")
                self.assertTrue(zeile["dedupe_key"])
                self.assertNotIn("4711234567", zeile["target_fingerprint"])

    def test_ein_fehlversand_steht_drin_und_wird_erneut_versucht(self):
        with tempfile.TemporaryDirectory() as tmp:
            pfad = Path(tmp) / "ledger.sqlite"
            hits, sent, _, state, stderr = self.run_scan(
                tmp, pfad, trades=[self.whale_trade(0)], rule=self.WHALE_RULE, ok=False)
            self.assertEqual((hits, sent), (1, 0))
            self.assertIn("HTTP 429", stderr)
            zeilen, zahlen = self.zustellungen(pfad)
            self.assertEqual(len(zeilen), 1)
            self.assertEqual(zeilen[0]["status"], "failed")
            self.assertIn("429", zeilen[0]["detail"])
            self.assertEqual((zahlen["attempts"], zahlen["sent"], zahlen["failed"]), (1, 0, 1))
            self.assertEqual(state["last_failed"], 1)
            # Zweiter Scan: nie gelungen, also weiter faellig.
            hits2, sent2, _, _, _ = self.run_scan(
                tmp, pfad, trades=[self.whale_trade(0)], rule=self.WHALE_RULE, ok=True)
            self.assertEqual((hits2, sent2), (1, 1))
            zeilen2, zahlen2 = self.zustellungen(pfad)
            self.assertEqual(len(zeilen2), 2)
            self.assertEqual(zahlen2["sent"], 1)

    def test_derselbe_print_geht_nach_erfolg_nicht_noch_einmal_raus(self):
        with tempfile.TemporaryDirectory() as tmp:
            pfad = Path(tmp) / "ledger.sqlite"
            self.run_scan(tmp, pfad, trades=[self.whale_trade(0)], rule=self.WHALE_RULE)
            _, sent2, _, _, _ = self.run_scan(tmp, pfad, trades=[self.whale_trade(0)], rule=self.WHALE_RULE)
            self.assertEqual(sent2, 0)
            zeilen, _ = self.zustellungen(pfad)
            self.assertEqual(len(zeilen), 1)

    def test_ein_umbepreister_markt_geht_innerhalb_der_ruhezeit_einmal_raus(self):
        # Das gerechnete Beispiel aus app/signals.py: derselbe Fast mover,
        # dreimal gescannt, dazwischen ein neuer updated_at der Venue.
        with tempfile.TemporaryDirectory() as tmp:
            pfad = Path(tmp) / "ledger.sqlite"
            raus = 0
            for stempel in ("2026-08-28T14:23:07Z", "2026-08-28T14:34:51Z", "2026-08-28T14:44:02Z"):
                _, sent, _, _, _ = self.run_scan(
                    tmp, pfad, markets=[self.fast_mover(stempel)], rule=self.MOVER_RULE)
                raus += sent
            self.assertEqual(raus, 1)
            zeilen, zahlen = self.zustellungen(pfad)
            self.assertEqual(len(zeilen), 1)
            self.assertEqual(zahlen["distinct_signals"], 1)


class ResolutionRunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        script = REPO_ROOT / "scripts" / "run_ledger_resolution.py"
        spec = importlib.util.spec_from_file_location("run_ledger_resolution_under_test", script)
        cls.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.mod)

    def test_fetch_filters_non_polymarket_keys(self):
        with mock.patch.object(self.mod.md, "get_polymarket_markets_by_condition_ids") as fetch:
            fetch.return_value = []
            result = self.mod.fetch_polymarket_resolutions(["KXHIGHNY-26JUL16", "", condition_id("a")])
            fetch.assert_called_once_with([condition_id("a")])
        self.assertEqual(result, {})

    def test_fetch_skips_gamma_call_without_condition_ids(self):
        with mock.patch.object(self.mod.md, "get_polymarket_markets_by_condition_ids") as fetch:
            result = self.mod.fetch_polymarket_resolutions(["KXHIGHNY-26JUL16"])
            fetch.assert_not_called()
        self.assertEqual(result, {})

    def test_resolve_once_writes_status_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "ledger.sqlite"
            conn = ledger.init_ledger(db_path)
            try:
                ledger.emit_signals(conn, pd.DataFrame([make_signal("Runner", market_key=condition_id("a"), price=0.25)]))
            finally:
                conn.close()
            raw_markets = [
                {"conditionId": condition_id("a"), "closed": True, "outcomes": '["Yes","No"]', "outcomePrices": '["1","0"]'}
            ]
            with contextlib.ExitStack() as stack:
                stack.enter_context(mock.patch.object(self.mod.ledger, "DEFAULT_LEDGER_PATH", db_path))
                stack.enter_context(mock.patch.object(self.mod, "STATUS_PATH", Path(tmp) / "status.json"))
                stack.enter_context(
                    mock.patch.object(self.mod.md, "get_polymarket_markets_by_condition_ids", lambda ids: raw_markets)
                )
                new_resolved, chain_ok = self.mod.resolve_once()
            self.assertEqual(new_resolved, 1)
            self.assertTrue(chain_ok)
            status = json.loads((Path(tmp) / "status.json").read_text(encoding="utf-8"))
            self.assertEqual(status["new_resolved"], 1)
            self.assertTrue(status["chain_ok"])
            self.assertEqual(status["emitted"], 1)
            self.assertEqual(status["resolved"], 1)
            self.assertEqual(status["pending"], 0)
            self.assertIn("last_run_at", status)


class SellPrintScoringTests(unittest.TestCase):
    """Ein Verkaufsdruck darf nicht als Kauf zum Emit-Preis verbucht werden.

    ``modeled_pnl_per_100`` kauft den notierten Ausgang zum Emit-Preis. Ein
    Whale print mit ``side = SELL`` meldet den Ausstieg aus genau diesem
    Ausgang. Loest der Markt zugunsten des Ausgangs auf, schrieb das Ledger
    frueher einen Treffer und +233.33 modellierte Dollar je 100 gesetzte gut:
    der Ausstieg bekam den Gewinn eines Einstiegs, den er nie gemacht hat.
    """

    @staticmethod
    def _whale(side, outcome="Yes", price=0.30):
        return {
            "signal_type": "Whale print",
            "severity": "warning",
            "time": pd.Timestamp("2026-07-16 09:30:00", tz="UTC"),
            "platform": "Polymarket",
            "title": "Fed cuts in December",
            "category": "",
            "outcome": outcome,
            "side": side,
            "price": price,
            "value": 12_000.0,
            "reason": f"{side} $12,000",
            "volume": 0.0,
            "liquidity": 0.0,
            "spread": None,
            "change_1h": None,
            "market_key": condition_id("d"),
            "wallet": "0xwhale",
            "trader": "whale",
            "notional": 12_000.0,
            "url": "https://example.com/m",
        }

    def test_resolvable_outcome_drops_the_sold_side(self):
        self.assertEqual(ledger.resolvable_outcome(self._whale("BUY")), "Yes")
        self.assertEqual(ledger.resolvable_outcome(self._whale("SELL")), "")
        self.assertEqual(ledger.resolvable_outcome(self._whale("sell")), "")
        # Ein Marktsignal nimmt keine Seite und bleibt bewertbar.
        self.assertEqual(ledger.resolvable_outcome(make_signal("Mover")), "Yes")

    def test_a_sell_print_never_enters_the_hit_rate(self):
        conn = ledger.init_ledger(":memory:")
        try:
            ledger.emit_signals(conn, pd.DataFrame([self._whale("SELL")]))
            # Der Ausgang loest zugunsten der verkauften Seite auf.
            resolutions = {
                condition_id("d"): {
                    "status": "resolved",
                    "outcome_prices": {"yes": 1.0, "no": 0.0},
                    "source": "gamma",
                }
            }
            self.assertEqual(ledger.resolve_pending(conn, lambda keys: resolutions), 0)
            zahlen = ledger.ledger_aggregates(conn)
            self.assertEqual(zahlen["emitted"], 1)
            self.assertEqual(zahlen["resolvable"], 0)
            self.assertEqual(zahlen["not_resolvable"], 1)
            self.assertEqual(zahlen["decisive"], 0)
            self.assertIsNone(zahlen["hit_rate"])
            self.assertEqual(zahlen["pnl_modeled_sum"], 0.0)
            # Die Zeile bleibt vollstaendig im Ledger nachlesbar.
            payload = json.loads(
                conn.execute("SELECT payload_json FROM signals_emitted").fetchone()["payload_json"])
            self.assertEqual(payload["side"], "SELL")
            self.assertEqual(payload["outcome"], "Yes")
            self.assertTrue(ledger.verify_chain(conn)[0])
        finally:
            conn.close()

    def test_a_buy_print_is_scored_as_before(self):
        conn = ledger.init_ledger(":memory:")
        try:
            ledger.emit_signals(conn, pd.DataFrame([self._whale("BUY")]))
            resolutions = {
                condition_id("d"): {
                    "status": "resolved",
                    "outcome_prices": {"yes": 1.0, "no": 0.0},
                    "source": "gamma",
                }
            }
            self.assertEqual(ledger.resolve_pending(conn, lambda keys: resolutions), 1)
            zahlen = ledger.ledger_aggregates(conn)
            self.assertEqual(zahlen["decisive"], 1)
            self.assertEqual(zahlen["hit_rate"], 1.0)
            # 100 * (1 - 0.30) / 0.30 = 233.33 -- die Zahl, die ein SELL frueher
            # unverdient mitgenommen haette.
            self.assertAlmostEqual(zahlen["pnl_modeled_sum"], 233.3333, places=3)
        finally:
            conn.close()


class DeliveryLogTests(unittest.TestCase):
    """Was rausging, stand nirgends -- nur, was gemessen wurde.

    Der Scanner fuehrte einen Dedupe-Zustand (``data/alert_scanner_state.json``)
    mit den Feldern ``last_hits`` und ``last_sent``: zwei Skalare, die jeder
    Scan ueberschreibt. Damit war "wie viele Alerts sind diese Woche
    rausgegangen" nicht beantwortbar, ein fehlgeschlagener Versand ging nach
    stderr und war weg, und die Trefferquote des Ledgers stand unter dem Satz
    "how often an alert that went out was on the right side", obwohl das
    Ledger die EMITTIERTEN Signale zaehlt.

    Das gerechnete Beispiel: ``MAX_MESSAGES_PER_SCAN = 10``. Ein Scan mit 47
    neuen Treffern schreibt 47 Ledger-Zeilen und verschickt hoechstens 10
    Nachrichten. 37 der 47 Zeilen im Nenner der Quote sind nie irgendwo
    angekommen, also 78,7 Prozent des Nenners.
    """

    ANGEKOMMEN = 10
    EMITTIERT = 47

    @contextlib.contextmanager
    def _ledger(self):
        conn = ledger.init_ledger(":memory:")
        try:
            yield conn
        finally:
            conn.close()

    def _zustellung(self, key, status="sent", **extra):
        row = {
            "dedupe_key": key,
            "channel": "telegram",
            "target": "-4711234567",
            "status": status,
            "signal_type": "Fast mover",
            "market_key": condition_id("a"),
        }
        row.update(extra)
        return row

    def test_eine_zustellung_haelt_zeit_kanal_und_status_fest(self):
        with self._ledger() as conn:
            geschrieben = ledger.record_deliveries(
                conn, [self._zustellung("Fast mover|0xa|Yes|")], delivered_at="2026-08-28T14:25:00+00:00")
            self.assertEqual(geschrieben, 1)
            zeilen = ledger.delivery_rows(conn)
            self.assertEqual(len(zeilen), 1)
            self.assertEqual(zeilen[0]["channel"], "telegram")
            self.assertEqual(zeilen[0]["status"], "sent")
            self.assertEqual(zeilen[0]["delivered_at"], "2026-08-28T14:25:00+00:00")
            self.assertEqual(zeilen[0]["dedupe_key"], "Fast mover|0xa|Yes|")

    def test_das_ziel_steht_als_fingerabdruck_nicht_als_chat_id(self):
        # Grundsatz des taeglichen Laufs: Audit nur als Hashes und Zaehler.
        with self._ledger() as conn:
            ledger.record_deliveries(conn, [self._zustellung("k1")])
            gespeichert = ledger.delivery_rows(conn)[0]["target_fingerprint"]
            self.assertNotIn("4711234567", gespeichert)
            self.assertEqual(gespeichert, ledger.target_fingerprint("-4711234567"))
            self.assertNotEqual(gespeichert, ledger.target_fingerprint("-4711234568"))

    def test_ein_fehlversand_steht_als_fehlversand_und_zaehlt_nicht_als_zustellung(self):
        with self._ledger() as conn:
            ledger.record_deliveries(conn, [
                self._zustellung("k1", status="failed", detail="HTTP 429: Too Many Requests"),
                self._zustellung("k2"),
            ])
            zahlen = ledger.delivery_aggregates(conn)
            self.assertEqual(zahlen["attempts"], 2)
            self.assertEqual(zahlen["sent"], 1)
            self.assertEqual(zahlen["failed"], 1)
            # Ein Fehlversand setzt die Ruhezeit nicht: sonst schweigt der
            # Alarm, weil Telegram einmal 429 gesagt hat.
            self.assertEqual(ledger.last_delivery_times(conn), {"k2": ledger.delivery_rows(conn)[1]["delivered_at"]})

    def test_die_kette_erkennt_eine_veraenderte_zustellzeile(self):
        with self._ledger() as conn:
            ledger.record_deliveries(conn, [self._zustellung("k1"), self._zustellung("k2"), self._zustellung("k3")])
            ok, geprueft = ledger.verify_delivery_chain(conn)
            self.assertTrue(ok)
            self.assertEqual(geprueft, 3)
            conn.execute("UPDATE signals_delivered SET status = 'sent' WHERE dedupe_key = 'k2' AND status = 'sent'")
            conn.execute("UPDATE signals_delivered SET channel = 'email' WHERE dedupe_key = 'k2'")
            conn.commit()
            ok, geprueft = ledger.verify_delivery_chain(conn)
            self.assertFalse(ok)
            self.assertEqual(geprueft, 2)

    def test_die_quote_traegt_n_intervall_stichprobenurteil_und_stand(self):
        with self._ledger() as conn:
            rows = [self._zustellung(f"k{i}") for i in range(9)]
            rows.append(self._zustellung("k9", status="failed", detail="HTTP 400"))
            ledger.record_deliveries(conn, rows)
            zahlen = ledger.delivery_aggregates(conn)
            self.assertEqual(zahlen["attempts"], 10)
            self.assertAlmostEqual(zahlen["delivery_rate"], 0.9, places=6)
            low, high = quant_wilson(9, 10)
            self.assertAlmostEqual(zahlen["delivery_rate_ci95"][0], low, places=6)
            self.assertAlmostEqual(zahlen["delivery_rate_ci95"][1], high, places=6)
            self.assertEqual(zahlen["sample"]["n"], 10)
            self.assertIn(zahlen["sample"]["quality"], ("insufficient", "developing", "adequate"))
            self.assertTrue(zahlen["as_of"])
            self.assertTrue(zahlen["chain_ok"])
            self.assertEqual(zahlen["channels"]["telegram"]["attempts"], 10)
            self.assertEqual(zahlen["channels"]["telegram"]["sent"], 9)

    def test_emittiert_ist_nicht_zugestellt(self):
        # Der Kern des Befunds, mit den Zahlen des Beispiels.
        with self._ledger() as conn:
            frame = pd.DataFrame([
                make_signal(f"Market {i}", market_key=condition_id("a"), outcome=f"Yes{i}")
                for i in range(self.EMITTIERT)
            ])
            self.assertEqual(ledger.emit_signals(conn, frame), self.EMITTIERT)
            ledger.record_deliveries(conn, [
                self._zustellung(f"Fast mover|{condition_id('a')}|Yes{i}|")
                for i in range(self.ANGEKOMMEN)
            ])
            zahlen = ledger.ledger_aggregates(conn)
            self.assertEqual(zahlen["emitted"], self.EMITTIERT)
            self.assertEqual(zahlen["delivered_signals"], self.ANGEKOMMEN)
            self.assertEqual(zahlen["emitted_not_delivered"], self.EMITTIERT - self.ANGEKOMMEN)

    def test_die_trefferquote_der_zugestellten_alerts_zaehlt_nur_zugestellte(self):
        # Zwei Maerkte, beide emittiert, beide aufgeloest: einer gewonnen, einer
        # verloren. Zugestellt wurde nur der verlorene. Ueber alle emittierten
        # Zeilen steht die Quote bei 50 Prozent, ueber die ausgelieferten bei 0.
        with self._ledger() as conn:
            gewonnen = make_signal("Won market", market_key=condition_id("b"), outcome="Yes", price=0.25)
            verloren = make_signal("Lost market", market_key=condition_id("c"), outcome="Yes", price=0.40)
            ledger.emit_signals(conn, pd.DataFrame([gewonnen, verloren]))
            ledger.record_deliveries(conn, [self._zustellung(
                sig_key := f"Fast mover|{condition_id('c')}|Yes|", market_key=condition_id("c"))])
            self.assertTrue(sig_key)
            resolutions = {
                condition_id("b"): {"status": "resolved", "outcome_prices": {"yes": 1.0, "no": 0.0}, "source": "gamma"},
                condition_id("c"): {"status": "resolved", "outcome_prices": {"yes": 0.0, "no": 1.0}, "source": "gamma"},
            }
            self.assertEqual(ledger.resolve_pending(conn, lambda keys: resolutions), 2)
            zahlen = ledger.ledger_aggregates(conn)
            self.assertEqual(zahlen["decisive_units"], 2)
            self.assertAlmostEqual(zahlen["hit_rate_units"], 0.5, places=6)
            self.assertEqual(zahlen["decisive_units_delivered"], 1)
            self.assertEqual(zahlen["hit_rate_delivered_units"], 0.0)
            self.assertEqual(zahlen["delivered_signals"], 1)
            self.assertEqual(zahlen["emitted_not_delivered"], 1)
            self.assertEqual(zahlen["delivery_unknown"], 0)

    def test_zeilen_von_vor_dem_protokoll_gelten_nicht_als_unzugestellt(self):
        with self._ledger() as conn:
            ledger.emit_signals(conn, pd.DataFrame([make_signal("Alt", market_key=condition_id("d"))]))
            conn.execute("UPDATE signals_emitted SET dedupe_key = ''")
            conn.commit()
            zahlen = ledger.ledger_aggregates(conn)
            self.assertEqual(zahlen["delivery_unknown"], 1)
            self.assertEqual(zahlen["emitted_not_delivered"], 0)
            self.assertEqual(zahlen["delivered_signals"], 0)

    def test_der_beste_versuch_faellt_nicht_ueber_ein_kaputtes_protokoll(self):
        with tempfile.TemporaryDirectory() as tmp:
            pfad = Path(tmp) / "nested" / "ledger.sqlite"
            geschrieben, fehler = ledger.safe_record_deliveries([self._zustellung("k1")], pfad)
            self.assertEqual(geschrieben, 1)
            self.assertEqual(fehler, "")
        geschrieben, fehler = ledger.safe_record_deliveries([self._zustellung("k1")], Path("."))
        self.assertEqual(geschrieben, 0)
        self.assertTrue(fehler)


if __name__ == "__main__":
    unittest.main()
