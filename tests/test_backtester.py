import json
import unittest

import pandas as pd

from app import backtester as bt


def trade(time, side, price, size, asset="tok-yes", market_key="cond-1", outcome="Yes", title="Test market"):
    return {
        "time": pd.Timestamp(time, tz="UTC"),
        "type": "TRADE",
        "side": side,
        "outcome": outcome,
        "title": title,
        "price": price,
        "size": size,
        "notional": price * size,
        "market_key": market_key,
        "asset": asset,
        "transactionHash": f"0x{abs(hash((time, side, price, size, asset))):x}",
    }


def frame(rows):
    return pd.DataFrame(rows)


def config(**overrides):
    base = dict(
        wallet="0x" + "a" * 40,
        days=90,
        bankroll=1000.0,
        sizing_mode=bt.SIZING_FIXED,
        stake_value=25.0,
        max_stake=250.0,
        # Diese Testreihe prueft Sizing, Spiegelung und Abrechnung, nicht die
        # Gebuehr. Dafuer muss sie sich abschalten lassen, und das geht nur
        # ueber das pauschale Modell — beim Venue-Modell haengt die Gebuehr
        # am Preis und nicht an fee_bps. Die Kurve hat eigene Tests.
        fee_bps=0.0,
        fee_model=bt.FEE_MODEL_FLAT,
        slippage_bps=0.0,
        flat_stake=25.0,
    )
    base.update(overrides)
    return bt.BacktestConfig(**base)


