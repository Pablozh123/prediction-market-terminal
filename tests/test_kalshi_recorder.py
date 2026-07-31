import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src import kalshi_recorder as kr


def event_page(markets, cursor="", category="Politics"):
    return {
        "cursor": cursor,
        "events": [{
            "event_ticker": "EVT-1", "series_ticker": "KXTEST",
            "category": category, "title": "Ein Ereignis",
            "markets": markets,
        }],
    }


def market(ticker="KXTEST-A", volume=100.0, oi=10.0, exchange_index=0):
    return {"ticker": ticker, "volume_24h_fp": str(volume),
            "open_interest_fp": str(oi), "exchange_index": exchange_index}


def book(yes=None, no=None):
    return {"orderbook_fp": {
        "yes_dollars": yes if yes is not None else [["0.40", "100"], ["0.39", "200"]],
        "no_dollars": no if no is not None else [["0.55", "50"], ["0.54", "80"]],
    }}


class ParlayTests(unittest.TestCase):
    def test_parlay_tickers_are_recognised(self):
        self.assertTrue(kr.is_parlay("KXMVESPORTSMULTIGAME-S2026"))

    def test_ordinary_tickers_are_not(self):
        self.assertFalse(kr.is_parlay("KXFED-27APR-T3.75"))
        self.assertFalse(kr.is_parlay(""))


class OrderbookTests(unittest.TestCase):
    def test_no_bids_are_reflected_into_yes_asks(self):
        # Ein NO-Gebot zu 0.55 ist ein YES-Brief zu 0.45. Ohne die Spiegelung
        # waere jeder Spread in jeder Folgestudie invertiert.
        bids, asks = kr.parse_orderbook(book(no=[["0.55", "50"]]))
        self.assertEqual(asks[0][0], 0.45)

    def test_yes_bids_are_taken_as_they_are(self):
        bids, _ = kr.parse_orderbook(book(yes=[["0.40", "100"]]))
        self.assertEqual(bids[0][0], 0.40)

    def test_the_best_bid_is_the_highest_and_the_best_ask_the_lowest(self):
        bids, asks = kr.parse_orderbook(book(
            yes=[["0.38", "5"], ["0.41", "5"], ["0.40", "5"]],
            no=[["0.50", "5"], ["0.55", "5"], ["0.52", "5"]]))
        self.assertEqual(bids[0][0], 0.41)
        self.assertEqual(asks[0][0], 0.45)

    def test_the_derived_book_never_crosses_on_real_shaped_input(self):
        bids, asks = kr.parse_orderbook(book())
        self.assertLess(bids[0][0], asks[0][0])

    def test_zero_size_levels_are_dropped(self):
        bids, _ = kr.parse_orderbook(book(yes=[["0.40", "0"], ["0.30", "5"]]))
        self.assertEqual(bids[0][0], 0.30)

    def test_malformed_levels_are_skipped(self):
        bids, _ = kr.parse_orderbook(book(yes=[["nope", "5"], ["0.30", "5"]]))
        self.assertEqual(len(bids), 1)

    def test_an_empty_book_yields_no_levels(self):
        bids, asks = kr.parse_orderbook({"orderbook_fp": {"yes_dollars": [],
                                                          "no_dollars": []}})
        self.assertEqual((bids, asks), ([], []))

    def test_a_missing_payload_does_not_raise(self):
        self.assertEqual(kr.parse_orderbook({}), ([], []))
        self.assertEqual(kr.parse_orderbook(None), ([], []))

    def test_the_level_limit_is_respected(self):
        yes = [[f"0.{40 - i:02d}", "5"] for i in range(10)]
        bids, _ = kr.parse_orderbook(book(yes=yes), levels=3)
        self.assertEqual(len(bids), 3)


class BookRowTests(unittest.TestCase):
    def setUp(self):
        self.market = {"ticker": "KXTEST-A", "event_ticker": "EVT-1",
                       "category": "Politics", "volume_24h": 500.0}

    def test_row_carries_mid_and_spread(self):
        row = kr.book_row("2026-07-31T00:00:00Z", self.market, book())
        self.assertAlmostEqual(row["best_bid"], 0.40, places=6)
        self.assertAlmostEqual(row["best_ask"], 0.45, places=6)
        self.assertAlmostEqual(row["spread"], 0.05, places=6)
        self.assertAlmostEqual(row["mid"], 0.425, places=6)

    def test_row_uses_the_polymarket_column_layout(self):
        row = kr.book_row("2026-07-31T00:00:00Z", self.market, book())
        for column in ("ts_utc", "market_id", "token_id", "best_bid",
                       "best_ask", "spread", "mid", "imbalance_top",
                       "bids_json", "asks_json"):
            self.assertIn(column, row)

    def test_depth_is_priced_in_dollars(self):
        row = kr.book_row("t", self.market, book(yes=[["0.40", "100"]],
                                                 no=[["0.55", "50"]]))
        self.assertAlmostEqual(row["bid_usd_top"], 40.0, places=2)
        self.assertAlmostEqual(row["ask_usd_top"], 0.45 * 50, places=2)

    def test_imbalance_is_the_bid_share_of_depth(self):
        row = kr.book_row("t", self.market, book(yes=[["0.50", "100"]],
                                                 no=[["0.50", "100"]]))
        self.assertAlmostEqual(row["imbalance_top"], 0.5, places=6)

    def test_a_one_sided_book_has_no_mid(self):
        row = kr.book_row("t", self.market, book(no=[]))
        self.assertIsNone(row["mid"])
        self.assertIsNone(row["spread"])

    def test_category_is_carried_for_the_fee_model(self):
        row = kr.book_row("t", self.market, book())
        self.assertEqual(row["category"], "Politics")


