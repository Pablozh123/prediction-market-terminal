import json
import tempfile
import unittest
from pathlib import Path

from app import watchlist


def write(directory: Path, payload) -> Path:
    path = directory / "watchlist.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


SAMPLE = {"paare": [
    {"kalshi_ticker": "KXA", "polymarket_token_ids": ["t1", "t2"]},
    {"kalshi_ticker": "KXB", "polymarket_token_ids": ["t3", "t4"]},
]}


class LoadTests(unittest.TestCase):
    def test_a_missing_file_degrades_to_empty(self):
        # Eine fehlende Watchlist darf einen Recorder nicht stoppen.
        self.assertEqual(watchlist.load("C:/gibt/es/nicht.json"), {"paare": []})

    def test_broken_json_degrades_to_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "w.json"
            path.write_text("{kaputt", encoding="utf-8")
            self.assertEqual(watchlist.load(path), {"paare": []})

    def test_wrong_shape_degrades_to_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(watchlist.load(write(Path(tmp), ["Liste"])),
                             {"paare": []})

    def test_a_valid_file_is_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(len(watchlist.load(write(Path(tmp), SAMPLE))["paare"]), 2)


class ExtractionTests(unittest.TestCase):
    def test_kalshi_tickers_are_extracted_in_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(watchlist.kalshi_tickers(write(Path(tmp), SAMPLE)),
                             ["KXA", "KXB"])

    def test_polymarket_tokens_cover_both_outcomes(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(
                watchlist.polymarket_token_ids(write(Path(tmp), SAMPLE)),
                ["t1", "t2", "t3", "t4"])

    def test_duplicates_are_collapsed(self):
        payload = {"paare": [{"kalshi_ticker": "KXA", "polymarket_token_ids": ["t1"]},
                             {"kalshi_ticker": "KXA", "polymarket_token_ids": ["t1"]}]}
        with tempfile.TemporaryDirectory() as tmp:
            path = write(Path(tmp), payload)
            self.assertEqual(watchlist.kalshi_tickers(path), ["KXA"])
            self.assertEqual(watchlist.polymarket_token_ids(path), ["t1"])

    def test_blank_entries_are_skipped(self):
        payload = {"paare": [{"kalshi_ticker": "  ", "polymarket_token_ids": ["", "t1"]}]}
        with tempfile.TemporaryDirectory() as tmp:
            path = write(Path(tmp), payload)
            self.assertEqual(watchlist.kalshi_tickers(path), [])
            self.assertEqual(watchlist.polymarket_token_ids(path), ["t1"])


class MergeTests(unittest.TestCase):
    def test_pinned_entries_come_first(self):
        self.assertEqual(watchlist.merge_pinned(["a"], ["b", "c"], 3),
                         ["a", "b", "c"])

    def test_the_cap_never_drops_a_pinned_entry(self):
        # Genau der Fehler, den ein nachtraegliches Kappen machen wuerde.
        merged = watchlist.merge_pinned(["a", "b"], ["c", "d", "e"], 3)
        self.assertIn("a", merged)
        self.assertIn("b", merged)
        self.assertEqual(len(merged), 3)

    def test_an_entry_in_both_lists_appears_once(self):
        self.assertEqual(watchlist.merge_pinned(["a"], ["a", "b"], 5), ["a", "b"])

    def test_without_pins_the_ranking_is_untouched(self):
        self.assertEqual(watchlist.merge_pinned([], ["a", "b"], 5), ["a", "b"])

    def test_a_zero_limit_yields_nothing(self):
        self.assertEqual(watchlist.merge_pinned(["a"], ["b"], 0), [])


class RealWatchlistTests(unittest.TestCase):
    def test_the_shipped_watchlist_parses_and_pins_both_venues(self):
        if not watchlist.DEFAULT_PATH.exists():
            self.skipTest("keine Watchlist im Arbeitsverzeichnis")
        self.assertTrue(watchlist.kalshi_tickers())
        self.assertTrue(watchlist.polymarket_token_ids())
        # Jedes Paar braucht beide Seiten, sonst ist es nicht vergleichbar.
        for pair in watchlist.load().get("paare", []):
            self.assertTrue(pair.get("kalshi_ticker"), pair)
            self.assertEqual(len(pair.get("polymarket_token_ids") or []), 2, pair)


if __name__ == "__main__":
    unittest.main()
