"""Die Abbildung roher API-Zeilen auf Anzeigefelder, geprueft auf Einheiten.

``web/js/util.js`` entscheidet, welche Zahl unter welcher Ueberschrift steht.
Der Harness ``tests/web_util_harness.mjs`` ruft die Funktionen mit rohen
Zeilen auf und gibt das Ergebnis als JSON aus; hier steht, was dabei
herauskommen muss.

Ohne node wird uebersprungen, in der CI nicht: dort installiert der Workflow
Node, und ein Test, der sich still ueberspringt, bewacht nichts.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import unittest
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[1]
HARNESS = WURZEL / "tests" / "web_util_harness.mjs"


class WebUtilAbbildungTests(unittest.TestCase):
    ausgabe: dict

    @classmethod
    def setUpClass(cls) -> None:
        node = shutil.which("node")
        if node is None:
            if os.environ.get("CI"):
                raise AssertionError(
                    "node fehlt in der CI, der Einheiten-Test der Weboberflaeche "
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

    def test_volume_24h_bleibt_der_tageswert(self) -> None:
        # Der Rueckfall auf activity_volume schrieb das Lebensvolumen in die
        # Spalte VOLUME 24H: ein Markt ohne Handel am Tag stand dort mit
        # 4.2m und kam durch den Filter "24h-Volumen > $1m".
        ruht = self.ausgabe["ruhender_markt"]
        self.assertEqual(ruht["vol"], 0)
        self.assertEqual(ruht["volTotal"], 4200000)

    def test_das_lebensvolumen_bleibt_erhalten(self) -> None:
        aktiv = self.ausgabe["aktiver_markt"]
        self.assertEqual(aktiv["vol"], 125000)
        self.assertEqual(aktiv["volTotal"], 900000)

    def test_preis_und_liquiditaet_behalten_ihre_einheit(self) -> None:
        ruht = self.ausgabe["ruhender_markt"]
        self.assertEqual(ruht["yes"], 62)
        self.assertEqual(ruht["chg"], 1)
        self.assertEqual(ruht["liq"], 15000)
        self.assertEqual(ruht["_extra"]["spread"], 2)
        # Keine gemeldete Liquiditaet bleibt null und wird in der Tabelle zum
        # Strich, nicht zu einer gemessenen Null.
        self.assertEqual(self.ausgabe["aktiver_markt"]["liq"], 0)

    def test_ein_print_wird_in_dollar_und_cent_gelesen(self) -> None:
        print_ = self.ausgabe["no_print"]
        self.assertEqual(print_["price"], "15.0¢")
        self.assertEqual(print_["size"], 30)

    def test_eine_studienadresse_findet_ihre_studie_auch_mit_bindestrich(self) -> None:
        # Der Eintrag in der Seitenleiste heisst "Post-mortems", die Studie
        # selbst "Postmortems". Wer die Beschriftung abschreibt, tippt
        # #research/post-mortems, und das zeigte auf keine Studie. Die Seite
        # blieb dann still auf dem Reiter stehen, der vorher offen war: die
        # Adresse sagte das eine, die Seite zeigte das andere.
        a = self.ausgabe["studien_adressen"]
        self.assertIn("postmortems", a["kanonisch"])
        self.assertEqual(a["postmortems"], a["mit_bindestrich"])
        self.assertEqual(a["postmortems"], a["mit_unterstrich_und_gross"])
        self.assertGreaterEqual(a["postmortems"], 0)
        # Umgekehrt genauso: die kanonische Adresse traegt den Bindestrich,
        # die Schreibweise ohne muss trotzdem ankommen.
        self.assertIn("field-notes", a["kanonisch"])
        self.assertEqual(a["feldnotizen_mit_strich"], a["feldnotizen_ohne_strich"])

    def test_ein_segment_ohne_studie_bleibt_ohne_studie(self) -> None:
        # Grosszuegig heisst nicht wahllos: was auf nichts zeigt, findet auch
        # nichts, und die Seite rueckt dann die Adresse zurecht.
        a = self.ausgabe["studien_adressen"]
        self.assertEqual(a["unbekannt"], -1)
        self.assertEqual(a["leer"], -1)
        self.assertEqual(a["nichts"], -1)

    def test_geldformat(self) -> None:
        self.assertEqual(self.ausgabe["geld"]["null"], "$0")
        self.assertEqual(self.ausgabe["geld"]["tausend"], "$1.5k")
        self.assertEqual(self.ausgabe["geld"]["million"], "$4.20m")

    def test_die_kopfzeile_behauptet_keine_venue_die_nicht_geantwortet_hat(self) -> None:
        # Die Zeile stand fest auf "LIVE, POLYMARKET + KALSHI". Faengt
        # /api/tape einen Parserfehler auf einer Venue ab, damit die andere
        # nicht mit ausfaellt, war die halbe Antwort von einer ganzen nicht
        # zu unterscheiden.
        zeile = self.ausgabe["statuszeile"]
        self.assertEqual(zeile["beide"], "LIVE · POLYMARKET + KALSHI")
        self.assertNotIn("KALSHI", zeile["kalshi_fehlt"].split("ONLY")[0])
        self.assertIn("POLYMARKET ONLY", zeile["kalshi_fehlt"])
        self.assertIn("KALSHI NOT ANSWERING", zeile["kalshi_fehlt"])
        self.assertIn("KALSHI ONLY", zeile["polymarket_fehlt"])
        self.assertIn("NO VENUE ANSWERING", zeile["keine"])
        # Die anderen Zustaende bleiben, wie sie waren.
        self.assertEqual(zeile["fehler"], "API OFFLINE · LAST KNOWN STATE")
        self.assertEqual(zeile["wartet"], "WAITING FOR API")
