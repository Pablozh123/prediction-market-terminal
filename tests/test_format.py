"""Tests for app/format.py — the presentation helpers the three consumers share.

These functions decide what a number looks like on screen, so their edge cases
are the ones a reader would notice: a missing value must read as a dash rather
than as zero, and a yield has to refuse to answer when the horizon it would
divide by is gone.
"""

from __future__ import annotations

import unittest

import pandas as pd

from app import format as fmt


class MoneyTests(unittest.TestCase):
    def test_scales_by_magnitude(self) -> None:
        self.assertEqual(fmt.money(999), "$999")
        self.assertEqual(fmt.money(1_500), "$1.5k")
        self.assertEqual(fmt.money(2_400_000), "$2.40m")
        self.assertEqual(fmt.money(3_100_000_000), "$3.10b")

    def test_sign_sits_before_the_currency(self) -> None:
        self.assertEqual(fmt.money(-2_500), "-$2.5k")

    def test_none_and_zero_read_as_zero_dollars(self) -> None:
        self.assertEqual(fmt.money(None), "$0")
        self.assertEqual(fmt.money(0), "$0")

    def test_markdown_escapes_the_dollar(self) -> None:
        # Streamlit markdown treats an unescaped $ as the start of maths.
        self.assertEqual(fmt.markdown_money(1_500), "\\$1.5k")


class MoneyOrDashTests(unittest.TestCase):
    """Nicht gemeldet ist nicht null."""

    def test_a_missing_figure_is_a_dash(self) -> None:
        self.assertEqual(fmt.money_or_dash(None), "-")
        self.assertEqual(fmt.money_or_dash(float("nan")), "-")
        self.assertEqual(fmt.money_or_dash("keine Angabe"), "-")

    def test_a_reported_zero_stays_zero(self) -> None:
        self.assertEqual(fmt.money_or_dash(0), "$0")
        self.assertEqual(fmt.money_or_dash(40_000), "$40.0k")


class ContractsTests(unittest.TestCase):
    """Kalshis Open Interest zaehlt Kontrakte; ein Dollarzeichen davor luegt."""

    def test_counts_are_labelled_as_counts(self) -> None:
        self.assertEqual(fmt.contracts(12_000), "12,000 contracts")
        self.assertEqual(fmt.contracts(0), "0 contracts")

    def test_missing_counts_are_a_dash(self) -> None:
        self.assertEqual(fmt.contracts(None), "-")
        self.assertEqual(fmt.contracts(float("nan")), "-")

    def test_a_count_never_reads_as_money(self) -> None:
        self.assertNotIn("$", fmt.contracts(12_000))


class ShareTests(unittest.TestCase):
    def test_percent_and_cents(self) -> None:
        self.assertEqual(fmt.pct(0.1234), "12.3%")
        self.assertEqual(fmt.cents(0.0258), "2.6c")
        self.assertEqual(fmt.signed_cents(0.0258), "+2.6c")
        self.assertEqual(fmt.signed_cents(-0.0258), "-2.6c")

    def test_missing_reads_as_a_dash_not_as_zero(self) -> None:
        for fn in (fmt.pct, fmt.cents, fmt.signed_cents):
            with self.subTest(fn=fn.__name__):
                self.assertEqual(fn(None), "-")
                self.assertEqual(fn(float("nan")), "-")


class SnapshotLabelTests(unittest.TestCase):
    def test_formats_utc(self) -> None:
        self.assertEqual(fmt.snapshot_label("2026-07-16T18:50:31Z"), "2026-07-16 18:50 UTC")

    def test_unparseable_is_a_dash(self) -> None:
        self.assertEqual(fmt.snapshot_label("not a date"), "-")
        self.assertEqual(fmt.snapshot_label(None), "-")


class ResolutionYieldTests(unittest.TestCase):
    NOW = pd.Timestamp("2026-01-01", tz="UTC")

    def test_picks_the_cheaper_side_and_annualises(self) -> None:
        out = fmt.resolution_yield_summary(0.80, "2026-07-01", now=self.NOW)
        self.assertEqual(out["side"], "Yes")
        self.assertAlmostEqual(out["price"], 0.80)
        self.assertAlmostEqual(out["days_to_end"], 181.0, places=0)
        # (1/0.8 - 1) over 181 days, annualised.
        self.assertAlmostEqual(out["apy"], 0.25 * (365 / out["days_to_end"]), places=6)

    def test_below_a_half_the_no_side_is_the_holding(self) -> None:
        out = fmt.resolution_yield_summary(0.20, "2026-07-01", now=self.NOW)
        self.assertEqual(out["side"], "No")
        self.assertAlmostEqual(out["price"], 0.80)

    def test_no_yield_without_a_horizon_to_divide_by(self) -> None:
        # A market that already ended cannot carry an annualised return.
        out = fmt.resolution_yield_summary(0.80, "2025-01-01", now=self.NOW)
        self.assertIsNone(out["apy"])
        out = fmt.resolution_yield_summary(0.80, None, now=self.NOW)
        self.assertIsNone(out["apy"])

    def test_a_settled_price_carries_no_yield(self) -> None:
        for price in (0.0, 1.0):
            with self.subTest(price=price):
                self.assertIsNone(fmt.resolution_yield_summary(price, "2026-07-01", now=self.NOW)["apy"])

    def test_garbage_price_answers_with_dashes_not_an_exception(self) -> None:
        out = fmt.resolution_yield_summary("n/a", "2026-07-01", now=self.NOW)
        self.assertEqual(out["side"], "-")
        self.assertIsNone(out["price"])


class TitleFamilyKeyTests(unittest.TestCase):
    def test_two_phrasings_of_one_question_share_a_key(self) -> None:
        a = fmt.market_title_family_key("Will the Fed cut rates in September 2026?")
        b = fmt.market_title_family_key("Fed cut rates by September 2026")
        self.assertEqual(a, b)

    def test_months_and_digits_drop_out(self) -> None:
        key = fmt.market_title_family_key("Will Bitcoin hit 150000 in July?")
        self.assertNotIn("july", key)
        self.assertNotIn("150000", key)
        self.assertIn("bitcoin", key)

    def test_empty_input_is_an_empty_key(self) -> None:
        self.assertEqual(fmt.market_title_family_key(None), "")
