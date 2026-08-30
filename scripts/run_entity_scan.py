"""Entity-Scan: auffaellige Wallets on-chain verknuepfen (Wallet-Graph Phase 2).

Selektiv mit Absicht: gescannt wird nie "alle", sondern eine benannte Liste,
denn jeder Scan sind ein paar Dutzend Etherscan-Seiten. Ziele kommen aus
drei Quellen, kombinierbar:

    python scripts/run_entity_scan.py --wallet 0xabc... --wallet 0xdef...
    python scripts/run_entity_scan.py --flagged 30       # auffaelligste Wallets (Insider-Score)
    python scripts/run_entity_scan.py --top-store 25     # groesste Wallets (meist Market-Maker)
    python scripts/run_entity_scan.py --loop --flagged 30   # geplante Task, taeglich

``--flagged`` ist die richtige Zielmenge: der Plan sagt "nur auffaellige
Wallets". Die groessten Wallets (``--top-store``) sind Market-Maker und
Profis, die erwartbar alle miteinander und ueber gemeinsame Infrastruktur
handeln - ein erster Lauf ueber die Top 50 machte 36 davon zu Hub-Knoten und
verschmolz keine echte Entity. Der Insider-Score hebt frische, konzentrierte
Konten heraus, deren Verknuepfung etwas bedeutet.

Im Loop-Modus (geplante Task ``MarketIntelEntityScan``) laeuft alle
``--interval-hours`` (Standard 24) ein Durchgang; die Rescan-Drossel sorgt
dafuer, dass dabei nur neue oder alt gewordene Wallets wirklich gescannt
werden. Anhalten: Datei data/entity_scan.stop anlegen. Einzelinstanz via
app/proc_lock, denn der Kanten-Rebuild vertraegt keinen zweiten Schreiber.

Je Wallet wird die Collateral-Historie (USDC/pUSD, begrenzt via Seitenbudget)
geholt und klassifiziert (app/flow_fetch + app/onchain_flows), dazu direkte
ERC-1155-Positionstransfers an den Exchanges vorbei. Externe Gegenparteien
und Positionsbewegungen landen in data/entity_graph.sqlite; danach werden
Kanten und Entities komplett neu abgeleitet (app/entity_graph): Stufe 1
fuehrt zusammen, Stufe 2 bleibt Kandidatenliste.

Braucht ETHERSCAN_API_KEY (.env oder Umgebung). Read-only: nur GET-Abrufe
oeffentlicher Transferlisten, kein Order-Pfad, keine Signaturen.
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import entity_graph as eg  # noqa: E402
from app import flow_fetch as ff  # noqa: E402
from app import proc_lock  # noqa: E402
from src import trade_store as ts  # noqa: E402

STOP_PATH = Path("data") / "entity_scan.stop"
LOCK_NAME = "entity_scan.lock"


def top_store_wallets(n: int) -> list[str]:
    """Die groessten Wallets (Notional-Summe) im Fenster des Tape-Stores."""

    pfad = ts.store_path()
    if n <= 0 or not pfad.exists():
        return []
    conn = ts.connect(pfad)
    try:
        fenster = ts.load_window(conn, days=ts.window_days())
    finally:
        conn.close()
    if fenster.empty:
        return []
    summen = fenster.groupby(fenster["wallet"].astype(str).str.lower())["notional"].sum()
    return [w for w in summen.sort_values(ascending=False).head(int(n)).index if w]


def flagged_wallets(n: int, min_score: float = 55.0) -> list[str]:
    """Die auffaelligsten Wallets aus dem Tape-Store, nach Insider-Score.

    Das ist die richtige Zielmenge fuer die Entity-Aufloesung: der Plan sagt
    "nur auffaellige Wallets". Die groessten Wallets sind Market-Maker und
    Profis, die erwartbar alle miteinander und ueber gemeinsame Infrastruktur
    handeln - ein erster Lauf ueber die Top 50 verkettete fast den ganzen
    Satz zu Hubs. Der Insider-Score (dieselbe Rechnung wie der Risk-Screen)
    hebt stattdessen frische, konzentrierte, einseitige Konten heraus, und
    genau die sind es, deren Verknuepfung etwas bedeutet.
    """

    from src import prediction_markets as md

    pfad = ts.store_path()
    if n <= 0 or not pfad.exists():
        return []
    conn = ts.connect(pfad)
    try:
        fenster = ts.load_window(conn, days=ts.window_days())
    finally:
        conn.close()
    if fenster.empty:
        return []
    try:
        scores = md.whale_wallet_risk_scores(fenster)
    except Exception as exc:  # noqa: BLE001 - keine Ziele ist besser als ein Absturz
        print(f"[warn] insider scores: {exc}", file=sys.stderr)
        return []
    if scores is None or scores.empty or "wallet" not in scores:
        return []
    treffer = scores[scores["wallet_insider_score"] >= float(min_score)]
    return [str(w).lower() for w in treffer["wallet"].head(int(n)) if str(w).strip()]


def scan_wallet(conn, wallet: str, api_key: str, pages: int, pause: float) -> str:
    """Eine Wallet scannen und festhalten; gibt die Log-Zeile zurueck."""

    flows, complete_flows, _contracts = ff.fetch_classified_flows(
        wallet, api_key, page_budget=pages, pause=pause)
    positions, complete_pos = ff.fetch_position_transfers(
        wallet, api_key, page_budget=pages, pause=pause)
    ergebnis = eg.record_scan(
        conn, wallet, flows, positions, complete=bool(complete_flows and complete_pos))
    kappe = "" if (complete_flows and complete_pos) else " (walk capped, lower bounds)"
    return (f"[scan] {wallet}: {ergebnis['external_transfers']} external transfers, "
            f"{ergebnis['position_transfers']} direct position transfers{kappe}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Link conspicuous wallets over on-chain evidence.")
    parser.add_argument("--wallet", action="append", default=[],
                        help="Wallet-Adresse; mehrfach angebbar.")
    parser.add_argument("--flagged", type=int, default=0,
                        help="Die N auffaelligsten Wallets (Insider-Score) aus dem Tape-Store scannen. "
                             "Die richtige Zielmenge fuer die Entity-Aufloesung.")
    parser.add_argument("--min-score", type=float, default=55.0,
                        help="Mindest-Insider-Score fuer --flagged (Standard 55, das 'Elevated'-Band).")
    parser.add_argument("--top-store", type=int, default=0,
                        help="Die N groessten Wallets (Notional) aus dem Tape-Store scannen. "
                             "Meist Market-Maker; fuer Entities schlechter als --flagged.")
    parser.add_argument("--pages", type=int, default=6,
                        help="Etherscan-Seitenbudget je Kontrakt und Wallet (Standard 6).")
    parser.add_argument("--pause", type=float, default=0.25,
                        help="Sekunden zwischen Etherscan-Seiten (Standard 0.25).")
    parser.add_argument("--rescan-days", type=float, default=7.0,
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


def run_pass(args, api_key: str) -> int:
    """Ein kompletter Durchgang: Ziele bestimmen, scannen, Graph neu ableiten.

    Keine Ziele sind im Loop kein Fehler: direkt nach dem Anmelden ist der
    Tape-Store oft noch leer, weil der Ingest-Task gerade erst anlaeuft.
    Der naechste Durchgang findet ihn gefuellt vor.
    """

    ziele: list[str] = []
    quellen = (list(args.wallet)
               + flagged_wallets(args.flagged, args.min_score)
               + top_store_wallets(args.top_store))
    for wallet in quellen:
        sauber = str(wallet).strip().lower()
        if sauber and sauber not in ziele:
            ziele.append(sauber)
    if not ziele:
        print("Keine Ziele: --wallet, --flagged oder --top-store nutzen (Tape-Store noetig).",
              file=sys.stderr, flush=True)
        return 0 if args.loop else 1

    conn = eg.connect(Path(args.db))
    try:
        # Beide Seiten im selben ISO-Format, damit der Textvergleich stimmt;
        # SQLites datetime('now') schreibt mit Leerzeichen statt T und
        # vergliche sich mit den gespeicherten Stempeln nur zufaellig richtig.
        schwelle = (datetime.now(timezone.utc)
                    - timedelta(days=max(0.0, float(args.rescan_days)))).isoformat(timespec="seconds")
        frisch = {
            row[0] for row in conn.execute(
                "SELECT wallet FROM scans WHERE scanned_at >= ?", (schwelle,))
        } if not args.force else set()
        uebersprungen = [w for w in ziele if w in frisch]
        for wallet in uebersprungen:
            print(f"[skip] {wallet}: scanned within the last {args.rescan_days:g} days")
        for wallet in ziele:
            if wallet in frisch:
                continue
            try:
                print(scan_wallet(conn, wallet, api_key, args.pages, args.pause), flush=True)
            except Exception as exc:  # noqa: BLE001 - eine Wallet darf den Lauf nicht kippen
                print(f"[warn] scan {wallet}: {exc}", file=sys.stderr, flush=True)
            time.sleep(max(0.0, float(args.pause)))

        kanten = eg.rebuild_edges(conn, degree_cap=args.degree_cap)
        entities = eg.assign_entities(conn)
        stand = eg.graph_stats(conn)
        kanten_text = ", ".join(f"{typ}={n}" for typ, n in sorted(kanten.items())) or "none"
        print(f"[edges] {kanten_text}")
        print(
            f"[entities] {entities['multi_wallet_entities']} multi-wallet of {entities['entities']} total; "
            f"graph: {stand['scans']} wallets scanned, {stand['hard_edges']} hard edges, "
            f"{stand['candidate_edges']} candidate edges"
        )
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
