import importlib.util
import json
import random
import sqlite3
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from app import base_rate_study as brs

REPO_ROOT = Path(__file__).resolve().parents[1]


def market(question: str, no_won: bool, *, closed: bool = True,
           no_price: str | None = None, end: str = "2026-06-23T23:00:00Z") -> dict:
    settled = no_price if no_price is not None else ("1" if no_won else "0")
    yes = "0" if settled == "1" else "1"
    return {
        "conditionId": f"0x{abs(hash(question)):x}"[:12],
        "question": question,
        "closed": closed,
        "endDate": end,
        "outcomes": json.dumps(["Yes", "No"]),
        "clobTokenIds": json.dumps([f"tok-yes-{question}", f"tok-no-{question}"]),
        "outcomePrices": json.dumps([yes, settled]),
    }


class EventParsingTests(unittest.TestCase):
    def test_event_lines_reads_the_no_side_and_its_result(self) -> None:
        event = {"slug": "match-exact-score", "markets": [
            market("Exact Score: A 0 - 0 B?", no_won=True),
            market("Exact Score: A 1 - 0 B?", no_won=False),
        ]}
        lines = brs.event_lines(event)
        self.assertEqual(len(lines), 2)
        self.assertEqual(list(lines["outcome"].unique()), ["No"])
        self.assertEqual(list(lines["won"]), [True, False])
        self.assertTrue(all(t.startswith("tok-no-") for t in lines["token_id"]))

    def test_unresolved_and_open_markets_are_dropped(self) -> None:
        event = {"slug": "s", "markets": [
            market("Exact Score: A 0 - 0 B?", no_won=True, closed=False),
            market("Exact Score: A 1 - 1 B?", no_won=True, no_price="0.63"),  # still trading
            market("Exact Score: A 2 - 0 B?", no_won=True),
        ]}
        self.assertEqual(len(brs.event_lines(event)), 1)

    def test_malformed_market_does_not_raise(self) -> None:
        event = {"slug": "s", "markets": [{"closed": True, "outcomes": "not json"}, None]}
        self.assertTrue(brs.event_lines(event).empty)

    def test_event_slug_extraction(self) -> None:
        self.assertEqual(
            brs.event_slug_from_url("https://polymarket.com/event/abc-exact-score"), "abc-exact-score"
        )
        self.assertEqual(brs.event_slug_from_url("nonsense"), "")
        self.assertEqual(
            brs.event_slugs_from_urls([
                "https://polymarket.com/event/a", "https://polymarket.com/event/a", "junk",
            ]),
            ["a"],
        )

    def test_is_exact_score_question(self) -> None:
        self.assertTrue(brs.is_exact_score_question("Exact Score: A 1 - 0 B?"))
        self.assertFalse(brs.is_exact_score_question("Will A win?"))


class LeadTimePriceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.end = pd.Timestamp("2026-06-23T23:00:00Z")
        self.history = pd.DataFrame({
            "time": pd.to_datetime([
                "2026-06-20T23:00:00Z", "2026-06-21T23:00:00Z", "2026-06-22T23:00:00Z",
            ]),
            "price": [0.90, 0.92, 0.95],
        })

    def test_takes_the_last_price_before_the_cutoff(self) -> None:
        # A point stamped exactly at the cutoff was available at the cutoff.
        self.assertAlmostEqual(brs.price_at_lead_time(self.history, self.end, 24), 0.95)
        self.assertAlmostEqual(brs.price_at_lead_time(self.history, self.end, 48), 0.92)
        self.assertAlmostEqual(brs.price_at_lead_time(self.history, self.end, 72), 0.90)

    def test_ignores_prices_after_the_cutoff(self) -> None:
        late = pd.concat([self.history, pd.DataFrame({
            "time": pd.to_datetime(["2026-06-23T22:00:00Z"]), "price": [0.99],
        })], ignore_index=True)
        self.assertAlmostEqual(brs.price_at_lead_time(late, self.end, 48), 0.92)

    def test_returns_none_when_history_is_too_short(self) -> None:
        """A missing price must stay missing: defaulting it would invent data."""
        self.assertIsNone(brs.price_at_lead_time(self.history, self.end, 24 * 10))
        self.assertIsNone(brs.price_at_lead_time(pd.DataFrame(), self.end, 24))


