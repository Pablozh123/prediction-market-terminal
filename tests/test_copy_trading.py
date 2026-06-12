import sqlite3
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

    def test_min_copy_notional_can_be_disabled_for_tiny_paper_buys(self) -> None:
        conn = ct.connect(self.db_path)
        try:
            default_order = ct.apply_paper_trade(conn, source_trade(tx="0xtiny1", price=0.5, size=1.0), self.settings)
            zero_min_order = ct.apply_paper_trade(
                conn,
                source_trade(tx="0xtiny2", price=0.5, size=1.0),
                ct.CopySettings(trade_limit=20, min_copy_notional=0.0),
            )
        finally:
            conn.close()

        self.assertEqual(default_order.status, "skipped")
        self.assertEqual(default_order.reason, "below_min_copy_notional")
        self.assertEqual(zero_min_order.status, "copied")
        self.assertEqual(zero_min_order.reason, "buy_scaled")
        self.assertAlmostEqual(zero_min_order.copy_notional, 0.005)
        self.assertAlmostEqual(zero_min_order.copy_size, 0.01)

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

    def test_dynamic_wallet_sizing_multiplier_scales_portfolio_percent(self) -> None:
        conn = ct.connect(self.db_path)
        try:
            ct._set_meta(conn, "tony_visible_equity", "200000")
            settings = ct.CopySettings(trade_limit=20, dynamic_sizing_multiplier=2.0, dynamic_scale_max=0.05)
            order = ct.apply_paper_trade(conn, source_trade(price=0.5, size=2000.0), settings)
            sizing = ct.get_dynamic_sizing_snapshot(conn=conn)
        finally:
            conn.close()

        self.assertEqual(order.status, "copied")
        self.assertAlmostEqual(order.copy_notional, 10.0)
        self.assertAlmostEqual(float(sizing["effective_copy_scale"]), 0.01)
        self.assertAlmostEqual(float(sizing["dynamic_sizing_multiplier"]), 2.0)

    def test_copy_settings_round_trip_persists_dynamic_sizing_options(self) -> None:
        path = Path(self.tmp.name) / "copy_settings.json"
        settings = ct.CopySettings(
            dynamic_sizing_enabled=True,
            dynamic_sizing_multiplier=1.75,
            copy_scale=0.02,
            dynamic_scale_max=0.08,
            max_order_equity_pct=0.12,
            min_copy_notional=0.0,
        )

        ct.save_copy_settings(settings, path=path)
        loaded = ct.load_copy_settings(path=path)

        self.assertTrue(loaded.dynamic_sizing_enabled)
        self.assertAlmostEqual(loaded.dynamic_sizing_multiplier, 1.75)
        self.assertAlmostEqual(loaded.copy_scale, 0.02)
        self.assertAlmostEqual(loaded.dynamic_scale_max, 0.08)
        self.assertAlmostEqual(loaded.max_order_equity_pct, 0.12)
        self.assertAlmostEqual(loaded.min_copy_notional, 0.0)

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
        settings = ct.CopySettings(trade_limit=20, auto_top_up_enabled=False)
        conn = ct.connect(self.db_path)
        try:
            conn.execute("UPDATE traders SET cash = 0 WHERE wallet = ?", (ct.COPY_TARGET_WALLET,))
            order = ct.apply_paper_trade(conn, source_trade(), settings)
            snapshot = ct.value_paper_portfolio(conn=conn)
        finally:
            conn.close()

        self.assertEqual(order.status, "skipped")
        self.assertEqual(order.reason, "insufficient_cash")
        self.assertAlmostEqual(snapshot.cash, 0.0)

    def test_auto_top_up_when_cash_is_empty_then_copies_buy(self) -> None:
        conn = ct.connect(self.db_path)
        try:
            conn.execute("UPDATE traders SET cash = 0 WHERE wallet = ?", (ct.COPY_TARGET_WALLET,))
            order = ct.apply_paper_trade(conn, source_trade(), self.settings)
            snapshot = ct.value_paper_portfolio(conn=conn)
            cash_events = ct.get_cash_events(conn=conn)
        finally:
            conn.close()

        self.assertEqual(order.status, "copied")
        self.assertEqual(order.reason, "buy_scaled")
        self.assertAlmostEqual(order.copy_notional, 10.0)
        self.assertAlmostEqual(snapshot.cash, 990.0)
        self.assertEqual(len(cash_events), 1)
        self.assertEqual(str(cash_events.iloc[0]["reason"]), "auto_copy_cash_top_up")
        self.assertEqual(str(cash_events.iloc[0]["trader_wallet"]), ct.COPY_TARGET_WALLET)
        self.assertAlmostEqual(float(cash_events.iloc[0]["amount"]), 1000.0)

    def test_auto_top_up_after_buy_drains_cash(self) -> None:
        settings = ct.CopySettings(trade_limit=20, max_order_equity_pct=1.0)
        conn = ct.connect(self.db_path)
        try:
            conn.execute("UPDATE traders SET cash = 10 WHERE wallet = ?", (ct.COPY_TARGET_WALLET,))
            order = ct.apply_paper_trade(conn, source_trade(), settings)
            snapshot = ct.value_paper_portfolio(conn=conn)
            cash_events = ct.get_cash_events(conn=conn)
        finally:
            conn.close()

        self.assertEqual(order.status, "copied")
        self.assertAlmostEqual(order.copy_notional, 10.0)
        self.assertAlmostEqual(snapshot.cash, 1000.0)
        self.assertEqual(len(cash_events), 1)
        self.assertEqual(str(cash_events.iloc[0]["reason"]), "auto_copy_cash_top_up")
        self.assertEqual(str(cash_events.iloc[0]["trader_wallet"]), ct.COPY_TARGET_WALLET)

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


