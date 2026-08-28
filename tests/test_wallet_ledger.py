"""app/wallet_ledger.py: the wallet ledger from Data-API rows and the two artefacts.

Fixtures mimic the public feeds' shapes (activity newest-first, both tails of
/closed-positions, /positions with a worthless leftover). Checks: attribution
bot / pilot / discretionary, the per-event roll-up, the aggregate identity
(net cash flow = sells + redeems − buys), the $0 redeem on a lost side, the
closed-feed cap flag, and the header fields the page relies on.
"""

from __future__ import annotations

import unittest

from app import wallet_ledger as wl

W = "0x29afe1bf37700768a640a08f1b35dad5f202f88d"
BOT_EVENT = "what-will-be-said-on-the-next-all-in-podcast-july-17-20260713144020193"
DISC_EVENT = "what-will-trump-say-during-tribute-to-lindsey-graham-20260724170556632"
PILOT_EVENT = "us-gdp-growth-in-q2-2026"
CID_BLUE = "0xaaa1"
CID_TENSION = "0xaaa2"
CID_EXTRA = "0xaaa3"
CID_TOUGH = "0xbbb1"
CID_GDP = "0xccc1"


def _row(typ, ts, cid, title, outcome, usd, size, side="BUY", event=BOT_EVENT, price=0.5):
    return {
        "proxyWallet": W, "timestamp": ts, "conditionId": cid, "type": typ, "size": size, "usdcSize": usd,
        "transactionHash": "0x" + str(ts), "price": price, "asset": "", "side": side if typ == "TRADE" else "",
        "outcomeIndex": 0 if outcome == "Yes" else 1, "title": title, "slug": title.lower().replace(" ", "-"),
        "eventSlug": event, "outcome": outcome, "name": "zh8000", "pseudonym": "x",
    }


def _closed(cid, title, outcome, pnl, event=BOT_EVENT, cur=None):
    return {"proxyWallet": W, "conditionId": cid, "avgPrice": 0.5, "totalBought": 10, "realizedPnl": pnl,
            "curPrice": (1 if pnl > 0 else 0) if cur is None else cur, "title": title, "slug": "s", "eventSlug": event,
            "outcome": outcome, "endDate": "2026-07-24", "timestamp": 1_753_400_000}


ACTIVITY = [
    # newest first, as the feed delivers it
    _row("REDEEM", 1_753_500_000, CID_TENSION, 'Will "Tension" be said?', "Yes", 0.0, 0.0),           # $0 redeem, winning side stamped
    _row("REDEEM", 1_753_499_000, CID_BLUE, 'Will "Blue" be said?', "Yes", 179.81, 179.81),
    _row("REDEEM", 1_753_498_000, CID_GDP, "Will US GDP growth in Q2 2026 be less than 1.0%?", "No", 5.17, 5.17, event=PILOT_EVENT),
    _row("TRADE", 1_753_400_100, CID_GDP, "Will US GDP growth in Q2 2026 be less than 1.0%?", "No", 5.01, 5.18, price=0.967, event=PILOT_EVENT),
    _row("TRADE", 1_753_400_050, CID_TOUGH, 'Will Trump say "Tough Cookie"?', "Yes", 100.04, 105.3, event=DISC_EVENT, price=0.95),
    _row("TRADE", 1_753_400_010, CID_EXTRA, 'Will "Extra" be said?', "Yes", 10.0, 20.0, price=0.5),
    _row("TRADE", 1_753_400_005, CID_TENSION, 'Will "Tension" be said?', "No", 22.11, 25.0, price=0.88),
    _row("TRADE", 1_753_400_002, CID_BLUE, 'Will "Blue" be said?', "Yes", 50.64, 74.47, price=0.68),
    _row("TRADE", 1_753_400_001, CID_BLUE, 'Will "Blue" be said?', "Yes", 73.20, 107.65, price=0.68),
    _row("TRADE", 1_753_400_003, CID_BLUE, 'Will "Blue" be said?', "Yes", 20.0, 30.0, side="SELL", price=0.667),
]

