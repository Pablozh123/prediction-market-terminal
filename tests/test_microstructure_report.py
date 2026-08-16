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
                self.assertIn(s["verdikt_art"], (
                    mr.VERDIKT_JA, mr.VERDIKT_NEIN, mr.VERDIKT_OFFEN, mr.VERDIKT_KONTROLLE))
                self.assertTrue(s.get("zahlen"), "keine Zahlen")
                self.assertTrue(s.get("basis"), "keine Datenbasis")


class AnalyseTests(unittest.TestCase):
    """Was genau untersucht wurde, muss auf der Seite stehen."""

    def test_jede_studie_erklaert_ihre_methode(self):
        for s in mr.build_payload(PROJEKT)["studien"]:
            with self.subTest(studie=s["id"]):
                schluessel = [a["schluessel"] for a in s["analyse"]]
                self.assertEqual(
                    schluessel, ["gemessen", "wie", "daten", "entscheidung"],
                    "Methodenblock unvollstaendig oder in falscher Reihenfolge",
                )
                for a in s["analyse"]:
                    self.assertTrue(a["titel"])
                    self.assertGreater(len(a["text"]), 40, "Methodentext zu duenn")

    def test_entscheidungsregel_steht_vor_dem_ergebnis(self):
        """Ohne vorab genannte Messlatte ist ein Verdikt nicht pruefbar."""
        for s in mr.build_payload(PROJEKT)["studien"]:
            regel = next(a for a in s["analyse"] if a["schluessel"] == "entscheidung")
            with self.subTest(studie=s["id"]):
                self.assertGreater(len(regel["text"]), 60)


class InterpretationTests(unittest.TestCase):
    def test_jede_studie_nennt_lesart_gegenlesart_und_grenze(self):
        for s in mr.build_payload(PROJEKT)["studien"]:
            with self.subTest(studie=s["id"]):
                arten = [i["art"] for i in s["interpretation"]]
                self.assertEqual(arten, [mr.LESART, mr.GEGENLESART, mr.GRENZE])
                for i in s["interpretation"]:
                    self.assertTrue(i["titel"])
                    self.assertGreater(len(i["text"]), 50, "Interpretation zu duenn")

    def test_gegenlesart_ist_nicht_die_lesart(self):
        for s in mr.build_payload(PROJEKT)["studien"]:
            texte = {i["art"]: i["text"] for i in s["interpretation"]}
            with self.subTest(studie=s["id"]):
                self.assertNotEqual(texte[mr.LESART], texte[mr.GEGENLESART])
                self.assertNotEqual(texte[mr.LESART], texte[mr.GRENZE])


class EinfachMitZahlenTests(unittest.TestCase):
    def test_erklaerung_traegt_echte_zahlen(self):
        for s in mr.build_payload(PROJEKT)["studien"]:
            with self.subTest(studie=s["id"]):
                self.assertTrue(
                    any(z.isdigit() for z in s["einfach"]),
                    "Erklaerung ohne eine einzige Zahl",
                )
                self.assertGreater(len(s["einfach"]), 120)

    def test_keine_platzhalter_uebrig(self):
        for s in mr.build_payload(PROJEKT)["studien"]:
            with self.subTest(studie=s["id"]):
                for muster in ("{", "}", "None", "nan"):
                    self.assertNotIn(muster, s["einfach"], f"'{muster}' im Text")


class StichprobeTests(unittest.TestCase):
    """Die Kopfzahl muss aus einer Zelle stammen, nicht aus deren Summe."""

    def test_beobachtungen_liegen_nicht_ueber_den_snapshots(self):
        for s in mr.build_payload(PROJEKT)["studien"]:
            basis = s.get("basis") or {}
            if not (basis.get("beobachtungen") and basis.get("snapshots")):
                continue
            with self.subTest(studie=s["id"]):
                self.assertLessEqual(
                    basis["beobachtungen"], basis["snapshots"],
                    "mehr Beobachtungen als Snapshots deutet auf gepoolte "
                    "ueberlappende Zellen hin",
                )

    def test_kanonische_zelle_wird_gewaehlt(self):
        studie = next(
            s for s in mr.build_payload(PROJEKT)["studien"] if s["id"] == "imbalance-direction"
        )
        roh = json.loads((PROJEKT / mr.REPORT_DIR / "orderflow_rest-2026-07.json").read_text(encoding="utf-8"))
        zelle = mr._kanon_zelle(roh["signals"]["imbalance"])
        self.assertEqual(studie["basis"]["beobachtungen"], zelle["n"])
        self.assertNotEqual(zelle["n"], roh["signals"]["imbalance"]["overall"]["n"])

    def test_jede_studie_nennt_ihr_kalenderfenster(self):
        for s in mr.build_payload(PROJEKT)["studien"]:
            with self.subTest(studie=s["id"]):
                self.assertTrue((s.get("basis") or {}).get("fenster"), "kein Zeitfenster")


