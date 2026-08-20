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

import html as _html_mod
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


def _html_unescape(text: str) -> str:
    return _html_mod.unescape(text)


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
            # Node schreibt UTF-8; ohne Angabe dekodiert Windows mit der
            # Locale-Codepage und aus "·" wird Kauderwelsch.
            encoding="utf-8",
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

    def test_whale_flow_gruppiert_das_tape_mit_kategorie(self) -> None:
        # Der Harness-Tape traegt einen Polymarket-Print (Wallet w1, Macro,
        # $9,000) und einen Kalshi-Print ohne Wallet. Die Seite zeigt die
        # Kategorie aus dem Print, zaehlt nur den gruppierbaren und sagt,
        # dass der andere fehlt — und keine Zahl, die nicht aus den beiden
        # Prints folgt.
        html = self.ausgabe["live"]["whale"]
        text = _sichtbarer_text(html)
        self.assertIn("Macro", text)
        self.assertIn("1/1 prints", text)              # MOSTLY IN mit Anteil
        self.assertIn("TOP CATEGORY BY $", text)
        self.assertIn("100% of $", text)               # Macro haelt alle gruppierten Dollar
        self.assertIn("$9.0k", text)                   # $ GROUPED
        self.assertIn("1 Kalshi print(s) are not shown here", text)
        self.assertIn("1 without a wallet left out", text)
        self.assertIn("One wallet accounts for all $9.0k", text)
        self.assertIn("Example question", text)        # TOP MARKET
        self.assertIn("100% of this wallet", text)
        self.assertIn("2 min ago", text)               # LAST PRINT
        self.assertIn("SORT BY", text)
        # Die Kalshi-Kategorie steht nicht in der Wallet-Tabelle: der Print
        # ist ausgeschlossen, seine Dollar zaehlen nirgends mit.
        self.assertNotIn("Crypto", text)
        self.assertNotIn("$12.0k", text)
        self.assertNotIn("$3.0k", text)
        # Kein Titel-Nachschlagen in T.markets mehr, und keine 24h-Behauptung
        # ueber ein Fenster, dessen Laenge niemand gemessen hat.
        self.assertNotIn("Other", text)
        self.assertNotIn("24H", text)
        for wert in ("18.4m", "214k"):
            self.assertNotIn(wert, text)
        quelltext = (WURZEL / "web" / "js" / "pages" / "trader_pages.js").read_text(encoding="utf-8")
        self.assertNotIn("T.markets.find((x) => x.title === t.market)", quelltext)
        # Ohne Tape bleibt der Leerzustand mit Quelle, ohne Kategorie und Kennzahl.
        leer = _sichtbarer_text(self.ausgabe["leer"]["whale"])
        self.assertIn("/api/tape", leer)
        self.assertNotIn("TOP CATEGORY", leer)
        self.assertNotIn("Macro", leer)

    def test_risk_screen_nennt_die_ausgeschlossenen_gruppen(self) -> None:
        for modus in ("leer", "live"):
            text = _sichtbarer_text(self.ausgabe[modus]["risk"])
            with self.subTest(modus=modus):
                self.assertIn("Sports odds, crypto &amp; market prices, and weather are excluded", text)
                self.assertNotIn("Sports odds and weather are excluded", text)

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

    def test_laeufe_ohne_fill_stehen_in_der_einen_tabelle(self) -> None:
        # Mit Ledger gibt es keine eigene "RUNS WITHOUT A FILL"-Box mehr: die
        # Laeufe ohne Fill stehen als NO-FILLS-Zeilen in der einen Event-
        # Tabelle unten, mit ihren Entscheidungszahlen als Status.
        live = _sichtbarer_text(self.ausgabe["live"]["runs_runs"])
        self.assertNotIn("RUNS WITHOUT A FILL", live)
        self.assertIn("Run with a fill", live)
        self.assertIn("Run without a fill", live)
        self.assertIn("NO FILLS", live)
        self.assertIn("160 decisions · 160 priced in · placed nothing", live)
        self.assertIn("Second run without a fill", live)
        # Die Einzeiler tragen keine Stake-Fusszeile — die gehoert zur Karte.
        self.assertNotIn("Stake $0.00", live)
        # Ohne Ledger bleibt die Box als Rueckfall, damit kein Lauf
        # verschwindet (runs_runs_many hat keinen Ledger).
        self.assertIn("RUNS WITHOUT A FILL · 6", _sichtbarer_text(self.ausgabe["live"]["runs_runs_many"]))

    def test_laufkurve_kommt_aus_den_laufwerten(self) -> None:
        # Vier Laeufe mit publizierten PnL-Werten ergeben eine Treppenkurve;
        # ohne Nutzlast gibt es keine (test_leerzustand_zeichnet_keine_kurve).
        live = self.ausgabe["live"]["runs_runs"]
        # Die Kurve zeigt die Wallet-Zahl der Kachel (55.97 → 66.0 kumuliert
        # ueber die zwei Bot-Events des Ledgers), nicht mehr die Log-Reihe.
        text = _sichtbarer_text(live)
        self.assertIn("CUMULATIVE WALLET PNL BY RUN", text)
        self.assertIn("USD · wallet ledger, bot markets", text)
        self.assertNotIn("CUMULATIVE REALIZED PNL BY RUN", text)
        self.assertRegex(live, r'<path d="M\s*\d')
        self.assertIn("66", text)
        self.assertIn("last bot fill 07-02 · ledger as of 2026-08-17 · log estimate +$24 — LOG VS WALLET above", text)
        # Ohne Ledger (runs_runs_many) faellt die Kurve auf die Log-Reihe
        # zurueck und sagt das im Titel.
        viele = _sichtbarer_text(self.ausgabe["live"]["runs_runs_many"])
        self.assertIn("CUMULATIVE REALIZED PNL BY RUN", viele)
        self.assertIn("USD · log-reconstructed", viele)

    def test_startseite_ist_forschungslandung(self) -> None:
        # Die Startseite fuehrt mit der Forschung, nicht mit dem Whale-Feed:
        # Kopfzeile, Unterzeile aus den Nutzlasten, Verdict board, Live-runs-
        # Streifen, Field notes, dann erst die Live-Kacheln. Die frueheren
        # Verweise "Open Leaderboard" / "OPEN THE SCREEN" gibt es nicht mehr.
        for modus in ("leer", "live"):
            text = _sichtbarer_text(self.ausgabe[modus]["overview"])
            with self.subTest(modus=modus):
                self.assertIn("Prediction-market microstructure, measured on self-recorded books.", text)
                self.assertIn("no profitability claim", text)
                self.assertIn("VERDICT BOARD", text)
                self.assertIn("TESTED STRATEGY · LIVE RUNS, REAL MONEY", text)
                self.assertIn("FIELD NOTES", text)
                # Die zwei Einstiege unter dem Titel: Strategie und Werkzeug.
                self.assertIn("TESTED STRATEGY →", text)
                self.assertIn("ANALYSIS TOOL →", text)
                self.assertIn("github.com/Pablozh123/prediction-market-terminal", self.ausgabe[modus]["overview"])
                self.assertIn("docs/research/ONE_PAGER.md", self.ausgabe[modus]["overview"])
                self.assertNotIn("Open Leaderboard", text)
                self.assertNotIn("OPEN THE SCREEN", text)
                self.assertNotIn("Where the money moved", text)
                self.assertNotIn("BIGGEST MOVES · 1H", text)
                self.assertNotIn("updated every 15 seconds", text)
                self.assertIn("refresh every 30 seconds", text)
        # Reihenfolge: die getestete Strategie zuerst, dann das Board, die
        # Notes, zuletzt das Analysewerkzeug.
        live = self.ausgabe["live"]["overview"]
        self.assertLess(live.index("TESTED STRATEGY · LIVE RUNS"), live.index("VERDICT BOARD"))
        self.assertLess(live.index("VERDICT BOARD"), live.index("FIELD NOTES"))
        self.assertLess(live.index("FIELD NOTES"), live.index("ANALYSIS TOOL · LIVE DATA"))

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

    def test_review_queue_eine_zeile_je_markt(self) -> None:
        # Der Harness traegt fuenf Faelle ueber zwei Slugs (drei Fenster fuer
        # example-question, zwei fuer second-question). Die Seite zeigt zwei
        # Zeilen, je den Fall mit der hoechsten Prioritaet, und nennt die
        # Fensterzahl in der Kachel und in der Spalte WINDOWS.
        zeilen = json.loads(self.ausgabe["live"]["_collapse_queue"])
        self.assertEqual([z["markt_slug"] for z in zeilen], ["example-question", "second-question"])
        self.assertEqual([z["id"] for z in zeilen], ["c1", "c5"])          # high band, dann juengster ts
        self.assertEqual([z["windows_n"] for z in zeilen], [3, 2])
        self.assertEqual(zeilen[0]["windows_first"], "2026-05-22T20:45:00Z")
        self.assertEqual(zeilen[0]["windows_last"], "2026-05-22T21:50:00Z")
        # Die Begruendung des behaltenen Falls bleibt unangetastet.
        self.assertEqual(zeilen[0]["begruendung"], "kept-high-case")
        self.assertEqual(zeilen[1]["begruendung"], "kept-newer-medium-case")
        # Ohne Nutzlast eine leere Liste, kein Fehler.
        self.assertEqual(json.loads(self.ausgabe["leer"]["_collapse_queue"]), [])
        html = self.ausgabe["live"]["research"]
        text = _sichtbarer_text(html)
        self.assertIn("2 markets", text)
        self.assertIn("5 windows", text)
        self.assertIn("WINDOWS", text)
        self.assertIn("3 · 05-22 20:45 → 21:50", text)
        self.assertIn("2 · 05-22 20:45 → 05-23 20:45", text)
        # Eine Zeile je Slug: der Slug steht genau einmal in der Tabelle.
        self.assertEqual(text.count("example-question"), 1)
        self.assertEqual(text.count("second-question"), 1)
        # Die verworfenen Fenster tauchen nicht als Zeilen auf.
        for verworfen in ("c2", "c3", "c4"):
            self.assertNotRegex(text, r"\b" + verworfen + r"\b")

    def test_category_efficiency_neue_und_alte_form(self) -> None:
        # Neue kategorie_karte.json: Kennzahlen mit n, Balken je Horizont,
        # Brier-ueber-Horizont-Linien, Kalibrierung, Tabelle mit allen
        # Horizonten, zugeklappte Methode mit Thesis-Schnappschuss.
        neu = self.ausgabe["live"]["research_category_efficiency"]
        text = _sichtbarer_text(neu)
        self.assertIn("MARKETS IN SAMPLE 540", text)
        self.assertIn("410 priced at T-7", text)
        # Traegt die Datei brier_offen, rangieren Best/Worst auf dem Brier
        # der offenen Fragen — der Gesamt-Brier kuert sonst die Kategorie
        # mit den meisten schon entschiedenen Preisen.
        self.assertIn("BEST AT T-7 Politics open Brier 0.150 · n 90", text)
        self.assertIn("WORST AT T-7 Sports open Brier 0.220 · n 180", text)
        self.assertIn("BRIER AT T-7 BY CATEGORY", text)
        self.assertIn("BRIER AT T-1 BY CATEGORY", text)
        self.assertIn("Politics · n 200", text)               # n am Balken
        self.assertIn("BRIER BY HORIZON", text)
        self.assertRegex(neu, r'<path d="M\s*\d')             # Linien nur mit Daten
        self.assertIn("CALIBRATION AT T-7", text)
        self.assertIn("predicted 3% · realised 5% · n 120", text)
        self.assertIn("T-30 BRIER · HIT · N", text)
        self.assertIn("0.200 80% · n 150", text)
        # Spalte mit dem offenen T-7-Brier, je Zelle mit n.
        self.assertIn("T-7 OPEN BRIER · N", text)
        self.assertIn("0.220 n 180", text)
        # Einpreisungs-Logik je Kategorie: Anker, Treiber, blinder Fleck,
        # t0-Quelle — plus Mechanik-Mix und die messlogik-only-Kategorie
        # (Weather erklaert ihre eigene Stichprobenluecke).
        self.assertIn("PRICING-IN LOGIC BY CATEGORY", text)
        self.assertIn("Harness anchor text.", text)
        self.assertIn("Harness blind spot.", text)
        self.assertIn("Harness weather gap.", text)
        self.assertIn("nachrichten n 200 (Brier T-1 0.060)", text)
        self.assertIn("THESIS FIGURES THIS TABLE REPLACES", text)
        self.assertIn("Politik: Brier T-7 0.352 (n 12)", text)
        self.assertIn("<details", neu)
        self.assertLess(neu.index("BY CATEGORY AND HORIZON"), neu.index("Harness method text."))
        self.assertLess(neu.index("PRICING-IN LOGIC BY CATEGORY"), neu.index("Harness method text."))
        # Alte Form (nur brier_t7/brier_t1): rendert weiter, ohne Kurve, ohne
        # erfundene Horizonte, ohne Kalibrierung, und n_t1 steht als unbekannt.
        alt = self.ausgabe["live"]["research_category_efficiency_alt"]
        text_alt = _sichtbarer_text(alt)
        self.assertIn("BEST AT T-7 Sport Brier 0.042 · n 26", text_alt)
        self.assertIn("WORST AT T-7 Politik Brier 0.352 · n 12", text_alt)
        self.assertNotIn("BRIER BY HORIZON", text_alt)
        self.assertNotIn("CALIBRATION", text_alt)
        self.assertNotIn("T-30", text_alt)
        self.assertNotRegex(alt, r'<path d="M\s*\d')
        self.assertIn("0.036 93% · n —", text_alt)
        # Leerzustand nennt die Datei.
        leer = _sichtbarer_text(self.ausgabe["leer"]["research_category_efficiency"])
        self.assertIn("kategorie_karte.json", leer)
        self.assertNotIn("BEST AT T-7", leer)

    # ---- Landing (Overview als Forschungsseite) ---------------------------

    def test_verdict_board_aus_der_nutzlast(self) -> None:
        # Vier Harness-Studien, jede als Zeile: Frage, Verdikt-Tag aus
        # verdikt_art, Kennzahl mit Einheit und n, Fenster. Die Zaehlung in
        # der Unterzeile kommt aus dem Payload (zaehler), nicht aus dem Code.
        html = self.ausgabe["live"]["overview"]
        text = _sichtbarer_text(html)
        self.assertIn("VERDICT BOARD · 4 STUDIES", text)
        self.assertIn("Four studies (2 refuted, 1 confirmed, 0 not identified, 1 control), 21 small-stake live runs, a pre-registered pilot — no profitability claim.", text)
        self.assertIn("Does the harness board render a confirmed row?", text)
        self.assertIn("CONFIRMED", text)
        self.assertEqual(text.count("REFUTED"), 2)
        self.assertIn("CONTROL", text)
        self.assertNotIn("NOT IDENTIFIED", text)          # 0 offene: kein Tag erfunden
        self.assertIn("55.5 %", text)
        self.assertIn("Hit rate · n = 205,835 obs", text)
        self.assertIn("2026-07-18 to 2026-07-28", text)
        self.assertIn("n = 8 pairs", text)
        self.assertIn("payload 2026-08-16 23:32 UTC", text)   # Stand der Datei
        # Direkt aufgerufene Helfer: Zaehlung und Unterzeile.
        self.assertEqual(json.loads(self.ausgabe["live"]["_verdict_counts"]),
                         {"total": 4, "ja": 1, "nein": 2, "offen": 0, "kontrolle": 1})
        self.assertTrue(self.ausgabe["live"]["_landing_subline"].startswith("Four studies (2 refuted"))
        # Ohne Nutzlast: Ladehinweis mit Dateinamen, keine Zeile, keine Zahl.
        leer = _sichtbarer_text(self.ausgabe["leer"]["overview"])
        self.assertIn("microstructure.json", leer)
        self.assertNotIn("CONFIRMED", leer)
        self.assertNotIn("REFUTED", leer)
        self.assertNotIn("studies (", leer)
        self.assertEqual(json.loads(self.ausgabe["leer"]["_verdict_counts"])["total"], 0)

    def test_live_runs_streifen_eine_pnl_zahl(self) -> None:
        # Eine PnL-Zelle: die Wallet-Zahl fuehrt (+$175.09 mit Abgleichsdatum),
        # die Log-Schaetzung steht benannt in der Unterzeile — nicht mehr zwei
        # gleichrangige Zellen plus Methodenabsatz.
        text = _sichtbarer_text(self.ausgabe["live"]["overview"])
        self.assertIn("NET PNL (WALLET) +$175.09", text)
        self.assertIn("reconciled 2026-07-18", text)
        self.assertIn("log estimate +$288.67", text)
        self.assertNotIn("LOG-RECONSTRUCTED PNL", text)
        self.assertIn("RUNS · BETS 21 · 27", text)
        self.assertIn("WON · LOST 25 · 2", text)
        self.assertNotIn("Two PnL figures on purpose", text)
        # Fehlt runs.json, sagt der Streifen das und zeigt keine PnL-Zahl.
        teil = _sichtbarer_text(self.ausgabe["live"]["overview_partial"])
        self.assertIn("runs.json did not load: HTTP 404", teil)
        self.assertNotIn("+$288.67", teil)
        self.assertNotIn("+$175.09", teil)
        self.assertNotIn("21 small-stake live runs", teil)
        # Und die noch ladende Notiz-Datei wird als ladend benannt.
        self.assertIn("Loading field_notes.json", teil)
        leer = _sichtbarer_text(self.ausgabe["leer"]["overview"])
        self.assertIn("runs.json", leer)
        self.assertNotIn("+$", leer)

    def test_field_notes_streifen_fuenf_titel(self) -> None:
        text = _sichtbarer_text(self.ausgabe["live"]["overview"])
        for i in ("one", "two", "three", "four", "five"):
            self.assertIn("Harness note " + i, text)
        self.assertNotIn("Harness note six", text)
        leer = _sichtbarer_text(self.ausgabe["leer"]["overview"])
        self.assertIn("field_notes.json", leer)
        self.assertNotIn("Harness note", leer)

    def test_landing_live_zeile_mit_stand(self) -> None:
        # Die Live-Kacheln tragen den as_of-Stempel des Polls; ohne Poll steht
        # keine Uhrzeit da, sondern die Quelle.
        live = _sichtbarer_text(self.ausgabe["live"]["overview"])
        self.assertIn("as of 2026-08-17 10:00 UTC", live)
        self.assertIn("MARKETS TRACKED 1", live)
        self.assertIn("PRINTS ≥ $2.5K · TAPE WINDOW 2", live)
        leer = _sichtbarer_text(self.ausgabe["leer"]["overview"])
        self.assertNotIn("as of", leer)
        self.assertIn("/api/markets", leer)
        self.assertIn("/api/tape", leer)

    def test_seitenleiste_neu_gruppiert_und_ohne_papierkasten(self) -> None:
        app_js = (WURZEL / "web" / "js" / "app.js").read_text(encoding="utf-8")
        for gruppe in ("START HERE", "TESTED STRATEGY", "RECORD", "ANALYSIS TOOL"):
            self.assertIn("'" + gruppe + "'", app_js)
        for weg in ("PAPER EQUITY", "No paper account", "'DASHBOARD'", "'TRADING'", "'SYSTEM'"):
            self.assertNotIn(weg, app_js)
        # Nicht mehr gelistet, aber als Route erreichbar.
        for seite in ("'settings'", "'track'", "'resolved'"):
            self.assertNotIn("this.navItem(" + seite, app_js)
        # Der Paper-Desk (Copy trade, Portfolio) steht nur in der Seitenleiste,
        # wo er laeuft: hinter paperDeskSichtbar() (lokaler Host oder eine
        # Antwort mit Schreibrecht), in einer eigenen Gruppe.
        self.assertIn("'PAPER DESK'", app_js)
        desk = app_js[app_js.index("if (this.paperDeskSichtbar())"):app_js.index("'PAPER DESK'") + 400]
        self.assertIn("this.navItem('copy'", desk)
        self.assertIn("this.navItem('portfolio'", desk)
        self.assertEqual(app_js.count("this.navItem('copy'"), 1)
        self.assertEqual(app_js.count("this.navItem('portfolio'"), 1)
        self.assertIn("settings: renderSettings", app_js)
        self.assertIn("track: renderTrack", app_js)
        # Fusszeile: Repo, Read-only-Satz, Live-run-Wallet.
        self.assertIn("github.com/Pablozh123/prediction-market-terminal", app_js)
        self.assertIn("Read-only. No orders placed. Public Polymarket &amp; Kalshi data.", app_js)
        self.assertIn("0x29af…f88d", app_js)
        # Titel der Seite.
        index = (WURZEL / "web" / "index.html").read_text(encoding="utf-8")
        self.assertIn("<title>Market Intel — prediction-market microstructure, measured</title>", index)

    # ---- Cross-venue Ehrlichkeits-Schranke ---------------------------------

    def test_cross_venue_schranke_und_ladezustand(self) -> None:
        # Laufende Anfrage: Ladezeile mit Quelle. Antwort ohne Treffer: der
        # ehrliche Leerblock mit Verweis auf die Studien 08 und 11 und die
        # Mikrostruktur-Route. Mit Treffer: Zeile plus Schranken-Satz.
        laedt = _sichtbarer_text(self.ausgabe["live"]["cross_loading"])
        self.assertIn("matching pairs across venues", laedt.lower())
        self.assertIn("/api/cross", laedt)
        leer = _sichtbarer_text(self.ausgabe["live"]["cross_gate_empty"])
        self.assertIn("No cross-venue pair clears the match gate right now (similarity ≥ 0.5, volume on both venues).", leer)
        self.assertIn("See studies 08 and 11: the two 79¢/64¢ 'edges' were mismatched questions.", leer)
        self.assertIn("#research/microstructure", leer)
        self.assertNotIn("Example question", leer)
        live = _sichtbarer_text(self.ausgabe["live"]["cross"])
        self.assertIn("1 of 9 candidate pairs clear the gate (similarity ≥ 0.5, volume on both venues)", live)
        self.assertIn("similarity 0.71", live)
        self.assertIn("GATE 0.50", live)
        # Der Schieber faengt bei der Schranke an, nicht darunter.
        self.assertNotIn("0.30", live)
        # Ohne jede Antwort (leerer Harness): Ladezustand, keine Zeile.
        leer0 = _sichtbarer_text(self.ausgabe["leer"]["cross"])
        self.assertIn("/api/cross", leer0)
        self.assertNotIn("Example question", leer0)

    # ---- Leaderboard: tote Regler weg, Score-Bestandteile beschriftet -------

    def test_leaderboard_ohne_tote_regler_und_ohne_rohen_tags_string(self) -> None:
        html = self.ausgabe["live"]["traders"]
        text = _sichtbarer_text(html)
        for weg in ("VIEW", "COLUMNS", "PERIOD", "Bot-like only", "Active only", "TRAITS", "BALANCE",
                    "ACCOUNT AGE", "ASSETS", "OPEN POSITIONS VALUE", "MINIMUM BOT SCORE",
                    "Fetch open positions", "Fetch win rates", "EXTRA DATA"):
            with self.subTest(weg=weg):
                self.assertNotIn(weg, text)
        # Ohne Werte in der Antwort gibt es weder Spalte noch Rangoption.
        self.assertNotIn("WIN RATE", text)
        self.assertNotIn("RESOLVED BETS", text)
        self.assertNotIn("Win rate", text)
        # Der rohe Begruendungs-String erscheint nicht; seine Bestandteile
        # stehen beschriftet unter der Wallet.
        self.assertNotIn("return 90, sharpe-proxy 60", text)
        self.assertNotIn("drawdown-proxy", text)
        self.assertIn("SCORE COMPONENTS", text)
        self.assertIn("return 90", text)
        self.assertIn("sharpe proxy 60", text)
        self.assertIn("volume 80", text)
        self.assertIn("grade B", text)
        # Rangoptionen, die tatsaechlich sortieren.
        for option in ("Smart score", "Profit", "Volume", "Profit / volume"):
            self.assertIn(option, text)
        # Auch das Detailpanel und die Suche leaken den String nicht.
        detail = _sichtbarer_text(self.ausgabe["live"]["_detail_wallet"])
        self.assertNotIn("return 90, sharpe-proxy 60", detail)
        self.assertIn("score components: return 90 · sharpe proxy 60 · volume 80", detail)
        suche = _sichtbarer_text(self.ausgabe["live"]["_suche"])
        self.assertNotIn("sharpe-proxy", suche)

    # ---- Markets: tote Ansichten weg, 1D statt 1H, kein Sparkline ----------

    def test_markets_ohne_tote_ansichten(self) -> None:
        text = _sichtbarer_text(self.ausgabe["live"]["markets"])
        for weg in ("VIEW", "Cards", "Calendar", "Saved", "My positions", "TREND 24H"):
            with self.subTest(weg=weg):
                self.assertNotIn(weg, text)
        self.assertIn("CHANGE 1D", text)
        self.assertIn("as of 2026-08-17 10:00 UTC", text)
        self.assertNotIn('<polyline', self.ausgabe["live"]["markets"])
        # Der Ueberblick: vier Kennzahlen des Ausschnitts, drei Einblick-
        # Panels, alles aus den geladenen Zeilen (ein Harness-Markt).
        self.assertIn("MARKETS IN SAMPLE 1 1 Polymarket · 0 Kalshi", text)
        self.assertIn("BIGGEST 1D MOVE +3¢ Example question", text)
        self.assertIn("MEDIAN SPREAD 2¢ n = 1 markets with a quoted spread", text)
        self.assertIn("TOP MOVERS · 1D", text)
        self.assertIn("RESOLVING NEXT", text)
        self.assertIn("in 120 d", text)
        self.assertIn("COIN FLIPS", text)
        self.assertIn("no market in the sample is priced 40–60¢", text)
        # Neue Spalten aus denselben API-Feldern, Kategorien-Chips mit Zahl.
        self.assertIn("SPREAD", text)
        self.assertIn("LIQUIDITY", text)
        self.assertIn("MACRO 1", text)
        # Leerzustand unveraendert: keine Kennzahl, die Quelle benannt.
        leer = _sichtbarer_text(self.ausgabe["leer"]["markets"])
        self.assertNotIn("MARKETS IN SAMPLE", leer)
        self.assertIn("/api/markets", leer)
        core = (WURZEL / "web" / "js" / "pages" / "core_pages.js").read_text(encoding="utf-8")
        self.assertNotIn("· 1H", core)
        util = (WURZEL / "web" / "js" / "util.js").read_text(encoding="utf-8")
        self.assertNotIn("sparkArr", util)
        # Kalshi "Cross Category" wird zu Other, im Frontend wie im Server.
        self.assertIn("cross[ -]?category", util)
        apv = (WURZEL / "app" / "api_views.py").read_text(encoding="utf-8")
        self.assertIn('"cross category"', apv)

    # ---- Live tape / Whale flow: Kategorie-Chips ---------------------------

    def test_tape_und_whale_kategorie_chips(self) -> None:
        # Der Harness-Tape traegt Macro (mit Wallet) und Crypto (Kalshi, ohne
        # Wallet). Die Chip-Leiste bietet genau die vorhandenen Kategorien an.
        tape = _sichtbarer_text(self.ausgabe["live"]["flow"])
        self.assertIn("CATEGORY ALL CRYPTO MACRO", tape)
        self.assertIn("PRINTS SHOWN 2", tape)
        crypto = _sichtbarer_text(self.ausgabe["live"]["flow_cat_crypto"])
        self.assertIn("PRINTS SHOWN 1", crypto)
        self.assertIn("KXBTC15M", crypto)
        self.assertNotIn("Example question", crypto)
        macro = _sichtbarer_text(self.ausgabe["live"]["flow_cat_macro"])
        self.assertIn("PRINTS SHOWN 1", macro)
        self.assertIn("Example question", macro)
        self.assertNotIn("KXBTC15M", macro)
        # Whale flow: nur Kategorien mit Wallet-Prints als Chips; Crypto (ohne
        # Wallet) laesst sich nicht gruppieren, und die Seite sagt das.
        whale = _sichtbarer_text(self.ausgabe["live"]["whale"])
        self.assertIn("CATEGORY ALL MACRO", whale)
        whale_macro = _sichtbarer_text(self.ausgabe["live"]["whale_cat_macro"])
        self.assertIn("in the category Macro", whale_macro)
        self.assertIn("$9.0k", whale_macro)
        whale_crypto = _sichtbarer_text(self.ausgabe["live"]["whale_cat_crypto"])
        self.assertIn("NO PRINTS IN THIS CATEGORY", whale_crypto)
        self.assertNotIn("$9.0k", whale_crypto)
        # Kein "TRACKED ONLY"-Chip mehr: nichts setzt das Flag.
        self.assertNotIn("TRACKED ONLY", tape)

    # ---- Backtester: kein Auto-Lauf, RUN-Knopf, 429 -------------------------

    def test_backtester_laeuft_nur_auf_knopfdruck(self) -> None:
        leer = _sichtbarer_text(self.ausgabe["leer"]["backtester"])
        self.assertIn("RUN backtest", leer)
        self.assertIn("Press RUN", leer)
        self.assertNotIn("hyperactive", leer)
        laeuft = _sichtbarer_text(self.ausgabe["live"]["backtester_running"])
        self.assertIn("running…", laeuft)
        self.assertNotIn("RUN backtest", laeuft)          # Knopf ist inert
        gebremst = _sichtbarer_text(self.ausgabe["live"]["backtester_rate_limited"])
        self.assertIn("rate-limited", gebremst)
        self.assertIn("retry in 7 s", gebremst)
        fehler = _sichtbarer_text(self.ausgabe["live"]["backtester_error"])
        self.assertIn("HTTP 502", fehler)
        # Kein Stepper ruft den Lauf mehr auf: bt() setzt nur den Zustand.
        trading = (WURZEL / "web" / "js" / "pages" / "trading_pages.js").read_text(encoding="utf-8")
        self.assertNotIn("T.runBacktestLive()", trading)
        self.assertIn("T.runBacktest()", trading)
        app_js = (WURZEL / "web" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertNotIn("setTimeout(async () =>", app_js)
        self.assertIn("err.status === 429", app_js)
        # Der lange Timeout gilt nur fuer /api/risk.
        api_js = (WURZEL / "web" / "js" / "api.js").read_text(encoding="utf-8")
        self.assertIn("LANGSAME_PFADE = ['/api/risk']", api_js)
        self.assertIn("TIMEOUT_LANG_MS = 150000", api_js)
        self.assertIn("TIMEOUT_MS = 45000", api_js)
        risk = _sichtbarer_text(self.ausgabe["live"]["risk_loading"])
        self.assertIn("building the day's tape, ~90 s on a cold cache", risk)

    def test_keine_sichtbaren_deutschen_oder_internen_texte(self) -> None:
        # Sichtbarer Text der eigenen Seiten ist Englisch; "Streamlit" ist
        # kein Begriff dieser Oberflaeche.
        verdaechtig = ("Streamlit", "Leerzustand", "Nutzlast", "Herkunft", "Papier", "Wallet-Zeilen", "Zeile")
        for modus in ("leer", "live"):
            for name, html in self.ausgabe[modus].items():
                if name.startswith("_") or name.startswith("research") or name.startswith("runs_") or name.startswith("alerts"):
                    continue
                text = _sichtbarer_text(html)
                for wort in verdaechtig:
                    with self.subTest(modus=modus, seite=name, wort=wort):
                        self.assertNotIn(wort, text)

    # ---- Live runs: eine PnL-Kachel, LOG VS WALLET zugeklappt, First taker --

    def test_live_runs_eine_pnl_kachel_und_log_vs_wallet(self) -> None:
        # Eine PnL-Kachel: die Wallet-Zahl fuehrt, und zwar aus der frischesten
        # Quelle — der Harness-Ledger (2026-08-17, Bot netto +$66.00) ist neuer
        # als der kuratierte Abgleich (2026-07-18, +$20). Die Log-Zahl steht
        # benannt in der Unterzeile; beide Spalten samt Begruendung liegen im
        # zugeklappten LOG VS WALLET, mit der Wallet-Adresse als Link.
        live = self.ausgabe["live"]["runs_runs"]
        text = _sichtbarer_text(live)
        self.assertIn("NET PNL (WALLET, AS OF 2026-08-17) +$66", text)
        self.assertIn("cash truth, wallet ledger · log estimate +$24", text)
        # Die Log-Zahl steht genau einmal: als Spalte im zugeklappten
        # LOG VS WALLET, nicht mehr als zweite Kachel.
        self.assertEqual(text.count("LOG-RECONSTRUCTED PNL"), 1)
        self.assertNotIn("WALLET-RECONCILED NET (AS OF", text)
        self.assertNotIn("TOTAL STAKE $40 wallet-reconciled", text)
        self.assertIn("TOTAL STAKE $40 log estimate", text)
        self.assertIn("LOG VS WALLET · WHY THE FIGURES DIFFER · WALLET AS OF 2026-08-17", text)
        self.assertIn('<details data-key="runs-abgleich"', live)
        self.assertIn("LOG STAKE $40.00 WALLET BUYS $61.34 LOG-RECONSTRUCTED PNL +$24.00 WALLET-RECONCILED NET +$66.00", text)
        self.assertIn("the order response price is the cap, not the fill", text)
        self.assertIn("post-mortem 2026-07-18", text)
        self.assertIn("Wallet columns come from the wallet ledger at the bottom of this page (bot markets only), as of 2026-08-17.", text)
        self.assertIn("0x29afe1bf37700768a640a08f1b35dad5f202f88d", text)
        self.assertIn('href="https://polygonscan.com/address/0x29afe1bf37700768a640a08f1b35dad5f202f88d"', live)
        self.assertIn('href="https://polymarket.com/profile/0x29afe1bf37700768a640a08f1b35dad5f202f88d"', live)
        self.assertIn("public Polymarket Data API", text)
        # Das Laufdetail steckt im aufklappbaren Bot-Event: die Zeile traegt
        # die Wallet-Zahl, das Detail nur noch die Log-Seite, so beschriftet.
        self.assertIn("run harness_a · Run with a fill · real orders · resolved", text)
        self.assertIn("Stake $20.00 (log est.) · log PnL +$14.00 — the wallet figure is the PNL column of this row", text)
        self.assertIn("Stake $20.00 (log est.) · log PnL +$10.00 — the wallet figure is the PNL column of this row", text)
        # Keine Karten mehr neben der Tabelle — eine Darstellung, nicht drei.
        self.assertNotIn("RUNS WITH FILLS", text)
        # Der Simulator-Reiter benennt seine Zahlen als Simulation.
        sim = _sichtbarer_text(self.ausgabe["live"]["runs_sim"])
        self.assertIn("simulation on log-estimated fills", sim)
        # Leerzustand: Kacheln mit Dateinamen, keine Zahl, keine Adresse.
        leer = _sichtbarer_text(self.ausgabe["leer"]["runs_runs"])
        self.assertIn("NET PNL — runs.json not loaded", leer)
        self.assertNotIn("LOG VS WALLET", leer)

    def test_live_runs_first_taker_aus_den_race_feldern(self) -> None:
        # Zwei Wetten mit Tape: eine mit null fremden Trades davor, eine mit
        # zwei; Verfolger 30 s und 60 s, Median 45 s.
        text = _sichtbarer_text(self.ausgabe["live"]["runs_runs"])
        self.assertIn("FIRST TAKER 1 of 2 first on the traded side · 2 tape-reconciled bets · median 45 s to the next buyer", text)
        leer = _sichtbarer_text(self.ausgabe["leer"]["runs_runs"])
        self.assertIn("FIRST TAKER — runs.json not loaded", leer)

    def test_live_runs_diagramme_und_saubere_titel(self) -> None:
        live = self.ausgabe["live"]["runs_runs"]
        text = _sichtbarer_text(live)
        # Der Preispfad nach dem Fill wird nicht mehr gezeichnet (Wunsch des
        # Wallet-Inhabers); die Daten bleiben im Timing-Reiter lesbar.
        self.assertNotIn("POST-FILL PRICE PATH", text)
        self.assertNotIn("lime won, red lost, grey open", text)
        self.assertNotIn("preis_nach_fill", text)
        # Interne Klammerzusaetze sind aus den Titeln verschwunden, die
        # Drop-Quelle steht als Chip; "event ↗" ist ein Link oder weg.
        self.assertNotIn("(URL-Prober)", text)
        self.assertNotIn("(kanalseite)", text)
        self.assertIn("Second run with a fill", text)
        self.assertIn("drop via RSS feed", text)
        self.assertIn('href="https://polymarket.com/event/harness-event-a"', live)
        # Keine Karten mehr: der "event ↗"-Kartenlink ist weg, der Link haengt
        # am Zeilentitel der Tabelle.
        self.assertNotIn(">event ↗</a>", live)
        # Timing-Reiter: Repricing-Treppen aus repricing[].punkte, dann die
        # Tabelle mit den Spalten aus preis_nach_fill (30 s war immer leer).
        timing = self.ausgabe["live"]["runs_timing"]
        ttext = _sichtbarer_text(timing)
        self.assertIn("REPRICING AFTER THE DROP · 1 BET", ttext)
        self.assertIn("our fill 10 s after drop · priced in after 2.0 min", ttext)
        self.assertIn("REPRICE 30 S REPRICE 900 S", ttext)
        self.assertIn("+5¢ +40¢", ttext)
        self.assertLess(timing.index("REPRICING AFTER THE DROP"), timing.index("TIMING AND REPRICING PER FILL"))
        # Kalibrierung: das Quadrat aus charts.js ueber der Tabelle.
        calib = self.ausgabe["live"]["runs_calib"]
        self.assertIn("ENTRY PRICE VS SETTLED SHARE · 2 BANDS", _sichtbarer_text(calib))
        self.assertLess(calib.index("ENTRY PRICE VS SETTLED SHARE"), calib.index("ENTRY PRICE BAND"))
        # Ohne Nutzlast keine Pfade und keine Kurven.
        leer = _sichtbarer_text(self.ausgabe["leer"]["runs_timing"])
        self.assertNotIn("REPRICING AFTER THE DROP", leer)

    def test_live_runs_wallet_ledger_je_event(self) -> None:
        # Die eine Tabelle unter den Karten: KPI-Zeile aus aggregat, jedes
        # Wallet-Event (Pilot als gruppierte Zeile), die Laeufe ohne Trade,
        # Typ-Chips, Links, Notizen mit Link, Legende — aus
        # extras.wallet_ledger (API) bzw. wallet_ledger.json (statisch).
        live = self.ausgabe["live"]["runs_runs"]
        text = _sichtbarer_text(live)
        self.assertIn("ALL EVENTS · RUNS AND WALLET", text)
        self.assertIn("WALLET/PUBLIC-API", text)
        self.assertIn("as of 2026-08-17 01:02 UTC", text)
        # Keine zweite KPI-Reihe mehr: die Wallet-Summen sind eine
        # beschriftete Textzeile, die Kacheln oben bleiben die einzigen.
        self.assertIn("Whole wallet: 4 events (2 bot · 1 discretionary · 1 pilot) · 7 trades (6 buys · 1 sell · 4 redemptions) · buys $176.35 · net cash flow +$58.66 (sells + redemptions − buys) · positions 3 won / 2 lost (1 expired worthless)", text)
        self.assertNotIn("STAKE (BUYS)", text)
        self.assertNotIn("NET CASH FLOW +$58.66 sells", text)
        # Der Herkunftstext der Tabelle ist zugeklappt, nicht ein Absatz.
        self.assertIn("WHAT THIS TABLE IS", text)
        self.assertIn('<details data-key="ledger-was"', live)
        self.assertIn("Race chips in an opened bot row compare each fill", text)
        self.assertIn("4 WALLET EVENTS + 2 RUNS WITHOUT A TRADE · NEWEST FIRST", text)
        # Reihenfolge: neueste Zeile zuerst; die Laeufe ohne Trade (07-03 und
        # 07-04) liegen zwischen Bot-Event A (07-18) und Bot-Event B (07-02).
        self.assertLess(text.index("Harness Curtis E3 event"), text.index("Harness pilot GDP event"))
        self.assertLess(text.index("Harness pilot GDP event"), text.index("Harness bot event"))
        self.assertLess(text.index("Harness bot event"), text.index("Second run without a fill"))
        self.assertLess(text.index("Second run without a fill"), text.index("Run without a fill"))
        self.assertLess(text.index("Run without a fill"), text.index("Harness bot event B"))
        # Der Pilot ist eine gruppierte Zeile mit dem Einzel-Event darin.
        self.assertIn("Pre-registered pilot — 1 small event", text)
        # Typ-Chips, gemischtes Event, Laufprofil, Maerkte je Event.
        self.assertIn("DISCRETIONARY 1 $100.00 +$0.97 1 won", text)
        self.assertIn("PILOT 1 $5.01 +$0.16 1 won", text)
        self.assertIn("harness_a BOT + discretionary 2 $51.34 +$45.97 1 won · 1 worthless", text)
        self.assertIn("1 of 2 markets are not in the run log of 'harness_a' (discretionary).", text)
        self.assertIn("worthless discretionary", text)
        # Links: Event-Seite je Zeile, Vorregistrierungs-Dokument in der Notiz, Download.
        self.assertIn('href="https://polymarket.com/event/harness-curtis-e3"', live)
        self.assertIn('href="https://polymarket.com/event/harness-pilot-gdp"', live)
        self.assertIn('href="https://github.com/Pablozh123/multi-agent-orchestration-informational-efficiency/blob/main/docs/project/PREREG_CURTIS_E3_2026-08-07.md"', live)
        self.assertIn('href="./data/wallet_ledger.json"', live)
        self.assertIn("Forecasts pre-registered before airing", text)
        self.assertIn("rules frozen 2026-07-18", text)
        # Legende: drei Typen plus NO FILLS; Bot-Zeilen tragen das Laufdetail.
        self.assertIn("BOT market and side appear in a runs.json run log — open the row for the full run detail (latency, decisions, every bet)", text)
        self.assertIn("DISCRETIONARY placed by hand, in no run log", text)
        self.assertIn("PILOT one of the pre-registered pilot trades of 2026-07-22", text)
        # Die NO-FILLS-Zeile erklaert sich in der Legende.
        self.assertIn("NO FILLS the bot ran and placed nothing — no wallet trace", text)
        # Im gemischten Event stehen die Handelszeilen von Hand unter dem
        # eingebetteten Laufdetail, beschriftet.
        self.assertIn("PLACED BY HAND ON THE SAME EVENT", text)
        # Ohne Ledger: die Zeile nennt die Datei und das Skript, keine Zahl.
        for name in ("runs_runs_many",):
            ohne = _sichtbarer_text(self.ausgabe["live"][name])
            self.assertIn("ALL EVENTS · RUNS AND WALLET", ohne)
            self.assertIn("public/data/wallet_ledger.json", ohne)
            self.assertIn("scripts/wallet_ledger.py", ohne)
            self.assertNotIn("WALLET EVENTS", ohne)
        leer = _sichtbarer_text(self.ausgabe["leer"]["runs_runs"])
        self.assertIn("public/data/wallet_ledger.json", leer)
        self.assertNotIn("Whole wallet:", leer)
        # api.js kennt die Datei fuer den statischen Rueckfall.
        api_js = (WURZEL / "web" / "js" / "api.js").read_text(encoding="utf-8")
        self.assertIn("'/api/research/wallet-ledger': 'wallet_ledger.json'", api_js)

    def test_live_runs_zeigt_alle_laeufe_ohne_deckel(self) -> None:
        # 15 Laeufe mit Fill werden 15 Karten, 6 ohne Fill 6 Zeilen — kein
        # Deckel (frueher .slice(0, 12)).
        viele = _sichtbarer_text(self.ausgabe["live"]["runs_runs_many"])
        for i in range(15):
            with self.subTest(karte=i):
                self.assertIn("Many-run card " + str(i), viele)
        self.assertIn("RUNS WITHOUT A FILL · 6", viele)
        for i in range(6):
            with self.subTest(zeile=i):
                self.assertIn("Many-run line " + str(i), viele)
        self.assertEqual(viele.count("REAL ORDERS"), 15)

    def test_kalibrierungsdiagramm_achsenbeschriftung_ohne_ueberlappung(self) -> None:
        # Frueher standen "→ realised ↑" (mittig) und "predicted 1" (rechts)
        # auf derselben Grundlinie und liefen bei 200 px ineinander. Jetzt:
        # "0" und "1" an den Achsenenden, "predicted" mittig unter der
        # x-Achse, "realised" gedreht an der y-Achse — und die Textboxen der
        # x-Achse ueberschneiden sich rechnerisch nicht.
        for name in ("runs_calib", "research_category_efficiency"):
            html = self.ausgabe["live"][name]
            svgs = re.findall(r'<svg[^>]*viewBox="0 0 200 200"[^>]*>(.*?)</svg>', html, re.S)
            self.assertTrue(svgs, name)
            svg = svgs[0]
            texte = re.findall(r'<text([^>]*)>([^<]*)</text>', svg)
            beschriftungen = [t.strip() for _, t in texte]
            with self.subTest(diagramm=name):
                self.assertEqual(sorted(beschriftungen), ["0", "0", "1", "1", "predicted", "realised"])
                self.assertNotIn("→ realised ↑", svg)
                self.assertNotIn("predicted 1", svg)
                # x-Achse: drei Texte auf einer Grundlinie, Boxen disjunkt
                # (Monospace 9 px ≈ 5.4 px je Zeichen).
                unten = []
                for attrs, txt in texte:
                    if 'transform="rotate' in attrs:
                        self.assertEqual(txt.strip(), "realised")
                        continue
                    x = float(re.search(r'\bx="([\d.]+)"', attrs).group(1))
                    y = float(re.search(r'\by="([\d.]+)"', attrs).group(1))
                    anker = re.search(r'text-anchor="(\w+)"', attrs)
                    anker = anker.group(1) if anker else "start"
                    breite = len(txt.strip()) * 5.4
                    links = x if anker == "start" else x - breite if anker == "end" else x - breite / 2
                    # Die x-Achsen-Beschriftung liegt unter dem Quadrat (y > 185);
                    # der y-Tick "0" bei y = 178 gehoert zur y-Achse.
                    if y > 185:
                        unten.append((links, links + breite, txt.strip()))
                unten.sort()
                self.assertEqual([t for _, _, t in unten], ["0", "predicted", "1"])
                for (_, ende_a, _), (start_b, _, _) in zip(unten, unten[1:]):
                    self.assertLess(ende_a, start_b)
                # y-Achse: "realised" gedreht, mittig zwischen den Ticks 1 (oben) und 0 (unten).
                gedreht = [a for a, t in texte if t.strip() == "realised"][0]
                self.assertIn('transform="rotate(-90 10 100)"', gedreht)

    # ---- Mentions latency, Pilot, Pipeline forward, Methodology ------------

    def test_mentions_latency_diagramm_und_ausschluesse(self) -> None:
        html = self.ausgabe["live"]["research_mentions_latency"]
        text = _sichtbarer_text(html)
        # Echter Median (0.5 und 10 → 5.25), als Kachel und als Referenzlinie.
        self.assertIn("MEDIAN LATENCY 5.25 min n = 2 events with a reaction", text)
        self.assertIn("MINUTES TO FIRST REACTION (≥ 2¢ MOVE) PER EVENT · n 2", text)
        self.assertIn("median 5.25 min", text)
        self.assertIn("MINUTES TO CONVERGENCE PER EVENT · n 2", text)
        self.assertIn("linear scale, 30 to 600 min", text)
        self.assertIn("EXCLUDED EVENTS · 1", text)
        self.assertIn("harness_excluded excluded · ambiguous mapping between content and market", text)
        self.assertIn("HOW TO READ IT First reaction is the first move of at least 2¢", text)
        # Das handelbare Fenster ist NICHT Konvergenz minus Reaktion — der
        # Lesetext muss das sagen (cnbc_kernen/jre_vance beweisen es).
        self.assertIn("not simply convergence minus reaction", text)
        # YES- und NO-Mediane getrennt, mit n, direkt aus aggregate.
        self.assertIn("RESOLVED YES · n 1", text)
        self.assertIn("RESOLVED NO · n 1", text)
        self.assertIn("median convergence 600 min", text)
        self.assertIn("median tradeable window 9.8 h", text)
        # Methode/Grenzen kommen aus quelle, zugeklappt.
        self.assertIn("METHOD, SAMPLE &amp; WHAT IT CANNOT SHOW", text)
        self.assertIn("Harness mentions method.", text)
        self.assertIn("Harness mentions caveat.", text)
        # Tabelle mit Outcome und Status je Zeile, alle Zeilen.
        self.assertIn("MENTIONS EVENTS · 3 OF 3", text)
        self.assertIn("RESOLVED STATUS", text)
        self.assertIn("harness_fast 0.5 min 30 min 0.5 YES ok", text)
        self.assertIn("harness_none — — — NO no_reaction", text)
        # Leerzustand nennt die Datei.
        leer = _sichtbarer_text(self.ausgabe["leer"]["research_mentions_latency"])
        self.assertIn("mentions_latenz.json", leer)
        self.assertNotIn("MEDIAN LATENCY", leer)
        self.assertNotIn("RESOLVED YES", leer)

    def test_pilot_alle_trades_englisch_und_slippage_diagramm(self) -> None:
        html = self.ausgabe["live"]["research_pilot"]
        text = _sichtbarer_text(html)
        self.assertIn("PILOT TRADES · 20 OF 20", text)
        self.assertEqual(text.count("held to resolution (protocol)"), 20)
        self.assertNotIn("haelt bis zur Aufloesung", text)
        self.assertNotIn("Protokoll", text)
        # Statische Kacheln: Einsatz aus den Trades, Abweichung benannt.
        self.assertIn("STAKE PER TRADE $5 protocol $10 · deviates from the frozen text", text)
        self.assertIn("TRADES 20 20 still open", text)
        # Keine Serie: die ehrliche Zeile statt einer Kurve, dann Slippage.
        self.assertIn("PILOT EQUITY VS RULE ADHERENCE: no series", text)
        self.assertNotRegex(html, r'<polyline points="\s*\d')
        self.assertIn("SLIPPAGE PER TRADE · EXECUTION MINUS SIGNAL PRICE · n 20", text)
        self.assertIn("10 of 20 worse than signal · mean +0.50¢", text)
        # Watcher-Trichter aus den Zaehlern.
        self.assertIn("1,992 markets scanned · 323 rule matches", text)
        self.assertIn("WATCHER FUNNEL · LAST RUN 2026-08-01 04:33 UTC", text)
        self.assertIn("arm 2 · already expired 1,155", text)
        self.assertIn("arm 2 signals 322", text)
        leer = _sichtbarer_text(self.ausgabe["leer"]["research_pilot"])
        self.assertIn("pilot.json", leer)
        self.assertNotIn("SLIPPAGE", leer)

    def test_pipeline_forward_ehrliche_ueberschrift(self) -> None:
        html = self.ausgabe["live"]["research_pipeline_forward"]
        text = _sichtbarer_text(html)
        self.assertIn("Almost nothing was tradable: 1 of 5 rule-compliant decision checks ended in a buy (20%) · dominant reason: no YES ask in the book (3 of 4 no-trades, 75%)", text)
        self.assertIn("WHY IT DID NOT TRADE · REASON COUNTS · 4 NO-TRADES ACROSS 2 RUNS", text)
        self.assertIn("No YES ask in the book 3", text)
        self.assertIn("YES ask (incl. fee) above the run cap 1", text)
        self.assertIn("No equity curve", text)
        self.assertNotIn("FORWARD PAPER EQUITY", text)
        self.assertIn("FORWARD LOG · 2 OF 2 RUNS", text)
        leer = _sichtbarer_text(self.ausgabe["leer"]["research_pipeline_forward"])
        self.assertIn("pipeline_forward.json", leer)
        self.assertNotIn("Almost nothing was tradable", leer)

    def test_methodology_hat_methodentext(self) -> None:
        for modus in ("leer", "live"):
            html = self.ausgabe[modus]["research_methodology"]
            text = _sichtbarer_text(html)
            with self.subTest(modus=modus):
                for titel in ("WHAT A STUDY OBSERVATION IS", "HIT RATE AND WILSON LOWER BOUND",
                              "ROUND-TRIP COST = SPREAD + FEE", "FILL MODELS: TOUCH VS TAPE, AND THE MARKOUT IDENTITY",
                              "BLOCK BOOTSTRAP", "CROSS-VENUE MATCHING AND FEE CURVES", "WALLET RECONCILIATION VS LOG",
                              "PRE-REGISTRATION POLICY", "AGENT LAYER GUARDRAILS"):
                    self.assertIn(titel, text)
                self.assertIn("The skeptic can only lower a case's priority", text)
                self.assertIn("default backend is a deterministic mock", text)
                self.assertIn("Read the full one-pager", text)
                self.assertIn("github.com/Pablozh123/prediction-market-terminal/blob/main/docs/research/ONE_PAGER.md", html)
        # Mit audit.json: die vier Zaehler und der Satz, dass mock heisst mock.
        live = _sichtbarer_text(self.ausgabe["live"]["research_methodology"])
        self.assertIn("AUDIT ENTRIES 3", live)
        self.assertIn("BACKEND mock not a live model run", live)
        self.assertIn("backend counter mock 3 of 3 entries", live)
        self.assertIn("review queue is mock output, not a live model run", live)
        # Ohne audit.json: Kacheln mit Dateinamen, Text trotzdem da.
        leer = _sichtbarer_text(self.ausgabe["leer"]["research_methodology"])
        self.assertIn("AUDIT ENTRIES — audit.json not loaded", leer)
        self.assertNotIn("backend counter mock", leer)

    def test_microstructure_sprungliste_und_verdiktzeile(self) -> None:
        html = self.ausgabe["live"]["research_microstructure"]
        text = _sichtbarer_text(html)
        # Verdiktzeile aus den Karten gezaehlt (eine Studie, refuted).
        self.assertIn("1 refuted · 0 confirmed · 0 not identified · 0 control · 1 studies", text)
        # Sprungliste: ein Anker je Karte unter der Research-Route, Label aus
        # der Studien-ID.
        self.assertIn('href="#research/microstructure/harness-study"', html)
        self.assertIn('id="research/microstructure/harness-study"', html)
        self.assertIn("01 Harness study", text)
        leer = _sichtbarer_text(self.ausgabe["leer"]["research_microstructure"])
        self.assertNotIn("refuted", leer)

    def test_postmortem_referenzen_werden_links(self) -> None:
        html = self.ausgabe["live"]["research_postmortems"]
        self.assertIn('href="https://github.com/Pablozh123/multi-agent-orchestration-informational-efficiency/pull/12"', html)
        self.assertIn('href="https://github.com/Pablozh123/multi-agent-orchestration-informational-efficiency/commit/8af07d6"', html)
        self.assertIn('href="https://github.com/Pablozh123/prediction-market-terminal/blob/main/docs/research/ONE_PAGER.md"', html)
        text = _sichtbarer_text(html)
        self.assertIn("PR #12 ↗ (fill accounting); commit 8af07d6 ↗ (heartbeat); docs/research/ONE_PAGER.md ↗ ; plain note", text)

    # ---- Risk screen: richer event rows and the flag log -----------------

    def test_risk_event_karte_zeigt_seite_preis_wallets_und_komponenten(self) -> None:
        # The harness carries one row in the richer /api/risk shape and one
        # older row without those fields. The rich card shows the side chip,
        # the price at flag time, the window, the wallets with profile links,
        # the market link and the score components as labelled numbers.
        html = self.ausgabe["live"]["risk"]
        text = _sichtbarer_text(html)
        self.assertIn("NO buys $34.0k of $40.0k (85%)", text)
        self.assertIn("at flag NO 34¢ (30¢–34¢)", text)
        self.assertIn("17 Aug 09:40 – 10:00 UTC · 20 min", text)
        self.assertIn("0xbbb2…0002 65% · NO buys · fresh", text)
        self.assertIn('href="https://polymarket.com/profile/0xbbb2000000000000000000000000000000000002"', html)
        self.assertIn('href="https://polymarket.com/event/example-question"', html)
        self.assertIn("market ↗", text)
        # Closed, the card carries the lead only: no flag sentence, no
        # components, the context note as a tooltip on the category; the
        # "Why this score" toggle opens them (state riskOpen, not <details>,
        # so the 30 s re-render keeps it open).
        self.assertIn("TIMING 61 /100 MEDIUM Example question", text)
        self.assertIn("POLITICS &amp; GEOPOLITICS · POLYMARKET NO buys", text)
        self.assertIn('title="decisions are known to officials before the public"', html)
        self.assertIn("20 min · 4 prints", text)
        self.assertNotIn("One wallet dominates", text)
        self.assertNotIn("three wallets, one side", text.split("EVENT SCREEN")[0])
        self.assertIn("WINDOW 2 h Why 61? ▾", text)
        self.assertIn("EVENT SCREEN 44 /100 ELEVATED KXFED-26SEP KALSHI", text)
        # Open: the score taken apart — one row per scoring part with its
        # bar, points, what the tape showed and what full marks take; the
        # zero parts in one "not found" line; the context multiplier; the
        # arithmetic, which says so when the listed parts do not reach the
        # score (this fixture lists four of eleven).
        offen = _sichtbarer_text(self.ausgabe["live"]["risk_open"])
        offen_html = self.ausgabe["live"]["risk_open"]
        self.assertIn("Why 61? ▴ WHY 61 / 100 · WHAT EACH PART SAW flags: three wallets, one side", offen)
        self.assertIn("One wallet dominates 9.8 /15 0xbbb2…0002 did 65% of the flow · full marks when one wallet did all of it", offen)
        self.assertIn("Size of the flow 6 /15 $40k traded in the window · full marks at $100k", offen)
        self.assertIn("Fresh wallets 5 /10 2 wallets barely seen on the tape, same side · full marks at 4", offen)
        self.assertIn("NOT FOUND late in the market (nothing inside the market's last 48 h)", offen)
        self.assertIn("Context Politics &amp; geopolitics — decisions are known to officials before the public", offen)
        self.assertIn("20.8 pts × 1.1 = 23 / 100 · the card says 61 — parts missing from this answer", offen)
        self.assertIn("width:65.3%", offen_html)           # 9.8 / 15 bar
        self.assertIn('title="share of the flow done by the top wallet"', offen_html)
        # The toggle must not trigger the card action, and the open block
        # neither.
        self.assertIn('<div data-stop data-act="0" class="hv-bd32"', html)
        self.assertIn('<div data-stop style="margin-top:12px; border-top:1px dashed', offen_html)
        # The older row renders as before: no side chip, no price, no invented
        # wallet or component.
        self.assertIn("KXFED-26SEP", text)
        self.assertNotIn("side n/a", text)
        self.assertNotIn("price n/a", text)
        # Links inside the card must not trigger the card action.
        self.assertIn("data-bg", html)
        self.assertIn('data-stop href="https://polymarket.com/event/example-question"', html)

    def test_flag_log_reiter_zustaende(self) -> None:
        # Tab exists on both modes; the log is fetched only when the tab opens.
        for modus in ("leer", "live"):
            self.assertIn("Flag log", _sichtbarer_text(self.ausgabe[modus]["risk"]))
        intro = "Every event the screen flags is logged with the side, price and wallets at that moment, so it can be checked afterwards against what happened next."
        # Loading: no rows, no numbers, names the endpoint.
        laedt = _sichtbarer_text(self.ausgabe["live"]["risk_log_loading"])
        self.assertIn(intro, laedt)
        self.assertIn("loading /api/risk/log", laedt)
        self.assertNotIn("+30 MIN", laedt)
        # Empty answer: says the log is empty and why, not a placeholder row.
        leer = _sichtbarer_text(self.ausgabe["live"]["risk_log_empty"])
        self.assertIn(intro, leer)
        self.assertIn("The flag log is empty so far", leer)
        self.assertIn("score 40 and up", leer)
        self.assertNotIn("+30 MIN", leer)
        # Error: names the endpoint and the error.
        fehler = _sichtbarer_text(self.ausgabe["live"]["risk_log_error"])
        self.assertIn("/api/risk/log did not answer: HTTP 503", fehler)
        # In the empty run the tab shows the loading line (nothing recorded yet).
        self.assertIn("loading /api/risk/log", _sichtbarer_text(self.ausgabe["leer"]["risk_log"]))

    def test_flag_log_zeilen_mit_preis_danach(self) -> None:
        html = self.ausgabe["live"]["risk_log"]
        text = _sichtbarer_text(html)
        self.assertIn("2 flags", text)
        self.assertIn("price after the flag read for 1 of the newest 2 Polymarket flags", text)
        # Newest first: the Polymarket flag (10:25) before the Kalshi flag (09:00).
        self.assertLess(text.find("17 Aug 10:25 UTC"), text.find("17 Aug 09:00 UTC"))
        self.assertIn("seen 3× since 17 Aug 10:05", text)
        self.assertIn("NO buys $34.0k of $40.0k (85%)", text)
        self.assertIn("at flag NO 34¢ (30¢–34¢)", text)
        # +30 min and +2 h with the move in cents, +24 h honestly "not yet".
        self.assertIn("+30 MIN 37¢ +3", text)
        self.assertIn("+2 H 31¢ -3", text)
        self.assertIn("+24 H not yet", text)
        self.assertIn("MEASURED ON NO side, from last print", text)
        # Kalshi row: no history, said so; no wallets, said so.
        self.assertIn("Kalshi: no history read", text)
        self.assertIn("wallet identities not public on this venue", text)
        self.assertIn('href="https://kalshi.com/markets/KXFED-26SEP"', html)
        self.assertIn("3 wallets · 4 prints", text)
        self.assertIn("top-wallet concentration 9.8/15", text)
        # app.js fetches the log only when the tab is opened, with enrich=1.
        app_js = (WURZEL / "web" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("openRiskLog()", app_js)
        self.assertIn("'/api/risk/log?limit=100&enrich=1'", app_js)
        self.assertIn("riskLog: null", app_js)

    def test_review_queue_ein_eintrag_je_markt(self) -> None:
        # Fuenf Faelle auf zwei Slugs -> zwei Zeilen; je Slug gewinnt die
        # hoechste Prioritaet, und die Fensterzahl steht daneben.
        zeilen = json.loads(self.ausgabe["live"]["_collapse_queue"])
        self.assertEqual([z["markt_slug"] for z in zeilen], sorted({z["markt_slug"] for z in zeilen}, key=[z["markt_slug"] for z in zeilen].index))
        self.assertEqual(len(zeilen), 2)
        je_slug = {z["markt_slug"]: z for z in zeilen}
        best = je_slug["example-question"].get("best") or je_slug["example-question"]
        self.assertEqual(best["score_band"], "high")
        self.assertEqual(int(je_slug["example-question"]["windows_n"]), 3)
        self.assertEqual(int(je_slug["second-question"]["windows_n"]), 2)
        self.assertEqual(json.loads(self.ausgabe["leer"]["_collapse_queue"]), [])

    def test_category_efficiency_zeigt_horizonte_und_n(self) -> None:
        text = _sichtbarer_text(self.ausgabe["live"]["research_category_efficiency"])
        self.assertIn("Which categories price things well", text)
        # Stichprobe je Kategorie und Horizont sichtbar, keine Zahl ohne n.
        self.assertRegex(text, r"n \d+")
        for tag in ("BRIER", "T-7", "T-1"):
            self.assertIn(tag, text.upper())
        leer = _sichtbarer_text(self.ausgabe["leer"]["research_category_efficiency"])
        self.assertIn("kategorie_karte.json", leer)

    # ---- Wallet page ------------------------------------------------------

    def test_wallet_seite_ohne_adresse_zeigt_eingabe_und_beispiel(self) -> None:
        # No address chosen: input, Analyse button, example chip, no figure.
        for name in ("wallet", "wallet_none"):
            html = self.ausgabe["leer"][name]
            text = _sichtbarer_text(html)
            with self.subTest(seite=name):
                self.assertIn('placeholder="0x… (40 hex characters)"', html)
                self.assertIn("Analyse →", text)
                self.assertIn("0x29af…f88d · live-run wallet", text)
                self.assertIn("0x29afe1bf37700768a640a08f1b35dad5f202f88d", html)
                self.assertIn("NO WALLET SELECTED", text)
                self.assertNotIn("SETTLED PNL", text)
                self.assertNotRegex(text, r"\$\d")
        # A partial address is named as such, nothing is fetched.
        teil = _sichtbarer_text(self.ausgabe["leer"]["wallet_partial_input"])
        self.assertIn("Not a full address yet", teil)
        self.assertIn("40 hex characters", teil)

    def test_wallet_seite_lade_und_fehlerzustaende(self) -> None:
        laden = _sichtbarer_text(self.ausgabe["leer"]["wallet_loading"])
        self.assertIn("ANALYSING 0XABC0…0ABC", laden)
        self.assertIn("up to ~10 s, six public API calls", laden)
        self.assertNotIn("SETTLED PNL", laden)
        fehler = _sichtbarer_text(self.ausgabe["leer"]["wallet_error"])
        self.assertIn("API DID NOT ANSWER", fehler)
        self.assertIn("/api/wallet/0xabc0…0abc did not answer: Failed to fetch", fehler)
        self.assertIn("Try again", fehler)
        vierhundert = _sichtbarer_text(self.ausgabe["leer"]["wallet_error_400"])
        self.assertIn("NOT A WALLET ADDRESS", vierhundert)
        self.assertIn("HTTP 400", vierhundert)
        limit = _sichtbarer_text(self.ausgabe["leer"]["wallet_error_429"])
        self.assertIn("RATE-LIMITED", limit)
        self.assertIn("try again in 7 s", limit)
        # No curve in any of these states.
        for name in ("wallet_loading", "wallet_error", "wallet_error_400", "wallet_error_429"):
            with self.subTest(seite=name):
                self.assertNotRegex(self.ausgabe["leer"][name], r'<path d="M\s*\d')

    def test_wallet_seite_mit_nutzlast_zeigt_jede_zahl_mit_n(self) -> None:
        # Overview: identity strip, KPI strip, fact line, the aside cards, the
        # PnL curve, top open / closed and the treemap. The other sections
        # sit on their tabs (below).
        html = self.ausgabe["live"]["wallet"]
        text = _sichtbarer_text(html)
        self.assertIn("harness_wallet", text)
        self.assertIn('href="https://polymarket.com/profile/0xabc0000000000000000000000000000000000abc"', html)
        self.assertIn('href="https://polygonscan.com/address/0xabc0000000000000000000000000000000000abc"', html)
        self.assertIn("as of 2026-08-17 19:00 UTC · cached 300 s", text)
        self.assertIn("Follow on the copy desk →", text)
        self.assertIn("Replay this wallet in the backtester →", text)
        self.assertIn("GRADE F · 27/100 BELOW SAMPLE GATE 4 DAYS ACTIVE", text)
        # KPI strip: every figure with its n / CI; the fact line below it.
        self.assertIn("SETTLED PNL +$210.00 n 12 resolved markets", text)
        self.assertIn("CORRECTED WIN RATE 73% 8/11 events · 95% [43%, 91%]", text)
        self.assertIn("GRADE F score 27 / 100 · below sample gate", text)
        self.assertIn("SHARPE · DAILY $ 11.92 n 5 d · profile curve", text)
        self.assertIn("MAX DRAWDOWN $5.00 25.0% of peak · profile curve", text)
        self.assertIn("VOLUME TRADED $105 TRADES 3 AVG TRADE $35.00 DAYS ACTIVE 4 SINCE 2026-07-01", text)
        # Aside: portfolio, breakdown, core stats, buy/sell bar, edge.
        self.assertIn("PORTFOLIO · OPEN $55.00 cost basis $50.00 unrealised +$5.00 positions 2", text)
        self.assertIn("PNL BREAKDOWN settled (track record) +$210.00 realised (closed rows) +$210.00 unrealised (open) +$5.00 position value $55.00", text)
        self.assertIn("CORE STATS avg trade $35.00 won / lost 9 / 3 open / resolved 2 / 12 buy / sell 2 / 1 trades / day 0.75 not redeemed 1", text)
        self.assertIn("BUY / SELL RATIO 66.7% buy 2 sell 1", text)
        self.assertIn("REALIZED EDGE 35.0¢ per $ 95% CI [12.0¢, 55.0¢] events 11 per share +5.0pp · thin CI excludes zero", text)
        # Tabs, PnL curve, top cards.
        self.assertIn("Overview Track record Positions Trades Categories Risk Similar wallets", text)
        # PnL timeline: head with the current PnL big, a time-axis area chart
        # with $ ticks and dates, six stat tiles, the definitions collapsed.
        self.assertIn("PNL TIMELINE · PROFILE CURVE i 6 daily points · 2026-07-01 → 2026-07-06 CURRENT PNL +$30 +$30.00 · 2026-07-06", text)
        self.assertRegex(html, r'<path d="M\s*\d')
        self.assertIn('<linearGradient id="pnlgrad', html)
        self.assertIn(">$30<", html)                                    # y tick
        self.assertIn("2026-07-01 2026-07-02 2026-07-04 2026-07-06", text)  # x dates on the time axis
        self.assertIn("SHARPE 11.92 n 5 d · $/day", text)
        self.assertIn("SORTINO — 2 down days · needs 3", text)
        self.assertIn("CALMAR 438.00 annual PnL / max DD", text)
        self.assertIn("MAX DRAWDOWN $5.00 25.0% of peak", text)
        self.assertIn("WIN DAYS 60% 3 up · 2 down", text)
        self.assertIn("BEST · WORST DAY +$15 · -$5 vol $9.62 / day", text)
        self.assertIn("<details", html)
        self.assertIn("BASIS · DEFINITIONS as of 2026-08-17 19:00 UTC", text)
        self.assertIn("Sortino = mean / downside RMS over all days (target 0), shown only with 3+ losing days", text)
        self.assertIn("TOP OPEN · BY UNREALISED YES Open harness market A? +38% $40.00 → $55.00 · +$15.00 unrealised", text)
        self.assertIn("TOP CLOSED · BY REALISED YES Harness market 0? +80% $50.00 → $90.00 · +$40.00 realised", text)
        # Limits stay on every tab.
        self.assertIn("LIMITS OF THIS READ", text)
        self.assertIn("50 rows per tail", text)
        # Track record tab: naive vs corrected side by side, flags, gate,
        # components, and the edge with its CI and category rows.
        record = _sichtbarer_text(self.ausgabe["live"]["wallet_tab_record"])
        self.assertIn("Naive — per position leg (what a leaderboard implies) 75% 9 / 12 [47%, 91%]", record)
        self.assertIn("Corrected — per event, NegRisk legs netted 73% 8 / 11 [43%, 91%]", record)
        self.assertIn("NEGRISK LEGS NETTED 1", record)
        self.assertIn("WASH / FARMER FLAG not flagged rule: volume", record)
        self.assertIn("SURVIVORSHIP GATE not passed 12 markets over 11 d · needs ≥ 10 and ≥ 14 d", record)
        self.assertIn("PROFIT CONCENTRATION 67% in top 3 best market 22%", record)
        self.assertIn("SCORE 27 / 100 · GRADE F · COMPONENTS insufficient sample", record)
        self.assertIn("insufficient sample (12 markets / 11d)", record)
        self.assertIn("EDGE PER $ · CLUSTER BOOTSTRAP 35.0¢ per $ 95% CI [12.0¢, 55.0¢] · n 11 events · excludes zero", record)
        self.assertIn("EDGE PER SHARE · ENTRY VS SETTLEMENT +5.0pp · THIN 95% CI [-2.0pp, +12.0pp] · n 11 events / 12 positions", record)
        self.assertIn("Politics · n 7", record)
        self.assertIn("RETURN PER $ STAKED · 95% CI", record)
        self.assertNotIn("CUMULATIVE PNL · PROFILE CURVE", record)
        # Positions tab: open (N of N, exposure, worthless, sort chips) and closed.
        pos_html = self.ausgabe["live"]["wallet_tab_positions"]
        pos = _sichtbarer_text(pos_html)
        self.assertIn("2 of 2 positions", pos)
        self.assertIn("TOTAL EXPOSURE $55.00 value at current prices · 2 positions", pos)
        self.assertIn("RESOLVED · NOT REDEEMED 1", pos)
        self.assertIn("resolved · not redeemed", pos)
        self.assertIn("SORT BY Value Unrealised Cost Ends", pos)
        self.assertIn("WON 9", pos)
        self.assertIn("LOST 3", pos)
        self.assertIn("2 of 12 resolved positions, largest |PnL| first", pos)
        self.assertNotIn("CAPPED", pos)
        self.assertGreaterEqual(pos_html.count("overflow-x:auto"), 2)
        sortiert = _sichtbarer_text(self.ausgabe["live"]["wallet_sort_pnl"])
        self.assertIn("Open harness market A?", sortiert)
        # Trades tab and categories tab.
        trades_html = self.ausgabe["live"]["wallet_tab_trades"]
        trades = _sichtbarer_text(trades_html)
        self.assertIn("3 of 3 trades, newest first", trades)
        self.assertIn("BUY · SELL 2 · 1", trades)
        self.assertIn("NET CASH FLOW +$5.00", trades)
        self.assertIn('href="https://polymarket.com/event/event-0"', trades_html)
        cats = _sichtbarer_text(self.ausgabe["live"]["wallet_tab_categories"])
        self.assertIn("STAKE BY CATEGORY", cats)
        self.assertIn("INSIDER-CONTEXT GROUPS · SHARE OF NOTIONAL", cats)
        self.assertIn("76% of traded notional sits in insider-plausible groups", cats)

    def test_wallet_risk_tab_and_similar_wallets(self) -> None:
        # Risk tab: the five cards from the resolved rows with their bands
        # and the rule text, the trading clock with its n and busiest cell.
        risk_html = self.ausgabe["live"]["wallet_tab_risk"]
        risk = _sichtbarer_text(risk_html)
        self.assertIn("PROFIT FACTOR 0.80 losing · wins $240.00 / losses $300.00", risk)
        self.assertIn("RISK / REWARD 0.80 about even · avg win $40.00 · avg loss $50.00", risk)
        self.assertIn("WIN STREAK 1 1 consecutive winning rows", risk)
        self.assertIn("LOSS STREAK 1 1 consecutive losing rows · current run 1", risk)
        self.assertIn("CONVICTION 1.00× even sizing · avg stake won $50.00 / lost $50.00", risk)
        self.assertNotIn("~PARTIAL", risk)  # not capped in the fixture
        self.assertIn("n 12 rows, 6 won, 6 lost", risk)
        self.assertIn("TRADING ACTIVITY · WEEKDAY × UTC HOUR n 3 trades", risk)
        self.assertIn("busiest cell Wed 10:00 UTC (1 trade)", risk)
        # 7 x 24 cells, three of them coloured, each with its count in the title.
        self.assertEqual(risk_html.count('height:16px; border-radius:3px; background:'), 7 * 24)
        self.assertEqual(risk_html.count("background:rgba(79,142,247,"), 3)
        self.assertIn('title="Wed 10:00 UTC — 1 trade · $50.00"', risk_html)
        # Similar wallets: waiting state names the request; the answer lists
        # shared markets, sides, overlap bar, leaderboard PnL where on the
        # board, and "not read" / "not on board" otherwise; the error state
        # offers a retry.
        warten = _sichtbarer_text(self.ausgabe["live"]["wallet_tab_similar"])
        self.assertIn("Reading the top holders of the largest open markets", warten)
        daten_html = self.ausgabe["live"]["wallet_tab_similar_data"]
        daten = _sichtbarer_text(daten_html)
        self.assertIn("SIMILAR WALLETS · TOP 2 as of 2026-08-18 15:00 UTC · 2 of 2 open markets checked · 7 wallets seen", daten)
        self.assertIn("bee · 0xbbbb…bbbb 2 same side 2 / 2 12 · $4,201 100% +$1,500 $90.0k Analyse profile ↗", daten)
        self.assertIn("0xcccc…cccc 1 opposite 1 / 2 not read 50% not on board — Analyse profile ↗", daten)
        self.assertIn("Markets that did not answer: 0x1111111…: holders down", daten)
        self.assertIn('href="https://polymarket.com/profile/0x' + "b" * 40 + '"', daten_html)
        fehler = _sichtbarer_text(self.ausgabe["live"]["wallet_tab_similar_err"])
        self.assertIn("/api/wallet/0xabc0…0abc/similar did not answer: HTTP 429", fehler)
        self.assertIn("Try again", fehler)
        # The tab bar carries both new tabs.
        self.assertIn("Overview Track record Positions Trades Categories Risk Similar wallets", _sichtbarer_text(self.ausgabe["live"]["wallet"]))

    def test_wallet_treemap_tiles_are_the_positions(self) -> None:
        # All: two open + two closed rows with a stake = four tiles, area from
        # the stake, colour from the PnL sign; each tile carries its figures
        # in the title. Closed only: the two closed rows. Open only: the two
        # open rows, the worthless one red.
        html = self.ausgabe["live"]["wallet"]
        text = _sichtbarer_text(html)
        self.assertIn("POSITIONS TREEMAP", text)
        self.assertIn("tile area = $ at stake", text)
        self.assertIn("4 tiles", text)
        # The hover card's figures ride in data-tip as JSON: title, the
        # market's own image URL from the feed, and label/value rows.
        tips = [json.loads(_html_unescape(m)) for m in re.findall(r'data-tip="([^"]*)"', html)]
        self.assertEqual(len(tips), 4)
        by_title = {t["title"]: t for t in tips}
        a = by_title["Open harness market A?"]
        self.assertEqual(a["image"], "https://polymarket-upload.s3.us-east-2.amazonaws.com/harness-open-a.png")
        self.assertEqual(a["pnl"], "up")
        rows = dict(a["rows"])
        self.assertEqual(rows["side"], "YES · open")
        self.assertEqual(rows["stake (cost)"], "$40.00")
        self.assertEqual(rows["value now"], "$55.00")
        self.assertEqual(rows["unrealised"], "+$15.00 (+38%)")
        self.assertIn("55.0¢", rows["price now"])
        self.assertEqual(rows["ends"], "2026-12-31")
        w = by_title["Resolved against, not redeemed?"]
        self.assertEqual(dict(w["rows"])["side"], "NO · resolved, not redeemed")
        self.assertEqual(w["image"], "")
        lost = by_title["Harness market 1?"]
        self.assertEqual(dict(lost["rows"])["side"], "YES · closed · lost")
        self.assertEqual(dict(lost["rows"])["realised"], "-$50.00 (-100%)")
        won = by_title["Harness market 0?"]
        self.assertEqual(dict(won["rows"])["returned"], "$90.00")
        self.assertEqual(won["image"], "https://polymarket-upload.s3.us-east-2.amazonaws.com/harness-event-0.jpg")
        # Tiles big enough carry the market image in place; the ones without
        # an image URL carry no <img> at all.
        self.assertIn('<img src="https://polymarket-upload.s3.us-east-2.amazonaws.com/harness-open-a.png"', html)
        self.assertEqual(html.count('class="tm-tile"'), 4)
        # Tiles: absolutely placed percent boxes; a lost row is red, a won one lime.
        self.assertGreaterEqual(html.count("position:absolute; left:"), 4)
        self.assertIn("background:rgba(255,69,69,", html)
        self.assertIn("background:rgba(200,245,66,", html)
        geschlossen = _sichtbarer_text(self.ausgabe["live"]["wallet_treemap_closed"])
        self.assertIn("2 tiles", geschlossen)
        offen = self.ausgabe["live"]["wallet_treemap_open"]
        self.assertIn("2 tiles", _sichtbarer_text(offen))
        self.assertNotIn("Harness market 1?", offen.split("POSITIONS TREEMAP")[-1])
        # The tiles link to the market where the row carries a URL.
        self.assertIn('href="https://polymarket.com/event/open-a"', html)

    def test_wallet_seite_leere_antwort_ohne_zahlen(self) -> None:
        # The API answered, but the wallet has nothing in the public feeds:
        # every block names its source, no figure appears, the failed part is
        # listed under the limits, and the treemap has nothing to tile.
        text = _sichtbarer_text(self.ausgabe["live"]["wallet_empty_answer"])
        self.assertIn("SETTLED PNL — no track record", text)
        self.assertIn("SHARPE · DAILY $ — no PnL curve", text)
        self.assertIn("No PnL curve — user-pnl-api.polymarket.com did not answer", text)
        self.assertIn("No open positions in the public /positions feed", text)
        self.assertIn("Nothing to tile: no positions with a stake in either feed", text)
        self.assertIn("TOP OPEN · BY UNREALISED nothing to show", text)
        self.assertIn("REALIZED EDGE — no resolved positions with a stake", text)
        self.assertIn("Parts that did not answer this time: resolved (HTTP 502)", text)
        self.assertNotRegex(text, r"\d+%")
        self.assertNotRegex(self.ausgabe["live"]["wallet_empty_answer"], r'<path d="M\s*\d')
        self.assertNotIn("position:absolute; left:", self.ausgabe["live"]["wallet_empty_answer"].split("POSITIONS TREEMAP")[-1])
        record = _sichtbarer_text(self.ausgabe["live"]["wallet_empty_record"])
        self.assertIn("No track record in the answer", record)
        self.assertIn("No realized edge", record)
        trades = _sichtbarer_text(self.ausgabe["live"]["wallet_empty_trades"])
        self.assertIn("No trades in the public /activity feed", trades)

    def test_wallet_seite_flache_profilkurve_zeigt_die_settled_kurve(self) -> None:
        # Theo4-shaped answer: 630 identical profile points. The block swaps
        # to the settled curve summed from the closed rows, says why in an
        # amber line, the ratios come from that curve, and the KPI strip
        # names the basis. The 22M level of the flat line is not charted.
        html = self.ausgabe["live"]["wallet_flat_profile"]
        text = _sichtbarer_text(html)
        self.assertIn("PNL TIMELINE · SETTLED CURVE i 22 closed rows · complete set · 2024-10-13 → 2025-01-01 REALISED PNL +$22.1M +$22,069,555 · 2025-01-01", text)
        self.assertIn("PROFILE CURVE FLAT one level (+$22.1M) for 630 points since 2024-11-28 — showing our settled curve instead", text)
        self.assertRegex(html, r'<path d="M\s*\d')
        self.assertIn("2024-10-13 2024-11-09 2024-12-05 2025-01-01", text)      # x dates on the time axis
        self.assertIn(">$20.0M<", html)                                       # y tick
        self.assertIn("SHARPE 3.94 n 80 d · $/day", text)
        self.assertIn("SORTINO — 1 down day · needs 3", text)
        self.assertIn("MAX DRAWDOWN $39,300 0.6% of peak", text)
        self.assertIn("WIN DAYS 88% 7 up · 1 down", text)
        self.assertIn("BEST · WORST DAY +$8.3M · -$21.35 vol $1.3M / day", text)
        # The long explanations sit in the collapsed basis block.
        self.assertIn("CURVE Realised PnL of the 22 closed-position rows summed in resolution order, starting at $0 the day before the first resolution", text)
        self.assertIn("PROFILE CURVE The profile curve is a flat line at $22,053,934 over its 630 points (2024-11-28 to 2026-08-18)", text)
        # KPI strip reads the same curve and says so.
        self.assertIn("SHARPE · DAILY $ 3.94 n 80 d · settled curve", text)
        self.assertIn("MAX DRAWDOWN $39,300 0.6% of peak · settled curve", text)
        # The flat 22,053,934 line is not the charted series.
        self.assertNotIn(">22,053,934<", html)

    def test_suchpalette_bietet_die_adresse_an(self) -> None:
        # A pasted full address is offered as an action, a partial one gets a
        # hint; both without any loaded list.
        for modus in ("leer", "live"):
            voll = _sichtbarer_text(self.ausgabe[modus]["_suche_adresse"])
            with self.subTest(modus=modus):
                self.assertIn("ANALYSE Analyse wallet 0x29af…f88d", voll)
                self.assertIn("opens the wallet page (#wallet/", voll)
        teil = _sichtbarer_text(self.ausgabe["leer"]["_suche_adresse_teil"])
        self.assertIn("Paste the full address to analyse a wallet", teil)
        self.assertIn("8 of 42 so far", teil)
        self.assertNotIn("Analyse wallet", teil)
        # The plain palette does not carry the action.
        self.assertNotIn("Analyse wallet", _sichtbarer_text(self.ausgabe["leer"]["_suche"]))

    def test_lade_zeigt_full_analysis_und_rendert_per_adresse(self) -> None:
        # The drawer for a leaderboard row links to the full page; a wallet
        # opened by address alone (whale flow, risk screen) renders too and
        # names the request it is waiting for.
        lade = _sichtbarer_text(self.ausgabe["live"]["_detail_wallet"])
        self.assertIn("Full analysis →", lade)
        self.assertIn("Open in the backtester", lade)
        adresse = _sichtbarer_text(self.ausgabe["leer"]["_detail_wallet_addr"])
        self.assertIn("0xbbb2000000000000000000000000000000000002", adresse)
        self.assertIn("Waiting for /api/wallet/0xbbb2…0002", adresse)
        self.assertIn("Full analysis →", adresse)
        self.assertNotRegex(adresse, r"\$\d")

    def test_wallet_route_und_seitenleiste(self) -> None:
        app_js = (WURZEL / "web" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("wallet: renderWallet", app_js)
        self.assertIn("this.navItem('wallet', 'Wallet')", app_js)
        self.assertLess(app_js.index("this.navItem('traders', 'Leaderboard')"), app_js.index("this.navItem('wallet', 'Wallet')"))
        # The deep link is pushed through adresseSetzen (no duplicate history
        # entry when the page already sits on it), and go('wallet') keeps the
        # analysed address in the hash.
        self.assertIn("this.adresseSetzen('wallet/' + key)", app_js)
        self.assertIn("if (s.page === 'wallet') return 'wallet' + (s.walletAddr ? '/' + s.walletAddr : '')", app_js)
        self.assertIn("analyseWallet(addr)", app_js)
        # No poll-state gate on the wallet fetches any more.
        self.assertNotIn("if (this.state.live !== 'live') return;\n    const t = this.traders.find", app_js)
        seite = (WURZEL / "web" / "js" / "pages" / "wallet_page.js").read_text(encoding="utf-8")
        self.assertIn("/^0x[0-9a-fA-F]{40}$/", seite)

    # ---- Copy desk ----------------------------------------------------------

    def test_copy_desk_traders_tab(self) -> None:
        # Two traders from the payload: the active one with its counts, the
        # paused one saying it has no curve and no baseline yet. Actions only
        # where the answer grants write access.
        live = _sichtbarer_text(self.ausgabe["live"]["copy"])
        self.assertIn("FOLLOW A WALLET", live)
        self.assertIn("FOLLOWING 1 active 1 paused", live)
        self.assertIn("WRITES · LOCAL", live)
        for wert in ("w1", "harness desk, slow trader", "ACTIVE", "1 / 0", "Pause", "w2", "PAUSED", "not seeded yet", "no curve yet", "no copy yet", "Resume", "Top up", "Edit"):
            self.assertIn(wert, live)
        self.assertIn("DAEMON RUNNING", live)
        self.assertIn("websocket connected", live)
        self.assertIn("Run one sync pass", live)
        self.assertIn("scripts\\run_copy_trader.py", live)
        # Every button on the desk carries a handler (data-act), none is a bare div.
        html = self.ausgabe["live"]["copy"]
        for knopf in ("Follow wallet", "Pause", "Resume", "Run one sync pass", "Refresh"):
            with self.subTest(knopf=knopf):
                self.assertRegex(html, r'data-act="\d+"[^>]*>' + re.escape(knopf) + "<")

    def test_copy_desk_read_only_and_token_states(self) -> None:
        ro = _sichtbarer_text(self.ausgabe["live"]["copy_readonly"])
        self.assertIn("READ-ONLY FROM HERE", ro)
        self.assertIn("COPY_ADMIN_TOKEN", ro)
        for weg in ("Follow wallet", "Pause", "Resume", "Run one sync pass", "Top up"):
            self.assertNotIn(weg, ro)
        token = _sichtbarer_text(self.ausgabe["live"]["copy_token_needed"])
        self.assertIn("ADMIN TOKEN", token)
        self.assertIn("Use token", token)
        self.assertNotIn("Follow wallet", token)

    def test_copy_desk_empty_and_error_states(self) -> None:
        leer = _sichtbarer_text(self.ausgabe["live"]["copy_no_traders"])
        self.assertIn("No traders followed yet", leer)
        self.assertIn("FOLLOWING 0 active", leer)
        self.assertIn("DAEMON NEVER RAN HERE", leer)
        self.assertIn("STATE NOT REPORTED", leer)
        fehler = _sichtbarer_text(self.ausgabe["live"]["copy_error"])
        self.assertIn("/api/copy did not answer: HTTP 404", fehler)
        self.assertNotIn("$", fehler)
        # In-flight and failed actions say so.
        self.assertIn("following…", _sichtbarer_text(self.ausgabe["live"]["copy_busy"]))
        self.assertIn("harness error line", _sichtbarer_text(self.ausgabe["live"]["copy_msg_err"]))

    def test_copy_desk_filters_settings_and_rows(self) -> None:
        # Trader filter: w2 has no orders, and the table says so instead of
        # showing w1's row.
        alle = _sichtbarer_text(self.ausgabe["live"]["copy_orders"])
        self.assertIn("Example question", alle)
        self.assertIn("TRADER All w1 w2", alle)
        nur_b = _sichtbarer_text(self.ausgabe["live"]["copy_filter_b"])
        self.assertNotIn("Example question", nur_b)
        self.assertIn("No paper orders reported by /api/copy yet.", nur_b)
        # Performance for one trader draws that trader's curve (three points)
        # and names it; the aggregate has no curve and says so.
        perf_a = self.ausgabe["live"]["copy_perf_filter_a"]
        self.assertIn("W1 — EQUITY VS CASH PUT IN", _sichtbarer_text(perf_a))
        self.assertRegex(perf_a, r'<polyline points="[0-9., ]+"')
        perf_all = self.ausgabe["live"]["copy_perf"]
        self.assertIn("No equity curve yet", _sichtbarer_text(perf_all))
        self.assertNotRegex(perf_all, r'<polyline points="[0-9., ]+"')
        # Settings tab: the editable fields with their saved values, and the
        # save button turns primary once something changed.
        settings = _sichtbarer_text(self.ausgabe["live"]["copy_settings"])
        for wert in ("SAME SHARE OF ACCOUNT", "FIXED % OF HIS TRADE", "DOLLAR FOR DOLLAR", "CASH THROTTLE", "AUTO TOP-UP",
                     "Save settings", "mode now: same share of account × 1"):
            self.assertIn(wert, settings)
        # Percent fields show percent (0.25 -> 25) and the worked example uses
        # the trader's source equity: $500 / $52,000 -> his $1,000 = $9.62 here.
        self.assertIn('value="25"', self.ausgabe["live"]["copy_settings"])
        self.assertIn("his equity $52,000 · your sub-account $500", settings)
        self.assertIn("his $1,000 bet (1.92 % of his account) = $9.62 here (1.92 % of yours)", settings)
        dirty = _sichtbarer_text(self.ausgabe["live"]["copy_settings_dirty"])
        self.assertIn("Discard changes", dirty)
        self.assertIn("mode now: fixed 2 % of his trade", dirty)
        self.assertIn("his $1,000 bet → $20.00 here (2 % of his trade", dirty)
        eins = _sichtbarer_text(self.ausgabe["live"]["copy_settings_one"])
        self.assertIn("mode now: dollar for dollar", eins)
        self.assertIn("his $1,000 bet → $1,000 here, dollar for dollar", eins)
        # The traders table names his equity and the neutral ratio per trader.
        self.assertIn("his equity $52,000 · ratio 0.962 %", _sichtbarer_text(self.ausgabe["live"]["copy"]))
        # Orders: a MERGE row says what a merge is and what the source holds
        # in that market now; the "Merges" chip keeps only that row.
        orders = _sichtbarer_text(self.ausgabe["live"]["copy_orders"])
        self.assertIn("KIND · SIDE", orders)
        self.assertIn("MERGE $3,000 $30 SETTLED", orders)
        self.assertIn("it is not a bet on Yes", orders)
        self.assertIn("source book now: 100 YES / 12.0k NO → net NO", orders)
        merges = _sichtbarer_text(self.ausgabe["live"]["copy_orders_merges"])
        self.assertIn("MERGE $3,000", merges)
        self.assertNotIn("BUY Yes $100", merges)
        # Inline rows.
        self.assertIn("NOTE — domain, cadence, why you follow", _sichtbarer_text(self.ausgabe["live"]["copy_edit_row"]))

    def test_risk_karte_zeigt_das_wallet_buch(self) -> None:
        # Before the answer: "reading", no side invented. With the answer: the
        # NO buys of a net-NO wallet ADD, the NO buys of a net-YES wallet are a
        # HEDGE / CLOSING — the reader sees which without opening the wallet.
        warten = _sichtbarer_text(self.ausgabe["live"]["risk"])
        self.assertIn("BOOK NOW reading the wallets' open positions", warten)
        # Closed card: the relation counts in one line; open card: one line
        # per wallet with the relation, the net side and the sentence.
        buch = _sichtbarer_text(self.ausgabe["live"]["risk_book"])
        self.assertIn("BOOK NOW 1 adds · 1 hedge / closing WALLETS 3", buch)
        self.assertNotIn("WALLET BOOK NOW", buch)
        offen = _sichtbarer_text(self.ausgabe["live"]["risk_open"])
        self.assertIn("0xbbb2…0002 ADDS TO BOOK · net NO holds 0 YES / 12.0k NO now", offen)
        self.assertIn("0xaaa1…0001 HEDGE / CLOSING · net YES holds 9.00k YES / 200 NO now", offen)
        self.assertIn("not a new NO bet", offen)
        fehler = _sichtbarer_text(self.ausgabe["live"]["risk_book_err"])
        self.assertIn("BOOK NOW not read (no answer within 45 s)", fehler)
        self.assertNotIn("net NO", fehler)
        # Kalshi cards (no wallets) carry no book line at all.
        self.assertEqual(offen.count("WALLET BOOK NOW"), 2)
        self.assertEqual(buch.count("BOOK NOW"), 1)
        self.assertIn("Add paper cash", _sichtbarer_text(self.ausgabe["live"]["copy_topup_row"]))
        # Cash events / positions carry a trader column and stay honest when empty.
        self.assertIn("No cash events reported by /api/copy", _sichtbarer_text(self.ausgabe["live"]["copy_cash"]))
        self.assertIn("No open paper positions reported by /api/copy", _sichtbarer_text(self.ausgabe["live"]["copy_positions"]))


if __name__ == "__main__":
    unittest.main()
