import unittest

import pandas as pd

from app import calibration as calib
from app import scorecard as sc
from app.format import snapshot_label
from src.prediction_markets import MarketDataError


def resolved_frame(n_markets, win_every=2):
    """n distinct resolved markets (distinct event keys), alternating wins."""

    rows = []
    for index in range(n_markets):
        won = index % win_every == 0
        rows.append(
            {
                "title": f"Market {index}",
                "avg_price": 0.5,
                "current_price": 1.0 if won else 0.0,
                "realized_pnl": 50.0 if won else -50.0,
                "total_bought": 50.0,
                "time": pd.Timestamp("2026-06-01", tz="UTC") + pd.Timedelta(days=index),
                "market_key": f"c{index}",
                "url": f"https://polymarket.com/event/event-{index}",
                "outcome": "Yes",
            }
        )
    return pd.DataFrame(rows)


class RecordingFetchers:
    def __init__(self, resolved=None, capped=False, smart_row=None, risk_row=None):
        self.resolved = resolved if resolved is not None else resolved_frame(32)
        self.capped = capped
        self.smart_row = smart_row
        self.risk_row = risk_row
        self.calls = {"resolved": 0, "smart_row": 0, "risk_row": 0}

    def fetchers(self):
        return {
            "resolved": self._resolved,
            "smart_row": self._smart,
            "risk_row": self._risk,
        }

    def _resolved(self, wallet):
        self.calls["resolved"] += 1
        return self.resolved, self.capped

    def _smart(self, wallet):
        self.calls["smart_row"] += 1
        return self.smart_row

    def _risk(self, wallet):
        self.calls["risk_row"] += 1
        return self.risk_row


class ScorecardShapeTests(unittest.TestCase):
    def setUp(self):
        sc.clear_cache()

    def test_full_card_shares_one_snapshot(self):
        fx = RecordingFetchers(
            smart_row={"copy_smart_score": 71.0, "copy_grade": "B"},
            risk_row={"wallet_insider_score": 44.0, "wallet_insider_level": "Medium", "flags": ["late burst"]},
        )
        card = sc.wallet_scorecard("0xabc", fetchers=fx.fetchers())
        self.assertEqual(card["wallet"], "0xabc")
        self.assertFalse(pd.isna(pd.to_datetime(card["snapshot_at"], utc=True)))
        self.assertEqual(card["data_window"], {"trades": 32, "source": "polymarket_closed_positions"})
        self.assertEqual(card["errors"], {})
        self.assertEqual(card["track"]["resolved_markets"], 32)
        self.assertEqual(card["calibration"]["n"], 32)
        self.assertEqual(card["realized_edge"]["n_events"], 32)
        self.assertIsNotNone(card["attribution"])
        self.assertEqual(card["smart"], {"copy_smart_score": 71.0, "copy_grade": "B"})
        self.assertEqual(
            card["risk"],
            {"wallet_insider_score": 44.0, "risk_level": "Medium", "flags": ["late burst"]},
        )
        self.assertEqual(card["sample"]["n_resolved"], 32)
        self.assertNotEqual(snapshot_label(card["snapshot_at"]), "-")

    def test_missing_smart_and_risk_are_none_without_errors(self):
        fx = RecordingFetchers()
        card = sc.wallet_scorecard("0xnone", fetchers=fx.fetchers())
        self.assertIsNone(card["smart"])
        self.assertIsNone(card["risk"])
        self.assertEqual(card["errors"], {})


class ScorecardCacheTests(unittest.TestCase):
    def setUp(self):
        sc.clear_cache()

    def test_two_calls_within_ttl_fetch_once(self):
        fx = RecordingFetchers()
        first = sc.wallet_scorecard("0xcache", fetchers=fx.fetchers())
        second = sc.wallet_scorecard("0xcache", fetchers=fx.fetchers())
        self.assertEqual(fx.calls["resolved"], 1)
        self.assertEqual(fx.calls["smart_row"], 1)
        self.assertIs(first, second)
        self.assertEqual(first["snapshot_at"], second["snapshot_at"])

    def test_refresh_forces_new_fetch(self):
        fx = RecordingFetchers()
        sc.wallet_scorecard("0xrefresh", fetchers=fx.fetchers())
        sc.wallet_scorecard("0xrefresh", fetchers=fx.fetchers(), refresh=True)
        self.assertEqual(fx.calls["resolved"], 2)

    def test_zero_ttl_disables_cache(self):
        fx = RecordingFetchers()
        sc.wallet_scorecard("0xnottl", fetchers=fx.fetchers(), ttl_seconds=0)
        sc.wallet_scorecard("0xnottl", fetchers=fx.fetchers(), ttl_seconds=0)
        self.assertEqual(fx.calls["resolved"], 2)

    def test_cache_key_is_case_insensitive(self):
        fx = RecordingFetchers()
        sc.wallet_scorecard("0xAbC1", fetchers=fx.fetchers())
        sc.wallet_scorecard("0xabc1", fetchers=fx.fetchers())
        self.assertEqual(fx.calls["resolved"], 1)


