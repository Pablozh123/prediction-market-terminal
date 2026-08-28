"""app/wallet_similar.py — overlap among top holders of the wallet's markets."""

from __future__ import annotations

import unittest

from app import wallet_similar as ws
from src import prediction_markets as md

ME = "0x" + "a" * 40
W1 = "0x" + "b" * 40
W2 = "0x" + "c" * 40
W3 = "0x" + "d" * 40
M1 = "0x" + "1" * 64
M2 = "0x" + "2" * 64
M3 = "0x" + "3" * 64


def _holders(*entries):
    # entries: (wallet, outcomeIndex, amount, name)
    yes = [{"proxyWallet": w, "outcomeIndex": i, "amount": a, "name": n} for w, i, a, n in entries if i == 0]
    no = [{"proxyWallet": w, "outcomeIndex": i, "amount": a, "name": n} for w, i, a, n in entries if i == 1]
    return [{"token": "tok-yes", "holders": yes}, {"token": "tok-no", "holders": no}]


class TallyTests(unittest.TestCase):
    def test_counts_shared_markets_and_sides(self) -> None:
        markets = [
            {"market_key": M1, "title": "One", "outcome": "Yes", "value": 300},
            {"market_key": M2, "title": "Two", "outcome": "No", "value": 200},
            {"market_key": M3, "title": "Three", "outcome": "Yes", "value": 100},
        ]
        holders = {
            M1: _holders((ME, 0, 50, "me"), (W1, 0, 40, "bee"), (W2, 1, 10, "")),
            M2: _holders((W1, 1, 5, "bee"), (W2, 0, 7, "cee")),
            M3: _holders((W1, 0, 1, ""), (W3, 0, 0, "zero")),  # zero amount does not count
        }
        rows = ws.tally_overlaps(ME, markets, holders)
        self.assertEqual([r["wallet"] for r in rows], [W1, W2])
        bee = rows[0]
        self.assertEqual(bee["shared"], 3)
        self.assertEqual(bee["same_side"], 3)  # Yes/Yes, No/No, Yes/Yes
        self.assertEqual(bee["name"], "bee")
        cee = rows[1]
        self.assertEqual(cee["shared"], 2)
        self.assertEqual(cee["opposite_side"], 2)
        self.assertEqual(cee["name"], "cee")
        self.assertEqual([m["side"] for m in cee["markets"]], ["opposite", "opposite"])

    def test_an_address_in_the_name_field_is_not_a_name(self) -> None:
        markets = [{"market_key": M1, "title": "One", "outcome": "Yes", "value": 1}]
        holders = {M1: _holders((W1, 0, 5, W1.upper()))}
        rows = ws.tally_overlaps(ME, markets, holders)
        self.assertEqual(rows[0]["name"], "")

    def test_both_sides_held_counts_the_market_once(self) -> None:
        markets = [{"market_key": M1, "title": "One", "outcome": "Yes", "value": 1}]
        holders = {M1: _holders((W1, 0, 5, ""), (W1, 1, 5, ""))}
        rows = ws.tally_overlaps(ME, markets, holders)
        self.assertEqual(rows[0]["shared"], 1)
        self.assertEqual(rows[0]["same_side"], 1)


