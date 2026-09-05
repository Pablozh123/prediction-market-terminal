"""Der Abschnitt "Paper scanner: executable edge" auf der Cross-venue-Seite.

Rendert ueber denselben Harness wie tests/test_web_leerzustand.py. Geprueft
wird, was der Abschnitt aus tests/fixtures/arb_scan_example.json macht (jede
Zahl kommt aus der Datei, die Datei kommt aus dem Scanner-Repo: npm run
feed:fixture), was er waehrend der Anfrage, ohne Datei, bei fehlgeschlagenem
Abruf, mit leeren Listen und mit einer Datei ohne Felder zeigt, dass die
bestehenden Cross-venue-Inhalte stehen bleiben, dass die alte Studienroute
umgeleitet wird, und dass die reinen Leseregeln (Health-Grenze, Verdikt-Satz,
Aufteilung der Kandidaten) das tun, was die Seite behauptet.

Seit 2026-09-05 traegt die Datei die Taxonomie des Scanners (Schema
arb_scan/2): Klasse, Horizont, Screen, Review, Gate. Jedes Wort auf der Seite
kommt aus ihrem vocabulary-Block; die Tests pruefen, dass die Seite sie so
zeigt und dass eine Zeile, die an Gate 1 gefallen ist, keine Renditezahl
traegt.
"""

from __future__ import annotations

import json
import unittest

from tests.test_web_leerzustand import WURZEL, _harness_ausgabe, _sichtbarer_text

FIXTURE = WURZEL / "tests" / "fixtures" / "arb_scan_example.json"
ABSCHNITT = "PAPER SCANNER · EXECUTABLE EDGE"
ANKER = 'id="cross/paper-scanner"'


