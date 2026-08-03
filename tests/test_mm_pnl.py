import json
import tempfile
import unittest
from pathlib import Path

from src import mm_pnl
from src import orderflow_study as ofs
from src.mm_simulator import QuoteParams


def book_series(n=30, step=120.0, mid=0.50, drift=0.0, spread=0.02,
                day="2026-07-01", start=1_000_000.0, imbalance=0.5):
    return [
        ofs.BookPoint(ts=start + i * step, mid=round(mid + i * drift, 6),
                      spread=spread, imbalance=imbalance, day=day)
        for i in range(n)
    ]


def fill(side="buy", price=0.49, shares=100.0, mid_at_fill=0.50,
         mid_markout=0.50, mid_final=0.50, day="2026-07-01"):
    return mm_pnl.MMFill(token_id="t", day=day, ts=0.0, side=side, price=price,
                         shares=shares, mid_at_fill=mid_at_fill,
                         mid_markout=mid_markout, mid_final=mid_final)


class FillMathTests(unittest.TestCase):
    def test_buying_below_the_mid_earns_spread(self):
        f = fill(side="buy", price=0.49, mid_at_fill=0.50, shares=100)
        self.assertAlmostEqual(f.spread_capture_usd, 1.0, places=6)

    def test_selling_above_the_mid_earns_spread(self):
        f = fill(side="sell", price=0.51, mid_at_fill=0.50, shares=100)
        self.assertAlmostEqual(f.spread_capture_usd, 1.0, places=6)

    def test_a_long_fill_followed_by_a_falling_mid_is_adverse_selection(self):
        f = fill(side="buy", price=0.49, mid_at_fill=0.50, mid_markout=0.45,
                 shares=100)
        self.assertLess(f.markout_usd, 0)

    def test_a_short_fill_followed_by_a_rising_mid_is_adverse_selection(self):
        f = fill(side="sell", price=0.51, mid_at_fill=0.50, mid_markout=0.55,
                 shares=100)
        self.assertLess(f.markout_usd, 0)

    def test_missing_markout_reference_contributes_nothing(self):
        f = fill(mid_markout=None, mid_final=0.60)
        self.assertEqual(f.markout_usd, 0.0)

    def test_signed_shares_flip_with_the_side(self):
        self.assertEqual(fill(side="buy", shares=10).signed_shares, 10)
        self.assertEqual(fill(side="sell", shares=10).signed_shares, -10)


class IdentityTests(unittest.TestCase):
    """The decomposition must reconstruct terminal PnL exactly, not roughly."""

    def test_identity_holds_for_a_single_buy(self):
        f = fill(side="buy", price=0.49, mid_at_fill=0.50, mid_markout=0.52,
                 mid_final=0.55, shares=100)
        parts = f.spread_capture_usd + f.markout_usd + f.late_drift_usd
        self.assertAlmostEqual(parts, f.terminal_usd, places=9)

    def test_identity_holds_for_a_single_sell(self):
        f = fill(side="sell", price=0.51, mid_at_fill=0.50, mid_markout=0.47,
                 mid_final=0.40, shares=100)
        parts = f.spread_capture_usd + f.markout_usd + f.late_drift_usd
        self.assertAlmostEqual(parts, f.terminal_usd, places=9)

    def test_identity_holds_without_a_markout_reference(self):
        f = fill(side="buy", price=0.49, mid_at_fill=0.50, mid_markout=None,
                 mid_final=0.55, shares=100)
        parts = f.spread_capture_usd + f.markout_usd + f.late_drift_usd
        self.assertAlmostEqual(parts, f.terminal_usd, places=9)

    def test_identity_holds_across_an_aggregated_run(self):
        fills = [
            fill(side="buy", price=0.48, mid_at_fill=0.50, mid_markout=0.51,
                 mid_final=0.53),
            fill(side="sell", price=0.53, mid_at_fill=0.52, mid_markout=0.50,
                 mid_final=0.53),
            fill(side="buy", price=0.30, mid_at_fill=0.31, mid_markout=0.29,
                 mid_final=0.25),
        ]
        run = mm_pnl.TokenRun(token_id="t", fills=fills)
        decomposition = mm_pnl.decompose([run])
        expected = sum(f.terminal_usd for f in fills)
        self.assertAlmostEqual(decomposition.mark_to_mid_usd, expected, places=9)

    def test_total_adds_rebate_on_top_of_mark_to_mid(self):
        run = mm_pnl.TokenRun(token_id="t", fills=[fill()])
        decomposition = mm_pnl.decompose([run], category="sports")
        self.assertGreater(decomposition.rebate_usd, 0)
        self.assertAlmostEqual(
            decomposition.total_usd,
            decomposition.mark_to_mid_usd + decomposition.rebate_usd,
            places=9)

    def test_a_fee_free_category_pays_no_rebate(self):
        run = mm_pnl.TokenRun(token_id="t", fills=[fill()])
        decomposition = mm_pnl.decompose([run], category="geopolitics")
        self.assertEqual(decomposition.rebate_usd, 0.0)

    def test_kalshi_makers_are_charged_instead_of_paid(self):
        run = mm_pnl.TokenRun(token_id="t", fills=[fill()])
        decomposition = mm_pnl.decompose([run], venue="kalshi")
        self.assertGreater(decomposition.fee_usd, 0)
        self.assertEqual(decomposition.rebate_usd, 0.0)
        self.assertLess(decomposition.total_usd, decomposition.mark_to_mid_usd)