class ReplayTests(unittest.TestCase):
    def test_fixed_buy_then_full_sell_books_profit(self):
        trades = frame(
            [
                trade("2026-05-01", "BUY", 0.50, 100.0),
                trade("2026-05-05", "SELL", 0.80, 100.0),
            ]
        )
        ledger, positions = bt.replay(trades, config())
        self.assertEqual(list(ledger["status"]), ["copied", "copied"])
        sell = ledger.iloc[1]
        self.assertAlmostEqual(sell["realized_pnl"], 15.0, places=6)
        self.assertEqual(positions, {})

    def test_fees_and_slippage_reduce_pnl(self):
        trades = frame(
            [
                trade("2026-05-01", "BUY", 0.50, 100.0),
                trade("2026-05-05", "SELL", 0.80, 100.0),
            ]
        )
        ledger, _ = bt.replay(trades, config(fee_bps=100.0, slippage_bps=100.0))
        buy = ledger.iloc[0]
        sell = ledger.iloc[1]
        self.assertAlmostEqual(buy["exec_price"], 0.505, places=6)
        self.assertAlmostEqual(buy["fee"], 0.25, places=6)
        shares = 25.0 / 0.505
        proceeds = shares * 0.792
        expected_realized = proceeds - proceeds * 0.01 - 25.0
        self.assertAlmostEqual(sell["realized_pnl"], expected_realized, places=6)
        self.assertLess(expected_realized, 15.0)

    def test_partial_source_sell_mirrors_fraction(self):
        trades = frame(
            [
                trade("2026-05-01", "BUY", 0.50, 100.0),
                trade("2026-05-05", "SELL", 0.60, 40.0),
            ]
        )
        ledger, positions = bt.replay(trades, config())
        sell = ledger.iloc[1]
        self.assertAlmostEqual(sell["shares"], 50.0 * 0.4, places=6)
        self.assertIn("tok-yes", positions)
        self.assertAlmostEqual(positions["tok-yes"]["shares"], 30.0, places=6)
        self.assertAlmostEqual(positions["tok-yes"]["cost_basis"], 15.0, places=6)

    def test_sell_without_position_is_filtered(self):
        # Kein Fehlschlag: die Position wurde nie gefolgt, der Verkauf
        # betrifft die Kopie nicht — "filtered" statt "skipped".
        trades = frame([trade("2026-05-01", "SELL", 0.50, 100.0)])
        ledger, positions = bt.replay(trades, config())
        self.assertEqual(ledger.iloc[0]["status"], "filtered")
        self.assertIn("not followed", ledger.iloc[0]["note"])
        self.assertEqual(positions, {})

    def test_follow_threshold_filters_small_entries(self):
        trades = frame(
            [
                trade("2026-05-01", "BUY", 0.50, 100.0, asset="klein", market_key="c1"),   # notional 50
                trade("2026-05-02", "BUY", 0.50, 400.0, asset="gross", market_key="c2"),   # notional 200
                trade("2026-05-03", "SELL", 0.60, 100.0, asset="klein", market_key="c1"),
            ]
        )
        ledger, positions = bt.replay(trades, config(min_follow_notional=100.0))
        self.assertEqual(list(ledger["status"]), ["filtered", "copied", "filtered"])
        self.assertIn("below the follow threshold", ledger.iloc[0]["note"])
        self.assertIn("not followed", ledger.iloc[2]["note"])
        self.assertIn("gross", positions)
        self.assertNotIn("klein", positions)

    def test_percent_sizing_uses_equity(self):
        trades = frame([trade("2026-05-01", "BUY", 0.50, 100.0)])
        ledger, _ = bt.replay(trades, config(sizing_mode=bt.SIZING_PERCENT, stake_value=5.0))
        self.assertAlmostEqual(ledger.iloc[0]["stake"], 50.0, places=6)

    def test_mirror_sizing_scales_source_notional(self):
        trades = frame([trade("2026-05-01", "BUY", 0.50, 1000.0)])
        ledger, _ = bt.replay(trades, config(sizing_mode=bt.SIZING_MIRROR, stake_value=2.0))
        self.assertAlmostEqual(ledger.iloc[0]["stake"], 10.0, places=6)

    def test_portfolio_share_sizing_matches_traders_share(self):
        trades = frame([trade("2026-05-01", "BUY", 0.50, 4000.0)])  # notional $2,000
        ledger, _ = bt.replay(
            trades,
            config(sizing_mode=bt.SIZING_PORTFOLIO, stake_value=1.0, trader_portfolio_value=100_000.0),
        )
        self.assertAlmostEqual(ledger.iloc[0]["stake"], 1000.0 * (2000.0 / 100_000.0), places=6)
        ledger2, _ = bt.replay(
            trades,
            config(sizing_mode=bt.SIZING_PORTFOLIO, stake_value=2.0, trader_portfolio_value=100_000.0),
        )
        self.assertAlmostEqual(ledger2.iloc[0]["stake"], 40.0, places=6)

    def test_portfolio_share_without_value_skips(self):
        trades = frame([trade("2026-05-01", "BUY", 0.50, 4000.0)])
        ledger, _ = bt.replay(trades, config(sizing_mode=bt.SIZING_PORTFOLIO, stake_value=1.0))
        self.assertEqual(ledger.iloc[0]["status"], "skipped")

    def test_kelly_sizing_stakes_quarter_kelly_of_equity(self):
        # Entry 0.50, assumed edge 5pt -> q=0.55, f* = 0.05/0.50 = 10%; quarter-Kelly
        # of the $1,000 bankroll = $25.
        trades = frame([trade("2026-05-01", "BUY", 0.50, 100.0)])
        ledger, _ = bt.replay(trades, config(sizing_mode=bt.SIZING_KELLY, stake_value=5.0))
        self.assertAlmostEqual(ledger.iloc[0]["stake"], 25.0, places=6)

    def test_kelly_fraction_override_scales_stake(self):
        trades = frame([trade("2026-05-01", "BUY", 0.50, 100.0)])
        ledger, _ = bt.replay(trades, config(sizing_mode=bt.SIZING_KELLY, stake_value=5.0, kelly_fraction=1.0))
        self.assertAlmostEqual(ledger.iloc[0]["stake"], 100.0, places=6)

    def test_kelly_zero_edge_skips(self):
        trades = frame([trade("2026-05-01", "BUY", 0.50, 100.0)])
        ledger, _ = bt.replay(trades, config(sizing_mode=bt.SIZING_KELLY, stake_value=0.0))
        self.assertEqual(ledger.iloc[0]["status"], "skipped")

    def test_kelly_fade_sizes_on_faded_price(self):
        # Fading a BUY at 0.60 buys the other side at 0.40; edge 5pt -> q=0.45,
        # f* = 0.05/0.60; quarter-Kelly of $1,000 = $20.8333.
        trades = frame([trade("2026-05-01", "BUY", 0.60, 100.0)])
        ledger, _ = bt.replay(trades, config(sizing_mode=bt.SIZING_KELLY, stake_value=5.0, strategy=bt.STRATEGY_FADE))
        self.assertAlmostEqual(ledger.iloc[0]["stake"], 1000.0 * 0.25 * (0.05 / 0.60), places=4)

    def test_exposure_cap_limits_open_copies(self):
        trades = frame(
            [
                trade("2026-05-01", "BUY", 0.50, 100.0, asset="tok-1", market_key="c1"),
                trade("2026-05-02", "BUY", 0.50, 100.0, asset="tok-2", market_key="c2"),
                trade("2026-05-03", "BUY", 0.50, 100.0, asset="tok-3", market_key="c3"),
                trade("2026-05-04", "SELL", 0.50, 100.0, asset="tok-1", market_key="c1"),
                trade("2026-05-05", "BUY", 0.50, 100.0, asset="tok-4", market_key="c4"),
            ]
        )
        ledger, _ = bt.replay(trades, config(stake_value=300.0, max_stake=300.0, max_exposure_pct=50.0))
        self.assertEqual(list(ledger["status"]), ["copied", "copied", "skipped", "copied", "copied"])
        self.assertAlmostEqual(ledger.iloc[0]["stake"], 300.0, places=6)
        self.assertAlmostEqual(ledger.iloc[1]["stake"], 200.0, places=6)
        self.assertIn("exposure cap", ledger.iloc[2]["note"])
        self.assertAlmostEqual(ledger.iloc[4]["stake"], 300.0, places=6)

    def test_mid_window_resolution_frees_capital_and_exposure(self):
        trades = frame(
            [
                trade("2026-05-01", "BUY", 0.50, 100.0, asset="tok-1", market_key="c1"),
                trade("2026-05-10", "BUY", 0.50, 100.0, asset="tok-2", market_key="c2"),
            ]
        )
        token_values = {
            "tok-1": {"price": 1.0, "closed": True, "end_time": pd.Timestamp("2026-05-05", tz="UTC")},
        }
        # Exposure cap 50% of $1,000 bankroll = $500; each copy wants $400.
        cfg = config(stake_value=400.0, max_stake=400.0, max_exposure_pct=50.0)
        ledger_blocked, _ = bt.replay(trades, cfg)
        self.assertEqual(list(ledger_blocked["status"]), ["copied", "copied"])
        self.assertAlmostEqual(ledger_blocked.iloc[1]["stake"], 100.0, places=6)  # clamped without recycling
        ledger_free, _ = bt.replay(trades, cfg, token_values)
        actions = list(ledger_free["action"])
        self.assertEqual(actions, ["BUY", "RESOLVE", "BUY"])
        resolve_row = ledger_free.iloc[1]
        self.assertEqual(str(resolve_row["time"]), str(pd.Timestamp("2026-05-05", tz="UTC")))
        self.assertAlmostEqual(resolve_row["realized_pnl"], 800.0 - 400.0, places=6)
        self.assertAlmostEqual(ledger_free.iloc[2]["stake"], 400.0, places=6)  # full stake after recycling

    def test_max_stake_caps_sizing(self):
        trades = frame([trade("2026-05-01", "BUY", 0.50, 1000.0)])
        ledger, _ = bt.replay(trades, config(sizing_mode=bt.SIZING_PERCENT, stake_value=50.0, max_stake=100.0))
        self.assertAlmostEqual(ledger.iloc[0]["stake"], 100.0, places=6)

    def test_cash_exhaustion_clamps_then_skips(self):
        trades = frame(
            [
                trade("2026-05-01", "BUY", 0.50, 100.0, asset="tok-1", market_key="c1"),
                trade("2026-05-02", "BUY", 0.50, 100.0, asset="tok-2", market_key="c2"),
                trade("2026-05-03", "BUY", 0.50, 100.0, asset="tok-3", market_key="c3"),
            ]
        )
        ledger, _ = bt.replay(trades, config(bankroll=30.0))
        self.assertEqual(list(ledger["status"]), ["copied", "copied", "skipped"])
        self.assertAlmostEqual(ledger.iloc[0]["stake"], 25.0, places=6)
        self.assertAlmostEqual(ledger.iloc[1]["stake"], 5.0, places=6)

    def test_bad_trade_data_is_skipped(self):
        trades = frame([trade("2026-05-01", "BUY", 0.0, 100.0)])
        ledger, positions = bt.replay(trades, config())
        self.assertEqual(ledger.iloc[0]["status"], "skipped")
        self.assertEqual(positions, {})


