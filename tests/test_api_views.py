"""Tests fuer app/api_views.py — das JSON-Mapping der Terminal-API."""

from __future__ import annotations

import json
import unittest
from dataclasses import dataclass, field

import pandas as pd

from app import api_views as apv


class LeaderboardRowsTests(unittest.TestCase):
    def test_merges_smart_scores_and_leaves_winrate_empty(self) -> None:
        lb = pd.DataFrame([
            {"trader": "Theo4", "wallet": "0xAAA1111111111111111111", "pnl": 1000.0, "volume": 50000.0},
            {"trader": "", "wallet": "0xBBB2222222222222222222", "pnl": 500.0, "volume": 20000.0},
        ])
        ranked = pd.DataFrame([
            {"wallet": "0xaaa1111111111111111111", "copy_smart_score": 87.4, "copy_grade": "A", "copy_rank_reason": "return 90"},
        ])
        rows = apv.leaderboard_rows(lb, ranked)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["name"], "Theo4")
        self.assertEqual(rows[0]["score"], 87.4)
        self.assertEqual(rows[0]["grade"], "A")
        self.assertIsNone(rows[0]["win"], "win rate darf ohne Resolved-Fetch nicht erscheinen")
        self.assertIsNone(rows[0]["resolved"])
        self.assertIsNone(rows[1]["score"])
        self.assertTrue(rows[1]["name"].startswith("0xBBB2"), rows[1]["name"])

    def test_empty_frame(self) -> None:
        self.assertEqual(apv.leaderboard_rows(pd.DataFrame()), [])


class WalletDetailTests(unittest.TestCase):
    def test_passes_caveats_through(self) -> None:
        card = {
            "wallet": "0xabc",
            "snapshot_at": "2026-07-31T12:00:00+00:00",
            "track": {"headline_win_rate": 0.61, "resolved_markets": 120, "resolved_capped": True},
            "calibration": {"n": 120, "buckets": pd.DataFrame([{"bucket": 1, "hit": 0.5}])},
            "realized_edge": {"n_events": 90, "edge": 0.03, "ci_low": 0.01, "ci_high": 0.05, "verdict": "positive"},
            "attribution": None,
            "smart": {"copy_smart_score": 80.0, "copy_grade": "A"},
            "risk": None,
            "sample": {"n_resolved": 90, "quality": "adequate", "verdict_allowed": True},
            "errors": {},
        }
        pnl = pd.DataFrame({"time": [1, 2, 3], "pnl": [0.0, 5.0, 3.0]})
        payload = apv.wallet_detail(card, positions=None, pnl_points=pnl)
        self.assertEqual(payload["sample"]["quality"], "adequate")
        self.assertTrue(payload["track"]["resolved_capped"])
        self.assertEqual(payload["pnl_curve"], [0.0, 5.0, 3.0])
        # DataFrame im Kalibrierungsblock muss JSON-tauglich geworden sein.
        self.assertIsInstance(payload["calibration"]["buckets"], list)
        # Ohne Resolved-Frame bleiben die Seitenbloecke leer, aber vorhanden.
        self.assertIn("identity", payload)
        self.assertEqual(payload["closed"]["n"], 0)
        self.assertEqual(payload["edge"]["per_dollar"]["groups"], 0)
        self.assertEqual(payload["activity"]["n_trades"], 0)


def _resolved_fixture(n: int) -> pd.DataFrame:
    """n resolved markets: even indices won (+$40 on $50), odd lost (-$50); markets 1 and 2 share one NegRisk event.

    ``total_bought`` carries the API's unit: SHARES. 100 shares at an average
    of 0.50 are $50 at risk, so a total loss is -$50.
    """

    rows = []
    for i in range(n):
        won = i % 2 == 0
        rows.append({
            "title": ("Will the Fed cut rates in " if i % 3 == 0 else "LoL: Team A vs Team B ") + f"market {i}?",
            "outcome": "Yes",
            "avg_price": 0.5,
            "current_price": 1.0 if won else 0.0,
            "total_bought": 100.0,
            "realized_pnl": 40.0 if won else -50.0,
            "time": pd.Timestamp("2026-06-01", tz="UTC") + pd.Timedelta(i, unit="D"),
            "market_key": f"0xc{i}",
            "url": "https://polymarket.com/event/event-1" if i in (1, 2) else f"https://polymarket.com/event/event-{i}",
        })
    return pd.DataFrame(rows)


def _activity_fixture() -> pd.DataFrame:
    base = pd.Timestamp("2026-07-01T10:00:00", tz="UTC")
    rows = [
        {"time": base, "type": "TRADE", "side": "BUY", "outcome": "Yes", "title": "Will the Fed cut rates in market 0?",
         "price": 0.5, "size": 100.0, "notional": 50.0, "market_key": "0xc0", "slug": "fed-0",
         "url": "https://polymarket.com/event/event-0", "trader": "harness_wallet"},
        {"time": base + pd.Timedelta(1, unit="D"), "type": "TRADE", "side": "BUY", "outcome": "No", "title": "LoL: Team A vs Team B market 1?",
         "price": 0.25, "size": 100.0, "notional": 25.0, "market_key": "0xc1", "slug": "lol-1",
         "url": "https://polymarket.com/event/event-1", "trader": "harness_wallet"},
        {"time": base + pd.Timedelta(2, unit="D"), "type": "TRADE", "side": "SELL", "outcome": "Yes", "title": "Will the Fed cut rates in market 0?",
         "price": 0.6, "size": 50.0, "notional": 30.0, "market_key": "0xc0", "slug": "fed-0",
         "url": "https://polymarket.com/event/event-0", "trader": "harness_wallet"},
        {"time": base + pd.Timedelta(4, unit="D"), "type": "REDEEM", "side": "", "outcome": "Yes", "title": "Will the Fed cut rates in market 0?",
         "price": 0.0, "size": 50.0, "notional": 50.0, "market_key": "0xc0", "slug": "fed-0",
         "url": "https://polymarket.com/event/event-0", "trader": "harness_wallet"},
    ]
    return pd.DataFrame(rows).sort_values("time", ascending=False).reset_index(drop=True)


def _positions_fixture() -> pd.DataFrame:
    return pd.DataFrame([
        {"title": "Open market A?", "outcome": "Yes", "size": 100.0, "avg_price": 0.4, "current_price": 0.55, "value": 55.0,
         "unrealized_pnl": 15.0, "pnl_pct": 0.375, "end_time": pd.Timestamp("2026-12-31", tz="UTC"), "market_key": "0xopenA",
         "url": "https://polymarket.com/event/open-a"},
        {"title": "Resolved against, not redeemed?", "outcome": "No", "size": 20.0, "avg_price": 0.5, "current_price": 0.0, "value": 0.0,
         "unrealized_pnl": -10.0, "pnl_pct": -1.0, "end_time": pd.Timestamp("2026-06-30", tz="UTC"), "market_key": "0xworthless",
         "url": "https://polymarket.com/event/"},
    ])


