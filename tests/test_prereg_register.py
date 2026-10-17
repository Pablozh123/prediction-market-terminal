"""Das Preregistrierungs-Register: Status am Stichtag, Zahlen aus dem
Trainings-Artefakt, drei Eintraege."""

from __future__ import annotations

import unittest
from datetime import date, datetime, timezone
from pathlib import Path

from app import prereg_register as pr
from app import research_payload as rp

PROJEKT = Path(__file__).resolve().parents[1]


class StatusTests(unittest.TestCase):
    def test_vor_waehrend_nach_dem_testfenster(self) -> None:
        von, bis = "2026-09-04", "2026-09-17"
        self.assertEqual(pr.queue_status(von, bis, date(2026, 9, 3)), (pr.STATUS_EINGEFROREN, "test window opens 2026-09-04"))
        self.assertEqual(pr.queue_status(von, bis, date(2026, 9, 4))[1], "day 1 of 14, closes 2026-09-17")
        self.assertEqual(pr.queue_status(von, bis, date(2026, 9, 17))[0], pr.STATUS_LAEUFT)
        self.assertEqual(pr.queue_status(von, bis, date(2026, 9, 18))[0], pr.STATUS_WARTET)

    def test_ohne_datum_eingefroren(self) -> None:
        self.assertEqual(pr.queue_status("", "", date(2026, 9, 4))[0], pr.STATUS_EINGEFROREN)


class NutzlastTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.p = pr.build_payload(PROJEKT, jetzt=datetime(2026, 9, 10, tzinfo=timezone.utc))

    def test_drei_eintraege_mit_status(self) -> None:
        self.assertEqual(self.p["fehlend"], [])
        ids = [e["id"] for e in self.p["eintraege"]]
        self.assertEqual(ids, ["pilot", "mm-queue", "track-record-validation"])
        status = {e["id"]: e["status"] for e in self.p["eintraege"]}
        self.assertEqual(status, {"pilot": pr.STATUS_ABGESCHLOSSEN, "mm-queue": pr.STATUS_LAEUFT, "track-record-validation": pr.STATUS_ENTWURF})
        self.assertEqual(self.p["zaehler"][pr.STATUS_LAEUFT], 1)
        for e in self.p["eintraege"]:
            self.assertTrue(e["status_text"])

    def test_queue_zahlen_aus_dem_training(self) -> None:
        q = next(e for e in self.p["eintraege"] if e["id"] == "mm-queue")
        self.assertEqual(q["fenster"], "2026-09-04 to 2026-09-17")
        self.assertEqual(q["eingefroren"], "2026-09-03")
        self.assertEqual(q["status_satz"], "day 7 of 14, closes 2026-09-17")
        self.assertEqual(q["gewaehlt"]["half_spread"], 0.02)
        self.assertEqual(q["gewaehlt"]["gamma"], 0.08)
        self.assertEqual(q["training"]["tage"], 22)
        self.assertEqual(len(q["diagramme"]["kandidaten"]["punkte"]), 6)
        self.assertEqual(q["diagramme"]["kandidaten"]["gruppen"], ["queue_back", "queue_front"])
        self.assertEqual(len(q["diagramme"]["tage"]["punkte"]), 22)
        # Kumuliert: der letzte Punkt ist die Trainingssumme des gewaehlten Satzes.
        self.assertAlmostEqual(q["diagramme"]["tage"]["punkte"][-1]["wert"], q["gewaehlt"]["total_usd"], places=0)
        self.assertEqual(len(q["tabellen"][0]["zeilen"]), 13)

    def test_track_record_entwurf(self) -> None:
        t = next(e for e in self.p["eintraege"] if e["id"] == "track-record-validation")
        self.assertIn("+0.15", t["primaermetrik"])
        self.assertIn("2026-11-14", t["primaermetrik"])
        self.assertEqual(t["extern"], "AsPredicted draft, not yet submitted")

    def test_policy_beide_sprachen(self) -> None:
        self.assertEqual(len(self.p["policy"]), 3)
        self.assertEqual(len(self.p["policy_de"]), 3)
        self.assertTrue(self.p["policy_de"][0].startswith("Preregistriert heisst"))

    def test_keine_wallet_adresse(self) -> None:
        self.assertEqual(rp.wallet_adressen_in(self.p), [])


if __name__ == "__main__":
    unittest.main()
