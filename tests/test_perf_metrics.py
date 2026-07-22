import math
import unittest

import pandas as pd

from app import perf_metrics as pmx


def curve(values: list[float], start: str = "2026-01-01") -> pd.DataFrame:
    stamps = pd.date_range(start, periods=len(values), freq="1D", tz="UTC")
    return pd.DataFrame({"time": stamps, "pnl": values})


class DailyPnlTests(unittest.TestCase):
    def test_differences_a_cumulative_curve(self) -> None:
        series = pmx.daily_pnl(curve([0.0, 10.0, 25.0, 20.0]))
        self.assertEqual([round(v, 6) for v in series], [10.0, 15.0, -5.0])

    def test_first_day_is_dropped(self) -> None:
        """A cumulative opening level says nothing about the change that made it."""
        self.assertEqual(len(pmx.daily_pnl(curve([100.0, 110.0]))), 1)

    def test_empty_and_malformed_input(self) -> None:
        self.assertTrue(pmx.daily_pnl(None).empty)
        self.assertTrue(pmx.daily_pnl(pd.DataFrame()).empty)
        self.assertTrue(pmx.daily_pnl(pd.DataFrame({"a": [1]})).empty)


class DrawdownTests(unittest.TestCase):
    def test_measures_peak_to_trough(self) -> None:
        absolute, relative = pmx.max_drawdown([0, 100, 40, 90])
        self.assertAlmostEqual(absolute, 60.0)
        self.assertAlmostEqual(relative, 0.6)

    def test_monotonic_curve_has_no_drawdown(self) -> None:
        absolute, relative = pmx.max_drawdown([0, 10, 20, 30])
        self.assertEqual(absolute, 0.0)
        self.assertEqual(relative, 0.0)

    def test_negative_peak_reports_absolute_only(self) -> None:
        """A peak at or below zero has no meaningful percentage drawdown."""
        absolute, relative = pmx.max_drawdown([-10, -50])
        self.assertAlmostEqual(absolute, 40.0)
        self.assertEqual(relative, 0.0)

    def test_empty(self) -> None:
        self.assertEqual(pmx.max_drawdown([]), (0.0, 0.0))


class RatioTests(unittest.TestCase):
    def test_sharpe_matches_the_definition(self) -> None:
        pnl = [1.0, -1.0, 2.0, 0.0, 3.0]
        series = pd.Series(pnl)
        expected = series.mean() / series.std(ddof=1) * math.sqrt(pmx.TRADING_DAYS)
        self.assertAlmostEqual(pmx.sharpe_ratio(pnl), expected)

    def test_zero_variance_returns_none_not_infinity(self) -> None:
        """A flawless-looking record must not read as an infinite Sharpe."""
        self.assertIsNone(pmx.sharpe_ratio([5.0, 5.0, 5.0]))
        self.assertIsNone(pmx.sharpe_ratio([1.0]))

    def test_sortino_ignores_upside_volatility(self) -> None:
        steady = [1.0, -1.0, 1.0, -1.0]
        spiky = [1.0, -1.0, 50.0, -1.0]
        self.assertGreater(pmx.sortino_ratio(spiky), pmx.sortino_ratio(steady))

    def test_sortino_without_losing_days_is_none(self) -> None:
        self.assertIsNone(pmx.sortino_ratio([1.0, 2.0, 3.0]))

    def test_calmar_needs_a_drawdown(self) -> None:
        self.assertIsNone(pmx.calmar_ratio([1.0, 2.0], [0, 1, 3]))
        self.assertIsNotNone(pmx.calmar_ratio([1.0, -2.0, 1.0], [0, 1, -1, 0]))