class BaseRateTableTests(unittest.TestCase):
    def _obs(self, rows: list[tuple[float, bool]]) -> pd.DataFrame:
        return pd.DataFrame([
            {"market_key": f"m{i}", "price": p, "won": w} for i, (p, w) in enumerate(rows)
        ])

    def test_fair_band_shows_no_significant_gap(self) -> None:
        rows = [(0.90, True)] * 90 + [(0.90, False)] * 10
        table = brs.base_rate_table(self._obs(rows), buckets=(0.8, 0.95))
        self.assertAlmostEqual(table.iloc[0]["realised"], 0.90)
        self.assertAlmostEqual(table.iloc[0]["gap_pp"], 0.0, places=6)
        self.assertFalse(bool(table.iloc[0]["significant"]))

    def test_cheap_band_is_flagged_significant(self) -> None:
        rows = [(0.85, True)] * 980 + [(0.85, False)] * 20
        table = brs.base_rate_table(self._obs(rows), buckets=(0.8, 0.95))
        self.assertGreater(table.iloc[0]["gap_pp"], 10.0)
        self.assertTrue(bool(table.iloc[0]["significant"]))

    def test_empty_input_returns_empty_table(self) -> None:
        self.assertTrue(brs.base_rate_table(pd.DataFrame()).empty)

    def test_rows_without_a_price_are_excluded(self) -> None:
        frame = pd.DataFrame([
            {"market_key": "a", "price": 0.9, "won": True},
            {"market_key": "b", "price": None, "won": False},
        ])
        table = brs.base_rate_table(frame, buckets=(0.8, 0.95))
        self.assertEqual(int(table.iloc[0]["n"]), 1)


class MultipleComparisonTests(unittest.TestCase):
    """Five buckets tested at 95 percent each are five chances to be wrong.
    On a universe priced exactly right, at least one band read "significant"
    in 22 percent of runs."""

    def _fair_universe(self, rng: random.Random) -> pd.DataFrame:
        rows = []
        for event in range(12):
            for line in range(17):
                price = rng.choice([0.30, 0.62, 0.84, 0.92, 0.965])
                rows.append({"event_slug": f"e{event}", "market_key": f"m{event}-{line}",
                             "price": price, "won": rng.random() < price})
        return pd.DataFrame(rows)

    def test_family_wise_error_stays_near_the_nominal_level(self) -> None:
        rng = random.Random(3)
        treffer = sum(
            bool(brs.base_rate_table(self._fair_universe(rng))["significant"].any())
            for _ in range(120)
        )
        self.assertLessEqual(treffer / 120, 0.10)

    def test_the_family_size_is_reported(self) -> None:
        table = brs.base_rate_table(self._fair_universe(random.Random(1)))
        self.assertEqual(int(table.iloc[0]["family"]), len(table))

    def test_the_adjusted_interval_is_the_wider_one(self) -> None:
        rows = [{"event_slug": f"e{i}", "market_key": f"m{i}",
                 "price": (0.35, 0.85, 0.92)[i % 3], "won": i % 7 != 0}
                for i in range(120)]
        table = brs.base_rate_table(pd.DataFrame(rows))
        self.assertEqual(int(table.iloc[0]["family"]), 3)
        for _, row in table.iterrows():
            self.assertLess(row["ci_low_adj"], row["ci_low"])
            self.assertGreater(row["ci_high_adj"], row["ci_high"])

    def test_a_single_bucket_is_not_penalised(self) -> None:
        rows = [{"event_slug": f"e{i}", "market_key": f"m{i}", "price": 0.85,
                 "won": i % 7 != 0} for i in range(120)]
        row = brs.base_rate_table(pd.DataFrame(rows)).iloc[0]
        self.assertEqual(int(row["family"]), 1)
        self.assertAlmostEqual(row["ci_low_adj"], row["ci_low"], places=4)

    def test_a_real_mispricing_still_clears_the_wider_interval(self) -> None:
        rng = random.Random(5)
        rows = [{"event_slug": f"e{i // 17}", "market_key": f"m{i}", "price": 0.85,
                 "won": rng.random() < 0.97} for i in range(1020)]
        table = brs.base_rate_table(pd.DataFrame(rows))
        self.assertTrue(bool(table["significant"].any()))


