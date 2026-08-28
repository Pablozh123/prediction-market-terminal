"""Flag log of the risk screen (app/risk_log.py): append, dedupe, read back, price after."""

from __future__ import annotations

import json
import os
import stat
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from app import risk_log


def _event(**overrides):
    base = {
        "kind": "WALLET CONCENTRATION", "score": 66, "sev": "medium",
        "market": "Rate hike in September?", "market_key": "0xc1", "venue": "Polymarket",
        "url": "https://polymarket.com/event/fed-september", "category": "Politics & geopolitics",
        "flags": ["wallet concentration", "one-sided flow"],
        "side": "NO buys", "side_notional": 20000.0, "side_share": 0.87,
        "side_split": {"buy_yes": 2000.0, "buy_no": 20000.0, "sell_yes": 1000.0, "sell_no": 0.0},
        "price_outcome": "NO", "price_last": 0.34, "price_min": 0.30, "price_max": 0.34,
        "notional_usd": 23000.0, "wallets": 3, "prints": 4,
        "top_wallets": [{"wallet": "0xbbb2", "short": "0xbbb2", "notional": 17000.0, "share": 0.74, "side": "NO buys", "fresh": True, "url": ""}],
        "components": [{"key": "component_notional", "label": "notional", "value": 5.8, "max": 15.0}],
        "first_print": "2026-08-16T12:00:00Z", "last_print": "2026-08-16T12:25:00Z", "window_minutes": 25.0,
        "token_id": "tokNO",
    }
    base.update(overrides)
    return base


class FlagRowTests(unittest.TestCase):
    def test_flag_id_is_stable_over_venue_market_side_day(self) -> None:
        a = risk_log.flag_id("Polymarket", "0xc1", "NO buys", "2026-08-16")
        b = risk_log.flag_id("polymarket", " 0xc1 ", "no buys", "2026-08-16")
        c = risk_log.flag_id("Polymarket", "0xc1", "YES buys", "2026-08-16")
        d = risk_log.flag_id("Polymarket", "0xc1", "NO buys", "2026-08-17")
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)
        self.assertNotEqual(a, d)
        self.assertEqual(len(a), 16)

    def test_flag_row_carries_the_review_fields(self) -> None:
        row = risk_log.flag_row(_event(), "2026-08-16T13:00:00Z")
        self.assertEqual(row["first_seen"], "2026-08-16T13:00:00Z")
        self.assertEqual(row["last_seen"], "2026-08-16T13:00:00Z")
        self.assertEqual(row["flag_id"], risk_log.flag_id("Polymarket", "0xc1", "NO buys", "2026-08-16"))
        for key in ("venue", "market_key", "title", "url", "category", "side", "price_at_flag", "notional",
                    "unique_wallets", "top_wallets", "score", "sev", "components", "window_start", "window_end"):
            self.assertIn(key, row, key)
        self.assertEqual(row["title"], "Rate hike in September?")
        self.assertAlmostEqual(row["price_at_flag"], 0.34)
        self.assertAlmostEqual(row["notional"], 23000.0)
        self.assertEqual(row["unique_wallets"], 3)
        self.assertEqual(row["window_start"], "2026-08-16T12:00:00Z")
        self.assertEqual(row["window_end"], "2026-08-16T12:25:00Z")
        self.assertEqual(row["token_id"], "tokNO")
        self.assertEqual(row["times_seen"], 1)


class RecordAndReadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "sub" / "flags.jsonl"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_records_creates_dir_and_appends_one_row_per_flagged_event(self) -> None:
        events = [_event(), _event(market="Other question", market_key="0xc2", side="YES buys", score=71, sev="high")]
        result = risk_log.record_flags(events, "2026-08-16T13:00:00Z", path=self.path)
        self.assertEqual(result["written"], 2)
        self.assertEqual(result["updated"], 0)
        self.assertIsNone(result["error"])
        self.assertTrue(self.path.exists())
        lines = self.path.read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(lines), 2)
        first = json.loads(lines[0])
        self.assertEqual(first["title"], "Rate hike in September?")

    def test_low_scores_are_skipped_by_the_min_score(self) -> None:
        events = [_event(score=39), _event(score=40, market_key="0xc3")]
        result = risk_log.record_flags(events, "2026-08-16T13:00:00Z", path=self.path, min_score_value=40.0)
        self.assertEqual(result["written"], 1)
        self.assertEqual(result["skipped"], 1)
        rows = risk_log.read_flags(path=self.path)
        self.assertEqual([r["market_key"] for r in rows], ["0xc3"])

    def test_same_flag_within_six_hours_updates_instead_of_duplicating(self) -> None:
        risk_log.record_flags([_event(score=60)], "2026-08-16T13:00:00Z", path=self.path)
        result = risk_log.record_flags([_event(score=72, sev="high", price_last=0.36)], "2026-08-16T15:00:00Z", path=self.path)
        self.assertEqual(result["written"], 0)
        self.assertEqual(result["updated"], 1)
        rows = risk_log.read_flags(path=self.path)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["first_seen"], "2026-08-16T13:00:00Z")
        self.assertEqual(row["last_seen"], "2026-08-16T15:00:00Z")
        self.assertEqual(row["times_seen"], 2)
        # The stronger reading wins, with its price.
        self.assertEqual(row["score"], 72)
        self.assertEqual(row["sev"], "high")
        self.assertAlmostEqual(row["price_at_flag"], 0.36)
        # A weaker later reading keeps the stronger score but bumps last_seen.
        risk_log.record_flags([_event(score=50)], "2026-08-16T16:00:00Z", path=self.path)
        row = risk_log.read_flags(path=self.path)[0]
        self.assertEqual(row["score"], 72)
        self.assertEqual(row["last_seen"], "2026-08-16T16:00:00Z")
        self.assertEqual(row["times_seen"], 3)

    def test_same_flag_after_the_dedupe_window_is_a_new_row(self) -> None:
        risk_log.record_flags([_event()], "2026-08-16T02:00:00Z", path=self.path)
        result = risk_log.record_flags([_event()], "2026-08-16T09:00:00Z", path=self.path)
        self.assertEqual(result["written"], 1)
        self.assertEqual(len(risk_log.read_flags(path=self.path)), 2)

    def test_different_side_or_day_is_a_different_flag(self) -> None:
        risk_log.record_flags([_event()], "2026-08-16T13:00:00Z", path=self.path)
        risk_log.record_flags([_event(side="YES buys")], "2026-08-16T13:05:00Z", path=self.path)
        risk_log.record_flags([_event()], "2026-08-17T00:30:00Z", path=self.path)
        rows = risk_log.read_flags(path=self.path)
        self.assertEqual(len(rows), 3)
        self.assertEqual(len({r["flag_id"] for r in rows}), 3)

    def test_read_flags_newest_first_with_limit_and_since(self) -> None:
        for hour, key in ((10, "0xa"), (12, "0xb"), (14, "0xc")):
            risk_log.record_flags([_event(market_key=key)], f"2026-08-16T{hour:02d}:00:00Z", path=self.path)
        rows = risk_log.read_flags(path=self.path)
        self.assertEqual([r["market_key"] for r in rows], ["0xc", "0xb", "0xa"])
        self.assertEqual([r["market_key"] for r in risk_log.read_flags(limit=2, path=self.path)], ["0xc", "0xb"])
        self.assertEqual([r["market_key"] for r in risk_log.read_flags(since="2026-08-16T11:00:00Z", path=self.path)], ["0xc", "0xb"])

    def test_read_flags_on_missing_file_is_empty(self) -> None:
        self.assertEqual(risk_log.read_flags(path=self.path), [])

    def test_no_events_writes_nothing(self) -> None:
        result = risk_log.record_flags([], "2026-08-16T13:00:00Z", path=self.path)
        self.assertEqual(result["written"], 0)
        self.assertFalse(self.path.exists())

    def test_env_dir_and_default_dir(self) -> None:
        old = os.environ.get("RISK_LOG_DIR")
        try:
            os.environ["RISK_LOG_DIR"] = self.tmp.name
            self.assertEqual(risk_log.log_path(), Path(self.tmp.name) / "flags.jsonl")
            os.environ["RISK_LOG_DIR"] = "relative/dir"
            self.assertEqual(risk_log.log_dir(), risk_log.ROOT / "relative" / "dir")
            os.environ.pop("RISK_LOG_DIR")
            self.assertEqual(risk_log.log_dir(), risk_log.ROOT / "data" / "risk_flags")
        finally:
            if old is None:
                os.environ.pop("RISK_LOG_DIR", None)
            else:
                os.environ["RISK_LOG_DIR"] = old

    def test_read_only_target_reports_error_instead_of_raising(self) -> None:
        # A file where the directory should be: mkdir fails with an OSError on
        # every platform, which is the shape of "not writable" the code guards.
        blocker = Path(self.tmp.name) / "blocked"
        blocker.write_text("x", encoding="utf-8")
        target = blocker / "flags.jsonl"
        result = risk_log.record_flags([_event()], "2026-08-16T13:00:00Z", path=target)
        self.assertEqual(result["written"], 0)
        self.assertIsNotNone(result["error"])
        if os.name != "nt":
            ro_dir = Path(self.tmp.name) / "ro"
            ro_dir.mkdir()
            os.chmod(ro_dir, stat.S_IRUSR | stat.S_IXUSR)
            try:
                result = risk_log.record_flags([_event()], "2026-08-16T13:00:00Z", path=ro_dir / "flags.jsonl")
                if os.geteuid() != 0:
                    self.assertIsNotNone(result["error"])
            finally:
                os.chmod(ro_dir, stat.S_IRWXU)


