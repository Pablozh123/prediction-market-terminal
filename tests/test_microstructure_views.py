"""Tests fuer die read-only Microstructure-Sichten (Recorder + Rolling-Study)."""

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app import microstructure_views as mv

BOOK_HEADER = (
    "ts_utc,market_id,slug,outcome,token_id,best_bid,best_ask,spread,mid,"
    "bid_usd_top,ask_usd_top,imbalance_top,bids_json,asks_json\n"
)


def _book_row(ts: str, token: str, mid: float, imb: float) -> str:
    return (
        f"{ts},1,slug,Yes,{token},{mid - 0.01},{mid + 0.01},0.02,{mid},"
        f"10,10,{imb},[],[]\n"
    )


class RecorderStatusTests(unittest.TestCase):
    def test_status_und_files(self):
        with TemporaryDirectory() as tmp:
            micro = Path(tmp)
            (micro / "recorder_status.json").write_text(
                json.dumps({"ts_utc": "2026-07-18T10:11:59Z",
                            "tracked_markets": 60, "book_rows": 120,
                            "book_errors": 0, "trade_rows": 44}),
                encoding="utf-8",
            )
            (micro / "books_2026-07-18.csv").write_text(
                BOOK_HEADER, encoding="utf-8"
            )
            (micro / "trades_2026-07-18.csv").write_text(
                "ts\n", encoding="utf-8"
            )
            status = mv.recorder_status(micro)
            self.assertEqual(status["tracked_markets"], 60)
            files = mv.recorder_files(micro)
            self.assertEqual(len(files), 2)
            arten = {f["art"] for f in files}
            self.assertEqual(arten, {"books", "trades"})

    def test_fehlende_daten_fail_safe(self):
        with TemporaryDirectory() as tmp:
            fehlt = Path(tmp) / "nope"
            self.assertIsNone(mv.recorder_status(fehlt))
            self.assertEqual(mv.recorder_files(fehlt), [])
            roll = mv.rolling_imbalance(fehlt)
            self.assertEqual(roll["rows"], [])
            self.assertEqual(roll["n_pairs"], 0)

    def test_kaputter_status_gibt_none(self):
        with TemporaryDirectory() as tmp:
            (Path(tmp) / "recorder_status.json").write_text(
                "{broken", encoding="utf-8"
            )
            self.assertIsNone(mv.recorder_status(Path(tmp)))


class RollingImbalanceTests(unittest.TestCase):
    def test_buckets_aus_recorder_csv(self):
        # Ein Token, bid-lastig (imbalance 0.7), mid steigt je 5 Minuten:
        # jedes Paar ist ein Richtungstreffer im 0.6-0.8-Bucket.
        with TemporaryDirectory() as tmp:
            micro = Path(tmp)
            zeilen = [BOOK_HEADER]
            for i, minute in enumerate(range(0, 40, 5)):
                ts = f"2026-07-18T10:{minute:02d}:00Z"
                zeilen.append(_book_row(ts, "tokA", 0.50 + i * 0.01, 0.70))
            (micro / "books_2026-07-18.csv").write_text(
                "".join(zeilen), encoding="utf-8"
            )
            roll = mv.rolling_imbalance(micro, horizon_s=300)
            self.assertEqual(roll["n_tokens"], 1)
            self.assertGreater(roll["n_pairs"], 0)
            bucket = next(
                r for r in roll["rows"] if r["bucket"] == "0.6-0.8"
            )
            self.assertGreater(bucket["n"], 0)
            self.assertEqual(bucket["hit_rate"], 1.0)


class StudyReportTests(unittest.TestCase):
    def test_reports_gruppieren_md_und_png(self):
        with TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "imbalance_study_x.md").write_text("# r", encoding="utf-8")
            (d / "imbalance_study_x.png").write_bytes(b"png")
            (d / "notes_only.md").write_text("# n", encoding="utf-8")
            reports = mv.study_reports(d)
            self.assertEqual(len(reports), 2)
            mit_png = next(r for r in reports if r["stem"] == "imbalance_study_x")
            self.assertIsNotNone(mit_png["png_path"])
            ohne_png = next(r for r in reports if r["stem"] == "notes_only")
            self.assertIsNone(ohne_png["png_path"])

    def test_fehlendes_verzeichnis(self):
        self.assertEqual(mv.study_reports(Path("nope-dir-xyz")), [])


if __name__ == "__main__":
    unittest.main()