CLOSED_DESC = [
    _closed(CID_BLUE, 'Will "Blue" be said?', "Yes", 55.97),
    _closed(CID_GDP, "Will US GDP growth in Q2 2026 be less than 1.0%?", "No", 0.16, event=PILOT_EVENT),
    _closed(CID_TOUGH, 'Will Trump say "Tough Cookie"?', "Yes", 0.97, event=DISC_EVENT),
    _closed(CID_TENSION, 'Will "Tension" be said?', "No", -22.11),
]
CLOSED_ASC = list(reversed(CLOSED_DESC))
POSITIONS = [{
    "proxyWallet": W, "conditionId": CID_EXTRA, "size": 20.0, "avgPrice": 0.5, "initialValue": 10.0,
    "currentValue": 0, "cashPnl": -10.0, "realizedPnl": -0.3, "curPrice": 0, "redeemable": True,
    "title": 'Will "Extra" be said?', "slug": "extra", "eventSlug": BOT_EVENT, "outcome": "Yes", "endDate": "2026-07-24",
}]

RUNS = {
    "stand_utc": "2026-08-07T04:33:11+00:00",
    "runs": [
        {"profil": "allin_july17", "event_slug": BOT_EVENT, "wetten": [
            {"frage": 'Will "Blue" be said?', "seite": "YES", "einsatz_usd": 132.36},
            {"frage": 'Will "Tension" be said?', "seite": "NO", "einsatz_usd": 22.5},
        ]},
        {"profil": "trump_graham_july28", "event_slug": DISC_EVENT, "wetten": []},
        {"profil": "no_slug_run", "event_slug": "", "wetten": []},
    ],
}
PILOT = {
    "stand_utc": "2026-08-07T04:33:12+00:00",
    "protokoll": {"regel_freeze_datum": "2026-07-18"},
    "trades": [{"markt_id": "2125608", "markt_frage": "Will US GDP growth in Q2 2026 be less than 1.0%?"}],
}


def _build(**overrides):
    kwargs = dict(activity=ACTIVITY, positions=POSITIONS, closed_desc=CLOSED_DESC, closed_asc=CLOSED_ASC,
                  runs_payload=RUNS, pilot_payload=PILOT, stand_utc="2026-08-17T00:00:00+00:00",
                  event_titles={BOT_EVENT: "What will be said on the next All-In Podcast? (July 17)"})
    kwargs.update(overrides)
    return wl.build_ledger(**kwargs)


class HeaderTests(unittest.TestCase):
    def test_header_fields(self) -> None:
        ledger = _build()
        self.assertEqual(ledger["wallet"], W)
        self.assertEqual(ledger["kennzeichnung"], "wallet/public-api")
        self.assertEqual(ledger["stand_utc"], "2026-08-17T00:00:00+00:00")
        self.assertIn("public Polymarket Data API", ledger["hinweis"])
        self.assertIn("scripts/wallet_ledger.py", ledger["hinweis"])
        self.assertIn("rules frozen 2026-07-18", ledger["regeln"]["pilot"])
        self.assertEqual(ledger["abgleich"]["runs_json_n_runs"], 3)
        self.assertEqual(ledger["abgleich"]["pilot_json_n_trades"], 1)


