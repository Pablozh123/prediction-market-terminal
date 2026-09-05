"""Die gemeinsame Spezifikation des Paar-Screens, Stufe 1 des Paar-Protokolls.

tests/fixtures/pair_screen_cases.json ist eine Kopie von
config/pair_screen_cases.json im Scanner-Repo (prediction-alpha-bot). Beide
Matcher, app/cross_pairs.py hier und crossVenueQuestionMatch.ts dort, muessen
jeden Fall auf dasselbe Urteil bringen. Ein Fall, der hier besteht und dort
nicht, oder umgekehrt, ist ein Fehler in einer der beiden Implementierungen
und keine Geschmacksfrage.

Das Vokabular der Datei ist neutral; dieser Test bildet die Urteile von
``pair_verdict`` darauf ab.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from app import cross_pairs

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "pair_screen_cases.json"

#: Urteil von ``pair_verdict`` -> Vokabular der Spezifikation.
NEUTRAL = {
    cross_pairs.PAIR_UNVERIFIED: "passed",
    cross_pairs.PAIR_OPPOSED: "inverted",
    cross_pairs.PAIR_DIFFERENT: "different_question",
    cross_pairs.PAIR_COMPOUND: "compound_market",
    cross_pairs.PAIR_TIME: "resolution_time_mismatch",
}


def _load() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class PairScreenCasesTest(unittest.TestCase):
    def test_the_file_is_the_shared_specification(self) -> None:
        daten = _load()
        self.assertEqual(daten["schema"], "pair_screen_cases/1")
        self.assertEqual(daten["vocabulary"],
                         ["passed", "inverted", "different_question",
                          "compound_market", "resolution_time_mismatch"])
        self.assertEqual(daten["resolution_gap_tolerance_days"],
                         cross_pairs.MAX_RESOLUTION_GAP_DAYS)
        self.assertGreaterEqual(len(daten["cases"]), 15)
        ids = [fall["id"] for fall in daten["cases"]]
        self.assertEqual(len(ids), len(set(ids)))
        # Jedes Urteil, das der Matcher kennt, hat ein Wort in der Datei.
        self.assertEqual(set(NEUTRAL.values()), set(daten["vocabulary"]))

    def test_every_case_reaches_the_expected_verdict(self) -> None:
        daten = _load()
        for fall in daten["cases"]:
            with self.subTest(fall=fall["id"]):
                pm = {"title": fall["polymarket"]["title"],
                      "end": fall["polymarket"].get("end")}
                ks = {"title": fall["kalshi"]["title"],
                      "ticker": fall["kalshi"].get("ticker"),
                      "end": fall["kalshi"].get("end")}
                urteil = cross_pairs.pair_verdict(
                    pm, ks, max_resolution_gap_days=daten["resolution_gap_tolerance_days"])
                self.assertEqual(
                    NEUTRAL[urteil["verdict"]], fall["expected"],
                    f"{fall['id']} ({fall['source']}): {'; '.join(urteil['reasons'])}")


if __name__ == "__main__":
    unittest.main()
