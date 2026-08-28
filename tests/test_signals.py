import unittest

import pandas as pd

from app import signals as sig


def market(title, volume_1h, volume_24h, **extra):
    row = {
        "platform": "Polymarket",
        "title": title,
        "market_key": title,
        "category": "",
        "yes_price": 0.5,
        "volume_1h": volume_1h,
        "volume_24h": volume_24h,
        "activity_volume": volume_24h,
        "liquidity": 50_000.0,
        "spread": 0.05,
        "change_1h": 0.0,
        "url": "https://example.com",
    }
    row.update(extra)
    return row


class VolumeAnomalyTests(unittest.TestCase):
    def _signals(self, markets):
        return sig.build_monitor_signals(
            pd.DataFrame(markets),
            pd.DataFrame(),
            min_volume=0.0,
            min_liquidity=0.0,
            min_move=0.05,
            max_spread=0.01,
            min_whale_notional=1e12,
            ending_days=0,
            holder_threshold=1.0,
            holder_checks=0,
            tracked_keys=set(),
        )

    def test_hot_hour_flags_anomaly(self):
        signals = self._signals(
            [
                market("Hot market", volume_1h=5_000.0, volume_24h=24_000.0),
                market("Calm market", volume_1h=1_000.0, volume_24h=24_000.0),
            ]
        )
        anomalies = signals[signals["signal_type"] == "Volume anomaly"]
        self.assertEqual(list(anomalies["title"]), ["Hot market"])
        self.assertAlmostEqual(float(anomalies.iloc[0]["value"]), 5.0, places=6)
        self.assertIn("5.0x the 24h baseline", anomalies.iloc[0]["reason"])

    def test_thin_markets_are_ignored(self):
        signals = self._signals([market("Tiny market", volume_1h=900.0, volume_24h=2_000.0)])
        if signals.empty:
            return
        self.assertTrue((signals["signal_type"] != "Volume anomaly").all())


class ObservationTimeTests(unittest.TestCase):
    """Der Zeitstempel eines Signals ist die Beobachtungszeit.

    Kalshi-Marktzeilen fuehren weder updated_at noch created_at. Der frueher
    hier stehende Rueckfall auf end_time schrieb den Schlusstermin des
    Marktes in das Signal: ein Signal von heute trug 2027, sortierte vor
    jedes frische Signal und ging so auch in den Ledger.
    """

    NOW = pd.Timestamp("2026-08-28 12:00:00", tz="UTC")
    ENDE = pd.Timestamp("2027-11-03 00:00:00", tz="UTC")

    def _signals(self, markets, trades=None):
        return sig.build_monitor_signals(
            pd.DataFrame(markets),
            pd.DataFrame() if trades is None else pd.DataFrame(trades),
            min_volume=0.0,
            min_liquidity=0.0,
            min_move=0.01,
            max_spread=0.02,
            min_whale_notional=1e12,
            ending_days=3650,
            holder_threshold=1.0,
            holder_checks=0,
            tracked_keys=set(),
            now=self.NOW,
        )

    def _kalshi(self):
        return {
            "platform": "Kalshi",
            "title": "K market",
            "market_key": "K1",
            "category": "",
            "yes_price": 0.4,
            "spread": 0.01,
            "liquidity": 50_000.0,
            "volume": 100_000.0,
            "end_time": self.ENDE,
            "url": "https://example.com",
        }

    def test_row_without_own_stamp_is_stamped_with_the_scan_time(self):
        signals = self._signals([self._kalshi()])
        self.assertFalse(signals.empty)
        for stamp in signals["time"]:
            self.assertEqual(stamp, self.NOW)
            self.assertNotEqual(stamp, self.ENDE)

    def test_a_rows_own_stamp_still_wins(self):
        eigen = pd.Timestamp("2026-08-28 09:15:00", tz="UTC")
        row = dict(self._kalshi(), updated_at=eigen)
        signals = self._signals([row])
        self.assertTrue((signals["time"] == eigen).all())

    def test_a_far_dated_market_no_longer_outranks_a_fresh_signal(self):
        # Beide Signale sind "warning"; sortiert wird nach Zeit absteigend.
        # Vorher trug die Kalshi-Zeile 2027 und stand damit immer oben.
        frisch = {
            "platform": "Polymarket",
            "title": "fresh mover",
            "market_key": "P1",
            "category": "",
            "yes_price": 0.5,
            "spread": 0.2,
            "liquidity": 50_000.0,
            "volume": 100_000.0,
            "change_1h": 0.09,
            "updated_at": pd.Timestamp("2026-08-28 11:59:00", tz="UTC"),
            "url": "https://example.com",
        }
        signals = self._signals([self._kalshi(), frisch])
        self.assertTrue((signals["time"] <= self.NOW).all())
        self.assertIn("Fast mover", set(signals["signal_type"]))
        # Und kein NaT: in einem gemischten Frame bekommt die Kalshi-Zeile
        # eine leere updated_at-Spalte von der Polymarket-Zeile, und NaN ist
        # in Python wahr — die alte "or"-Kette lieferte dort NaT.
        self.assertTrue(signals["time"].notna().all())


