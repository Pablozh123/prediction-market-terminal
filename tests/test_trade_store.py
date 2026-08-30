"""Der persistente Whale-Tape-Speicher, und was er dem Netzwerk-Tape beilegt.

Die Kernzusagen: ein Print wird genau einmal gespeichert (Dedup wie in
load_deep_tape), das Lesefenster liefert die Tape-Spalten samt
Zuschnitt-Vermerk, und extend_tape ist in jede Richtung fail-soft — ohne
Datei kommt das Live-Tape unveraendert zurueck, mit Datei sagt der Vermerk,
was der Speicher beigetragen hat. Ein stiller Beitrag waere derselbe Fehler,
den die Regelleiter behoben hat: ein Bild, das sich auf eine Stichprobe
beruft, die es nicht nennt.
"""

from __future__ import annotations

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import pandas as pd

from src import prediction_markets as md
from src import trade_store as ts

WALLET_A = "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
WALLET_B = "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"


def _tape(n: int = 4, start_ts: int | None = None, notional: float = 2000.0) -> pd.DataFrame:
    """Ein kleines Tape mit allen Spalten, die der Speicher behaelt."""

    basis = int(start_ts if start_ts is not None else pd.Timestamp.utcnow().timestamp())
    rows = []
    for index in range(n):
        stempel = basis - index * 3600
        rows.append({
            "transaction_hash": f"0xtx{index:04d}",
            "wallet": WALLET_A if index % 2 == 0 else WALLET_B,
            "asset": f"asset-{index % 3}",
            "timestamp": stempel,
            "side": "BUY",
            "outcome": "YES",
            "title": f"Market {index % 2}",
            "price": 0.42,
            "size": notional / 0.42,
            "notional": notional,
            "market_key": f"0xcond{index % 2}",
            "slug": "some-market",
            "trader": "someone",
            "time": pd.Timestamp(stempel, unit="s", tz="UTC"),
        })
    return pd.DataFrame(rows)


class RecordTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "store.sqlite"
        self.conn = ts.connect(self.path)
        self.addCleanup(self.conn.close)

    def test_a_print_is_stored_exactly_once(self) -> None:
        tape = _tape(4)
        self.assertEqual(ts.record_tape(self.conn, tape), 4)
        # Dieselben Prints noch einmal: nichts Neues, kein Fehler.
        self.assertEqual(ts.record_tape(self.conn, tape), 0)
        self.assertEqual(ts.store_stats(self.conn)["rows"], 4)

    def test_rows_without_identity_are_dropped_not_stored(self) -> None:
        tape = _tape(2)
        tape.loc[0, "transaction_hash"] = ""
        self.assertEqual(ts.record_tape(self.conn, tape), 1)

    def test_recording_stamps_the_ingest_time(self) -> None:
        ts.record_tape(self.conn, _tape(1))
        self.assertTrue(ts.store_stats(self.conn)["last_ingest_utc"])

    def test_prune_removes_only_the_old_tape(self) -> None:
        jetzt = int(pd.Timestamp.utcnow().timestamp())
        ts.record_tape(self.conn, _tape(2, start_ts=jetzt))
        alt = _tape(2, start_ts=jetzt - 90 * 86_400)
        alt["transaction_hash"] = ["0xold1", "0xold2"]
        ts.record_tape(self.conn, alt)
        self.assertEqual(ts.prune(self.conn, keep_days=45.0), 2)
        self.assertEqual(ts.store_stats(self.conn)["rows"], 2)


class WindowTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "store.sqlite"
        self.conn = ts.connect(self.path)
        self.addCleanup(self.conn.close)

    def test_the_window_is_a_tape_frame_with_its_own_sample_record(self) -> None:
        ts.record_tape(self.conn, _tape(4))
        fenster = ts.load_window(self.conn, days=14.0)
        for spalte in ("wallet", "title", "outcome", "notional", "time", "market_key", "url", "platform"):
            self.assertIn(spalte, fenster.columns)
        vermerk = md.sample_coverage(fenster)
        self.assertEqual(vermerk["source"], "trade_store")
        self.assertEqual(vermerk["rows"], 4)
        self.assertEqual(vermerk["store_days_with_data"], 1)

    def test_the_window_cuts_by_age_and_by_floor(self) -> None:
        jetzt = int(pd.Timestamp.utcnow().timestamp())
        ts.record_tape(self.conn, _tape(2, start_ts=jetzt, notional=5000.0))
        alt = _tape(2, start_ts=jetzt - 30 * 86_400, notional=500.0)
        alt["transaction_hash"] = ["0xold1", "0xold2"]
        ts.record_tape(self.conn, alt)
        self.assertEqual(len(ts.load_window(self.conn, days=14.0)), 2)
        self.assertEqual(len(ts.load_window(self.conn, days=60.0, min_cash=1000.0)), 2)
        self.assertEqual(len(ts.load_window(self.conn, days=60.0)), 4)

    def test_an_empty_store_answers_with_an_empty_frame_and_a_record(self) -> None:
        fenster = ts.load_window(self.conn, days=14.0)
        self.assertTrue(fenster.empty)
        self.assertEqual(md.sample_coverage(fenster)["rows"], 0)


