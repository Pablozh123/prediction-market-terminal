"""Die lesbare Fassung fuer schmale Geraete.

Der Design-Review vom 2026-08-28 (Befund 2) hat gemessen, was auf einem
375px-Geraet wirklich passiert: die Huelle legt sich auf 1316px aus, das
Geraet zoomt die Seite auf Faktor 0.29, und die haeufigste Beschriftung
rendert als 3.2 Geraete-Pixel. Auch der Hinweis, der das erklaeren sollte,
war damit unlesbar.

Unter 768px liegt die Huelle deshalb nicht mehr im Layout, und eine eigene,
lesbare Zusammenfassung steht an ihrer Stelle. Dieser Test haelt die drei
Bedingungen fest, die das traegt: die Regeln im CSS, das Markup in
index.html, und dass die einzige Zahlenzeile aus der Nutzlast kommt statt aus
einem Platzhalter.
"""

from __future__ import annotations

import html
import re
import unittest
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[1]
CSS = WURZEL / "web" / "css" / "terminal.css"
INDEX = WURZEL / "web" / "index.html"
APP = WURZEL / "web" / "js" / "app.js"


class SchmaleFassungTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.css = CSS.read_text(encoding="utf-8")
        cls.index = INDEX.read_text(encoding="utf-8")
        cls.app = APP.read_text(encoding="utf-8")

    def _block(self, query: str) -> str:
        """Der Rumpf einer Media-Query, bis zur schliessenden Klammer."""

        start = self.css.find(query)
        self.assertGreater(start, 0, f"{query} fehlt in terminal.css")
        tiefe = 0
        for i in range(self.css.find("{", start), len(self.css)):
            if self.css[i] == "{":
                tiefe += 1
            elif self.css[i] == "}":
                tiefe -= 1
                if tiefe == 0:
                    return self.css[start:i + 1]
        self.fail(f"{query} ist nicht geschlossen")

    def test_unter_768px_faellt_die_huelle_aus_dem_layout(self) -> None:
        # Das ist der ganze Trick: was den Zoom erzwingt, ist die
        # min-width der Huelle. Nur display:none nimmt sie aus dem Layout,
        # visibility oder Transparenz wuerden die 1280px stehen lassen.
        block = self._block("@media (max-width: 767px)")
        self.assertRegex(block, r"\.shell,\s*\.narrow-note\s*\{\s*display:\s*none")
        self.assertIn(".narrow-fallback", block)
        self.assertRegex(block, r"\.narrow-fallback\s*\{[^}]*display:\s*block")

    def test_zwischen_768_und_1279_bleibt_es_beim_hinweis(self) -> None:
        # Ein Laptopfenster von 1000px soll das Terminal behalten. Dort
        # zoomt das Geraet kaum, der Hinweis reicht.
        block = self._block("@media (min-width: 768px) and (max-width: 1279px)")
        self.assertIn(".narrow-note", block)
        self.assertNotIn(".shell", block)

    def test_wer_die_huelle_trotzdem_will_bekommt_sie(self) -> None:
        self.assertRegex(
            self.css, r'\[data-narrow-override="1"\]\s*\.shell\s*\{\s*display:\s*flex')
        self.assertRegex(
            self.css, r'\[data-narrow-override="1"\]\s*\.narrow-fallback\s*\{\s*display:\s*none')
        self.assertIn('id="narrow-override"', self.index)
        self.assertIn("data-narrow-override", self.app)

    def test_die_fassung_steht_im_markup_und_ist_benannt(self) -> None:
        self.assertIn('class="narrow-fallback"', self.index)
        self.assertIn('aria-label="Summary for small screens"', self.index)
        # Sie muss auch die Wege nach draussen tragen, die die Huelle sonst
        # bietet: Quelle, Impressum, Datenschutz.
        for ziel in ("./imprint.html", "./privacy.html",
                     "https://github.com/Pablozh123/prediction-market-terminal"):
            with self.subTest(ziel=ziel):
                self.assertIn(ziel, self._fallback())

    def _fallback(self) -> str:
        m = re.search(r'<section class="narrow-fallback".*?</section>', self.index, re.S)
        self.assertIsNotNone(m, "der Abschnitt fehlt in index.html")
        return m.group(0)

    def test_die_zahlenzeile_ist_leer_bis_die_nutzlast_da_ist(self) -> None:
        # Im ausgelieferten HTML darf keine Zahl stehen: ein Platzhalter, der
        # spaeter ueberschrieben wird, ist eine Behauptung ohne Quelle.
        abschnitt = self._fallback()
        m = re.search(r'<p class="facts" id="narrow-facts">(.*?)</p>', abschnitt, re.S)
        self.assertIsNotNone(m, "die Zahlenzeile fehlt")
        self.assertEqual(m.group(1).strip(), "")
        # Und ueberhaupt keine nackte Zahl im sichtbaren Text. 768 und 1280
        # stehen im CSS, nicht hier; im Abschnitt selbst hat keine Zahl etwas
        # zu suchen, die nicht aus der Nutzlast kommt.
        sichtbar = html.unescape(re.sub(r"<[^>]+>", " ", abschnitt))
        self.assertNotRegex(sichtbar, r"\d")

    def test_die_zahlenzeile_kommt_aus_derselben_quelle_wie_die_startseite(self) -> None:
        # landingSubline liest die Nutzlast. Eine zweite, eigene Formulierung
        # waere eine Zahl, die neben derselben Zahl anders steht.
        self.assertIn("schmaleZusammenfassung", self.app)
        self.assertIn("landingSubline(this.landing)", self.app)
        # Ohne Studien in der Nutzlast bleibt die Zeile leer.
        stelle = self.app.find("schmaleZusammenfassung()")
        rumpf = self.app[stelle:stelle + 900]
        self.assertIn("ziel.textContent = ''", rumpf)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
