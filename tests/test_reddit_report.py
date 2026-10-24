"""Die Reddit-Sentiment-Nutzlast: nachgerechnete Korrelationen gegen den
Bericht, Verdikt aus den Zahlen, keine erfundenen Werte."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from app import reddit_report as rr
from app import research_payload as rp

PROJEKT = Path(__file__).resolve().parents[1]


class KorrelationTests(unittest.TestCase):
    def test_pearson_und_spearman_von_hand(self) -> None:
        xs = [1.0, 2.0, 3.0, 4.0]
        ys = [2.0, 4.0, 6.0, 8.0]
        self.assertAlmostEqual(rp.pearson(xs, ys), 1.0)
        self.assertAlmostEqual(rp.spearman(xs, ys), 1.0)
        self.assertAlmostEqual(rp.spearman(xs, [8.0, 6.0, 4.0, 2.0]), -1.0)
        self.assertIsNone(rp.pearson([1.0, 2.0], [1.0, 2.0]))
        self.assertIsNone(rp.pearson([1.0, 1.0, 1.0], [1.0, 2.0, 3.0]))

    def test_raenge_mit_bindungen(self) -> None:
        self.assertEqual(rp.raenge([10.0, 20.0, 20.0, 30.0]), [1.0, 2.5, 2.5, 4.0])

    def test_richtung(self) -> None:
        zeilen = [
            {"probability": "0.7", "adjusted_weighted": "0.2", "stance_score": "0.1"},
            {"probability": "0.3", "adjusted_weighted": "0.2", "stance_score": "0.1"},
            {"probability": "0.2", "adjusted_weighted": "-0.4", "stance_score": "-0.2"},
        ]
        k = rr.korrelationen(zeilen)
        self.assertEqual(k["n"], 3)
        self.assertEqual(k["richtung_gleich"], 2)


class NutzlastTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.p = rr.build_payload(PROJEKT, jetzt=datetime(2026, 9, 4, tzinfo=timezone.utc))
        cls.s = cls.p["studie"]

    def test_artefakte_vorhanden(self) -> None:
        self.assertEqual(rr.fehlende_dateien(PROJEKT), [])
        self.assertEqual(self.p["fehlend"], [])
        self.assertEqual(self.p["stand_utc"], "2026-09-04T00:00:00+00:00")

    def test_nachgerechnet_gleich_bericht(self) -> None:
        # Der Bericht nennt r = +0.0791 und rho = +0.1508 auf 29 Maerkten;
        # die Nutzlast rechnet beides aus der Markttabelle nach.
        self.assertEqual(self.s["basis"]["maerkte"], 29)
        self.assertIn("r = +0.08 (p = 0.683)", self.s["verdikt"])
        self.assertIn("13 of 29", self.s["verdikt"])
        self.assertIn("Pearson r = +0.079", self.s["einfach"])
        self.assertIn("Spearman rho = +0.151", self.s["einfach"])
        self.assertEqual(self.s["verdikt_art"], rp.VERDIKT_NEIN)

    def test_stance_und_subreddits(self) -> None:
        self.assertIn("r = -0.086", self.s["einfach"])
        self.assertIn("H = 92.05", self.s["einfach"])
        subs = self.s["diagramme"]["subreddits"]["punkte"]
        self.assertEqual(subs[0]["label"], "r/stocks (n 277)")
        self.assertEqual(subs[-1]["label"], "r/Economics (n 7)")

    def test_audit_und_streuung(self) -> None:
        audit = {p["label"]: p["wert"] for p in self.s["diagramme"]["audit"]["punkte"]}
        self.assertEqual(audit, {"Relevant to the market": 0, "Partly relevant": 13, "Unrelated": 37})
        punkte = self.s["diagramme"]["streuung"]["punkte"]
        self.assertEqual(len(punkte), 29)
        self.assertTrue(all(0 <= p["x"] <= 100 and -1 <= p["y"] <= 1 for p in punkte))

    def test_tabellen_und_pflichtfelder(self) -> None:
        for feld in ("frage", "verdikt", "einfach", "analyse", "interpretation", "zahlen", "report", "modul"):
            self.assertTrue(self.s.get(feld), feld)
        titel = [t["titel"] for t in self.s["tabellen"]]
        self.assertIn("Every market in the sample", titel)
        self.assertEqual(len([t for t in self.s["tabellen"] if t["titel"] == "Every market in the sample"][0]["zeilen"]), 29)

    def test_keine_wallet_adresse(self) -> None:
        # Die Markttabelle traegt Condition-IDs (0x + 64 Hex); das ist keine
        # Wallet, aber die Pruefung muss trotzdem sauber durchlaufen.
        self.assertEqual(rp.wallet_adressen_in(self.p), [])

    def test_ohne_artefakte_leere_nutzlast(self) -> None:
        with TemporaryDirectory() as tmp:
            p = rr.build_payload(tmp)
            self.assertIsNone(p["studie"])
            self.assertEqual(len(p["fehlend"]), 4)


if __name__ == "__main__":
    unittest.main()
