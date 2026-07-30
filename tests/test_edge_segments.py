import json
import tempfile
import unittest
from pathlib import Path

from src import edge_segments as es
from src import orderflow_study as ofs


def observation(day="2026-07-01", spread_cents=1.0, entry_mid=0.5,
                strength=0.9, gross_cents=0.5, fee_cents=2.5, ts=0.0):
    return ofs.Observation(
        token_id="t", day=day, ts=ts, signal="imbalance", direction=1,
        strength=strength, delay_s=0.0, horizon_s=300.0, entry_mid=entry_mid,
        exit_mid=entry_mid + gross_cents / 100.0, spread_cents=spread_cents,
        gross_cents=gross_cents, spread_cost_cents=spread_cents,
        fee_cost_cents=fee_cents,
        net_cents=round(gross_cents - spread_cents - fee_cents, 4))


class SegmenterTests(unittest.TestCase):
    def test_spread_buckets_split_at_the_documented_edges(self):
        self.assertEqual(es.spread_segment(observation(spread_cents=0.2)), "0-0.5c")
        self.assertEqual(es.spread_segment(observation(spread_cents=0.5)), "0.5-1c")
        self.assertEqual(es.spread_segment(observation(spread_cents=7.0)), "5-10.1c")

    def test_a_spread_outside_every_bucket_is_dropped(self):
        self.assertIsNone(es.spread_segment(observation(spread_cents=50.0)))

    def test_price_buckets_cover_the_traded_range(self):
        self.assertEqual(es.price_segment(observation(entry_mid=0.10)), "0.05-0.15")
        self.assertEqual(es.price_segment(observation(entry_mid=0.50)), "0.35-0.65")

    def test_price_outside_the_filtered_range_is_dropped(self):
        self.assertIsNone(es.price_segment(observation(entry_mid=0.99)))

    def test_strength_is_mirrored_so_both_directions_share_bins(self):
        long_side = es.strength_segment(observation(strength=0.90))
        short_side = es.strength_segment(observation(strength=0.10))
        self.assertEqual(long_side, short_side)

    def test_a_neutral_strength_falls_outside_every_bucket(self):
        self.assertIsNone(es.strength_segment(observation(strength=0.50)))


class RescoreTests(unittest.TestCase):
    def test_a_fee_free_category_only_leaves_the_spread(self):
        obs = observation(gross_cents=1.0, spread_cents=0.5, fee_cents=2.5)
        self.assertAlmostEqual(es.rescore(obs, "geopolitics"), 0.5, places=4)

    def test_a_dearer_category_lowers_the_net_edge(self):
        obs = observation()
        self.assertLess(es.rescore(obs, "crypto"), es.rescore(obs, "politics"))

    def test_rescoring_leaves_the_gross_move_untouched(self):
        obs = observation(gross_cents=1.0, spread_cents=0.5)
        cheap = es.rescore(obs, "geopolitics")
        dear = es.rescore(obs, "crypto")
        self.assertAlmostEqual(cheap - dear,
                               2 * ofs.vf.fee_cents_per_share(
                                   "polymarket", obs.entry_mid, "crypto", 100.0),
                               places=4)

    def test_the_fee_is_symmetric_around_fifty_cents(self):
        low = es.rescore(observation(entry_mid=0.25), "sports")
        high = es.rescore(observation(entry_mid=0.75), "sports")
        self.assertAlmostEqual(low, high, places=4)


class ScoreSegmentTests(unittest.TestCase):
    def test_empty_segment_is_reported_not_crashed(self):
        self.assertEqual(es.score_segment([], "sports")["n"], 0)

    def test_walk_forward_columns_appear_with_several_days(self):
        observations = [observation(day=f"2026-07-0{i}") for i in range(1, 6)] * 4
        stats = es.score_segment(observations, "sports")
        self.assertIsNotNone(stats["train_net_cents"])
        self.assertIsNotNone(stats["test_net_cents"])

    def test_a_single_day_yields_no_out_of_sample_number(self):
        stats = es.score_segment([observation()] * 5, "sports")
        self.assertIsNone(stats["test_net_cents"])

    def test_a_fee_free_category_scores_better_than_a_dear_one(self):
        observations = [observation(day=f"2026-07-0{i}") for i in range(1, 6)]
        cheap = es.score_segment(observations, "geopolitics")
        dear = es.score_segment(observations, "crypto")
        self.assertGreater(cheap["mean_net_cents"], dear["mean_net_cents"])

    def test_hit_rate_ignores_observations_that_did_not_move(self):
        observations = [observation(gross_cents=0.0)] * 4 + [observation(gross_cents=1.0)]
        self.assertEqual(es.score_segment(observations, "sports")["hit_rate"], 1.0)


