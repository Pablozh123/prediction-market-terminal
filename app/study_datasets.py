"""Der Datensatz zu einer Studie, verlinkt statt nur erwaehnt.

Jede Studienkarte verlinkt bisher den Bericht und das Modul. Was fehlt, ist
das Dritte, ohne das man nichts nachrechnen kann: die Zahlen selbst. Zu jedem
Bericht unter ``docs/research/`` liegt ein Datensatz mit demselben
Namensstamm, meist als CSV und als JSON, in einem Fall nur als JSON.

Verlinkt wird nur, was wirklich da liegt. Ein toter Link auf eine CSV, die es
zu dieser Studie nie gab, waere schlimmer als kein Link: er behauptet einen
Beleg, den niemand oeffnen kann. Deshalb prueft dieses Modul im Repo nach,
und deshalb steht es hier und nicht im Frontend, das nichts pruefen kann.

Zwei Aufrufer, mit Absicht:

* ``app/microstructure_report.py`` schreibt das Feld beim Publizieren mit, so
  dass eine ausgelieferte Nutzlast es von sich aus traegt.
* ``api/server.py`` fuellt es beim Lesen nach, damit auch eine Nutzlast, die
  vor dieser Aenderung geschrieben wurde, die Links schon zeigt.

Streamlit-frei, ohne Abhaengigkeiten.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

#: Welche Endungen als Datensatz gelten, in der Reihenfolge, in der sie
#: angeboten werden. CSV zuerst: wer nachrechnen will, oeffnet sie zuerst.
DATASET_SUFFIXES = ((".csv", "CSV"), (".json", "JSON"))

#: Wo ein Datensatz liegen darf. Ein Bericht ausserhalb dieses Ordners
#: bekommt keine Links: der Pfad kommt aus einer Nutzlast, und eine Nutzlast
#: ist eine Datei, die auch anders aussehen kann als erwartet.
DATASET_DIR = "docs/research"


def _sicher(pfad: Any) -> str:
    """Repo-relativer Pfad unter DATASET_DIR, sonst leer.

    Kein ``..``, kein absoluter Pfad, kein anderer Ordner. Der Wert kommt aus
    einer JSON-Datei, also wird er wie eine Eingabe behandelt.
    """

    roh = str(pfad or "").strip().replace("\\", "/")
    if not roh or roh.startswith("/") or ":" in roh:
        return ""
    teile = [t for t in roh.split("/") if t]
    if any(t in ("..", ".") for t in teile):
        return ""
    gemeinsam = "/".join(teile)
    if not gemeinsam.startswith(DATASET_DIR + "/"):
        return ""
    return gemeinsam


def dataset_links(report: Any, root: Path | str = ROOT) -> list[dict[str, str]]:
    """Die vorhandenen Datensaetze zu einem Berichtspfad.

    ``[{"format": "CSV", "path": "docs/research/x.csv"}, ...]``, leer wenn
    keiner existiert.
    """

    rel = _sicher(report)
    if not rel:
        return []
    basis = Path(root)
    stamm = rel.rsplit(".", 1)[0] if "." in rel.rsplit("/", 1)[-1] else rel
    treffer: list[dict[str, str]] = []
    for endung, wort in DATASET_SUFFIXES:
        kandidat = stamm + endung
        if (basis / kandidat).is_file():
            treffer.append({"format": wort, "path": kandidat})
    return treffer


def with_datasets(payload: Any, root: Path | str = ROOT) -> Any:
    """Jede Studie der Nutzlast um ``daten`` ergaenzen, ohne sie zu veraendern.

    Traegt eine Studie das Feld schon (weil der Publish-Lauf es geschrieben
    hat), bleibt es stehen. Ist die Nutzlast keine Studienliste, kommt sie
    unveraendert zurueck.
    """

    if not isinstance(payload, dict):
        return payload
    studien = payload.get("studien")
    if not isinstance(studien, list):
        return payload
    neu = []
    beruehrt = False
    for studie in studien:
        if not isinstance(studie, dict) or studie.get("daten") is not None:
            neu.append(studie)
            continue
        links = dataset_links(studie.get("report"), root)
        if not links:
            neu.append(studie)
            continue
        kopie = dict(studie)
        kopie["daten"] = links
        neu.append(kopie)
        beruehrt = True
    if not beruehrt:
        return payload
    kopie_payload = dict(payload)
    kopie_payload["studien"] = neu
    return kopie_payload
