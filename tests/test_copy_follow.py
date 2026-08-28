"""Tests for app/copy_follow.py — which wallets count as followed.

The set this module returns decides which rows the UI marks as followed and
which the daemon acts on, so the interesting cases are the ones where a wallet
should fall out: inactive, malformed, or differing only in case.
"""

from __future__ import annotations

import unittest

import pandas as pd

from app import copy_follow as cf

WALLET_A = "0x" + "a" * 40
WALLET_B = "0x" + "b" * 40


class ActiveWalletSetTests(unittest.TestCase):
    def test_only_active_rows_count(self) -> None:
        traders = pd.DataFrame([
            {"wallet": WALLET_A, "active": True},
            {"wallet": WALLET_B, "active": False},
        ])
        self.assertEqual(cf.active_wallet_set(traders), {WALLET_A})

    def test_addresses_are_matched_case_insensitively(self) -> None:
        traders = pd.DataFrame([{"wallet": WALLET_A.upper().replace("0X", "0x"), "active": True}])
        self.assertEqual(cf.active_wallet_set(traders), {WALLET_A})

    def test_rows_that_are_not_wallets_are_dropped(self) -> None:
        traders = pd.DataFrame([
            {"wallet": "not-an-address", "active": True},
            {"wallet": "", "active": True},
            {"wallet": WALLET_A, "active": True},
        ])
        self.assertEqual(cf.active_wallet_set(traders), {WALLET_A})

    def test_missing_active_column_follows_nobody(self) -> None:
        # Absent means unknown, and an unknown follow flag must not act.
        traders = pd.DataFrame([{"wallet": WALLET_A}])
        self.assertEqual(cf.active_wallet_set(traders), set())

    def test_empty_and_none_are_empty_sets(self) -> None:
        self.assertEqual(cf.active_wallet_set(None), set())
        self.assertEqual(cf.active_wallet_set(pd.DataFrame()), set())
        self.assertEqual(cf.active_wallet_set(pd.DataFrame([{"x": 1}])), set())


class StatsByWalletTests(unittest.TestCase):
    def test_indexes_rows_by_lowercased_wallet(self) -> None:
        stats = pd.DataFrame([
            {"wallet": WALLET_A.upper().replace("0X", "0x"), "pnl": 10.0},
            {"wallet": WALLET_B, "pnl": -5.0},
        ])
        by_wallet = cf.stats_by_wallet(stats)
        self.assertEqual(set(by_wallet), {WALLET_A, WALLET_B})
        self.assertEqual(by_wallet[WALLET_A]["pnl"], 10.0)

    def test_empty_inputs_give_an_empty_mapping(self) -> None:
        self.assertEqual(cf.stats_by_wallet(None), {})
        self.assertEqual(cf.stats_by_wallet(pd.DataFrame()), {})
        self.assertEqual(cf.stats_by_wallet(pd.DataFrame([{"x": 1}])), {})


class StatusLabelTests(unittest.TestCase):
    def test_labels_only_members_of_the_set(self) -> None:
        self.assertEqual(cf.status_label(WALLET_A, {WALLET_A}), "Following")
        self.assertEqual(cf.status_label(WALLET_B, {WALLET_A}), "")
        self.assertEqual(cf.status_label(None, {WALLET_A}), "")

    def test_case_does_not_hide_a_followed_wallet(self) -> None:
        self.assertEqual(cf.status_label(WALLET_A.upper().replace("0X", "0x"), {WALLET_A}), "Following")


