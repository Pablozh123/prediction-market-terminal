import unittest

import pandas as pd

from app import suspicion as susp
from src import prediction_markets as md


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


class PlatzhalterIstKeineWalletTests(unittest.TestCase):
    """Kalshi veroeffentlicht keine Wallets und stempelt "Not public" ein.

    Ueber die Wallet gruppiert faellt damit jeder Kalshi-Print der Venue in
    einen einzigen Pseudo-Trader mit dem gebuendelten Volumen des ganzen
    Bandes. Der stand mit 71/100 ("High") ueber jeder echten Adresse (57) an
    der Spitze der Wallet-Tabelle des Risk-Screens.
    """

    def _mixed_tape(self):
        base = pd.Timestamp("2026-08-28T12:00:00", tz="UTC")
        rows = [{
            "platform": "Kalshi", "time": base + pd.Timedelta(seconds=20 * i), "wallet": "Not public",
            "trader": "Not public", "side": "yes", "outcome": "yes", "title": f"KXCEO-26AUG28-{i % 5}",
            "market_key": f"KXCEO-26AUG28-{i % 5}", "price": 0.08, "size": 40000, "notional": 3200.0,
            "end_time": base + pd.Timedelta(hours=10),
        } for i in range(40)]
        rows.append({
            "platform": "Polymarket", "time": base, "wallet": "0x" + "1" * 40, "trader": "", "side": "BUY",
            "outcome": "Yes", "title": "Will the CEO resign?", "market_key": "0xabc", "price": 0.1,
            "size": 30000, "notional": 3000.0, "end_time": base + pd.Timedelta(hours=10),
        })
        return pd.DataFrame(rows)

    def test_identified_wallets_rejects_the_placeholder(self) -> None:
        mask = md.identified_wallets(pd.Series(["0xabc", "Not public", "not public", "", "nan", "NaN", "None"]))
        self.assertEqual(list(mask), [True, False, False, False, False, False, False])

    def test_the_pooled_venue_never_reaches_the_wallet_scores(self) -> None:
        scores = md.whale_wallet_risk_scores(self._mixed_tape(), whale_threshold=2500.0)
        self.assertEqual(list(scores["wallet"]), ["0x" + "1" * 40])

    def test_fresh_wallet_clusters_ignore_it_too(self) -> None:
        clusters = susp.fresh_wallet_clusters(self._mixed_tape(), whale_threshold=2500.0)
        self.assertTrue(clusters.empty)


class ZaehleinheitMarktTests(unittest.TestCase):
    """Ein Markt ist ein Schluessel, kein Titel.

    Die wiederkehrende Podcast-Frage laeuft jede Woche unter einer neuen
    conditionId: von den 45 aufgeloesten Maerkten der Referenz-Wallet tragen
    nur 43 verschiedene Titel. Ueber den Titel gruppiert sehen zwei Folgen
    wie ein Markt aus, und "single-market concentration" schlaegt bei einer
    Wallet an, die ihren Flow auf zwei verteilt hat.
    """

    def _tape(self):
        base = pd.Timestamp("2026-08-28T12:00:00", tz="UTC")
        titel = 'Will "Nvidia" be said during the next episode of the All-In Podcast?'
        return pd.DataFrame([
            {"platform": "Polymarket", "time": base, "wallet": "0x" + "1" * 40, "trader": "", "side": "BUY",
             "outcome": "Yes", "title": titel, "market_key": "0xweek1", "price": 0.4, "size": 10000,
             "notional": 4000.0, "end_time": base + pd.Timedelta(days=5)},
            {"platform": "Polymarket", "time": base + pd.Timedelta(minutes=3), "wallet": "0x" + "1" * 40,
             "trader": "", "side": "BUY", "outcome": "Yes", "title": titel, "market_key": "0xweek2",
             "price": 0.4, "size": 10000, "notional": 4000.0, "end_time": base + pd.Timedelta(days=12)},
        ])

    def test_two_episodes_are_two_markets(self) -> None:
        scores = md.whale_wallet_risk_scores(self._tape(), whale_threshold=2500.0)
        row = scores.iloc[0]
        self.assertEqual(int(row["markets"]), 2)
        self.assertAlmostEqual(float(row["top_market_share"]), 0.5, places=6)
        self.assertNotIn("single-market concentration", str(row["wallet_insider_flags"]))

    def test_the_card_still_shows_the_question_not_the_key(self) -> None:
        scores = md.whale_wallet_risk_scores(self._tape(), whale_threshold=2500.0)
        self.assertIn("Nvidia", str(scores.iloc[0]["top_market"]))

    def test_market_identity_falls_back_to_the_title(self) -> None:
        frame = pd.DataFrame([{"title": "A question", "market_key": ""}, {"title": "B", "market_key": "0xb"}])
        self.assertEqual(list(md.market_identity(frame)), ["A question", "0xb"])


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
            ("Exact Score: Mexico 3 - 3 South Africa?", "", susp.CONTEXT_SPORTS),
            ("Mexico leading at halftime?", "", susp.CONTEXT_SPORTS),
            ("Mexico wins by over 1.5 goals?", "", susp.CONTEXT_SPORTS),
            ("Will Mexico score over 1.5 goals?", "", susp.CONTEXT_SPORTS),
            ("Who lifts the World Cup?", "", susp.CONTEXT_SPORTS),
            ("Will the UN reach its climate goals?", "", susp.CONTEXT_GENERAL),
            ("Some niche question", "", susp.CONTEXT_GENERAL),
        ]
        for title, category, expected in cases:
            group, multiplier, _note = susp.classify_insider_context(title, category)
            self.assertEqual(group, expected, title)
            self.assertEqual(multiplier, susp.CONTEXT_MULTIPLIERS[expected])

    def test_title_keywords_beat_category(self):
        group, _, _ = susp.classify_insider_context("Will the CEO resign before July?", "Politics")
        self.assertEqual(group, susp.CONTEXT_CORPORATE)

    def test_event_title_context_classifies_neutral_submarket_titles(self):
        # Polymarket sub-markets ("Will Mexico win on 2026-06-11?") carry no sports
        # keyword — the parent event title ("Mexico vs. South Africa") must decide.
        group, _, _ = susp.classify_insider_context("Will Mexico win on 2026-06-11?", "", "Mexico vs. South Africa")
        self.assertEqual(group, susp.CONTEXT_SPORTS)
        # ...but an election-day market must stay politics, not sports.
        group, _, _ = susp.classify_insider_context("Will Newsom win on 2026-11-03?", "", "California Governor Election 2026")
        self.assertEqual(group, susp.CONTEXT_POLITICS)

    def test_apply_category_context_uses_context_text_column(self):
        events = pd.DataFrame(
            [{"title": "Will Mexico win on 2026-06-11?", "market_key": "0xc1", "event_insider_score": 80.0, "event_insider_flags": "", "notional": 50000.0}]
        )
        categories = pd.DataFrame([{"market_key": "0xc1", "category": "", "context_text": "Mexico vs. South Africa"}])
        adjusted = susp.apply_category_context(events, categories)
        self.assertEqual(adjusted.iloc[0]["insider_context"], susp.CONTEXT_SPORTS)
        self.assertAlmostEqual(adjusted.iloc[0]["event_insider_score"], 48.0)

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
                "trades": 8,
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
        self.assertIn("8 sampled prints", story)
        self.assertIn("long odds", story)
        self.assertIn("close to resolution", story)
        self.assertIn("one wallet drives 70", story)
        self.assertIn("3 fresh wallets on YES", story)
        self.assertIn("+6c", story)

    def test_event_story_single_print_makes_no_distribution_claims(self):
        row = pd.Series(
            {
                "notional": 11100.0,
                "unique_wallets": 1,
                "trades": 1,
                "long_odds_share": 1.0,
                "top_wallet_share": 1.0,
                "event_directional_share": 1.0,
                "event_directional_label": "YES",
            }
        )
        story = susp.event_story(row)
        self.assertIn("1 sampled print", story)
        self.assertIn("too few sampled prints", story)
        self.assertIn("placed at long odds", story)
        self.assertNotIn("one wallet drives", story)
        self.assertNotIn("of flow is YES", story)
        self.assertNotIn("100.0%", story)

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