class RuleThresholdScopeTests(unittest.TestCase):
    """Eine Schwelle darf nur die Signalarten filtern, die ihr Feld fuehren.

    Marktsignale tragen ``notional`` 0.0, Trade-Signale ``liquidity`` 0.0 --
    beides per Konstruktion, nicht als Messung. Eine ungebundene Schwelle
    loescht die jeweils andere Art daher restlos aus. Das Regelformular des
    Monitors fuellt "Min notional" mit der Whale-Schwelle vor (Standard 2500),
    also traf das jede mit den Standardwerten gespeicherte Regel.
    """

    def _frame(self):
        gemeinsam = {
            "severity": "warning",
            "time": pd.Timestamp("2026-08-28 12:00:00", tz="UTC"),
            "platform": "Polymarket",
            "title": "Fed cuts in December",
            "market_key": "0xcond",
            "url": "https://example.com",
        }
        return pd.DataFrame([
            dict(gemeinsam, signal_type="Fast mover", outcome="Yes", side="",
                 price=0.40, value=0.08, reason="1h move +8.0c", volume=50_000.0,
                 liquidity=40_000.0, spread=0.02, change_1h=0.08, notional=0.0,
                 wallet="", trader=""),
            dict(gemeinsam, signal_type="Whale print", outcome="Yes", side="BUY",
                 price=0.40, value=9_000.0, reason="BUY $9,000", volume=0.0,
                 liquidity=0.0, spread=None, change_1h=None, notional=9_000.0,
                 wallet="0xwhale", trader="whale"),
        ])

    def test_notional_threshold_leaves_market_signals_alone(self):
        # Vorher: 0 Treffer. Der Fast mover hat notional 0.0, weil ein
        # Marktsignal kein Notional hat -- nicht, weil er klein waere.
        regel = {"signal_type": "Fast mover", "min_notional": 2500.0, "min_move": 0.03}
        treffer = sig.monitor_rule_matches(self._frame(), regel)
        self.assertEqual(len(treffer), 1)
        self.assertEqual(treffer.iloc[0]["signal_type"], "Fast mover")

    def test_notional_threshold_still_filters_whale_prints(self):
        regel = {"signal_type": "Whale print", "min_notional": 25_000.0}
        self.assertEqual(sig.monitor_rule_match_count(self._frame(), regel), 0)
        regel_klein = {"signal_type": "Whale print", "min_notional": 5_000.0}
        self.assertEqual(sig.monitor_rule_match_count(self._frame(), regel_klein), 1)

    def test_liquidity_threshold_leaves_whale_prints_alone(self):
        # Vorher: 0 Treffer. Das Tape traegt keine Buchtiefe, also stand da
        # 0.0 -- ein Print in einem Markt mit $40k Liquiditaet verschwand.
        regel = {"signal_type": "Whale print", "min_liquidity": 1_000.0}
        treffer = sig.monitor_rule_matches(self._frame(), regel)
        self.assertEqual(len(treffer), 1)
        self.assertEqual(treffer.iloc[0]["signal_type"], "Whale print")

    def test_liquidity_threshold_still_filters_market_signals(self):
        regel = {"signal_type": "Fast mover", "min_liquidity": 100_000.0}
        self.assertEqual(sig.monitor_rule_match_count(self._frame(), regel), 0)

    def test_the_default_form_rule_matches_both_kinds(self):
        # Die Regel, die das Formular mit seinen Standardwerten speichert.
        regel = {
            "name": "Default", "signal_type": "Any", "platforms": ["Polymarket"],
            "query": "", "min_notional": 2500.0, "min_move": 0.03,
            "max_spread": 0.07, "min_liquidity": 0.0, "active": True,
        }
        arten = set(sig.monitor_rule_matches(self._frame(), regel)["signal_type"])
        self.assertEqual(arten, {"Fast mover", "Whale print"})


