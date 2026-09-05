"""Aufloesung der Arb-Papier-Trades: Gamma-Nachschlag, Abrechnung, Koerbe."""

import unittest
from datetime import datetime, timezone

from app import arb_resolution as ar

JETZT = datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)


def _markt(slug, prices, closed=True, uma="resolved", closed_time="2026-08-01 07:10:29+00", neg_risk=True, event="ev"):
    return {
        "slug": slug, "question": slug.replace("-", " "), "conditionId": "0x" + slug[:6],
        "closed": closed, "umaResolutionStatus": uma, "closedTime": closed_time, "endDate": "2026-12-31T00:00:00Z",
        "outcomes": '["Yes", "No"]', "outcomePrices": prices,
        "events": [{"slug": event, "title": event, "negRisk": neg_risk}],
    }


def _trade(slug, entry, size=1.0, shares=None, opp="opp-1", ts=1747785600000, side="NO", tid=None):
    return {
        "id": tid or ("t-" + slug), "strategy": "neg_risk_bracket_arb", "slug": slug, "question": "",
        "token_id": "tok-" + slug, "side": side, "size_usd": size, "entry_price": entry,
        "size_shares": shares, "timestamp": ts, "opportunity_id": opp, "link_status": "linked",
    }


class ParseUndSettlement(unittest.TestCase):
    def test_parse_liest_strings_und_negrisk_vom_ereignis(self):
        m = ar.parse_market(_markt("a", '["0", "1"]'))
        self.assertEqual(m["outcomes"], ["Yes", "No"])
        self.assertEqual(m["prices"], [0.0, 1.0])
        self.assertTrue(m["neg_risk"])
        self.assertEqual(m["event_slug"], "ev")

    def test_no_seite_gewinnt_wenn_no_auf_eins_steht(self):
        s = ar.settlement(ar.parse_market(_markt("a", '["0", "1"]')), "NO")
        self.assertEqual((s["status"], s["price"], s["kind"]), ("resolved", 1.0, "yes_no"))

    def test_no_seite_verliert_wenn_yes_gewonnen_hat(self):
        s = ar.settlement(ar.parse_market(_markt("a", '["1", "0"]')), "no")
        self.assertEqual((s["status"], s["price"]), ("resolved", 0.0))

    def test_halbe_abrechnung_ist_eigene_art(self):
        s = ar.settlement(ar.parse_market(_markt("a", '["0.5", "0.5"]')), "NO")
        self.assertEqual((s["status"], s["price"], s["kind"]), ("resolved", 0.5, "split"))

    def test_offener_markt_bleibt_offen(self):
        s = ar.settlement(ar.parse_market(_markt("a", '["0.42", "0.58"]', closed=False, uma="")), "NO")
        self.assertEqual(s["status"], "open")
        self.assertEqual(s["reason"], "market_open")

    def test_geschlossen_aber_nicht_aufgeloest_zaehlt_nicht_als_abgerechnet(self):
        s = ar.settlement(ar.parse_market(_markt("a", '["0.42", "0.58"]', closed=True, uma="proposed")), "NO")
        self.assertEqual(s["status"], "open")
        self.assertIn("proposed", s["reason"])

    def test_fehlender_markt_ist_unbekannt(self):
        s = ar.settlement(None, "NO")
        self.assertEqual((s["status"], s["reason"]), ("unknown", "market_not_found"))

    def test_fremde_seite_ist_unbekannt(self):
        s = ar.settlement(ar.parse_market(_markt("a", '["0", "1"]')), "Maybe")
        self.assertEqual(s["reason"], "outcome_not_in_market")


