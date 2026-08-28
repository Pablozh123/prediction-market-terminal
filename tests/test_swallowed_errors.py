"""Was passiert, wenn EIN Teil einer zerlegten Anfrage ausfaellt.

Fortsetzung von ``tests/test_venue_feed_integrity.py``. Dort ging es um das
umbenannte Feld, hier um den ausgefallenen Request: eine Anfrage, die in
zwanzig Ids je Batch oder in vier Seiten je 500 Prints zerlegt wird, und von
der einer der Teile nicht ankommt.

``continue`` bzw. ``break`` machen daraus eine kuerzere Liste, und eine
kuerzere Liste ist von einer vollstaendigen nicht zu unterscheiden. Die drei
Stellen, die diese Datei prueft, hatten drei verschiedene Folgen:

* **Batch-Nachschlagung** (``get_polymarket_markets_by_condition_ids``,
  ``..._by_event_slugs``): ein ausgefallener Batch von 20 conditionIds sah
  fuer den Aufrufer aus wie 20 Maerkte, die es nicht gibt. Der Backtester
  laesst deren Positionen dann "open at cost" stehen, bucht also einen
  gewonnenen Markt mit null Ergebnis und meldet einen zu niedrigen ROI.
* **Seitenschleife** (``paged_polymarket_trades``): die Stichprobe des
  Co-Trading-Netzes hing daran, auf welcher Seite der Fehler kam. Zwei
  Seiten statt vier heisst weniger geteilte Maerkte je Wallet-Paar, also
  weniger Cluster oberhalb der Schwelle, also weniger Syndikate auf einer
  Seite, die dabei aussieht wie eine ruhige Messung.
* **Kategorie-Anreicherung** (``/api/tape``): faellt das Marktuniversum aus,
  bekommt jede Zeile ihre Kategorie nur noch aus dem Titel. Das Ergebnis ist
  nicht leer, sondern anders, und die Kategorieleiste, der Kategoriefilter
  und "Where the money flows" zeigen eine Verteilung, die es so nicht gibt.

Alles gegen tests/market_api_fixtures.py, also ohne Netz.
"""

from __future__ import annotations

import unittest

import pandas as pd

from app import api_views as apv
from src import prediction_markets as md
from tests.market_api_fixtures import (
    CONDITION_IDS,
    SLUGS,
    failing_requests,
    offline_market_apis,
)


def _viele_ids(anzahl: int) -> list[str]:
    """``anzahl`` verschiedene conditionIds, die ersten davon echte."""

    weitere = ["0x" + f"{index:064x}" for index in range(anzahl)]
    return (CONDITION_IDS + weitere)[:anzahl]


class BatchNachschlagungTests(unittest.TestCase):
    """Ein gescheiterter Batch verschwindet nicht mehr aus dem Ergebnis."""

    def test_the_intact_fixture_answers_every_batch(self) -> None:
        # Die Ausgangslage, gegen die die Ausfaelle unten gemessen werden:
        # 45 Ids sind drei Batches, und jeder Batch liefert die drei
        # Fixture-Maerkte zurueck.
        with offline_market_apis():
            markets = md.get_polymarket_markets_by_condition_ids(_viele_ids(45))
        self.assertEqual(len(markets), 9)

    def test_a_failed_condition_id_batch_raises_instead_of_dropping_its_ids(self) -> None:
        # Batch 1 und 2 kommen an, Batch 3 nicht. Vorher: 6 Maerkte statt 9,
        # ohne Fehler, und der Aufrufer haelt die 15 Ids des dritten Batches
        # fuer Maerkte, die es nicht gibt.
        with offline_market_apis(), failing_requests("/markets", after=2):
            with self.assertRaises(md.MarketDataError) as gefangen:
                md.get_polymarket_markets_by_condition_ids(_viele_ids(45))
        text = str(gefangen.exception)
        self.assertIn("batch 3", text)
        self.assertIn("45 ids", text)

    def test_a_failed_event_slug_batch_raises_too(self) -> None:
        slugs = (SLUGS + [f"fixture-event-{index}" for index in range(45)])[:45]
        with offline_market_apis(), failing_requests("/events", after=1):
            with self.assertRaises(md.MarketDataError) as gefangen:
                md.get_polymarket_markets_by_event_slugs(slugs)
        self.assertIn("batch 2", str(gefangen.exception))

    def test_an_empty_but_successful_answer_is_still_allowed(self) -> None:
        # Der Unterschied, auf den es ankommt: nicht gefunden ist eine
        # Aussage, nicht gefragt nicht. Fuer Sport-Untermaerkte antwortet
        # Gamma regelmaessig leer, obwohl der Markt existiert, und genau
        # dafuer gibt es den Slug-Rueckweg. Das darf nicht abbrechen.
        with offline_market_apis():
            leer = md.get_polymarket_markets_by_condition_ids([])
        self.assertEqual(leer, [])

    def test_the_settlement_lookup_of_the_backtester_carries_the_failure_through(self) -> None:
        # Der Weg, auf dem der falsche ROI entstand: die Aufloesung sitzt in
        # market_category_frame bzw. im Backtester hinter derselben Funktion.
        with offline_market_apis(), failing_requests("/markets"):
            with self.assertRaises(md.MarketDataError):
                md.market_category_frame(_viele_ids(25))