class VerdiktTests(unittest.TestCase):
    def test_kontrollstudie_zaehlt_nicht_als_bestaetigt(self):
        p = mr.build_payload(PROJEKT)
        kontrolle = [s for s in p["studien"] if s["verdikt_art"] == mr.VERDIKT_KONTROLLE]
        self.assertTrue(kontrolle, "keine Kontrollstudie ausgewiesen")
        self.assertEqual(p["zaehler"]["kontrolle"], len(kontrolle))
        for s in kontrolle:
            self.assertNotIn(s["id"], [x["id"] for x in p["studien"] if x["verdikt_art"] == mr.VERDIKT_JA])

    def test_bestaetigtes_verdikt_faengt_nicht_mit_nein_an(self):
        """Genau der Widerspruch, den die Pruefung gefunden hat.

        `book-reconcile` trug das Badge CONFIRMED ueber einem Verdikt, das
        mit "No." beginnt. In den Kopfkacheln war das als bestaetigte
        Hypothese gezaehlt, obwohl die Studie eine Kontrolle ist.
        """
        for s in mr.build_payload(PROJEKT)["studien"]:
            if s["verdikt_art"] != mr.VERDIKT_JA:
                continue
            with self.subTest(studie=s["id"]):
                self.assertFalse(
                    s["verdikt"].strip().lower().startswith("no"),
                    "Badge CONFIRMED, aber das Verdikt beginnt mit No",
                )

    def test_zaehler_summiert_alle_arten(self):
        z = mr.build_payload(PROJEKT)["zaehler"]
        self.assertEqual(z["nein"] + z["ja"] + z["offen"] + z["kontrolle"], z["gesamt"])


class DetailTabellenTests(unittest.TestCase):
    def test_tabellen_sind_wohlgeformt(self):
        for s in mr.build_payload(PROJEKT)["studien"]:
            tab = s.get("details")
            with self.subTest(studie=s["id"]):
                self.assertIsNotNone(tab, "keine Detailtabelle")
                self.assertTrue(tab["titel"])
                self.assertTrue(tab["spalten"])
                self.assertTrue(tab["zeilen"], "Tabelle ohne Zeilen")
                for zeile in tab["zeilen"]:
                    self.assertEqual(
                        len(zeile), len(tab["spalten"]),
                        f"Zeile passt nicht zu den Spalten: {zeile}",
                    )

    def test_zaehler_summiert_auf(self):
        z = mr.build_payload(PROJEKT)["zaehler"]
        self.assertEqual(z["nein"] + z["ja"] + z["offen"] + z["kontrolle"], z["gesamt"])

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

    def test_imbalance_diagramm_zeigt_alle_gitterzellen(self):
        """Jede Horizont/Delay-Zelle wird zur Zeile mit Wilson-Band."""
        p = mr.build_payload(PROJEKT)
        studie = next(s for s in p["studien"] if s["id"] == "imbalance-direction")
        roh = json.loads(
            (PROJEKT / mr.REPORT_DIR / "orderflow_rest-2026-07.json").read_text(encoding="utf-8"))
        gitter = roh["signals"]["imbalance"]["latency"]
        zellen = sum(len(z) for z in gitter.values())
        punkte = studie["diagramm"]["punkte"]
        self.assertEqual(len(punkte), zellen)
        for punkt in punkte:
            # Band von der Untergrenze zum Punktschaetzer, nie andersherum.
            self.assertLessEqual(punkt["von"], punkt["wert"])
            self.assertEqual(punkt["bis"], punkt["wert"])
        # Die kanonische Zelle ist markiert, damit die Kopfzahl auffindbar bleibt.
        self.assertTrue(any(p_["label"].endswith("←") for p_ in punkte))

    def test_segmente_diagramm_zeigt_spread_schnitte(self):
        """Die Kernaussage — negativ in jedem Segment — steht als Bild da."""
        p = mr.build_payload(PROJEKT)
        studie = next(s for s in p["studien"] if s["id"] == "edge-segments")
        punkte = studie["diagramm"]["punkte"]
        spread = [p_ for p_ in punkte if p_["label"].startswith("Spread ")]
        self.assertGreaterEqual(len(spread), 3)
        for punkt in spread:
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
            # Die kanonische Zelle aendern, nicht die gepoolte Summe: die
            # Seite liest bewusst genau diese Zelle.
            zelle = next(
                z for z in daten["signals"]["imbalance"]["latency"][mr.KANON_HORIZONT]
                if float(z["delay_s"]) == mr.KANON_DELAY
            )
            zelle["hit_rate"] = 0.611
            pfad.write_text(json.dumps(daten), encoding="utf-8")

            studie = next(
                s for s in mr.build_payload(wurzel)["studien"]
                if s["id"] == "imbalance-direction"
            )
            treffer = next(z for z in studie["zahlen"] if z["label"] == "Hit rate")
            self.assertEqual(treffer["wert"], 61.1)
            # Der Fliesstext haengt an derselben Quelle wie die Kennzahl.
            self.assertIn("61.1", studie["einfach"])

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
