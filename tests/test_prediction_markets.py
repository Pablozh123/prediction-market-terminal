import unittest
from unittest.mock import patch

import pandas as pd

from src import prediction_markets as md


class LocalRouteTargetTests(unittest.TestCase):
    def test_trader_profile_route_maps_to_wallet_workspace(self) -> None:
        target = md.local_route_target("https://predictparity.local/traders/p/@swisstony")

        self.assertEqual(target, {"page_slug": "wallets", "profile": "swisstony", "market": ""})

    def test_wallet_route_keeps_wallet_target(self) -> None:
        target = md.local_route_target("/wallets/0x204f72f35326db932158cba6adff0b9a1da95e14")

        self.assertEqual(
            target,
            {
                "page_slug": "wallets",
                "profile": "0x204f72f35326db932158cba6adff0b9a1da95e14",
                "market": "",
            },
        )

    def test_plain_workspace_route_returns_slug_only(self) -> None:
        self.assertEqual(md.local_route_target("/live-trades"), {"page_slug": "live-trades", "profile": "", "market": ""})

    def test_market_route_captures_market_slug(self) -> None:
        self.assertEqual(
            md.local_route_target("/markets/will-bitcoin-hit-100k"),
            {"page_slug": "markets", "profile": "", "market": "will-bitcoin-hit-100k"},
        )


class PredictParityQueryFilterTests(unittest.TestCase):
    def test_search_filter_view_parses_global_search_params(self) -> None:
        view = md.predictparity_search_filter_view(
            {
                "q": "bitcoin",
                "platform": "polymarket",
                "type": "markets,traders,cross-venue",
                "minValue": "10000",
                "tracked": "true",
                "active": "false",
                "broadPairs": "false",
                "limit": "40",
            }
        )

        self.assertEqual(view["query"], "bitcoin")
        self.assertEqual(view["platforms"], ["Polymarket"])
        self.assertEqual(view["result_types"], ["Markets", "Traders", "Cross-Venue"])
        self.assertEqual(view["min_value"], 10000.0)
        self.assertTrue(view["tracked_only"])
        self.assertFalse(view["active_markets_only"])
        self.assertFalse(view["broad_pairs"])
        self.assertEqual(view["rows"], 40)

    def test_market_filter_view_parses_search_platform_status_and_ranges(self) -> None:
        view = md.predictparity_market_filter_view(
            {
                "q": "bitcoin",
                "platform": "polymarket,kalshi",
                "status": "active",
                "category": "Crypto,Politics",
                "probMin": "0.05",
                "probMax": "0.95",
                "volumeMin": "10000",
                "liquidityMin": "5000",
                "spreadMax": "0.07",
                "sort": "volume_24h",
                "limit": "50",
            }
        )

        self.assertEqual(view["query"], "bitcoin")
        self.assertEqual(view["platform_filter"], ["Polymarket", "Kalshi"])
        self.assertEqual(view["status_filter"], "Active")
        self.assertEqual(view["include_categories"], ["Crypto", "Politics"])
        self.assertEqual(view["prob_preset"], "Custom")
        self.assertEqual(view["custom_prob"], [5, 95])
        self.assertEqual(view["volume_preset"], "Custom")
        self.assertEqual(view["custom_volume"], 10000.0)
        self.assertEqual(view["liquidity_preset"], "Custom")
        self.assertEqual(view["custom_liquidity"], 5000.0)
        self.assertEqual(view["spread_preset"], "Custom")
        self.assertEqual(view["custom_spread"], 7.0)
        self.assertEqual(view["sort_by"], "volume_24h")
        self.assertEqual(view["limit_rows"], 50)

    def test_market_filter_view_parses_view_quick_and_calendar_params(self) -> None:
        view = md.predictparity_market_filter_view(
            {"view": "calendar", "quick": "ending-soon", "endDays": "7", "ageDays": "30"}
        )

        self.assertEqual(view["view"], "Calendar")
        self.assertEqual(view["quick"], "Ending Soon")
        self.assertEqual(view["end_preset"], "Custom")
        self.assertEqual(view["custom_days"], 7)
        self.assertEqual(view["age_preset"], "Custom")
        self.assertEqual(view["custom_age_days"], 30)

    def test_overview_filter_view_parses_dashboard_params(self) -> None:
        view = md.predictparity_overview_filter_view(
            {
                "q": "bitcoin",
                "platform": "polymarket",
                "featured": "any",
                "marketRows": "9",
                "category": "Politics,Crypto",
                "excludeCategory": "Sports",
                "minVolume": "10000",
                "minLiquidity": "5000",
                "minFlow": "2500",
                "active": "false",
                "showNews": "false",
            }
        )

        self.assertEqual(view["query"], "bitcoin")
        self.assertEqual(view["platforms"], ["Polymarket"])
        self.assertEqual(view["featured_source"], "Any")
        self.assertEqual(view["market_rows"], 9)
        self.assertEqual(view["include_categories"], ["Politics", "Crypto"])
        self.assertEqual(view["exclude_categories"], ["Sports"])
        self.assertEqual(view["min_volume"], 10000.0)
        self.assertEqual(view["min_liquidity"], 5000.0)
        self.assertEqual(view["min_flow_notional"], 2500.0)
        self.assertFalse(view["active_only"])
        self.assertFalse(view["show_news"])

    def test_trader_filter_view_parses_bot_and_active_position_params(self) -> None:
        view = md.predictparity_trader_filter_view({"bot": "true", "apMin": "101"})

        self.assertTrue(view["bots_only"])
        self.assertEqual(view["trait_filter"], ["Bot-like"])
        self.assertEqual(view["bot_score_min"], 65)
        self.assertTrue(view["active_only"])
        self.assertTrue(view["enrich_positions"])
        self.assertEqual(view["active_positions_min"], 101)

    def test_trader_filter_view_parses_search_sort_and_metric_params(self) -> None:
        view = md.predictparity_trader_filter_view(
            {
                "q": "swisstony",
                "period": "month",
                "orderBy": "vol",
                "pnlMin": "500000",
                "volMin": "1000000",
                "limit": "50",
            }
        )

        self.assertEqual(view["query"], "swisstony")
        self.assertEqual(view["period"], "MONTH")
        self.assertEqual(view["rank_by"], "VOL")
        self.assertEqual(view["pnl_preset"], "Custom")
        self.assertEqual(view["custom_pnl"], 500000.0)
        self.assertEqual(view["volume_preset"], "Custom")
        self.assertEqual(view["custom_volume"], 1000000.0)
        self.assertEqual(view["rows"], 50)

    def test_trader_filter_view_ignores_invalid_values(self) -> None:
        view = md.predictparity_trader_filter_view({"bot": "false", "apMin": "bad", "period": "year"})

        self.assertEqual(view, {})

    def test_live_trade_filter_view_parses_tape_params(self) -> None:
        view = md.predictparity_live_trade_filter_view(
            {
                "q": "swisstony",
                "platform": "polymarket",
                "side": "buy,no",
                "minNotional": "2500",
                "whale": "true",
                "trackedWallets": "yes",
                "limit": "150",
            }
        )

        self.assertEqual(view["query"], "swisstony")
        self.assertEqual(view["platforms"], ["Polymarket"])
        self.assertEqual(view["sides"], ["BUY", "no"])
        self.assertEqual(view["min_notional"], 2500.0)
        self.assertTrue(view["large_only"])
        self.assertTrue(view["tracked_wallets_only"])
        self.assertEqual(view["rows"], 150)

    def test_track_filter_view_parses_tracking_hub_params(self) -> None:
        view = md.predictparity_track_filter_view(
            {
                "q": "tony",
                "platform": "polymarket,kalshi",
                "minWatchVolume": "10000",
                "signal": "tight-spread",
                "minWalletValue": "2500",
                "limit": "120",
            }
        )

        self.assertEqual(view["query"], "tony")
        self.assertEqual(view["platforms"], ["Polymarket", "Kalshi"])
        self.assertEqual(view["min_watch_volume"], 10000.0)
        self.assertEqual(view["signal_filter"], "Tight spread")
        self.assertEqual(view["min_wallet_value"], 2500.0)
        self.assertEqual(view["rows"], 120)

    def test_whale_filter_view_parses_flow_thresholds(self) -> None:
        view = md.predictparity_whale_filter_view(
            {
                "q": "iran",
                "platform": "polymarket",
                "side": "buy,yes",
                "minPrint": "5000",
                "minWalletNotional": "25000",
                "minWalletTrades": "3",
                "bias": "yes",
                "trackedWallets": "true",
                "rows": "200",
            }
        )

        self.assertEqual(view["query"], "iran")
        self.assertEqual(view["platforms"], ["Polymarket"])
        self.assertEqual(view["sides"], ["BUY", "yes"])
        self.assertEqual(view["min_notional"], 5000.0)
        self.assertEqual(view["min_wallet_notional"], 25000.0)
        self.assertEqual(view["min_wallet_trades"], 3)
        self.assertEqual(view["bias_filter"], "YES")
        self.assertTrue(view["tracked_wallets_only"])
        self.assertEqual(view["rows"], 200)

    def test_cross_venue_filter_view_parses_gap_and_price_params(self) -> None:
        view = md.predictparity_cross_venue_filter_view(
            {
                "q": "bitcoin",
                "minSimilarity": "0.35",
                "maxPairs": "120",
                "minGap": "0.08",
                "pmVolumeMin": "10000",
                "ksVolumeMin": "5000",
                "lower": "kalshi",
                "priceMin": "0.05",
                "priceMax": "0.95",
            }
        )

        self.assertEqual(view["query"], "bitcoin")
        self.assertEqual(view["min_similarity"], 0.35)
        self.assertEqual(view["max_pairs"], 120)
        self.assertEqual(view["min_gap_cents"], 8.0)
        self.assertEqual(view["min_pm_volume"], 10000.0)
        self.assertEqual(view["min_ks_volume"], 5000.0)
        self.assertEqual(view["lower_filter"], "Kalshi")
        self.assertEqual(view["min_price_pct"], 5)
        self.assertEqual(view["max_price_pct"], 95)

    def test_monitor_filter_view_parses_signal_thresholds_and_scope(self) -> None:
        view = md.predictparity_monitor_filter_view(
            {
                "q": "bitcoin",
                "platform": "polymarket",
                "signal": "whale-print,tight-spread",
                "watched": "true",
                "minVolume": "10000",
                "minLiquidity": "5000",
                "minMove": "0.03",
                "maxSpread": "0.07",
                "minWhale": "2500",
                "endingDays": "5",
                "holderChecks": "3",
                "holderThreshold": "25",
                "limit": "75",
            }
        )

        self.assertEqual(view["query"], "bitcoin")
        self.assertEqual(view["platforms"], ["Polymarket"])
        self.assertEqual(view["signal_types"], ["Whale print", "Tight spread"])
        self.assertTrue(view["watched_only"])
        self.assertEqual(view["min_volume"], 10000.0)
        self.assertEqual(view["min_liquidity"], 5000.0)
        self.assertEqual(view["min_move"], 3.0)
        self.assertEqual(view["max_spread"], 7.0)
        self.assertEqual(view["min_whale"], 2500.0)
        self.assertEqual(view["ending_days"], 5)
        self.assertEqual(view["holder_checks"], 3)
        self.assertEqual(view["holder_threshold"], 0.25)
        self.assertEqual(view["rows"], 75)

    def test_alert_filter_view_parses_hits_only_and_monitor_thresholds(self) -> None:
        view = md.predictparity_alert_filter_view(
            {
                "q": "iran",
                "signal": "fast-mover",
                "hitsOnly": "true",
                "minWhale": "5000",
                "maxSpread": "7",
            }
        )

        self.assertEqual(view["query"], "iran")
        self.assertEqual(view["signal_types"], ["Fast mover"])
        self.assertTrue(view["hits_only"])
        self.assertEqual(view["min_whale"], 5000.0)
        self.assertEqual(view["max_spread"], 7.0)

    def test_resolved_filter_view_parses_accuracy_archive_params(self) -> None:
        view = md.predictparity_resolved_filter_view(
            {
                "q": "iran",
                "outcome": "yes,no",
                "decisiveOnly": "true",
                "minVolume": "10000",
                "minLiquidity": "5000",
                "category": "Politics,Crypto",
                "closedWindow": "30d",
                "finalYesMin": "0.95",
                "sort": "final-yes",
                "limit": "300",
            }
        )

        self.assertEqual(view["query"], "iran")
        self.assertEqual(view["outcomes"], ["Yes", "No"])
        self.assertTrue(view["decisive_only"])
        self.assertEqual(view["min_volume"], 10000.0)
        self.assertEqual(view["min_liquidity"], 5000.0)
        self.assertEqual(view["category_filter"], ["Politics", "Crypto"])
        self.assertEqual(view["closed_window"], "<30d")
        self.assertEqual(view["final_yes_range"], [95, 100])
        self.assertEqual(view["sort_by"], "final_yes_price")
        self.assertEqual(view["rows"], 300)

    def test_portfolio_filter_view_parses_dashboard_params(self) -> None:
        view = md.predictparity_portfolio_filter_view(
            {
                "q": "tony",
                "platform": "polymarket",
                "outcome": "yes",
                "minValue": "100",
                "minPnl": "-50",
                "source": "research,copy,history",
                "copyStatus": "copied,settled",
                "losersOnly": "true",
                "limit": "75",
            }
        )

        self.assertEqual(view["query"], "tony")
        self.assertEqual(view["platforms"], ["Polymarket"])
        self.assertEqual(view["outcomes"], ["Yes"])
        self.assertEqual(view["min_value"], 100.0)
        self.assertEqual(view["min_pnl"], -50.0)
        self.assertEqual(view["sources"], ["Research", "Copy", "History"])
        self.assertEqual(view["copy_statuses"], ["copied", "settled"])
        self.assertTrue(view["losers_only"])
        self.assertEqual(view["rows"], 75)