class WalletPageBlocksTests(unittest.TestCase):
    """Die Bloecke der Wallet-Seite: Zahlen mit n, CI, capped/window_truncated und as_of."""

    def _card(self, resolved: pd.DataFrame, capped: bool, activity: pd.DataFrame | None = None) -> dict:
        from app import calibration as calib
        from app import track_record as trec

        frame = calib.resolution_frame(resolved)
        return {
            "wallet": "0x29afe1bf37700768a640a08f1b35dad5f202f88d",
            "snapshot_at": "2026-08-17T19:00:00+00:00",
            "track": trec.track_record(resolved, None, activity, resolved_capped=capped),
            "calibration": calib.calibration_report(frame, capped=capped),
            "realized_edge": calib.realized_edge(frame, capped=capped),
            "attribution": trec.pnl_attribution(resolved),
            "smart": None, "risk": None,
            "sample": {"n_resolved": 10, "quality": "insufficient", "verdict_allowed": False},
            "errors": {},
        }

    def _classify(self):
        return apv.chained_classifier(lambda raw, title: "", apv.context_group_classifier())

    def test_full_payload_from_fixtures(self) -> None:
        resolved = _resolved_fixture(12)
        activity = _activity_fixture()
        pnl = pd.DataFrame({
            "time": pd.date_range("2026-07-01", periods=6, freq="D", tz="UTC"),
            "pnl": [0.0, 10.0, 5.0, 20.0, 15.0, 30.0],
        })
        payload = apv.wallet_detail(
            self._card(resolved, False, activity), _positions_fixture(), pnl, activity,
            resolved=resolved, resolved_capped=False, activity_truncated=False,
            classify=self._classify(), pseudonym="", as_of="2026-08-17 19:00 UTC",
            positions_requested=250,
        )
        # Legacy keys the drawer reads stay in place.
        for key in ("track", "pnl_curve", "positions", "recent_trades", "sample", "realized_edge"):
            self.assertIn(key, payload)
        self.assertIsInstance(payload["positions"], list)
        # recent_trades lists trades, not redemptions.
        self.assertTrue(all("BUY" in r["side"] or "SELL" in r["side"] for r in payload["recent_trades"]))

        ident = payload["identity"]
        self.assertEqual(ident["short"], "0x29af…f88d")
        self.assertEqual(ident["pseudonym"], "harness_wallet")          # from the activity feed
        self.assertTrue(ident["profile_url"].endswith("/profile/0x29afe1bf37700768a640a08f1b35dad5f202f88d"))
        self.assertIn("polygonscan.com/address/", ident["polygonscan_url"])
        self.assertEqual(ident["first_activity"], "2026-07-01T10:00:00Z")
        self.assertEqual(ident["days_active"], 4.0)
        self.assertFalse(ident["activity_truncated"])

        tr = payload["track_record"]
        self.assertEqual(tr["as_of"], "2026-08-17 19:00 UTC")
        self.assertFalse(tr["capped"])
        # 12 legs, 6 won -> naive 50%; two legs share one event -> 11 events.
        self.assertEqual(tr["naive"]["n"], 12)
        self.assertEqual(tr["naive"]["wins"], 6)
        self.assertAlmostEqual(tr["naive"]["win_rate"], 0.5)
        self.assertEqual(len(tr["naive"]["ci95"]), 2)
        self.assertLess(tr["naive"]["ci95"][0], 0.5)
        self.assertGreater(tr["naive"]["ci95"][1], 0.5)
        self.assertEqual(tr["corrected"]["n"], 11)
        self.assertEqual(tr["legs_netted"], 1)
        self.assertEqual(tr["per_market"]["n"], 12)
        self.assertAlmostEqual(tr["settled_pnl"], 6 * 40.0 - 6 * 50.0)
        self.assertFalse(tr["wash_flag"]["flag"])
        self.assertIn("25,000", tr["wash_flag"]["rule"])
        self.assertEqual(tr["survivorship_gate"]["min_markets"], 10)
        self.assertEqual(tr["survivorship_gate"]["resolved_markets"], 12)
        self.assertEqual(len(tr["concentration"]["top3"]), 3)
        self.assertAlmostEqual(tr["concentration"]["top3_share"], 0.5)   # 3 of 6 equal winners
        self.assertIn(tr["grade"], list("ABCDF"))
        self.assertTrue(tr["score_components"])
        self.assertTrue(all({"label", "value", "max"} <= set(c) for c in tr["score_components"]))
        self.assertAlmostEqual(sum(c["value"] for c in tr["score_components"]), tr["score"], places=0)

        curve = payload["pnl"]
        self.assertEqual(curve["n_points"], 6)
        self.assertEqual(curve["points"][0], {"t": "2026-07-01T00:00:00Z", "pnl": 0.0})
        self.assertEqual(curve["stats"]["n_days"], 5)
        self.assertIsInstance(curve["stats"]["n_days"], int)
        self.assertAlmostEqual(curve["stats"]["total_pnl"], 30.0)
        self.assertAlmostEqual(curve["stats"]["max_drawdown"], 5.0)
        self.assertEqual(curve["stats"]["winning_days"], 3)
        self.assertEqual(curve["stats"]["losing_days"], 2)

        edge = payload["edge"]
        self.assertEqual(edge["per_dollar"]["groups"], 11)
        self.assertAlmostEqual(edge["per_dollar"]["edge"], (6 * 40.0 - 6 * 50.0) / 600.0)
        self.assertIsNotNone(edge["per_dollar"]["ci_low"])
        self.assertLessEqual(edge["per_dollar"]["ci_low"], edge["per_dollar"]["edge"])
        self.assertGreaterEqual(edge["per_dollar"]["ci_high"], edge["per_dollar"]["edge"])
        self.assertEqual(edge["per_share"]["n_events"], 11)
        cats = {r["category"]: r for r in edge["by_category"]}
        self.assertIn("Sports", cats)                                   # "LoL: X vs Y" via the context patterns
        self.assertEqual(sum(r["positions"] for r in edge["by_category"]), 12)

        opened = payload["open_positions"]
        self.assertEqual(opened["n"], 2)
        self.assertFalse(opened["capped"])
        self.assertEqual(opened["worthless_n"], 1)
        self.assertEqual(opened["rows"][0]["title"], "Open market A?")   # sorted by value
        self.assertEqual(opened["rows"][0]["status"], "open")
        self.assertEqual(opened["rows"][1]["status"], "worthless")
        self.assertEqual(opened["rows"][1]["url"], "")                    # "…/event/" is a link to nothing
        self.assertAlmostEqual(opened["total_exposure"], 55.0)
        # Der Verlust der wertlosen Position ist aufgeloest, nicht
        # unrealisiert: er lief bisher in dieselbe Summe (15 - 10 = 5) und
        # stand auf der Seite unter "UNREALISED (open)". Jetzt zeigt die
        # offene Position ihre +15 und der abgeschlossene Verlust steht mit
        # -10 daneben.
        self.assertAlmostEqual(opened["unrealized_pnl"], 15.0)
        self.assertAlmostEqual(opened["worthless_pnl"], -10.0)
        self.assertAlmostEqual(opened["worthless_cost"], 10.0)
        # Kostenbasis und Exposure beschreiben ebenfalls nur die offenen
        # Zeilen (100 x 0.40 = 40, ohne die 20 x 0.50 der wertlosen).
        self.assertAlmostEqual(opened["total_cost"], 40.0)
        self.assertIn("settled, not unrealised", opened["note"])

        closed = payload["closed"]
        self.assertEqual((closed["n"], closed["won"], closed["lost"], closed["flat"]), (12, 6, 6, 0))
        self.assertEqual(closed["worthless_not_redeemed"], 1)
        self.assertFalse(closed["capped"])
        self.assertEqual(closed["rows"][0]["result"], "lost")             # |-50| sorts before |+40|
        self.assertIn("50 rows per tail", closed["source"])

        act = payload["activity"]
        self.assertEqual(act["n_rows"], 4)
        self.assertEqual(act["n_trades"], 3)
        self.assertEqual(act["n_redeems"], 1)
        self.assertEqual((act["buy_n"], act["sell_n"]), (2, 1))
        self.assertAlmostEqual(act["buy_notional"], 75.0)
        self.assertAlmostEqual(act["sell_notional"], 30.0)
        self.assertAlmostEqual(act["redeem_notional"], 50.0)
        self.assertAlmostEqual(act["net_cash_flow"], 5.0)
        self.assertAlmostEqual(act["avg_trade_size"], 35.0)
        self.assertFalse(act["window_truncated"])
        self.assertEqual(act["trades"][0]["url"], "https://polymarket.com/event/event-0")
        self.assertEqual(len(act["trades"]), 3)

        cats = {r["category"]: r for r in payload["categories"]["rows"]}
        self.assertAlmostEqual(cats["Sports"]["stake"], 25.0)
        self.assertEqual(cats["Sports"]["trades"], 1)
        ctx = payload["context"]
        self.assertEqual(ctx["n_trades"], 3)
        groups = {g["group"]: g for g in ctx["groups"]}
        self.assertIn("Sports odds", groups)
        self.assertFalse(groups["Sports odds"]["insider_prone"])
        self.assertAlmostEqual(sum(g["share"] for g in ctx["groups"]), 1.0, places=3)
        self.assertTrue(payload["limits"])
        self.assertTrue(any("closed-positions" in line for line in payload["limits"]))
        # JSON-serialisable end to end.
        json.dumps(payload)

        # Risk profile: from the 12 resolved rows (6 won +$40, 6 lost -$50,
        # alternating in time) and the trading-hours heatmap from the 3 trades.
        rp = payload["risk_profile"]
        self.assertFalse(rp["partial"])
        self.assertEqual(rp["n_rows"], 12)
        self.assertEqual((rp["n_win"], rp["n_loss"]), (6, 6))
        self.assertAlmostEqual(rp["profit_factor"], 240 / 300, places=2)
        self.assertAlmostEqual(rp["risk_reward"], 0.8, places=2)
        self.assertEqual(rp["conviction"], 1.0)  # $50 bought on every row
        self.assertEqual((rp["win_streak"], rp["loss_streak"]), (1, 1))
        self.assertEqual(rp["current_streak_kind"], "loss")  # market 11 lost, last in time
        self.assertEqual(rp["bands"]["profit_factor"], "losing")
        self.assertEqual(rp["bands"]["risk_reward"], "about even")
        self.assertEqual(rp["bands"]["conviction"], "even sizing")
        self.assertIn("n 12 rows, 6 won, 6 lost", rp["note"])
        hm = rp["heatmap"]
        self.assertEqual(hm["n"], 3)
        self.assertEqual(sum(sum(r) for r in hm["counts"]), 3)
        # 2026-07-01 10:00 UTC is a Wednesday (weekday 2), hour 10; two more
        # trades on Thu 10:00 and Fri 10:00.
        self.assertEqual(hm["counts"][2][10], 1)
        self.assertEqual(hm["counts"][3][10], 1)
        self.assertEqual(hm["counts"][4][10], 1)
        self.assertEqual(hm["notional"][2][10], 50.0)
        self.assertEqual(hm["busiest"]["hour"], 10)
        self.assertEqual(hm["tz"], "UTC")

    def test_risk_profile_streaks_partial_and_empty(self) -> None:
        # Three wins in a row then two losses, bigger stakes on the wins;
        # capped tails mark the block PARTIAL.
        rows = []
        for i, (pnl, stake) in enumerate([(10, 100), (20, 120), (5, 80), (-30, 40), (-10, 60)]):
            rows.append({"realized_pnl": pnl, "total_bought": stake, "time": pd.Timestamp("2026-06-01", tz="UTC") + pd.Timedelta(i, unit="D")})
        rp = apv._wallet_risk_profile(pd.DataFrame(rows), True, None, "x")
        self.assertTrue(rp["partial"])
        self.assertEqual(rp["win_streak"], 3)
        self.assertEqual(rp["loss_streak"], 2)
        self.assertEqual(rp["current_streak"], 2)
        self.assertEqual(rp["current_streak_kind"], "loss")
        self.assertAlmostEqual(rp["profit_factor"], round(35 / 40, 2), places=3)
        self.assertAlmostEqual(rp["conviction"], 100 / 50, places=3)
        self.assertEqual(rp["bands"]["conviction"], "sizes up when right")
        self.assertIn("CAPPED", rp["note"])
        self.assertEqual(rp["heatmap"]["n"], 0)
        # Nothing at all: every figure None / 0, no bands, no note.
        empty = apv._wallet_risk_profile(None, False, None, "x")
        self.assertIsNone(empty["profit_factor"])
        self.assertEqual(empty["win_streak"], 0)
        self.assertEqual(empty["bands"], {})
        json.dumps(empty)
        # Only wins: profit factor undefined, band says why.
        wins = pd.DataFrame([{"realized_pnl": 5, "total_bought": 10, "time": pd.Timestamp("2026-06-01", tz="UTC")}])
        only = apv._wallet_risk_profile(wins, False, None, "x")
        self.assertIsNone(only["profit_factor"])
        self.assertEqual(only["bands"]["profit_factor"], "no losing row")

    def test_capped_and_truncated_flags_travel(self) -> None:
        resolved = _resolved_fixture(8)
        payload = apv.wallet_detail(
            self._card(resolved, True), None, None, _activity_fixture(),
            resolved=resolved, resolved_capped=True, activity_truncated=True,
            classify=self._classify(), as_of="2026-08-17 19:00 UTC",
        )
        self.assertTrue(payload["track_record"]["capped"])
        self.assertFalse(payload["track_record"]["win_rate_reliable"])
        self.assertTrue(payload["closed"]["capped"])
        self.assertTrue(payload["edge"]["capped"])
        self.assertEqual(payload["edge"]["per_share"]["verdict"], "capped")
        self.assertTrue(payload["activity"]["window_truncated"])
        self.assertTrue(payload["identity"]["activity_truncated"])
        # Below the survivorship gate: 8 markets < 10.
        self.assertFalse(payload["track_record"]["survivorship_gate"]["ok"])
        self.assertIn("insufficient sample", payload["track_record"]["score_components"][0]["label"])
        # No profile curve -> no profile stats, no invented Sharpe; the block
        # falls back to the settled curve from the 8 capped rows and says so.
        self.assertIsNone(payload["pnl"]["stats"])
        self.assertEqual(payload["pnl"]["points"], [])
        self.assertFalse(payload["pnl"]["flat"])
        self.assertEqual(payload["pnl"]["shown"], "settled")
        self.assertTrue(payload["pnl"]["settled"]["capped"])
        self.assertIn("Capped tails", payload["pnl"]["settled"]["note"])
        self.assertEqual(payload["open_positions"]["n"], 0)

    def test_flat_profile_curve_swaps_to_the_settled_curve(self) -> None:
        # Theo4's case: user-pnl-api's history starts after the wallet's last
        # trade, so the profile curve is one level for 630 points. The block
        # names it flat, sums the closed rows into its own curve (starting at
        # $0 the day before the first resolution) and points the page there.
        resolved = _resolved_fixture(6)          # +40 -50 +40 -50 +40 -50 on 2026-06-01..06
        flat = pd.DataFrame({
            "time": pd.date_range("2026-07-01", periods=630, freq="D", tz="UTC"),
            "pnl": [22053934.0] * 630,
        })
        block = apv._wallet_pnl(flat, "2026-08-18 16:00 UTC", "All", resolved, False)
        self.assertTrue(block["flat"])
        self.assertEqual(block["shown"], "settled")
        self.assertEqual(block["n_points"], 630)
        self.assertEqual(block["first"], "2026-07-01T00:00:00Z")
        self.assertIn("flat line at $22,053,934 over its 630 points (2026-07-01 to 2028-03-21)", block["note"])
        self.assertIsNone(block["stats"]["sharpe"])
        self.assertEqual(block["stats"]["winning_days"], 0)
        settled = block["settled"]
        self.assertEqual(settled["n_rows"], 6)
        self.assertEqual(settled["n_points"], 7)
        self.assertEqual(settled["points"][0], {"t": "2026-05-31T00:00:00Z", "pnl": 0.0})
        self.assertEqual(settled["points"][1], {"t": "2026-06-01T00:00:00Z", "pnl": 40.0})
        self.assertEqual(settled["points"][-1]["pnl"], -30.0)
        self.assertAlmostEqual(settled["total"], -30.0)
        self.assertFalse(settled["capped"])
        self.assertEqual(settled["stats"]["n_days"], 6)
        self.assertEqual(settled["stats"]["winning_days"], 3)
        self.assertEqual(settled["stats"]["losing_days"], 3)
        self.assertAlmostEqual(settled["stats"]["total_pnl"], -30.0)
        self.assertIn("Complete resolved set", settled["note"])
        json.dumps(block)
        # A moving profile curve stays the shown one, settled travels along.
        moving = pd.DataFrame({"time": pd.date_range("2026-07-01", periods=3, freq="D", tz="UTC"), "pnl": [0.0, 5.0, 3.0]})
        block = apv._wallet_pnl(moving, "x", "All", resolved, False)
        self.assertFalse(block["flat"])
        self.assertEqual(block["shown"], "profile")
        self.assertEqual(block["settled"]["n_rows"], 6)
        # Nothing at all: shown is none, settled is None.
        block = apv._wallet_pnl(None, "x", "All", None, False)
        self.assertEqual(block["shown"], "none")
        self.assertIsNone(block["settled"])
        # A flat curve and no closed rows: the flat profile stays shown, flagged.
        block = apv._wallet_pnl(flat, "x", "All", None, False)
        self.assertEqual(block["shown"], "profile")
        self.assertTrue(block["flat"])

    def test_positions_capped_when_the_page_is_full(self) -> None:
        pos = pd.concat([_positions_fixture()] * 5, ignore_index=True)
        payload = apv.wallet_detail({"wallet": "0xabc", "snapshot_at": "", "errors": {}}, pos, None, None,
                                    positions_requested=10, as_of="x")
        self.assertTrue(payload["open_positions"]["capped"])
        self.assertEqual(payload["open_positions"]["n"], 10)


class RiskWalletAddressTests(unittest.TestCase):
    def test_wallet_rows_carry_the_full_address(self) -> None:
        wallets = pd.DataFrame([{
            "wallet": "0xbbb2000000000000000000000000000000000002", "trader": "", "top_market": "Example",
            "wallet_insider_score": 71.0, "trade_count": 3, "notional": 40000.0, "first_seen": "2026-08-17T09:40:00Z",
        }])
        payload = apv.risk_payload(wallets, pd.DataFrame())
        self.assertEqual(payload["wallets"][0]["address"], "0xbbb2000000000000000000000000000000000002")
        self.assertEqual(payload["wallets"][0]["wallet"], "0xbbb2…0002")

    def test_wallet_rows_explain_the_score_and_keep_small_dollars(self) -> None:
        # The score alone said nothing: the row now carries the scorer's own
        # reasons, and a $450 wallet reads "$450", not "$0k".
        wallets = pd.DataFrame([{
            "wallet": "0xbbb2000000000000000000000000000000000002", "trader": "", "top_market": "Example",
            "wallet_insider_score": 55.0, "trade_count": 1, "notional": 450.0, "largest_trade": 450.0,
            "first_seen": "2026-08-17", "wallet_insider_flags": "long-odds big bet; late-market flow",
        }])
        row = apv.risk_payload(wallets, pd.DataFrame())["wallets"][0]
        self.assertEqual(row["flags"], ["long-odds big bet", "late-market flow"])
        self.assertEqual(row["notional"], "$450")
        self.assertEqual(row["largest"], "$450")
        self.assertNotIn("cluster", row)


class CrossRowsTests(unittest.TestCase):
    def test_maps_candidate_frame(self) -> None:
        frame = pd.DataFrame([
            {
                "polymarket_title": "Fed cuts rates", "kalshi_title": "Fed cut",
                "polymarket_yes": 0.62, "kalshi_yes": 0.60,
                "polymarket_volume_usd": 100000.0, "kalshi_volume_contracts": 40000.0,
                "similarity": 0.71,
            },
            {"polymarket_title": "broken", "polymarket_yes": None, "kalshi_yes": 0.5},
        ])
        rows = apv.cross_rows(frame)
        self.assertEqual(len(rows), 1, "Zeilen ohne beide Preise fliegen raus")
        self.assertEqual(rows[0]["pm"], 62)
        self.assertEqual(rows[0]["ks"], 60)
        self.assertEqual(rows[0]["sim"], 0.71)