class WalletlessVenueTests(unittest.TestCase):
    """Kalshi publishes no wallet identities — blank-wallet rows must feed event-level
    signals while every wallet-level helper skips them."""

    def _mixed_tape(self):
        rows = [
            trade("0xaaa", "Will X happen?", "Yes", 6000.0, "2026-06-10T12:00:00Z"),
            trade("0xbbb", "Will X happen?", "Yes", 7000.0, "2026-06-10T12:01:00Z"),
        ]
        rows += [
            trade("", "Fed decision in June?", "Yes", 15000.0, "2026-06-10T12:02:00Z"),
            trade("", "Fed decision in June?", "Yes", 18000.0, "2026-06-10T12:03:00Z"),
            trade("", "Fed decision in June?", "Yes", 22000.0, "2026-06-10T12:04:00Z"),
        ]
        return tape(rows)

    def test_event_story_for_walletless_event(self):
        story = susp.event_story(pd.Series({"notional": 55000.0, "unique_wallets": 0}))
        self.assertIn("wallet identities not public", story)
        self.assertNotIn("0 wallet", story)

    def test_fresh_wallet_clusters_ignore_blank_wallets(self):
        clusters = susp.fresh_wallet_clusters(self._mixed_tape(), whale_threshold=2500.0)
        self.assertNotIn("Fed decision in June?", set(clusters.get("title", pd.Series(dtype=str))))

    def test_coordinated_clusters_ignore_blank_wallets(self):
        clusters = susp.coordinated_clusters(self._mixed_tape(), window_minutes=30.0, min_wallets=2)
        self.assertNotIn("Fed decision in June?", set(clusters.get("title", pd.Series(dtype=str))))

    def test_co_trading_network_ignores_blank_wallets(self):
        rows = []
        for market in ("Fed decision in June?", "Rate cut by July?", "CPI above 3%?"):
            rows.append(trade("", market, "Yes", 15000.0, "2026-06-10T12:00:00Z"))
            rows.append(trade("", market, "Yes", 18000.0, "2026-06-10T12:01:00Z"))
        nodes, edges = susp.co_trading_network(tape(rows), window_minutes=5.0, min_shared=2)
        self.assertTrue(nodes.empty)
        self.assertTrue(edges.empty)

    def test_wallets_for_event_returns_empty_for_walletless_event(self):
        wallet_risk = pd.DataFrame([{"wallet": "0xaaa", "wallet_insider_score": 40.0}])
        subset = susp.wallets_for_event(self._mixed_tape(), wallet_risk, "Fed decision in June?")
        self.assertTrue(subset.empty)