class Nachschlag(unittest.TestCase):
    def test_geschlossen_zuerst_dann_offen_dann_token(self):
        aufrufe = []

        def fetch(url):
            aufrufe.append(url)
            if "closed=true" in url and "slug=" in url:
                return []
            if "slug=" in url:
                return []
            if "clob_token_ids" in url and "closed=true" in url:
                return [_markt("a", '["0", "1"]')]
            return []

        m = ar.lookup_market("a", "tok", fetch)
        self.assertIsNotNone(m)
        self.assertEqual(len(aufrufe), 3)
        self.assertTrue(aufrufe[0].endswith("slug=a&closed=true"))
        self.assertIn("clob_token_ids=tok&closed=true", aufrufe[2])

    def test_erster_treffer_gewinnt_und_slug_wird_bevorzugt(self):
        def fetch(url):
            return [_markt("b", '["1", "0"]'), _markt("a", '["0", "1"]')]

        m = ar.lookup_market("a", "", fetch)
        self.assertEqual(m["slug"], "a")

    def test_netzfehler_bricht_nicht_ab(self):
        def fetch(url):
            raise OSError("down")

        self.assertIsNone(ar.lookup_market("a", "tok", fetch))


class TradeRechnung(unittest.TestCase):
    def test_no_gewinnt_auszahlung_ist_stueck_mal_eins(self):
        z = ar.resolve_trade(_trade("a", 0.72), ar.parse_market(_markt("a", '["0", "1"]')), JETZT)
        self.assertEqual(z["status"], "resolved")
        self.assertAlmostEqual(z["shares"], 1 / 0.72, places=5)
        self.assertAlmostEqual(z["payout_usd"], 1 / 0.72, places=3)
        self.assertAlmostEqual(z["pnl_usd"], 1 / 0.72 - 1.0, places=3)
        self.assertEqual(z["resolved_at"][:10], "2026-08-01")
        # 2025-05-21 00:00 UTC -> 2026-08-01 07:10 UTC
        self.assertGreater(z["days_held"], 400)

    def test_size_shares_schlaegt_entry_price(self):
        z = ar.resolve_trade(_trade("a", 0.5, size=0.5, shares=1.0), ar.parse_market(_markt("a", '["1", "0"]')), JETZT)
        self.assertEqual(z["shares"], 1.0)
        self.assertEqual(z["payout_usd"], 0.0)
        self.assertEqual(z["pnl_usd"], -0.5)

    def test_halbe_abrechnung_zahlt_fuenfzig_cent_je_stueck(self):
        z = ar.resolve_trade(_trade("a", 0.48, size=0.48, shares=1.0), ar.parse_market(_markt("a", '["0.5", "0.5"]')), JETZT)
        self.assertEqual(z["resolution_kind"], "split")
        self.assertAlmostEqual(z["pnl_usd"], 0.02, places=6)

    def test_einstiegspreis_null_gibt_keinen_gewinn_sondern_grund(self):
        z = ar.resolve_trade(_trade("a", 0.0), ar.parse_market(_markt("a", '["0", "1"]')), JETZT)
        self.assertEqual(z["status"], "resolved")
        self.assertIsNone(z["pnl_usd"])
        self.assertEqual(z["pnl_reason"], "invalid_entry_price")
        self.assertIsNotNone(z["days_held"])

    def test_offener_trade_zaehlt_tage_bis_jetzt(self):
        z = ar.resolve_trade(_trade("a", 0.7), ar.parse_market(_markt("a", '["0.4", "0.6"]', closed=False, uma="")), JETZT)
        self.assertEqual(z["status"], "open")
        self.assertIsNone(z["pnl_usd"])
        self.assertGreater(z["days_held"], 470)

    def test_opened_at_aus_payload_statt_timestamp(self):
        t = _trade("a", 0.7)
        t.pop("timestamp")
        t["opened_at"] = "2026-05-20T10:00:00Z"
        z = ar.resolve_trade(t, ar.parse_market(_markt("a", '["0", "1"]')), JETZT)
        self.assertEqual(z["opened_at"], "2026-05-20T10:00:00+00:00")
        self.assertAlmostEqual(z["days_held"], 72.88, places=1)