class ClusterUnitTests(unittest.TestCase):
    """One football match contributes about seventeen mutually exclusive lines
    and exactly one draw. n is lines; events is the thing that varied."""

    def test_events_are_counted_next_to_the_lines(self) -> None:
        rows = [{"event_slug": "match-1", "market_key": f"m{i}", "price": 0.92,
                 "won": i != 0} for i in range(17)]
        row = brs.base_rate_table(pd.DataFrame(rows)).iloc[0]
        self.assertEqual(int(row["n"]), 17)
        self.assertEqual(int(row["markets"]), 17)
        self.assertEqual(int(row["events"]), 1)

    def test_a_single_event_is_never_significant(self) -> None:
        """Seventeen lines of one match cannot carry a finding about a band."""
        rows = [{"event_slug": "match-1", "market_key": f"m{i}", "price": 0.50,
                 "won": True} for i in range(17)]
        self.assertFalse(bool(brs.base_rate_table(pd.DataFrame(rows))["significant"].any()))

    def test_without_event_slugs_events_falls_back_to_the_line_count(self) -> None:
        rows = [{"market_key": f"m{i}", "price": 0.9, "won": True} for i in range(10)]
        self.assertEqual(int(brs.base_rate_table(pd.DataFrame(rows)).iloc[0]["events"]), 10)


class SelectionGapTests(unittest.TestCase):
    """The picked lines against the ones left alone: two disjoint halves, so
    the difference can carry an interval."""

    def _universe(self, picked_rate: float, rest_rate: float, seed: int = 5) -> pd.DataFrame:
        rng = random.Random(seed)
        rows = []
        for i in range(400):
            gewaehlt = i % 4 == 0
            rows.append({"event_slug": f"e{i // 17}", "token_id": f"t{i}", "price": 0.85,
                         "won": rng.random() < (picked_rate if gewaehlt else rest_rate)})
        return pd.DataFrame(rows)

    def _picked(self, universe: pd.DataFrame) -> list[str]:
        return [t for i, t in enumerate(universe["token_id"]) if i % 4 == 0]

    def test_a_real_picking_edge_is_separable(self) -> None:
        universe = self._universe(0.97, 0.85)
        out = brs.selection_gap(universe, self._picked(universe))
        self.assertEqual(out["n_picked"], 100)
        self.assertEqual(out["n_rest"], 300)
        self.assertGreater(out["selection_pp"], 0.0)
        self.assertGreater(out["ci_low"], 0.0)
        self.assertTrue(out["separable"])

    def test_no_picking_edge_leaves_the_interval_across_zero(self) -> None:
        universe = self._universe(0.85, 0.85, seed=11)
        out = brs.selection_gap(universe, self._picked(universe))
        self.assertLessEqual(out["ci_low"], 0.0)
        self.assertGreaterEqual(out["ci_high"], 0.0)
        self.assertFalse(out["separable"])

    def test_an_empty_half_yields_no_comparison(self) -> None:
        universe = self._universe(0.9, 0.9)
        out = brs.selection_gap(universe, [])
        self.assertEqual(out["n_picked"], 0)
        self.assertIsNone(out["selection_pp"])

    def test_missing_key_column_is_handled(self) -> None:
        self.assertIsNone(brs.selection_gap(pd.DataFrame(), [])["selection_pp"])


