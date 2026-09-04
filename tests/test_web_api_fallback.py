"""Der statische Rueckfall in web/js/api.js parst nur, was eine JSON-Datei ist.

Auf marketintel.dev (Cloudflare Pages) antwortet ein fehlender Pfad unter
./data/ mit der Startseite der Anwendung: Status 200, text/html. Bis zum
2026-09-04 lief das blind in JSON.parse, und die Seite meldete "JSON.parse:
unexpected character at line 1 column 1" fuer eine Datei, die es noch nicht
gab (arb_scan.json). Der Harness tests/web_api_harness.mjs stellt fetch nach
und prueft: HTML-Antwort, 404, echte Datei, Netzausfall.

Ohne node wird uebersprungen, in der CI nicht (wie test_web_leerzustand).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import unittest
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[1]
HARNESS = WURZEL / "tests" / "web_api_harness.mjs"


class StatischerRueckfallTest(unittest.TestCase):
    ausgabe: dict

    @classmethod
    def setUpClass(cls) -> None:
        node = shutil.which("node")
        if node is None:
            if os.environ.get("CI"):
                raise AssertionError("node fehlt in der CI — der API-Rueckfall-Test kann nicht laufen")
            raise unittest.SkipTest("node ist nicht installiert")
        lauf = subprocess.run([node, str(HARNESS)], cwd=str(WURZEL), capture_output=True,
                              text=True, encoding="utf-8", timeout=60)
        if lauf.returncode != 0:
            raise AssertionError(f"Harness brach ab:\n{lauf.stderr}")
        cls.ausgabe = json.loads(lauf.stdout)

    def test_pages_startseite_ist_eine_fehlende_datei(self) -> None:
        # API 404 + HTML statt Datei: null, also Leerzustand — kein Parse-Fehler.
        f = self.ausgabe["faelle"]
        self.assertEqual(f["pages_liefert_startseite"], {"wert": None})
        self.assertEqual(f["datei_404"], {"wert": None})
        self.assertEqual(f["api_404_datei_netz_tot"], {"wert": None})

    def test_echte_datei_kommt_als_statisch_markiert(self) -> None:
        f = self.ausgabe["faelle"]
        self.assertEqual(f["datei_json"]["wert"]["_quelle"], "statisch")
        self.assertEqual(f["datei_json"]["wert"]["summary"]["validated_24h"], 9)
        # Ein reiner Dateiserver ohne Content-Type: der Body entscheidet.
        self.assertEqual(f["datei_json_ohne_typ"]["wert"]["kennzeichnung"], "curated/field-notes")
        self.assertEqual(f["netz_tot_mit_datei"]["wert"]["_quelle"], "statisch")

    def test_api_antwort_hat_vorrang(self) -> None:
        f = self.ausgabe["faelle"]
        self.assertEqual(f["api_antwortet"]["wert"]["summary"]["validated_24h"], 3)
        self.assertNotIn("_quelle", f["api_antwortet"]["wert"])

    def test_echte_fehler_bleiben_fehler(self) -> None:
        # Nichts hat geantwortet: die Seite muss das sagen, nicht "leer".
        f = self.ausgabe["faelle"]
        self.assertEqual(f["netz_tot_ohne_datei"]["fehler"], "Failed to fetch")
        self.assertEqual(f["api_500_ohne_datei"]["fehler"], "HTTP 500")
        self.assertEqual(f["api_500_ohne_datei"]["status"], 500)
        # Ohne publizierte Datei dahinter bleibt auch ein 404 ein Fehler.
        self.assertEqual(f["ohne_statische_datei"]["fehler"], "HTTP 404")

    def test_reiner_leser(self) -> None:
        r = self.ausgabe["rein"]
        self.assertIsNone(r["html_200"])
        self.assertIsNone(r["json_404"])
        self.assertEqual(r["json_ok"], {"a": 1})
        self.assertEqual(r["json_mit_bom"], {"a": 2})
        self.assertEqual(r["liste_ohne_typ"], [1, 2])
        self.assertIsNone(r["html_ohne_typ"])
        self.assertIsNone(r["kaputt"])
        self.assertIsNone(r["leer"])
        self.assertIsNone(r["zahl"])

    def test_jede_studie_hat_ihren_rueckfall(self) -> None:
        statisch = self.ausgabe["statisch"]
        self.assertEqual(statisch["/api/research/arb-scan"], "arb_scan.json")
        for datei in statisch.values():
            self.assertTrue(datei.endswith(".json"), datei)


if __name__ == "__main__":
    unittest.main()
