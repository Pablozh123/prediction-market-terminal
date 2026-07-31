import csv
import json
import tempfile
import unittest
from pathlib import Path

from src import gap_lifetime as gl


def quote(ts, bid, ask):
    return gl.Quote(ts=ts, bid=bid, ask=ask)


def write_books(directory: Path, name: str, rows, key_column: str):
    fields = ["recv_ts", key_column, "best_bid", "best_ask", "mid"]
    with open(directory / name, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


class AsOfTests(unittest.TestCase):
    def setUp(self):
        self.quotes = [quote(10.0, 0.4, 0.42), quote(20.0, 0.5, 0.52)]
        self.stamps = [q.ts for q in self.quotes]

    def test_the_most_recent_earlier_quote_is_used(self):
        self.assertEqual(gl.as_of(self.quotes, self.stamps, 25.0).ts, 20.0)

    def test_a_quote_exactly_at_the_target_counts(self):
        self.assertEqual(gl.as_of(self.quotes, self.stamps, 20.0).ts, 20.0)

    def test_the_future_is_never_used(self):
        # Nach vorne zu schauen waere bequemer und wuerde Preise aus der
        # Zukunft verwenden.
        self.assertIsNone(gl.as_of(self.quotes, self.stamps, 5.0))

    def test_a_stale_partner_is_rejected(self):
        self.assertIsNone(gl.as_of(self.quotes, self.stamps, 200.0,
                                   max_staleness=60.0))

    def test_an_empty_series_yields_nothing(self):
        self.assertIsNone(gl.as_of([], [], 10.0))


class NetEdgeTests(unittest.TestCase):
    def test_a_wide_gap_is_positive_net(self):
        pm = quote(0, 0.30, 0.32)
        kx = quote(0, 0.60, 0.62)
        self.assertGreater(gl.net_edge_cents(pm, kx, "politics", "politics"), 0)

    def test_a_gap_that_only_covers_fees_is_negative(self):
        pm = quote(0, 0.48, 0.49)
        kx = quote(0, 0.51, 0.52)
        self.assertLess(gl.net_edge_cents(pm, kx, "politics", "politics"), 0)

    def test_identical_books_have_no_edge(self):
        same = quote(0, 0.50, 0.51)
        self.assertLess(gl.net_edge_cents(same, same, "politics", "politics"), 0)

    def test_an_edge_is_found_whichever_venue_is_cheap(self):
        cheap_pm = gl.net_edge_cents(quote(0, 0.30, 0.32), quote(0, 0.60, 0.62),
                                     "politics", "politics")
        cheap_kx = gl.net_edge_cents(quote(0, 0.60, 0.62), quote(0, 0.30, 0.32),
                                     "politics", "politics")
        self.assertGreater(cheap_pm, 0)
        self.assertGreater(cheap_kx, 0)
        # Nicht symmetrisch, und das ist richtig: die Gebuehrenkurven der
        # beiden Venues sind verschieden, also kostet dasselbe Geschaeft je
        # nach Richtung unterschiedlich viel.
        self.assertNotAlmostEqual(cheap_pm, cheap_kx, places=4)
        self.assertLess(abs(cheap_pm - cheap_kx), 1.0)

    def test_a_fee_free_category_clears_a_smaller_gap(self):
        pm, kx = quote(0, 0.48, 0.49), quote(0, 0.52, 0.53)
        self.assertGreater(gl.net_edge_cents(pm, kx, "geopolitics", "geopolitics"),
                           gl.net_edge_cents(pm, kx, "politics", "politics"))


class WindowTests(unittest.TestCase):
    def test_a_contiguous_positive_stretch_is_one_window(self):
        windows = gl.find_windows([(1.0, 0.5), (2.0, 0.6), (3.0, 0.4)], "p")
        self.assertEqual(len(windows), 1)
        self.assertEqual(windows[0].seconds, 2.0)
        self.assertEqual(windows[0].observations, 3)

    def test_a_negative_value_closes_the_window(self):
        windows = gl.find_windows([(1.0, 0.5), (2.0, -0.1), (3.0, 0.5)], "p")
        self.assertEqual(len(windows), 2)

    def test_an_all_negative_series_has_no_windows(self):
        self.assertEqual(gl.find_windows([(1.0, -1.0), (2.0, -2.0)], "p"), [])

    def test_a_window_still_open_at_the_end_is_kept(self):
        windows = gl.find_windows([(1.0, -1.0), (2.0, 0.5), (3.0, 0.5)], "p")
        self.assertEqual(len(windows), 1)
        self.assertEqual(windows[0].seconds, 1.0)

    def test_peak_and_mean_are_reported(self):
        windows = gl.find_windows([(1.0, 1.0), (2.0, 3.0)], "p")
        self.assertEqual(windows[0].peak_net_cents, 3.0)
        self.assertEqual(windows[0].mean_net_cents, 2.0)

    def test_a_single_observation_window_has_zero_duration(self):
        windows = gl.find_windows([(5.0, 1.0), (6.0, -1.0)], "p")
        self.assertEqual(windows[0].seconds, 0.0)

    def test_an_empty_series_has_no_windows(self):
        self.assertEqual(gl.find_windows([], "p"), [])


class PairSeriesTests(unittest.TestCase):
    def test_every_kalshi_observation_with_a_fresh_partner_is_priced(self):
        pm = [quote(0.0, 0.30, 0.32), quote(10.0, 0.30, 0.32)]
        kx = [quote(5.0, 0.60, 0.62), quote(15.0, 0.60, 0.62)]
        series = gl.pair_series(pm, kx, "politics", "politics")
        self.assertEqual(len(series), 2)
        self.assertTrue(all(net > 0 for _, net in series))

    def test_observations_without_a_partner_are_dropped(self):
        pm = [quote(1000.0, 0.30, 0.32)]
        kx = [quote(5.0, 0.60, 0.62)]
        self.assertEqual(gl.pair_series(pm, kx, "politics", "politics"), [])

    def test_a_stale_partner_drops_the_observation(self):
        pm = [quote(0.0, 0.30, 0.32)]
        kx = [quote(5000.0, 0.60, 0.62)]
        self.assertEqual(gl.pair_series(pm, kx, "politics", "politics",
                                        max_staleness=60.0), [])


class LoadTests(unittest.TestCase):
    def test_only_the_wanted_keys_are_loaded(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            write_books(directory, "kalshi_stream_books_2026-07-31.csv", [
                {"recv_ts": "2026-07-31T00:00:01.000Z", "market_id": "A",
                 "best_bid": 0.4, "best_ask": 0.42, "mid": 0.41},
                {"recv_ts": "2026-07-31T00:00:02.000Z", "market_id": "B",
                 "best_bid": 0.4, "best_ask": 0.42, "mid": 0.41},
            ], "market_id")
            loaded = gl.load_quotes(directory, "kalshi_stream_books_*.csv",
                                    "market_id", {"A"})
            self.assertEqual(list(loaded), ["A"])

    def test_one_sided_and_crossed_rows_are_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            write_books(directory, "kalshi_stream_books_2026-07-31.csv", [
                {"recv_ts": "2026-07-31T00:00:01.000Z", "market_id": "A",
                 "best_bid": "", "best_ask": 0.42, "mid": ""},
                {"recv_ts": "2026-07-31T00:00:02.000Z", "market_id": "A",
                 "best_bid": 0.6, "best_ask": 0.4, "mid": 0.5},
            ], "market_id")
            self.assertEqual(gl.load_quotes(directory, "kalshi_stream_books_*.csv",
                                            "market_id", {"A"}), {})

    def test_quotes_come_back_time_sorted(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            write_books(directory, "kalshi_stream_books_2026-07-31.csv", [
                {"recv_ts": "2026-07-31T00:00:09.000Z", "market_id": "A",
                 "best_bid": 0.4, "best_ask": 0.42, "mid": 0.41},
                {"recv_ts": "2026-07-31T00:00:01.000Z", "market_id": "A",
                 "best_bid": 0.4, "best_ask": 0.42, "mid": 0.41},
            ], "market_id")
            quotes = gl.load_quotes(directory, "kalshi_stream_books_*.csv",
                                    "market_id", {"A"})["A"]
            self.assertLess(quotes[0].ts, quotes[1].ts)


class EndToEndTests(unittest.TestCase):
    def _setup(self, tmp: Path, pm_rows, kx_rows):
        data = tmp / "data"
        data.mkdir()
        write_books(data, "stream_books_2026-07-31.csv", pm_rows, "token_id")
        write_books(data, "kalshi_stream_books_2026-07-31.csv", kx_rows, "market_id")
        wl = tmp / "wl.json"
        wl.write_text(json.dumps({"paare": [
            {"kalshi_ticker": "KXA", "polymarket_token_ids": ["t1"],
             "question": "Eine Frage"}]}), encoding="utf-8")
        return data, wl

    def test_an_open_window_is_found_and_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pm = [{"recv_ts": f"2026-07-31T00:00:0{i}.000Z", "token_id": "t1",
                   "best_bid": 0.30, "best_ask": 0.32, "mid": 0.31}
                  for i in range(1, 4)]
            kx = [{"recv_ts": f"2026-07-31T00:00:0{i}.000Z", "market_id": "KXA",
                   "best_bid": 0.60, "best_ask": 0.62, "mid": 0.61}
                  for i in range(1, 4)]
            data, wl = self._setup(root, pm, kx)
            results = gl.run_study(data, watchlist_path=wl)
            row = results["rows"][0]
            self.assertEqual(row["windows"], 1)
            self.assertGreater(row["peak_net_cents"], 0)
            self.assertEqual(row["open_share"], 1.0)

    def test_a_pair_without_both_sides_is_reported_as_such(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            kx = [{"recv_ts": "2026-07-31T00:00:01.000Z", "market_id": "KXA",
                   "best_bid": 0.60, "best_ask": 0.62, "mid": 0.61}]
            data, wl = self._setup(root, [], kx)
            results = gl.run_study(data, watchlist_path=wl)
            self.assertEqual(results["rows"][0]["observations"], 0)
            self.assertIn("nicht aufgezeichnet", results["rows"][0]["reason"])

    def test_reports_are_written_without_the_eszett(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pm = [{"recv_ts": "2026-07-31T00:00:01.000Z", "token_id": "t1",
                   "best_bid": 0.30, "best_ask": 0.32, "mid": 0.31}]
            kx = [{"recv_ts": "2026-07-31T00:00:02.000Z", "market_id": "KXA",
                   "best_bid": 0.60, "best_ask": 0.62, "mid": 0.61}]
            data, wl = self._setup(root, pm, kx)
            results = gl.run_study(data, watchlist_path=wl)
            paths = gl.write_outputs(results, "test", research_dir=root / "r")
            body = paths["md"].read_text(encoding="utf-8")
            self.assertIn("Lebensdauer", body)
            self.assertNotIn("ß", body)
            self.assertTrue(paths["csv"].exists())


if __name__ == "__main__":
    unittest.main()