class AuditRegressionTests(unittest.TestCase):
    """Regressions for the 2026-07 adversarial audit findings."""

    def test_vs_titles_with_corporate_or_politics_markers_not_sports(self):
        group, _, _ = susp.classify_insider_context("Epic vs Apple ruling upheld?")
        self.assertEqual(group, susp.CONTEXT_CORPORATE)
        group, _, _ = susp.classify_insider_context("Zelensky vs Putin meeting in 2025?")
        self.assertEqual(group, susp.CONTEXT_POLITICS)

    def test_esports_counter_strike_is_sports_not_politics(self):
        # "strike" inside "Counter-Strike" must not trigger the politics
        # pattern; strong sports markers win before everything else.
        group, _, _ = susp.classify_insider_context(
            "Counter-Strike: LPH Gaming vs TheBoys - Map 2 Winner"
        )
        self.assertEqual(group, susp.CONTEXT_SPORTS)
        group, _, _ = susp.classify_insider_context("Will Russia strike Kyiv in July?")
        self.assertEqual(group, susp.CONTEXT_POLITICS)

    def test_wnba_and_finals_are_sports(self):
        group, _, _ = susp.classify_insider_context("Will Atlanta Dream win the 2026 WNBA Finals?")
        self.assertEqual(group, susp.CONTEXT_SPORTS)
        # ...but a singular legal "final ruling" must stay corporate/legal.
        group, _, _ = susp.classify_insider_context("Will the court issue a final ruling by August?")
        self.assertEqual(group, susp.CONTEXT_CORPORATE)

    def test_plain_matchup_still_sports(self):
        group, _, _ = susp.classify_insider_context("Mexico vs. South Africa")
        self.assertEqual(group, susp.CONTEXT_SPORTS)
        group, _, _ = susp.classify_insider_context(
            "Will Mexico win on 2026-06-11?", context_text="Mexico vs. South Africa"
        )
        self.assertEqual(group, susp.CONTEXT_SPORTS)

    def test_science_category_is_not_weather(self):
        group, _, _ = susp.classify_insider_context("Will the mission launch?", category="Science")
        self.assertNotEqual(group, susp.CONTEXT_WEATHER)

    def test_fresh_bonus_stays_on_its_platform(self):
        rows = [
            trade("0xaaa", "Fed decision in June?", "Yes", 20000.0),
            trade("0xbbb", "Fed decision in June?", "Yes", 22000.0),
        ]
        frame = tape(rows)
        frame["platform"] = "Polymarket"
        clusters = susp.fresh_wallet_clusters(frame, whale_threshold=10000.0)
        self.assertEqual(list(clusters["platform"]), ["Polymarket"])
        event_risk = pd.DataFrame(
            [
                {"platform": "Polymarket", "title": "Fed decision in June?", "event_insider_score": 40.0, "event_insider_level": "Elevated", "event_insider_flags": ""},
                {"platform": "Kalshi", "title": "Fed decision in June?", "event_insider_score": 40.0, "event_insider_level": "Elevated", "event_insider_flags": ""},
            ]
        )
        boosted = susp.apply_fresh_wallet_bonus(event_risk, clusters)
        by_platform = dict(zip(boosted["platform"], boosted["event_insider_score"]))
        self.assertGreater(by_platform["Polymarket"], 40.0)
        self.assertEqual(by_platform["Kalshi"], 40.0)

    def test_coordination_bonus_halved_when_burst_already_flagged(self):
        rows = [
            trade("0xaaa", "Cabinet pick announced?", "Yes", 15000.0, "2026-06-10T12:00:00Z"),
            trade("0xbbb", "Cabinet pick announced?", "Yes", 15000.0, "2026-06-10T12:05:00Z"),
            trade("0xccc", "Cabinet pick announced?", "Yes", 15000.0, "2026-06-10T12:10:00Z"),
        ]
        clusters = susp.coordinated_clusters(tape(rows))
        base = pd.DataFrame(
            [
                {"title": "Cabinet pick announced?", "event_insider_score": 40.0, "event_insider_level": "Elevated", "event_insider_flags": "multi-wallet burst"},
                {"title": "Second market?", "event_insider_score": 40.0, "event_insider_level": "Elevated", "event_insider_flags": "watch only"},
            ]
        )
        clusters_second = clusters.copy()
        clusters_second["title"] = "Second market?"
        boosted_bursty = susp.apply_coordination_bonus(base.iloc[[0]].copy(), clusters)
        boosted_clean = susp.apply_coordination_bonus(base.iloc[[1]].copy(), clusters_second)
        bursty_gain = float(boosted_bursty["event_insider_score"].iloc[0]) - 40.0
        clean_gain = float(boosted_clean["event_insider_score"].iloc[0]) - 40.0
        self.assertGreater(clean_gain, 0.0)
        self.assertAlmostEqual(bursty_gain, clean_gain / 2.0)

    def test_filter_insider_prone_trades_drops_sports(self):
        rows = [
            trade("0xaaa", "Lakers vs Celtics", "Yes", 15000.0),
            trade("0xbbb", "Cabinet pick announced?", "Yes", 15000.0),
        ]
        filtered = susp.filter_insider_prone_trades(tape(rows))
        self.assertEqual(list(filtered["title"]), ["Cabinet pick announced?"])

    def test_filter_insider_prone_trades_drops_crypto_minute_markets(self):
        """Krypto raus, sonst baut der belebteste Markt den groessten Cluster.

        Die Fuenf-Minuten-Up-Down-Maerkte sind die aktivsten der Venue, also
        fassen dort routinemaessig dutzende Wallets dieselben Titel an. Genau
        die Scheinverbindung soll der Filter verhindern.
        """
        rows = [
            trade("0xaaa", "Bitcoin Up or Down - August 6, 5:35PM-5:40PM ET", "Up", 15000.0),
            trade("0xbbb", "Ethereum Up or Down - August 6, 5PM ET", "Down", 15000.0),
            trade("0xccc", "Cabinet pick announced?", "Yes", 15000.0),
        ]
        filtered = susp.filter_insider_prone_trades(tape(rows))
        self.assertEqual(list(filtered["title"]), ["Cabinet pick announced?"])

    def test_matchday_submarkets_classify_as_sports(self):
        """Spieltag-Untermaerkte ohne Kontexttitel duerfen nicht durchrutschen.

        "Will FC Thun win on 2026-08-06?" traegt kein Liga- oder Vereinswort,
        das der Katalog kennt, und landete deshalb als General im
        Insider-Screen. Live baute genau das den groessten Cluster.
        """
        for titel in (
            "Will FC Thun win on 2026-08-06?",
            "Will FC Hradec Kralove win on 2026-08-06?",
            "Will Mexico win on 2026-06-11?",
        ):
            with self.subTest(titel=titel):
                self.assertEqual(susp.classify_insider_context(titel, None)[0], susp.CONTEXT_SPORTS)

    def test_matchday_muster_frisst_keine_politik(self):
        """Die Regel steht hinter Politik, sonst waere ein Wahltag Sport."""
        self.assertEqual(
            susp.classify_insider_context("Will the president win on 2026-11-03?", None)[0],
            susp.CONTEXT_POLITICS,
        )

    def test_filter_default_matches_the_insider_prone_focus(self):
        """Ausschlussliste und Fokusliste duerfen nicht auseinanderlaufen.

        Die Seite zeigt `INSIDER_PRONE_GROUPS`; wenn der Netzwerkfilter eine
        Gruppe durchlaesst, die dort nicht auftaucht, baut er Cluster aus
        Maerkten, die der Screen selbst nicht als insider-anfaellig fuehrt.
        """
        import inspect

        vorgabe = inspect.signature(susp.filter_insider_prone_trades).parameters["excluded"].default
        self.assertEqual(tuple(vorgabe), tuple(susp.EXCLUDED_CONTEXTS))
        self.assertEqual(
            inspect.signature(susp.exclude_contexts).parameters["excluded"].default,
            susp.EXCLUDED_CONTEXTS,
        )
        for gruppe in vorgabe:
            self.assertNotIn(gruppe, susp.INSIDER_PRONE_GROUPS)
        for gruppe in susp.CONTEXT_MULTIPLIERS:
            if gruppe not in susp.INSIDER_PRONE_GROUPS:
                self.assertIn(gruppe, vorgabe, f"{gruppe} wird gezeigt, aber nicht ausgeschlossen")


