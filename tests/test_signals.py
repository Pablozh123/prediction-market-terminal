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


if __name__ == "__main__":
    unittest.main()