class RiskPayloadTests(unittest.TestCase):
    def test_builds_kpis_and_disclaimer(self) -> None:
        wallets = pd.DataFrame([
            {"wallet": "0x1234567890abcdef000000", "trader": "", "wallet_insider_score": 84.0,
             "trade_count": 9, "notional": 212000.0, "first_seen": "2026-07-25T10:00:00Z", "top_market": "Fed cuts"},
            {"wallet": "0x2222222222222222222222", "trader": "quiet", "wallet_insider_score": 41.0,
             "trade_count": 2, "notional": 38000.0, "first_seen": "2023-01-01", "top_market": ""},
        ])
        events = pd.DataFrame([
            {"title": "Iraq win", "event_insider_score": 82.0, "event_insider_level": "High",
             "event_insider_flags": ["coordinated burst"], "unique_wallets": 6,
             "notional": 214000.0, "trades_per_hour": 12.0, "platform": "Polymarket"},
        ])
        payload = apv.risk_payload(wallets, events)
        self.assertIn("research leads", payload["disclaimer"])
        self.assertEqual(payload["kpis"]["high_risk_wallets"], 1)
        self.assertEqual(payload["kpis"]["high_risk_events"], 1)
        self.assertEqual(payload["events"][0]["kind"], "COORDINATED BURST")
        self.assertEqual(payload["wallets"][0]["score"], 84)

    def test_events_below_the_flag_threshold_are_counted_not_shown(self) -> None:
        # Der Scorer bewertet JEDEN Markt mit einem Print im Tape; ohne Boden
        # fuellten "0/100"-Zeilen das Grid, sobald das gefilterte Tape duenn
        # war. Karten gibt es ab der Log-Schwelle (risk_log.min_score(), 40);
        # was darunter liegt, wird gezaehlt statt gezeigt.
        events = pd.DataFrame([
            {"title": "Cabinet reshuffle", "event_insider_score": 62.0, "event_insider_level": "Medium",
             "event_insider_flags": "one-sided flow", "unique_wallets": 3, "notional": 80000.0,
             "trades_per_hour": 8.0, "platform": "Polymarket"},
            {"title": "Tiny market", "event_insider_score": 0.0, "event_insider_level": "Low",
             "event_insider_flags": "", "unique_wallets": 1, "notional": 45.0,
             "trades_per_hour": 1.0, "platform": "Polymarket"},
            {"title": "Small market", "event_insider_score": 12.0, "event_insider_level": "Low",
             "event_insider_flags": "watch only", "unique_wallets": 1, "notional": 900.0,
             "trades_per_hour": 2.0, "platform": "Kalshi"},
        ])
        payload = apv.risk_payload(pd.DataFrame(), events)
        self.assertEqual([e["market"] for e in payload["events"]], ["Cabinet reshuffle"])
        self.assertEqual(payload["event_min_score"], 40)
        self.assertEqual(payload["events_below_min"], 2)
        # events_screened zaehlt die gescorten Maerkte, nicht die Karten —
        # vorher stand hier len(events) und die Zahl log.
        self.assertEqual(payload["kpis"]["events_screened"], 3)
        self.assertEqual(payload["kpis"]["events_flagged"], 1)

    def test_all_events_below_threshold_leave_an_empty_screen_with_counts(self) -> None:
        events = pd.DataFrame([
            {"title": "Tiny market", "event_insider_score": 2.0, "event_insider_level": "Low",
             "event_insider_flags": "", "unique_wallets": 1, "notional": 45.0,
             "trades_per_hour": 1.0, "platform": "Polymarket"},
            {"title": "Small market", "event_insider_score": 31.0, "event_insider_level": "Low",
             "event_insider_flags": "watch only", "unique_wallets": 2, "notional": 3200.0,
             "trades_per_hour": 2.0, "platform": "Kalshi"},
        ])
        payload = apv.risk_payload(pd.DataFrame(), events)
        self.assertEqual(payload["events"], [])
        self.assertEqual(payload["events_below_min"], 2)
        self.assertEqual(payload["kpis"]["events_screened"], 2)
        self.assertEqual(payload["kpis"]["events_flagged"], 0)

    def test_threshold_override_zero_shows_every_scored_row(self) -> None:
        events = pd.DataFrame([
            {"title": "Tiny market", "event_insider_score": 0.0, "event_insider_level": "Low",
             "event_insider_flags": "", "unique_wallets": 1, "notional": 45.0,
             "trades_per_hour": 1.0, "platform": "Polymarket"},
        ])
        payload = apv.risk_payload(pd.DataFrame(), events, min_event_score=0.0)
        self.assertEqual(len(payload["events"]), 1)
        self.assertEqual(payload["events_below_min"], 0)

    def test_cluster_kpis_start_unmeasured_not_at_zero(self) -> None:
        """The cluster stage runs later and may never run at all. A hard 0 here
        rendered in the KPI tile as a measured "no clusters found"; None draws
        as an em dash, which is what an unmeasured number should look like."""
        payload = apv.risk_payload(pd.DataFrame(), pd.DataFrame())
        self.assertIsNone(payload["kpis"]["fresh_clusters"])
        self.assertIsNone(payload["kpis"]["coordinated_clusters"])

    def test_cluster_payload_fills_the_kpis_in_with_real_counts(self) -> None:
        payload = apv.risk_payload(pd.DataFrame(), pd.DataFrame())
        payload["kpis"].update(apv.cluster_payload(
            pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
        ).pop("kpis_clusters"))
        self.assertEqual(payload["kpis"]["fresh_clusters"], 0)
        self.assertEqual(payload["kpis"]["coordinated_clusters"], 0)


class NetworkGraphPayloadTests(unittest.TestCase):
    """A cluster picture without its denominator, its control and its snapshot
    time cannot be placed by anyone reading it."""

    def _frames(self):
        nodes = pd.DataFrame([
            {"wallet": "0xa", "cluster_id": 1, "x": 0.0, "y": 0.0, "volume": 10_000.0,
             "markets": 3, "trades": 5, "shared_markets": 2},
            {"wallet": "0xb", "cluster_id": 1, "x": 1.0, "y": 1.0, "volume": 8_000.0,
             "markets": 3, "trades": 4, "shared_markets": 2},
        ])
        edges = pd.DataFrame([{"wallet_a": "0xa", "wallet_b": "0xb", "shared_markets": 3,
                               "pair_notional": 18_000.0, "expected_shared": 0.6, "lift": 5.0}])
        return nodes, edges

    def test_edges_carry_expectation_and_lift(self) -> None:
        graph = apv.network_graph(*self._frames())
        self.assertEqual(graph["kanten"][0]["erwartet"], 0.6)
        self.assertEqual(graph["kanten"][0]["lift"], 5.0)
        self.assertEqual(graph["kennzahl"]["lift_median"], 5.0)

    def test_lift_that_cannot_be_computed_stays_none(self) -> None:
        nodes, edges = self._frames()
        edges.loc[0, "lift"] = float("nan")
        graph = apv.network_graph(nodes, edges)
        self.assertIsNone(graph["kanten"][0]["lift"])
        self.assertNotIn("lift_median", graph["kennzahl"])

    def test_denominator_control_and_snapshot_ride_along(self) -> None:
        graph = apv.network_graph(
            *self._frames(),
            regel="same side of at least 2 markets",
            wallets_im_tape=300,
            nullmodell={"runs": 2, "cluster": 4, "kanten": 846},
            stand_utc="2026-08-28T09:00:00+00:00")
        self.assertEqual(graph["kennzahl"]["wallets"], 2)
        self.assertEqual(graph["kennzahl"]["wallets_im_tape"], 300)
        self.assertEqual(graph["nullmodell"]["cluster"], 4)
        self.assertEqual(graph["stand_utc"], "2026-08-28T09:00:00+00:00")

    def test_missing_context_is_left_out_rather_than_faked(self) -> None:
        graph = apv.network_graph(*self._frames())
        self.assertNotIn("nullmodell", graph)
        self.assertNotIn("stand_utc", graph)
        self.assertNotIn("wallets_im_tape", graph["kennzahl"])


class AlertRowsTests(unittest.TestCase):
    def test_maps_signal_frame(self) -> None:
        signals = pd.DataFrame([
            {"signal_type": "Whale print", "time": "2026-07-31T14:18:22Z", "title": "Brazil win",
             "platform": "Polymarket", "notional": 18400.0, "reason": "big print"},
            {"signal_type": "Watched market", "time": "2026-07-31 13:02:10", "title": "CPI",
             "platform": "Kalshi", "notional": None, "reason": "on the watchlist"},
        ])
        rows = apv.alert_rows(signals)
        self.assertEqual(rows[0]["rule"], "WHALE PRINT")
        self.assertEqual(rows[0]["time"], "14:18")
        self.assertEqual(rows[0]["value"], "$18,400")
        self.assertTrue(rows[1]["watched"])

    def test_counts_cover_the_whole_scan_not_the_shown_rows(self) -> None:
        # Der Feed schneidet nach ALERT_ROW_LIMIT ab. Wer die Treffer aus den
        # gezeigten Zeilen zaehlt, meldet fuer die abgeschnittene Art null,
        # obwohl der Scan sie gefunden hat.
        viele = [
            {"signal_type": "Ending soon", "time": "2026-07-31T14:00:00Z", "title": f"m{i}",
             "platform": "Polymarket", "value": 0.5, "reason": "ends soon"}
            for i in range(apv.ALERT_ROW_LIMIT + 5)
        ]
        viele.append({"signal_type": "Whale print", "time": "2026-07-31T13:00:00Z",
                      "title": "late whale", "platform": "Polymarket", "notional": 9000.0,
                      "reason": "big print"})
        signals = pd.DataFrame(viele)

        rows = apv.alert_rows(signals)
        self.assertEqual(len(rows), apv.ALERT_ROW_LIMIT)
        self.assertNotIn("WHALE PRINT", {r["rule"] for r in rows})

        counts = apv.alert_rule_counts(signals)
        self.assertEqual(counts["WHALE PRINT"], 1)
        self.assertEqual(counts["ENDING SOON"], apv.ALERT_ROW_LIMIT + 5)

    def test_counts_on_an_empty_frame(self) -> None:
        self.assertEqual(apv.alert_rule_counts(pd.DataFrame()), {})