class TouchFillTests(unittest.TestCase):
    def test_a_crossing_ask_fills_our_bid(self):
        self.assertEqual(mm_pnl.touch_fills(0.50, 0.55, 0.44, 0.49), ["buy"])

    def test_a_crossing_bid_fills_our_ask(self):
        self.assertEqual(mm_pnl.touch_fills(0.40, 0.50, 0.51, 0.56), ["sell"])

    def test_an_untouched_book_fills_nothing(self):
        self.assertEqual(mm_pnl.touch_fills(0.40, 0.60, 0.45, 0.55), [])

    def test_a_missing_quote_cannot_fill(self):
        self.assertEqual(mm_pnl.touch_fills(None, 0.60, 0.10, 0.20), [])


class TapeFillTests(unittest.TestCase):
    def test_a_taker_sell_through_our_bid_fills_us_long(self):
        prints = [(1.0, 0.48, -100.0)]
        self.assertEqual(mm_pnl.tape_fills(0.50, 0.55, prints), [("buy", 0.50)])

    def test_a_taker_buy_through_our_ask_fills_us_short(self):
        prints = [(1.0, 0.56, 100.0)]
        self.assertEqual(mm_pnl.tape_fills(0.50, 0.55, prints), [("sell", 0.55)])

    def test_a_print_that_does_not_reach_our_quote_is_ignored(self):
        prints = [(1.0, 0.52, -100.0)]
        self.assertEqual(mm_pnl.tape_fills(0.50, 0.55, prints), [])

    def test_a_taker_sell_cannot_fill_our_ask(self):
        prints = [(1.0, 0.99, -100.0)]
        self.assertEqual(mm_pnl.tape_fills(0.50, 0.55, prints), [])

    def test_a_side_fills_at_most_once_per_interval(self):
        # Unsere Quote hat eine endliche Groesse. Ohne dieses Limit fuellt ein
        # aktiver Token dieselben 50 Dollar bei jedem Print im Intervall und
        # der Inventar-Cap wird bedeutungslos.
        prints = [(1.0, 0.48, -100.0), (2.0, 0.47, -50.0), (3.0, 0.46, -25.0)]
        self.assertEqual(mm_pnl.tape_fills(0.50, 0.55, prints), [("buy", 0.50)])

    def test_both_sides_can_fill_once_each(self):
        prints = [(1.0, 0.48, -100.0), (2.0, 0.56, 100.0)]
        fills = mm_pnl.tape_fills(0.50, 0.55, prints)
        self.assertEqual(sorted(side for side, _ in fills), ["buy", "sell"])

    def test_no_quote_means_no_fill(self):
        self.assertEqual(mm_pnl.tape_fills(None, None, [(1.0, 0.4, -10.0)]), [])


