"""Der Datensatz zu einer Studie wird verlinkt, aber nur wenn es ihn gibt.

Ein toter Link auf eine CSV, die es zu dieser Studie nie gab, behauptet einen
Beleg, den niemand oeffnen kann. Das waere schlechter als kein Link. Also
prueft ``app/study_datasets.py`` im Repo nach, und diese Tests halten fest,
dass es wirklich prueft und nicht raet.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from app import study_datasets as sd

WURZEL = Path(__file__).resolve().parents[1]
NUTZLAST = WURZEL / "public" / "data" / "microstructure.json"


class DatasetLinkTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(self.enterContext(__import__("tempfile").TemporaryDirectory()))
        (self.tmp / "docs" / "research").mkdir(parents=True)

    def _lege_an(self, name: str) -> None:
        (self.tmp / "docs" / "research" / name).write_text("x", encoding="utf-8")

    def test_beide_endungen_kommen_csv_zuerst(self) -> None:
        self._lege_an("studie.md")
        self._lege_an("studie.csv")
        self._lege_an("studie.json")
        links = sd.dataset_links("docs/research/studie.md", self.tmp)
        self.assertEqual([e["format"] for e in links], ["CSV", "JSON"])
        self.assertEqual(links[0]["path"], "docs/research/studie.csv")

    def test_was_nicht_da_ist_wird_nicht_verlinkt(self) -> None:
        # Eine der zwoelf Studien hat nur eine JSON. Genau der Fall.
        self._lege_an("nur_json.md")
        self._lege_an("nur_json.json")
        links = sd.dataset_links("docs/research/nur_json.md", self.tmp)
        self.assertEqual([e["format"] for e in links], ["JSON"])

    def test_ohne_datensatz_kommt_gar_nichts(self) -> None:
        self._lege_an("allein.md")
        self.assertEqual(sd.dataset_links("docs/research/allein.md", self.tmp), [])

    def test_ein_pfad_aus_der_nutzlast_wird_wie_eine_eingabe_behandelt(self) -> None:
        # Der Wert kommt aus einer JSON-Datei. Nichts davon darf aus dem
        # Forschungsordner herausfuehren.
        for boese in ("../../etc/passwd.md", "/etc/passwd.md", "C:/tmp/x.md",
                      "docs/research/../../secrets.md", "app/secrets.md", "", None):
            with self.subTest(pfad=boese):
                self.assertEqual(sd.dataset_links(boese, self.tmp), [])


class WithDatasetsTests(unittest.TestCase):
    def test_die_nutzlast_wird_nicht_veraendert(self) -> None:
        original = {"studien": [{"id": "a", "report": "docs/research/x.md"}]}
        kopie = json.loads(json.dumps(original))
        sd.with_datasets(original, WURZEL)
        self.assertEqual(original, kopie)

    def test_ein_vorhandenes_feld_bleibt_stehen(self) -> None:
        # Hat der Publish-Lauf die Links schon geschrieben, entscheidet er.
        eigen = [{"format": "CSV", "path": "docs/research/eigen.csv"}]
        payload = {"studien": [{"id": "a", "report": "docs/research/orderflow_rest-2026-07.md",
                                "daten": eigen}]}
        self.assertEqual(sd.with_datasets(payload, WURZEL)["studien"][0]["daten"], eigen)

    def test_etwas_das_keine_studienliste_ist_kommt_unveraendert_zurueck(self) -> None:
        for wert in (None, [], {"a": 1}, {"studien": "nope"}):
            with self.subTest(wert=wert):
                self.assertIs(sd.with_datasets(wert, WURZEL), wert)

    @unittest.skipUnless(NUTZLAST.exists(), "microstructure.json ist nicht publiziert")
    def test_jede_echte_studie_bekommt_mindestens_einen_datensatz(self) -> None:
        payload = json.loads(NUTZLAST.read_text(encoding="utf-8"))
        angereichert = sd.with_datasets(payload, WURZEL)
        for studie in angereichert["studien"]:
            with self.subTest(studie=studie["id"]):
                links = studie.get("daten") or []
                self.assertTrue(links, f"{studie['id']} hat keinen Datensatz")
                for eintrag in links:
                    self.assertTrue((WURZEL / eintrag["path"]).is_file(),
                                    f"{eintrag['path']} existiert nicht")


class GeneratorTests(unittest.TestCase):
    def test_der_publish_lauf_schreibt_die_links_gleich_mit(self) -> None:
        # Sonst haengt die Anreicherung allein am Endpunkt, und eine statisch
        # ausgelieferte Nutzlast traegt sie nie.
        from app.microstructure_report import build_payload

        payload = build_payload(WURZEL)
        mit = [s for s in payload["studien"] if s.get("daten")]
        self.assertEqual(len(mit), len(payload["studien"]))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