class CopyPayloadTests(unittest.TestCase):
    def test_builds_status_kpis_and_rows(self) -> None:
        orders = pd.DataFrame([
            {"source_time": "2026-07-31T14:19:00Z", "title": "Brazil win", "copy_side": "buy",
             "outcome": "No", "source_notional": 18400.0, "copy_notional": 7728.0, "status": "copied"},
            {"source_time": "2026-07-31T13:04:00Z", "title": "Germany win", "copy_side": "buy",
             "outcome": "No", "source_notional": 11200.0, "copy_notional": 0.0, "status": "skipped"},
        ])
        positions = pd.DataFrame([
            {"title": "Brazil win", "outcome": "No", "size": 186.2, "avg_price": 0.415, "current_price": 0.435},
        ])
        cash = pd.DataFrame([{"created_at": "2026-05-31T00:00:00Z", "reason": "Start cash", "amount": 1000.0}])
        equity = pd.DataFrame({"equity": [1000.0, 1020.0, 1043.18]})
        portfolio = {"cash": 312.40, "position_value": 730.78, "equity": 1043.18, "realized_pnl": 20.0, "unrealized_pnl": 23.18}
        payload = apv.copy_payload(orders, positions, cash, equity, portfolio, 1000.0, "0x204f72f35326db932158cba6adff0b9a1da95e14", "Swisstony", {"effective_copy_scale": 0.42})
        self.assertEqual(payload["kpis"]["mirrored"], 1)
        self.assertEqual(payload["kpis"]["skipped"], 1)
        self.assertAlmostEqual(payload["kpis"]["pnl"], 43.18, places=2)
        self.assertEqual(payload["status"]["scale"], 0.42)
        self.assertIn("Swisstony", payload["status"]["source"])
        self.assertEqual(payload["orders"][0]["side"], "BUY No")
        self.assertEqual(payload["orders"][0]["kind"], "BUY")
        self.assertEqual(payload["positions"][0][0], "Brazil win")
        self.assertEqual(payload["equity_curve"][-1], 1043.18)

    def test_penny_copies_show_cents_instead_of_dollar_zero(self) -> None:
        # A $1k sub-account copying a $1.2M whale fills pennies per order;
        # whole-dollar rounding rendered every one of them as "$0" and the
        # Orders tab read as broken. Cents stay visible, true zero stays "$0".
        orders = pd.DataFrame([
            {"source_time": "2026-08-20T19:45:00Z", "title": "Penny copy", "copy_side": "buy",
             "outcome": "Yes", "source_notional": 34.0, "copy_notional": 0.03, "status": "copied"},
            {"source_time": "2026-08-20T19:44:00Z", "title": "Big copy", "copy_side": "buy",
             "outcome": "Yes", "source_notional": 2307.0, "copy_notional": 1234.56, "status": "copied"},
            {"source_time": "2026-08-20T19:43:00Z", "title": "Observed", "copy_side": "buy",
             "outcome": "Yes", "source_notional": 500.0, "copy_notional": 0.0, "status": "seed_observed"},
            {"source_time": "2026-08-20T19:42:00Z", "title": "Sub-cent copy", "copy_side": "buy",
             "outcome": "Yes", "source_notional": 3.75, "copy_notional": 0.003, "status": "copied"},
        ])
        payload = apv.copy_payload(orders, pd.DataFrame(), pd.DataFrame(), pd.DataFrame(),
                                   {"cash": 1000.0, "equity": 1000.0}, 1000.0, "0x" + "a" * 40, "x", {})
        penny, big, observed, subcent = payload["orders"]
        self.assertEqual(penny["yours"], "$0.03")
        self.assertEqual(penny["theirs"], "$34.00")
        self.assertEqual(big["yours"], "$1,235")
        self.assertEqual(big["theirs"], "$2,307")
        self.assertEqual(observed["yours"], "$0")
        self.assertEqual(subcent["yours"], "<$0.01")

    def test_merges_and_settlements_say_what_they_are_and_carry_the_source_book(self) -> None:
        # The row that confused the reader: source_side MERGE with outcome
        # "Yes" read like a YES bet, while the wallet was net NO. The kind says
        # MERGE, the sentence says both sides went back for cash, and the book
        # line says what the source holds in that market now.
        w = "0x" + "a" * 40
        orders = pd.DataFrame([
            {"source_time": "2026-08-17T10:00:00Z", "title": "Iran fees Hormuz until 31 Aug", "source_side": "MERGE",
             "outcome": "Yes", "source_notional": 3000.0, "copy_notional": 30.0, "status": "settled",
             "reason": "merge_complete_set", "source_wallet": w, "market_key": "0xcond"},
            {"source_time": "2026-08-17T09:00:00Z", "title": "Iran fees Hormuz until 31 Aug", "source_side": "REDEEM",
             "outcome": "No", "source_notional": 500.0, "copy_notional": 5.0, "status": "settled",
             "reason": "redeem_resolution", "source_wallet": w, "market_key": "0xother"},
            {"source_time": "2026-08-17T08:00:00Z", "title": "Old market", "source_side": "",
             "outcome": "Yes", "source_notional": 0.0, "copy_notional": 0.0, "status": "settled",
             "reason": "resolution_loser_loss", "source_wallet": w, "market_key": "0xold"},
            {"source_time": "2026-08-17T07:00:00Z", "title": "Iran fees Hormuz until 31 Aug", "source_side": "BUY",
             "outcome": "Yes", "source_notional": 1000.0, "copy_notional": 10.0, "status": "copied",
             "reason": "buy_scaled", "source_wallet": w, "market_key": "0xcond"},
        ])
        source_positions = pd.DataFrame([
            {"wallet": w, "market_key": "0xcond", "outcome": "No", "shares": 12000.0},
            {"wallet": w, "market_key": "0xcond", "outcome": "Yes", "shares": 100.0},
        ])
        payload = apv.copy_payload(orders, pd.DataFrame(), pd.DataFrame(), pd.DataFrame(),
                                   {"cash": 1000.0, "equity": 1000.0}, 1000.0, w, "x", {}, source_positions=source_positions)
        merge, redeem, resolution, buy = payload["orders"]
        self.assertEqual(merge["kind"], "MERGE")
        self.assertIn("both sides", merge["explain"])
        self.assertIn("not a bet on Yes", merge["explain"])
        self.assertEqual(merge["book"], "source book now: 100 YES / 12.0k NO → net NO")
        self.assertEqual(redeem["kind"], "REDEEM")
        self.assertEqual(redeem["book"], "")  # no mirror row for that market
        self.assertEqual(resolution["kind"], "RESOLUTION")
        self.assertIn("against Yes", resolution["explain"])
        self.assertEqual(buy["kind"], "BUY")
        self.assertEqual(buy["book"], merge["book"])
        # Without the mirror the book line stays empty rather than "flat".
        bare = apv.copy_payload(orders, pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), {"cash": 1000.0, "equity": 1000.0}, 1000.0, w, "x", {})
        self.assertEqual(bare["orders"][0]["book"], "")

    def test_source_book_line_wording(self) -> None:
        self.assertEqual(apv.source_book_line({"yes": 0.0, "no": 0.0}), "source book now: flat in this market")
        self.assertEqual(apv.source_book_line({"yes": 950.0, "no": 1000.0}), "source book now: 950 YES / 1.0k NO → balanced")
        self.assertEqual(apv.source_book_line(None), "")


@dataclass
class _FakeResult:
    stats: dict
    benchmark_stats: dict
    equity: pd.DataFrame
    ledger: pd.DataFrame
    open_positions: pd.DataFrame = field(default_factory=pd.DataFrame)


class BacktestPayloadTests(unittest.TestCase):
    def test_maps_result_and_keeps_truncation_flag(self) -> None:
        result = _FakeResult(
            stats={"final_equity": 1120.0, "roi": 0.12, "total_pnl": 120.0, "win_rate": 0.6,
                   "wins": 6, "losses": 4, "max_drawdown": -0.08, "copied_trades": 10,
                   "skipped_trades": 3, "fees_paid": 2.5, "open_value": 80.0, "window_truncated": True,
                   "realized_pnl": 95.0, "unrealized_pnl": 25.0, "open_positions": 2},
            benchmark_stats={"total_pnl": 60.0},
            equity=pd.DataFrame({"equity": [1000.0, 1120.0], "benchmark": [1000.0, 1060.0], "drawdown": [0.0, -0.02]}),
            ledger=pd.DataFrame([
                {"time": "2026-07-30T14:19:00Z", "action": "BUY", "status": "copied", "title": "Brazil win",
                 "outcome": "No", "source_notional": 18400.0, "stake": 25.0, "exec_price": 0.415,
                 "fee": 0.05, "equity_after": 1010.0},
            ]),
        )
        payload = apv.backtest_payload(result)
        self.assertTrue(payload["stats"]["window_truncated"])
        self.assertEqual(payload["equity"], [1000.0, 1120.0])
        self.assertEqual(payload["log"][0]["action"], "BUY")
        self.assertEqual(payload["benchmark_stats"]["total_pnl"], 60.0)
        # Der noch offene Teil des Ergebnisses muss mitreisen: 25 der 120
        # Dollar stecken in Maerkten, die am Fensterende nicht entschieden
        # waren, und stehen nur zum letzten Preis darin.
        self.assertEqual(payload["stats"]["realized_pnl"], 95.0)
        self.assertEqual(payload["stats"]["unrealized_pnl"], 25.0)
        self.assertEqual(payload["stats"]["open_positions"], 2)

    def test_payload_carries_the_win_rate_denominator(self) -> None:
        """Die Trefferquote braucht ihren Nenner, sonst rechnet die Seite ihn falsch.

        Die Kachel rechnete wins / copied_trades. copied_trades zaehlt alle
        kopierten BUY- und SELL-Zeilen, also auch die noch offenen Einstiege:
        100 Kopien, 60 davon geschlossen (35 gewonnen), 40 noch offen ergaben
        35 Prozent statt der gemessenen 58.3 Prozent. Der Nenner steht in
        stats["closed_trades"] und muss mitgeliefert werden.
        """

        result = _FakeResult(
            stats={"final_equity": 1000.0, "roi": 0.0, "total_pnl": 0.0, "win_rate": 35 / 60,
                   "wins": 35, "losses": 25, "max_drawdown": 0.0, "copied_trades": 100,
                   "closed_trades": 60, "skipped_trades": 0, "fees_paid": 0.0, "open_value": 400.0},
            benchmark_stats={},
            equity=pd.DataFrame({"equity": [1000.0, 1000.0]}),
            ledger=pd.DataFrame(),
        )
        stats = apv.backtest_payload(result)["stats"]
        self.assertEqual(stats["closed_trades"], 60)
        self.assertEqual(stats["copied_trades"], 100)
        self.assertAlmostEqual(stats["wins"] / stats["closed_trades"], 0.5833, places=4)
        # Der frueher benutzte Nenner haette 35 Prozent ergeben.
        self.assertAlmostEqual(stats["wins"] / stats["copied_trades"], 0.35, places=4)


class PipelineTrimTests(unittest.TestCase):
    def test_slims_run_entries_and_drops_word_counters(self) -> None:
        # Die Lauf-Eintraege bleiben VOLLZAEHLIG erhalten (die Seite zaehlt
        # den Trichter darueber), aber je Eintrag nur action und reason —
        # frueher flogen sie ganz raus und die Kopfzeile zaehlte nur die
        # gekappte Spiegel-Liste eines einzigen Laufs.
        payload = {
            "hinweis": "x",
            "eintraege": [{"a": i} for i in range(200)],
            "wortzaehler_endstaende": {"m": 3},
            "laeufe": [{
                "profil": "p1", "n_eintraege": 2, "wortzaehler_endstaende": {"m": 1},
                "eintraege": [
                    {"action": "NONE", "reason": "kein_yes_ask", "limit_price": None, "bestes_angebot": 0.9, "size_usd": 0.0},
                    {"action": "YES", "reason": "count 2 >= ziel 1", "limit_price": 0.8, "bestes_angebot": 0.8, "size_usd": 12.0},
                ],
            }],
        }
        out = apv.trim_pipeline_payload(payload, max_entries=40)
        self.assertEqual(len(out["eintraege"]), 40)
        self.assertNotIn("wortzaehler_endstaende", out)
        self.assertNotIn("wortzaehler_endstaende", out["laeufe"][0])
        self.assertEqual(out["laeufe"][0]["eintraege"], [
            {"action": "NONE", "reason": "kein_yes_ask"},
            {"action": "YES", "reason": "count 2 >= ziel 1"},
        ])
        self.assertEqual(out["laeufe"][0]["n_eintraege"], 2)
        # Original bleibt unangetastet
        self.assertEqual(len(payload["eintraege"]), 200)
        self.assertIn("size_usd", payload["laeufe"][0]["eintraege"][0])




class ResolvedRowsTests(unittest.TestCase):
    def test_maps_closed_markets_and_skips_multi(self) -> None:
        closed = pd.DataFrame([
            {"title": "Fed holds in July", "platform": "Polymarket", "category": "Economy",
             "resolved_outcome": "Yes", "final_yes_price": 0.81, "decisive_resolution": False,
             "closed_time": pd.Timestamp.now(tz="UTC") - pd.Timedelta(hours=9), "volume": 8400000.0},
            {"title": "Multi outcome", "platform": "Polymarket", "category": "Politics",
             "resolved_outcome": "Multi", "final_yes_price": 0.4, "decisive_resolution": False,
             "closed_time": pd.Timestamp.now(tz="UTC"), "volume": 100.0},
        ])
        rows = apv.resolved_rows(closed)
        self.assertEqual(len(rows), 1, "Multi-Outcome-Maerkte fliegen raus")
        self.assertEqual(rows[0]["err"], 19)
        self.assertTrue(rows[0]["yes"])
        self.assertIn("h ago", rows[0]["when"])


class TrackPayloadTests(unittest.TestCase):
    def test_joins_leaderboard_and_grades(self) -> None:
        lb = pd.DataFrame([{"wallet": "0xAAA1111111111111111111", "trader": "Theo4", "pnl": 22050000.0}])
        ranked = pd.DataFrame([{"wallet": "0xaaa1111111111111111111", "copy_grade": "A"}])
        payload = apv.track_payload(["0xAAA1111111111111111111", "0xBBB2222222222222222222"],
                                    [{"platform": "Polymarket", "market_key": "0xcond", "title": "Fed cuts", "url": "u"}],
                                    ranked, lb)
        self.assertEqual(payload["wallets"][0]["name"], "Theo4")
        self.assertEqual(payload["wallets"][0]["grade"], "A")
        self.assertIsNone(payload["wallets"][1]["pnl"])
        self.assertEqual(payload["watchlist"][0]["market_key"], "0xcond")


class ResearchFilesTests(unittest.TestCase):
    def test_microstructure_wird_wie_die_uebrigen_studien_serviert(self) -> None:
        """Microstructure kommt aus public/data, nicht aus einem Sonderpfad."""
        self.assertEqual(apv.RESEARCH_FILES["microstructure"], "microstructure")


