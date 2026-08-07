"""Die Weboberflaeche darf ohne Daten keine Zahl zeigen.

Die Seiten unter web/js sind reine Funktionen ueber ein Zustandsobjekt. Der
Harness tests/web_render_harness.mjs rendert jede von ihnen zweimal, einmal
ohne jede Nutzlast und einmal mit einer minimalen echten, und gibt das
Ergebnis als JSON aus. Hier wird geprueft, was dabei herauskommen muss:

1. Keine Seite bricht beim Rendern ab, in keinem der beiden Zustaende.
2. Im Leerzustand taucht keiner der frueheren Demo-Werte mehr auf.
3. Im Leerzustand nennt jede betroffene Seite die fehlende Quelle.
4. Mit Daten stehen die echten Werte da, nicht der Leerzustand.

Ohne node wird uebersprungen; die Suite laeuft auch auf Maschinen ohne
Node-Installation durch.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[1]
HARNESS = WURZEL / "tests" / "web_render_harness.mjs"

# Werte, die frueher erschienen, sobald die API schwieg. Jeder einzelne stand
# unter einer Ueberschrift, die ihn als Messung auswies.
ERFUNDENE_WERTE = [
    "1,284",        # MARKETS TRACKED
    "84.2m",        # VOLUME 24H
    "+12.4%",       # "vs yesterday"
    "Theo4",        # BEST WALLET
    "22.05m",       # dessen Gewinn
    "61.4m",        # Volumen Polymarket
    "22.8m",        # Volumen Kalshi
    "1,043.18",     # Papierkonto in der Seitenleiste
    "18.4m",        # Whale-Flow Gesamtsumme
    "214k",         # groesster Print
    "1,208",        # Wetten der Live-Laeufe
    "780 ms",       # Median-Latenz
    "chat 4711",    # angeblich geprueftes Telegram-Ziel
    "hits today",   # feste Trefferzahlen der Alarm-Regeln
]

# Je Seite ein Text, der im Leerzustand dastehen muss.
LEER_ERWARTET = {
    "overview": "/api/markets",
    "markets": "/api/markets",
    "flow": "/api/tape",
    "cross": "/api/cross",
    "resolved": "/api/resolved",
    "traders": "/api/leaderboard",
    "whale": "/api/tape",
    "risk": "/api/risk",
    "alerts": "/api/alerts",
    "track": "/api/track",
}


def _sichtbarer_text(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]*>", " ", html)).strip()


class WebLeerzustandTest(unittest.TestCase):
    ausgabe: dict

    @classmethod
    def setUpClass(cls) -> None:
        node = shutil.which("node")
        if node is None:
            raise unittest.SkipTest("node ist nicht installiert")
        lauf = subprocess.run(
            [node, str(HARNESS)],
            cwd=str(WURZEL),
            capture_output=True,
            text=True,
            timeout=120,
        )
        if lauf.returncode != 0:
            raise AssertionError(f"Harness brach ab:\n{lauf.stderr}")
        cls.ausgabe = json.loads(lauf.stdout)

    def test_jede_seite_rendert(self) -> None:
        for modus in ("leer", "live"):
            for name, html in self.ausgabe[modus].items():
                with self.subTest(modus=modus, seite=name):
                    self.assertNotIn("RENDER-FEHLER", html)

    def test_leerzustand_ohne_erfundene_werte(self) -> None:
        for name, html in self.ausgabe["leer"].items():
            text = _sichtbarer_text(html)
            for wert in ERFUNDENE_WERTE:
                with self.subTest(seite=name, wert=wert):
                    self.assertNotIn(wert, text)

    def test_leerzustand_nennt_die_quelle(self) -> None:
        for seite, quelle in LEER_ERWARTET.items():
            text = _sichtbarer_text(self.ausgabe["leer"][seite])
            with self.subTest(seite=seite):
                self.assertIn(quelle, text)

    def test_leerzustand_zeichnet_keine_kurve(self) -> None:
        # Ein polyline mit Punkten ist eine Behauptung ueber einen Verlauf.
        for name, html in self.ausgabe["leer"].items():
            with self.subTest(seite=name):
                self.assertNotRegex(html, r'<polyline points="\s*\d')

    def test_mit_daten_echte_werte(self) -> None:
        text = _sichtbarer_text(self.ausgabe["live"]["overview"])
        self.assertIn("$125k", text)
        self.assertNotIn("Waiting for /api/markets", text)
        whale = _sichtbarer_text(self.ausgabe["live"]["whale"])
        self.assertIn("$9.0k", whale)

    def test_backtester_nennt_das_gebuehrenmodell(self) -> None:
        # Voreinstellung ist die Venue-Kurve, und der Kopf des Laufs sagt es.
        kurve = _sichtbarer_text(self.ausgabe["leer"]["backtester_advanced"])
        self.assertIn("FEE MODEL", kurve)
        self.assertIn("fees on the venue curve", kurve)
        self.assertIn("250 bps", kurve)
        # Der pauschale Satz bleibt erreichbar und wird als solcher benannt.
        flach = _sichtbarer_text(self.ausgabe["leer"]["backtester_flat_fee"])
        self.assertIn("FLAT FEE (BPS)", flach)
        self.assertIn("fees 20 bps flat", flach)

    def test_regel_treffer_kommen_aus_dem_feed(self) -> None:
        # Der Feed traegt genau einen Whale-Print, also steht dort eine 1 und
        # bei den uebrigen eingeschalteten Regeln eine 0.
        leer = _sichtbarer_text(self.ausgabe["leer"]["alerts_rules"])
        self.assertIn("no feed loaded", leer)
        live = _sichtbarer_text(self.ausgabe["live"]["alerts_rules"])
        self.assertNotIn("no feed loaded", live)
        # Gezaehlt wird der ganze Scan, nicht die abgeschnittene Tabelle: der
        # Feed traegt eine Whale-Zeile, der Scan meldet fuenf.
        self.assertIn("5 in this scan", live)
        self.assertIn("0 in this scan", live)
        # Eine nicht ausgewertete Regel meldet keine Null.
        self.assertIn("not evaluated by this endpoint", live)

    def test_abgeschnittene_signalliste_sagt_es(self) -> None:
        live = _sichtbarer_text(self.ausgabe["live"]["alerts"])
        self.assertIn("showing the top 60 of 125 signals", live)

    def test_seitenleiste_ohne_papierstand(self) -> None:
        # Die Seitenleiste wird nicht ueber den Harness gerendert, sie haengt
        # an app.js. Geprueft wird deshalb die Quelle: der feste Betrag darf
        # dort nicht mehr stehen.
        quelltext = (WURZEL / "web" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertNotIn("1043.18", quelltext)
        self.assertNotIn("4.3;", quelltext)

    def test_kein_kurvengenerator_mehr(self) -> None:
        # curve() war der Zufallspfad mit einstellbarem Aufwaertsdrift.
        for datei in (WURZEL / "web" / "js").rglob("*.js"):
            quelltext = datei.read_text(encoding="utf-8")
            with self.subTest(datei=datei.name):
                self.assertNotRegex(quelltext, r"\bexport function curve\b")

    def test_keine_demo_fixtures_mehr(self) -> None:
        self.assertFalse((WURZEL / "web" / "js" / "demo_data.js").exists())
        for datei in (WURZEL / "web" / "js").rglob("*.js"):
            quelltext = datei.read_text(encoding="utf-8")
            with self.subTest(datei=datei.name):
                self.assertNotIn("demo_data.js", quelltext)


if __name__ == "__main__":
    unittest.main()
