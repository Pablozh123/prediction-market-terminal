import json
import unittest
from datetime import date
from pathlib import Path

from app import pilot_result as pr

PROJEKT = Path(__file__).resolve().parents[1]
PILOT = PROJEKT / "public" / "data" / "pilot.json"


def _trade(**felder):
    basis = {
        "zeitstempel_utc": "2026-07-22T13:07:54Z",
        "arm": "arm2",
        "signal_regel": "arm2_favorit_090_097_max21d",
        "signalpreis": "0.92",
        "ausfuehrungspreis": "0.94",
        "groesse_usd": "5.0",
        "slippage": "0.02",
        "orderbuchtiefe_einstieg_usd": "460",
        "exit_preis": "",
    }
    basis.update(felder)
    return basis


def _payload(trades, **protokoll):
    kopf = {
        "budget_usdc": 100.0,
        "einsatz_je_trade_usdc": 5.0,
        "regel_freeze_datum": "2026-07-18",
        "handelsfenster_bis": "2026-08-01",
    }
    kopf.update(protokoll)
    return {"protokoll": kopf, "trades": trades}


class PhasenTests(unittest.TestCase):
    def test_fenster_offen(self):
        r = pr.evaluate(_payload([_trade()]), heute=date(2026, 7, 25))
        self.assertEqual(r["phase"], pr.PHASE_LAEUFT)

    def test_fenster_zu_aber_positionen_offen(self):
        r = pr.evaluate(_payload([_trade()]), heute=date(2026, 8, 4))
        self.assertEqual(r["phase"], pr.PHASE_OFFEN)
        self.assertIn("still open", r["offener_ausgang"])

    def test_alles_geschlossen(self):
        r = pr.evaluate(_payload([_trade(exit_preis="1.0")]), heute=date(2026, 8, 4))
        self.assertEqual(r["phase"], pr.PHASE_FERTIG)
        self.assertNotIn("offener_ausgang", r)

    def test_am_letzten_tag_ist_das_fenster_noch_offen(self):
        r = pr.evaluate(_payload([_trade()]), heute=date(2026, 8, 1))
        self.assertEqual(r["phase"], pr.PHASE_LAEUFT)

    def test_ohne_trades(self):
        r = pr.evaluate(_payload([]), heute=date(2026, 8, 4))
        self.assertEqual(r["trades"]["gesamt"], 0)
        self.assertIn("No trades", r["befund"])

    def test_leere_nutzlast(self):
        self.assertEqual(pr.evaluate(None), {})
        self.assertEqual(pr.evaluate({}), {})


class SlippageTests(unittest.TestCase):
    def test_rechnet_richtungen_aus(self):
        r = pr.evaluate(_payload([
            _trade(slippage="0.02"),
            _trade(slippage="-0.01"),
            _trade(slippage="0.0"),
        ]), heute=date(2026, 8, 4))
        s = r["slippage"]
        self.assertEqual(s["n"], 3)
        self.assertEqual(s["teurer_als_signal"], 1)
        self.assertEqual(s["billiger_als_signal"], 1)
        self.assertEqual(s["genau_am_signal"], 1)
        self.assertEqual(s["schlechtester"], 0.02)
        self.assertEqual(s["bester"], -0.01)

    def test_faellt_auf_die_preisdifferenz_zurueck(self):
        r = pr.evaluate(_payload([
            _trade(slippage="", signalpreis="0.90", ausfuehrungspreis="0.95"),
        ]), heute=date(2026, 8, 4))
        self.assertEqual(r["slippage"]["mittel"], 0.05)

    def test_ohne_preise_keine_slippage(self):
        r = pr.evaluate(_payload([
            _trade(slippage="", signalpreis="", ausfuehrungspreis=""),
        ]), heute=date(2026, 8, 4))
        self.assertEqual(r["slippage"], {"n": 0, "episoden": 0})
        self.assertIn("nothing to measure", r["befund"])


