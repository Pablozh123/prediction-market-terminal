import unittest

import pandas as pd

from app import suspicion as susp


def tape(rows):
    return pd.DataFrame(rows)


def trade(wallet, title, outcome="Yes", notional=5000.0, time="2026-06-10T12:00:00Z"):
    return {
        "wallet": wallet,
        "title": title,
        "outcome": outcome,
        "notional": notional,
        "time": pd.Timestamp(time),
    }


class FreshWalletClusterTests(unittest.TestCase):
    def test_cluster_of_fresh_wallets_same_side_is_detected(self):
        trades = tape(
            [
                trade("0xaaa", "Will X happen?", "Yes", 6000.0),
                trade("0xbbb", "Will X happen?", "Yes", 7000.0),
                trade("0xccc", "Will X happen?", "Yes", 8000.0),
                trade("0xddd", "Will X happen?", "No", 9000.0),
            ]
        )
        clusters = susp.fresh_wallet_clusters(trades, whale_threshold=2500.0)
        self.assertEqual(len(clusters), 1)
        row = clusters.iloc[0]
        self.assertEqual(row["title"], "Will X happen?")
        self.assertEqual(row["fresh_wallets"], 3)
        self.assertEqual(row["fresh_outcome"], "YES")
        self.assertAlmostEqual(row["fresh_notional"], 21000.0)

    def test_active_wallets_are_not_fresh(self):
        rows = [trade("0xaaa", "Busy market", "Yes", 6000.0, f"2026-06-10T0{i}:00:00Z") for i in range(5)]
        rows += [trade("0xbbb", "Busy market", "Yes", 6000.0)]
        clusters = susp.fresh_wallet_clusters(tape(rows), whale_threshold=2500.0)
        self.assertTrue(clusters.empty)

    def test_small_fresh_wallets_below_threshold_ignored(self):
        trades = tape(
            [
                trade("0xaaa", "Tiny market", "Yes", 100.0),
                trade("0xbbb", "Tiny market", "Yes", 150.0),
            ]
        )
        clusters = susp.fresh_wallet_clusters(trades, whale_threshold=2500.0)
        self.assertTrue(clusters.empty)


class BonusTests(unittest.TestCase):
    def _event_risk(self):
        return pd.DataFrame(
            [
                {"title": "Will X happen?", "event_insider_score": 55.0, "event_insider_flags": "long-odds big bet", "notional": 20000.0},
                {"title": "Quiet market", "event_insider_score": 20.0, "event_insider_flags": "watch only", "notional": 5000.0},
            ]
        )

    def test_fresh_cluster_bonus_and_flag(self):
        clusters = pd.DataFrame([{"title": "Will X happen?", "fresh_wallets": 3, "fresh_outcome": "YES", "fresh_notional": 21000.0}])
        enriched = susp.apply_fresh_wallet_bonus(self._event_risk(), clusters)
        hot = enriched[enriched["title"] == "Will X happen?"].iloc[0]
        self.assertAlmostEqual(hot["event_insider_score"], round(55.0 + 7.5), places=1)
        self.assertIn("3 fresh wallets on YES", hot["event_insider_flags"])
        quiet = enriched[enriched["title"] == "Quiet market"].iloc[0]
        self.assertAlmostEqual(quiet["event_insider_score"], 20.0)
        self.assertEqual(quiet["event_insider_flags"], "watch only")

    def test_score_capped_at_100(self):
        events = pd.DataFrame([{"title": "Hot", "event_insider_score": 96.0, "event_insider_flags": ""}])
        clusters = pd.DataFrame([{"title": "Hot", "fresh_wallets": 4, "fresh_outcome": "YES", "fresh_notional": 1.0}])
        enriched = susp.apply_fresh_wallet_bonus(events, clusters)
        self.assertEqual(enriched.iloc[0]["event_insider_score"], 100.0)
        self.assertEqual(enriched.iloc[0]["event_insider_level"], "High")

    def test_account_age_bonus_only_for_young_accounts(self):
        wallet_risk = pd.DataFrame(
            [
                {"wallet": "0xAAA", "wallet_insider_score": 50.0, "wallet_insider_flags": "watch only"},
                {"wallet": "0xbbb", "wallet_insider_score": 50.0, "wallet_insider_flags": "fast burst"},
            ]
        )
        stats = pd.DataFrame(
            [
                {"wallet": "0xaaa", "account_age_days": 5.0},
                {"wallet": "0xbbb", "account_age_days": 400.0},
            ]
        )
        enriched = susp.apply_account_age_bonus(wallet_risk, stats)
        young = enriched[enriched["wallet"].str.lower() == "0xaaa"].iloc[0]
        old = enriched[enriched["wallet"].str.lower() == "0xbbb"].iloc[0]
        self.assertAlmostEqual(young["wallet_insider_score"], 60.0)
        self.assertIn("new account (5d)", young["wallet_insider_flags"])
        self.assertAlmostEqual(old["wallet_insider_score"], 50.0)
        self.assertNotIn("new account", old["wallet_insider_flags"])

    def test_missing_stats_leave_scores_unchanged(self):
        wallet_risk = pd.DataFrame([{"wallet": "0xaaa", "wallet_insider_score": 50.0, "wallet_insider_flags": ""}])
        enriched = susp.apply_account_age_bonus(wallet_risk, pd.DataFrame())
        self.assertAlmostEqual(enriched.iloc[0]["wallet_insider_score"], 50.0)