class SeitenschleifeTests(unittest.TestCase):
    """Die Stichprobe sagt selbst, wie tief sie ist und ob sie abbrach."""

    def test_the_intact_fixture_reads_every_requested_page(self) -> None:
        with offline_market_apis():
            tape = md.paged_polymarket_trades(1000.0, pages=4, page_size=24)
        record = md.sample_coverage(tape)
        self.assertEqual(record["pages_read"], 4)
        self.assertEqual(record["rows"], 96)
        self.assertFalse(record["truncated_by_error"])
        note = md.sample_note(record)
        self.assertIn("$1,000", note)
        self.assertIn("4 of up to 4 pages", note)

    def test_a_failed_page_shortens_the_sample_and_says_so(self) -> None:
        # Zwei Seiten statt vier: die halbe Stichprobe. Vorher stand darunter
        # dieselbe Bildunterschrift wie ueber der ganzen.
        with offline_market_apis(), failing_requests("/trades", after=2):
            tape = md.paged_polymarket_trades(1000.0, pages=4, page_size=24)
        record = md.sample_coverage(tape)
        self.assertEqual(record["pages_read"], 2)
        self.assertEqual(record["rows"], 48)
        self.assertTrue(record["truncated_by_error"])
        note = md.sample_note(record)
        self.assertIn("2 of up to 4 pages", note)
        self.assertIn("stopped answering after page 2", note)

    def test_a_feed_that_simply_ends_is_not_reported_as_a_failure(self) -> None:
        # Eine kurze Seite beendet die Schleife genauso, ist aber keine
        # Stoerung. Die beiden duerfen nicht denselben Satz bekommen.
        with offline_market_apis():
            tape = md.paged_polymarket_trades(1000.0, pages=4, page_size=500)
        record = md.sample_coverage(tape)
        self.assertEqual(record["pages_read"], 1)
        self.assertFalse(record["truncated_by_error"])
        self.assertIn("The feed had nothing beyond that.", md.sample_note(record))

    def test_the_note_names_the_threshold_even_without_a_record(self) -> None:
        # Die Abrufschwelle ist ein Argument, kein Messergebnis: sie steht
        # auch dann in der Bildunterschrift, wenn der Vermerk unterwegs
        # verloren geht.
        self.assertIn("$1,000", md.sample_note({"min_cash": 1000.0}))
        self.assertEqual(md.sample_note({}), "")

    def test_a_venue_that_did_not_answer_is_named_in_the_note(self) -> None:
        note = md.sample_note({"min_cash": 1000.0, "venues_missing": ["Kalshi"]})
        self.assertIn("Kalshi did not answer", note)

    def test_the_first_page_failing_leaves_an_empty_frame_that_says_why(self) -> None:
        with offline_market_apis(), failing_requests("/trades"):
            tape = md.paged_polymarket_trades(1000.0, pages=4, page_size=24)
        self.assertTrue(tape.empty)
        record = md.sample_coverage(tape)
        self.assertEqual(record["pages_read"], 0)
        self.assertTrue(record["truncated_by_error"])


class KategorieHerkunftTests(unittest.TestCase):
    """Kategorien aus dem Titel statt aus dem Universum sind ein anderer Zustand."""

    def _universum(self) -> pd.DataFrame:
        frame = pd.DataFrame([
            {"market_key": CONDITION_IDS[0], "title": "Fixture", "category": "Politics",
             "filter_category": "Politics"},
        ])
        return apv.with_venue_sources(frame, [apv.venue_source("Polymarket", ok=True, rows=1),
                                              apv.venue_source("Kalshi", ok=True, rows=0)])

    def test_a_readable_universe_reports_ok_and_no_gap(self) -> None:
        record = apv.category_coverage(self._universum())
        self.assertTrue(record["ok"])
        self.assertEqual(record["markets"], 1)
        self.assertEqual(record["venues_missing"], [])

    def test_a_failed_universe_is_not_reported_as_an_empty_one(self) -> None:
        record = apv.category_coverage(pd.DataFrame(), error="MarketDataError: gamma down")
        self.assertFalse(record["ok"])
        self.assertIn("gamma down", record["error"])

    def test_a_venue_missing_from_the_universe_is_named(self) -> None:
        frame = apv.with_venue_sources(
            pd.DataFrame([{"market_key": CONDITION_IDS[0], "category": "Politics"}]),
            [apv.venue_source("Polymarket", ok=True, rows=1),
             apv.venue_source("Kalshi", ok=False, error="RequestException: timeout")],
        )
        self.assertEqual(apv.category_coverage(frame)["venues_missing"], ["Kalshi"])

    def test_the_wrong_output_the_missing_universe_produced(self) -> None:
        # Das Zahlenbeispiel: dieselben vier Prints, einmal mit und einmal
        # ohne Nachschlagetabelle. Ohne sie faellt der Politik-Print auf die
        # Titel-Heuristik zurueck; das Ergebnis ist eine andere Verteilung,
        # kein leeres Feld, und genau deshalb faellt es niemandem auf.
        prints = pd.DataFrame([
            {"platform": "Polymarket", "market_key": CONDITION_IDS[0], "title": "Quarterly filing beat",
             "slug": "", "ticker": ""},
        ])
        mit = apv.tape_rows_with_category(prints, self._universum(), lambda raw, title: raw)
        ohne = apv.tape_rows_with_category(prints, pd.DataFrame(), lambda raw, title: raw)
        self.assertEqual(list(mit["category"]), ["Politics"])
        self.assertNotEqual(list(ohne["category"]), ["Politics"])