class MarketPricesExclusionTests(unittest.TestCase):
    """Crypto & market prices are EXCLUDED from the risk screen, exactly like
    sports odds and weather — not damped, not behind a toggle. Asset prices are
    public (no insider knowledge possible) and the 15-minute crypto markets
    would otherwise flood every output with noise."""

    BTC_TITLE = "Will Bitcoin hit $150k by December 31?"
    KALSHI_TICKER = "KXBTC15M-26AUG16-1345-T119000"
    POLITICS_TITLE = "Cabinet pick announced?"

    def _tape(self):
        rows = []
        # A large, bursty, one-sided crypto print stream that would score high
        # on every event/wallet signal if it were allowed into the screen.
        for i, wallet in enumerate(("0xc01", "0xc02", "0xc03", "0xc04")):
            rows.append(trade(wallet, self.BTC_TITLE, "Yes", 250_000.0, f"2026-06-10T12:0{i}:00Z"))
            rows.append(trade(wallet, self.KALSHI_TICKER, "Yes", 250_000.0, f"2026-06-10T12:0{i}:30Z"))
            rows.append(trade(wallet, "Ethereum Up or Down - August 6, 5PM ET", "Up", 250_000.0, f"2026-06-10T12:0{i}:45Z"))
        rows.append(trade("0xp01", self.POLITICS_TITLE, "Yes", 15_000.0, "2026-06-10T12:00:00Z"))
        rows.append(trade("0xp02", self.POLITICS_TITLE, "Yes", 15_000.0, "2026-06-10T12:01:00Z"))
        frame = tape(rows)
        frame["platform"] = "Polymarket"
        frame["market_key"] = frame["title"]
        return frame

    def test_market_prices_is_an_excluded_context(self):
        self.assertIn(susp.CONTEXT_MARKET_PRICES, susp.EXCLUDED_CONTEXTS)
        self.assertIn(susp.CONTEXT_SPORTS, susp.EXCLUDED_CONTEXTS)
        self.assertIn(susp.CONTEXT_WEATHER, susp.EXCLUDED_CONTEXTS)
        self.assertNotIn(susp.CONTEXT_MARKET_PRICES, susp.INSIDER_PRONE_GROUPS)
        # Excluded and focused groups partition the whole context space.
        self.assertEqual(set(susp.EXCLUDED_CONTEXTS) | set(susp.INSIDER_PRONE_GROUPS), set(susp.CONTEXT_MULTIPLIERS))
        self.assertFalse(set(susp.EXCLUDED_CONTEXTS) & set(susp.INSIDER_PRONE_GROUPS))

    def test_crypto_titles_and_kalshi_price_tickers_classify_as_market_prices(self):
        for title in (
            self.BTC_TITLE,
            self.KALSHI_TICKER,
            "KXETHD-26AUG16-T4200",
            "KXINXD-26AUG16-T6400",
            # Live /api/risk leaks (2026-08-16): 15-minute commodity tickers and
            # Polymarket's price-series formats classified as "General".
            "KXWTI15M-26AUG162045-45",
            "KXGOLD15M-26AUG162045-45",
            "Bitcoin Up or Down - August 16, 1:45PM-2:00PM ET",
            "BNB Up or Down - August 16, 8:30PM-8:45PM ET",
            "WTI Crude Oil (WTI) Up or Down on August 17?",
            "Will WTI Crude Oil (WTI) hit (HIGH) $85 in August?",
            "Will Crude Oil reach a new all-time high by December 31?",
            "Will Apple be the largest company in the world by market cap on December 31?",
            "Bitcoin price at 1:45pm EDT?",
        ):
            with self.subTest(title=title):
                self.assertEqual(susp.classify_insider_context(title)[0], susp.CONTEXT_MARKET_PRICES)
        # The ticker rule must not swallow unrelated KX tickers, and the new
        # price words must leave the insider-prone arenas alone.
        for title in (
            "KXETHIOPIA-26DEC31-YES",
            "Will Trump acquire Greenland before 2027?",
            "Iran charges Hormuz fees by August 31?",
            "Will Brent Venables be fired before the season ends?",
            "OpenAI IPO closing market cap above $800B?",
        ):
            with self.subTest(title=title):
                self.assertNotEqual(susp.classify_insider_context(title)[0], susp.CONTEXT_MARKET_PRICES)

    def test_filter_drops_every_crypto_print_before_scoring(self):
        screened = susp.filter_insider_prone_trades(self._tape())
        self.assertEqual(set(screened["title"]), {self.POLITICS_TITLE})
        self.assertEqual(len(screened), 2)

    def test_exclude_contexts_drops_scored_crypto_events_and_wallets(self):
        events = pd.DataFrame(
            [
                {"title": self.BTC_TITLE, "market_key": "b1", "event_insider_score": 95.0, "event_insider_flags": "long-odds big bet", "notional": 1_000_000.0},
                {"title": self.KALSHI_TICKER, "market_key": "b2", "event_insider_score": 95.0, "event_insider_flags": "multi-wallet burst", "notional": 1_000_000.0},
                {"title": "Lakers vs Celtics", "market_key": "s1", "event_insider_score": 95.0, "event_insider_flags": "", "notional": 1_000_000.0},
                {"title": self.POLITICS_TITLE, "market_key": "p1", "event_insider_score": 40.0, "event_insider_flags": "", "notional": 30_000.0},
            ]
        )
        scored = susp.apply_category_context(events)
        kept = susp.exclude_contexts(scored)
        self.assertEqual(list(kept["title"]), [self.POLITICS_TITLE])
        self.assertTrue(kept["insider_context"].isin(susp.INSIDER_PRONE_GROUPS).all())

        wallet_risk = pd.DataFrame(
            [
                {"wallet": "0xc01", "wallet_insider_score": 95.0, "wallet_insider_flags": "long-odds big bet", "notional": 750_000.0},
                {"wallet": "0xp01", "wallet_insider_score": 45.0, "wallet_insider_flags": "watch only", "notional": 15_000.0},
            ]
        )
        wallets = susp.exclude_contexts(susp.apply_wallet_category_context(wallet_risk, self._tape()))
        self.assertEqual(list(wallets["wallet"]), ["0xp01"])

    def test_large_crypto_print_never_reaches_any_screen_output(self):
        """End-to-end over the API pipeline: gate the tape, then score/cluster.

        A $250k-per-print, four-wallet, same-minute, same-side stream on
        "Will Bitcoin hit $150k…" / "KXBTC15M-…" must not appear in events,
        wallets, fresh-wallet clusters, timing clusters or the network.
        """
        from src import prediction_markets as md

        base = susp.filter_insider_prone_trades(self._tape())
        events = md.whale_event_risk_scores(base, whale_threshold=2_500.0)
        wallets = md.whale_wallet_risk_scores(base, whale_threshold=2_500.0)
        fresh = susp.fresh_wallet_clusters(base, whale_threshold=2_500.0)
        timing = susp.coordinated_clusters(base, window_minutes=30.0, min_wallets=2)
        nodes, edges = susp.co_trading_network(base, window_minutes=None, min_shared=1)

        crypto_titles = {self.BTC_TITLE, self.KALSHI_TICKER, "Ethereum Up or Down - August 6, 5PM ET"}
        crypto_wallets = {"0xc01", "0xc02", "0xc03", "0xc04"}
        for name, frame in (("events", events), ("fresh", fresh), ("timing", timing)):
            titles = set(frame["title"].astype(str)) if not frame.empty and "title" in frame else set()
            self.assertFalse(titles & crypto_titles, f"{name} still carries a crypto market: {titles & crypto_titles}")
        self.assertEqual(set(events["title"]), {self.POLITICS_TITLE})
        self.assertFalse(set(wallets["wallet"].astype(str).str.lower()) & crypto_wallets)
        self.assertFalse(set(nodes.get("wallet", pd.Series(dtype=str)).astype(str)) & crypto_wallets)
        for column in ("wallet_a", "wallet_b"):
            self.assertFalse(set(edges.get(column, pd.Series(dtype=str)).astype(str)) & crypto_wallets)

    def test_all_crypto_tape_yields_empty_screen_not_a_crypto_screen(self):
        rows = [
            trade("0xc01", self.BTC_TITLE, "Yes", 250_000.0),
            trade("0xc02", self.KALSHI_TICKER, "Yes", 250_000.0),
        ]
        screened = susp.filter_insider_prone_trades(tape(rows))
        self.assertTrue(screened.empty)


