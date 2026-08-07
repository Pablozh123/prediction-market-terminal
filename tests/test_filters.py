"""Tests for app/filters.py — the dataframe filters behind every screen.

Two properties matter more than any individual threshold. A filter must never
raise on a frame that is missing the column it filters on, because the two
venues do not deliver the same columns and a missing one has to mean "cannot
narrow" rather than "crash". And an unrecognised preset must leave the frame
alone rather than silently emptying it, because an empty table reads as a
measured result.
"""

from __future__ import annotations

import unittest

import pandas as pd

from app import filters as flt


def markets() -> pd.DataFrame:
    return pd.DataFrame([
        {"title": "Fed cuts rates", "category": "Macro", "yes_price": 0.62,
         "spread": 0.02, "market_age_days": 5.0, "volume_24h": 250_000.0,
         "end_time": "2099-01-01T00:00:00Z", "change_1d": 0.04},
        {"title": "Bitcoin above 150k", "category": "Crypto", "yes_price": 0.11,
         "spread": 0.09, "market_age_days": 400.0, "volume_24h": 900.0,
         "end_time": "2000-01-01T00:00:00Z", "change_1d": -0.002},
    ])


class FilterTextTests(unittest.TestCase):
    def test_matches_across_the_searchable_columns(self) -> None:
        self.assertEqual(len(flt.filter_text(markets(), "bitcoin")), 1)
        self.assertEqual(len(flt.filter_text(markets(), "macro")), 1)

    def test_is_case_insensitive_and_ignores_padding(self) -> None:
        self.assertEqual(len(flt.filter_text(markets(), "  FED  ")), 1)

    def test_regex_characters_are_taken_literally(self) -> None:
        # A user typing "150k?" must not be interpreted as a pattern.
        self.assertEqual(len(flt.filter_text(markets(), "150k?")), 0)

    def test_empty_query_and_empty_frame_pass_through(self) -> None:
        self.assertEqual(len(flt.filter_text(markets(), "")), 2)
        self.assertEqual(len(flt.filter_text(markets(), "   ")), 2)
        self.assertTrue(flt.filter_text(pd.DataFrame(), "fed").empty)

    def test_a_frame_without_searchable_columns_is_returned_whole(self) -> None:
        frame = pd.DataFrame([{"x": 1}, {"x": 2}])
        self.assertEqual(len(flt.filter_text(frame, "anything")), 2)


class CopyOrderStatusBucketTests(unittest.TestCase):
    def test_seeding_collapses_into_baseline(self) -> None:
        self.assertEqual(flt.copy_order_status_bucket("seed_observed"), "baseline")
        self.assertEqual(flt.copy_order_status_bucket("copied", "initial_baseline"), "baseline")

    def test_known_statuses_pass_through(self) -> None:
        for status in flt.COPY_ORDER_STATUS_FILTERS:
            with self.subTest(status=status):
                self.assertEqual(flt.copy_order_status_bucket(status), status)

    def test_unknown_and_missing(self) -> None:
        self.assertEqual(flt.copy_order_status_bucket("something_else"), "something_else")
        self.assertEqual(flt.copy_order_status_bucket(None), "-")


class NumericColTests(unittest.TestCase):
    def test_missing_column_yields_the_default_not_an_error(self) -> None:
        series = flt.numeric_col(markets(), "does_not_exist", default=7.0)
        self.assertEqual(list(series), [7.0, 7.0])

    def test_unparseable_values_fall_back_to_the_default(self) -> None:
        frame = pd.DataFrame([{"v": "abc"}, {"v": "2.5"}])
        self.assertEqual(list(flt.numeric_col(frame, "v", default=0.0)), [0.0, 2.5])


class BoolMaskTests(unittest.TestCase):
    def test_missing_values_take_the_default(self) -> None:
        mask = flt.bool_mask(pd.Series([True, None, False]), default=False)
        self.assertEqual(list(mask), [True, False, False])

    def test_scalar_expands_over_the_index(self) -> None:
        index = pd.Index([0, 1, 2])
        self.assertEqual(list(flt.bool_mask(True, index=index)), [True, True, True])


