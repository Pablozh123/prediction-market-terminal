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


def _quoted(title, key, bid, ask, category="Economics", volume=100000.0):
    """Eine Zeile mit beidseitiger Quote, so wie beide Venues sie liefern."""

    return {
        "title": title, "market_key": key, "ticker": key,
        "yes_price": round((bid + ask) / 2, 6), "best_bid": bid, "best_ask": ask,
        "volume_24h": volume, "activity_volume": volume,
        "category": category, "url": "",
    }


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


class BasketEdgeTests(unittest.TestCase):
    """Die Luecke zwischen zwei Mitten ist keine Spanne, die man nehmen kann."""

    def _pair(self, pm_bid=0.61, pm_ask=0.63, ks_bid=0.67, ks_ask=0.69):
        pm = pd.DataFrame([_quoted("Will the Fed cut rates in September 2026?",
                                   "0xfed", pm_bid, pm_ask)])
        ks = pd.DataFrame([_quoted("Fed cuts rates at the September 2026 meeting?",
                                   "KXFED", ks_bid, ks_ask)])
        return cross_pairs.deep_cross_candidates(pm, ks, min_similarity=0.2).iloc[0]

    def test_the_executable_edge_is_bid_against_ask_not_mid_against_mid(self) -> None:
        row = self._pair()
        # Mitte gegen Mitte sind 6 Cent. Gekauft wird auf Polymarket zum
        # Brief 0.63 und die Gegenseite auf Kalshi zum Brief 1 - 0.67, macht
        # zusammen 0.96 fuer eine Auszahlung von 1.00: 4 Cent, nicht 6.
        self.assertAlmostEqual(abs(row["gap"]), 0.06, places=6)
        self.assertAlmostEqual(row["gross_edge_cents"], 4.0, places=4)
        self.assertEqual(row["edge_direction"], "buy Polymarket, sell Kalshi")

    def test_both_fee_curves_come_off_before_the_number_is_an_edge(self) -> None:
        row = self._pair()
        self.assertGreater(row["fee_band_cents"], 0.0)
        self.assertAlmostEqual(
            row["net_edge_cents"],
            round(row["gross_edge_cents"] - row["fee_band_cents"], 4), places=3)
        self.assertLess(row["net_edge_cents"], row["gross_edge_cents"])

    def test_a_gap_that_the_fees_eat_reports_a_negative_edge(self) -> None:
        # Zwei Cent Rohabstand liegen unter der Gebuehrenschwelle beider
        # Venues. Die Zeile darf nicht als Vorteil erscheinen.
        row = self._pair(ks_bid=0.64, ks_ask=0.66)
        self.assertAlmostEqual(row["gross_edge_cents"], 1.0, places=4)
        self.assertLess(row["net_edge_cents"], 0.0)

    def test_the_other_direction_is_checked_too(self) -> None:
        row = self._pair(pm_bid=0.71, pm_ask=0.73, ks_bid=0.61, ks_ask=0.63)
        self.assertEqual(row["edge_direction"], "buy Kalshi, sell Polymarket")
        self.assertAlmostEqual(row["gross_edge_cents"], 8.0, places=4)

    def test_without_a_two_sided_quote_the_edge_is_unknown_not_zero(self) -> None:
        pm = _pm_frame([("Will the Fed cut rates in September 2026?", "0xfed", 0.62, 100.0)])
        ks = _ks_frame([("Fed cuts rates at the September 2026 meeting?", "KXFED", 0.68, 100.0)])
        row = cross_pairs.deep_cross_candidates(pm, ks, min_similarity=0.2).iloc[0]
        self.assertIsNone(row["gross_edge_cents"])
        self.assertIsNone(row["net_edge_cents"])
        self.assertEqual(row["edge_direction"], "")

    def test_an_empty_side_of_the_book_is_not_a_quote_at_zero(self) -> None:
        pm = pd.DataFrame([_quoted("Will the Fed cut rates in September 2026?",
                                   "0xfed", 0.0, 0.63)])
        ks = pd.DataFrame([_quoted("Fed cuts rates at the September 2026 meeting?",
                                   "KXFED", 0.67, 0.69)])
        row = cross_pairs.deep_cross_candidates(pm, ks, min_similarity=0.2).iloc[0]
        # Nur eine Richtung bleibt uebrig: die, die das leere Polymarket-Geld
        # nicht braucht.
        self.assertEqual(row["edge_direction"], "buy Polymarket, sell Kalshi")
        self.assertAlmostEqual(row["gross_edge_cents"], 4.0, places=4)