class AggregateTests(unittest.TestCase):
    def test_cash_identity_and_counts(self) -> None:
        agg = _build()["aggregat"]
        buys = 5.01 + 100.04 + 10.0 + 22.11 + 50.64 + 73.20
        self.assertAlmostEqual(agg["kaeufe_usd"], round(buys, 2), places=2)
        self.assertAlmostEqual(agg["verkaeufe_usd"], 20.0, places=2)
        self.assertAlmostEqual(agg["einloesungen_usd"], 179.81 + 5.17, places=2)
        self.assertAlmostEqual(agg["netto_cashflow_usd"], round(20.0 + 179.81 + 5.17 - buys, 2), places=2)
        self.assertEqual(agg["n_trades"], 7)
        self.assertEqual(agg["n_kaeufe"], 6)
        self.assertEqual(agg["n_verkaeufe"], 1)
        self.assertEqual(agg["n_einloesungen"], 3)
        self.assertEqual(agg["n_events"], 3)
        self.assertEqual(agg["n_maerkte"], 5)
        self.assertIsNone(agg["einzahlungen_usd"])
        self.assertIn("not derivable", agg["einzahlungen_hinweis"])
        self.assertEqual(agg["erste_aktivitaet_utc"], "2025-07-24T23:33:21Z")
        self.assertEqual(agg["letzte_aktivitaet_utc"], "2025-07-26T03:20:00Z")

    def test_deklarierte_einzahlungen(self) -> None:
        # Der Betreiber kann die Einzahlungen deklarieren (per USDC-Transfers
        # der Wallet on-chain nachpruefbar); der Hinweis nennt dann die
        # Herkunft statt des "not derivable"-Satzes.
        agg = _build(einzahlungen_usd=300.0)["aggregat"]
        self.assertEqual(agg["einzahlungen_usd"], 300.0)
        self.assertIn("declared by the wallet owner", agg["einzahlungen_hinweis"])
        self.assertIn("verifiable on-chain", agg["einzahlungen_hinweis"])
        self.assertNotIn("needs an on-chain", agg["einzahlungen_hinweis"])

    def test_position_outcomes(self) -> None:
        agg = _build()["aggregat"]
        # 3 won (Blue, GDP, Tough Cookie), 1 lost (Tension), 1 worthless (Extra), none open/unknown.
        self.assertEqual(agg["positionen"], {"won": 3, "lost": 1, "flat": 0, "worthless": 1, "open": 0, "unknown": 0})
        self.assertEqual(agg["positionen_gewonnen"], 3)
        self.assertEqual(agg["positionen_verloren"], 2)
        self.assertEqual(agg["positionen_wertlos"], 1)
        self.assertFalse(agg["closed_positions_capped"])
        self.assertAlmostEqual(agg["realisierter_pnl_api_usd"], 55.97 + 0.16 + 0.97 - 22.11, places=2)

    def test_by_type(self) -> None:
        by = _build()["aggregat"]["nach_typ"]
        self.assertEqual(by["bot"]["events"], 1)
        self.assertEqual(by["bot"]["maerkte"], 2)          # Blue + Tension; Extra is discretionary
        self.assertEqual(by["discretionary"]["events"], 1)  # Trump–Graham; the Extra market sits in the bot event
        self.assertEqual(by["discretionary"]["maerkte"], 2)
        self.assertEqual(by["pilot"]["events"], 1)
        self.assertEqual(by["pilot"]["maerkte"], 1)
        self.assertAlmostEqual(by["pilot"]["einsatz_usd"], 5.01, places=2)
        self.assertAlmostEqual(by["pilot"]["netto_cash_usd"], 0.16, places=2)

    def test_capped_flag_when_both_tails_hit_the_cap(self) -> None:
        many = [_closed(f"0xd{i:03d}", f"Q{i}", "Yes", 1.0 + i) for i in range(50)]
        agg = _build(closed_desc=many, closed_asc=list(reversed(many)))["aggregat"]
        self.assertTrue(agg["closed_positions_capped"])


class EventTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ledger = _build()
        self.by_slug = {e["event_slug"]: e for e in self.ledger["events"]}

    def test_sorted_by_date_desc_and_urls(self) -> None:
        slugs = [e["event_slug"] for e in self.ledger["events"]]
        self.assertEqual(slugs, [PILOT_EVENT, DISC_EVENT, BOT_EVENT])
        for e in self.ledger["events"]:
            self.assertEqual(e["url"], "https://polymarket.com/event/" + e["event_slug"])

    def test_bot_event_with_a_discretionary_market_is_mixed(self) -> None:
        e = self.by_slug[BOT_EVENT]
        self.assertEqual(e["typ"], "bot")
        self.assertEqual(e["typ_mix"], "bot + discretionary")
        self.assertEqual(e["run_profil"], "allin_july17")
        self.assertTrue(e["run_im_log"])
        self.assertEqual(e["titel"], "What will be said on the next All-In Podcast? (July 17)")
        self.assertEqual(e["titel_quelle"], "gamma")
        self.assertEqual(e["n_maerkte"], 3)
        self.assertEqual(e["n_trades"], 5)
        self.assertEqual(e["n_einloesungen"], 2)
        self.assertAlmostEqual(e["einsatz_usd"], 10.0 + 22.11 + 50.64 + 73.20, places=2)
        self.assertAlmostEqual(e["verkaeufe_usd"], 20.0, places=2)
        self.assertAlmostEqual(e["einloesungen_usd"], 179.81, places=2)
        self.assertAlmostEqual(e["netto_cash_usd"], round(20.0 + 179.81 - (10.0 + 22.11 + 50.64 + 73.20), 2), places=2)
        self.assertAlmostEqual(e["pnl_usd"], 55.97 - 22.11 - 10.0, places=2)
        self.assertEqual(e["status"], {"won": 1, "lost": 1, "flat": 0, "worthless": 1, "open": 0, "unknown": 0})
        self.assertEqual(e["status_text"], "1 won · 1 lost · 1 worthless")
        self.assertEqual(e["notes"], ["1 of 3 markets are not in the run log of 'allin_july17' (discretionary)."])
        markets = {m["titel"]: m for m in e["maerkte"]}
        blue = markets['Will "Blue" be said?']
        self.assertEqual(blue["zuordnung"], "bot")
        self.assertEqual(blue["run_profil"], "allin_july17")
        self.assertEqual(blue["seite"], "Yes")
        self.assertAlmostEqual(blue["shares"], 74.47 + 107.65, places=2)
        self.assertAlmostEqual(blue["avg_preis"], round((50.64 + 73.20) / (74.47 + 107.65), 4), places=4)
        self.assertEqual(blue["status"], "won")
        self.assertAlmostEqual(blue["pnl_usd"], 55.97, places=2)
        self.assertEqual(blue["n_trades"], 3)
        extra = markets['Will "Extra" be said?']
        self.assertEqual(extra["zuordnung"], "discretionary")
        self.assertEqual(extra["status"], "worthless")
        self.assertAlmostEqual(extra["pnl_usd"], -10.0, places=2)
        self.assertIn("not redeemed", extra["pnl_art"])

    def test_zero_dollar_redeem_attaches_to_the_held_side(self) -> None:
        # The $0 REDEEM row on "Tension" is stamped "Yes" by the API although the
        # wallet held NO. It must not open a phantom "Tension · Yes" market.
        e = self.by_slug[BOT_EVENT]
        tension = [m for m in e["maerkte"] if "Tension" in m["titel"]]
        self.assertEqual(len(tension), 1)
        self.assertEqual(tension[0]["seite"], "No")
        self.assertEqual(tension[0]["n_einloesungen"], 1)
        self.assertEqual(tension[0]["status"], "lost")
        self.assertAlmostEqual(tension[0]["pnl_usd"], -22.11, places=2)

    def test_run_without_fills_is_discretionary_with_a_note(self) -> None:
        e = self.by_slug[DISC_EVENT]
        self.assertEqual(e["typ"], "discretionary")
        self.assertEqual(e["typ_mix"], "")
        self.assertEqual(e["run_profil"], "trump_graham_july28")
        self.assertFalse(e["run_im_log"])
        self.assertEqual(e["titel_quelle"], "slug")
        self.assertEqual(e["titel"], "What will trump say during tribute to lindsey graham")
        self.assertIn("covered this event but its log records no fill here", e["notes"][0])
        self.assertEqual(e["status_text"], "1 won")

    def test_pilot_event_by_title_or_condition_id(self) -> None:
        e = self.by_slug[PILOT_EVENT]
        self.assertEqual(e["typ"], "pilot")
        self.assertEqual(e["maerkte"][0]["zuordnung"], "pilot")
        self.assertIn("rules frozen 2026-07-18", e["notes"][0])
        # With the condition id known and the title changed, the id alone still matches.
        activity = [dict(r, title="renamed") if r["conditionId"] == CID_GDP else r for r in ACTIVITY]
        by_cid = _build(activity=activity, pilot_condition_ids=[CID_GDP])
        pilot_ev = [x for x in by_cid["events"] if x["event_slug"] == PILOT_EVENT][0]
        self.assertEqual(pilot_ev["typ"], "pilot")
        # Without either, it is discretionary.
        neither = _build(activity=activity)
        pilot_ev = [x for x in neither["events"] if x["event_slug"] == PILOT_EVENT][0]
        self.assertEqual(pilot_ev["typ"], "discretionary")

    def test_curtis_note_is_attached_by_slug(self) -> None:
        curtis = "what-will-be-said-during-the-third-episode-of-president-curtis-season-1-20260804193637080"
        activity = [_row("TRADE", 1_786_132_602, "0xeee1", 'Will anyone say "Rick" during President Curtis E3 S1?', "Yes", 13.45, 100.0, event=curtis)]
        ledger = _build(activity=activity, positions=[], closed_desc=[], closed_asc=[], runs_payload=None, pilot_payload=None)
        e = ledger["events"][0]
        self.assertEqual(e["typ"], "discretionary")
        self.assertIn("pre-registered before airing", e["notes"][0])
        self.assertIn("PREREG_CURTIS_E3_2026-08-07.md", e["notes"][0])
        self.assertEqual(e["maerkte"][0]["status"], "unknown")
        self.assertIsNone(e["maerkte"][0]["pnl_usd"])
        self.assertIsNone(e["pnl_usd"])