class WhalePrintSideTests(unittest.TestCase):
    """Die genommene Seite gehoert als Feld in die Zeile, nicht nur in den Text."""

    def test_the_traded_side_is_its_own_column(self):
        trades = pd.DataFrame([
            {"platform": "Polymarket", "time": pd.Timestamp("2026-08-28 12:00:00", tz="UTC"),
             "trader": "whale", "wallet": "0xwhale", "side": "SELL", "outcome": "Yes",
             "title": "Fed cuts in December", "price": 0.30, "size": 40_000.0,
             "notional": 12_000.0, "market_key": "0xcond", "url": "https://example.com"},
        ])
        signals = sig.build_monitor_signals(
            pd.DataFrame(), trades,
            min_volume=0.0, min_liquidity=0.0, min_move=0.05, max_spread=0.01,
            min_whale_notional=1_000.0, ending_days=0, holder_threshold=1.0,
            holder_checks=0, tracked_keys=set(),
        )
        self.assertEqual(list(signals["signal_type"]), ["Whale print"])
        self.assertEqual(signals.iloc[0]["side"], "SELL")


class DedupeKeyTests(unittest.TestCase):
    """Der Zustell-Schluessel muss zwei verschiedene Prints trennen.

    Er bestand aus Art, Markt, Wallet und Minute. Ein Kauf von Yes ueber
    9.000 Dollar und ein Kauf von No ueber 4.000 derselben Wallet im selben
    Markt und derselben Minute trugen damit denselben Schluessel: nur der
    erste ging raus, nur der erste kam ins Ledger.
    """

    ZEIT = pd.Timestamp("2026-08-28 14:03:12", tz="UTC")

    def _print(self, outcome, notional, price, tx=""):
        return {
            "signal_type": "Whale print", "market_key": "0xcond", "wallet": "0xwhale",
            "outcome": outcome, "time": self.ZEIT, "side": "BUY",
            "notional": notional, "price": price, "tx": tx,
        }

    def test_two_outcomes_of_one_market_are_two_signals(self):
        a = sig.signal_dedupe_key(self._print("Yes", 9_000.0, 0.40, "0xtx1"))
        b = sig.signal_dedupe_key(self._print("No", 4_000.0, 0.61, "0xtx2"))
        self.assertNotEqual(a, b)

    def test_two_clips_in_the_same_minute_stay_apart_without_a_tx_hash(self):
        # Kalshi liefert keinen Transaktions-Hash; dann trennen Seite,
        # Groesse und Preis.
        a = sig.signal_dedupe_key(self._print("Yes", 9_000.0, 0.40))
        b = sig.signal_dedupe_key(self._print("Yes", 4_000.0, 0.41))
        self.assertNotEqual(a, b)

    def test_the_same_print_keeps_its_key_across_scans(self):
        eins = self._print("Yes", 9_000.0, 0.40, "0xtx1")
        self.assertEqual(sig.signal_dedupe_key(eins), sig.signal_dedupe_key(dict(eins)))

    def test_a_market_signal_key_does_not_move_with_its_reading(self):
        # Marktsignale beschreiben einen Zustand, der bei jedem Scan neu
        # gemessen wird. Haenge der Wert im Schluessel, wuerde dieselbe
        # Beobachtung bei jedem Tick erneut zugestellt.
        basis = {"signal_type": "Fast mover", "market_key": "0xcond", "wallet": "",
                 "outcome": "Yes", "time": self.ZEIT}
        self.assertEqual(
            sig.signal_dedupe_key(dict(basis, value=0.08)),
            sig.signal_dedupe_key(dict(basis, value=0.09)),
        )

    def test_missing_fields_do_not_become_the_word_nan(self):
        key = sig.signal_dedupe_key({"signal_type": "Whale print", "market_key": "0xc",
                                     "wallet": float("nan"), "outcome": "Yes",
                                     "time": self.ZEIT, "tx": float("nan"),
                                     "side": "BUY", "notional": 100.0, "price": 0.5})
        self.assertNotIn("nan", key)


