import unittest

from app import liquidity_rewards as lr


class OrderScoreTests(unittest.TestCase):
    def test_an_order_at_the_mid_scores_the_maximum(self):
        self.assertAlmostEqual(lr.order_score(0.0, 4.5), 1.0, places=9)

    def test_an_order_at_the_cap_scores_nothing(self):
        self.assertEqual(lr.order_score(4.5, 4.5), 0.0)

    def test_an_order_beyond_the_cap_scores_nothing(self):
        self.assertEqual(lr.order_score(9.0, 4.5), 0.0)

    def test_the_score_is_quadratic_in_the_distance(self):
        # Halbe Entfernung zum Cap muss den vierfachen Score geben.
        near = lr.order_score(1.125, 4.5)   # (1 - 0.25)^2 = 0.5625
        far = lr.order_score(2.25, 4.5)     # (1 - 0.5)^2  = 0.25
        self.assertAlmostEqual(near / far, 2.25, places=6)

    def test_the_in_game_multiplier_scales_the_score(self):
        self.assertAlmostEqual(lr.order_score(1.0, 4.5, multiplier=2.0),
                               2 * lr.order_score(1.0, 4.5), places=9)

    def test_a_degenerate_cap_scores_nothing(self):
        self.assertEqual(lr.order_score(1.0, 0.0), 0.0)


class QualificationTests(unittest.TestCase):
    def test_an_order_at_the_minimum_size_qualifies(self):
        self.assertTrue(lr.qualifies(20.0, 20.0))

    def test_a_smaller_order_does_not(self):
        self.assertFalse(lr.qualifies(19.9, 20.0))

    def test_undersized_orders_contribute_nothing_to_a_side(self):
        self.assertEqual(lr.side_score([(0.5, 5.0)], min_size_shares=20.0), 0.0)

    def test_side_score_weights_by_size(self):
        one = lr.side_score([(1.0, 100.0)])
        two = lr.side_score([(1.0, 200.0)])
        self.assertAlmostEqual(two, 2 * one, places=9)

    def test_side_score_sums_several_orders(self):
        combined = lr.side_score([(1.0, 100.0), (2.0, 100.0)])
        separate = (lr.side_score([(1.0, 100.0)]) + lr.side_score([(2.0, 100.0)]))
        self.assertAlmostEqual(combined, separate, places=9)


class TwoSidedRuleTests(unittest.TestCase):
    def test_balanced_two_sided_quoting_scores_the_smaller_side(self):
        self.assertAlmostEqual(lr.q_min(10.0, 10.0, 0.5), 10.0, places=9)

    def test_in_the_middle_a_single_side_still_scores_a_third(self):
        self.assertAlmostEqual(lr.q_min(30.0, 0.0, 0.5), 10.0, places=9)

    def test_at_the_wings_a_single_side_scores_nothing(self):
        self.assertEqual(lr.q_min(30.0, 0.0, 0.95), 0.0)
        self.assertEqual(lr.q_min(30.0, 0.0, 0.05), 0.0)

    def test_the_band_edges_still_count_as_middle(self):
        self.assertGreater(lr.q_min(30.0, 0.0, 0.10), 0.0)
        self.assertGreater(lr.q_min(30.0, 0.0, 0.90), 0.0)

    def test_a_lopsided_quote_beats_the_pure_minimum_rule(self):
        # min waere 1.0, der Bonus hebt es auf 30/3 = 10.
        self.assertAlmostEqual(lr.q_min(30.0, 1.0, 0.5), 10.0, places=9)

    def test_negative_inputs_cannot_create_score(self):
        self.assertEqual(lr.q_min(-5.0, -5.0, 0.5), 0.0)


class QuoteScoreTests(unittest.TestCase):
    def test_a_two_sided_quote_scores(self):
        self.assertGreater(lr.quote_score(1.0, 1.0, 100.0, 0.5), 0.0)

    def test_a_missing_side_in_the_middle_still_scores(self):
        self.assertGreater(lr.quote_score(1.0, None, 100.0, 0.5), 0.0)

    def test_a_missing_side_at_the_wing_scores_nothing(self):
        self.assertEqual(lr.quote_score(1.0, None, 100.0, 0.95), 0.0)

    def test_quoting_nothing_scores_nothing(self):
        self.assertEqual(lr.quote_score(None, None, 100.0, 0.5), 0.0)

    def test_a_quote_outside_the_cap_scores_nothing(self):
        self.assertEqual(lr.quote_score(9.0, 9.0, 100.0, 0.5,
                                        max_spread_cents=4.5), 0.0)


