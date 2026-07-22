"""Universe base rate for Exact Score "No" lines, and how one wallet compares.

Answers the question the wallet-level calibration cannot: is the 0.80-0.95 band
cheap for everyone, or only for the lines this wallet picked? Every line of each
event is priced at a fixed lead time, including the ones the wallet ignored.

    python scripts/run_base_rate_study.py --hours-before 48
    python scripts/run_base_rate_study.py --hours-before 48 --wallet 0x204f...

Writes a CSV of raw observations so the table can be recomputed without
re-fetching. Read-only: public endpoints, no order path.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import pandas as pd  # noqa: E402
import requests  # noqa: E402

from app import base_rate_study as brs  # noqa: E402
from src import copy_trading as ct  # noqa: E402
from src import prediction_markets as pm  # noqa: E402

GAMMA_EVENT_URL = "https://gamma-api.polymarket.com/events/slug/"
SESSION = requests.Session()
SESSION.headers["User-Agent"] = "prediction-market-terminal base-rate-study/1.0 (read-only)"


def event_slugs_from_copy_db(db_path: Path, wallet: str, limit: int,
                             sample: str = "random", seed: int = 7) -> list[str]:
    """Exact Score event slugs observed in the local copy-trading tape.

    ``sample="first"`` reproduces insertion order, which is a trap: the tape
    starts with the headline tournament, and those markets are both the most
    liquid and the ones this wallet loses money in. A base rate read off them
    describes the exception, not the population. Default is a seeded random
    sample so the long tail, where the volume actually sits, is represented.
    """
    conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True, timeout=60)
    try:
        rows = pd.read_sql_query(
            """SELECT DISTINCT source_json FROM paper_orders
               WHERE source_wallet = ? AND title LIKE 'Exact Score%' AND source_json != ''""",
            conn,
            params=(wallet,),
        )
    finally:
        conn.close()
    urls = []
    for blob in rows["source_json"]:
        try:
            urls.append(json.loads(blob).get("url", ""))
        except (TypeError, ValueError):
            continue
    slugs = brs.event_slugs_from_urls(urls)
    if sample == "first" or len(slugs) <= limit:
        return slugs[:limit]
    return list(pd.Series(slugs).sample(n=limit, random_state=seed))


def fetch_event(slug: str) -> dict:
    response = SESSION.get(f"{GAMMA_EVENT_URL}{slug}", timeout=30)
    response.raise_for_status()
    payload = response.json()
    return payload if isinstance(payload, dict) else {}


def build_observations(slugs: list[str], hours_before: float, days: int, pause: float) -> pd.DataFrame:
    frames = []
    for index, slug in enumerate(slugs, start=1):
        try:
            lines = brs.event_lines(fetch_event(slug))
        except Exception as exc:  # noqa: BLE001 - one bad event must not stop the sweep
            print(f"  [{index}/{len(slugs)}] {slug}: FEHLER {type(exc).__name__}")
            continue
        if lines.empty:
            print(f"  [{index}/{len(slugs)}] {slug}: keine aufgeloesten Linien")
            continue
        prices = []
        for _, line in lines.iterrows():
            history = pm.get_polymarket_price_history(
                line["token_id"], days=days, interval="1h", end_time=line["end_time"]
            )
            prices.append(brs.price_at_lead_time(history, line["end_time"], hours_before))
            time.sleep(pause)
        lines["price"] = prices
        priced = lines.dropna(subset=["price"])
        frames.append(priced)
        print(f"  [{index}/{len(slugs)}] {slug}: {len(priced)}/{len(lines)} Linien mit Preis")
    if not frames:
        return pd.DataFrame(columns=brs.OBSERVATION_COLUMNS)
    return pd.concat(frames, ignore_index=True)


def wallet_observations(db_path: Path, wallet: str, universe: pd.DataFrame) -> pd.DataFrame:
    """The same lines, restricted to the ones the wallet bought, carrying its stake.

    The stake matters: the wallet's measured edge came from betting far more on
    some lines than others, and a line-weighted view cannot see that.
    """
    conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True, timeout=60)
    try:
        bought = pd.read_sql_query(
            """SELECT market_key, asset, SUM(source_notional) AS stake, COUNT(*) AS fills
               FROM paper_orders
               WHERE source_wallet = ? AND source_side = 'BUY' AND title LIKE 'Exact Score%'
               GROUP BY market_key, asset""",
            conn,
            params=(wallet,),
        )
    finally:
        conn.close()
    if bought.empty or universe.empty:
        return pd.DataFrame(columns=list(universe.columns) + ["stake", "fills"])
    bought["asset"] = bought["asset"].astype(str)
    merged = universe.assign(asset=universe["token_id"].astype(str)).merge(
        bought, left_on=["market_key", "asset"], right_on=["market_key", "asset"], how="inner"
    )
    return merged.drop(columns=["asset"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hours-before", type=float, default=48.0, help="Vorlaufzeit fuer den Preis")
    parser.add_argument("--events", type=int, default=25, help="Anzahl Events")
    parser.add_argument("--days", type=int, default=14, help="Fenster der Preishistorie")
    parser.add_argument("--pause", type=float, default=0.15, help="Pause zwischen Requests")
    parser.add_argument("--sample", choices=("random", "first"), default="random",
                        help="'first' folgt der Tape-Reihenfolge und trifft nur die Headline-Events")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--wallet", default=ct.COPY_TARGET_WALLET)
    parser.add_argument("--db", default=str(ct.DEFAULT_DB_PATH))
    parser.add_argument("--out", default=str(REPO_ROOT / "data" / "base_rate_exact_score.csv"))
    args = parser.parse_args()

    db_path = Path(args.db)
    slugs = event_slugs_from_copy_db(db_path, args.wallet, args.events,
                                     sample=args.sample, seed=args.seed)
    print(f"Events: {len(slugs)} ({args.sample})   Vorlaufzeit: T-{args.hours_before:g} h\n")
    universe = build_observations(slugs, args.hours_before, args.days, args.pause)
    if universe.empty:
        print("\nKeine Beobachtungen. Abbruch.")
        return 1

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    universe.to_csv(out_path, index=False)

    print(f"\nBeobachtungen: {len(universe):,} Linien aus {universe['event_slug'].nunique()} Events")
    print(f"gespeichert -> {out_path}\n")
    print("=== UNIVERSUM: alle Exact-Score-No-Linien ===")
    universe_table = brs.base_rate_table(universe)
    print(universe_table.to_string(index=False, float_format=lambda v: f"{v:,.4f}"))

    picked = wallet_observations(db_path, args.wallet, universe)
    if picked.empty:
        print("\nKeine ueberlappenden Wallet-Linien, Vergleich entfaellt.")
        return 0
    print(f"\n=== NUR seine Auswahl ({len(picked):,} von {len(universe):,} Linien) ===")
    wallet_table = brs.base_rate_table(picked)
    print(wallet_table.to_string(index=False, float_format=lambda v: f"{v:,.4f}"))
    print("\n=== SELEKTION: seine Luecke minus Universums-Luecke ===")
    print("positiv = er pickt bessere Linien als der Bandschnitt (nicht kopierbar ohne sein Modell)")
    print("nahe 0  = das Band ist fuer alle billig (kopierbar)")
    comparison = brs.compare_to_wallet(universe_table, wallet_table)
    print(comparison.to_string(index=False, float_format=lambda v: f"{v:,.4f}"))

    print("\n=== KONVIKTION: seine grossen gegen seine kleinen Einsaetze ===")
    print("Sein gemessener Edge kam aus der Groesse, nicht aus der blossen Auswahl.")
    split = brs.conviction_split(picked)
    if split.empty:
        print("zu wenig Einsatzdaten fuer den Split.")
    else:
        print(split.to_string(index=False, float_format=lambda v: f"{v:,.4f}"))
        universe_gap = float(universe_table["gap_pp"].mean())
        print(f"\nUniversums-Luecke im Schnitt: {universe_gap:+.2f} pp")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