class EmptyAndHelperTests(unittest.TestCase):
    def test_empty_inputs(self) -> None:
        ledger = wl.build_ledger([], [], [], [], stand_utc="2026-08-17T00:00:00+00:00")
        self.assertEqual(ledger["events"], [])
        self.assertEqual(ledger["aggregat"]["n_events"], 0)
        self.assertEqual(ledger["aggregat"]["kaeufe_usd"], 0.0)
        self.assertEqual(ledger["aggregat"]["erste_aktivitaet_utc"], "")

    def test_humanize_slug_drops_the_numeric_id(self) -> None:
        self.assertEqual(wl.humanize_slug("what-will-trump-say-20260724170556632"), "What will trump say")
        self.assertEqual(wl.humanize_slug("us-gdp-growth-in-q2-2026"), "Us gdp growth in q2 2026")

    def test_bot_bets_index_and_pilot_index(self) -> None:
        idx = wl.bot_bets_index(RUNS)
        self.assertEqual(set(idx), {BOT_EVENT, DISC_EVENT})
        self.assertIn(('Will "Blue" be said?', "YES"), idx[BOT_EVENT]["bets"])
        self.assertEqual(idx[DISC_EVENT]["bets"], {})
        pil = wl.pilot_index(PILOT, ["0xABC"])
        self.assertEqual(pil["condition_ids"], {"0xabc"})
        self.assertEqual(pil["market_ids"], {"2125608"})
        self.assertEqual(pil["regel_freeze_datum"], "2026-07-18")

    def test_resolved_union_dedupes_by_market_and_side(self) -> None:
        rows, capped = wl.resolved_positions_union(CLOSED_DESC, CLOSED_ASC)
        self.assertEqual(len(rows), 4)
        self.assertFalse(capped)


# Echte Zeilen der Wallet, Feld fuer Feld aus dem oeffentlichen Feed
# uebernommen (2026-08-28): der gehaltene Ausgang ist mit curPrice 1
# aufgeloest und die Einloesung hat je Anteil einen Dollar gezahlt, aber
# /closed-positions meldet minus den ganzen Einsatz.
CID_A2 = "0x5a2f58c07be8f99012ca65766c9c727afecbe61d30914210f91d0cf704267b62"
EVENT_A2 = "which-company-has-the-2-ai-model-end-of-july-style-control-on"
TITEL_A2 = "Will Anthropic have the #2 AI model at the end of July 2026?"
WIDERSPRUCH_ACTIVITY = [
    _row("REDEEM", 1_785_533_852, CID_A2, TITEL_A2, "Yes", 5.319133, 5.319133, event=EVENT_A2),
    _row("TRADE", 1_784_725_737, CID_A2, TITEL_A2, "Yes", 5.011975, 5.319133, price=0.94, event=EVENT_A2),
]
WIDERSPRUCH_CLOSED = [{
    "proxyWallet": W, "conditionId": CID_A2, "avgPrice": 0.9422, "totalBought": 5.3191,
    "realizedPnl": -5.0119, "curPrice": 1, "title": TITEL_A2, "slug": "s", "eventSlug": EVENT_A2,
    "outcome": "Yes", "endDate": "2026-07-31", "timestamp": 1_785_533_802,
}]