class ShareTests(unittest.TestCase):
    def test_no_competition_takes_the_whole_pool(self):
        self.assertEqual(lr.reward_share(10.0, 0.0), 1.0)

    def test_equal_competition_halves_the_pool(self):
        self.assertAlmostEqual(lr.reward_share(10.0, 1.0), 0.5, places=9)

    def test_heavy_competition_shrinks_the_share(self):
        self.assertAlmostEqual(lr.reward_share(10.0, 19.0), 0.05, places=9)

    def test_scoring_nothing_earns_nothing(self):
        self.assertEqual(lr.reward_share(0.0, 1.0), 0.0)
        self.assertEqual(lr.daily_reward_usd(0.0, 1.0, 100.0), 0.0)

    def test_the_payout_scales_with_the_pool(self):
        self.assertAlmostEqual(lr.daily_reward_usd(10.0, 1.0, 100.0), 50.0, places=9)


class EstimateTests(unittest.TestCase):
    def _samples(self, n=10, duration=60.0, mid=0.5, half_spread=0.01):
        return [(duration, mid, mid - half_spread, mid + half_spread, mid)
                for _ in range(n)]

    def test_an_empty_run_earns_nothing(self):
        estimate = lr.estimate_from_quotes([], quote_usd=50.0)
        self.assertEqual(estimate.usd(1.0), 0.0)
        self.assertEqual(estimate.mean_score, 0.0)

    def test_zero_duration_samples_are_ignored(self):
        estimate = lr.estimate_from_quotes(
            [(0.0, 0.5, 0.49, 0.51, 0.5)], quote_usd=50.0)
        self.assertEqual(estimate.hours_quoted, 0.0)

    def test_hours_are_summed_from_the_sample_durations(self):
        estimate = lr.estimate_from_quotes(self._samples(n=60, duration=60.0),
                                           quote_usd=50.0)
        self.assertAlmostEqual(estimate.hours_quoted, 1.0, places=6)

    def test_a_tighter_quote_scores_higher(self):
        tight = lr.estimate_from_quotes(self._samples(half_spread=0.005),
                                        quote_usd=50.0)
        wide = lr.estimate_from_quotes(self._samples(half_spread=0.03),
                                       quote_usd=50.0)
        self.assertGreater(tight.mean_score, wide.mean_score)

    def test_a_quote_outside_the_cap_never_qualifies(self):
        estimate = lr.estimate_from_quotes(self._samples(half_spread=0.06),
                                           quote_usd=50.0)
        self.assertEqual(estimate.qualifying_share, 0.0)
        self.assertEqual(estimate.usd(1.0), 0.0)

    def test_reward_scales_with_the_window_length(self):
        short = lr.estimate_from_quotes(self._samples(n=60, duration=60.0),
                                        quote_usd=50.0, pool_usd=100.0)
        long = lr.estimate_from_quotes(self._samples(n=120, duration=60.0),
                                       quote_usd=50.0, pool_usd=100.0)
        self.assertAlmostEqual(long.usd(1.0), 2 * short.usd(1.0), places=6)

    def test_reward_scales_with_the_number_of_markets(self):
        one = lr.estimate_from_quotes(self._samples(), quote_usd=50.0, markets=1)
        many = lr.estimate_from_quotes(self._samples(), quote_usd=50.0, markets=10)
        self.assertAlmostEqual(many.usd(1.0), 10 * one.usd(1.0), places=6)

    def test_sensitivity_covers_every_competition_scenario(self):
        estimate = lr.estimate_from_quotes(self._samples(), quote_usd=50.0)
        rows = estimate.sensitivity()
        self.assertEqual([r["competition_multiple"] for r in rows],
                         list(lr.COMPETITION_SCENARIOS))
        # Mehr Konkurrenz muss immer weniger auszahlen.
        payouts = [r["reward_usd"] for r in rows]
        self.assertEqual(payouts, sorted(payouts, reverse=True))

    def test_the_estimate_carries_its_snapshot_date(self):
        estimate = lr.estimate_from_quotes(self._samples(), quote_usd=50.0)
        self.assertEqual(estimate.as_dict()["snapshot_date"],
                         lr.REWARD_SNAPSHOT_DATE)

    def test_a_one_sided_quote_at_the_wing_earns_nothing(self):
        samples = [(60.0, 0.95, 0.94, None, 0.95) for _ in range(10)]
        estimate = lr.estimate_from_quotes(samples, quote_usd=50.0)
        self.assertEqual(estimate.usd(1.0), 0.0)


class MeasuredConstantsTests(unittest.TestCase):
    def test_the_measured_snapshot_is_internally_consistent(self):
        # Summe / Anzahl muss dem gemessenen Mittelwert entsprechen.
        implied_mean = lr.TOTAL_DAILY_POOL_USD / lr.MARKETS_WITH_POOL
        self.assertAlmostEqual(implied_mean, lr.POOL_MEAN_USD, places=1)

    def test_the_median_pool_is_far_below_the_mean(self):
        # Die Verteilung ist stark rechtsschief; das darf nicht verloren gehen.
        self.assertLess(lr.POOL_MEDIAN_USD, lr.POOL_MEAN_USD / 3)


if __name__ == "__main__":
    unittest.main()
