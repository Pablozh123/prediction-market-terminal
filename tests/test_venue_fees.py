import math
import unittest

from app import venue_fees as vf


class PolymarketFeeTests(unittest.TestCase):
    def test_formula_matches_documented_shape(self):
        # fee = shares * rate * p * (1 - p), Politik-Rate 0.04
        fee = vf.polymarket_taker_fee(100, 0.5, "politics")
        self.assertAlmostEqual(fee, 100 * 0.04 * 0.25, places=9)

    def test_fee_is_symmetric_around_fifty_cents(self):
        low = vf.polymarket_taker_fee(100, 0.25, "sports")
        high = vf.polymarket_taker_fee(100, 0.75, "sports")
        self.assertAlmostEqual(low, high, places=9)

    def test_fee_peaks_at_the_middle(self):
        mid = vf.polymarket_taker_fee(100, 0.50, "crypto")
        edge = vf.polymarket_taker_fee(100, 0.05, "crypto")
        self.assertGreater(mid, edge)

    def test_geopolitics_is_fee_free(self):
        self.assertEqual(vf.polymarket_taker_fee(1000, 0.5, "geopolitics"), 0.0)

    def test_unknown_category_falls_back_to_general_rate(self):
        self.assertEqual(vf.polymarket_category_rate("does-not-exist"),
                         vf.POLYMARKET_TAKER_RATES["other"])

    def test_category_lookup_is_case_insensitive(self):
        self.assertEqual(vf.polymarket_category_rate("PoLiTiCs"), 0.04)

    def test_makers_pay_nothing(self):
        self.assertEqual(vf.polymarket_maker_fee(500, 0.5, "crypto"), 0.0)

    def test_maker_rebate_is_bounded_by_the_taker_fee(self):
        shares, price, cat = 100, 0.5, "crypto"
        rebate = vf.polymarket_maker_rebate(shares, price, cat)
        self.assertLess(rebate, vf.polymarket_taker_fee(shares, price, cat))
        self.assertGreater(rebate, 0.0)

    def test_prices_outside_the_unit_interval_never_credit(self):
        self.assertEqual(vf.polymarket_taker_fee(100, 1.4, "sports"), 0.0)
        self.assertEqual(vf.polymarket_taker_fee(100, -0.2, "sports"), 0.0)

    def test_negative_size_is_clamped(self):
        self.assertEqual(vf.polymarket_taker_fee(-100, 0.5, "sports"), 0.0)


class KalshiFeeTests(unittest.TestCase):
    def test_formula_with_ceiling_to_the_next_cent(self):
        # 0.07 * 100 * 0.5 * 0.5 = 1.75 exakt, kein Aufrunden noetig
        self.assertAlmostEqual(vf.kalshi_taker_fee(100, 0.5), 1.75, places=9)

    def test_order_level_rounding_hits_small_clips_hardest(self):
        # 0.07 * 1 * 0.25 = 0.0175 -> aufgerundet 0.02, also 14 Prozent teurer
        self.assertAlmostEqual(vf.kalshi_taker_fee(1, 0.5), 0.02, places=9)
        per_share_small = vf.fee_cents_per_share("kalshi", 0.5, shares=1)
        per_share_block = vf.fee_cents_per_share("kalshi", 0.5, shares=1000)
        self.assertGreater(per_share_small, per_share_block)

    def test_zero_fee_at_the_boundaries(self):
        self.assertEqual(vf.kalshi_taker_fee(100, 1.0), 0.0)
        self.assertEqual(vf.kalshi_taker_fee(100, 0.0), 0.0)

    def test_maker_rate_is_a_quarter_of_the_taker_rate(self):
        self.assertAlmostEqual(vf.KALSHI_MAKER_RATE / vf.KALSHI_TAKER_RATE,
                               0.25, places=6)

    def test_maker_fee_is_cheaper_than_taker_fee_on_a_block(self):
        self.assertLess(vf.kalshi_maker_fee(1000, 0.5),
                        vf.kalshi_taker_fee(1000, 0.5))

    def test_kalshi_is_dearer_than_polymarket_politics_at_the_middle(self):
        # Gleiche Funktionsform, Rate 0.07 vs 0.04
        self.assertGreater(vf.kalshi_taker_fee(1000, 0.5),
                           vf.polymarket_taker_fee(1000, 0.5, "politics"))


