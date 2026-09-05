"""app/outliers.py: a wallet far above its market's own baseline, and whether it was alone."""

from __future__ import annotations

import os
import unittest
from unittest import mock

import numpy as np
import pandas as pd

from app import outliers as outl

NOW = pd.Timestamp("2026-09-05T18:00:00Z")


def _print(t, wallet, notional, price=0.4, side="BUY", outcome="Yes", title="Will the Fed cut in September?", key="0xfed", trader=""):
    return {"platform": "Polymarket", "time": pd.Timestamp(t), "wallet": wallet, "trader": trader, "side": side,
            "outcome": outcome, "title": title, "price": price, "size": notional / price, "notional": notional,
            "market_key": key, "url": "https://polymarket.com/event/fed"}


def retail_history(n=400, days=5, seed=3, **kw):
    """Ordinary prints from many wallets over ``days``, sizes $5 to $800, all older than the window."""

    rng = np.random.default_rng(seed)
    rows = []
    start = NOW - pd.Timedelta(days=days)
    for i in range(n):
        t = start + pd.Timedelta(seconds=float(rng.uniform(0, days * 86_400 - 2 * 3600)))
        rows.append(_print(t, f"0xretail{int(rng.integers(0, 120)):03d}", float(rng.choice([5, 12, 30, 80, 200, 800], p=[.3, .25, .2, .15, .07, .03])), **kw))
    return rows


class BaselineTests(unittest.TestCase):
    def test_baseline_reads_only_prints_before_the_cut(self) -> None:
        rows = retail_history() + [_print(NOW - pd.Timedelta(minutes=5), "0xnew", 50_000.0)]
        base = outl.market_baseline(pd.DataFrame(rows), before=NOW - pd.Timedelta(minutes=60))
        self.assertEqual(base["n"], 400)
        self.assertEqual(base["state"], outl.BASELINE_SOLID)
        self.assertLess(base["max"], 50_000.0)
        self.assertGreater(base["yardstick"], 0.0)
        self.assertGreaterEqual(base["yardstick"], base["median"])
        self.assertGreater(base["hours"], 100.0)
        self.assertEqual(base["wallets"], len({r["wallet"] for r in rows[:-1]}))
        self.assertIsNotNone(base["volume_per_hour"])

    def test_thin_and_empty_baselines_say_so(self) -> None:
        thin = outl.market_baseline(pd.DataFrame(retail_history(n=40)), before=NOW)
        self.assertEqual(thin["state"], outl.BASELINE_THIN)
        self.assertEqual(thin["n"], 40)
        none = outl.market_baseline(pd.DataFrame(), before=NOW)
        self.assertEqual(none["state"], outl.BASELINE_NONE)
        self.assertIsNone(none["yardstick"])

    def test_the_yardstick_is_a_wallet_hour_quantile_not_a_print_quantile(self) -> None:
        # One wallet splitting $10k into ten clips inside one hour makes a
        # $10k wallet-hour; the largest single print stays $1k.
        rows = retail_history(n=200)
        hour = NOW - pd.Timedelta(days=2)
        rows += [_print(hour + pd.Timedelta(minutes=i), "0xsplit", 1_000.0) for i in range(10)]
        base = outl.market_baseline(pd.DataFrame(rows), before=NOW, quantile=0.999)
        # The top wallet-hour is $10k; the quantile interpolates towards it
        # and lands far above any single print.
        self.assertGreater(base["yardstick"], 5_000.0)
        self.assertLessEqual(base["yardstick"], 10_000.0)
        self.assertAlmostEqual(base["max"], 1_000.0)


class WalletWindowTests(unittest.TestCase):
    def test_window_sums_per_wallet_with_side_price_and_share(self) -> None:
        rows = [
            _print(NOW - pd.Timedelta(minutes=50), "0xA", 30_000.0, price=0.20, side="BUY", outcome="Yes", trader="alpha"),
            _print(NOW - pd.Timedelta(minutes=40), "0xa", 10_000.0, price=0.30, side="BUY", outcome="Yes"),
            _print(NOW - pd.Timedelta(minutes=30), "0xb", 1_000.0, price=0.6, side="SELL", outcome="No"),
            _print(NOW - pd.Timedelta(minutes=90), "0xc", 99_000.0),  # before the window
        ]
        window = outl.wallet_window(pd.DataFrame(rows), since=NOW - pd.Timedelta(minutes=60), until=NOW)
        self.assertEqual(list(window["wallet"]), ["0xa", "0xb"])
        a = window.iloc[0]
        self.assertEqual(a["prints"], 2)
        self.assertAlmostEqual(a["total"], 40_000.0)
        self.assertAlmostEqual(a["largest"], 30_000.0)
        self.assertEqual(a["side"], "YES buys")
        self.assertAlmostEqual(a["price"], 0.225)
        self.assertEqual(a["trader"], "alpha")
        self.assertAlmostEqual(a["share"], 40_000.0 / 41_000.0)
        self.assertEqual(window.iloc[1]["side"], "NO sells")

    def test_empty_window(self) -> None:
        self.assertTrue(outl.wallet_window(pd.DataFrame(), since=NOW - pd.Timedelta(hours=1), until=NOW).empty)


