"""Whale-Tape-Ingest: fuellt den persistenten Trade-Store (src/trade_store.py).

Der Risk-Screen sieht live rund einen Tag Tape; Cluster bauen sich ueber
Wochen auf. Dieser Runner holt in Abstaenden die juengsten Whale-Prints der
Polymarket Data-API und schreibt sie dedupliziert nach
data/trade_store.sqlite (TRADE_STORE_PATH). load_deep_tape der API reichert
sein Live-Tape damit an; ohne laufenden Runner aendert sich am Screen nichts.

Run:
    python scripts/run_trade_ingest.py             # Schleife, Standard alle 15 min
    python scripts/run_trade_ingest.py --once      # ein Zyklus (zum Testen)
    python scripts/run_trade_ingest.py --interval-min 10 --pages 4

Anhalten: Datei data/trade_ingest.stop anlegen (wie beim Alert-Scanner).

Kadenz-Rechnung: bei $1.000 Mindestbetrag traegt das Band grob acht
Tausenderseiten pro Tag; vier Seiten je Zyklus alle 15 Minuten ueberlappen
also weit mehr, als sie auslassen. Ein Loch entsteht erst, wenn der Runner
laenger als etwa einen halben Tag steht — und genau das macht der
days-with-data-Vermerk im Store sichtbar.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import prediction_markets as md
from src import trade_store as ts

STOP_PATH = Path("data") / "trade_ingest.stop"


def run_cycle(min_cash: float, pages: int, keep_days: float) -> None:
    conn = ts.connect()
    try:
        try:
            ergebnis = ts.ingest_once(conn, min_cash=min_cash, pages=pages)
        except md.MarketDataError as exc:
            print(f"[warn] ingest: feed unavailable: {exc}")
            return
        geloescht = ts.prune(conn, keep_days=keep_days)
        stats = ts.store_stats(conn)
        vermerk = ergebnis["coverage"]
        # Der Grund gehoert in die Zeile: "feed stopped early" ohne Ursache
        # liest sich wie ein ruhiger Markt, dabei war es beim ersten Live-Lauf
        # eine DNS-Sperre des Providers (NXDOMAIN fuer *.polymarket.com).
        abbruch = ""
        if vermerk.get("truncated_by_error"):
            abbruch = f" (feed stopped early: {str(vermerk.get('error') or '')[:200]})"
        print(
            f"[ingest] fetched={ergebnis['fetched']} new={ergebnis['new']} "
            f"pruned={geloescht} store_rows={stats['rows']} "
            f"span={stats['first_utc']}..{stats['last_utc']}{abbruch}"
        )
    finally:
        try:
            conn.close()
        except Exception:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--once", action="store_true", help="ein Zyklus, dann Ende")
    parser.add_argument("--interval-min", type=float, default=15.0,
                        help="Minuten zwischen Zyklen (Standard 15)")
    parser.add_argument("--min-cash", type=float, default=1000.0,
                        help="Mindest-Notional je Print (Standard 1000, wie der Netzwerk-Tape)")
    parser.add_argument("--pages", type=int, default=4,
                        help="Data-API-Seiten je Zyklus a 1000 Prints (Standard 4)")
    parser.add_argument("--keep-days", type=float, default=45.0,
                        help="Aufbewahrung in Tagen (Standard 45)")
    args = parser.parse_args()

    if args.once:
        run_cycle(args.min_cash, args.pages, args.keep_days)
        return 0

    print(f"[ingest] loop every {args.interval_min:g} min; stop file: {STOP_PATH}")
    while True:
        if STOP_PATH.exists():
            print("[ingest] stop file found, exiting")
            return 0
        run_cycle(args.min_cash, args.pages, args.keep_days)
        # In kleinen Schritten schlafen, damit die Stop-Datei zeitnah wirkt.
        rest = max(60.0, args.interval_min * 60.0)
        while rest > 0:
            if STOP_PATH.exists():
                print("[ingest] stop file found, exiting")
                return 0
            schritt = min(15.0, rest)
            time.sleep(schritt)
            rest -= schritt


if __name__ == "__main__":
    raise SystemExit(main())