class TradeRowTests(unittest.TestCase):
    def setUp(self):
        self.market = {"ticker": "KXTEST-A", "event_ticker": "EVT-1"}

    def test_a_taker_buying_yes_is_a_buy(self):
        rows = kr.trade_rows("t", self.market, [{
            "taker_side": "yes", "yes_price_dollars": "0.40",
            "count_fp": "10", "created_time": "2026-07-31T00:00:00Z",
            "trade_id": "abc"}])
        self.assertEqual(rows[0]["side"], "BUY")

    def test_a_taker_buying_no_is_a_sell_of_yes(self):
        rows = kr.trade_rows("t", self.market, [{
            "taker_side": "no", "yes_price_dollars": "0.40", "count_fp": "10"}])
        self.assertEqual(rows[0]["side"], "SELL")

    def test_the_price_recorded_is_always_the_yes_price(self):
        rows = kr.trade_rows("t", self.market, [{
            "taker_side": "no", "yes_price_dollars": "0.40",
            "no_price_dollars": "0.60", "count_fp": "10"}])
        self.assertEqual(rows[0]["price"], "0.40")

    def test_an_empty_tape_yields_no_rows(self):
        self.assertEqual(kr.trade_rows("t", self.market, []), [])
        self.assertEqual(kr.trade_rows("t", self.market, None), [])

    def test_non_dict_entries_are_skipped(self):
        self.assertEqual(kr.trade_rows("t", self.market, ["kaputt"]), [])


class DiscoveryTests(unittest.TestCase):
    def test_markets_are_ranked_by_volume(self):
        def get_json(path, params=None):
            return event_page([market("A", 10), market("B", 900),
                               market("C", 100)])
        picked = kr.discover_markets(get_json=get_json, pages=1, top_n=3)
        self.assertEqual([m["ticker"] for m in picked], ["B", "C", "A"])

    def test_parlay_markets_are_dropped(self):
        def get_json(path, params=None):
            return event_page([market("KXMVE-X", 9999), market("REAL", 1)])
        picked = kr.discover_markets(get_json=get_json, pages=1, top_n=5)
        self.assertEqual([m["ticker"] for m in picked], ["REAL"])

    def test_the_category_comes_from_the_event(self):
        def get_json(path, params=None):
            return event_page([market("A")], category="Economics")
        self.assertEqual(kr.discover_markets(get_json=get_json, pages=1)[0]["category"],
                         "Economics")

    def test_top_n_caps_the_selection(self):
        def get_json(path, params=None):
            return event_page([market(f"M{i}", i) for i in range(10)])
        self.assertEqual(len(kr.discover_markets(get_json=get_json, pages=1,
                                                 top_n=4)), 4)

    def test_paging_stops_when_the_cursor_runs_out(self):
        calls = {"n": 0}

        def get_json(path, params=None):
            calls["n"] += 1
            return event_page([market(f"M{calls['n']}")], cursor="")
        kr.discover_markets(get_json=get_json, pages=9)
        self.assertEqual(calls["n"], 1)

    def test_duplicate_tickers_are_collapsed(self):
        def get_json(path, params=None):
            return event_page([market("A", 5), market("A", 5)])
        self.assertEqual(len(kr.discover_markets(get_json=get_json, pages=1)), 1)

    def test_an_empty_exchange_yields_no_markets(self):
        self.assertEqual(kr.discover_markets(
            get_json=lambda p, q=None: {"events": [], "cursor": ""}, pages=1), [])