class Koerbe(unittest.TestCase):
    def _zeilen(self):
        return [
            ar.resolve_trade(_trade("may", 0.96, size=0.96, shares=1.0, opp="deadline"), ar.parse_market(_markt("may", '["0", "1"]', neg_risk=False, event="starmer")), JETZT),
            ar.resolve_trade(_trade("jun", 0.72, size=0.72, shares=1.0, opp="deadline"), ar.parse_market(_markt("jun", '["1", "0"]', neg_risk=False, event="starmer")), JETZT),
            ar.resolve_trade(_trade("dec", 0.28, size=0.28, shares=1.0, opp="deadline"), ar.parse_market(_markt("dec", '["1", "0"]', neg_risk=False, event="starmer")), JETZT),
            ar.resolve_trade(_trade("w1", 0.9, size=0.9, shares=1.0, opp=None), ar.parse_market(_markt("w1", '["0", "1"]', event="weinstein")), JETZT),
            ar.resolve_trade(_trade("w2", 0.2, size=0.2, shares=1.0, opp=None), ar.parse_market(_markt("w2", '["1", "0"]', event="weinstein")), JETZT),
            ar.resolve_trade(_trade("x", 0.5, opp=None), None, JETZT),
        ]

    def test_gestaffelte_fristen_sind_kein_ausschluss_und_verlieren(self):
        k = {b["key"]: b for b in ar.baskets(self._zeilen())}
        d = k["deadline"]
        self.assertTrue(d["linked"])
        self.assertIs(d["mutually_exclusive"], False)
        self.assertEqual(d["legs"], 3)
        self.assertAlmostEqual(d["cost_usd"], 1.96)
        self.assertAlmostEqual(d["payout_usd"], 1.0)
        self.assertAlmostEqual(d["pnl_usd"], -0.96)
        self.assertEqual(d["resolved_at"][:10], "2026-08-01")

    def test_unverknuepfte_trades_gruppieren_ueber_das_ereignis(self):
        k = {b["key"]: b for b in ar.baskets(self._zeilen())}
        w = k["event:weinstein"]
        self.assertFalse(w["linked"])
        self.assertIs(w["mutually_exclusive"], True)
        self.assertAlmostEqual(w["pnl_usd"], 1.0 - 1.1, places=6)

    def test_korb_ohne_markt_hat_keinen_gewinn_und_kein_aufloesungsdatum(self):
        k = {b["key"]: b for b in ar.baskets(self._zeilen())}
        x = k["event:x"]
        self.assertEqual(x["unknown_legs"], 1)
        self.assertIsNone(x["pnl_usd"])
        self.assertIsNone(x["resolved_at"])
        self.assertIsNone(x["mutually_exclusive"])

    def test_summary_zaehlt_alles_einzeln(self):
        z = self._zeilen()
        s = ar.summary(z, ar.baskets(z))
        self.assertEqual((s["trades"], s["resolved"], s["unknown"], s["with_pnl"]), (6, 5, 1, 5))
        self.assertEqual((s["won"], s["lost"], s["flat"]), (2, 3, 0))
        self.assertAlmostEqual(s["pnl_usd"], -0.96 - 0.1, places=6)
        self.assertEqual(s["baskets_not_exclusive"], 1)
        self.assertEqual(s["baskets_resolved"], 2)
        self.assertIsNotNone(s["median_days_held"])