class CrossVenueCandidateTests(unittest.TestCase):
    def test_candidates_include_trackable_market_ids(self) -> None:
        polymarket = pd.DataFrame(
            [
                {
                    "title": "Will Bitcoin hit 100k in 2026?",
                    "yes_price": 0.42,
                    "activity_volume": 15000,
                    "market_key": "poly-condition",
                    "ticker": "poly-ticker",
                    "url": "https://polymarket.com/event/bitcoin",
                }
            ]
        )
        kalshi = pd.DataFrame(
            [
                {
                    "title": "Bitcoin above 100k in 2026?",
                    "yes_price": 0.47,
                    "activity_volume": 9000,
                    "market_key": "kalshi-market",
                    "ticker": "kalshi-ticker",
                    "url": "https://kalshi.com/markets/bitcoin",
                }
            ]
        )

        candidates = md.cross_venue_candidates(polymarket, kalshi, min_similarity=0.10)

        self.assertEqual(len(candidates), 1)
        row = candidates.iloc[0]
        self.assertEqual(row["polymarket_market_key"], "poly-condition")
        self.assertEqual(row["kalshi_market_key"], "kalshi-market")
        self.assertEqual(row["polymarket_ticker"], "poly-ticker")
        self.assertEqual(row["kalshi_ticker"], "kalshi-ticker")
        self.assertAlmostEqual(row["gap"], -0.05)


class OrderbookTests(unittest.TestCase):
    def test_orderbook_ladder_cumulates_bid_and_ask_totals(self) -> None:
        bids = pd.DataFrame(
            [
                {"price": 0.40, "size": 10.0, "notional": 4.0},
                {"price": 0.39, "size": 5.0, "notional": 1.95},
            ]
        )
        asks = pd.DataFrame(
            [
                {"price": 0.42, "size": 3.0, "notional": 1.26},
                {"price": 0.43, "size": 7.0, "notional": 3.01},
            ]
        )

        ladder = md.orderbook_ladder(bids, asks)

        self.assertEqual(ladder["side"].tolist(), ["Bid", "Bid", "Ask", "Ask"])
        self.assertAlmostEqual(float(ladder.iloc[1]["total_shares"]), 15.0)
        self.assertAlmostEqual(float(ladder.iloc[1]["total"]), 5.95)
        self.assertAlmostEqual(float(ladder.iloc[3]["total_shares"]), 10.0)
        self.assertAlmostEqual(float(ladder.iloc[3]["total"]), 4.27)

    def test_orderbook_summary_computes_spread_mid_and_depth(self) -> None:
        bids = pd.DataFrame([{"price": 0.39, "notional": 10.0}, {"price": 0.40, "notional": 5.0}])
        asks = pd.DataFrame([{"price": 0.43, "notional": 7.0}, {"price": 0.42, "notional": 8.0}])

        summary = md.orderbook_summary(bids, asks)

        self.assertAlmostEqual(summary["best_bid"], 0.40)
        self.assertAlmostEqual(summary["best_ask"], 0.42)
        self.assertAlmostEqual(summary["spread"], 0.02)
        self.assertAlmostEqual(summary["midpoint"], 0.41)
        self.assertAlmostEqual(summary["bid_depth"], 15.0)
        self.assertAlmostEqual(summary["ask_depth"], 15.0)