class LiveRunsExtrasTests(unittest.TestCase):
    def test_sims_calibration_and_monthly(self) -> None:
        payload = {"runs": [{
            "profil": "test_run",
            "wetten": [
                {"frage": "Says X", "seite": "YES", "entscheidungs_preis": 0.5, "avg_fill_preis": 0.5,
                 "shares": 50.0, "einsatz_usd": 25.0, "aufgeloest": True, "gewonnen": True,
                 "pnl_usd": 25.0, "fill_ts_utc": "2026-07-24T12:00:00Z"},
                {"frage": "Says Y", "seite": "YES", "entscheidungs_preis": 0.4, "avg_fill_preis": 0.4,
                 "shares": 62.5, "einsatz_usd": 25.0, "aufgeloest": True, "gewonnen": False,
                 "pnl_usd": -25.0, "fill_ts_utc": "2026-07-25T12:00:00Z"},
            ],
        }]}
        extras = apv.live_runs_extras(payload)
        self.assertIn("sims", extras)
        self.assertEqual(extras["sims"][0]["bets"], 2)
        self.assertIn("monthly", extras)
        self.assertEqual(extras["monthly"][0]["month"], "2026-07")
        self.assertEqual(extras["monthly"][0]["bets"], 2)
        self.assertAlmostEqual(extras["monthly"][0]["net"], 0.0, places=2)

    def test_monthly_carries_the_settled_stake_as_its_own_basis(self) -> None:
        """Der Zaehler zaehlt nur aufgeloeste Wetten, der Nenner muss das auch.

        Die Monatstabelle rechnete net / stake ueber alle Wetten des Monats,
        offene eingeschlossen. Ein Monat mit $100 Einsatz, davon $40 in noch
        offenen Wetten, und +$18 aus den aufgeloesten stand mit +18.0 Prozent
        da; auf den aufgeloesten Einsatz gerechnet sind es +30.0 Prozent.
        """

        wetten = [
            {"einsatz_usd": 60.0, "aufgeloest": True, "gewonnen": True, "pnl_usd": 18.0,
             "fill_ts_utc": "2026-07-10T12:00:00Z", "seite": "YES", "entscheidungs_preis": 0.5,
             "avg_fill_preis": 0.5, "shares": 120.0, "frage": "Says A"},
            {"einsatz_usd": 40.0, "aufgeloest": False, "pnl_usd": None,
             "fill_ts_utc": "2026-07-11T12:00:00Z", "seite": "YES", "entscheidungs_preis": 0.5,
             "avg_fill_preis": 0.5, "shares": 80.0, "frage": "Says B"},
        ]
        monat = apv.live_runs_extras({"runs": [{"profil": "p", "wetten": wetten}]})["monthly"][0]
        self.assertEqual(monat["bets"], 2)
        self.assertEqual(monat["settled_bets"], 1)
        self.assertAlmostEqual(monat["stake"], 100.0)
        self.assertAlmostEqual(monat["settled_stake"], 60.0)
        self.assertAlmostEqual(monat["net"], 18.0)
        self.assertAlmostEqual(monat["net"] / monat["settled_stake"], 0.30, places=4)
        # Der frueher benutzte Nenner haette 18 Prozent ergeben.
        self.assertAlmostEqual(monat["net"] / monat["stake"], 0.18, places=4)

    def test_wallet_ledger_rides_along_when_published(self) -> None:
        """extras.wallet_ledger is the published file, or absent when there is none."""
        import json
        from pathlib import Path
        from tempfile import TemporaryDirectory

        payload = {"runs": []}
        with TemporaryDirectory() as tmp:
            self.assertNotIn("wallet_ledger", apv.live_runs_extras(payload, publish_dir=Path(tmp)))
            ledger = {"kennzeichnung": "wallet/public-api", "wallet": "0xabc", "aggregat": {"n_events": 2}, "events": []}
            (Path(tmp) / "wallet_ledger.json").write_text(json.dumps(ledger), encoding="utf-8")
            extras = apv.live_runs_extras(payload, publish_dir=Path(tmp))
            self.assertEqual(extras["wallet_ledger"]["aggregat"]["n_events"], 2)
            self.assertEqual(extras["wallet_ledger"]["kennzeichnung"], "wallet/public-api")
        # The same file is also served as its own study.
        self.assertEqual(apv.RESEARCH_FILES["wallet-ledger"], "wallet_ledger")


class ClusterPayloadTests(unittest.TestCase):
    def test_maps_suspicion_frames(self) -> None:
        fresh = pd.DataFrame([{"platform": "Polymarket", "title": "Iraq win", "fresh_wallets": 4,
                               "fresh_outcome": "Yes", "fresh_notional": 88000.0}])
        coord = pd.DataFrame([{"platform": "Polymarket", "title": "Iraq win", "coordinated_wallets": 6,
                               "coordinated_outcome": "Yes", "coordinated_span_minutes": 0.67,
                               "coordinated_notional": 214000.0}])
        nodes = pd.DataFrame([
            {"wallet": "0xa", "cluster_id": 0, "cluster_size": 2, "shared_markets": 3, "volume": 100.0},
            {"wallet": "0xb", "cluster_id": 0, "cluster_size": 2, "shared_markets": 3, "volume": 50.0},
        ])
        edges = pd.DataFrame([{"wallet_a": "0xa", "wallet_b": "0xb", "shared_markets": 3, "pair_notional": 150.0}])
        payload = apv.cluster_payload(fresh, coord, nodes, edges, lambda cn, ce: {
            "headline": "Two wallets, three shared markets.", "pattern": "Tight clique",
            "markets": [{"title": "Iraq win", "label": "$88.0k"}],
        })
        # count, not "score": the fresh number is a wallet count and says so.
        self.assertEqual(payload["fresh"][0]["count"], 4)
        self.assertEqual(payload["fresh"][0]["side"], "YES")
        self.assertEqual(payload["fresh"][0]["notional"], "$88.0k")
        self.assertEqual(payload["timing"][0]["window"], "40 s")
        self.assertEqual(payload["timing"][0]["span_minutes"], 0.7)
        self.assertEqual(payload["timing"][0]["side"], "YES")
        netz = payload["network"][0]
        self.assertEqual(netz["size"], 2)
        self.assertIn("Two wallets", netz["story"])
        # The card can say who is in the cluster and where they met.
        self.assertEqual(netz["id"], 0)
        self.assertEqual(netz["pattern"], "Tight clique")
        self.assertEqual([m["wallet"] for m in netz["members"]], ["0xa", "0xb"])
        self.assertEqual(netz["members"][0]["kurz"], "0xa")
        self.assertEqual(netz["markets"][0]["title"], "Iraq win")
        self.assertEqual(payload["kpis_clusters"], {"fresh_clusters": 1, "coordinated_clusters": 1})


class VariantsPayloadTests(unittest.TestCase):
    def test_maps_comparison_frame(self) -> None:
        frame = pd.DataFrame([{"strategy": "Fixed $25", "final_equity": 1100.0, "roi": 0.1,
                               "max_drawdown": -0.05, "win_rate": 0.6, "closed_trades": 5,
                               "copied_trades": 10, "skipped_trades": 2}])
        rows = apv.variants_payload(frame)
        self.assertEqual(rows[0]["name"], "Fixed $25")
        self.assertEqual(rows[0]["final_equity"], 1100.0)
        # Das n der Trefferquote reist mit: COPIED ist keine Stichprobe.
        self.assertEqual(rows[0]["closed_trades"], 5)
        self.assertEqual(apv.variants_payload(frame.drop(columns=["closed_trades"]))[0]["closed_trades"], 0)


if __name__ == "__main__":
    unittest.main()


class BalancedHeadTests(unittest.TestCase):
    """Das Tape darf nicht von einer Venue allein gefuellt werden."""

    @staticmethod
    def _tape() -> pd.DataFrame:
        # 1000 Kalshi-Mikroprints in den letzten Sekunden, 300 aeltere Polymarket-Prints.
        ks_times = pd.date_range("2026-08-17 00:14:20", periods=1000, freq="ms", tz="UTC")
        pm_times = pd.date_range("2026-08-17 00:10:00", periods=300, freq="-1min", tz="UTC")
        ks = pd.DataFrame({"platform": "Kalshi", "time": ks_times, "notional": 2.9})
        pm = pd.DataFrame({"platform": "Polymarket", "time": pm_times, "notional": 5000.0})
        return pd.concat([ks, pm], ignore_index=True)

    def test_naive_head_would_be_kalshi_only(self) -> None:
        naive = self._tape().sort_values("time", ascending=False).head(250)
        self.assertEqual(set(naive["platform"]), {"Kalshi"})

    def test_balanced_head_gives_each_venue_half(self) -> None:
        out = apv.balanced_head(self._tape(), 250)
        counts = out["platform"].value_counts()
        self.assertEqual(len(out), 250)
        self.assertEqual(int(counts["Kalshi"]), 125)
        self.assertEqual(int(counts["Polymarket"]), 125)
        # sorted by time, newest first
        self.assertTrue(out["time"].is_monotonic_decreasing)

    def test_leftover_quota_flows_to_the_other_venue(self) -> None:
        tape = self._tape()
        small = pd.concat([tape[tape["platform"] == "Polymarket"], tape[tape["platform"] == "Kalshi"].head(5)])
        out = apv.balanced_head(small, 250)
        counts = out["platform"].value_counts()
        self.assertEqual(int(counts["Kalshi"]), 5)
        self.assertEqual(int(counts["Polymarket"]), 245)

    def test_single_venue_and_empty(self) -> None:
        tape = self._tape()
        only_pm = tape[tape["platform"] == "Polymarket"]
        self.assertEqual(len(apv.balanced_head(only_pm, 50)), 50)
        self.assertEqual(len(apv.balanced_head(only_pm.iloc[0:0], 50)), 0)
        self.assertEqual(len(apv.balanced_head(tape, 0)), 0)


class TapeCategoryTests(unittest.TestCase):
    """Jeder Print traegt eine Kategorie: Universum zuerst, dann Titel-Heuristik, sonst Other."""

    @staticmethod
    def _universe() -> pd.DataFrame:
        return pd.DataFrame([
            {"platform": "Polymarket", "market_key": "0xcond1", "slug": "fed-cut-sept", "title": "Fed cut in September?", "category": "Economics", "filter_category": "Finance"},
            {"platform": "Polymarket", "market_key": "0xcond2", "slug": "some-slug", "title": "Some question", "category": "Politics", "filter_category": ""},
            {"platform": "Kalshi", "market_key": "KXHIGHNY-26AUG17-B80", "slug": "KXHIGHNY-26AUG17-B80", "title": "KXHIGHNY-26AUG17-B80", "category": "Climate and Weather", "filter_category": "Weather"},
        ])

    @staticmethod
    def _classify(raw, title):
        # Kleine, nachvollziehbare Titel-Heuristik anstelle von md.market_filter_category.
        text = f"{raw or ''} {title or ''}".upper()
        if "BTC" in text or "BITCOIN" in text:
            return "Crypto"
        if "NBA" in text:
            return "Sports"
        if "TRUMP" in text:
            return "Politics"
        return raw or "Uncategorized"

    def test_universe_hit_wins_by_key_slug_or_title(self) -> None:
        tape = pd.DataFrame([
            {"platform": "Polymarket", "market_key": "0xcond1", "slug": "", "title": "Any title"},
            {"platform": "Polymarket", "market_key": "0xunknown", "slug": "fed-cut-sept", "title": "Any title"},
            {"platform": "Polymarket", "market_key": "0xunknown", "slug": "", "title": "Fed cut in September?"},
            {"platform": "Kalshi", "ticker": "KXHIGHNY-26AUG17-B80", "title": "KXHIGHNY-26AUG17-B80"},
        ])
        out = apv.tape_rows_with_category(tape, self._universe(), self._classify)
        self.assertEqual(out["category"].tolist(), ["Finance", "Finance", "Finance", "Weather"])

    def test_universe_hit_without_filter_category_runs_the_classifier(self) -> None:
        tape = pd.DataFrame([{"platform": "Polymarket", "market_key": "0xcond2", "slug": "", "title": "Some question"}])
        out = apv.tape_rows_with_category(tape, self._universe(), self._classify)
        # Rohkategorie "Politics" ohne filter_category -> classify(raw, title) -> raw.
        self.assertEqual(out["category"].tolist(), ["Politics"])

    def test_no_universe_hit_falls_back_to_the_title(self) -> None:
        tape = pd.DataFrame([
            {"platform": "Polymarket", "market_key": "0xnew", "slug": "", "title": "Will Bitcoin hit $150k?"},
            {"platform": "Polymarket", "market_key": "0xnew2", "slug": "", "title": "Will Trump sign it?"},
            {"platform": "Polymarket", "market_key": "0xnew3", "slug": "", "title": "Something without a keyword"},
        ])
        out = apv.tape_rows_with_category(tape, self._universe(), self._classify)
        self.assertEqual(out["category"].tolist(), ["Crypto", "Politics", "Other"])

    def test_kalshi_uses_the_ticker_series_prefix(self) -> None:
        tape = pd.DataFrame([
            {"platform": "Kalshi", "ticker": "KXBTC15M-26AUG17-1030-T115", "title": "KXBTC15M-26AUG17-1030-T115"},
            {"platform": "Kalshi", "ticker": "KXNBA-26OCT01-LAL", "title": "KXNBA-26OCT01-LAL"},
            {"platform": "Kalshi", "ticker": "KXFOO-26AUG17", "title": "KXFOO-26AUG17"},
        ])
        out = apv.tape_rows_with_category(tape, None, self._classify)
        self.assertEqual(out["category"].tolist(), ["Crypto", "Sports", "Other"])
        self.assertEqual(apv.kalshi_series("KXBTC15M-26AUG17-1030-T115"), "KXBTC15M")
        self.assertEqual(apv.kalshi_series(""), "")

    def test_real_classifier_on_realistic_prints(self) -> None:
        from src import prediction_markets as md

        tape = pd.DataFrame([
            {"platform": "Polymarket", "market_key": "0xa", "slug": "", "title": "Will Bitcoin close above $120k on Friday?"},
            {"platform": "Polymarket", "market_key": "0xb", "slug": "", "title": "Will Trump sign the executive order?"},
            {"platform": "Polymarket", "market_key": "0xc", "slug": "", "title": "Lakers vs Celtics: NBA Finals winner"},
            {"platform": "Kalshi", "ticker": "KXBTC15M-26AUG17-1030-T115", "title": "KXBTC15M-26AUG17-1030-T115"},
            {"platform": "Kalshi", "ticker": "KXHIGHNY-26AUG17-B80", "title": "KXHIGHNY-26AUG17-B80"},
        ])
        out = apv.tape_rows_with_category(tape, None, md.market_filter_category)
        self.assertEqual(out["category"].tolist(), ["Crypto", "Politics", "Sports", "Crypto", "Other"])

    def test_chained_classifier_catches_what_the_market_heuristic_misses(self) -> None:
        # Genau die Prints, die das echte Tape dominieren und mit der
        # Markt-Heuristik allein "Other" blieben.
        from src import prediction_markets as md

        chain = apv.chained_classifier(md.market_filter_category, apv.context_group_classifier())
        tape = pd.DataFrame([
            {"platform": "Polymarket", "market_key": "0x1", "title": "LoL: LYON vs Sentinels (BO3) - LCS Regular Season"},
            {"platform": "Polymarket", "market_key": "0x2", "title": "Seattle Mariners vs. Houston Astros"},
            {"platform": "Polymarket", "market_key": "0x3", "title": "Dota 2: TEAM VISION vs BoomBoys (BO3) - The International Playoffs"},
            {"platform": "Polymarket", "market_key": "0x4", "title": "Will CF América win on 2026-08-16?"},
            {"platform": "Polymarket", "market_key": "0x5", "title": "Will the CEO resign before October?"},
            {"platform": "Polymarket", "market_key": "0x6", "title": "Will the film win Best Picture at the Oscars?"},
            {"platform": "Polymarket", "market_key": "0x7", "title": "Will Elon Musk post 120-139 tweets from August 11 to August 18, 2026?"},
            # Die Markt-Heuristik gewinnt, wo sie etwas sagt.
            {"platform": "Polymarket", "market_key": "0x8", "title": "Will the price of Bitcoin be above $64,000 on August 17?"},
        ])
        out = apv.tape_rows_with_category(tape, None, chain)
        self.assertEqual(
            out["category"].tolist(),
            ["Sports", "Sports", "Sports", "Sports", "Business", "Entertainment", "Other", "Crypto"],
        )

    def test_context_group_classifier_maps_groups_and_leaves_general_empty(self) -> None:
        fake = lambda title, raw="", context_text="": ("Sports odds" if "vs" in str(title) else "General", 1.0, "")  # noqa: E731
        classify = apv.context_group_classifier(fake)
        self.assertEqual(classify("", "A vs B"), "Sports")
        self.assertEqual(classify("", "Something else"), "")
        self.assertEqual(apv.chained_classifier(classify)("", "Something else"), "Other")

    def test_never_leaks_uncategorized_or_raw_series_codes(self) -> None:
        self.assertEqual(apv.clean_category("Uncategorized"), "Other")
        self.assertEqual(apv.clean_category(""), "Other")
        self.assertEqual(apv.clean_category(None), "Other")
        self.assertEqual(apv.clean_category("KXHIGHNY"), "Other")
        self.assertEqual(apv.clean_category("Politics"), "Politics")

    def test_input_is_not_mutated_and_empty_frames_survive(self) -> None:
        tape = pd.DataFrame([{"platform": "Polymarket", "market_key": "0xcond1", "slug": "", "title": "x"}])
        out = apv.tape_rows_with_category(tape, self._universe(), self._classify)
        self.assertNotIn("category", tape.columns)
        self.assertIn("category", out.columns)
        empty = apv.tape_rows_with_category(pd.DataFrame(), self._universe(), self._classify)
        self.assertTrue(empty.empty)
        self.assertIn("category", empty.columns)
        self.assertTrue(apv.tape_rows_with_category(None, None, None).empty)

    def test_enrich_filter_categories_fills_only_the_others(self) -> None:
        # Das Universum sagte zuletzt in 907 von 1000 Zeilen "Other" — die
        # Titelmuster kennen die Formen (Parlays, Einzelspiele). Nur Other-
        # Zeilen laufen durch den Klassifizierer; benannte bleiben, wie sie
        # sind, und die Eingabe wird nicht veraendert.
        from src import prediction_markets as md

        # Dieselbe Kette wie der Server (TAPE_CLASSIFIER): Parlays sind eine
        # eigene Kategorie, sonst fluteten sie "Sports".
        chain = apv.chained_classifier(md.market_filter_category, apv.parlay_classifier, apv.context_group_classifier())
        universe = pd.DataFrame([
            {"title": "Parlay · 2 legs: yes Both Teams To Score · yes Bilbao wins", "category": "", "filter_category": "Other"},
            {"title": "Will CF América win on 2026-08-16?", "category": "", "filter_category": ""},
            {"title": "Xi Jinping out before 2027?", "category": "", "filter_category": "Politics"},
            {"title": "Completely unclassifiable thing", "category": "", "filter_category": ""},
        ])
        out = apv.enrich_filter_categories(universe, chain)
        self.assertEqual(out["filter_category"].tolist(), ["Parlays", "Sports", "Politics", "Other"])
        self.assertEqual(universe["filter_category"].tolist(), ["Other", "", "Politics", ""])
        # Ohne Titel oder ohne Zeilen: unveraendert zurueck, kein Fehler.
        ohne_titel = pd.DataFrame([{"category": "", "filter_category": ""}])
        self.assertIs(apv.enrich_filter_categories(ohne_titel, chain), ohne_titel)
        self.assertTrue(apv.enrich_filter_categories(pd.DataFrame(), chain).empty)


