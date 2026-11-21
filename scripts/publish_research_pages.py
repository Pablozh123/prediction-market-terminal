#!/usr/bin/env python3
"""Schreibt die vier Forschungsseiten-Nutzlasten nach public/data.

    python scripts/publish_research_pages.py
    python scripts/publish_research_pages.py --thesis-root ../multi-agent-orchestration-informational-efficiency
    python scripts/publish_research_pages.py --only reddit,prereg --check

Vier Dateien, je eine Seite:

    thesis_results.json     app/thesis_results.py     aus dem Thesis-Repo (data/results)
    reddit_sentiment.json   app/reddit_report.py      aus docs/research/reddit_sentiment
    preregistrations.json   app/prereg_register.py    aus docs/research
    literature.json         app/literature_context.py aus docs/research/ertragsquellen_2026-07-31.md

Jede Nutzlast laeuft vor dem Schreiben durch die Redaktionspruefung
(keine Wallet-Adresse). Fehlt das Thesis-Repo, wird thesis_results.json
uebersprungen und gemeldet; die anderen drei haengen nur an diesem Repo.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import literature_context, prereg_register, reddit_report, thesis_results  # noqa: E402
from app.research_payload import schreibe_nutzlast, wallet_adressen_in  # noqa: E402

SEITEN = {
    "thesis": "thesis_results.json",
    "reddit": "reddit_sentiment.json",
    "prereg": "preregistrations.json",
    "literature": "literature.json",
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", default=".", help="Projektwurzel (Vorgabe: .)")
    parser.add_argument("--publish-dir", default="public/data", help="Zielverzeichnis (Vorgabe: public/data)")
    parser.add_argument("--thesis-root", default=None, help="Thesis-Repo; sonst THESIS_ROOT oder der Nachbarordner")
    parser.add_argument("--only", default="", help="Kommagetrennt: thesis,reddit,prereg,literature")
    parser.add_argument("--check", action="store_true", help="Nur bauen und berichten, nichts schreiben")
    args = parser.parse_args(argv)

    root = Path(args.root)
    ziel = root / args.publish_dir
    gewaehlt = [s.strip() for s in args.only.split(",") if s.strip()] or list(SEITEN)
    rueck = 0

    for seite in gewaehlt:
        if seite not in SEITEN:
            print(f"unbekannte Seite: {seite}", file=sys.stderr)
            rueck = 2
            continue
        if seite == "thesis":
            wurzel = thesis_results.thesis_root(args.thesis_root, repo_root=root.resolve())
            fehlend = thesis_results.fehlende_dateien(wurzel)
            if fehlend:
                print(f"thesis: {len(fehlend)} Tabellen fehlen unter {wurzel / thesis_results.RESULTS_DIR} ({fehlend[0]} ...), uebersprungen", file=sys.stderr)
                rueck = max(rueck, 1)
                continue
            nutzlast = thesis_results.build_payload(wurzel)
            print(f"thesis: {nutzlast['zaehler']['gesamt']} Abschnitte aus {wurzel}")
        elif seite == "reddit":
            nutzlast = reddit_report.build_payload(root)
            if nutzlast.get("fehlend"):
                print(f"reddit: Artefakte fehlen: {', '.join(nutzlast['fehlend'])}", file=sys.stderr)
                rueck = max(rueck, 1)
                continue
            print(f"reddit: {nutzlast['studie']['basis']['maerkte']} Maerkte, Verdikt {nutzlast['studie']['verdikt_art']}")
        elif seite == "prereg":
            nutzlast = prereg_register.build_payload(root)
            print(f"prereg: {len(nutzlast['eintraege'])} Eintraege, Status " + ", ".join(f"{e['id']}={e['status']}" for e in nutzlast["eintraege"]))
            if nutzlast.get("fehlend"):
                print(f"prereg: fehlend {', '.join(nutzlast['fehlend'])}", file=sys.stderr)
        else:
            nutzlast = literature_context.build_payload(root)
            print(f"literature: {len(nutzlast['eigene'])} eigene Befunde, {len(nutzlast['literatur'])} Studien")

        adressen = wallet_adressen_in(nutzlast)
        if adressen:
            print(f"{seite}: Wallet-Adresse in der Nutzlast, nicht geschrieben ({adressen[0]})", file=sys.stderr)
            rueck = 2
            continue
        if args.check:
            continue
        schreibe_nutzlast(ziel / SEITEN[seite], nutzlast)
        print(f"  -> {ziel / SEITEN[seite]}")
    return rueck


if __name__ == "__main__":
    raise SystemExit(main())