class WithBasketEdgeTests(unittest.TestCase):
    """Die Streamlit-Seite paart ueber ``md.cross_venue_candidates``.

    Dieser Matcher kennt eine Suchanfrage und liefert nur die Mittelkurse.
    Ohne die Ergaenzung stand dort eine Mittelkurs-Luecke unter der
    Ueberschrift GAP, waehrend die Web-Oberflaeche daneben schon die
    ausfuehrbare und die Netto-Spanne zeigte.
    """

    def _paar(self):
        pm = pd.DataFrame([_quoted("Will the Fed cut rates in September 2026?", "0xfed", 0.61, 0.63)])
        ks = pd.DataFrame([_quoted("Fed cuts rates at the September 2026 meeting?", "KXFED", 0.67, 0.69)])
        kandidaten = pd.DataFrame([{
            "similarity": 0.8,
            "gap": pm.iloc[0]["yes_price"] - ks.iloc[0]["yes_price"],
            "abs_gap": abs(pm.iloc[0]["yes_price"] - ks.iloc[0]["yes_price"]),
            "polymarket_market_key": "0xfed", "kalshi_market_key": "KXFED",
            "polymarket_ticker": "", "kalshi_ticker": "KXFED",
            "polymarket_title": "Will the Fed cut rates in September 2026?",
            "kalshi_title": "Fed cuts rates at the September 2026 meeting?",
        }])
        return kandidaten, pm, ks

    def test_the_mid_gap_is_not_the_executable_edge(self) -> None:
        kandidaten, pm, ks = self._paar()
        row = cross_pairs.with_basket_edge(kandidaten, pm, ks).iloc[0]
        # 6 Cent zwischen den Mittelkursen, 4 davon ausfuehrbar (0.67 - 0.63),
        # und die Gebuehren beider Venues gehen davon noch ab.
        self.assertAlmostEqual(abs(row["gap"]) * 100, 6.0, places=4)
        self.assertAlmostEqual(row["gross_edge_cents"], 4.0, places=4)
        self.assertLess(row["net_edge_cents"], row["gross_edge_cents"])
        self.assertEqual(row["edge_direction"], "buy Polymarket, sell Kalshi")

    def test_a_pair_matched_only_by_title_still_finds_its_quotes(self) -> None:
        kandidaten, pm, ks = self._paar()
        kandidaten = kandidaten.assign(polymarket_market_key="", kalshi_market_key="", kalshi_ticker="")
        row = cross_pairs.with_basket_edge(kandidaten, pm, ks).iloc[0]
        self.assertAlmostEqual(row["gross_edge_cents"], 4.0, places=4)

    def test_a_pair_without_quotes_carries_none_not_zero(self) -> None:
        kandidaten, pm, ks = self._paar()
        pm = pm.drop(columns=["best_bid", "best_ask"])
        row = cross_pairs.with_basket_edge(kandidaten, pm, ks).iloc[0]
        self.assertIsNone(row["gross_edge_cents"])
        self.assertIsNone(row["net_edge_cents"])
        self.assertEqual(row["edge_direction"], "")

    def test_an_unknown_market_is_not_priced_from_another_row(self) -> None:
        kandidaten, pm, ks = self._paar()
        row = cross_pairs.with_basket_edge(kandidaten, pm.iloc[0:0], ks).iloc[0]
        self.assertIsNone(row["net_edge_cents"])

    def test_an_empty_candidate_table_passes_through(self) -> None:
        self.assertTrue(cross_pairs.with_basket_edge(pd.DataFrame(), pd.DataFrame(), pd.DataFrame()).empty)


if __name__ == "__main__":
    unittest.main()
