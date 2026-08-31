"""Der Entity-Scan als Bibliothek: eine Runde ueber benannte oder auffaellige Wallets.

Die Logik lebte in ``scripts/run_entity_scan.py`` und ist hierher gezogen,
weil der Scan auf zwei Arten laeuft und beide dieselbe Runde brauchen:

- lokal als geplante Task (``scripts/run_entity_scan.py``, jetzt ein duenner
  CLI-Mantel mit proc_lock, Stop-Datei und Schleife), und
- auf dem Deploy-Host IM API-ProzESS (``api/server.py``,
  ``ENTITY_SCAN_INTERVAL_H``): dort gibt es keinen Taskplaner, die
  Graph-Datei liegt auf dem gemounteten Volume, und ein Worker-Thread ist
  das Muster, mit dem Flag-Sampler und Copy-Daemon dort laengst laufen.

Zielmengen (kombinierbar): eine benannte Liste, die auffaelligsten Wallets
nach Insider-Score (``flagged`` - die richtige Population, der Plan sagt
"nur auffaellige Wallets") oder die groessten nach Notional (``top_store`` -
meist Market-Maker, fuer Entities die falsche Population und nur fuer
gezielte Blicke gedacht).

Je Wallet wird die Collateral-Historie (USDC/pUSD, begrenzt via Seitenbudget)
geholt und klassifiziert (app/flow_fetch + app/onchain_flows), dazu direkte
ERC-1155-Positionstransfers an den Exchanges vorbei. Danach werden Kanten und
Entities komplett neu abgeleitet (app/entity_graph): Stufe 1 fuehrt zusammen,
Stufe 2 bleibt Kandidatenliste.

Read-only: nur GET-Abrufe oeffentlicher Transferlisten, kein Order-Pfad,
keine Signaturen. Fortschritt geht auf stdout, wie bei den anderen
Hintergrundjobs des Repos: auf Railway IST stdout das Log.
"""

from __future__ import annotations

import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from app import entity_graph as eg
from app import flow_fetch as ff
from src import trade_store as ts

DEFAULT_MIN_SCORE = 55.0
DEFAULT_PAGES = 6
DEFAULT_PAUSE = 0.25
DEFAULT_RESCAN_DAYS = 7.0
#: So viele Fan-out-Lookups darf ein Durchgang machen (je Adresse einmalig,
#: danach gecacht). Der Deckel haelt die Etherscan-Last planbar; was diesmal
#: nicht drankommt, kommt im naechsten Durchgang dran.
DEFAULT_FANOUT_LOOKUPS = 25


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


def flagged_wallets(n: int, min_score: float = DEFAULT_MIN_SCORE) -> list[str]:
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


def enrich_fanouts(
    conn,
    api_key: str,
    *,
    degree_cap: int = eg.DEFAULT_MAX_SHARED_WALLETS,
    max_lookups: int = DEFAULT_FANOUT_LOOKUPS,
    pause: float = DEFAULT_PAUSE,
    fanout=None,
) -> int:
    """Globalen Fan-out der potenziell harten geteilten Gegenparteien nachschlagen.

    Der lokale Grad einer geteilten Finanzierungsquelle hat eine Luecke: ein
    Router, der on-chain tausende Konten bedient, aber zufaellig nur zwei der
    gescannten, sieht lokal wie eine private Operator-Quelle aus. Fuer jede
    Adresse, die eine harte Kante ERZEUGEN wuerde, wird deshalb einmalig
    nachgeschlagen, wie viele verschiedene Partner sie ueberhaupt hat; das
    Ergebnis landet gecacht im Graphen, und ``rebuild_edges`` stuft busy
    Adressen auf Kandidat zurueck. ``fanout`` ist der Abruf und existiert,
    damit die Runde netzfrei pruefbar bleibt.
    """

    hole = fanout or ff.counterparty_fanout
    offen = eg.pending_fanout_counterparties(conn, degree_cap)
    for gegen in offen[:max(0, int(max_lookups))]:
        try:
            info = hole(gegen, api_key, pause=pause)
        except Exception as exc:  # noqa: BLE001 - ein Lookup darf den Lauf nicht kippen
            print(f"[warn] fanout {gegen}: {exc}", file=sys.stderr, flush=True)
            continue
        eg.record_fanout(conn, gegen, info)
        grenze = "+" if not info.get("complete") else ""
        print(f"[fanout] {gegen}: {info.get('partners', 0)}{grenze} partners on-chain", flush=True)
    if len(offen) > int(max_lookups):
        print(f"[fanout] {len(offen) - int(max_lookups)} counterparties deferred to the next pass", flush=True)
    return min(len(offen), int(max_lookups))


