"""Richtung, Ergebnis und Filter der Live-Tape-Zeilen (web/js/util.js).

Der Fehler, den diese Datei festhaelt: Richtung und Ergebnis eines Prints
standen nur als zusammengesetztes Etikett ("BUY yes") da, und die Filter
suchten darin mit indexOf. Kalshi liefert seine Seite klein geschrieben
(``taker_side``/``taker_outcome_side``, src/prediction_markets.py), also
liess die Auswahl OUTCOME = Yes jeden Kalshi-Print fallen; umgekehrt kam
jeder Print eines Mehrfachmarktes mit dem Ergebnisnamen "November" durch die
Auswahl OUTCOME = No, weil "November" die Zeichenkette "No" enthaelt.

Der Harness tests/web_tape_harness.mjs ruft die Helfer ohne Browser auf und
gibt das Ergebnis als JSON aus. Ohne node wird uebersprungen, in der CI
nicht.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import unittest
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[1]
HARNESS = WURZEL / "tests" / "web_tape_harness.mjs"


class WebTapeTest(unittest.TestCase):
    ausgabe: dict

    @classmethod
    def setUpClass(cls) -> None:
        node = shutil.which("node")
        if node is None:
            if os.environ.get("CI"):
                raise AssertionError(
                    "node fehlt in der CI — der Tape-Test der Weboberflaeche "
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

    def test_richtung_je_venue(self) -> None:
        # Kalshi kennt keine Verkaufsseite im Tape: der Taker kauft die
        # Seite, die in derselben Spalte steht. Nur Polymarkets SELL ist ein
        # Verkauf.
        self.assertEqual(self.ausgabe["richtung"], ["BUY", "SELL", "BUY", "BUY", "BUY"])

    def test_ergebnis_schreibweise_vereinheitlicht(self) -> None:
        self.assertEqual(self.ausgabe["ergebnis"], ["Yes", "No", "No", "Yes", "November"])
        self.assertEqual(
            self.ausgabe["etikett"],
            ["BUY Yes", "SELL No", "BUY No", "BUY Yes", "BUY November"])

    def test_outcome_filter_nimmt_kalshi_mit(self) -> None:
        yes = self.ausgabe["outcome_yes"]
        no = self.ausgabe["outcome_no"]
        # Vorher war diese Liste leer von Kalshi-Zeilen.
        self.assertTrue(any(eintrag.split("|")[1] == "Kalshi" for eintrag in yes), yes)
        self.assertTrue(any(eintrag.split("|")[1] == "Kalshi" for eintrag in no), no)
        self.assertEqual(len(yes), 2)
        self.assertEqual(len(no), 2)

    def test_outcome_no_faengt_keinen_namen_mit_no_darin(self) -> None:
        # "November" enthaelt "No"; die Auswahl No darf diesen Print nicht
        # mitzaehlen.
        self.assertFalse(
            any("November" in eintrag for eintrag in self.ausgabe["outcome_no"]),
            self.ausgabe["outcome_no"])

    def test_kauf_und_verkauf_summieren_sich_zum_gesamt(self) -> None:
        kauf = self.ausgabe["side_buy_summe"]
        verkauf = self.ausgabe["side_sell_summe"]
        self.assertEqual(kauf + verkauf, self.ausgabe["gesamt_summe"])
        # 250 + 300 + 200 + 500 aus dem Harness; nur der Polymarket-SELL
        # (300) faellt auf die Verkaufsseite.
        self.assertEqual(kauf, 1250)
        self.assertEqual(verkauf, 300)

    def test_notional_in_dollar_nicht_in_anteilen(self) -> None:
        # size ist der Dollarbetrag des Prints (notional), nicht die Zahl der
        # Anteile: 1000 Anteile zu 25 Cent sind $250, nicht 1000.
        self.assertEqual(self.ausgabe["groesse"], [250, 300, 300, 200, 500])

    def test_helfer_normalisieren_einzeln(self) -> None:
        h = self.ausgabe["helfer"]
        self.assertEqual(h["dir_sell"], "SELL")
        self.assertEqual(h["dir_kalshi_no"], "BUY")
        self.assertEqual(h["dir_leer"], "BUY")
        self.assertEqual(h["out_klein"], "No")
        self.assertEqual(h["out_gross"], "No")
        self.assertEqual(h["out_leer"], "Yes")
        self.assertEqual(h["out_name"], "November")

    def test_platform_filter_trifft_kalshi(self) -> None:
        self.assertEqual(self.ausgabe["kalshi_only"], 2)

    def test_fenster_nennt_die_spanne_je_venue(self) -> None:
        """TOTAL MOVED und $ GROUPED sind Summen ueber eine Spanne, die nirgends stand.

        Beide Venues bekommen gleich viele Zeilen (api_views.balanced_head),
        aber Kalshis 15-Minuten-Kryptomaerkte drucken um Groessenordnungen
        schneller. Im Harness deckt Polymarket 360 Minuten ab und Kalshi 2 —
        dieselbe Zeilenzahl, zwei verschiedene Fenster. Eine Summe ueber
        beide ohne diese Angabe laesst sich nicht einordnen.
        """

        fenster = self.ausgabe["fenster"]
        self.assertEqual(fenster["prints"], 5)
        self.assertEqual(fenster["minuten"], 360)
        je = {v["venue"]: v for v in fenster["jeVenue"]}
        self.assertEqual(je["Polymarket"]["minuten"], 360)
        self.assertEqual(je["Kalshi"]["minuten"], 2)
        satz = self.ausgabe["fenster_satz"]
        self.assertIn("Window: 6.0 h · 5 prints", satz)
        self.assertIn("Kalshi 2 min (2)", satz)
        self.assertIn("Polymarket 6.0 h (3)", satz)

    def test_fenster_ohne_zeit_erfindet_keine_spanne(self) -> None:
        self.assertIsNone(self.ausgabe["fenster_leer"])
        self.assertIsNone(self.ausgabe["fenster_ohne_zeit"])

    def test_dauer_formatiert_ohne_falsche_genauigkeit(self) -> None:
        self.assertEqual(self.ausgabe["dauer"], ["<1 min", "42 min", "6.0 h", "3.0 d"])


if __name__ == "__main__":
    unittest.main()