class RegeltreueTests(unittest.TestCase):
    def test_sauberer_lauf_besteht_alles(self):
        r = pr.evaluate(_payload([_trade(), _trade()]), heute=date(2026, 8, 4))
        rt = r["regeltreue"]
        self.assertEqual(rt["erfuellt"], rt["gesamt"])

    def test_abweichender_einsatz_wird_gemeldet(self):
        r = pr.evaluate(
            _payload([_trade(groesse_usd="5.0")], einsatz_je_trade_usdc=10.0),
            heute=date(2026, 8, 4),
        )
        punkt = next(p for p in r["regeltreue"]["punkte"] if "Stake" in p["regel"])
        self.assertFalse(punkt["erfuellt"])
        self.assertIn("hinweis", punkt)

    def test_preis_ausserhalb_der_bandbreite_faellt_auf(self):
        r = pr.evaluate(_payload([_trade(signalpreis="0.80")]), heute=date(2026, 8, 4))
        punkt = next(p for p in r["regeltreue"]["punkte"] if "band" in p["regel"])
        self.assertFalse(punkt["erfuellt"])
        self.assertIn("0 of 1", punkt["ist"])

    def test_zwei_verschiedene_regeln_fallen_auf(self):
        r = pr.evaluate(
            _payload([_trade(), _trade(signal_regel="arm1_referenz")]),
            heute=date(2026, 8, 4),
        )
        punkt = next(p for p in r["regeltreue"]["punkte"] if "frozen signal rule" in p["regel"])
        self.assertFalse(punkt["erfuellt"])

    def test_budgetueberschreitung_faellt_auf(self):
        trades = [_trade(groesse_usd="60.0"), _trade(groesse_usd="60.0")]
        r = pr.evaluate(_payload(trades, einsatz_je_trade_usdc=60.0), heute=date(2026, 8, 4))
        punkt = next(p for p in r["regeltreue"]["punkte"] if "budget" in p["regel"].lower())
        self.assertFalse(punkt["erfuellt"])


class BefundTests(unittest.TestCase):
    def test_setzt_slippage_ins_verhaeltnis_zum_spielraum(self):
        r = pr.evaluate(_payload([
            _trade(slippage="0.02", ausfuehrungspreis="0.90"),
        ]), heute=date(2026, 8, 4))
        # Spielraum 10 Cent, Slippage 2 Cent -> 20 Prozent
        self.assertIn("20 percent", r["befund"])

    def test_kein_spielraum_wird_nicht_durch_null_geteilt(self):
        r = pr.evaluate(_payload([
            _trade(slippage="0.01", ausfuehrungspreis="1.0"),
        ]), heute=date(2026, 8, 4))
        self.assertIn("no upside", r["befund"])


class EchtdatenTests(unittest.TestCase):
    """Gegen die publizierte Datei, ohne Annahme ueber ihren Inhalt.

    `public/data/pilot.json` ist laufzeitgeneriert: je nach Stand stehen
    dort null oder zwanzig Trades. Geprueft wird deshalb, dass die
    Auswertung auf der echten Struktur durchlaeuft und wohlgeformt ist,
    nicht wieviel gerade drinsteht.
    """

    @unittest.skipUnless(PILOT.exists(), "public/data/pilot.json fehlt")
    def test_laeuft_auf_der_publizierten_datei(self):
        payload = json.loads(PILOT.read_text(encoding="utf-8"))
        r = pr.evaluate(payload, heute=date(2026, 8, 4))
        self.assertIn(r["phase"], (pr.PHASE_LAEUFT, pr.PHASE_OFFEN,
                                   pr.PHASE_UNGEKLAERT, pr.PHASE_FERTIG))
        self.assertTrue(r["befund"])
        self.assertGreaterEqual(r["trades"]["gesamt"], 0)
        if r["trades"]["gesamt"]:
            self.assertIn("slippage", r)
            self.assertIn("regeltreue", r)

    @unittest.skipUnless(PILOT.exists(), "public/data/pilot.json fehlt")
    def test_die_publizierte_datei_traegt_ihren_ausgang_nicht_ewig_als_offen(self):
        """Die 20 Eintritte stammen alle vom 2026-07-22, Arm 2 nimmt hoechstens
        21 Tage Restlaufzeit. Ab dem 2026-08-13 kann keine Position mehr offen
        sein; leere Exit-Zellen sind dann ein fehlender Eintrag."""
        payload = json.loads(PILOT.read_text(encoding="utf-8"))
        if not (payload.get("trades") or []):
            self.skipTest("keine Trades in der publizierten Datei")
        spaet = pr.evaluate(payload, heute=date(2026, 9, 30))
        if spaet["trades"]["offen"]:
            self.assertEqual(spaet["phase"], pr.PHASE_UNGEKLAERT)
            self.assertIn("was not written back", spaet["offener_ausgang"])