class QuoteSideTests(unittest.TestCase):
    def test_symmetric_mode_always_shows_both_sides(self):
        for imbalance in (0.05, 0.5, 0.95):
            self.assertEqual(mm_pnl.quote_sides(imbalance, 0.65, "symmetric"),
                             (True, True))

    def test_a_bid_heavy_book_pulls_the_ask(self):
        # Bid-lastig heisst steigende Tendenz; verkauft zu werden hiesse dann,
        # short in einen Anstieg zu gehen. Also Gegenseite ziehen.
        self.assertEqual(mm_pnl.quote_sides(0.90, 0.65, "signal"), (True, False))

    def test_an_ask_heavy_book_pulls_the_bid(self):
        self.assertEqual(mm_pnl.quote_sides(0.10, 0.65, "signal"), (False, True))

    def test_a_neutral_book_keeps_both_sides(self):
        self.assertEqual(mm_pnl.quote_sides(0.50, 0.65, "signal"), (True, True))

    def test_lean_mode_only_reacts_to_extremes(self):
        mild = mm_pnl.quote_sides(0.70, 0.65, "lean")
        strong = mm_pnl.quote_sides(0.95, 0.65, "lean")
        self.assertEqual(mild, (True, True))
        self.assertEqual(strong, (True, False))

    def test_lean_is_never_stricter_than_signal(self):
        for imbalance in (0.05, 0.3, 0.5, 0.7, 0.95):
            lean = mm_pnl.quote_sides(imbalance, 0.65, "lean")
            signal = mm_pnl.quote_sides(imbalance, 0.65, "signal")
            self.assertGreaterEqual(sum(lean), sum(signal), imbalance)

    def test_unknown_mode_is_a_programming_error(self):
        with self.assertRaises(ValueError):
            mm_pnl.quote_sides(0.5, 0.65, "hellsehen")


class SignalQuotingTests(unittest.TestCase):
    def setUp(self):
        self.params = QuoteParams(half_spread=0.01, gamma=0.08, quote_usd=50.0,
                                  inventory_cap_usd=250.0)

    def test_signal_mode_fills_only_on_the_favoured_side(self):
        # Buch dauerhaft bid-lastig -> nur die Bid-Seite steht, also nur Kaeufe.
        series = book_series(n=20, imbalance=0.95)
        trades = [ofs.TradePoint(ts=1_000_000 + i * 120 - 1, signed_usd=sign * 100.0,
                                 usd=100.0, price=price)
                  for i in range(1, 20)
                  for sign, price in ((-1.0, 0.40), (1.0, 0.60))]
        trades.sort(key=lambda t: t.ts)
        run = mm_pnl.run_token("t", series, trades, self.params, "tape",
                               quote_mode="signal")
        self.assertTrue(run.fills)
        self.assertEqual({f.side for f in run.fills}, {"buy"})

    def test_symmetric_mode_fills_on_both_sides_of_the_same_tape(self):
        series = book_series(n=20, imbalance=0.95)
        trades = [ofs.TradePoint(ts=1_000_000 + i * 120 - 1, signed_usd=sign * 100.0,
                                 usd=100.0, price=price)
                  for i in range(1, 20)
                  for sign, price in ((-1.0, 0.40), (1.0, 0.60))]
        trades.sort(key=lambda t: t.ts)
        run = mm_pnl.run_token("t", series, trades, self.params, "tape",
                               quote_mode="symmetric")
        self.assertEqual({f.side for f in run.fills}, {"buy", "sell"})

    def test_comparison_scores_every_mode(self):
        books = {"t": book_series(n=40, imbalance=0.9)}
        trades = {"t": [ofs.TradePoint(ts=1_000_000 + i * 120 - 1,
                                       signed_usd=-100.0, usd=100.0, price=0.40)
                        for i in range(1, 40)]}
        rows = mm_pnl.quote_mode_comparison(books, trades, self.params,
                                            fill_model="tape",
                                            modes=("symmetric", "signal"))
        self.assertEqual([r["quote_mode"] for r in rows], ["symmetric", "signal"])
        self.assertTrue(all("markout_cents_per_fill" in r for r in rows))