class SegmentTableTests(unittest.TestCase):
    def test_one_row_per_populated_bucket(self):
        observations = ([observation(spread_cents=0.2)] * 5
                        + [observation(spread_cents=3.0)] * 5)
        rows = es.segment_table(observations, "spread", "sports")
        self.assertEqual(sorted(r["bucket"] for r in rows), ["0-0.5c", "2-5c"])

    def test_thin_buckets_are_flagged_rather_than_hidden(self):
        rows = es.segment_table([observation()] * 5, "spread", "sports",
                                min_observations=100)
        self.assertTrue(rows[0]["thin"])
        self.assertEqual(rows[0]["n"], 5)

    def test_cross_table_pairs_spread_with_strength(self):
        observations = [observation(spread_cents=0.2, strength=0.9)] * 4
        rows = es.cross_segment_table(observations, "sports")
        self.assertEqual(rows[0]["spread_bucket"], "0-0.5c")
        self.assertEqual(rows[0]["strength_bucket"], "0.85-0.95")

    def test_observations_outside_any_bucket_are_skipped_by_the_cross(self):
        self.assertEqual(
            es.cross_segment_table([observation(strength=0.5)], "sports"), [])


class SurvivorTests(unittest.TestCase):
    def test_a_segment_positive_only_in_sample_does_not_survive(self):
        rows = [{"n": 1000, "mean_net_cents": 0.5, "test_net_cents": -0.2}]
        self.assertEqual(es.survivors(rows), [])

    def test_a_segment_positive_in_both_windows_survives(self):
        rows = [{"n": 1000, "mean_net_cents": 0.5, "test_net_cents": 0.3}]
        self.assertEqual(len(es.survivors(rows)), 1)

    def test_a_thin_segment_cannot_survive_however_good_it_looks(self):
        rows = [{"n": 10, "mean_net_cents": 5.0, "test_net_cents": 5.0}]
        self.assertEqual(es.survivors(rows), [])

    def test_survivors_are_ranked_by_the_out_of_sample_number(self):
        rows = [
            {"n": 1000, "mean_net_cents": 9.0, "test_net_cents": 0.1},
            {"n": 1000, "mean_net_cents": 0.2, "test_net_cents": 0.9},
        ]
        self.assertEqual(es.survivors(rows)[0]["test_net_cents"], 0.9)

    def test_missing_scores_cannot_survive(self):
        rows = [{"n": 1000, "mean_net_cents": 0.5, "test_net_cents": None}]
        self.assertEqual(es.survivors(rows), [])


class EndToEndTests(unittest.TestCase):
    def _write_days(self, directory: Path, days: int, rows_per_day: int) -> None:
        import csv as _csv
        for day_index in range(1, days + 1):
            day = f"2026-07-{day_index:02d}"
            with open(directory / f"books_{day}.csv", "w", newline="",
                      encoding="utf-8") as handle:
                writer = _csv.DictWriter(handle, fieldnames=[
                    "ts_utc", "token_id", "best_bid", "best_ask", "spread",
                    "mid", "imbalance_top"])
                writer.writeheader()
                for i in range(rows_per_day):
                    mid = 0.50 + i * 0.001
                    writer.writerow({
                        "ts_utc": f"{day}T{i // 30:02d}:{(i * 2) % 60:02d}:00Z",
                        "token_id": "t1", "best_bid": round(mid - 0.005, 4),
                        "best_ask": round(mid + 0.005, 4), "spread": 0.01,
                        "mid": round(mid, 4), "imbalance_top": 0.9,
                    })

    def test_study_runs_across_fee_scenarios_and_writes_reports(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "data"
            data.mkdir()
            self._write_days(data, days=4, rows_per_day=30)

            results = es.run_study(data, categories=("sports", "geopolitics"))
            self.assertGreater(results["observations"], 0)
            self.assertEqual(sorted(results["by_category"]),
                             ["geopolitics", "sports"])
            cheap = results["by_category"]["geopolitics"]["overall"]["mean_net_cents"]
            dear = results["by_category"]["sports"]["overall"]["mean_net_cents"]
            self.assertGreater(cheap, dear)

            out = Path(tmp) / "research"
            paths = es.write_outputs(results, "test", research_dir=out)
            body = paths["md"].read_text(encoding="utf-8")
            self.assertIn("Wo sitzt die Kante", body)
            self.assertNotIn("ß", body)
            payload = json.loads(paths["json"].read_text(encoding="utf-8"))
            self.assertIn("by_category", payload)
            self.assertTrue(paths["csv"].exists())

    def test_no_candidates_is_stated_explicitly_in_the_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "data"
            data.mkdir()
            self._write_days(data, days=3, rows_per_day=20)
            results = es.run_study(data, categories=("sports",))
            # Bei diesen Kosten kann nichts ueberleben, das muss dastehen.
            results["by_category"]["sports"]["survivors"] = []
            out = Path(tmp) / "research"
            body = es.write_outputs(results, "leer",
                                    research_dir=out)["md"].read_text(encoding="utf-8")
            self.assertIn("Keine.", body)

    def test_study_on_an_empty_directory_does_not_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            results = es.run_study(Path(tmp), categories=("sports",))
            self.assertEqual(results["observations"], 0)
            self.assertEqual(results["by_category"]["sports"]["overall"]["n"], 0)


if __name__ == "__main__":
    unittest.main()