class ShardTests(unittest.TestCase):
    """Kalshi shards trading from 2026-08-06. The field cannot be backfilled."""

    def test_the_exchange_index_is_carried_from_discovery(self):
        def get_json(path, params=None):
            return event_page([market("A", exchange_index=1)])
        self.assertEqual(kr.discover_markets(get_json=get_json, pages=1)[0]
                         ["exchange_index"], 1)

    def test_it_lands_in_the_book_row(self):
        row = kr.book_row("t", {"ticker": "A", "event_ticker": "E",
                                "category": "P", "volume_24h": 1.0,
                                "exchange_index": 1}, book())
        self.assertEqual(row["exchange_index"], 1)

    def test_it_lands_in_the_trade_row(self):
        rows = kr.trade_rows("t", {"ticker": "A", "event_ticker": "E",
                                   "exchange_index": 1},
                             [{"taker_side": "yes", "yes_price_dollars": "0.4",
                               "count_fp": "1"}])
        self.assertEqual(rows[0]["exchange_index"], 1)

    def test_it_is_a_recorded_column_not_just_an_internal_field(self):
        self.assertIn("exchange_index", kr.BOOK_FIELDS)
        self.assertIn("exchange_index", kr.TRADE_FIELDS)

    def test_a_market_without_the_field_still_records(self):
        row = kr.book_row("t", {"ticker": "A", "event_ticker": "E",
                                "category": "P", "volume_24h": 1.0}, book())
        self.assertIsNone(row["exchange_index"])


class RunOnceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        self.markets = [{"ticker": "KXTEST-A", "event_ticker": "EVT-1",
                         "category": "Politics", "volume_24h": 5.0}]

    def _get_json(self, path, params=None):
        if "orderbook" in path:
            return book()
        if "trades" in path:
            return {"trades": [{"taker_side": "yes",
                                "yes_price_dollars": "0.42",
                                "count_fp": "3",
                                "created_time": "2026-07-31T00:00:00Z"}]}
        return {"events": [], "cursor": ""}

    def test_a_pass_writes_books_and_trades(self):
        summary = kr.run_once(out_dir=self.out, get_json=self._get_json,
                              markets=self.markets,
                              now=datetime(2026, 7, 31, tzinfo=timezone.utc))
        self.assertEqual(summary["book_rows"], 1)
        self.assertEqual(summary["trade_rows"], 1)
        self.assertTrue((self.out / "kalshi_books_2026-07-31.csv").exists())
        self.assertTrue((self.out / "kalshi_trades_2026-07-31.csv").exists())

    def test_two_sided_books_are_counted(self):
        summary = kr.run_once(out_dir=self.out, get_json=self._get_json,
                              markets=self.markets)
        self.assertEqual(summary["two_sided_books"], 1)

    def test_a_broken_book_does_not_stop_the_pass(self):
        def flaky(path, params=None):
            if "orderbook" in path:
                raise ConnectionError("boom")
            return self._get_json(path, params)

        summary = kr.run_once(out_dir=self.out, get_json=flaky,
                              markets=self.markets)
        self.assertEqual(summary["book_errors"], 1)
        self.assertEqual(summary["trade_rows"], 1)

    def test_a_broken_tape_does_not_stop_the_books(self):
        def flaky(path, params=None):
            if "trades" in path:
                raise ConnectionError("boom")
            return self._get_json(path, params)

        summary = kr.run_once(out_dir=self.out, get_json=flaky,
                              markets=self.markets)
        self.assertEqual(summary["trade_errors"], 1)
        self.assertEqual(summary["book_rows"], 1)

    def test_the_status_file_is_written(self):
        kr.run_once(out_dir=self.out, get_json=self._get_json,
                    markets=self.markets)
        status = json.loads(
            (self.out / "kalshi_recorder_status.json").read_text(encoding="utf-8"))
        self.assertIn("tracked_markets", status)

    def test_rows_append_across_passes(self):
        for _ in range(3):
            kr.run_once(out_dir=self.out, get_json=self._get_json,
                        markets=self.markets,
                        now=datetime(2026, 7, 31, tzinfo=timezone.utc))
        lines = (self.out / "kalshi_books_2026-07-31.csv").read_text(
            encoding="utf-8").strip().splitlines()
        self.assertEqual(len(lines), 4)  # eine Kopfzeile plus drei Passes


class SchemaCompatibilityTests(unittest.TestCase):
    def test_the_orderflow_loader_reads_kalshi_books(self):
        # Der Sinn des gemeinsamen Layouts: die Studien laufen unveraendert.
        from src import orderflow_study as ofs

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            markets = [{"ticker": "KXTEST-A", "event_ticker": "E",
                        "category": "Politics", "volume_24h": 1.0}]
            for minute in range(6):
                kr.run_once(out_dir=out,
                            get_json=lambda p, q=None: book(),
                            markets=markets,
                            now=datetime(2026, 7, 31, 0, minute * 2,
                                         tzinfo=timezone.utc))
            renamed = out / "books_2026-07-31.csv"
            (out / "kalshi_books_2026-07-31.csv").rename(renamed)
            series = ofs.load_books(out)
            self.assertEqual(len(series), 1)
            self.assertGreater(len(next(iter(series.values()))), 1)


if __name__ == "__main__":
    unittest.main()