class RunTokenTests(unittest.TestCase):
    def setUp(self):
        self.params = QuoteParams(half_spread=0.01, gamma=0.08, quote_usd=50.0,
                                  inventory_cap_usd=250.0)

    def test_a_flat_quiet_book_produces_no_touch_fills(self):
        run = mm_pnl.run_token("t", book_series(), [], self.params,
                               fill_model="touch")
        self.assertEqual(run.fills, [])

    def test_a_series_that_is_too_short_returns_empty(self):
        run = mm_pnl.run_token("t", book_series(n=1), [], self.params)
        self.assertEqual(run.fills, [])

    def test_a_swinging_market_generates_touch_fills(self):
        series = []
        for i in range(40):
            mid = 0.50 + (0.06 if i % 2 else -0.06)
            series.append(ofs.BookPoint(ts=1_000_000 + i * 120, mid=mid,
                                        spread=0.01, imbalance=0.5,
                                        day="2026-07-01"))
        run = mm_pnl.run_token("t", series, [], self.params, fill_model="touch")
        self.assertTrue(run.fills)

    def test_tape_prints_generate_fills_where_touch_does_not(self):
        series = book_series(n=10)
        trades = [ofs.TradePoint(ts=1_000_000 + i * 120 - 1, signed_usd=-100.0,
                                 usd=100.0, price=0.40) for i in range(1, 10)]
        touch = mm_pnl.run_token("t", series, trades, self.params, "touch")
        tape = mm_pnl.run_token("t", series, trades, self.params, "tape")
        self.assertEqual(touch.fills, [])
        self.assertTrue(tape.fills)

    def test_quotes_are_pulled_in_the_resolution_zone(self):
        series = book_series(n=20, mid=0.99, spread=0.005)
        trades = [ofs.TradePoint(ts=1_000_000 + i * 120 - 1, signed_usd=-100.0,
                                 usd=100.0, price=0.10) for i in range(1, 20)]
        run = mm_pnl.run_token("t", series, trades, self.params, "tape")
        self.assertEqual(run.fills, [])

    def test_wide_spreads_stop_quoting(self):
        series = book_series(n=20, spread=0.5)
        trades = [ofs.TradePoint(ts=1_000_000 + i * 120 - 1, signed_usd=-100.0,
                                 usd=100.0, price=0.10) for i in range(1, 20)]
        run = mm_pnl.run_token("t", series, trades, self.params, "tape")
        self.assertEqual(run.fills, [])

    def test_spread_capture_is_positive_because_we_quote_around_the_mid(self):
        # Referenz ist der Mid zum Zeitpunkt des Quotens. Waere es der Mid nach
        # der Bewegung, die uns gefuellt hat, waere der Spread-Ertrag per
        # Konstruktion negativ und die Zerlegung waertlos.
        series = book_series(n=20)
        trades = [ofs.TradePoint(ts=1_000_000 + i * 120 - 1, signed_usd=-100.0,
                                 usd=100.0, price=0.40) for i in range(1, 20)]
        run = mm_pnl.run_token("t", series, trades, self.params, "tape")
        self.assertTrue(run.fills)
        self.assertTrue(all(f.spread_capture_usd > 0 for f in run.fills))

    def test_the_reference_mid_is_the_quoting_mid_not_the_fill_mid(self):
        series = [
            ofs.BookPoint(ts=1_000_000, mid=0.50, spread=0.02,
                          imbalance=0.5, day="2026-07-01"),
            ofs.BookPoint(ts=1_000_120, mid=0.40, spread=0.02,
                          imbalance=0.5, day="2026-07-01"),
            ofs.BookPoint(ts=1_000_240, mid=0.40, spread=0.02,
                          imbalance=0.5, day="2026-07-01"),
        ]
        trades = [ofs.TradePoint(ts=1_000_119, signed_usd=-100.0, usd=100.0,
                                 price=0.30)]
        run = mm_pnl.run_token("t", series, trades, self.params, "tape")
        self.assertTrue(run.fills)
        self.assertEqual(run.fills[0].mid_at_fill, 0.50)

    def test_inventory_is_tracked_over_the_run(self):
        series = book_series(n=10)
        trades = [ofs.TradePoint(ts=1_000_000 + i * 120 - 1, signed_usd=-100.0,
                                 usd=100.0, price=0.40) for i in range(1, 10)]
        run = mm_pnl.run_token("t", series, trades, self.params, "tape")
        self.assertTrue(any(v != 0 for v in run.inventory_path))


