import unittest

import pandas as pd

from app import filters as flt
from app import format as fmt


class FormatTests(unittest.TestCase):
    def test_money_scales_and_sign(self) -> None:
        self.assertEqual(fmt.money(0), "$0")
        self.assertEqual(fmt.money(950), "$950")
        self.assertEqual(fmt.money(1500), "$1.5k")
        self.assertEqual(fmt.money(1_234_567), "$1.23m")
        self.assertEqual(fmt.money(2_000_000_000), "$2.00b")
        self.assertEqual(fmt.money(-1500), "-$1.5k")

    def test_markdown_money_escapes_dollar(self) -> None:
        self.assertEqual(fmt.markdown_money(1500), "\\$1.5k")

    def test_pct_cents_handle_none_and_nan(self) -> None:
        self.assertEqual(fmt.pct(None), "-")
        self.assertEqual(fmt.pct(float("nan")), "-")
        self.assertEqual(fmt.pct(0.5), "50.0%")
        self.assertEqual(fmt.cents(0.5), "50.0c")
        self.assertEqual(fmt.signed_cents(0.5), "+50.0c")
        self.assertEqual(fmt.signed_cents(-0.5), "-50.0c")

    def test_resolution_yield_summary(self) -> None:
        now = pd.Timestamp("2026-01-01T00:00:00Z")
        end = now + pd.Timedelta(days=365)
        summary = fmt.resolution_yield_summary(0.5, end, now=now)
        self.assertEqual(summary["side"], "Yes")
        self.assertAlmostEqual(summary["price"], 0.5)
        self.assertAlmostEqual(summary["apy"], 1.0)
        self.assertAlmostEqual(summary["days_to_end"], 365.0)

    def test_resolution_yield_summary_picks_cheaper_side(self) -> None:
        now = pd.Timestamp("2026-01-01T00:00:00Z")
        end = now + pd.Timedelta(days=365)
        summary = fmt.resolution_yield_summary(0.8, end, now=now)
        self.assertEqual(summary["side"], "Yes")
        self.assertAlmostEqual(summary["price"], 0.8)
        summary_no = fmt.resolution_yield_summary(0.2, end, now=now)
        self.assertEqual(summary_no["side"], "No")
        self.assertAlmostEqual(summary_no["price"], 0.8)

    def test_resolution_yield_summary_invalid(self) -> None:
        self.assertIsNone(fmt.resolution_yield_summary("nan", "2026-01-01")["apy"])
        self.assertIsNone(fmt.resolution_yield_summary(1.0, "2030-01-01")["apy"])

    def test_market_title_family_key_drops_stopwords_and_digits(self) -> None:
        key = fmt.market_title_family_key("Will the Bitcoin price hit 100000 by December?")
        self.assertNotIn("will", key.split())
        self.assertNotIn("the", key.split())
        self.assertNotIn("100000", key.split())
        self.assertIn("bitcoin", key.split())