class ConvictionSplitTests(unittest.TestCase):
    def _frame(self, rows: list[tuple[float, bool, float]]) -> pd.DataFrame:
        return pd.DataFrame([
            {"market_key": f"m{i}", "price": p, "won": w, "stake": s}
            for i, (p, w, s) in enumerate(rows)
        ])

    def test_big_bets_are_scored_separately(self) -> None:
        """A sizing edge is invisible line-weighted, so the halves must split on stake."""
        small = [(0.90, i % 10 != 0, 5.0) for i in range(40)]  # 90% hit, fair
        big = [(0.90, True, 5000.0) for _ in range(10)]  # 100% hit, cheap
        split = brs.conviction_split(self._frame(small + big), quantile=0.8)
        halves = split.set_index("half")
        self.assertAlmostEqual(halves.loc["big", "realised"], 1.0)
        self.assertGreater(halves.loc["big", "gap_pp"], halves.loc["small", "gap_pp"])

    def test_each_half_carries_its_interval(self) -> None:
        """Two gap numbers without intervals invite a sizing story out of ten
        lines, which is the mistake this module exists to catch one level up."""
        small = [(0.90, i % 10 != 0, 5.0) for i in range(40)]
        big = [(0.90, True, 5000.0) for _ in range(10)]
        halves = brs.conviction_split(self._frame(small + big), quantile=0.8).set_index("half")
        self.assertLess(halves.loc["big", "ci_low"], halves.loc["big", "realised"])
        self.assertLessEqual(halves.loc["big", "ci_high"], 1.0)
        # Zehn Linien schliessen den fairen Preis nicht aus.
        self.assertLess(halves.loc["big", "ci_low"], 0.90)
        self.assertEqual(int(halves.loc["big", "events"]), 10)

    def test_missing_stake_column_returns_empty(self) -> None:
        frame = pd.DataFrame([{"market_key": "a", "price": 0.9, "won": True}])
        self.assertTrue(brs.conviction_split(frame).empty)

    def test_empty_input_returns_empty(self) -> None:
        self.assertTrue(brs.conviction_split(pd.DataFrame()).empty)


class SelectionComparisonTests(unittest.TestCase):
    def test_selection_column_isolates_the_wallet_effect(self) -> None:
        universe = pd.DataFrame([{"bucket": "(0.8, 0.95]", "n": 500, "gap_pp": 1.0}])
        wallet = pd.DataFrame([{"bucket": "(0.8, 0.95]", "n": 50, "gap_pp": 6.0}])
        out = brs.compare_to_wallet(universe, wallet)
        self.assertAlmostEqual(out.iloc[0]["selection_pp"], 5.0)
        self.assertAlmostEqual(out.iloc[0]["universe_gap_pp"], 1.0)

    def test_empty_inputs_are_handled(self) -> None:
        self.assertTrue(brs.compare_to_wallet(pd.DataFrame(), pd.DataFrame()).empty)


def load_run_script():
    script = REPO_ROOT / "scripts" / "run_base_rate_study.py"
    spec = importlib.util.spec_from_file_location("run_base_rate_study_under_test", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class EventSlugsFromCopyDbTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = load_run_script()

    @staticmethod
    def _seed_db(db_path: Path, blobs: list) -> None:
        conn = sqlite3.connect(db_path)
        try:
            conn.execute(
                """CREATE TABLE paper_orders (
                    source_wallet TEXT, title TEXT, source_json TEXT
                )"""
            )
            for blob in blobs:
                conn.execute(
                    "INSERT INTO paper_orders VALUES (?, 'Exact Score: A 0 - 0 B', ?)",
                    ("0xwallet", blob),
                )
            conn.commit()
        finally:
            conn.close()

    def test_a_row_whose_json_is_not_an_object_is_skipped_not_fatal(self) -> None:
        # "[]" is valid JSON but has no .get(), unlike a malformed string.
        blobs = [
            "[]",
            json.dumps({"url": "https://polymarket.com/event/match-exact-score"}),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "copy.sqlite"
            self._seed_db(db_path, blobs)
            slugs = self.mod.event_slugs_from_copy_db(db_path, "0xwallet", limit=10)
        self.assertEqual(slugs, ["match-exact-score"])

    def test_malformed_json_string_is_still_skipped(self) -> None:
        blobs = ["not json", json.dumps({"url": "https://polymarket.com/event/still-fine"})]
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "copy.sqlite"
            self._seed_db(db_path, blobs)
            slugs = self.mod.event_slugs_from_copy_db(db_path, "0xwallet", limit=10)
        self.assertEqual(slugs, ["still-fine"])


if __name__ == "__main__":
    unittest.main()