class InventoryCapTests(unittest.TestCase):
    def test_the_cap_stops_a_one_sided_inventory_from_running_away(self):
        params = QuoteParams(half_spread=0.01, gamma=0.08, quote_usd=50.0,
                             inventory_cap_usd=100.0)
        series = book_series(n=40)
        trades = [ofs.TradePoint(ts=1_000_000 + i * 120 - 1, signed_usd=-100.0,
                                 usd=100.0, price=0.30) for i in range(1, 40)]
        run = mm_pnl.run_token("t", series, trades, params, "tape")
        self.assertTrue(run.inventory_path)
        # Der Cap wirkt erst nach dem Fill, ein Quote darf ihn also einmal
        # ueberschreiten - aber nicht unbegrenzt weiterlaufen.
        self.assertLess(max(run.inventory_path), 100.0 + 2 * params.quote_usd)


class SplitTests(unittest.TestCase):
    def test_days_are_split_chronologically(self):
        books = {"t": book_series(n=5, day="2026-07-01")
                 + book_series(n=5, day="2026-07-02", start=2_000_000)
                 + book_series(n=5, day="2026-07-03", start=3_000_000)}
        train, test = mm_pnl.split_books_by_day(books, train_share=0.6)
        self.assertEqual({p.day for p in train["t"]}, {"2026-07-01"})
        self.assertEqual({p.day for p in test["t"]}, {"2026-07-02", "2026-07-03"})

    def test_a_single_day_cannot_be_split(self):
        books = {"t": book_series(n=5, day="2026-07-01")}
        train, test = mm_pnl.split_books_by_day(books)
        self.assertEqual(test, {})
        self.assertEqual(len(train["t"]), 5)

    def test_per_day_totals_group_by_calendar_day(self):
        fills = [fill(day="2026-07-01"), fill(day="2026-07-02"),
                 fill(day="2026-07-02")]
        totals = mm_pnl.per_day_totals([mm_pnl.TokenRun("t", fills)])
        self.assertEqual(sorted(totals), ["2026-07-01", "2026-07-02"])
        self.assertAlmostEqual(totals["2026-07-02"], 2 * totals["2026-07-01"],
                               places=6)


class SweepTests(unittest.TestCase):
    def setUp(self):
        self.params = QuoteParams(half_spread=0.01, gamma=0.08, quote_usd=50.0,
                                  inventory_cap_usd=250.0)
        self.books = {"t": book_series(n=40)}
        self.trades = {"t": [ofs.TradePoint(ts=1_000_000 + i * 120 - 1,
                                            signed_usd=-100.0, usd=100.0,
                                            price=0.40)
                             for i in range(1, 40)]}

    def test_sweep_returns_one_row_per_gamma(self):
        rows = mm_pnl.gamma_sweep(self.books, self.trades, self.params,
                                  gammas=(0.0, 0.1), fill_model="tape")
        self.assertEqual([r["gamma"] for r in rows], [0.0, 0.1])

    def test_stronger_skew_holds_less_inventory(self):
        rows = mm_pnl.gamma_sweep(self.books, self.trades, self.params,
                                  gammas=(0.0, 0.5), fill_model="tape")
        self.assertLessEqual(rows[1]["inventory_abs_mean_usd"],
                             rows[0]["inventory_abs_mean_usd"])

    def test_half_spread_sweep_returns_one_row_per_width(self):
        rows = mm_pnl.half_spread_sweep(self.books, self.trades, self.params,
                                        half_spreads=(0.01, 0.04),
                                        fill_model="tape")
        self.assertEqual([r["half_spread"] for r in rows], [0.01, 0.04])

    def test_a_wider_quote_earns_more_spread_per_fill(self):
        rows = mm_pnl.half_spread_sweep(self.books, self.trades, self.params,
                                        half_spreads=(0.01, 0.04),
                                        fill_model="tape")
        self.assertGreater(rows[1]["spread_capture_cents_per_fill"],
                           rows[0]["spread_capture_cents_per_fill"])

    def test_capture_over_markout_is_reported_as_the_breakeven_ratio(self):
        rows = mm_pnl.half_spread_sweep(self.books, self.trades, self.params,
                                        half_spreads=(0.01,), fill_model="tape")
        self.assertIn("capture_over_markout", rows[0])

    def test_walk_forward_reports_a_control_alongside_the_choice(self):
        books = {"t": book_series(n=20, day="2026-07-01")
                 + book_series(n=20, day="2026-07-02", start=2_000_000)
                 + book_series(n=20, day="2026-07-03", start=3_000_000)}
        trades = {"t": [ofs.TradePoint(ts=t, signed_usd=-100.0, usd=100.0,
                                       price=0.40)
                        for t in range(1_000_000, 3_002_400, 60)]}
        result = mm_pnl.walk_forward_gamma(books, trades, self.params,
                                           gammas=(0.0, 0.2), fill_model="tape")
        self.assertIn("chosen_gamma", result)
        self.assertIsNotNone(result["test"])
        self.assertIsNotNone(result["control_test"])

    def test_walk_forward_without_a_test_period_is_reported_as_such(self):
        result = mm_pnl.walk_forward_gamma(self.books, self.trades, self.params,
                                           gammas=(0.0,), fill_model="tape")
        self.assertIsNone(result["test"])


