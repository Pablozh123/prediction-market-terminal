import unittest

import pandas as pd

from app import track_record as tr


def closed(rows):
    return pd.DataFrame(rows)


def pos(market, pnl, bought, *, title="M", url="", time="2026-01-01", outcome="Yes"):
    return {"market_key": market, "title": title, "realized_pnl": pnl, "total_bought": bought, "time": time, "url": url, "outcome": outcome}


class MarketRecordTests(unittest.TestCase):
    def test_nets_legs_of_same_condition_into_one_market(self):
        cp = closed([pos("c1", 30, 100), pos("c1", -10, 40)])
        markets = tr.market_records(cp)
        self.assertEqual(len(markets), 1)
        self.assertAlmostEqual(float(markets.iloc[0]["net_pnl"]), 20.0)
        self.assertTrue(bool(markets.iloc[0]["win"]))

    def test_event_records_net_negrisk_outcomes(self):
        # Three separate conditionIds, one NegRisk event: netted = 1 winning event.
        ev = "https://polymarket.com/event/election"
        cp = closed([pos("c1", 80, 100, url=ev), pos("c2", -10, 30, url=ev), pos("c3", -20, 40, url=ev)])
        events = tr.event_records(cp)
        self.assertEqual(len(events), 1)
        self.assertTrue(bool(events.iloc[0]["win"]))

    def test_empty_frames_safe(self):
        self.assertTrue(tr.market_records(pd.DataFrame()).empty)
        self.assertTrue(tr.event_records(pd.DataFrame()).empty)


class PnlAttributionTests(unittest.TestCase):
    def test_both_sides_market_reads_as_structural(self):
        cp = closed(
            [
                pos("c1", 100, 100, outcome="Yes"),
                pos("c1", -40, 60, outcome="No"),
                pos("c2", 40, 50, outcome="Yes"),
            ]
        )
        att = tr.pnl_attribution(cp)
        self.assertEqual(att["structural_markets"], 1)
        self.assertAlmostEqual(att["structural_share"], 0.6, places=9)
        self.assertAlmostEqual(att["top_event_share"], 0.4, places=9)
        self.assertAlmostEqual(att["remaining_share"], 0.0, places=9)

    def test_one_event_dominates(self):
        cp = closed(
            [
                pos("c1", 800, 500, title="the big one"),
                pos("c2", 100, 100),
                pos("c3", 100, 100),
            ]
        )
        att = tr.pnl_attribution(cp)
        self.assertAlmostEqual(att["structural_share"], 0.0, places=9)
        self.assertAlmostEqual(att["top_event_share"], 0.8, places=9)
        self.assertAlmostEqual(att["remaining_share"], 0.2, places=9)
        self.assertEqual(att["top_event_title"], "the big one")

    def test_negrisk_legs_net_before_attribution(self):
        ev = "https://polymarket.com/event/one"
        cp = closed(
            [
                pos("c1", 500, 300, url=ev),
                pos("c2", -100, 100, url=ev),
                pos("c3", 600, 400),
            ]
        )
        att = tr.pnl_attribution(cp)
        # Event nets to +400; standalone market +600 → gross 1000.
        self.assertAlmostEqual(att["top_event_share"], 0.6, places=9)
        self.assertAlmostEqual(att["remaining_share"], 0.4, places=9)

    def test_no_gross_profit_gives_no_shares(self):
        att = tr.pnl_attribution(closed([pos("c1", -50, 100), pos("c2", -20, 40)]))
        self.assertIsNone(att["structural_share"])
        self.assertEqual(att["gross_profit"], 0.0)

    def test_empty_safe(self):
        att = tr.pnl_attribution(pd.DataFrame())
        self.assertIsNone(att["structural_share"])
        self.assertEqual(att["structural_markets"], 0)