class Tagespreis(unittest.TestCase):
    VERLAUF = [{"t": 1747699200, "p": 0.41}, {"t": 1747785600, "p": 0.9385}, {"t": 1747872000, "p": 0.96}]

    def test_naechster_punkt_zum_fill(self):
        d = ar.clob_price_near("tok", datetime.fromtimestamp(1747785600 - 6 * 3600, tz=timezone.utc), history=self.VERLAUF)
        self.assertEqual(d["price"], 0.9385)
        self.assertEqual(d["hours_off"], 6.0)

    def test_zu_weit_weg_ist_kein_tagespreis(self):
        d = ar.clob_price_near("tok", datetime.fromtimestamp(1747872000 + 3 * 86400, tz=timezone.utc), history=self.VERLAUF)
        self.assertIsNone(d)

    def test_ohne_token_oder_zeit_nichts(self):
        self.assertIsNone(ar.clob_price_near("", JETZT, history=self.VERLAUF))
        self.assertIsNone(ar.clob_price_near("tok", None, history=self.VERLAUF))
        self.assertIsNone(ar.clob_price_near("tok", JETZT, history=[]))

    def test_verlauf_kommt_vom_clob_wenn_keiner_uebergeben_wird(self):
        urls = []

        def fetch(url):
            urls.append(url)
            return {"history": self.VERLAUF}

        d = ar.clob_price_near("tok", datetime.fromtimestamp(1747785600, tz=timezone.utc), fetch)
        self.assertEqual(d["price"], 0.9385)
        self.assertIn("prices-history?market=tok&interval=max&fidelity=1440", urls[0])

    def test_entry_check(self):
        self.assertEqual(ar.entry_check(0.0615, 0.9385), "complement")
        self.assertEqual(ar.entry_check(0.96, 0.961), "entry")
        self.assertEqual(ar.entry_check(0.0115, 0.904), "neither")
        self.assertEqual(ar.entry_check(0.5, 0.52), "entry")
        self.assertEqual(ar.entry_check(0.7, None), "no_data")
        self.assertEqual(ar.entry_check(None, 0.5), "no_data")


class KorrigierteRechnung(unittest.TestCase):
    def test_gegenseite_im_journal_wird_zu_eins_minus_einstieg(self):
        tag = {"price": 0.9385, "at": "2026-05-20T00:00:00+00:00", "hours_off": 6.8}
        z = ar.resolve_trade(_trade("a", 0.0615), ar.parse_market(_markt("a", '["0", "1"]')), JETZT, day=tag)
        self.assertEqual(z["entry_check"], "complement")
        self.assertAlmostEqual(z["entry_price_corrected"], 0.9385, places=6)
        # As recorded: 1 / 0.0615 shares, a windfall the book never offered.
        self.assertAlmostEqual(z["pnl_usd"], 1 / 0.0615 - 1, places=3)
        # Corrected: 1 / 0.9385 shares at settlement 1.
        self.assertAlmostEqual(z["pnl_corrected_usd"], 1 / 0.9385 - 1, places=3)

    def test_stueckzahl_zeilen_behalten_ihren_einstieg(self):
        tag = {"price": 0.961, "at": "x", "hours_off": 8.9}
        z = ar.resolve_trade(_trade("a", 0.96, size=0.96, shares=1.0), ar.parse_market(_markt("a", '["0", "1"]')), JETZT, day=tag)
        self.assertEqual(z["entry_check"], "entry")
        self.assertIsNone(z["entry_price_corrected"])
        self.assertAlmostEqual(z["pnl_corrected_usd"], 0.04, places=6)
        self.assertEqual(z["pnl_corrected_usd"], z["pnl_usd"])

    def test_unpassender_einstieg_bekommt_keine_korrigierte_zahl(self):
        tag = {"price": 0.904, "at": "x", "hours_off": 6.8}
        z = ar.resolve_trade(_trade("a", 0.0115), ar.parse_market(_markt("a", '["0", "1"]')), JETZT, day=tag)
        self.assertEqual(z["entry_check"], "neither")
        self.assertIsNotNone(z["pnl_usd"])
        self.assertIsNone(z["pnl_corrected_usd"])
        self.assertEqual(z["pnl_corrected_reason"], "entry_unsupported_by_day_price")

    def test_ohne_tagespreis_keine_korrigierte_zahl_fuer_journalzeilen(self):
        z = ar.resolve_trade(_trade("a", 0.7), ar.parse_market(_markt("a", '["0", "1"]')), JETZT, day=None)
        self.assertEqual(z["entry_check"], "no_data")
        self.assertIsNone(z["pnl_corrected_usd"])
        self.assertEqual(z["pnl_corrected_reason"], "no_day_price")

    def test_stueckzahl_zeile_ohne_tagespreis_behaelt_die_rechnung(self):
        z = ar.resolve_trade(_trade("a", 0.96, size=0.96, shares=1.0), ar.parse_market(_markt("a", '["0", "1"]')), JETZT, day=None)
        self.assertAlmostEqual(z["pnl_corrected_usd"], 0.04, places=6)

    def test_fill_nach_marktschluss_ist_ein_befund_und_keine_zahl(self):
        # Fill on 2026-05-19, but the market closed on 2026-05-01.
        m = ar.parse_market(_markt("a", '["0", "1"]', closed_time="2026-05-01 00:00:00+00"))
        z = ar.resolve_trade(_trade("a", 0.7, ts=1779210670000), m, JETZT, day={"price": 0.7, "at": "x", "hours_off": 1.0})
        self.assertTrue(z["filled_after_close"])
        self.assertLess(z["days_held"], 0)
        self.assertIsNone(z["pnl_corrected_usd"])
        self.assertEqual(z["pnl_corrected_reason"], "filled_after_close")
        s = ar.summary([z], ar.baskets([z]))
        self.assertEqual(s["filled_after_close"], 1)
        self.assertEqual(s["days_held_n"], 0)
        self.assertIsNone(s["mean_days_held"])
        self.assertEqual(s["without_corrected_pnl_reasons"], {"filled_after_close": 1})