class RewardEstimateTests(unittest.TestCase):
    def setUp(self):
        self.params = QuoteParams(half_spread=0.01, gamma=0.08, quote_usd=50.0,
                                  inventory_cap_usd=250.0)

    def test_a_run_records_its_quote_path(self):
        run = mm_pnl.run_token("t", book_series(n=10), [], self.params)
        self.assertEqual(len(run.quote_path), 10)

    def test_reward_samples_weight_quotes_by_standing_time(self):
        run = mm_pnl.run_token("t", book_series(n=5, step=120.0), [], self.params)
        samples = run.reward_samples()
        self.assertEqual(len(samples), 4)
        self.assertTrue(all(s[0] == 120.0 for s in samples))

    def test_a_tight_quote_earns_a_reward(self):
        run = mm_pnl.run_token("t", book_series(n=30), [], self.params)
        estimate = mm_pnl.reward_estimate([run], quote_usd=50.0, pool_usd=100.0)
        self.assertGreater(estimate.usd(1.0), 0.0)

    def test_quoting_outside_the_reward_spread_earns_nothing(self):
        wide = QuoteParams(half_spread=0.09, gamma=0.0, quote_usd=50.0,
                           inventory_cap_usd=250.0)
        run = mm_pnl.run_token("t", book_series(n=30, spread=0.005), [], wide)
        estimate = mm_pnl.reward_estimate([run], quote_usd=50.0, pool_usd=100.0)
        self.assertEqual(estimate.usd(1.0), 0.0)

    def test_more_markets_earn_more_at_the_same_score(self):
        runs = [mm_pnl.run_token(f"t{i}", book_series(n=30), [], self.params)
                for i in range(3)]
        one = mm_pnl.reward_estimate(runs[:1], quote_usd=50.0, pool_usd=100.0)
        three = mm_pnl.reward_estimate(runs, quote_usd=50.0, pool_usd=100.0)
        self.assertAlmostEqual(three.usd(1.0), 3 * one.usd(1.0), places=4)

    def test_parallel_markets_do_not_inflate_the_hours_quoted(self):
        # Zehn Maerkte gleichzeitig zu quoten verlaengert nicht die Zeit am
        # Markt; sonst waere ein Portfolio automatisch zehnmal so lange da.
        runs = [mm_pnl.run_token(f"t{i}", book_series(n=31, step=120.0), [],
                                 self.params) for i in range(10)]
        estimate = mm_pnl.reward_estimate(runs, quote_usd=50.0)
        self.assertAlmostEqual(estimate.hours_quoted, 1.0, places=3)

    def test_an_empty_run_earns_no_reward(self):
        estimate = mm_pnl.reward_estimate([], quote_usd=50.0)
        self.assertEqual(estimate.usd(1.0), 0.0)
        self.assertEqual(estimate.markets, 0)