class RecentTradeActionTests(unittest.TestCase):
    def test_prepare_recent_trade_actions_adds_timestamps_and_links(self) -> None:
        wallet = "0x" + "a" * 40
        trades = pd.DataFrame(
            [
                {
                    "time": "2026-05-29T11:30:00Z",
                    "trader": "SharpTrader",
                    "wallet": wallet,
                    "side": "Buy",
                    "outcome": "Yes",
                    "title": "Example market",
                    "price": 0.25,
                    "size": 100,
                    "notional": 25,
                    "transaction_hash": "0xabc",
                    "url": "https://polymarket.com/event/example",
                }
            ]
        )

        prepared = md.prepare_recent_trade_actions(trades, now="2026-05-29T12:00:00Z")

        row = prepared.iloc[0]
        self.assertEqual(row["time_utc"], "2026-05-29 11:30:00")
        self.assertAlmostEqual(float(row["age_min"]), 30.0)
        self.assertTrue(bool(row["valid_wallet"]))
        self.assertEqual(row["wallet_url"], f"https://polymarket.com/profile/{wallet}")
        self.assertEqual(row["tx_url"], "https://polygonscan.com/tx/0xabc")
        self.assertEqual(row["direction"], "Yes")
        self.assertAlmostEqual(float(row["directional_share"]), 1.0)
        self.assertEqual(row["wallet_market_trades"], 1)
        self.assertAlmostEqual(float(row["wallet_market_notional"]), 25.0)
        self.assertIn("100% SharpTrader | Buy Yes | $25.00", row["action_label"])

    def test_prepare_recent_trade_actions_handles_missing_wallet_and_bad_tx(self) -> None:
        trades = pd.DataFrame([{"time": "bad", "wallet": "not-wallet", "side": "Sell", "outcome": "No", "notional": 1000}])

        prepared = md.prepare_recent_trade_actions(trades, now="2026-05-29T12:00:00Z")

        row = prepared.iloc[0]
        self.assertEqual(row["time_utc"], "-")
        self.assertFalse(bool(row["valid_wallet"]))
        self.assertEqual(row["wallet_url"], "")
        self.assertEqual(row["tx_url"], "")
        self.assertIn("Sell No | $1,000", row["action_label"])

    def test_prepare_recent_trade_actions_scores_wallet_directional_flow(self) -> None:
        wallet = "0x" + "b" * 40
        trades = pd.DataFrame(
            [
                {"time": "2026-05-29T11:00:00Z", "trader": "BiasTrader", "wallet": wallet, "side": "BUY", "outcome": "No", "notional": 60},
                {"time": "2026-05-29T11:01:00Z", "trader": "BiasTrader", "wallet": wallet, "side": "SELL", "outcome": "Yes", "notional": 30},
                {"time": "2026-05-29T11:02:00Z", "trader": "BiasTrader", "wallet": wallet, "side": "BUY", "outcome": "Yes", "notional": 10},
            ]
        )

        prepared = md.prepare_recent_trade_actions(trades, now="2026-05-29T12:00:00Z")

        first = prepared.iloc[0]
        last = prepared.iloc[2]
        self.assertEqual(first["direction"], "No")
        self.assertAlmostEqual(float(first["directional_share"]), 0.9)
        self.assertEqual(first["wallet_market_trades"], 3)
        self.assertAlmostEqual(float(first["wallet_market_notional"]), 100.0)
        self.assertIn("90% BiasTrader", first["trader_badge"])
        self.assertEqual(last["direction"], "Yes")
        self.assertAlmostEqual(float(last["directional_share"]), 0.1)


class TraderTraitFilterTests(unittest.TestCase):
    def test_bots_only_uses_configurable_bot_score_threshold(self) -> None:
        leaderboard = pd.DataFrame(
            [
                {"wallet": "0xbot", "trader": "bot", "bot_score": 82, "whale_score": 10, "volume": 1000, "verified": False},
                {"wallet": "0xactive", "trader": "active", "bot_score": 64, "whale_score": 90, "volume": 2_000_000, "verified": False},
            ]
        )

        filtered = md.apply_trader_trait_filters(leaderboard, bots_only=True, bot_score_min=80)

        self.assertEqual(filtered["wallet"].tolist(), ["0xbot"])

    def test_bots_only_has_leaderboard_fallback_when_recent_flow_score_is_missing(self) -> None:
        leaderboard = pd.DataFrame(
            [
                {"wallet": "0xturnover", "trader": "turnover", "bot_score": 0, "pnl": 900_000, "volume": 300_000_000, "verified": False},
                {"wallet": "0xconviction", "trader": "conviction", "bot_score": 0, "pnl": 10_000_000, "volume": 10_000_000, "verified": True},
            ]
        )

        filtered = md.apply_trader_trait_filters(leaderboard, bots_only=True, bot_score_min=65)

        self.assertEqual(filtered["wallet"].tolist(), ["0xturnover"])
        self.assertGreaterEqual(float(filtered.iloc[0]["bot_score"]), 65)

    def test_trait_filters_can_stack_whale_bot_and_verified(self) -> None:
        leaderboard = pd.DataFrame(
            [
                {"wallet": "0xmatch", "trader": "match", "bot_score": 90, "whale_score": 80, "volume": 500, "verified": True},
                {"wallet": "0xnotverified", "trader": "bot whale", "bot_score": 90, "whale_score": 80, "volume": 500, "verified": False},
                {"wallet": "0xnotbot", "trader": "verified whale", "bot_score": 20, "whale_score": 80, "volume": 500, "verified": True},
            ]
        )

        filtered = md.apply_trader_trait_filters(leaderboard, trait_filter=["Whales", "Bot-like", "Verified"])

        self.assertEqual(filtered["wallet"].tolist(), ["0xmatch"])


class FeaturedCarouselTests(unittest.TestCase):
    def test_cycle_featured_index_wraps_forward_and_backward(self) -> None:
        self.assertEqual(md.cycle_featured_index(0, 3, 1), 1)
        self.assertEqual(md.cycle_featured_index(2, 3, 1), 0)
        self.assertEqual(md.cycle_featured_index(0, 3, -1), 2)

    def test_cycle_featured_index_handles_bad_state(self) -> None:
        self.assertEqual(md.cycle_featured_index("bad", 3, 0), 0)
        self.assertEqual(md.cycle_featured_index(5, 0, 1), 0)


