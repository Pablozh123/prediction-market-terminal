import unittest

import pandas as pd

from app import track_record as tr


def closed(rows):
    return pd.DataFrame(rows)


def pos(market, pnl, bought, *, title="M", url="", time="2026-01-01"):
    return {"market_key": market, "title": title, "realized_pnl": pnl, "total_bought": bought, "time": time, "url": url}


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


if __name__ == "__main__":
    unittest.main()
