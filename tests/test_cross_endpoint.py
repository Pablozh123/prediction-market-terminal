"""/api/cross end to end: was die Seite bekommt, wenn beide Venues antworten.

Die beiden Befunde aus PR #106 sitzen genau an dieser Naht. Der Paarer in
``app/cross_pairs.py`` prueft seit diesem Zweig, ob zwei Titel dieselbe Frage
stellen, und rechnet die Spanne auf der Tiefe an der Quote. Beides nuetzt der
Oberflaeche nur, wenn der Endpunkt es auch abruft und mitliefert. Netzfrei:
beide Marktabrufe und beide Buecher sind hier gesetzt.
"""

from __future__ import annotations

import unittest
from unittest import mock

import pandas as pd

from api import server
from app import cross_pairs


def _markt(title, key, bid, ask, *, platform, category="Crypto", volume=100000.0,
           token="", end="2026-12-31T12:00:00Z"):
    return {
        "platform": platform, "title": title, "market_key": key, "id": key,
        "ticker": key, "yes_price": round((bid + ask) / 2, 6),
        "best_bid": bid, "best_ask": ask, "volume": volume, "volume_24h": volume,
        "activity_volume": volume, "category": category, "url": "",
        "yes_token_id": token, "end_time": pd.Timestamp(end),
    }


def _polymarket():
    return pd.DataFrame([
        _markt("Will Bitcoin be above $120,000 on December 31, 2026?", "0xbtc",
               0.61, 0.63, platform="Polymarket", token="TOK-BTC"),
        _markt("Will the Fed cut rates at the September 2026 meeting?", "0xfed",
               0.61, 0.63, platform="Polymarket", category="Economics",
               token="TOK-FED", end="2026-09-17T18:00:00Z"),
    ])


def _kalshi():
    return pd.DataFrame([
        # Die Umkehrung: teilt jedes Wort ausser above/below.
        _markt("Will Bitcoin be below $120,000 on December 31, 2026?", "KXBTC",
               0.36, 0.38, platform="Kalshi"),
        _markt("Fed cuts rates at the September 2026 meeting?", "KXFED",
               0.67, 0.69, platform="Kalshi", category="Economics",
               end="2026-09-17T22:00:00Z"),
    ])


def _book(bid_price, bid_size, ask_price, ask_size):
    bids = pd.DataFrame([{"price": bid_price, "size": bid_size}]) if bid_price else pd.DataFrame()
    asks = pd.DataFrame([{"price": ask_price, "size": ask_size}]) if ask_price else pd.DataFrame()
    return bids, asks


class CrossEndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        server._CACHE.clear()

    def _cross(self, pm_book=None, ks_book=None):
        def _pm_markets(limit=250, offset=0, **kwargs):
            return _polymarket() if offset == 0 else pd.DataFrame()

        pm_book = pm_book or (lambda token: _book(0.61, 500.0, 0.63, 500.0))
        ks_book = ks_book or (lambda ticker: _book(0.67, 500.0, 0.69, 500.0))
        with mock.patch.object(server.md, "get_polymarket_markets", side_effect=_pm_markets), \
             mock.patch.object(server.md, "get_kalshi_markets_deep", return_value=_kalshi()), \
             mock.patch.object(server.md, "get_polymarket_orderbook", side_effect=pm_book), \
             mock.patch.object(server.md, "get_kalshi_orderbook", side_effect=ks_book):
            # Direkt aufgerufen, ohne FastAPI: die Query-Vorgaben sind hier
            # noch Query-Objekte und muessen benannt werden.
            return server.cross(query="", min_similarity=0.5, max_pairs=150)

    def test_the_inverted_pair_is_counted_and_never_priced(self) -> None:
        payload = self._cross()
        titel = [row["event"] for row in payload["rows"]]
        self.assertNotIn("Will Bitcoin be above $120,000 on December 31, 2026?", titel)
        suppressed = payload["suppressed"]
        self.assertEqual(suppressed["total"], 1)
        self.assertEqual(suppressed["by_verdict"][cross_pairs.PAIR_OPPOSED], 1)
        self.assertIn("above against below", suppressed["examples"][0]["why"])
        # Ein verworfenes Paar traegt keine Zahl, auch nicht in seinem
        # Beispielblock: zwischen zwei Fragen ist die Luecke keine Aussage.
        self.assertNotIn("net", suppressed["examples"][0])

    def test_the_surviving_pair_carries_the_size_it_was_measured_at(self) -> None:
        payload = self._cross(ks_book=lambda ticker: _book(0.67, 3.0, 0.69, 400.0))
        row = next(r for r in payload["rows"] if r["event"].startswith("Will the Fed"))
        self.assertTrue(row["depthChecked"])
        self.assertEqual(row["size"], 3.0)
        self.assertIsNotNone(row["net"])

    def test_an_empty_book_leaves_no_number_at_all(self) -> None:
        payload = self._cross(ks_book=lambda ticker: (pd.DataFrame(), pd.DataFrame()))
        row = next(r for r in payload["rows"] if r["event"].startswith("Will the Fed"))
        self.assertTrue(row["depthChecked"])
        self.assertEqual(row["size"], 0.0)
        self.assertIsNone(row["net"])
        self.assertIsNone(row["gross"])

    def test_without_a_reachable_book_the_row_says_the_size_is_unmeasured(self) -> None:
        def _kaputt(_key):
            raise RuntimeError("book endpoint down")

        payload = self._cross(pm_book=_kaputt, ks_book=_kaputt)
        row = next(r for r in payload["rows"] if r["event"].startswith("Will the Fed"))
        self.assertFalse(row["depthChecked"])
        self.assertEqual(row["size"], 100.0)
        self.assertIsNotNone(row["net"])

    def test_the_payload_names_how_many_rows_are_re_quoted(self) -> None:
        payload = self._cross()
        self.assertEqual(payload["depth_rows"], server.CROSS_DEPTH_ROWS)
        self.assertIn("suppressed", payload["note"])


if __name__ == "__main__":
    unittest.main()
