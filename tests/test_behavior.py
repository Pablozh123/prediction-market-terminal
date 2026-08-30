"""Der Verhaltens-Layer: Muster werden berichtet, nie zusammengefuehrt.

Die zwei Detektoren liefern Fakten mit Belegzeiten, keine Scores: der
dichteste Burst je Wallet (Order-Splitting) und Paare, die wiederholt
zeitnah gegeneinander im selben Buch stehen (Wash-Verdacht, "verhaelt sich
wie"). Die Kappung auf die groessten Wallets darf eine ausdruecklich
erfragte Wallet nie verschlucken, und das Notional zaehlt jeden Print genau
einmal, wie im Co-Trading-Netz.
"""

from __future__ import annotations

import unittest

import pandas as pd

from app import behavior as bhv

W_A = "0x" + "a" * 40
W_B = "0x" + "b" * 40
W_C = "0x" + "c" * 40


def _print(wallet: str, seconds: float, side: str = "BUY", outcome: str = "YES",
           notional: float = 100.0, market: str = "m1", title: str | None = None) -> dict:
    return {
        "wallet": wallet, "market_key": market, "title": title or f"Market {market}",
        "side": side, "outcome": outcome, "notional": notional,
        "time": pd.Timestamp("2026-08-30T12:00:00Z") + pd.Timedelta(seconds=seconds),
    }


class FingerprintTests(unittest.TestCase):
    def test_a_burst_is_reported_with_its_evidence(self) -> None:
        rows = [_print(W_A, i * 4.0) for i in range(10)]           # 10 Prints in 36s
        rows += [_print(W_B, i * 3600.0) for i in range(10)]       # 10 Prints ueber Stunden
        frame = bhv.order_splitting_fingerprints(pd.DataFrame(rows))
        self.assertEqual(list(frame["wallet"]), [W_A])
        reihe = frame.iloc[0]
        self.assertEqual(int(reihe["burst_prints"]), 10)
        self.assertAlmostEqual(float(reihe["burst_seconds"]), 36.0)
        self.assertEqual(reihe["burst_outcome"], "YES")
        self.assertAlmostEqual(float(reihe["burst_notional"]), 1000.0)
        self.assertTrue(str(reihe["burst_start"]).startswith("2026-08-30T12:00:00"))

    def test_below_the_threshold_nothing_is_a_fingerprint(self) -> None:
        rows = [_print(W_A, i * 4.0) for i in range(7)]
        frame = bhv.order_splitting_fingerprints(pd.DataFrame(rows))
        self.assertTrue(frame.empty)
        self.assertEqual(list(frame.columns), bhv.FINGERPRINT_COLUMNS)

    def test_a_burst_must_sit_on_one_market_side(self) -> None:
        # Zehn schnelle Prints, aber ueber zwei Maerkte verteilt: kein
        # Splitting-Muster, nur ein beschaeftigter Moment.
        rows = [_print(W_A, i * 4.0, market=f"m{i % 2}") for i in range(10)]
        self.assertTrue(bhv.order_splitting_fingerprints(pd.DataFrame(rows)).empty)

    def test_empty_input_answers_with_the_empty_shape(self) -> None:
        frame = bhv.order_splitting_fingerprints(pd.DataFrame())
        self.assertTrue(frame.empty)
        self.assertEqual(list(frame.columns), bhv.FINGERPRINT_COLUMNS)


