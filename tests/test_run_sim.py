import unittest

import pandas as pd

from app import run_sim as rs


def payload():
    return {
        "runs": [
            {
                "profil": "allin_july3",
                "wetten": [
                    {"frage": "Will 'Tourism' be said?", "seite": "YES", "entscheidungs_preis": 0.13,
                     "avg_fill_preis": 0.50, "shares": 10.0, "einsatz_usd": 5.0,
                     "aufgeloest": True, "gewonnen": True, "pnl_usd": 5.0},
                    {"frage": "Will 'Mars' be said?", "seite": "YES", "entscheidungs_preis": 0.20,
                     "avg_fill_preis": 0.25, "shares": 20.0, "einsatz_usd": 5.0,
                     "aufgeloest": True, "gewonnen": False, "pnl_usd": -5.0},
                    {"frage": "Open bet", "seite": "YES", "entscheidungs_preis": 0.10,
                     "avg_fill_preis": 0.85, "shares": 7.0, "einsatz_usd": 6.0,
                     "aufgeloest": False, "gewonnen": None, "pnl_usd": None},
                ],
            },
            {
                "profil": "jre_july6",
                "wetten": [
                    {"frage": "No fill price", "seite": "NO", "entscheidungs_preis": 0.40,
                     "avg_fill_preis": None, "shares": 5.0, "einsatz_usd": 2.0,
                     "aufgeloest": True, "gewonnen": True, "pnl_usd": 3.0},
                ],
            },
        ]
    }


class BetsFrameTests(unittest.TestCase):
    def test_collects_all_bets_with_fill_fallback(self):
        bets = rs.bets_frame(payload())
        self.assertEqual(len(bets), 4)
        # fill falls back to decision price when avg fill missing
        nofill = bets[bets["frage"] == "No fill price"].iloc[0]
        self.assertAlmostEqual(nofill["fill_preis"], 0.40)
        self.assertEqual(set(bets["profil"]), {"allin_july3", "jre_july6"})

    def test_empty_payload_safe(self):
        self.assertTrue(rs.bets_frame(None).empty)
        self.assertTrue(rs.bets_frame({}).empty)


class SimulateSizingTests(unittest.TestCase):
    def test_as_executed_matches_recorded_pnl_shape(self):
        bets = rs.bets_frame(payload())
        frame, summary = rs.simulate_sizing(bets, rs.SIM_AS_EXECUTED)
        # 3 resolved (open bet excluded), one of them via fallback price
        self.assertEqual(summary["n_resolved"], 3)
        self.assertEqual(summary["n_open"], 1)
        win = frame[frame["frage"] == "Will 'Tourism' be said?"].iloc[0]
        # stake 5 at 0.50 -> 10 shares -> win pays 10 * 0.5 = 5
        self.assertAlmostEqual(win["sim_pnl"], 5.0)
        loss = frame[frame["frage"] == "Will 'Mars' be said?"].iloc[0]
        self.assertAlmostEqual(loss["sim_pnl"], -5.0)

    def test_fixed_stake_resizes_every_bet(self):
        bets = rs.bets_frame(payload())
        frame, summary = rs.simulate_sizing(bets, rs.SIM_FIXED, fixed_stake=10.0)
        self.assertTrue((frame["sim_stake"] == 10.0).all())
        # win at 0.50: 20 shares -> +10; loss: -10; win at 0.40: 25 shares -> +15
        self.assertAlmostEqual(summary["sim_pnl"], 10.0 - 10.0 + 15.0)
        self.assertAlmostEqual(summary["sim_stake"], 30.0)

    def test_kelly_sizes_from_bankroll_and_edge(self):
        bets = rs.bets_frame(payload())
        frame, _ = rs.simulate_sizing(
            bets, rs.SIM_KELLY, bankroll=1000.0, kelly_edge_pt=5.0, kelly_fraction=0.25
        )
        win = frame[frame["frage"] == "Will 'Tourism' be said?"].iloc[0]
        # price 0.50, prob 0.55 -> f* = 0.05/0.50 = 10%; quarter -> 2.5% of 1000 = 25
        self.assertAlmostEqual(win["sim_stake"], 25.0, places=6)

    def test_empty_and_unresolved_only(self):
        frame, summary = rs.simulate_sizing(pd.DataFrame(), rs.SIM_FIXED)
        self.assertEqual(summary["n_resolved"], 0)
        only_open = rs.bets_frame({"runs": [{"profil": "x", "wetten": [
            {"frage": "open", "avg_fill_preis": 0.5, "einsatz_usd": 1.0, "aufgeloest": False, "gewonnen": None}
        ]}]})
        frame, summary = rs.simulate_sizing(only_open, rs.SIM_KELLY)
        self.assertEqual(summary["n_resolved"], 0)
        self.assertEqual(summary["n_open"], 1)

    def test_unknown_mode_raises(self):
        with self.assertRaises(ValueError):
            rs.simulate_sizing(rs.bets_frame(payload()), "yolo")