class MarketFilterMetricTests(unittest.TestCase):
    def test_market_filter_metrics_add_age_volume_and_price_deltas(self) -> None:
        markets = pd.DataFrame(
            [
                {
                    "created_at": "2026-05-26T00:00:00Z",
                    "volume_1h": 200.0,
                    "volume_24h": 2400.0,
                    "volume_1w": 7000.0,
                    "change_1h": 0.02,
                    "change_1d": -0.05,
                }
            ]
        )

        enriched = md.add_market_filter_metrics(markets, now=pd.Timestamp("2026-05-28T00:00:00Z"))

        row = enriched.iloc[0]
        self.assertAlmostEqual(row["market_age_days"], 2.0)
        self.assertAlmostEqual(row["volume_delta_1h"], 1.0)
        self.assertAlmostEqual(row["volume_delta_24h"], 1.4)
        self.assertAlmostEqual(row["price_delta_1h"], 0.02)
        self.assertAlmostEqual(row["price_delta_24h"], -0.05)

    def test_resolution_yield_summary_uses_higher_probability_side(self) -> None:
        summary = md.resolution_yield_summary(
            0.12,
            "2026-06-01T00:00:00Z",
            now=pd.Timestamp("2026-05-30T00:00:00Z"),
        )

        self.assertEqual(summary["side"], "No")
        self.assertAlmostEqual(float(summary["price"]), 0.88)
        self.assertAlmostEqual(float(summary["days_to_end"]), 2.0)
        self.assertAlmostEqual(float(summary["apy"]), ((1 / 0.88) - 1) * (365 / 2))

    def test_market_detail_header_metrics_include_predictparity_fields(self) -> None:
        metrics = md.market_detail_header_metrics(
            {
                "platform": "Polymarket",
                "yes_price": 0.153,
                "volume_1h": 4700,
                "volume_24h": 1_600_000,
                "liquidity": 484_600,
                "end_time": "2026-05-31T00:00:00Z",
            },
            now=pd.Timestamp("2026-05-29T00:00:00Z"),
        )

        self.assertEqual(metrics["venue"], "Polymarket")
        self.assertAlmostEqual(metrics["yes_price"], 0.153)
        self.assertAlmostEqual(metrics["no_price"], 0.847)
        self.assertAlmostEqual(metrics["volume_1h"], 4700.0)
        self.assertAlmostEqual(metrics["volume_24h"], 1_600_000.0)
        self.assertAlmostEqual(metrics["liquidity_or_oi"], 484_600.0)
        self.assertEqual(metrics["end_label"], "in 2 days")
        self.assertEqual(metrics["apy_label"], "No APY")
        self.assertIsNotNone(metrics["apy"])

    def test_market_detail_header_metrics_handles_duplicate_columns(self) -> None:
        row = pd.Series(
            ["Polymarket", 0.4, 0.6, 0.61, 100.0],
            index=["platform", "yes_price", "no_price", "no_price", "volume_1h"],
        )

        metrics = md.market_detail_header_metrics(row, now=pd.Timestamp("2026-05-29T00:00:00Z"))

        self.assertEqual(metrics["venue"], "Polymarket")
        self.assertAlmostEqual(metrics["yes_price"], 0.4)
        self.assertAlmostEqual(metrics["no_price"], 0.6)
        self.assertAlmostEqual(metrics["volume_1h"], 100.0)

    def test_relative_time_label_matches_market_scanner_style(self) -> None:
        now = pd.Timestamp("2026-05-30T12:00:00Z")

        self.assertEqual(md.relative_time_label("2026-05-30T13:00:00Z", now=now), "in 1 hour")
        self.assertEqual(md.relative_time_label("2026-06-01T12:00:00Z", now=now), "in 2 days")
        self.assertEqual(md.relative_time_label("2026-05-29T12:00:00Z", now=now), "1 day ago")
        self.assertEqual(md.relative_time_label(None, now=now), "-")

    def test_compact_elapsed_label_matches_profile_sync_style(self) -> None:
        now = pd.Timestamp("2026-05-29T12:00:00Z")

        self.assertEqual(md.compact_elapsed_label("2026-05-29T11:57:00Z", now=now), "3m")
        self.assertEqual(md.compact_elapsed_label("2026-05-29T10:00:00Z", now=now), "2h")
        self.assertEqual(md.compact_elapsed_label("2026-05-27T12:00:00Z", now=now), "2d")
        self.assertEqual(md.compact_elapsed_label("2026-05-29T12:00:00Z", now=now), "now")

    def test_pnl_window_label_matches_profile_chart_copy(self) -> None:
        self.assertEqual(md.pnl_window_label("1d"), "Past day")
        self.assertEqual(md.pnl_window_label("1w"), "Past week")
        self.assertEqual(md.pnl_window_label("1mo"), "Past month")
        self.assertEqual(md.pnl_window_label("All"), "All time")
        self.assertEqual(md.pnl_window_label("bad"), "Past week")

    def test_market_calendar_days_builds_month_grid_with_top_markets(self) -> None:
        markets = pd.DataFrame(
            [
                {"market_key": "low", "title": "Low volume", "platform": "Polymarket", "yes_price": 0.4, "activity_volume": 10, "end_time": "2026-05-29T12:00:00Z"},
                {"market_key": "high", "title": "High volume", "platform": "Polymarket", "yes_price": 0.6, "activity_volume": 100, "end_time": "2026-05-29T18:00:00Z"},
                {"market_key": "next", "title": "Next day", "platform": "Kalshi", "yes_price": 0.7, "activity_volume": 50, "end_time": "2026-05-30T18:00:00Z"},
            ]
        )

        calendar = md.market_calendar_days(markets, month="2026-05-01", top_per_day=1)

        self.assertEqual(len(calendar), 35)
        self.assertEqual(calendar.iloc[0]["date"], "2026-04-27")
        may_29 = calendar[calendar["date"].eq("2026-05-29")].iloc[0]
        self.assertEqual(int(may_29["markets"]), 2)
        self.assertAlmostEqual(float(may_29["volume"]), 110.0)
        self.assertEqual(may_29["top_markets"][0]["market_key"], "high")
        self.assertEqual(int(may_29["more_count"]), 1)

    def test_related_markets_groups_by_event_slug(self) -> None:
        markets = pd.DataFrame(
            [
                {"market_key": "a", "event_slug": "world-cup", "title": "Team A wins", "yes_price": 0.4, "activity_volume": 10, "closed": False},
                {"market_key": "b", "event_slug": "world-cup", "title": "Team B wins", "yes_price": 0.6, "activity_volume": 20, "closed": False},
                {"market_key": "c", "event_slug": "other", "title": "Other market", "yes_price": 0.2, "activity_volume": 30, "closed": False},
            ]
        )

        related = md.related_markets(markets, markets.iloc[0])

        self.assertEqual(set(related["market_key"]), {"a", "b"})