class FeeCurveTests(unittest.TestCase):
    """Die Gebuehr folgt dem Venue-Modell, nicht einem pauschalen Satz."""

    def kurve(self, **overrides):
        base = dict(
            wallet="0x" + "a" * 40, days=90, bankroll=1000.0,
            sizing_mode=bt.SIZING_FIXED, stake_value=25.0, max_stake=250.0,
            slippage_bps=0.0, flat_stake=25.0,
        )
        base.update(overrides)
        return bt.BacktestConfig(**base)

    def test_kurve_ist_die_voreinstellung(self):
        self.assertEqual(bt.BacktestConfig(wallet="0x" + "a" * 40).fee_model,
                         bt.FEE_MODEL_CURVE)

    def test_gebuehr_haengt_am_preis(self):
        # fee / stake = rate * (1 - p), allgemeiner Satz 5 Prozent.
        satz = bt.fee_rate_for(self.kurve())
        self.assertAlmostEqual(satz(0.50), 0.025, places=6)
        self.assertAlmostEqual(satz(0.90), 0.005, places=6)
        self.assertAlmostEqual(satz(0.10), 0.045, places=6)

    def test_mitte_des_buchs_kostet_ein_vielfaches_der_alten_pauschale(self):
        # Der Kern der Sache: 20 bps gegen rund 250 bps bei 0.50. Dieser Test
        # faellt, sobald jemand die Kurve wieder gegen einen flachen Satz
        # tauscht, der in der Mitte des Buchs zu billig ist.
        kurve = bt.fee_rate_for(self.kurve())(0.50)
        pauschal = bt.fee_rate_for(self.kurve(fee_model=bt.FEE_MODEL_FLAT, fee_bps=20.0))(0.50)
        self.assertGreater(kurve, 10.0 * pauschal)

    def test_kategorie_senkt_den_satz(self):
        allgemein = bt.fee_rate_for(self.kurve())(0.50)
        politik = bt.fee_rate_for(self.kurve(fee_category="politics"))(0.50)
        self.assertLess(politik, allgemein)

    def test_kauf_bucht_die_kurvengebuehr(self):
        trades = frame([trade("2026-05-01", "BUY", 0.50, 100.0)])
        ledger, _ = bt.replay(trades, self.kurve())
        buy = ledger.iloc[0]
        self.assertAlmostEqual(buy["stake"], 25.0, places=6)
        # 25 Dollar zu 0.50 sind 50 Anteile: 50 * 0.05 * 0.25 = 0.625
        self.assertAlmostEqual(buy["fee"], 0.625, places=6)

    def test_verkauf_bucht_die_kurvengebuehr(self):
        trades = frame([
            trade("2026-05-01", "BUY", 0.50, 100.0),
            trade("2026-05-05", "SELL", 0.80, 100.0),
        ])
        ledger, _ = bt.replay(trades, self.kurve())
        sell = ledger.iloc[1]
        erloes = (25.0 / 0.50) * 0.80
        self.assertAlmostEqual(sell["fee"], erloes * 0.05 * 0.20, places=6)

    def test_kurve_kostet_mehr_als_die_alte_pauschale(self):
        trades = frame([
            trade("2026-05-01", "BUY", 0.50, 100.0),
            trade("2026-05-05", "SELL", 0.55, 100.0),
        ])
        mit_kurve, _ = bt.replay(trades, self.kurve())
        mit_pauschale, _ = bt.replay(trades, self.kurve(fee_model=bt.FEE_MODEL_FLAT, fee_bps=20.0))
        self.assertGreater(float(mit_kurve["fee"].sum()), float(mit_pauschale["fee"].sum()))
        self.assertLess(float(mit_kurve["realized_pnl"].sum()),
                        float(mit_pauschale["realized_pnl"].sum()))

    def test_pauschalmodell_bleibt_erreichbar(self):
        trades = frame([trade("2026-05-01", "BUY", 0.50, 100.0)])
        ledger, _ = bt.replay(trades, self.kurve(fee_model=bt.FEE_MODEL_FLAT, fee_bps=100.0))
        self.assertAlmostEqual(ledger.iloc[0]["fee"], 0.25, places=6)


