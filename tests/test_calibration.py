import unittest

import pandas as pd

from app import calibration as calib


def resolved_frame(rows):
    columns = ["title", "avg_price", "current_price", "realized_pnl", "total_bought", "time", "market_key"]
    frame = pd.DataFrame(rows, columns=columns)
    return frame


def row(title, avg_price, current_price, realized_pnl, total_bought=50.0, time="2026-06-01", market_key="c1"):
    return [title, avg_price, current_price, realized_pnl, total_bought, pd.Timestamp(time, tz="UTC"), market_key]


class ResolutionFrameTests(unittest.TestCase):
    def test_decisive_settlement_uses_current_price(self):
        frame = calib.resolution_frame(
            resolved_frame([row("win", 0.40, 1.0, 60.0), row("loss", 0.60, 0.0, -60.0)])
        )
        self.assertEqual(len(frame), 2)
        self.assertEqual(list(frame["outcome"]), [1.0, 0.0])
        self.assertEqual(list(frame["forecast"]), [0.40, 0.60])

    def test_indecisive_price_falls_back_to_pnl_sign(self):
        frame = calib.resolution_frame(
            resolved_frame([row("early exit win", 0.70, 0.5, 30.0), row("early exit loss", 0.30, 0.5, -10.0)])
        )
        self.assertEqual(list(frame["outcome"]), [1.0, 0.0])

    def test_rows_without_entry_price_are_dropped(self):
        frame = calib.resolution_frame(
            resolved_frame([row("bad", 0.0, 1.0, 10.0), row("nan", float("nan"), 1.0, 10.0), row("ok", 0.5, 1.0, 25.0)])
        )
        self.assertEqual(len(frame), 1)
        self.assertEqual(frame.iloc[0]["title"], "ok")

    def test_empty_input(self):
        self.assertTrue(calib.resolution_frame(pd.DataFrame()).empty)
        self.assertTrue(calib.resolution_frame(None).empty)


class CalibrationReportTests(unittest.TestCase):
    def _frame(self):
        return calib.resolution_frame(
            resolved_frame(
                [
                    row("a", 0.40, 1.0, 60.0, total_bought=40.0),
                    row("b", 0.60, 0.0, -60.0, total_bought=60.0),
                    row("c", 0.25, 1.0, 75.0, total_bought=25.0),
                    row("d", 0.70, 0.5, 30.0, total_bought=35.0),
                ]
            )
        )

    def test_report_numbers(self):
        report = calib.calibration_report(self._frame())
        self.assertEqual(report["n"], 4)
        self.assertAlmostEqual(report["hit_rate"], 0.75, places=9)
        self.assertAlmostEqual(report["avg_entry"], 0.4875, places=9)
        self.assertAlmostEqual(report["edge_per_share"], 0.2625, places=9)
        self.assertAlmostEqual(report["brier_entry"], 0.343125, places=9)
        self.assertAlmostEqual(report["brier_baseline"], 0.1875, places=9)  # p̄(1−p̄) at 75% base rate
        self.assertAlmostEqual(report["stake_weighted_edge"], 17.25 / 160.0, places=9)
        self.assertLess(report["edge_low"], report["edge_per_share"])
        self.assertGreater(report["edge_high"], report["edge_per_share"])
        self.assertFalse(report["sample_ok"])
        self.assertIn("Small sample", report["note"])
        self.assertFalse(report["buckets"].empty)

    def test_capped_note_wins(self):
        report = calib.calibration_report(self._frame(), capped=True)
        self.assertTrue(report["capped"])
        self.assertIn("Extremes-only", report["note"])

    def test_empty_report(self):
        report = calib.calibration_report(pd.DataFrame())
        self.assertEqual(report["n"], 0)
        self.assertIsNone(report["hit_rate"])
        self.assertIn("No resolved positions", report["note"])


class RealizedEdgeTests(unittest.TestCase):
    def _frame(self, wins, losses, price=0.5):
        rows = [row(f"w{i}", price, 1.0, 50.0, market_key=f"mw{i}") for i in range(wins)]
        rows += [row(f"l{i}", price, 0.0, -50.0, market_key=f"ml{i}") for i in range(losses)]
        return calib.resolution_frame(resolved_frame(rows))

    def test_positive_edge_clears_zero(self):
        # 30W/10L at 0.5 entry: mean edge +0.25, t-CI well above zero.
        report = calib.realized_edge(self._frame(30, 10))
        self.assertEqual(report["verdict"], "positive")
        self.assertEqual(report["n_events"], 40)
        self.assertAlmostEqual(report["edge"], 0.25, places=9)
        self.assertGreater(report["ci_low"], 0.0)
        self.assertLess(report["ci_low"], report["edge"])
        self.assertIn("Edge beyond chance", report["headline"])

    def test_coinflip_record_reads_as_chance(self):
        report = calib.realized_edge(self._frame(15, 15))
        self.assertEqual(report["verdict"], "chance")
        self.assertAlmostEqual(report["edge"], 0.0, places=9)
        self.assertLess(report["ci_low"], 0.0)
        self.assertGreater(report["ci_high"], 0.0)

    def test_negative_edge(self):
        # 10W/30L at 0.5 entry: mean edge -0.25, CI below zero.
        report = calib.realized_edge(self._frame(10, 30))
        self.assertEqual(report["verdict"], "negative")
        self.assertLess(report["ci_high"], 0.0)

    def test_thin_sample_gets_no_verdict(self):
        report = calib.realized_edge(self._frame(8, 2))
        self.assertEqual(report["verdict"], "thin")
        self.assertEqual(report["n_events"], 10)
        self.assertIsNotNone(report["ci_low"])  # still reported, just not a verdict
        self.assertIn("Too few resolved events", report["headline"])

    def test_capped_feed_blocks_verdict(self):
        report = calib.realized_edge(self._frame(30, 10), capped=True)
        self.assertEqual(report["verdict"], "capped")
        self.assertIn("Extremes-only", report["headline"])

    def test_negrisk_legs_net_to_one_event(self):
        # Three legs of one event + one standalone market → 2 independent events.
        frame = resolved_frame(
            [
                row("leg a", 0.30, 1.0, 70.0, market_key="c1"),
                row("leg b", 0.40, 0.0, -40.0, market_key="c2"),
                row("leg c", 0.20, 0.0, -20.0, market_key="c3"),
                row("solo", 0.50, 1.0, 50.0, market_key="c4"),
            ]
        )
        frame["url"] = [
            "https://polymarket.com/event/one-event",
            "https://polymarket.com/event/one-event",
            "https://polymarket.com/event/one-event",
            "https://polymarket.com/event/other-event",
        ]
        report = calib.realized_edge(calib.resolution_frame(frame))
        self.assertEqual(report["n_positions"], 4)
        self.assertEqual(report["n_events"], 2)

    def test_single_event_has_no_interval(self):
        report = calib.realized_edge(self._frame(1, 0))
        self.assertEqual(report["verdict"], "thin")
        self.assertIsNone(report["ci_low"])

    def test_empty_input(self):
        report = calib.realized_edge(pd.DataFrame())
        self.assertEqual(report["verdict"], "none")
        self.assertEqual(report["n_events"], 0)

    def test_t_quantile_asymptote(self):
        self.assertAlmostEqual(calib._t_quantile_975(1), 12.706, places=3)
        self.assertAlmostEqual(calib._t_quantile_975(30), 2.042, places=3)
        self.assertAlmostEqual(calib._t_quantile_975(60), 2.0017, places=3)
        self.assertGreater(calib._t_quantile_975(1000), 1.96)


if __name__ == "__main__":
    unittest.main()