class ProfileSearchTests(unittest.TestCase):
    def test_x_profile_url_normalizes_handles_and_urls(self) -> None:
        self.assertEqual(md.x_profile_url("SwissTonyPM"), "https://x.com/SwissTonyPM")
        self.assertEqual(md.x_profile_url("@SwissTonyPM"), "https://x.com/SwissTonyPM")
        self.assertEqual(md.x_profile_url("https://twitter.com/SwissTonyPM"), "https://x.com/SwissTonyPM")
        self.assertEqual(md.x_profile_url("https://x.com/SwissTonyPM/status/1"), "https://x.com/SwissTonyPM")
        self.assertEqual(md.x_profile_url("bad handle"), "")

    def test_predictparity_trader_url_normalizes_handles_and_urls(self) -> None:
        self.assertEqual(md.predictparity_trader_url("swisstony"), "https://predictparity.com/traders/p/@swisstony")
        self.assertEqual(md.predictparity_trader_url("@swisstony"), "https://predictparity.com/traders/p/@swisstony")
        self.assertEqual(md.predictparity_trader_url("https://predictparity.com/traders/p/@swisstony"), "https://predictparity.com/traders/p/@swisstony")
        self.assertEqual(md.predictparity_trader_url("bad handle"), "")
        self.assertEqual(md.predictparity_trader_url("0x" + "a" * 40), "")

    def test_resolve_profile_query_to_wallet_accepts_handles_urls_and_wallets(self) -> None:
        wallet = "0x" + "a" * 40
        profiles = pd.DataFrame([{"wallet": wallet, "trader": "swisstony", "x_username": "SwissTonyPM"}])

        self.assertEqual(md.resolve_profile_query_to_wallet(wallet, profiles), wallet)
        self.assertEqual(md.resolve_profile_query_to_wallet("@swisstony", profiles), wallet)
        self.assertEqual(md.resolve_profile_query_to_wallet("https://predictparity.com/traders/p/@swisstony", profiles), wallet)
        self.assertEqual(md.resolve_profile_query_to_wallet("https://polymarket.com/profile/swisstony", profiles), wallet)
        self.assertEqual(md.resolve_profile_query_to_wallet("@missing", profiles), "")

    def test_merge_profile_position_values_fills_open_position_metrics(self) -> None:
        profiles = pd.DataFrame(
            [
                {"wallet": "0xABC", "trader": "alice", "pnl": 10.0, "volume": 100.0},
                {"wallet": "0xDEF", "trader": "bob", "pnl": 5.0, "volume": 50.0},
            ]
        )
        position_values = pd.DataFrame(
            [
                {"wallet": "0xabc", "positions_value": 42.0, "open_positions": 3, "open_markets": 2},
            ]
        )

        enriched = md.merge_profile_position_values(profiles, position_values)

        alice = enriched[enriched["trader"].eq("alice")].iloc[0]
        bob = enriched[enriched["trader"].eq("bob")].iloc[0]
        self.assertAlmostEqual(float(alice["positions_value"]), 42.0)
        self.assertEqual(int(alice["open_positions"]), 3)
        self.assertEqual(int(alice["open_markets"]), 2)
        self.assertAlmostEqual(float(bob["positions_value"]), 0.0)
        self.assertEqual(int(bob["open_positions"]), 0)

    def test_merge_profile_position_values_adds_defaults_without_fetch_data(self) -> None:
        profiles = pd.DataFrame([{"wallet": "0xABC", "trader": "alice", "pnl": 10.0, "volume": 100.0}])

        enriched = md.merge_profile_position_values(profiles, pd.DataFrame())

        self.assertIn("positions_value", enriched.columns)
        self.assertIn("open_positions", enriched.columns)
        self.assertIn("open_markets", enriched.columns)
        self.assertAlmostEqual(float(enriched.iloc[0]["positions_value"]), 0.0)
        self.assertEqual(int(enriched.iloc[0]["open_positions"]), 0)

    def test_wallet_profile_tab_labels_include_compact_counts(self) -> None:
        labels = md.wallet_profile_tab_labels(
            pd.DataFrame([{} for _ in range(101)]),
            pd.DataFrame([{} for _ in range(4)]),
            pd.DataFrame([{} for _ in range(12)]),
            pd.DataFrame([{} for _ in range(250)]),
        )

        self.assertEqual(labels[0], "POSITIONS (100+)")
        self.assertEqual(labels[1], "Insights")
        self.assertEqual(labels[2], "Active positions (100+)")
        self.assertEqual(labels[3], "Closed positions (4)")
        self.assertEqual(labels[4], "Trades (12)")
        self.assertEqual(labels[5], "ACTIVITY (100+)")

    def test_filter_wallet_positions_by_parity_status(self) -> None:
        positions = pd.DataFrame(
            [
                {"title": "Open one", "status": "Open", "value": 5.0},
                {"title": "Closed one", "status": "Closed", "value": 2.0},
            ]
        )

        active = md.filter_wallet_positions_by_status(positions, "Active")
        closed = md.filter_wallet_positions_by_status(positions, "Closed")
        all_rows = md.filter_wallet_positions_by_status(positions, "All")

        self.assertEqual(active["title"].tolist(), ["Open one"])
        self.assertEqual(closed["title"].tolist(), ["Closed one"])
        self.assertEqual(all_rows["title"].tolist(), ["Open one", "Closed one"])
        self.assertEqual(md.wallet_position_status_value("Open"), "Open")

    def test_predictparity_trader_profile_parses_public_graphql_fields(self) -> None:
        responses = [
            {"data": {"resolveTrader": {"id": "trader-1", "platform": "polymarket"}}},
            {
                "data": {
                    "trader": {
                        "id": "trader-1",
                        "platform": "polymarket",
                        "platformId": "0xabc",
                        "username": "handle",
                        "displayName": "Display",
                        "platformAccountCreatedAt": "2025-07-29T14:46:06Z",
                        "lastSyncedAt": "2026-05-29T15:48:00Z",
                        "analytics": {"allTimeVolume": 1000.5, "allTimePnl": 42.25, "rank": 7},
                        "onchain": {
                            "usdcBalance": 12.5,
                            "firstTransactionDate": "2025-08-07T11:13:51Z",
                            "firstFundingAmount": 4999,
                            "firstFundingSource": "0xfunder",
                            "firstFundingTxHash": "0xtx",
                            "accountAgeDays": 295,
                        },
                        "traits": {
                            "winRate": {"percentage": 52.91},
                            "activePositions": {"microdollars": 244_773_051_500},
                            "usdcBalanceMicrodollars": 12_500_000,
                        },
                    }
                }
            },
        ]

        with patch("src.prediction_markets._post_json", side_effect=responses):
            profile = md.get_predictparity_trader_profile("@handle")

        self.assertEqual(profile["id"], "trader-1")
        self.assertEqual(profile["display_name"], "Display")
        self.assertAlmostEqual(profile["all_time_pnl"], 42.25)
        self.assertAlmostEqual(profile["first_funding_amount"], 4999.0)
        self.assertEqual(profile["first_funding_tx_hash"], "0xtx")
        self.assertAlmostEqual(profile["win_rate"], 0.5291)
        self.assertAlmostEqual(profile["active_positions_value"], 244_773.0515)

    def test_predictparity_trader_profile_returns_empty_when_unresolved(self) -> None:
        with patch("src.prediction_markets._post_json", return_value={"data": {"resolveTrader": None}}):
            self.assertEqual(md.get_predictparity_trader_profile("@missing"), {})

    def test_predictparity_traders_parse_public_leaderboard(self) -> None:
        response = {
            "data": {
                "traders": {
                    "data": [
                        {
                            "id": "trader-1",
                            "platform": "polymarket",
                            "platformId": "0x204f72f35326db932158cba6adff0b9a1da95e14",
                            "username": "swisstony",
                            "displayName": "swisstony",
                            "customDisplayName": None,
                            "profileImageUrl": "https://example.com/avatar.png",
                            "isVerified": True,
                            "socialTwitter": "tony",
                            "badges": {"isBot": False, "activePositionsCount": 14},
                            "analytics": {"allTimeVolume": 827_840_000, "allTimePnl": 9_030_000, "rank": 3},
                            "onchain": {"usdcBalance": 2_010_000, "accountAgeDays": 304},
                            "traits": {
                                "winRate": {"percentage": 52.91},
                                "activePositions": {"microdollars": 244_095_180_000},
                                "usdcBalanceMicrodollars": 2_010_000_000_000,
                            },
                        }
                    ],
                    "hasMore": True,
                }
            }
        }

        with patch("src.prediction_markets._post_json", return_value=response) as post_json:
            leaderboard = md.get_predictparity_traders(limit=100, sort_by="volume", search="tony", min_active_positions=100)

        self.assertEqual(len(leaderboard), 1)
        row = leaderboard.iloc[0]
        self.assertEqual(row["source"], "PredictParity")
        self.assertEqual(row["username"], "swisstony")
        self.assertEqual(row["trader"], "swisstony")
        self.assertAlmostEqual(row["pnl"], 9_030_000)
        self.assertAlmostEqual(row["volume"], 827_840_000)
        self.assertAlmostEqual(row["win_rate"], 0.5291)
        self.assertAlmostEqual(row["positions_value"], 244_095.18)
        self.assertAlmostEqual(row["cash_balance"], 2_010_000)
        self.assertEqual(row["open_positions"], 14)
        self.assertEqual(post_json.call_args.kwargs["params"]["op"], "GetTraders")
        variables = post_json.call_args.args[1]["variables"]
        self.assertEqual(variables["sortBy"], "volume")
        self.assertEqual(variables["search"], "tony")
        self.assertEqual(variables["filtersInput"]["minActivePositions"], 100)

    def test_predictparity_trader_pnl_chart_parses_points(self) -> None:
        response = {
            "data": {
                "traderPnlChart": {
                    "range": "1w",
                    "dataPoints": [
                        {"timestamp": 1780056000000, "totalPnl": 10.5},
                        {"timestamp": 1780142400000, "totalPnl": 12.25},
                    ],
                }
            }
        }

        with patch("src.prediction_markets._post_json", return_value=response) as post_json:
            chart = md.get_predictparity_trader_pnl_chart("trader-1", "1w")

        self.assertEqual(len(chart), 2)
        self.assertEqual(chart["series"].tolist(), ["Total PnL", "Total PnL"])
        self.assertEqual(chart["source"].tolist(), ["PredictParity", "PredictParity"])
        self.assertAlmostEqual(float(chart.iloc[-1]["pnl"]), 12.25)
        self.assertEqual(str(chart.iloc[0]["time"]), "2026-05-29 12:00:00+00:00")
        self.assertEqual(post_json.call_args.kwargs["params"]["op"], "GetTraderPnlChart")

    def test_predictparity_trader_pnl_chart_maps_all_window(self) -> None:
        response = {"data": {"traderPnlChart": {"range": "all", "dataPoints": []}}}

        with patch("src.prediction_markets._post_json", return_value=response) as post_json:
            md.get_predictparity_trader_pnl_chart("trader-1", "All")

        self.assertEqual(post_json.call_args.args[1]["variables"]["range"], "all")

    def test_predictparity_trader_pnl_chart_handles_missing_id(self) -> None:
        chart = md.get_predictparity_trader_pnl_chart("", "1w")

        self.assertTrue(chart.empty)
        self.assertEqual(chart.columns.tolist(), ["time", "pnl", "series", "source"])


