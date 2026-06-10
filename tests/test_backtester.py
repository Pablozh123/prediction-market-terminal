import json
import unittest

import pandas as pd

from app import backtester as bt


def trade(time, side, price, size, asset="tok-yes", market_key="cond-1", outcome="Yes", title="Test market"):
    return {
        "time": pd.Timestamp(time, tz="UTC"),
        "type": "TRADE",
        "side": side,
        "outcome": outcome,
        "title": title,
        "price": price,
        "size": size,
        "notional": price * size,
        "market_key": market_key,
        "asset": asset,
        "transactionHash": f"0x{abs(hash((time, side, price, size, asset))):x}",
    }


def frame(rows):
    return pd.DataFrame(rows)


def config(**overrides):
    base = dict(
        wallet="0x" + "a" * 40,
        days=90,
        bankroll=1000.0,
        sizing_mode=bt.SIZING_FIXED,
        stake_value=25.0,
        max_stake=250.0,
        fee_bps=0.0,
        slippage_bps=0.0,
        flat_stake=25.0,
    )
    base.update(overrides)
    return bt.BacktestConfig(**base)


class ReplayTests(unittest.TestCase):
    def test_fixed_buy_then_full_sell_books_profit(self):
        trades = frame(
            [
                trade("2026-05-01", "BUY", 0.50, 100.0),
                trade("2026-05-05", "SELL", 0.80, 100.0),
            ]
        )
        ledger, positions = bt.replay(trades, config())
        self.assertEqual(list(ledger["status"]), ["copied", "copied"])
        sell = ledger.iloc[1]
        self.assertAlmostEqual(sell["realized_pnl"], 15.0, places=6)
        self.assertEqual(positions, {})

    def test_fees_and_slippage_reduce_pnl(self):
        trades = frame(
            [
                trade("2026-05-01", "BUY", 0.50, 100.0),
                trade("2026-05-05", "SELL", 0.80, 100.0),
            ]
        )
        ledger, _ = bt.replay(trades, config(fee_bps=100.0, slippage_bps=100.0))
        buy = ledger.iloc[0]
        sell = ledger.iloc[1]
        self.assertAlmostEqual(buy["exec_price"], 0.505, places=6)
        self.assertAlmostEqual(buy["fee"], 0.25, places=6)
        shares = 25.0 / 0.505
        proceeds = shares * 0.792
        expected_realized = proceeds - proceeds * 0.01 - 25.0
        self.assertAlmostEqual(sell["realized_pnl"], expected_realized, places=6)
        self.assertLess(expected_realized, 15.0)

    def test_partial_source_sell_mirrors_fraction(self):
        trades = frame(
            [
                trade("2026-05-01", "BUY", 0.50, 100.0),
                trade("2026-05-05", "SELL", 0.60, 40.0),
            ]
        )
        ledger, positions = bt.replay(trades, config())
        sell = ledger.iloc[1]
        self.assertAlmostEqual(sell["shares"], 50.0 * 0.4, places=6)
        self.assertIn("tok-yes", positions)
        self.assertAlmostEqual(positions["tok-yes"]["shares"], 30.0, places=6)
        self.assertAlmostEqual(positions["tok-yes"]["cost_basis"], 15.0, places=6)

    def test_sell_without_position_is_skipped(self):
        trades = frame([trade("2026-05-01", "SELL", 0.50, 100.0)])
        ledger, positions = bt.replay(trades, config())
        self.assertEqual(ledger.iloc[0]["status"], "skipped")
        self.assertEqual(positions, {})

    def test_percent_sizing_uses_equity(self):
        trades = frame([trade("2026-05-01", "BUY", 0.50, 100.0)])
        ledger, _ = bt.replay(trades, config(sizing_mode=bt.SIZING_PERCENT, stake_value=5.0))
        self.assertAlmostEqual(ledger.iloc[0]["stake"], 50.0, places=6)

    def test_mirror_sizing_scales_source_notional(self):
        trades = frame([trade("2026-05-01", "BUY", 0.50, 1000.0)])
        ledger, _ = bt.replay(trades, config(sizing_mode=bt.SIZING_MIRROR, stake_value=2.0))
        self.assertAlmostEqual(ledger.iloc[0]["stake"], 10.0, places=6)

    def test_max_stake_caps_sizing(self):
        trades = frame([trade("2026-05-01", "BUY", 0.50, 1000.0)])
        ledger, _ = bt.replay(trades, config(sizing_mode=bt.SIZING_PERCENT, stake_value=50.0, max_stake=100.0))
        self.assertAlmostEqual(ledger.iloc[0]["stake"], 100.0, places=6)

    def test_cash_exhaustion_clamps_then_skips(self):
        trades = frame(
            [
                trade("2026-05-01", "BUY", 0.50, 100.0, asset="tok-1", market_key="c1"),
                trade("2026-05-02", "BUY", 0.50, 100.0, asset="tok-2", market_key="c2"),
                trade("2026-05-03", "BUY", 0.50, 100.0, asset="tok-3", market_key="c3"),
            ]
        )
        ledger, _ = bt.replay(trades, config(bankroll=30.0))
        self.assertEqual(list(ledger["status"]), ["copied", "copied", "skipped"])
        self.assertAlmostEqual(ledger.iloc[0]["stake"], 25.0, places=6)
        self.assertAlmostEqual(ledger.iloc[1]["stake"], 5.0, places=6)

    def test_bad_trade_data_is_skipped(self):
        trades = frame([trade("2026-05-01", "BUY", 0.0, 100.0)])
        ledger, positions = bt.replay(trades, config())
        self.assertEqual(ledger.iloc[0]["status"], "skipped")
        self.assertEqual(positions, {})


