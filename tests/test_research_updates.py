import json
import math
import shutil
import unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from app.research_updates import build_updates


ROOT = Path(__file__).resolve().parents[1]


class ResearchUpdatesTests(unittest.TestCase):
    def test_six_portable_cards(self):
        cards = build_updates(ROOT)
        self.assertEqual(len(cards), 6)
        self.assertEqual(len({card["id"] for card in cards}), 6)
        for card in cards:
            with self.subTest(card=card["id"]):
                self.assertEqual(card["status"], "recent")
                self.assertIn(card["verdikt_art"], {"offen", "nein"})
                self.assertGreater(len(card["einfach"]), 120)
                self.assertTrue(any(char.isdigit() for char in card["einfach"]))
                self.assertFalse(any(word in card["einfach"] for word in ("None", "nan", "{")))
                self.assertTrue(card["basis"]["fenster"])
                self.assertTrue(datetime.fromisoformat(card["published_at_utc"].replace("Z", "+00:00")).tzinfo)
                self.assertEqual({a["schluessel"] for a in card["analyse"]}, {"gemessen", "wie", "daten", "entscheidung"})
                self.assertEqual({a["art"] for a in card["interpretation"]}, {"lesart", "gegenlesart", "grenze"})
                self.assertTrue(all(len(a["text"]) > 50 for a in card["interpretation"]))
                self.assertTrue((ROOT / card["report"]).is_file())
                self.assertTrue((ROOT / card["modul"]).is_file())
                self.assertTrue(card["daten"])
                self.assertTrue(all((ROOT / item["path"]).is_file() for item in card["daten"]))
                self.assertTrue(all(math.isfinite(n["wert"]) for n in card["zahlen"]))
                self.assertIn(card["diagramm"]["art"], {"kosten", "vergleich", "intervall", "quote", "anteil"})
                self.assertTrue(all(math.isfinite(p["wert"]) for p in card["diagramm"]["punkte"]))
                self.assertEqual(len(card["details"]["spalten"]), len(card["details"]["zeilen"][0]))

    def test_source_values_and_windows(self):
        cards = {card["id"]: card for card in build_updates(ROOT)}
        snapshot = json.loads((ROOT / "docs/research/research_updates_2026-10-12.json").read_text(encoding="utf-8"))
        self.assertEqual(snapshot["cex_forward"]["completed_hour_blocks"], 21)
        self.assertEqual(snapshot["cex_forward"]["qualified_impulses"], 46)
        self.assertEqual(snapshot["cex_forward"]["baseline"]["250"]["closed_trades"], 193)
        self.assertEqual(snapshot["cex_forward"]["baseline"]["250"]["net_pnl"], 32.27246)
        self.assertEqual(snapshot["cex_execution"]["baseline"]["500"]["realized_pnl"], -5.53763)
        self.assertEqual(snapshot["mm_queue"]["queue_back"]["250"]["sum_usd"], -39705.31)
        self.assertEqual(snapshot["source_speed"]["rows"], 39)
        self.assertEqual(snapshot["arb_funnel"]["cross_raw"], 2505)
        self.assertEqual(snapshot["fed"]["n_meetings"], 5)
        self.assertTrue(all(evaluation["n"] == 5 for evaluation in snapshot["fed"]["evaluation"].values()))
        for source in snapshot["sources"].values():
            self.assertEqual(len(source["sha256"]), 64)
            self.assertFalse(Path(source["path"]).is_absolute())
            self.assertNotIn("Users", source["path"])
        self.assertIn("2026-10-12", cards["cex-leadlag-forward"]["basis"]["fenster"])
        self.assertIn("2026-09-04", cards["mm-queue-forward"]["basis"]["fenster"])
        for card_id in ("cex-leadlag-forward", "cex-execution-latency"):
            self.assertEqual(cards[card_id]["modul"], "app/research_updates.py")
            self.assertEqual(cards[card_id]["module_role"], "publication")

    def test_builds_without_other_projects_or_ignored_outputs(self):
        cards = build_updates(ROOT)
        with TemporaryDirectory(dir=ROOT) as temporary:
            portable = Path(temporary)
            self.assertTrue(portable.resolve().is_relative_to(ROOT.resolve()))
            paths = {"docs/research/research_updates_2026-10-12.json"}
            paths.update(card["report"] for card in cards)
            paths.update(card["modul"] for card in cards)
            for path in paths:
                target = portable / path
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / path, target)
            self.assertEqual(build_updates(portable), cards)


if __name__ == "__main__":
    unittest.main()
