import unittest

import pandas as pd

from app import calibration as calib


def resolved_frame(rows):
    columns = ["title", "avg_price", "current_price", "realized_pnl", "total_bought", "time", "market_key"]
    frame = pd.DataFrame(rows, columns=columns)
    return frame


def row(title, avg_price, current_price, realized_pnl, total_bought=100.0, time="2026-06-01", market_key="c1"):
    """``total_bought`` is the API's unit: SHARES. Dollars at risk = shares x avg_price."""
    return [title, avg_price, current_price, realized_pnl, total_bought, pd.Timestamp(time, tz="UTC"), market_key]


class ResolutionFrameTests(unittest.TestCase):
    def test_decisive_settlement_uses_current_price(self):
        frame = calib.resolution_frame(
            resolved_frame([row("win", 0.40, 1.0, 60.0), row("loss", 0.60, 0.0, -60.0)])
        )
        self.assertEqual(len(frame), 2)
        self.assertEqual(list(frame["outcome"]), [1.0, 0.0])
        self.assertEqual(list(frame["forecast"]), [0.40, 0.60])

    def test_unsettled_market_is_not_scored(self):
        # A position closed by selling out of a still-trading market has a
        # trading result, not an outcome. Scoring the +30 exit as "the 70%
        # entry resolved YES" would put an open market on the curve.
        frame = calib.resolution_frame(
            resolved_frame([row("early exit win", 0.70, 0.5, 30.0), row("early exit loss", 0.30, 0.5, -10.0)])
        )
        self.assertTrue(frame.empty)

    def test_unresolved_exits_are_counted(self):
        rows = resolved_frame(
            [
                row("settled win", 0.40, 1.0, 60.0),
                row("early exit win", 0.70, 0.55, 30.0),
                row("still holding", 0.42, 0.42, 0.0),
                row("no entry price", 0.0, 0.61, 5.0),
            ]
        )
        self.assertEqual(len(calib.resolution_frame(rows)), 1)
        self.assertEqual(calib.unresolved_exits(rows), 2)
        self.assertEqual(calib.unresolved_exits(pd.DataFrame()), 0)

    def test_open_market_no_longer_reads_as_a_loss(self):
        # realized_pnl 0 on an untouched open position used to score 0/1 as a
        # loss at the entry price; now it is simply not a resolution.
        frame = calib.resolution_frame(resolved_frame([row("open", 0.42, 0.42, 0.0)]))
        self.assertTrue(frame.empty)

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
                    # Anteile, nicht Dollar: 100 x 0.40 = 40 Dollar Einsatz usw.
                    row("a", 0.40, 1.0, 60.0, total_bought=100.0),
                    row("b", 0.60, 0.0, -60.0, total_bought=100.0),
                    row("c", 0.25, 1.0, 75.0, total_bought=100.0),
                    row("d", 0.70, 1.0, 30.0, total_bought=50.0),
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
        self.assertEqual(report["n_unresolved"], 0)
        self.assertLess(report["edge_low"], report["edge_per_share"])
        self.assertGreater(report["edge_high"], report["edge_per_share"])
        self.assertFalse(report["sample_ok"])
        self.assertIn("Small sample", report["note"])
        self.assertFalse(report["buckets"].empty)

    def test_unresolved_count_is_reported_next_to_the_sample(self):
        report = calib.calibration_report(self._frame(), unresolved=7)
        self.assertEqual(report["n_unresolved"], 7)
        self.assertIn("still trading", report["note"])

    def test_only_unresolved_positions_report_an_honest_empty(self):
        report = calib.calibration_report(pd.DataFrame(), unresolved=12)
        self.assertEqual(report["n"], 0)
        self.assertEqual(report["n_unresolved"], 12)
        self.assertIn("still trading", report["note"])

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


class EventCountTests(unittest.TestCase):
    """Die Quote zaehlt Positionen, das Verdict darueber zaehlt Events.

    ``realized_edge`` nettet die Beine eines NegRisk-Events zu einer
    Beobachtung, weil ihre Ausgaenge mechanisch korreliert sind. Die
    Trefferquote, ihr Wilson-Intervall und die Eimer der Kurve taten das
    nicht, und die Seite nannte den Unterschied nicht. Beide Zahlen stehen
    jetzt in der Nutzlast.
    """

    def _legs(self) -> pd.DataFrame:
        # Vier Beine eines Events plus zwei einzelne Maerkte.
        rows = [
            {"forecast": 0.20, "outcome": 1.0, "stake": 10.0, "title": "leg a", "time": pd.NaT,
             "market_key": "m1", "event_key": "E1"},
            {"forecast": 0.25, "outcome": 0.0, "stake": 10.0, "title": "leg b", "time": pd.NaT,
             "market_key": "m2", "event_key": "E1"},
            {"forecast": 0.30, "outcome": 0.0, "stake": 10.0, "title": "leg c", "time": pd.NaT,
             "market_key": "m3", "event_key": "E1"},
            {"forecast": 0.35, "outcome": 0.0, "stake": 10.0, "title": "leg d", "time": pd.NaT,
             "market_key": "m4", "event_key": "E1"},
            {"forecast": 0.60, "outcome": 1.0, "stake": 10.0, "title": "solo one", "time": pd.NaT,
             "market_key": "m5", "event_key": "E2"},
            {"forecast": 0.70, "outcome": 1.0, "stake": 10.0, "title": "solo two", "time": pd.NaT,
             "market_key": "m6", "event_key": "E3"},
        ]
        return pd.DataFrame(rows)

    def test_the_report_carries_both_counting_units(self) -> None:
        report = calib.calibration_report(self._legs())
        self.assertEqual(report["n"], 6)
        self.assertEqual(report["n_events"], 3)
        self.assertAlmostEqual(report["repeat_factor"], 2.0)
        # Und sie stimmt mit dem Verdict darueber ueberein.
        self.assertEqual(calib.realized_edge(self._legs())["n_events"], 3)

    def test_the_note_says_the_interval_rests_on_positions(self) -> None:
        note = calib.calibration_report(self._legs())["note"]
        self.assertIn("6 positions come from 3 events", note)
        self.assertIn("2.0 legs per event", note)

    def test_a_wallet_without_repeated_legs_is_not_lectured(self) -> None:
        einzeln = self._legs().iloc[4:].reset_index(drop=True)
        report = calib.calibration_report(einzeln)
        self.assertEqual(report["n"], report["n_events"])
        self.assertAlmostEqual(report["repeat_factor"], 1.0)
        self.assertNotIn("legs per event", report["note"])

    def test_every_bucket_names_its_events(self) -> None:
        buckets = calib.calibration_report(self._legs())["buckets"]
        self.assertIn("events", buckets.columns)
        # Der 20-40-Eimer haelt drei Positionen (0.25/0.30/0.35, 0.20 faellt
        # in den Eimer darunter), aber nur ein Event.
        zeile = buckets[buckets["bucket"].eq("20–40%")].iloc[0]
        self.assertEqual(int(zeile["n"]), 3)
        self.assertEqual(int(zeile["events"]), 1)
        # Und die Summe ueber die Eimer bleibt die Zahl der Positionen.
        self.assertEqual(int(buckets["n"].sum()), 6)

    def test_an_empty_report_still_carries_the_keys(self) -> None:
        leer = calib.calibration_report(pd.DataFrame())
        self.assertEqual(leer["n_events"], 0)
        self.assertIsNone(leer["repeat_factor"])


if __name__ == "__main__":
    unittest.main()