class ArbScanAbschnittTest(unittest.TestCase):
    ausgabe: dict

    @classmethod
    def setUpClass(cls) -> None:
        cls.ausgabe = _harness_ausgabe()

    def _text(self) -> str:
        return _sichtbarer_text(self.ausgabe["live"]["cross"])

    def test_fixture_ist_der_vertrag(self) -> None:
        daten = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.assertEqual(daten["schema"], "arb_scan/2")
        for feld in ("generated_at", "generator", "disclaimer", "health", "config", "summary",
                     "strategies", "rejections_24h", "vocabulary", "opportunities", "chances",
                     "carry_candidates", "rejected_examples", "pairs", "paper_positions"):
            self.assertIn(feld, daten)
        for o in daten["opportunities"]:
            for feld in ("id", "strategy", "class", "venues", "title", "legs", "gross_edge_bps",
                         "executable_net_edge_bps", "net_profit_usd", "status", "rule_match",
                         "rule_screen", "rule_review", "gate_failed", "capital_lock_class",
                         "hurdle_met", "resolution_at_by_venue"):
                self.assertIn(feld, o, o.get("id"))
        # Die Woerter der Datei sind die des Scanners, nicht erfundene.
        strategien = {s["id"] for s in daten["vocabulary"]["strategies"]}
        self.assertEqual(strategien, {"neg_risk_bracket_arb", "within_market_fast_arb",
                                      "within_market_yes_no_arb", "clear_win_watch",
                                      "cross_venue_yes_no_arb"})
        gruende = {r["id"]: r for r in daten["vocabulary"]["rejection_reasons"]}
        self.assertEqual(gruende["multi_winner_or_qualifier_basket"]["gate"], 1)
        self.assertEqual(gruende["below_annualized_hurdle"]["gate"], 4)
        self.assertEqual([k["id"] for k in daten["vocabulary"]["classes"]],
                         ["same_market_complement", "neg_risk_no_basket", "cross_venue_complement",
                          "cross_venue_price_spread", "neg_risk_long_tail_no_carry",
                          "clear_win_convergence"])
        # Gate 1 traegt keine Renditezahl, in der Datei selbst.
        for o in daten["opportunities"]:
            if o["gate_failed"] == 1:
                self.assertIsNone(o["gross_edge_bps"], o["id"])
                self.assertIsNone(o["executable_net_edge_bps"], o["id"])
                self.assertIsNone(o["annualized_pct"], o["id"])
        self.assertEqual(daten["config"]["hurdle_pct"], 10)

    def test_registrierung_abschnitt_statt_studie(self) -> None:
        # Kein eigener Studieneintrag, kein Sidebar-Eintrag, keine eigene Route.
        studies = (WURZEL / "web" / "js" / "studies.js").read_text(encoding="utf-8")
        self.assertNotIn("Arb scan", studies)
        app_js = (WURZEL / "web" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertNotIn("navStudyByTab('Arb scan'", app_js)
        self.assertNotIn("SCANNER · ROLLING", app_js)
        system = (WURZEL / "web" / "js" / "pages" / "system_pages.js").read_text(encoding="utf-8")
        self.assertNotIn("arb_scan_page", system)
        self.assertNotIn("ARB_SCAN_DATEI", system)
        # Der Abschnitt haengt an der Cross-venue-Seite, die Daten an liveData.arbScan.
        core = (WURZEL / "web" / "js" / "pages" / "core_pages.js").read_text(encoding="utf-8")
        self.assertIn("import { renderArbScanAbschnitt } from './arb_scan_page.js';", core)
        self.assertEqual(core.count("renderArbScanAbschnitt(T.liveData.arbScan)"), 2)
        self.assertIn("this.holen('arbScan', '/api/research/arb-scan')", app_js)
        # Die alte Adresse leitet um: beide Schreibweisen, Anker auf den Abschnitt.
        self.assertIn("istArbScanAdresse(segmente)", app_js)
        self.assertIn("replace(/_/g, '-') === 'arb-scan'", app_js)
        self.assertIn("import { ARB_ANKER } from './pages/arb_scan_page.js';", app_js)
        self.assertEqual(app_js.count("this._pendingAnchor = ARB_ANKER;"), 2)
        self.assertEqual(app_js.count("history.replaceState(null, '', '#cross')"), 2)
        # Der statische Rueckfall und die API-Route bleiben.
        api_js = (WURZEL / "web" / "js" / "api.js").read_text(encoding="utf-8")
        self.assertIn("'/api/research/arb-scan': 'arb_scan.json'", api_js)
        smoke = (WURZEL / "scripts" / "ux_smoke.py").read_text(encoding="utf-8")
        self.assertIn('"#research/arb-scan"', smoke)
        self.assertNotIn('"Arbitrage scan"', smoke)

    def test_seite_tippt_keine_labels_ab(self) -> None:
        # Die Klartexte der Gruende, Klassen und Status stehen nur in der
        # Datei; das Modul kennt die Schluessel, nicht die Saetze.
        modul = (WURZEL / "web" / "js" / "pages" / "arb_scan_page.js").read_text(encoding="utf-8")
        for satz in ("legs can pay out more than once", "edge gone at executable prices",
                     "YES plus NO in one market", "identity and structure"):
            with self.subTest(satz=satz):
                self.assertNotIn(satz, modul)

    def test_rendert_in_jedem_zustand(self) -> None:
        for modus in ("leer", "live"):
            for name in ("cross", "cross_loading", "cross_gate_empty", "cross_arb_laedt", "cross_arb_ohne_datei",
                         "cross_arb_fehler", "cross_arb_leere_listen", "cross_arb_nur_schema", "cross_arb_frisch"):
                with self.subTest(modus=modus, seite=name):
                    self.assertNotIn("RENDER-FEHLER", self.ausgabe[modus][name])

    def test_abschnitt_steht_unter_jedem_zustand_des_paarvergleichs(self) -> None:
        # Laufender Scan, leeres Gate, Treffer: der Abschnitt mit Anker ist immer da,
        # und die bestehenden Cross-venue-Texte stehen unveraendert davor.
        for name in ("cross", "cross_loading", "cross_gate_empty"):
            html = self.ausgabe["live"][name]
            text = _sichtbarer_text(html)
            with self.subTest(seite=name):
                self.assertIn(ANKER, html)
                self.assertIn(ABSCHNITT, text)
                self.assertIn("CROSS-VENUE The same question, two prices", text)
                self.assertLess(text.index("The same question, two prices"), text.index(ABSCHNITT))
                self.assertIn("Paper scanner: executable edge", text)
        live = self._text()
        self.assertIn("1 of 9 candidate pairs clear the gate", live)
        self.assertLess(live.index("Example question"), live.index(ABSCHNITT))

    # ---- ohne Datei -----------------------------------------------------------

    def test_ohne_datei_nennt_die_datei_und_den_schreiber(self) -> None:
        # Noch nicht geantwortet (leerer Harness und Variante): der Ladesatz nennt die Datei.
        for name, modus in (("cross", "leer"), ("cross_arb_laedt", "live")):
            text = _sichtbarer_text(self.ausgabe[modus][name])
            with self.subTest(seite=name):
                self.assertIn(ABSCHNITT, text)
                self.assertIn("Loading public/data/arb_scan.json", text)
                self.assertNotIn("validated of", text)
        # Geantwortet, aber keine Datei: der Leerzustand nennt Datei und Schreiber.
        for modus in ("leer", "live"):
            text = _sichtbarer_text(self.ausgabe[modus]["cross_arb_ohne_datei"])
            with self.subTest(modus=modus):
                self.assertIn("No scan file yet.", text)
                self.assertIn("public/data/arb_scan.json", text)
                self.assertIn("prediction-alpha-bot", text)
                self.assertNotIn("validated of", text)
                self.assertNotIn("Download the data", text)
                self.assertNotIn("JSON.parse", text)
        fehler = _sichtbarer_text(self.ausgabe["live"]["cross_arb_fehler"])
        self.assertIn("public/data/arb_scan.json did not answer: HTTP 503", fehler)
        self.assertNotIn("validated of", fehler)

    # ---- mit der Fixture ------------------------------------------------------

    def test_kopf_verdikt_schwellen_stempel_und_kennzeichnung(self) -> None:
        html = self.ausgabe["live"]["cross"]
        text = self._text()
        self.assertIn("Paper scanner: executable edge", text)
        self.assertIn("2 validated of 54 raw candidates in 24 h, 2 carry candidates above the hurdle, 1 paper trade resolved.", text)
        # Die Schwellen, gegen die die Zahlen geprueft wurden, aus config.
        self.assertIn("JUDGED AGAINST · hurdle 10.0% a year · target size $20.00 · min executable capital $5.00 · short window 72 h · medium up to 14 d · legs priced as taker · fee schedule 2026-07-30", text)
        # Registrierungsstempel und Publish-Uhr stehen beide (stempelBlock).
        self.assertIn("paper scanner · rolling", text)
        self.assertIn("published 2026-09-05 14:00 UTC", text)
        self.assertIn("PAPER SCANNER / DESCRIPTIVE", text)
        # Der Disclaimer des Erzeugers und der Vorbehalt aus dem Register.
        self.assertIn("GENERATOR'S DISCLAIMER", text)
        self.assertIn("Paper-only research. Not trading advice.", text)
        self.assertIn('data-caveat="parity_not_arbitrage"', html)
        self.assertIn('data-caveat="modeled_not_realized"', html)
        # Snapshot-Zeile und Download-Link.
        self.assertIn("Snapshot 2026-09-05 14:00 UTC · generator prediction-alpha-bot@fixture · mode paper · schema arb_scan/2", text)
        self.assertIn('href="./data/arb_scan.json"', html)
        self.assertIn("Download the data", text)

    def test_health_warnt_bei_altem_zyklus_und_nicht_bei_frischem(self) -> None:
        # Die Fixture ist vom 2026-09-05 14:00 UTC; gegen die echte Uhr ist der
        # letzte Zyklus aelter als drei Intervalle, die Leiste warnt und nennt
        # die gehaltene Kadenz neben der konfigurierten.
        alt = self.ausgabe["live"]["cross"]
        self.assertIn("border-left:2px solid var(--warn)", alt)
        text = _sichtbarer_text(alt)
        self.assertIn("ALIVE", text)
        self.assertIn("6 cycles / 24 h", text)
        self.assertIn("1 error / 24 h", text)
        self.assertIn("(limit 1.5 min = 3 intervals)", text)
        self.assertIn("cadence 30 s kept against 10 s configured", text)
        self.assertRegex(text, r"last cycle [0-9.]+ (min|h|d) ago")
        # Derselbe Datensatz mit einem Zyklus von eben: keine Warnfarbe.
        frisch = self.ausgabe["live"]["cross_arb_frisch"]
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
        # Die Grenze folgt der gehaltenen Kadenz (30 s), nicht der konfigurierten (10 s).
        self.assertEqual(h["frisch"]["konfiguriertMs"], 10000)
        self.assertEqual(h["frisch"]["effektivMs"], 30000)
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
        self.assertEqual(v["voll"], "2 validated of 54 raw candidates in 24 h, 2 carry candidates above the hurdle, 1 paper trade resolved.")
        # Eine Datei der ersten Fassung (ohne Carry-Zaehler) liest sich wie vorher.
        self.assertEqual(v["ohne_resolved"], "1 validated of 1 raw candidate in 24 h.")
        self.assertEqual(v["leer"], "")
        self.assertEqual(v["nur_validated"], "")
        # Nullen sind Messungen, kein fehlender Wert.
        self.assertEqual(v["null_werte"], "0 validated of 0 raw candidates in 24 h, 0 paper trades resolved.")

    def test_kennzahlen_aus_summary(self) -> None:
        text = self._text()
        for wert in ("RAW CANDIDATES 24H 54", "NEAR MISSES 24H 612", "VALIDATED 24H 2",
                     "CARRY CANDIDATES 24H 2", "PAPER FIRED 24H 2", "OPEN PAPER POSITIONS 2",
                     "RESOLVED PAPER TRADES 1", "RESOLVED PAPER PNL +$10.20"):
            with self.subTest(wert=wert):
                self.assertIn(wert, text)
        # Die Stichprobennotiz steht an der PnL-Kachel und am Paper-Buch.
        self.assertEqual(text.count("1 resolved paper trade(s) with a linked candidate"), 2)

    def test_trichter_mit_klasse_near_miss_und_carry(self) -> None:
        text = self._text()
        self.assertIn("FUNNEL BY STRATEGY · LAST 24 H", text)
        self.assertIn("STRATEGY RAW 24H NEAR MISS VALIDATED CARRY PAPER TOP REJECTION", text)
        self.assertIn("Within-market YES+NO (Polymarket) within_market_fast_arb · YES plus NO in one market 41 612 1 2.4% 0 2 edge gone at executable prices (gate 3)", text)
        self.assertIn("Cross-venue YES/NO (Kalshi x Polymarket) cross_venue_yes_no_arb · YES on one venue, NO on the other 7 0 1 14% 1 0 titles ask different questions (gate 1)", text)
        self.assertIn("NEG_RISK bracket sum-arb (Polymarket) neg_risk_bracket_arb · NO on every leg of a NEG_RISK event 5 0 0 0.0% 1 0 annualised net return below the hurdle rate (gate 4)", text)
        self.assertIn("NEAR MISS is the watch band above one dollar", text)

    def test_ablehnungsbalken_mit_klartext_und_gate(self) -> None:
        html = self.ausgabe["live"]["cross"]
        text = self._text()
        self.assertIn("WHY CANDIDATES WERE REJECTED · LAST 24 H · 6 REJECTIONS", text)
        self.assertIn("legs can pay out more than once multi_winner_or_qualifier_basket · gate 1 identity and structure 1", text)
        self.assertIn("annualised net return below the hurdle rate below_annualized_hurdle · gate 4 horizon 1", text)
        # Sechs Gruende zu je einem Treffer: sechs volle Balken, kein Diagramm.
        self.assertEqual(html.count("width:100.0%"), 6)
        self.assertNotRegex(html, r'<polyline points="\s*\d')

    def test_chancen_nur_was_jedes_gate_bestanden_hat(self) -> None:
        html = self.ausgabe["live"]["cross"]
        text = self._text()
        self.assertIn("CHANCES · 2 PASSED EVERY GATE", text)
        self.assertIn("CANDIDATE · CLASS · VENUES HORIZON RULES GROSS NET EXEC. NET $ DEPTH CAPITAL DAYS ANN. · HURDLE OPEN SINCE", text)
        # Reihenfolge nach Dollar-Gewinn am ausfuehrbaren Volumen, nicht nach Prozent:
        # 5.68 Dollar bei 19 Prozent vor 0.29 Dollar bei 536 Prozent.
        somaliland = text.index("Will Trump recognize Somaliland before 2027? YES on one venue, NO on the other · cross_venue_yes_no_arb · kalshi ↔ polymarket CARRY · LONG SCREEN PASSED REVIEW · EQUIVALENT 764.3 bps 611.4 bps +$5.68 $92.90 $92.90 117 d 19.0% ✓")
        fed = text.index("Will the Fed cut rates by 25 bps at the September 2026 meeting? YES plus NO in one market · within_market_fast_arb · polymarket ARB · SHORT STRUCTURAL 193.7 bps 146.8 bps +$0.29 $380.00 $19.62 1.1 d 535.8% ✓")
        self.assertLess(somaliland, fed)
        # Beide Termine je Zeile, Legs aufklappbar, data-key haelt sie ueber den Poll offen.
        self.assertIn("Kalshi settles 2026-12-31 · Polymarket settles 2026-12-31", text)
        self.assertIn('data-key="arb:opp:opp-0005"', html)
        self.assertIn("kalshi YES 36.0¢ $36.00 taker $0.90", text)
        self.assertIn("polymarket NO 56.9¢ $56.90 taker $0.52", text)
        self.assertIn("screen one contract: equivalence by construction", text)
        self.assertIn("review a person read both rulebooks and found them equivalent", text)
        # Klebrige Tabellenkoepfe: Paarvergleich plus die Koepfe des Abschnitts.
        self.assertGreaterEqual(html.count("position:sticky; top:0; z-index:3"), 8)

    def test_carry_tafel_heisst_carry_und_nennt_die_hurdle(self) -> None:
        text = self._text()
        self.assertIn("CARRY CANDIDATES · 2 · CARRY, NOT ARBITRAGE", text)
        self.assertIn("Will Marine Le Pen win the 2027 French presidential election? YES on one venue, NO on the other · cross_venue_yes_no_arb · polymarket ↔ kalshi CARRY · LONG SCREEN PASSED NO REVIEW 416.7 bps 137.5 bps +$1.32 $96.00 $96.00 237 d 12.1% ✓", text)
        self.assertIn("Kalshi settles 2028-05-29 · Polymarket settles 2027-04-30", text)
        self.assertIn("OpenSea FDV one day after launch NO on every leg of a NEG_RISK event · neg_risk_bracket_arb · polymarket CARRY · LONG SCREEN PASSED 330.6 bps 299.1 bps +$0.59 $4.8k $19.77 41.0 d 26.6% ✓", text)
        self.assertIn("the hurdle of 10.0% a year", text)
        self.assertIn("does not paper-fire them", text)
        # Die Chancen stehen vor den Carry-Kandidaten, die vor den Ablehnungen.
        self.assertLess(text.index("CHANCES · 2 PASSED EVERY GATE"), text.index("CARRY CANDIDATES · 2"))
        self.assertLess(text.index("CARRY CANDIDATES · 2"), text.index("REJECTED · 6 IN 24 H"))

    def test_abgelehnte_je_grund_mit_gate_und_ohne_rendite_an_gate_1(self) -> None:
        html = self.ausgabe["live"]["cross"]
        text = self._text()
        self.assertIn("REJECTED · 6 IN 24 H · 6 REASONS WITH EXAMPLES", text)
        self.assertIn('data-key="arb:rejected"', html)
        # Der Brasilien-Korb vom 2026-09-05: Gate 1, Multi-Winner, keine einzige Renditezahl.
        self.assertIn("Which candidates will advance to Brazil's presidential runoff? NO on every leg of a NEG_RISK event · neg_risk_bracket_arb · polymarket · legs can pay out more than once CARRY · LONG GATE 1 · IDENTITY AND STRUCTURE — — — $0.00 $0.00 — —", text)
        self.assertIn("rejection multi_winner_or_qualifier_basket at gate 1 (identity and structure)", text)
        # Ein Mensch hat die Regelwerke als verschieden befunden: Gate 1, MISMATCH-Wort im alten Feld.
        self.assertIn("Will Marco Rubio win the 2028 US Presidential Election? YES on one venue, NO on the other · cross_venue_yes_no_arb · kalshi ↔ polymarket · a person found the two rulebooks not equivalent CARRY · LONG SCREEN PASSED REVIEW · NOT EQUIVALENT GATE 1 · IDENTITY AND STRUCTURE — — —", text)
        # Gate 3 und 4 tragen ihre Zahlen weiter, in der Abgelehnt-Farbe.
        self.assertIn("Macron out as President of France by December 31, 2026?", text)
        self.assertIn("color:var(--neg-soft)\">-91.2 bps", html)
        self.assertIn("2028 Republican presidential nominee", text)
        self.assertIn("0.2% ✗", text)
        self.assertIn("SCREEN · DIFFERENT QUESTION", text)

    def test_paartafel_mit_screen_review_terminen_und_regeltexten(self) -> None:
        html = self.ausgabe["live"]["cross"]
        text = self._text()
        self.assertIn("CROSS-VENUE PAIR BOARD · 4 PAIRS", text)
        self.assertIn("PAIR · KALSHI ↔ POLYMARKET SCREEN REVIEW SETTLES LAST NET ANN. HEDGED", text)
        self.assertEqual(html.count('data-key="arb:pair:'), 4)
        # Somaliland: geprueft, gleich, gehedgt, zuerst.
        somaliland = text.index("Will Trump recognize Somaliland before 2027? KXRECOGSOMALI-29-27 ↔ will-trump-recognize-somaliland-before-2027 · config SCREEN PASSED REVIEW · EQUIVALENT 2026-09-08")
        self.assertIn("+5.68¢ 19.0% HEDGED", text)
        # Rubio: geprueft, nicht gleich, zwei offene Wetten, ein Jahr Abstand.
        rubio = text.index("KXPRESPERSON-28-MRUB ↔ will-marco-rubio-win-the-2028-us-presidential-election · config SCREEN PASSED REVIEW · NOT EQUIVALENT 2026-07-31")
        self.assertLess(somaliland, rubio)
        self.assertIn("365 d apart", text)
        self.assertIn("TWO OPEN BETS", text)
        self.assertIn("checklist: 1 ✓ 2 ✗ 3 ✗ 4 ✓ 5 ✗ 6 ✓ 7 · 365 days apart, Kalshi later", text)
        self.assertIn("Kalshi pays on who is inaugurated in 2029; Polymarket on who wins the election per AP, Fox and NBC.", text)
        self.assertIn("If Marco Rubio is the next person inaugurated as President for the term beginning in 2029, then the market resolves to Yes.", text)
        self.assertIn("source: docs/research/resolution_rules_2026-07-31.md", text)
        # Le Pen: Screen bestanden, kein Review, kein HEDGED.
        self.assertIn("KXFRENCHPRES-27-MLEP ↔ will-marine-le-pen-win-the-2027-french-presidential-election · config SCREEN PASSED NO REVIEW", text)
        self.assertIn("No review on file: nobody has read both rulebooks for this pair.", text)
        # Michigan: der Screen sagt nein, mit Begruendung.
        self.assertIn("KXMISENPRIMMARGIN-26 ↔ will-abdul-el-sayed-win-the-2026-michigan-democratic-senate-primary · discovery SCREEN · DIFFERENT QUESTION NO REVIEW", text)
        self.assertIn("screen: different question types: result against margin", text)
        # Genau ein HEDGED-Chip auf vier Paaren; die anderen drei tragen TWO OPEN BETS.
        self.assertEqual(html.count(">HEDGED</span>"), 1)
        self.assertEqual(html.count(">TWO OPEN BETS</span>"), 3)
        self.assertIn("HEDGED appears only after an equivalent review", text)

    def test_aufteilung_der_kandidaten(self) -> None:
        t = json.loads(self.ausgabe["live"]["_arb_teilung"])
        # Die Leseregel der ersten Fassung: validated oben, alles andere (auch
        # candidate) unten, sortiert nach Netto-Edge.
        self.assertEqual(t["oben"], ["opp-0005", "opp-0010"])
        self.assertEqual(set(t["unten"]), {"opp-0001", "opp-0002", "opp-0003", "opp-0004", "opp-0006", "opp-0007", "opp-0008", "opp-0009"})
        self.assertEqual(t["unten"][:3], ["opp-0006", "opp-0002", "opp-0007"])
        # Ohne Status entscheidet der Grund; ein unbekannter Status faellt nach unten.
        self.assertEqual(t["ohne_status"], ["a", "c"])

    def test_paper_buch_mit_stichprobennotiz(self) -> None:
        text = self._text()
        self.assertIn("PAPER BOOK · 3 POSITIONS", text)
        self.assertIn("Jobless claims above 230k for the week of 29 August?", text)
        self.assertIn("+$10.20", text)
        self.assertIn("pt-0003 · from opp-0010 within_market_fast_arb", text)
        self.assertIn("Modeled value frozen at emit time; not realized profit.", text)

    def test_klassentafel_und_methodik(self) -> None:
        text = self._text()
        self.assertIn("WHAT THE SCANNER CALLS ARBITRAGE, AND WHAT IT DOES NOT", text)
        self.assertIn("neg_risk_long_tail_no_carry · defined, not scanned", text)
        self.assertIn("Never fixed by contract.", text)
        self.assertIn("Fixed by contract when always: one contract, one rulebook.", text)
        self.assertIn("HOW TO READ THIS", text)
        self.assertIn("Five gates, in a fixed order.", text)
        self.assertIn("Rules: screen and review are two different things.", text)
        self.assertIn("That is carry, not arbitrage.", text)
        self.assertNotIn("risk-free", text.lower())

    # ---- leere Listen und leere Datei ------------------------------------------

    def test_leere_listen_der_ersten_fassung_lesen_sich_wie_vorher(self) -> None:
        html = self.ausgabe["live"]["cross_arb_leere_listen"]
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
        self.assertNotIn("CARRY CANDIDATES", text)
        self.assertIn("RESOLVED PAPER PNL —", text)
        self.assertIn("No resolved paper trades yet.", text)

    def test_datei_ohne_felder_zeigt_striche_statt_nullen(self) -> None:
        html = self.ausgabe["live"]["cross_arb_nur_schema"]
        text = _sichtbarer_text(html)
        self.assertIn("SCANNER HEALTH not in payload", text)
        self.assertNotIn("validated of", text)
        self.assertNotIn("JUDGED AGAINST", text)
        self.assertIn("RAW CANDIDATES 24H —", text)
        self.assertIn("RESOLVED PAPER PNL —", text)
        self.assertIn("Snapshot time not in payload · schema arb_scan/1", text)
        self.assertIn("No candidates in the payload.", text)
        # Kein Feld des Abschnitts traegt eine Null, die die Datei nicht enthaelt.
        abschnitt = text[text.index(ABSCHNITT):]
        self.assertNotIn(" 0 ", abschnitt)


if __name__ == "__main__":
    unittest.main()
