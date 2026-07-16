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


if __name__ == "__main__":
    unittest.main()
