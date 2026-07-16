"""Tests for the read-only microstructure book recorder."""

from __future__ import annotations

import csv
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src import book_recorder as br

NOW = datetime(2026, 7, 16, 18, 0, 0, tzinfo=timezone.utc)


def gamma_market(mid: str, volume: float, outcomes=("Yes", "No")) -> dict:
    return {
        "id": mid,
        "slug": f"markt-{mid}",
        "question": f"Frage {mid}?",
        "volume24hr": volume,
        "outcomes": json.dumps(list(outcomes)),
        "clobTokenIds": json.dumps([f"tok_{mid}_yes", f"tok_{mid}_no"]),
    }


def clob_book(best_bid: float, best_ask: float, size: float = 100.0) -> dict:
    return {
        "bids": [
            {"price": str(best_bid), "size": str(size)},
            {"price": str(round(best_bid - 0.01, 2)), "size": str(size)},
        ],
        "asks": [
            {"price": str(best_ask), "size": str(size)},
            {"price": str(round(best_ask + 0.01, 2)), "size": str(size)},
        ],
    }


class SelectMarketsTest(unittest.TestCase):
    def test_sorts_by_volume_and_filters_non_binary(self) -> None:
        raw = [
            gamma_market("low", 10.0),
            gamma_market("high", 999.0),
            gamma_market("multi", 500.0, outcomes=("A", "B", "C")),
        ]
        tracked = br.select_markets(raw, top_n=5)
        self.assertEqual([t["market_id"] for t in tracked], ["high", "low"])
        self.assertEqual(tracked[0]["tokens"][0], ("Yes", "tok_high_yes"))

    def test_top_n_limit(self) -> None:
        raw = [gamma_market(str(i), float(i)) for i in range(10)]
        self.assertEqual(len(br.select_markets(raw, top_n=3)), 3)


class BookRowTest(unittest.TestCase):
    def test_row_metrics(self) -> None:
        tracked = {"market_id": "m1", "slug": "s1"}
        row = br.book_row("2026-07-16T18:00:00Z", tracked, "Yes", "tok",
                          clob_book(0.60, 0.64))
        self.assertEqual(row["best_bid"], 0.60)
        self.assertEqual(row["best_ask"], 0.64)
        self.assertEqual(row["spread"], 0.04)
        self.assertEqual(row["mid"], 0.62)
        # bid usd: 0.60*100 + 0.59*100 = 119; ask usd: 0.64*100 + 0.65*100 = 129
        self.assertEqual(row["bid_usd_top"], 119.0)
        self.assertEqual(row["ask_usd_top"], 129.0)
        self.assertAlmostEqual(row["imbalance_top"], 119.0 / 248.0, places=4)

    def test_empty_book_has_none_metrics(self) -> None:
        row = br.book_row("ts", {"market_id": "m", "slug": "s"}, "Yes", "tok", {})
        self.assertIsNone(row["best_bid"])
        self.assertIsNone(row["imbalance_top"])


class TradesRowsTest(unittest.TestCase):
    def test_filters_to_tracked_tokens_and_has_no_wallet_column(self) -> None:
        token_map = {"tok_a": {"market_id": "m1", "slug": "s1", "outcome": "Yes"}}
        tape = [
            {"asset": "tok_a", "side": "BUY", "price": 0.5, "size": 10,
             "timestamp": 1, "transactionHash": "0x1", "proxyWallet": "0xW"},
            {"asset": "tok_x", "side": "SELL", "price": 0.4, "size": 5,
             "timestamp": 2, "transactionHash": "0x2"},
        ]
        rows = br.trades_rows("ts", token_map, tape)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["market_id"], "m1")
        self.assertNotIn("proxyWallet", rows[0])
        self.assertFalse(any("wallet" in key.lower() for key in rows[0]))


class RunOnceTest(unittest.TestCase):
    def _fake_get(self, url: str, params: dict | None = None, timeout: int = 20):
        params = params or {}
        if url == br.GAMMA_MARKETS_URL:
            if params.get("offset", 0) > 0:
                return []
            return [gamma_market("m1", 100.0)]
        if url == br.CLOB_BOOK_URL:
            return clob_book(0.55, 0.58)
        if url == br.TRADES_URL:
            if params.get("offset", 0) > 0:
                return []
            return [{"asset": "tok_m1_yes", "side": "BUY", "price": 0.56,
                     "size": 3, "timestamp": 7, "transactionHash": "0xabc"}]
        raise AssertionError(f"unexpected url {url}")

    def test_writes_day_partitioned_csvs_and_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            summary = br.run_once(out_dir=out, get_json=self._fake_get, now=NOW)
            self.assertEqual(summary["tracked_markets"], 1)
            self.assertEqual(summary["book_rows"], 2)  # YES und NO Token
            self.assertEqual(summary["trade_rows"], 1)
            with open(out / "books_2026-07-16.csv", newline="", encoding="utf-8") as f:
                books = list(csv.DictReader(f))
            self.assertEqual(len(books), 2)
            self.assertEqual(books[0]["market_id"], "m1")
            with open(out / "trades_2026-07-16.csv", newline="", encoding="utf-8") as f:
                trades = list(csv.DictReader(f))
            self.assertEqual(trades[0]["tx_hash"], "0xabc")
            self.assertTrue((out / "recorder_status.json").exists())

    def test_append_keeps_single_header(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            br.run_once(out_dir=out, get_json=self._fake_get, now=NOW)
            br.run_once(out_dir=out, get_json=self._fake_get, now=NOW)
            with open(out / "books_2026-07-16.csv", encoding="utf-8") as f:
                lines = f.read().strip().splitlines()
            self.assertEqual(len(lines), 1 + 4)  # ein Header, zwei Paesse a 2 Zeilen


if __name__ == "__main__":
    unittest.main()