def _make_legacy_db(path: Path, cash: float = 987.5, start_cash: float = 1000.0) -> None:
    """Create a pre-multi-trader database (no ``trader_wallet`` columns)."""
    conn = sqlite3.connect(path)
    try:
        conn.executescript(
            """
            CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE positions (
                asset TEXT PRIMARY KEY, market_key TEXT, title TEXT, outcome TEXT,
                shares REAL NOT NULL, avg_price REAL NOT NULL, cost_basis REAL NOT NULL,
                last_price REAL NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE tony_positions (
                asset TEXT PRIMARY KEY, market_key TEXT, title TEXT, outcome TEXT,
                shares REAL NOT NULL, avg_price REAL, last_price REAL,
                seeded_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE cash_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT, event_time TEXT NOT NULL,
                amount REAL NOT NULL, cash_before REAL NOT NULL, cash_after REAL NOT NULL,
                reason TEXT NOT NULL, note TEXT
            );
            """
        )
        conn.execute("INSERT INTO meta (key, value) VALUES ('cash', ?)", (f"{cash:.10f}",))
        conn.execute("INSERT INTO meta (key, value) VALUES ('paper_start_cash', ?)", (f"{start_cash:.10f}",))
        conn.execute(
            "INSERT INTO positions (asset, market_key, title, outcome, shares, avg_price, cost_basis, last_price, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("asset-1", "market-1", "Example market", "Yes", 10.0, 0.5, 5.0, 0.5, "2026-05-30T00:00:00+00:00"),
        )
        conn.execute(
            "INSERT INTO tony_positions (asset, market_key, title, outcome, shares, avg_price, last_price, seeded_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("asset-1", "market-1", "Example market", "Yes", 1000.0, 0.5, 0.5, "2026-05-30T00:00:00+00:00", "2026-05-30T00:00:00+00:00"),
        )
        conn.execute(
            "INSERT INTO cash_events (event_time, amount, cash_before, cash_after, reason, note) VALUES (?, ?, ?, ?, ?, ?)",
            ("2026-05-30T00:00:00+00:00", -12.5, 1000.0, 987.5, "buy", ""),
        )
        conn.commit()
    finally:
        conn.close()


class SchemaMigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "copy.sqlite"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_fresh_db_creates_multitrader_schema(self) -> None:
        conn = ct.connect(self.db_path)
        try:
            tables = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()}
            position_cols = ct._table_columns(conn, "positions")
            cash_cols = ct._table_columns(conn, "cash_events")
            source_pk = [row["name"] for row in conn.execute("PRAGMA table_info(source_positions)").fetchall() if row["pk"]]
        finally:
            conn.close()

        self.assertTrue({"traders", "source_positions", "trader_stats"} <= tables)
        self.assertIn("trader_wallet", position_cols)
        self.assertIn("trader_wallet", cash_cols)
        self.assertEqual(set(source_pk), {"wallet", "asset"})

    def test_fresh_db_seeds_swisstony_as_first_trader(self) -> None:
        traders = ct.get_traders(db_path=self.db_path)

        self.assertEqual(len(traders), 1)
        row = traders.iloc[0]
        self.assertEqual(str(row["wallet"]), ct.COPY_TARGET_WALLET)
        self.assertEqual(str(row["label"]), ct.SWISSTONY_LABEL)
        self.assertEqual(int(row["active"]), 1)
        self.assertAlmostEqual(float(row["cash"]), 1000.0)
        self.assertAlmostEqual(float(row["start_cash"]), 1000.0)

    def test_legacy_db_is_migrated_to_sub_portfolios(self) -> None:
        _make_legacy_db(self.db_path)

        conn = ct.connect(self.db_path)
        try:
            position_cols = ct._table_columns(conn, "positions")
            cash_cols = ct._table_columns(conn, "cash_events")
            pos_wallet = conn.execute("SELECT trader_wallet FROM positions WHERE asset = 'asset-1'").fetchone()["trader_wallet"]
            cash_wallet = conn.execute("SELECT trader_wallet FROM cash_events LIMIT 1").fetchone()["trader_wallet"]
            source = conn.execute("SELECT * FROM source_positions WHERE asset = 'asset-1'").fetchone()
            trader = conn.execute("SELECT * FROM traders WHERE wallet = ?", (ct.COPY_TARGET_WALLET,)).fetchone()
        finally:
            conn.close()

        self.assertIn("trader_wallet", position_cols)
        self.assertIn("trader_wallet", cash_cols)
        self.assertEqual(str(pos_wallet), ct.COPY_TARGET_WALLET)
        self.assertEqual(str(cash_wallet), ct.COPY_TARGET_WALLET)
        self.assertIsNotNone(source)
        self.assertEqual(str(source["wallet"]), ct.COPY_TARGET_WALLET)
        self.assertAlmostEqual(float(source["shares"]), 1000.0)
        self.assertIsNotNone(trader)
        self.assertAlmostEqual(float(trader["cash"]), 987.5)
        self.assertAlmostEqual(float(trader["start_cash"]), 1000.0)

    def test_legacy_trade_dedup_keys_get_wallet_prefixed(self) -> None:
        legacy_key = "0xtx|asset-1|BUY|10.00000000|0.50000000|1779900000"
        conn = ct.connect(self.db_path)
        try:
            conn.execute(
                "INSERT INTO paper_orders (dedup_key, source_wallet, status, reason, source_side, created_at)"
                " VALUES (?, ?, 'copied', 'buy_scaled', 'BUY', ?)",
                (legacy_key, ct.COPY_TARGET_WALLET, ct.utc_now()),
            )
            conn.execute("DELETE FROM meta WHERE key = 'trade_dedup_wallet_prefixed_at'")
            conn.commit()
        finally:
            conn.close()

        conn = ct.connect(self.db_path)
        try:
            migrated = conn.execute("SELECT dedup_key FROM paper_orders").fetchone()["dedup_key"]
        finally:
            conn.close()

        self.assertEqual(str(migrated), f"{ct.COPY_TARGET_WALLET}|{legacy_key}")

    def test_migration_is_idempotent(self) -> None:
        _make_legacy_db(self.db_path)
        ct.connect(self.db_path).close()

        conn = ct.connect(self.db_path)
        try:
            trader_count = conn.execute("SELECT COUNT(*) AS n FROM traders").fetchone()["n"]
            source_count = conn.execute("SELECT COUNT(*) AS n FROM source_positions").fetchone()["n"]
        finally:
            conn.close()

        self.assertEqual(int(trader_count), 1)
        self.assertEqual(int(source_count), 1)


class MultiTraderPlumbingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "copy.sqlite"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_active_trader_wallets_lists_active_in_follow_order(self) -> None:
        conn = ct.connect(self.db_path)
        try:
            conn.execute("DELETE FROM traders")
            conn.execute(
                "INSERT INTO traders (wallet, label, active, start_cash, cash, rank_score, added_at, updated_at)"
                " VALUES ('0xaaa', 'First', 1, 1000, 1000, 0, '2026-05-31T00:00:01+00:00', '2026-05-31T00:00:01+00:00')"
            )
            conn.execute(
                "INSERT INTO traders (wallet, label, active, start_cash, cash, rank_score, added_at, updated_at)"
                " VALUES ('0xbbb', 'Paused', 0, 1000, 1000, 0, '2026-05-31T00:00:02+00:00', '2026-05-31T00:00:02+00:00')"
            )
            conn.execute(
                "INSERT INTO traders (wallet, label, active, start_cash, cash, rank_score, added_at, updated_at)"
                " VALUES ('0xccc', 'Third', 1, 1000, 1000, 0, '2026-05-31T00:00:03+00:00', '2026-05-31T00:00:03+00:00')"
            )
            conn.commit()
            wallets = ct.active_trader_wallets(conn=conn)
        finally:
            conn.close()

        self.assertEqual(wallets, ["0xaaa", "0xccc"])
        self.assertNotIn("0xbbb", wallets)

    def test_active_trader_wallets_falls_back_to_default(self) -> None:
        conn = ct.connect(self.db_path)
        try:
            conn.execute("DELETE FROM traders")
            conn.commit()
            wallets = ct.active_trader_wallets(conn=conn)
        finally:
            conn.close()

        self.assertEqual(wallets, [ct.COPY_TARGET_WALLET])

    def test_seed_source_positions_is_wallet_scoped_and_upserts(self) -> None:
        positions = pd.DataFrame(
            [{"asset": "asset-1", "size": 1000.0, "market_key": "market-1", "title": "Example", "outcome": "Yes", "avg_price": 0.5, "current_price": 0.6}]
        )
        updated = pd.DataFrame(
            [{"asset": "asset-1", "size": 1500.0, "market_key": "market-1", "title": "Example", "outcome": "Yes", "avg_price": 0.5, "current_price": 0.7}]
        )
        conn = ct.connect(self.db_path)
        try:
            first = ct.seed_source_positions(conn, "0xwhale", positions)
            second = ct.seed_source_positions(conn, "0xwhale", updated)
            conn.commit()
            rows = conn.execute("SELECT * FROM source_positions WHERE wallet = '0xwhale'").fetchall()
        finally:
            conn.close()

        self.assertEqual(first, 1)
        self.assertEqual(second, 1)
        self.assertEqual(len(rows), 1)
        self.assertEqual(str(rows[0]["asset"]), "asset-1")
        self.assertAlmostEqual(float(rows[0]["shares"]), 1500.0)


class MultiTraderEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "copy.sqlite"
        ct.reset_paper_portfolio(db_path=self.db_path)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _add_trader(self, conn: sqlite3.Connection, wallet: str) -> None:
        conn.execute(
            "INSERT OR IGNORE INTO traders (wallet, label, active, start_cash, cash, rank_score, added_at, updated_at)"
            " VALUES (?, ?, 1, 1000, 1000, 0, '2026-05-31T00:00:05+00:00', '2026-05-31T00:00:05+00:00')",
            (wallet, "Whale"),
        )

    def test_buys_are_booked_into_separate_sub_accounts(self) -> None:
        conn = ct.connect(self.db_path)
        try:
            self._add_trader(conn, "0xwhale")
            tony_settings = ct.CopySettings(trade_limit=20)
            whale_settings = ct.CopySettings(trade_limit=20, target_wallet="0xwhale")
            ct.apply_paper_trade(conn, source_trade(tx="0xtony", asset="asset-1", price=0.5, size=2000.0), tony_settings)
            ct.apply_paper_trade(conn, source_trade(tx="0xwhale", asset="asset-1", price=0.5, size=2000.0), whale_settings)
            conn.commit()
            rows = conn.execute("SELECT trader_wallet, asset FROM positions WHERE asset = 'asset-1'").fetchall()
            tony_pos = ct._get_position(conn, ct.COPY_TARGET_WALLET, "asset-1")
            whale_pos = ct._get_position(conn, "0xwhale", "asset-1")
        finally:
            conn.close()

        self.assertEqual(len(rows), 2)
        self.assertIsNotNone(tony_pos)
        self.assertIsNotNone(whale_pos)
        self.assertAlmostEqual(float(tony_pos["shares"]), 20.0)
        self.assertAlmostEqual(float(whale_pos["shares"]), 20.0)

    def test_sub_account_sell_only_touches_its_own_position(self) -> None:
        conn = ct.connect(self.db_path)
        try:
            self._add_trader(conn, "0xwhale")
            tony_settings = ct.CopySettings(trade_limit=20)
            whale_settings = ct.CopySettings(trade_limit=20, target_wallet="0xwhale")
            ct.apply_paper_trade(conn, source_trade(tx="0xtony", asset="asset-1", price=0.4, size=1000.0), tony_settings)
            ct.apply_paper_trade(conn, source_trade(tx="0xwhale", asset="asset-1", price=0.4, size=1000.0), whale_settings)
            # Whale sells half of its source position; Tony's sub-account must be untouched.
            ct.apply_paper_trade(conn, source_trade(tx="0xwhalesell", asset="asset-1", side="SELL", price=0.6, size=500.0), whale_settings)
            conn.commit()
            tony_pos = ct._get_position(conn, ct.COPY_TARGET_WALLET, "asset-1")
            whale_pos = ct._get_position(conn, "0xwhale", "asset-1")
        finally:
            conn.close()

        self.assertAlmostEqual(float(tony_pos["shares"]), 10.0)
        self.assertAlmostEqual(float(whale_pos["shares"]), 5.0)

    def test_sub_account_cash_is_isolated(self) -> None:
        conn = ct.connect(self.db_path)
        try:
            self._add_trader(conn, "0xwhale")
            tony_settings = ct.CopySettings(trade_limit=20)
            whale_settings = ct.CopySettings(trade_limit=20, target_wallet="0xwhale")
            ct.apply_paper_trade(conn, source_trade(tx="0xt", asset="a1", price=0.5, size=2000.0), tony_settings)
            ct.apply_paper_trade(conn, source_trade(tx="0xw", asset="a2", price=0.5, size=4000.0), whale_settings)
            conn.commit()
            tony_cash = ct._get_trader_cash(conn, ct.COPY_TARGET_WALLET, 0.0)
            whale_cash = ct._get_trader_cash(conn, "0xwhale", 0.0)
            total_cash = ct.value_paper_portfolio(conn=conn).cash
            tony_equity = ct.value_sub_account(ct.COPY_TARGET_WALLET, conn=conn).equity
        finally:
            conn.close()

        self.assertAlmostEqual(tony_cash, 990.0)
        self.assertAlmostEqual(whale_cash, 980.0)
        self.assertAlmostEqual(total_cash, 1970.0)
        self.assertAlmostEqual(tony_equity, 1000.0)

    def test_dynamic_sizing_uses_per_wallet_source_stats(self) -> None:
        conn = ct.connect(self.db_path)
        try:
            self._add_trader(conn, "0xwhale")
            # Swisstony is sized off the legacy global stat; whale off its own.
            ct._set_meta(conn, "tony_visible_equity", "200000")
            ct._set_meta(conn, "wallet_stat:0xwhale:visible_equity", "100000")
            tony_settings = ct.CopySettings(trade_limit=20)
            whale_settings = ct.CopySettings(trade_limit=20, target_wallet="0xwhale")
            tony_order = ct.apply_paper_trade(conn, source_trade(tx="0xt", asset="a1", price=0.5, size=2000.0), tony_settings)
            whale_order = ct.apply_paper_trade(conn, source_trade(tx="0xw", asset="a2", price=0.5, size=2000.0), whale_settings)
            conn.commit()
        finally:
            conn.close()

        self.assertEqual(tony_order.status, "copied")
        self.assertEqual(whale_order.status, "copied")
        self.assertAlmostEqual(tony_order.copy_notional, 5.0)
        self.assertAlmostEqual(whale_order.copy_notional, 10.0)

    def test_same_trade_for_different_wallets_is_not_cross_deduped(self) -> None:
        conn = ct.connect(self.db_path)
        try:
            self._add_trader(conn, "0xwhale")
            tony_settings = ct.CopySettings(trade_limit=20)
            whale_settings = ct.CopySettings(trade_limit=20, target_wallet="0xwhale")
            # Identical trade fields including an empty tx hash; only the wallet differs.
            trade = source_trade(tx="", asset="asset-1", price=0.5, size=2000.0)
            tony_order = ct.apply_paper_trade(conn, dict(trade), tony_settings)
            whale_order = ct.apply_paper_trade(conn, dict(trade), whale_settings)
            conn.commit()
        finally:
            conn.close()

        self.assertEqual(tony_order.status, "copied")
        self.assertEqual(whale_order.status, "copied")
        self.assertNotEqual(tony_order.dedup_key, whale_order.dedup_key)

    def test_aggregate_sync_results_sums_fields(self) -> None:
        combined = ct.aggregate_sync_results(
            {
                "0xa": ct.SyncResult(processed=2, copied=1, skipped=1, duplicates=0, errors=("e1",)),
                "0xb": ct.SyncResult(processed=3, copied=2, skipped=1, duplicates=1, errors=("e2",)),
            }
        )
        self.assertEqual(combined.processed, 5)
        self.assertEqual(combined.copied, 3)
        self.assertEqual(combined.skipped, 2)
        self.assertEqual(combined.duplicates, 1)
        self.assertEqual(set(combined.errors), {"e1", "e2"})
        self.assertEqual(ct.aggregate_sync_results({}).processed, 0)

    def test_sync_active_copy_trades_iterates_active_traders(self) -> None:
        conn = ct.connect(self.db_path)
        try:
            self._add_trader(conn, "0xwhale")
            conn.commit()
        finally:
            conn.close()

        calls: list[tuple[str, str]] = []

        def fake_sync(wallet, settings=None, db_path=None):
            calls.append((wallet, settings.target_wallet))
            return ct.SyncResult(processed=1)

        with patch("src.copy_trading.sync_copy_trades", side_effect=fake_sync):
            results = ct.sync_active_copy_trades(db_path=self.db_path)

        self.assertEqual(set(results.keys()), {ct.COPY_TARGET_WALLET, "0xwhale"})
        self.assertIn((ct.COPY_TARGET_WALLET, ct.COPY_TARGET_WALLET), calls)
        self.assertIn(("0xwhale", "0xwhale"), calls)