class CategoryContextTests(unittest.TestCase):
    def test_classifier_groups(self):
        cases = [
            ("Lakers vs Celtics: who wins?", "", susp.CONTEXT_SPORTS),
            ("Will Bitcoin hit $200k in 2026?", "", susp.CONTEXT_MARKET_PRICES),
            ("Highest temperature in NYC this week?", "", susp.CONTEXT_WEATHER),
            ("Will the film win Best Picture at the Oscars?", "", susp.CONTEXT_AWARDS),
            ("Will the CEO resign before July?", "", susp.CONTEXT_CORPORATE),
            ("Who wins the 2026 election?", "Politics", susp.CONTEXT_POLITICS),
            ("Will there be a ceasefire by July?", "", susp.CONTEXT_POLITICS),
            ("Some niche market", "Sports", susp.CONTEXT_SPORTS),
            ("Spread: Knicks (-1.5)", "", susp.CONTEXT_SPORTS),
            ("Lakers moneyline tonight", "", susp.CONTEXT_SPORTS),
            ("Some niche question", "", susp.CONTEXT_GENERAL),
        ]
        for title, category, expected in cases:
            group, multiplier, _note = susp.classify_insider_context(title, category)
            self.assertEqual(group, expected, title)
            self.assertEqual(multiplier, susp.CONTEXT_MULTIPLIERS[expected])

    def test_title_keywords_beat_category(self):
        group, _, _ = susp.classify_insider_context("Will the CEO resign before July?", "Politics")
        self.assertEqual(group, susp.CONTEXT_CORPORATE)

    def test_event_scores_damped_for_sports_and_boosted_for_awards(self):
        events = pd.DataFrame(
            [
                {"title": "Lakers vs Celtics: who wins?", "market_key": "c1", "event_insider_score": 80.0, "event_insider_flags": "", "notional": 50000.0},
                {"title": "Will the film win Best Picture at the Oscars?", "market_key": "c2", "event_insider_score": 80.0, "event_insider_flags": "", "notional": 20000.0},
            ]
        )
        adjusted = susp.apply_category_context(events)
        awards = adjusted[adjusted["market_key"] == "c2"].iloc[0]
        sports = adjusted[adjusted["market_key"] == "c1"].iloc[0]
        self.assertAlmostEqual(sports["event_insider_score"], 48.0)
        self.assertEqual(sports["insider_context"], susp.CONTEXT_SPORTS)
        self.assertAlmostEqual(sports["event_score_raw"], 80.0)
        self.assertAlmostEqual(awards["event_insider_score"], 92.0)
        self.assertEqual(adjusted.iloc[0]["market_key"], "c2")

    def test_category_map_used_when_title_is_neutral(self):
        events = pd.DataFrame([{"title": "Will team Alpha prevail?", "market_key": "c9", "event_insider_score": 60.0, "event_insider_flags": "", "notional": 1000.0}])
        categories = pd.DataFrame([{"market_key": "c9", "category": "Sports"}])
        adjusted = susp.apply_category_context(events, categories)
        self.assertEqual(adjusted.iloc[0]["insider_context"], susp.CONTEXT_SPORTS)
        self.assertAlmostEqual(adjusted.iloc[0]["event_insider_score"], 36.0)

    def test_dominant_context_map_weights_by_notional(self):
        trades = tape(
            [
                trade("0xAAA", "Lakers vs Celtics: who wins?", "Yes", 9000.0),
                trade("0xaaa", "Will there be a ceasefire by July?", "Yes", 1000.0),
                trade("0xbbb", "Will there be a ceasefire by July?", "Yes", 5000.0),
            ]
        )
        mapping = susp.dominant_context_map(trades)
        self.assertEqual(mapping["0xaaa"], susp.CONTEXT_SPORTS)
        self.assertEqual(mapping["0xbbb"], susp.CONTEXT_POLITICS)

    def test_dominant_context_map_empty_tape(self):
        self.assertEqual(susp.dominant_context_map(pd.DataFrame()), {})

    def test_wallet_context_weights_by_notional(self):
        trades = tape(
            [
                trade("0xaaa", "Lakers vs Celtics: who wins?", "Yes", 9000.0),
                trade("0xaaa", "Lakers vs Celtics: who wins?", "Yes", 9000.0),
                trade("0xbbb", "Will the CEO resign before July?", "Yes", 9000.0),
            ]
        )
        wallet_risk = pd.DataFrame(
            [
                {"wallet": "0xaaa", "wallet_insider_score": 70.0, "wallet_insider_flags": "watch only", "notional": 18000.0},
                {"wallet": "0xbbb", "wallet_insider_score": 70.0, "wallet_insider_flags": "watch only", "notional": 9000.0},
            ]
        )
        adjusted = susp.apply_wallet_category_context(wallet_risk, trades)
        sports_wallet = adjusted[adjusted["wallet"] == "0xaaa"].iloc[0]
        corp_wallet = adjusted[adjusted["wallet"] == "0xbbb"].iloc[0]
        self.assertAlmostEqual(sports_wallet["wallet_insider_score"], 42.0)
        self.assertIn("flow mostly in sports odds", sports_wallet["wallet_insider_flags"])
        self.assertEqual(corp_wallet["insider_context"], susp.CONTEXT_CORPORATE)
        self.assertAlmostEqual(corp_wallet["wallet_insider_score"], 80.0)
        self.assertIn("insider-prone categories", corp_wallet["wallet_insider_flags"])


