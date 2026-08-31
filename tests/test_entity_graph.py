"""Der Entity-Graph: harte Belege fuehren zusammen, Kandidaten nie.

Die Kernzusagen aus dem Produktvorschlag, hier als Vertrag: nur externe
Gegenparteien werden ueberhaupt festgehalten (Protokoll- und Bridge-Verkehr
verbindet niemanden), Stufe-1-Belege (direkte Transfers, gemeinsamer Funder,
gemeinsames Auszahlungsziel, Positionstransfers) mergen per Union-Find,
Stufe-2-Beobachtungen (Gegenpartei verhaelt sich wie eine Boerse) bleiben
Kandidatenliste, und jeder Rebuild ist idempotent, weil der Graph eine
Ableitung ist und keine zweite Wahrheit.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from app import entity_graph as eg

W_A = "0x" + "a" * 40
W_B = "0x" + "b" * 40
W_C = "0x" + "c" * 40
W_D = "0x" + "d" * 40
W_E = "0x" + "e" * 40
FUNDER = "0x" + "f" * 40


def _flows(rows: list[dict]) -> pd.DataFrame:
    data = []
    for index, row in enumerate(rows):
        data.append({
            "tx": row.get("tx", f"0xt{index}"),
            "counterparty": row["counterparty"],
            "direction": row.get("direction", "in"),
            "amount": float(row.get("amount", 100.0)),
            "classification": row.get("classification", "external"),
            "timestamp": pd.Timestamp(row.get("ts", "2026-08-01T12:00:00Z")),
        })
    return pd.DataFrame(data)


def _positions(rows: list[dict]) -> pd.DataFrame:
    data = []
    for index, row in enumerate(rows):
        data.append({
            "tx": row.get("tx", f"0xp{index}"),
            "sender": row["sender"],
            "recipient": row["recipient"],
            "shares": float(row.get("shares", 1000.0)),
            "timestamp": pd.Timestamp(row.get("ts", "2026-08-02T12:00:00Z")),
        })
    return pd.DataFrame(data)


class EntityGraphTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.conn = eg.connect(Path(tmp.name) / "graph.sqlite")
        self.addCleanup(self.conn.close)

    def _rebuild(self, degree_cap: int = eg.DEFAULT_DEGREE_CAP) -> None:
        eg.rebuild_edges(self.conn, degree_cap=degree_cap)
        eg.assign_entities(self.conn)

    def test_only_external_counterparties_enter_the_link_table(self) -> None:
        ergebnis = eg.record_scan(self.conn, W_A, _flows([
            {"counterparty": FUNDER, "classification": "external"},
            {"counterparty": "0x" + "1" * 40, "classification": "protocol"},
            {"counterparty": "0x" + "2" * 40, "classification": "ambiguous"},
        ]))
        self.assertEqual(ergebnis["external_transfers"], 1)
        rows = self.conn.execute("SELECT counterparty FROM funding_links").fetchall()
        self.assertEqual([r[0] for r in rows], [FUNDER])

    def test_a_direct_transfer_between_scanned_wallets_merges_them(self) -> None:
        eg.record_scan(self.conn, W_A, _flows([
            {"counterparty": W_B, "direction": "in", "tx": "0xlink", "ts": "2026-07-01T00:00:00Z"}]))
        eg.record_scan(self.conn, W_B, _flows([]))
        self._rebuild()
        ansicht = eg.entity_view(self.conn, W_A)
        self.assertEqual(ansicht["entity_wallets"], [W_A, W_B])
        [kante] = ansicht["linked_wallets"]
        self.assertEqual(kante["typ"], eg.TYP_DIRECT)
        self.assertEqual(kante["stufe"], 1)
        self.assertAlmostEqual(kante["konfidenz"], 0.95)
        self.assertIn("0xlink", kante["evidenz"]["tx_sample"])
        self.assertTrue(kante["first_seen"].startswith("2026-07-01"))

    def test_an_unscanned_counterparty_stays_a_funding_source(self) -> None:
        eg.record_scan(self.conn, W_A, _flows([{"counterparty": W_B}]))
        self._rebuild()
        ansicht = eg.entity_view(self.conn, W_A)
        self.assertEqual(ansicht["entity_wallets"], [W_A])
        self.assertEqual(ansicht["linked_wallets"], [])

    def test_a_shared_funder_links_two_wallets(self) -> None:
        eg.record_scan(self.conn, W_A, _flows([{"counterparty": FUNDER, "tx": "0xa1"}]))
        eg.record_scan(self.conn, W_B, _flows([{"counterparty": FUNDER, "tx": "0xb1"}]))
        self._rebuild()
        ansicht = eg.entity_view(self.conn, W_A)
        self.assertEqual(ansicht["entity_wallets"], [W_A, W_B])
        [kante] = ansicht["linked_wallets"]
        self.assertEqual(kante["typ"], eg.TYP_SHARED_FUNDER)
        [beleg] = kante["evidenz"]["shared_counterparties"]
        self.assertEqual(beleg["counterparty"], FUNDER)
        self.assertEqual(sorted(beleg["tx_sample"]), ["0xa1", "0xb1"])

    def test_a_busy_counterparty_is_a_candidate_not_a_link(self) -> None:
        for index, wallet in enumerate((W_A, W_B, W_C, W_D, W_E)):
            eg.record_scan(self.conn, wallet, _flows([
                {"counterparty": FUNDER, "ts": f"2026-08-{10 + index * 5:02d}T12:00:00Z"}]))
        self._rebuild(degree_cap=4)
        ansicht = eg.entity_view(self.conn, W_A)
        # Fuenf Kunden derselben Adresse: verhaelt sich wie eine Boerse.
        self.assertEqual(ansicht["entity_wallets"], [W_A])
        self.assertEqual(ansicht["linked_wallets"], [])
        self.assertTrue(ansicht["candidates"])
        for kandidat in ansicht["candidates"]:
            self.assertEqual(kandidat["typ"], eg.TYP_SHARED_HUB)
            self.assertEqual(kandidat["stufe"], 2)
            [beleg] = kandidat["evidenz"]["shared_counterparties"]
            self.assertEqual(beleg["counterparty_wallets"], 5)

    def test_a_narrow_window_raises_candidate_confidence(self) -> None:
        stempel = ["2026-08-10T12:00:00Z", "2026-08-11T06:00:00Z", "2026-06-01T00:00:00Z",
                   "2026-07-01T00:00:00Z", "2026-05-01T00:00:00Z"]
        for wallet, ts in zip((W_A, W_B, W_C, W_D, W_E), stempel):
            eg.record_scan(self.conn, wallet, _flows([{"counterparty": FUNDER, "ts": ts}]))
        self._rebuild(degree_cap=4)
        kanten = eg.entity_view(self.conn, W_A)["candidates"]
        nach_wallet = {k["wallet"]: k for k in kanten}
        # A und B wurden binnen 18 Stunden finanziert: engeres Fenster,
        # mehr Konfidenz - aber weiter Kandidat, nie ein Merge.
        self.assertAlmostEqual(nach_wallet[W_B]["konfidenz"], eg.KONFIDENZ_HUB_ENGES_FENSTER)
        self.assertTrue(nach_wallet[W_B]["evidenz"]["shared_counterparties"][0]["narrow_window"])
        self.assertAlmostEqual(nach_wallet[W_C]["konfidenz"], eg.KONFIDENZ[eg.TYP_SHARED_HUB])

    def test_three_wallets_at_one_counterparty_is_a_candidate_not_a_merge(self) -> None:
        # Ab drei bedienten Wallets ist eine geteilte Gegenpartei auf Polygon
        # fast immer ein Deposit-Router oder eine Boersen-Hotwallet, nicht ein
        # Operator, der genau diese drei kontrolliert. Der Standard-Cap ist 2
        # (der Operator-Fall); drei sind Kandidat, nie Merge.
        for wallet in (W_A, W_B, W_C):
            eg.record_scan(self.conn, wallet, _flows([
                {"counterparty": FUNDER, "direction": "out"}]))
        self._rebuild()
        ansicht = eg.entity_view(self.conn, W_A)
        self.assertEqual(ansicht["entity_wallets"], [W_A])
        self.assertEqual(ansicht["linked_wallets"], [])
        self.assertEqual({k["typ"] for k in ansicht["candidates"]}, {eg.TYP_SHARED_HUB})

    def test_a_high_degree_wallet_does_not_merge_the_whole_set(self) -> None:
        # Eine Market-Maker-Wallet, die mit vielen Konten direkt Geld bewegt,
        # ist selbst Infrastruktur: ihre harten Kanten bleiben sichtbar, aber
        # sie verschmelzen den halben Scan-Satz nicht zu einer Entity. Ohne
        # diese Schranke zog ein einziger Hub-Knoten 45 der 50 groessten
        # Wallets in eine "Entity".
        partner = ["0x" + f"{i:040x}" for i in range(1, 7)]
        for w in partner:
            eg.record_scan(self.conn, w, _flows([]))
        # W_A bewegt direkt Geld an sechs gescannte Wallets: harter Grad 6.
        eg.record_scan(self.conn, W_A, _flows([
            {"counterparty": p, "direction": "out", "tx": f"0xhub{i}"}
            for i, p in enumerate(partner)]))
        eg.rebuild_edges(self.conn)
        eg.assign_entities(self.conn, hub_hard_degree=4)
        ansicht = eg.entity_view(self.conn, W_A)
        # Die Kanten stehen weiter da (der Transfer ist echt), aber keine Entity.
        self.assertTrue(ansicht["linked_wallets"])
        self.assertEqual(ansicht["entity_wallets"], [W_A])
        self.assertIn(W_A, eg.hub_wallets(self.conn, hub_hard_degree=4))

    def test_a_pair_collects_evidence_across_shared_counterparties(self) -> None:
        zweiter_funder = "0x" + "9" * 40
        eg.record_scan(self.conn, W_A, _flows([
            {"counterparty": FUNDER, "tx": "0xa1"},
            {"counterparty": zweiter_funder, "tx": "0xa2"},
        ]))
        eg.record_scan(self.conn, W_B, _flows([
            {"counterparty": FUNDER, "tx": "0xb1"},
            {"counterparty": zweiter_funder, "tx": "0xb2"},
        ]))
        self._rebuild()
        [kante] = eg.entity_view(self.conn, W_A)["linked_wallets"]
        # Ein Paar, ein Kantentyp, ZWEI gesammelte Belege: zwei gemeinsame
        # Funder sind ein staerkerer Befund als einer, und frueher
        # ueberlebte je Paar und Typ nur die zuletzt geschriebene
        # Gegenpartei.
        self.assertEqual(kante["typ"], eg.TYP_SHARED_FUNDER)
        gegenparteien = {b["counterparty"] for b in kante["evidenz"]["shared_counterparties"]}
        self.assertEqual(gegenparteien, {FUNDER, zweiter_funder})

    def test_a_globally_busy_funder_is_a_candidate_despite_local_degree_two(self) -> None:
        # Die bekannte Luecke des lokalen Grads: ein Router bedient on-chain
        # tausende Konten, im Scan-Set aber zufaellig nur zwei - ohne den
        # globalen Blick saehe er wie eine private Operator-Quelle aus.
        eg.record_scan(self.conn, W_A, _flows([{"counterparty": FUNDER}]))
        eg.record_scan(self.conn, W_B, _flows([{"counterparty": FUNDER}]))
        eg.record_fanout(self.conn, FUNDER, {"partners": 500, "transfers": 10000, "complete": False})
        self._rebuild()
        ansicht = eg.entity_view(self.conn, W_A)
        self.assertEqual(ansicht["entity_wallets"], [W_A])
        self.assertEqual(ansicht["linked_wallets"], [])
        [kandidat] = ansicht["candidates"]
        self.assertEqual(kandidat["typ"], eg.TYP_SHARED_HUB)
        [beleg] = kandidat["evidenz"]["shared_counterparties"]
        self.assertEqual(beleg["global_partners"], 500)
        self.assertFalse(beleg["global_complete"])

    def test_a_checked_private_funder_still_links_and_says_so(self) -> None:
        eg.record_scan(self.conn, W_A, _flows([{"counterparty": FUNDER}]))
        eg.record_scan(self.conn, W_B, _flows([{"counterparty": FUNDER}]))
        eg.record_fanout(self.conn, FUNDER, {"partners": 4, "transfers": 30, "complete": True})
        self._rebuild()
        [kante] = eg.entity_view(self.conn, W_A)["linked_wallets"]
        [beleg] = kante["evidenz"]["shared_counterparties"]
        self.assertEqual(beleg["global_partners"], 4)
        self.assertTrue(beleg["global_complete"])

    def test_an_unchecked_funder_links_but_marks_the_missing_look(self) -> None:
        # Ohne Lookup bleibt die Kante hart (der Scan holt den Blick im
        # naechsten Durchgang nach), aber der Beleg sagt das ausdruecklich:
        # "nicht geprueft" ist eine andere Aussage als "geprueft und privat".
        eg.record_scan(self.conn, W_A, _flows([{"counterparty": FUNDER}]))
        eg.record_scan(self.conn, W_B, _flows([{"counterparty": FUNDER}]))
        self._rebuild()
        [kante] = eg.entity_view(self.conn, W_A)["linked_wallets"]
        [beleg] = kante["evidenz"]["shared_counterparties"]
        self.assertIsNone(beleg["global_partners"])
        self.assertIsNone(beleg["global_complete"])

    def test_pending_fanout_lists_only_potential_hard_counterparties(self) -> None:
        drei = "0x" + "3" * 40
        for wallet in (W_A, W_B):
            eg.record_scan(self.conn, wallet, _flows([
                {"counterparty": FUNDER}, {"counterparty": drei}]))
        eg.record_scan(self.conn, W_C, _flows([{"counterparty": drei}]))
        eg.record_fanout(self.conn, FUNDER, {"partners": 2, "transfers": 4, "complete": True})
        # FUNDER ist schon nachgeschlagen; "drei" bedient drei Wallets und
        # wird ohnehin Kandidat - niemand braucht dafuer einen Lookup.
        self.assertEqual(eg.pending_fanout_counterparties(self.conn), [])

    def test_transitive_hard_evidence_builds_one_entity(self) -> None:
        eg.record_scan(self.conn, W_A, _flows([{"counterparty": W_B, "direction": "out"}]))
        eg.record_scan(self.conn, W_B, _flows([{"counterparty": FUNDER}]))
        eg.record_scan(self.conn, W_C, _flows([{"counterparty": FUNDER}]))
        self._rebuild()
        ansicht = eg.entity_view(self.conn, W_B)
        self.assertEqual(ansicht["entity_wallets"], [W_A, W_B, W_C])
        self.assertEqual(ansicht["entity_id"], f"entity:{W_A}")

    def test_position_transfers_link_at_top_confidence(self) -> None:
        eg.record_scan(self.conn, W_A, _flows([]),
                       _positions([{"sender": W_A, "recipient": W_B, "tx": "0xpos"}]))
        eg.record_scan(self.conn, W_B, _flows([]))
        self._rebuild()
        [kante] = eg.entity_view(self.conn, W_A)["linked_wallets"]
        self.assertEqual(kante["typ"], eg.TYP_POSITION)
        self.assertAlmostEqual(kante["konfidenz"], 0.95)
        self.assertIn("0xpos", kante["evidenz"]["tx_sample"])
        self.assertEqual(eg.entity_view(self.conn, W_B)["entity_wallets"], [W_A, W_B])

    def test_rebuild_is_idempotent(self) -> None:
        eg.record_scan(self.conn, W_A, _flows([{"counterparty": FUNDER}]))
        eg.record_scan(self.conn, W_B, _flows([{"counterparty": FUNDER}]))
        self._rebuild()
        vorher = eg.graph_stats(self.conn)
        self._rebuild()
        self.assertEqual(eg.graph_stats(self.conn), vorher)

    def test_a_rescan_replaces_instead_of_accumulating(self) -> None:
        fluss = _flows([{"counterparty": FUNDER, "amount": 100.0}])
        eg.record_scan(self.conn, W_A, fluss)
        eg.record_scan(self.conn, W_A, fluss)
        betrag = self.conn.execute(
            "SELECT amount FROM funding_links WHERE wallet = ?", (W_A,)).fetchone()[0]
        self.assertAlmostEqual(betrag, 100.0)

    def test_the_view_separates_not_scanned_from_stands_alone(self) -> None:
        eg.record_scan(self.conn, W_A, _flows([]))
        self._rebuild()
        allein = eg.entity_view(self.conn, W_A)
        self.assertTrue(allein["scanned"])
        self.assertEqual(allein["entity_wallets"], [W_A])
        fremd = eg.entity_view(self.conn, W_B)
        self.assertFalse(fremd["scanned"])
        self.assertIsNone(fremd["entity_id"])


class EntityRouteTests(unittest.TestCase):
    """Die API-Route liest nur den lokalen Graphen und benennt seine Grenzen."""

    def test_the_route_reads_the_graph_and_carries_the_caveat(self) -> None:
        import os
        from unittest import mock

        from api import server

        server._CACHE.clear()
        with tempfile.TemporaryDirectory() as tmp:
            pfad = Path(tmp) / "graph.sqlite"
            conn = eg.connect(pfad)
            try:
                eg.record_scan(conn, W_A, _flows([]))
                eg.assign_entities(conn)
            finally:
                conn.close()
            with mock.patch.dict(os.environ, {"ENTITY_GRAPH_PATH": str(pfad)}):
                payload = server.wallet_entity(W_A)
            self.assertTrue(payload["available"])
            self.assertTrue(payload["scanned"])
            self.assertEqual(payload["entity_wallets"], [W_A])
            self.assertTrue(payload["caveat"])
            # Kein Graph auf diesem Host ist eine eigene Antwort, kein leerer
            # Befund - die Route sagt, wie man einen bekommt.
            with mock.patch.dict(os.environ, {"ENTITY_GRAPH_PATH": str(Path(tmp) / "missing.sqlite")}):
                fehlt = server.wallet_entity(W_B)
            self.assertFalse(fehlt["available"])
            self.assertFalse(fehlt["scanned"])

    def test_the_route_carries_tier3_behavior_when_the_store_holds_tape(self) -> None:
        import os
        import time as time_mod
        from unittest import mock

        from api import server
        from src import trade_store as trs

        server._CACHE.clear()
        with tempfile.TemporaryDirectory() as tmp:
            graph = Path(tmp) / "graph.sqlite"
            conn = eg.connect(graph)
            try:
                eg.record_scan(conn, W_A, _flows([]))
                eg.assign_entities(conn)
            finally:
                conn.close()
            # Acht Prints in 28 Sekunden auf derselben Marktseite: der
            # Splitting-Fingerprint aus dem gespeicherten Band.
            jetzt = int(time_mod.time())
            tape = pd.DataFrame([
                {
                    "transaction_hash": f"0xt{i}", "wallet": W_A, "asset": f"as{i}",
                    "timestamp": jetzt - i * 4, "side": "BUY", "outcome": "YES",
                    "title": "Burst market", "price": 0.5, "size": 200.0,
                    "notional": 100.0, "market_key": "m1", "slug": "s", "trader": "",
                }
                for i in range(8)
            ])
            store = Path(tmp) / "store.sqlite"
            sconn = trs.connect(store)
            try:
                trs.record_tape(sconn, tape)
            finally:
                sconn.close()
            umgebung = {"ENTITY_GRAPH_PATH": str(graph), "TRADE_STORE_PATH": str(store)}
            with mock.patch.dict(os.environ, umgebung):
                payload = server.wallet_entity(W_A)
        verhalten = payload["behavior"]
        self.assertTrue(verhalten["available"])
        [fingerprint] = verhalten["fingerprints"]
        self.assertEqual(fingerprint["wallet"], W_A)
        self.assertEqual(int(fingerprint["burst_prints"]), 8)
        self.assertIn("never used to merge", verhalten["note"])


if __name__ == "__main__":
    unittest.main()
