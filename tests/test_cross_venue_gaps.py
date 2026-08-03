import json
import tempfile
import unittest
from pathlib import Path

from src import cross_venue_gaps as cvg


def pm_market(question="Will the Republicans win the House in 2026?",
              bid=0.44, ask=0.46, market_id="1", category="politics"):
    return {"id": market_id, "question": question, "bestBid": bid,
            "bestAsk": ask, "category": category}


def kalshi_market(title="Republicans win the House 2026", ticker="CONTROLH-2026-R",
                  bid=0.50, ask=0.52, category="Elections", subtitle=""):
    return {"ticker": ticker, "title": title, "subtitle": subtitle,
            "category": category, "yes_bid": bid, "yes_ask": ask}


class NormaliseTests(unittest.TestCase):
    def test_stopwords_and_punctuation_are_removed(self):
        self.assertEqual(cvg.normalise("Will the Fed cut rates?"),
                         ["fed", "cut", "rates"])

    def test_numbers_survive_because_they_carry_the_strike(self):
        self.assertIn("2026", cvg.normalise("House control in 2026"))

    def test_single_characters_are_dropped(self):
        self.assertNotIn("a", cvg.normalise("a b Fed"))

    def test_empty_input_is_empty(self):
        self.assertEqual(cvg.normalise(""), [])
        self.assertEqual(cvg.normalise(None), [])


class MatchScoreTests(unittest.TestCase):
    def test_identical_titles_score_one(self):
        score, shared = cvg.match_score("Fed cuts rates", "Fed cuts rates")
        self.assertEqual(score, 1.0)
        self.assertEqual(shared, 3)

    def test_unrelated_titles_score_zero(self):
        score, shared = cvg.match_score("Fed cuts rates", "Lakers win title")
        self.assertEqual(score, 0.0)
        self.assertEqual(shared, 0)

    def test_partial_overlap_scores_between(self):
        score, _ = cvg.match_score("Fed cuts rates in March",
                                   "Fed cuts rates in June")
        self.assertGreater(score, 0.4)
        self.assertLess(score, 1.0)

    def test_an_empty_side_cannot_match(self):
        self.assertEqual(cvg.match_score("", "Fed"), (0.0, 0))


class SuspectPairTests(unittest.TestCase):
    """The two failure modes that produced the largest apparent edges live."""

    def test_winning_versus_merely_running_is_flagged(self):
        reasons = cvg.suspect_reasons(
            "Will Mark Kelly win the 2028 Democratic presidential nomination?",
            "Who will run for the Democratic presidential nomination in 2028? Mark Kelly")
        self.assertTrue(reasons)
        self.assertIn("different question types", reasons[0])

    def test_a_margin_market_is_not_the_outright_market(self):
        reasons = cvg.suspect_reasons(
            "Will Abdul El-Sayed win the 2026 Michigan Democratic Primary?",
            "Michigan Democratic Senate primary margin of victory? Abdul El-Sayed, 6-9%")
        self.assertTrue(reasons)

    def test_a_genuine_pair_is_not_flagged(self):
        self.assertEqual(cvg.suspect_reasons(
            "Will Marco Rubio win the 2028 US Presidential Election?",
            "2028 U.S. Presidential Election winner? Marco Rubio"), [])

    def test_word_forms_do_not_count_as_a_difference(self):
        # "winner" gegen "win" ist dieselbe Frage, nur andere Wortform.
        self.assertEqual(cvg.suspect_reasons("Who wins the race?",
                                             "Race winner?"), [])

    def test_winning_a_nomination_equals_being_the_nominee(self):
        # Fehlalarm aus dem ersten Livelauf: beide fragen nach dem Ergebnis.
        self.assertEqual(cvg.suspect_reasons(
            "Will J.B. Pritzker win the 2028 Democratic presidential nomination?",
            "2028 Democratic presidential nominee J.B. Pritzker"), [])

    def test_hosting_questions_match_across_phrasings(self):
        self.assertEqual(cvg.suspect_reasons(
            "Will Sofia host Eurovision 2027?",
            "Which city will host Eurovision in 2027? Sofia"), [])

    def test_a_percentage_range_on_one_side_only_is_flagged(self):
        self.assertTrue(cvg.suspect_reasons("Lakers win the title",
                                            "Lakers title odds 6-9%"))

    def test_suspect_pairs_are_excluded_from_the_headline_counts(self):
        rows = [
            {"tradable": True, "suspect": ["Fragewoerter"], "net_edge_cents": 78.0,
             "gross_edge_cents": 80.0, "breakeven_gap_cents": 1.2},
            {"tradable": True, "suspect": [], "net_edge_cents": 1.0,
             "gross_edge_cents": 3.0, "breakeven_gap_cents": 2.0},
        ]
        summary = cvg.summarise(rows)
        self.assertEqual(summary["suspect"], 1)
        self.assertEqual(summary["usable"], 1)
        self.assertEqual(summary["max_net_cents"], 1.0)

    def test_a_run_of_only_suspect_pairs_reports_nothing_usable(self):
        summary = cvg.summarise([{"tradable": True, "suspect": ["x"],
                                  "net_edge_cents": 50.0}])
        self.assertEqual(summary["usable"], 0)
        self.assertIsNone(summary["max_net_cents"])

    def test_candidates_carry_their_suspect_reasons(self):
        found = cvg.find_candidates(
            [pm_market(question="Will Kelly win the 2028 nomination?")],
            [kalshi_market(title="Who will run for the 2028 nomination? Kelly",
                           ticker="KX-1")])
        self.assertTrue(found)
        self.assertTrue(found[0].suspect)


