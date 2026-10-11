import sqlite3
import time
import unittest
from unittest.mock import patch

from src import copy_trading as ct


class RealisticCopyTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        ct.init_db(self.conn)
        self.settings = ct.CopySettings(realistic_copy_enabled=True)

    def tearDown(self):
        self.conn.close()

    def trade(self, side="BUY", size=3000, tx="first"):
        return dict(asset="123", side=side, size=size, price=.5,
                    timestamp=time.time()-1, transactionHash=tx, title="Market")

    def book(self, **extra):
        return dict(asset_id="123", timestamp=str(int(time.time()*1000)),
                    asks=[dict(price=".52", size="2000"), dict(price=".51", size="1000")],
                    bids=[dict(price=".49", size="5000")], **extra)

    def apply(self, trade, book=None):
        with patch("src.copy_execution.fetch_book", return_value=book or self.book()):
            return ct.apply_paper_trade(self.conn, trade, self.settings)

    def test_equal_shares_walk_depth_and_fund_above_cash_limit(self):
        order = self.apply(self.trade())
        self.assertEqual(order.copy_size, 3000)
        self.assertAlmostEqual(order.copy_notional, 1550)
        row = self.conn.execute("SELECT * FROM paper_orders").fetchone()
        self.assertAlmostEqual(row["copy_price"], 1550/3000)
        self.assertAlmostEqual(ct.trader_contributions(self.conn, self.settings.target_wallet), 1550)

    def test_partial_fill_and_no_reuse_of_same_snapshot_liquidity(self):
        book = self.book()
        first = self.apply(self.trade(size=4000), book)
        second = self.apply(self.trade(size=4000, tx="second"), book)
        self.assertEqual(first.copy_size, 3000)
        self.assertEqual(first.reason, "book_partial")
        self.assertEqual(second.copy_size, 0)

    def test_sell_walks_bids_and_never_shorts(self):
        self.apply(self.trade())
        order = self.apply(self.trade(side="SELL", size=4000, tx="sell"))
        self.assertEqual(order.copy_size, 3000)
        self.assertAlmostEqual(order.realized_pnl, -80)

    def test_stale_pre_fill_wrong_asset_and_invalid_books_fail_closed(self):
        for change in [dict(timestamp="1"), dict(asset_id="other"),
                       dict(asks=[dict(price="NaN", size="500")])]:
            book = self.book()
            book.update(change)
            order = self.apply(self.trade(tx=str(change)), book)
            self.assertEqual(order.copy_size, 0)

    def test_http_failure_never_falls_back_to_source_price(self):
        with patch("src.copy_execution.fetch_book", side_effect=ValueError("bad book")):
            order = ct.apply_paper_trade(self.conn, self.trade(), self.settings)
        self.assertEqual(order.copy_size, 0)
        self.assertEqual(order.reason, "book_unavailable")

    def test_duplicate_does_not_consume_or_fund_twice(self):
        trade = self.trade()
        self.apply(trade)
        self.assertEqual(self.apply(trade).status, "duplicate")
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM cash_events").fetchone()[0], 1)

    def test_precise_source_time_rejects_earlier_book_in_same_second(self):
        base = int(time.time()) - 2
        trade = self.trade()
        trade["timestamp"] = base + .9
        book = self.book()
        book["timestamp"] = str(int((base + .1)*1000))
        self.assertEqual(self.apply(trade, book).reason, "book_stale_or_pre_fill")

    def test_out_of_order_and_inconsistent_books_do_not_replenish(self):
        base = time.time() - .1
        first = self.book()
        first["timestamp"] = str(int(base*1000))
        self.assertEqual(self.apply(self.trade(), first).copy_size, 3000)
        old = {**first, "timestamp": str(int((base-.1)*1000)), "asks": [dict(price=".51", size="50")]}
        self.assertEqual(self.apply(self.trade(tx="old"), old).copy_size, 0)
        same_time = {**first, "asks": [dict(price=".53", size="5000")]}
        self.assertEqual(self.apply(self.trade(tx="changed"), same_time).copy_size, 0)
        self.assertEqual(self.apply(self.trade(tx="replay"), first).copy_size, 0)

    def test_network_call_holds_no_write_transaction(self):
        def fetch(asset):
            self.assertFalse(self.conn.in_transaction)
            return self.book()
        with patch("src.copy_execution.fetch_book", side_effect=fetch):
            ct.apply_paper_trade(self.conn, self.trade(), self.settings)
        self.assertFalse(self.conn.in_transaction)

    def test_position_comparison_shows_source_copy_and_stale_marks(self):
        from app.copy_positions import comparison
        self.apply(self.trade())
        row = comparison(self.conn, {})[self.settings.target_wallet][0]
        self.assertEqual(row["source_size"], 3000)
        self.assertEqual(row["copy_size"], 3000)
        self.assertAlmostEqual(row["copy_entry"], 1550/3000)
        self.assertTrue(row["source_stale"])
        self.assertEqual(row["last_execution"]["filled_size"], 3000)

    def test_slippage_does_not_inflate_execution_fidelity(self):
        from app.copy_fidelity import execution_fidelity
        self.apply(self.trade())
        result = execution_fidelity(ct.get_paper_orders(conn=self.conn))
        self.assertEqual(result["fidelity"], 1.0)

    def test_book_minimum_size_is_respected(self):
        order = self.apply(self.trade(size=2), self.book(min_order_size="5"))
        self.assertEqual(order.copy_size, 0)
        self.assertEqual(order.reason, "book_below_min_size")


if __name__ == "__main__":
    unittest.main()
