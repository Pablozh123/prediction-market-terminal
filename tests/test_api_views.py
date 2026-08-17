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
        payload = apv.cluster_payload(fresh, coord, nodes, edges, lambda cn, ce: {"headline": "Two wallets, three shared markets."})
        self.assertEqual(payload["fresh"][0]["score"], 4)
        self.assertEqual(payload["timing"][0]["window"], "40 s")
        self.assertEqual(payload["network"][0]["size"], 2)
        self.assertIn("Two wallets", payload["network"][0]["story"])
        self.assertEqual(payload["kpis_clusters"], {"fresh_clusters": 1, "coordinated_clusters": 1})


class VariantsPayloadTests(unittest.TestCase):
    def test_maps_comparison_frame(self) -> None:
        frame = pd.DataFrame([{"strategy": "Fixed $25", "final_equity": 1100.0, "roi": 0.1,
                               "max_drawdown": -0.05, "win_rate": 0.6, "copied_trades": 10, "skipped_trades": 2}])
        rows = apv.variants_payload(frame)
        self.assertEqual(rows[0]["name"], "Fixed $25")
        self.assertEqual(rows[0]["final_equity"], 1100.0)


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


class MarketRecordsTests(unittest.TestCase):
    """/api/markets liefert nur die Felder, die das Frontend liest."""

    def _frame(self) -> pd.DataFrame:
        return pd.DataFrame([
            {
                "market_key": "0xcond1", "ticker": "0xcond1", "slug": "fed-cuts", "title": "Fed cuts rates",
                "platform": "Polymarket", "category": "Economics", "filter_category": "Finance",
                "yes_price": 0.62, "change_1d": 0.03, "volume_24h": 120000.0, "liquidity": 40000.0,
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
             "polymarket_volume": 100000.0, "kalshi_volume": 40000.0, "similarity": 0.71},
            {"polymarket_title": "too dissimilar", "kalshi_title": "x", "polymarket_yes": 0.79, "kalshi_yes": 0.64,
             "polymarket_volume": 100000.0, "kalshi_volume": 40000.0, "similarity": 0.44},
            {"polymarket_title": "no kalshi volume", "kalshi_title": "x", "polymarket_yes": 0.5, "kalshi_yes": 0.5,
             "polymarket_volume": 100000.0, "kalshi_volume": 0.0, "similarity": 0.9},
            {"polymarket_title": "no polymarket volume", "kalshi_title": "x", "polymarket_yes": 0.5, "kalshi_yes": 0.5,
             "polymarket_volume": None, "kalshi_volume": 4000.0, "similarity": 0.9},
            {"polymarket_title": "exactly at the gate", "kalshi_title": "x", "polymarket_yes": 0.5, "kalshi_yes": 0.5,
             "polymarket_volume": 1.0, "kalshi_volume": 1.0, "similarity": 0.5},
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
        self.assertEqual(parts, [{"label": "return", "value": 13, "weight": 0.35}])
        self.assertEqual(apv.score_parts({}), [])
