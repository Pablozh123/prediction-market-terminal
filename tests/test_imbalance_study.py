"""Tests for the book-imbalance study core functions."""

from __future__ import annotations

import json
import unittest

from src import imbalance_study as st


class WilsonTest(unittest.TestCase):
    def test_matches_playbook_reference_value(self) -> None:
        # 26 Treffer bei 28 Faellen -> Wilson lb95 ~ 77.4% (EDGES.md-Referenz)
        self.assertAlmostEqual(st.wilson_lb(26, 28), 0.774, places=3)

    def test_zero_n_is_zero(self) -> None:
        self.assertEqual(st.wilson_lb(0, 0), 0.0)


class ImbalanceTest(unittest.TestCase):
    def test_bid_share_of_top5_usd(self) -> None:
        bids = json.dumps([[0.60, 100], [0.59, 100]])   # 119 USD
        asks = json.dumps([[0.64, 100], [0.65, 100]])   # 129 USD
        self.assertAlmostEqual(
            st.imbalance_from_json(bids, asks), 119.0 / 248.0, places=6
        )

    def test_thin_books_are_filtered(self) -> None:
        bids = json.dumps([[0.60, 10]])
        asks = json.dumps([[0.64, 10]])
        self.assertIsNone(st.imbalance_from_json(bids, asks, min_total_usd=50.0))

    def test_dict_levels_are_supported(self) -> None:
        bids = json.dumps([{"price": "0.5", "size": "100"}])
        asks = json.dumps([{"price": "0.5", "size": "100"}])
        self.assertAlmostEqual(st.imbalance_from_json(bids, asks), 0.5, places=6)


class ForwardPairsTest(unittest.TestCase):
    def test_pairs_first_snapshot_in_window(self) -> None:
        series = [(0.0, 0.50, 0.9), (100.0, 0.52, 0.9), (320.0, 0.55, 0.1),
                  (900.0, 0.60, 0.5)]
        pairs = st.forward_pairs(series, horizon_s=300)
        # t=0 -> erster Snapshot >= 300s ist t=320 (im Fenster [300, 600]):
        # Drift = (0.55 - 0.50) * 100 = 5 Cents.
        self.assertEqual(pairs[0], (0.9, 5.0))
        # t=100 -> Ziel 400, naechster ist 900 > 2H-Fenster (700) -> kein Paar;
        # t=320 -> Ziel 620, 900 > 640? nein: Fenster [620, 960] -> Paar.
        self.assertEqual(len(pairs), 2)
        self.assertAlmostEqual(pairs[1][1], 5.0)

    def test_no_pair_without_forward_snapshot(self) -> None:
        self.assertEqual(st.forward_pairs([(0.0, 0.5, 0.5)], 300), [])


class BucketizeTest(unittest.TestCase):
    def test_direction_logic_and_neutral_bucket(self) -> None:
        pairs = (
            [(0.1, -1.0)] * 8 + [(0.1, 1.0)] * 2      # tiefes Bucket: 8/10 runter
            + [(0.9, 2.0)] * 9 + [(0.9, -2.0)] * 1    # hohes Bucket: 9/10 hoch
            + [(0.5, 3.0)] * 5                        # neutral: keine Richtung
        )
        rows = st.bucketize(pairs)
        low, neutral, high = rows[0], rows[2], rows[4]
        self.assertEqual(low["hit_rate"], 0.8)
        self.assertEqual(high["hit_rate"], 0.9)
        self.assertIsNone(neutral["hit_rate"])
        self.assertEqual(neutral["n"], 5)
        self.assertTrue(0 < low["wilson_lb95"] < low["hit_rate"])

    def test_hit_rate_ist_bedingt_auf_bewegung(self) -> None:
        pairs = [(0.1, -1.0)] * 4 + [(0.1, 0.0)] * 6  # 10 Paare, 4 bewegt
        low = st.bucketize(pairs)[0]
        self.assertEqual(low["n"], 10)
        self.assertEqual(low["moved"], 4)
        self.assertEqual(low["moved_share"], 0.4)
        self.assertEqual(low["hit_rate"], 1.0)  # alle bewegten gingen runter

    def test_empty_buckets_are_reported(self) -> None:
        rows = st.bucketize([])
        self.assertEqual(len(rows), 5)
        self.assertTrue(all(row["n"] == 0 for row in rows))


if __name__ == "__main__":
    unittest.main()