class BotResolutionFrameTests(unittest.TestCase):
    def test_shapes_resolved_bets_for_calibration(self):
        bets = rs.bets_frame(payload())
        scored = rs.bot_resolution_frame(bets)
        self.assertEqual(len(scored), 3)
        self.assertEqual(set(scored["outcome"]), {0, 1})
        self.assertTrue((scored["forecast"] > 0).all())

    def test_feeds_calibration_report(self):
        from app import calibration as calib

        scored = rs.bot_resolution_frame(rs.bets_frame(payload()))
        report = calib.calibration_report(scored, capped=False)
        self.assertEqual(report["n"], 3)
        self.assertIsNotNone(report["hit_rate"])


if __name__ == "__main__":
    unittest.main()


class TimingDecayTests(unittest.TestCase):
    def payload_mit_timing(self):
        return {
            "runs": [
                {
                    "profil": "r1",
                    "wetten": [
                        {  # gewonnen, Referenz steigt, ab +120s ueber der Kaufgrenze
                            "frage": "A", "seite": "YES", "avg_fill_preis": 0.50,
                            "einsatz_usd": 10.0, "shares": 20.0,
                            "aufgeloest": True, "gewonnen": True, "pnl_usd": 10.0,
                            "preis_nach_fill": {"0": 0.50, "30": 0.80, "60": 0.80,
                                                 "120": 0.95, "300": 0.95, "900": 0.95},
                        },
                        {  # offen -> fliegt raus
                            "frage": "B", "seite": "YES", "avg_fill_preis": 0.40,
                            "einsatz_usd": 5.0, "shares": 12.5,
                            "aufgeloest": False, "gewonnen": None, "pnl_usd": None,
                            "preis_nach_fill": {"0": 0.40},
                        },
                        {  # aufgeloest, aber nie ein fremder Kauf -> kein Referenzpreis
                            "frage": "C", "seite": "YES", "avg_fill_preis": 0.90,
                            "einsatz_usd": 5.0, "shares": 5.56,
                            "aufgeloest": True, "gewonnen": True, "pnl_usd": 0.56,
                            "preis_nach_fill": {"0": None, "30": None, "60": None,
                                                 "120": None, "300": None, "900": None},
                        },
                    ],
                }
            ]
        }

    def test_summary_pro_delay(self):
        frame = rs.timing_decay_summary(self.payload_mit_timing())
        self.assertEqual(list(frame["delay_s"]), [0, 30, 60, 120, 300, 900])
        d0 = frame[frame["delay_s"] == 0].iloc[0]
        # A: fremde Referenz 0.50 -> +10; C: kein Fremdkauf -> eigener Fill
        # 0.90 -> 5.56 shares -> +0.56. B ist offen und fliegt raus.
        self.assertEqual(d0["n_bets"], 2)
        self.assertEqual(d0["n_foreign_ref"], 1)
        self.assertAlmostEqual(d0["sim_pnl_usd"], 10.56, places=2)
        self.assertAlmostEqual(d0["pnl_delta_usd"], 0.0)
        d30 = frame[frame["delay_s"] == 30].iloc[0]
        # A: Entry 0.80 -> +2.5 statt +10; C unveraendert
        self.assertAlmostEqual(d30["sim_pnl_usd"], 3.06, places=2)
        self.assertAlmostEqual(d30["pnl_delta_usd"], -7.5, places=2)
        d120 = frame[frame["delay_s"] == 120].iloc[0]
        # A: 0.95 > cap -> priced out, PnL 0; C bleibt
        self.assertEqual(d120["n_priced_out"], 1)
        self.assertAlmostEqual(d120["sim_pnl_usd"], 0.56, places=2)
        self.assertAlmostEqual(d120["pnl_delta_usd"], -10.0, places=2)

    def test_leer_ohne_referenzen(self):
        frame = rs.timing_decay_summary({"runs": []})
        self.assertEqual(int(frame["n_bets"].max()), 0)
