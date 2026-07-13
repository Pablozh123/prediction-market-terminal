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


if __name__ == "__main__":
    unittest.main()