class DispatchTests(unittest.TestCase):
    def test_venue_dispatch_picks_the_right_model(self):
        self.assertEqual(vf.taker_fee("kalshi", 100, 0.5),
                         vf.kalshi_taker_fee(100, 0.5))
        self.assertEqual(vf.taker_fee("polymarket", 100, 0.5, "sports"),
                         vf.polymarket_taker_fee(100, 0.5, "sports"))

    def test_unknown_venue_defaults_to_polymarket(self):
        self.assertEqual(vf.taker_fee("some-new-venue", 100, 0.5, "sports"),
                         vf.polymarket_taker_fee(100, 0.5, "sports"))

    def test_fee_cents_per_share_scales_out_the_size(self):
        cents = vf.fee_cents_per_share("polymarket", 0.5, "politics", shares=100)
        self.assertAlmostEqual(cents, 100 * 0.04 * 0.25, places=6)


class BasketEconomicsTests(unittest.TestCase):
    def test_a_gap_that_only_covers_fees_is_not_an_arbitrage(self):
        # Fees: Polymarket Politics 0.04*0.25 = 1.0 Cent, Kalshi 0.07*0.25 = 1.75 Cent
        # zusammen 2.75 Cent. Ein Gap von 2 Cent reicht damit nicht.
        leg_a = vf.BasketLeg("polymarket", 0.49, 1000, "politics")
        leg_b = vf.BasketLeg("kalshi", 0.49, 1000)
        result = vf.basket_economics(leg_a, leg_b)
        self.assertGreater(result["gross_edge_per_share"], 0)
        self.assertFalse(result["is_arbitrage"])
        self.assertLess(result["net_edge_per_share"], 0)

    def test_a_wide_enough_gap_survives_both_fees(self):
        leg_a = vf.BasketLeg("polymarket", 0.45, 1000, "politics")
        leg_b = vf.BasketLeg("kalshi", 0.45, 1000)
        result = vf.basket_economics(leg_a, leg_b)
        self.assertTrue(result["is_arbitrage"])
        self.assertGreater(result["net_profit_usd"], 0)

    def test_size_is_capped_by_the_shallower_book(self):
        leg_a = vf.BasketLeg("polymarket", 0.45, depth_shares=20, category="politics")
        leg_b = vf.BasketLeg("kalshi", 0.45, depth_shares=5000)
        result = vf.basket_economics(leg_a, leg_b)
        self.assertEqual(result["shares"], 20)

    def test_requested_size_cannot_exceed_available_depth(self):
        leg_a = vf.BasketLeg("polymarket", 0.45, depth_shares=20, category="politics")
        leg_b = vf.BasketLeg("kalshi", 0.45, depth_shares=5000)
        result = vf.basket_economics(leg_a, leg_b, shares=1000)
        self.assertEqual(result["shares"], 20)

    def test_breakeven_gap_equals_the_no_arb_band(self):
        leg_a = vf.BasketLeg("polymarket", 0.49, 1000, "politics")
        leg_b = vf.BasketLeg("kalshi", 0.49, 1000)
        result = vf.basket_economics(leg_a, leg_b)
        band = vf.no_arb_band_cents(0.49, 0.49, "polymarket", "kalshi",
                                    "politics", None, shares=1000)
        self.assertAlmostEqual(result["breakeven_gap_cents"], band, places=3)

    def test_geopolitics_leg_pays_no_fee(self):
        leg_a = vf.BasketLeg("polymarket", 0.49, 1000, "geopolitics")
        leg_b = vf.BasketLeg("polymarket", 0.49, 1000, "geopolitics")
        result = vf.basket_economics(leg_a, leg_b)
        self.assertEqual(result["fee_usd_total"], 0.0)
        self.assertTrue(result["is_arbitrage"])

    def test_maker_leg_on_polymarket_is_free(self):
        taker = vf.BasketLeg("polymarket", 0.49, 1000, "politics", is_taker=True)
        maker = vf.BasketLeg("polymarket", 0.49, 1000, "politics", is_taker=False)
        self.assertGreater(taker.fee_usd(1000), 0.0)
        self.assertEqual(maker.fee_usd(1000), 0.0)

    def test_carry_case_annualises_a_small_edge_over_a_long_hold(self):
        leg_a = vf.BasketLeg("polymarket", 0.45, 1000, "politics")
        leg_b = vf.BasketLeg("kalshi", 0.45, 1000)
        quick = vf.basket_economics(leg_a, leg_b, days_to_resolution=60)
        slow = vf.basket_economics(leg_a, leg_b, days_to_resolution=180)
        self.assertEqual(quick["return_on_capital"], slow["return_on_capital"])
        self.assertGreater(quick["annualised_return"], slow["annualised_return"])

    def test_short_horizons_are_not_annualised(self):
        """Vier Tage auf ein Jahr hochgerechnet ergibt 1e63 Prozent.

        Die Potenz ist korrekt und die Aussage wertlos: sie unterstellt, der
        Abstand liesse sich neunzigmal im Jahr wiederholen. Genau so eine Zahl
        stand in der Cross-Venue-Belegtabelle.
        """
        leg_a = vf.BasketLeg("polymarket", 0.10, 1000, "politics")
        leg_b = vf.BasketLeg("kalshi", 0.11, 1000)
        kurz = vf.basket_economics(leg_a, leg_b, days_to_resolution=4)
        self.assertIsNone(kurz["annualised_return"])
        self.assertIsNotNone(kurz["return_on_capital"])

        knapp_darueber = vf.basket_economics(
            leg_a, leg_b, days_to_resolution=vf.MIN_ANNUALISIERUNG_TAGE)
        self.assertIsNotNone(knapp_darueber["annualised_return"])

    def test_zero_depth_yields_no_trade(self):
        leg_a = vf.BasketLeg("polymarket", 0.45, depth_shares=0, category="politics")
        leg_b = vf.BasketLeg("kalshi", 0.45, depth_shares=100)
        result = vf.basket_economics(leg_a, leg_b)
        self.assertEqual(result["shares"], 0)
        self.assertFalse(result["is_arbitrage"])