class PortfolioImportTests(unittest.TestCase):
    def test_market_quick_trade_ticket_prefills_no_outcome(self) -> None:
        row = pd.Series(
            {
                "platform": "Polymarket",
                "market_key": "condition-1",
                "title": "Example market",
                "url": "https://polymarket.com/event/example",
                "yes_price": 0.42,
                "no_price": 0.59,
            }
        )

        ticket = md.market_quick_trade_ticket(row, "No")

        self.assertEqual(ticket["market_key"], "condition-1")
        self.assertEqual(ticket["default_outcome"], "No")
        self.assertAlmostEqual(ticket["yes_price"], 0.42)
        self.assertAlmostEqual(ticket["no_price"], 0.59)

    def test_market_quick_trade_ticket_derives_no_price_when_missing(self) -> None:
        ticket = md.market_quick_trade_ticket({"title": "Derived market", "yes_price": 0.37}, "Yes")

        self.assertEqual(ticket["market_key"], "Derived market")
        self.assertEqual(ticket["default_outcome"], "Yes")
        self.assertAlmostEqual(ticket["no_price"], 0.63)

    def test_wallet_positions_convert_to_research_portfolio_rows(self) -> None:
        positions = pd.DataFrame(
            [
                {
                    "platform": "Polymarket",
                    "title": "Example market",
                    "market_key": "condition-1",
                    "url": "https://polymarket.com/event/example",
                    "outcome": "Yes",
                    "size": "12.5",
                    "avg_price": "0.4",
                    "current_price": "0.6",
                },
                {
                    "platform": "Polymarket",
                    "title": "Zero position",
                    "market_key": "condition-2",
                    "outcome": "No",
                    "size": "0",
                    "avg_price": "0.2",
                    "current_price": "0.1",
                },
            ]
        )

        portfolio = md.wallet_positions_to_research_portfolio(positions)

        self.assertEqual(len(portfolio), 1)
        row = portfolio.iloc[0]
        self.assertEqual(row["market"], "Example market")
        self.assertEqual(row["market_key"], "condition-1")
        self.assertEqual(row["outcome"], "Yes")
        self.assertAlmostEqual(row["shares"], 12.5)
        self.assertAlmostEqual(row["avg_price"], 0.4)
        self.assertAlmostEqual(row["current_price"], 0.6)

    def test_research_trade_preview_caps_sell_to_existing_position(self) -> None:
        preview = md.research_trade_preview(
            existing_shares=10.0,
            existing_avg_price=0.40,
            side="Sell",
            requested_notional=10.0,
            price=0.50,
        )

        self.assertAlmostEqual(preview["requested_shares"], 20.0)
        self.assertAlmostEqual(preview["executed_shares"], 10.0)
        self.assertAlmostEqual(preview["executed_notional"], 5.0)
        self.assertAlmostEqual(preview["new_shares"], 0.0)
        self.assertAlmostEqual(preview["realized_pnl"], 1.0)
        self.assertEqual(preview["capped"], 1.0)

    def test_research_trade_preview_updates_buy_average(self) -> None:
        preview = md.research_trade_preview(
            existing_shares=10.0,
            existing_avg_price=0.30,
            side="Buy",
            requested_notional=8.0,
            price=0.40,
        )

        self.assertAlmostEqual(preview["executed_shares"], 20.0)
        self.assertAlmostEqual(preview["new_shares"], 30.0)
        self.assertAlmostEqual(preview["avg_price_after"], (10.0 * 0.30 + 8.0) / 30.0)
        self.assertAlmostEqual(preview["realized_pnl"], 0.0)

    def test_research_trade_max_notional_uses_cash_for_buy_and_position_for_sell(self) -> None:
        self.assertAlmostEqual(md.research_trade_max_notional(available_cash=125.0, existing_shares=10.0, price=0.4, side="Buy"), 125.0)
        self.assertAlmostEqual(md.research_trade_max_notional(available_cash=125.0, existing_shares=10.0, price=0.4, side="Sell"), 4.0)

    def test_research_trade_executable_notional_caps_buys_to_cash(self) -> None:
        self.assertAlmostEqual(md.research_trade_executable_notional(200.0, available_cash=75.0, side="Buy"), 75.0)
        self.assertAlmostEqual(md.research_trade_executable_notional(200.0, available_cash=75.0, side="Sell"), 200.0)

    def test_polymarket_event_slug_from_url_accepts_event_url_or_slug(self) -> None:
        self.assertEqual(
            md.polymarket_event_slug_from_url("https://polymarket.com/event/wnba-las-dal-2026-05-28"),
            "wnba-las-dal-2026-05-28",
        )
        self.assertEqual(md.polymarket_event_slug_from_url("wnba-las-dal-2026-05-28"), "wnba-las-dal-2026-05-28")

    def test_polymarket_event_markets_normalizes_event_market_rows(self) -> None:
        event_payload = {
            "slug": "example-event",
            "sport": "Basketball",
            "description": "Event rules",
            "markets": [
                {
                    "id": "1",
                    "question": "Example game?",
                    "conditionId": "0xcondition",
                    "slug": "example-game",
                    "outcomes": '["Yes","No"]',
                    "outcomePrices": '["0.42","0.58"]',
                    "clobTokenIds": '["yes-token","no-token"]',
                    "volumeNum": "1000",
                    "volume24hr": "250",
                    "active": True,
                    "closed": False,
                }
            ],
        }

        with patch("src.prediction_markets._get_json", return_value=event_payload):
            markets = md.get_polymarket_event_markets("https://polymarket.com/event/example-event")

        self.assertEqual(len(markets), 1)
        self.assertEqual(markets.iloc[0]["market_key"], "0xcondition")
        self.assertEqual(markets.iloc[0]["event_slug"], "example-event")
        self.assertEqual(markets.iloc[0]["category"], "Basketball")
        self.assertEqual(markets.iloc[0]["yes_token_id"], "yes-token")
        self.assertAlmostEqual(float(markets.iloc[0]["yes_price"]), 0.42)

    def test_held_market_keys_merges_research_and_copy_positions(self) -> None:
        research = pd.DataFrame(
            [
                {"market_key": "research-1", "shares": 10},
                {"market_key": "closed-research", "shares": 0},
                {"market_key": "", "shares": 5},
            ]
        )
        copy = pd.DataFrame(
            [
                {"market_key": "copy-1", "shares": 2.5},
                {"market_key": "closed-copy", "shares": 0},
            ]
        )

        self.assertEqual(md.held_market_keys(research, copy), {"research-1", "copy-1"})

    def test_watchlist_market_upsert_adds_and_refreshes_by_market_key(self) -> None:
        watchlist = [{"platform": "Polymarket", "market_key": "market-1", "title": "Old", "url": ""}]

        updated, changed = md.upsert_watchlist_market(
            watchlist,
            {"platform": "Polymarket", "market_key": "market-1", "title": "New title", "url": "https://example.test/market"},
        )
        added, added_changed = md.upsert_watchlist_market(updated, {"platform": "Kalshi", "ticker": "KX-1", "title": "Kalshi market"})

        self.assertTrue(changed)
        self.assertEqual(len(updated), 1)
        self.assertEqual(updated[0]["title"], "New title")
        self.assertEqual(updated[0]["url"], "https://example.test/market")
        self.assertTrue(added_changed)
        self.assertEqual([item["market_key"] for item in added], ["market-1", "KX-1"])

    def test_watchlist_market_bulk_upsert_dedupes_and_counts_changes(self) -> None:
        watchlist = [{"platform": "Polymarket", "market_key": "market-1", "title": "Old", "url": ""}]
        rows = pd.DataFrame(
            [
                {"platform": "Polymarket", "market_key": "market-1", "title": "Fresh", "url": "https://example.test/fresh"},
                {"platform": "Kalshi", "ticker": "KX-2", "title": "Second", "url": "https://example.test/second"},
                {"platform": "Polymarket", "market_key": "", "title": ""},
            ]
        )

        updated, changed = md.upsert_watchlist_markets(watchlist, rows)

        self.assertEqual(changed, 2)
        self.assertEqual(len(updated), 2)
        self.assertEqual(updated[0]["title"], "Fresh")
        self.assertEqual(updated[1]["market_key"], "KX-2")

    def test_remove_watchlist_market_reports_changed_state(self) -> None:
        watchlist = [{"market_key": "keep"}, {"market_key": "remove"}]

        updated, changed = md.remove_watchlist_market(watchlist, "remove")
        same, same_changed = md.remove_watchlist_market(updated, "missing")

        self.assertTrue(changed)
        self.assertEqual(updated, [{"market_key": "keep"}])
        self.assertFalse(same_changed)
        self.assertEqual(same, [{"market_key": "keep"}])

    def test_upsert_followed_wallet_validates_and_dedupes_addresses(self) -> None:
        wallet = "0x1111111111111111111111111111111111111111"
        wallets, changed = md.upsert_followed_wallet([], wallet)
        duplicate, duplicate_changed = md.upsert_followed_wallet(wallets, wallet.upper().replace("X", "x", 1))
        invalid, invalid_changed = md.upsert_followed_wallet(wallets, "not-a-wallet")

        self.assertTrue(changed)
        self.assertEqual(wallets, [wallet])
        self.assertFalse(duplicate_changed)
        self.assertEqual(duplicate, [wallet])
        self.assertFalse(invalid_changed)
        self.assertEqual(invalid, [wallet])

    def test_upsert_followed_wallets_bulk_adds_valid_unique_wallets(self) -> None:
        first = "0x1111111111111111111111111111111111111111"
        second = "0x2222222222222222222222222222222222222222"
        rows = pd.DataFrame(
            [
                {"wallet": first.upper().replace("X", "x", 1)},
                {"wallet": second},
                {"wallet": "not-a-wallet"},
                {"wallet": pd.NA},
            ]
        )

        updated, changed = md.upsert_followed_wallets([first], rows)

        self.assertEqual(changed, 1)
        self.assertEqual(updated, [first, second])

    def test_tracked_trader_rows_merges_leaderboard_flow_and_positions(self) -> None:
        wallet = "0x1111111111111111111111111111111111111111"
        leaderboard = pd.DataFrame(
            [
                {
                    "wallet": wallet,
                    "rank": 3,
                    "trader": "swisstony",
                    "pnl": 9_000_000.0,
                    "volume": 827_000_000.0,
                    "verified": True,
                }
            ]
        )
        flow = pd.DataFrame(
            [
                {
                    "wallet": wallet.upper().replace("X", "x", 1),
                    "recent_trades": 12,
                    "recent_notional": 34_000.0,
                    "largest_trade": 10_000.0,
                    "markets": 4,
                    "last_seen": "2026-05-29T02:00:00Z",
                    "flow_trait": "Whale",
                }
            ]
        )
        positions = pd.DataFrame([{"wallet": wallet, "positions_value": 123_000.0, "open_positions": 7, "open_markets": 5}])

        tracked = md.tracked_trader_rows([wallet], leaderboard, flow, positions)

        self.assertEqual(len(tracked), 1)
        row = tracked.iloc[0]
        self.assertEqual(row["trader"], "swisstony")
        self.assertEqual(row["tracked_status"], "Active")
        self.assertAlmostEqual(float(row["positions_value"]), 123_000.0)
        self.assertAlmostEqual(float(row["recent_notional"]), 34_000.0)
        self.assertTrue(bool(row["verified"]))

    def test_tracked_trader_rows_dedupes_and_ignores_invalid_wallets(self) -> None:
        wallet = "0x2222222222222222222222222222222222222222"

        tracked = md.tracked_trader_rows([wallet, wallet.upper().replace("X", "x", 1), "bad"])

        self.assertEqual(tracked["wallet"].tolist(), [wallet])
        self.assertEqual(str(tracked.iloc[0]["tracked_status"]), "Idle")

    def test_market_watch_signal_prioritizes_move_spread_then_ending(self) -> None:
        now = pd.Timestamp("2026-05-29T12:00:00Z")

        self.assertEqual(md.market_watch_signal({"change_1h": 0.05, "spread": 0.01, "end_time": "2026-05-30T12:00:00Z"}, now=now), "Fast move")
        self.assertEqual(md.market_watch_signal({"change_1h": 0.01, "spread": 0.02, "end_time": "2026-05-30T12:00:00Z"}, now=now), "Tight spread")
        self.assertEqual(md.market_watch_signal({"change_1h": 0.0, "spread": 0.10, "end_time": "2026-05-30T12:00:00Z"}, now=now), "Ending soon")
        self.assertEqual(md.market_watch_signal({"change_1h": 0.0, "spread": 0.10, "end_time": "2026-07-30T12:00:00Z"}, now=now), "")

    def test_add_market_watch_signals_adds_labels_to_frame(self) -> None:
        markets = pd.DataFrame(
            [
                {"market_key": "a", "change_1h": 0.04, "spread": 0.10, "end_time": "2026-06-30T12:00:00Z"},
                {"market_key": "b", "change_1h": 0.0, "spread": 0.10, "end_time": "2026-05-30T12:00:00Z"},
            ]
        )

        labelled = md.add_market_watch_signals(markets, now=pd.Timestamp("2026-05-29T12:00:00Z"))

        self.assertEqual(labelled["watch_signal"].tolist(), ["Fast move", "Ending soon"])

    def test_market_category_chips_include_counts_and_state(self) -> None:
        markets = pd.DataFrame(
            [
                {"category": "Politics"},
                {"category": "Sports"},
                {"category": "Sports"},
                {"category": "Crypto"},
                {"category": ""},
            ]
        )

        chips = md.market_category_chip_options(markets, ["Politics"], ["Sports"], limit=2)

        self.assertEqual(
            chips,
            [
                {"category": "Sports", "display": "Sports", "count": 2, "state": "exclude", "label": "- Sports 2"},
                {"category": "Politics", "display": "Politics", "count": 1, "state": "include", "label": "+ Politics 1"},
            ],
        )

    def test_market_category_label_humanizes_kalshi_slugs(self) -> None:
        self.assertEqual(md.market_category_label("KXMVESPORTSMULTIGAMEEXTENDED"), "Sports")
        self.assertEqual(md.market_category_label("KXMVECROSSCATEGORY"), "Cross Category")
        self.assertEqual(md.market_category_label("crypto"), "Crypto")

    def test_market_filter_category_infers_sports_from_uncategorized_title(self) -> None:
        self.assertEqual(md.market_filter_category("Uncategorized", "Will Scotland win the 2026 FIFA World Cup?"), "Sports")
        self.assertEqual(md.market_filter_category("Uncategorized", "Will Bitcoin hit $100k?"), "Crypto")

    def test_add_market_filter_metrics_adds_filter_category(self) -> None:
        markets = pd.DataFrame(
            [
                {"category": "Uncategorized", "title": "Will Portugal win the 2026 FIFA World Cup?"},
                {"category": "Uncategorized", "title": "US-Iran nuclear deal by June 30?"},
            ]
        )

        enriched = md.add_market_filter_metrics(markets, now=pd.Timestamp("2026-05-29T12:00:00Z"))

        self.assertEqual(enriched["filter_category"].tolist(), ["Sports", "Uncategorized"])

    def test_market_category_chip_cycle_updates_include_and_exclude_lists(self) -> None:
        include, exclude = md.cycle_market_category_filter([], ["Sports"], "Sports")
        self.assertEqual(include, [])
        self.assertEqual(exclude, [])

        include, exclude = md.cycle_market_category_filter(include, exclude, "Sports")
        self.assertEqual(include, ["Sports"])
        self.assertEqual(exclude, [])

        include, exclude = md.cycle_market_category_filter(include, exclude, "Sports")
        self.assertEqual(include, [])
        self.assertEqual(exclude, ["Sports"])