class TrackRecordTests(unittest.TestCase):
    def test_negrisk_win_rate_correction_flagged(self):
        # 1 winning outcome + 3 losing outcomes across two NegRisk events.
        e1 = "https://polymarket.com/event/e1"
        e2 = "https://polymarket.com/event/e2"
        cp = closed(
            [
                pos("c1", 100, 100, url=e1),
                pos("c2", -10, 20, url=e1),
                pos("c3", -10, 20, url=e1),
                pos("c4", 50, 100, url=e2),
                pos("c5", -5, 10, url=e2),
            ]
        )
        r = tr.track_record(cp, min_resolved_markets=1, min_span_days=0)
        # Naive: 2 of 5 rows positive = 40%. Event-netted: 2 of 2 events won = 100%.
        self.assertAlmostEqual(r["naive_win_rate"], 0.4)
        self.assertAlmostEqual(r["event_win_rate"], 1.0)
        self.assertTrue(any("misleads" in f for f in r["flags"]))

    def test_settled_pnl_uses_closed_positions_not_visible_only(self):
        # closed-positions retains the redeemed winner that /positions would drop.
        cp = closed([pos("win", 11_400_000, 500_000), pos("loss", -3_500_000, 400_000)])
        r = tr.track_record(cp, min_resolved_markets=1, min_span_days=0)
        self.assertAlmostEqual(r["settled_pnl"], 7_900_000.0)  # not the -3.5M a naive visible-only sum shows

    def test_farmer_flag_on_high_volume_zero_edge(self):
        rows = [pos(f"m{i}", 1.0, 50_000, time=f"2026-01-{i+1:02d}") for i in range(6)]
        r = tr.track_record(closed(rows), min_resolved_markets=1, min_span_days=0)
        self.assertTrue(r["farmer_flag"])
        self.assertEqual(r["grade"], "F")

    def test_one_hit_wonder_flagged(self):
        rows = [pos("big", 1000, 100, time="2026-01-01")] + [pos(f"m{i}", 10, 100, time=f"2026-02-{i+1:02d}") for i in range(6)]
        r = tr.track_record(closed(rows), min_resolved_markets=1, min_span_days=0)
        self.assertTrue(r["one_hit_flag"])
        self.assertGreaterEqual(r["top_market_share"], 0.6)

    def test_insufficient_sample_gate_caps_score(self):
        cp = closed([pos("c1", 5000, 100)])
        r = tr.track_record(cp)  # default gate: needs >=10 markets / >=14d
        self.assertFalse(r["sample_ok"])
        self.assertLessEqual(r["score"], 30.0)
        self.assertTrue(any("insufficient sample" in f for f in r["flags"]))

    def test_empty_wallet_is_safe(self):
        r = tr.track_record(pd.DataFrame())
        self.assertEqual(r["resolved_markets"], 0)
        self.assertIsNone(r["corrected_win_rate"])
        self.assertEqual(r["grade"], "F")

    def test_uncapped_union_gives_real_reliable_win_rate(self):
        # Full winners+losers set (not capped) -> real, reliable win rate incl. losses.
        cp = closed(
            [pos("w1", 500, 100, time="2026-01-01"), pos("w2", 300, 100, time="2026-02-01"),
             pos("l1", -200, 100, time="2026-03-01")]
        )
        r = tr.track_record(cp, resolved_capped=False, min_resolved_markets=1, min_span_days=0)
        self.assertTrue(r["win_rate_reliable"])
        self.assertAlmostEqual(r["corrected_win_rate"], 2 / 3)
        self.assertAlmostEqual(r["settled_pnl"], 600.0)  # 500 + 300 - 200, losers counted

    def test_capped_set_flags_extremes_only(self):
        cp = closed([pos("w1", 500, 100, time="2026-01-01"), pos("l1", -200, 100, time="2026-03-01")])
        r = tr.track_record(cp, resolved_capped=True, min_resolved_markets=1, min_span_days=0)
        self.assertFalse(r["win_rate_reliable"])
        self.assertTrue(any("extremes only" in f for f in r["flags"]))


