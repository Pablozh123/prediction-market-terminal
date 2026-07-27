"""Tests for the streaming ledger aggregator."""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

_spec = importlib.util.spec_from_file_location(
    "full_wallet_ledger", REPO_ROOT / "scripts" / "full_wallet_ledger.py"
)
fwl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fwl)

WALLET = "0x204f72f35326db932158cba6adff0b9a1da95e14"
OTHER = "0x1111111111111111111111111111111111111111"


def row(frm: str, to: str, usdc: float, block: int = 1000, ts: int = 1_754_000_000,
        tx: str = "0xabc") -> dict:
    return {"from": frm, "to": to, "value": str(int(usdc * 10 ** 6)), "tokenDecimal": "6",
            "blockNumber": str(block), "timeStamp": str(ts), "hash": tx}


class LedgerTests(unittest.TestCase):
    def test_tracks_both_directions(self) -> None:
        ledger = fwl.Ledger()
        ledger.add(WALLET, row(OTHER, WALLET, 1000.0))
        ledger.add(WALLET, row(WALLET, OTHER, 250.0, tx="0xdef"))
        self.assertAlmostEqual(ledger.total_in, 1000.0)
        self.assertAlmostEqual(ledger.total_out, 250.0)
        self.assertEqual(ledger.rows, 2)

    def test_ignores_transfers_not_touching_the_wallet(self) -> None:
        ledger = fwl.Ledger()
        ledger.add(WALLET, row(OTHER, "0x2222222222222222222222222222222222222222", 500.0))
        self.assertEqual(ledger.rows, 0)

    def test_aggregates_per_counterparty_and_direction(self) -> None:
        ledger = fwl.Ledger()
        ledger.add(WALLET, row(OTHER, WALLET, 10.0, block=5, tx="0x1"))
        ledger.add(WALLET, row(OTHER, WALLET, 30.0, block=9, tx="0x2"))
        entry = ledger.by_counterparty[(OTHER, "in")]
        self.assertAlmostEqual(entry["amount"], 40.0)
        self.assertEqual(entry["count"], 2)
        self.assertEqual(entry["first_block"], 5)
        self.assertEqual(entry["last_block"], 9)

    def test_large_transfers_are_kept_row_by_row(self) -> None:
        ledger = fwl.Ledger()
        ledger.add(WALLET, row(OTHER, WALLET, 9_999.0, tx="0x1"))
        ledger.add(WALLET, row(OTHER, WALLET, 25_000.0, tx="0x2"))
        self.assertEqual(len(ledger.large), 1)
        self.assertAlmostEqual(ledger.large[0]["amount"], 25_000.0)

    def test_monthly_buckets_use_the_transfer_timestamp(self) -> None:
        ledger = fwl.Ledger()
        ledger.add(WALLET, row(OTHER, WALLET, 100.0, ts=1_754_006_400))   # 2025-08-01 UTC
        ledger.add(WALLET, row(WALLET, OTHER, 40.0, ts=1_756_684_800, tx="0x2"))  # 2025-09-01
        self.assertAlmostEqual(ledger.by_month["2025-08"]["in"], 100.0)
        self.assertAlmostEqual(ledger.by_month["2025-09"]["out"], 40.0)

    def test_malformed_rows_are_skipped_not_counted(self) -> None:
        """A bad row must drop out rather than corrupt a running total."""
        ledger = fwl.Ledger()
        bad = row(OTHER, WALLET, 5.0)
        bad["value"] = "not a number"
        ledger.add(WALLET, bad)
        self.assertEqual(ledger.rows, 0)
        self.assertAlmostEqual(ledger.total_in, 0.0)

    def test_state_round_trip_preserves_totals(self) -> None:
        """Resume must not lose or double-count what an interrupted run collected."""
        ledger = fwl.Ledger()
        ledger.add(WALLET, row(OTHER, WALLET, 1234.5, block=7, tx="0x1"))
        ledger.add(WALLET, row(WALLET, OTHER, 34.5, block=8, tx="0x2"))
        restored = fwl.Ledger.from_state(json.loads(json.dumps(ledger.to_state())))
        self.assertAlmostEqual(restored.total_in, ledger.total_in)
        self.assertAlmostEqual(restored.total_out, ledger.total_out)
        self.assertEqual(restored.rows, ledger.rows)
        self.assertAlmostEqual(
            restored.by_counterparty[(OTHER, "in")]["amount"],
            ledger.by_counterparty[(OTHER, "in")]["amount"],
        )

    def test_empty_state_yields_empty_ledger(self) -> None:
        ledger = fwl.Ledger.from_state({})
        self.assertEqual(ledger.rows, 0)
        self.assertAlmostEqual(ledger.total_in, 0.0)


class ApiKeyTests(unittest.TestCase):
    def test_reads_key_from_env_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".env").write_text('ETHERSCAN_API_KEY="abc123"\n', encoding="utf-8")
            self.assertEqual(fwl.load_api_key(root), "abc123")

    def test_missing_env_file_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(fwl.load_api_key(Path(tmp)))


if __name__ == "__main__":
    unittest.main()
