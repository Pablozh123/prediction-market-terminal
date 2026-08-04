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
        self.assertEqual(r["slippage"], {"n": 0})
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
    @unittest.skipUnless(PILOT.exists(), "public/data/pilot.json fehlt")
    def test_laeuft_auf_der_publizierten_datei(self):
        payload = json.loads(PILOT.read_text(encoding="utf-8"))
        r = pr.evaluate(payload, heute=date(2026, 8, 4))
        self.assertGreater(r["trades"]["gesamt"], 0)
        self.assertIn(r["phase"], (pr.PHASE_LAEUFT, pr.PHASE_OFFEN, pr.PHASE_FERTIG))
        self.assertTrue(r["befund"])


if __name__ == "__main__":
    unittest.main()
