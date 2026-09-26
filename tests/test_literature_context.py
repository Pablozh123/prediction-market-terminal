"""Die Literatur-Nutzlast: jede kuratierte Zahl steht woertlich im Text,
aus dem sie zitiert ist, und jede verlinkte Studie existiert auf der
Microstructure-Seite."""

from __future__ import annotations

import unittest
from pathlib import Path

from app import literature_context as lc
from app import microstructure_report as mr

PROJEKT = Path(__file__).resolve().parents[1]


class DriftTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.md = (PROJEKT / lc.QUELLE_MD).read_text(encoding="utf-8")

    def test_jede_zahl_steht_im_text(self) -> None:
        for zahl in lc.alle_zahlen():
            with self.subTest(zahl=zahl):
                self.assertIn(zahl, self.md)

    def test_kernsatz_kommt_aus_dem_text(self) -> None:
        satz = lc.kernsatz(self.md)
        self.assertTrue(satz.startswith("Predicting direction works measurably and does not pay"))

    def test_verlinkte_studien_existieren(self) -> None:
        ids = {s.id for s in mr.STUDIEN}
        for e in lc.EIGENE + [lc.PROGRAMM]:
            with self.subTest(studie=e["studie"]):
                self.assertIn(e["studie"], ids)


class NutzlastTests(unittest.TestCase):
    def test_bloecke_und_diagramme(self) -> None:
        p = lc.build_payload(PROJEKT)
        self.assertEqual(p["fehlend"], [])
        self.assertEqual(len(p["eigene"]), 5)
        self.assertEqual(len(p["literatur"]), 3)
        self.assertEqual(len(p["anomalien"]), 3)
        self.assertEqual([r["rang"] for r in p["rangfolge"]], [1, 2, 3])
        self.assertEqual(len(p["diagramme"]["wer_verliert"]["punkte"]), 3)
        self.assertTrue(p["einleitung"].startswith("Predicting direction"))
        self.assertEqual(p["report"], "docs/research/ertragsquellen_2026-07-31.md")

    def test_ohne_text_gemeldet(self) -> None:
        p = lc.build_payload("/nirgends")
        self.assertEqual(p["fehlend"], ["docs/research/ertragsquellen_2026-07-31.md"])
        self.assertTrue(p["einleitung"])


if __name__ == "__main__":
    unittest.main()