class IngestTests(unittest.TestCase):
    def test_one_cycle_fetches_pages_and_reports_what_it_saw(self) -> None:
        tape = _tape(3)

        def fetch(limit: int, min_cash: float, offset: int = 0) -> pd.DataFrame:
            return tape if offset == 0 else pd.DataFrame()

        with TemporaryDirectory() as tmp:
            conn = ts.connect(Path(tmp) / "store.sqlite")
            try:
                ergebnis = ts.ingest_once(conn, min_cash=1000.0, pages=2, fetch=fetch)
                self.assertEqual(ergebnis["fetched"], 3)
                self.assertEqual(ergebnis["new"], 3)
                self.assertEqual(ergebnis["coverage"]["min_cash"], 1000.0)
                # Zweiter Zyklus ueber dasselbe Band: nichts Neues.
                self.assertEqual(ts.ingest_once(conn, min_cash=1000.0, pages=2, fetch=fetch)["new"], 0)
            finally:
                conn.close()


class ExtendTests(unittest.TestCase):
    def test_without_a_store_file_the_live_tape_comes_back_untouched(self) -> None:
        live = _tape(2)
        with TemporaryDirectory() as tmp:
            zurueck = ts.extend_tape(live, path=Path(tmp) / "missing.sqlite")
        self.assertIs(zurueck, live)

    def test_with_a_store_the_union_is_deduped_and_the_record_says_so(self) -> None:
        with TemporaryDirectory() as tmp:
            pfad = Path(tmp) / "store.sqlite"
            conn = ts.connect(pfad)
            try:
                ts.record_tape(conn, _tape(4))
            finally:
                conn.close()
            live = _tape(2)  # dieselben zwei juengsten Prints, plus zwei nur im Speicher
            live.attrs[md.SAMPLE_ATTR] = {"source": "polymarket_trades", "rows": 2, "min_cash": 1000.0}
            zusammen = ts.extend_tape(live, days=14.0, path=pfad)
        self.assertEqual(len(zusammen), 4)
        vermerk = md.sample_coverage(zusammen)
        self.assertEqual(vermerk["rows"], 2)  # der Live-Anteil bleibt benannt
        self.assertEqual(vermerk["store_rows"], 4)
        self.assertEqual(vermerk["combined_rows"], 4)
        self.assertTrue(vermerk["store_last_ingest_utc"])

    def test_an_empty_live_tape_still_gets_the_stored_window(self) -> None:
        with TemporaryDirectory() as tmp:
            pfad = Path(tmp) / "store.sqlite"
            conn = ts.connect(pfad)
            try:
                ts.record_tape(conn, _tape(3))
            finally:
                conn.close()
            leer = pd.DataFrame()
            leer.attrs[md.SAMPLE_ATTR] = {"source": "polymarket_trades", "rows": 0}
            zusammen = ts.extend_tape(leer, days=14.0, path=pfad)
        self.assertEqual(len(zusammen), 3)
        self.assertEqual(md.sample_coverage(zusammen)["store_rows"], 3)


class NoteTests(unittest.TestCase):
    def test_the_note_names_the_stores_contribution(self) -> None:
        satz = ts.store_note({
            "store_rows": 4200, "store_window_days": 14.0, "store_days_with_data": 9,
            "store_last_ingest_utc": "2026-08-30T10:00:00+00:00", "combined_rows": 5100,
        })
        self.assertIn("4,200 prints", satz)
        self.assertIn("9 of 14 days", satz)
        self.assertIn("5,100 prints", satz)
        self.assertIn("last ingest", satz)

    def test_without_store_rows_there_is_no_second_sentence(self) -> None:
        self.assertEqual(ts.store_note({"rows": 800}), "")

    def test_a_capped_window_says_that_the_oldest_days_are_missing(self) -> None:
        satz = ts.store_note({"store_rows": 10, "store_window_days": 14.0,
                              "store_days_with_data": 1, "store_rows_capped": True})
        self.assertIn("row cap", satz)


