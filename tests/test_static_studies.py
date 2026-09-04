"""Eine eigene Adresse je eingefrorener Studie, gebaut aus der Nutzlast.

``app/static_studies.py`` baut je Studie ein statisches Dokument fuer Crawler
und fuer Leser ohne JavaScript. Die Regel dahinter ist dieselbe wie ueberall
sonst im Projekt: keine Zahl, die nicht in der veroeffentlichten Nutzlast
steht, und der Stand der Datei an jeder Zahl.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from app import claims
from app import static_studies as st

WURZEL = Path(__file__).resolve().parents[1]
NUTZLAST = WURZEL / "public" / "data" / "microstructure.json"


def _studie(**felder: object) -> dict:
    basis = {
        "id": "cross-venue",
        "frage": "Are price gaps between the two venues arbitrage?",
        "verdikt": "No, carry. The gaps that survive settle in 2027 or 2028.",
        "verdikt_art": "nein",
        "einfach": "Eight pairs matched, five usable, three clear both fee curves.",
        "basis": {"paare": 8, "maerkte": 900, "fenster": "2026-07-30"},
        "zahlen": [
            {"label": "Pairs matched", "wert": 8},
            {"label": "Best net gap", "wert": 3.0669, "einheit": "cents"},
        ],
        "report": "docs/research/cross_venue_gaps_2026-07-31.md",
        "modul": "src/cross_venue_gaps.py",
    }
    basis.update(felder)
    return basis


class SlugTests(unittest.TestCase):
    def test_der_slug_ist_der_anker_der_oberflaeche(self) -> None:
        # Die Oberflaeche springt auf #research/microstructure/<id>. Weicht das
        # Segment davon ab, zeigt der Link der statischen Seite ins Leere.
        self.assertEqual(st.study_slug({"id": "mm-120s"}), "mm-120s")
        self.assertEqual(st.study_slug({"id": "MM 120s"}), "mm-120s")
        self.assertEqual(st.study_slug({"id": "  a/b  "}), "a-b")
        self.assertEqual(st.study_slug({}), "")
        self.assertEqual(st.study_slug(None), "")


class BasisSatzTests(unittest.TestCase):
    def test_n_und_fenster_stehen_beide_da(self) -> None:
        satz = st.basis_satz({"paare": 8, "maerkte": 900, "fenster": "2026-07-30"})
        self.assertIn("900 markets", satz)
        self.assertIn("8 pairs", satz)
        self.assertIn("2026-07-30", satz)

    def test_grosse_zahlen_bekommen_tausendertrenner(self) -> None:
        self.assertIn("205,835 observations", st.basis_satz({"beobachtungen": 205835}))

    def test_ohne_basis_bleibt_die_zeile_leer(self) -> None:
        self.assertEqual(st.basis_satz(None), "")
        self.assertEqual(st.basis_satz({}), "")
        # Eine Null ist keine Basis und darf nicht als "0 pairs" erscheinen.
        self.assertEqual(st.basis_satz({"paare": 0}), "")


class SeitenInhaltTests(unittest.TestCase):
    def setUp(self) -> None:
        self.html = st.study_page_html(_studie(), "2026-08-17")

    def test_die_seite_traegt_frage_verdikt_basis_und_stand(self) -> None:
        self.assertIn("Are price gaps between the two venues arbitrage?", self.html)
        self.assertIn("No, carry.", self.html)
        self.assertIn("900 markets", self.html)
        self.assertIn("8 pairs", self.html)
        # Ohne Stand koennte ein Leser die Zahlen fuer heutige halten.
        self.assertIn("Payload snapshot 2026-08-17", self.html)

    def test_die_kopfangaben_sind_eigen_und_zeigen_auf_sich_selbst(self) -> None:
        self.assertIn("<title>Are price gaps between the two venues arbitrage? — Market Intel</title>", self.html)
        self.assertIn('rel="canonical" href="https://marketintel.dev/study/cross-venue/"', self.html)
        self.assertIn('property="og:url" content="https://marketintel.dev/study/cross-venue/"', self.html)
        self.assertIn('name="robots" content="index,follow"', self.html)
        # Die Beschreibung ist das Verdikt, nicht der Seitentitel des Terminals.
        self.assertIn('name="description" content="No, carry.', self.html)

    def test_die_kennzahlen_kommen_mit_einheit(self) -> None:
        self.assertIn("Pairs matched", self.html)
        self.assertIn(">8<", self.html)
        self.assertIn("3.067 cents", self.html)

    def test_der_hinweis_kommt_aus_dem_register(self) -> None:
        # Ein von Hand geschriebener Vorbehalt waere eine zweite, driftende
        # Fassung derselben Zeile. Genau dagegen gibt es das Register.
        self.assertIn(claims.disclaimer("research_tool_only", "en"), self.html)

    def test_die_seite_verlinkt_quelle_und_terminal(self) -> None:
        self.assertIn("docs/research/cross_venue_gaps_2026-07-31.md", self.html)
        self.assertIn("src/cross_venue_gaps.py", self.html)
        self.assertIn('href="../../#research/microstructure/cross-venue"', self.html)

    def test_html_in_der_nutzlast_wird_entschaerft(self) -> None:
        boes = st.study_page_html(_studie(frage="<script>alert(1)</script>"), "2026-08-17")
        self.assertNotIn("<script>alert(1)</script>", boes)
        self.assertIn("&lt;script&gt;", boes)

    def test_fehlende_felder_erfinden_nichts(self) -> None:
        duenn = st.study_page_html({"id": "x", "frage": "Q?", "verdikt": "V."}, "")
        self.assertIn("Q?", duenn)
        self.assertNotIn("Data ·", duenn)
        self.assertNotIn("Payload snapshot", duenn)
        self.assertNotIn("Full report", duenn)


class SeitenMengeTests(unittest.TestCase):
    def test_jede_studie_mit_id_bekommt_genau_eine_seite(self) -> None:
        payload = {"stand_utc": "2026-08-17T18:38:23+00:00",
                   "studien": [_studie(), _studie(id="gap-lifetime"), _studie(id="cross-venue")]}
        seiten = st.study_pages(payload)
        self.assertEqual(sorted(seiten), ["cross-venue", "gap-lifetime"])
        self.assertIn("Payload snapshot 2026-08-17", seiten["cross-venue"])

    def test_ohne_nutzlast_entstehen_keine_seiten(self) -> None:
        self.assertEqual(st.study_pages(None), {})
        self.assertEqual(st.study_pages({}), {})
        self.assertEqual(st.study_pages({"studien": "nope"}), {})
        self.assertEqual(st.study_pages({"studien": [{"frage": "no id"}]}), {})

    @unittest.skipUnless(NUTZLAST.exists(), "microstructure.json ist nicht publiziert")
    def test_die_echte_nutzlast_ergibt_zwoelf_seiten_mit_verdikt(self) -> None:
        payload = json.loads(NUTZLAST.read_text(encoding="utf-8"))
        seiten = st.study_pages(payload)
        self.assertEqual(len(seiten), len(payload["studien"]))
        for slug, seite in seiten.items():
            with self.subTest(slug=slug):
                self.assertIn("<title>", seite)
                self.assertIn('rel="canonical"', seite)
                self.assertIn("Frozen study", seite)


class CspTests(unittest.TestCase):
    """Die Seiten muessen unter der Content-Security-Policy von web/_headers
    unveraendert rendern.

    Die Richtlinie erlaubt Skripte nur aus eigener Herkunft und einen einzigen
    Hash (den Theme-Bootstrap der bestehenden HTML-Dateien). Ein Skript auf
    einer Studienseite waere still blockiert; ein Inline-Handler ebenso.
    Inline-Styles sind erlaubt (``style-src 'unsafe-inline'``), darauf ruht
    das eingebettete Stylesheet.
    """

    def setUp(self) -> None:
        self.html = st.study_page_html(_studie(), "2026-08-17")

    def test_die_seite_bringt_kein_skript_mit(self) -> None:
        self.assertNotIn("<script", self.html.lower())

    def test_und_keinen_inline_handler(self) -> None:
        for attr in ("onclick=", "onload=", "onerror=", "onmouseover=", "javascript:"):
            with self.subTest(attr=attr):
                self.assertNotIn(attr, self.html.lower())

    def test_sie_laedt_nichts_von_fremden_hosts(self) -> None:
        # default-src 'self': ein Stylesheet oder Bild von aussen waere
        # blockiert und die Seite saehe kaputt aus, ohne dass jemand etwas
        # sieht. Verweise auf fremde Hosts sind nur als Link erlaubt.
        import re

        for tag in re.findall(r"<(link|img|iframe|source)[^>]*>", self.html, re.I):
            self.fail(f"unerwartetes Ladeelement: {tag}")

    def test_das_stylesheet_liegt_in_der_seite(self) -> None:
        # Kein zweiter Abruf, kein Cache-Problem, kein Pfad, der von der
        # Verschachtelungstiefe abhaengt.
        self.assertIn("<style>", self.html)
        self.assertIn("prefers-color-scheme", self.html)


class SitemapTests(unittest.TestCase):
    XML = ('<?xml version="1.0" encoding="UTF-8"?>\n<urlset>\n'
           "  <url>\n    <loc>https://marketintel.dev/</loc>\n  </url>\n</urlset>\n")

    def test_die_studien_landen_in_der_sitemap(self) -> None:
        raus = st.sitemap_mit_studien(self.XML, ["cross-venue", "rewards"], "2026-08-17")
        self.assertIn("<loc>https://marketintel.dev/study/cross-venue/</loc>", raus)
        self.assertIn("<loc>https://marketintel.dev/study/rewards/</loc>", raus)
        self.assertIn("<lastmod>2026-08-17</lastmod>", raus)
        self.assertTrue(raus.rstrip().endswith("</urlset>"))
        # Die vorhandene Adresse bleibt stehen.
        self.assertIn("<loc>https://marketintel.dev/</loc>", raus)

    def test_ein_zweiter_lauf_verdoppelt_nichts(self) -> None:
        einmal = st.sitemap_mit_studien(self.XML, ["cross-venue"], "2026-08-17")
        zweimal = st.sitemap_mit_studien(einmal, ["cross-venue"], "2026-08-17")
        self.assertEqual(einmal, zweimal)

    def test_eine_datei_ohne_urlset_bleibt_unberuehrt(self) -> None:
        self.assertEqual(st.sitemap_mit_studien("kaputt", ["x"], "2026-08-17"), "kaputt")


class BauLaufTests(unittest.TestCase):
    """Der Bau schreibt die Seiten wirklich, und zwar dorthin, wo sie erwartet
    werden. Ein Modul, das die richtige Zeichenkette baut, und ein Bau, der sie
    nirgends ablegt, sind zusammen immer noch nichts."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.ziel = Path(tempfile.mkdtemp(prefix="mi-studies-"))
        cls.lauf = subprocess.run(
            [sys.executable, str(WURZEL / "scripts" / "build_static_site.py"),
             "--out", str(cls.ziel)],
            capture_output=True, text=True, cwd=str(WURZEL))

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.ziel, ignore_errors=True)

    def test_der_bau_laeuft_durch(self) -> None:
        self.assertEqual(self.lauf.returncode, 0, self.lauf.stderr)

    @unittest.skipUnless(NUTZLAST.exists(), "microstructure.json ist nicht publiziert")
    def test_jede_studie_liegt_unter_ihrer_eigenen_adresse(self) -> None:
        payload = json.loads(NUTZLAST.read_text(encoding="utf-8"))
        for studie in payload["studien"]:
            slug = st.study_slug(studie)
            seite = self.ziel / st.STUDY_DIR / slug / "index.html"
            with self.subTest(slug=slug):
                self.assertTrue(seite.exists(), f"{seite} fehlt")
                self.assertIn(str(studie["verdikt"])[:30], seite.read_text(encoding="utf-8"))

    @unittest.skipUnless(NUTZLAST.exists(), "microstructure.json ist nicht publiziert")
    def test_die_sitemap_des_baus_kennt_die_studien(self) -> None:
        xml = (self.ziel / "sitemap.xml").read_text(encoding="utf-8")
        self.assertIn("/study/cross-venue/", xml)
        # Die Startseite ist weiter drin.
        self.assertIn("<loc>https://marketintel.dev/</loc>", xml)

    def test_der_bau_meldet_wie_viele_seiten_entstanden(self) -> None:
        self.assertIn("study page(s) under study/", self.lauf.stdout)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
