"""Die Cluster-Probe: der Iran-Test als Werkzeug, netzfrei geprueft.

Der Runner holt je Wallet die Handelshistorie ueber die Data-API und legt
alle Band-Signale nebeneinander. Der Vertrag hier: die Seitenschleife
unterscheidet "Historie zu Ende" von "Budget zu Ende" (ein halb gelesener
Ring saehe sonst ruhig aus), und ein koordiniertes Paar feuert die strenge
Co-Trading-Regel, waehrend die Detektoren ihre Befunde beisteuern.
"""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

import pandas as pd

_spec = importlib.util.spec_from_file_location(
    "run_cluster_probe_under_test",
    Path(__file__).resolve().parents[1] / "scripts" / "run_cluster_probe.py",
)
probe_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(probe_mod)

W_A = "0x" + "a" * 40
W_B = "0x" + "b" * 40


def _tape(wallet: str, offset_s: float) -> pd.DataFrame:
    start = pd.Timestamp("2026-08-30T12:00:00Z")
    rows = []
    for index in range(3):
        rows.append({
            "wallet": wallet, "market_key": f"m{index}", "title": f"Market {index}",
            "outcome": "YES", "side": "BUY", "notional": 6000.0,
            "time": start + pd.Timedelta(minutes=index * 10, seconds=offset_s),
            "transaction_hash": f"0x{wallet[-4:]}{index}", "asset": f"a{index}",
        })
    return pd.DataFrame(rows)


class FetchTests(unittest.TestCase):
    def setUp(self) -> None:
        self._page_size = probe_mod.PAGE_SIZE
        probe_mod.PAGE_SIZE = 3

    def tearDown(self) -> None:
        probe_mod.PAGE_SIZE = self._page_size

    def test_a_short_page_ends_the_history_cleanly(self) -> None:
        def fetch(limit, min_cash, user, offset):
            return _tape(user, 0.0).head(2) if offset == 0 else pd.DataFrame()

        frame, truncated = probe_mod.fetch_wallet_tape(W_A, pages=4, fetch=fetch)
        self.assertEqual(len(frame), 2)
        self.assertFalse(truncated)

    def test_a_full_last_page_at_the_budget_reads_as_truncated(self) -> None:
        def fetch(limit, min_cash, user, offset):
            frame = _tape(user, float(offset))
            frame["transaction_hash"] = frame["transaction_hash"] + str(offset)
            return frame

        frame, truncated = probe_mod.fetch_wallet_tape(W_A, pages=2, fetch=fetch)
        self.assertEqual(len(frame), 6)
        self.assertTrue(truncated)


class ProbeTests(unittest.TestCase):
    def test_a_coordinated_pair_fires_the_strict_co_trading_rule(self) -> None:
        def fetch(limit, min_cash, user, offset):
            return _tape(user, 0.0 if user == W_A else 60.0) if offset == 0 else pd.DataFrame()

        ergebnis = probe_mod.probe([W_A, W_B], pages=2, fetch=fetch)
        self.assertEqual(ergebnis["tape_rows"], 6)
        self.assertEqual(len(ergebnis["strict_edges"]), 1)
        kante = ergebnis["strict_edges"][0]
        self.assertEqual({kante["wallet_a"], kante["wallet_b"]}, {W_A, W_B})
        self.assertEqual(int(kante["shared_markets"]), 3)
        self.assertEqual(len(ergebnis["loose_edges"]), 1)
        self.assertEqual([z["prints"] for z in ergebnis["coverage"]], [3, 3])
        self.assertIn("behavior", ergebnis)

    def test_an_unknown_wallet_shows_up_as_empty_coverage_not_an_error(self) -> None:
        def fetch(limit, min_cash, user, offset):
            return pd.DataFrame()

        ergebnis = probe_mod.probe([W_A, W_B], pages=2, fetch=fetch)
        self.assertEqual(ergebnis["tape_rows"], 0)
        self.assertEqual([z["prints"] for z in ergebnis["coverage"]], [0, 0])
        self.assertEqual(ergebnis["strict_edges"], [])


if __name__ == "__main__":
    unittest.main()