class ThresholdFilterTests(unittest.TestCase):
    def test_option_metric_presets_and_custom(self) -> None:
        self.assertEqual(len(flt.option_metric_filter(markets(), "volume_24h", ">$100k")), 1)
        self.assertEqual(len(flt.option_metric_filter(markets(), "volume_24h", "Custom", 500.0)), 2)

    def test_probability_band(self) -> None:
        self.assertEqual(len(flt.apply_probability_filter(markets(), "20-80%", (0, 100))), 1)
        self.assertEqual(len(flt.apply_probability_filter(markets(), "Custom", (10.0, 20.0))), 1)

    def test_spread_uses_a_pessimistic_default_for_missing_values(self) -> None:
        # A market with no spread must not pass a "tight spread" filter.
        frame = pd.DataFrame([{"spread": None}, {"spread": 0.01}])
        self.assertEqual(len(flt.apply_spread_filter(frame, "<3c", 0)), 1)

    def test_end_date_open_and_past_due(self) -> None:
        self.assertEqual(len(flt.apply_end_date_filter(markets(), "Open", 0)), 1)
        self.assertEqual(len(flt.apply_end_date_filter(markets(), "Past due", 0)), 1)

    def test_market_age(self) -> None:
        self.assertEqual(len(flt.apply_market_age_filter(markets(), "<7d", 0)), 1)
        self.assertEqual(len(flt.apply_market_age_filter(markets(), ">365d", 0)), 1)

    def test_price_delta_is_measured_on_the_absolute_move(self) -> None:
        self.assertEqual(len(flt.apply_price_delta_filter(markets(), "change_1d", ">3c", 0)), 1)


class RobustnessTests(unittest.TestCase):
    """A missing column means "cannot narrow", never an exception."""

    FILTER_CALLS = [
        (flt.option_metric_filter, ("volume_24h", ">$100k")),
        (flt.apply_probability_filter, ("20-80%", (0, 100))),
        (flt.apply_spread_filter, ("<3c", 0)),
        (flt.apply_end_date_filter, ("<7d", 0)),
        (flt.apply_market_age_filter, ("<7d", 0)),
        (flt.apply_percent_delta_filter, ("nope", ">25%", 0)),
        (flt.apply_price_delta_filter, ("nope", ">3c", 0)),
    ]

    def test_column_absent_returns_the_frame_untouched(self) -> None:
        frame = pd.DataFrame([{"unrelated": 1}, {"unrelated": 2}])
        for fn, args in self.FILTER_CALLS:
            with self.subTest(fn=fn.__name__):
                self.assertEqual(len(fn(frame, *args)), 2)

    def test_empty_frame_stays_empty_without_raising(self) -> None:
        for fn, args in self.FILTER_CALLS:
            with self.subTest(fn=fn.__name__):
                self.assertTrue(fn(pd.DataFrame(), *args).empty)

    def test_an_unknown_preset_does_not_empty_the_table(self) -> None:
        # Silently returning nothing would read as "no market qualifies".
        self.assertEqual(len(flt.option_metric_filter(markets(), "volume_24h", ">$3.50")), 2)
        self.assertEqual(len(flt.apply_spread_filter(markets(), "<0.5c", 0)), 2)
        self.assertEqual(len(flt.apply_percent_delta_filter(markets(), "change_1d", ">9000%", 0)), 2)

    def test_all_is_a_pass_through(self) -> None:
        for fn, args in self.FILTER_CALLS:
            preset_args = tuple("All" if a in (">$100k", "20-80%", "<3c", "<7d", ">25%", ">3c") else a for a in args)
            with self.subTest(fn=fn.__name__):
                self.assertEqual(len(fn(markets(), *preset_args)), 2)


if __name__ == "__main__":
    unittest.main()
