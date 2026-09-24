import unittest
from app.fed_comparison import bucket_for, parse_cme_csv, asof, brier, checkpoint, ts


BUCKETS = [
    {"key": "cut50", "min": None, "max": -50},
    {"key": "cut25", "min": -25, "max": -25},
    {"key": "hold", "min": 0, "max": 0},
    {"key": "hike25", "min": 25, "max": 25},
    {"key": "hike50", "min": 50, "max": None},
]


class FedComparisonTests(unittest.TestCase):
    def test_bucket_tails(self):
        self.assertEqual(bucket_for(100, BUCKETS), "hike50")
        self.assertEqual(bucket_for(-75, BUCKETS), "cut50")
        self.assertEqual(bucket_for(0, BUCKETS), "hold")
        self.assertIsNone(bucket_for(12, BUCKETS))

    def test_cme_maps_levels_and_uses_conservative_close(self):
        rows = parse_cme_csv("Date,(350-375),(375-400),(400-425)\n09/14/2026,0.1,0.8,0.1\n", 375, BUCKETS)
        self.assertEqual(rows[0]["probabilities"], dict(cut50=0, cut25=0, hold=.1, hike25=.8, hike50=.1))
        self.assertEqual(rows[0]["t"], ts("2026-09-15T04:59:59Z"))

    def test_invalid_cme_is_not_silently_zero(self):
        for value in ["NaN", "-0.1", "2", "", "0.2"]:
            with self.assertRaises(ValueError):
                parse_cme_csv(f"Date,(350-375)\n09/14/2026,{value}\n", 375, BUCKETS)

    def test_cme_blank_unreachable_tail_requires_complete_remaining_mass(self):
        rows = parse_cme_csv("Date,(350-375),(375-400),(400-425)\n09/14/2026,0.1,0.9,\n", 375, BUCKETS)
        self.assertEqual(rows[0]["probabilities"]["hike50"], 0)

    def test_asof_never_uses_future_or_stale(self):
        rows = [{"t": 100, "p": .2}, {"t": 200, "p": .9}]
        self.assertEqual(asof(rows, 199, 100)["p"], .2)
        self.assertIsNone(asof(rows, 99, 100))
        self.assertIsNone(asof(rows, 301, 100))

    def test_brier_requires_complete_valid_distribution(self):
        self.assertAlmostEqual(brier({"a": .8, "b": .2}, "a"), .08)
        self.assertEqual(brier({"a": 1, "b": 0}, "a"), 0)
        with self.assertRaises(ValueError):
            brier({"a": .4, "b": .4}, "a")

    def test_checkpoint_pairs_same_time_not_later_pm(self):
        meeting = {"decision_ts": 20*86400, "comparable_after": 0, "actual": "a", "buckets": [{"key": "a"}, {"key": "b"}],
                   "cme": [{"t": 18*86400, "probabilities": {"a": .8, "b": .2}}],
                   "polymarket": {"a": [{"t": 18*86400-1, "p": .6}, {"t": 19*86400, "p": 1}],
                                  "b": [{"t": 18*86400-1, "p": .4}, {"t": 19*86400, "p": 0}]}}
        row = checkpoint(meeting, 1)
        self.assertAlmostEqual(row["pm_brier"], .32)
        self.assertAlmostEqual(row["cme_brier"], .08)
        self.assertEqual(row["asof"], 18*86400)
        meeting["polymarket"]["b"] = []
        self.assertIsNone(checkpoint(meeting, 1)["pm_brier"])

    def test_unknown_previous_rate_prevents_comparison(self):
        self.assertEqual(parse_cme_csv("Date,(350-375)\n09/14/2026,1\n", None, BUCKETS), [])

    def test_checkpoint_finds_latest_complete_pair_within_age_limit(self):
        meeting = {"decision_ts": 20*86400, "comparable_after": 0, "actual": "a",
                   "buckets": [{"key": "a"}, {"key": "b"}],
                   "cme": [{"t": t*86400, "probabilities": {"a": .8, "b": .2}} for t in (17, 18)],
                   "polymarket": {"a": [{"t": 17*86400, "p": .6}], "b": [{"t": 17*86400, "p": .4}]}}
        self.assertEqual(checkpoint(meeting, 1)["asof"], 17*86400)
        meeting["cme"][0]["t"] = 14*86400
        self.assertIsNone(checkpoint(meeting, 1)["asof"])

    def test_meeting_day_close_never_enters_checkpoint(self):
        meeting = {"decision_ts": 20*86400, "comparable_after": 0, "actual": "a", "buckets": [{"key": "a"}],
                   "cme": [{"t": 20*86400+1, "probabilities": {"a": 1}}], "polymarket": {"a": [{"t": 20*86400+1, "p": 1}]}}
        self.assertIsNone(checkpoint(meeting, 1)["asof"])


if __name__ == '__main__':
    unittest.main()