class AnnualisationTests(unittest.TestCase):
    def test_one_year_hold_returns_the_period_return(self):
        self.assertAlmostEqual(vf.annualised_return(0.10, 365), 0.10, places=6)

    def test_compounding_shortens_with_the_holding_period(self):
        self.assertAlmostEqual(vf.annualised_return(0.01, 182.5),
                               1.01 ** 2 - 1, places=6)

    def test_non_positive_horizon_is_undefined(self):
        self.assertIsNone(vf.annualised_return(0.05, 0))
        self.assertIsNone(vf.annualised_return(0.05, -3))

    def test_missing_return_stays_missing(self):
        self.assertIsNone(vf.annualised_return(None, 30))

    def test_total_loss_cannot_compound_below_minus_one(self):
        self.assertEqual(vf.annualised_return(-1.5, 30), -1.0)


class RoundTripCostTests(unittest.TestCase):
    def test_round_trip_counts_two_fees_and_two_half_spreads(self):
        cost = vf.round_trip_cost_cents("polymarket", 0.5, "politics",
                                        half_spread_cents=0.5, shares=1000)
        fee = vf.fee_cents_per_share("polymarket", 0.5, "politics", shares=1000)
        self.assertAlmostEqual(cost, 2 * fee + 1.0, places=4)

    def test_the_hurdle_is_lowest_at_the_extremes(self):
        middle = vf.round_trip_cost_cents("kalshi", 0.5, shares=1000)
        wing = vf.round_trip_cost_cents("kalshi", 0.10, shares=1000)
        self.assertGreater(middle, wing)

    def test_fee_model_version_is_exposed_for_report_footers(self):
        self.assertTrue(vf.FEE_MODEL_VERSION)
        self.assertIn("polymarket", vf.FEE_SOURCES)


class SanityTests(unittest.TestCase):
    def test_documented_rate_table_stays_within_plausible_bounds(self):
        for category, rate in vf.POLYMARKET_TAKER_RATES.items():
            self.assertGreaterEqual(rate, 0.0, category)
            self.assertLessEqual(rate, 0.10, category)

    def test_fee_never_exceeds_the_notional(self):
        for price in (0.01, 0.1, 0.5, 0.9, 0.99):
            fee = vf.polymarket_taker_fee(100, price, "crypto")
            self.assertLess(fee, 100 * price)
            self.assertTrue(math.isfinite(fee))


if __name__ == "__main__":
    unittest.main()


class BpsVergleichTests(unittest.TestCase):
    """Der Backtester rechnet flach; hier steht, wie weit das danebenliegt."""

    def test_gebuehr_in_bps_haengt_am_preis(self):
        mitte = vf.taker_fee_bps("polymarket", 0.50, "politics")
        rand = vf.taker_fee_bps("polymarket", 0.90, "politics")
        self.assertGreater(mitte, rand)
        self.assertGreater(mitte, 100.0)

    def test_flache_zwanzig_bps_unterschaetzen_die_mitte_deutlich(self):
        """Die Vorgabe des Backtesters gegen das echte Modell."""
        from app import backtester as btr

        flach = btr.BacktestConfig(wallet="0xtest").fee_bps
        echt = vf.taker_fee_bps("polymarket", 0.50, "politics")
        self.assertGreater(echt, flach * 5,
                           "wenn das nicht mehr gilt, gehoert der Hinweis im UI angepasst")

    def test_ohne_einsatz_keine_bps(self):
        self.assertEqual(vf.taker_fee_bps("polymarket", 0.0, "politics"), 0.0)
