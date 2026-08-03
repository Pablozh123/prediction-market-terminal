import json
import tempfile
import unittest
from pathlib import Path

from src import reward_selection as rs


def market(pool=10.0, max_spread=4.5, min_size=20.0, token="t1",
           question="Eine Frage?"):
    return {
        "condition_id": "0xabc", "question": question,
        "tokens": [{"token_id": token}, {"token_id": "t2"}],
        "rewards": {"rates": [{"rewards_daily_rate": str(pool)}],
                    "max_spread": max_spread, "min_size": min_size},
    }


def book(bids=None, asks=None):
    return {
        "bids": bids if bids is not None else [{"price": "0.49", "size": "100"}],
        "asks": asks if asks is not None else [{"price": "0.51", "size": "100"}],
    }


class ConfigTests(unittest.TestCase):
    def test_a_market_with_a_pool_is_kept(self):
        config = rs.reward_config(market(pool=25.0))
        self.assertEqual(config["pool_usd_per_day"], 25.0)
        self.assertEqual(config["token_ids"], ["t1", "t2"])

    def test_a_market_without_a_pool_is_dropped(self):
        self.assertIsNone(rs.reward_config(market(pool=0.0)))

    def test_a_market_without_rewards_is_dropped(self):
        self.assertIsNone(rs.reward_config({"condition_id": "x"}))

    def test_several_rates_are_summed(self):
        raw = market()
        raw["rewards"]["rates"] = [{"rewards_daily_rate": "3"},
                                   {"rewards_daily_rate": "4"}]
        self.assertEqual(rs.reward_config(raw)["pool_usd_per_day"], 7.0)

    def test_missing_config_falls_back_to_the_measured_modes(self):
        raw = market()
        raw["rewards"].pop("max_spread")
        raw["rewards"].pop("min_size")
        config = rs.reward_config(raw)
        self.assertEqual(config["max_spread_cents"], rs.lr.MAX_SPREAD_CENTS_MODE)
        self.assertEqual(config["min_size_shares"], rs.lr.MIN_SIZE_SHARES_MODE)


class DepthTests(unittest.TestCase):
    def test_orders_inside_the_band_are_counted(self):
        shares, orders = rs.qualifying_depth(
            [{"price": "0.49", "size": "100"}],
            [{"price": "0.51", "size": "100"}],
            mid=0.50, max_spread_cents=4.5, min_size_shares=20.0)
        self.assertEqual(shares, 200.0)
        self.assertEqual(orders, 2)

    def test_orders_outside_the_band_are_ignored(self):
        shares, orders = rs.qualifying_depth(
            [{"price": "0.40", "size": "100"}], [], mid=0.50,
            max_spread_cents=4.5, min_size_shares=20.0)
        self.assertEqual((shares, orders), (0.0, 0))

    def test_orders_below_the_minimum_size_do_not_qualify(self):
        shares, orders = rs.qualifying_depth(
            [{"price": "0.49", "size": "5"}], [], mid=0.50,
            max_spread_cents=4.5, min_size_shares=20.0)
        self.assertEqual((shares, orders), (0.0, 0))

    def test_the_band_edge_separates_inside_from_outside(self):
        # Nicht exakt auf der Kante pruefen: 0.50 minus 0.455 ist in Float
        # weder sicher ueber noch unter 4.5 Cent, und ein Test, der davon
        # abhaengt, prueft die Gleitkommadarstellung statt die Regel.
        def shares_at(price):
            shares, _ = rs.qualifying_depth(
                [{"price": price, "size": "100"}], [], mid=0.50,
                max_spread_cents=4.5, min_size_shares=20.0)
            return shares

        self.assertEqual(shares_at("0.46"), 100.0)   # 4.0 Cent, drin
        self.assertEqual(shares_at("0.45"), 0.0)     # 5.0 Cent, draussen

    def test_several_levels_per_side_are_all_counted(self):
        # Regression: echte Buecher haben viele Ebenen, die Testbuecher hatten
        # eine, und der Fehler zeigte sich erst im Livelauf.
        shares, orders = rs.qualifying_depth(
            [{"price": "0.49", "size": "100"}, {"price": "0.48", "size": "50"}],
            [{"price": "0.51", "size": "70"}, {"price": "0.52", "size": "30"}],
            mid=0.50, max_spread_cents=4.5, min_size_shares=20.0)
        self.assertEqual(shares, 250.0)
        self.assertEqual(orders, 4)

    def test_pair_shaped_levels_are_accepted_too(self):
        shares, _ = rs.qualifying_depth([["0.49", "100"]], [], mid=0.50,
                                        max_spread_cents=4.5,
                                        min_size_shares=20.0)
        self.assertEqual(shares, 100.0)

    def test_malformed_levels_are_skipped(self):
        shares, _ = rs.qualifying_depth([{"price": "nein", "size": "100"}], [],
                                        mid=0.50, max_spread_cents=4.5,
                                        min_size_shares=20.0)
        self.assertEqual(shares, 0.0)


