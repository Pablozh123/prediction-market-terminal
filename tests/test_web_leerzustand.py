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
import os
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

# Werte, die auch mit einer echten, aber leeren Antwort nicht erscheinen
# duerfen: die Rueckfaelle der Copy- und Portfolio-Reiter griffen genau dann,
# wenn die API antwortete, das Buch aber leer war.
ERFUNDENE_WERTE_LIVE = [
    "312.40",          # CASH FREE
    "28.60",           # UNREALISED
    "$268 · 26%",      # Konzentration: groesste Position
    "$641 · 61%",      # Konzentration: Top drei
    "$392 · 38%",      # Konzentration: Aufloesung in 7 Tagen
    "$312 · 23%",      # Konzentration: freie Kasse
    "$412",            # Allokation MACRO
    "-$11.40",         # Fidelity: Kasse leer
    "-$4.20",          # Fidelity: schlechterer Preis
    "-$16.50",         # Fidelity: Summe
    "last sync 40 s",  # erfundene Sync-Zeiten
    "Swisstony",       # fest verdrahteter Wallet-Name in der Legende
    "900 ms",          # synthetische Latenz (900 + i * 140) fuer i = 0
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
            # Lokal ohne Node ueberspringen, in der CI nicht: ein Test, der
            # sich dort still ueberspringt, bewacht nichts. Die CI-Definition
            # installiert Node, und wenn dieser Schritt je verschwindet, soll
            # es hier auffallen statt in einer gruenen Zusammenfassung.
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
        # Ein polyline mit Punkten ist eine Behauptung ueber einen Verlauf,
        # ein path mit Koordinaten (die Treppenkurve aus charts.js) genauso.
        for name, html in self.ausgabe["leer"].items():
            with self.subTest(seite=name):
                self.assertNotRegex(html, r'<polyline points="\s*\d')
                self.assertNotRegex(html, r'<path d="M\s*\d')

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
        # Eine Art, die der Schnitt komplett verschluckt, wird benannt —
        # sonst widerspricht ihre Regelkarte scheinbar der Tabelle.
        self.assertIn("none of ENDING SOON (120) made the cut", live)
        # Eine Art mit null Treffern gehoert nicht in diese Aufzaehlung.
        self.assertNotIn("FAST MOVER (0)", live)

    def test_regelschalter_blenden_aus_und_sagen_es(self) -> None:
        live = _sichtbarer_text(self.ausgabe["live"]["alerts"])
        # Der Tight-Spread-Schalter steht aus, also faellt die Zeile weg und
        # die Seite schreibt hin, dass sie sie ausblendet.
        self.assertIn("1 signal hidden by the rule switches", live)
        self.assertNotIn("TIGHT SPREAD", live)
        # Eingeschaltete Arten und Arten ohne Schalter bleiben stehen.
        self.assertIn("WHALE PRINT", live)
        self.assertIn("WATCHED MARKET", live)

    def test_seite_behauptet_keinen_telegram_versand(self) -> None:
        for modus in ("leer", "live"):
            text = _sichtbarer_text(self.ausgabe[modus]["alerts"])
            with self.subTest(modus=modus):
                self.assertNotIn("Switch one on and it also goes to Telegram", text)
                self.assertIn("configured on the scanner", text)

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

    def test_papierbuch_ohne_positionen_ohne_zahlen(self) -> None:
        # Der Harness liefert Status und Kennzahlen, aber kein Buch. Genau
        # dann griffen frueher die Rueckfaelle der Copy- und Portfolio-Reiter.
        for name in ("copy", "copy_fidelity", "portfolio", "portfolio_exposure"):
            text = _sichtbarer_text(self.ausgabe["live"][name])
            for wert in ERFUNDENE_WERTE_LIVE:
                with self.subTest(seite=name, wert=wert):
                    self.assertNotIn(wert, text)
        exposure = _sichtbarer_text(self.ausgabe["live"]["portfolio_exposure"])
        self.assertIn("nothing to break down", exposure)
        fidelity = _sichtbarer_text(self.ausgabe["live"]["copy_fidelity"])
        self.assertIn("fidelity_detail is missing", fidelity)
        # Der Daemon-Zustand kommt aus der Antwort: running true heisst RUNNING.
        copy = _sichtbarer_text(self.ausgabe["live"]["copy"])
        self.assertIn("RUNNING", copy)
        self.assertNotIn("STATE NOT REPORTED", copy)
        # Ohne gemessene Latenz steht ein Strich, keine Zahl in Millisekunden.
        self.assertNotRegex(copy, r"\d+ ms")

    def test_keine_toten_knoepfe(self) -> None:
        # Jeder dieser Knoepfe stand als gestyltes Div ohne Handler da.
        tot = ["Sign in", "Get alerts", "Save this view", "Export trade log CSV",
               "Watch this market", "Follow on paper", "Mirror this on paper",
               "Save this setup", "Sync now", "Seed baseline", "Stop the copier",
               "Start the copier", "Export CSV", "Open on Polymarket", "Open on Kalshi"]
        for modus in ("leer", "live"):
            for name, html in self.ausgabe[modus].items():
                text = _sichtbarer_text(html)
                for knopf in tot:
                    with self.subTest(modus=modus, seite=name, knopf=knopf):
                        self.assertNotIn(knopf, text)
        app_js = (WURZEL / "web" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertNotIn(">Sign in<", app_js)
        self.assertNotIn(">Get alerts<", app_js)

    def test_kopfzeile_auf_englisch_und_ohne_demo(self) -> None:
        app_js = (WURZEL / "web" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertNotIn("DEMO-DATEN", app_js)
        self.assertNotIn("API GETRENNT", app_js)
        self.assertNotIn("live: 'demo'", app_js)
        self.assertIn("WAITING FOR API", app_js)
        self.assertIn("API OFFLINE · LAST KNOWN STATE", app_js)

    def test_forschungsknoepfe_tun_etwas(self) -> None:
        # "Download the data" ist ein Link auf die publizierte Datei der
        # Studie, "Read the method" fuehrt zur Methodik. Auf der Methodik
        # selbst gibt es keinen Verweis auf sich selbst.
        live = self.ausgabe["live"]
        # Reiter 0 (Review queue) traegt im Harness eine Nutzlast.
        self.assertIn('href="./data/queue.json"', live["research"])
        self.assertIn("Read the method", _sichtbarer_text(live["research"]))
        self.assertIn('href="./data/audit.json"', live["research_methodology"])
        self.assertNotIn("Read the method", _sichtbarer_text(live["research_methodology"]))
        # Ohne Nutzlast gibt es keine Datei zum Herunterladen und keine Knoepfe.
        self.assertNotIn("Download the data", _sichtbarer_text(self.ausgabe["leer"]["research"]))

    def test_studienkarte_fuehrt_mit_befund_und_klappt_methode_zu(self) -> None:
        # Verdikt und Diagramm stehen offen, Methode und Deutung liegen in
        # einem <details> — vorhanden, aber nicht zwischen Leser und Befund.
        live = self.ausgabe["live"]["research_microstructure"]
        text = _sichtbarer_text(live)
        self.assertIn("METHOD &amp; HOW TO READ IT", live)
        self.assertIn("Does the harness study render?", text)
        self.assertIn("Harness interval", text)
        self.assertIn("<details", live)
        # Der Methodentext steht im Dokument (nichts ist geloescht) …
        self.assertIn("Harness method text.", text)
        # … und zwar erst nach dem Diagramm, nicht davor.
        self.assertLess(live.index("Harness interval"), live.index("Harness method text."))
        # Leerzustand nennt die Datei, wie bisher.
        leer = _sichtbarer_text(self.ausgabe["leer"]["research_microstructure"])
        self.assertIn("microstructure.json", leer)

    def test_laeufe_ohne_fill_werden_einzeilig(self) -> None:
        live = _sichtbarer_text(self.ausgabe["live"]["runs_runs"])
        self.assertIn("RUNS WITHOUT A FILL · 2", live)
        self.assertIn("Run with a fill", live)
        self.assertIn("Run without a fill", live)
        # Die Einzeiler tragen keine Stake-Fusszeile — die gehoert zur Karte.
        self.assertNotIn("Stake $0.00", live)

    def test_laufkurve_kommt_aus_den_laufwerten(self) -> None:
        # Vier Laeufe mit publizierten PnL-Werten ergeben eine Treppenkurve;
        # ohne Nutzlast gibt es keine (test_leerzustand_zeichnet_keine_kurve).
        live = self.ausgabe["live"]["runs_runs"]
        self.assertIn("CUMULATIVE REALIZED PNL BY RUN", _sichtbarer_text(live))
        self.assertRegex(live, r'<path d="M\s*\d')
        # Der Hinweis nennt den wallet-abgeglichenen Wert aus der Nutzlast.
        self.assertIn("wallet-reconciled net +$20", _sichtbarer_text(live))

    def test_startseite_leerpanels_sind_verweise(self) -> None:
        leer = _sichtbarer_text(self.ausgabe["leer"]["overview"])
        self.assertIn("Open Leaderboard", leer)
        self.assertIn("OPEN THE SCREEN", leer)
        # Der Grund bleibt benannt, der Absatz nicht.
        self.assertIn("/api/risk", leer)
        self.assertNotIn("would hold up this page", leer)
        # Mit Daten ersetzt die echte Kachel den Verweis.
        live = _sichtbarer_text(self.ausgabe["live"]["overview"])
        self.assertNotIn("Open Leaderboard", live)
        self.assertNotIn("OPEN THE SCREEN", live)

    def test_field_notes_leerzustand(self) -> None:
        # Die neue Studie rendert ohne Nutzlast den Leerzustand mit Dateinamen
        # und in keinem Zustand eine erfundene Notiz.
        for modus in ("leer", "live"):
            text = _sichtbarer_text(self.ausgabe[modus]["research_field_notes"])
            with self.subTest(modus=modus):
                self.assertIn("Field notes", text)
                self.assertIn("field_notes.json", text)
        api_js = (WURZEL / "web" / "js" / "api.js").read_text(encoding="utf-8")
        self.assertIn("'/api/research/field-notes': 'field_notes.json'", api_js)
        platzhalter = json.loads((WURZEL / "public" / "data" / "field_notes.json").read_text(encoding="utf-8"))
        self.assertEqual(platzhalter["kennzeichnung"], "curated/field-notes")
        self.assertIsInstance(platzhalter["notes"], list)


if __name__ == "__main__":
    unittest.main()
