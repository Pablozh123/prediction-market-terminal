import json
import tempfile
import unittest
from pathlib import Path

from src import orderflow_study as ofs


def book_series(n=20, step=120.0, mid=0.50, drift=0.0, imbalance=0.9,
                spread=0.01, day="2026-07-01", start=1_000_000.0):
    return [
        ofs.BookPoint(ts=start + i * step, mid=round(mid + i * drift, 6),
                      spread=spread, imbalance=imbalance, day=day)
        for i in range(n)
    ]


def write_books(directory: Path, day: str, rows: list[dict],
                stream: bool = False) -> None:
    import csv as _csv
    name = f"{'stream_books' if stream else 'books'}_{day}.csv"
    fields = ["ts_utc", "recv_ts", "token_id", "best_bid", "best_ask",
              "spread", "mid", "imbalance_top"]
    with open(directory / name, "w", newline="", encoding="utf-8") as handle:
        writer = _csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


class ParseTsTests(unittest.TestCase):
    def test_reads_the_recorder_format(self):
        self.assertIsNotNone(ofs.parse_ts("2026-07-27T00:01:10Z"))

    def test_reads_the_stream_format_with_milliseconds(self):
        coarse = ofs.parse_ts("2026-07-27T00:01:10Z")
        fine = ofs.parse_ts("2026-07-27T00:01:10.500Z")
        self.assertAlmostEqual(fine - coarse, 0.5, places=3)

    def test_rejects_nonsense(self):
        self.assertIsNone(ofs.parse_ts("gestern"))
        self.assertIsNone(ofs.parse_ts(""))
        self.assertIsNone(ofs.parse_ts(None))


class DirectionTests(unittest.TestCase):
    def test_above_threshold_is_long(self):
        self.assertEqual(ofs.direction_from(0.80, 0.65), 1)

    def test_below_the_mirror_is_short(self):
        self.assertEqual(ofs.direction_from(0.20, 0.65), -1)

    def test_dead_zone_is_flat(self):
        self.assertEqual(ofs.direction_from(0.50, 0.65), 0)

    def test_the_thresholds_are_inclusive(self):
        self.assertEqual(ofs.direction_from(0.65, 0.65), 1)
        self.assertEqual(ofs.direction_from(0.35, 0.65), -1)

    def test_imbalance_signal_uses_the_raw_value(self):
        direction, strength = ofs.signal_direction("imbalance", 0.9, None, 0.65)
        self.assertEqual(direction, 1)
        self.assertEqual(strength, 0.9)

    def test_flow_is_rescaled_from_minus_one_to_one(self):
        direction, strength = ofs.signal_direction("flow", 0.5, 1.0, 0.65)
        self.assertEqual(direction, 1)
        self.assertEqual(strength, 1.0)
        direction, _ = ofs.signal_direction("flow", 0.5, -1.0, 0.65)
        self.assertEqual(direction, -1)

    def test_flow_without_prints_gives_no_signal(self):
        self.assertEqual(ofs.signal_direction("flow", 0.9, None, 0.65)[0], 0)

    def test_combo_needs_both_sides_to_agree(self):
        agree, _ = ofs.signal_direction("combo", 0.9, 0.8, 0.65)
        self.assertEqual(agree, 1)
        disagree, _ = ofs.signal_direction("combo", 0.9, -0.8, 0.65)
        self.assertEqual(disagree, 0)

    def test_unknown_signal_is_a_programming_error(self):
        with self.assertRaises(ValueError):
            ofs.signal_direction("astrologie", 0.9, 0.5, 0.65)


class FlowImbalanceTests(unittest.TestCase):
    def test_pure_buying_is_plus_one(self):
        trades = [ofs.TradePoint(ts=10, signed_usd=100, usd=100)]
        self.assertEqual(ofs.flow_imbalance(trades, 0, 20), 1.0)

    def test_pure_selling_is_minus_one(self):
        trades = [ofs.TradePoint(ts=10, signed_usd=-100, usd=100)]
        self.assertEqual(ofs.flow_imbalance(trades, 0, 20), -1.0)

    def test_balanced_flow_is_zero(self):
        trades = [ofs.TradePoint(ts=10, signed_usd=100, usd=100),
                  ofs.TradePoint(ts=11, signed_usd=-100, usd=100)]
        self.assertEqual(ofs.flow_imbalance(trades, 0, 20), 0.0)

    def test_window_bounds_are_respected(self):
        trades = [ofs.TradePoint(ts=1, signed_usd=100, usd=100),
                  ofs.TradePoint(ts=99, signed_usd=-100, usd=100)]
        self.assertEqual(ofs.flow_imbalance(trades, 90, 120), -1.0)

    def test_too_little_volume_yields_no_signal(self):
        trades = [ofs.TradePoint(ts=10, signed_usd=0.1, usd=0.1)]
        self.assertIsNone(ofs.flow_imbalance(trades, 0, 20, min_usd=1.0))

    def test_empty_tape_yields_no_signal(self):
        self.assertIsNone(ofs.flow_imbalance([], 0, 20))


