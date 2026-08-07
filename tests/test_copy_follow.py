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
