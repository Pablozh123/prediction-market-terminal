"""Das Caveat-Register, wie es im Browser ankommt.

``web/js/claims.js`` ist der einzige Weg, auf dem ein Vorbehalt in die
Oberflaeche kommt, und ``web/js/claims_register.js`` ist die aus
``data/claims.yaml`` kompilierte Fassung, die er liest. Der Harness
``tests/web_claims_harness.mjs`` ruft das Modul auf wie eine Seite es tut;
hier steht, was dabei herauskommen muss.

Geprueft wird auch der Uebergang: die Saetze, die vor diesem Umbau als Prosa
in den Seiten standen, muessen unveraendert ankommen. Ein Register, das die
Formulierung nebenbei aendert, hat den Text nicht uebernommen, sondern
ersetzt.

Ohne node wird uebersprungen, in der CI nicht.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import unittest
from pathlib import Path

from app import claims

WURZEL = Path(__file__).resolve().parents[1]
HARNESS = WURZEL / "tests" / "web_claims_harness.mjs"


class WebClaimsRegisterTests(unittest.TestCase):
    ausgabe: dict

    @classmethod
    def setUpClass(cls) -> None:
        node = shutil.which("node")
        if node is None:
            if os.environ.get("CI"):
                raise AssertionError(
                    "node fehlt in der CI, der Register-Test der Weboberflaeche "
                    "kann nicht laufen (setup-node im Workflow pruefen)")
            raise unittest.SkipTest("node ist nicht installiert")
        lauf = subprocess.run(
            [node, str(HARNESS)],
            cwd=str(WURZEL),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=120,
        )
        if lauf.returncode != 0:
            raise AssertionError(f"Harness brach ab:\n{lauf.stderr}")
        cls.ausgabe = json.loads(lauf.stdout)

    def test_der_browser_liest_dasselbe_register_wie_python(self) -> None:
        kompiliert = self.ausgabe["kompiliert"]
        self.assertEqual(kompiliert, claims.frontend_register())
        for key in claims.disclaimer_keys():
            with self.subTest(key=key):
                self.assertEqual(kompiliert["disclaimers"][key]["en"], claims.disclaimer(key, "en"))
                self.assertEqual(kompiliert["disclaimers"][key]["de"], claims.disclaimer(key, "de"))

    def test_der_stand_des_registers_ist_ablesbar(self) -> None:
        stand = self.ausgabe["stand_eingebaut"]
        self.assertEqual(stand["quelle"], "eingebaut")
        self.assertEqual(stand["eintraege"], len(claims.disclaimer_keys()))
        self.assertEqual(stand["updated"], str(claims.load_claims().get("updated")))

    def test_die_fusszeile_traegt_ihren_alten_satz_unveraendert(self) -> None:
        # Wortgleich mit dem, was vor dem Umbau in app.js stand.
        zeile = self.ausgabe["fusszeile"]
        self.assertIn('data-caveat="site_footer_readonly"', zeile)
        self.assertIn("Read-only. No orders placed. Public Polymarket &amp; Kalshi data.", zeile)

    def test_beschreibung_und_vorbehalt_stehen_in_einem_absatz(self) -> None:
        zeile = self.ausgabe["zeile_mit_vorsatz"]
        self.assertIn('data-caveat="screen_not_proof"', zeile)
        self.assertIn("Sports odds are excluded.", zeile)
        self.assertIn("research leads, not legal findings", zeile)
        self.assertIn("Bands are listed below.", zeile)
        self.assertLess(zeile.index("Sports odds"), zeile.index("research leads"))

    def test_inline_und_beide_sprachen(self) -> None:
        self.assertIn('<span data-caveat="score_generic">', self.ausgabe["inline"])
        self.assertIn("not investment advice", self.ausgabe["inline"])
        self.assertEqual(self.ausgabe["text_en"], claims.disclaimer("backtest_modeled", "en"))
        self.assertEqual(self.ausgabe["text_de"], claims.disclaimer("backtest_modeled", "de"))

    def test_unbekannter_schluessel_rendert_nichts(self) -> None:
        for feld in ("unbekannt_text", "unbekannt_zeile", "unbekannt_inline"):
            with self.subTest(feld=feld):
                self.assertEqual(self.ausgabe[feld], "")
        # Beschreibender Text ohne Eintrag bleibt stehen, traegt aber kein
        # data-caveat: er ist keiner.
        nur_prosa = self.ausgabe["unbekannt_mit_vorsatz"]
        self.assertIn("Only prose.", nur_prosa)
        self.assertNotIn("data-caveat", nur_prosa)

    def test_eine_kaputte_antwort_laesst_den_eingebauten_stand_stehen(self) -> None:
        self.assertEqual(self.ausgabe["muell_angenommen"], [False, False, False, False])
        self.assertEqual(self.ausgabe["nach_muell"], claims.disclaimer("score_generic", "en"))
        self.assertEqual(self.ausgabe["stand_nach_muell"]["quelle"], "eingebaut")

    def test_eine_neuere_fassung_von_der_api_wird_uebernommen(self) -> None:
        self.assertTrue(self.ausgabe["api_angenommen"])
        self.assertEqual(self.ausgabe["nach_api"], "Newer text from the API.")
        self.assertEqual(self.ausgabe["stand_nach_api"]["quelle"], "api")
        self.assertEqual(self.ausgabe["stand_nach_api"]["version"], 2)


if __name__ == "__main__":
    unittest.main()