class MarktsignalSchluesselWandertNichtTests(unittest.TestCase):
    """Der Zustell-Schluessel eines Marktsignals darf nicht am Venue-Stempel haengen.

    ``_observed_at`` stempelt ein Marktsignal mit dem ``updated_at`` des
    Marktes, und der Schluessel trug diesen Stempel auf die Minute genau. Der
    Wert wandert aber unter einem aktiv umbepreisten Markt, also wandert der
    Schluessel mit, und dieselbe unveraenderte Beobachtung gilt bei jedem Scan
    als neu.

    Das gerechnete Beispiel (Scanner-Standardintervall 10 Minuten):

    ==========  ==================  ====================  ==============
    Scan (UTC)  updated_at (Gamma)  Schluessel-Minute     Zustellung
    ==========  ==================  ====================  ==============
    14:25:00    14:23:07            2026-08-28 14:23      1. Alert
    14:35:00    14:34:51            2026-08-28 14:34      2. Alert
    14:45:00    14:44:02            2026-08-28 14:44      3. Alert
    ==========  ==================  ====================  ==============

    Ein Markt mit unveraendertem 1h-Move von 8 Cent erzeugt in einer halben
    Stunde drei Alerts und drei Ledger-Zeilen. Der Nachbarmarkt mit demselben
    Move, den Gamma seit 09:12 nicht neu gestempelt hat, erzeugt genau einen.
    Die Zustellhaeufigkeit entscheidet damit die Buchhaltung der Venue, nicht
    der Scanner.
    """

    MOVE = 0.08

    def _fast_mover(self, updated_at, scan_time):
        signals = sig.build_monitor_signals(
            pd.DataFrame([market("Fed cuts in March", 1_000.0, 24_000.0,
                                 change_1h=self.MOVE, market_key="0xcond",
                                 updated_at=updated_at)]),
            pd.DataFrame(),
            min_volume=0.0,
            min_liquidity=0.0,
            min_move=0.03,
            max_spread=0.0,
            min_whale_notional=1e12,
            ending_days=0,
            holder_threshold=1.0,
            holder_checks=0,
            tracked_keys=set(),
            now=pd.Timestamp(scan_time, tz="UTC"),
        )
        movers = signals[signals["signal_type"] == "Fast mover"]
        self.assertEqual(len(movers), 1)
        return movers.iloc[0]

    def test_drei_scans_eines_umbepreisten_marktes_bleiben_eine_zustellung(self):
        schluessel = [
            sig.signal_dedupe_key(self._fast_mover("2026-08-28T14:23:07Z", "2026-08-28 14:25:00")),
            sig.signal_dedupe_key(self._fast_mover("2026-08-28T14:34:51Z", "2026-08-28 14:35:00")),
            sig.signal_dedupe_key(self._fast_mover("2026-08-28T14:44:02Z", "2026-08-28 14:45:00")),
        ]
        self.assertEqual(len(set(schluessel)), 1, f"drei Schluessel fuer eine Beobachtung: {schluessel}")

    def test_der_stille_nachbarmarkt_traegt_denselben_schluessel_wie_der_laute(self):
        # Beide Maerkte melden denselben Move; nur ihr Venue-Stempel ist
        # verschieden. Der Schluessel darf sie deshalb nicht verschieden
        # oft zustellen -- er unterscheidet sie ueber den market_key.
        laut = self._fast_mover("2026-08-28T14:44:02Z", "2026-08-28 14:45:00")
        still = self._fast_mover("2026-08-28T09:12:00Z", "2026-08-28 14:45:00")
        self.assertEqual(sig.signal_dedupe_key(laut), sig.signal_dedupe_key(still))

    def test_zwei_maerkte_bleiben_zwei_zustellungen(self):
        a = {"signal_type": "Fast mover", "market_key": "0xaaa", "outcome": "Yes", "wallet": "",
             "time": pd.Timestamp("2026-08-28 14:23", tz="UTC")}
        b = dict(a, market_key="0xbbb")
        self.assertNotEqual(sig.signal_dedupe_key(a), sig.signal_dedupe_key(b))

    def test_ein_print_behaelt_seine_eigene_zeit_im_schluessel(self):
        # Nur Marktsignale verlieren den Stempel. Bei einem Print IST die Zeit
        # Teil der Identitaet des Ereignisses.
        basis = {"signal_type": "Whale print", "market_key": "0xcond", "wallet": "0xw",
                 "outcome": "Yes", "side": "BUY", "notional": 9_000.0, "price": 0.4, "tx": ""}
        frueh = dict(basis, time=pd.Timestamp("2026-08-28 14:03:12", tz="UTC"))
        spaet = dict(basis, time=pd.Timestamp("2026-08-28 14:59:12", tz="UTC"))
        self.assertNotEqual(sig.signal_dedupe_key(frueh), sig.signal_dedupe_key(spaet))