def _leaderboard_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"wallet": "0xskill", "pnl": 5000.0, "volume": 10000.0, "win_rate": 0.70, "is_bot": False, "open_positions": 60},
            {"wallet": "0xwhale", "pnl": 9000.0, "volume": 90000.0, "win_rate": 0.55, "is_bot": False, "open_positions": 120},
            {"wallet": "0xloser", "pnl": -2000.0, "volume": 8000.0, "win_rate": 0.30, "is_bot": False, "open_positions": 20},
            {"wallet": "0xtiny", "pnl": 100.0, "volume": 500.0, "win_rate": 0.90, "is_bot": False, "open_positions": 5},
            {"wallet": "0xbot", "pnl": 8000.0, "volume": 20000.0, "win_rate": 0.80, "is_bot": True, "open_positions": 200},
        ]
    )


class TraderDiscoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "copy.sqlite"
        ct.reset_paper_portfolio(db_path=self.db_path)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_compute_roi(self) -> None:
        self.assertAlmostEqual(ct.compute_roi(5000.0, 10000.0), 0.5)
        self.assertAlmostEqual(ct.compute_roi(100.0, 0.0), 0.0)

    def test_rank_traders_by_roi_applies_thresholds_and_orders(self) -> None:
        ranked = ct.rank_traders_by_roi(_leaderboard_df())

        self.assertEqual(ranked["wallet"].tolist(), ["0xskill", "0xwhale"])
        self.assertAlmostEqual(float(ranked.iloc[0]["roi"]), 0.5)
        self.assertAlmostEqual(float(ranked.iloc[0]["rank_score"]), 0.5)
        self.assertAlmostEqual(float(ranked.iloc[1]["roi"]), 0.1)

    def test_rank_traders_by_smart_score_exposes_polyhuntr_style_factors(self) -> None:
        leaderboard = _leaderboard_df().assign(
            recent_trades=[12, 3, 20, 1, 50],
            recent_notional=[5000.0, 2000.0, 4000.0, 100.0, 10000.0],
            trades_per_hour=[1.5, 0.2, 2.0, 0.1, 8.0],
            positions_value=[2500.0, 80000.0, 0.0, 50.0, 5000.0],
            cash_balance=[2500.0, 10000.0, 0.0, 50.0, 5000.0],
            closed_positions=[40, 30, 20, 5, 100],
            bot_score=[10, 20, 5, 0, 95],
        )

        ranked = ct.rank_traders_by_smart_score(leaderboard)

        self.assertEqual(ranked.iloc[0]["wallet"], "0xskill")
        self.assertEqual(ranked["wallet"].tolist(), ["0xskill", "0xwhale"])
        for column in [
            "copy_smart_score",
            "copy_return_score",
            "copy_sharpe_proxy",
            "copy_drawdown_proxy",
            "copy_win_score",
            "copy_recency_score",
            "copy_volume_score",
            "copy_rank_reason",
            "copy_grade",
        ]:
            self.assertIn(column, ranked.columns)
        self.assertGreaterEqual(float(ranked.iloc[0]["copy_smart_score"]), float(ranked.iloc[1]["copy_smart_score"]))
        self.assertIn("return", str(ranked.iloc[0]["copy_rank_reason"]))

    def test_rank_traders_by_smart_score_pushes_negative_returns_down_when_allowed(self) -> None:
        ranked = ct.rank_traders_by_smart_score(_leaderboard_df(), require_positive_roi=False, min_volume=1000.0)

        self.assertIn("0xloser", ranked["wallet"].tolist())
        loser_score = float(ranked.loc[ranked["wallet"].eq("0xloser"), "copy_smart_score"].iloc[0])
        skill_score = float(ranked.loc[ranked["wallet"].eq("0xskill"), "copy_smart_score"].iloc[0])
        self.assertLess(loser_score, skill_score)

    def test_follow_and_unfollow_trader(self) -> None:
        added = ct.follow_trader("0xnew", label="New", db_path=self.db_path)
        re_followed = ct.follow_trader("0xnew", db_path=self.db_path)
        active_after_follow = ct.active_trader_wallets(db_path=self.db_path)
        changed = ct.unfollow_trader("0xnew", db_path=self.db_path)
        active_after_unfollow = ct.active_trader_wallets(db_path=self.db_path)
        no_change = ct.unfollow_trader("0xnew", db_path=self.db_path)

        self.assertTrue(added)
        self.assertFalse(re_followed)
        self.assertIn("0xnew", active_after_follow)
        self.assertTrue(changed)
        self.assertNotIn("0xnew", active_after_unfollow)
        self.assertFalse(no_change)

    def test_follow_trader_normalizes_wallet_case(self) -> None:
        mixed = "0xAbCdEf0000000000000000000000000000001234"
        lower = mixed.lower()
        added = ct.follow_trader(mixed, db_path=self.db_path)
        active = ct.active_trader_wallets(db_path=self.db_path)

        self.assertTrue(added)
        self.assertIn(lower, active)
        self.assertNotIn(mixed, active)
        # unfollow with the mixed-case form still matches the stored lowercase row
        self.assertTrue(ct.unfollow_trader(mixed, db_path=self.db_path))
        self.assertNotIn(lower, ct.active_trader_wallets(db_path=self.db_path))

    def test_refresh_trader_stats_persists_and_mirrors_rank_score(self) -> None:
        ranked = ct.rank_traders_by_roi(_leaderboard_df())
        conn = ct.connect(self.db_path)
        try:
            ct.follow_trader("0xskill", conn=conn)
            count = ct.refresh_trader_stats(conn, ranked)
            conn.commit()
            stats = ct.get_trader_stats(conn=conn)
            skill = conn.execute("SELECT rank_score FROM traders WHERE wallet = '0xskill'").fetchone()
        finally:
            conn.close()

        self.assertEqual(count, 2)
        self.assertEqual(set(stats["wallet"]), {"0xskill", "0xwhale"})
        self.assertEqual(str(stats.iloc[0]["wallet"]), "0xskill")
        self.assertAlmostEqual(float(stats.iloc[0]["roi"]), 0.5)
        self.assertAlmostEqual(float(skill["rank_score"]), 0.5)


