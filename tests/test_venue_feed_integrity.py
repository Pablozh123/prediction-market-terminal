"""Ein umbenanntes Feld darf nicht als halbes Tape durchgehen.

Der Ausfall, um den es geht, kommt ohne Netzfehler: die Venue antwortet mit
200 und wohlgeformtem JSON, nur heisst eine Spalte anders. Fuer den Kalshi-
Pfad hiess das bisher zweierlei, je nachdem welches Feld wegfiel:

* ``count_fp`` oder ``yes_price_dollars`` weg: ``df.get(name, 0)`` gibt einen
  Skalar zurueck, ``pd.to_numeric(0).fillna(...)`` wirft einen AttributeError
  ("'int' object has no attribute 'fillna'"). Der landet in
  ``api/server.py::load_tape`` in einem ``except Exception`` und wird zu einer
  Zeile auf stdout. Die Antwort traegt danach nur noch Polymarket, und die
  Kopfzeile der Seite sagt weiter "LIVE, POLYMARKET + KALSHI".
* ``ticker`` weg: gar kein Fehler. Jede Zeile bekommt den Vorgabewert "",
  also market_key "", also eine URL, die auf die Marktliste zeigt. Zwanzig
  Prints, alle im selben leeren Markt. Das ist der stillere und schlimmere
  Fall.

Die Haltung aus PR #124 gilt hier genauso: ein geschluckter Fehler ist
schlimmer als ein sichtbarer. Ein Feld, an dem eine Zahl oder eine Identitaet
haengt, muss also laut fehlen, und wo trotzdem eine Venue ausfaellt, muss die
Antwort das mitfuehren, statt die Luecke als Datenlage auszugeben.

Getestet wird gegen tests/market_api_fixtures.py, also ohne Netz und
deterministisch.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

import pandas as pd

from src import prediction_markets as md
from tests.market_api_fixtures import offline_market_apis, renamed_field


class KalshiTradeFeedFieldTests(unittest.TestCase):
    """Der Kalshi-Trade-Feed: jedes tragende Feld faellt laut aus."""

    def test_the_fixture_tape_is_intact_to_begin_with(self) -> None:
        with offline_market_apis():
            tape = md.get_kalshi_trades(limit=20)
        self.assertEqual(len(tape), 20)
        # Das Zahlenbeispiel, gegen das die Ausfaelle unten gemessen werden:
        # 20 Prints, zusammen 53.280 Dollar Notional, zwei echte Ticker.
        self.assertAlmostEqual(float(tape["notional"].sum()), 53_280.0, places=2)
        self.assertEqual(sorted(set(tape["ticker"].astype(str))), ["KXPRES-26-DEM", "KXPRES-26-REP"])

    def test_a_renamed_size_field_fails_loudly_instead_of_as_an_attributeerror(self) -> None:
        with offline_market_apis(), renamed_field("kalshi_trades", "count_fp", "contract_count"):
            with self.assertRaises(md.MarketDataError) as gefangen:
                md.get_kalshi_trades(limit=20)
        self.assertIn("count_fp", str(gefangen.exception))

    def test_a_renamed_price_field_fails_loudly(self) -> None:
        with offline_market_apis(), renamed_field("kalshi_trades", "yes_price_dollars", "yes_px"):
            with self.assertRaises(md.MarketDataError) as gefangen:
                md.get_kalshi_trades(limit=20)
        self.assertIn("yes_price_dollars", str(gefangen.exception))

    def test_a_renamed_ticker_fails_instead_of_emptying_every_market_key(self) -> None:
        # Vorher: 20 Zeilen, market_key "" auf allen. Keine Ausnahme, keine
        # Warnung, und jede Gruppierung ueber market_key sah einen Markt.
        with offline_market_apis(), renamed_field("kalshi_trades", "ticker", "market_ticker"):
            with self.assertRaises(md.MarketDataError) as gefangen:
                md.get_kalshi_trades(limit=20)
        self.assertIn("ticker", str(gefangen.exception))

    def test_a_renamed_time_field_fails_instead_of_a_column_of_nat(self) -> None:
        with offline_market_apis(), renamed_field("kalshi_trades", "created_time", "ts"):
            with self.assertRaises(md.MarketDataError) as gefangen:
                md.get_kalshi_trades(limit=20)
        self.assertIn("created_time", str(gefangen.exception))

    def test_a_renamed_side_fails_instead_of_a_column_of_empty_strings(self) -> None:
        with offline_market_apis(), renamed_field("kalshi_trades", "taker_side", "side"):
            with self.assertRaises(md.MarketDataError):
                md.get_kalshi_trades(limit=20)

    def test_the_cent_form_of_the_price_is_read_and_not_booked_as_zero(self) -> None:
        # Kalshi fuehrt jeden Betrag zweimal: ``yes_price_dollars`` und die
        # dokumentierte Cent-Form ``yes_price``. get_kalshi_orderbook las
        # frueher nur die Dollarform und gab ein Buch in Cents als leer
        # zurueck; derselbe Fehler stand im Trade-Feed und buchte jeden
        # Print zu 0 Dollar. Bei min_cash 2500 verschwindet damit die halbe
        # Seite, ohne dass irgendetwas scheitert.
        raw = {"trades": [
            {"ticker": "KXFED-26SEP", "created_time": "2026-06-10T12:00:00Z", "taker_side": "yes",
             "taker_outcome_side": "yes", "yes_price": 45, "count_fp": 1000.0},
        ]}
        with patch("src.prediction_markets._get_json", return_value=raw):
            trades = md.get_kalshi_trades()
        self.assertAlmostEqual(float(trades["price"].iloc[0]), 0.45)
        self.assertAlmostEqual(float(trades["notional"].iloc[0]), 450.0)

    def test_the_contract_count_stays_a_count(self) -> None:
        # Einheiten aus PR #110 bleiben, wie sie sind: size zaehlt Kontrakte,
        # notional ist size mal Preis und damit erst Dollar.
        with offline_market_apis():
            tape = md.get_kalshi_trades(limit=20)
        zeile = tape.iloc[0]
        self.assertAlmostEqual(float(zeile["notional"]), float(zeile["size"]) * float(zeile["price"]))


class PolymarketTradeFeedFieldTests(unittest.TestCase):
    """Derselbe Wachposten auf der anderen Haelfte des Tapes."""

    def test_the_fixture_tape_is_intact_to_begin_with(self) -> None:
        with offline_market_apis():
            tape = md.get_polymarket_trades(limit=50)
        self.assertFalse(tape.empty)
        self.assertEqual(len(set(tape["market_key"].astype(str))), 3)

    def test_a_renamed_condition_id_fails_instead_of_collapsing_every_market(self) -> None:
        # Vorher: market_key "" auf jeder Zeile, also ein einziger Markt fuer
        # jede Gruppierung, jeden Risk-Score und jede Event-Karte.
        with offline_market_apis(), renamed_field("polymarket_trades", "conditionId", "condition_id"):
            with self.assertRaises(md.MarketDataError) as gefangen:
                md.get_polymarket_trades(limit=50)
        self.assertIn("conditionId", str(gefangen.exception))

    def test_a_renamed_wallet_fails_instead_of_one_anonymous_trader(self) -> None:
        with offline_market_apis(), renamed_field("polymarket_trades", "proxyWallet", "wallet"):
            with self.assertRaises(md.MarketDataError) as gefangen:
                md.get_polymarket_trades(limit=50)
        self.assertIn("proxyWallet", str(gefangen.exception))

    def test_a_renamed_timestamp_fails_as_a_marketdataerror_not_a_keyerror(self) -> None:
        with offline_market_apis(), renamed_field("polymarket_trades", "timestamp", "ts"):
            with self.assertRaises(md.MarketDataError) as gefangen:
                md.get_polymarket_trades(limit=50)
        self.assertIn("timestamp", str(gefangen.exception))

    def test_a_renamed_size_fails_loudly(self) -> None:
        with offline_market_apis(), renamed_field("polymarket_trades", "size", "shares"):
            with self.assertRaises(md.MarketDataError) as gefangen:
                md.get_polymarket_trades(limit=50)
        self.assertIn("size", str(gefangen.exception))


class KalshiMarketFeedFieldTests(unittest.TestCase):
    def test_a_renamed_ticker_fails_instead_of_markets_without_a_key(self) -> None:
        with offline_market_apis(), renamed_field("kalshi_markets", "ticker", "market_ticker"):
            with self.assertRaises(md.MarketDataError) as gefangen:
                md.get_kalshi_markets(limit=10)
        self.assertIn("ticker", str(gefangen.exception))

    def test_an_empty_answer_is_not_a_field_error(self) -> None:
        # Kein Markt ist kein Schema-Bruch: die Ticker-Abfrage einer Wallet
        # ohne Treffer muss weiter leer zurueckkommen, nicht werfen.
        with patch("src.prediction_markets._get_json", return_value={"markets": []}):
            self.assertTrue(md.get_kalshi_markets(limit=10).empty)
        with patch("src.prediction_markets._get_json", return_value={"trades": []}):
            self.assertTrue(md.get_kalshi_trades(limit=10).empty)


class TapeVenueStatusTests(unittest.TestCase):
    """Faellt eine Venue aus, sagt die Antwort das, statt LIVE zu behaupten."""

    def setUp(self) -> None:
        from api import server

        server._CACHE.clear()
        self.server = server

    def tearDown(self) -> None:
        self.server._CACHE.clear()

    def test_both_venues_report_ok_on_fixtures(self) -> None:
        with offline_market_apis():
            payload = self.server.tape(limit=40, min_cash=0.0)
        quellen = {row["venue"]: row for row in payload["sources"]}
        self.assertEqual(sorted(quellen), ["Kalshi", "Polymarket"])
        self.assertTrue(all(row["ok"] for row in quellen.values()))
        self.assertTrue(all(row["rows"] > 0 for row in quellen.values()))

    def test_a_broken_kalshi_feed_is_reported_and_not_swallowed(self) -> None:
        with offline_market_apis(), renamed_field("kalshi_trades", "count_fp", "contract_count"):
            payload = self.server.tape(limit=40, min_cash=0.0)
        quellen = {row["venue"]: row for row in payload["sources"]}
        self.assertFalse(quellen["Kalshi"]["ok"])
        self.assertIn("count_fp", quellen["Kalshi"]["error"])
        self.assertTrue(quellen["Polymarket"]["ok"])
        # Die Zeilen der anderen Venue bleiben stehen: eine halbe Antwort ist
        # brauchbar, sobald sie sich als halb zu erkennen gibt.
        self.assertTrue(payload["rows"])
        self.assertEqual({str(row["platform"]) for row in payload["rows"]}, {"Polymarket"})

    def test_the_market_universe_reports_the_same_way(self) -> None:
        with offline_market_apis(), renamed_field("kalshi_markets", "ticker", "market_ticker"):
            payload = self.server.markets(limit=250)
        quellen = {row["venue"]: row for row in payload["sources"]}
        self.assertFalse(quellen["Kalshi"]["ok"])
        self.assertTrue(quellen["Polymarket"]["ok"])


class VenueSourceHelperTests(unittest.TestCase):
    def test_missing_venues_are_named(self) -> None:
        from app import api_views as apv

        quellen = [
            {"venue": "Polymarket", "ok": True, "rows": 24, "error": ""},
            {"venue": "Kalshi", "ok": False, "rows": 0, "error": "boom"},
        ]
        self.assertEqual(apv.missing_venues(quellen), ["Kalshi"])
        self.assertEqual(apv.missing_venues([]), [])

    def test_the_status_travels_on_the_frame(self) -> None:
        from app import api_views as apv

        frame = apv.with_venue_sources(pd.DataFrame({"a": [1]}), [{"venue": "Kalshi", "ok": False, "rows": 0, "error": "x"}])
        self.assertEqual(apv.venue_sources(frame)[0]["venue"], "Kalshi")
        # Ein Frame ohne Vermerk liefert eine leere Liste, keinen Fehler.
        self.assertEqual(apv.venue_sources(pd.DataFrame()), [])
        self.assertEqual(apv.venue_sources(None), [])


if __name__ == "__main__":
    unittest.main()
