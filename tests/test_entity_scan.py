"""Die Scan-Runde als Bibliothek: Zielwahl, Drossel, und der Worker-Schalter.

Die Runde laeuft an zwei Orten (geplante Task lokal, Worker-Thread im
API-Prozess auf dem Deploy-Host) und muss deshalb ohne Netz pruefbar sein:
der eigentliche Wallet-Scan wird hier durch einen Doppel ersetzt, der nur
festhaelt, wer drankam. Die Zielwahl (--flagged) liest den Tape-Store und
uebernimmt genau die Wallets, die der Insider-Score des Risk-Screens ueber
die Schwelle hebt - nicht die groessten.
"""

from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import pandas as pd

from app import entity_graph as eg
from app import entity_scan as es
from src import trade_store as trs

W_A = "0x" + "a" * 40
W_B = "0x" + "b" * 40
AUFFAELLIG = "0x" + "e" * 40
UNAUFFAELLIG = "0x" + "d" * 40


def _store_mit_tape(pfad: Path) -> None:
    """Ein Tape, in dem genau eine Wallet den Insider-Score reisst.

    Zwei spaete Long-Odds-Prints, ein Markt, eine Richtung: Long-Odds-,
    Konzentrations-, Richtungs- und Frische-Punkte zusammen liegen klar
    ueber der 55er-Schwelle. Die Hintergrund-Wallet verteilt kleine Prints
    ueber das Fenster und bleibt weit darunter.
    """

    jetzt = int(time.time())
    rows = []
    for i in range(6):
        rows.append({
            "transaction_hash": f"0xbg{i}", "wallet": UNAUFFAELLIG, "asset": f"b{i}",
            "timestamp": jetzt - i * 7200, "side": "BUY" if i % 2 else "SELL",
            "outcome": "YES" if i % 2 else "NO", "title": f"Market {i}", "price": 0.5,
            "size": 200.0, "notional": 100.0, "market_key": f"m{i}", "slug": "s", "trader": "",
        })
    for i in range(2):
        rows.append({
            "transaction_hash": f"0xhot{i}", "wallet": AUFFAELLIG, "asset": f"h{i}",
            "timestamp": jetzt - 60 - i * 30, "side": "BUY", "outcome": "YES",
            "title": "Longshot market", "price": 0.1, "size": 300000.0,
            "notional": 30000.0, "market_key": "mhot", "slug": "s", "trader": "",
        })
    conn = trs.connect(pfad)
    try:
        trs.record_tape(conn, pd.DataFrame(rows))
    finally:
        conn.close()