def rtds_message(
    *,
    wallet: str = ct.COPY_TARGET_WALLET,
    tx: str = "0xws1",
    asset: str = "asset-ws",
    side: str = "BUY",
    price: float = 0.4,
    size: float = 500.0,
    timestamp: int = 1779900100,
    as_list: bool = False,
) -> dict:
    payload = {
        "proxyWallet": wallet,
        "side": side,
        "asset": asset,
        "conditionId": "cond-ws",
        "price": price,
        "size": size,
        "timestamp": timestamp,
        "title": "WS market",
        "outcome": "Yes",
        "transactionHash": tx,
        "eventSlug": "ws-market",
    }
    return {"topic": "activity", "type": "trades", "payload": [payload] if as_list else payload}


class WsDetectionTests(unittest.TestCase):
    """RTDS WebSocket detection: decode, listener dedup, apply, cross-path dedup."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "copy.sqlite"
        self.settings = ct.CopySettings(trade_limit=20)
        ct.reset_paper_portfolio(db_path=self.db_path)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _seed(self, baseline_cutoff: int = 0) -> None:
        conn = ct.connect(self.db_path)
        try:
            ct._set_meta(conn, "tony_seeded_at", ct.utc_now())
            ct._set_meta(conn, "baseline_cutoff_ts", str(baseline_cutoff))
            conn.commit()
        finally:
            conn.close()

    def test_subscribe_payload_targets_global_trade_firehose(self) -> None:
        payload = ct.rtds_subscribe_payload()
        self.assertEqual(payload["action"], "subscribe")
        self.assertEqual(payload["subscriptions"], [{"topic": "activity", "type": "trades", "filters": ""}])

    def test_decode_rtds_trade_matches_target_wallet(self) -> None:
        trade = ct.decode_rtds_trade(rtds_message(), [ct.COPY_TARGET_WALLET])
        self.assertIsNotNone(trade)
        self.assertEqual(trade["source"], "rtds_ws")
        self.assertEqual(trade["side"], "BUY")
        self.assertEqual(trade["asset"], "asset-ws")
        self.assertEqual(trade["transaction_hash"], "0xws1")
        self.assertEqual(trade["market_key"], "cond-ws")
        self.assertAlmostEqual(trade["price"], 0.4)
        self.assertAlmostEqual(trade["size"], 500.0)
        self.assertAlmostEqual(trade["notional"], 200.0)
        self.assertEqual(trade["timestamp"], 1779900100)

    def test_decode_rtds_trade_ignores_other_wallets_and_junk(self) -> None:
        self.assertIsNone(ct.decode_rtds_trade(rtds_message(wallet="0x" + "9" * 40), [ct.COPY_TARGET_WALLET]))
        self.assertIsNone(ct.decode_rtds_trade(rtds_message(side="REDEEM"), [ct.COPY_TARGET_WALLET]))
        self.assertIsNone(ct.decode_rtds_trade(rtds_message(price=0.0), [ct.COPY_TARGET_WALLET]))
        self.assertIsNone(ct.decode_rtds_trade({"topic": "crypto_prices", "payload": {}}, [ct.COPY_TARGET_WALLET]))
        self.assertIsNone(ct.decode_rtds_trade("not-a-mapping", [ct.COPY_TARGET_WALLET]))

    def test_decode_rtds_trade_accepts_flat_messages(self) -> None:
        flat = rtds_message()["payload"]
        trade = ct.decode_rtds_trade(flat, [ct.COPY_TARGET_WALLET.upper()])
        self.assertIsNotNone(trade)
        self.assertEqual(trade["wallet"], ct.COPY_TARGET_WALLET)

    def test_listener_handle_message_dedups_and_drains(self) -> None:
        listener = ct.RtdsTradeListener([ct.COPY_TARGET_WALLET])
        import json as _json

        raw = _json.dumps(rtds_message(as_list=True))
        self.assertEqual(listener.handle_message(raw), 1)
        self.assertEqual(listener.handle_message(raw), 0)
        trades = listener.drain()
        self.assertEqual(len(trades), 1)
        self.assertEqual(listener.drain(), [])
        status = listener.status()
        self.assertEqual(status["matched"], 1)
        self.assertEqual(status["messages"], 2)

    def test_apply_ws_trades_copies_after_baseline(self) -> None:
        self._seed(baseline_cutoff=0)
        trade = ct.decode_rtds_trade(rtds_message(), [ct.COPY_TARGET_WALLET])
        results = ct.apply_ws_trades([trade], settings=self.settings, db_path=self.db_path)
        combined = ct.aggregate_sync_results(results)
        self.assertEqual(combined.copied, 1)
        self.assertEqual(combined.source, "ws")

    def test_apply_ws_trades_marks_pre_baseline_as_observed(self) -> None:
        self._seed(baseline_cutoff=1779900100)
        trade = ct.decode_rtds_trade(rtds_message(timestamp=1779900100), [ct.COPY_TARGET_WALLET])
        results = ct.apply_ws_trades([trade], settings=self.settings, db_path=self.db_path)
        combined = ct.aggregate_sync_results(results)
        self.assertEqual(combined.copied, 0)
        self.assertEqual(combined.skipped, 1)
        conn = ct.connect(self.db_path)
        try:
            row = conn.execute("SELECT status FROM paper_orders WHERE source_tx = '0xws1'").fetchone()
        finally:
            conn.close()
        self.assertEqual(row["status"], "seed_observed")

    def test_apply_ws_trades_skips_unseeded_database(self) -> None:
        trade = ct.decode_rtds_trade(rtds_message(), [ct.COPY_TARGET_WALLET])
        results = ct.apply_ws_trades([trade], settings=self.settings, db_path=self.db_path)
        combined = ct.aggregate_sync_results(results)
        self.assertEqual(combined.copied, 0)
        self.assertEqual(combined.skipped, 1)
        conn = ct.connect(self.db_path)
        try:
            count = conn.execute("SELECT COUNT(*) AS n FROM paper_orders").fetchone()["n"]
        finally:
            conn.close()
        self.assertEqual(count, 0)

    def test_chain_reconciliation_skips_fill_already_copied_via_ws(self) -> None:
        self._seed(baseline_cutoff=0)
        ws_trade = ct.decode_rtds_trade(rtds_message(), [ct.COPY_TARGET_WALLET])
        ct.apply_ws_trades([ws_trade], settings=self.settings, db_path=self.db_path)
        # The on-chain log reports the same economic fill ~2s later with block
        # timestamp and recomputed price — a different dedup_key, same fill.
        chain_trade = {
            "transaction_hash": "0xws1",
            "asset": "asset-ws",
            "side": "BUY",
            "price": 0.4000001,
            "size": 500.0,
            "timestamp": 1779900102,
            "source": "polygon_order_filled",
            "wallet": ct.COPY_TARGET_WALLET,
        }
        conn = ct.connect(self.db_path)
        try:
            order = ct.apply_paper_trade(conn, chain_trade, ct.CopySettings(target_wallet=ct.COPY_TARGET_WALLET))
            count = conn.execute(
                "SELECT COUNT(*) AS n FROM paper_orders WHERE source_tx = '0xws1' AND source_side = 'BUY'"
            ).fetchone()["n"]
        finally:
            conn.close()
        self.assertEqual(order.status, "duplicate")
        self.assertEqual(order.reason, "duplicate_fill")
        self.assertEqual(count, 1)

    def test_distinct_fills_in_same_transaction_are_not_deduped(self) -> None:
        self._seed(baseline_cutoff=0)
        first = ct.decode_rtds_trade(rtds_message(asset="asset-a"), [ct.COPY_TARGET_WALLET])
        second = ct.decode_rtds_trade(rtds_message(asset="asset-b"), [ct.COPY_TARGET_WALLET])
        results = ct.apply_ws_trades([first, second], settings=self.settings, db_path=self.db_path)
        combined = ct.aggregate_sync_results(results)
        self.assertEqual(combined.copied, 2)

    def test_onchain_reconciliation_soft_fails_on_rate_limited_rpc(self) -> None:
        # The on-chain layer is best-effort behind the WebSocket — a 429 from the
        # free RPC must return a soft error, never raise and abort the daemon loop.
        self._seed(baseline_cutoff=0)
        import requests as _requests

        with patch("src.copy_trading._rpc_call", side_effect=_requests.RequestException("429 Too Many Requests")):
            result = ct.sync_onchain_copy_trades(ct.COPY_TARGET_WALLET, settings=self.settings, db_path=self.db_path)
        self.assertEqual(result.source, "chain")
        self.assertTrue(result.errors)
        self.assertIn("rpc unavailable", result.errors[0])


if __name__ == "__main__":
    unittest.main()
