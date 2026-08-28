"""app/wallet_book.py — the flagged wallet's book against the flagged flow.

The case that motivated it: a wallet holding a large NO position bought YES;
the risk card said "YES buys", the copy desk later showed a merge. The card
must say "net NO — the YES buys work against a NO book" instead of leaving
that to the reader.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from app import wallet_book as wb
from src import prediction_markets as md

WALLET = "0x" + "a" * 40
MARKET = "0x" + "b" * 64


def _pos(outcome: str, size: float, avg: float = 0.5, cur: float = 0.5, cid: str = MARKET) -> dict:
    return {"outcome": outcome, "size": size, "avgPrice": avg, "curPrice": cur, "currentValue": size * cur, "conditionId": cid}


class SettledLeftoverTests(unittest.TestCase):
    """Aufgeloeste, nie eingeloeste Anteile sind kein Buch.

    Echte Zeile der Referenz-Wallet aus /positions (2026-08-28): 228.1766
    Anteile NO in "Will Procter & Gamble say 'Fiscal' 10+ times during
    earnings call?", curPrice 0, currentValue 0, endDate 2026-07-29. Die
    Karte las daraus ein Netto-NO-Buch und beschrieb jeden YES-Kauf als
    Absicherung gegen eine Position, die es nicht mehr gibt.
    """

    def test_dead_side_is_not_a_book(self) -> None:
        book = wb.summarize_book([_pos("No", 228.1766, avg=0.0438, cur=0.0)])
        self.assertEqual(book["no_shares"], 0)
        self.assertEqual(book["net"], "none")
        self.assertAlmostEqual(book["settled_shares"], 228.18, places=2)
        self.assertEqual(book["settled_positions"], 1)

    def test_live_side_survives_next_to_a_dead_one(self) -> None:
        book = wb.summarize_book([_pos("Yes", 400, cur=0.62), _pos("No", 5000, cur=0.0)])
        self.assertEqual(book["yes_shares"], 400)
        self.assertEqual(book["no_shares"], 0)
        self.assertEqual(book["net"], "YES")
        self.assertEqual(book["settled_shares"], 5000)

    def test_relation_names_the_leftover_instead_of_a_hedge(self) -> None:
        book = wb.summarize_book([_pos("No", 228.1766, avg=0.0438, cur=0.0)])
        rel = wb.relate_flow_to_book("YES BUYS", book)
        self.assertEqual(rel["relation"], "new_bet")
        self.assertIn("settled position left unredeemed", rel["text"])
        self.assertNotIn("work against a NO book", rel["text"])

    def test_row_without_a_price_stays_unknown_not_settled(self) -> None:
        book = wb.summarize_book([{"outcome": "Yes", "size": 10}])
        self.assertEqual(book["settled_positions"], 0)
        self.assertEqual(book["unpriced_positions"], 1)
        self.assertEqual(book["unpriced_shares"], 10)
        # Und auch keine Seite: ohne Preis ist nicht lesbar, ob die Zeile noch
        # laeuft, und 10 YES zu behaupten waere dieselbe Erfindung wie 10
        # abgerechnete Anteile.
        self.assertEqual(book["yes_shares"], 0)


class UnpricedRowTests(unittest.TestCase):
    """Ein fehlender Preis ist keine gemessene Null.

    Dieselbe Verwechslung, die PR #119 in src/prediction_markets.py behoben
    hat, stand hier noch: ``_num`` macht aus ``curPrice: null`` eine 0.0, und
    die Null heisst in diesem Feed "gegen die Wallet aufgeloest". Die alte
    Abfrage sah nur den fehlenden Schluessel; eine vorhandene, leere Zahl lief
    voll in ``settled_shares``. Geprueft wird gegen dieselbe Regel, die die
    Wallet-Seite liest: ``md.position_price_state``.
    """

    def test_null_price_is_unpriced_not_settled(self) -> None:
        book = wb.summarize_book([
            {"outcome": "No", "size": 228.1766, "avgPrice": 0.0438, "curPrice": None, "currentValue": None},
        ])
        self.assertEqual(book["settled_positions"], 0)
        self.assertEqual(book["settled_shares"], 0)
        self.assertEqual(book["unpriced_positions"], 1)
        self.assertAlmostEqual(book["unpriced_shares"], 228.18, places=2)
        self.assertEqual(book["no_shares"], 0)
        self.assertEqual(book["net"], "none")

    def test_nan_price_is_unpriced_too(self) -> None:
        book = wb.summarize_book([_pos("No", 500, cur=float("nan"))])
        self.assertEqual(book["unpriced_positions"], 1)
        self.assertEqual(book["settled_positions"], 0)

    def test_measured_zero_is_still_a_settled_loss(self) -> None:
        book = wb.summarize_book([_pos("No", 500, cur=0.0)])
        self.assertEqual(book["settled_positions"], 1)
        self.assertEqual(book["settled_shares"], 500)
        self.assertEqual(book["unpriced_positions"], 0)

    def test_value_without_a_price_still_counts_as_a_book(self) -> None:
        # Preis fehlt, Geld steht da: die Zeile laeuft, nur der Kurs fehlt.
        book = wb.summarize_book([
            {"outcome": "Yes", "size": 200, "avgPrice": 0.5, "curPrice": None, "currentValue": 120.0},
        ])
        self.assertEqual(book["yes_shares"], 200)
        self.assertEqual(book["yes_value"], 120.0)
        self.assertEqual(book["unpriced_positions"], 0)

    def test_second_spelling_survives_a_null_first_one(self) -> None:
        book = wb.summarize_book([
            {"outcome": "No", "size": 100, "curPrice": None, "current_price": 0.62, "currentValue": None, "value": 62.0},
        ])
        self.assertEqual(book["no_shares"], 100)
        self.assertEqual(book["no_value"], 62.0)
        self.assertEqual(book["unpriced_positions"], 0)

    def test_relation_says_unpriced_instead_of_flat(self) -> None:
        book = wb.summarize_book([{"outcome": "No", "size": 12000, "curPrice": None}])
        rel = wb.relate_flow_to_book("YES buys", book)
        self.assertEqual(rel["relation"], "unpriced")
        self.assertIn("12.0k shares in rows the feed did not price", rel["text"])
        self.assertNotIn("no open position left", rel["text"])

    def test_unpriced_shares_are_named_next_to_a_live_book(self) -> None:
        book = wb.summarize_book([_pos("No", 12000), {"outcome": "Yes", "size": 300, "curPrice": None}])
        rel = wb.relate_flow_to_book("NO buys", book)
        self.assertEqual(rel["relation"], "adds")
        self.assertIn("holds 0 YES / 12.0k NO now", rel["text"])
        self.assertIn("300 shares in rows the feed did not price", rel["text"])

    def test_both_leftovers_are_named_in_one_line(self) -> None:
        book = wb.summarize_book([_pos("No", 400, cur=0.0), {"outcome": "Yes", "size": 300, "curPrice": None}])
        rel = wb.relate_flow_to_book("YES buys", book)
        self.assertEqual(rel["relation"], "unpriced")
        self.assertIn("400 shares of a settled position left unredeemed", rel["text"])
        self.assertIn("300 shares in rows the feed did not price", rel["text"])


class SummarizeBookTests(unittest.TestCase):
    def test_sums_each_side_and_reads_the_net(self) -> None:
        book = wb.summarize_book([_pos("Yes", 100, 0.6), _pos("No", 12000, 0.4), _pos("No", 500, 0.42)])
        self.assertEqual(book["yes_shares"], 100)
        self.assertEqual(book["no_shares"], 12500)
        self.assertEqual(book["net"], "NO")
        self.assertEqual(book["net_shares"], 12400)
        self.assertAlmostEqual(book["no_avg"], (12000 * 0.4 + 500 * 0.42) / 12500, places=4)

    def test_balanced_within_tolerance_and_empty(self) -> None:
        self.assertEqual(wb.summarize_book([_pos("Yes", 1000), _pos("No", 950)])["net"], "balanced")
        self.assertEqual(wb.summarize_book([])["net"], "none")
        # Zero-size rows and unknown outcomes do not count as a side.
        book = wb.summarize_book([_pos("Yes", 0), _pos("Maybe", 10, cur=0.3)])
        self.assertEqual(book["net"], "none")
        self.assertEqual(book["other_outcomes"], 1)


class RelateFlowTests(unittest.TestCase):
    def test_yes_buys_against_a_no_book_are_a_hedge_not_a_bet(self) -> None:
        book = wb.summarize_book([_pos("No", 12000)])
        rel = wb.relate_flow_to_book("YES buys", book)
        self.assertEqual(rel["relation"], "reduces")
        self.assertIn("net NO", rel["text"])
        self.assertIn("not a new YES bet", rel["text"])

    def test_buys_on_the_side_held_add_to_the_book(self) -> None:
        rel = wb.relate_flow_to_book("NO buys", wb.summarize_book([_pos("No", 12000)]))
        self.assertEqual(rel["relation"], "adds")

    def test_sells_of_the_held_side_are_an_exit(self) -> None:
        rel = wb.relate_flow_to_book("NO sells", wb.summarize_book([_pos("No", 3000)]))
        self.assertEqual(rel["relation"], "exit")

    def test_empty_book_says_not_held(self) -> None:
        rel = wb.relate_flow_to_book("YES buys", wb.summarize_book([]))
        self.assertEqual(rel["relation"], "new_bet")
        self.assertIn("no open position", rel["text"])

    def test_balanced_book_is_a_hedge(self) -> None:
        rel = wb.relate_flow_to_book("YES buys", wb.summarize_book([_pos("Yes", 1000), _pos("No", 1000)]))
        self.assertEqual(rel["relation"], "hedge")

    def test_unreadable_side_is_unknown_but_still_shows_the_holdings(self) -> None:
        rel = wb.relate_flow_to_book("", wb.summarize_book([_pos("No", 10)]))
        self.assertEqual(rel["relation"], "unknown")
        self.assertIn("holds 0 YES / 10 NO", rel["text"])


class WalletBookTests(unittest.TestCase):
    def test_reads_positions_and_filters_to_the_market(self) -> None:
        rows = [_pos("No", 5000), _pos("Yes", 700, cid="0x" + "c" * 64)]
        with patch("app.wallet_book.md._get_json", return_value=rows) as get:
            book = wb.wallet_book(WALLET.upper().replace("0X", "0x"), MARKET, "YES buys")
        self.assertTrue(book["read"])
        self.assertEqual(book["positions"], 1)
        self.assertEqual(book["net"], "NO")
        self.assertEqual(book["relation"], "reduces")
        self.assertEqual(book["wallet"], WALLET)
        params = get.call_args.kwargs["params"]
        self.assertEqual(params["user"], WALLET)
        self.assertEqual(params["market"], MARKET)

    def test_unpriced_count_reaches_the_card(self) -> None:
        rows = [{"outcome": "No", "size": 5000, "avgPrice": 0.4, "curPrice": None, "conditionId": MARKET}]
        with patch("app.wallet_book.md._get_json", return_value=rows):
            book = wb.wallet_book(WALLET, MARKET, "YES buys")
        self.assertEqual(book["unpriced_positions"], 1)
        self.assertEqual(book["unpriced_shares"], 5000)
        self.assertEqual(book["settled_positions"], 0)
        self.assertEqual(book["relation"], "unpriced")
        self.assertIn("did not price", book["text"])

    def test_network_failure_is_reported_not_read(self) -> None:
        with patch("app.wallet_book.md._get_json", side_effect=md.MarketDataError("down")):
            book = wb.wallet_book(WALLET, MARKET, "YES buys")
        self.assertFalse(book["read"])
        self.assertIn("down", book["error"])
        self.assertNotIn("net", book)

    def test_bad_inputs_read_as_empty(self) -> None:
        self.assertEqual(wb.fetch_market_positions("not-a-wallet", MARKET), [])
        self.assertEqual(wb.fetch_market_positions(WALLET, ""), [])

    def test_market_books_dedups_caps_and_reports_dropped(self) -> None:
        with patch("app.wallet_book.md._get_json", return_value=[]):
            out = wb.market_books(MARKET, [WALLET, WALLET, "0x" + "d" * 40, "junk"], "NO buys", max_wallets=1)
        self.assertEqual(len(out["wallets"]), 1)
        self.assertEqual(out["dropped"], 1)
        self.assertEqual(out["wallets"][0]["relation"], "new_bet")


if __name__ == "__main__":
    unittest.main()