class FirstSeenTests(unittest.TestCase):
    """Die First-Seen-Tabelle: Untergrenze des Wallet-Alters, prune-fest.

    Im Ein-Tages-Band sieht jede spaet eintretende Wallet neu aus; der Store
    ist die einzige Stelle, die "kannten wir schon vorher" belegen kann
    (``md.whale_wallet_risk_scores`` nimmt die Map als ``known_since``).
    Deshalb darf weder Ueberlappung zwischen Zyklen noch prune die Werte
    verschieben — sonst wandern die Fehlalarme zurueck, die sie abstellt.
    """

    def setUp(self) -> None:
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.conn = ts.connect(Path(tmp.name) / "store.sqlite")
        self.addCleanup(self.conn.close)

    def test_first_seen_survives_overlapping_ingests_in_any_order(self) -> None:
        jetzt = int(pd.Timestamp.utcnow().timestamp())
        spaet = _tape(1, start_ts=jetzt)
        frueh = _tape(1, start_ts=jetzt - 10 * 86_400)
        frueh["transaction_hash"] = ["0xearly"]
        ts.record_tape(self.conn, spaet)
        ts.record_tape(self.conn, frueh)
        ts.record_tape(self.conn, spaet)
        self.assertEqual(ts.first_seen_map(self.conn, [WALLET_A])[WALLET_A], jetzt - 10 * 86_400)

    def test_prune_forgets_old_prints_but_not_old_acquaintances(self) -> None:
        jetzt = int(pd.Timestamp.utcnow().timestamp())
        alt = _tape(1, start_ts=jetzt - 90 * 86_400)
        ts.record_tape(self.conn, alt)
        neu = _tape(1, start_ts=jetzt)
        neu["transaction_hash"] = ["0xfresh"]
        ts.record_tape(self.conn, neu)
        self.assertEqual(ts.prune(self.conn, keep_days=45.0), 1)
        # Der Print ist weg, das Kennenlernen nicht: die Wallet bleibt alt.
        self.assertEqual(ts.first_seen_map(self.conn, [WALLET_A])[WALLET_A], jetzt - 90 * 86_400)

    def test_the_map_lowercases_and_limits_to_the_asked_wallets(self) -> None:
        tape = _tape(2)
        tape["wallet"] = ["0xAbC" + "0" * 37, "0xDeF" + "0" * 37]
        ts.record_tape(self.conn, tape)
        treffer = ts.first_seen_map(self.conn, ["0xABC" + "0" * 37])
        self.assertEqual(list(treffer), ["0xabc" + "0" * 37])
        self.assertEqual(len(ts.first_seen_map(self.conn)), 2)


class StaleIngestNoteTests(unittest.TestCase):
    def test_an_ingest_older_than_the_live_band_names_the_gap(self) -> None:
        vor_drei_tagen = (pd.Timestamp.utcnow() - pd.Timedelta(days=3)).isoformat()
        satz = ts.store_note({"store_rows": 10, "store_window_days": 14.0,
                              "store_days_with_data": 5,
                              "store_last_ingest_utc": vor_drei_tagen})
        self.assertIn("the tape in between is missing", satz)

    def test_a_fresh_ingest_needs_no_gap_warning(self) -> None:
        gerade = pd.Timestamp.utcnow().isoformat()
        satz = ts.store_note({"store_rows": 10, "store_window_days": 14.0,
                              "store_days_with_data": 5,
                              "store_last_ingest_utc": gerade})
        self.assertNotIn("missing from this picture", satz)


class MaybeRecordTests(unittest.TestCase):
    def test_off_by_default_nothing_is_written(self) -> None:
        with TemporaryDirectory() as tmp:
            pfad = Path(tmp) / "store.sqlite"
            with mock.patch.dict(os.environ, {"TRADE_STORE_PATH": str(pfad)}, clear=False):
                os.environ.pop("TRADE_STORE_RECORD", None)
                self.assertEqual(ts.maybe_record(_tape(2)), 0)
            self.assertFalse(pfad.exists())

    def test_opting_in_records_the_frame(self) -> None:
        with TemporaryDirectory() as tmp:
            pfad = Path(tmp) / "store.sqlite"
            umgebung = {"TRADE_STORE_PATH": str(pfad), "TRADE_STORE_RECORD": "1"}
            with mock.patch.dict(os.environ, umgebung, clear=False):
                self.assertEqual(ts.maybe_record(_tape(2)), 2)
                conn = ts.connect(pfad)
                try:
                    self.assertEqual(ts.store_stats(conn)["rows"], 2)
                finally:
                    conn.close()


if __name__ == "__main__":
    unittest.main()