class WalletActivitySummaryTests(unittest.TestCase):
    def test_wallet_activity_summary_counts_flow(self) -> None:
        activity = pd.DataFrame(
            [
                {"type": "TRADE", "side": "BUY", "notional": 10},
                {"type": "TRADE", "side": "SELL", "notional": 5},
                {"type": "REDEEM", "side": "", "notional": 7},
            ]
        )

        summary = md.wallet_activity_summary(activity)

        self.assertEqual(summary["events"], 3)
        self.assertEqual(summary["notional"], 22)
        self.assertEqual(summary["buys"], 1)
        self.assertEqual(summary["sells"], 1)
        self.assertEqual(summary["settlements"], 1)


class TraderInsightTests(unittest.TestCase):
    def test_trader_insights_estimate_behavior_percentages_and_exposure(self) -> None:
        open_positions = pd.DataFrame([{"value": 25.0}])
        closed_positions = pd.DataFrame([{"realized_pnl": 10.0}, {"realized_pnl": -2.0}])
        trades = pd.DataFrame(
            [
                {"side": "BUY", "price": 0.10, "size": 100.0, "notional": 10.0},
                {"side": "BUY", "price": 0.80, "size": 50.0, "notional": 40.0},
                {"side": "SELL", "price": 0.90, "size": 10.0, "notional": 9.0},
                {"side": "BUY", "price": 0.45, "size": 20.0, "notional": 9.0},
            ]
        )

        insights = md.trader_insight_metrics(open_positions, closed_positions, trades, cash_balance=75.0, whale_threshold=20.0)

        self.assertAlmostEqual(insights["win_rate"], 0.5)
        self.assertAlmostEqual(insights["contrarian"], 19.0 / 68.0)
        self.assertAlmostEqual(insights["trend_follower"], 40.0 / 68.0)
        self.assertAlmostEqual(insights["lottery_ticket"], 10.0 / 68.0)
        self.assertAlmostEqual(insights["whale_splash"], 40.0 / 68.0)
        self.assertAlmostEqual(insights["exposure"], 0.25)

    def test_wallet_pnl_window_filters_curve_rows(self) -> None:
        curve = pd.DataFrame(
            [
                {"time": "2026-05-20T00:00:00Z", "pnl": 1.0, "series": "Realized PnL"},
                {"time": "2026-05-28T00:00:00Z", "pnl": 2.0, "series": "Realized PnL"},
                {"time": "2026-05-29T00:00:00Z", "pnl": 3.0, "series": "Realized + open PnL"},
            ]
        )

        filtered = md.filter_pnl_curve_window(curve, "1w", now=pd.Timestamp("2026-05-29T00:00:00Z"))

        self.assertEqual(filtered["pnl"].tolist(), [2.0, 3.0])

    def test_wallet_pnl_calendar_groups_realized_pnl_by_day(self) -> None:
        closed_positions = pd.DataFrame(
            [
                {"time": "2026-05-28T10:00:00Z", "realized_pnl": 5.0},
                {"time": "2026-05-28T12:00:00Z", "realized_pnl": -2.0},
                {"time": "2026-05-29T09:00:00Z", "realized_pnl": 7.0},
            ]
        )

        calendar = md.wallet_pnl_calendar(closed_positions, "1w", now=pd.Timestamp("2026-05-29T12:00:00Z"))

        self.assertEqual(len(calendar), 2)
        self.assertAlmostEqual(float(calendar.iloc[0]["realized_pnl"]), 3.0)
        self.assertEqual(int(calendar.iloc[0]["closed_positions"]), 2)
        self.assertAlmostEqual(float(calendar.iloc[1]["cumulative_realized_pnl"]), 10.0)

    def test_activity_counterparty_hints_match_near_opposite_public_trade(self) -> None:
        activity = pd.DataFrame(
            [
                {
                    "time": "2026-05-29T00:00:00Z",
                    "type": "TRADE",
                    "side": "BUY",
                    "market_key": "market-1",
                    "asset": "asset-1",
                    "price": 0.42,
                    "size": 100.0,
                    "wallet": "0xtarget",
                }
            ]
        )
        public_trades = pd.DataFrame(
            [
                {
                    "time": "2026-05-29T00:00:02Z",
                    "side": "SELL",
                    "market_key": "market-1",
                    "asset": "asset-1",
                    "price": 0.421,
                    "size": 98.0,
                    "wallet": "0xcounter",
                    "trader": "counterparty",
                },
                {
                    "time": "2026-05-29T00:00:01Z",
                    "side": "BUY",
                    "market_key": "market-1",
                    "asset": "asset-1",
                    "price": 0.42,
                    "size": 100.0,
                    "wallet": "0xwrongside",
                    "trader": "wrongside",
                },
            ]
        )

        enriched = md.enrich_activity_counterparties(activity, public_trades, wallet="0xtarget")

        self.assertEqual(enriched.iloc[0]["counterparty"], "counterparty")
        self.assertEqual(enriched.iloc[0]["counterparty_wallet"], "0xcounter")
        self.assertGreater(float(enriched.iloc[0]["counterparty_confidence"]), 0.9)
        self.assertAlmostEqual(float(enriched.iloc[0]["counterparty_time_delta_sec"]), 2.0)