class FadeStrategyTests(unittest.TestCase):
    def test_fade_buy_opens_opposite_side(self):
        trades = frame([trade("2026-05-01", "BUY", 0.60, 100.0)])
        ledger, positions = bt.replay(trades, config(strategy=bt.STRATEGY_FADE))
        buy = ledger.iloc[0]
        self.assertAlmostEqual(buy["exec_price"], 0.40, places=6)
        self.assertAlmostEqual(buy["shares"], 25.0 / 0.40, places=6)
        self.assertIn("fade:tok-yes", positions)
        self.assertTrue(positions["fade:tok-yes"]["fade"])

    def test_fade_loses_when_source_side_wins(self):
        trades = frame([trade("2026-05-01", "BUY", 0.60, 100.0)])
        _, positions = bt.replay(trades, config(strategy=bt.STRATEGY_FADE))
        token_values = {"tok-yes": {"price": 1.0, "closed": True, "end_time": pd.Timestamp("2026-05-20", tz="UTC")}}
        settlement, _ = bt.settle(positions, token_values, asof=pd.Timestamp("2026-06-01", tz="UTC"))
        self.assertAlmostEqual(settlement.iloc[0]["realized_pnl"], -25.0, places=6)

    def test_fade_wins_when_source_side_loses(self):
        trades = frame([trade("2026-05-01", "BUY", 0.60, 100.0)])
        _, positions = bt.replay(trades, config(strategy=bt.STRATEGY_FADE))
        token_values = {"tok-yes": {"price": 0.0, "closed": True, "end_time": pd.Timestamp("2026-05-20", tz="UTC")}}
        settlement, _ = bt.settle(positions, token_values, asof=pd.Timestamp("2026-06-01", tz="UTC"))
        self.assertAlmostEqual(settlement.iloc[0]["realized_pnl"], (25.0 / 0.40) * 1.0 - 25.0, places=6)

    def test_fade_mirrored_sell_exits_at_inverse_price(self):
        trades = frame(
            [
                trade("2026-05-01", "BUY", 0.60, 100.0),
                trade("2026-05-05", "SELL", 0.80, 100.0),
            ]
        )
        ledger, positions = bt.replay(trades, config(strategy=bt.STRATEGY_FADE))
        sell = ledger.iloc[1]
        self.assertAlmostEqual(sell["exec_price"], 0.20, places=6)
        expected = (25.0 / 0.40) * 0.20 - 25.0
        self.assertAlmostEqual(sell["realized_pnl"], expected, places=6)
        self.assertEqual(positions, {})

    def test_fade_open_position_marks_to_inverse_market(self):
        trades = frame([trade("2026-05-01", "BUY", 0.60, 100.0)])
        _, positions = bt.replay(trades, config(strategy=bt.STRATEGY_FADE))
        token_values = {"tok-yes": {"price": 0.7, "closed": False, "end_time": None}}
        settlement, open_positions = bt.settle(positions, token_values, asof=pd.Timestamp("2026-06-01", tz="UTC"))
        self.assertTrue(settlement.empty)
        self.assertAlmostEqual(open_positions.iloc[0]["current_price"], 0.3, places=6)
        self.assertAlmostEqual(open_positions.iloc[0]["unrealized_pnl"], (25.0 / 0.40) * 0.3 - 25.0, places=6)