class AusgangsfristTests(unittest.TestCase):
    """Eine leere Exit-Zelle heisst nur so lange "offen", wie das Protokoll die
    Position offen sein laesst. Danach ist sie ein fehlender Eintrag, und ein
    Verlust saehe genauso aus."""

    def _payload_mit_frist(self, tage=21.0):
        return {"protokoll": {"budget_usdc": 100.0, "einsatz_je_trade_usdc": 5.0,
                              "handelsfenster_bis": "2026-08-01"},
                "watcher_parameter": {"arm2_max_restlaufzeit_tage": tage,
                                      "arm2_min_preis": 0.9, "arm2_max_preis": 0.97},
                "trades": [_trade()]}

    def test_innerhalb_der_frist_bleibt_es_offen(self):
        r = pr.evaluate(self._payload_mit_frist(), heute=date(2026, 8, 5))
        self.assertEqual(r["phase"], pr.PHASE_OFFEN)
        self.assertIn("still open", r["offener_ausgang"])

    def test_nach_der_frist_ist_der_ausgang_ungeklaert(self):
        r = pr.evaluate(self._payload_mit_frist(), heute=date(2026, 8, 28))
        self.assertEqual(r["phase"], pr.PHASE_UNGEKLAERT)
        self.assertEqual(r["phase_text"], "Entry window closed, outcome not recorded")
        self.assertIn("a loss would look exactly like this", r["offener_ausgang"])
        self.assertEqual(r["endpunkte"]["spaetester_ausgang"], "2026-08-12")

    def test_eingetragene_exits_bleiben_abgeschlossen(self):
        payload = self._payload_mit_frist()
        payload["trades"] = [_trade(exit_preis="1.0")]
        r = pr.evaluate(payload, heute=date(2026, 8, 28))
        self.assertEqual(r["phase"], pr.PHASE_FERTIG)
        self.assertNotIn("offener_ausgang", r)

    def test_ohne_frist_greift_die_protokollvoreinstellung(self):
        payload = self._payload_mit_frist()
        payload.pop("watcher_parameter")
        r = pr.evaluate(payload, heute=date(2026, 8, 28))
        self.assertEqual(r["phase"], pr.PHASE_UNGEKLAERT)