class FadeStrategyTests(unittest.TestCase):
    def test_fade_buy_opens_opposite_side(self):
        trades = frame([trade("2026-05-01", "BUY", 0.60, 100.0)])
        ledger, positions = bt.replay(trades, config(strategy=bt.STRATEGY_FADE))
        buy = ledger.iloc[0]
        self.assertAlmostEqual(buy["exec_price"], 0.40, places=6)
        self.assertAlmostEqual(buy["shares"], 25.0 / 0.40, places=6)
        self.assertIn("fade:tok-yes", positions)
        self.assertTrue(positions["fade:tok-yes"]["fade"])

    def test_fade_loses_when_source_side_wins(self):
        trades = frame([trade("2026-05-01", "BUY", 0.60, 100.0)])
        _, positions = bt.replay(trades, config(strategy=bt.STRATEGY_FADE))
        token_values = {"tok-yes": {"price": 1.0, "closed": True, "end_time": pd.Timestamp("2026-05-20", tz="UTC")}}
        settlement, _ = bt.settle(positions, token_values, asof=pd.Timestamp("2026-06-01", tz="UTC"))
        self.assertAlmostEqual(settlement.iloc[0]["realized_pnl"], -25.0, places=6)

    def test_fade_wins_when_source_side_loses(self):
        trades = frame([trade("2026-05-01", "BUY", 0.60, 100.0)])
        _, positions = bt.replay(trades, config(strategy=bt.STRATEGY_FADE))
        token_values = {"tok-yes": {"price": 0.0, "closed": True, "end_time": pd.Timestamp("2026-05-20", tz="UTC")}}
        settlement, _ = bt.settle(positions, token_values, asof=pd.Timestamp("2026-06-01", tz="UTC"))
        self.assertAlmostEqual(settlement.iloc[0]["realized_pnl"], (25.0 / 0.40) * 1.0 - 25.0, places=6)

    def test_fade_mirrored_sell_exits_at_inverse_price(self):
        trades = frame(
            [
                trade("2026-05-01", "BUY", 0.60, 100.0),
                trade("2026-05-05", "SELL", 0.80, 100.0),
            ]
        )
        ledger, positions = bt.replay(trades, config(strategy=bt.STRATEGY_FADE))
        sell = ledger.iloc[1]
        self.assertAlmostEqual(sell["exec_price"], 0.20, places=6)
        expected = (25.0 / 0.40) * 0.20 - 25.0
        self.assertAlmostEqual(sell["realized_pnl"], expected, places=6)
        self.assertEqual(positions, {})

    def test_fade_open_position_marks_to_inverse_market(self):
        trades = frame([trade("2026-05-01", "BUY", 0.60, 100.0)])
        _, positions = bt.replay(trades, config(strategy=bt.STRATEGY_FADE))
        token_values = {"tok-yes": {"price": 0.7, "closed": False, "end_time": None}}
        settlement, open_positions = bt.settle(positions, token_values, asof=pd.Timestamp("2026-06-01", tz="UTC"))
        self.assertTrue(settlement.empty)
        self.assertAlmostEqual(open_positions.iloc[0]["current_price"], 0.3, places=6)
        self.assertAlmostEqual(open_positions.iloc[0]["unrealized_pnl"], (25.0 / 0.40) * 0.3 - 25.0, places=6)


class SettleTests(unittest.TestCase):
    def _positions(self):
        trades = frame([trade("2026-05-01", "BUY", 0.50, 100.0)])
        _, positions = bt.replay(trades, config())
        return positions

    def test_resolution_win_realizes_payout(self):
        positions = self._positions()
        token_values = {"tok-yes": {"price": 1.0, "closed": True, "end_time": pd.Timestamp("2026-05-20", tz="UTC")}}
        settlement, open_positions = bt.settle(positions, token_values, asof=pd.Timestamp("2026-06-01", tz="UTC"))
        self.assertEqual(len(settlement), 1)
        self.assertAlmostEqual(settlement.iloc[0]["realized_pnl"], 50.0 - 25.0, places=6)
        self.assertTrue(open_positions.empty)

    def test_resolution_loss_realizes_negative(self):
        positions = self._positions()
        token_values = {"tok-yes": {"price": 0.0, "closed": True, "end_time": pd.Timestamp("2026-05-20", tz="UTC")}}
        settlement, _ = bt.settle(positions, token_values, asof=pd.Timestamp("2026-06-01", tz="UTC"))
        self.assertAlmostEqual(settlement.iloc[0]["realized_pnl"], -25.0, places=6)

    def test_open_position_marks_to_market(self):
        positions = self._positions()
        token_values = {"tok-yes": {"price": 0.6, "closed": False, "end_time": None}}
        settlement, open_positions = bt.settle(positions, token_values, asof=pd.Timestamp("2026-06-01", tz="UTC"))
        self.assertTrue(settlement.empty)
        self.assertEqual(len(open_positions), 1)
        self.assertAlmostEqual(open_positions.iloc[0]["unrealized_pnl"], 50.0 * 0.6 - 25.0, places=6)

    def test_unknown_token_falls_back_to_cost(self):
        positions = self._positions()
        settlement, open_positions = bt.settle(positions, {}, asof=pd.Timestamp("2026-06-01", tz="UTC"))
        self.assertTrue(settlement.empty)
        self.assertAlmostEqual(open_positions.iloc[0]["unrealized_pnl"], 0.0, places=6)
        self.assertEqual(open_positions.iloc[0]["market_status"], "unknown")


