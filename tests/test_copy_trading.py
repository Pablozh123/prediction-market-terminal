import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from src import copy_trading as ct


def source_trade(
    *,
    tx: str = "0xabc",
    asset: str = "asset-1",
    side: str = "BUY",
    outcome: str = "Yes",
    price: float = 0.5,
    size: float = 2000.0,
    timestamp: int = 1779900000,
) -> dict:
    return {
        "transaction_hash": tx,
        "asset": asset,
        "side": side,
        "price": price,
        "size": size,
        "timestamp": timestamp,
        "market_key": "market-1",
        "title": "Example market",
        "outcome": outcome,
        "time": "2026-05-27T18:00:00Z",
    }


def uint_word(value: int) -> str:
    return f"{value:064x}"


class CopyTradingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "copy.sqlite"
        self.settings = ct.CopySettings(trade_limit=20)
        ct.reset_paper_portfolio(db_path=self.db_path)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_buy_uses_one_percent_of_source_notional(self) -> None:
        conn = ct.connect(self.db_path)
        try:
            order = ct.apply_paper_trade(conn, source_trade(price=0.5, size=2000.0), self.settings)
            snapshot = ct.value_paper_portfolio(conn=conn)
        finally:
            conn.close()

        self.assertEqual(order.status, "copied")
        self.assertAlmostEqual(order.copy_notional, 10.0)
        self.assertAlmostEqual(order.copy_size, 20.0)
        self.assertAlmostEqual(snapshot.cash, 990.0)

    def test_large_buy_is_capped_at_five_percent_equity(self) -> None:
        conn = ct.connect(self.db_path)
        try:
            order = ct.apply_paper_trade(conn, source_trade(price=0.5, size=100000.0), self.settings)
        finally:
            conn.close()

        self.assertEqual(order.status, "copied")
        self.assertAlmostEqual(order.copy_notional, 50.0)
        self.assertAlmostEqual(order.copy_size, 100.0)

    def test_dynamic_wallet_sizing_matches_relative_equity(self) -> None:
        conn = ct.connect(self.db_path)
        try:
            ct._set_meta(conn, "tony_visible_equity", "200000")
            order = ct.apply_paper_trade(conn, source_trade(price=0.5, size=2000.0), self.settings)
            sizing = ct.get_dynamic_sizing_snapshot(conn=conn)
        finally:
            conn.close()

        self.assertEqual(order.status, "copied")
        self.assertAlmostEqual(order.copy_notional, 5.0)
        self.assertAlmostEqual(float(sizing["effective_copy_scale"]), 0.005)
        self.assertEqual(sizing["copy_scale_mode"], "dynamic_wallet_equity")

    def test_dynamic_cap_can_follow_tony_largest_position_pct(self) -> None:
        conn = ct.connect(self.db_path)
        try:
            ct._set_meta(conn, "tony_visible_equity", "100000")
            ct._set_meta(conn, "tony_max_market_position_pct", "0.10")
            order = ct.apply_paper_trade(conn, source_trade(price=0.5, size=20000.0), self.settings)
            sizing = ct.get_dynamic_sizing_snapshot(conn=conn)
        finally:
            conn.close()

        self.assertEqual(order.status, "copied")
        self.assertAlmostEqual(order.copy_notional, 100.0)
        self.assertAlmostEqual(float(sizing["effective_max_order_equity_pct"]), 0.10)

    def test_add_paper_cash_keeps_open_positions(self) -> None:
        conn = ct.connect(self.db_path)
        try:
            ct.apply_paper_trade(conn, source_trade(price=0.5, size=2000.0), self.settings)
            conn.commit()
        finally:
            conn.close()

        new_cash = ct.add_paper_cash(1000.0, db_path=self.db_path)
        snapshot = ct.value_paper_portfolio(db_path=self.db_path)
        cash_events = ct.get_cash_events(db_path=self.db_path)

        self.assertAlmostEqual(new_cash, 1990.0)
        self.assertAlmostEqual(snapshot.cash, 1990.0)
        self.assertEqual(len(snapshot.positions), 1)
        self.assertEqual(len(cash_events), 1)
        self.assertAlmostEqual(float(cash_events.iloc[0]["amount"]), 1000.0)

    def test_duplicate_trade_is_ignored(self) -> None:
        trade = source_trade()
        conn = ct.connect(self.db_path)
        try:
            first = ct.apply_paper_trade(conn, trade, self.settings)
            second = ct.apply_paper_trade(conn, trade, self.settings)
            orders = ct.get_paper_orders(conn=conn)
        finally:
            conn.close()

        self.assertEqual(first.status, "copied")
        self.assertEqual(second.status, "duplicate")
        self.assertEqual(len(orders), 1)

    def test_sell_copies_same_position_reduction_ratio(self) -> None:
        conn = ct.connect(self.db_path)
        try:
            buy = source_trade(tx="0xbuy", price=0.4, size=1000.0)
            sell = source_trade(tx="0xsell", side="SELL", price=0.6, size=500.0)
            ct.apply_paper_trade(conn, buy, self.settings)
            sell_order = ct.apply_paper_trade(conn, sell, self.settings)
            snapshot = ct.value_paper_portfolio(conn=conn)
        finally:
            conn.close()

        self.assertEqual(sell_order.status, "copied")
        self.assertAlmostEqual(sell_order.copy_size, 5.0)
        self.assertAlmostEqual(sell_order.copy_notional, 3.0)
        self.assertAlmostEqual(sell_order.realized_pnl, 1.0)
        self.assertAlmostEqual(float(snapshot.positions.iloc[0]["shares"]), 5.0)

    def test_sell_without_tony_baseline_is_skipped(self) -> None:
        conn = ct.connect(self.db_path)
        try:
            order = ct.apply_paper_trade(conn, source_trade(side="SELL", price=0.6, size=500.0), self.settings)
        finally:
            conn.close()

        self.assertEqual(order.status, "skipped")
        self.assertEqual(order.reason, "skipped_unmatched_sell")

    def test_buy_is_skipped_when_no_cash_is_available(self) -> None:
        conn = ct.connect(self.db_path)
        try:
            conn.execute("UPDATE meta SET value = '0' WHERE key = 'cash'")
            order = ct.apply_paper_trade(conn, source_trade(), self.settings)
            snapshot = ct.value_paper_portfolio(conn=conn)
        finally:
            conn.close()

        self.assertEqual(order.status, "skipped")
        self.assertEqual(order.reason, "insufficient_cash")
        self.assertAlmostEqual(snapshot.cash, 0.0)

    def test_invalid_trade_is_skipped(self) -> None:
        conn = ct.connect(self.db_path)
        try:
            order = ct.apply_paper_trade(conn, source_trade(price=0.0, size=1000.0), self.settings)
        finally:
            conn.close()

        self.assertEqual(order.status, "skipped")
        self.assertEqual(order.reason, "invalid_trade")

    def test_decode_order_filled_maker_buy_log(self) -> None:
        wallet = ct.COPY_TARGET_WALLET
        asset = 46318155243932940013516475197746789436901911354434252871506026640562155818285
        log = {
            "address": ct.POLYMARKET_EXCHANGE_ADDRESSES[0],
            "transactionHash": "0xtrade",
            "blockNumber": hex(123),
            "transactionIndex": "0x1",
            "logIndex": "0x2",
            "topics": [
                ct.ORDER_FILLED_TOPIC,
                "0x" + "1" * 64,
                ct._address_topic(wallet),
                ct._address_topic(ct.POLYMARKET_EXCHANGE_ADDRESSES[0]),
            ],
            "data": "0x"
            + uint_word(0)
            + uint_word(asset)
            + uint_word(15_750_000)
            + uint_word(25_000_000)
            + uint_word(1000)
            + uint_word(0)
            + uint_word(0),
        }

        decoded = ct.decode_order_filled_log(log, wallet, {123: 1779911473})

        self.assertIsNotNone(decoded)
        self.assertEqual(decoded["side"], "BUY")
        self.assertEqual(decoded["asset"], str(asset))
        self.assertAlmostEqual(decoded["price"], 0.63)
        self.assertAlmostEqual(decoded["size"], 25.0)
        self.assertAlmostEqual(decoded["notional"], 15.75)

    def test_decode_order_filled_maker_sell_log(self) -> None:
        wallet = ct.COPY_TARGET_WALLET
        asset = 123456789
        log = {
            "address": ct.POLYMARKET_EXCHANGE_ADDRESSES[0],
            "transactionHash": "0xtrade",
            "blockNumber": hex(124),
            "transactionIndex": "0x1",
            "logIndex": "0x2",
            "topics": [
                ct.ORDER_FILLED_TOPIC,
                "0x" + "2" * 64,
                ct._address_topic(wallet),
                ct._address_topic(ct.POLYMARKET_EXCHANGE_ADDRESSES[0]),
            ],
            "data": "0x"
            + uint_word(asset)
            + uint_word(0)
            + uint_word(50_000_000)
            + uint_word(20_000_000)
            + uint_word(0)
            + uint_word(0)
            + uint_word(0),
        }

        decoded = ct.decode_order_filled_log(log, wallet, {124: 1779911474})

        self.assertIsNotNone(decoded)
        self.assertEqual(decoded["side"], "SELL")
        self.assertEqual(decoded["asset"], str(asset))
        self.assertAlmostEqual(decoded["price"], 0.4)
        self.assertAlmostEqual(decoded["size"], 50.0)
        self.assertAlmostEqual(decoded["notional"], 20.0)

    def test_redeem_recycles_winning_paper_position_to_cash(self) -> None:
        activity = pd.DataFrame(
            [
                {
                    "type": "REDEEM",
                    "conditionId": "market-1",
                    "transactionHash": "0xredeem",
                    "timestamp": 1779900100,
                    "size": 2000.0,
                    "usdcSize": 2000.0,
                    "title": "Example market",
                }
            ]
        )
        conn = ct.connect(self.db_path)
        try:
            ct.apply_paper_trade(conn, source_trade(price=0.5, size=2000.0), self.settings)
            conn.commit()
        finally:
            conn.close()

        with patch("src.copy_trading.fetch_source_activity", return_value=activity), patch(
            "src.copy_trading.fetch_closed_position_assets", return_value={"market-1": {"asset-1"}}
        ), patch("src.copy_trading.fetch_position_metadata", return_value={}):
            result = ct.sync_settlement_activity(ct.COPY_TARGET_WALLET, settings=self.settings, db_path=self.db_path)

        snapshot = ct.value_paper_portfolio(db_path=self.db_path)
        orders = ct.get_paper_orders(db_path=self.db_path)
        settled = orders[orders["status"] == "settled"]
        self.assertEqual(result.copied, 1)
        self.assertTrue(snapshot.positions.empty)
        self.assertAlmostEqual(snapshot.cash, 1010.0)
        self.assertAlmostEqual(float(settled.iloc[0]["copy_notional"]), 20.0)
        self.assertEqual(str(settled.iloc[0]["reason"]), "redeem_resolution")
        self.assertAlmostEqual(float(settled.iloc[0]["realized_pnl"]), 10.0)

    def test_redeem_resolution_realizes_loser_loss(self) -> None:
        activity = pd.DataFrame(
            [
                {
                    "type": "REDEEM",
                    "conditionId": "market-1",
                    "transactionHash": "0xredeem-loss",
                    "timestamp": 1779900100,
                    "size": 1000.0,
                    "usdcSize": 1000.0,
                    "title": "Example market",
                }
            ]
        )
        conn = ct.connect(self.db_path)
        try:
            ct.apply_paper_trade(conn, source_trade(tx="0xno", asset="no-token", outcome="No", price=0.6, size=1000.0), self.settings)
            conn.commit()
        finally:
            conn.close()

        with patch("src.copy_trading.fetch_source_activity", return_value=activity), patch(
            "src.copy_trading.fetch_closed_position_assets", return_value={"market-1": {"yes-token"}}
        ), patch("src.copy_trading.fetch_position_metadata", return_value={}):
            result = ct.sync_settlement_activity(ct.COPY_TARGET_WALLET, settings=self.settings, db_path=self.db_path)

        snapshot = ct.value_paper_portfolio(db_path=self.db_path)
        orders = ct.get_paper_orders(db_path=self.db_path)
        settled = orders[orders["status"] == "settled"]
        self.assertEqual(result.copied, 1)
        self.assertTrue(snapshot.positions.empty)
        self.assertAlmostEqual(snapshot.cash, 994.0)
        self.assertAlmostEqual(snapshot.realized_pnl, -6.0)
        self.assertAlmostEqual(float(settled.iloc[0]["copy_notional"]), 0.0)
        self.assertAlmostEqual(float(settled.iloc[0]["realized_pnl"]), -6.0)

    def test_resolved_winner_without_recent_redeem_moves_unrealized_to_realized(self) -> None:
        conn = ct.connect(self.db_path)
        try:
            ct.apply_paper_trade(conn, source_trade(price=0.5, size=2000.0), self.settings)
            conn.commit()
        finally:
            conn.close()

        before = ct.value_paper_portfolio(db_path=self.db_path, price_lookup=lambda _: 0.8)
        self.assertAlmostEqual(before.unrealized_pnl, 6.0)

        with patch("src.copy_trading.fetch_source_activity", return_value=pd.DataFrame()), patch(
            "src.copy_trading.fetch_closed_position_assets", return_value={"market-1": {"asset-1"}}
        ), patch("src.copy_trading.fetch_position_metadata", return_value={}):
            result = ct.sync_settlement_activity(ct.COPY_TARGET_WALLET, settings=self.settings, db_path=self.db_path)

        snapshot = ct.value_paper_portfolio(db_path=self.db_path)
        orders = ct.get_paper_orders(db_path=self.db_path)
        settled = orders[orders["status"] == "settled"]
        self.assertEqual(result.copied, 1)
        self.assertTrue(snapshot.positions.empty)
        self.assertAlmostEqual(snapshot.cash, 1010.0)
        self.assertAlmostEqual(snapshot.realized_pnl, 10.0)
        self.assertAlmostEqual(snapshot.unrealized_pnl, 0.0)
        self.assertEqual(str(settled.iloc[0]["reason"]), "resolution_winner_payout")

    def test_resolved_loser_without_recent_redeem_moves_unrealized_loss_to_realized(self) -> None:
        conn = ct.connect(self.db_path)
        try:
            ct.apply_paper_trade(conn, source_trade(asset="no-token", outcome="No", price=0.6, size=1000.0), self.settings)
            conn.commit()
        finally:
            conn.close()

        before = ct.value_paper_portfolio(db_path=self.db_path, price_lookup=lambda _: 0.0)
        self.assertAlmostEqual(before.unrealized_pnl, -6.0)

        with patch("src.copy_trading.fetch_source_activity", return_value=pd.DataFrame()), patch(
            "src.copy_trading.fetch_closed_position_assets", return_value={"market-1": {"yes-token"}}
        ), patch("src.copy_trading.fetch_position_metadata", return_value={}):
            result = ct.sync_settlement_activity(ct.COPY_TARGET_WALLET, settings=self.settings, db_path=self.db_path)

        snapshot = ct.value_paper_portfolio(db_path=self.db_path)
        orders = ct.get_paper_orders(db_path=self.db_path)
        settled = orders[orders["status"] == "settled"]
        self.assertEqual(result.copied, 1)
        self.assertTrue(snapshot.positions.empty)
        self.assertAlmostEqual(snapshot.cash, 994.0)
        self.assertAlmostEqual(snapshot.realized_pnl, -6.0)
        self.assertAlmostEqual(snapshot.unrealized_pnl, 0.0)
        self.assertEqual(str(settled.iloc[0]["reason"]), "resolution_loser_loss")

    def test_closed_market_fallback_realizes_loser_without_tony_winner_row(self) -> None:
        conn = ct.connect(self.db_path)
        try:
            ct.apply_paper_trade(conn, source_trade(asset="no-token", outcome="No", price=0.6, size=1000.0), self.settings)
            conn.commit()
        finally:
            conn.close()

        with patch("src.copy_trading.fetch_source_activity", return_value=pd.DataFrame()), patch(
            "src.copy_trading.fetch_closed_position_assets", return_value={}
        ), patch("src.copy_trading.fetch_closed_market_winner_assets", return_value={"market-1": {"yes-token"}}), patch(
            "src.copy_trading.fetch_position_metadata", return_value={}
        ):
            result = ct.sync_settlement_activity(ct.COPY_TARGET_WALLET, settings=self.settings, db_path=self.db_path)

        snapshot = ct.value_paper_portfolio(db_path=self.db_path)
        orders = ct.get_paper_orders(db_path=self.db_path)
        loss_rows = orders[orders["reason"] == "resolution_loser_loss"]
        self.assertEqual(result.copied, 1)
        self.assertTrue(snapshot.positions.empty)
        self.assertAlmostEqual(snapshot.cash, 994.0)
        self.assertAlmostEqual(snapshot.realized_pnl, -6.0)
        self.assertEqual(len(loss_rows), 1)

    def test_redeem_resolution_moves_unrealized_pair_to_realized(self) -> None:
        activity = pd.DataFrame(
            [
                {
                    "type": "REDEEM",
                    "conditionId": "market-1",
                    "transactionHash": "0xredeem-pair",
                    "timestamp": 1779900100,
                    "size": 1000.0,
                    "usdcSize": 1000.0,
                    "title": "Example market",
                }
            ]
        )
        conn = ct.connect(self.db_path)
        try:
            ct.apply_paper_trade(conn, source_trade(tx="0xyes", asset="yes-token", price=0.4, size=1000.0), self.settings)
            ct.apply_paper_trade(conn, source_trade(tx="0xno", asset="no-token", outcome="No", price=0.6, size=1000.0), self.settings)
            conn.commit()
        finally:
            conn.close()

        with patch("src.copy_trading.fetch_source_activity", return_value=activity), patch(
            "src.copy_trading.fetch_closed_position_assets", return_value={"market-1": {"yes-token"}}
        ), patch("src.copy_trading.fetch_position_metadata", return_value={}):
            result = ct.sync_settlement_activity(ct.COPY_TARGET_WALLET, settings=self.settings, db_path=self.db_path)

        snapshot = ct.value_paper_portfolio(db_path=self.db_path)
        self.assertEqual(result.copied, 2)
        self.assertTrue(snapshot.positions.empty)
        self.assertAlmostEqual(snapshot.cash, 1000.0)
        self.assertAlmostEqual(snapshot.realized_pnl, 0.0)
        self.assertAlmostEqual(snapshot.unrealized_pnl, 0.0)

    def test_settlement_sync_reconciles_loser_even_when_redeem_is_duplicate(self) -> None:
        source = {
            "type": "REDEEM",
            "conditionId": "market-1",
            "transactionHash": "0xold-redeem",
            "timestamp": 1779900100,
            "size": 1000.0,
            "usdcSize": 1000.0,
            "title": "Example market",
        }
        activity = pd.DataFrame([source])
        conn = ct.connect(self.db_path)
        try:
            ct.apply_paper_trade(conn, source_trade(tx="0xno", asset="no-token", outcome="No", price=0.6, size=1000.0), self.settings)
            parsed = ct.parse_settlement_activity(source, ct.COPY_TARGET_WALLET)
            old_order = ct.PaperOrder(parsed["dedup_key"], "skipped", "redeem_no_paper_position", parsed["side"], parsed["source_notional"])
            ct._insert_order(conn, parsed, old_order, source)
            conn.commit()
        finally:
            conn.close()

        with patch("src.copy_trading.fetch_source_activity", return_value=activity), patch(
            "src.copy_trading.fetch_closed_position_assets", return_value={"market-1": {"yes-token"}}
        ), patch("src.copy_trading.fetch_position_metadata", return_value={}):
            result = ct.sync_settlement_activity(ct.COPY_TARGET_WALLET, settings=self.settings, db_path=self.db_path)

        snapshot = ct.value_paper_portfolio(db_path=self.db_path)
        orders = ct.get_paper_orders(db_path=self.db_path)
        loss_rows = orders[orders["reason"] == "resolution_loser_loss"]
        self.assertEqual(result.copied, 1)
        self.assertTrue(snapshot.positions.empty)
        self.assertAlmostEqual(snapshot.realized_pnl, -6.0)
        self.assertEqual(len(loss_rows), 1)

    def test_merge_recycles_complete_set_to_cash(self) -> None:
        activity = pd.DataFrame(
            [
                {
                    "type": "MERGE",
                    "conditionId": "market-1",
                    "transactionHash": "0xmerge",
                    "timestamp": 1779900100,
                    "size": 1000.0,
                    "usdcSize": 1000.0,
                    "title": "Example market",
                }
            ]
        )
        conn = ct.connect(self.db_path)
        try:
            ct.apply_paper_trade(conn, source_trade(tx="0xyes", asset="yes-token", price=0.4, size=1000.0), self.settings)
            ct.apply_paper_trade(conn, source_trade(tx="0xno", asset="no-token", price=0.6, size=1000.0), self.settings)
            conn.commit()
        finally:
            conn.close()

        with patch("src.copy_trading.fetch_source_activity", return_value=activity), patch(
            "src.copy_trading.fetch_closed_position_assets", return_value={}
        ), patch(
            "src.copy_trading.fetch_closed_market_winner_assets", return_value={}
        ), patch("src.copy_trading.fetch_position_metadata", return_value={}):
            result = ct.sync_settlement_activity(ct.COPY_TARGET_WALLET, settings=self.settings, db_path=self.db_path)

        snapshot = ct.value_paper_portfolio(db_path=self.db_path)
        self.assertEqual(result.copied, 1)
        self.assertTrue(snapshot.positions.empty)
        self.assertAlmostEqual(snapshot.cash, 1000.0)
        self.assertAlmostEqual(snapshot.realized_pnl, 0.0)


if __name__ == "__main__":
    unittest.main()