class ZustellSperreTests(unittest.TestCase):
    """Wie oft eine Beobachtung gemeldet wird, entscheidet der Scanner.

    Der Schluessel sagt, WAS ein Signal ist; die Sperre sagt, WIE OFT es
    rausgehen darf. Vorher steckte beides im selben Zeitstempel, und der kam
    von der Venue.
    """

    JETZT = pd.Timestamp("2026-08-28 15:00:00", tz="UTC")
    MARKT = {"signal_type": "Fast mover"}
    PRINT = {"signal_type": "Whale print"}

    def test_ein_print_hat_keine_ruhezeit_und_geht_genau_einmal(self):
        self.assertEqual(sig.delivery_cooldown_minutes("Whale print"), 0)
        self.assertTrue(sig.due_for_delivery(self.PRINT, None, self.JETZT))
        self.assertFalse(sig.due_for_delivery(self.PRINT, "2020-01-01T00:00:00+00:00", self.JETZT))

    def test_ein_marktsignal_ruht_eine_stunde(self):
        self.assertEqual(sig.delivery_cooldown_minutes("Fast mover"), 60)
        self.assertTrue(sig.due_for_delivery(self.MARKT, None, self.JETZT))
        self.assertFalse(sig.due_for_delivery(self.MARKT, "2026-08-28T14:25:00+00:00", self.JETZT))
        self.assertTrue(sig.due_for_delivery(self.MARKT, "2026-08-28T13:59:00+00:00", self.JETZT))

    def test_drei_scans_in_einer_halben_stunde_ergeben_eine_zustellung(self):
        # Dasselbe Beispiel wie oben, jetzt durch die Sperre gerechnet.
        zugestellt = None
        raus = []
        for scan in ("2026-08-28 14:25:00", "2026-08-28 14:35:00", "2026-08-28 14:45:00"):
            jetzt = pd.Timestamp(scan, tz="UTC")
            if sig.due_for_delivery(self.MARKT, zugestellt, jetzt):
                raus.append(scan)
                zugestellt = jetzt.isoformat()
        self.assertEqual(raus, ["2026-08-28 14:25:00"])

    def test_ein_unlesbarer_stempel_blockiert_nicht(self):
        self.assertTrue(sig.due_for_delivery(self.MARKT, "irgendwas", self.JETZT))
        self.assertTrue(sig.due_for_delivery(self.MARKT, "", self.JETZT))


