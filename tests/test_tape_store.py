"""Der persistente Tape-Store: Entdopplung, Fenster, First-Seen, Abdeckung.

Der Store existiert, damit der Co-Trading-Graph ueber Wochen rechnen kann
statt ueber den einen Tag des Live-Feeds. Sein Vertrag ist deshalb vor allem
Idempotenz: der Ingest liest jede Runde dieselben Seiten noch einmal, und
Ueberlappung darf weder Zeilen noch First-Seen-Werte verschieben. Und er muss
sagen koennen, was er enthaelt (coverage) — ein Band ohne Zuschnitts-Vermerk
haette dasselbe Problem, das die Stichproben-Notiz am Live-Band geloest hat.
"""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from app import tape_store as ts

_spec = importlib.util.spec_from_file_location(
    "run_tape_ingest_under_test",
    Path(__file__).resolve().parents[1] / "scripts" / "run_tape_ingest.py",
)
ingest = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ingest)


def _tape(rows: list[dict]) -> pd.DataFrame:
    base = {
        "platform": "Polymarket", "trader": "", "side": "BUY", "outcome": "Yes",
        "title": "Market", "price": 0.5, "size": 2000.0, "notional": 1000.0,
        "market_key": "0xcond", "asset": "a1", "slug": "s", "url": "u",
    }
    return pd.DataFrame([{**base, **row} for row in rows])


class TapeStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "tape.sqlite"
        self.conn = ts.connect(self.path)

    def tearDown(self) -> None:
        self.conn.close()
        self._tmp.cleanup()

    def test_reingesting_the_same_page_changes_nothing(self) -> None:
        frame = _tape([
            {"transaction_hash": "0xt1", "wallet": "0xA", "timestamp": 100},
            {"transaction_hash": "0xt2", "wallet": "0xB", "timestamp": 200},
        ])
        first = ts.insert_tape(self.conn, frame)
        second = ts.insert_tape(self.conn, frame)
        self.assertEqual(first["inserted"], 2)
        self.assertEqual(second["inserted"], 0)
        self.assertEqual(ts.coverage(self.conn)["rows"], 2)

    def test_the_same_hash_stays_two_rows_for_two_wallets(self) -> None:
        # Ein Fill hat zwei Seiten; der Schluessel ist (tx, wallet, asset),
        # nicht der Hash allein.
        frame = _tape([
            {"transaction_hash": "0xt1", "wallet": "0xA", "timestamp": 100},
            {"transaction_hash": "0xt1", "wallet": "0xB", "timestamp": 100},
        ])
        self.assertEqual(ts.insert_tape(self.conn, frame)["inserted"], 2)

    def test_rows_without_identity_are_counted_not_stored(self) -> None:
        frame = _tape([
            {"transaction_hash": "", "wallet": "0xA", "timestamp": 100},
            {"transaction_hash": "0xt2", "wallet": "", "timestamp": 100},
            {"transaction_hash": "0xt3", "wallet": "0xC", "timestamp": 0},
            {"transaction_hash": "0xt4", "wallet": "0xD", "timestamp": 400},
        ])
        result = ts.insert_tape(self.conn, frame)
        self.assertEqual(result["inserted"], 1)
        self.assertEqual(result["skipped"], 3)

    def test_first_seen_survives_overlapping_ingests_in_any_order(self) -> None:
        spaet = _tape([{"transaction_hash": "0xt2", "wallet": "0xA", "timestamp": 900}])
        frueh = _tape([{"transaction_hash": "0xt1", "wallet": "0xA", "timestamp": 100}])
        ts.insert_tape(self.conn, spaet)
        ts.insert_tape(self.conn, frueh)
        ts.insert_tape(self.conn, spaet)
        seen = ts.first_seen_map(self.conn, ["0xA"])
        self.assertEqual(seen["0xa"], 100)

    def test_window_load_filters_days_and_floor_and_keeps_the_tape_shape(self) -> None:
        now = 1_000_000
        frame = _tape([
            {"transaction_hash": "0xt1", "wallet": "0xA", "timestamp": now - 86400, "notional": 5000.0},
            {"transaction_hash": "0xt2", "wallet": "0xB", "timestamp": now - 86400, "notional": 500.0},
            {"transaction_hash": "0xt3", "wallet": "0xC", "timestamp": now - 10 * 86400, "notional": 5000.0},
        ])
        ts.insert_tape(self.conn, frame)
        fenster = ts.load_tape_window(self.conn, days=2.0, min_cash=1000.0, now_ts=now)
        self.assertEqual(list(fenster["wallet"]), ["0xa"])
        self.assertEqual(list(fenster.columns), ts.TAPE_COLUMNS)
        self.assertEqual(str(fenster["time"].dt.tz), "UTC")
        self.assertEqual(fenster.iloc[0]["transaction_hash"], "0xt1")
        self.assertEqual(fenster.iloc[0]["platform"], "Polymarket")

    def test_coverage_reports_span_floor_and_last_run(self) -> None:
        ts.insert_tape(self.conn, _tape([
            {"transaction_hash": "0xt1", "wallet": "0xA", "timestamp": 100},
            {"transaction_hash": "0xt2", "wallet": "0xB", "timestamp": 100 + 2 * 86400},
        ]))
        ts.record_run(self.conn, {
            "started_at": "2026-08-30T10:00:00+00:00", "finished_at": "2026-08-30T10:00:05+00:00",
            "min_cash": 1000.0, "pages_requested": 8, "pages_read": 2,
            "rows_fetched": 2, "rows_inserted": 2, "rows_skipped": 0,
            "oldest_ts": 100, "newest_ts": 100 + 2 * 86400,
            "truncated_by_error": True, "error": "boom",
        })
        cov = ts.coverage(self.conn)
        self.assertEqual(cov["rows"], 2)
        self.assertEqual(cov["wallets"], 2)
        self.assertAlmostEqual(cov["window_days"], 2.0)
        self.assertEqual(cov["ingest_floor"], 1000.0)
        self.assertEqual(cov["runs"], 1)
        self.assertTrue(cov["last_run_truncated"])
        self.assertEqual(cov["last_run_error"], "boom")

    def test_first_seen_map_lowercases_and_limits_to_the_asked_wallets(self) -> None:
        ts.insert_tape(self.conn, _tape([
            {"transaction_hash": "0xt1", "wallet": "0xAbC", "timestamp": 100},
            {"transaction_hash": "0xt2", "wallet": "0xDeF", "timestamp": 200},
        ]))
        seen = ts.first_seen_map(self.conn, ["0xABC"])
        self.assertEqual(seen, {"0xabc": 100})
        self.assertEqual(len(ts.first_seen_map(self.conn)), 2)


