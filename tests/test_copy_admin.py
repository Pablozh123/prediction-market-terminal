"""Tests for app/copy_admin.py — the paper copy desk behind the web page.

What is checked: who may write, how pasted input becomes a wallet, that a
follow lays down the wallet's own baseline, that pause/resume behaves (resume
re-seeds), that settings changes are clamped and never touch live trading,
that the overview reads each sub-account's own books, that the daemon status
is judged for freshness rather than believed, and that the one-shot sync is
single-flight.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from app import copy_admin as ca
from src import copy_trading as ct

WALLET_A = "0x" + "a" * 40
WALLET_B = "0x" + "b" * 40


def _trade(tx: str, ts: int, asset: str = "asset-1") -> dict:
    return {
        "transaction_hash": tx, "asset": asset, "side": "BUY", "price": 0.5, "size": 100.0,
        "timestamp": ts, "market_key": "m-1", "title": "Example", "outcome": "Yes", "time": "2026-05-27T18:00:00Z",
    }


class WriteAccessTests(unittest.TestCase):
    def test_loopback_without_token_may_write(self) -> None:
        access = ca.write_access("127.0.0.1", None, "")
        self.assertTrue(access.allowed)
        self.assertEqual(access.mode, "loopback")
        self.assertTrue(ca.write_access("::1", None, None).allowed)
        self.assertTrue(ca.write_access("::ffff:127.0.0.1", None, None).allowed)

    def test_remote_without_token_is_locked(self) -> None:
        access = ca.write_access("203.0.113.9", None, "")
        self.assertFalse(access.allowed)
        self.assertEqual(access.mode, "locked")
        self.assertIn(ca.ADMIN_TOKEN_ENV, access.reason)

    def test_configured_token_is_required_everywhere(self) -> None:
        self.assertFalse(ca.write_access("127.0.0.1", None, "s3cret").allowed)
        self.assertFalse(ca.write_access("127.0.0.1", "wrong", "s3cret").allowed)
        ok = ca.write_access("203.0.113.9", "s3cret", "s3cret")
        self.assertTrue(ok.allowed)
        self.assertEqual(ok.mode, "token")
        self.assertEqual(ca.write_access("127.0.0.1", "", "s3cret").mode, "token")

    def test_as_dict_carries_the_reason(self) -> None:
        self.assertEqual(set(ca.write_access("127.0.0.1", None, "").as_dict()), {"allowed", "mode", "reason"})


class ResolveWalletTests(unittest.TestCase):
    def test_bare_address_and_profile_url(self) -> None:
        self.assertEqual(ca.resolve_wallet(WALLET_A.upper().replace("0X", "0x")), WALLET_A)
        self.assertEqual(ca.resolve_wallet(f"https://polymarket.com/profile/{WALLET_A}?tab=positions"), WALLET_A)
        self.assertEqual(ca.resolve_wallet("  " + WALLET_A + "  "), WALLET_A)

    def test_handle_needs_a_leaderboard(self) -> None:
        self.assertEqual(ca.resolve_wallet("swisstony"), "")
        lb = pd.DataFrame([{"wallet": WALLET_B, "trader": "SwissTony"}])
        calls: list[str] = []

        def loader(limit, period, order_by):
            calls.append(order_by)
            return lb

        self.assertEqual(ca.resolve_wallet("@swisstony", loader), WALLET_B)
        self.assertEqual(ca.resolve_wallet("nobody-here", loader), "")
        self.assertIn("VOL", calls)  # both slices were tried for the miss

    def test_garbage_is_empty(self) -> None:
        self.assertEqual(ca.resolve_wallet(""), "")
        self.assertEqual(ca.resolve_wallet(None), "")
        self.assertEqual(ca.resolve_wallet("0x1234"), "")


class FollowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "copy.sqlite"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_follow_opens_the_sub_account_and_seeds_its_baseline(self) -> None:
        with patch("src.copy_trading.fetch_source_trades", return_value=pd.DataFrame([_trade("0xh1", 1780000000), _trade("0xh2", 1780000100)])), \
                patch("src.copy_trading.md.get_polymarket_positions", return_value=pd.DataFrame()):
            out = ca.follow(WALLET_A, label="Geo", start_cash=750, note="geopolitics", db_path=self.db)
        self.assertTrue(out["added"])
        self.assertTrue(out["seeded"])
        self.assertIsNone(out["seed_error"])
        self.assertEqual(out["seed"]["processed"], 2)
        conn = ct.connect(self.db)
        try:
            self.assertEqual(ct.wallet_baseline_cutoff(conn, WALLET_A), 1780000100)
            row = conn.execute("SELECT label, note, start_cash, cash, active FROM traders WHERE wallet = ?", (WALLET_A,)).fetchone()
        finally:
            conn.close()
        self.assertEqual((row["label"], row["note"], row["start_cash"], row["cash"], row["active"]), ("Geo", "geopolitics", 750.0, 750.0, 1))

    def test_follow_reports_a_failed_seed_instead_of_raising(self) -> None:
        with patch("src.copy_trading.fetch_source_trades", side_effect=RuntimeError("data api down")):
            out = ca.follow(WALLET_A, db_path=self.db)
        self.assertTrue(out["added"])
        self.assertFalse(out["seeded"])
        self.assertIn("data api down", out["seed_error"])
        # The row exists regardless; the daemon seeds it on its first pass.
        self.assertIn(WALLET_A, ct.active_trader_wallets(db_path=self.db))

    def test_follow_validates_input(self) -> None:
        with self.assertRaises(ValueError):
            ca.follow("swisstony", db_path=self.db)
        with self.assertRaises(ValueError):
            ca.follow(WALLET_A, start_cash=0, db_path=self.db)

    def test_pause_keeps_the_books_and_resume_reseeds(self) -> None:
        with patch("src.copy_trading.fetch_source_trades", return_value=pd.DataFrame([_trade("0xh1", 1780000000)])), \
                patch("src.copy_trading.md.get_polymarket_positions", return_value=pd.DataFrame()):
            ca.follow(WALLET_A, db_path=self.db)
        paused = ca.set_trader(WALLET_A, active=False, db_path=self.db)
        self.assertFalse(paused["active"])
        self.assertFalse(paused["resumed"])
        self.assertNotIn(WALLET_A, ct.active_trader_wallets(db_path=self.db))
        # While paused the source traded; on resume that trade is observed, not copied.
        with patch("src.copy_trading.fetch_source_trades", return_value=pd.DataFrame([_trade("0xwhile-paused", 1780000500)])), \
                patch("src.copy_trading.md.get_polymarket_positions", return_value=pd.DataFrame()):
            resumed = ca.set_trader(WALLET_A, active=True, db_path=self.db)
        self.assertTrue(resumed["resumed"])
        self.assertTrue(resumed["seeded"])
        conn = ct.connect(self.db)
        try:
            self.assertEqual(ct.wallet_baseline_cutoff(conn, WALLET_A), 1780000500)
            status = conn.execute("SELECT status FROM paper_orders WHERE source_tx = '0xwhile-paused'").fetchone()["status"]
        finally:
            conn.close()
        self.assertEqual(status, "seed_observed")
        self.assertIn(WALLET_A, ct.active_trader_wallets(db_path=self.db))

    def test_relabel_does_not_reseed(self) -> None:
        ca.follow(WALLET_A, db_path=self.db, seed=False)
        with patch("app.copy_admin._seed_now") as seed:
            out = ca.set_trader(WALLET_A, label="New name", note="n", db_path=self.db)
        seed.assert_not_called()
        self.assertTrue(out["active"])
        row = ct.get_traders(db_path=self.db).set_index("wallet").loc[WALLET_A]
        self.assertEqual((row["label"], row["note"]), ("New name", "n"))

    def test_unknown_wallet_cannot_be_set(self) -> None:
        with self.assertRaises(KeyError):
            ca.set_trader(WALLET_B, active=False, db_path=self.db)

    def test_top_up_books_a_cash_event_on_that_wallet(self) -> None:
        ca.follow(WALLET_A, start_cash=100, db_path=self.db, seed=False)
        out = ca.top_up(WALLET_A, 50, db_path=self.db)
        self.assertAlmostEqual(out["cash_after"], 150.0)
        events = ct.get_cash_events(db_path=self.db)
        self.assertEqual(str(events.iloc[0]["trader_wallet"]), WALLET_A)
        with self.assertRaises(ValueError):
            ca.top_up(WALLET_A, 0, db_path=self.db)


class SettingsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "copy_settings.json"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_editable_keys_are_applied_and_saved(self) -> None:
        updated = ca.update_settings({"copy_scale": "0.02", "dynamic_sizing_enabled": "false", "cash_throttle_pct": 0.5, "trade_limit": 100}, self.path)
        self.assertAlmostEqual(updated.copy_scale, 0.02)
        self.assertFalse(updated.dynamic_sizing_enabled)
        self.assertAlmostEqual(updated.cash_throttle_pct, 0.5)
        self.assertEqual(updated.trade_limit, 100)
        reloaded = ct.load_copy_settings(self.path)
        self.assertAlmostEqual(reloaded.copy_scale, 0.02)
        self.assertFalse(reloaded.dynamic_sizing_enabled)

    def test_live_trading_cannot_be_enabled_and_unknown_keys_are_ignored(self) -> None:
        updated = ca.update_settings({"live_trading_enabled": True, "target_wallet": WALLET_A, "nonsense": 1}, self.path)
        self.assertFalse(updated.live_trading_enabled)
        self.assertEqual(updated.target_wallet, ct.COPY_TARGET_WALLET)
        self.assertNotIn("live_trading_enabled", ca.settings_view(updated)["editable"])

    def test_bad_values_name_the_field(self) -> None:
        with self.assertRaises(ValueError) as caught:
            ca.update_settings({"copy_scale": "abc"}, self.path)
        self.assertIn("copy_scale", str(caught.exception))
        with self.assertRaises(ValueError):
            ca.update_settings({"max_order_equity_pct": 5}, self.path)
        with self.assertRaises(ValueError):
            ca.update_settings({"auto_top_up_amount": -1}, self.path)
        # Nothing was written by the failed calls.
        self.assertFalse(self.path.exists())


class OverviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "copy.sqlite"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_rows_read_each_sub_account_on_its_own(self) -> None:
        ca.follow(WALLET_A, label="A", start_cash=1000, note="slow", db_path=self.db, seed=False)
        ca.follow(WALLET_B, label="B", start_cash=500, db_path=self.db, seed=False)
        conn = ct.connect(self.db)
        try:
            ct.apply_paper_trade(conn, _trade("0xa1", 1780000000), ct.CopySettings(target_wallet=WALLET_A))
            ct.apply_paper_trade(conn, _trade("0xb1", 1780000001, asset="asset-tiny"), ct.CopySettings(target_wallet=WALLET_B, min_copy_notional=1e9))
            conn.commit()
            ct.record_trader_equity_snapshots(conn=conn, min_interval_seconds=0.0)
        finally:
            conn.close()
        ca.top_up(WALLET_A, 100, db_path=self.db)
        rows = {r["wallet"]: r for r in ca.traders_overview(db_path=self.db)}
        self.assertEqual(set(rows), {ct.COPY_TARGET_WALLET, WALLET_A, WALLET_B})
        a, b = rows[WALLET_A], rows[WALLET_B]
        self.assertEqual(a["label"], "A")
        self.assertEqual(a["note"], "slow")
        self.assertEqual(a["orders"]["copied"], 1)
        self.assertEqual(a["open_positions"], 1)
        self.assertAlmostEqual(a["contributions"], 1100.0)
        # $100 top-up is a contribution, not profit: the position marks at cost.
        self.assertAlmostEqual(a["pnl"], 0.0, places=6)
        self.assertEqual(len(a["equity_curve"]), 1)
        self.assertEqual(b["orders"]["skipped"], 1)
        self.assertEqual(b["orders"]["copied"], 0)
        self.assertAlmostEqual(b["equity"], 500.0)
        self.assertIsNone(b["last_copy_at"])
        self.assertIsNotNone(a["last_copy_at"])
        self.assertTrue(a["profile_url"].endswith(WALLET_A))

    def test_desk_state_bundles_everything(self) -> None:
        state = ca.desk_state(db_path=self.db, settings_path=Path(self.tmp.name) / "s.json", status_path=Path(self.tmp.name) / "none.json")
        self.assertEqual(set(state), {"traders", "active_count", "settings", "daemon", "sync", "totals"})
        self.assertEqual(state["active_count"], 1)  # the seed wallet from the migration
        self.assertIsNone(state["daemon"]["running"])
        self.assertIn("editable", state["settings"])


class DaemonStatusTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "status.json"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _write(self, **payload) -> None:
        self.path.write_text(json.dumps(payload), encoding="utf-8")

    def test_missing_file_is_unknown_not_stopped(self) -> None:
        status = ca.daemon_status(self.path)
        self.assertIsNone(status["running"])
        self.assertIn("has not run", status["reason"])

    def test_fresh_heartbeat_counts_as_running(self) -> None:
        now = datetime(2026, 8, 18, 12, 0, tzinfo=timezone.utc)
        self._write(running=True, pid=4242, mode="paper_ws_chain", last_sync_at=(now - timedelta(seconds=20)).isoformat(), ws_connected=True)
        status = ca.daemon_status(self.path, now=now)
        self.assertTrue(status["running"])
        self.assertFalse(status["stale"])
        self.assertEqual(status["pid"], 4242)
        self.assertTrue(status["ws_connected"])

    def test_stale_running_flag_is_not_believed(self) -> None:
        now = datetime(2026, 8, 18, 12, 0, tzinfo=timezone.utc)
        self._write(running=True, last_sync_at=(now - timedelta(minutes=30)).isoformat())
        status = ca.daemon_status(self.path, now=now)
        self.assertFalse(status["running"])
        self.assertTrue(status["claims_running"])
        self.assertTrue(status["stale"])
        self.assertIn("treat as stopped", status["reason"])

    def test_explicit_stop_is_reported(self) -> None:
        self._write(running=False, stop_reason="stop_file", stopped_at="2026-08-18T11:00:00+00:00")
        status = ca.daemon_status(self.path)
        self.assertFalse(status["running"])
        self.assertIn("stop_file", status["reason"])

    def test_broken_file_is_unknown(self) -> None:
        self.path.write_text("{not json", encoding="utf-8")
        self.assertIsNone(ca.daemon_status(self.path)["running"])


class DaemonStatusWriteTests(unittest.TestCase):
    """scripts/run_copy_trader.py write_status: the Windows rename race must
    not kill the daemon (it did, the second the page was refreshed)."""

    @classmethod
    def setUpClass(cls) -> None:
        import importlib.util
        from pathlib import Path as _P

        script = _P(__file__).resolve().parents[1] / "scripts" / "run_copy_trader.py"
        spec = importlib.util.spec_from_file_location("run_copy_trader_under_test", script)
        cls.mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(cls.mod)

    def test_retries_the_rename_and_never_raises(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        try:
            target = Path(tmp.name) / "status.json"
            calls = {"n": 0}
            real_replace = Path.replace

            def flaky(self_path, dest):
                calls["n"] += 1
                if calls["n"] < 3:
                    raise PermissionError(5, "Zugriff verweigert")
                return real_replace(self_path, dest)

            with patch.object(Path, "replace", flaky):
                self.mod.write_status(target, {"running": True, "pid": 1})
            self.assertEqual(calls["n"], 3)
            self.assertTrue(json.loads(target.read_text(encoding="utf-8"))["running"])
            # Permanently locked: falls back to an in-place write, still no exception.
            with patch.object(Path, "replace", side_effect=PermissionError(5, "locked")):
                self.mod.write_status(target, {"running": False, "pid": 1}, attempts=2)
            self.assertFalse(json.loads(target.read_text(encoding="utf-8"))["running"])
        finally:
            tmp.cleanup()


class SyncPassTests(unittest.TestCase):
    def test_start_sync_is_single_flight_and_records_the_result(self) -> None:
        out = ca.start_sync(runner=lambda: {"api": {"copied": 1}}, in_thread=False)
        self.assertTrue(out["started"])
        state = ca.sync_state()
        self.assertFalse(state["running"])
        self.assertEqual(state["result"], {"api": {"copied": 1}})
        self.assertIsNone(state["error"])

    def test_errors_land_in_the_state(self) -> None:
        def boom():
            raise RuntimeError("upstream 503")

        ca.start_sync(runner=boom, in_thread=False)
        state = ca.sync_state()
        self.assertIn("upstream 503", state["error"])
        self.assertIsNone(state["result"])
        self.assertFalse(state["running"])

    def test_busy_while_a_pass_runs(self) -> None:
        import threading

        gate = threading.Event()
        release = threading.Event()

        def slow():
            gate.set()
            release.wait(5)
            return {"ok": True}

        first = ca.start_sync(runner=slow, in_thread=True)
        self.assertTrue(first["started"])
        gate.wait(5)
        second = ca.start_sync(runner=lambda: {}, in_thread=False)
        self.assertFalse(second["started"])
        self.assertTrue(second["busy"])
        release.set()
        deadline = datetime.now() + timedelta(seconds=5)
        while ca.sync_state()["running"] and datetime.now() < deadline:
            pass
        self.assertFalse(ca.sync_state()["running"])

    def test_run_sync_pass_calls_both_syncs(self) -> None:
        with patch("src.copy_trading.sync_active_copy_trades", return_value={WALLET_A: ct.SyncResult(copied=2)}) as api, \
                patch("src.copy_trading.sync_active_settlement_activity", return_value={WALLET_A: ct.SyncResult(source="settlement")}) as settle, \
                patch("src.copy_trading.value_paper_portfolio", side_effect=RuntimeError("no db")):
            out = ca.run_sync_pass(db_path=Path("nowhere.sqlite"), settings=ct.CopySettings())
        api.assert_called_once()
        settle.assert_called_once()
        self.assertEqual(out["api"]["copied"], 2)
        self.assertEqual(out["settlement"]["wallets"], 1)


if __name__ == "__main__":
    unittest.main()
