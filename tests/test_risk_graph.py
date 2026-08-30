"""Die Regelleiter unter dem Co-Trading-Bild, und was die Nutzlast davon sagt.

Der Graph auf dem Risk-Screen entsteht unter der ersten Kantenregel, die
ueberhaupt etwas findet. Das ist richtig so — ein leeres Bild ist keine
Antwort —, aber es ist Teil des Befunds: derselbe Graph unter der strengsten
und unter der lockersten Sprosse sagt zwei verschiedene Dinge. Die Nutzlast
nannte bisher nur die Sprosse, die getragen hat, und das Bild berief sich
darauf, als waere es die einzige.
"""

from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

import pandas as pd

from api import server
from app import api_views as apv

WALLET_A = "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
WALLET_B = "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"


def _tape(stunden_auseinander: float, notional: float = 500.0) -> pd.DataFrame:
    """Zwei Wallets, zwei gemeinsame Maerkte, aber nicht gleichzeitig.

    Damit faellt die strengste Sprosse (3 Maerkte in 5 Minuten, 10k Notional)
    aus, die mittlere (2 Maerkte in 5 Minuten) auch, und nur die unterste
    (2 Maerkte irgendwann im Fenster) findet die Kante.
    """

    start = pd.Timestamp("2026-08-28T12:00:00Z")
    rows = []
    for markt in ("Market one", "Market two"):
        for index, wallet in enumerate((WALLET_A, WALLET_B)):
            rows.append({
                "wallet": wallet, "title": markt, "outcome": "YES",
                "notional": notional,
                "time": start + pd.Timedelta(hours=stunden_auseinander * index),
            })
        start = start + pd.Timedelta(days=1)
    return pd.DataFrame(rows)


class LadderTests(unittest.TestCase):
    def test_the_ladder_reports_every_rung_it_tried(self) -> None:
        nodes, edges, sprossen = server.co_trading_ladder(_tape(6.0))
        self.assertFalse(nodes.empty)
        self.assertEqual(len(sprossen), len(server.CO_TRADING_LADDER))
        # Die beiden strengen Sprossen wurden versucht und fanden nichts.
        self.assertTrue(all(s["versucht"] for s in sprossen))
        self.assertEqual(sprossen[0]["wallets"], 0)
        self.assertEqual(sprossen[1]["wallets"], 0)
        self.assertEqual(sprossen[2]["wallets"], 2)
        self.assertEqual([s["gewaehlt"] for s in sprossen], [False, False, True])

    def test_a_rung_below_the_chosen_one_counts_as_not_tried(self) -> None:
        # Nicht versucht ist etwas anderes als nichts gefunden, und null
        # waere die zweite Aussage. Also steht dort None.
        _, _, sprossen = server.co_trading_ladder(_tape(0.0, notional=20_000.0))
        self.assertTrue(sprossen[0]["versucht"])
        self.assertFalse(sprossen[-1]["versucht"])
        self.assertIsNone(sprossen[-1]["wallets"])

    def test_an_empty_tape_leaves_every_rung_empty_handed(self) -> None:
        nodes, _, sprossen = server.co_trading_ladder(pd.DataFrame())
        self.assertTrue(nodes.empty)
        self.assertTrue(all(s["versucht"] for s in sprossen))
        self.assertFalse(any(s["gewaehlt"] for s in sprossen))

    def test_the_ladder_is_a_named_constant_the_payload_can_quote(self) -> None:
        self.assertEqual(len(server.CO_TRADING_LADDER), 3)
        for beschreibung, parameter in server.CO_TRADING_LADDER:
            self.assertTrue(beschreibung.strip())
            self.assertIn("min_shared", parameter)