class WidersprechendeSchlusszeileTests(unittest.TestCase):
    """Eine eingeloeste Gewinnposition darf nicht als Totalverlust erscheinen."""

    def _ledger(self):
        return wl.build_ledger(WIDERSPRUCH_ACTIVITY, [], WIDERSPRUCH_CLOSED, [],
                               stand_utc="2026-08-28T00:00:00+00:00")

    def test_kassenstrom_schlaegt_widerspruechliches_realized_pnl(self) -> None:
        markt = self._ledger()["events"][0]["maerkte"][0]
        # Gekauft fuer 5.01, eingeloest fuer 5.32 -> plus 0.31, nicht minus 5.01.
        self.assertEqual(markt["status"], "won")
        self.assertAlmostEqual(markt["pnl_usd"], 0.31, places=2)
        self.assertTrue(markt["pnl_art"].startswith(wl.KASSEN_KORREKTUR))

    def test_korrektur_wird_gezaehlt_und_geht_in_die_summe(self) -> None:
        agg = self._ledger()["aggregat"]
        self.assertEqual(agg["positionen_kassenkorrigiert"], 1)
        self.assertEqual(agg["positionen_gewonnen"], 1)
        self.assertEqual(agg["positionen_verloren"], 0)
        self.assertAlmostEqual(agg["realisierter_pnl_api_usd"], 0.31, places=2)
        # Fuer eine vollstaendig abgerechnete Position ist der Netto-Cashflow
        # die Probe: er kennt weder realizedPnl noch curPrice.
        self.assertAlmostEqual(agg["netto_cashflow_usd"], agg["abgerechneter_pnl_usd"], places=2)

    def test_kein_eingriff_ohne_beleg(self) -> None:
        # Ohne Einloesung (Position vor der Aufloesung mit Verlust verkauft)
        # bleibt realizedPnl stehen, auch wenn der Markt spaeter auf 1 ging.
        ohne_redeem = [r for r in WIDERSPRUCH_ACTIVITY if r["type"] != "REDEEM"]
        markt = wl.build_ledger(ohne_redeem, [], WIDERSPRUCH_CLOSED, [])["events"][0]["maerkte"][0]
        self.assertEqual(markt["status"], "lost")
        self.assertAlmostEqual(markt["pnl_usd"], -5.01, places=2)
        self.assertEqual(markt["pnl_art"], "realised (API realizedPnl)")


class AbgerechneterPnlTests(unittest.TestCase):
    """Nicht eingeloeste, aufgeloeste Positionen fehlen im closed-Feed."""

    def test_wertlose_verluste_stehen_neben_dem_api_wert(self) -> None:
        agg = _build()["aggregat"]
        # Extra: 20 Anteile zu 0.50 gekauft, wertlos ausgelaufen, nie eingeloest.
        self.assertAlmostEqual(agg["wertlos_pnl_usd"], -10.0, places=2)
        self.assertAlmostEqual(agg["abgerechneter_pnl_usd"],
                               agg["realisierter_pnl_api_usd"] + agg["wertlos_pnl_usd"], places=2)
        self.assertLess(agg["abgerechneter_pnl_usd"], agg["realisierter_pnl_api_usd"])
        self.assertEqual(agg["offener_pnl_usd"], 0.0)
        self.assertIn("abgerechneter_pnl_usd", _build()["hinweis"])


if __name__ == "__main__":
    unittest.main()
