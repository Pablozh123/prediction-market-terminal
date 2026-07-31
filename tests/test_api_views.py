"""Tests fuer app/api_views.py — das JSON-Mapping der Terminal-API."""

from __future__ import annotations

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


class CrossRowsTests(unittest.TestCase):
    def test_maps_candidate_frame(self) -> None:
        frame = pd.DataFrame([
            {
                "polymarket_title": "Fed cuts rates", "kalshi_title": "Fed cut",
                "polymarket_yes": 0.62, "kalshi_yes": 0.60,
                "polymarket_volume": 100000.0, "kalshi_volume": 40000.0,
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
        self.assertEqual(payload["positions"][0][0], "Brazil win")
        self.assertEqual(payload["equity_curve"][-1], 1043.18)


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
                   "skipped_trades": 3, "fees_paid": 2.5, "open_value": 80.0, "window_truncated": True},
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


class PipelineTrimTests(unittest.TestCase):
    def test_trims_entries_and_word_counters(self) -> None:
        payload = {
            "hinweis": "x",
            "eintraege": [{"a": i} for i in range(200)],
            "wortzaehler_endstaende": {"m": 3},
            "laeufe": [{"profil": "p1", "eintraege": [1, 2, 3], "wortzaehler_endstaende": {"m": 1}, "n_eintraege": 3}],
        }
        out = apv.trim_pipeline_payload(payload, max_entries=40)
        self.assertEqual(len(out["eintraege"]), 40)
        self.assertNotIn("wortzaehler_endstaende", out)
        self.assertNotIn("eintraege", out["laeufe"][0])
        self.assertEqual(out["laeufe"][0]["n_eintraege"], 3)
        # Original bleibt unangetastet
        self.assertEqual(len(payload["eintraege"]), 200)


if __name__ == "__main__":
    unittest.main()