class GraphPayloadTests(unittest.TestCase):
    def _graph(self, sprossen):
        nodes = pd.DataFrame([
            {"wallet": WALLET_A, "cluster_id": 0, "x": 0.1, "y": 0.2, "volume": 1000.0,
             "markets": 2, "trades": 2, "shared_markets": 2},
            {"wallet": WALLET_B, "cluster_id": 0, "x": 0.3, "y": 0.4, "volume": 900.0,
             "markets": 2, "trades": 2, "shared_markets": 2},
        ])
        edges = pd.DataFrame([{"wallet_a": WALLET_A, "wallet_b": WALLET_B,
                               "shared_markets": 2, "pair_notional": 2000.0,
                               "expected_shared": 0.4, "lift": 5.0}])
        return apv.network_graph(nodes, edges, regel="loose rule", leiter=sprossen)

    def test_the_payload_carries_the_whole_ladder_not_only_the_winner(self) -> None:
        _, _, sprossen = server.co_trading_ladder(_tape(6.0))
        graph = self._graph(sprossen)
        self.assertEqual(len(graph["regel_leiter"]), 3)
        self.assertEqual([s["gewaehlt"] for s in graph["regel_leiter"]],
                         [False, False, True])
        self.assertEqual(graph["regel_leiter"][0]["wallets"], 0)
        self.assertIn("min_shared", graph["regel_leiter"][0]["parameter"])

    def test_an_untried_rung_stays_unknown_rather_than_zero(self) -> None:
        graph = self._graph([
            {"regel": "strict", "parameter": {"min_shared": 3}, "versucht": True,
             "wallets": 2, "kanten": 1, "gewaehlt": True},
            {"regel": "loose", "parameter": {"min_shared": 2}, "versucht": False,
             "wallets": None, "kanten": None, "gewaehlt": False},
        ])
        self.assertIsNone(graph["regel_leiter"][1]["wallets"])
        self.assertFalse(graph["regel_leiter"][1]["versucht"])

    def test_without_a_ladder_the_key_stays_out_of_the_payload(self) -> None:
        self.assertNotIn("regel_leiter", self._graph(None))


class StoreTapeTests(unittest.TestCase):
    """``load_store_tape``: der Store traegt das Bild nur, wenn er es tragen kann.

    Drei Wachposten, jeder gegen ein stilles Falschbild: keine Datei (Deploy-
    Host), zu wenig Fenster (das Live-Band waere tiefer) und ein stehender
    Ingest (ein eingefrorenes Band saehe sonst aktuell aus). Nur wenn alle
    drei durchlassen, kommt ein Frame mit Store-Stichprobenvermerk zurueck.
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _store(self, hours: int, end_offset_s: int = 0) -> Path:
        from app import tape_store as ts

        now = int(time.time()) - end_offset_s
        rows = [
            {
                "transaction_hash": f"0xt{i}", "wallet": WALLET_A if i % 2 else WALLET_B,
                "asset": f"a{i}", "timestamp": now - i * 3600, "notional": 50_000.0,
                "title": f"Market {i % 5}", "outcome": "Yes", "side": "BUY",
                "price": 0.5, "size": 1.0, "market_key": f"m{i % 5}",
                "trader": "", "slug": "", "url": "",
            }
            for i in range(hours)
        ]
        path = self.tmp / "tape.sqlite"
        conn = ts.connect(path)
        try:
            ts.insert_tape(conn, pd.DataFrame(rows))
        finally:
            conn.close()
        return path

    def test_a_missing_store_is_an_empty_frame(self) -> None:
        self.assertTrue(server.load_store_tape(self.tmp / "missing.sqlite").empty)

    def test_a_deep_fresh_store_carries_the_basis_and_names_its_window(self) -> None:
        from src import prediction_markets as md

        frame = server.load_store_tape(self._store(hours=72))
        self.assertFalse(frame.empty)
        record = md.sample_coverage(frame)
        self.assertEqual(record["source"], "tape_store")
        self.assertIn("days of stored tape", md.sample_note(record))

    def test_a_thin_store_defers_to_the_live_tape(self) -> None:
        self.assertTrue(server.load_store_tape(self._store(hours=24)).empty)

    def test_a_stale_store_defers_instead_of_freezing_the_screen(self) -> None:
        stale = self._store(hours=72, end_offset_s=2 * 86400)
        self.assertTrue(server.load_store_tape(stale).empty)


if __name__ == "__main__":
    unittest.main()
