import json
import tempfile
import unittest
from pathlib import Path

from src import resolution_rules as rr


def kalshi_payload(primary="Resolves YES if X wins.", secondary=""):
    return {"market": {"rules_primary": primary, "rules_secondary": secondary,
                       "expiration_time": "2028-11-08T00:00:00Z"}}


def gamma_payload(description="This market resolves to the winner.",
                  source=""):
    return [{"description": description, "resolutionSource": source,
             "endDate": "2028-11-08T00:00:00Z"}]


def feed(kalshi=None, gamma=None):
    def get_json(url, params=None):
        if "elections.kalshi" in url:
            return kalshi if kalshi is not None else kalshi_payload()
        return gamma if gamma is not None else gamma_payload()
    return get_json


class NormaliseTests(unittest.TestCase):
    def test_whitespace_is_collapsed(self):
        self.assertEqual(rr.normalise_text("a\n\n  b\t c"), "a b c")

    def test_missing_text_becomes_empty(self):
        self.assertEqual(rr.normalise_text(None), "")


class FlagTests(unittest.TestCase):
    def test_an_ambiguity_clause_is_flagged(self):
        self.assertIn("mehrdeutigkeit",
                      rr.flags("If the outcome is ambiguous, the market voids."))

    def test_a_last_traded_price_clause_is_flagged(self):
        self.assertIn("mehrdeutigkeit",
                      rr.flags("settles at the last traded price"))

    def test_a_named_source_is_flagged(self):
        self.assertIn("quelle", rr.flags("according to official results"))

    def test_a_partial_payout_clause_is_flagged(self):
        self.assertIn("teilweise", rr.flags("pro rata across winners"))

    def test_plain_text_trips_nothing_relevant(self):
        self.assertNotIn("mehrdeutigkeit", rr.flags("Resolves YES if X wins."))

    def test_flags_are_case_insensitive(self):
        self.assertIn("mehrdeutigkeit", rr.flags("AMBIGUOUS OUTCOME"))

    def test_empty_text_has_no_flags(self):
        self.assertEqual(rr.flags(""), [])


class FetchTests(unittest.TestCase):
    def test_kalshi_rules_are_read(self):
        result = rr.kalshi_rules("KXA", feed())
        self.assertEqual(result["primary"], "Resolves YES if X wins.")

    def test_polymarket_rules_are_read(self):
        result = rr.polymarket_rules("1", feed())
        self.assertIn("resolves to the winner", result["description"])

    def test_a_failing_kalshi_call_is_reported_not_raised(self):
        def boom(url, params=None):
            raise ConnectionError("weg")
        self.assertIn("error", rr.kalshi_rules("KXA", boom))

    def test_a_failing_gamma_call_is_reported_not_raised(self):
        def boom(url, params=None):
            raise ConnectionError("weg")
        self.assertIn("error", rr.polymarket_rules("1", boom))

    def test_an_empty_gamma_response_does_not_raise(self):
        result = rr.polymarket_rules("1", lambda u, p=None: [])
        self.assertEqual(result["description"], "")


class ComparisonTests(unittest.TestCase):
    def _pair(self):
        return {"kalshi_ticker": "KXA", "polymarket_market_id": "1",
                "question": "Eine Frage"}

    def test_a_pair_with_both_texts_is_marked_as_such(self):
        row = rr.compare_pair(self._pair(), feed())
        self.assertTrue(row["both_texts_present"])

    def test_a_clause_on_one_side_only_is_surfaced(self):
        # Genau der Cardi-B-Fall: eine Boerse regelt Mehrdeutigkeit, die
        # andere nicht.
        row = rr.compare_pair(self._pair(), feed(
            kalshi=kalshi_payload("If ambiguous, settle at last traded price."),
            gamma=gamma_payload("Resolves to the winner.")))
        self.assertIn("mehrdeutigkeit", row["one_sided_flags"])

    def test_a_clause_on_both_sides_is_not_one_sided(self):
        row = rr.compare_pair(self._pair(), feed(
            kalshi=kalshi_payload("If ambiguous, void."),
            gamma=gamma_payload("If the outcome is ambiguous, void.")))
        self.assertNotIn("mehrdeutigkeit", row["one_sided_flags"])

    def test_a_missing_text_is_not_silently_a_match(self):
        row = rr.compare_pair(self._pair(), feed(
            kalshi=kalshi_payload(""), gamma=gamma_payload("")))
        self.assertFalse(row["both_texts_present"])


class ReportTests(unittest.TestCase):
    def _results(self):
        return rr.run_study(self._watchlist, feed())

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self._watchlist = Path(self.tmp.name) / "wl.json"
        self._watchlist.write_text(json.dumps({"paare": [
            {"kalshi_ticker": "KXA", "polymarket_market_id": "1",
             "question": "Eine Frage"}]}), encoding="utf-8")

    def test_the_study_covers_every_pair(self):
        results = self._results()
        self.assertEqual(results["pairs"], 1)
        self.assertEqual(results["with_both_texts"], 1)

    def test_the_report_refuses_to_judge_in_writing(self):
        paths = rr.write_outputs(self._results(), "test",
                                 research_dir=Path(self.tmp.name) / "r")
        body = paths["md"].read_text(encoding="utf-8")
        self.assertIn("urteilt nicht", body)
        self.assertIn("nicht freigegeben", body)
        self.assertNotIn("ß", body)

    def test_both_rulebooks_appear_in_the_report(self):
        paths = rr.write_outputs(self._results(), "test",
                                 research_dir=Path(self.tmp.name) / "r")
        body = paths["md"].read_text(encoding="utf-8")
        self.assertIn("Kalshi", body)
        self.assertIn("Polymarket", body)
        self.assertIn("Resolves YES if X wins.", body)

    def test_an_empty_watchlist_yields_an_empty_study(self):
        empty = Path(self.tmp.name) / "leer.json"
        empty.write_text(json.dumps({"paare": []}), encoding="utf-8")
        self.assertEqual(rr.run_study(empty, feed())["pairs"], 0)


if __name__ == "__main__":
    unittest.main()
