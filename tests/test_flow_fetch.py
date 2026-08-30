"""Der begrenzte On-Chain-Walk hinter /api/wallet/{wallet}/flows.

Der Vertrag des Moduls ist das ``complete``-Flag: eine gekappte Historie darf
nie wie eine ganze aussehen, und eine ganze nie wie eine gekappte. Dazu die
zwei Abbruchregeln des Etherscan-Pagings (nur eine leere oder eine vollstaendig
bekannte Seite beendet die Historie — eine kurze Seite nicht) und die
Weiterverwendung von app/onchain_flows fuer Klassifikation und Summen.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pandas as pd

from app import flow_fetch as ff
from app import onchain_flows as ocf

WALLET = "0x" + "a" * 40
EXTERN = "0x" + "b" * 40
PROTOKOLL = "0x3a3bd7bb9528e159577f7c2e685cc81a765002e2"  # WrappedCollateral
USDC_E = ocf.USDC_CONTRACTS[0]


def _row(block: int, sender: str, recipient: str, dollars: float, ts: int = 1_600_000_000) -> dict:
    return {
        "hash": f"0xtx{block}", "from": sender, "to": recipient,
        "value": str(int(dollars * 1_000_000)), "blockNumber": str(block),
        "timeStamp": str(ts), "contractAddress": USDC_E, "tokenDecimal": "6",
    }


class PagingTests(unittest.TestCase):
    def test_a_short_page_does_not_end_the_walk_a_known_page_does(self) -> None:
        # Seite 1 ist kurz (der Server kappt Seiten stillschweigend), also
        # laeuft der Walk weiter; Seite 2 bringt nur den schon gesehenen
        # letzten Block und beendet die Historie als vollstaendig.
        rows = [_row(10, EXTERN, WALLET, 100.0)]
        calls: list[int] = []

        def get(params):
            calls.append(int(params["startblock"]))
            return {"result": [r for r in rows if int(r["blockNumber"]) >= int(params["startblock"])]}

        got, complete = ff.fetch_contract_transfers(
            WALLET, "key", USDC_E, page_budget=4, page_size=1000, pause=0.0, get=get)
        self.assertTrue(complete)
        self.assertEqual(len(got), 1)
        self.assertEqual(calls, [0, 10])

    def test_the_page_budget_caps_the_walk_and_says_so(self) -> None:
        def get(params):
            start = int(params["startblock"])
            return {"result": [_row(start + 1, EXTERN, WALLET, 1.0),
                               _row(start + 2, EXTERN, WALLET, 1.0)]}

        got, complete = ff.fetch_contract_transfers(
            WALLET, "key", USDC_E, page_budget=2, page_size=2, pause=0.0, get=get)
        self.assertFalse(complete)
        self.assertEqual(len(got), 4)

    def test_a_page_that_never_answers_is_incomplete_not_empty(self) -> None:
        def get(params):
            raise OSError("down")

        got, complete = ff.fetch_contract_transfers(
            WALLET, "key", USDC_E, page_budget=2, pause=0.0, retries=2, get=get)
        self.assertFalse(complete)
        self.assertEqual(got, [])

    def test_no_transactions_found_is_a_complete_empty_history(self) -> None:
        def get(params):
            return {"status": "0", "message": "No transactions found", "result": ""}

        got, complete = ff.fetch_contract_transfers(
            WALLET, "key", USDC_E, page_budget=2, pause=0.0, retries=1, get=get)
        self.assertTrue(complete)
        self.assertEqual(got, [])


class ReportTests(unittest.TestCase):
    def _get(self, params):
        rows = [
            _row(10, EXTERN, WALLET, 100.0, ts=1_600_000_000),   # Einzahlung
            _row(20, PROTOKOLL, WALLET, 50.0, ts=1_600_100_000),  # Settlement
            _row(30, WALLET, EXTERN, 30.0, ts=1_600_200_000),     # Auszahlung
        ]
        return {"result": [r for r in rows if int(r["blockNumber"]) >= int(params["startblock"])]}

    def test_the_report_reuses_the_flow_kernel_and_dates_the_first_transfer(self) -> None:
        report = ff.wallet_flow_report(
            WALLET, "key", contracts=[USDC_E], pause=0.0, get=self._get)
        self.assertTrue(report["complete"])
        self.assertEqual(report["n_transfers"], 3)
        self.assertAlmostEqual(report["summary"]["deposits_external"], 100.0)
        self.assertAlmostEqual(report["summary"]["withdrawals_external"], 30.0)
        self.assertAlmostEqual(report["summary"]["net_external"], 70.0)
        self.assertAlmostEqual(report["summary"]["deposits_protocol"], 50.0)
        self.assertAlmostEqual(report["peak_external_exposure"], 100.0)
        self.assertEqual(report["first_transfer_at"],
                         pd.Timestamp(1_600_000_000, unit="s", tz="UTC").isoformat())
        gegenparteien = {c["counterparty"] for c in report["counterparties"]}
        self.assertIn(EXTERN, gegenparteien)
        self.assertNotIn(PROTOKOLL, gegenparteien)

    def test_an_incomplete_walk_labels_its_totals_as_lower_bounds(self) -> None:
        def get(params):
            start = int(params["startblock"])
            return {"result": [_row(start + 1, EXTERN, WALLET, 1.0),
                               _row(start + 2, EXTERN, WALLET, 1.0)]}

        report = ff.wallet_flow_report(
            WALLET, "key", contracts=[USDC_E], page_budget=1, page_size=2, pause=0.0, get=get)
        self.assertFalse(report["complete"])
        self.assertIn("lower bounds", report["note"])

    def test_without_a_key_the_report_refuses_instead_of_guessing(self) -> None:
        with self.assertRaises(ff.FlowFetchError):
            ff.wallet_flow_report(WALLET, "", get=self._get)


class ApiKeyTests(unittest.TestCase):
    def test_the_dotenv_fallback_reads_the_key_without_logging_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / ".env").write_text('ETHERSCAN_API_KEY="secret123"\n', encoding="utf-8")
            with mock.patch.dict(os.environ):
                os.environ.pop("ETHERSCAN_API_KEY", None)
                os.environ.pop("POLYGONSCAN_API_KEY", None)
                self.assertEqual(ff.load_api_key(tmp), "secret123")

    def test_the_environment_wins_over_the_dotenv(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / ".env").write_text("ETHERSCAN_API_KEY=filekey\n", encoding="utf-8")
            with mock.patch.dict(os.environ, {"ETHERSCAN_API_KEY": "envkey"}):
                self.assertEqual(ff.load_api_key(tmp), "envkey")

    def test_no_key_anywhere_is_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ):
                os.environ.pop("ETHERSCAN_API_KEY", None)
                os.environ.pop("POLYGONSCAN_API_KEY", None)
                self.assertIsNone(ff.load_api_key(tmp))


if __name__ == "__main__":
    unittest.main()