if __name__ == "__main__":
    unittest.main()


class KalshiSportsWeatherTickerTests(unittest.TestCase):
    """API-side Kalshi rows carry the raw ticker as title; the series must classify."""

    def test_sports_series_tickers_are_sports(self) -> None:
        for ticker in ("KXATPMATCH-26AUG16ROMHUR-HUR", "KXMLBGAME-26AUG16NYYBOS-NYY", "KXWNBAGAME-26AUG16IND-IND",
                       "KXVALORANTMAP-26AUG16-1", "KXWTASETWINNER-26AUG15BOUSTE-2-BOU"):
            self.assertEqual(susp.classify_insider_context(ticker, "")[0], susp.CONTEXT_SPORTS, ticker)

    def test_weather_series_tickers_are_weather(self) -> None:
        for ticker in ("KXHIGHTHOU-26AUG16-B90", "KXHIGHNY-26AUG16-T88", "KXRAINNYC-26AUG16"):
            self.assertEqual(susp.classify_insider_context(ticker, "")[0], susp.CONTEXT_WEATHER, ticker)

    def test_non_sports_kx_tickers_stay_untouched(self) -> None:
        self.assertNotIn(susp.classify_insider_context("KXETHIOPIA-26DEC31", "")[0], susp.EXCLUDED_CONTEXTS)
        self.assertEqual(susp.classify_insider_context("Will the president win on 2026-11-03?", "")[0], susp.CONTEXT_POLITICS)


