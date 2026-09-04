"""Die Arbitrage-scan-Seite: eine Studienseite ueber die Datei des Scanners.

Rendert ueber denselben Harness wie tests/test_web_leerzustand.py. Geprueft
wird, was die Seite aus tests/fixtures/arb_scan_example.json macht (jede
Zahl kommt aus der Datei), was sie ohne Datei, bei fehlgeschlagenem Abruf,
mit leeren Listen und mit einer Datei ohne Felder zeigt, und dass die reinen
Leseregeln (Health-Grenze, Verdikt-Satz, Aufteilung der Kandidaten) das tun,
was die Seite behauptet.
"""

from __future__ import annotations

import json
import unittest

from tests.test_web_leerzustand import WURZEL, _harness_ausgabe, _sichtbarer_text

FIXTURE = WURZEL / "tests" / "fixtures" / "arb_scan_example.json"


class ArbScanSeiteTest(unittest.TestCase):
    ausgabe: dict

    @classmethod
    def setUpClass(cls) -> None:
        cls.ausgabe = _harness_ausgabe()

    def test_fixture_ist_der_vertrag(self) -> None:
        daten = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.assertEqual(daten["schema"], "arb_scan/1")
        for feld in ("generated_at", "generator", "disclaimer", "health", "summary",
                     "strategies", "rejections_24h", "opportunities", "paper_positions"):
            self.assertIn(feld, daten)
        for o in daten["opportunities"]:
            for feld in ("id", "strategy", "venues", "title", "legs", "gross_edge_bps",
                         "executable_net_edge_bps", "status", "rule_match"):
                self.assertIn(feld, o, o.get("id"))

    def test_registrierung_in_allen_listen(self) -> None:
        api_js = (WURZEL / "web" / "js" / "api.js").read_text(encoding="utf-8")
        self.assertIn("'/api/research/arb-scan': 'arb_scan.json'", api_js)
        studies = (WURZEL / "web" / "js" / "studies.js").read_text(encoding="utf-8")
        self.assertIn("tab: 'Arb scan'", studies)
        system = (WURZEL / "web" / "js" / "pages" / "system_pages.js").read_text(encoding="utf-8")
        self.assertIn("'postmortems.json', 'field_notes.json', ARB_SCAN_DATEI", system)
        self.assertIn("studienSlug(study) === 'arb-scan'", system)
        app_js = (WURZEL / "web" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("this.navStudyByTab('Arb scan', 'Arbitrage scan')", app_js)
        self.assertIn("'SCANNER · ROLLING'", app_js)
        # #research/arb_scan und #research/arb-scan sind dieselbe Seite.
        self.assertIn("replace(/_/g, '-')", app_js)

    def test_rendert_in_jedem_zustand(self) -> None:
        for modus in ("leer", "live"):
            for name in ("research_arb_scan", "research_arb_scan_ohne_datei", "research_arb_scan_fehler",
                         "research_arb_scan_leere_listen", "research_arb_scan_nur_schema", "research_arb_scan_frisch"):
                with self.subTest(modus=modus, seite=name):
                    self.assertNotIn("RENDER-FEHLER", self.ausgabe[modus][name])

    # ---- ohne Datei -----------------------------------------------------------

    def test_ohne_datei_nennt_die_datei_und_den_schreiber(self) -> None:
        # Noch nicht geantwortet: der Ladezustand nennt die Datei.
        laedt = _sichtbarer_text(self.ausgabe["leer"]["research_arb_scan"])
        self.assertIn("RESEARCH · ARB SCAN", laedt)
        self.assertIn("loading public/data/arb_scan.json", laedt)
        # Geantwortet, aber keine Datei: der Leerzustand nennt Datei und Schreiber.
        for modus in ("leer", "live"):
            text = _sichtbarer_text(self.ausgabe[modus]["research_arb_scan_ohne_datei"])
            with self.subTest(modus=modus):
                self.assertIn("Cross-venue arbitrage scan", text)
                self.assertIn("public/data/arb_scan.json", text)
                self.assertIn("prediction-alpha-bot", text)
                self.assertNotIn("validated of", text)
                self.assertNotIn("Download the data", text)
        fehler = _sichtbarer_text(self.ausgabe["live"]["research_arb_scan_fehler"])
        self.assertIn("public/data/arb_scan.json did not answer: HTTP 503", fehler)
        self.assertNotIn("validated of", fehler)

    # ---- mit der Fixture ------------------------------------------------------

    def test_kopf_verdikt_stempel_und_kennzeichnung(self) -> None:
        html = self.ausgabe["live"]["research_arb_scan"]
        text = _sichtbarer_text(html)
        self.assertIn("Cross-venue arbitrage scan", text)
        self.assertIn("9 validated of 412 raw candidates in 24 h, 6 paper trades resolved.", text)
        # Registrierungsstempel und Publish-Uhr stehen beide (stempelBlock).
        self.assertIn("paper scanner · rolling", text)
        self.assertIn("published 2026-09-03 05:40 UTC", text)
        self.assertIn("PAPER SCANNER / DESCRIPTIVE", text)
        # Der Disclaimer des Erzeugers und der Vorbehalt aus dem Register.
        self.assertIn("GENERATOR'S DISCLAIMER", text)
        self.assertIn("no order was placed, no capital moved", text)
        self.assertIn('data-caveat="parity_not_arbitrage"', html)
        self.assertIn('data-caveat="modeled_not_realized"', html)
        # Snapshot-Zeile und Download-Link.
        self.assertIn("Snapshot 2026-09-03 05:40 UTC · generator prediction-alpha-bot@3f9c2a1 · mode paper · schema arb_scan/1", text)
        self.assertIn('href="./data/arb_scan.json"', html)
        self.assertIn("Download the data", text)

    def test_health_warnt_bei_altem_zyklus_und_nicht_bei_frischem(self) -> None:
        # Die Fixture ist vom 2026-09-03; gegen die echte Uhr ist der letzte
        # Zyklus aelter als drei Intervalle (90 s), die Leiste warnt.
        alt = self.ausgabe["live"]["research_arb_scan"]
        self.assertIn("border-left:2px solid var(--warn)", alt)
        text = _sichtbarer_text(alt)
        self.assertIn("ALIVE", text)
        self.assertIn("2,870 cycles / 24 h", text)
        self.assertIn("3 errors / 24 h", text)
        self.assertIn("(limit 1.5 min = 3 intervals)", text)
        self.assertRegex(text, r"last cycle [0-9.]+ (h|d) ago")
        # Derselbe Datensatz mit einem Zyklus von eben: keine Warnfarbe.
        frisch = self.ausgabe["live"]["research_arb_scan_frisch"]
        self.assertIn("border-left:2px solid var(--pos)", frisch)
        self.assertNotIn("border-left:2px solid var(--warn)", frisch)

    def test_health_regel_drei_intervalle(self) -> None:
        h = json.loads(self.ausgabe["live"]["_arb_health"])
        self.assertFalse(h["frisch"]["warnung"])
        self.assertFalse(h["frisch"]["zuAlt"])
        # 90 s ist genau die Grenze, nicht darueber.
        self.assertFalse(h["an_der_grenze"]["warnung"])
        self.assertTrue(h["alt"]["zuAlt"])
        self.assertTrue(h["alt"]["warnung"])
        self.assertAlmostEqual(h["alt"]["grenzeMin"], 1.5)
        # alive:false warnt auch bei einem Zyklus von eben.
        self.assertTrue(h["tot"]["warnung"])
        self.assertFalse(h["tot"]["zuAlt"])
        # Ohne Health-Block: unbekannt, keine Warnung und keine Behauptung.
        self.assertFalse(h["leer"]["bekannt"])
        self.assertFalse(h["leer"]["warnung"])
        # Ohne Intervall kann das Alter nicht beurteilt werden: nur alive zaehlt.
        self.assertIsNone(h["ohne_intervall"]["grenzeMin"])
        self.assertFalse(h["ohne_intervall"]["warnung"])
        self.assertGreater(h["ohne_intervall"]["alterMin"], 500)

    def test_verdikt_satz_nur_wenn_die_daten_ihn_tragen(self) -> None:
        v = json.loads(self.ausgabe["live"]["_arb_verdikt"])
        self.assertEqual(v["voll"], "9 validated of 412 raw candidates in 24 h, 6 paper trades resolved.")
        self.assertEqual(v["ohne_resolved"], "1 validated of 1 raw candidate in 24 h.")
        self.assertEqual(v["leer"], "")
        self.assertEqual(v["nur_validated"], "")
        # Nullen sind Messungen, kein fehlender Wert.
        self.assertEqual(v["null_werte"], "0 validated of 0 raw candidates in 24 h, 0 paper trades resolved.")

    def test_kennzahlen_aus_summary(self) -> None:
        text = _sichtbarer_text(self.ausgabe["live"]["research_arb_scan"])
        for wert in ("RAW CANDIDATES 24H 412", "VALIDATED 24H 9", "PAPER FIRED 24H 4",
                     "OPEN PAPER POSITIONS 3", "RESOLVED PAPER TRADES 6", "RESOLVED PAPER PNL +$3.42"):
            with self.subTest(wert=wert):
                self.assertIn(wert, text)
        # Die Stichprobennotiz steht an der PnL-Kachel und am Paper-Buch.
        self.assertEqual(text.count("6 resolved paper trades: far too few"), 2)

    def test_trichter_und_ablehnungsbalken(self) -> None:
        html = self.ausgabe["live"]["research_arb_scan"]
        text = _sichtbarer_text(html)
        self.assertIn("FUNNEL BY STRATEGY · LAST 24 H", text)
        self.assertIn("Cross-venue parity cross_venue_parity 301 6 2.0% 3 net_edge_below_fees", text)
        self.assertIn("Multi-outcome sum over one dollar multi_outcome_sum 23 1 4.3% 0 rule_mismatch_suspected", text)
        self.assertIn("WHY CANDIDATES WERE REJECTED · LAST 24 H · 403 REJECTIONS", text)
        # Balken aus Divs, groesster Grund voll, kleinster anteilig.
        self.assertIn("width:100.0%", html)
        self.assertIn("width:3.3%", html)
        self.assertIn("net_edge_below_fees 244", text)
        self.assertIn("days_to_resolution_too_long 8", text)
        # Keine SVG-Kurve: das Diagramm sind die Balken.
        self.assertNotRegex(html, r'<polyline points="\s*\d')

    def test_kandidaten_validierte_oben_abgelehnte_eingeklappt(self) -> None:
        html = self.ausgabe["live"]["research_arb_scan"]
        text = _sichtbarer_text(html)
        self.assertIn("CANDIDATES · 3 VALIDATED · 2 REJECTED", text)
        # Reihenfolge nach ausfuehrbarem Netto-Edge, groesster zuerst.
        fed = text.index("Fed cuts rates at the September 2026 meeting?")
        curtis = text.index("Will the Curtis E6 episode air before 15 September?")
        btc = text.index("Bitcoin above $70,000 on 30 September 2026?")
        self.assertLess(fed, curtis)
        self.assertLess(curtis, btc)
        # Zeile: Strategie und Venues unter dem Titel, Zahlen in bps und $.
        self.assertIn("cross_venue_parity · Polymarket ↔ Kalshi · paper_fired 250 bps 96 bps $180.00 $360.00 12.3 d 28.5% REVIEWED 27 min", text)
        self.assertIn("UNVERIFIED", text)
        # Abgelehnte darunter, zugeklappt, mit Grund.
        self.assertIn("REJECTED · 2 CANDIDATES WITH REASON", text)
        self.assertIn("rejected: rule_mismatch_suspected", text)
        self.assertIn("rejected: net_edge_below_fees", text)
        self.assertIn("MISMATCH", text)
        # Negativer Netto-Edge in der Abgelehnt-Farbe, positiver in gruen.
        self.assertIn("color:var(--neg-soft)\">-58 bps", html)
        self.assertIn("color:var(--pos)\">96 bps", html)
        # Legs je Zeile, aufklappbar; data-key haelt sie ueber den Poll offen.
        self.assertIn('data-key="arb:opp:opp-20260903-0007"', html)
        self.assertIn('data-key="arb:rejected"', html)
        self.assertIn("Polymarket BUY YES 61.5¢ $180.00 long $0.00", text)
        self.assertIn("Kalshi BUY NO 36.0¢ $180.00 hedge $2.52", text)
        self.assertIn("ref pm:0x8d1f…c3a2 / ks:KXFEDDECISION-26SEP-C25", text)
        # Ein Gap, das seit ueber einer Stunde offen ist, faerbt sich amber.
        self.assertIn("color:var(--warn)\" title=\"open for over an hour", html)
        self.assertIn("8.6 h", text)
        # Klebriger Tabellenkopf.
        self.assertIn("position:sticky; top:0; z-index:3", html)

    def test_aufteilung_der_kandidaten(self) -> None:
        t = json.loads(self.ausgabe["live"]["_arb_teilung"])
        self.assertEqual(t["oben"], ["opp-20260903-0007", "opp-20260903-0011", "opp-20260903-0003"])
        self.assertEqual(t["unten"], ["opp-20260903-0009", "opp-20260903-0014"])
        # Ohne Status entscheidet der Grund; ein unbekannter Status faellt nach unten.
        self.assertEqual(t["ohne_status"], ["a", "c"])

    def test_paper_buch_mit_stichprobennotiz(self) -> None:
        text = _sichtbarer_text(self.ausgabe["live"]["research_arb_scan"])
        self.assertIn("PAPER BOOK · 5 POSITIONS", text)
        self.assertIn("pt-20260903-0007 · from opp-20260903-0007 cross_venue_parity 2026-09-03 05:12 UTC $360.00 96 bps open open", text)
        self.assertIn("Jobless claims above 230k for the week of 29 August?", text)
        self.assertIn("+$0.86", text)
        self.assertIn("-$0.41", text)
        self.assertIn("Modeled value frozen at emit time; not realized profit.", text)

    def test_methodik_absatz(self) -> None:
        text = _sichtbarer_text(self.ausgabe["live"]["research_arb_scan"])
        self.assertIn("HOW TO READ THIS", text)
        self.assertIn("Executable net edge is the quoted gap after the fee schedule of both venues", text)
        self.assertIn("Rule match is unverified by default.", text)
        self.assertIn("That is carry, not arbitrage.", text)
        self.assertNotIn("risk-free", text.lower())

    # ---- leere Listen und leere Datei ------------------------------------------

    def test_leere_listen_sagen_es_und_zeigen_keine_erfundene_zeile(self) -> None:
        html = self.ausgabe["live"]["research_arb_scan_leere_listen"]
        text = _sichtbarer_text(html)
        self.assertIn("0 validated of 0 raw candidates in 24 h, 0 paper trades resolved.", text)
        self.assertIn("NOT ALIVE", text)
        self.assertIn("border-left:2px solid var(--warn)", html)
        for satz in ("No strategies in the payload.", "No rejections recorded in the last 24 h.",
                     "No candidates in the payload.", "No paper positions in the payload."):
            with self.subTest(satz=satz):
                self.assertIn(satz, text)
        self.assertIn("CANDIDATES · NONE VALIDATED", text)
        self.assertNotIn('data-key="arb:rejected"', html)
        self.assertIn("RESOLVED PAPER PNL —", text)
        self.assertIn("No resolved paper trades yet.", text)

    def test_datei_ohne_felder_zeigt_striche_statt_nullen(self) -> None:
        html = self.ausgabe["live"]["research_arb_scan_nur_schema"]
        text = _sichtbarer_text(html)
        self.assertIn("SCANNER HEALTH not in payload", text)
        self.assertNotIn("validated of", text)
        self.assertIn("RAW CANDIDATES 24H —", text)
        self.assertIn("RESOLVED PAPER PNL —", text)
        self.assertIn("Snapshot time not in payload · schema arb_scan/1", text)
        self.assertIn("No candidates in the payload.", text)
        # Kein einziges Feld traegt eine Null, die die Datei nicht enthaelt.
        self.assertNotIn(" 0 ", text)


if __name__ == "__main__":
    unittest.main()
