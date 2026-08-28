"""Die Einheit der Volumenfelder, festgenagelt an einem echten Payload.

Die Fixtures unten sind ein woertlicher Ausschnitt der oeffentlichen
Kalshi-Antworten vom 2026-08-28 (Markt- und Trade-Endpunkt, kein Login, keine
Zugangsdaten). Sie liegen hier, damit der Test ohne Netz laeuft und damit die
Frage "Dollar oder Stueck?" nicht ein drittes Mal aufgemacht wird.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from app import venue_units as vu
from src import prediction_markets as md

#: Woertlicher Ausschnitt aus GET /trade-api/v2/markets/KXWTAMATCH-26AUG27VIDBAR-BAR
#: (oeffentlich, 2026-08-28). Gekuerzt um Regeltexte und Zeitstempel, sonst
#: unveraendert. Beachte die Suffixe: Preise und Liquiditaet tragen _dollars,
#: Volumen, Open Interest und Ordergroessen tragen _fp.
KALSHI_MARKET_PAYLOAD = {
    "ticker": "KXWTAMATCH-26AUG27VIDBAR-BAR",
    "event_ticker": "KXWTAMATCH-26AUG27VIDBAR",
    "title": "Nikola Bartunkova wins",
    "yes_sub_title": "Nikola Bartunkova",
    "market_type": "binary",
    "status": "active",
    "last_price_dollars": "0.6400",
    "liquidity_dollars": "0.0000",
    "no_ask_dollars": "0.3700",
    "no_bid_dollars": "0.3600",
    "notional_value_dollars": "1.0000",
    "open_interest_fp": "562817.82",
    "previous_price_dollars": "0.4500",
    "volume_24h_fp": "800514.92",
    "volume_fp": "896792.27",
    "yes_ask_dollars": "0.6400",
    "yes_ask_size_fp": "77880.52",
    "yes_bid_dollars": "0.6300",
    "yes_bid_size_fp": "6582.06",
}

#: Die Gegenprobe in klein. Ueber alle 4399 Trades dieses Marktes ergab
#: sum(count_fp) exakt 896792.27, also genau volume_fp, waehrend
#: sum(count_fp * Preis) bei 636041.30 lag. Die vier Zeilen hier haben die
#: Form der echten Antwort und dieselbe Eigenschaft im Kleinen.
KALSHI_TRADES_PAYLOAD = {
    "trades": [
        {"ticker": "KXWTAMATCH-26AUG27VIDBAR-BAR", "count_fp": "100.00",
         "yes_price_dollars": "0.6300", "no_price_dollars": "0.3700",
         "taker_side": "yes", "taker_outcome_side": "yes",
         "created_time": "2026-08-27T22:26:20.084176Z", "trade_id": "t1"},
        {"ticker": "KXWTAMATCH-26AUG27VIDBAR-BAR", "count_fp": "250.00",
         "yes_price_dollars": "0.6400", "no_price_dollars": "0.3600",
         "taker_side": "yes", "taker_outcome_side": "yes",
         "created_time": "2026-08-27T22:26:21.084176Z", "trade_id": "t2"},
        {"ticker": "KXWTAMATCH-26AUG27VIDBAR-BAR", "count_fp": "50.00",
         "yes_price_dollars": "0.6200", "no_price_dollars": "0.3800",
         "taker_side": "no", "taker_outcome_side": "no",
         "created_time": "2026-08-27T22:26:22.084176Z", "trade_id": "t3"},
        {"ticker": "KXWTAMATCH-26AUG27VIDBAR-BAR", "count_fp": "600.00",
         "yes_price_dollars": "0.6500", "no_price_dollars": "0.3500",
         "taker_side": "yes", "taker_outcome_side": "yes",
         "created_time": "2026-08-27T22:26:23.084176Z", "trade_id": "t4"},
    ]
}

#: Die Stueckzahl, die der Markt melden wuerde, wenn er nur aus den vier
#: Trades oben bestuende.
FIXTURE_CONTRACTS = 1000.0

#: Was in denselben vier Trades tatsaechlich an Dollar umgesetzt wurde:
#: 100*0.63 + 250*0.64 + 50*0.38 + 600*0.65 = 632.0. Der NO-Nehmer zahlt
#: 1 - yes, deshalb 0.38 und nicht 0.62.
FIXTURE_USD = 632.0


class PayloadShapeTests(unittest.TestCase):
    """Was im echten Payload steht, und was eben nicht drinsteht."""

    def test_dollar_fields_carry_the_dollars_suffix(self) -> None:
        dollar_felder = [k for k in KALSHI_MARKET_PAYLOAD if k.endswith("_dollars")]
        self.assertIn("liquidity_dollars", dollar_felder)
        self.assertIn("yes_bid_dollars", dollar_felder)
        self.assertIn("notional_value_dollars", dollar_felder)

    def test_there_is_no_volume_in_dollars_field(self) -> None:
        # Der frueher hier stehende Rueckfall auf volume_dollars griff nach
        # einem Feld, das die API auf keinem Host liefert.
        self.assertNotIn("volume_dollars", KALSHI_MARKET_PAYLOAD)
        self.assertNotIn("volume_24h_dollars", KALSHI_MARKET_PAYLOAD)
        self.assertNotIn("volume", KALSHI_MARKET_PAYLOAD)

    def test_volume_and_sizes_carry_the_fp_suffix(self) -> None:
        for feld in ("volume_fp", "volume_24h_fp", "open_interest_fp",
                     "yes_bid_size_fp", "yes_ask_size_fp"):
            self.assertIn(feld, KALSHI_MARKET_PAYLOAD)

    def test_one_contract_settles_for_one_dollar(self) -> None:
        self.assertEqual(float(KALSHI_MARKET_PAYLOAD["notional_value_dollars"]),
                         vu.KALSHI_CONTRACT_NOTIONAL_USD)


class TradeArithmeticTests(unittest.TestCase):
    """Die Gegenprobe: das Volumenfeld ist die Stueckzahl, nicht der Umsatz."""

    def test_volume_field_matches_the_sum_of_counts(self) -> None:
        stueck = sum(float(t["count_fp"]) for t in KALSHI_TRADES_PAYLOAD["trades"])
        self.assertAlmostEqual(stueck, FIXTURE_CONTRACTS, places=2)

    def test_volume_field_does_not_match_the_dollar_notional(self) -> None:
        with patch("src.prediction_markets._get_json",
                   return_value=KALSHI_TRADES_PAYLOAD):
            tape = md.get_kalshi_trades(ticker="KXWTAMATCH-26AUG27VIDBAR-BAR")
        umsatz = float(tape["notional"].sum())
        self.assertAlmostEqual(umsatz, FIXTURE_USD, places=2)
        self.assertNotAlmostEqual(umsatz, FIXTURE_CONTRACTS, places=2)

    def test_contract_count_overstates_dollars_by_one_over_price(self) -> None:
        # Der Kern des Fehlers: bei 50 Cent ist der Faktor 2, bei 40 Cent 2.5.
        mittlerer_preis = FIXTURE_USD / FIXTURE_CONTRACTS
        self.assertAlmostEqual(FIXTURE_CONTRACTS / FIXTURE_USD,
                               1.0 / mittlerer_preis, places=6)


class NormalizedFrameTests(unittest.TestCase):
    """Was ``get_kalshi_markets`` aus dem echten Payload macht."""

    def _frame(self):
        with patch("src.prediction_markets._get_json",
                   return_value={"markets": [KALSHI_MARKET_PAYLOAD]}):
            return md.get_kalshi_markets()

    def test_volume_columns_carry_the_contract_count(self) -> None:
        row = self._frame().iloc[0]
        self.assertAlmostEqual(float(row["volume"]), 896792.27, places=2)
        self.assertAlmostEqual(float(row["volume_24h"]), 800514.92, places=2)
        self.assertAlmostEqual(float(row["open_interest"]), 562817.82, places=2)

    def test_frame_declares_the_unit_it_is_in(self) -> None:
        row = self._frame().iloc[0]
        self.assertEqual(row["volume_unit"], vu.CONTRACTS)

    def test_polymarket_frame_declares_dollars(self) -> None:
        payload = [{
            "conditionId": "0xabc", "question": "Will it?", "slug": "will-it",
            "outcomePrices": '["0.55", "0.45"]', "outcomes": '["Yes", "No"]',
            "volumeNum": 1234.0, "volume24hr": 500.0, "liquidityNum": 100.0,
            "clobTokenIds": '["1", "2"]',
        }]
        with patch("src.prediction_markets._get_json", return_value=payload):
            frame = md.get_polymarket_markets()
        self.assertEqual(frame.iloc[0]["volume_unit"], vu.USD)


class UnitRegistryTests(unittest.TestCase):
    def test_each_venue_reports_its_own_unit(self) -> None:
        self.assertEqual(vu.volume_unit("Polymarket"), vu.USD)
        self.assertEqual(vu.volume_unit("Kalshi"), vu.CONTRACTS)
        self.assertEqual(vu.volume_unit("kalshi"), vu.CONTRACTS)

    def test_an_unknown_venue_gets_no_guessed_unit(self) -> None:
        self.assertEqual(vu.volume_unit("Betfair"), vu.UNKNOWN)
        self.assertEqual(vu.volume_unit(None), vu.UNKNOWN)
        self.assertFalse(vu.is_usd("Betfair"))


class FormatVolumeTests(unittest.TestCase):
    def test_dollars_get_a_dollar_sign(self) -> None:
        self.assertEqual(vu.format_volume(1_234_567, "Polymarket"), "$1.23m")

    def test_contracts_get_the_word_instead(self) -> None:
        self.assertEqual(vu.format_volume(896792.27, "Kalshi"),
                         "896,792 contracts")
        self.assertNotIn("$", vu.format_volume(896792.27, "Kalshi"))

    def test_missing_stays_a_dash(self) -> None:
        self.assertEqual(vu.format_volume(None, "Kalshi"), "-")
        self.assertEqual(vu.format_volume("keine Zahl", "Polymarket"), "-")

    def test_unknown_venue_gets_the_bare_number(self) -> None:
        self.assertEqual(vu.format_volume(2500, "Betfair"), "2,500")


class CombinedVolumeTests(unittest.TestCase):
    def test_same_unit_adds_up(self) -> None:
        ergebnis = vu.combined_volume([
            {"platform": "Polymarket", "volume": 1000.0},
            {"platform": "Polymarket", "volume": 250.0},
        ])
        self.assertEqual(ergebnis["total"], 1250.0)
        self.assertEqual(ergebnis["unit"], vu.USD)
        self.assertFalse(ergebnis["mixed"])

    def test_dollars_plus_contracts_refuses_to_be_one_number(self) -> None:
        # Genau die Summe, die in der Cross-Venue-Tabelle stand.
        ergebnis = vu.combined_volume([
            {"platform": "Polymarket", "volume": 1_000_000.0},
            {"platform": "Kalshi", "volume": 4_157_305.0},
        ])
        self.assertIsNone(ergebnis["total"])
        self.assertTrue(ergebnis["mixed"])
        self.assertEqual(ergebnis["by_unit"][vu.USD], 1_000_000.0)
        self.assertEqual(ergebnis["by_unit"][vu.CONTRACTS], 4_157_305.0)

    def test_nothing_measurable_is_not_a_zero(self) -> None:
        ergebnis = vu.combined_volume([])
        self.assertIsNone(ergebnis["total"])
        self.assertFalse(ergebnis["mixed"])


class VolumeByUnitTests(unittest.TestCase):
    """Der Weg fuer Frames: zwei Spalten rein, eine Summe je Einheit raus."""

    def test_two_venues_stay_two_sums(self) -> None:
        je_einheit = vu.volume_by_unit(
            ["Polymarket", "Kalshi", "Polymarket", "Kalshi"],
            [1000.0, 4_157_305.0, 250.0, 896_792.0],
        )
        self.assertAlmostEqual(je_einheit[vu.USD], 1250.0)
        self.assertAlmostEqual(je_einheit[vu.CONTRACTS], 5_054_097.0)
        self.assertNotIn("total", je_einheit)

    def test_a_venue_without_rows_is_absent_not_zero(self) -> None:
        je_einheit = vu.volume_by_unit(["Polymarket"], [500.0])
        self.assertEqual(list(je_einheit), [vu.USD])
        # Der Aufrufer entscheidet, ob er dafuer 0 oder einen Strich zeigt.
        self.assertEqual(je_einheit.get(vu.CONTRACTS, 0.0), 0.0)

    def test_unparsable_rows_are_skipped(self) -> None:
        je_einheit = vu.volume_by_unit(
            ["Polymarket", "Polymarket", "Kalshi"],
            [100.0, None, "keine Zahl"],
        )
        self.assertEqual(je_einheit, {vu.USD: 100.0})

    def test_empty_input_is_an_empty_answer(self) -> None:
        self.assertEqual(vu.volume_by_unit([], []), {})


class ContractsToUsdTests(unittest.TestCase):
    def test_a_real_price_converts(self) -> None:
        self.assertAlmostEqual(vu.contracts_to_usd(1000, 0.632), 632.0, places=6)

    def test_no_price_means_no_number(self) -> None:
        self.assertIsNone(vu.contracts_to_usd(1000, None))
        self.assertIsNone(vu.contracts_to_usd(1000, 0.0))
        self.assertIsNone(vu.contracts_to_usd(1000, 1.4))

    def test_never_falls_back_to_the_contract_count(self) -> None:
        # Der Rueckfall auf die Stueckzahl war der Fehler; hier darf er nicht
        # durch die Hintertuer zurueckkommen.
        self.assertNotEqual(vu.contracts_to_usd(1000, None), 1000)


if __name__ == "__main__":
    unittest.main()