class ArmBandTests(unittest.TestCase):
    """Arm 1 fadet eine bereits entschiedene Seite und hat keine Untergrenze.
    Beide Arme gegen 0.90 bis 0.97 zu pruefen meldete jeden erlaubten
    Arm-1-Trade als Protokollbruch."""

    def _band_punkt(self, trades):
        payload = {"protokoll": {"budget_usdc": 100.0, "handelsfenster_bis": "2026-08-01"},
                   "watcher_parameter": {"arm1_max_entry_preis": 0.97,
                                         "arm2_min_preis": 0.9, "arm2_max_preis": 0.97},
                   "trades": trades}
        r = pr.evaluate(payload, heute=date(2026, 8, 4))
        return next(p for p in r["regeltreue"]["punkte"] if "band" in p["regel"])

    def test_arm1_unter_090_ist_kein_protokollbruch(self):
        punkt = self._band_punkt([_trade(arm="arm1", signalpreis="0.62",
                                         signal_regel="arm1_referenz")])
        self.assertTrue(punkt["erfuellt"])
        self.assertEqual(punkt["abweichungen"], [])
        self.assertIn("arm1 at most 0.97", punkt["regel"])

    def test_arm1_ueber_seiner_obergrenze_faellt_auf(self):
        punkt = self._band_punkt([_trade(arm="arm1", signalpreis="0.985",
                                         signal_regel="arm1_referenz")])
        self.assertFalse(punkt["erfuellt"])
        self.assertEqual(punkt["abweichungen"], ["arm1 0.985"])

    def test_arm2_behaelt_seine_untergrenze(self):
        punkt = self._band_punkt([_trade(arm="arm2", signalpreis="0.80")])
        self.assertFalse(punkt["erfuellt"])
        self.assertEqual(punkt["abweichungen"], ["arm2 0.8"])

    def test_beide_arme_werden_gegen_ihr_eigenes_band_geprueft(self):
        punkt = self._band_punkt([
            _trade(arm="arm1", signalpreis="0.62", signal_regel="arm1_referenz"),
            _trade(arm="arm2", signalpreis="0.93"),
        ])
        self.assertTrue(punkt["erfuellt"])
        self.assertIn("2 of 2 inside", punkt["ist"])


class StichprobeTests(unittest.TestCase):
    """Zwanzig Fills aus einem einzigen automatisierten Lauf sind zwanzig
    Positionen und ein Moment."""

    def test_mittelwert_traegt_intervall_und_episodenzahl(self):
        trades = [_trade(slippage=str(v), zeitstempel_utc="2026-07-22T13:07:54Z")
                  for v in ("0.01", "0.02", "0.03", "0.02")]
        r = pr.evaluate({"protokoll": {"handelsfenster_bis": "2026-08-01"},
                         "trades": trades}, heute=date(2026, 8, 4))
        sl = r["slippage"]
        self.assertEqual(sl["n"], 4)
        self.assertEqual(sl["episoden"], 1)
        self.assertIsNotNone(sl["ci_low"])
        self.assertLess(sl["ci_low"], sl["mittel"])
        self.assertGreater(sl["ci_high"], sl["mittel"])
        self.assertIn("4 fills from 1 execution moment", r["befund"])
        self.assertIn("not one independent draw per fill", r["befund"])
        self.assertIn("95 percent interval", r["befund"])

    def test_mehrere_momente_werden_gezaehlt(self):
        trades = [_trade(slippage="0.01", zeitstempel_utc="2026-07-22T13:07:54Z"),
                  _trade(slippage="0.03", zeitstempel_utc="2026-07-23T09:00:00Z")]
        r = pr.evaluate({"protokoll": {"handelsfenster_bis": "2026-08-01"},
                         "trades": trades}, heute=date(2026, 8, 4))
        self.assertEqual(r["slippage"]["episoden"], 2)
        self.assertNotIn("not one independent draw", r["befund"])

    def test_ein_einziger_fill_bekommt_kein_intervall(self):
        r = pr.evaluate(_payload([_trade()]), heute=date(2026, 8, 4))
        self.assertIsNone(r["slippage"]["ci_low"])
        self.assertIsNone(r["slippage"]["ci_high"])


class EndpunktTests(unittest.TestCase):
    def test_nennt_was_gemessen_ist_und_was_offen_bleibt(self):
        r = pr.evaluate(_payload([_trade()], quelle="docs/protokoll.md"),
                        heute=date(2026, 8, 4))
        endpunkte = r["endpunkte"]
        self.assertIn("execution friction", endpunkte["gemessen"])
        self.assertIn("settled outcome", endpunkte["offen"])
        self.assertEqual(endpunkte["protokoll_quelle"], "docs/protokoll.md")

    def test_fehlende_protokollquelle_wird_benannt(self):
        r = pr.evaluate(_payload([_trade()]), heute=date(2026, 8, 4))
        self.assertEqual(r["endpunkte"]["protokoll_quelle"], "not stated")


if __name__ == "__main__":
    unittest.main()