class AsOfTests(unittest.TestCase):
    def test_picks_the_first_point_at_or_after_the_target(self):
        series = book_series(n=5, step=100.0, start=0.0)
        point = ofs.as_of(series, 250.0, staleness=200.0)
        self.assertEqual(point.ts, 300.0)

    def test_rejects_a_match_that_is_too_stale(self):
        series = book_series(n=5, step=100.0, start=0.0)
        self.assertIsNone(ofs.as_of(series, 250.0, staleness=10.0))

    def test_returns_none_past_the_end(self):
        series = book_series(n=3, step=100.0, start=0.0)
        self.assertIsNone(ofs.as_of(series, 10_000.0, staleness=100.0))


class BuildObservationTests(unittest.TestCase):
    def test_a_rising_market_with_a_bullish_book_is_a_hit(self):
        books = {"t": book_series(n=20, drift=0.001, imbalance=0.9)}
        obs = ofs.build_observations(books, {}, signal="imbalance",
                                     delays_s=(0.0,), horizons_s=(300.0,))
        self.assertTrue(obs)
        self.assertTrue(all(o.direction == 1 for o in obs))
        self.assertTrue(all(o.gross_cents > 0 for o in obs))

    def test_direction_flips_the_sign_of_the_drift(self):
        books = {"t": book_series(n=20, drift=0.001, imbalance=0.1)}
        obs = ofs.build_observations(books, {}, signal="imbalance",
                                     delays_s=(0.0,), horizons_s=(300.0,))
        self.assertTrue(all(o.direction == -1 for o in obs))
        self.assertTrue(all(o.gross_cents < 0 for o in obs))

    def test_dead_zone_produces_no_observations(self):
        books = {"t": book_series(n=20, imbalance=0.5)}
        self.assertEqual(ofs.build_observations(books, {}, signal="imbalance"), [])

    def test_costs_are_split_into_spread_and_fee(self):
        books = {"t": book_series(n=20, spread=0.02, mid=0.5, imbalance=0.9)}
        obs = ofs.build_observations(books, {}, delays_s=(0.0,),
                                     horizons_s=(300.0,), category="sports")
        first = obs[0]
        self.assertAlmostEqual(first.spread_cost_cents, 2.0, places=3)
        self.assertGreater(first.fee_cost_cents, 0.0)
        self.assertAlmostEqual(first.cost_cents,
                               first.spread_cost_cents + first.fee_cost_cents,
                               places=3)

    def test_net_is_gross_minus_both_cost_parts(self):
        books = {"t": book_series(n=20, drift=0.001, imbalance=0.9)}
        obs = ofs.build_observations(books, {}, delays_s=(0.0,),
                                     horizons_s=(300.0,))
        for o in obs:
            self.assertAlmostEqual(
                o.net_cents, o.gross_cents - o.spread_cost_cents - o.fee_cost_cents,
                places=3)

    def test_maker_bound_equals_the_gross_move(self):
        books = {"t": book_series(n=20, drift=0.001, imbalance=0.9)}
        obs = ofs.build_observations(books, {}, delays_s=(0.0,), horizons_s=(300.0,))
        self.assertEqual(obs[0].net_maker_cents, obs[0].gross_cents)

    def test_a_fee_free_category_removes_the_fee_leg(self):
        books = {"t": book_series(n=20, imbalance=0.9)}
        obs = ofs.build_observations(books, {}, delays_s=(0.0,),
                                     horizons_s=(300.0,), category="geopolitics")
        self.assertEqual(obs[0].fee_cost_cents, 0.0)

    def test_delay_at_or_beyond_the_horizon_is_skipped(self):
        books = {"t": book_series(n=20, imbalance=0.9)}
        obs = ofs.build_observations(books, {}, delays_s=(300.0, 600.0),
                                     horizons_s=(300.0,))
        self.assertEqual(obs, [])

    def test_a_later_entry_starts_from_a_later_price(self):
        books = {"t": book_series(n=30, step=1.0, drift=0.001, imbalance=0.9)}
        obs = ofs.build_observations(books, {}, delays_s=(0.0, 5.0),
                                     horizons_s=(20.0,))
        zero = [o for o in obs if o.delay_s == 0.0][0]
        late = [o for o in obs if o.delay_s == 5.0 and o.ts == zero.ts][0]
        self.assertGreater(late.entry_mid, zero.entry_mid)
        self.assertLess(late.gross_cents, zero.gross_cents)

    def test_wide_spreads_are_filtered_out_at_load_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            write_books(directory, "2026-07-01", [{
                "ts_utc": "2026-07-01T00:00:00Z", "token_id": "t",
                "best_bid": 0.3, "best_ask": 0.9, "spread": 0.6,
                "mid": 0.6, "imbalance_top": 0.9,
            }])
            self.assertEqual(ofs.load_books(directory), {})

    def test_resolution_zone_snapshots_are_filtered_out(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            write_books(directory, "2026-07-01", [{
                "ts_utc": "2026-07-01T00:00:00Z", "token_id": "t",
                "best_bid": 0.98, "best_ask": 0.99, "spread": 0.01,
                "mid": 0.985, "imbalance_top": 0.9,
            }])
            self.assertEqual(ofs.load_books(directory), {})


class SummariseTests(unittest.TestCase):
    def test_empty_input_is_reported_not_crashed(self):
        stats = ofs.summarise([])
        self.assertEqual(stats["n"], 0)
        self.assertIsNone(stats["hit_rate"])

    def test_hit_rate_is_conditional_on_movement(self):
        books = {"t": book_series(n=20, drift=0.0, imbalance=0.9)}
        obs = ofs.build_observations(books, {}, delays_s=(0.0,), horizons_s=(300.0,))
        stats = ofs.summarise(obs)
        self.assertEqual(stats["moved"], 0)
        self.assertIsNone(stats["hit_rate"])
        self.assertEqual(stats["moved_share"], 0.0)

    def test_a_perfect_signal_scores_one(self):
        books = {"t": book_series(n=20, drift=0.001, imbalance=0.9)}
        obs = ofs.build_observations(books, {}, delays_s=(0.0,), horizons_s=(300.0,))
        stats = ofs.summarise(obs)
        self.assertEqual(stats["hit_rate"], 1.0)
        self.assertGreater(stats["wilson_lb95"], 0.5)

    def test_day_count_is_reported(self):
        books = {
            "a": book_series(n=10, imbalance=0.9, day="2026-07-01"),
            "b": book_series(n=10, imbalance=0.9, day="2026-07-02"),
        }
        obs = ofs.build_observations(books, {}, delays_s=(0.0,), horizons_s=(300.0,))
        self.assertEqual(ofs.summarise(obs)["days"], 2)


class LatencyCurveTests(unittest.TestCase):
    def test_one_row_per_delay(self):
        books = {"t": book_series(n=40, step=1.0, drift=0.001, imbalance=0.9)}
        obs = ofs.build_observations(books, {}, delays_s=(0.0, 5.0, 10.0),
                                     horizons_s=(20.0,))
        rows = ofs.latency_curve(obs, 20.0)
        self.assertEqual([r["delay_s"] for r in rows], [0.0, 5.0, 10.0])

    def test_edge_retention_is_relative_to_the_zero_delay_row(self):
        books = {"t": book_series(n=40, step=1.0, drift=0.001, imbalance=0.9)}
        obs = ofs.build_observations(books, {}, delays_s=(0.0, 5.0),
                                     horizons_s=(20.0,))
        rows = ofs.edge_retention(ofs.latency_curve(obs, 20.0))
        self.assertEqual(rows[0]["edge_retained"], 1.0)
        self.assertLess(rows[1]["edge_retained"], 1.0)

    def test_retention_is_undefined_without_a_zero_delay_row(self):
        rows = ofs.edge_retention([{"delay_s": 5.0, "mean_gross_cents": 1.0}])
        self.assertIsNone(rows[0]["edge_retained"])

    def test_retention_is_undefined_when_there_was_no_edge_to_lose(self):
        # Ohne Schutz meldet ein Signal ohne Kante Quoten wie "200 Prozent
        # erhalten", was sich wie ein Ergebnis liest und keines ist.
        rows = ofs.edge_retention([
            {"delay_s": 0.0, "mean_gross_cents": -0.002},
            {"delay_s": 120.0, "mean_gross_cents": -0.004},
        ])
        self.assertTrue(all(r["edge_retained"] is None for r in rows))

    def test_retention_is_reported_when_the_base_edge_is_real(self):
        rows = ofs.edge_retention([
            {"delay_s": 0.0, "mean_gross_cents": 0.20},
            {"delay_s": 120.0, "mean_gross_cents": 0.02},
        ])
        self.assertEqual(rows[0]["edge_retained"], 1.0)
        self.assertAlmostEqual(rows[1]["edge_retained"], 0.1, places=4)

    def test_empty_curve_stays_empty(self):
        self.assertEqual(ofs.edge_retention([]), [])


class BootstrapTests(unittest.TestCase):
    def test_interval_brackets_the_mean(self):
        values = [1.0, 1.1, 0.9, 1.05] * 5
        groups = ["d1", "d2", "d3", "d4"] * 5
        lo, hi = ofs.block_bootstrap_ci(values, groups, iterations=200)
        self.assertLessEqual(lo, 1.0125)
        self.assertGreaterEqual(hi, 1.0125)

    def test_a_single_day_gives_no_interval(self):
        self.assertIsNone(ofs.block_bootstrap_ci([1.0, 2.0], ["d1", "d1"]))

    def test_mismatched_inputs_are_rejected(self):
        self.assertIsNone(ofs.block_bootstrap_ci([1.0], ["d1", "d2"]))

    def test_result_is_deterministic_for_a_fixed_seed(self):
        values = [1.0, 2.0, 3.0, 4.0]
        groups = ["a", "b", "c", "d"]
        first = ofs.block_bootstrap_ci(values, groups, iterations=100)
        second = ofs.block_bootstrap_ci(values, groups, iterations=100)
        self.assertEqual(first, second)


class WalkForwardTests(unittest.TestCase):
    def test_split_is_by_day_and_later_days_are_the_test_set(self):
        books = {f"t{i}": book_series(n=10, imbalance=0.9, day=f"2026-07-0{i}")
                 for i in range(1, 6)}
        obs = ofs.build_observations(books, {}, delays_s=(0.0,), horizons_s=(300.0,))
        train, test = ofs.walk_forward_split(obs, train_share=0.6)
        self.assertTrue(max(o.day for o in train) < min(o.day for o in test))

    def test_a_single_day_cannot_be_split(self):
        books = {"t": book_series(n=10, imbalance=0.9, day="2026-07-01")}
        obs = ofs.build_observations(books, {}, delays_s=(0.0,), horizons_s=(300.0,))
        train, test = ofs.walk_forward_split(obs)
        self.assertEqual(test, [])
        self.assertEqual(len(train), len(obs))


class ThresholdTests(unittest.TestCase):
    def test_every_candidate_is_scored_not_just_the_winner(self):
        books = {"t": book_series(n=20, drift=0.001, imbalance=0.9)}
        result = ofs.pick_threshold(books, {}, "imbalance", (0.6, 0.7, 0.95),
                                    horizon_s=300.0)
        self.assertEqual(len(result["candidates"]), 3)
        self.assertIsNotNone(result["best"])

    def test_no_firing_signal_yields_no_winner(self):
        books = {"t": book_series(n=20, imbalance=0.5)}
        result = ofs.pick_threshold(books, {}, "imbalance", (0.9,), horizon_s=300.0)
        self.assertIsNone(result["best"])


class EndToEndTests(unittest.TestCase):
    def test_study_runs_and_writes_all_report_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "data"
            data.mkdir()
            for day_index in (1, 2, 3):
                rows = []
                for i in range(12):
                    mid = 0.50 + i * 0.002
                    rows.append({
                        "ts_utc": f"2026-07-0{day_index}T00:{i * 2:02d}:00Z",
                        "token_id": "t1", "best_bid": round(mid - 0.005, 4),
                        "best_ask": round(mid + 0.005, 4), "spread": 0.01,
                        "mid": round(mid, 4), "imbalance_top": 0.9,
                    })
                write_books(data, f"2026-07-0{day_index}", rows)

            results = ofs.run_study(data, signals=("imbalance",),
                                    horizons_s=(300.0,), delays_s=(0.0, 120.0))
            self.assertEqual(results["tokens"], 1)
            self.assertEqual(len(results["days"]), 3)
            self.assertGreater(results["signals"]["imbalance"]["overall"]["n"], 0)

            out = Path(tmp) / "research"
            paths = ofs.write_outputs(results, "test", research_dir=out)
            self.assertTrue(paths["md"].exists())
            self.assertTrue(paths["csv"].exists())
            payload = json.loads(paths["json"].read_text(encoding="utf-8"))
            self.assertIn("imbalance", payload["signals"])
            body = paths["md"].read_text(encoding="utf-8")
            self.assertIn("Order-Flow-Studie", body)
            self.assertNotIn("ß", body)

    def test_study_on_an_empty_directory_does_not_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            results = ofs.run_study(Path(tmp), signals=("imbalance",))
            self.assertEqual(results["tokens"], 0)
            self.assertEqual(results["signals"]["imbalance"]["overall"]["n"], 0)

    def test_stream_files_are_read_when_requested(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            write_books(data, "2026-07-01", [{
                "recv_ts": "2026-07-01T00:00:00.500Z", "token_id": "t",
                "best_bid": 0.495, "best_ask": 0.505, "spread": 0.01,
                "mid": 0.5, "imbalance_top": 0.9,
            }], stream=True)
            self.assertEqual(len(ofs.load_books(data, stream=True)), 1)
            self.assertEqual(ofs.load_books(data, stream=False), {})


if __name__ == "__main__":
    unittest.main()
