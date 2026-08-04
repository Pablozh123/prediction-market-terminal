"""Schreibt die Microstructure-Studien nach public/data/microstructure.json.

Die uebrigen Dateien in public/data liefert der Thesis-Lauf per
`daily_review_run --publish-dir`. Microstructure ist der Gegenfall: die
Quelle sind die Reports in docs/research dieses Repos, also veroeffentlicht
dieses Repo sie auch selbst.

Aufruf:

    python scripts/publish_microstructure.py
    python scripts/publish_microstructure.py --publish-dir public/data --check
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.microstructure_report import build_payload  # noqa: E402

ZIEL = "microstructure.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", default=".",
        help="Projektwurzel, unter der docs/research liegt (Vorgabe: .)",
    )
    parser.add_argument(
        "--publish-dir", default="public/data",
        help="Zielverzeichnis (Vorgabe: public/data)",
    )
    parser.add_argument(
        "--check", action="store_true",
        help="Nur pruefen und berichten, nichts schreiben",
    )
    args = parser.parse_args(argv)

    nutzlast = build_payload(args.root)
    studien = nutzlast["studien"]
    fehlend = nutzlast["fehlend"]

    if fehlend:
        print(f"Fehlende Studiendateien: {', '.join(sorted(set(fehlend)))}", file=sys.stderr)
    if not studien:
        print("Keine Studie gefunden, nichts zu veroeffentlichen.", file=sys.stderr)
        return 1

    z = nutzlast["zaehler"]
    print(f"{z['gesamt']} Studien: {z['nein']} widerlegt, {z['ja']} bestaetigt, {z['offen']} offen")

    if args.check:
        return 1 if fehlend else 0

    ziel = Path(args.root) / args.publish_dir
    ziel.mkdir(parents=True, exist_ok=True)
    pfad = ziel / ZIEL
    with pfad.open("w", encoding="utf-8") as fh:
        json.dump(nutzlast, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    print(f"geschrieben: {pfad}")
    return 1 if fehlend else 0


if __name__ == "__main__":
    raise SystemExit(main())
