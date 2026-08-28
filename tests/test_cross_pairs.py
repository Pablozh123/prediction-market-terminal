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


def _quoted(title, key, bid, ask, category="Economics", volume=100000.0, end=None):
    """Eine Zeile mit beidseitiger Quote, so wie beide Venues sie liefern."""

    row = {
        "title": title, "market_key": key, "ticker": key,
        "yes_price": round((bid + ask) / 2, 6), "best_bid": bid, "best_ask": ask,
        "volume_24h": volume, "activity_volume": volume,
        "category": category, "url": "",
    }
    if end is not None:
        row["end_time"] = end
    return row


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


class PairVerdictTests(unittest.TestCase):
    """Fragen die beiden Seiten ueberhaupt dasselbe?

    Der Matcher vergleicht Titel und ist blind fuer genau die Woerter, die
    die Frage tragen. Die drei Faelle hier sind die drei Arten, wie ein Paar
    aus lauter gemeinsamen Woertern besteht und trotzdem keins ist.
    """

    def _btc(self, pm_title, ks_title, pm=(0.61, 0.63), ks=(0.36, 0.38), **kw):
        pm_frame = pd.DataFrame([_quoted(pm_title, "0xbtc", pm[0], pm[1],
                                         category="Crypto", **kw)])
        ks_frame = pd.DataFrame([_quoted(ks_title, "KXBTC", ks[0], ks[1],
                                         category="Crypto", **kw)])
        return pm_frame, ks_frame

    def test_a_question_and_its_inversion_are_not_a_pair(self) -> None:
        # Vorher: Aehnlichkeit 0.78, brutto +23.0 Cent, netto +19.7 Cent unter
        # der Ueberschrift "buy Kalshi, sell Polymarket". Der Korb dahinter
        # ist YES auf Kalshi (BTC unter 120k) zu 0.38 plus NO auf Polymarket
        # (BTC nicht ueber 120k) zu 0.39: 0.77 fuer eine Auszahlung von 2.00
        # im einen und 0.00 im anderen Ausgang. Das ist keine Absicherung,
        # sondern dieselbe Wette zweimal, und 19.7 Cent sind keine Spanne,
        # sondern ein Vorzeichenfehler.
        pm, ks = self._btc("Will Bitcoin be above $120,000 on December 31, 2026?",
                           "Will Bitcoin be below $120,000 on December 31, 2026?")
        self.assertTrue(cross_pairs.deep_cross_candidates(pm, ks, min_similarity=0.2).empty)

    def test_the_rejected_pair_can_be_listed_but_never_priced(self) -> None:
        pm, ks = self._btc("Will Bitcoin be above $120,000 on December 31, 2026?",
                           "Will Bitcoin be below $120,000 on December 31, 2026?")
        row = cross_pairs.deep_cross_candidates(
            pm, ks, min_similarity=0.2, include_rejected=True).iloc[0]
        self.assertEqual(row["pair_verdict"], cross_pairs.PAIR_OPPOSED)
        self.assertIn("above against below", row["pair_reasons"])
        self.assertIsNone(row["gross_edge_cents"])
        self.assertIsNone(row["net_edge_cents"])
        self.assertEqual(row["edge_direction"], "")

    def test_two_strikes_of_the_same_event_are_two_questions(self) -> None:
        # Kalshi listet zwanzig Schwellen zu einem Ereignis, alle mit
        # demselben Titelkopf. Vorher paarte der Matcher die 120k-Frage mit
        # der 68.2k-Frage (Aehnlichkeit 0.73) und druckte +70.4 Cent netto.
        pm, ks = self._btc("Bitcoin price on August 19, 2026? $120,000 or above",
                           "Bitcoin price on August 19, 2026? $68,200 or above",
                           pm=(0.20, 0.22), ks=(0.94, 0.96))
        self.assertTrue(cross_pairs.deep_cross_candidates(pm, ks, min_similarity=0.2).empty)
        row = cross_pairs.deep_cross_candidates(
            pm, ks, min_similarity=0.2, include_rejected=True).iloc[0]
        self.assertEqual(row["pair_verdict"], cross_pairs.PAIR_DIFFERENT)
        self.assertIn("different thresholds", row["pair_reasons"])

    def test_the_same_words_in_two_months_are_two_questions(self) -> None:
        # September gegen Dezember: jedes Wort ausser dem Monat ist gleich,
        # der Matcher gab 0.72 und die Zeile stand mit +19.7 Cent netto da.
        pm = pd.DataFrame([_quoted("Will the Fed cut rates at the September 2026 meeting?",
                                   "0xfed", 0.61, 0.63, end="2026-09-17T18:00:00Z")])
        ks = pd.DataFrame([_quoted("Will the Fed cut rates at the December 2026 meeting?",
                                   "KXFED", 0.36, 0.38, end="2026-12-10T18:00:00Z")])
        self.assertTrue(cross_pairs.deep_cross_candidates(pm, ks, min_similarity=0.2).empty)
        row = cross_pairs.deep_cross_candidates(
            pm, ks, min_similarity=0.2, include_rejected=True).iloc[0]
        self.assertEqual(row["pair_verdict"], cross_pairs.PAIR_DIFFERENT)
        self.assertIn("days apart", row["pair_reasons"])

    def test_two_close_times_of_the_same_event_stay_one_question(self) -> None:
        # Kalshi meldet close_time, Polymarket endDate. Ein paar Stunden
        # Unterschied sind dieselbe Frage und duerfen die Zeile nicht kosten.
        pm = pd.DataFrame([_quoted("Will the Fed cut rates at the September 2026 meeting?",
                                   "0xfed", 0.61, 0.63, end="2026-09-17T18:00:00Z")])
        ks = pd.DataFrame([_quoted("Fed cuts rates at the September 2026 meeting?",
                                   "KXFED", 0.67, 0.69, end="2026-09-17T22:00:00Z")])
        row = cross_pairs.deep_cross_candidates(pm, ks, min_similarity=0.2).iloc[0]
        self.assertEqual(row["pair_verdict"], cross_pairs.PAIR_UNVERIFIED)
        self.assertAlmostEqual(row["gross_edge_cents"], 4.0, places=4)

    def test_the_right_counterpart_wins_over_the_inverted_one(self) -> None:
        # Die Umkehrung teilt fast jedes Wort und gewinnt den
        # Aehnlichkeitsvergleich deshalb regelmaessig gegen die richtige
        # Entsprechung. Geprueft wird deshalb waehrend der Paarung, nicht
        # danach, sonst verliert der Markt sein gutes Paar an das falsche.
        pm = pd.DataFrame([_quoted("Will Bitcoin be above $120,000 on December 31, 2026?",
                                   "0xbtc", 0.61, 0.63, category="Crypto")])
        ks = pd.DataFrame([
            _quoted("Will Bitcoin be below $120,000 on December 31, 2026?",
                    "KXBTC-BELOW", 0.36, 0.38, category="Crypto"),
            _quoted("Bitcoin above $120,000 on December 31, 2026", "KXBTC-ABOVE",
                    0.67, 0.69, category="Crypto"),
        ])
        row = cross_pairs.deep_cross_candidates(pm, ks, min_similarity=0.2).iloc[0]
        self.assertEqual(row["kalshi_ticker"], "KXBTC-ABOVE")
        self.assertEqual(row["pair_verdict"], cross_pairs.PAIR_UNVERIFIED)

    def test_a_negation_on_one_side_only_is_an_inversion(self) -> None:
        self.assertEqual(
            cross_pairs.pair_verdict({"title": "Will the government shut down in October?"},
                                     {"title": "Will the government not shut down in October?"}
                                     )["verdict"],
            cross_pairs.PAIR_OPPOSED)

    def test_a_rewording_is_not_an_inversion(self) -> None:
        # "wins" gegen "winner" ist dieselbe Richtung in zwei Wortformen.
        self.assertEqual(cross_pairs.opposed_reasons("Who wins the race?", "Race winner?"), [])
        self.assertEqual(
            cross_pairs.pair_verdict({"title": "Will Sofia host Eurovision 2027?"},
                                     {"title": "Which city will host Eurovision in 2027? Sofia"}
                                     )["verdict"],
            cross_pairs.PAIR_UNVERIFIED)

    def test_a_side_that_names_both_directions_decides_nothing(self) -> None:
        self.assertEqual(cross_pairs.opposed_reasons(
            "Will the index close above 6000 or below 5000?",
            "Index above 6000 on Dec 31"), [])

    def test_a_missing_date_is_not_a_verdict(self) -> None:
        urteil = cross_pairs.pair_verdict(
            {"title": "Fed cuts rates in September", "end": "2026-09-17T18:00:00Z"},
            {"title": "Fed cuts rates in September", "end": None})
        self.assertIsNone(urteil["resolution_gap_days"])
        self.assertEqual(urteil["verdict"], cross_pairs.PAIR_UNVERIFIED)

    def test_a_bare_year_is_not_a_threshold(self) -> None:
        # Nur was ein Dollar- oder Prozentzeichen traegt, ist eine Schwelle.
        # Ein Vergleich ueber nackte Zahlen wuerde jedes Datum zum Befund
        # machen und damit fast jedes echte Paar wegwerfen.
        self.assertEqual(cross_pairs.strikes("Will Rubio win the 2028 election?"), set())
        self.assertEqual(cross_pairs.strikes("Bitcoin above $68.2k"), {("usd", 68200.0)})
        self.assertEqual(cross_pairs.strikes("$68,200 or above"), {("usd", 68200.0)})


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