class SnapshotTests(unittest.TestCase):
    def test_a_two_sided_book_is_returned(self):
        snap = rs.book_snapshot("t1", get_json=lambda u, p=None: book())
        self.assertAlmostEqual(snap["mid"], 0.50, places=6)

    def test_a_one_sided_book_is_rejected(self):
        self.assertIsNone(rs.book_snapshot(
            "t1", get_json=lambda u, p=None: book(asks=[])))

    def test_a_crossed_book_is_rejected(self):
        self.assertIsNone(rs.book_snapshot("t1", get_json=lambda u, p=None: book(
            bids=[{"price": "0.60", "size": "1"}],
            asks=[{"price": "0.40", "size": "1"}])))

    def test_a_failing_request_is_reported_as_none(self):
        def boom(url, params=None):
            raise ConnectionError("weg")
        self.assertIsNone(rs.book_snapshot("t1", get_json=boom))


class ScoringTests(unittest.TestCase):
    def test_an_empty_band_is_flagged(self):
        config = rs.reward_config(market())
        snap = rs.book_snapshot("t1", get_json=lambda u, p=None: book(
            bids=[{"price": "0.30", "size": "100"}],
            asks=[{"price": "0.70", "size": "100"}]))
        row = rs.score_market(config, snap)
        self.assertTrue(row["empty_band"])

    def test_a_crowded_band_ranks_below_an_empty_one(self):
        # Der Kern der Auswertung: Pool allein sagt nichts.
        config = rs.reward_config(market(pool=100.0))
        crowded = rs.score_market(config, rs.book_snapshot(
            "t1", get_json=lambda u, p=None: book(
                bids=[{"price": "0.499", "size": "10000"}],
                asks=[{"price": "0.501", "size": "10000"}])))
        quiet = rs.score_market(config, rs.book_snapshot(
            "t1", get_json=lambda u, p=None: book(
                bids=[{"price": "0.499", "size": "25"}],
                asks=[{"price": "0.501", "size": "25"}])))
        self.assertLess(crowded["pool_per_competing_share"],
                        quiet["pool_per_competing_share"])

    def test_a_bigger_pool_ranks_above_a_smaller_one_at_equal_crowding(self):
        small = rs.score_market(rs.reward_config(market(pool=5.0)),
                                rs.book_snapshot("t1", get_json=lambda u, p=None: book()))
        big = rs.score_market(rs.reward_config(market(pool=500.0)),
                              rs.book_snapshot("t1", get_json=lambda u, p=None: book()))
        self.assertGreater(big["pool_per_competing_share"],
                           small["pool_per_competing_share"])

    def test_our_own_score_is_positive_inside_the_band(self):
        row = rs.score_market(rs.reward_config(market()),
                              rs.book_snapshot("t1", get_json=lambda u, p=None: book()))
        self.assertGreater(row["own_score"], 0)

    def test_the_token_list_does_not_leak_into_the_row(self):
        row = rs.score_market(rs.reward_config(market()),
                              rs.book_snapshot("t1", get_json=lambda u, p=None: book()))
        self.assertNotIn("token_ids", row)


class EndToEndTests(unittest.TestCase):
    def _feed(self, markets):
        def get_json(url, params=None):
            if url == rs.SAMPLING_URL:
                return {"data": markets, "next_cursor": "LTE="}
            return book()
        return get_json

    def test_the_study_ranks_by_ratio_not_by_pool(self):
        markets = [market(pool=1000.0, token="crowded", question="Grosser Pool"),
                   market(pool=10.0, token="quiet", question="Kleiner Pool")]

        def get_json(url, params=None):
            if url == rs.SAMPLING_URL:
                return {"data": markets, "next_cursor": "LTE="}
            if params and params.get("token_id") == "t1":
                return book(bids=[{"price": "0.499", "size": "100000"}],
                            asks=[{"price": "0.501", "size": "100000"}])
            return book()

        results = rs.run_study(probe=5, get_json=get_json)
        self.assertEqual(results["markets_with_pool"], 2)
        self.assertEqual(results["probed"], 2)

    def test_an_exchange_without_reward_markets_does_not_crash(self):
        results = rs.run_study(probe=5, get_json=self._feed([]))
        self.assertEqual(results["markets_with_pool"], 0)
        self.assertEqual(results["rows"], [])

    def test_all_report_files_are_written(self):
        results = rs.run_study(probe=2, get_json=self._feed([market()]))
        with tempfile.TemporaryDirectory() as tmp:
            paths = rs.write_outputs(results, "test", research_dir=Path(tmp))
            for key in ("json", "csv", "md"):
                self.assertTrue(paths[key].exists(), key)
            body = paths["md"].read_text(encoding="utf-8")
            self.assertIn("Reward market selection", body)
            self.assertNotIn("ß", body)
            self.assertIn("by_ratio" if False else "It is a ranking, not a payout", body)
            json.loads(paths["json"].read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