class MarketPictureTests(unittest.TestCase):
    def _market(self, extra):
        return pd.DataFrame(retail_history() + extra)

    def test_a_lone_whale_is_the_single_deviation(self) -> None:
        tape = self._market([
            _print(NOW - pd.Timedelta(minutes=20), "0xwhale", 24_000.0, trader="magnus"),
            _print(NOW - pd.Timedelta(minutes=18), "0xwhale", 24_000.0),
            _print(NOW - pd.Timedelta(minutes=10), "0xsmall", 300.0),
        ])
        picture = outl.market_picture(tape, now=NOW, whale_threshold=2500.0)
        self.assertEqual(picture["verdict"], "single")
        self.assertEqual(picture["elevated"], 1)
        whale = picture["wallets"][0]
        self.assertEqual(whale["wallet"], "0xwhale")
        self.assertTrue(whale["elevated"])
        self.assertAlmostEqual(whale["total"], 48_000.0)
        self.assertGreater(whale["ratio"], outl.OUTLIER_RATIO)
        self.assertEqual(whale["name"], "magnus")
        self.assertEqual(whale["side"], "YES buys")
        self.assertFalse(picture["wallets"][1]["elevated"])
        self.assertEqual(picture["window"]["wallets"], 2)
        self.assertIn("the only wallet above the baseline", picture["verdict_text"])
        self.assertIn("1 other wallet inside it", picture["verdict_text"])
        self.assertGreater(picture["window"]["volume_ratio"], 1.0)

    def test_several_wallets_above_the_baseline(self) -> None:
        tape = self._market([
            _print(NOW - pd.Timedelta(minutes=20), "0xw1", 30_000.0),
            _print(NOW - pd.Timedelta(minutes=15), "0xw2", 12_000.0),
            _print(NOW - pd.Timedelta(minutes=12), "0xw3", 9_000.0),
        ])
        picture = outl.market_picture(tape, now=NOW, whale_threshold=2500.0)
        self.assertEqual(picture["verdict"], "several")
        self.assertEqual(picture["elevated"], 3)
        self.assertEqual([w["wallet"] for w in picture["wallets"]], ["0xw1", "0xw2", "0xw3"])
        self.assertIn("3 wallets above the baseline", picture["verdict_text"])

    def test_the_floor_keeps_dust_markets_quiet(self) -> None:
        # A $1,000 wallet-hour is many times this market's yardstick but
        # below the whale threshold: not an outlier.
        tape = self._market([_print(NOW - pd.Timedelta(minutes=20), "0xmid", 1_000.0)])
        picture = outl.market_picture(tape, now=NOW, whale_threshold=2500.0)
        self.assertEqual(picture["verdict"], "none")
        self.assertFalse(picture["wallets"][0]["elevated"])
        self.assertGreater(picture["wallets"][0]["ratio"], 1.0)

    def test_a_whale_market_keeps_its_own_scale(self) -> None:
        # Where $20k wallet-hours are routine, a $30k hour is not a deviation.
        rows = retail_history(n=200)
        rng = np.random.default_rng(7)
        for i in range(60):
            t = NOW - pd.Timedelta(hours=float(rng.uniform(2, 100)))
            rows.append(_print(t, f"0xbig{i % 12:02d}", float(rng.uniform(15_000, 25_000))))
        rows.append(_print(NOW - pd.Timedelta(minutes=20), "0xanother", 30_000.0))
        picture = outl.market_picture(pd.DataFrame(rows), now=NOW, whale_threshold=2500.0)
        self.assertEqual(picture["verdict"], "none")

    def test_no_baseline_means_no_verdict(self) -> None:
        tape = pd.DataFrame(retail_history(n=30) + [_print(NOW - pd.Timedelta(minutes=5), "0xwhale", 100_000.0)])
        picture = outl.market_picture(tape, now=NOW, whale_threshold=2500.0)
        self.assertEqual(picture["baseline"]["state"], outl.BASELINE_THIN)
        self.assertEqual(picture["verdict"], "none")
        self.assertFalse(picture["wallets"][0]["elevated"])
        self.assertIn("no baseline yet: 30 prints", picture["verdict_text"])

    def test_rules_can_be_handed_in_and_read_from_the_environment(self) -> None:
        tape = self._market([_print(NOW - pd.Timedelta(minutes=20), "0xwhale", 6_000.0)])
        strict = outl.market_picture(tape, now=NOW, whale_threshold=2500.0, rules={"ratio": 500.0})
        self.assertEqual(strict["verdict"], "none")
        with mock.patch.dict(os.environ, {"RISK_OUTLIER_RATIO": "1.5", "RISK_OUTLIER_MIN_PRINTS": "50", "RISK_OUTLIER_RECENT_MINUTES": "30"}):
            rules = outl.outlier_rules()
        self.assertEqual((rules["ratio"], rules["min_prints"], rules["recent_minutes"]), (1.5, 50, 30.0))
        with mock.patch.dict(os.environ, {"RISK_OUTLIER_QUANTILE": "1.7"}):
            self.assertEqual(outl.outlier_rules()["quantile"], outl.OUTLIER_QUANTILE)


