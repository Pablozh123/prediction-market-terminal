"""Schreibt die Co-Trading-Figur als eigenstaendige SVG.

Nimmt die Daten entweder vom laufenden Terminal-API oder rechnet sie
direkt aus den Modulen, dann braucht es keinen Server.

    python scripts/export_cluster_figure.py
    python scripts/export_cluster_figure.py --out docs/research/cluster_figur.svg
    python scripts/export_cluster_figure.py --api http://localhost:8787

Read-only: liest den oeffentlichen Trade-Feed, kein Order-Pfad.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import api_views as apv  # noqa: E402
from app import cluster_figure as fig  # noqa: E402

STANDARD_ZIEL = "docs/research/co_trading_cluster.svg"


def payload_von_api(basis: str) -> dict:
    with urllib.request.urlopen(basis.rstrip("/") + "/api/risk", timeout=120) as antwort:
        return json.loads(antwort.read().decode("utf-8"))


def payload_direkt(seiten: int) -> dict:
    """Ohne Server: Tape holen, filtern, Netzwerk rechnen, Nutzlast bauen."""
    import pandas as pd

    from app import suspicion as susp
    from src import prediction_markets as md

    teile = []
    for seite in range(seiten):
        block = md.get_polymarket_trades(limit=1000, min_cash=1000.0, offset=seite * 1000)
        if block is None or block.empty:
            break
        teile.append(block)
    if not teile:
        raise SystemExit("kein Tape erhalten")
    tape = pd.concat(teile, ignore_index=True, sort=False)
    schluessel = [s for s in ("transaction_hash", "wallet", "asset") if s in tape.columns]
    if schluessel:
        tape = tape.drop_duplicates(subset=schluessel, keep="first")

    keys = sorted({str(k) for k in tape.get("market_key", pd.Series(dtype=str)).dropna().astype(str) if k})
    try:
        kategorien = md.market_category_frame(keys)
    except Exception as exc:
        print(f"[warn] Kategorien nicht geladen ({exc}), Titelmuster muessen reichen")
        kategorien = pd.DataFrame()
    basis = susp.filter_insider_prone_trades(tape, kategorien)

    leiter = (
        ("same side of at least 3 markets within 5 minutes, $10k paired notional",
         dict(window_minutes=5.0, min_shared=3, min_pair_notional=10_000.0)),
        ("same side of at least 2 markets within 5 minutes",
         dict(window_minutes=5.0, min_shared=2)),
        ("same side of at least 2 markets anywhere in the window, no simultaneity required",
         dict(window_minutes=None, min_shared=2)),
    )
    regel, nodes, edges = leiter[-1][0], None, None
    regel_kwargs: dict[str, object] = dict(leiter[-1][1])
    for beschreibung, kwargs in leiter:
        nodes, edges = susp.co_trading_network(basis, max_wallets=300, **kwargs)
        if not nodes.empty:
            regel, regel_kwargs = beschreibung, dict(kwargs)
            break
    if nodes is None or nodes.empty:
        return {"graph": {}, "matrix": {}}

    try:
        modularitaet = susp.network_modularity(nodes, edges)
    except Exception:
        modularitaet = None
    # Die Kontrolle gehoert in genau diese Datei: sie ist die Fassung, die in
    # einer schriftlichen Arbeit landet, und ein Inselbild ohne die Angabe,
    # was dieselbe Regel auf gemischten Daten findet, behauptet zu viel.
    try:
        nullmodell = susp.null_model_reference(basis, runs=3, max_wallets=300, **regel_kwargs)
    except Exception as exc:
        print(f"[warn] Nullmodell nicht gerechnet ({exc})")
        nullmodell = None
    graph = apv.network_graph(
        susp.cluster_layout(nodes), edges,
        regel=regel, modularitaet=modularitaet, nullmodell=nullmodell,
        wallets_im_tape=int(basis["wallet"].astype(str).nunique()),
        stand_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    graph["fenster"] = apv.tape_window_label(basis)
    return {"graph": graph, "matrix": apv.overlap_matrix(basis, nodes)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=STANDARD_ZIEL, help=f"Zieldatei (Vorgabe: {STANDARD_ZIEL})")
    parser.add_argument("--api", default="", help="laufendes Terminal-API statt Direktberechnung")
    parser.add_argument("--seiten", type=int, default=8, help="Tape-Seiten a 1000 Prints (Vorgabe: 8)")
    parser.add_argument("--breite", type=int, default=1400, help="Bildbreite in Punkten")
    args = parser.parse_args(argv)

    payload = payload_von_api(args.api) if args.api else payload_direkt(args.seiten)
    graph = payload.get("graph") or {}
    if not graph.get("knoten"):
        print("Kein Cluster im aktuellen Fenster. Das ist ein Ergebnis, kein Fehler.", file=sys.stderr)
        return 1

    ziel = Path(args.out)
    ziel.parent.mkdir(parents=True, exist_ok=True)
    ziel.write_text(fig.build_svg(payload, breite=args.breite), encoding="utf-8")

    k = graph.get("kennzahl") or {}
    print(f"{k.get('wallets', 0)} Wallets, {k.get('kanten', 0)} Kanten, "
          f"{k.get('cluster', 0)} Cluster, Modularitaet {k.get('modularitaet', '—')}")
    print(f"Regel: {graph.get('regel', '')}")
    print(f"Fenster: {graph.get('fenster', '')}")
    print(f"geschrieben: {ziel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