class CoordinationTests(unittest.TestCase):
    def test_tight_window_cluster_detected(self):
        rows = [
            trade("0xaaa", "Ceasefire by July?", "Yes", 5000.0, "2026-06-10T12:00:00Z"),
            trade("0xbbb", "Ceasefire by July?", "Yes", 6000.0, "2026-06-10T12:10:00Z"),
            trade("0xccc", "Ceasefire by July?", "Yes", 7000.0, "2026-06-10T12:20:00Z"),
            trade("0xddd", "Ceasefire by July?", "Yes", 8000.0, "2026-06-10T18:00:00Z"),
        ]
        clusters = susp.coordinated_clusters(tape(rows), window_minutes=30.0, min_wallets=3)
        self.assertEqual(len(clusters), 1)
        row = clusters.iloc[0]
        self.assertEqual(row["coordinated_wallets"], 3)
        self.assertEqual(row["coordinated_outcome"], "YES")
        self.assertLessEqual(row["coordinated_span_minutes"], 30.0)

    def test_spread_out_trades_are_not_a_cluster(self):
        rows = [
            trade("0xaaa", "Slow market", "Yes", 5000.0, "2026-06-10T01:00:00Z"),
            trade("0xbbb", "Slow market", "Yes", 5000.0, "2026-06-10T05:00:00Z"),
            trade("0xccc", "Slow market", "Yes", 5000.0, "2026-06-10T09:00:00Z"),
        ]
        clusters = susp.coordinated_clusters(tape(rows), window_minutes=30.0, min_wallets=3)
        self.assertTrue(clusters.empty)

    def test_coordination_bonus_applied(self):
        events = pd.DataFrame([{"title": "Ceasefire by July?", "event_insider_score": 50.0, "event_insider_flags": "", "notional": 10000.0}])
        clusters = pd.DataFrame([{"title": "Ceasefire by July?", "coordinated_wallets": 4, "coordinated_outcome": "YES", "coordinated_span_minutes": 12.0, "coordinated_notional": 20000.0}])
        enriched = susp.apply_coordination_bonus(events, clusters)
        self.assertAlmostEqual(enriched.iloc[0]["event_insider_score"], 58.0)
        self.assertIn("4 wallets within 12min on YES", enriched.iloc[0]["event_insider_flags"])