class FlaggedTargetTests(unittest.TestCase):
    def test_flagged_picks_the_conspicuous_wallet_not_the_background(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pfad = Path(tmp) / "store.sqlite"
            _store_mit_tape(pfad)
            with mock.patch.dict(os.environ, {"TRADE_STORE_PATH": str(pfad)}):
                treffer = es.flagged_wallets(10, min_score=55.0)
        self.assertIn(AUFFAELLIG, treffer)
        self.assertNotIn(UNAUFFAELLIG, treffer)

    def test_without_a_store_there_are_no_targets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fehlt = str(Path(tmp) / "missing.sqlite")
            with mock.patch.dict(os.environ, {"TRADE_STORE_PATH": fehlt}):
                self.assertEqual(es.flagged_wallets(10), [])
                self.assertEqual(es.top_store_wallets(10), [])


class ScanPassTests(unittest.TestCase):
    def _fake_scan(self, conn, wallet, api_key, pages, pause):
        eg.record_scan(conn, wallet, pd.DataFrame(), complete=True)
        return f"[scan] {wallet}: faked"

    def test_a_pass_scans_named_wallets_and_rederives_the_graph(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "graph.sqlite"
            with mock.patch.object(es, "scan_wallet", self._fake_scan):
                ergebnis = es.scan_pass(db, "key", wallets=[W_A, W_B], pause=0.0)
        self.assertEqual(ergebnis["targets"], 2)
        self.assertEqual(ergebnis["scanned"], 2)
        self.assertEqual(ergebnis["stats"]["scans"], 2)

    def test_the_rescan_throttle_skips_fresh_wallets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "graph.sqlite"
            with mock.patch.object(es, "scan_wallet", self._fake_scan):
                es.scan_pass(db, "key", wallets=[W_A], pause=0.0)
                zweiter = es.scan_pass(db, "key", wallets=[W_A], pause=0.0)
        self.assertEqual(zweiter["scanned"], 0)
        self.assertEqual(zweiter["skipped"], 1)

    def test_no_targets_is_a_state_not_an_exception(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "graph.sqlite"
            fehlt = str(Path(tmp) / "missing.sqlite")
            with mock.patch.dict(os.environ, {"TRADE_STORE_PATH": fehlt}):
                ergebnis = es.scan_pass(db, "key", flagged=10)
        self.assertEqual(ergebnis["targets"], 0)
        self.assertEqual(ergebnis["scanned"], 0)

    def test_one_failing_wallet_does_not_kill_the_pass(self) -> None:
        def kaputt(conn, wallet, api_key, pages, pause):
            if wallet == W_A:
                raise RuntimeError("walk died")
            return self._fake_scan(conn, wallet, api_key, pages, pause)

        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "graph.sqlite"
            with mock.patch.object(es, "scan_wallet", kaputt):
                ergebnis = es.scan_pass(db, "key", wallets=[W_A, W_B], pause=0.0)
        self.assertEqual(ergebnis["errors"], 1)
        self.assertEqual(ergebnis["scanned"], 1)


class FanoutEnrichmentTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.conn = eg.connect(Path(tmp.name) / "graph.sqlite")
        self.addCleanup(self.conn.close)

    def _shared_funder(self, funder: str) -> None:
        for wallet in (W_A, W_B):
            eg.record_scan(self.conn, wallet, pd.DataFrame([{
                "tx": "0xt" + wallet[-1], "counterparty": funder, "direction": "in",
                "amount": 100.0, "classification": "external",
                "timestamp": pd.Timestamp("2026-08-01T12:00:00Z"),
            }]))

    def test_enrichment_looks_up_and_caches_each_counterparty_once(self) -> None:
        funder = "0x" + "f" * 40
        self._shared_funder(funder)
        aufrufe: list[str] = []

        def fake(gegen, api_key, pause=0.0):
            aufrufe.append(gegen)
            return {"partners": 500, "transfers": 10000, "complete": False}

        self.assertEqual(es.enrich_fanouts(self.conn, "key", fanout=fake), 1)
        self.assertEqual(aufrufe, [funder])
        # Zweiter Durchgang: gecacht, kein weiterer Abruf.
        self.assertEqual(es.enrich_fanouts(self.conn, "key", fanout=fake), 0)
        self.assertEqual(len(aufrufe), 1)
        # Und der Rebuild nutzt den Cache: Kandidat statt harter Kante.
        eg.rebuild_edges(self.conn)
        eg.assign_entities(self.conn)
        self.assertEqual(eg.entity_view(self.conn, W_A)["linked_wallets"], [])

    def test_the_lookup_budget_defers_the_rest_to_the_next_pass(self) -> None:
        funders = ["0x" + f"{i + 100:040x}" for i in range(3)]
        for wallet in (W_A, W_B):
            eg.record_scan(self.conn, wallet, pd.DataFrame([{
                "tx": f"0xt{wallet[-1]}{i}", "counterparty": funder, "direction": "in",
                "amount": 100.0, "classification": "external",
                "timestamp": pd.Timestamp("2026-08-01T12:00:00Z"),
            } for i, funder in enumerate(funders)]))

        def fake(gegen, api_key, pause=0.0):
            return {"partners": 1, "transfers": 2, "complete": True}

        erste = es.enrich_fanouts(self.conn, "key", max_lookups=2, fanout=fake)
        zweite = es.enrich_fanouts(self.conn, "key", max_lookups=2, fanout=fake)
        self.assertEqual(erste, 2)
        self.assertEqual(zweite, 1)

    def test_a_failing_lookup_does_not_kill_the_enrichment(self) -> None:
        funder = "0x" + "f" * 40
        self._shared_funder(funder)

        def kaputt(gegen, api_key, pause=0.0):
            raise RuntimeError("etherscan down")

        es.enrich_fanouts(self.conn, "key", fanout=kaputt)
        # Nicht gecacht: der naechste Durchgang darf es erneut versuchen.
        self.assertEqual(eg.pending_fanout_counterparties(self.conn), [funder])


class WorkerGateTests(unittest.TestCase):
    def test_the_worker_stays_off_without_the_env_switch(self) -> None:
        # ENTITY_SCAN_INTERVAL_H wird beim Import gelesen; ohne die Variable
        # ist der Schalter 0 und der Worker darf nie starten - lokal scannt
        # die geplante Task, und der Graph hat genau einen Schreiber.
        from api import server

        self.assertEqual(server.ENTITY_SCAN_INTERVAL_H, 0.0)
        self.assertFalse(server.start_entity_scan_worker())


if __name__ == "__main__":
    unittest.main()