class MarketRecordsTests(unittest.TestCase):
    """/api/markets liefert nur die Felder, die das Frontend liest."""

    def _frame(self) -> pd.DataFrame:
        return pd.DataFrame([
            {
                "market_key": "0xcond1", "ticker": "0xcond1", "slug": "fed-cuts", "title": "Fed cuts rates",
                "platform": "Polymarket", "category": "Economics", "filter_category": "Finance",
                "yes_price": 0.62, "change_1d": 0.03, "volume_24h": 120000.0, "liquidity": 40000.0,
                "volume": 4200000.0, "activity_volume": 120000.0,
                "end_time": pd.Timestamp("2026-12-31", tz="UTC"), "url": "https://polymarket.com/event/x",
                "spread": 0.02, "market_age_days": 40.2,
                # Ballast, der nicht in die Antwort darf:
                "raw": {"question": "Fed cuts rates", "description": "x" * 5000, "clobTokenIds": ["1", "2"]},
                "description": "y" * 3000, "image": "https://img/x.png",
                "outcomes": ["Yes", "No"], "yes_token_id": "111", "no_token_id": "222",
            },
            {
                "market_key": "KXMVECROSSCATEGORY-26AUG", "ticker": "KXMVECROSSCATEGORY-26AUG", "slug": "",
                "title": "Parlay", "platform": "Kalshi", "category": "KXMVECROSSCATEGORY",
                "filter_category": "Cross Category", "yes_price": 0.4, "change_1d": 0.0,
                "volume_24h": 10.0, "liquidity": 0.0, "end_time": None, "url": "", "raw": {"a": 1},
                "description": "", "image": "", "outcomes": ["Yes", "No"], "yes_token_id": None, "no_token_id": None,
            },
        ])

    def test_strips_blobs_and_keeps_frontend_fields(self) -> None:
        rows = apv.market_records(self._frame())
        self.assertEqual(len(rows), 2)
        for row in rows:
            for weg in ("raw", "description", "image", "outcomes", "yes_token_id", "no_token_id"):
                self.assertNotIn(weg, row)
        first = rows[0]
        for feld in ("market_key", "title", "platform", "filter_category", "yes_price", "change_1d",
                     "volume_24h", "liquidity", "end_time", "url", "spread", "market_age_days"):
            self.assertIn(feld, first)
        self.assertEqual(first["yes_price"], 0.62)
        self.assertTrue(str(first["end_time"]).startswith("2026-12-31"))
        # Tages- und Lebensvolumen fahren getrennt mit: das Frontend darf das
        # eine nicht als das andere ausweisen.
        self.assertEqual(first["volume_24h"], 120000.0)
        self.assertEqual(first["volume"], 4200000.0)
        # Kompakt: zwei Zeilen unter einem Kilobyte, statt der 8k Ballast oben.
        import json
        self.assertLess(len(json.dumps(rows)), 1200)

    def test_cross_category_becomes_other_and_limit_applies(self) -> None:
        rows = apv.market_records(self._frame())
        self.assertEqual(rows[1]["filter_category"], "Other")
        self.assertEqual(rows[1]["category"], "Other")
        self.assertEqual(rows[0]["filter_category"], "Finance")
        self.assertEqual(len(apv.market_records(self._frame(), limit=1)), 1)
        self.assertEqual(apv.market_records(pd.DataFrame()), [])
        self.assertEqual(apv.market_records(None), [])
        self.assertEqual(apv.clean_category("Cross Category"), "Other")
        self.assertEqual(apv.clean_category("cross-category"), "Other")

    def test_missing_columns_do_not_break(self) -> None:
        rows = apv.market_records(pd.DataFrame([{"title": "only a title", "platform": "Kalshi"}]))
        self.assertEqual(rows, [{"title": "only a title", "platform": "Kalshi"}])


class CrossGateTests(unittest.TestCase):
    """Cross-Venue-Paare: nur Aehnlichkeit >= 0.5 und Volumen auf beiden Seiten."""

    def _candidates(self) -> pd.DataFrame:
        return pd.DataFrame([
            {"polymarket_title": "kept", "kalshi_title": "kept", "polymarket_yes": 0.62, "kalshi_yes": 0.58,
             "polymarket_volume_usd": 100000.0, "kalshi_volume_contracts": 40000.0, "similarity": 0.71},
            {"polymarket_title": "too dissimilar", "kalshi_title": "x", "polymarket_yes": 0.79, "kalshi_yes": 0.64,
             "polymarket_volume_usd": 100000.0, "kalshi_volume_contracts": 40000.0, "similarity": 0.44},
            {"polymarket_title": "no kalshi volume", "kalshi_title": "x", "polymarket_yes": 0.5, "kalshi_yes": 0.5,
             "polymarket_volume_usd": 100000.0, "kalshi_volume_contracts": 0.0, "similarity": 0.9},
            {"polymarket_title": "no polymarket volume", "kalshi_title": "x", "polymarket_yes": 0.5, "kalshi_yes": 0.5,
             "polymarket_volume_usd": None, "kalshi_volume_contracts": 4000.0, "similarity": 0.9},
            {"polymarket_title": "exactly at the gate", "kalshi_title": "x", "polymarket_yes": 0.5, "kalshi_yes": 0.5,
             "polymarket_volume_usd": 1.0, "kalshi_volume_contracts": 1.0, "similarity": 0.5},
        ])

    def test_default_gate_keeps_only_similar_pairs_with_volume_on_both_venues(self) -> None:
        rows = apv.cross_rows(self._candidates())
        self.assertEqual([r["event"] for r in rows], ["kept", "exactly at the gate"])
        self.assertEqual(rows[0]["sim"], 0.71)
        self.assertEqual(apv.CROSS_MIN_SIMILARITY, 0.5)

    def test_gate_can_be_tightened_or_volume_requirement_dropped(self) -> None:
        strenger = apv.cross_rows(self._candidates(), min_similarity=0.6)
        self.assertEqual([r["event"] for r in strenger], ["kept"])
        ohne_volumen = apv.cross_rows(self._candidates(), require_volume=False)
        self.assertEqual([r["event"] for r in ohne_volumen], ["kept", "no kalshi volume", "no polymarket volume", "exactly at the gate"])
        self.assertEqual(apv.cross_rows(pd.DataFrame()), [])

    def test_server_gate_cannot_be_lowered_below_default(self) -> None:
        # api/server.py klemmt den Query-Parameter auf mindestens die Schranke.
        from pathlib import Path
        server = (Path(__file__).resolve().parents[1] / "api" / "server.py").read_text(encoding="utf-8")
        self.assertIn("min_similarity = max(float(min_similarity), apv.CROSS_MIN_SIMILARITY)", server)
        self.assertIn('"candidates_before_gate"', server)

    def test_the_row_carries_the_edge_net_of_both_fee_curves(self) -> None:
        frame = self._candidates()
        frame.loc[0, "gross_edge_cents"] = 4.0
        frame.loc[0, "fee_band_cents"] = 2.7155
        frame.loc[0, "net_edge_cents"] = 1.2845
        frame.loc[0, "edge_direction"] = "buy Polymarket, sell Kalshi"
        row = apv.cross_rows(frame)[0]
        self.assertEqual(row["gross"], 4.0)
        self.assertEqual(row["band"], 2.7155)
        self.assertEqual(row["net"], 1.2845)
        self.assertEqual(row["dir"], "buy Polymarket, sell Kalshi")

    def test_a_pair_without_quotes_reports_no_edge_rather_than_zero(self) -> None:
        # Ohne beidseitige Quote gibt es keine Spanne zu rechnen. Null waere
        # hier eine Messung, und gemessen wurde nichts.
        row = apv.cross_rows(self._candidates())[0]
        self.assertIsNone(row["gross"])
        self.assertIsNone(row["net"])
        self.assertEqual(row["dir"], "")


