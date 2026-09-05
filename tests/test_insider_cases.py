"""data/insider_cases.yaml replayed through the screen: every documented expectation holds."""

from __future__ import annotations

import unittest

from app import insider_cases as ic
from app import risk_log
from app import suspicion as susp


class CaseListTests(unittest.TestCase):
    def setUp(self) -> None:
        self.cases = ic.load_cases()

    def test_the_list_exists_and_every_case_is_usable(self) -> None:
        self.assertGreaterEqual(len(self.cases), 10)
        for case in self.cases:
            self.assertEqual(ic.validate_case(case), [], case.get("id"))

    def test_ids_are_unique_and_sources_are_named(self) -> None:
        ids = [case["id"] for case in self.cases]
        self.assertEqual(len(ids), len(set(ids)))
        for case in self.cases:
            source = str(case["source"])
            self.assertTrue(source.startswith("http") or case["source_kind"] == "store", case["id"])
            self.assertIn(case["expectation"], ic.EXPECTATIONS, case["id"])

    def test_the_list_covers_the_groups_the_screen_is_for(self) -> None:
        categories = {str(case.get("category")) for case in self.cases}
        self.assertTrue({"geopolitics", "macro", "politics"} <= categories, categories)
        expectations = {str(case.get("expectation")) for case in self.cases}
        self.assertTrue({"flag", "no_flag", "excluded"} <= expectations, expectations)

    def test_summary_names_the_file_and_the_count(self) -> None:
        summary = ic.summary()
        self.assertEqual(summary["n"], len(self.cases))
        self.assertEqual(summary["path"], "data/insider_cases.yaml")
        self.assertIn("not a hit rate", summary["reads"])
        self.assertEqual(sum(summary["by_expectation"].values()), len(self.cases))


class CaseTapeTests(unittest.TestCase):
    def test_the_case_prints_sit_in_a_background_window_with_their_origins(self) -> None:
        case = {
            "id": "t-1", "market": "Will the Fed cut rates?", "side": "NO", "price": 0.4, "notional": 30000,
            "wallets": 2, "prints": 4, "minutes_before_end": 120, "first_trade_days": 0.5, "date": "2026-09-01",
        }
        tape, origins, now = ic.case_tape(case)
        mine = tape[tape["title"].eq(case["market"])]
        self.assertEqual(len(mine), 4)
        self.assertEqual(mine["wallet"].nunique(), 2)
        self.assertAlmostEqual(float(mine["notional"].sum()), 30000.0)
        self.assertTrue((mine["outcome"] == "No").all())
        self.assertEqual(len(origins), 2)
        for wallet, origin in origins.items():
            first_print = mine[mine["wallet"].eq(wallet)]["time"].min()
            self.assertAlmostEqual((first_print.timestamp() - origin["first_trade_ts"]) / 86_400.0, 0.5, places=3)
        self.assertEqual(now, ic.case_now(case))
        self.assertGreater(len(tape), 4)

    def test_without_a_first_trade_the_wallet_stays_unmeasured(self) -> None:
        case = {"id": "t-2", "market": "Q?", "side": "YES", "price": 0.5, "notional": 1000, "wallets": 1,
                "first_trade_days": None, "date": "2026-09-01"}
        _, origins, _ = ic.case_tape(case)
        self.assertEqual(origins, {})


class ReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.results = {result["id"]: result for result in ic.replay_all()}

    def test_every_documented_expectation_holds(self) -> None:
        misses = [
            f"{result['id']}: expected {result['expectation']}, got score {result['event_score']} "
            f"flagged={result['flagged']} excluded={result['excluded']} flags={result['flags']}"
            for result in self.results.values() if not result.get("ok", True)
        ]
        self.assertEqual(misses, [])

    def test_the_lone_fresh_wallet_clears_the_floor_through_its_first_trade(self) -> None:
        # The tracker post of 2026-03-27: one wallet, one $170k print at 22 cents.
        result = self.results["pms-2026-03-27-us-forces-iran"]
        self.assertTrue(result["flagged"])
        self.assertGreaterEqual(result["event_score"], risk_log.DEFAULT_MIN_SCORE)
        self.assertEqual(result["context"], susp.CONTEXT_GEOPOLITICS)
        self.assertGreater(result["components"].get("first_trade", 0.0), 20.0)
        self.assertTrue(any(flag.startswith("fresh wallet: first trade") for flag in result["flags"]), result["flags"])
        # The same print without the freshness stays where the old screen left it.
        case = next(c for c in ic.load_cases() if c["id"] == "pms-2026-03-27-us-forces-iran")
        old = ic.replay_case({**case, "first_trade_days": None})
        self.assertFalse(old["flagged"])

    def test_macro_cases_carry_their_own_group(self) -> None:
        for case_id in ("pms-2026-09-04-fed-48k-ten-hour-wallet", "pms-2026-08-31-fed-not-hiking-40k-sixteen-hour-wallet"):
            self.assertEqual(self.results[case_id]["context"], susp.CONTEXT_MACRO, case_id)
            self.assertTrue(self.results[case_id]["flagged"], case_id)

    def test_sports_stays_excluded_and_the_orca_stays_below(self) -> None:
        self.assertTrue(self.results["pms-2026-05-10-ufc-underdog-200k-fresh-wallet"]["excluded"])
        orca = self.results["acdc-2026-08-orca-definition"]
        self.assertFalse(orca["flagged"])
        self.assertLess(orca["event_score"], 20)

    def test_controls_stay_below_the_floor(self) -> None:
        for case_id, result in self.results.items():
            if result["expectation"] == "no_flag":
                self.assertFalse(result["flagged"], case_id)
                self.assertLess(result["event_score"], risk_log.DEFAULT_MIN_SCORE, case_id)

    def test_unreplayable_cases_are_reported_not_scored(self) -> None:
        result = self.results["ap-2026-04-07-ceasefire-fifty-wallets"]
        self.assertFalse(result["replayable"])
        self.assertIsNone(result["event_score"])
        self.assertTrue(result["ok"])


if __name__ == "__main__":
    unittest.main()
