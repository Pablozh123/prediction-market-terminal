import math
import unittest

from app import quant as qm


class KellyTests(unittest.TestCase):
    def test_kelly_known_value(self):
        # f* = (0.45 - 0.30) / (1 - 0.30) = 0.2142857...
        self.assertAlmostEqual(qm.kelly_binary(0.30, 0.45), 0.15 / 0.70, places=9)

    def test_kelly_no_edge_is_zero(self):
        self.assertEqual(qm.kelly_binary(0.50, 0.50), 0.0)
        self.assertEqual(qm.kelly_binary(0.50, 0.40), 0.0)

    def test_kelly_invalid_inputs_are_zero(self):
        self.assertEqual(qm.kelly_binary(0.0, 0.5), 0.0)
        self.assertEqual(qm.kelly_binary(1.0, 0.5), 0.0)
        self.assertEqual(qm.kelly_binary(None, 0.5), 0.0)
        self.assertEqual(qm.kelly_binary(0.3, float("nan")), 0.0)


class BayesTests(unittest.TestCase):
    def test_posterior_known_value(self):
        # odds 0.3/0.7 * 3 = 1.2857... -> p = 0.5625
        self.assertAlmostEqual(qm.bayes_posterior(0.30, 3.0), 0.5625, places=9)

    def test_lr_one_keeps_prior(self):
        self.assertAlmostEqual(qm.bayes_posterior(0.42, 1.0), 0.42, places=9)

    def test_invalid_inputs_are_nan(self):
        self.assertTrue(math.isnan(qm.bayes_posterior(0.0, 2.0)))
        self.assertTrue(math.isnan(qm.bayes_posterior(0.5, 0.0)))
        self.assertTrue(math.isnan(qm.bayes_posterior(0.5, -1.0)))

    def test_implied_lr_known_value(self):
        self.assertAlmostEqual(qm.implied_likelihood_ratio(0.30, 0.55), 2.851852, places=5)

    def test_posterior_roundtrips_implied_lr(self):
        p0, p1 = 0.22, 0.61
        lr = qm.implied_likelihood_ratio(p0, p1)
        self.assertAlmostEqual(qm.bayes_posterior(p0, lr), p1, places=9)


class ScoreTests(unittest.TestCase):
    def test_brier_perfect_and_coinflip(self):
        self.assertAlmostEqual(qm.brier_score([1.0, 0.0], [1, 0]), 0.0, places=9)
        self.assertAlmostEqual(qm.brier_score([0.5, 0.5, 0.5, 0.5], [1, 0, 1, 0]), 0.25, places=9)

    def test_brier_empty_is_none(self):
        self.assertIsNone(qm.brier_score([], []))

    def test_log_loss_known_value(self):
        self.assertAlmostEqual(qm.log_loss([0.8], [1]), -math.log(0.8), places=9)

    def test_log_loss_confident_miss_is_finite(self):
        value = qm.log_loss([1.0], [0])
        self.assertTrue(math.isfinite(value))
        self.assertGreater(value, 10.0)

    def test_wilson_interval_known_value(self):
        lo, hi = qm.wilson_interval(18, 30)
        self.assertAlmostEqual(lo, 0.4232, delta=0.001)
        self.assertAlmostEqual(hi, 0.7541, delta=0.001)
        # 60% on 30 trades does not exclude the coin flip.
        self.assertLess(lo, 0.5)
        self.assertGreater(hi, 0.5)

    def test_wilson_interval_empty(self):
        self.assertEqual(qm.wilson_interval(0, 0), (0.0, 1.0))


class CalibrationTableTests(unittest.TestCase):
    def test_buckets_and_edge(self):
        table = qm.calibration_table([0.10, 0.15, 0.70, 0.75], [0, 1, 1, 1], bins=5)
        self.assertEqual(list(table.columns), ["bucket", "n", "avg_forecast", "hit_rate", "edge", "hit_low", "hit_high"])
        self.assertEqual(len(table), 2)
        low = table.iloc[0]
        self.assertEqual(low["n"], 2)
        self.assertAlmostEqual(low["avg_forecast"], 0.125, places=9)
        self.assertAlmostEqual(low["hit_rate"], 0.5, places=9)
        self.assertAlmostEqual(low["edge"], 0.375, places=9)
        high = table.iloc[1]
        self.assertEqual(high["n"], 2)
        self.assertAlmostEqual(high["hit_rate"], 1.0, places=9)
        self.assertAlmostEqual(high["edge"], 1.0 - 0.725, places=9)
        self.assertTrue((table["hit_low"] <= table["hit_rate"]).all())
        self.assertTrue((table["hit_high"] >= table["hit_rate"]).all())

    def test_empty_input_keeps_columns(self):
        table = qm.calibration_table([], [])
        self.assertTrue(table.empty)
        self.assertIn("edge", table.columns)


if __name__ == "__main__":
    unittest.main()
