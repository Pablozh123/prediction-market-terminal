import json
import shutil
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from app import microstructure_report as mr

PROJEKT = Path(__file__).resolve().parents[1]


def _kopiere_studien(ziel: Path) -> Path:
    """Legt eine Arbeitskopie von docs/research an, damit Tests sie aendern koennen."""
    quelle = PROJEKT / mr.REPORT_DIR
    kopie = ziel / mr.REPORT_DIR
    kopie.mkdir(parents=True, exist_ok=True)
    for datei in quelle.glob("*.json"):
        shutil.copy2(datei, kopie / datei.name)
    return ziel


class PayloadTests(unittest.TestCase):
    def test_baut_alle_studien(self):
        p = mr.build_payload(PROJEKT)
        self.assertEqual(p["fehlend"], [])
        self.assertEqual(len(p["studien"]), len(mr.STUDIEN))
        self.assertEqual(p["zaehler"]["gesamt"], len(p["studien"]))

    def test_ids_sind_eindeutig(self):
        ids = [s.id for s in mr.STUDIEN]
        self.assertEqual(len(ids), len(set(ids)))

    def test_jede_studie_hat_pflichtfelder(self):
        for s in mr.build_payload(PROJEKT)["studien"]:
            with self.subTest(studie=s["id"]):
                for feld in ("frage", "verdikt", "verdikt_art", "einfach", "report", "modul"):
                    self.assertTrue(s.get(feld), f"{feld} fehlt")
                self.assertIn(s["verdikt_art"], (mr.VERDIKT_JA, mr.VERDIKT_NEIN, mr.VERDIKT_OFFEN))
                self.assertTrue(s.get("zahlen"), "keine Zahlen")
                self.assertTrue(s.get("basis"), "keine Datenbasis")

    def test_zaehler_summiert_auf(self):
        z = mr.build_payload(PROJEKT)["zaehler"]
        self.assertEqual(z["nein"] + z["ja"] + z["offen"], z["gesamt"])

    def test_report_und_modul_existieren(self):
        for s in mr.build_payload(PROJEKT)["studien"]:
            with self.subTest(studie=s["id"]):
                self.assertTrue((PROJEKT / s["report"]).exists(), s["report"])
                self.assertTrue((PROJEKT / s["modul"]).exists(), s["modul"])
                if s.get("bild"):
                    self.assertTrue((PROJEKT / s["bild"]).exists(), s["bild"])

    def test_zeitstempel_wird_uebernommen(self):
        fest = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
        p = mr.build_payload(PROJEKT, jetzt=fest)
        self.assertEqual(p["stand_utc"], fest.isoformat())


class DiagrammTests(unittest.TestCase):
    ARTEN = {mr.DIA_KOSTEN, mr.DIA_VERGLEICH, mr.DIA_INTERVALL, mr.DIA_QUOTE, mr.DIA_ANTEIL}

    def test_diagramme_sind_renderbar(self):
        for s in mr.build_payload(PROJEKT)["studien"]:
            d = s.get("diagramm")
            with self.subTest(studie=s["id"]):
                self.assertIsNotNone(d, "kein Diagramm")
                self.assertIn(d["art"], self.ARTEN)
                self.assertTrue(d.get("titel"))
                self.assertTrue(d.get("punkte"), "keine Datenpunkte")
                for punkt in d["punkte"]:
                    self.assertTrue(punkt.get("label"))
                    hat_wert = punkt.get("wert") is not None
                    hat_werte = isinstance(punkt.get("werte"), list) and punkt["werte"]
                    self.assertTrue(hat_wert or hat_werte, f"Punkt ohne Wert: {punkt}")

    def test_intervall_punkte_sind_geordnet(self):
        for s in mr.build_payload(PROJEKT)["studien"]:
            d = s.get("diagramm") or {}
            if d.get("art") != mr.DIA_INTERVALL:
                continue
            for punkt in d["punkte"]:
                if punkt.get("von") is None:
                    continue
                with self.subTest(studie=s["id"], punkt=punkt["label"]):
                    self.assertLessEqual(punkt["von"], punkt["bis"])
                    self.assertLessEqual(punkt["von"], punkt["wert"])
                    self.assertLessEqual(punkt["wert"], punkt["bis"])

    def test_vergleich_hat_passende_gruppen(self):
        for s in mr.build_payload(PROJEKT)["studien"]:
            d = s.get("diagramm") or {}
            if d.get("art") != mr.DIA_VERGLEICH or "gruppen" not in d:
                continue
            for punkt in d["punkte"]:
                with self.subTest(studie=s["id"], punkt=punkt["label"]):
                    self.assertEqual(len(punkt["werte"]), len(d["gruppen"]))


