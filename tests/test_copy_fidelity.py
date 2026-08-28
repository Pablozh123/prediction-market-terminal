import unittest

import pandas as pd

from app import copy_fidelity as cf


class ConfigFidelityTests(unittest.TestCase):
    def test_neutral_uncapped_is_full_fidelity(self) -> None:
        report = cf.config_fidelity(19_500.0, 1_530_000.0, multiplier=1.0, scale_cap=0.0)
        self.assertAlmostEqual(report["neutral_scale"], 19_500.0 / 1_530_000.0)
        self.assertAlmostEqual(report["fidelity"], 1.0)
        self.assertEqual(report["factors"], [])

    def test_binding_scale_cap_reports_fidelity_loss(self) -> None:
        # neutral 1.27%, cap 1.0% -> fidelity ~0.787
        report = cf.config_fidelity(19_500.0, 1_530_000.0, multiplier=1.0, scale_cap=0.01)
        self.assertAlmostEqual(report["effective_scale"], 0.01)
        self.assertAlmostEqual(report["fidelity"], 0.01 / (19_500.0 / 1_530_000.0))
        self.assertEqual(len(report["factors"]), 1)
        self.assertIn("Scale cap", report["factors"][0][0])

    def test_non_binding_cap_is_silent(self) -> None:
        report = cf.config_fidelity(1_000.0, 200_000.0, multiplier=1.0, scale_cap=0.01)
        self.assertAlmostEqual(report["fidelity"], 1.0)
        self.assertEqual(report["factors"], [])

    def test_multiplier_scales_fidelity(self) -> None:
        report = cf.config_fidelity(10_000.0, 1_000_000.0, multiplier=0.5, scale_cap=0.0)
        self.assertAlmostEqual(report["fidelity"], 0.5)
        self.assertIn("Multiplier", report["factors"][0][0])

    def test_fixed_mode_compares_to_neutral(self) -> None:
        report = cf.config_fidelity(10_000.0, 1_000_000.0, dynamic_enabled=False, fixed_scale=0.02)
        self.assertAlmostEqual(report["fidelity"], 2.0)
        self.assertIn("Fixed-scale", report["factors"][0][0])

    def test_zero_source_equity_is_safe(self) -> None:
        report = cf.config_fidelity(10_000.0, 0.0)
        self.assertEqual(report["neutral_scale"], 0.0)
        self.assertEqual(report["fidelity"], 0.0)


class ExecutionFidelityTests(unittest.TestCase):
    def _orders(self) -> pd.DataFrame:
        now = pd.Timestamp.now(tz="UTC")
        return pd.DataFrame(
            [
                # full fill
                {"status": "copied", "reason": "buy_scaled", "desired_notional": 10.0, "copy_notional": 10.0, "created_at": now.isoformat()},
                # clamped fill (throttle/cap)
                {"status": "copied", "reason": "buy_scaled", "desired_notional": 8.0, "copy_notional": 2.0, "created_at": now.isoformat()},
                # cash-outage skip
                {"status": "skipped", "reason": "insufficient_cash", "desired_notional": 5.0, "copy_notional": 0.0, "created_at": now.isoformat()},
                # legacy row without desired -> ignored
                {"status": "copied", "reason": "buy_scaled", "desired_notional": 0.0, "copy_notional": 3.0, "created_at": now.isoformat()},
                # outside window -> ignored
                {"status": "skipped", "reason": "insufficient_cash", "desired_notional": 99.0, "copy_notional": 0.0, "created_at": (now - pd.Timedelta(days=3)).isoformat()},
            ]
        )

    def test_window_fidelity_and_loss_breakdown(self) -> None:
        report = cf.execution_fidelity(self._orders(), window_hours=24.0)
        self.assertAlmostEqual(report["desired"], 23.0)
        self.assertAlmostEqual(report["filled"], 12.0)
        self.assertAlmostEqual(report["fidelity"], 12.0 / 23.0)
        self.assertAlmostEqual(report["lost_to_skips"]["insufficient_cash"], 5.0)
        self.assertAlmostEqual(report["lost_to_clamps"], 6.0)
        self.assertEqual(report["orders"], 3)

    def test_empty_orders(self) -> None:
        report = cf.execution_fidelity(pd.DataFrame())
        self.assertIsNone(report["fidelity"])