class PriceAfterTests(unittest.TestCase):
    def _history(self) -> pd.DataFrame:
        start = pd.Timestamp("2026-08-16T12:00:00Z")
        times = [start + pd.Timedelta(minutes=5 * i) for i in range(0, 12 * 26)]  # 26 h of 5-min points
        prices = [0.34 + 0.0005 * i for i in range(len(times))]
        return pd.DataFrame({"time": times, "price": prices})

    def test_prices_at_the_three_horizons_and_moves_in_cents(self) -> None:
        after = risk_log.price_after(self._history(), "2026-08-16T12:25:00Z", 0.34, now="2026-08-18T00:00:00Z")
        self.assertIsNotNone(after)
        # +30 min -> 12:55 -> index 11 -> 0.3455
        self.assertAlmostEqual(after["30m"]["price"], 0.3455)
        self.assertAlmostEqual(after["30m"]["move_c"], 0.55, delta=0.06)  # rounded to a tenth of a cent
        self.assertAlmostEqual(after["2h"]["price"], 0.34 + 0.0005 * 29)
        self.assertAlmostEqual(after["24h"]["price"], 0.34 + 0.0005 * 293)
        self.assertGreater(after["24h"]["move_c"], after["2h"]["move_c"])

    def test_future_horizon_is_none_not_a_number(self) -> None:
        after = risk_log.price_after(self._history(), "2026-08-16T12:25:00Z", 0.34, now="2026-08-16T13:00:00Z")
        self.assertIsNotNone(after["30m"])
        self.assertIsNone(after["2h"])
        self.assertIsNone(after["24h"])

    def test_no_history_or_no_points_after_the_flag(self) -> None:
        self.assertIsNone(risk_log.price_after(pd.DataFrame(), "2026-08-16T12:25:00Z", 0.34))
        self.assertIsNone(risk_log.price_after(None, "2026-08-16T12:25:00Z", 0.34))
        self.assertIsNone(risk_log.price_after(self._history(), "not a time", 0.34))
        # History that ends before the flag: every horizon passed without a
        # print. Das ist etwas anderes als "noch nicht faellig" und darf in
        # der Anzeige nicht dieselbe Zelle bekommen.
        early = self._history().head(3)
        after = risk_log.price_after(early, "2026-08-16T13:00:00Z", 0.34, now="2026-08-18T00:00:00Z")
        leer = {"price": None, "move_c": None, "no_print": True}
        self.assertEqual(after, {"30m": leer, "2h": leer, "24h": leer})

    def test_a_passed_horizon_without_a_print_is_not_pending(self) -> None:
        # Ein Flag von gestern in einem Markt, der seither nicht mehr
        # gehandelt hat: die +24-h-Zelle las "not yet", obwohl der Horizont
        # einen Tag vorbei war. Nur ein noch offener Horizont ist None.
        history = self._history()
        after = risk_log.price_after(history, "2026-08-16T12:25:00Z", 0.34, now="2026-08-16T13:00:00Z")
        self.assertIsNone(after["2h"])
        early = history.head(3)
        vorbei = risk_log.price_after(early, "2026-08-16T13:00:00Z", 0.34, now="2026-08-18T00:00:00Z")
        self.assertTrue(vorbei["24h"]["no_print"])
        self.assertIsNone(vorbei["24h"]["price"])

    def test_a_horizon_that_elapsed_before_the_flag_was_written_says_so(self) -> None:
        # Die Horizonte laufen ab dem letzten Print des Flusses, lesbar wird
        # das Flag erst mit dem Sampler-Lauf. Liegt der eine Stunde spaeter,
        # war der +30-min-Punkt schon vorbei, bevor ihn jemand sehen konnte.
        after = risk_log.price_after(
            self._history(), "2026-08-16T12:25:00Z", 0.34,
            now="2026-08-18T00:00:00Z", known_at="2026-08-16T13:25:00Z")
        self.assertTrue(after["30m"]["already_past"])
        self.assertNotIn("already_past", after["2h"])
        self.assertNotIn("already_past", after["24h"])
        # Der gemessene Wert bleibt unveraendert, nur die Einordnung kommt dazu.
        self.assertAlmostEqual(after["30m"]["price"], 0.3455)

    def test_without_known_at_nothing_is_marked(self) -> None:
        after = risk_log.price_after(self._history(), "2026-08-16T12:25:00Z", 0.34, now="2026-08-18T00:00:00Z")
        for label in ("30m", "2h", "24h"):
            self.assertNotIn("already_past", after[label])

    def test_missing_flag_price_leaves_move_none(self) -> None:
        after = risk_log.price_after(self._history(), "2026-08-16T12:25:00Z", None, now="2026-08-18T00:00:00Z")
        self.assertIsNotNone(after["30m"]["price"])
        self.assertIsNone(after["30m"]["move_c"])


