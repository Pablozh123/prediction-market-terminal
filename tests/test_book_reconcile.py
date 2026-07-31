import json
import tempfile
import unittest
from pathlib import Path

from src import book_reconcile as br
from src import book_stream as bs


def stream_with(token="t1", bids=None, asks=None):
    state = bs.StreamState()
    state.handle({
        "event_type": "book", "asset_id": token, "timestamp": "1",
        "bids": bids if bids is not None else [{"price": "0.40", "size": "100"}],
        "asks": asks if asks is not None else [{"price": "0.42", "size": "100"}],
    }, "r1")
    return state


def rest(bids=None, asks=None):
    return {
        "bids": bids if bids is not None else [{"price": "0.40", "size": "100"}],
        "asks": asks if asks is not None else [{"price": "0.42", "size": "100"}],
    }


class RestTouchTests(unittest.TestCase):
    def test_the_best_prices_are_picked_not_the_first(self):
        # Die eigene OpenAPI-Spec und die Prosaseite widersprechen sich zur
        # Sortierung, deshalb verlaesst sich hier nichts auf die Reihenfolge.
        bid, ask = br.rest_touch(rest(
            bids=[{"price": "0.30", "size": "1"}, {"price": "0.40", "size": "1"}],
            asks=[{"price": "0.50", "size": "1"}, {"price": "0.42", "size": "1"}]))
        self.assertEqual((bid, ask), (0.40, 0.42))

    def test_pair_shaped_levels_are_accepted(self):
        bid, _ = br.rest_touch({"bids": [["0.40", "1"]], "asks": []})
        self.assertEqual(bid, 0.40)

    def test_an_empty_side_yields_none(self):
        self.assertEqual(br.rest_touch({"bids": [], "asks": []}), (None, None))

    def test_a_missing_payload_does_not_raise(self):
        self.assertEqual(br.rest_touch({}), (None, None))
        self.assertEqual(br.rest_touch(None), (None, None))

    def test_malformed_levels_are_skipped(self):
        bid, _ = br.rest_touch({"bids": [{"price": "nein"}, {"price": "0.4"}],
                                "asks": []})
        self.assertEqual(bid, 0.4)


class TickInferenceTests(unittest.TestCase):
    """The tick is not constant, and assuming it manufactures false drift."""

    def test_cent_prices_imply_a_cent_tick(self):
        self.assertEqual(br.infer_tick(0.65, 0.66, 0.63), 0.01)

    def test_finer_prices_imply_the_finer_tick(self):
        self.assertEqual(br.infer_tick(0.652, 0.653), 0.001)

    def test_no_prices_falls_back(self):
        self.assertEqual(br.infer_tick(None, None), br.DEFAULT_TICK)

    def test_one_cent_apart_on_a_cent_market_is_one_tick_not_ten(self):
        # Der Fehler aus dem ersten langen Lauf: acht gemeldete Abweichungen,
        # alle glatte Ganz-Cent-Vielfache, alle in Wahrheit ein Tick.
        result = br.compare("t1", stream_with(bids=[{"price": "0.65", "size": "1"}],
                                              asks=[{"price": "0.66", "size": "1"}]),
                            rest(bids=[{"price": "0.64", "size": "1"}],
                                 asks=[{"price": "0.66", "size": "1"}]))
        self.assertEqual(result.bid_diff_ticks, 1.0)
        self.assertEqual(result.verdict(), "match")

    def test_a_genuinely_large_move_is_still_drift(self):
        result = br.compare("t1", stream_with(bids=[{"price": "0.65", "size": "1"}],
                                              asks=[{"price": "0.66", "size": "1"}]),
                            rest(bids=[{"price": "0.55", "size": "1"}],
                                 asks=[{"price": "0.66", "size": "1"}]))
        self.assertEqual(result.verdict(), "drift")


