"""web/llms.txt: eine maschinenlesbare Beschreibung der Seite, ohne Zahlen.

Der Text beschreibt, was das Projekt ist und wo die Befunde liegen. Er darf
keine Kennzahl tragen: eine Zahl in einer von Hand gepflegten Datei hat keine
Quelle und keinen Stand, altert still und widerspricht irgendwann der Seite.
Die zahlengestuetzte Fassung entsteht spaeter aus der Nutzlast.

Der stehende Hinweis darin ist derselbe wie ueberall sonst, naemlich der aus
``data/claims.yaml``. Eine zweite, abweichende Fassung waere genau das, wogegen
es das Register gibt, also bindet dieser Test beide aneinander.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from app import claims

WURZEL = Path(__file__).resolve().parents[1]
LLMS = WURZEL / "web" / "llms.txt"
ROBOTS = WURZEL / "web" / "robots.txt"
INDEX = WURZEL / "web" / "index.html"


class LlmsTxtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = LLMS.read_text(encoding="utf-8")

    def test_die_datei_liegt_da_wo_sie_abgerufen_wird(self) -> None:
        # Der statische Bau kopiert web/ eins zu eins, also wird aus
        # web/llms.txt genau /llms.txt.
        self.assertTrue(LLMS.is_file())
        self.assertTrue(self.text.startswith("# Market Intel"))

    def test_der_hinweis_ist_der_registrierte(self) -> None:
        self.assertIn(claims.disclaimer("research_tool_only", "en"), self.text)

    def test_die_datei_traegt_keine_kennzahl(self) -> None:
        # Erlaubt sind Ziffern nur in Adressen (URLs und Pfaden), sonst
        # keine. Eine Zahl ohne Quelle und ohne Stand gehoert hier nicht hin.
        ohne_urls = re.sub(r"https?://\S+", " ", self.text)
        ohne_pfade = re.sub(r"/\S+", " ", ohne_urls)
        gefunden = re.findall(r"\d[\d.,%]*", ohne_pfade)
        self.assertEqual(gefunden, [], f"Zahlen in llms.txt: {gefunden}")

    def test_sie_faellt_unter_die_wortliste_des_registers(self) -> None:
        # Eine eigene Wortliste hier waere eine zweite Wahrheit. Die Datei
        # steht in scripts/lint_claims.py::LINT_SOURCES und wird gegen
        # data/claims.yaml geprueft wie jede andere Oberflaeche.
        quelltext = (WURZEL / "scripts" / "lint_claims.py").read_text(encoding="utf-8")
        self.assertIn('"web/llms.txt"', quelltext)
        self.assertEqual(claims.find_forbidden(self.text), [])

    def test_sie_nennt_die_wege_zu_den_befunden_und_zur_quelle(self) -> None:
        for ziel in ("/#research/microstructure", "/#research/methodology",
                     "/imprint.html", "/privacy.html",
                     "https://github.com/Pablozh123/prediction-market-terminal"):
            with self.subTest(ziel=ziel):
                self.assertIn(ziel, self.text)

    def test_robots_txt_zeigt_auf_sie(self) -> None:
        self.assertIn("https://marketintel.dev/llms.txt", ROBOTS.read_text(encoding="utf-8"))

    def test_die_beschreibung_widerspricht_der_startseite_nicht(self) -> None:
        # Beide sagen dasselbe ueber die Datenquelle. Steht auf der einen
        # Seite etwas anderes als in der Datei, glaubt ein Leser der Datei.
        index = INDEX.read_text(encoding="utf-8")
        self.assertIn("Polymarket and Kalshi", index)
        self.assertIn("Polymarket and Kalshi", self.text)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