class ScorecardPartialFailureTests(unittest.TestCase):
    def setUp(self):
        sc.clear_cache()

    def test_resolved_failure_yields_partial_card(self):
        def broken_resolved(wallet):
            raise MarketDataError("closed-positions feed down")

        fx = RecordingFetchers(smart_row={"copy_smart_score": 60.0, "copy_grade": "C"})
        fetchers = fx.fetchers()
        fetchers["resolved"] = broken_resolved
        card = sc.wallet_scorecard("0xfail", fetchers=fetchers)
        self.assertIn("resolved", card["errors"])
        self.assertIn("feed down", card["errors"]["resolved"])
        self.assertEqual(card["track"]["resolved_markets"], 0)
        self.assertEqual(card["sample"]["quality"], "insufficient")
        self.assertEqual(card["smart"], {"copy_smart_score": 60.0, "copy_grade": "C"})

    def test_smart_failure_keeps_resolved_parts(self):
        def broken_smart(wallet):
            raise MarketDataError("leaderboard down")

        fx = RecordingFetchers()
        fetchers = fx.fetchers()
        fetchers["smart_row"] = broken_smart
        card = sc.wallet_scorecard("0xsmartfail", fetchers=fetchers)
        self.assertIsNone(card["smart"])
        self.assertIn("smart", card["errors"])
        self.assertEqual(card["track"]["resolved_markets"], 32)
        self.assertEqual(card["realized_edge"]["n_events"], 32)

    def test_no_exception_reaches_the_caller(self):
        def explode(wallet):
            raise ValueError("boom")

        card = sc.wallet_scorecard(
            "0xboom",
            fetchers={"resolved": explode, "smart_row": explode, "risk_row": explode},
        )
        self.assertEqual(set(card["errors"]), {"resolved", "smart", "risk"})


class SampleQualityTests(unittest.TestCase):
    def setUp(self):
        sc.clear_cache()

    def test_threshold_boundaries(self):
        below_min = sc.sample_quality(calib.MIN_SAMPLE - 1)
        at_min = sc.sample_quality(calib.MIN_SAMPLE)
        below_verdict = sc.sample_quality(calib.MIN_VERDICT_EVENTS - 1)
        at_verdict = sc.sample_quality(calib.MIN_VERDICT_EVENTS)
        self.assertEqual(below_min["quality"], "insufficient")
        self.assertEqual(at_min["quality"], "developing")
        self.assertEqual(below_verdict["quality"], "developing")
        self.assertEqual(at_verdict["quality"], "adequate")
        self.assertFalse(below_verdict["verdict_allowed"])
        self.assertTrue(at_verdict["verdict_allowed"])

    def test_quality_flows_from_netted_events(self):
        for n, expected in (
            (calib.MIN_SAMPLE - 1, "insufficient"),
            (calib.MIN_SAMPLE, "developing"),
            (calib.MIN_VERDICT_EVENTS, "adequate"),
        ):
            sc.clear_cache()
            fx = RecordingFetchers(resolved=resolved_frame(n))
            card = sc.wallet_scorecard(f"0xq{n}", fetchers=fx.fetchers())
            self.assertEqual(card["sample"]["n_resolved"], n)
            self.assertEqual(card["sample"]["quality"], expected)


class BlockMappingTests(unittest.TestCase):
    def test_smart_block_handles_missing_and_nan(self):
        self.assertIsNone(sc._smart_block(None))
        self.assertIsNone(sc._smart_block({"copy_smart_score": float("nan")}))
        self.assertEqual(
            sc._smart_block({"copy_smart_score": 88, "copy_grade": "A", "extra": 1}),
            {"copy_smart_score": 88.0, "copy_grade": "A"},
        )

    def test_risk_block_normalizes_flags_and_level(self):
        self.assertIsNone(sc._risk_block(None))
        block = sc._risk_block({"wallet_insider_score": 55.0, "wallet_risk_level": "High", "flags": "single flag"})
        self.assertEqual(block, {"wallet_insider_score": 55.0, "risk_level": "High", "flags": ["single flag"]})


if __name__ == "__main__":
    unittest.main()