class HoldingPeriodTests(unittest.TestCase):
    def test_a_future_date_yields_positive_days(self):
        self.assertGreater(cvg.days_until("2099-01-01T00:00:00Z"), 0)

    def test_a_past_date_is_treated_as_unknown(self):
        self.assertIsNone(cvg.days_until("2000-01-01T00:00:00Z"))

    def test_several_date_formats_are_accepted(self):
        for value in ("2099-01-01T00:00:00Z", "2099-01-01T00:00:00.000Z",
                      "2099-01-01"):
            self.assertIsNotNone(cvg.days_until(value), value)

    def test_unreadable_input_is_none(self):
        self.assertIsNone(cvg.days_until("irgendwann"))
        self.assertIsNone(cvg.days_until(None))

    def test_a_distant_resolution_shrinks_the_annualised_return(self):
        near = dict(pm_market(bid=0.30, ask=0.32), endDate="2026-09-01T00:00:00Z")
        far = dict(pm_market(bid=0.30, ask=0.32), endDate="2099-01-01T00:00:00Z")
        kalshi = [kalshi_market(bid=0.60, ask=0.62)]
        near_row = cvg.evaluate_candidate(cvg.find_candidates([near], kalshi)[0])
        far_row = cvg.evaluate_candidate(cvg.find_candidates([far], kalshi)[0])
        self.assertEqual(near_row["net_edge_cents"], far_row["net_edge_cents"])
        self.assertGreater(near_row["annualised_return"],
                           far_row["annualised_return"])

    def test_a_pair_without_a_date_reports_no_annualised_figure(self):
        row = cvg.evaluate_candidate(
            cvg.find_candidates([pm_market()], [kalshi_market()])[0])
        self.assertIsNone(row["annualised_return"])


class CategoryTests(unittest.TestCase):
    def test_kalshi_elections_map_onto_the_politics_fee_rate(self):
        self.assertEqual(cvg.kalshi_category_as_pm("Elections"), "politics")

    def test_world_maps_onto_the_fee_free_category(self):
        self.assertEqual(cvg.kalshi_category_as_pm("World"), "geopolitics")

    def test_an_unknown_category_falls_back(self):
        self.assertEqual(cvg.kalshi_category_as_pm("Voegel"), "other")

    def test_polymarket_category_is_read_from_the_market(self):
        self.assertEqual(cvg.pm_category({"category": "Sports"}), "sports")

    def test_a_market_without_category_falls_back(self):
        self.assertEqual(cvg.pm_category({}), "other")


class QuoteTests(unittest.TestCase):
    def test_best_bid_and_ask_are_used_when_present(self):
        self.assertEqual(cvg.pm_quote({"bestBid": 0.4, "bestAsk": 0.42}),
                         (0.4, 0.42))

    def test_outcome_prices_are_the_fallback(self):
        bid, ask = cvg.pm_quote({"outcomePrices": json.dumps(["0.37", "0.63"])})
        self.assertEqual((bid, ask), (0.37, 0.37))

    def test_a_market_without_any_price_yields_zeroes(self):
        self.assertEqual(cvg.pm_quote({}), (0.0, 0.0))