class HolderEnrichmentTests(unittest.TestCase):
    def test_market_positions_normalize_active_and_closed_pnl(self) -> None:
        payload = [
            {
                "token": "yes-token",
                "positions": [
                    {
                        "proxyWallet": "0x1111111111111111111111111111111111111111",
                        "name": "alice",
                        "asset": "yes-token",
                        "conditionId": "market-1",
                        "avgPrice": 0.25,
                        "size": 100.0,
                        "currPrice": 0.40,
                        "currentValue": 40.0,
                        "cashPnl": 15.0,
                        "realizedPnl": 3.0,
                        "totalPnl": 18.0,
                        "totalBought": 25.0,
                        "outcome": "Yes",
                        "outcomeIndex": 0,
                        "verified": True,
                    }
                ],
            },
            {
                "token": "no-token",
                "positions": [
                    {
                        "proxyWallet": "0x2222222222222222222222222222222222222222",
                        "name": "bob",
                        "asset": "no-token",
                        "conditionId": "market-1",
                        "avgPrice": 0.70,
                        "size": 0.0,
                        "currPrice": 0.0,
                        "currentValue": 0.0,
                        "cashPnl": 0.0,
                        "realizedPnl": 8.0,
                        "totalPnl": 8.0,
                        "totalBought": 70.0,
                        "outcome": "No",
                        "outcomeIndex": 1,
                    }
                ],
            },
        ]

        with patch("src.prediction_markets._get_json", return_value=payload) as fetch:
            positions = md.get_polymarket_market_positions("market-1", status="OPEN", sort_by="TOTAL_PNL", limit=50)

        params = fetch.call_args.kwargs["params"]
        self.assertEqual(params["status"], "OPEN")
        self.assertEqual(params["sortBy"], "TOTAL_PNL")
        self.assertEqual(positions["trader"].tolist(), ["alice", "bob"])
        self.assertEqual(positions.iloc[0]["status"], "Active")
        self.assertEqual(positions.iloc[1]["status"], "Closed")
        self.assertAlmostEqual(float(positions.iloc[0]["total_pnl"]), 18.0)
        self.assertAlmostEqual(float(positions.iloc[0]["avg_price"]), 0.25)
        self.assertTrue(bool(positions.iloc[0]["verified"]))

    def test_enrich_market_holders_adds_value_pnl_and_latest_activity(self) -> None:
        holders = pd.DataFrame(
            [
                {"wallet": "0xabc", "trader": "alice", "outcome": "Yes", "amount": 100.0},
                {"wallet": "0xdef", "trader": "bob", "outcome": "No", "amount": 50.0},
            ]
        )
        trades = pd.DataFrame(
            [
                {"wallet": "0xabc", "outcome": "Yes", "side": "BUY", "size": 40.0, "price": 0.20, "time": "2026-05-28T10:00:00Z"},
                {"wallet": "0xabc", "outcome": "Yes", "side": "BUY", "size": 60.0, "price": 0.30, "time": "2026-05-28T11:00:00Z"},
                {"wallet": "0xabc", "outcome": "Yes", "side": "SELL", "size": 5.0, "price": 0.45, "time": "2026-05-28T12:00:00Z"},
            ]
        )

        enriched = md.enrich_market_holders(holders, trades, yes_price=0.50, no_price=0.50)

        row = enriched[enriched["wallet"].eq("0xabc")].iloc[0]
        self.assertAlmostEqual(row["shares"], 100.0)
        self.assertAlmostEqual(row["value"], 50.0)
        self.assertAlmostEqual(row["avg_price_est"], 0.26)
        self.assertAlmostEqual(row["unrealized_pnl_est"], 24.0)
        self.assertEqual(row["activity_side"], "SELL")
        self.assertAlmostEqual(row["activity_size"], 5.0)

    def test_holder_strength_summary_tracks_side_skew_and_concentration(self) -> None:
        holders = pd.DataFrame(
            [
                {"outcome": "Yes", "value": 70.0},
                {"outcome": "Yes", "value": 10.0},
                {"outcome": "No", "value": 20.0},
            ]
        )

        summary = md.holder_strength_summary(holders)

        self.assertEqual(summary["dominant_side"], "Yes")
        self.assertAlmostEqual(summary["yes_value"], 80.0)
        self.assertAlmostEqual(summary["no_value"], 20.0)
        self.assertAlmostEqual(summary["yes_share"], 0.8)
        self.assertAlmostEqual(summary["skew"], 0.6)
        self.assertAlmostEqual(summary["top_10_share"], 1.0)

    def test_holder_side_panels_split_yes_no_by_shares(self) -> None:
        holders = pd.DataFrame(
            [
                {"trader": "small-yes", "wallet": "0x1", "outcome": "Yes", "shares": 10.0, "value": 4.0, "activity": "Buy 10"},
                {"trader": "big-yes", "wallet": "0x2", "outcome": "Yes", "shares": 25.0, "value": 9.0, "activity": "Sell 1"},
                {"trader": "no", "wallet": "0x3", "outcome": "No", "shares": 11.0, "value": 6.0, "activity": "Buy 11"},
            ]
        )

        panels = md.holder_side_panels(holders, top_n=1)

        self.assertEqual(panels["Yes"].iloc[0]["trader"], "big-yes")
        self.assertEqual(len(panels["Yes"]), 1)
        self.assertEqual(panels["No"].iloc[0]["trader"], "no")
        self.assertIn("activity", panels["Yes"].columns)


if __name__ == "__main__":
    unittest.main()