class ScorePartsTests(unittest.TestCase):
    def test_leaderboard_rows_carry_labelled_score_parts(self) -> None:
        lb = pd.DataFrame([{"trader": "Theo4", "wallet": "0xAAA1111111111111111111", "pnl": 1000.0, "volume": 50000.0}])
        ranked = pd.DataFrame([{
            "wallet": "0xaaa1111111111111111111", "copy_smart_score": 87.4, "copy_grade": "A",
            "copy_rank_reason": "return 90, sharpe-proxy 60, drawdown-proxy 100, win 55, recency 50, volume 80",
            "copy_return_score": 90.0, "copy_sharpe_proxy": 60.4, "copy_drawdown_proxy": 100.0,
            "copy_win_score": 55.0, "copy_recency_score": 50.0, "copy_volume_score": 80.0,
        }])
        rows = apv.leaderboard_rows(lb, ranked)
        parts = rows[0]["score_parts"]
        self.assertEqual([p["label"] for p in parts], ["return", "sharpe proxy", "drawdown proxy", "win", "recency", "volume"])
        self.assertEqual([p["value"] for p in parts], [90, 60, 100, 55, 50, 80])
        self.assertAlmostEqual(sum(p["weight"] for p in parts), 1.0)
        # Ohne Ranked-Treffer eine leere Liste, kein None und keine Nullen.
        rows_ohne = apv.leaderboard_rows(lb, None)
        self.assertEqual(rows_ohne[0]["score_parts"], [])

    def test_score_parts_skips_missing_columns(self) -> None:
        parts = apv.score_parts({"copy_return_score": 12.6, "copy_win_score": None})
        self.assertEqual(parts, [{"label": "return", "value": 13, "weight": 0.35, "imputed": False}])
        self.assertEqual(apv.score_parts({}), [])

    def test_score_parts_marken_ersatzwerte_als_nicht_gemessen(self) -> None:
        """Ein Bestandteil ohne Eingabe im Feed ist fuer jede Wallet dieselbe Konstante.

        Die oeffentliche Leaderboard-Antwort traegt nur pnl und volume
        (prediction_markets.get_polymarket_leaderboard), also setzt
        rank_traders_by_smart_score win/recency/drawdown/sharpe auf einen
        Ersatzwert und vermerkt das in copy_score_imputed. Die Oberflaeche
        darf diese Zahlen nicht als Messung zeigen.
        """

        row = {
            "copy_return_score": 100.0, "copy_sharpe_proxy": 21.2, "copy_drawdown_proxy": 100.0,
            "copy_win_score": 50.0, "copy_recency_score": 50.0, "copy_volume_score": 90.0,
            "copy_score_imputed": "copy_sharpe_proxy,copy_drawdown_proxy,copy_win_score,copy_recency_score",
        }
        parts = apv.score_parts(row)
        geschaetzt = {p["label"] for p in parts if p["imputed"]}
        self.assertEqual(geschaetzt, {"sharpe proxy", "drawdown proxy", "win", "recency"})
        gemessen = {p["label"] for p in parts if not p["imputed"]}
        self.assertEqual(gemessen, {"return", "volume"})

        basis = apv.score_basis(parts, cohort_n=250)
        self.assertAlmostEqual(basis["measured_weight"], 0.45)
        self.assertAlmostEqual(basis["imputed_weight"], 0.55)
        self.assertEqual(basis["cohort_n"], 250)
        self.assertEqual(basis["imputed"], ["sharpe proxy", "drawdown proxy", "win", "recency"])

    def test_leaderboard_rows_tragen_die_score_basis(self) -> None:
        lb = pd.DataFrame([{"trader": "Theo4", "wallet": "0xAAA1111111111111111111", "pnl": 1000.0, "volume": 50000.0}])
        ranked = pd.DataFrame([{
            "wallet": "0xaaa1111111111111111111", "copy_smart_score": 73.0, "copy_grade": "B",
            "copy_return_score": 100.0, "copy_sharpe_proxy": 21.2, "copy_drawdown_proxy": 100.0,
            "copy_win_score": 50.0, "copy_recency_score": 50.0, "copy_volume_score": 90.0,
            "copy_score_imputed": "copy_sharpe_proxy,copy_drawdown_proxy,copy_win_score,copy_recency_score",
        }])
        basis = apv.leaderboard_rows(lb, ranked)[0]["score_basis"]
        self.assertAlmostEqual(basis["measured_weight"], 0.45)
        self.assertEqual(basis["cohort_n"], 1)
        # Eine Zeile ohne Ranked-Treffer traegt keine erfundene Basis.
        self.assertIsNone(apv.leaderboard_rows(lb, None)[0]["score_basis"])


    def test_score_interval_umschliesst_den_gezeigten_score(self) -> None:
        """Die Spanne ist kein Konfidenzintervall, aber sie haelt den Score.

        ``copy_smart_score`` ist exakt die gewichtete Summe der sechs
        Bestandteile (``copy_trading.rank_traders_by_smart_score``). Setzt man
        die geschaetzten auf 0 beziehungsweise 100, entstehen Unter- und
        Obergrenze, und der gezeigte Score liegt konstruktionsbedingt
        dazwischen.
        """

        row = {
            "copy_return_score": 100.0, "copy_sharpe_proxy": 21.2, "copy_drawdown_proxy": 100.0,
            "copy_win_score": 50.0, "copy_recency_score": 50.0, "copy_volume_score": 90.0,
            "copy_score_imputed": "copy_sharpe_proxy,copy_drawdown_proxy,copy_win_score,copy_recency_score",
        }
        parts = apv.score_parts(row)
        lo, hi = apv.score_interval(parts)
        # gemessen: return 100 * 0.35 + volume 90 * 0.10 = 44.0
        self.assertAlmostEqual(lo, 44.0)
        # dazu 55 Prozent offenes Gewicht mal 100 Punkte
        self.assertAlmostEqual(hi, 99.0)
        score = (100.0 * 0.35 + 21.2 * 0.20 + 100.0 * 0.15
                 + 50.0 * 0.10 + 50.0 * 0.10 + 90.0 * 0.10)
        self.assertGreaterEqual(score, lo)
        self.assertLessEqual(score, hi)
        # Ohne Bestandteile keine erfundene Spanne.
        self.assertIsNone(apv.score_interval([]))

    def test_score_interval_ohne_platzhalter_ist_ein_punkt(self) -> None:
        parts = [
            {"label": "return", "value": 80, "weight": 0.5, "imputed": False},
            {"label": "volume", "value": 40, "weight": 0.5, "imputed": False},
        ]
        self.assertEqual(apv.score_interval(parts), [60.0, 60.0])

    def test_sample_badge_nennt_den_gemessenen_anteil(self) -> None:
        self.assertIsNone(apv.score_sample_badge(None))
        wenig = apv.score_sample_badge({"measured_weight": 0.45})
        self.assertEqual(wenig["quality"], "mostly placeholder")
        self.assertFalse(wenig["verdict_allowed"])
        mittel = apv.score_sample_badge({"measured_weight": 0.65})
        self.assertEqual(mittel["quality"], "part measured")
        viel = apv.score_sample_badge({"measured_weight": 0.9})
        self.assertEqual(viel["quality"], "measured")
        self.assertTrue(viel["verdict_allowed"])

    def test_leaderboard_rows_tragen_n_spanne_und_abzeichen(self) -> None:
        lb = pd.DataFrame([{"trader": "Theo4", "wallet": "0xAAA1111111111111111111", "pnl": 1000.0, "volume": 50000.0}])
        ranked = pd.DataFrame([{
            "wallet": "0xaaa1111111111111111111", "copy_smart_score": 73.0, "copy_grade": "B",
            "copy_return_score": 100.0, "copy_sharpe_proxy": 21.2, "copy_drawdown_proxy": 100.0,
            "copy_win_score": 50.0, "copy_recency_score": 50.0, "copy_volume_score": 90.0,
            "copy_score_imputed": "copy_sharpe_proxy,copy_drawdown_proxy,copy_win_score,copy_recency_score",
        }])
        row = apv.leaderboard_rows(lb, ranked)[0]
        self.assertEqual(row["score_n"], 1)
        self.assertEqual(row["score_ci"], [44.0, 99.0])
        self.assertEqual(row["sample_badge"]["quality"], "mostly placeholder")
        # Ohne Ranked-Treffer bleibt jedes der drei Felder leer statt geraten.
        ohne = apv.leaderboard_rows(lb, None)[0]
        self.assertIsNone(ohne["score_n"])
        self.assertIsNone(ohne["score_ci"])
        self.assertIsNone(ohne["sample_badge"])

    def test_leaderboard_scale_nennt_boden_und_saettigung(self) -> None:
        """Beide Schwellen sind Eigenschaften der Kohorte, nicht der Wallet."""

        from src.copy_trading import ROI_MIN_VOLUME

        ranked = pd.DataFrame({"volume": [1_000.0 * i for i in range(1, 101)]})
        skala = apv.leaderboard_scale(ranked)
        self.assertEqual(skala["gate_volume"], float(ROI_MIN_VOLUME))
        self.assertAlmostEqual(skala["saturates_at"], float(ranked["volume"].quantile(0.95)))
        # Ohne Menge keine erfundene Schwelle.
        leer = apv.leaderboard_scale(pd.DataFrame())
        self.assertIsNone(leer["saturates_at"])

class RiskScoreBinsTests(unittest.TestCase):
    """Die Score-Verteilung des Screens: gezaehlt, nicht geschaetzt."""

    def _frame(self, werte: list[float]) -> pd.DataFrame:
        return pd.DataFrame([{"event_insider_score": w} for w in werte])

    def test_bins_zaehlen_alle_gescorten_maerkte(self) -> None:
        bins = apv.risk_score_bins(self._frame([0.0, 5.0, 39.9, 40.0, 72.0, 100.0]), 40.0)
        self.assertEqual(len(bins), 10)
        self.assertEqual(sum(b["anzahl"] for b in bins), 6)
        nach_von = {b["von"]: b for b in bins}
        self.assertEqual(nach_von[0]["anzahl"], 2)
        self.assertEqual(nach_von[30]["anzahl"], 1)
        self.assertEqual(nach_von[40]["anzahl"], 1)
        self.assertEqual(nach_von[70]["anzahl"], 1)
        # Die 100 faellt in den obersten Bin, nicht heraus.
        self.assertEqual(nach_von[90]["anzahl"], 1)

    def test_geflaggt_ist_die_teilmenge_ab_der_schwelle(self) -> None:
        bins = apv.risk_score_bins(self._frame([10.0, 41.0, 44.0, 88.0]), 40.0)
        nach_von = {b["von"]: b for b in bins}
        self.assertEqual(nach_von[40]["anzahl"], 2)
        self.assertEqual(nach_von[40]["geflaggt"], 2)
        self.assertEqual(nach_von[10]["geflaggt"], 0)
        self.assertEqual(sum(b["geflaggt"] for b in bins), 3)

    def test_ohne_maerkte_keine_bins(self) -> None:
        self.assertEqual(apv.risk_score_bins(pd.DataFrame(), 40.0), [])
        self.assertEqual(apv.risk_score_bins(None, 40.0), [])

    def test_payload_traegt_die_verteilung(self) -> None:
        events = self._frame([12.0, 55.0])
        events["title"] = ["A", "B"]
        events["platform"] = ["Polymarket", "Polymarket"]
        payload = apv.risk_payload(pd.DataFrame(), events, min_event_score=40.0)
        bins = payload["score_bins"]
        self.assertEqual(sum(b["anzahl"] for b in bins), 2)
        self.assertEqual(sum(b["geflaggt"] for b in bins), 1)
        # Die Summe der Bins ist genau das, was der Trichter als gescreent zaehlt.
        self.assertEqual(sum(b["anzahl"] for b in bins), payload["kpis"]["events_screened"])

class TradePnlDistributionTests(unittest.TestCase):
    """Die Verteilung der Trade-Ergebnisse und ihre Konzentration."""

    def _ledger(self, werte: list[float]) -> pd.DataFrame:
        rows = [{"status": "copied", "action": "SELL", "realized_pnl": w} for w in werte]
        # Ein Kauf und ein uebersprungener Trade duerfen nicht mitzaehlen.
        rows.append({"status": "copied", "action": "BUY", "realized_pnl": None})
        rows.append({"status": "skipped", "action": "SELL", "realized_pnl": 999.0})
        return pd.DataFrame(rows)

    def test_zaehlt_nur_geschlossene_kopien(self) -> None:
        v = apv.trade_pnl_distribution(self._ledger([1.0, -2.0, 3.0]))
        self.assertEqual(v["n"], 3)
        self.assertEqual(sum(b["anzahl"] for b in v["bins"]), 3)
        self.assertEqual(v["best"], 3.0)
        self.assertEqual(v["worst"], -2.0)
        self.assertEqual(v["unit"], "USD")

    def test_konzentration_ist_der_anteil_der_drei_groessten_gewinner(self) -> None:
        v = apv.trade_pnl_distribution(self._ledger([10.0, 6.0, 4.0, 2.0, 3.0, -5.0]))
        self.assertEqual(v["winners"], 5)
        self.assertEqual(v["gross_win"], 25.0)
        self.assertEqual(v["top3"], 20.0)
        self.assertAlmostEqual(v["top3_share"], 0.8)

    def test_ohne_gewinn_ist_der_anteil_nicht_definiert(self) -> None:
        v = apv.trade_pnl_distribution(self._ledger([-1.0, -2.0]))
        self.assertIsNone(v["top3_share"])
        self.assertEqual(v["winners"], 0)

    def test_ohne_geschlossene_kopie_kein_bild(self) -> None:
        self.assertIsNone(apv.trade_pnl_distribution(None))
        self.assertIsNone(apv.trade_pnl_distribution(pd.DataFrame()))
        nur_kaeufe = pd.DataFrame([{"status": "copied", "action": "BUY", "realized_pnl": None}])
        self.assertIsNone(apv.trade_pnl_distribution(nur_kaeufe))

    def test_gleiche_werte_bekommen_trotzdem_eine_achsenbreite(self) -> None:
        v = apv.trade_pnl_distribution(self._ledger([5.0, 5.0, 5.0]))
        self.assertEqual(sum(b["anzahl"] for b in v["bins"]), 3)
        self.assertLess(v["bins"][0]["von"], v["bins"][-1]["bis"])