class CoTradingClusterTests(unittest.TestCase):
    def test_wallets_sharing_two_markets_cluster_together(self):
        rows = [
            trade("0xaaa", "Market A", "Yes", 5000.0),
            trade("0xaaa", "Market B", "No", 5000.0),
            trade("0xbbb", "Market A", "Yes", 5000.0),
            trade("0xbbb", "Market B", "No", 5000.0),
            trade("0xccc", "Market A", "Yes", 5000.0),
        ]
        clusters = susp.wallet_co_trading_clusters(tape(rows), min_shared=2)
        self.assertEqual(set(clusters["wallet"]), {"0xaaa", "0xbbb"})
        self.assertTrue((clusters["cluster_size"] == 2).all())
        self.assertTrue((clusters["shared_markets"] >= 2).all())

    def test_opposite_sides_do_not_cluster(self):
        rows = [
            trade("0xaaa", "Market A", "Yes", 5000.0),
            trade("0xaaa", "Market B", "Yes", 5000.0),
            trade("0xbbb", "Market A", "No", 5000.0),
            trade("0xbbb", "Market B", "No", 5000.0),
        ]
        clusters = susp.wallet_co_trading_clusters(tape(rows), min_shared=2)
        self.assertTrue(clusters.empty)

    def test_cluster_bonus_and_flag(self):
        wallet_risk = pd.DataFrame([
            {"wallet": "0xAAA", "wallet_insider_score": 60.0, "wallet_insider_flags": "watch only"},
            {"wallet": "0xzzz", "wallet_insider_score": 60.0, "wallet_insider_flags": "watch only"},
        ])
        clusters = pd.DataFrame([{"wallet": "0xaaa", "cluster_id": 1, "cluster_size": 3, "shared_markets": 2}])
        enriched = susp.apply_cluster_bonus(wallet_risk, clusters)
        linked = enriched[enriched["wallet"].str.lower() == "0xaaa"].iloc[0]
        unlinked = enriched[enriched["wallet"].str.lower() == "0xzzz"].iloc[0]
        self.assertAlmostEqual(linked["wallet_insider_score"], 65.0)
        self.assertIn("moves with 2 other wallets", linked["wallet_insider_flags"])
        self.assertAlmostEqual(unlinked["wallet_insider_score"], 60.0)