class EventFlowDetailTests(unittest.TestCase):
    """Side, price, window, top wallets and link per event, from the same tape as the score."""

    def _tape(self) -> pd.DataFrame:
        base = {"platform": "Polymarket", "title": "Rate hike in September?", "market_key": "0xc1",
                "slug": "rate-hike-sep", "url": "https://polymarket.com/event/fed-september"}
        return pd.DataFrame([
            dict(base, time="2026-08-16T12:00:00Z", wallet="0xAAA1", side="BUY", outcome="No", price=0.30, notional=3000.0, asset="tokNO"),
            dict(base, time="2026-08-16T12:10:00Z", wallet="0xBBB2", side="BUY", outcome="No", price=0.34, notional=17000.0, asset="tokNO"),
            dict(base, time="2026-08-16T12:20:00Z", wallet="0xCCC3", side="BUY", outcome="Yes", price=0.66, notional=2000.0, asset="tokYES"),
            dict(base, time="2026-08-16T12:25:00Z", wallet="0xAAA1", side="SELL", outcome="Yes", price=0.65, notional=1000.0, asset="tokYES"),
            {"platform": "Kalshi", "title": "KXFED-26SEP", "market_key": "KXFED-26SEP", "time": "2026-08-16T12:20:00Z",
             "wallet": "Not public", "side": "yes", "outcome": "yes", "price": 0.40, "notional": 4000.0,
             "url": "https://kalshi.com/markets/KXFED-26SEP"},
        ])

    def test_side_split_dominant_side_and_prices(self) -> None:
        details = susp.event_flow_details(self._tape(), whale_threshold=2500.0)
        row = details[details["title"].eq("Rate hike in September?")].iloc[0]
        self.assertEqual(row["side"], "NO buys")
        self.assertAlmostEqual(row["side_buy_no"], 20000.0)
        self.assertAlmostEqual(row["side_buy_yes"], 2000.0)
        self.assertAlmostEqual(row["side_sell_yes"], 1000.0)
        self.assertAlmostEqual(row["side_sell_no"], 0.0)
        self.assertAlmostEqual(row["side_notional"], 20000.0)
        self.assertAlmostEqual(row["side_share"], 20000.0 / 23000.0)
        # Prices are those of the dominant side's outcome (NO), first/last by time.
        self.assertEqual(row["price_outcome"], "NO")
        self.assertAlmostEqual(row["price_first"], 0.30)
        self.assertAlmostEqual(row["price_last"], 0.34)
        self.assertAlmostEqual(row["price_min"], 0.30)
        self.assertAlmostEqual(row["price_max"], 0.34)
        self.assertEqual(row["token_id"], "tokNO")

    def test_window_top_wallets_and_link(self) -> None:
        details = susp.event_flow_details(self._tape(), whale_threshold=2500.0)
        row = details[details["title"].eq("Rate hike in September?")].iloc[0]
        self.assertEqual(str(row["first_print"]), "2026-08-16 12:00:00+00:00")
        self.assertEqual(str(row["last_print"]), "2026-08-16 12:25:00+00:00")
        self.assertAlmostEqual(row["window_minutes"], 25.0)
        # Gemessene Print-Positionen im Fenster (0..1): 12:00, 12:10, 12:20,
        # 12:25 auf 25 Minuten. Ein Ein-Print-Event (Kalshi) liegt auf 0.
        self.assertEqual(list(row["print_offsets"]), [0.0, 0.4, 0.8, 1.0])
        kalshi = susp.event_flow_details(self._tape(), whale_threshold=2500.0)
        kalshi_row = kalshi[kalshi["title"].eq("KXFED-26SEP")].iloc[0]
        self.assertEqual(list(kalshi_row["print_offsets"]), [0.0])
        wallets = row["top_wallets"]
        self.assertEqual([w["wallet"] for w in wallets], ["0xbbb2", "0xaaa1", "0xccc3"])
        self.assertAlmostEqual(wallets[0]["share"], 17000.0 / 23000.0)
        self.assertEqual(wallets[0]["side"], "NO buys")
        # 0xBBB2: one print, $17k >= threshold -> fresh; 0xAAA1: two prints but
        # only $4k in total; 0xCCC3: $2k below threshold. Neither is fresh.
        self.assertTrue(wallets[0]["fresh"])
        self.assertTrue(wallets[1]["fresh"])
        self.assertFalse(wallets[2]["fresh"])
        self.assertEqual(row["url"], "https://polymarket.com/event/fed-september")
        self.assertEqual(row["slug"], "rate-hike-sep")

    def test_fresh_is_none_when_not_computed_and_kalshi_has_no_wallets(self) -> None:
        details = susp.event_flow_details(self._tape())
        poly = details[details["title"].eq("Rate hike in September?")].iloc[0]
        self.assertIsNone(poly["top_wallets"][0]["fresh"])
        kalshi = details[details["title"].eq("KXFED-26SEP")].iloc[0]
        self.assertEqual(kalshi["top_wallets"], [])
        # Kalshi taker side "yes" is a YES buy; the price is the YES price.
        self.assertEqual(kalshi["side"], "YES buys")
        self.assertEqual(kalshi["price_outcome"], "YES")
        self.assertAlmostEqual(kalshi["price_last"], 0.40)
        self.assertEqual(kalshi["token_id"], "")

    def test_empty_and_walletless_frames(self) -> None:
        self.assertTrue(susp.event_flow_details(pd.DataFrame()).empty)
        self.assertTrue(susp.event_flow_details(None).empty)
        no_title = pd.DataFrame([{"wallet": "0x1", "notional": 5.0}])
        self.assertTrue(susp.event_flow_details(no_title).empty)

    def test_enrich_event_flow_merges_by_platform_and_title_and_keeps_base_url(self) -> None:
        from src import prediction_markets as md

        tape_df = self._tape()
        events = md.whale_event_risk_scores(tape_df, whale_threshold=2500.0)
        enriched = susp.enrich_event_flow(events, tape_df, whale_threshold=2500.0)
        self.assertEqual(len(enriched), len(events))
        poly = enriched[enriched["title"].eq("Rate hike in September?")].iloc[0]
        self.assertEqual(poly["side"], "NO buys")
        # The flow share (dominant YES/NO bucket) replaces the base BUY/SELL share.
        self.assertAlmostEqual(poly["side_share"], 20000.0 / 23000.0)
        self.assertEqual(poly["url"], "https://polymarket.com/event/fed-september")
        for column in ("price_last", "first_print", "last_print", "top_wallets", "window_minutes", "token_id"):
            self.assertIn(column, enriched.columns)
        # Base component columns survive the merge.
        self.assertIn("component_notional", enriched.columns)

    def test_enrich_event_flow_leaves_empty_frames_alone(self) -> None:
        empty = pd.DataFrame()
        self.assertTrue(susp.enrich_event_flow(empty, self._tape()).empty)
        events = pd.DataFrame([{"platform": "Polymarket", "title": "x", "event_insider_score": 10.0}])
        self.assertEqual(len(susp.enrich_event_flow(events, pd.DataFrame())), 1)


