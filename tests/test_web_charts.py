"""Die Diagramme der Werkzeugseiten: da, beschriftet, und ohne Daten leer.

Der Design-Review vom 2026-08-28 hat auf den Werkzeugseiten null SVG bei rund
dreissig Kennzahlenkacheln gezaehlt (Abschnitt B.0). Hier steht, was jedes
neue Diagramm liefern muss, damit die Zaehlung nicht wieder auf null faellt
und die Diagramme nicht das kaputtmachen, was das Projekt an Einheiten
sortiert hat:

1. Ohne Nutzlast kein Diagramm. Eine Achse ueber leerer Flaeche ist eine
   Behauptung.
2. Mit Nutzlast ein Diagramm, und beide Achsen tragen ihre Einheit im
   Klartext. Dollar, Cent, Kontrakte und Wahrscheinlichkeiten stehen im
   Terminal nebeneinander; eine Achse ohne Einheit macht sie wieder gleich.
3. Jede Marke traegt einen Tooltip.
4. Score-Diagramme tragen n, Intervall, Sample-Abzeichen und Stichtag.

Gerendert wird ueber denselben Node-Harness wie tests/test_web_leerzustand.py.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import claims  # noqa: E402

WURZEL = Path(__file__).resolve().parents[1]
HARNESS = WURZEL / "tests" / "web_render_harness.mjs"

#: Werkzeugseiten, die mit Nutzlast ein Diagramm zeichnen muessen.
SEITEN_MIT_DIAGRAMM = ("traders", "wallet", "risk", "markets_verteilung", "backtester_stats")

#: Je Seite die Achsenbeschriftungen, die im Klartext dastehen muessen.
#: Dollar, Cent, Kontrakte und Wahrscheinlichkeiten stehen im Terminal
#: nebeneinander; eine Achse ohne Einheit macht sie wieder gleich.
ACHSEN_MIT_EINHEIT = {
    "traders": ["smart score (points out of 100)", "volume traded (USD, log)"],
    "wallet": ["at stake (USD)"],
    "risk": ["insider-pattern score (points out of 100)", "markets screened"],
    "markets_verteilung": ["yes price (cents)", "markets in the sample"],
    "backtester_stats": ["result per closed copy (USD)", "closed copies"],
}


def _svg_zahl(html: str) -> int:
    return html.count("<svg")


class WebDiagrammTest(unittest.TestCase):
    ausgabe: dict

    @classmethod
    def setUpClass(cls) -> None:
        node = shutil.which("node")
        if node is None:
            if os.environ.get("CI"):
                raise AssertionError(
                    "node fehlt in der CI, der Diagrammtest der Weboberflaeche "
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

    # -- 1. Ohne Nutzlast kein Diagramm ------------------------------------
    def test_ohne_nutzlast_zeichnet_keine_werkzeugseite(self) -> None:
        for seite in ("traders", "markets", "risk", "backtester", "wallet"):
            with self.subTest(seite=seite):
                self.assertEqual(
                    _svg_zahl(self.ausgabe["leer"][seite]), 0,
                    f"{seite} zeichnet ohne Nutzlast ein SVG")

    # -- 2. Mit Nutzlast ein Diagramm je Werkzeugseite ----------------------
    def test_mit_nutzlast_zeichnen_die_werkzeugseiten(self) -> None:
        for seite in SEITEN_MIT_DIAGRAMM:
            with self.subTest(seite=seite):
                self.assertGreaterEqual(
                    _svg_zahl(self.ausgabe["live"][seite]), 1,
                    f"{seite} hat mit Nutzlast kein SVG")

    # -- 3. Achsen mit Einheit --------------------------------------------
    def test_jede_achse_nennt_ihre_einheit(self) -> None:
        for seite, achsen in ACHSEN_MIT_EINHEIT.items():
            html = self.ausgabe["live"][seite]
            for achse in achsen:
                with self.subTest(seite=seite, achse=achse):
                    self.assertIn(achse, html)

    # -- 4. Jede Marke traegt einen Tooltip --------------------------------
    def test_marken_tragen_tooltips(self) -> None:
        for seite in SEITEN_MIT_DIAGRAMM:
            html = self.ausgabe["live"][seite]
            svgs = re.findall(r"<svg.*?</svg>", html, flags=re.S)
            treffer = [s for s in svgs if "<title>" in s]
            with self.subTest(seite=seite):
                self.assertTrue(treffer, f"{seite}: kein SVG mit Tooltip")

    # -- 5. Score-Diagramme tragen n, Intervall, Sample und Stichtag --------
    def test_score_punktwolke_traegt_n_intervall_sample_und_stichtag(self) -> None:
        html = self.ausgabe["live"]["traders"]
        self.assertIn("SCORE AGAINST THE EVIDENCE UNDER IT", html)
        # n
        self.assertIn("n = 250 wallets", html)
        # Intervall, ausdruecklich nicht als Konfidenzintervall verkauft
        self.assertIn("unmeasured range", html)
        self.assertIn('data-caveat="composite_range_not_ci"', html)
        self.assertIn(claims.disclaimer("composite_range_not_ci", "en"), html)
        # Sample-Abzeichen
        self.assertIn("Sample: part measured", html)
        # Stichtag
        self.assertIn("Snapshot 2026-08-07", html)

    def test_wallet_zeigt_positionen_als_balken_und_die_treemap_mit_schluessel(self) -> None:
        """Laenge auf gemeinsamer Grundlinie statt Flaechenvergleich.

        Die Treemap bleibt als zweite Ansicht, aber nur mit einem Schluessel
        fuer ihre Farbintensitaet: ohne ihn ist ein dunkleres Gruen nur
        dunkler.
        """

        balken = self.ausgabe["live"]["wallet"]
        self.assertIn("POSITIONS BY SIZE", balken)
        self.assertIn("bar length = stake, colour = profit or loss", balken)
        treemap = self.ausgabe["live"]["wallet_treemap_alle"]
        self.assertIn("POSITIONS TREEMAP", treemap)
        self.assertIn("RESULT vs STAKE", treemap)
        # Und kein hartes Dunkel mehr hinter den Kacheln.
        self.assertNotIn("#0D1114", treemap)

    def test_risk_zeigt_die_score_verteilung_mit_beiden_bandgrenzen(self) -> None:
        """Der Trichter zaehlt drei Stufen, das Histogramm zeigt die Form."""

        html = self.ausgabe["live"]["risk"]
        self.assertIn("WHERE THE SCORES SIT", html)
        self.assertIn("flag 40", html)
        self.assertIn("high 70", html)
        # Geflaggte Teilmenge als zweite Lage, mit Legende statt nur Farbe.
        self.assertIn("flagged, gets a card", html)
        self.assertIn("screened", html)
        # Der Screen-Vorbehalt steht im Kopf der Seite, aus dem Register,
        # und genau einmal: nicht noch einmal unter dem Bild.
        self.assertIn('data-caveat="screen_not_proof"', html)
        self.assertEqual(html.count(claims.disclaimer("screen_not_proof", "en")), 1)

    def test_markets_zeigt_die_preisverteilung_in_cent(self) -> None:
        """Cent, nicht Dollar, und ausdruecklich nicht das Volumen.

        Der YES-Preis ist auf beiden Boersen dieselbe Groesse. Das Volumen
        ist es nicht (Polymarket meldet Dollar, Kalshi zaehlt Kontrakte,
        app/venue_units.py), deshalb steht es nicht in diesem Bild, und die
        Fussnote sagt warum.
        """

        html = self.ausgabe["live"]["markets_verteilung"]
        self.assertIn("WHAT THE SAMPLE BELIEVES", html)
        self.assertIn("yes price (cents)", html)
        self.assertIn("Kalshi counts in contracts", html)
        # Ein einzelner Markt ergibt kein Histogramm.
        self.assertNotIn("WHAT THE SAMPLE BELIEVES", self.ausgabe["live"]["markets"])

    def test_backtester_zeigt_verteilung_und_konzentration(self) -> None:
        """Traegt das Ergebnis eine Reihe von Trades oder drei?"""

        html = self.ausgabe["live"]["backtester_stats"]
        self.assertIn("RESULT PER CLOSED COPY", html)
        self.assertIn("break even", html)
        self.assertIn("The three largest winners carry 38% of the gross profit", html)
        # Modelliert, nicht realisiert: der Vorbehalt steht am Bild.
        # Wie beim Risk-Screen: der Vorbehalt gilt dem ganzen Lauf, steht
        # im Kopf und dort nur einmal.
        self.assertIn('data-caveat="backtest_modeled"', html)
        self.assertEqual(html.count(claims.disclaimer("backtest_modeled", "en")), 1)
        # Ohne Lauf kein Diagramm.
        self.assertNotIn("RESULT PER CLOSED COPY", self.ausgabe["live"]["backtester"])

    def test_live_runs_zeigt_die_trefferquote_mit_ihrer_spanne(self) -> None:
        """Kein Diagramm, sondern eine Intervall-Marke.

        Bei n unter etwa fuenfzig ist die Spanne die Information; eine
        Verteilung ueber drei aufgeloeste Maerkte waere Zierrat.
        """

        html = self.ausgabe["live"]["runs_runs"]
        self.assertIn("WIN RATE", html)
        self.assertIn("95% 21% to 94%", html)
        self.assertIn("wallet ledger", html)
        # Die Marke traegt ihre Skala und ihren Text fuer Screenreader.
        self.assertIn("win rate 67%, 95% Wilson interval 21% to 94%, n 3", html)
        self.assertIn(">0%<", html)
        self.assertIn(">100%<", html)

    def test_der_score_aufbau_wird_genau_einmal_erklaert(self) -> None:
        """Anteil und Kohorten-n stehen im Basis-Satz, nicht auch im Bild.

        Der Basis-Satz ueber dem Diagramm (scoreBasisSatz, Zwilling von
        api_views.score_basis_note) ist die eine Erklaerung. Stuende der
        gemessene Anteil zusaetzlich unter dem Diagramm, gaebe es zwei
        Lesarten derselben Groesse in zwei Formulierungen.
        """

        html = self.ausgabe["live"]["traders"]
        text = re.sub(r"<[^>]*>", " ", re.sub(r"<title>.*?</title>", " ", html, flags=re.S))
        self.assertEqual(text.count("of the composite weight rests on"), 1)
        self.assertEqual(text.count("wallets ranked together"), 1)
        # Und die Spanne wird nicht zusaetzlich in eigenen Worten erklaert.
        self.assertNotIn("Horizontal bar:", text)

    def test_punktwolke_faerbt_keinen_text_mit_der_datenfarbe(self) -> None:
        """Text traegt Ink-Stufen, Marken tragen die Serienfarbe."""

        html = self.ausgabe["live"]["traders"]
        for treffer in re.findall(r"<text[^>]*>", html):
            with self.subTest(knoten=treffer[:80]):
                self.assertNotRegex(treffer, r"fill:var\(--s[0-9]\)")

    def test_kein_textknoten_unter_der_hellen_aa_schwelle(self) -> None:
        """Ink-Stufen unter .55 bestehen auf dem hellen Grund kein AA.

        Gemessen mit --ink 0,0,0 auf --bg #F4F1EA: .55 ergibt 4.62:1, .50
        nur 3.88:1. Die Diagrammtexte tragen deshalb Ink-Stufen, und die
        schwaechste davon (--ink-4) ist genau die Untergrenze: .55 im
        dunklen, .58 im hellen Thema. Roh geschriebene Alphas werden hier
        weiterhin gelesen, damit eine neue Aufrufstelle die Leiter nicht
        umgehen kann.
        """

        # Die Werte stammen aus web/css/terminal.css, dunkles Thema.
        stufe_je_token = {"--ink-1": 0.85, "--ink-2": 0.7, "--ink-3": 0.6, "--ink-4": 0.55}
        stufen = set()
        for seite in SEITEN_MIT_DIAGRAMM:
            html = self.ausgabe["live"][seite]
            for svg in re.findall(r"<svg.*?</svg>", html, flags=re.S):
                for treffer in re.findall(r"<text[^>]*fill:rgba\(var\(--ink\),\s*(\.[0-9]+)\)", svg):
                    stufen.add(float(treffer))
                for token in re.findall(r"<text[^>]*fill:var\((--[a-z0-9-]+)\)", svg):
                    with self.subTest(token=token):
                        self.assertIn(token, stufe_je_token, "Textknoten ausserhalb der Ink-Leiter")
                    stufen.add(stufe_je_token.get(token, 0.0))
        self.assertTrue(stufen, "keine gemessenen Textstufen gefunden")
        for stufe in sorted(stufen):
            with self.subTest(stufe=stufe):
                self.assertGreaterEqual(stufe, 0.55)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
