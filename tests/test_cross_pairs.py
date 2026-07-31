"""Tests fuer app/cross_pairs.py — Cross-Venue-Paarung ueber die volle Breite."""

from __future__ import annotations

import unittest

import pandas as pd

from app import cross_pairs


def _pm_frame(rows):
    return pd.DataFrame([
        {"title": t, "market_key": k, "ticker": "", "yes_price": y, "volume_24h": v, "activity_volume": v, "url": ""}
        for t, k, y, v in rows
    ])


def _ks_frame(rows):
    return pd.DataFrame([
        {"title": t, "market_key": k, "ticker": k, "yes_price": y, "volume_24h": v, "activity_volume": v, "url": ""}
        for t, k, y, v in rows
    ])


class DeepCrossCandidatesTests(unittest.TestCase):
    def test_matches_shared_token_titles_across_full_breadth(self) -> None:
        # Das passende Kalshi-Gegenstueck steht NICHT in den Top-Zeilen —
        # genau der Fall, den die Top-80-Kappung des Seitenmatchers verliert.
        pm = _pm_frame([("Will the Fed cut rates in September 2026?", "0xfed", 0.62, 1000.0)])
        ks_rows = [(f"yes Team {i},yes Team {i + 1}", f"PARLAY-{i}", 0.5, 99999.0) for i in range(90)]
        ks_rows.append(("Fed cuts rates at the September 2026 meeting?", "KXFED", 0.60, 10.0))
        ks = _ks_frame(ks_rows)
        out = cross_pairs.deep_cross_candidates(pm, ks, min_similarity=0.2)
        self.assertEqual(len(out), 1)
        row = out.iloc[0]
        self.assertEqual(row["kalshi_ticker"], "KXFED")
        self.assertAlmostEqual(row["abs_gap"], 0.02, places=6)
        self.assertGreaterEqual(row["similarity"], 0.2)

    def test_requires_two_shared_tokens(self) -> None:
        pm = _pm_frame([("Will bitcoin hit $1m?", "0xbtc", 0.1, 100.0)])
        ks = _ks_frame([("Government shutdown in October?", "KXSHUT", 0.3, 100.0)])
        out = cross_pairs.deep_cross_candidates(pm, ks, min_similarity=0.0)
        self.assertTrue(out.empty)

    def test_drops_rows_without_usable_price(self) -> None:
        pm = _pm_frame([("Fed cuts rates in September", "0xfed", None, 100.0)])
        ks = _ks_frame([("Fed cuts rates in September", "KXFED", 0.6, 100.0)])
        out = cross_pairs.deep_cross_candidates(pm, ks)
        self.assertTrue(out.empty)

    def test_empty_inputs(self) -> None:
        self.assertTrue(cross_pairs.deep_cross_candidates(pd.DataFrame(), pd.DataFrame()).empty)


if __name__ == "__main__":
    unittest.main()