class EventComponentTests(unittest.TestCase):
    """Score components come out as labelled numbers, never a joined string."""

    def test_components_from_scored_frame_with_bonuses_and_context(self) -> None:
        from src import prediction_markets as md

        rows = [
            trade("0xf1", "CEO resigns by Friday?", "Yes", 30_000.0, "2026-06-10T12:00:00Z"),
            trade("0xf2", "CEO resigns by Friday?", "Yes", 30_000.0, "2026-06-10T12:03:00Z"),
            trade("0xf3", "CEO resigns by Friday?", "Yes", 30_000.0, "2026-06-10T12:05:00Z"),
        ]
        for row in rows:
            row["platform"] = "Polymarket"
            row["side"] = "BUY"
            row["price"] = 0.2
        base = tape(rows)
        events = md.whale_event_risk_scores(base, whale_threshold=2_500.0)
        events = susp.apply_fresh_wallet_bonus(events, susp.fresh_wallet_clusters(base, whale_threshold=2_500.0))
        events = susp.apply_coordination_bonus(events, susp.coordinated_clusters(base))
        events = susp.apply_category_context(events)
        parts = susp.event_components(events.iloc[0])
        keys = {p["key"]: p for p in parts}
        for key in ("component_notional", "component_largest", "component_concentration", "component_burst",
                    "component_fresh_wallets", "component_coordination", "context_multiplier"):
            self.assertIn(key, keys, key)
        self.assertGreater(keys["component_fresh_wallets"]["value"], 0.0)
        self.assertGreater(keys["component_coordination"]["value"], 0.0)
        self.assertEqual(keys["component_fresh_wallets"]["max"], 10.0)
        self.assertAlmostEqual(keys["context_multiplier"]["value"], susp.CONTEXT_MULTIPLIERS[susp.CONTEXT_CORPORATE])
        for part in parts:
            self.assertIsInstance(part["label"], str)
            self.assertIsInstance(part["value"], float)

    def test_components_of_an_older_row_without_columns_is_empty(self) -> None:
        row = pd.Series({"title": "x", "event_insider_score": 50.0})
        self.assertEqual(susp.event_components(row), [])
        self.assertEqual(susp.event_components({}), [])

    def test_nan_components_are_skipped(self) -> None:
        row = pd.Series({"component_notional": float("nan"), "component_burst": 3.25, "context_multiplier": 1.15})
        parts = susp.event_components(row)
        self.assertEqual([p["key"] for p in parts], ["component_burst", "context_multiplier"])
        self.assertEqual(parts[0]["value"], 3.2)


class KalshiTickerContextTests(unittest.TestCase):
    """Kalshi prints now carry the market's question as title; the KX… ticker
    patterns still apply because the ticker rides along as context."""

    def _tape(self) -> pd.DataFrame:
        return pd.DataFrame([
            {"platform": "Kalshi", "title": "Silver price up in next 15 mins? · Target Price: $65.758", "ticker": "KXSILVER15M-26AUG191430-30", "market_key": "KXSILVER15M-26AUG191430-30", "wallet": "", "notional": 500.0},
            {"platform": "Kalshi", "title": "Will the temp in Miami be above 94.99° on Aug 19, 2026?", "ticker": "KXHIGHMIA-26AUG19-T94.99", "market_key": "", "wallet": "", "notional": 500.0},
            {"platform": "Kalshi", "title": "Parlay · 2 legs: yes Detroit · yes Atlanta", "ticker": "KXMVECROSSCATEGORY-SHARD1-S2026-AB", "market_key": "KXMVECROSSCATEGORY-SHARD1-S2026-AB", "wallet": "", "notional": 500.0},
            {"platform": "Kalshi", "title": "Will Insidious have the highest Rotten Tomatoes score on Aug 24, 2026?", "ticker": "KXRTCOMPARE-INS26AUG24-INS", "market_key": "KXRTCOMPARE-INS26AUG24-INS", "wallet": "", "notional": 500.0},
            {"platform": "Polymarket", "title": "Will ACM Neto win the 2026 Bahia gubernatorial election?", "market_key": "0x" + "a" * 64, "wallet": "0x" + "b" * 40, "notional": 500.0},
        ])

    def test_filter_reads_the_ticker_when_the_title_is_the_question(self) -> None:
        kept = susp.filter_insider_prone_trades(self._tape())
        self.assertEqual(kept["title"].tolist(), [
            "Will Insidious have the highest Rotten Tomatoes score on Aug 24, 2026?",
            "Will ACM Neto win the 2026 Bahia gubernatorial election?",
        ])

    def test_event_context_reads_the_ticker(self) -> None:
        events = pd.DataFrame([
            {"title": "Silver price up in next 15 mins?", "ticker": "KXSILVER15M-26AUG191430-30", "event_insider_score": 60.0, "notional": 500.0},
            {"title": "Will the temp in Miami be above 94.99°?", "market_key": "KXHIGHMIA-26AUG19-T94.99", "event_insider_score": 60.0, "notional": 500.0},
        ])
        out = susp.apply_category_context(events)
        self.assertEqual(set(out["insider_context"]), {susp.CONTEXT_MARKET_PRICES, susp.CONTEXT_WEATHER})

    def test_polymarket_keys_are_not_context(self) -> None:
        # A conditionId is no ticker: nothing is appended, the title decides.
        self.assertEqual(susp._context_with_ticker("0x" + "a" * 64, {}), "")
        self.assertEqual(susp._context_with_ticker("KXFED-26SEP", {"KXFED-26SEP": "parent"}), "parent KXFED-26SEP")