class PnlPerVolumeIsTheEdgeTests(unittest.TestCase):
    """``pnl_per_volume`` und die realisierte Rendite je Dollar sind dieselbe
    Zahl, und die Wallet-Seite zeigt beide.

    Algebraisch: die Rendite ist ``payout / cost - 1``, und ``payout`` ist
    ``cost + pnl``, also ``pnl / cost``. ``pnl_per_volume`` ist ``settled_pnl
    / volume``, und ``volume`` ist dieselbe Summe ueber ``stake_usd`` wie
    ``cost``. Die Kachel sagt das seit eben dazu; dieser Test haelt fest, dass
    es stimmt, damit die Beschriftung nicht falsch wird, wenn eine der beiden
    Definitionen sich aendert.
    """

    def _closed(self) -> pd.DataFrame:
        return pd.DataFrame([
            {"market_key": "0xa", "title": "A", "realized_pnl": 40.0,
             "total_bought": 200.0, "avg_price": 0.5, "time": "2026-07-01T00:00:00Z"},
            {"market_key": "0xb", "title": "B", "realized_pnl": -30.0,
             "total_bought": 100.0, "avg_price": 0.3, "time": "2026-07-10T00:00:00Z"},
            {"market_key": "0xc", "title": "C", "realized_pnl": 12.5,
             "total_bought": 50.0, "avg_price": 0.8, "time": "2026-07-20T00:00:00Z"},
        ])

    def test_die_beiden_kennzahlen_sind_dieselbe_zahl(self) -> None:
        from app import perf_metrics as perf

        closed = self._closed()
        record = tr.track_record(closed, None, None)

        df = closed.copy()
        df["cost"] = tr.stake_usd(df)
        df["payout"] = df["cost"] + pd.to_numeric(df["realized_pnl"], errors="coerce").fillna(0.0)
        df["group"] = df.apply(tr._event_key, axis=1)
        edge = perf.cluster_bootstrap_edge(df, "group", cost_column="cost", payout_column="payout")

        self.assertIsNotNone(edge["edge"])
        self.assertAlmostEqual(record["pnl_per_volume"], edge["edge"], places=12)

    def test_die_identitaet_haelt_auch_bei_verlust(self) -> None:
        from app import perf_metrics as perf

        closed = self._closed()
        closed.loc[0, "realized_pnl"] = -90.0
        record = tr.track_record(closed, None, None)
        df = closed.copy()
        df["cost"] = tr.stake_usd(df)
        df["payout"] = df["cost"] + pd.to_numeric(df["realized_pnl"], errors="coerce").fillna(0.0)
        df["group"] = df.apply(tr._event_key, axis=1)
        edge = perf.cluster_bootstrap_edge(df, "group", cost_column="cost", payout_column="payout")

        self.assertLess(record["pnl_per_volume"], 0)
        self.assertAlmostEqual(record["pnl_per_volume"], edge["edge"], places=12)


class ActivityReconstructionTests(unittest.TestCase):
    def _activity(self, rows):
        return pd.DataFrame(rows)

    def act(self, market, side, notional, typ="TRADE"):
        return {"market_key": market, "side": side, "notional": notional, "type": typ}

    def test_reconstructs_loss_from_activity(self):
        # Market m1: bought 100, redeemed 250 -> win. m2: bought 80, sold 30 -> loss.
        a = self._activity([
            self.act("m1", "BUY", 100),
            self.act("m1", "", 250, typ="REDEEM"),
            self.act("m2", "BUY", 80),
            self.act("m2", "SELL", 30),
        ])
        rec = tr.settled_from_activity(a)
        self.assertEqual(len(rec), 2)
        m1 = rec[rec["market_key"] == "m1"].iloc[0]
        m2 = rec[rec["market_key"] == "m2"].iloc[0]
        self.assertAlmostEqual(float(m1["net_pnl"]), 150.0)
        self.assertTrue(bool(m1["win"]))
        self.assertAlmostEqual(float(m2["net_pnl"]), -50.0)
        self.assertFalse(bool(m2["win"]))

    def test_activity_is_secondary_crosscheck_not_headline(self):
        # settled PnL/win rate come from the closed union; activity only yields exit_win_rate.
        cp = closed([pos("m1", 150, 100), pos("l1", -40, 100)])
        a = self._activity([
            self.act("m1", "BUY", 100), self.act("m1", "", 250, typ="REDEEM"),
            self.act("m2", "BUY", 80), self.act("m2", "SELL", 30),  # a sold loss
        ])
        r = tr.track_record(cp, activity=a, resolved_capped=False, min_resolved_markets=1, min_span_days=0)
        self.assertAlmostEqual(r["settled_pnl"], 110.0)  # 150 - 40, from closed union
        self.assertAlmostEqual(r["exit_win_rate"], 0.5)  # activity cross-check: m1 win, m2 loss
        self.assertTrue(r["win_rate_reliable"])

    def test_empty_activity_safe(self):
        self.assertTrue(tr.settled_from_activity(pd.DataFrame()).empty)


