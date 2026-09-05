"""Die publizierten Nutzlasten unter ``public/data/`` gegen ihre eigenen
Invarianten.

Diese Dateien sind das, was marketintel.dev ohne laufende API ausliefert: die
Forschungsseiten lesen sie direkt. Ein Publish-Lauf, der eine davon in einen
widerspruechlichen Zustand schreibt, faellt sonst niemandem auf, bis ein Leser
zwei Zahlen nebeneinander sieht, die sich ausschliessen.

Geprueft werden ausschliesslich Beziehungen, keine Werte: die Dateien werden
neu geschrieben, die Beziehungen zwischen ihren Zahlen nicht. Ein Test, der
"acht widerlegte Studien" festschreibt, waere beim naechsten Lauf rot, ohne
dass etwas kaputt ist. Ein Test, der "der Zaehler stimmt mit der Liste
ueberein" festschreibt, ist es nur dann, wenn wirklich etwas kaputt ist.
"""

from __future__ import annotations

import json
import unittest
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[1]
DATEN = WURZEL / "public" / "data"

#: Die Verdikt-Arten, die die Oberflaeche kennt (web/js/pages/microstructure_page.js
#: faerbt und beschriftet nach ihnen). Eine unbekannte Art rendert als nichts.
VERDIKT_ARTEN = {"ja", "nein", "offen", "kontrolle"}


def _laden(name: str):
    pfad = DATEN / name
    if not pfad.exists():
        return None
    return json.loads(pfad.read_text(encoding="utf-8"))


def _zeit(wert) -> datetime | None:
    text = str(wert or "").strip()
    if not text:
        return None
    try:
        stamp = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return stamp if stamp.tzinfo else stamp.replace(tzinfo=timezone.utc)


class AllePayloadsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dateien = sorted(DATEN.glob("*.json"))
        if not self.dateien:
            self.skipTest("keine publizierten Nutzlasten in public/data/")

    def test_jede_datei_ist_lesbares_json_mit_einem_objekt(self) -> None:
        for pfad in self.dateien:
            with self.subTest(datei=pfad.name):
                inhalt = json.loads(pfad.read_text(encoding="utf-8"))
                self.assertIsInstance(inhalt, dict, "die Seiten lesen jede Nutzlast als Objekt")

    def test_jede_datei_traegt_einen_brauchbaren_stand(self) -> None:
        # Ohne Stand kann keine Seite den Zeitstempel neben ihre Zahlen
        # schreiben, und genau das verlangt dieses Haus an jeder Zahl.
        jetzt = datetime.now(timezone.utc)
        for pfad in self.dateien:
            with self.subTest(datei=pfad.name):
                inhalt = json.loads(pfad.read_text(encoding="utf-8"))
                # Der Publish-Lauf schreibt stand_utc. Die Datei des Arb-Scanners
                # (Schema arb_scan/1, aus dem Repo prediction-alpha-bot) und
                # unser Aufloesungslauf darueber (arb_resolutions/1) nennen den
                # Stempel generated_at, und die Seite liest ihn unter dem Namen.
                stamp = _zeit(inhalt.get("stand_utc")) or _zeit(inhalt.get("generated_at"))
                self.assertIsNotNone(stamp, f"{pfad.name} hat weder ein lesbares stand_utc noch ein lesbares generated_at")
                # Eine Stunde Toleranz fuer Uhren, die auseinanderlaufen.
                self.assertLess(stamp, jetzt + timedelta(hours=1),
                                f"{pfad.name} traegt einen Stand in der Zukunft")


class MicrostructurePayloadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.payload = _laden("microstructure.json")
        if self.payload is None:
            self.skipTest("microstructure.json ist nicht publiziert")
        self.studien = self.payload.get("studien") or []

    def test_jede_studie_traegt_ihre_pflichtfelder(self) -> None:
        self.assertTrue(self.studien, "eine Nutzlast ohne Studien traegt nichts")
        for studie in self.studien:
            with self.subTest(studie=studie.get("id")):
                for feld in ("id", "frage", "verdikt", "verdikt_art"):
                    self.assertTrue(str(studie.get(feld) or "").strip(), f"{feld} fehlt")
                self.assertIn(studie["verdikt_art"], VERDIKT_ARTEN)

    def test_die_ids_sind_eindeutig_und_adresstauglich(self) -> None:
        # Aus der ID wird das Adresssegment der Studienseite und der Anker im
        # Terminal. Zwei gleiche IDs waeren zwei Seiten unter einer Adresse.
        ids = [str(s.get("id")) for s in self.studien]
        self.assertEqual(len(ids), len(set(ids)))
        for wert in ids:
            with self.subTest(id=wert):
                self.assertRegex(wert, r"^[a-z0-9]+(-[a-z0-9]+)*$")

    def test_der_zaehler_stimmt_mit_den_studien_ueberein(self) -> None:
        # Die Startseite schreibt ihre Unterzeile aus dem Zaehler und ihr
        # Verdikt-Board aus der Liste. Weichen die beiden ab, widerspricht die
        # Seite sich selbst in zwei benachbarten Zeilen.
        zaehler = self.payload.get("zaehler") or {}
        gezaehlt = Counter(s.get("verdikt_art") for s in self.studien)
        self.assertEqual(int(zaehler.get("gesamt", -1)), len(self.studien))
        for art in VERDIKT_ARTEN:
            with self.subTest(art=art):
                self.assertEqual(int(zaehler.get(art, 0)), gezaehlt.get(art, 0))

    def test_jeder_genannte_pfad_liegt_wirklich_im_repo(self) -> None:
        # Bericht, Modul und Bild werden verlinkt. Ein Link auf eine Datei,
        # die es nicht gibt, behauptet einen Beleg, den niemand oeffnen kann.
        for studie in self.studien:
            for feld in ("report", "modul", "bild"):
                pfad = str(studie.get(feld) or "").strip()
                if not pfad:
                    continue
                with self.subTest(studie=studie.get("id"), feld=feld):
                    self.assertTrue((WURZEL / pfad).is_file(), f"{pfad} fehlt")

    def test_eine_studie_ohne_basis_behauptet_kein_n(self) -> None:
        # basis traegt n und Fenster. Ein leeres Objekt ist erlaubt, ein
        # Objekt mit einer Null darin nicht: "0 Beobachtungen" liest sich wie
        # eine Messung.
        for studie in self.studien:
            basis = studie.get("basis") or {}
            with self.subTest(studie=studie.get("id")):
                for schluessel, wert in basis.items():
                    if isinstance(wert, (int, float)) and not isinstance(wert, bool):
                        self.assertGreater(wert, 0, f"{schluessel} ist null")


class RunsPayloadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.payload = _laden("runs.json")
        if self.payload is None:
            self.skipTest("runs.json ist nicht publiziert")
        self.aggregat = self.payload.get("aggregat") or {}

    def test_die_zahl_der_laeufe_stimmt_mit_der_liste(self) -> None:
        self.assertEqual(int(self.aggregat.get("n_runs", -1)), len(self.payload.get("runs") or []))

    def test_gewonnen_verloren_offen_ergeben_die_wetten(self) -> None:
        teile = sum(int(self.aggregat.get(k, 0)) for k in ("gewonnen", "verloren", "offen"))
        self.assertEqual(teile, int(self.aggregat.get("n_wetten", -1)))


class WalletLedgerPayloadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.payload = _laden("wallet_ledger.json")
        if self.payload is None:
            self.skipTest("wallet_ledger.json ist nicht publiziert")
        self.aggregat = self.payload.get("aggregat") or {}
        self.positionen = self.aggregat.get("positionen") or {}
        if not self.positionen:
            self.skipTest("keine Positionsaufteilung in wallet_ledger.json")

    def test_die_aufteilung_ergibt_die_zahl_der_maerkte(self) -> None:
        self.assertEqual(sum(int(v) for v in self.positionen.values()),
                         int(self.aggregat.get("n_maerkte", -1)))

    def test_die_einzelzaehler_stimmen_mit_der_aufteilung(self) -> None:
        p = self.positionen
        self.assertEqual(int(self.aggregat.get("positionen_gewonnen", -1)), int(p.get("won", 0)))
        self.assertEqual(int(self.aggregat.get("positionen_flat", -1)), int(p.get("flat", 0)))
        self.assertEqual(int(self.aggregat.get("positionen_wertlos", -1)), int(p.get("worthless", 0)))
        self.assertEqual(int(self.aggregat.get("positionen_offen", -1)), int(p.get("open", 0)))
        # Wertlose Positionen sind Verluste, und die Seite zaehlt sie so.
        self.assertEqual(int(self.aggregat.get("positionen_verloren", -1)),
                         int(p.get("lost", 0)) + int(p.get("worthless", 0)))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
