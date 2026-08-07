"""Tests for the on-chain wallet ledger scanners.

These scripts reconstruct a wallet's complete transfer history from the block
explorer, which is the lane that gets around the 50-row cap on the venue's
closed-positions endpoint. Two properties carry the correctness of the result:

- A transfer must be booked in the right direction with the right decimals, and
  a row that does not involve the wallet must not be booked at all.
- The parallel scanner splits the block range into windows and merges them, so
  the merged tally has to equal what a single serial pass would have produced.
  A merge that loses a row or keeps the wrong block bound corrupts a ledger
  silently, which is exactly the failure a reconciliation is supposed to catch.
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))


def _laden(name: str):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / "scripts" / f"{name}.py")
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


erc1155 = _laden("scan_erc1155_ledger")
parallel = _laden("scan_wallet_ledger_parallel")

WALLET = "0x204f72f35326db932158cba6adff0b9a1da95e14"
GEGEN = "0x" + "b" * 40
FREMD = "0x" + "c" * 40
TOKEN = "0x" + "d" * 40


def transfer(*, an=WALLET, von=GEGEN, wert="2000000", block=100, ts=1_760_000_000,
             token_id="7", tx="0xaa", kind="erc1155", decimals="6"):
    """One explorer row. tokenValue has six decimals for conditional tokens."""
    row = {"from": von, "to": an, "blockNumber": str(block), "timeStamp": str(ts),
           "contractAddress": TOKEN, "tokenID": token_id, "hash": tx,
           "functionName": "redeemPositions(bytes32,uint256[])"}
    if kind == "erc1155":
        row["tokenValue"] = wert
    else:
        row["value"] = wert
        row["tokenDecimal"] = decimals
    return row


class Ledger1155Tests(unittest.TestCase):
    def test_direction_and_decimals(self) -> None:
        ledger = erc1155.Ledger1155()
        ledger.add(WALLET, transfer(an=WALLET, wert="2500000"))       # 2.5 shares in
        ledger.add(WALLET, transfer(an=GEGEN, von=WALLET, wert="1000000"))  # 1.0 out
        self.assertAlmostEqual(ledger.total_in, 2.5)
        self.assertAlmostEqual(ledger.total_out, 1.0)
        self.assertEqual(ledger.rows, 2)

    def test_a_row_that_does_not_touch_the_wallet_is_not_booked(self) -> None:
        ledger = erc1155.Ledger1155()
        ledger.add(WALLET, transfer(an=FREMD, von=GEGEN))
        self.assertEqual(ledger.rows, 0)
        self.assertAlmostEqual(ledger.total_in, 0.0)

    def test_malformed_rows_are_skipped_rather_than_raising(self) -> None:
        # The explorer occasionally returns a null value; one bad row must not
        # end a scan that has already cost thousands of requests.
        ledger = erc1155.Ledger1155()
        ledger.add(WALLET, {"from": GEGEN, "to": WALLET, "tokenValue": None})
        ledger.add(WALLET, {"from": GEGEN, "to": WALLET, "tokenValue": "x", "blockNumber": "1"})
        self.assertEqual(ledger.rows, 0)

    def test_counterparty_direction_and_token_are_one_key(self) -> None:
        ledger = erc1155.Ledger1155()
        ledger.add(WALLET, transfer(an=WALLET, block=10, ts=1_700_000_000))
        ledger.add(WALLET, transfer(an=WALLET, block=50, ts=1_700_000_500))
        entry = ledger.by_counterparty[(GEGEN, "in", TOKEN)]
        self.assertEqual(entry["count"], 2)
        self.assertEqual(entry["first_block"], 10)
        self.assertEqual(entry["last_block"], 50)

    def test_month_buckets_follow_the_timestamp(self) -> None:
        ledger = erc1155.Ledger1155()
        ledger.add(WALLET, transfer(ts=1_767_225_600))   # 2026-01
        ledger.add(WALLET, transfer(ts=1_769_904_000))   # 2026-02
        self.assertEqual(set(ledger.by_month), {"2026-01", "2026-02"})

    def test_large_transfers_are_captured_with_their_transaction(self) -> None:
        gross = str(int((erc1155.LARGE_SHARES + 1) * 1_000_000))
        ledger = erc1155.Ledger1155()
        ledger.add(WALLET, transfer(wert=gross, tx="0xbeef"))
        ledger.add(WALLET, transfer(wert="1000", tx="0xsmall"))
        self.assertEqual([e["tx"] for e in ledger.large], ["0xbeef"])

    def test_state_round_trip_preserves_the_tally(self) -> None:
        # The scan resumes from this state after an interruption.
        ledger = erc1155.Ledger1155()
        ledger.add(WALLET, transfer(wert="3000000"))
        ledger.add(WALLET, transfer(an=GEGEN, von=WALLET, wert="1000000"))
        wieder = erc1155.Ledger1155.from_state(ledger.to_state())
        self.assertAlmostEqual(wieder.total_in, ledger.total_in)
        self.assertAlmostEqual(wieder.total_out, ledger.total_out)
        self.assertEqual(wieder.rows, ledger.rows)
        self.assertEqual(wieder.by_counterparty[(GEGEN, "in", TOKEN)]["count"], 1)


class BucketTests(unittest.TestCase):
    def test_erc20_uses_the_token_decimals(self) -> None:
        bucket = parallel.Bucket()
        bucket.add(WALLET, transfer(kind="erc20", wert="1500000", decimals="6"), "erc20", 1e9)
        self.assertAlmostEqual(bucket.total_in, 1.5)

        achtzehn = parallel.Bucket()
        achtzehn.add(WALLET, transfer(kind="erc20", wert="2" + "0" * 18, decimals="18"), "erc20", 1e9)
        self.assertAlmostEqual(achtzehn.total_in, 2.0)

    def test_erc1155_is_always_six_decimals(self) -> None:
        bucket = parallel.Bucket()
        bucket.add(WALLET, transfer(wert="2500000"), "erc1155", 1e9)
        self.assertAlmostEqual(bucket.total_in, 2.5)

    def test_method_is_taken_without_its_signature(self) -> None:
        bucket = parallel.Bucket()
        bucket.add(WALLET, transfer(), "erc1155", 1e9)
        self.assertIn(("in", "redeemPositions"), bucket.by_method)


class MergeEqualsSerialTests(unittest.TestCase):
    """The point of the parallel scanner: windows merge to the serial answer."""

    ROWS = [
        transfer(block=10, ts=1_767_225_600, wert="1000000"),
        transfer(block=20, ts=1_767_225_700, wert="2000000", an=GEGEN, von=WALLET),
        transfer(block=30, ts=1_769_904_000, wert="4000000"),
        transfer(block=40, ts=1_769_904_100, wert="500000", an=GEGEN, von=WALLET),
        transfer(block=50, ts=1_769_904_200, wert="750000"),
    ]

    def _seriell(self) -> "parallel.Bucket":
        bucket = parallel.Bucket()
        for row in self.ROWS:
            bucket.add(WALLET, row, "erc1155", 1e9)
        return bucket

    def _fenster(self, schnitte: list[int]) -> "parallel.Bucket":
        gesamt = parallel.Bucket()
        for lo, hi in zip([0] + schnitte, schnitte + [10**9]):
            fenster = parallel.Bucket()
            for row in self.ROWS:
                if lo <= int(row["blockNumber"]) < hi:
                    fenster.add(WALLET, row, "erc1155", 1e9)
            gesamt.merge(fenster)
        return gesamt

    def test_totals_and_row_count_match(self) -> None:
        seriell, parallel_ = self._seriell(), self._fenster([25, 45])
        self.assertEqual(parallel_.rows, seriell.rows)
        self.assertAlmostEqual(parallel_.total_in, seriell.total_in)
        self.assertAlmostEqual(parallel_.total_out, seriell.total_out)

    def test_the_split_points_do_not_change_the_answer(self) -> None:
        seriell = self._seriell()
        for schnitte in ([25], [15, 35], [11, 21, 31, 41], [5, 45, 60]):
            with self.subTest(schnitte=schnitte):
                gemerged = self._fenster(schnitte)
                self.assertEqual(gemerged.rows, seriell.rows)
                self.assertAlmostEqual(gemerged.total_in, seriell.total_in)

    def test_block_bounds_survive_the_merge(self) -> None:
        # first_block must be the earliest across every window, not the first
        # window that happened to be merged.
        gemerged = self._fenster([25, 45])
        entry = gemerged.by_cp[(GEGEN, "in", TOKEN)]
        self.assertEqual(entry["first_block"], 10)
        self.assertEqual(entry["last_block"], 50)

    def test_month_buckets_and_counterparties_match(self) -> None:
        seriell, gemerged = self._seriell(), self._fenster([25, 45])
        self.assertEqual(set(gemerged.by_month), set(seriell.by_month))
        for month, werte in seriell.by_month.items():
            self.assertAlmostEqual(gemerged.by_month[month]["in"], werte["in"])
            self.assertAlmostEqual(gemerged.by_month[month]["out"], werte["out"])
        self.assertEqual(set(gemerged.by_cp), set(seriell.by_cp))

    def test_merging_an_empty_window_changes_nothing(self) -> None:
        bucket = self._seriell()
        vorher = (bucket.rows, bucket.total_in, bucket.total_out)
        bucket.merge(parallel.Bucket())
        self.assertEqual((bucket.rows, bucket.total_in, bucket.total_out), vorher)

    def test_incomplete_windows_are_carried_up(self) -> None:
        # A window that hit the page cap is reported, not silently dropped.
        gesamt, fenster = parallel.Bucket(), parallel.Bucket()
        fenster.incomplete.append(1234)
        gesamt.merge(fenster)
        self.assertEqual(gesamt.incomplete, [1234])


class BaseParamsTests(unittest.TestCase):
    def test_action_follows_the_token_standard(self) -> None:
        self.assertEqual(parallel.base_params(WALLET, "erc1155", None, "k")["action"], "token1155tx")
        self.assertEqual(parallel.base_params(WALLET, "erc20", None, "k")["action"], "tokentx")

    def test_a_token_filter_is_passed_through_and_omitted_when_absent(self) -> None:
        self.assertEqual(parallel.base_params(WALLET, "erc20", TOKEN, "k")["contractaddress"], TOKEN)
        self.assertNotIn("contractaddress", parallel.base_params(WALLET, "erc20", None, "k"))

    def test_ascending_order_because_the_scan_resumes_by_block(self) -> None:
        self.assertEqual(parallel.base_params(WALLET, "erc20", None, "k")["sort"], "asc")


class ApiKeyTests(unittest.TestCase):
    def test_no_key_is_reported_as_none_not_as_an_empty_string(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            for modul in (erc1155, parallel):
                with self.subTest(modul=modul.__name__):
                    self.assertIsNone(modul.load_api_key(Path(tmp)))

    def test_the_key_is_read_from_the_env_file_and_never_hardcoded(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / ".env").write_text("ETHERSCAN_API_KEY=abc123\n", encoding="utf-8")
            self.assertEqual(erc1155.load_api_key(Path(tmp)), "abc123")


if __name__ == "__main__":
    unittest.main()
