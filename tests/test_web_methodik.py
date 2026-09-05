"""Die Methodik-Seite muss dieselben Schwellen nennen, die der Code benutzt.

``web/js/pages/system_pages.js`` erklaert unter HOW A WALLET RECORD IS COUNTED
die vier Korrekturen aus ``app/track_record.py``. Der Text nennt vier Zahlen.
Stehen die im JavaScript und die Konstanten im Python auseinander, erklaert die
Seite eine Regel, nach der nichts gerechnet wird -- und das ist schlimmer als
gar keine Erklaerung. Dieser Test bindet beide aneinander.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from app import track_record as tr

WURZEL = Path(__file__).resolve().parents[1]
SEITE = WURZEL / "web" / "js" / "pages" / "system_pages.js"


class MethodikSchwellenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.quelltext = SEITE.read_text(encoding="utf-8")

    def _abschnitt(self) -> str:
        anfang = self.quelltext.find("HOW A WALLET RECORD IS COUNTED")
        self.assertGreater(anfang, 0, "der Abschnitt fehlt auf der Methodik-Seite")
        ende = self.quelltext.find("abschnitt('CROSS-VENUE MATCHING", anfang)
        self.assertGreater(ende, anfang)
        return self.quelltext[anfang:ende]

    def test_die_sample_gates_stehen_so_da_wie_sie_gelten(self) -> None:
        text = self._abschnitt()
        self.assertEqual(tr.MIN_RESOLVED_MARKETS, 10)
        self.assertEqual(tr.MIN_SPAN_DAYS, 14.0)
        self.assertIn("mono('%d')" % tr.MIN_RESOLVED_MARKETS, text)
        self.assertIn("mono('%d')" % int(tr.MIN_SPAN_DAYS), text)

    def test_die_farmer_schwellen_stehen_so_da_wie_sie_gelten(self) -> None:
        text = self._abschnitt()
        self.assertEqual(tr.FARMER_MIN_VOLUME, 25_000.0)
        self.assertEqual(tr.FARMER_MAX_EDGE, 0.005)
        self.assertIn("mono('$%s')" % f"{int(tr.FARMER_MIN_VOLUME):,}", text)
        self.assertIn("mono('%s%%')" % f"{tr.FARMER_MAX_EDGE * 100:g}", text)

    def test_die_vier_korrekturen_werden_alle_genannt(self) -> None:
        # Der Modulkopf von track_record.py fuehrt vier Korrekturen. Faellt
        # eine aus dem Text, erklaert die Seite ein anderes Verfahren als das,
        # das laeuft.
        text = self._abschnitt()
        for stichwort in ("NegRisk", "auto-redeem", "farming", "survivorship"):
            with self.subTest(stichwort=stichwort):
                self.assertIn(stichwort, text)
        # Und die Einschraenkung, die alles traegt.
        self.assertIn("Settled rows only", text)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