class LimitsSectionTests(unittest.TestCase):
    def _results(self, stream, days, fills, totals):
        return {
            "stream": stream,
            "days": [f"2026-07-{i:02d}" for i in range(1, days + 1)],
            "fill_models": {
                name: {"decomposition": {"fills": fills, "total_usd": total}}
                for name, total in totals.items()
            },
        }

    def test_a_rest_run_carries_the_staleness_caveat(self):
        text = " ".join(mm_pnl._limits_section(
            self._results(False, 11, 30000, {"touch": -1.0, "tape": -1.0})))
        self.assertIn("120-second grid", text)

    def test_a_stream_run_must_not_carry_the_rest_caveat(self):
        # Sonst stuende eine falsche Aussage im eingefrorenen Artefakt.
        text = " ".join(mm_pnl._limits_section(
            self._results(True, 11, 30000, {"touch": -1.0, "tape": -1.0})))
        self.assertNotIn("120-second grid", text)
        self.assertIn("under a second", text)

    def test_a_thin_sample_is_called_out(self):
        text = " ".join(mm_pnl._limits_section(
            self._results(True, 1, 230, {"touch": -1.0, "tape": 1.0})))
        self.assertIn("SAMPLE WARNING", text)

    def test_a_fat_sample_carries_no_sample_warning(self):
        text = " ".join(mm_pnl._limits_section(
            self._results(False, 11, 30000, {"touch": -1.0, "tape": -1.0})))
        self.assertNotIn("SAMPLE WARNING", text)

    def test_models_disagreeing_in_sign_is_stated(self):
        text = " ".join(mm_pnl._limits_section(
            self._results(True, 5, 5000, {"touch": -1.0, "tape": 1.0})))
        self.assertIn("do not even agree on the sign", text)

    def test_models_agreeing_in_sign_say_nothing_about_it(self):
        text = " ".join(mm_pnl._limits_section(
            self._results(False, 11, 30000, {"touch": -1.0, "tape": -2.0})))
        self.assertNotIn("do not even agree on the sign", text)


class EndToEndTests(unittest.TestCase):
    def _write(self, directory: Path, day: str, rows: int, mid_fn) -> None:
        import csv as _csv
        with open(directory / f"books_{day}.csv", "w", newline="",
                  encoding="utf-8") as handle:
            writer = _csv.DictWriter(handle, fieldnames=[
                "ts_utc", "token_id", "best_bid", "best_ask", "spread", "mid",
                "imbalance_top"])
            writer.writeheader()
            for i in range(rows):
                mid = mid_fn(i)
                writer.writerow({
                    "ts_utc": f"{day}T{i // 30:02d}:{(i * 2) % 60:02d}:00Z",
                    "token_id": "t1", "best_bid": round(mid - 0.01, 4),
                    "best_ask": round(mid + 0.01, 4), "spread": 0.02,
                    "mid": round(mid, 4), "imbalance_top": 0.5,
                })

    def test_study_runs_and_writes_reports(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "data"
            data.mkdir()
            for index, day in enumerate(("2026-07-01", "2026-07-02", "2026-07-03")):
                self._write(data, day, 40,
                            lambda i, o=index: 0.50 + (0.05 if i % 2 else -0.05))

            results = mm_pnl.run_study(data, gammas=(0.0, 0.08))
            self.assertEqual(results["tokens"], 1)
            self.assertIn("touch", results["fill_models"])
            self.assertIn("tape", results["fill_models"])

            out = Path(tmp) / "research"
            paths = mm_pnl.write_outputs(results, "test", research_dir=out)
            self.assertTrue(paths["md"].exists())
            body = paths["md"].read_text(encoding="utf-8")
            self.assertIn("PnL decomposition", body)
            self.assertNotIn("ß", body)
            payload = json.loads(paths["json"].read_text(encoding="utf-8"))
            self.assertIn("fill_models", payload)

    def test_study_on_an_empty_directory_does_not_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            results = mm_pnl.run_study(Path(tmp), gammas=(0.0,))
            self.assertEqual(results["tokens"], 0)
            self.assertEqual(
                results["fill_models"]["touch"]["decomposition"]["fills"], 0)


if __name__ == "__main__":
    unittest.main()
