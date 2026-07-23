import json
import unittest

import pandas as pd

from app import base_rate_study as brs


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


if __name__ == "__main__":
    unittest.main()