def _book(bid_price, bid_size, ask_price, ask_size):
    """Ein Buch mit genau einer Stufe je Seite, Form wie ``md.get_*_orderbook``."""

    bids = pd.DataFrame([{"price": bid_price, "size": bid_size}]) if bid_price else pd.DataFrame()
    asks = pd.DataFrame([{"price": ask_price, "size": ask_size}]) if ask_price else pd.DataFrame()
    return bids, asks


class BookDepthTests(unittest.TestCase):
    """Eine Spanne fuer drei Kontrakte ist kein Geschaeft ueber hundert.

    ``src/cross_venue_gaps.py`` fragt die Buecher seit jeher ab, die
    Web-Paarung tat es nicht: dieselbe Zahl unter demselben Namen, einmal
    gemessen und einmal angenommen.
    """

    def _paar(self):
        pm = pd.DataFrame([dict(_quoted("Will the Fed cut rates at the September 2026 meeting?",
                                        "0xfed", 0.61, 0.63), yes_token_id="TOK")])
        ks = pd.DataFrame([_quoted("Fed cuts rates at the September 2026 meeting?",
                                   "KXFED", 0.67, 0.69)])
        return cross_pairs.deep_cross_candidates(pm, ks, min_similarity=0.2), pm, ks

    def test_without_a_book_the_size_is_an_assumption_and_says_so(self) -> None:
        cand, _, _ = self._paar()
        row = cand.iloc[0]
        self.assertAlmostEqual(row["net_edge_cents"], 1.2845, places=3)
        # 100 Stueck sind der Clip der Gebuehrenkurve, keine gemessene Tiefe.
        self.assertEqual(row["size_shares"], 100.0)
        self.assertFalse(bool(row["depth_checked"]))

    def test_the_shallower_side_sets_the_size(self) -> None:
        cand, pm, ks = self._paar()
        out = cross_pairs.with_book_depth(
            cand, pm, ks,
            pm_book=lambda token: _book(0.61, 500.0, 0.63, 8.0),
            ks_book=lambda ticker: _book(0.67, 3.0, 0.69, 400.0))
        row = out.iloc[0]
        # Dieselbe Spanne, aber fuer drei Kontrakte statt fuer hundert: aus
        # 1.28 Dollar Gewinn werden dreieinhalb Cent, und die Kalshi-Gebuehr
        # rundet auf den naechsten Cent der Order auf, was die Schwelle auf
        # dieser Groesse spuerbar anhebt.
        self.assertEqual(row["size_shares"], 3.0)
        self.assertTrue(bool(row["depth_checked"]))
        self.assertGreater(row["fee_band_cents"], 2.7155)

    def test_an_empty_book_is_no_size_not_a_free_edge(self) -> None:
        cand, pm, ks = self._paar()
        out = cross_pairs.with_book_depth(
            cand, pm, ks,
            pm_book=lambda token: _book(0.61, 500.0, 0.63, 8.0),
            ks_book=lambda ticker: (pd.DataFrame(), pd.DataFrame()))
        row = out.iloc[0]
        # Ohne den Abbruch bei Tiefe null faellt die Gebuehr je Stueck durch
        # die Division auf null, und die Zeile ohne Buch saehe besser aus als
        # jede Zeile mit einem.
        self.assertTrue(pd.isna(row["net_edge_cents"]))
        self.assertEqual(row["size_shares"], 0.0)
        self.assertTrue(bool(row["depth_checked"]))

    def test_the_touch_price_comes_from_the_book_not_from_the_stale_frame(self) -> None:
        cand, pm, ks = self._paar()
        out = cross_pairs.with_book_depth(
            cand, pm, ks,
            pm_book=lambda token: _book(0.61, 500.0, 0.68, 500.0),
            ks_book=lambda ticker: _book(0.67, 500.0, 0.69, 500.0))
        row = out.iloc[0]
        # Der Frame ist bis zu fuenf Minuten alt. Steht an der Spitze
        # inzwischen 0.68 statt 0.63, ist die Spanne weg und nicht bloss
        # kleiner: 0.67 Geld gegen 0.68 Brief.
        self.assertAlmostEqual(row["gross_edge_cents"], -1.0, places=4)
        self.assertLess(row["net_edge_cents"], 0.0)

    def test_nothing_happens_without_a_reader(self) -> None:
        cand, pm, ks = self._paar()
        out = cross_pairs.with_book_depth(cand, pm, ks)
        self.assertFalse(bool(out.iloc[0]["depth_checked"]))
        self.assertEqual(out.iloc[0]["size_shares"], 100.0)


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