def scan_pass(
    db_path: Path | str,
    api_key: str,
    *,
    wallets: Iterable[str] = (),
    flagged: int = 0,
    min_score: float = DEFAULT_MIN_SCORE,
    top_store: int = 0,
    pages: int = DEFAULT_PAGES,
    pause: float = DEFAULT_PAUSE,
    rescan_days: float = DEFAULT_RESCAN_DAYS,
    force: bool = False,
    degree_cap: int = eg.DEFAULT_MAX_SHARED_WALLETS,
) -> dict[str, Any]:
    """Ein kompletter Durchgang: Ziele bestimmen, scannen, Graph neu ableiten.

    Keine Ziele sind kein Fehler, sondern ein Zustand: direkt nach dem Start
    ist der Tape-Store oft noch leer, weil der Ingest gerade erst anlaeuft;
    der naechste Durchgang findet ihn gefuellt vor. Der Rueckgabewert sagt,
    was der Durchgang gesehen und getan hat - der Aufrufer entscheidet, ob
    ein leerer Durchgang bei ihm ein Fehlercode ist (CLI-Einmallauf) oder
    nicht (Schleife, Worker).
    """

    ergebnis: dict[str, Any] = {"targets": 0, "scanned": 0, "skipped": 0, "errors": 0,
                                "edges": {}, "entities": {}, "stats": {}}
    ziele: list[str] = []
    quellen = (list(wallets)
               + flagged_wallets(flagged, min_score)
               + top_store_wallets(top_store))
    for wallet in quellen:
        sauber = str(wallet).strip().lower()
        if sauber and sauber not in ziele:
            ziele.append(sauber)
    ergebnis["targets"] = len(ziele)
    if not ziele:
        print("Keine Ziele: wallets, flagged oder top_store angeben (Tape-Store noetig).",
              file=sys.stderr, flush=True)
        return ergebnis

    conn = eg.connect(Path(db_path))
    try:
        # Beide Seiten im selben ISO-Format, damit der Textvergleich stimmt;
        # SQLites datetime('now') schreibt mit Leerzeichen statt T und
        # vergliche sich mit den gespeicherten Stempeln nur zufaellig richtig.
        schwelle = (datetime.now(timezone.utc)
                    - timedelta(days=max(0.0, float(rescan_days)))).isoformat(timespec="seconds")
        frisch = {
            row[0] for row in conn.execute(
                "SELECT wallet FROM scans WHERE scanned_at >= ?", (schwelle,))
        } if not force else set()
        for wallet in ziele:
            if wallet in frisch:
                ergebnis["skipped"] += 1
                print(f"[skip] {wallet}: scanned within the last {rescan_days:g} days")
                continue
            try:
                print(scan_wallet(conn, wallet, api_key, int(pages), float(pause)), flush=True)
                ergebnis["scanned"] += 1
            except Exception as exc:  # noqa: BLE001 - eine Wallet darf den Lauf nicht kippen
                ergebnis["errors"] += 1
                print(f"[warn] scan {wallet}: {exc}", file=sys.stderr, flush=True)
            time.sleep(max(0.0, float(pause)))

        try:
            ergebnis["fanout_lookups"] = enrich_fanouts(
                conn, api_key, degree_cap=int(degree_cap), pause=float(pause))
        except Exception as exc:  # noqa: BLE001 - der Rebuild laeuft auch ohne den Blick
            print(f"[warn] fanout enrichment: {exc}", file=sys.stderr, flush=True)
        kanten = eg.rebuild_edges(conn, degree_cap=int(degree_cap))
        entities = eg.assign_entities(conn)
        stand = eg.graph_stats(conn)
        ergebnis.update({"edges": kanten, "entities": entities, "stats": stand})
        kanten_text = ", ".join(f"{typ}={n}" for typ, n in sorted(kanten.items())) or "none"
        print(f"[edges] {kanten_text}")
        print(
            f"[entities] {entities['multi_wallet_entities']} multi-wallet of {entities['entities']} total; "
            f"graph: {stand['scans']} wallets scanned, {stand['hard_edges']} hard edges, "
            f"{stand['candidate_edges']} candidate edges",
            flush=True,
        )
    finally:
        conn.close()
    return ergebnis