class FilterTests(unittest.TestCase):
    def test_numeric_col_missing_and_coerce(self) -> None:
        df = pd.DataFrame({"a": ["1", "x", None]})
        self.assertTrue((flt.numeric_col(df, "missing", 5.0) == 5.0).all())
        self.assertEqual(list(flt.numeric_col(df, "a")), [1.0, 0.0, 0.0])

    def test_bool_mask_handles_missing_and_scalar(self) -> None:
        mask = flt.bool_mask(pd.Series([True, None, 0, 1]), default=False)
        self.assertEqual(list(mask), [True, False, False, True])
        scalar_mask = flt.bool_mask(None, default=True, index=pd.Index([10, 11]))
        self.assertEqual(list(scalar_mask), [True, True])

    def test_copy_order_status_bucket(self) -> None:
        self.assertEqual(flt.copy_order_status_bucket("seed_observed"), "baseline")
        self.assertEqual(flt.copy_order_status_bucket("copied", "initial_baseline"), "baseline")
        self.assertEqual(flt.copy_order_status_bucket("copied"), "copied")
        self.assertEqual(flt.copy_order_status_bucket(""), "-")

    def test_option_metric_filter_thresholds(self) -> None:
        df = pd.DataFrame({"v": [50, 500, 5000, 50000]})
        self.assertEqual(len(flt.option_metric_filter(df, "v", "All")), 4)
        self.assertEqual(list(flt.option_metric_filter(df, "v", ">$1k")["v"]), [5000, 50000])
        self.assertEqual(list(flt.option_metric_filter(df, "v", "Custom", custom_min=100)["v"]), [500, 5000, 50000])

    def test_apply_probability_filter(self) -> None:
        df = pd.DataFrame({"yes_price": [0.02, 0.5, 0.9, 0.97]})
        self.assertEqual(list(flt.apply_probability_filter(df, "5-95%", (5, 95))["yes_price"]), [0.5, 0.9])
        self.assertEqual(list(flt.apply_probability_filter(df, ">95%", (5, 95))["yes_price"]), [0.97])
        self.assertEqual(len(flt.apply_probability_filter(df, "All", (5, 95))), 4)

    def test_apply_end_date_filter_open_and_past(self) -> None:
        now = pd.Timestamp.utcnow()
        df = pd.DataFrame({"end_time": [now - pd.Timedelta(days=1), now + pd.Timedelta(days=2), None]})
        self.assertEqual(len(flt.apply_end_date_filter(df, "Past due", 0)), 1)
        self.assertEqual(len(flt.apply_end_date_filter(df, "Open", 0)), 2)  # future + undated

    def test_apply_account_age_filter(self) -> None:
        df = pd.DataFrame({"account_age_days": [5, 30, 400]})
        self.assertEqual(list(flt.apply_account_age_filter(df, "<14d", 0)["account_age_days"]), [5])
        self.assertEqual(list(flt.apply_account_age_filter(df, ">365d", 0)["account_age_days"]), [400])

    def test_filter_text_matches_across_fields(self) -> None:
        df = pd.DataFrame({"title": ["Bitcoin to 100k", "Election 2026"], "category": ["Crypto", "Politics"]})
        self.assertEqual(list(flt.filter_text(df, "bitcoin")["title"]), ["Bitcoin to 100k"])
        self.assertEqual(list(flt.filter_text(df, "politics")["title"]), ["Election 2026"])
        self.assertEqual(len(flt.filter_text(df, "")), 2)

    def test_add_market_filter_metrics_adds_columns(self) -> None:
        now = pd.Timestamp("2026-01-10T00:00:00Z")
        df = pd.DataFrame(
            [{"title": "BTC up?", "category": "Crypto", "created_at": "2026-01-01T00:00:00Z", "volume_24h": 2400.0, "volume_1h": 200.0}]
        )
        enriched = flt.add_market_filter_metrics(df, now=now)
        self.assertIn("filter_category", enriched.columns)
        self.assertIn("market_age_days", enriched.columns)
        self.assertIn("volume_delta_1h", enriched.columns)
        self.assertAlmostEqual(float(enriched.iloc[0]["market_age_days"]), 9.0)

    def test_apply_copy_trade_order_filters_basic(self) -> None:
        orders = pd.DataFrame(
            [
                {"source_side": "BUY", "status": "copied", "reason": "buy_scaled", "source_notional": 1000.0, "copy_notional": 10.0, "realized_pnl": 1.0},
                {"source_side": "SELL", "status": "skipped", "reason": "skipped_unmatched_sell", "source_notional": 5.0, "copy_notional": 0.0, "realized_pnl": 0.0},
            ]
        )
        out = flt.apply_copy_trade_order_filters(
            orders, query="", sides=["BUY"], statuses=["copied"], min_tony_notional=0.0,
            min_copy_notional=0.0, min_pnl=0.0, reason_query="", latency_only=False, rows=100,
        )
        self.assertEqual(len(out), 1)
        self.assertEqual(str(out.iloc[0]["source_side"]), "BUY")


if __name__ == "__main__":
    unittest.main()