class ComparisonTests(unittest.TestCase):
    def test_identical_books_match(self):
        result = br.compare("t1", stream_with(), rest())
        self.assertEqual(result.verdict(), "match")
        self.assertEqual(result.bid_diff_ticks, 0.0)

    def test_a_one_tick_difference_is_within_tolerance(self):
        result = br.compare("t1", stream_with(),
                            rest(bids=[{"price": "0.401", "size": "1"}]))
        self.assertEqual(result.verdict(tolerance=1.0), "match")

    def test_a_large_difference_is_drift(self):
        result = br.compare("t1", stream_with(),
                            rest(bids=[{"price": "0.30", "size": "1"}]))
        self.assertEqual(result.verdict(), "drift")
        # Zehn Cent auf einem Cent-Markt sind zehn Ticks, nicht hundert.
        self.assertEqual(result.bid_diff_ticks, 10.0)

    def test_a_missing_stream_book_is_named_not_counted_as_match(self):
        result = br.compare("unbekannt", bs.StreamState(), rest())
        self.assertEqual(result.verdict(), "kein Stream-Buch")

    def test_a_missing_rest_book_is_named(self):
        result = br.compare("t1", stream_with(), {"bids": [], "asks": []})
        self.assertEqual(result.verdict(), "kein REST-Buch")

    def test_diffs_are_none_when_a_side_is_absent(self):
        result = br.compare("t1", stream_with(),
                            rest(bids=[], asks=[{"price": "0.42", "size": "1"}]))
        self.assertIsNone(result.bid_diff_ticks)
        self.assertEqual(result.ask_diff_ticks, 0.0)

    def test_the_row_carries_the_verdict_and_both_books(self):
        row = br.compare("t1", stream_with(), rest()).as_row("ts")
        self.assertEqual(row["verdict"], "match")
        self.assertEqual(row["stream_bid"], 0.40)
        self.assertEqual(row["rest_bid"], 0.40)


class SummaryTests(unittest.TestCase):
    def test_an_empty_run_is_reported_not_crashed(self):
        self.assertEqual(br.summarise([])["comparisons"], 0)

    def test_the_rate_ignores_unusable_comparisons(self):
        rows = [
            {"verdict": "match", "bid_diff_ticks": 0.0, "ask_diff_ticks": 0.0},
            {"verdict": "drift", "bid_diff_ticks": 9.0, "ask_diff_ticks": 0.0},
            {"verdict": "kein REST-Buch", "bid_diff_ticks": None,
             "ask_diff_ticks": None},
        ]
        summary = br.summarise(rows)
        self.assertEqual(summary["unusable"], 1)
        self.assertEqual(summary["match_rate"], 0.5)

    def test_the_largest_divergence_is_reported(self):
        rows = [{"verdict": "drift", "bid_diff_ticks": 3.0, "ask_diff_ticks": 9.0}]
        self.assertEqual(br.summarise(rows)["max_diff_ticks"], 9.0)

    def test_a_run_with_only_unusable_rows_has_no_rate(self):
        rows = [{"verdict": "kein Stream-Buch", "bid_diff_ticks": None,
                 "ask_diff_ticks": None}]
        self.assertIsNone(br.summarise(rows)["match_rate"])


class RoundTests(unittest.TestCase):
    def test_a_round_compares_every_token(self):
        rows = br.run_round(["t1"], stream_with(),
                            get_json=lambda u, p=None: rest())
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["verdict"], "match")

    def test_a_failing_request_drops_that_token_only(self):
        calls = {"n": 0}

        def flaky(url, params=None):
            calls["n"] += 1
            if calls["n"] == 1:
                raise ConnectionError("weg")
            return rest()

        rows = br.run_round(["t1", "t1"], stream_with(), get_json=flaky)
        self.assertEqual(len(rows), 1)


class StudyTests(unittest.TestCase):
    class FakeSocket:
        def __init__(self):
            self.sent = []
            self.closed = False

        def send(self, payload):
            self.sent.append(payload)

        def recv(self):
            raise TimeoutError("still")

        def close(self):
            self.closed = True

    def test_a_round_that_cannot_connect_contributes_nothing(self):
        def boom(url):
            raise ConnectionError("refused")

        results = br.run_study(token_count=1, rounds=2, seconds_per_round=0.01,
                               ws_factory=boom,
                               get_json=lambda *a, **k: [])
        self.assertEqual(results["rounds_connected"], 0)
        self.assertEqual(results["summary"]["comparisons"], 0)

    def test_reports_are_written(self):
        results = {"tokens": 1, "rounds_requested": 1, "rounds_connected": 1,
                   "seconds_per_round": 1.0, "tolerance_ticks": 1.0,
                   "summary": br.summarise([]), "rows": []}
        with tempfile.TemporaryDirectory() as tmp:
            paths = br.write_outputs(results, "test", research_dir=Path(tmp))
            body = paths["md"].read_text(encoding="utf-8")
            self.assertIn("Buch-Abgleich", body)
            self.assertIn("keine Sequenznummern", body)
            self.assertNotIn("ß", body)
            json.loads(paths["json"].read_text(encoding="utf-8"))

    def test_rows_append_to_the_day_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows = [br.compare("t1", stream_with(), rest()).as_row("ts")]
            br.append_rows(Path(tmp), rows)
            written = list(Path(tmp).glob("reconcile_*.csv"))
            self.assertEqual(len(written), 1)
            self.assertIn("verdict", written[0].read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