class PlatzhalterNullenTests(unittest.TestCase):
    """Eine Null, die "nicht messbar" bedeutet, darf nicht wie eine Messung aussehen.

    ``build_monitor_signals`` fuellt die Felder, die eine Signalart nicht
    fuehren kann, mit 0.0, damit der Frame saubere numerische Spalten hat.
    In der Tabelle war das nicht zu erkennen: neben Marktsignalen mit echter
    Buchtiefe stand jeder Whale-Print mit Volume 0 und Liquidity $0 da, als
    waere sein Markt leer, und wer nach Liquiditaet sortierte, bekam alle
    Prints ans Ende gestellt.
    """

    def _frame(self) -> pd.DataFrame:
        return sig.build_monitor_signals(
            pd.DataFrame([market("Fed cuts", 9_000.0, 60_000.0, change_1h=0.09)]),
            pd.DataFrame([{
                "platform": "Polymarket", "time": pd.Timestamp("2026-08-28 12:00", tz="UTC"),
                "title": "Fed cuts", "side": "BUY", "outcome": "Yes", "price": 0.62,
                "notional": 12_500.0, "wallet": "0xabc", "trader": "tony",
                "market_key": "Fed cuts", "url": "", "transaction_hash": "0xtx",
            }]),
            min_volume=0.0, min_liquidity=0.0, min_move=0.05, max_spread=0.01,
            min_whale_notional=1_000.0, ending_days=0, holder_threshold=1.0,
            holder_checks=0, tracked_keys=set(),
        )

    def test_der_rohe_frame_behaelt_die_nullen(self):
        """Scanner und Ledger sehen den Frame unveraendert."""

        roh = self._frame()
        print_zeile = roh[roh["signal_type"].eq("Whale print")].iloc[0]
        markt_zeile = roh[roh["signal_type"].eq("Fast mover")].iloc[0]
        self.assertEqual(float(print_zeile["volume"]), 0.0)
        self.assertEqual(float(print_zeile["liquidity"]), 0.0)
        self.assertEqual(float(markt_zeile["notional"]), 0.0)

    def test_die_anzeige_laesst_die_felder_leer(self):
        anzeige = sig.blank_structural_placeholders(self._frame())
        print_zeile = anzeige[anzeige["signal_type"].eq("Whale print")].iloc[0]
        markt_zeile = anzeige[anzeige["signal_type"].eq("Fast mover")].iloc[0]
        self.assertTrue(pd.isna(print_zeile["volume"]))
        self.assertTrue(pd.isna(print_zeile["liquidity"]))
        self.assertTrue(pd.isna(markt_zeile["notional"]))
        # Was gemessen ist, bleibt stehen.
        self.assertEqual(float(print_zeile["notional"]), 12_500.0)
        self.assertEqual(float(markt_zeile["volume"]), 60_000.0)
        self.assertEqual(float(markt_zeile["liquidity"]), 50_000.0)

    def test_leerer_frame_und_frame_ohne_art(self):
        self.assertTrue(sig.blank_structural_placeholders(pd.DataFrame()).empty)
        ohne = pd.DataFrame([{"volume": 0.0}])
        self.assertEqual(float(sig.blank_structural_placeholders(ohne).iloc[0]["volume"]), 0.0)

    def test_die_volumenspalte_ist_der_mischwert(self):
        """Nicht "24h": ohne Handel heute steht das Lebensvolumen darin."""

        frame = pd.DataFrame([{"activity_volume": 4_200_000.0, "volume_24h": 0.0}])
        self.assertEqual(sig.monitor_volume_col(frame), "activity_volume")
        self.assertEqual(sig.monitor_volume_col(pd.DataFrame([{"volume_24h": 1.0}])), "volume_24h")


if __name__ == "__main__":
    unittest.main()
