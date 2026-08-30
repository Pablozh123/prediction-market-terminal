"""Entity-Scan: auffaellige Wallets on-chain verknuepfen (Wallet-Graph Phase 2).

Duenner CLI-Mantel um ``app/entity_scan.py`` - die Runde selbst (Ziele
bestimmen, scannen, Graph neu ableiten) lebt dort, weil sie auf dem
Deploy-Host auch ohne dieses Skript laeuft (``ENTITY_SCAN_INTERVAL_H`` im
API-Prozess, siehe api/server.py). Hier kommen nur die Dinge dazu, die eine
geplante Task auf einem Rechner braucht: Argumente, Einzelinstanz-Lock,
Stop-Datei, Schleife.

    python scripts/run_entity_scan.py --wallet 0xabc... --wallet 0xdef...
    python scripts/run_entity_scan.py --flagged 30       # auffaelligste Wallets (Insider-Score)
    python scripts/run_entity_scan.py --top-store 25     # groesste Wallets (meist Market-Maker)
    python scripts/run_entity_scan.py --loop --flagged 30   # geplante Task, taeglich

``--flagged`` ist die richtige Zielmenge: der Plan sagt "nur auffaellige
Wallets". Die groessten Wallets (``--top-store``) sind Market-Maker und
Profis, die erwartbar alle miteinander und ueber gemeinsame Infrastruktur
handeln - ein erster Lauf ueber die Top 50 machte 36 davon zu Hub-Knoten und
verschmolz keine echte Entity.

Im Loop-Modus (geplante Task ``MarketIntelEntityScan``) laeuft alle
``--interval-hours`` (Standard 24) ein Durchgang; die Rescan-Drossel sorgt
dafuer, dass dabei nur neue oder alt gewordene Wallets wirklich gescannt
werden. Anhalten: Datei data/entity_scan.stop anlegen. Einzelinstanz via
app/proc_lock, denn der Kanten-Rebuild vertraegt keinen zweiten Schreiber.

Braucht ETHERSCAN_API_KEY (.env oder Umgebung). Read-only.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import entity_graph as eg  # noqa: E402
from app import entity_scan as es  # noqa: E402
from app import flow_fetch as ff  # noqa: E402
from app import proc_lock  # noqa: E402

STOP_PATH = Path("data") / "entity_scan.stop"
LOCK_NAME = "entity_scan.lock"


def run_pass(args, api_key: str) -> int:
    ergebnis = es.scan_pass(
        Path(args.db), api_key,
        wallets=list(args.wallet), flagged=args.flagged, min_score=args.min_score,
        top_store=args.top_store, pages=args.pages, pause=args.pause,
        rescan_days=args.rescan_days, force=args.force, degree_cap=args.degree_cap,
    )
    # Im Einmallauf ist "keine Ziele" ein Fehler (der Aufrufer wollte etwas
    # scannen); in der Schleife ist es der normale Zustand kurz nach dem
    # Anmelden, solange der Ingest den Store noch fuellt.
    if ergebnis["targets"] == 0 and not args.loop:
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Link conspicuous wallets over on-chain evidence.")
    parser.add_argument("--wallet", action="append", default=[],
                        help="Wallet-Adresse; mehrfach angebbar.")
    parser.add_argument("--flagged", type=int, default=0,
                        help="Die N auffaelligsten Wallets (Insider-Score) aus dem Tape-Store scannen. "
                             "Die richtige Zielmenge fuer die Entity-Aufloesung.")
    parser.add_argument("--min-score", type=float, default=es.DEFAULT_MIN_SCORE,
                        help="Mindest-Insider-Score fuer --flagged (Standard 55, das 'Elevated'-Band).")
    parser.add_argument("--top-store", type=int, default=0,
                        help="Die N groessten Wallets (Notional) aus dem Tape-Store scannen. "
                             "Meist Market-Maker; fuer Entities schlechter als --flagged.")
    parser.add_argument("--pages", type=int, default=es.DEFAULT_PAGES,
                        help="Etherscan-Seitenbudget je Kontrakt und Wallet (Standard 6).")
    parser.add_argument("--pause", type=float, default=es.DEFAULT_PAUSE,
                        help="Sekunden zwischen Etherscan-Seiten (Standard 0.25).")
    parser.add_argument("--rescan-days", type=float, default=es.DEFAULT_RESCAN_DAYS,
                        help="Wallets, deren Scan juenger ist, werden uebersprungen (Standard 7).")
    parser.add_argument("--force", action="store_true", help="Auch frisch gescannte Wallets erneut scannen.")
    parser.add_argument("--degree-cap", type=int, default=eg.DEFAULT_MAX_SHARED_WALLETS,
                        help="Bis zu so vielen Wallets je Gegenpartei noch harte Kante (Standard 2).")
    parser.add_argument("--db", default=str(eg.DEFAULT_GRAPH_PATH), help="Pfad der Graph-Datenbank.")
    parser.add_argument("--loop", action="store_true",
                        help="Endlosschleife: alle --interval-hours ein Durchgang (fuer die geplante Task).")
    parser.add_argument("--interval-hours", type=float, default=24.0,
                        help="Stunden zwischen Durchgaengen im Loop (Standard 24).")
    args = parser.parse_args()

    api_key = ff.load_api_key()
    if not api_key:
        print("Kein API-Key gefunden (ETHERSCAN_API_KEY in .env oder Umgebung).", file=sys.stderr)
        return 1

    # Einzelinstanz fuer BEIDE Modi: rebuild_edges loescht und schreibt den
    # ganzen Kantenbestand, ein zweiter Schreiber mitten darin hinterlaesst
    # einen halben Graphen. Laeuft die geplante Task, sagt ein manueller
    # Start das klar, statt still hineinzuschreiben.
    try:
        lock = proc_lock.acquire(Path(args.db).parent, name=LOCK_NAME)
    except proc_lock.AlreadyRunning as exc:
        print(str(exc), file=sys.stderr)
        return 1
    try:
        if not args.loop:
            return run_pass(args, api_key)
        print(f"[entity-scan] loop every {args.interval_hours:g} h; stop file: {STOP_PATH}", flush=True)
        while True:
            if STOP_PATH.exists():
                STOP_PATH.unlink(missing_ok=True)
                print("[entity-scan] stop file found, exiting")
                return 0
            try:
                run_pass(args, api_key)
            except Exception as exc:  # noqa: BLE001 - ein Durchgang darf die Task nicht kippen
                print(f"[warn] entity scan pass failed: {exc}", file=sys.stderr, flush=True)
            rest = max(60.0, float(args.interval_hours) * 3600.0)
            while rest > 0:
                if STOP_PATH.exists():
                    STOP_PATH.unlink(missing_ok=True)
                    print("[entity-scan] stop file found, exiting")
                    return 0
                schritt = min(15.0, rest)
                time.sleep(schritt)
                rest -= schritt
    finally:
        proc_lock.release(lock)


if __name__ == "__main__":
    raise SystemExit(main())