class ComplementaryTests(unittest.TestCase):
    def _pair_tape(self) -> pd.DataFrame:
        rows = []
        for i in range(5):
            rows.append(_print(W_A, i * 30.0, side="BUY", outcome="YES", notional=100.0))
            rows.append(_print(W_B, i * 30.0 + 5.0, side="BUY", outcome="NO", notional=200.0))
        return pd.DataFrame(rows)

    def test_opposite_sides_of_one_book_become_a_reported_pair(self) -> None:
        frame = bhv.complementary_books(self._pair_tape())
        self.assertEqual(len(frame), 1)
        reihe = frame.iloc[0]
        self.assertEqual((reihe["wallet_a"], reihe["wallet_b"]), (W_A, W_B))
        # Alle zehn Prints liegen im 5-Minuten-Fenster: jede A-B-Kombination
        # ist ein Ereignis, aber jeder Print zaehlt im Notional genau einmal.
        self.assertEqual(int(reihe["events"]), 25)
        self.assertAlmostEqual(float(reihe["notional_a"]), 500.0)
        self.assertAlmostEqual(float(reihe["notional_b"]), 1000.0)
        self.assertEqual(int(reihe["markets"]), 1)
        self.assertEqual(reihe["top_market"], "Market m1")

    def test_sell_no_and_buy_no_oppose_each_other(self) -> None:
        # Entscheidend ist die Wirkung auf das YES-Buch, nicht das Wort auf
        # dem Ticket: SELL NO drueckt nach oben, BUY NO nach unten.
        rows = []
        for i in range(4):
            rows.append(_print(W_A, i * 30.0, side="SELL", outcome="NO"))
            rows.append(_print(W_B, i * 30.0 + 5.0, side="BUY", outcome="NO"))
        self.assertEqual(len(bhv.complementary_books(pd.DataFrame(rows))), 1)

    def test_the_same_direction_is_co_trading_not_wash(self) -> None:
        rows = []
        for i in range(5):
            rows.append(_print(W_A, i * 30.0, side="BUY", outcome="YES"))
            rows.append(_print(W_B, i * 30.0 + 5.0, side="BUY", outcome="YES"))
        self.assertTrue(bhv.complementary_books(pd.DataFrame(rows)).empty)

    def test_too_few_events_stay_unreported(self) -> None:
        rows = [
            _print(W_A, 0.0, side="BUY", outcome="YES"),
            _print(W_B, 5.0, side="BUY", outcome="NO"),
        ]
        self.assertTrue(bhv.complementary_books(pd.DataFrame(rows)).empty)

    def test_focus_wallets_survive_the_size_cap(self) -> None:
        tape = self._pair_tape()
        wal = pd.DataFrame([_print(W_C, 9000.0, notional=1_000_000.0, market="m9")])
        tape = pd.concat([tape, wal], ignore_index=True)
        ohne = bhv.complementary_books(tape, max_wallets=1)
        self.assertTrue(ohne.empty)
        mit = bhv.complementary_books(tape, max_wallets=1, focus_wallets=[W_A, W_B])
        self.assertEqual(len(mit), 1)


class ReportTests(unittest.TestCase):
    def test_the_report_filters_results_not_the_tape(self) -> None:
        rows = []
        for i in range(5):
            rows.append(_print(W_A, i * 30.0, side="BUY", outcome="YES"))
            rows.append(_print(W_B, i * 30.0 + 5.0, side="BUY", outcome="NO"))
        rows += [_print(W_C, 500.0 + i * 4.0, market="m2") for i in range(10)]
        report = bhv.behavior_report(pd.DataFrame(rows), wallets=[W_A])
        # Der Partner W_B steht ausserhalb der gefragten Menge und bleibt im
        # Paar sichtbar; W_Cs Fingerprint betrifft die Menge nicht und faellt.
        self.assertEqual(len(report["complementary_pairs"]), 1)
        self.assertEqual(report["complementary_pairs"][0]["wallet_b"], W_B)
        self.assertEqual(report["fingerprints"], [])
        self.assertIn("params", report)

    def test_an_empty_tape_is_an_empty_report(self) -> None:
        report = bhv.behavior_report(pd.DataFrame())
        self.assertEqual(report["fingerprints"], [])
        self.assertEqual(report["complementary_pairs"], [])
        self.assertEqual(report["tape_rows"], 0)


if __name__ == "__main__":
    unittest.main()