class PnlOverlayTests(unittest.TestCase):
    def test_overlay_rebases_both_series(self) -> None:
        t0 = pd.Timestamp("2026-06-12T10:00:00+00:00")
        snaps = pd.DataFrame(
            [
                {"snapshot_time": (t0 + pd.Timedelta(minutes=i * 10)).isoformat(), "equity": 1000.0 + i * 10, "contributions": 1000.0}
                for i in range(4)
            ]
        )
        source = pd.DataFrame(
            [
                {"time": t0 + pd.Timedelta(minutes=i * 10), "pnl": 1_000_000.0 + i * 20_000}
                for i in range(4)
            ]
        )
        overlay = cf.pnl_overlay(snaps, source, source_base_equity=2_000_000.0)

        ours = overlay[overlay["series"] == "Paper copy"]
        theirs = overlay[overlay["series"] == "Source wallet"]
        self.assertEqual(len(ours), 4)
        self.assertEqual(len(theirs), 4)
        self.assertAlmostEqual(float(ours["pct"].iloc[0]), 0.0)
        self.assertAlmostEqual(float(theirs["pct"].iloc[0]), 0.0)
        self.assertAlmostEqual(float(ours["pct"].iloc[-1]), 30.0 / 1000.0)
        self.assertAlmostEqual(float(theirs["pct"].iloc[-1]), 60_000.0 / 2_000_000.0)

    def test_overlay_empty_when_no_snapshots(self) -> None:
        source = pd.DataFrame([{"time": pd.Timestamp.now(tz="UTC"), "pnl": 1.0}])
        self.assertTrue(cf.pnl_overlay(pd.DataFrame(), source, 1.0).empty)


class LatencyAndPriceGapTests(unittest.TestCase):
    """Config- und Execution-Fidelity sind reine Notional-Zahlen.

    Der Paper-Book bucht zum Quellpreis (src/copy_trading.py::_insert_order),
    also ist die Slippage bauartbedingt null. Das darf nicht als gemessene
    Null durchgehen, und die Verzoegerung steht ungenutzt daneben.
    """

    NOW = pd.Timestamp("2026-08-28 12:00:00", tz="UTC")

    def _orders(self, rows):
        return pd.DataFrame(rows)

    def _row(self, *, delay_s=45.0, source_price=0.50, copy_price=None, side="BUY",
             copy_size=200.0, status="copied", minutes_ago=30.0):
        booked = self.NOW - pd.Timedelta(minutes=minutes_ago)
        return {
            "created_at": booked.isoformat(),
            "source_time": (booked - pd.Timedelta(seconds=delay_s)).isoformat(),
            "source_side": side,
            "source_price": source_price,
            "copy_price": source_price if copy_price is None else copy_price,
            "copy_size": copy_size,
            "status": status,
        }

    def test_paper_book_reports_zero_modelled_price_impact(self) -> None:
        # Quellpreis 0.50, Kopie zum selben Preis: die Luecke ist genau null,
        # und models_price_impact sagt, dass das eine Bauart ist.
        report = cf.latency_and_price_gap(self._orders([self._row(), self._row()]), now=self.NOW)
        self.assertEqual(report["n"], 2)
        self.assertAlmostEqual(report["mean_price_gap_cents"], 0.0)
        self.assertFalse(report["models_price_impact"])

    def test_latency_percentiles_come_from_the_recorded_stamps(self) -> None:
        rows = [self._row(delay_s=d) for d in (10.0, 20.0, 30.0, 40.0, 300.0)]
        report = cf.latency_and_price_gap(self._orders(rows), now=self.NOW)
        self.assertAlmostEqual(report["median_latency_s"], 30.0)
        self.assertAlmostEqual(report["max_latency_s"], 300.0)
        self.assertGreater(report["p90_latency_s"], 40.0)

    def test_a_real_price_gap_would_be_reported_as_a_cost(self) -> None:
        # Kaufen bei 0.54 statt 0.50 kostet 4 Cent je Anteil; verkaufen bei
        # 0.46 statt 0.50 kostet ebenfalls 4. Gleiches Vorzeichen.
        rows = [
            self._row(source_price=0.50, copy_price=0.54, side="BUY"),
            self._row(source_price=0.50, copy_price=0.46, side="SELL"),
        ]
        report = cf.latency_and_price_gap(self._orders(rows), now=self.NOW)
        self.assertAlmostEqual(report["mean_price_gap_cents"], 4.0, places=9)
        self.assertTrue(report["models_price_impact"])

    def test_assumed_crossing_cost_scales_with_copied_shares(self) -> None:
        rows = [self._row(copy_size=200.0), self._row(copy_size=300.0)]
        report = cf.latency_and_price_gap(self._orders(rows), now=self.NOW, assumed_cross_cents=2.0)
        self.assertAlmostEqual(report["copied_shares"], 500.0)
        self.assertAlmostEqual(report["assumed_cross_cost_usd"], 10.0)
        self.assertAlmostEqual(report["assumed_cross_cents"], 2.0)

    def test_no_assumption_means_no_what_if_number(self) -> None:
        report = cf.latency_and_price_gap(self._orders([self._row()]), now=self.NOW)
        self.assertEqual(report["assumed_cross_cost_usd"], 0.0)

    def test_skipped_orders_and_rows_outside_the_window_are_ignored(self) -> None:
        rows = [
            self._row(status="skipped"),
            self._row(minutes_ago=60 * 48),
            self._row(),
        ]
        self.assertEqual(cf.latency_and_price_gap(self._orders(rows), now=self.NOW)["n"], 1)

    def test_empty_and_missing_columns_are_safe(self) -> None:
        self.assertEqual(cf.latency_and_price_gap(pd.DataFrame(), now=self.NOW)["n"], 0)
        self.assertEqual(cf.latency_and_price_gap(pd.DataFrame([{"x": 1}]), now=self.NOW)["n"], 0)


if __name__ == "__main__":
    unittest.main()