class CoTradingNetworkTests(unittest.TestCase):
    def _syndicate_rows(self):
        rows = []
        for market in ("Market A", "Market B", "Market C"):
            for wallet in ("0xaaa", "0xbbb", "0xccc"):
                rows.append(trade(wallet, market, "Yes", 5000.0, "2026-06-10T12:00:00Z"))
        for market in ("Market X", "Market Y"):
            for wallet in ("0xddd", "0xeee"):
                rows.append(trade(wallet, market, "No", 4000.0, "2026-06-10T13:00:00Z"))
        return rows

    def test_two_separate_syndicates_become_two_clusters(self):
        nodes, edges = susp.co_trading_network(tape(self._syndicate_rows()), window_minutes=5.0, min_shared=2)
        self.assertEqual(set(nodes["wallet"]), {"0xaaa", "0xbbb", "0xccc", "0xddd", "0xeee"})
        self.assertEqual(nodes["cluster_id"].nunique(), 2)
        big = nodes[nodes["wallet"] == "0xaaa"].iloc[0]
        self.assertEqual(big["cluster_size"], 3)
        self.assertEqual(big["cluster_id"], 1)
        self.assertGreaterEqual(big["shared_markets"], 2)
        self.assertFalse(edges.empty)

    def test_time_window_excludes_slow_co_movers(self):
        rows = [
            trade("0xaaa", "Market A", "Yes", 5000.0, "2026-06-10T12:00:00Z"),
            trade("0xbbb", "Market A", "Yes", 5000.0, "2026-06-10T15:00:00Z"),
            trade("0xaaa", "Market B", "Yes", 5000.0, "2026-06-10T12:00:00Z"),
            trade("0xbbb", "Market B", "Yes", 5000.0, "2026-06-10T15:00:00Z"),
        ]
        nodes, _ = susp.co_trading_network(tape(rows), window_minutes=5.0, min_shared=2)
        self.assertTrue(nodes.empty)
        nodes_loose, _ = susp.co_trading_network(tape(rows), window_minutes=None, min_shared=2)
        self.assertEqual(set(nodes_loose["wallet"]), {"0xaaa", "0xbbb"})

    def test_min_pair_notional_filters_weak_money_pairs(self):
        rows = [
            trade("0xaaa", "Market A", "Yes", 500.0),
            trade("0xbbb", "Market A", "Yes", 500.0),
            trade("0xaaa", "Market B", "Yes", 500.0),
            trade("0xbbb", "Market B", "Yes", 500.0),
        ]
        strict_nodes, _ = susp.co_trading_network(tape(rows), window_minutes=5.0, min_shared=2, min_pair_notional=10_000.0)
        self.assertTrue(strict_nodes.empty)
        loose_nodes, _ = susp.co_trading_network(tape(rows), window_minutes=5.0, min_shared=2)
        self.assertEqual(set(loose_nodes["wallet"]), {"0xaaa", "0xbbb"})

    def test_network_modularity_reports_meaningful_structure(self):
        nodes, edges = susp.co_trading_network(tape(self._syndicate_rows()), window_minutes=5.0, min_shared=2)
        modularity = susp.network_modularity(nodes, edges)
        self.assertIsNotNone(modularity)
        # The 0.3 "meaningful structure" bar applies to real tapes; this tiny
        # 5-node toy graph still has to show clearly positive partition quality.
        self.assertGreater(modularity, 0.2)

    def test_cluster_story_explains_tight_clique(self):
        rows = self._syndicate_rows()
        nodes, edges = susp.co_trading_network(tape(rows), window_minutes=5.0, min_shared=2)
        big = nodes[nodes["cluster_id"] == 1]
        big_edges = edges[edges["wallet_a"].isin(set(big["wallet"])) & edges["wallet_b"].isin(set(big["wallet"]))]
        story = susp.cluster_story(big, big_edges, tape(rows))
        self.assertIn("3 wallets", story["headline"])
        self.assertEqual(story["pattern"], "Tight clique")
        self.assertTrue(any("same side" in reason for reason in story["reasons"]))
        self.assertTrue(story["top_markets"])
        self.assertGreaterEqual(story["density"], 0.99)

    def test_cluster_story_labels_loose_chain(self):
        nodes = pd.DataFrame(
            [{"wallet": f"0x{i}", "cluster_id": 1, "cluster_size": 6, "shared_markets": 2, "volume": 1000.0, "markets": 2, "trades": 2} for i in range(6)]
        )
        edges = pd.DataFrame([{"wallet_a": "0x0", "wallet_b": "0x1", "shared_markets": 2, "pair_notional": 2000.0}])
        story = susp.cluster_story(nodes, edges, pd.DataFrame())
        self.assertEqual(story["pattern"], "Loose chain")
        self.assertTrue(any("herd behavior" in reason for reason in story["reasons"]))

    def test_cluster_layout_separates_islands(self):
        nodes, _ = susp.co_trading_network(tape(self._syndicate_rows()), window_minutes=5.0, min_shared=2)
        placed = susp.cluster_layout(nodes)
        self.assertTrue({"x", "y"}.issubset(placed.columns))
        centers = placed.groupby("cluster_id")[["x", "y"]].mean()
        self.assertEqual(len(centers), 2)
        distance = ((centers.iloc[0] - centers.iloc[1]) ** 2).sum() ** 0.5
        self.assertGreater(distance, 5.0)


class StoryAndDrilldownTests(unittest.TestCase):
    def test_event_story_mentions_key_patterns(self):
        row = pd.Series(
            {
                "notional": 45000.0,
                "unique_wallets": 4,
                "long_odds_share": 0.6,
                "late_share": 0.5,
                "top_wallet_share": 0.7,
                "fresh_wallets": 3,
                "fresh_outcome": "YES",
                "event_directional_share": 0.9,
                "event_directional_label": "YES",
                "price_move": 0.06,
            }
        )
        story = susp.event_story(row)
        self.assertIn("whale flow from 4 wallets", story)
        self.assertIn("long odds", story)
        self.assertIn("close to resolution", story)
        self.assertIn("3 fresh wallets on YES", story)
        self.assertIn("+6c", story)

    def test_event_story_handles_quiet_event(self):
        story = susp.event_story(pd.Series({"notional": 5000.0, "unique_wallets": 1}))
        self.assertIn("no single dominant pattern", story)

    def test_wallets_for_event_filters_and_sorts(self):
        trades = tape(
            [
                trade("0xaaa", "Will X happen?"),
                trade("0xbbb", "Will X happen?"),
                trade("0xccc", "Other market"),
            ]
        )
        wallet_risk = pd.DataFrame(
            [
                {"wallet": "0xaaa", "wallet_insider_score": 40.0},
                {"wallet": "0xbbb", "wallet_insider_score": 80.0},
                {"wallet": "0xccc", "wallet_insider_score": 90.0},
            ]
        )
        subset = susp.wallets_for_event(trades, wallet_risk, "Will X happen?")
        self.assertEqual(list(subset["wallet"]), ["0xbbb", "0xaaa"])


if __name__ == "__main__":
    unittest.main()
