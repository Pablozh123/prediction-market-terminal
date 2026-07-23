"""Tests for the Etherscan-backed flow scanner's parsing and pagination."""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

# The script lives under scripts/ and is not a package module; load it directly.
_spec = importlib.util.spec_from_file_location(
    "fetch_wallet_flows_api", REPO_ROOT / "scripts" / "fetch_wallet_flows_api.py"
)
fwa = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fwa)

from app import onchain_flows as ocf  # noqa: E402

WALLET = "0x204f72f35326db932158cba6adff0b9a1da95e14"


def row(block: int, frm: str, to: str, value_usdc: float, tx: str) -> dict:
    return {
        "blockNumber": str(block), "timeStamp": str(1_754_000_000 + block),
        "hash": tx, "from": frm, "to": to,
        "value": str(int(value_usdc * 10 ** 6)), "tokenDecimal": "6",
        "contractAddress": ocf.USDC_CONTRACTS[0],
    }


class FakeApi:
    """Serves tokentx pages, capped at `cap` rows regardless of requested offset."""

    def __init__(self, rows: list[dict], cap: int = 1000):
        self.rows = rows
        self.cap = cap
        self.calls = 0

    def get(self, url, params=None, timeout=None):
        self.calls += 1
        start = int(params["startblock"])
        page = [r for r in self.rows if int(r["blockNumber"]) >= start][: self.cap]
        payload = {"status": "1", "message": "OK", "result": page}

        class R:
            def json(self_inner):
                return payload
        return R()


class PaginationTests(unittest.TestCase):
    def test_walks_past_the_server_page_cap(self) -> None:
        """The API caps pages below the requested offset; a short page is not the end."""
        rows = [row(1000 + i, "0xaaa", WALLET, 10.0, f"0x{i:064x}") for i in range(2500)]
        api = FakeApi(rows, cap=1000)
        fwa.SESSION = api
        got, complete = fwa.fetch_token_transfers(WALLET, "key", ocf.USDC_CONTRACTS[0], pause=0.0)
        self.assertTrue(complete)
        self.assertEqual(len(got), 2500)  # all three pages, not just the first 1000

    def test_stops_when_a_page_adds_nothing_new(self) -> None:
        rows = [row(5000, "0xaaa", WALLET, 1.0, f"0x{i:064x}") for i in range(1000)]
        api = FakeApi(rows, cap=1000)
        fwa.SESSION = api
        got, complete = fwa.fetch_token_transfers(WALLET, "key", ocf.USDC_CONTRACTS[0], pause=0.0)
        self.assertEqual(len(got), 1000)

    def test_keep_filter_discards_but_still_advances(self) -> None:
        rows = ([row(1000 + i, ocf.USDC_CONTRACTS[0], WALLET, 5.0, f"0x{i:064x}") for i in range(1500)])
        api = FakeApi(rows, cap=1000)
        fwa.SESSION = api
        got, _ = fwa.fetch_token_transfers(
            WALLET, "key", ocf.USDC_CONTRACTS[0], pause=0.0, keep=lambda r: False
        )
        self.assertEqual(len(got), 0)          # everything filtered out
        self.assertGreaterEqual(api.calls, 2)  # but pagination still advanced


class ParsingTests(unittest.TestCase):
    def test_to_transfer_frame_scales_and_dedups(self) -> None:
        rows = [
            row(10, "0xaaa", WALLET, 1000.0, "0xtx1"),
            row(10, "0xaaa", WALLET, 1000.0, "0xtx1"),  # duplicate
            row(11, WALLET, "0xbbb", 250.0, "0xtx2"),
        ]
        frame = fwa.to_transfer_frame(rows)
        self.assertEqual(len(frame), 2)
        self.assertAlmostEqual(frame.iloc[0]["amount"], 1000.0)
        self.assertIn("timestamp", frame.columns)

    def test_empty_rows(self) -> None:
        self.assertTrue(fwa.to_transfer_frame([]).empty)

    def test_load_api_key_prefers_environment(self) -> None:
        import os
        os.environ["ETHERSCAN_API_KEY"] = "env-key-123"
        try:
            self.assertEqual(fwa.load_api_key(), "env-key-123")
        finally:
            del os.environ["ETHERSCAN_API_KEY"]


if __name__ == "__main__":
    unittest.main()