class TapeEndpointTests(unittest.TestCase):
    """``/api/tape`` sagt, woher die Kategorie jeder Zeile kam."""

    def setUp(self) -> None:
        from api import server

        server._CACHE.clear()
        self.server = server

    def tearDown(self) -> None:
        self.server._CACHE.clear()

    def test_the_answer_carries_the_category_source(self) -> None:
        with offline_market_apis():
            payload = self.server.tape(limit=40, min_cash=0.0)
        self.assertIn("categories", payload)
        self.assertTrue(payload["categories"]["ok"])
        self.assertGreater(payload["categories"]["markets"], 0)

    def test_a_failed_universe_is_named_instead_of_printed(self) -> None:
        # Vorher: eine Zeile auf stdout, danach jede Kategorie aus dem Titel.
        # Die Zeilen bleiben stehen, aber die Antwort gibt zu, dass ihre
        # Kategoriespalte aus einer anderen Quelle stammt als sonst.
        from unittest.mock import patch

        with offline_market_apis():
            with patch.object(self.server, "load_universe", side_effect=RuntimeError("gamma down")):
                payload = self.server.tape(limit=40, min_cash=0.0)
        self.assertTrue(payload["rows"])
        self.assertFalse(payload["categories"]["ok"])
        self.assertIn("gamma down", payload["categories"]["error"])


class DeepTapeTests(unittest.TestCase):
    """Der tiefe Tape des Risk-Screens fuehrt seinen Abbruch mit.

    Der Satz, den die Seite ohne diesen Vermerk schrieb, lautete: "No
    co-trading cluster in the current window. That is a result, not a gap."
    Er stimmt, solange das Fenster steht. Bricht die Seitenschleife nach
    einer von acht Seiten ab, ist die leere Flaeche genau die Luecke, die
    der Satz bestreitet.
    """

    def setUp(self) -> None:
        from api import server

        server._CACHE.clear()
        self.server = server

    def tearDown(self) -> None:
        self.server._CACHE.clear()

    def test_the_deep_tape_records_a_truncated_page_loop(self) -> None:
        # Die Fixtures liefern eine kurze Seite, der Server fragt 1000 je
        # Seite: die Schleife endet regulaer nach der ersten. Der Ausfall
        # muss also die erste treffen, damit ueberhaupt einer eintritt.
        with offline_market_apis(), failing_requests("/trades"):
            tape = self.server.load_deep_tape(seiten=8, min_cash=1000.0)
        record = md.sample_coverage(tape)
        self.assertTrue(tape.empty)
        self.assertTrue(record["truncated_by_error"])
        self.assertEqual(record["pages_read"], 0)
        self.assertIn("stopped answering after page 0", md.sample_note(record))

    def test_the_risk_payload_names_the_truncation_next_to_the_empty_graph(self) -> None:
        # Der Weg bis auf die Seite: ohne dieses Feld steht dort "No
        # co-trading cluster in the current window. That is a result, not a
        # gap", waehrend der Tape auf halber Strecke abgebrochen ist. Der
        # Screen-Tape und der tiefe Tape lesen denselben Endpunkt, deshalb
        # bricht hier nur der tiefe ab.
        from unittest.mock import patch

        with offline_market_apis():
            with patch.object(self.server, "load_deep_tape", side_effect=lambda *a, **k: self._abgebrochen()):
                payload = self.server.risk()
        self.assertIn("cluster_sample", payload)
        self.assertIn("stopped answering after page 2", payload["cluster_sample"]["note"])

    def _abgebrochen(self) -> pd.DataFrame:
        with offline_market_apis(), failing_requests("/trades", after=2):
            return md.paged_polymarket_trades(1000.0, pages=8, page_size=24)

    def test_an_intact_run_records_no_truncation(self) -> None:
        with offline_market_apis():
            tape = self.server.load_deep_tape(seiten=8, min_cash=1000.0)
        self.assertFalse(md.sample_coverage(tape)["truncated_by_error"])


if __name__ == "__main__":
    unittest.main()
