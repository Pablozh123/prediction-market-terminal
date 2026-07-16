"""Tests for the paper market-making simulator."""

from __future__ import annotations

import unittest

from src import mm_simulator as mm

P = mm.QuoteParams(half_spread=0.01, gamma=0.08, quote_usd=50.0,
                   inventory_cap_usd=250.0)


class ComputeQuotesTest(unittest.TestCase):
    def test_flat_inventory_quotes_symmetric_around_mid(self) -> None:
        bid, ask = mm.compute_quotes(0.50, 0.49, 0.51, 0.0, P)
        self.assertAlmostEqual(bid, 0.49, places=4)
        self.assertAlmostEqual(ask, 0.51, places=4)

    def test_long_inventory_shifts_both_quotes_down(self) -> None:
        flach = mm.compute_quotes(0.50, 0.45, 0.55, 0.0, P)
        long = mm.compute_quotes(0.50, 0.45, 0.55, 125.0, P)  # halbes Cap
        self.assertLess(long[0], flach[0])
        self.assertLess(long[1], flach[1])
        # halbes Cap, var=0.25: Shift = 0.08 * 0.25 * 0.5 = 0.01
        self.assertAlmostEqual(flach[0] - long[0], 0.01, places=4)

    def test_short_inventory_shifts_both_quotes_up(self) -> None:
        kurz = mm.compute_quotes(0.50, 0.45, 0.55, -125.0, P)
        self.assertGreater(kurz[0], 0.49)
        self.assertGreater(kurz[1], 0.51)

    def test_quotes_never_cross_the_opposite_touch(self) -> None:
        bid, ask = mm.compute_quotes(0.50, 0.499, 0.501, 0.0, P)
        self.assertLess(bid, 0.501)
        self.assertGreater(ask, 0.499)

    def test_cap_pulls_the_accumulating_side(self) -> None:
        bid, ask = mm.compute_quotes(0.50, 0.45, 0.55, 250.0, P)
        self.assertIsNone(bid)
        self.assertIsNotNone(ask)
        bid, ask = mm.compute_quotes(0.50, 0.45, 0.55, -250.0, P)
        self.assertIsNotNone(bid)
        self.assertIsNone(ask)


class InferFillsTest(unittest.TestCase):
    def test_bid_fills_when_next_ask_crosses(self) -> None:
        self.assertEqual(mm.infer_fills(0.49, 0.51, 0.47, 0.49), ["buy"])

    def test_ask_fills_when_next_bid_crosses(self) -> None:
        self.assertEqual(mm.infer_fills(0.49, 0.51, 0.51, 0.53), ["sell"])

    def test_no_fill_without_cross(self) -> None:
        self.assertEqual(mm.infer_fills(0.49, 0.51, 0.495, 0.505), [])

    def test_pulled_side_cannot_fill(self) -> None:
        self.assertEqual(mm.infer_fills(None, 0.51, 0.40, 0.42), [])


class RunTokenTest(unittest.TestCase):
    def test_fills_happen_at_quoted_prices_and_accounting_is_consistent(self) -> None:
        series = [
            (0.0, 0.49, 0.51),    # quotiert 0.49 / 0.51
            (10.0, 0.47, 0.49),   # Ask kreuzt runter: buy-Fill zu 0.49
            (30.0, 0.52, 0.54),   # Bid kreuzt hoch: sell-Fill zur Ask-Quote
            (40.0, 0.52, 0.54),
        ]
        result = mm.run_token("t", series, P)
        seiten = [f.side for f in result.fills]
        self.assertIn("buy", seiten)
        self.assertIn("sell", seiten)
        kauf = next(f for f in result.fills if f.side == "buy")
        self.assertAlmostEqual(kauf.price, 0.49, places=4)  # exakt unsere Quote
        # Kontoführung: equity == Cash-Fluss der Fills + Inventar * letzter Mid.
        cash = sum((f.shares * f.price if f.side == "sell" else -f.shares * f.price)
                   for f in result.fills)
        inventar = sum((f.shares if f.side == "buy" else -f.shares)
                       for f in result.fills)
        letzter_mid = (series[-1][1] + series[-1][2]) / 2.0
        self.assertAlmostEqual(result.equity_final,
                               cash + inventar * letzter_mid, delta=0.05)

    def test_no_quotes_outside_mid_bounds(self) -> None:
        series = [(0.0, 0.965, 0.975), (10.0, 0.90, 0.92)]
        result = mm.run_token("t", series, P)
        self.assertEqual(result.fills, [])  # Aufloesungszone: nie quotiert

    def test_wide_books_pull_quotes(self) -> None:
        series = [(0.0, 0.30, 0.70), (10.0, 0.10, 0.20)]
        result = mm.run_token("t", series, P)
        self.assertEqual(result.fills, [])

    def test_markout_negative_when_market_runs_against_buy(self) -> None:
        series = [
            (0.0, 0.49, 0.51),
            (10.0, 0.47, 0.49),     # buy zu 0.49
            (320.0, 0.40, 0.42),    # 5min spaeter: Mid 0.41 -> Markout negativ
            (330.0, 0.40, 0.42),
        ]
        result = mm.run_token("t", series, P)
        kauf = next(f for f in result.fills if f.side == "buy")
        self.assertIsNotNone(kauf.markout)
        self.assertLess(kauf.markout, 0)

    def test_skew_reduces_terminal_inventory_on_one_sided_flow(self) -> None:
        # Schnell fallender Markt (2 Cents pro Schritt, schneller als der
        # halbe Spread): der Ask kreuzt wiederholt unsere Bids. Enges Cap,
        # damit der Skew frueh greift; hohes gamma zieht das Bid weg.
        series = [(float(i * 10), 0.60 - i * 0.02, 0.62 - i * 0.02)
                  for i in range(8)]
        ohne = mm.run_token("t", series, mm.QuoteParams(
            half_spread=0.01, gamma=0.0, quote_usd=50.0,
            inventory_cap_usd=200.0))
        mit = mm.run_token("t", series, mm.QuoteParams(
            half_spread=0.01, gamma=0.5, quote_usd=50.0,
            inventory_cap_usd=200.0))
        inv_ohne = abs(ohne.inventory_path[-1][1])
        inv_mit = abs(mit.inventory_path[-1][1])
        self.assertGreater(inv_ohne, 0.0)  # ohne Skew laeuft Inventar auf
        self.assertLess(inv_mit, inv_ohne)


class ExperimentTest(unittest.TestCase):
    def test_two_modes_reported(self) -> None:
        series = {"t": [(0.0, 0.49, 0.51), (10.0, 0.47, 0.49),
                        (20.0, 0.52, 0.54)]}
        exp = mm.run_experiment(series, P)
        self.assertEqual(set(exp), {"skew_on", "skew_off"})
        self.assertEqual(exp["skew_off"]["params"].gamma, 0.0)
        self.assertGreaterEqual(exp["skew_on"]["fills"], 1)


if __name__ == "__main__":
    unittest.main()