class IngestOnceTests(unittest.TestCase):
    """Die Seitenschleife des Ingest-Jobs, netzfrei ueber ``fetch``."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.conn = ts.connect(Path(self._tmp.name) / "tape.sqlite")

    def tearDown(self) -> None:
        self.conn.close()
        self._tmp.cleanup()

    def test_a_full_page_of_known_prints_ends_the_pass(self) -> None:
        bekannt = _tape([
            {"transaction_hash": f"0xt{i}", "wallet": "0xA", "timestamp": 100 + i}
            for i in range(3)
        ])
        ts.insert_tape(self.conn, bekannt)
        calls: list[int] = []

        def fetch(limit: int, min_cash: float, offset: int) -> pd.DataFrame:
            calls.append(offset)
            return bekannt.head(limit)

        record = ingest.ingest_once(self.conn, min_cash=1000.0, pages=5, page_size=3, fetch=fetch)
        self.assertEqual(calls, [0])
        self.assertEqual(record["rows_inserted"], 0)
        self.assertEqual(record["pages_read"], 1)
        self.assertFalse(record["truncated_by_error"])

    def test_a_short_page_means_the_feed_ended(self) -> None:
        seite = _tape([{"transaction_hash": "0xt1", "wallet": "0xA", "timestamp": 100}])

        def fetch(limit: int, min_cash: float, offset: int) -> pd.DataFrame:
            return seite if offset == 0 else pd.DataFrame()

        record = ingest.ingest_once(self.conn, min_cash=1000.0, pages=5, page_size=3, fetch=fetch)
        self.assertEqual(record["pages_read"], 1)
        self.assertEqual(record["rows_inserted"], 1)

    def test_a_feed_error_is_recorded_as_truncation_not_swallowed(self) -> None:
        seite = _tape([
            {"transaction_hash": f"0xt{i}", "wallet": "0xA", "timestamp": 100 + i}
            for i in range(3)
        ])

        def fetch(limit: int, min_cash: float, offset: int) -> pd.DataFrame:
            if offset == 0:
                return seite
            raise RuntimeError("feed down")

        record = ingest.ingest_once(self.conn, min_cash=1000.0, pages=5, page_size=3, fetch=fetch)
        self.assertTrue(record["truncated_by_error"])
        self.assertIn("feed down", record["error"])
        self.assertEqual(record["rows_inserted"], 3)
        cov = ts.coverage(self.conn)
        self.assertEqual(cov["runs"], 1)
        self.assertTrue(cov["last_run_truncated"])


if __name__ == "__main__":
    unittest.main()