class CandidateTests(unittest.TestCase):
    def test_a_clear_pair_is_found(self):
        found = cvg.find_candidates([pm_market()], [kalshi_market()])
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].kalshi_ticker, "CONTROLH-2026-R")

    def test_an_unrelated_market_is_not_paired(self):
        found = cvg.find_candidates(
            [pm_market()], [kalshi_market(title="Lakers beat Celtics tonight",
                                          ticker="KXNBA-1")])
        self.assertEqual(found, [])

    def test_too_few_shared_tokens_blocks_a_match(self):
        found = cvg.find_candidates([pm_market(question="Fed decision")],
                                    [kalshi_market(title="Fed")],
                                    min_shared=2)
        self.assertEqual(found, [])

    def test_only_the_best_kalshi_match_per_market_is_kept(self):
        found = cvg.find_candidates(
            [pm_market()],
            [kalshi_market(ticker="A", title="Republicans House Senate 2026 odds"),
             kalshi_market(ticker="B", title="Republicans win House 2026")])
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].kalshi_ticker, "B")

    def test_candidates_are_ranked_by_score(self):
        found = cvg.find_candidates(
            [pm_market(market_id="1"),
             pm_market(market_id="2", question="Republicans win the House 2026")],
            [kalshi_market()])
        self.assertGreaterEqual(found[0].score, found[1].score)

    def test_the_threshold_is_respected(self):
        # Teilueberlappung liegt bei rund 0.5 und faellt unter eine 0.9-Huerde.
        partial = [kalshi_market(title="Republicans win the Senate in 2028")]
        self.assertTrue(cvg.find_candidates([pm_market()], partial,
                                            min_score=0.3))
        self.assertEqual(cvg.find_candidates([pm_market()], partial,
                                             min_score=0.9), [])

    def test_top_n_caps_the_list(self):
        markets = [pm_market(market_id=str(i)) for i in range(5)]
        self.assertEqual(len(cvg.find_candidates(markets, [kalshi_market()],
                                                 top_n=2)), 2)


class EconomicsTests(unittest.TestCase):
    def _candidate(self, pm_bid=0.44, pm_ask=0.46, kx_bid=0.50, kx_ask=0.52):
        return cvg.find_candidates(
            [pm_market(bid=pm_bid, ask=pm_ask)],
            [kalshi_market(bid=kx_bid, ask=kx_ask)])[0]

    def test_both_directions_are_checked(self):
        result = cvg.evaluate_candidate(self._candidate())
        self.assertEqual(result["directions_checked"], 2)

    def test_the_better_direction_wins(self):
        # Polymarket billig, Kalshi teuer -> auf Polymarket kaufen.
        result = cvg.evaluate_candidate(self._candidate())
        self.assertEqual(result["direction"], "pm_yes_kalshi_no")

    def test_the_reverse_direction_is_picked_when_kalshi_is_cheaper(self):
        result = cvg.evaluate_candidate(
            self._candidate(pm_bid=0.60, pm_ask=0.62, kx_bid=0.40, kx_ask=0.42))
        self.assertEqual(result["direction"], "kalshi_yes_pm_no")

    def test_a_gap_that_only_covers_fees_is_not_tradable(self):
        # 2 Cent brutto gegen rund 2.75 Cent Gebuehren.
        result = cvg.evaluate_candidate(
            self._candidate(pm_bid=0.48, pm_ask=0.49, kx_bid=0.51, kx_ask=0.52))
        self.assertGreater(result["gross_edge_cents"], 0)
        self.assertLess(result["net_edge_cents"], 0)
        self.assertFalse(result["is_arbitrage"])

    def test_a_wide_gap_survives_both_fees(self):
        result = cvg.evaluate_candidate(
            self._candidate(pm_bid=0.30, pm_ask=0.32, kx_bid=0.60, kx_ask=0.62))
        self.assertTrue(result["is_arbitrage"])

    def test_depth_caps_the_size(self):
        result = cvg.evaluate_candidate(self._candidate(), shares=1000,
                                        kalshi_depth=25.0)
        self.assertEqual(result["shares"], 25.0)

    def test_missing_quotes_are_reported_as_untradable(self):
        candidate = cvg.Candidate(
            pm_id="1", pm_question="q", pm_category="politics", pm_bid=0.0,
            pm_ask=0.0, kalshi_ticker="T", kalshi_title="t",
            kalshi_category="Elections", kalshi_bid=0.0, kalshi_ask=0.0,
            score=0.9, shared_tokens=3)
        result = cvg.evaluate_candidate(candidate)
        self.assertFalse(result["tradable"])

    def test_a_fee_free_pair_has_a_lower_bar(self):
        political = cvg.evaluate_candidate(self._candidate())
        world = cvg.find_candidates(
            [pm_market(category="geopolitics")],
            [kalshi_market(category="World")])[0]
        world_result = cvg.evaluate_candidate(world)
        self.assertLess(world_result["breakeven_gap_cents"],
                        political["breakeven_gap_cents"])


