"""Read-only Sichten auf den Book/Tape-Recorder und die Imbalance-Studie.

UI-freie Helfer fuer den Microstructure-Workspace: Recorder-Status und
Dateibestand aus ``data/microstructure`` sowie die rollierende
Out-of-Sample-Wiederholung der Imbalance-Auswertung auf den live
gesammelten Buechern (gleiche Definition wie die Mai-Studie in
``src/imbalance_study.py``; Trefferquote bedingt auf Bewegung,
Wilson-Untergrenze). Kein Order-Pfad, keine Netzabrufe.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src import imbalance_study as ims

REPO_ROOT = Path(__file__).resolve().parents[1]
MICRO_DIR_DEFAULT = REPO_ROOT / "data" / "microstructure"
RESEARCH_DIR_DEFAULT = REPO_ROOT / "docs" / "research"

#: Unterhalb dieser Paar-Zahl zeigt die Seite "sammelt noch" statt Statistik.
MIN_PAIRS_FOR_STATS = 200


def recorder_status(micro_dir: Path = MICRO_DIR_DEFAULT) -> dict[str, Any] | None:
    """Letzter Pass des Recorders (recorder_status.json) oder None."""

    path = Path(micro_dir) / "recorder_status.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def recorder_files(micro_dir: Path = MICRO_DIR_DEFAULT) -> list[dict[str, Any]]:
    """Tagesdateien des Recorders (Groesse/Alter), neueste zuerst."""

    directory = Path(micro_dir)
    if not directory.exists():
        return []
    rows: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*_*.csv"), reverse=True):
        try:
            stat = path.stat()
        except OSError:
            continue
        rows.append(
            {
                "datei": path.name,
                "art": "books" if path.name.startswith("books_") else "trades",
                "groesse_kb": round(stat.st_size / 1024.0, 1),
                "geaendert_utc": datetime.fromtimestamp(
                    stat.st_mtime, tz=timezone.utc
                ).strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
        )
    return rows


def rolling_imbalance(
    micro_dir: Path = MICRO_DIR_DEFAULT, horizon_s: int = 300
) -> dict[str, Any]:
    """Imbalance-Buckets ueber ALLE bisher gesammelten Recorder-Buecher.

    Rollierend: jeder Aufruf liest den aktuellen Datenstand; die Seite
    cached das Ergebnis nur kurz. Leergebnis ist fail-safe ({rows: []}).
    """

    directory = Path(micro_dir)
    leer = {"horizon_s": horizon_s, "n_tokens": 0, "n_pairs": 0, "rows": []}
    if not directory.exists() or not list(directory.glob("books_*.csv")):
        return leer
    series = ims.load_recorder(str(directory))
    if not series:
        return leer
    results = ims.analyse(series)
    rows = results.get(horizon_s, [])
    return {
        "horizon_s": horizon_s,
        "n_tokens": len(series),
        "n_pairs": sum(int(r.get("n", 0)) for r in rows),
        "rows": rows,
    }


def study_reports(research_dir: Path = RESEARCH_DIR_DEFAULT) -> list[dict[str, Any]]:
    """Eingefrorene Studien-Reports (Markdown + PNG) unter docs/research."""

    directory = Path(research_dir)
    if not directory.exists():
        return []
    reports: list[dict[str, Any]] = []
    for md_path in sorted(directory.glob("*.md"), reverse=True):
        png_path = md_path.with_suffix(".png")
        reports.append(
            {
                "stem": md_path.stem,
                "md_path": str(md_path),
                "png_path": str(png_path) if png_path.exists() else None,
            }
        )
    return reports
