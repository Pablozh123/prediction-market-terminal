"""app/wallet_origin.py: the measured first trade of a wallet, cached in the trade store."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from app import wallet_origin as wo
from src import trade_store as ts


def _fake_api(answers: dict[str, object]):
    """A get_json stand-in: answers[wallet] is a list of rows, an exception, or missing (empty)."""

    calls: list[str] = []

    def get_json(url, params=None, timeout=20):
        wallet = str((params or {}).get("user"))
        calls.append(wallet)
        answer = answers.get(wallet, [])
        if isinstance(answer, Exception):
            raise answer
        return answer

    get_json.calls = calls  # type: ignore[attr-defined]
    return get_json


class FetchFirstTradeTests(unittest.TestCase):
    def test_a_trade_row_is_a_measured_first_trade(self) -> None:
        api = _fake_api({"0xabc": [{"timestamp": 1788506814, "type": "TRADE"}]})
        row = wo.fetch_first_trade("0xABC", get_json=api)
        self.assertEqual(row["state"], wo.ORIGIN_MEASURED)
        self.assertEqual(row["first_trade_ts"], 1788506814)
        self.assertEqual(row["wallet"], "0xabc")
        # The call asks for the oldest TRADE, one row, nothing else.
        self.assertEqual(api.calls, ["0xabc"])

    def test_no_row_is_none_and_a_failure_is_error(self) -> None:
        self.assertEqual(wo.fetch_first_trade("0xabc", get_json=_fake_api({}))["state"], wo.ORIGIN_NONE)
        row = wo.fetch_first_trade("0xabc", get_json=_fake_api({"0xabc": RuntimeError("boom")}))
        self.assertEqual(row["state"], wo.ORIGIN_ERROR)
        self.assertIn("boom", row["detail"])
        self.assertIsNone(row["first_trade_ts"])

    def test_an_unreadable_timestamp_is_an_error_not_a_zero(self) -> None:
        row = wo.fetch_first_trade("0xabc", get_json=_fake_api({"0xabc": [{"timestamp": "soon"}]}))
        self.assertEqual(row["state"], wo.ORIGIN_ERROR)

    def test_empty_wallet_never_hits_the_network(self) -> None:
        api = _fake_api({})
        self.assertEqual(wo.fetch_first_trade("", get_json=api)["state"], wo.ORIGIN_ERROR)
        self.assertEqual(api.calls, [])


class OriginCandidatesTests(unittest.TestCase):
    def test_whale_sized_identified_wallets_largest_first(self) -> None:
        tape = pd.DataFrame([
            {"wallet": "0xAAA", "notional": 3000.0},
            {"wallet": "0xaaa", "notional": 900.0},
            {"wallet": "0xbbb", "notional": 12000.0},
            {"wallet": "0xccc", "notional": 2499.0},
            {"wallet": "0xddd", "notional": 1300.0},
            {"wallet": "0xddd", "notional": 1300.0},
            {"wallet": "Not public", "notional": 50000.0},
            {"wallet": "", "notional": 50000.0},
        ])
        # Summed over the tape: 0xddd reaches the threshold through two prints.
        self.assertEqual(wo.origin_candidates(tape, whale_threshold=2500.0), ["0xbbb", "0xaaa", "0xddd"])
        self.assertEqual(wo.origin_candidates(tape, whale_threshold=2500.0, limit=1), ["0xbbb"])
        self.assertEqual(wo.origin_candidates(pd.DataFrame(), whale_threshold=2500.0), [])


class FirstTradeMapTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Path(self.tmp.name) / "store.sqlite"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_fetches_within_the_budget_and_remembers_the_answers(self) -> None:
        api = _fake_api({
            "0xa": [{"timestamp": 100}], "0xb": [{"timestamp": 200}], "0xc": [{"timestamp": 300}],
        })
        fetch = lambda w: wo.fetch_first_trade(w, get_json=api)  # noqa: E731
        origins, meta = wo.first_trade_map(["0xA", "0xb", "0xc", "0xa"], path=self.store, budget=2, fetch=fetch, now=1000)
        self.assertEqual(meta["asked"], 3)
        self.assertEqual(meta["fetched"], 2)
        self.assertEqual(meta["skipped"], 1)
        self.assertEqual(set(origins), {"0xa", "0xb"})
        self.assertEqual(origins["0xa"]["first_trade_ts"], 100)
        # Second pass: the two answers come from the store, only the third is asked.
        origins, meta = wo.first_trade_map(["0xa", "0xb", "0xc"], path=self.store, budget=2, fetch=fetch, now=2000)
        self.assertEqual(meta["cached"], 2)
        self.assertEqual(meta["fetched"], 1)
        self.assertEqual(set(origins), {"0xa", "0xb", "0xc"})
        self.assertEqual(api.calls, ["0xa", "0xb", "0xc"])
        conn = ts.connect(self.store)
        try:
            self.assertEqual(ts.origin_map(conn)["0xc"]["first_trade_ts"], 300)
        finally:
            conn.close()

    def test_a_measured_wallet_is_never_asked_again(self) -> None:
        api = _fake_api({"0xa": [{"timestamp": 100}]})
        fetch = lambda w: wo.fetch_first_trade(w, get_json=api)  # noqa: E731
        wo.first_trade_map(["0xa"], path=self.store, budget=5, fetch=fetch, now=1000)
        wo.first_trade_map(["0xa"], path=self.store, budget=5, fetch=fetch, now=10_000_000)
        self.assertEqual(api.calls, ["0xa"])

    def test_none_and_error_are_retried_only_after_the_retry_window(self) -> None:
        api = _fake_api({"0xa": RuntimeError("down"), "0xb": []})
        fetch = lambda w: wo.fetch_first_trade(w, get_json=api)  # noqa: E731
        _, meta = wo.first_trade_map(["0xa", "0xb"], path=self.store, budget=5, fetch=fetch, now=1000)
        self.assertEqual(meta["errors"], 1)
        wo.first_trade_map(["0xa", "0xb"], path=self.store, budget=5, fetch=fetch, now=1000 + 3600)
        self.assertEqual(api.calls, ["0xa", "0xb"])
        wo.first_trade_map(["0xa", "0xb"], path=self.store, budget=5, fetch=fetch, now=1000 + int(wo.RETRY_HOURS * 3600) + 1)
        self.assertEqual(api.calls, ["0xa", "0xb", "0xa", "0xb"])

    def test_a_late_measurement_replaces_an_earlier_error(self) -> None:
        answers: dict[str, object] = {"0xa": RuntimeError("down")}
        api = _fake_api(answers)
        fetch = lambda w: wo.fetch_first_trade(w, get_json=api)  # noqa: E731
        wo.first_trade_map(["0xa"], path=self.store, budget=5, fetch=fetch, now=1000)
        answers["0xa"] = [{"timestamp": 42}]
        origins, _ = wo.first_trade_map(["0xa"], path=self.store, budget=5, fetch=fetch, now=1000 + 200_000)
        self.assertEqual(origins["0xa"]["state"], wo.ORIGIN_MEASURED)
        self.assertEqual(origins["0xa"]["first_trade_ts"], 42)

    def test_zero_budget_reads_the_store_and_asks_nothing(self) -> None:
        api = _fake_api({"0xa": [{"timestamp": 100}]})
        fetch = lambda w: wo.fetch_first_trade(w, get_json=api)  # noqa: E731
        origins, meta = wo.first_trade_map(["0xa"], path=self.store, budget=0, fetch=fetch, now=1000)
        self.assertEqual(origins, {})
        self.assertEqual(meta["skipped"], 1)
        self.assertEqual(api.calls, [])

    def test_placeholders_and_blanks_are_not_wallets(self) -> None:
        api = _fake_api({})
        fetch = lambda w: wo.fetch_first_trade(w, get_json=api)  # noqa: E731
        origins, meta = wo.first_trade_map(["Not public", "", "nan"], path=self.store, budget=5, fetch=fetch, now=1000)
        self.assertEqual(origins, {})
        self.assertEqual(meta["asked"], 0)


class AgeDaysTests(unittest.TestCase):
    def test_days_between_first_trade_and_a_moment(self) -> None:
        self.assertAlmostEqual(wo.age_days(0, 86_400 * 2.5), 2.5)
        self.assertAlmostEqual(wo.age_days(86_400, pd.Timestamp("1970-01-03T00:00:00Z")), 1.0)
        self.assertEqual(wo.age_days(86_400 * 10, 0), 0.0)
        self.assertIsNone(wo.age_days(None, 0))
        self.assertIsNone(wo.age_days("later", 0))


if __name__ == "__main__":
    unittest.main()