class GanzerLauf(unittest.TestCase):
    def test_resolve_all_fragt_gamma_und_clob_je_einmal(self):
        urls = []

        def fetch(url):
            urls.append(url)
            if "prices-history" in url:
                return {"history": [{"t": 1747785600, "p": 0.5}]}
            return [_markt("a", '["0", "1"]')]

        cache = {}
        out = ar.resolve_all([_trade("a", 0.5, tid="1"), _trade("a", 0.5, tid="2")], fetch=fetch, cache=cache, now=JETZT)
        self.assertEqual(sum(1 for u in urls if "gamma-api" in u), 1)
        self.assertEqual(sum(1 for u in urls if "prices-history" in u), 1)
        self.assertIn("clob:tok-a", cache)
        self.assertEqual(out["trades"][0]["entry_check"], "entry")
        self.assertIsNotNone(out["trades"][0]["pnl_corrected_usd"])

    def test_resolve_all_nutzt_cache_je_slug(self):
        aufrufe = []

        def fetch(url):
            aufrufe.append(url)
            return [_markt("a", '["0", "1"]')]

        cache = {}
        out = ar.resolve_all([_trade("a", 0.5, tid="1"), _trade("a", 0.5, tid="2")], fetch=fetch, cache=cache, now=JETZT, with_clob=False)
        self.assertEqual(len(aufrufe), 1)
        self.assertEqual(out["schema"], "arb_resolutions/1")
        self.assertEqual(out["summary"]["trades"], 2)
        self.assertEqual(out["generated_at"], JETZT.isoformat())
        self.assertIn("closed=true", out["source"])
        self.assertIn("before any fee", out["method"])

    def test_payload_positionen_ergeben_status_aber_keinen_gewinn(self):
        payload = {"paper_positions": [{"trade_id": "p1", "strategy": "neg_risk_bracket_arb", "title": "a",
                                        "opened_at": "2026-05-20T00:00:00Z", "capital_usd": 0.5, "opportunity_id": "o"}]}
        trades = ar.trades_from_payload(payload)
        out = ar.resolve_all(trades, fetch=lambda url: [_markt("a", '["0", "1"]')], now=JETZT)
        z = out["trades"][0]
        self.assertEqual((z["trade_id"], z["status"]), ("p1", "resolved"))
        self.assertIsNone(z["pnl_usd"])
        self.assertEqual(z["pnl_reason"], "invalid_entry_price")


if __name__ == "__main__":
    unittest.main()