class PnlSplitTests(unittest.TestCase):
    """Ein Prozentwert, der Gebuchtes und Bewertetes vermengt, sagt nichts.

    Das Zahlenbeispiel, an dem der Fehler haengt: 1.000 Dollar eingezahlt,
    eine Kopie ist aufgeloest und hat 120 Dollar gekostet, eine zweite ist
    offen und steht 300 Dollar ueber ihrem Einstand. Die Schlagzeile las
    daraus "+180 Dollar, +18,00 %". Gebucht ist davon nichts: der Tisch hat
    120 Dollar verloren, und die 300 Dollar sind eine Bewertung von
    Positionen, die noch nicht entschieden sind (im Standardpfad zum zuletzt
    gedruckten Preis der Quelle, nicht zu einem Marktkurs).
    """

    def test_the_headline_splits_into_settled_and_marked(self) -> None:
        split = cf.pnl_split(contributions=1000.0, realized_pnl=-120.0,
                             unrealized_pnl=300.0, equity=1180.0)
        self.assertAlmostEqual(split["settled_pnl"], -120.0)
        self.assertAlmostEqual(split["open_pnl"], 300.0)
        self.assertAlmostEqual(split["total_pnl"], 180.0)
        self.assertAlmostEqual(split["settled_pct"], -12.0)
        self.assertAlmostEqual(split["open_pct"], 30.0)
        self.assertAlmostEqual(split["total_pct"], 18.0)
        # Die Haelften addieren sich zur Schlagzeile, sonst ist die
        # Aufteilung keine Aufteilung.
        self.assertAlmostEqual(split["settled_pct"] + split["open_pct"], split["total_pct"])
        self.assertTrue(split["reconciles"])

    def test_books_that_do_not_add_up_say_so(self) -> None:
        # Equity minus Einzahlungen muss gebucht plus bewertet ergeben. Tut
        # es das nicht, ist die Zerlegung falsch und darf nicht als
        # Zerlegung auftreten.
        split = cf.pnl_split(contributions=1000.0, realized_pnl=-120.0,
                             unrealized_pnl=300.0, equity=1500.0)
        self.assertFalse(split["reconciles"])
        self.assertAlmostEqual(split["residual"], 320.0)

    def test_without_equity_the_total_is_the_sum_of_the_halves(self) -> None:
        split = cf.pnl_split(contributions=500.0, realized_pnl=25.0, unrealized_pnl=-5.0)
        self.assertAlmostEqual(split["total_pnl"], 20.0)
        self.assertAlmostEqual(split["total_pct"], 4.0)
        self.assertTrue(split["reconciles"])

    def test_no_capital_means_no_percentage_instead_of_zero(self) -> None:
        # Der Nenner war 0 und das Ergebnis stand als "+0,00 %" da: eine
        # gemessene Null, wo nichts gemessen wurde.
        split = cf.pnl_split(contributions=0.0, realized_pnl=0.0, unrealized_pnl=0.0)
        self.assertIsNone(split["total_pct"])
        self.assertIsNone(split["settled_pct"])
        self.assertIsNone(split["open_pct"])

    def test_both_halves_share_the_denominator(self) -> None:
        # Zaehler ueber die aufgeloesten Positionen und Nenner ueber alle war
        # der wiederkehrende Fehler. Hier ist der Nenner fuer beide Haelften
        # dieselbe Groesse (das eingezahlte Kapital), und genau deshalb
        # addieren sich die beiden Prozentwerte.
        split = cf.pnl_split(contributions=2000.0, realized_pnl=100.0, unrealized_pnl=100.0)
        self.assertAlmostEqual(split["settled_pct"], 5.0)
        self.assertAlmostEqual(split["open_pct"], 5.0)
        self.assertAlmostEqual(split["total_pct"], 10.0)
        self.assertEqual(split["denominator"], "contributions")


class MirrorCoverageTests(unittest.TestCase):
    """Zaehler und Nenner ueber derselben Menge.

    Das Zahlenbeispiel: 100 Orderzeilen, davon 40 als Baseline nur
    beobachtet, 30 kopiert und inzwischen aufgeloest, 20 kopiert und offen,
    10 uebersprungen. Die Kachel las "20 / 100", weil der Zaehler nur
    ``copied`` zaehlte, waehrend der Nenner jede Zeile mitnahm, auch die
    beobachteten. Gespiegelt wurden 50 von 60 Zeilen, ueber die ueberhaupt
    zu entscheiden war.
    """

    def test_the_denominator_covers_the_same_set_as_the_numerator(self) -> None:
        cov = cf.mirror_coverage(copied=20, settled=30, skipped=10, observed=40)
        self.assertEqual(cov["mirrored"], 50)
        self.assertEqual(cov["actionable"], 60)
        self.assertEqual(cov["observed"], 40)
        self.assertAlmostEqual(cov["coverage_pct"], 50 / 60 * 100)

    def test_a_settled_copy_does_not_leave_the_numerator(self) -> None:
        # Eine kopierte Order wechselt beim Aufloesen den Status von copied
        # auf settled. Vorher fiel sie damit aus dem Zaehler und blieb im
        # Nenner: je laenger der Tisch laeuft, desto schlechter sah er aus.
        vorher = cf.mirror_coverage(copied=50, settled=0, skipped=10, observed=40)
        nachher = cf.mirror_coverage(copied=20, settled=30, skipped=10, observed=40)
        self.assertAlmostEqual(vorher["coverage_pct"], nachher["coverage_pct"])

    def test_nothing_actionable_yet_is_not_a_hundred_percent(self) -> None:
        cov = cf.mirror_coverage(copied=0, settled=0, skipped=0, observed=40)
        self.assertIsNone(cov["coverage_pct"])
        self.assertEqual(cov["actionable"], 0)


class SafeKeyTests(unittest.TestCase):
    def test_joins_parts_and_replaces_everything_unsafe(self) -> None:
        # Streamlit widget keys must survive as identifiers.
        self.assertEqual(cf.safe_key("copy", "0xAb-1", "yes/no"), "copy_0xAb_1_yes_no")

    def test_is_capped_so_a_long_title_cannot_blow_the_key(self) -> None:
        key = cf.safe_key("x" * 500)
        self.assertEqual(len(key), 90)
        self.assertEqual(cf.safe_key("x" * 500, limit=10), "x" * 10)

    def test_none_parts_become_empty_segments(self) -> None:
        self.assertEqual(cf.safe_key("a", None, "b"), "a__b")


if __name__ == "__main__":
    unittest.main()