class LiveRunsWinRateTests(unittest.TestCase):
    """25 zu 2 ohne Spanne ist die angreifbarste Zahl des Portfolios."""

    def _ledger(self, stati: list[str]) -> dict:
        return {"events": [{"maerkte": [{"zuordnung": "bot", "status": s} for s in stati]}]}

    def test_ledger_gewinnt_gegen_das_lauf_aggregat(self) -> None:
        payload = {"aggregat": {"gewonnen": 25, "verloren": 2}}
        quote = apv.live_runs_win_rate(payload, self._ledger(["won", "won", "lost"]))
        self.assertEqual(quote["source"], "wallet ledger")
        self.assertEqual((quote["wins"], quote["losses"], quote["n"]), (2, 1, 3))

    def test_wertlos_zaehlt_als_verloren_offen_zaehlt_gar_nicht(self) -> None:
        quote = apv.live_runs_win_rate({}, self._ledger(["won", "worthless", "open", "open"]))
        self.assertEqual((quote["wins"], quote["losses"], quote["n"]), (1, 1, 2))

    def test_ohne_ledger_faellt_es_auf_die_lauf_logs_zurueck(self) -> None:
        quote = apv.live_runs_win_rate({"aggregat": {"gewonnen": 25, "verloren": 2}}, None)
        self.assertEqual(quote["source"], "run logs")
        self.assertEqual(quote["n"], 27)
        self.assertAlmostEqual(quote["p"], 25 / 27, places=4)

    def test_die_spanne_ist_wilson_und_bleibt_in_null_bis_eins(self) -> None:
        from app import quant

        quote = apv.live_runs_win_rate({"aggregat": {"gewonnen": 25, "verloren": 2}}, None)
        lo, hi = quant.wilson_interval(25, 27)
        self.assertEqual(quote["ci95"], [round(lo, 4), round(hi, 4)])
        # Genau der Punkt: die Normalapproximation liefe hier ueber 100 Prozent.
        self.assertLessEqual(quote["ci95"][1], 1.0)
        self.assertGreaterEqual(quote["ci95"][0], 0.0)
        self.assertLess(quote["ci95"][0], quote["p"])

    def test_ohne_aufgeloeste_wette_keine_quote(self) -> None:
        self.assertIsNone(apv.live_runs_win_rate({}, None))
        self.assertIsNone(apv.live_runs_win_rate({"aggregat": {"gewonnen": 0, "verloren": 0}}, None))
        self.assertIsNone(apv.live_runs_win_rate({}, self._ledger(["open"])))

class RiskEventRowTests(unittest.TestCase):
    """The event card carries side, price, wallets, window, link and components — or honest gaps."""

    def _row(self) -> pd.Series:
        return pd.Series({
            "platform": "Polymarket", "title": "Rate hike in September?", "market_key": "0xc1",
            "url": "https://polymarket.com/event/fed-september", "slug": "rate-hike-sep",
            "event_insider_score": 66.0, "event_insider_level": "Medium",
            "event_insider_flags": "wallet concentration; one-sided flow; 2 fresh wallets on NO",
            "unique_wallets": 3, "trades": 4, "notional": 23000.0, "trades_per_hour": 9.6,
            "insider_context": "Politics & geopolitics", "context_note": "decisions are known early",
            "context_multiplier": 1.1,
            "side": "NO buys", "side_notional": 20000.0, "side_share": 20000.0 / 23000.0,
            "side_buy_yes": 2000.0, "side_buy_no": 20000.0, "side_sell_yes": 1000.0, "side_sell_no": 0.0,
            "price_outcome": "NO", "price_first": 0.30, "price_last": 0.34, "price_min": 0.30, "price_max": 0.34,
            "first_print": pd.Timestamp("2026-08-16T12:00:00Z"), "last_print": pd.Timestamp("2026-08-16T12:25:00Z"),
            "window_minutes": 25.0, "print_offsets": [0.0, 0.4, 0.8, 1.0],
            "top_wallets": [
                {"wallet": "0xbbb2000000000000000000000000000000000002", "notional": 17000.0, "share": 0.739, "side": "NO buys", "fresh": True},
                {"wallet": "0xaaa1000000000000000000000000000000000001", "notional": 4000.0, "share": 0.174, "side": "NO buys", "fresh": None},
            ],
            "component_notional": 5.75, "component_concentration": 8.3, "component_fresh_wallets": 5.0,
            "price_move_score": 2.7, "token_id": "tokNO",
        })

    def test_full_row(self) -> None:
        event = apv.risk_event_row(self._row())
        self.assertEqual(event["kind"], "WALLET CONCENTRATION")
        self.assertEqual(event["flags"], ["wallet concentration", "one-sided flow", "2 fresh wallets on NO"])
        self.assertEqual(event["detail"], "wallet concentration · one-sided flow · 2 fresh wallets on NO")
        self.assertEqual(event["url"], "https://polymarket.com/event/fed-september")
        self.assertEqual(event["market_key"], "0xc1")
        self.assertEqual(event["category"], "Politics & geopolitics")
        self.assertEqual(event["side"], "NO buys")
        self.assertAlmostEqual(event["side_notional"], 20000.0)
        self.assertAlmostEqual(event["side_share"], round(20000.0 / 23000.0, 4))
        self.assertEqual(event["side_split"], {"buy_yes": 2000.0, "buy_no": 20000.0, "sell_yes": 1000.0, "sell_no": 0.0})
        self.assertEqual(event["price_outcome"], "NO")
        self.assertAlmostEqual(event["price_last"], 0.34)
        self.assertAlmostEqual(event["price_min"], 0.30)
        self.assertEqual(event["first_print"], "2026-08-16T12:00:00Z")
        self.assertEqual(event["last_print"], "2026-08-16T12:25:00Z")
        self.assertEqual(event["window_minutes"], 25.0)
        self.assertEqual(event["print_offsets"], [0.0, 0.4, 0.8, 1.0])
        self.assertEqual(event["prints"], 4)
        self.assertEqual(event["notional"], "$23k")
        self.assertAlmostEqual(event["notional_usd"], 23000.0)
        self.assertEqual(event["sev"], "medium")
        wallets = event["top_wallets"]
        self.assertEqual(wallets[0]["short"], "0xbbb2…0002")
        self.assertEqual(wallets[0]["url"], "https://polymarket.com/profile/0xbbb2000000000000000000000000000000000002")
        self.assertTrue(wallets[0]["fresh"])
        self.assertIsNone(wallets[1]["fresh"])
        keys = [c["key"] for c in event["components"]]
        self.assertEqual(keys, ["component_notional", "component_concentration", "price_move_score",
                                "component_fresh_wallets", "context_multiplier"])
        self.assertEqual(event["components"][0]["value"], 5.8)
        self.assertEqual(event["token_id"], "tokNO")

    def test_older_row_without_flow_fields_has_honest_gaps(self) -> None:
        event = apv.risk_event_row(pd.Series({
            "platform": "Kalshi", "title": "KXFED-26SEP", "market_key": "KXFED-26SEP",
            "event_insider_score": 20.0, "event_insider_level": "Low", "event_insider_flags": "watch only",
            "unique_wallets": 0, "notional": 12000.0, "trades_per_hour": 3.0,
        }))
        self.assertEqual(event["kind"], "EVENT SCREEN")
        self.assertEqual(event["flags"], [])
        self.assertEqual(event["url"], "https://kalshi.com/markets/KXFED-26SEP")
        self.assertEqual(event["side"], "")
        self.assertIsNone(event["price_last"])
        self.assertEqual(event["first_print"], "")
        self.assertIsNone(event["window_minutes"])
        self.assertEqual(event["print_offsets"], [])
        self.assertEqual(event["top_wallets"], [])
        self.assertEqual(event["components"], [])
        self.assertEqual(event["side_split"], {"buy_yes": 0.0, "buy_no": 0.0, "sell_yes": 0.0, "sell_no": 0.0})

    def test_market_url_and_wallet_url(self) -> None:
        self.assertEqual(apv.market_url("Polymarket", "0xc1", "https://polymarket.com/event/x"), "https://polymarket.com/event/x")
        self.assertEqual(apv.market_url("Polymarket", "0xc1", "", "my-slug"), "https://polymarket.com/event/my-slug")
        self.assertEqual(apv.market_url("Kalshi", "KXFED-26SEP"), "https://kalshi.com/markets/KXFED-26SEP")
        self.assertEqual(apv.market_url("Polymarket", "0xc1"), "")
        self.assertEqual(apv.wallet_profile_url("Polymarket", "0xabc"), "https://polymarket.com/profile/0xabc")
        self.assertEqual(apv.wallet_profile_url("Kalshi", "Not public"), "")

    def test_risk_payload_uses_the_richer_rows_and_the_limit(self) -> None:
        events = pd.DataFrame([self._row().to_dict() for _ in range(apv.RISK_EVENT_LIMIT + 3)])
        payload = apv.risk_payload(pd.DataFrame(), events)
        self.assertEqual(len(payload["events"]), apv.RISK_EVENT_LIMIT)
        self.assertEqual(payload["events"][0]["side"], "NO buys")
        self.assertIn("components", payload["events"][0])


class WatchlistKeysTests(unittest.TestCase):
    """Der Alarm-Endpunkt muss die gespeicherte Watchlist lesen.

    ``build_monitor_signals`` erzeugt "Watched market"-Zeilen nur fuer die
    Keys, die es bekommt; der Endpunkt uebergab eine leere Menge. Damit
    lieferte SCOPE = "Watched only" auf der Alarm-Seite immer null Zeilen,
    egal was auf der Liste stand.
    """

    def test_keys_come_out_deduplicated_and_trimmed(self) -> None:
        keys = apv.watchlist_market_keys([
            {"platform": "Polymarket", "market_key": " 0xcond1 ", "title": "A"},
            {"platform": "Polymarket", "market_key": "0xcond1", "title": "A again"},
            {"platform": "Kalshi", "market_key": "KXFED-26SEP", "title": "B"},
            {"platform": "Polymarket", "market_key": "", "title": "no key"},
            "not a mapping",
        ])
        self.assertEqual(keys, {"0xcond1", "KXFED-26SEP"})

    def test_an_empty_or_broken_list_gives_an_empty_set(self) -> None:
        self.assertEqual(apv.watchlist_market_keys(None), set())
        self.assertEqual(apv.watchlist_market_keys([]), set())
        self.assertEqual(apv.watchlist_market_keys(["x", 3, None]), set())

    def test_a_watched_market_signal_reaches_the_feed_row(self) -> None:
        from app import signals as sig

        markets = pd.DataFrame([{
            "platform": "Polymarket", "title": "Fed cuts in December",
            "market_key": "0xcond1", "category": "Macro", "yes_price": 0.62,
            "spread": 0.30, "liquidity": 40_000.0, "volume": 100_000.0,
            "change_1h": 0.0, "url": "https://example.com",
        }])
        signals = sig.build_monitor_signals(
            markets, pd.DataFrame(),
            min_volume=0.0, min_liquidity=0.0, min_move=0.05, max_spread=0.01,
            min_whale_notional=1e12, ending_days=0, holder_threshold=1.0,
            holder_checks=0,
            tracked_keys=apv.watchlist_market_keys([{"market_key": "0xcond1"}]),
        )
        rows = apv.alert_rows(signals)
        self.assertEqual([r["rule"] for r in rows], ["WATCHED MARKET"])
        self.assertTrue(rows[0]["watched"])
        # Mit leerer Menge entsteht die Zeile gar nicht erst -- der Zustand,
        # in dem der Filter der Seite nichts finden konnte.
        ohne = sig.build_monitor_signals(
            markets, pd.DataFrame(),
            min_volume=0.0, min_liquidity=0.0, min_move=0.05, max_spread=0.01,
            min_whale_notional=1e12, ending_days=0, holder_threshold=1.0,
            holder_checks=0, tracked_keys=set(),
        )
        self.assertEqual([r for r in apv.alert_rows(ohne) if r["watched"]], [])


class AlertReadingUnitsTests(unittest.TestCase):
    """Nicht jede Zahl unter 1.0 in der READING-Spalte ist ein Preis."""

    @staticmethod
    def _signal(signal_type, value, **extra):
        row = {
            "signal_type": signal_type, "severity": "warning",
            "time": pd.Timestamp("2026-08-28 12:00:00", tz="UTC"),
            "platform": "Polymarket", "title": "Fed cuts in December",
            "category": "Macro", "outcome": "Yes", "side": "", "price": 0.62,
            "value": value, "reason": "", "volume": 100_000.0,
            "liquidity": 40_000.0, "spread": 0.02, "change_1h": 0.0,
            "market_key": "0xcond", "wallet": "", "trader": "", "notional": 0.0,
            "url": "",
        }
        row.update(extra)
        return row

    def test_a_holder_share_is_a_share_not_a_price(self) -> None:
        # 62 Prozent des Bestands standen als "62.0¢" in derselben Spalte wie
        # echte Cent-Werte.
        rows = apv.alert_rows(pd.DataFrame([self._signal("Holder concentration", 0.62)]))
        self.assertEqual(rows[0]["value"], "62%")

    def test_a_volume_ratio_carries_its_unit(self) -> None:
        rows = apv.alert_rows(pd.DataFrame([self._signal("Volume anomaly", 3.5)]))
        self.assertEqual(rows[0]["value"], "3.5x")

    def test_prices_and_moves_keep_their_cents(self) -> None:
        rows = apv.alert_rows(pd.DataFrame([
            self._signal("Fast mover", 0.08),
            self._signal("Tight spread", 0.02),
            self._signal("Whale print", 12_000.0, notional=12_000.0, side="BUY"),
        ]))
        werte = {r["rule"]: r["value"] for r in rows}
        self.assertEqual(werte["FAST MOVER"], "+8.0¢")
        self.assertEqual(werte["TIGHT SPREAD"], "2.0¢")
        self.assertEqual(werte["WHALE PRINT"], "$12,000")