class EventComponentFactsTests(unittest.TestCase):
    """Each score component carries what the tape showed and what full marks
    would take, in plain words, from the row's own columns."""

    def _row(self) -> dict:
        return {
            "component_notional": 0.2, "component_largest": 0.8, "component_long_odds": 0.0,
            "component_concentration": 14.5, "component_direction": 10.0, "component_burst": 15.0,
            "component_late": 0.0, "price_move_score": 2.4, "component_cluster": 10.0,
            "component_fresh_wallets": 0.0, "component_coordination": 4.0,
            "context_multiplier": 1.1, "insider_context": "Politics & geopolitics",
            "context_note": "decisions are known to officials before the public",
            "whale_base": 2500.0, "notional": 1020.0, "largest_trade": 400.0,
            "top_wallet": "0x07be0000000000000000000000000000005233", "top_wallet_share": 0.97,
            "event_directional_share": 0.97, "event_directional_label": "NO",
            "trades": 5, "trades_per_hour": 60.0, "price_move": 0.024, "unique_wallets": 4,
            "coordinated_wallets": 4, "coordinated_span_minutes": 0.2, "coordinated_outcome": "NO",
            "distribution_sample_weight": 1.0, "late_share": 0.0, "long_odds_notional": 0.0, "fresh_wallets": 0,
        }

    def test_facts_and_rules(self) -> None:
        parts = {c["key"]: c for c in susp.event_components(self._row())}
        self.assertEqual(parts["component_notional"]["label"], "Size of the flow")
        self.assertEqual(parts["component_notional"]["fact"], "$1k traded in the window")
        self.assertEqual(parts["component_notional"]["rule"], "full marks at $100k")
        self.assertEqual(parts["component_largest"]["rule"], "full marks at $12.5k")
        self.assertEqual(parts["component_concentration"]["fact"], "0x07be…5233 did 97% of the flow")
        self.assertEqual(parts["component_direction"]["fact"], "97% of the money net on NO")
        self.assertEqual(parts["component_burst"]["fact"], "5 prints at 60 an hour")
        self.assertEqual(parts["price_move_score"]["fact"], "price moved +2¢ the flow's way inside the window")
        self.assertEqual(parts["component_cluster"]["fact"], "4 wallets, 60 prints an hour")
        self.assertEqual(parts["component_coordination"]["fact"], "4 wallets on NO within 0 min")
        self.assertIn("halved because", parts["component_coordination"]["rule"])
        self.assertEqual(parts["component_long_odds"]["fact"], "no money placed at 20¢ or below")
        self.assertEqual(parts["component_long_odds"]["rule"], "")
        self.assertEqual(parts["context_multiplier"]["label"], "Context")
        self.assertEqual(parts["context_multiplier"]["fact"], "Politics & geopolitics — decisions are known to officials before the public")
        self.assertNotIn("weight", parts["component_concentration"])
        # Every component names what it measures.
        self.assertTrue(all(c["measures"] for c in parts.values()))

    def test_sample_weight_is_named(self) -> None:
        row = self._row()
        row["distribution_sample_weight"] = 0.5
        row["trades"] = 3
        parts = {c["key"]: c for c in susp.event_components(row)}
        self.assertEqual(parts["component_concentration"]["weight"], 0.5)
        self.assertEqual(parts["component_concentration"]["weight_note"], "damped ×0.50: only 3 prints in the sample")
        self.assertNotIn("weight", parts["component_notional"])

    def test_size_weight_is_named_too(self) -> None:
        row = self._row()
        row["distribution_size_weight"] = 0.2
        row["distribution_size_floor"] = 500.0
        row["notional"] = 100.0
        parts = {c["key"]: c for c in susp.event_components(row)}
        self.assertEqual(parts["component_concentration"]["weight"], 0.2)
        self.assertEqual(parts["component_concentration"]["weight_note"], "damped ×0.20: only $100 of flow, full weight from $500")
        # "Several wallets at once" is size-weighted, not sample-weighted.
        self.assertEqual(parts["component_cluster"]["weight"], 0.2)
        self.assertNotIn("weight", parts["component_notional"])
        # Both dampings at once: the note names both, the weight is the product.
        row["distribution_sample_weight"] = 0.5
        row["trades"] = 3
        parts = {c["key"]: c for c in susp.event_components(row)}
        self.assertEqual(parts["component_concentration"]["weight"], 0.1)
        self.assertEqual(parts["component_concentration"]["weight_note"], "damped ×0.10: only 3 prints in the sample; only $100 of flow, full weight from $500")

    def test_missing_columns_yield_nothing_invented(self) -> None:
        self.assertEqual(susp.event_components({}), [])
        parts = susp.event_components({"component_burst": 3.0})
        self.assertEqual(len(parts), 1)
        self.assertEqual(parts[0]["fact"], "0 prints at 0 an hour")
