"""Die vier Vorschau-Studien (Thesis, Reddit sentiment, Pre-registrations,
Literature) und der Schalter, hinter dem sie stehen.

Drei Dinge werden geprueft:

1. Die Verdrahtung ist an allen vier Stellen dieselbe: studies.js,
   RESEARCH_DATEI in system_pages.js, STATISCH in api.js und RESEARCH_FILES
   in app/api_views.py nennen dieselben Dateien in derselben Reihenfolge.
2. Jede Seite rendert mit Nutzlast ihren Befund samt Diagrammen, ohne
   Nutzlast ihren Leerzustand mit Dateinamen, und nach einem gescheiterten
   Abruf den Fehler; nirgends eine Wallet-Adresse.
3. Der Schalter (web/js/preview.js) liest Adresse und Speicher so, wie die
   Seitenleiste ihn braucht, und die Sperrkarte traegt genau eine h1.

Gerendert wird ueber denselben Node-Harness wie tests/test_web_leerzustand.py.
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
WALLET = re.compile(r"0x[0-9a-fA-F]{40}")

VORSCHAU = [
    ("Thesis", "thesis", "thesis_results.json", "thesis_results"),
    ("Reddit sentiment", "reddit-sentiment", "reddit_sentiment.json", "reddit_sentiment"),
    ("Pre-registrations", "pre-registrations", "preregistrations.json", "preregistrations"),
    ("Literature", "literature", "literature.json", "literature"),
]

PREVIEW_PROBE = """
import { previewAn, gesperrt, sperrkarteHtml } from '../web/js/preview.js';
const store = () => { const m = {}; return { getItem: (k) => (k in m ? m[k] : null), setItem: (k, v) => { m[k] = v; }, removeItem: (k) => { delete m[k]; }, m }; };
const s1 = store();
const raus = {
  aus_ohne_alles: previewAn('', s1),
  an_per_adresse: previewAn('?preview=1', s1),
  gemerkt: previewAn('', s1),
  aus_per_adresse: previewAn('?preview=0', s1),
  vergessen: previewAn('', s1),
  ohne_speicher: previewAn('?preview=1', null),
  gesperrt_ohne: gesperrt({ preview: true }, false),
  gesperrt_mit: gesperrt({ preview: true }, true),
  frei: gesperrt({}, false),
  karte: sperrkarteHtml({ title: 'A <study>' })
};
process.stdout.write(JSON.stringify(raus));
"""


def _node() -> str:
    node = shutil.which("node")
    if node is None:
        if os.environ.get("CI"):
            raise AssertionError("node fehlt in der CI (setup-node im Workflow pruefen)")
        raise unittest.SkipTest("node ist nicht installiert")
    return node


def _sichtbar(html: str) -> str:
    ohne_tooltip = re.sub(r"<title>.*?</title>", " ", html, flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]*>", " ", ohne_tooltip)).strip()


class VerdrahtungTest(unittest.TestCase):
    def test_vier_stellen_nennen_dieselben_dateien(self) -> None:
        studies = (WURZEL / "web" / "js" / "studies.js").read_text(encoding="utf-8")
        system = (WURZEL / "web" / "js" / "pages" / "system_pages.js").read_text(encoding="utf-8")
        api_js = (WURZEL / "web" / "js" / "api.js").read_text(encoding="utf-8")
        from app import api_views as apv

        tabs = re.findall(r"tab: '([^']+)'", studies)
        letzte = tabs[-len(VORSCHAU):]
        self.assertEqual(letzte, [v[0] for v in VORSCHAU])
        # preview: true steht bei genau diesen vier.
        self.assertEqual(len(re.findall(r"^\s+preview: true$", studies, re.M)), len(VORSCHAU))
        dateien = re.search(r"const RESEARCH_DATEI = \[(.*?)\];", system, re.S).group(1)
        namen = re.findall(r"'([a-z_]+\.json)'", dateien)
        self.assertEqual(namen[-len(VORSCHAU):], [v[2] for v in VORSCHAU])
        self.assertEqual(len(namen), len(tabs), "RESEARCH_DATEI muss so lang sein wie STUDIEN")
        for _, slug, datei, name in VORSCHAU:
            self.assertIn(f"'/api/research/{slug}': '{datei}'", api_js)
            self.assertEqual(apv.RESEARCH_FILES[slug], name)

    def test_publizierte_dateien_liegen_unter_public_data(self) -> None:
        for _, _, datei, _ in VORSCHAU:
            pfad = WURZEL / "public" / "data" / datei
            with self.subTest(datei=datei):
                self.assertTrue(pfad.exists(), f"{datei} fehlt; scripts/publish_research_pages.py")
                nutzlast = json.loads(pfad.read_text(encoding="utf-8"))
                self.assertIn("stand_utc", nutzlast)
                self.assertEqual(WALLET.findall(pfad.read_text(encoding="utf-8")), [])


class RenderTest(unittest.TestCase):
    ausgabe: dict

    @classmethod
    def setUpClass(cls) -> None:
        lauf = subprocess.run([_node(), str(HARNESS)], cwd=str(WURZEL), capture_output=True, text=True, encoding="utf-8", timeout=120)
        if lauf.returncode != 0:
            raise AssertionError(f"Harness brach ab:\n{lauf.stderr}")
        cls.ausgabe = json.loads(lauf.stdout)

    def test_mit_nutzlast_befund_und_diagramme(self) -> None:
        live = self.ausgabe["live"]
        erwartet = {
            "research_thesis": ("Mixed.", "Right side, wrong number", "Granger p", "SUPPORTED", "MIXED"),
            "research_reddit": ("No measurable link", "NOT SUPPORTED", "Kruskal-Wallis"),
            "research_prereg": ("TEST WINDOW RUNNING", "COMPLETED", "DRAFT", "half spread"),
            "research_literature": ("Akey", "Buergi", "Providing liquidity"),
        }
        for seite, texte in erwartet.items():
            with self.subTest(seite=seite):
                html = live[seite]
                text = _sichtbar(html)
                self.assertNotIn("RENDER-FEHLER", html)
                self.assertEqual(html.count("<h1"), 1)
                self.assertGreaterEqual(html.count("<svg"), 2, "jede Vorschau-Seite zeichnet mit Nutzlast")
                for t in texte:
                    self.assertIn(t, text)
                self.assertEqual(WALLET.findall(html), [])

    def test_tabellen_tragen_rollen(self) -> None:
        html = self.ausgabe["live"]["research_thesis"]
        self.assertGreaterEqual(html.count('role="table"'), 4)
        self.assertGreaterEqual(html.count('role="columnheader"'), 8)
        self.assertGreaterEqual(html.count('role="cell"'), 20)
        # Keine Zeile ist zugleich ein Knopf.
        for treffer in re.finditer(r"<div([^>]*)>", html):
            attrs = treffer.group(1)
            self.assertFalse('role="row"' in attrs and 'role="button"' in attrs)

    def test_ohne_nutzlast_dateiname_und_kein_diagramm(self) -> None:
        for seite, datei in (("research_thesis_leer", "thesis_results.json"), ("research_reddit_leer", "reddit_sentiment.json"),
                             ("research_literature_leer", "literature.json")):
            with self.subTest(seite=seite):
                html = self.ausgabe["live"][seite]
                self.assertIn(datei, _sichtbar(html))
                self.assertIn("publish_research_pages.py", _sichtbar(html))
                self.assertEqual(html.count("<svg"), 0)
        for seite in ("research_thesis", "research_reddit", "research_prereg", "research_literature"):
            with self.subTest(modus="leer", seite=seite):
                html = self.ausgabe["leer"][seite]
                self.assertIn("loading public/data/", _sichtbar(html))
                self.assertEqual(html.count("<svg"), 0)

    def test_gescheiterter_abruf_sagt_es(self) -> None:
        for seite in ("research_thesis_fehler", "research_prereg_fehler"):
            with self.subTest(seite=seite):
                text = _sichtbar(self.ausgabe["live"][seite])
                self.assertIn("failed (HTTP 503)", text)
                self.assertIn("Nothing is shown in its place", text)

    def test_thesis_zahlen_aus_der_nutzlast(self) -> None:
        nutzlast = json.loads((WURZEL / "tests" / "fixtures" / "thesis_results_example.json").read_text(encoding="utf-8"))
        text = _sichtbar(self.ausgabe["live"]["research_thesis"])
        for s in nutzlast["sektionen"]:
            with self.subTest(abschnitt=s["id"]):
                self.assertIn(s["verdikt"][:60], text)
                for z in s["zahlen"][:2]:
                    self.assertIn(z["label"], text)


class SchalterTest(unittest.TestCase):
    def test_previewan_liest_adresse_und_speicher(self) -> None:
        node = _node()
        probe = WURZEL / "tests" / "_preview_probe.mjs"
        probe.write_text(PREVIEW_PROBE, encoding="utf-8")
        try:
            lauf = subprocess.run([node, str(probe)], cwd=str(WURZEL), capture_output=True, text=True, encoding="utf-8", timeout=60)
        finally:
            probe.unlink(missing_ok=True)
        self.assertEqual(lauf.returncode, 0, lauf.stderr)
        raus = json.loads(lauf.stdout)
        self.assertFalse(raus["aus_ohne_alles"])
        self.assertTrue(raus["an_per_adresse"])
        self.assertTrue(raus["gemerkt"], "?preview=1 wird gemerkt")
        self.assertFalse(raus["aus_per_adresse"])
        self.assertFalse(raus["vergessen"], "?preview=0 loescht die Merkung")
        self.assertTrue(raus["ohne_speicher"])
        self.assertTrue(raus["gesperrt_ohne"])
        self.assertFalse(raus["gesperrt_mit"])
        self.assertFalse(raus["frei"])
        self.assertEqual(raus["karte"].count("<h1"), 1)
        self.assertIn("A &lt;study&gt;", raus["karte"])
        self.assertIn("IN PREPARATION", raus["karte"])

    def test_seitenleiste_und_suche_kennen_den_schalter(self) -> None:
        app = (WURZEL / "web" / "js" / "app.js").read_text(encoding="utf-8")
        overlays = (WURZEL / "web" / "js" / "overlays.js").read_text(encoding="utf-8")
        self.assertIn("IN PREPARATION · PREVIEW", app)
        self.assertIn("this.studieGesperrt(this.state.researchTab)", app)
        self.assertIn("sperrkarteHtml(this.studies[this.state.researchTab])", app)
        self.assertIn("!st.preview || vorschau", overlays)


if __name__ == "__main__":
    unittest.main()
