"""Cluster-Probe: eine benannte Wallet-Menge durch alle Verknuepfungs-Signale schicken.

Das Erfolgskriterium aus dem Wallet-Graph-Plan ("haette das System den
US-Iran-Ring gefunden?") als Werkzeug: man gibt die Konten eines bekannten
oder vermuteten Rings herein, und heraus kommt, welche Signalklassen auf
ihnen feuern - und welche nicht. Ein Ring, der nur auf der lockersten
Co-Trading-Sprosse haengt, ist ein anderes Ergebnis als einer mit
Funding-Kanten und Fingerprints, und genau diese Trennung ist der Befund.

    python scripts/run_cluster_probe.py --wallet 0xabc... --wallet 0xdef...
    python scripts/run_cluster_probe.py --file ring.txt --onchain

Die Handelshistorie kommt je Wallet aus der oeffentlichen Data-API
(``/trades?user=``), also auch fuer Zeitraeume weit vor dem eigenen
Tape-Store. ``--onchain`` scannt zusaetzlich die Collateral- und
Positions-Historie (Etherscan, braucht ETHERSCAN_API_KEY) in eine EIGENE
Probe-Datenbank (Standard data/cluster_probe.sqlite), damit ein Testlauf
den produktiven Entity-Graphen nicht mit historischen Faellen mischt.

Read-only; Sprachregel wie ueberall: Signale sind Rechercheanlaesse,
keine Feststellungen.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import behavior as bhv  # noqa: E402
from app import entity_graph as eg  # noqa: E402
from app import flow_fetch as ff  # noqa: E402
from app import suspicion as susp  # noqa: E402
from src import prediction_markets as md  # noqa: E402

DEFAULT_PROBE_DB = Path("data") / "cluster_probe.sqlite"
PAGE_SIZE = 1000

#: Die strenge und die lockerste Sprosse der Regel-Leiter des Risk-Screens.
#: Beide werden immer berichtet: "nur unter der lockersten Regel verbunden"
#: ist ein eigener Befund, kein halber.
STRICT_RULE = dict(window_minutes=5.0, min_shared=3, min_pair_notional=10_000.0)
LOOSE_RULE = dict(window_minutes=None, min_shared=2)


def fetch_wallet_tape(wallet: str, pages: int, fetch=None) -> tuple[pd.DataFrame, bool]:
    """Handelshistorie einer Wallet, seitenweise; (frame, truncated).

    ``truncated`` heisst: die letzte gelesene Seite war voll und das Budget
    zu Ende, die Historie geht also weiter. Der Bericht sagt das dazu, denn
    ein halb gelesener Ring sieht ruhiger aus als er war.
    """

    hole = fetch or md.get_polymarket_trades
    frames: list[pd.DataFrame] = []
    truncated = False
    for page in range(max(1, int(pages))):
        frame = hole(limit=PAGE_SIZE, min_cash=0, user=wallet, offset=page * PAGE_SIZE)
        if frame is None or frame.empty:
            break
        frames.append(frame)
        if len(frame) < PAGE_SIZE:
            break
    else:
        truncated = bool(frames) and len(frames[-1]) >= PAGE_SIZE
    if not frames:
        return pd.DataFrame(), False
    zusammen = pd.concat(frames, ignore_index=True, sort=False)
    schluessel = [s for s in ("transaction_hash", "wallet", "asset") if s in zusammen.columns]
    if schluessel:
        zusammen = zusammen.drop_duplicates(subset=schluessel, keep="first")
    return zusammen.reset_index(drop=True), truncated


def probe(wallets: list[str], pages: int, fetch=None) -> dict:
    """Alle Band-Signale ueber der Wallet-Menge; das On-Chain-Stueck macht main."""

    baender: list[pd.DataFrame] = []
    abdeckung: list[dict] = []
    for wallet in wallets:
        band, truncated = fetch_wallet_tape(wallet, pages, fetch=fetch)
        abdeckung.append({"wallet": wallet, "prints": int(len(band)), "truncated": truncated})
        if not band.empty:
            baender.append(band)
    if baender:
        zusammen = pd.concat(baender, ignore_index=True, sort=False)
        schluessel = [s for s in ("transaction_hash", "wallet", "asset") if s in zusammen.columns]
        if schluessel:
            zusammen = zusammen.drop_duplicates(subset=schluessel, keep="first")
    else:
        zusammen = pd.DataFrame()

    strict_nodes, strict_edges = susp.co_trading_network(zusammen, **STRICT_RULE)
    loose_nodes, loose_edges = susp.co_trading_network(zusammen, **LOOSE_RULE)
    verhalten = bhv.behavior_report(zusammen, wallets=wallets)
    return {
        "coverage": abdeckung,
        "tape_rows": int(len(zusammen)),
        "strict_edges": strict_edges.to_dict(orient="records"),
        "strict_wallets": int(len(strict_nodes)),
        "loose_edges": loose_edges.to_dict(orient="records"),
        "loose_wallets": int(len(loose_nodes)),
        "behavior": verhalten,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe a named wallet set against every linkage signal.")
    parser.add_argument("--wallet", action="append", default=[], help="Wallet-Adresse; mehrfach angebbar.")
    parser.add_argument("--file", default="", help="Datei mit einer Adresse je Zeile (# = Kommentar).")
    parser.add_argument("--pages", type=int, default=4, help="Data-API-Seiten je Wallet a 1000 Prints (Standard 4).")
    parser.add_argument("--onchain", action="store_true",
                        help="Zusaetzlich Funding/Positionen via Etherscan in die Probe-DB scannen.")
    parser.add_argument("--db", default=str(DEFAULT_PROBE_DB),
                        help="Probe-Datenbank fuer --onchain (getrennt vom produktiven Graphen).")
    parser.add_argument("--degree-cap", type=int, default=eg.DEFAULT_DEGREE_CAP)
    parser.add_argument("--probe-pages", type=int, default=6, help="Etherscan-Seitenbudget je Kontrakt (--onchain).")
    args = parser.parse_args()

    wallets: list[str] = []
    quellen = list(args.wallet)
    if args.file:
        for zeile in Path(args.file).read_text(encoding="utf-8").splitlines():
            zeile = zeile.split("#", 1)[0].strip()
            if zeile:
                quellen.append(zeile)
    for wallet in quellen:
        sauber = str(wallet).strip().lower()
        if sauber and sauber not in wallets:
            wallets.append(sauber)
    if len(wallets) < 2:
        print("Mindestens zwei Wallets angeben (--wallet/--file): verknuepfen braucht ein Gegenueber.",
              file=sys.stderr)
        return 1

    ergebnis = probe(wallets, args.pages)
    for zeile in ergebnis["coverage"]:
        rest = " (history truncated at the page budget)" if zeile["truncated"] else ""
        print(f"[tape] {zeile['wallet']}: {zeile['prints']} prints{rest}")
    print(f"[co-trading strict] {len(ergebnis['strict_edges'])} edges over {ergebnis['strict_wallets']} wallets"
          f" (same side of 3+ markets within 5 min, $10k paired)")
    print(f"[co-trading loose]  {len(ergebnis['loose_edges'])} edges over {ergebnis['loose_wallets']} wallets"
          f" (2+ shared markets, no simultaneity)")
    verhalten = ergebnis["behavior"]
    print(f"[fingerprints] {len(verhalten['fingerprints'])} wallets with order-splitting bursts")
    for reihe in verhalten["fingerprints"][:5]:
        print(f"    {reihe['wallet']}: {reihe['burst_prints']} prints in {reihe['burst_seconds']:.0f}s"
              f" on {str(reihe['burst_market'])[:60]}")
    print(f"[complementary] {len(verhalten['complementary_pairs'])} pairs repeatedly on opposite sides")
    for reihe in verhalten["complementary_pairs"][:5]:
        print(f"    {reihe['wallet_a']} vs {reihe['wallet_b']}: {reihe['events']} events"
              f" in {reihe['markets']} markets")

    funding_kanten = 0
    if args.onchain:
        api_key = ff.load_api_key()
        if not api_key:
            print("[onchain] skipped: no ETHERSCAN_API_KEY", file=sys.stderr)
        else:
            conn = eg.connect(Path(args.db))
            try:
                for wallet in wallets:
                    fluesse, complete, _ = ff.fetch_classified_flows(wallet, api_key, page_budget=args.probe_pages)
                    positionen, pos_complete = ff.fetch_position_transfers(wallet, api_key, page_budget=args.probe_pages)
                    eg.record_scan(conn, wallet, fluesse, positionen, complete=bool(complete and pos_complete))
                eg.rebuild_edges(conn, degree_cap=args.degree_cap)
                eg.assign_entities(conn)
                stand = eg.graph_stats(conn)
                funding_kanten = stand["hard_edges"]
                print(f"[onchain] {stand['hard_edges']} hard edges, {stand['candidate_edges']} candidates,"
                      f" {stand['multi_wallet_entities']} multi-wallet entities -> {args.db}")
            finally:
                conn.close()

    gefeuert = []
    if ergebnis["strict_edges"]:
        gefeuert.append("strict co-trading")
    elif ergebnis["loose_edges"]:
        gefeuert.append("loose co-trading only")
    if verhalten["fingerprints"]:
        gefeuert.append("order-splitting fingerprints")
    if verhalten["complementary_pairs"]:
        gefeuert.append("complementary books")
    if funding_kanten:
        gefeuert.append("on-chain funding links")
    print("[verdict] signals firing on this set: " + (", ".join(gefeuert) if gefeuert else "none")
          + ". Research leads, not findings.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
