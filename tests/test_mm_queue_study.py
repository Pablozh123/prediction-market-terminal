import csv
import json
import tempfile
import unittest
from pathlib import Path

from src import mm_queue_study as mqs
from src.book_stream import STREAM_BOOK_FIELDS, STREAM_TRADE_FIELDS


def write_stream_day(directory: Path, day: str, rows: int = 60,
                     token: str = "t1") -> None:
    """A stream day with a mid that swings every second and a print each second."""
    with open(directory / f"stream_books_{day}.csv", "w", newline="",
              encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=STREAM_BOOK_FIELDS)
        writer.writeheader()
        for i in range(rows):
            mid = 0.50 + (0.03 if i % 2 else -0.03)
            writer.writerow({
                "recv_ts": f"{day}T00:00:{i % 60:02d}.000Z" if i < 60
                else f"{day}T00:01:{i % 60:02d}.000Z",
                "token_id": token, "event_type": "price_change",
                "best_bid": round(mid - 0.01, 4), "best_ask": round(mid + 0.01, 4),
                "spread": 0.02, "mid": round(mid, 4), "imbalance_top": 0.5,
                "bid_size_touch": 10.0, "ask_size_touch": 10.0,
            })
    with open(directory / f"stream_trades_{day}.csv", "w", newline="",
              encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=STREAM_TRADE_FIELDS)
        writer.writeheader()
        for i in range(rows):
            writer.writerow({
                "recv_ts": f"{day}T00:00:{i % 60:02d}.500Z",
                "exchange_ts": "", "token_id": token,
                "side": "SELL" if i % 2 else "BUY",
                "price": 0.40 if i % 2 else 0.60, "size": 200, "tx_hash": "x",
            })


def agg(model, candidate, total, fills=5000, days=3):
    return {"model": model, "candidate": candidate, "total_usd": total,
            "fills": fills, "days": days}


class CandidateTests(unittest.TestCase):
    def test_key_is_stable_and_distinct(self):
        keys = {mqs.candidate_key(c) for c in mqs.CANDIDATES}
        self.assertEqual(len(keys), len(mqs.CANDIDATES))
        self.assertEqual(mqs.candidate_key({"half_spread": 0.01, "gamma": 0.0,
                                            "latency_s": 0.0}), "hs0.01_g0.0_lat0.0")

    def test_the_grid_is_the_pre_registered_one(self):
        self.assertEqual(len(mqs.CANDIDATES), 6)
        self.assertTrue(all(c["latency_s"] == 0.0 for c in mqs.CANDIDATES))


class ChoiceTests(unittest.TestCase):
    def test_the_highest_back_total_wins(self):
        aggregates = [agg("queue_back", "a", 10.0), agg("queue_back", "b", 30.0),
                      agg("queue_front", "c", 99.0)]
        self.assertEqual(mqs.choose(aggregates)["candidate"], "b")

    def test_thin_candidates_are_not_candidates(self):
        aggregates = [agg("queue_back", "a", 10.0, fills=5000),
                      agg("queue_back", "b", 30.0, fills=10)]
        self.assertEqual(mqs.choose(aggregates)["candidate"], "a")

    def test_nothing_eligible_means_nothing_chosen(self):
        self.assertIsNone(mqs.choose([agg("queue_back", "a", 10.0, fills=10)]))
        self.assertIsNone(mqs.choose([]))


class AggregateTests(unittest.TestCase):
    def _row(self, day, model="queue_back", candidate="a", total=1.0, fills=10):
        return {"day": day, "model": model, "candidate": candidate,
                "half_spread": 0.01, "gamma": 0.0, "latency_s": 0.0,
                "total_usd": total, "fills": fills,
                "spread_capture_usd": 2.0 * fills / 100, "markout_usd": -1.0 * fills / 100}

    def test_days_are_summed_per_model_and_candidate(self):
        rows = [self._row("2026-07-01", total=1.0), self._row("2026-07-02", total=2.0),
                self._row("2026-07-01", model="queue_front", total=5.0)]
        out = {(a["model"], a["candidate"]): a for a in mqs.aggregate(rows)}
        back = out[("queue_back", "a")]
        self.assertEqual(back["days"], 2)
        self.assertAlmostEqual(back["total_usd"], 3.0)
        self.assertAlmostEqual(back["mean_daily_usd"], 1.5)
        self.assertEqual(back["daily_totals"], {"2026-07-01": 1.0, "2026-07-02": 2.0})
        self.assertEqual(out[("queue_front", "a")]["days"], 1)

    def test_per_fill_figures_are_weighted_by_fills(self):
        rows = [self._row("2026-07-01", fills=100), self._row("2026-07-02", fills=300)]
        back = mqs.aggregate(rows)[0]
        self.assertAlmostEqual(back["spread_capture_cents_per_fill"], 2.0)
        self.assertAlmostEqual(back["markout_cents_per_fill"], -1.0)

    def test_the_bootstrap_needs_three_days(self):
        two = [self._row("2026-07-01"), self._row("2026-07-02")]
        three = two + [self._row("2026-07-03")]
        self.assertIsNone(mqs.aggregate(two)[0]["daily_ci95_usd"])
        self.assertIsNotNone(mqs.aggregate(three)[0]["daily_ci95_usd"])


class RunDayTests(unittest.TestCase):
    def test_one_day_scores_every_candidate_on_every_model_plus_reference(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            write_stream_day(data, "2026-07-01")
            rows = mqs.run_day(data, "2026-07-01")
            self.assertEqual(len(rows), len(mqs.CANDIDATES) * len(mqs.MODELS) + 1)
            self.assertEqual(rows[-1]["model"], "tape")
            self.assertTrue(all(r["day"] == "2026-07-01" for r in rows))
            self.assertIn("queue_resets", rows[0])
            self.assertTrue(any(r["fills"] > 0 for r in rows))


class ResumeTests(unittest.TestCase):
    def test_a_rerun_skips_days_already_scored(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "data"
            data.mkdir()
            out = Path(tmp) / "research"
            for day in ("2026-07-01", "2026-07-02"):
                write_stream_day(data, day)
            log: list[str] = []
            mqs.run_study(data, "t", research_dir=out, log=log.append)
            self.assertEqual(sum("done" in line for line in log), 2)
            write_stream_day(data, "2026-07-03")
            log.clear()
            paths = mqs.run_study(data, "t", research_dir=out, log=log.append)
            self.assertEqual(sum("skipping" in line for line in log), 2)
            self.assertEqual(sum("done" in line for line in log), 1)
            payload = json.loads(paths["json"].read_text(encoding="utf-8"))
            self.assertEqual(payload["days"], ["2026-07-01", "2026-07-02", "2026-07-03"])
            body = paths["md"].read_text(encoding="utf-8")
            self.assertIn("## Choice", body)
            self.assertNotIn("ß", body)

    def test_duplicate_rows_for_a_day_do_not_double_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.rows.jsonl"
            row = {"day": "2026-07-01", "model": "queue_back", "candidate": "a",
                   "total_usd": 1.0}
            mqs.append_rows(path, [row, dict(row, total_usd=2.0)])
            rows = mqs.load_rows(path)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["total_usd"], 2.0)

    def test_the_day_window_is_honoured(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "data"
            data.mkdir()
            for day in ("2026-07-01", "2026-07-02", "2026-07-03"):
                write_stream_day(data, day)
            self.assertEqual(mqs.available_days(data, "2026-07-02", None),
                             ["2026-07-02", "2026-07-03"])
            self.assertEqual(mqs.available_days(data, None, "2026-07-01"),
                             ["2026-07-01"])


if __name__ == "__main__":
    unittest.main()