class ReconcileWithActivityTests(unittest.TestCase):
    """Eine eingeloeste Gewinnposition darf nicht als Totalverlust dastehen.

    Echte Zeilen der Wallet 0x29af...f88d (2026-08-28): /closed-positions
    meldet fuer "Will Anthropic have the #2 AI model at the end of July
    2026?" avgPrice 0.9422, totalBought 5.3191, curPrice 1 und realizedPnl
    -5.0119. Die Aktivitaet dazu: ein Kauf ueber $5.011975 und eine
    Einloesung ueber $5.319133 - also plus 31 Cent. Die Seite zeigte den
    Verlust und ihre eigene Kalibrierungskurve, die den Aufloesungspreis
    liest, gleichzeitig einen Treffer.
    """

    CID = "0x5a2f58c07be8f99012ca65766c9c727afecbe61d30914210f91d0cf704267b62"

    def _resolved(self, pnl=-5.0119, cur=1.0):
        return pd.DataFrame([{
            "market_key": self.CID, "outcome": "Yes", "title": "Anthropic #2",
            "avg_price": 0.9422, "current_price": cur, "total_bought": 5.3191, "realized_pnl": pnl,
        }])

    def _activity(self, mit_redeem=True):
        rows = [{"market_key": self.CID, "outcome": "Yes", "type": "TRADE", "side": "BUY", "notional": 5.011975}]
        if mit_redeem:
            rows.append({"market_key": self.CID, "outcome": "Yes", "type": "REDEEM", "side": "", "notional": 5.319133})
        return pd.DataFrame(rows)

    def test_cash_flow_replaces_the_contradictory_row(self):
        frame, n = tr.reconcile_resolved_with_activity(self._resolved(), self._activity())
        self.assertEqual(n, 1)
        self.assertAlmostEqual(float(frame.iloc[0]["realized_pnl"]), 0.307158, places=5)
        self.assertEqual(frame.iloc[0]["pnl_source"], "cash_flow")

    def test_no_redemption_no_correction(self):
        # Vor der Aufloesung mit Verlust verkauft: realizedPnl stimmt, auch
        # wenn der Markt spaeter auf 1 ging.
        frame, n = tr.reconcile_resolved_with_activity(self._resolved(), self._activity(mit_redeem=False))
        self.assertEqual(n, 0)
        self.assertAlmostEqual(float(frame.iloc[0]["realized_pnl"]), -5.0119, places=4)
        self.assertEqual(frame.iloc[0]["pnl_source"], "api")

    def test_untouched_when_the_feed_does_not_contradict_itself(self):
        frame, n = tr.reconcile_resolved_with_activity(self._resolved(pnl=-5.0119, cur=0.0), self._activity())
        self.assertEqual(n, 0)
        self.assertAlmostEqual(float(frame.iloc[0]["realized_pnl"]), -5.0119, places=4)

    def test_without_activity_nothing_is_invented(self):
        frame, n = tr.reconcile_resolved_with_activity(self._resolved(), None)
        self.assertEqual(n, 0)
        self.assertEqual(frame.iloc[0]["pnl_source"], "api")
        leer, n_leer = tr.reconcile_resolved_with_activity(pd.DataFrame(), self._activity())
        self.assertEqual(n_leer, 0)
        self.assertTrue(leer.empty)


class StakeUsdTests(unittest.TestCase):
    """``total_bought`` zaehlt Anteile; jede Dollar-Groesse muss umrechnen.

    Beleg aus dem oeffentlichen Feed (2026-08-28, Wallet 0x29af...f88d):
    'Will "Blue" be said during the next episode of the All-In Podcast?'
    steht mit totalBought 179.809, avgPrice 0.6887 und realizedPnl 55.9739 -
    und 179.809 x (1 - 0.6887) = 55.974. Die Zahl geht nur auf, wenn
    totalBought Anteile sind: 179.809 Anteile fuer $123.83.
    """

    def test_shares_times_price_is_the_dollar_stake(self):
        frame = closed([pos("blue", 55.9739, 179.809)])
        frame["avg_price"] = 0.6887
        self.assertAlmostEqual(float(tr.stake_usd(frame).iloc[0]), 123.83, places=2)

    def test_cost_usd_column_wins_when_present(self):
        frame = closed([pos("blue", 55.9739, 179.809)])
        frame["avg_price"] = 0.6887
        frame["cost_usd"] = 120.0
        self.assertAlmostEqual(float(tr.stake_usd(frame).iloc[0]), 120.0, places=6)

    def test_without_a_price_the_share_count_is_all_there_is(self):
        frame = closed([pos("blue", 55.9739, 179.809)])
        self.assertAlmostEqual(float(tr.stake_usd(frame).iloc[0]), 179.809, places=3)
        self.assertTrue(tr.stake_usd(pd.DataFrame()).empty)

    def test_market_return_is_pnl_per_dollar(self):
        frame = closed([pos("m1", 50.0, 200.0)])
        frame["avg_price"] = 0.5
        rec = tr.market_records(frame)
        self.assertAlmostEqual(float(rec.iloc[0]["volume"]), 100.0)
        self.assertAlmostEqual(float(rec.iloc[0]["return"]), 0.5)


if __name__ == "__main__":
    unittest.main()