class SummaryTests(unittest.TestCase):
    def test_an_empty_run_is_reported_not_crashed(self):
        summary = cvg.summarise([])
        self.assertEqual(summary["usable"], 0)
        self.assertIsNone(summary["median_net_cents"])

    def test_untradable_rows_are_excluded(self):
        summary = cvg.summarise([{"tradable": False}])
        self.assertEqual(summary["usable"], 0)
        self.assertEqual(summary["pairs"], 1)

    def test_gross_and_net_counts_are_separate(self):
        rows = [
            {"tradable": True, "gross_edge_cents": 2.0, "net_edge_cents": -0.5,
             "breakeven_gap_cents": 2.5},
            {"tradable": True, "gross_edge_cents": 5.0, "net_edge_cents": 2.0,
             "breakeven_gap_cents": 3.0},
        ]
        summary = cvg.summarise(rows)
        self.assertEqual(summary["gross_positive"], 2)
        self.assertEqual(summary["net_positive"], 1)

    def test_medians_are_computed_over_usable_rows(self):
        rows = [{"tradable": True, "gross_edge_cents": g, "net_edge_cents": g - 3,
                 "breakeven_gap_cents": 3.0} for g in (1.0, 2.0, 3.0)]
        summary = cvg.summarise(rows)
        self.assertEqual(summary["median_gross_cents"], 2.0)


class ReportTests(unittest.TestCase):
    def _results(self):
        candidate = cvg.find_candidates([pm_market()], [kalshi_market()])[0]
        rows = [cvg.evaluate_candidate(candidate)]
        return {
            "ts_utc": "2026-07-31T00:00:00Z", "pm_markets": 10,
            "kalshi_markets": 20, "min_match_score": 0.45, "shares": 100.0,
            "fee_model_version": "2026-07-30", "pairs_verified": False,
            "summary": cvg.summarise(rows), "rows": rows,
        }

    def test_all_three_report_files_are_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = cvg.write_outputs(self._results(), "test",
                                      research_dir=Path(tmp))
            for key in ("json", "csv", "md"):
                self.assertTrue(paths[key].exists(), key)

    def test_the_report_states_that_pairs_are_unverified(self):
        with tempfile.TemporaryDirectory() as tmp:
            body = cvg.write_outputs(self._results(), "test",
                                     research_dir=Path(tmp))["md"].read_text(
                                         encoding="utf-8")
            self.assertIn("pairs are not verified", body)
            self.assertIn("comparison of its resolution rules", body)

    def test_the_report_avoids_the_eszett(self):
        with tempfile.TemporaryDirectory() as tmp:
            body = cvg.write_outputs(self._results(), "test",
                                     research_dir=Path(tmp))["md"].read_text(
                                         encoding="utf-8")
            self.assertNotIn("ß", body)


class EndToEndTests(unittest.TestCase):
    def test_study_runs_against_injected_feeds(self):
        def pm_get(url, params=None):
            if params and params.get("offset"):
                return []
            return [dict(pm_market(), outcomes=json.dumps(["Yes", "No"]),
                         clobTokenIds=json.dumps(["a", "b"]))]

        def kx_get(path, params=None):
            if "orderbook" in path:
                return {"orderbook_fp": {"yes_dollars": [["0.50", "30"]],
                                         "no_dollars": [["0.48", "30"]]}}
            return {"cursor": "", "events": [{
                "event_ticker": "E", "series_ticker": "S", "category": "Elections",
                "title": "Republicans win the House 2026",
                "markets": [{"ticker": "CONTROLH-2026-R", "volume_24h_fp": "100",
                             "open_interest_fp": "10", "yes_bid_dollars": "0.50",
                             "yes_ask_dollars": "0.52"}]}]}

        results = cvg.run_study(pm_pages=1, kalshi_top_n=5, pm_get_json=pm_get,
                                kalshi_get_json=kx_get)
        self.assertEqual(results["pm_markets"], 1)
        self.assertEqual(results["kalshi_markets"], 1)
        self.assertFalse(results["pairs_verified"])
        self.assertEqual(results["summary"]["pairs"], 1)

    def test_a_study_without_matches_does_not_crash(self):
        def pm_get(url, params=None):
            return []

        def kx_get(path, params=None):
            return {"cursor": "", "events": []}

        results = cvg.run_study(pm_pages=1, pm_get_json=pm_get,
                                kalshi_get_json=kx_get)
        self.assertEqual(results["summary"]["usable"], 0)


if __name__ == "__main__":
    unittest.main()