class ZahlenKommenAusDenReportsTests(unittest.TestCase):
    """Der Kern der Konstruktion: Prosa ist kuratiert, Zahlen nie."""

    def test_geaenderter_report_schlaegt_durch(self):
        with TemporaryDirectory() as tmp:
            wurzel = _kopiere_studien(Path(tmp))
            pfad = wurzel / mr.REPORT_DIR / "orderflow_rest-2026-07.json"
            daten = json.loads(pfad.read_text(encoding="utf-8"))
            daten["signals"]["imbalance"]["overall"]["hit_rate"] = 0.611
            pfad.write_text(json.dumps(daten), encoding="utf-8")

            studie = next(
                s for s in mr.build_payload(wurzel)["studien"]
                if s["id"] == "imbalance-direction"
            )
            treffer = next(z for z in studie["zahlen"] if z["label"] == "Hit rate")
            self.assertEqual(treffer["wert"], 61.1)

    def test_staleness_verschraenkt_beide_laeufe(self):
        with TemporaryDirectory() as tmp:
            wurzel = _kopiere_studien(Path(tmp))
            pfad = wurzel / mr.REPORT_DIR / "mm_pnl_july-2026.json"
            daten = json.loads(pfad.read_text(encoding="utf-8"))
            daten["fill_models"]["tape"]["decomposition"]["markout_cents_per_fill"] = -500.0
            pfad.write_text(json.dumps(daten), encoding="utf-8")

            studie = next(
                s for s in mr.build_payload(wurzel)["studien"] if s["id"] == "mm-staleness"
            )
            langsam = next(
                z for z in studie["zahlen"] if z["label"] == "Adverse selection at 120s"
            )
            self.assertEqual(langsam["wert"], -500.0)

    def test_ueberlebende_segmente_werden_gezaehlt(self):
        studie = next(
            s for s in mr.build_payload(PROJEKT)["studien"] if s["id"] == "edge-segments"
        )
        ueberlebende = next(z for z in studie["zahlen"] if z["label"] == "Cuts that survived")
        self.assertGreaterEqual(ueberlebende["wert"], 0)
        intervall = [z for z in studie["zahlen"] if z["label"] == "Survivor, 95% interval"]
        if intervall:
            von, bis = intervall[0]["wert"]
            self.assertLessEqual(von, 0.0)
            self.assertGreaterEqual(bis, 0.0)


class FehlendeDateienTests(unittest.TestCase):
    def test_leeres_verzeichnis_bricht_nicht_ab(self):
        with TemporaryDirectory() as tmp:
            p = mr.build_payload(Path(tmp))
            self.assertEqual(p["studien"], [])
            self.assertTrue(p["fehlend"])
            self.assertEqual(p["zaehler"]["gesamt"], 0)

    def test_eine_fehlende_datei_laesst_den_rest_stehen(self):
        with TemporaryDirectory() as tmp:
            wurzel = _kopiere_studien(Path(tmp))
            (wurzel / mr.REPORT_DIR / "reward_selection_2026-07-31.json").unlink()
            p = mr.build_payload(wurzel)
            ids = {s["id"] for s in p["studien"]}
            self.assertNotIn("rewards", ids)
            self.assertIn("imbalance-direction", ids)
            self.assertIn("reward_selection_2026-07-31", p["fehlend"])


if __name__ == "__main__":
    unittest.main()