class CurveAndStatsTests(unittest.TestCase):
    def test_equity_curve_and_drawdown(self):
        trades = frame(
            [
                trade("2026-05-01", "BUY", 0.50, 100.0, asset="tok-1", market_key="c1"),
                trade("2026-05-03", "SELL", 0.80, 100.0, asset="tok-1", market_key="c1"),
                trade("2026-05-05", "BUY", 0.50, 100.0, asset="tok-2", market_key="c2"),
                trade("2026-05-07", "SELL", 0.10, 100.0, asset="tok-2", market_key="c2"),
            ]
        )
        ledger, _ = bt.replay(trades, config())
        start = pd.Timestamp("2026-04-30", tz="UTC")
        end = pd.Timestamp("2026-05-10", tz="UTC")
        curve = bt.equity_curve(ledger, start, end, 1000.0)
        self.assertEqual(len(curve), 11)
        self.assertAlmostEqual(curve["equity"].iloc[0], 1000.0, places=6)
        self.assertAlmostEqual(curve["equity"].iloc[-1], 1000.0 + 15.0 - 20.0, places=6)
        self.assertLessEqual(curve["drawdown"].min(), 0.0)
        stats = bt.compute_stats(ledger, bt._empty_positions(), curve, 1000.0)
        self.assertEqual(stats["closed_trades"], 2)
        self.assertEqual(stats["wins"], 1)
        self.assertEqual(stats["losses"], 1)
        self.assertAlmostEqual(stats["win_rate"], 0.5, places=6)
        self.assertAlmostEqual(stats["total_pnl"], -5.0, places=6)
        self.assertAlmostEqual(stats["max_drawdown"], curve["drawdown"].min(), places=6)
        self.assertAlmostEqual(stats["profit_factor"], 15.0 / 20.0, places=6)

    def test_empty_ledger_stats_are_zeroed(self):
        curve = bt.equity_curve(
            bt._empty_ledger(),
            pd.Timestamp("2026-05-01", tz="UTC"),
            pd.Timestamp("2026-05-10", tz="UTC"),
            1000.0,
        )
        stats = bt.compute_stats(bt._empty_ledger(), bt._empty_positions(), curve, 1000.0)
        self.assertEqual(stats["copied_trades"], 0)
        self.assertIsNone(stats["win_rate"])
        self.assertAlmostEqual(stats["final_equity"], 1000.0, places=6)


class FetchWindowTradesTests(unittest.TestCase):
    """Zeitfenster-Slices: der Offset-Cap der Daten-API darf das Fenster
    nicht mehr abschneiden, solange der Fetcher ``end`` versteht."""

    NOW = pd.Timestamp("2026-06-10", tz="UTC")

    def _minute_rows(self, count):
        # Ein Trade pro Minute, rueckwaerts ab NOW; jede Zeile eindeutig.
        return [
            trade((self.NOW - pd.Timedelta(minutes=i)).tz_convert(None).isoformat(), "BUY", 0.5, 10.0, asset=f"tok-{i}", market_key=f"c-{i}")
            for i in range(count)
        ]

    def _sliced_fetcher(self, rows, offset_cap=3000):
        def fetch_activity(wallet, limit=500, offset=0, end=None):
            if offset + limit > offset_cap:
                raise AssertionError("deep pagination — the API would reject this")
            subset = rows if end is None else [r for r in rows if int(r["time"].timestamp()) <= end]
            return pd.DataFrame(subset[offset : offset + limit])

        return fetch_activity

    def test_time_sliced_pagination_covers_the_window(self):
        rows = self._minute_rows(4000)
        window_start = self.NOW - pd.Timedelta(minutes=3500)
        trades, truncated = bt.fetch_window_trades(
            "0x" + "a" * 40,
            window_start,
            self._sliced_fetcher(rows),
            page_size=250,
            slice_rows=1000,
        )
        self.assertFalse(truncated)
        # Alle 3501 Zeilen im Fenster (i = 0..3500), Randzeilen der Scheiben
        # ohne Dubletten.
        self.assertEqual(len(trades), 3501)
        self.assertEqual(trades["transactionHash"].nunique(), 3501)
        self.assertTrue(trades["time"].is_monotonic_increasing)

    def test_max_rows_cap_still_reports_truncation(self):
        rows = self._minute_rows(4000)
        window_start = self.NOW - pd.Timedelta(minutes=3500)
        trades, truncated = bt.fetch_window_trades(
            "0x" + "a" * 40,
            window_start,
            self._sliced_fetcher(rows),
            page_size=250,
            max_rows=1500,
            slice_rows=1000,
        )
        self.assertTrue(truncated)
        self.assertLess(len(trades), 3501)

    def test_legacy_fetcher_without_end_stops_at_slice_cap(self):
        rows = self._minute_rows(4000)
        window_start = self.NOW - pd.Timedelta(minutes=3500)

        def fetch_activity(wallet, limit=500, offset=0):
            return pd.DataFrame(rows[offset : offset + limit])

        trades, truncated = bt.fetch_window_trades(
            "0x" + "a" * 40,
            window_start,
            fetch_activity,
            page_size=250,
            slice_rows=1000,
        )
        self.assertTrue(truncated)
        self.assertEqual(len(trades), 1000)