class CandidateMarketsTests(unittest.TestCase):
    def test_polymarket_markets_with_a_whale_sized_wallet_total(self) -> None:
        tape = pd.DataFrame([
            _print(NOW, "0xa", 1_500.0, key="0xm1", title="M1"),
            _print(NOW, "0xa", 1_500.0, key="0xm1", title="M1"),
            _print(NOW, "0xb", 9_000.0, key="0xm2", title="M2"),
            _print(NOW, "0xc", 2_000.0, key="0xm3", title="M3"),
            {**_print(NOW, "Not public", 50_000.0, key="KXFED-26SEP", title="Kalshi"), "platform": "Kalshi"},
        ])
        found = outl.candidate_markets(tape, whale_threshold=2500.0)
        self.assertEqual([m["market_key"] for m in found], ["0xm2", "0xm1"])
        self.assertEqual(found[0]["title"], "M2")
        self.assertAlmostEqual(found[0]["top_wallet_total"], 9_000.0)
        self.assertEqual([m["market_key"] for m in outl.candidate_markets(tape, whale_threshold=2500.0, limit=1)], ["0xm2"])
        self.assertEqual(outl.candidate_markets(pd.DataFrame(), whale_threshold=2500.0), [])


class SizeOutliersTests(unittest.TestCase):
    def test_rows_and_pictures_across_markets(self) -> None:
        fed = pd.DataFrame(retail_history() + [_print(NOW - pd.Timedelta(minutes=20), "0xwhale", 48_000.0, trader="magnus")])
        quiet = pd.DataFrame(retail_history(seed=9, key="0xq", title="Quiet?") + [_print(NOW - pd.Timedelta(minutes=9), "0xsmall", 400.0, key="0xq", title="Quiet?")])
        rows, pictures = outl.size_outliers(
            {"0xfed": fed, "0xq": quiet}, now=NOW, whale_threshold=2500.0,
            meta={"0xfed": {"title": "Will the Fed cut in September?", "category": "Macro & central banks"}},
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(len(pictures), 1)
        row = rows[0]
        self.assertEqual(row["wallet"], "0xwhale")
        self.assertEqual(row["name"], "magnus")
        self.assertEqual(row["category"], "Macro & central banks")
        self.assertEqual(row["market_key"], "0xfed")
        self.assertEqual(row["verdict"], "single")
        self.assertEqual(row["elevated_wallets"], 1)
        self.assertEqual(row["total_label"], "$48.0k")
        self.assertTrue(row["ratio_label"].endswith("×"))
        self.assertEqual(row["first_trade_label"], "not asked")
        self.assertEqual(pictures[0]["market_key"], "0xfed")

    def test_first_trades_are_written_into_rows_and_pictures(self) -> None:
        fed = pd.DataFrame(retail_history() + [_print(NOW - pd.Timedelta(minutes=20), "0xwhale", 48_000.0)])
        rows, pictures = outl.size_outliers({"0xfed": fed}, now=NOW, whale_threshold=2500.0)
        stamp = int((NOW - pd.Timedelta(minutes=20)).timestamp() - 0.5 * 86_400)
        outl.attach_first_trades(rows, pictures, {"0xwhale": {"first_trade_ts": stamp, "state": "measured"}})
        self.assertAlmostEqual(rows[0]["first_trade_days"], 0.5, places=2)
        self.assertEqual(rows[0]["first_trade_state"], "measured")
        self.assertEqual(rows[0]["first_trade_label"], "12 h")
        self.assertAlmostEqual(pictures[0]["wallets"][0]["first_trade_days"], 0.5, places=2)

    def test_payload_names_the_rule(self) -> None:
        payload = outl.outlier_payload([], [], screened=7, whale_threshold=2500.0, as_of="2026-09-05 18:00 UTC")
        self.assertEqual(payload["count"], 0)
        self.assertEqual(payload["screened"], 7)
        self.assertEqual(payload["rules"]["floor"], 2500.0)
        self.assertIn("99th percentile", payload["rules"]["reads"])
        self.assertIn("2 times", payload["rules"]["reads"])
        self.assertIn("no probability", payload["note"])


if __name__ == "__main__":
    unittest.main()
