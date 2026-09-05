"""Die Gebuehrentabelle existiert zweimal, einmal je Sprache.

tests/fixtures/fee_schedule_2026-07-30.json ist die Kopie von
config/fee_schedule_2026-07-30.json aus dem Scanner-Repo (prediction-alpha-bot).
Beide Repos pruefen ihre eigenen Konstanten gegen dieselbe Datei; ein Satz,
der an einer Stelle geaendert wird und an der anderen nicht, laesst einen Test
fallen, statt jede Netto-Zahl leise zu verschieben.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from app import venue_fees as vf

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "fee_schedule_2026-07-30.json"


class FeeScheduleParityTest(unittest.TestCase):
    def setUp(self) -> None:
        self.daten = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def test_the_file_matches_venue_fees(self) -> None:
        self.assertEqual(self.daten["schema"], "fee_schedule/1")
        self.assertEqual(self.daten["version"], vf.FEE_MODEL_VERSION)
        self.assertEqual(self.daten["polymarket"]["taker_rates_by_category"],
                         vf.POLYMARKET_TAKER_RATES)
        self.assertEqual(self.daten["polymarket"]["default_category"],
                         vf.POLYMARKET_DEFAULT_CATEGORY)
        self.assertEqual(self.daten["kalshi"]["taker_rate"], vf.KALSHI_TAKER_RATE)
        self.assertEqual(self.daten["kalshi"]["maker_rate"], vf.KALSHI_MAKER_RATE)
        self.assertEqual(self.daten["polymarket"]["maker_rate"], 0)
        self.assertEqual(vf.polymarket_maker_fee(100, 0.5), 0.0)

    def test_the_disputed_general_rate_is_the_one_the_band_carries(self) -> None:
        streit = self.daten["polymarket"]["general_rate_dispute"]
        self.assertEqual(streit["documented"], vf.POLYMARKET_DISPUTED_RATE)
        self.assertEqual(streit["secondary_sources"], vf.POLYMARKET_DISPUTED_RATE_LOW)
        self.assertEqual(streit["used"], "documented")
        band = vf.polymarket_rate_band("other")
        self.assertTrue(band["disputed"])
        self.assertEqual(band["rate"], streit["documented"])
        self.assertEqual(band["low"], streit["secondary_sources"])

    def test_the_sources_are_named_and_dated(self) -> None:
        for venue in ("polymarket", "kalshi"):
            self.assertIn("2026-07-30", self.daten["sources"][venue])
            self.assertIn("2026-07-30", vf.FEE_SOURCES[venue])


if __name__ == "__main__":
    unittest.main()