class RunBacktestTests(unittest.TestCase):
    def test_end_to_end_with_injected_fetchers(self):
        now = pd.Timestamp("2026-06-10", tz="UTC")
        rows = [
            trade("2026-05-01", "BUY", 0.50, 100.0, asset="tok-yes", market_key="cond-1"),
            trade("2026-05-05", "BUY", 0.40, 50.0, asset="tok-open", market_key="cond-2"),
            trade("2025-12-01", "BUY", 0.50, 100.0, asset="tok-old", market_key="cond-3"),
        ]
        activity = pd.DataFrame(rows)
        redeem = trade("2026-05-06", "", 0.5, 10.0, asset="tok-yes", market_key="cond-1")
        redeem["type"] = "REDEEM"
        activity = pd.concat([activity, pd.DataFrame([redeem])], ignore_index=True)

        def fetch_activity(wallet, limit=500, offset=0):
            return activity if offset == 0 else pd.DataFrame()

        def fetch_markets(ids):
            self.assertIn("cond-1", ids)
            self.assertIn("cond-2", ids)
            return [
                {
                    "conditionId": "cond-1",
                    "clobTokenIds": json.dumps(["tok-yes", "tok-no"]),
                    "outcomePrices": json.dumps(["1", "0"]),
                    "closed": True,
                    "endDate": "2026-05-20T00:00:00Z",
                },
                {
                    "conditionId": "cond-2",
                    "clobTokenIds": json.dumps(["tok-open", "tok-open-no"]),
                    "outcomePrices": json.dumps(["0.6", "0.4"]),
                    "closed": False,
                    "endDate": "2026-12-31T00:00:00Z",
                },
            ]

        result = bt.run_backtest(
            config(),
            fetch_activity=fetch_activity,
            fetch_markets_by_ids=fetch_markets,
            now=now,
        )
        self.assertEqual(result.stats["copied_trades"], 2)
        self.assertEqual(result.stats["closed_trades"], 1)
        self.assertAlmostEqual(result.stats["realized_pnl"], 25.0, places=6)
        self.assertEqual(result.stats["open_positions"], 1)
        expected_unrealized = (25.0 / 0.40) * 0.6 - 25.0
        self.assertAlmostEqual(result.stats["unrealized_pnl"], expected_unrealized, places=6)
        self.assertIn("benchmark", result.equity.columns)
        self.assertEqual(len(result.equity), 91)
        self.assertTrue(result.ledger["time"].is_monotonic_decreasing)
        self.assertAlmostEqual(
            result.equity["equity"].iloc[-1],
            result.stats["final_equity"],
            places=6,
        )

    def test_benchmark_uses_flat_stake(self):
        now = pd.Timestamp("2026-06-10", tz="UTC")
        rows = [
            trade("2026-05-01", "BUY", 0.50, 2000.0, asset="tok-1", market_key="c1"),
            trade("2026-05-02", "BUY", 0.50, 2000.0, asset="tok-2", market_key="c2"),
        ]
        activity = pd.DataFrame(rows)

        def fetch_activity(wallet, limit=500, offset=0):
            return activity if offset == 0 else pd.DataFrame()

        result = bt.run_backtest(
            config(sizing_mode=bt.SIZING_MIRROR, stake_value=10.0, flat_stake=25.0),
            fetch_activity=fetch_activity,
            fetch_markets_by_ids=lambda ids: [],
            now=now,
        )
        self.assertAlmostEqual(result.stats["volume_copied"], 200.0, places=6)
        self.assertAlmostEqual(result.benchmark_stats["volume_copied"], 50.0, places=6)

    def test_window_truncation_is_flagged_for_hyperactive_wallets(self):
        now = pd.Timestamp("2026-06-10", tz="UTC")

        def fetch_activity(wallet, limit=500, offset=0):
            rows = [
                trade("2026-06-01", "BUY", 0.5, 10.0, asset=f"tok-{offset}-{i}", market_key=f"c-{offset}-{i}")
                for i in range(limit)
            ]
            return pd.DataFrame(rows)

        result = bt.run_backtest(
            config(),
            fetch_activity=fetch_activity,
            fetch_markets_by_ids=lambda ids: [],
            now=now,
        )
        self.assertTrue(result.stats["window_truncated"])
        self.assertIn("effective_start", result.stats)

    def test_window_fully_covered_is_not_flagged(self):
        now = pd.Timestamp("2026-06-10", tz="UTC")
        activity = pd.DataFrame([trade("2026-05-01", "BUY", 0.5, 10.0)])

        def fetch_activity(wallet, limit=500, offset=0):
            return activity if offset == 0 else pd.DataFrame()

        result = bt.run_backtest(
            config(),
            fetch_activity=fetch_activity,
            fetch_markets_by_ids=lambda ids: [],
            now=now,
        )
        self.assertFalse(result.stats["window_truncated"])

    def test_truncated_window_anchors_curve_at_covered_edge(self):
        # Deckt der Fetch nur die letzten zwei Tage ab, darf die Kurve nicht
        # 28 erfundene flache Tage davor zeigen: sie beginnt an der Datenkante
        # und laeuft stundenweise statt taeglich.
        now = pd.Timestamp("2026-06-10", tz="UTC")
        rows = [
            trade((now - pd.Timedelta(seconds=40 * i)).tz_convert(None).isoformat(), "BUY", 0.5, 10.0, asset=f"tok-{i}", market_key=f"c-{i}")
            for i in range(4000)  # ~44 Stunden im 40-Sekunden-Takt
        ]

        # Legacy-Fetcher ohne end-Parameter: der Scan endet am Slice-Cap
        # (3000 Zeilen), das Fenster ist abgeschnitten.
        def fetch_activity(wallet, limit=500, offset=0):
            return pd.DataFrame(rows[offset : offset + limit])

        result = bt.run_backtest(
            config(days=30),
            fetch_activity=fetch_activity,
            fetch_markets_by_ids=lambda ids: [],
            now=now,
        )
        self.assertTrue(result.stats["window_truncated"])
        curve_start = result.equity["time"].min()
        # Datenkante: aeltester geladener Trade (Slice-Cap 3000 -> Zeile 2999),
        # auf die volle Stunde gerundet.
        self.assertGreaterEqual(curve_start, (now - pd.Timedelta(seconds=40 * 3000)).floor("h"))
        self.assertGreater(len(result.equity), 24)   # stundenweise ueber ~33 Stunden
        self.assertLess(len(result.equity), 80)      # nicht 31 Tagespunkte, nicht Minutentakt

    def test_skip_reasons_are_counted(self):
        trades = frame(
            [
                trade("2026-05-01", "BUY", 0.50, 100.0, asset="a1", market_key="c1"),
                trade("2026-05-02", "BUY", 0.50, 100.0, asset="a2", market_key="c2"),
                trade("2026-05-03", "BUY", 0.50, 100.0, asset="a3", market_key="c3"),
                trade("2026-05-04", "SELL", 0.50, 100.0, asset="a9", market_key="c9"),
            ]
        )
        # Bankroll 30, 10% Gebuehr: Kauf 1 kostet 25+2.50, Kauf 2 nimmt den
        # Kassenrest, Kauf 3 ist "out of cash" (die Gebuehren haben die Kasse
        # unter den Exposure-Spielraum gedrueckt); der Verkauf trifft keine
        # kopierte Position und zaehlt als "filtered", nicht als Fehlschlag.
        ledger, positions = bt.replay(trades, config(bankroll=30.0, fee_bps=1000.0))
        curve = bt.equity_curve(ledger, pd.Timestamp("2026-05-01", tz="UTC"), pd.Timestamp("2026-05-10", tz="UTC"), 30.0)
        stats = bt.compute_stats(ledger, bt._empty_positions(), curve, 30.0)
        self.assertEqual(stats["skip_reasons"]["out_of_cash"], 1)
        self.assertEqual(stats["skip_reasons"]["no_position"], 0)
        self.assertEqual(stats["skip_reasons"]["exposure_cap"], 0)
        self.assertEqual(stats["skipped_trades"], 1)
        self.assertEqual(stats["filtered_trades"], 1)

    def test_source_peak_concurrency_counts_open_positions(self):
        trades = frame(
            [
                trade("2026-05-01", "BUY", 0.5, 10.0, asset="a1", market_key="c1"),
                trade("2026-05-02", "BUY", 0.5, 10.0, asset="a2", market_key="c2"),
                trade("2026-05-03", "SELL", 0.5, 10.0, asset="a1", market_key="c1"),
                trade("2026-05-04", "BUY", 0.5, 10.0, asset="a3", market_key="c3"),
                trade("2026-05-06", "BUY", 0.5, 10.0, asset="a4", market_key="c4"),
            ]
        )
        # a2 ist am 2026-05-05 aufgeloest: beim Kauf von a4 sind nur a3+a4
        # offen. Hoechststand: a2+a3 (und zuvor a1+a2) -> 2.
        token_values = {"a2": {"price": 1.0, "closed": True, "end_time": pd.Timestamp("2026-05-05", tz="UTC")}}
        self.assertEqual(bt.source_peak_concurrency(trades, token_values), 2)
        # Ohne Aufloesungen bleibt a2 offen: a2+a3+a4 -> 3.
        self.assertEqual(bt.source_peak_concurrency(trades, {}), 3)
        self.assertEqual(bt.source_peak_concurrency(pd.DataFrame(), {}), 0)

    def _zehn_positionen(self):
        rows = [
            trade(f"2026-05-{tag:02d}", "BUY", 0.50, 100.0, asset=f"tok-{tag}", market_key=f"c-{tag}")
            for tag in range(1, 11)
        ]
        activity = pd.DataFrame(rows)

        def fetch_activity(wallet, limit=500, offset=0):
            return activity if offset == 0 else pd.DataFrame()

        return fetch_activity

    def test_auto_fit_sizes_stake_to_the_wallets_pace(self):
        # Zehn gleichzeitig offene Positionen, Einsatz 250 zu gross fuer die
        # 1000er-Bankroll: Auto-Fit dimensioniert auf 0.9 * 1000 / 10 = 90
        # je Copy, und ALLE zehn Trades werden kopiert statt vier.
        result = bt.run_backtest(
            config(stake_value=250.0, auto_fit=True),
            fetch_activity=self._zehn_positionen(),
            fetch_markets_by_ids=lambda ids: [],
            now=pd.Timestamp("2026-06-10", tz="UTC"),
        )
        self.assertTrue(result.stats["auto_fit"]["applied"])
        self.assertEqual(result.stats["auto_fit"]["peak_concurrent"], 10)
        self.assertAlmostEqual(result.stats["auto_fit"]["stake"], 90.0, places=6)
        self.assertEqual(result.stats["copied_trades"], 10)
        self.assertEqual(result.stats["skip_reasons"]["exposure_cap"], 0)
        self.assertEqual(result.stats["skip_reasons"]["out_of_cash"], 0)

    def test_auto_fit_off_reports_the_fitting_stake(self):
        result = bt.run_backtest(
            config(stake_value=250.0, auto_fit=False),
            fetch_activity=self._zehn_positionen(),
            fetch_markets_by_ids=lambda ids: [],
            now=pd.Timestamp("2026-06-10", tz="UTC"),
        )
        self.assertFalse(result.stats["auto_fit"]["applied"])
        self.assertEqual(result.stats["auto_fit"]["peak_concurrent"], 10)
        self.assertAlmostEqual(result.stats["auto_fit"]["stake"], 90.0, places=6)
        # Ohne Fit laeuft die Bankroll voll: 4 Kopien, der Rest am Deckel.
        self.assertEqual(result.stats["copied_trades"], 4)
        self.assertEqual(result.stats["skip_reasons"]["exposure_cap"], 6)

    def test_auto_fit_follows_the_largest_entries_at_the_set_stake(self):
        # Drei grosse Einstiege (notional 500) neben sieben kleinen (5), alle
        # gleichzeitig offen. Budget 100 bei Einsatz 25 -> Kapazitaet 3:
        # Auto-Fit setzt die Folge-Schwelle auf 500 und kopiert die drei
        # grossen beim EINGESTELLTEN Einsatz, statt den Einsatz auf Staub zu
        # schrumpfen. Die kleinen sind "filtered", nicht "skipped".
        rows = [
            trade(f"2026-05-{tag:02d}", "BUY", 0.50, 1000.0, asset=f"gross-{tag}", market_key=f"g-{tag}")
            for tag in range(1, 4)
        ] + [
            trade(f"2026-05-{tag:02d}", "BUY", 0.50, 10.0, asset=f"klein-{tag}", market_key=f"k-{tag}")
            for tag in range(4, 11)
        ]
        activity = pd.DataFrame(rows)

        def fetch_activity(wallet, limit=500, offset=0):
            return activity if offset == 0 else pd.DataFrame()

        result = bt.run_backtest(
            config(bankroll=100.0, stake_value=25.0, auto_fit=True),
            fetch_activity=fetch_activity,
            fetch_markets_by_ids=lambda ids: [],
            now=pd.Timestamp("2026-06-10", tz="UTC"),
        )
        fit = result.stats["auto_fit"]
        self.assertTrue(fit["applied"])
        self.assertEqual(fit["mode"], "threshold")
        self.assertAlmostEqual(fit["follow_threshold"], 500.0, places=6)
        self.assertEqual(fit["followed_positions"], 3)
        self.assertAlmostEqual(fit["stake"], 25.0, places=6)
        self.assertEqual(result.stats["copied_trades"], 3)
        self.assertEqual(result.stats["filtered_trades"], 7)
        self.assertEqual(result.stats["skipped_trades"], 0)

    def test_fit_follow_threshold_binary_search(self):
        t0 = pd.Timestamp("2026-05-01", tz="UTC")
        intervals = [(t0, None, float(n)) for n in (5, 10, 50, 200, 500)]
        # Kapazitaet 2: nur die zwei groessten Einstiege passen -> Schwelle 200.
        self.assertAlmostEqual(bt._fit_follow_threshold(intervals, 2), 200.0, places=6)
        # Alles passt -> Schwelle 0.
        self.assertEqual(bt._fit_follow_threshold(intervals, 5), 0.0)
        # Selbst der groesste Einstieg allein passt nicht -> None.
        self.assertIsNone(bt._fit_follow_threshold([(t0, None, 50.0)] * 3, 0))
        gleich = [(t0, None, 50.0), (t0, None, 50.0), (t0, None, 50.0)]
        self.assertIsNone(bt._fit_follow_threshold(gleich, 2))

    def test_auto_fit_leaves_self_sizing_modes_alone(self):
        result = bt.run_backtest(
            config(sizing_mode=bt.SIZING_MIRROR, stake_value=10.0, auto_fit=True),
            fetch_activity=self._zehn_positionen(),
            fetch_markets_by_ids=lambda ids: [],
            now=pd.Timestamp("2026-06-10", tz="UTC"),
        )
        self.assertFalse(result.stats["auto_fit"]["applied"])
        self.assertEqual(result.stats["auto_fit"]["peak_concurrent"], 10)

    def test_event_slug_fallback_resolves_missing_markets(self):
        # /markets?condition_ids= kommt fuer Sport-Untermaerkte regelmaessig
        # leer zurueck; ueber das Elternereignis muss die Position trotzdem
        # aufgeloest werden, statt ewig "open at cost" zu stehen.
        now = pd.Timestamp("2026-06-10", tz="UTC")
        row = trade("2026-05-01", "BUY", 0.50, 100.0, asset="tok-sport", market_key="cond-sport")
        row["event_slug"] = "epl-xyz-2026-05-01"
        activity = pd.DataFrame([row])

        def fetch_activity(wallet, limit=500, offset=0):
            return activity if offset == 0 else pd.DataFrame()

        def fetch_by_slugs(slugs):
            self.assertEqual(slugs, ["epl-xyz-2026-05-01"])
            return [
                {
                    "conditionId": "cond-sport",
                    "clobTokenIds": json.dumps(["tok-sport", "tok-sport-no"]),
                    "outcomePrices": json.dumps(["1", "0"]),
                    "closed": True,
                    "endDate": "2026-05-02T00:00:00Z",
                }
            ]

        result = bt.run_backtest(
            config(),
            fetch_activity=fetch_activity,
            fetch_markets_by_ids=lambda ids: [],
            fetch_markets_by_event_slugs=fetch_by_slugs,
            now=now,
        )
        self.assertEqual(result.stats["wins"], 1)
        self.assertEqual(result.stats["open_positions"], 0)
        self.assertAlmostEqual(result.stats["realized_pnl"], 25.0, places=6)

    def test_strategy_comparison_ranks_variants(self):
        now = pd.Timestamp("2026-06-10", tz="UTC")
        rows = [
            trade("2026-05-01", "BUY", 0.50, 100.0),
            trade("2026-05-05", "SELL", 0.80, 100.0),
        ]
        activity = pd.DataFrame(rows)

        def fetch_activity(wallet, limit=500, offset=0):
            return activity if offset == 0 else pd.DataFrame()

        comparison = bt.strategy_comparison(
            config(),
            fetch_activity=fetch_activity,
            fetch_markets_by_ids=lambda ids: [],
            now=now,
        )
        self.assertEqual(len(comparison), 8)
        self.assertTrue(comparison["final_equity"].is_monotonic_decreasing)
        # Several variants can tie on the top final equity on this fixture, and
        # the descending sort's tie-break order is not stable — so assert the
        # winner is one of the top-equity variants, not a hard-coded name.
        best_equity = comparison["final_equity"].max()
        top_variants = set(comparison.loc[comparison["final_equity"] == best_equity, "strategy"])
        self.assertIn(comparison.iloc[0]["strategy"], top_variants)
        self.assertIn("5% of bankroll", top_variants)
        self.assertIn("Kelly 1/4 (+5pt edge)", set(comparison["strategy"]))
        with_portfolio = bt.strategy_comparison(
            config(trader_portfolio_value=10_000.0),
            fetch_activity=fetch_activity,
            fetch_markets_by_ids=lambda ids: [],
            now=now,
        )
        self.assertEqual(len(with_portfolio), 10)

    def test_empty_activity_yields_flat_result(self):
        result = bt.run_backtest(
            config(),
            fetch_activity=lambda wallet, limit=500, offset=0: pd.DataFrame(),
            fetch_markets_by_ids=lambda ids: [],
            now=pd.Timestamp("2026-06-10", tz="UTC"),
        )
        self.assertTrue(result.ledger.empty)
        self.assertEqual(result.stats["copied_trades"], 0)
        self.assertAlmostEqual(result.equity["equity"].iloc[-1], 1000.0, places=6)


if __name__ == "__main__":
    unittest.main()
