import unittest

import pandas as pd

from app import suspicion as susp


def tape(rows):
    return pd.DataFrame(rows)


def trade(wallet, title, outcome="Yes", notional=5000.0, time="2026-06-10T12:00:00Z"):
    return {
        "wallet": wallet,
        "title": title,
        "outcome": outcome,
        "notional": notional,
        "time": pd.Timestamp(time),
    }


class FreshWalletClusterTests(unittest.TestCase):
    def test_cluster_of_fresh_wallets_same_side_is_detected(self):
        trades = tape(
            [
                trade("0xaaa", "Will X happen?", "Yes", 6000.0),
                trade("0xbbb", "Will X happen?", "Yes", 7000.0),
                trade("0xccc", "Will X happen?", "Yes", 8000.0),
                trade("0xddd", "Will X happen?", "No", 9000.0),
            ]
        )
        clusters = susp.fresh_wallet_clusters(trades, whale_threshold=2500.0)
        self.assertEqual(len(clusters), 1)
        row = clusters.iloc[0]
        self.assertEqual(row["title"], "Will X happen?")
        self.assertEqual(row["fresh_wallets"], 3)
        self.assertEqual(row["fresh_outcome"], "YES")
        self.assertAlmostEqual(row["fresh_notional"], 21000.0)

    def test_active_wallets_are_not_fresh(self):
        rows = [trade("0xaaa", "Busy market", "Yes", 6000.0, f"2026-06-10T0{i}:00:00Z") for i in range(5)]
        rows += [trade("0xbbb", "Busy market", "Yes", 6000.0)]
        clusters = susp.fresh_wallet_clusters(tape(rows), whale_threshold=2500.0)
        self.assertTrue(clusters.empty)

    def test_small_fresh_wallets_below_threshold_ignored(self):
        trades = tape(
            [
                trade("0xaaa", "Tiny market", "Yes", 100.0),
                trade("0xbbb", "Tiny market", "Yes", 150.0),
            ]
        )
        clusters = susp.fresh_wallet_clusters(trades, whale_threshold=2500.0)
        self.assertTrue(clusters.empty)


class BonusTests(unittest.TestCase):
    def _event_risk(self):
        return pd.DataFrame(
            [
                {"title": "Will X happen?", "event_insider_score": 55.0, "event_insider_flags": "long-odds big bet", "notional": 20000.0},
                {"title": "Quiet market", "event_insider_score": 20.0, "event_insider_flags": "watch only", "notional": 5000.0},
            ]
        )

    def test_fresh_cluster_bonus_and_flag(self):
        clusters = pd.DataFrame([{"title": "Will X happen?", "fresh_wallets": 3, "fresh_outcome": "YES", "fresh_notional": 21000.0}])
        enriched = susp.apply_fresh_wallet_bonus(self._event_risk(), clusters)
        hot = enriched[enriched["title"] == "Will X happen?"].iloc[0]
        self.assertAlmostEqual(hot["event_insider_score"], round(55.0 + 7.5), places=1)
        self.assertIn("3 fresh wallets on YES", hot["event_insider_flags"])
        quiet = enriched[enriched["title"] == "Quiet market"].iloc[0]
        self.assertAlmostEqual(quiet["event_insider_score"], 20.0)
        self.assertEqual(quiet["event_insider_flags"], "watch only")

    def test_score_capped_at_100(self):
        events = pd.DataFrame([{"title": "Hot", "event_insider_score": 96.0, "event_insider_flags": ""}])
        clusters = pd.DataFrame([{"title": "Hot", "fresh_wallets": 4, "fresh_outcome": "YES", "fresh_notional": 1.0}])
        enriched = susp.apply_fresh_wallet_bonus(events, clusters)
        self.assertEqual(enriched.iloc[0]["event_insider_score"], 100.0)
        self.assertEqual(enriched.iloc[0]["event_insider_level"], "High")

    def test_account_age_bonus_only_for_young_accounts(self):
        wallet_risk = pd.DataFrame(
            [
                {"wallet": "0xAAA", "wallet_insider_score": 50.0, "wallet_insider_flags": "watch only"},
                {"wallet": "0xbbb", "wallet_insider_score": 50.0, "wallet_insider_flags": "fast burst"},
            ]
        )
        stats = pd.DataFrame(
            [
                {"wallet": "0xaaa", "account_age_days": 5.0},
                {"wallet": "0xbbb", "account_age_days": 400.0},
            ]
        )
        enriched = susp.apply_account_age_bonus(wallet_risk, stats)
        young = enriched[enriched["wallet"].str.lower() == "0xaaa"].iloc[0]
        old = enriched[enriched["wallet"].str.lower() == "0xbbb"].iloc[0]
        self.assertAlmostEqual(young["wallet_insider_score"], 60.0)
        self.assertIn("new account (5d)", young["wallet_insider_flags"])
        self.assertAlmostEqual(old["wallet_insider_score"], 50.0)
        self.assertNotIn("new account", old["wallet_insider_flags"])

    def test_missing_stats_leave_scores_unchanged(self):
        wallet_risk = pd.DataFrame([{"wallet": "0xaaa", "wallet_insider_score": 50.0, "wallet_insider_flags": ""}])
        enriched = susp.apply_account_age_bonus(wallet_risk, pd.DataFrame())
        self.assertAlmostEqual(enriched.iloc[0]["wallet_insider_score"], 50.0)


class StoryAndDrilldownTests(unittest.TestCase):
    def test_event_story_mentions_key_patterns(self):
        row = pd.Series(
            {
                "notional": 45000.0,
                "unique_wallets": 4,
                "long_odds_share": 0.6,
                "late_share": 0.5,
                "top_wallet_share": 0.7,
                "fresh_wallets": 3,
                "fresh_outcome": "YES",
                "event_directional_share": 0.9,
                "event_directional_label": "YES",
                "price_move": 0.06,
            }
        )
        story = susp.event_story(row)
        self.assertIn("whale flow from 4 wallets", story)
        self.assertIn("long odds", story)
        self.assertIn("close to resolution", story)
        self.assertIn("3 fresh wallets on YES", story)
        self.assertIn("+6c", story)

    def test_event_story_handles_quiet_event(self):
        story = susp.event_story(pd.Series({"notional": 5000.0, "unique_wallets": 1}))
        self.assertIn("no single dominant pattern", story)

    def test_wallets_for_event_filters_and_sorts(self):
        trades = tape(
            [
                trade("0xaaa", "Will X happen?"),
                trade("0xbbb", "Will X happen?"),
                trade("0xccc", "Other market"),
            ]
        )
        wallet_risk = pd.DataFrame(
            [
                {"wallet": "0xaaa", "wallet_insider_score": 40.0},
                {"wallet": "0xbbb", "wallet_insider_score": 80.0},
                {"wallet": "0xccc", "wallet_insider_score": 90.0},
            ]
        )
        subset = susp.wallets_for_event(trades, wallet_risk, "Will X happen?")
        self.assertEqual(list(subset["wallet"]), ["0xbbb", "0xaaa"])


if __name__ == "__main__":
    unittest.main()