class SimilarWalletsTests(unittest.TestCase):
    def test_builds_rows_with_summaries_and_leaderboard(self) -> None:
        open_rows = [
            {"market_key": M2, "title": "Two", "outcome": "No", "value": 200},
            {"market_key": M1, "title": "One", "outcome": "Yes", "value": 300},
            {"market_key": "not-a-condition", "title": "junk", "outcome": "Yes", "value": 999},
        ]
        calls: list[tuple[str, int]] = []

        def holders(key, limit):
            calls.append((key, limit))
            if key == M1:
                return _holders((W1, 0, 40, "bee"), (W2, 1, 10, ""))
            return _holders((W1, 1, 5, ""))

        summaries = {W1: {"positions": 12, "value": 4200.0, "read": True}, W2: {"positions": 3, "value": 80.0, "read": True}}
        lb = {W1: {"pnl": 1500.0, "volume": 90000.0, "name": "bee-lb"}}
        out = ws.similar_wallets(ME, open_rows, max_markets=5, holders_per_token=7, top=5, leaderboard=lb,
                                 holders_fetcher=holders, summary_fetcher=lambda w: summaries[w])
        # Largest first, junk key dropped, limit passed through.
        self.assertEqual(calls, [(M1, 7), (M2, 7)])
        self.assertEqual(out["basis"]["markets_checked"], 2)
        self.assertEqual(out["basis"]["markets_available"], 2)
        self.assertEqual(out["candidates"], 2)
        r1, r2 = out["rows"]
        self.assertEqual(r1["wallet"], W1)
        self.assertEqual(r1["shared"], 2)
        self.assertEqual(r1["overlap"], 1.0)
        self.assertEqual(r1["same_side"], 2)
        self.assertEqual(r1["their_positions"], 12)
        self.assertEqual(r1["lb_pnl"], 1500.0)
        self.assertEqual(r1["lb_volume"], 90000.0)
        self.assertTrue(r1["on_leaderboard"])
        self.assertEqual(r1["name"], "bee")
        self.assertEqual(r2["wallet"], W2)
        self.assertEqual(r2["overlap"], 0.5)
        self.assertIsNone(r2["lb_pnl"])
        self.assertFalse(r2["on_leaderboard"])
        self.assertTrue(r2["profile_url"].endswith(W2))
        self.assertIn("top 7 holders per outcome", out["basis"]["note"])

    def test_upstream_failures_are_reported_not_hidden(self) -> None:
        def holders(key, limit):
            raise md.MarketDataError("holders down")

        out = ws.similar_wallets(ME, [{"market_key": M1, "outcome": "Yes", "value": 1}], holders_fetcher=holders,
                                 summary_fetcher=lambda w: {"positions": 0, "value": 0.0, "read": True})
        self.assertEqual(out["rows"], [])
        self.assertEqual(len(out["basis"]["errors"]), 1)
        self.assertIn("holders down", out["basis"]["errors"][0])

    def test_summary_failure_marks_the_row_unread(self) -> None:
        def summary(w):
            raise md.MarketDataError("positions down")

        out = ws.similar_wallets(ME, [{"market_key": M1, "outcome": "Yes", "value": 1}],
                                 holders_fetcher=lambda k, n: _holders((W1, 0, 3, "")), summary_fetcher=summary)
        self.assertFalse(out["rows"][0]["summary_read"])
        self.assertIsNone(out["rows"][0]["their_positions"])

    def test_no_open_markets_gives_an_empty_honest_answer(self) -> None:
        out = ws.similar_wallets(ME, [], holders_fetcher=lambda k, n: [], summary_fetcher=lambda w: {})
        self.assertEqual(out["rows"], [])
        self.assertEqual(out["basis"]["markets_checked"], 0)
        self.assertEqual(out["basis"]["markets_read"], 0)


class DenominatorTests(unittest.TestCase):
    """A market whose holder list never arrived cannot hold a match, so it
    cannot sit in the denominator either."""

    def test_failed_reads_do_not_dilute_the_overlap(self) -> None:
        def holders(key, limit):
            if key == M1:
                return _holders((W1, 0, 40, "bee"))
            raise md.MarketDataError("holders down")

        rows = [{"market_key": M1, "outcome": "Yes", "value": 300},
                {"market_key": M2, "outcome": "Yes", "value": 200}]
        out = ws.similar_wallets(ME, rows, holders_fetcher=holders,
                                 summary_fetcher=lambda w: {"positions": 1, "value": 1.0, "read": True})
        self.assertEqual(out["basis"]["markets_checked"], 2)
        self.assertEqual(out["basis"]["markets_read"], 1)
        # In dem einen lesbaren Markt sitzt das Wallet: 100 Prozent, nicht 50.
        self.assertEqual(out["rows"][0]["shared"], 1)
        self.assertEqual(out["rows"][0]["overlap"], 1.0)
        self.assertIn("1 whose holder list was actually read", out["basis"]["note"])


class BaseRateTests(unittest.TestCase):
    """The holders feed ranks by size, so the same large wallets recur across
    markets. A row means nothing without the rate an ordinary candidate hits."""

    def test_median_candidate_overlap_is_reported(self) -> None:
        def holders(key, limit):
            if key == M1:
                return _holders((W1, 0, 40, ""), (W2, 0, 20, ""))
            return _holders((W1, 0, 30, ""))

        rows = [{"market_key": M1, "outcome": "Yes", "value": 300},
                {"market_key": M2, "outcome": "Yes", "value": 200}]
        out = ws.similar_wallets(ME, rows, holders_fetcher=holders,
                                 summary_fetcher=lambda w: {"positions": 1, "value": 1.0, "read": True})
        self.assertEqual(out["basis"]["median_shared"], 1.0)
        by_wallet = {r["wallet"]: r for r in out["rows"]}
        self.assertEqual(by_wallet[W1]["shared_vs_median"], 2.0)
        self.assertEqual(by_wallet[W2]["shared_vs_median"], 1.0)
        self.assertIn("median candidate here shares 1", out["basis"]["note"])


if __name__ == "__main__":
    unittest.main()