class SettleTests(unittest.TestCase):
    def _positions(self):
        trades = frame([trade("2026-05-01", "BUY", 0.50, 100.0)])
        _, positions = bt.replay(trades, config())
        return positions

    def test_resolution_win_realizes_payout(self):
        positions = self._positions()
        token_values = {"tok-yes": {"price": 1.0, "closed": True, "end_time": pd.Timestamp("2026-05-20", tz="UTC")}}
        settlement, open_positions = bt.settle(positions, token_values, asof=pd.Timestamp("2026-06-01", tz="UTC"))
        self.assertEqual(len(settlement), 1)
        self.assertAlmostEqual(settlement.iloc[0]["realized_pnl"], 50.0 - 25.0, places=6)
        self.assertTrue(open_positions.empty)

    def test_resolution_loss_realizes_negative(self):
        positions = self._positions()
        token_values = {"tok-yes": {"price": 0.0, "closed": True, "end_time": pd.Timestamp("2026-05-20", tz="UTC")}}
        settlement, _ = bt.settle(positions, token_values, asof=pd.Timestamp("2026-06-01", tz="UTC"))
        self.assertAlmostEqual(settlement.iloc[0]["realized_pnl"], -25.0, places=6)

    def test_open_position_marks_to_market(self):
        positions = self._positions()
        token_values = {"tok-yes": {"price": 0.6, "closed": False, "end_time": None}}
        settlement, open_positions = bt.settle(positions, token_values, asof=pd.Timestamp("2026-06-01", tz="UTC"))
        self.assertTrue(settlement.empty)
        self.assertEqual(len(open_positions), 1)
        self.assertAlmostEqual(open_positions.iloc[0]["unrealized_pnl"], 50.0 * 0.6 - 25.0, places=6)

    def test_unknown_token_falls_back_to_cost(self):
        positions = self._positions()
        settlement, open_positions = bt.settle(positions, {}, asof=pd.Timestamp("2026-06-01", tz="UTC"))
        self.assertTrue(settlement.empty)
        self.assertAlmostEqual(open_positions.iloc[0]["unrealized_pnl"], 0.0, places=6)
        self.assertEqual(open_positions.iloc[0]["market_status"], "unknown")


class CurveAndStatsTests(unittest.TestCase):
    def test_equity_curve_and_drawdown(self):
        trades = frame(
            [
                trade("2026-05-01", "BUY", 0.50, 100.0, asset="tok-1", market_key="c1"),
                trade("2026-05-03", "SELL", 0.80, 100.0, asset="tok-1", market_key="c1"),
                trade("2026-05-05", "BUY", 0.50, 100.0, asset="tok-2", market_key="c2"),
                trade("2026-05-07", "SELL", 0.10, 100.0, asset="tok-2", market_key="c2"),
            ]
        )
        ledger, _ = bt.replay(trades, config())
        start = pd.Timestamp("2026-04-30", tz="UTC")
        end = pd.Timestamp("2026-05-10", tz="UTC")
        curve = bt.equity_curve(ledger, start, end, 1000.0)
        self.assertEqual(len(curve), 11)
        self.assertAlmostEqual(curve["equity"].iloc[0], 1000.0, places=6)
        self.assertAlmostEqual(curve["equity"].iloc[-1], 1000.0 + 15.0 - 20.0, places=6)
        self.assertLessEqual(curve["drawdown"].min(), 0.0)
        stats = bt.compute_stats(ledger, bt._empty_positions(), curve, 1000.0)
        self.assertEqual(stats["closed_trades"], 2)
        self.assertEqual(stats["wins"], 1)
        self.assertEqual(stats["losses"], 1)
        self.assertAlmostEqual(stats["win_rate"], 0.5, places=6)
        self.assertAlmostEqual(stats["total_pnl"], -5.0, places=6)
        self.assertAlmostEqual(stats["max_drawdown"], curve["drawdown"].min(), places=6)
        self.assertAlmostEqual(stats["profit_factor"], 15.0 / 20.0, places=6)

    def test_empty_ledger_stats_are_zeroed(self):
        curve = bt.equity_curve(
            bt._empty_ledger(),
            pd.Timestamp("2026-05-01", tz="UTC"),
            pd.Timestamp("2026-05-10", tz="UTC"),
            1000.0,
        )
        stats = bt.compute_stats(bt._empty_ledger(), bt._empty_positions(), curve, 1000.0)
        self.assertEqual(stats["copied_trades"], 0)
        self.assertIsNone(stats["win_rate"])
        self.assertAlmostEqual(stats["final_equity"], 1000.0, places=6)


