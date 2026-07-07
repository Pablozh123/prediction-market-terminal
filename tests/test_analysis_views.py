import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app import analysis_views as av


class LoadPayloadTests(unittest.TestCase):
    def test_loads_valid_json(self):
        with TemporaryDirectory() as tmp:
            (Path(tmp) / "meta.json").write_text('{"backend": "mock"}', encoding="utf-8")
            self.assertEqual(av.load_publish_payload(Path(tmp), "meta.json"), {"backend": "mock"})

    def test_missing_or_broken_returns_none(self):
        with TemporaryDirectory() as tmp:
            self.assertIsNone(av.load_publish_payload(Path(tmp), "queue.json"))
            (Path(tmp) / "queue.json").write_text("{broken", encoding="utf-8")
            self.assertIsNone(av.load_publish_payload(Path(tmp), "queue.json"))
            (Path(tmp) / "list.json").write_text("[1, 2]", encoding="utf-8")
            self.assertIsNone(av.load_publish_payload(Path(tmp), "list.json"))


class QueueFilterTests(unittest.TestCase):
    CARDS = [
        {"id": "a", "score_band": "high"},
        {"id": "b", "score_band": "medium"},
        {"id": "c", "score_band": "low"},
    ]

    def test_filters_by_band(self):
        self.assertEqual([c["id"] for c in av.filter_queue_cards(self.CARDS, "medium")], ["b"])

    def test_unknown_band_returns_all(self):
        self.assertEqual(len(av.filter_queue_cards(self.CARDS, "Alle")), 3)


class KategoriePointsTests(unittest.TestCase):
    def test_joins_and_marks_censored(self):
        karte = {
            "zeilen": [
                {"kategorie": "Politik", "brier_t7": 0.35, "n_maerkte": 73},
                {"kategorie": "Sport", "brier_t7": 0.04, "n_maerkte": 60},
                {"kategorie": "Krypto", "brier_t7": None, "n_maerkte": 81},
            ],
            "beispiele": [
                {"kategorie": "Politik", "minuten_bis_konvergenz": 60.0, "praezisions_hinweis": "Median"},
                {"kategorie": "Sport", "minuten_bis_konvergenz": 210.0, "praezisions_hinweis": "enthaelt Spieldauer"},
                {"kategorie": "Krypto", "minuten_bis_konvergenz": 2.0, "praezisions_hinweis": ""},
            ],
        }
        points = av.kategorie_points(karte)
        self.assertEqual([p["kategorie"] for p in points], ["Politik", "Sport"])
        self.assertFalse(points[0]["censored"])
        self.assertTrue(points[1]["censored"])
        self.assertEqual(points[1]["minuten"], 210.0)

    def test_negative_konvergenz_floored_to_one_minute(self):
        # Vor dem Ereignis eingepreist (negative Minuten) darf auf der
        # log-Achse nicht still verschwinden -> Untergrenze 1 Minute.
        karte = {
            "zeilen": [{"kategorie": "Krypto", "brier_t7": 0.11, "n_maerkte": 81}],
            "beispiele": [{"kategorie": "Krypto", "minuten_bis_konvergenz": -44.0, "praezisions_hinweis": "Untergrenze 1 Minute"}],
        }
        points = av.kategorie_points(karte)
        self.assertEqual(len(points), 1)
        self.assertEqual(points[0]["minuten"], 1.0)
        self.assertEqual(points[0]["minuten_roh"], -44.0)

    def test_empty_karte_safe(self):
        self.assertEqual(av.kategorie_points({}), [])


class MentionsBarsTests(unittest.TestCase):
    def test_sorted_by_konvergenz(self):
        payload = {
            "faelle": [
                {"event": "b", "minuten_bis_erste_reaktion": 1.0, "minuten_bis_konvergenz": 30.0},
                {"event": "a", "minuten_bis_erste_reaktion": 2.0, "minuten_bis_konvergenz": 5.0},
                {"event": "leer", "minuten_bis_erste_reaktion": None, "minuten_bis_konvergenz": None},
            ]
        }
        rows = av.mentions_bars(payload)
        self.assertEqual([r["event"] for r in rows], ["a", "b"])


class PipelineTimelineTests(unittest.TestCase):
    def test_sorted_and_whitelisted(self):
        payload = {
            "eintraege": [
                {"ts": "2026-07-03T21:00:00Z", "action": "NO", "reason": "final", "limit_price": None, "size_usd": None, "best_ask": 0.9, "best_bid": 0.8},
                {"ts": "2026-07-03T20:00:00Z", "action": "YES", "reason": "count", "limit_price": 0.82, "size_usd": 12.3, "best_ask": 0.82, "best_bid": 0.8},
            ]
        }
        rows = av.pipeline_timeline(payload)
        self.assertEqual([r["action"] for r in rows], ["YES", "NO"])
        self.assertEqual(set(rows[0].keys()), {"ts", "action", "reason", "limit_price", "size_usd", "best_ask", "best_bid"})


class AuditHashTests(unittest.TestCase):
    def test_pairs_and_caps(self):
        audit = {"prompt_hashes": ["p1", "p2", "p3"], "output_hashes": ["o1", "o2", "o3"]}
        rows = av.audit_hash_rows(audit, limit=2)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0], {"call": "1", "prompt_hash": "p1", "output_hash": "o1"})


if __name__ == "__main__":
    unittest.main()