class FlagScoreboardTests(unittest.TestCase):
    """Die Quote ueber die gemessenen Flags, mit n, CI, Badge und Stand."""

    def _rows(self, moves, venue="Polymarket"):
        return [
            {"flag_id": f"f{i}", "venue": venue,
             "after": {"30m": {"price": 0.5, "move_c": m} if m is not None else None, "2h": None, "24h": None}}
            for i, m in enumerate(moves)
        ]

    def test_hits_ties_and_interval(self):
        board = risk_log.flag_scoreboard(self._rows([3.0, 1.5, -2.0, 0.0, None]), as_of="2026-08-28T10:00:00Z")
        h = board["horizons"]["30m"]
        self.assertEqual(h["n"], 4)          # vier gemessene, eine ohne Kurs
        self.assertEqual(h["ties"], 1)       # eine Bewegung von genau null
        self.assertEqual(h["n_decisive"], 3)
        self.assertEqual(h["hits"], 2)
        self.assertAlmostEqual(h["hit_rate"], 2 / 3, places=4)
        self.assertLess(h["ci95"][0], h["hit_rate"])
        self.assertGreater(h["ci95"][1], h["hit_rate"])
        self.assertAlmostEqual(h["avg_move_c"], round((3.0 + 1.5 - 2.0 + 0.0) / 4, 2), places=6)
        self.assertEqual(board["as_of"], "2026-08-28T10:00:00Z")

    def test_small_sample_is_labelled_not_stated_as_a_verdict(self):
        board = risk_log.flag_scoreboard(self._rows([1.0, 2.0, 3.0]))
        self.assertEqual(board["horizons"]["30m"]["sample"]["quality"], "insufficient")
        self.assertFalse(board["horizons"]["30m"]["sample"]["verdict_allowed"])
        big = risk_log.flag_scoreboard(self._rows([1.0] * 30))
        self.assertEqual(big["horizons"]["30m"]["sample"]["quality"], "adequate")
        self.assertTrue(big["horizons"]["30m"]["sample"]["verdict_allowed"])

    def test_denominators_and_multiplicity_travel_with_the_ratio(self):
        rows = self._rows([1.0, None]) + self._rows([None], venue="Kalshi")
        board = risk_log.flag_scoreboard(rows, enrich_max=30)
        self.assertEqual(board["flags_total"], 3)
        self.assertEqual(board["flags_measured"], 1)
        self.assertEqual(board["flags_by_venue"], {"Polymarket": 2, "Kalshi": 1})
        self.assertIn("only the newest 30 flags", board["basis"])
        self.assertIn("many comparisons", board["multiplicity"])

    def test_nothing_measured_yields_no_number(self):
        board = risk_log.flag_scoreboard([])
        self.assertEqual(board["flags_total"], 0)
        for label in risk_log.HORIZONS:
            self.assertIsNone(board["horizons"][label]["hit_rate"])
            self.assertIsNone(board["horizons"][label]["ci95"])


if __name__ == "__main__":
    unittest.main()