class RunBacktestTests(unittest.TestCase):
    def test_end_to_end_with_injected_fetchers(self):
        now = pd.Timestamp("2026-06-10", tz="UTC")
        rows = [
            trade("2026-05-01", "BUY", 0.50, 100.0, asset="tok-yes", market_key="cond-1"),
            trade("2026-05-05", "BUY", 0.40, 50.0, asset="tok-open", market_key="cond-2"),
            trade("2025-12-01", "BUY", 0.50, 100.0, asset="tok-old", market_key="cond-3"),
        ]
        activity = pd.DataFrame(rows)
        redeem = trade("2026-05-06", "", 0.5, 10.0, asset="tok-yes", market_key="cond-1")
        redeem["type"] = "REDEEM"
        activity = pd.concat([activity, pd.DataFrame([redeem])], ignore_index=True)

        def fetch_activity(wallet, limit=500, offset=0):
            return activity if offset == 0 else pd.DataFrame()

        def fetch_markets(ids):
            self.assertIn("cond-1", ids)
            self.assertIn("cond-2", ids)
            return [
                {
                    "conditionId": "cond-1",
                    "clobTokenIds": json.dumps(["tok-yes", "tok-no"]),
                    "outcomePrices": json.dumps(["1", "0"]),
                    "closed": True,
                    "endDate": "2026-05-20T00:00:00Z",
                },
                {
                    "conditionId": "cond-2",
                    "clobTokenIds": json.dumps(["tok-open", "tok-open-no"]),
                    "outcomePrices": json.dumps(["0.6", "0.4"]),
                    "closed": False,
                    "endDate": "2026-12-31T00:00:00Z",
                },
            ]

        result = bt.run_backtest(
            config(),
            fetch_activity=fetch_activity,
            fetch_markets_by_ids=fetch_markets,
            now=now,
        )
        self.assertEqual(result.stats["copied_trades"], 2)
        self.assertEqual(result.stats["closed_trades"], 1)
        self.assertAlmostEqual(result.stats["realized_pnl"], 25.0, places=6)
        self.assertEqual(result.stats["open_positions"], 1)
        expected_unrealized = (25.0 / 0.40) * 0.6 - 25.0
        self.assertAlmostEqual(result.stats["unrealized_pnl"], expected_unrealized, places=6)
        self.assertIn("benchmark", result.equity.columns)
        self.assertEqual(len(result.equity), 91)
        self.assertTrue(result.ledger["time"].is_monotonic_decreasing)
        self.assertAlmostEqual(
            result.equity["equity"].iloc[-1],
            result.stats["final_equity"],
            places=6,
        )

    def test_benchmark_uses_flat_stake(self):
        now = pd.Timestamp("2026-06-10", tz="UTC")
        rows = [
            trade("2026-05-01", "BUY", 0.50, 2000.0, asset="tok-1", market_key="c1"),
            trade("2026-05-02", "BUY", 0.50, 2000.0, asset="tok-2", market_key="c2"),
        ]
        activity = pd.DataFrame(rows)

        def fetch_activity(wallet, limit=500, offset=0):
            return activity if offset == 0 else pd.DataFrame()

        result = bt.run_backtest(
            config(sizing_mode=bt.SIZING_MIRROR, stake_value=10.0, flat_stake=25.0),
            fetch_activity=fetch_activity,
            fetch_markets_by_ids=lambda ids: [],
            now=now,
        )
        self.assertAlmostEqual(result.stats["volume_copied"], 200.0, places=6)
        self.assertAlmostEqual(result.benchmark_stats["volume_copied"], 50.0, places=6)

    def test_window_truncation_is_flagged_for_hyperactive_wallets(self):
        now = pd.Timestamp("2026-06-10", tz="UTC")

        def fetch_activity(wallet, limit=500, offset=0):
            rows = [
                trade("2026-06-01", "BUY", 0.5, 10.0, asset=f"tok-{offset}-{i}", market_key=f"c-{offset}-{i}")
                for i in range(limit)
            ]
            return pd.DataFrame(rows)

        result = bt.run_backtest(
            config(),
            fetch_activity=fetch_activity,
            fetch_markets_by_ids=lambda ids: [],
            now=now,
        )
        self.assertTrue(result.stats["window_truncated"])
        self.assertIn("effective_start", result.stats)

    def test_window_fully_covered_is_not_flagged(self):
        now = pd.Timestamp("2026-06-10", tz="UTC")
        activity = pd.DataFrame([trade("2026-05-01", "BUY", 0.5, 10.0)])

        def fetch_activity(wallet, limit=500, offset=0):
            return activity if offset == 0 else pd.DataFrame()

        result = bt.run_backtest(
            config(),
            fetch_activity=fetch_activity,
            fetch_markets_by_ids=lambda ids: [],
            now=now,
        )
        self.assertFalse(result.stats["window_truncated"])

    def test_empty_activity_yields_flat_result(self):
        result = bt.run_backtest(
            config(),
            fetch_activity=lambda wallet, limit=500, offset=0: pd.DataFrame(),
            fetch_markets_by_ids=lambda ids: [],
            now=pd.Timestamp("2026-06-10", tz="UTC"),
        )
        self.assertTrue(result.ledger.empty)
        self.assertEqual(result.stats["copied_trades"], 0)
        self.assertAlmostEqual(result.equity["equity"].iloc[-1], 1000.0, places=6)


if __name__ == "__main__":
    unittest.main()
