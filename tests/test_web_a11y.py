"""Die Datentabellen der Weboberflaeche tragen Tabellensemantik.

Jede Tabelle ist ein Raster aus divs (CSS grid), kein <table>. Ein
Screenreader fand darin nur Text: keinen Tabellennamen, keine Spaltenkoepfe,
keine Zeilen. Der Harness tests/web_render_harness.mjs rendert die Seiten
wie in test_web_leerzustand; hier wird auf dem HTML geprueft:

1. Jede gelistete Tabelle traegt genau ein role="table" mit einem Namen.
2. Sie hat Spaltenkoepfe, Zeilen und Zellen.
3. Kein Element ist zugleich Zeile und Knopf — eine klickbare Zeile behaelt
   Handler und Tab-Stop, nicht die Knopfrolle.

Ohne node wird uebersprungen; in der CI ist das ein Fehler.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import unittest
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[1]
HARNESS = WURZEL / "tests" / "web_render_harness.mjs"
SEITEN_DIR = WURZEL / "web" / "js" / "pages"

# Harness-Seite -> aria-label der Tabelle darauf.
TABELLEN = {
    "markets": "Markets",
    "flow": "Live tape",
    "resolved": "Resolved markets",
    "cross": "Cross-venue pairs",
    "traders": "Leaderboard",
    "whale": "Whale flow",
}

# Die Seitenmodule, die Tabellenzeilen mit Handler rendern.
SEITEN_MODULE = ["core_pages.js", "trader_pages.js", "trading_pages.js", "copy_page.js"]

# Ein oeffnendes div mit seinen Attributen.
TAG = re.compile(r"<div\b([^>]*)>")


def _harness_ausgabe() -> dict:
    """Derselbe Aufruf wie in test_web_leerzustand._harness_ausgabe."""
    node = shutil.which("node")
    if node is None:
        if os.environ.get("CI"):
            raise AssertionError(
                "node fehlt in der CI — der Render-Test der Weboberflaeche "
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
    return json.loads(lauf.stdout)


class WebTabellenSemantikTest(unittest.TestCase):
    ausgabe: dict

    @classmethod
    def setUpClass(cls) -> None:
        cls.ausgabe = _harness_ausgabe()

    def test_jede_tabelle_hat_genau_eine_rolle_und_einen_namen(self) -> None:
        for seite, name in TABELLEN.items():
            with self.subTest(seite=seite):
                html = self.ausgabe["live"][seite]
                self.assertEqual(html.count('role="table"'), 1)
                self.assertIn('role="table" aria-label="' + name + '"', html)

    def test_koepfe_zeilen_und_zellen(self) -> None:
        for seite in TABELLEN:
            with self.subTest(seite=seite):
                html = self.ausgabe["live"][seite]
                self.assertGreaterEqual(html.count('role="columnheader"'), 1)
                # Die Kopfzeile und mindestens eine Datenzeile mit Zellen.
                self.assertGreaterEqual(html.count('role="row"'), 2)
                self.assertGreaterEqual(html.count('role="cell"'), 1)

    def test_markets_kopf_sagt_die_sortierung(self) -> None:
        # Standard ist Volumen absteigend; die drei anderen sortierbaren
        # Koepfe sagen "none", die nicht sortierbaren sagen nichts.
        html = self.ausgabe["live"]["markets"]
        self.assertIn('aria-sort="descending"', html)
        self.assertEqual(html.count('aria-sort="descending"'), 1)
        self.assertEqual(html.count('aria-sort="none"'), 3)
        self.assertNotIn("aria-pressed", html.split('role="table"', 1)[1].split('role="cell"', 1)[0])

    def test_kein_element_ist_zeile_und_knopf(self) -> None:
        for modus in ("leer", "live"):
            for seite, html in self.ausgabe[modus].items():
                with self.subTest(modus=modus, seite=seite):
                    for treffer in TAG.finditer(html):
                        attrs = treffer.group(1)
                        self.assertFalse(
                            'role="row"' in attrs and 'role="button"' in attrs,
                            f"Zeile und Knopf zugleich: <div{attrs}>")

    def test_klickbare_zeilen_bestellen_die_knopfrolle_ab(self) -> None:
        # Der Harness-Stub von T.act vergibt keine Rolle; die echte
        # app.js::act haengt role="button" an. Was die Seiten daraus machen,
        # steht in der Quelle: eine Zeile mit Handler bestellt die Rolle ab
        # ({ role: null }) oder nimmt den Handler durch zeilenAct, das sie
        # entfernt.
        for modul in SEITEN_MODULE:
            quelle = (SEITEN_DIR / modul).read_text(encoding="utf-8")
            for nr, zeile in enumerate(quelle.splitlines(), 1):
                if 'role="row"' not in zeile or "T.act(" not in zeile:
                    continue
                with self.subTest(modul=modul, zeile=nr):
                    self.assertIn("{ role: null }", zeile)
        core = (SEITEN_DIR / "core_pages.js").read_text(encoding="utf-8")
        self.assertIn('act.replace(/ role="[^"]*"/, \'\')', core)


if __name__ == "__main__":
    unittest.main()