class ClusterBootstrapTests(unittest.TestCase):
    def _trades(self, markets: int, fills: int, payout_factor: float) -> pd.DataFrame:
        rows = []
        for m in range(markets):
            for _ in range(fills):
                rows.append({"market": f"m{m}", "cost": 100.0, "payout": 100.0 * payout_factor})
        return pd.DataFrame(rows)

    def test_point_estimate_is_the_realised_edge(self) -> None:
        out = pmx.cluster_bootstrap_edge(self._trades(50, 4, 1.10), "market")
        self.assertAlmostEqual(out["edge"], 0.10, places=6)
        self.assertEqual(out["groups"], 50)

    def test_clustering_uses_markets_not_fills(self) -> None:
        """200 fills across 50 markets is a sample of 50, not 200."""
        out = pmx.cluster_bootstrap_edge(self._trades(50, 4, 1.10), "market")
        self.assertEqual(out["groups"], 50)

    def test_more_fills_per_market_does_not_narrow_the_interval(self) -> None:
        few = pmx.cluster_bootstrap_edge(self._trades(30, 1, 1.10), "market")
        many = pmx.cluster_bootstrap_edge(self._trades(30, 20, 1.10), "market")
        self.assertAlmostEqual(few["ci_high"] - few["ci_low"], many["ci_high"] - many["ci_low"], places=6)

    def test_mixed_outcomes_produce_a_real_interval(self) -> None:
        rows = []
        for m in range(40):
            rows.append({"market": f"m{m}", "cost": 100.0, "payout": 150.0 if m % 2 else 60.0})
        out = pmx.cluster_bootstrap_edge(pd.DataFrame(rows), "market")
        self.assertLess(out["ci_low"], out["edge"])
        self.assertGreater(out["ci_high"], out["edge"])

    def test_missing_columns_and_empty_input(self) -> None:
        self.assertIsNone(pmx.cluster_bootstrap_edge(pd.DataFrame(), "market")["edge"])
        self.assertIsNone(pmx.cluster_bootstrap_edge(pd.DataFrame({"a": [1]}), "market")["edge"])

    def test_zero_cost_is_not_a_division(self) -> None:
        frame = pd.DataFrame([{"market": "m", "cost": 0.0, "payout": 0.0}])
        self.assertIsNone(pmx.cluster_bootstrap_edge(frame, "market")["edge"])


class SummaryTests(unittest.TestCase):
    def test_reports_the_full_set(self) -> None:
        summary = pmx.summarize_curve(curve([0.0, 10.0, 5.0, 30.0]))
        self.assertEqual(summary["n_days"], 3)
        self.assertAlmostEqual(summary["total_pnl"], 30.0)
        self.assertAlmostEqual(summary["best_day"], 25.0)
        self.assertAlmostEqual(summary["worst_day"], -5.0)
        self.assertAlmostEqual(summary["max_drawdown"], 5.0)
        self.assertEqual(summary["winning_days"], 2)
        self.assertEqual(summary["losing_days"], 1)

    def test_returns_stay_none_without_a_capital_base(self) -> None:
        """Quoting a return against an invented stake would fabricate precision."""
        summary = pmx.summarize_curve(curve([0.0, 10.0, 30.0]))
        self.assertIsNone(summary["return_on_capital"])
        self.assertIsNone(summary["annualised_return"])

    def test_capital_base_produces_returns(self) -> None:
        summary = pmx.summarize_curve(curve([0.0, 50.0, 100.0]), capital=200.0)
        self.assertAlmostEqual(summary["return_on_capital"], 0.5)

    def test_ratios_are_scale_invariant(self) -> None:
        small = pmx.summarize_curve(curve([0.0, 1.0, 0.5, 3.0]))
        large = pmx.summarize_curve(curve([0.0, 1000.0, 500.0, 3000.0]))
        self.assertAlmostEqual(small["sharpe"], large["sharpe"])

    def test_empty_curve(self) -> None:
        summary = pmx.summarize_curve(pd.DataFrame({"time": [], "pnl": []}))
        self.assertEqual(summary["n_days"], 0)
        self.assertIsNone(summary["sharpe"])


if __name__ == "__main__":
    unittest.main()
