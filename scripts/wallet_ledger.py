#!/usr/bin/env python3
"""Rebuild public/data/wallet_ledger.json from the public Polymarket Data API.

    python scripts/wallet_ledger.py                       # default wallet -> public/data/wallet_ledger.json
    python scripts/wallet_ledger.py --wallet 0x... --out /tmp/ledger.json
    python scripts/wallet_ledger.py --no-gamma            # skip event titles / pilot condition ids

Read-only, no key: /activity, /positions, /closed-positions (both sort
directions — the feed caps at ~50 rows per direction) and /trades (count
check only). Event titles and the pilot markets' condition ids come from the
Gamma API and are optional; without them the ledger falls back to a title
derived from the slug and to matching pilot trades by question text.

The transformation itself lives in app/wallet_ledger.py (pure, unit-tested);
this file only fetches, calls build_ledger() and writes the JSON.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import requests  # noqa: E402

from app import wallet_ledger as wl  # noqa: E402
from app.analysis_views import load_publish_payload  # noqa: E402

DATA_API = "https://data-api.polymarket.com"
GAMMA_API = "https://gamma-api.polymarket.com"
HEADERS = {"User-Agent": "prediction-market-terminal/0.1 (+local research app)", "Accept": "application/json"}
PUBLISH_DIR = REPO_ROOT / "public" / "data"
PAGE = 500
SESSION = requests.Session()


def get_json(url: str, params: dict[str, Any] | None = None, timeout: int = 30) -> Any:
    for attempt in range(4):
        try:
            response = SESSION.get(url, params=params, headers=HEADERS, timeout=timeout)
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as exc:
            if attempt == 3:
                raise RuntimeError(f"{url} failed: {exc}") from exc
            time.sleep(1.5 * (attempt + 1))
    return None


def fetch_paged(path: str, wallet: str, **extra: Any) -> list[dict[str, Any]]:
    """Walk offset pages until a short page; the feeds return plain lists."""

    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        params = {"user": wallet, "limit": PAGE, "offset": offset, **extra}
        page = get_json(f"{DATA_API}{path}", params=params)
        if isinstance(page, dict):
            page = page.get("data", [])
        if not isinstance(page, list):
            break
        rows.extend(r for r in page if isinstance(r, dict))
        if len(page) < PAGE:
            break
        offset += PAGE
        time.sleep(0.2)
    return rows


def fetch_closed(wallet: str, direction: str) -> list[dict[str, Any]]:
    page = get_json(f"{DATA_API}/closed-positions",
                    params={"user": wallet, "limit": PAGE, "sortBy": "REALIZEDPNL", "sortDirection": direction})
    if isinstance(page, dict):
        page = page.get("data", [])
    return [r for r in page if isinstance(r, dict)] if isinstance(page, list) else []


def gamma_event_titles(slugs: list[str]) -> dict[str, str]:
    titles: dict[str, str] = {}
    for slug in slugs:
        try:
            data = get_json(f"{GAMMA_API}/events", params={"slug": slug}, timeout=20)
        except RuntimeError as exc:
            print(f"  [warn] gamma event {slug}: {exc}", file=sys.stderr)
            continue
        if isinstance(data, list) and data and isinstance(data[0], dict) and data[0].get("title"):
            titles[slug] = str(data[0]["title"])
        time.sleep(0.15)
    return titles


def gamma_condition_ids(market_ids: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for mid in market_ids:
        try:
            data = get_json(f"{GAMMA_API}/markets/{mid}", timeout=20)
        except RuntimeError as exc:
            print(f"  [warn] gamma market {mid}: {exc}", file=sys.stderr)
            continue
        if isinstance(data, dict) and data.get("conditionId"):
            out[mid] = str(data["conditionId"])
        time.sleep(0.15)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--wallet", default=wl.WALLET)
    parser.add_argument("--out", type=Path, default=PUBLISH_DIR / "wallet_ledger.json")
    parser.add_argument("--publish-dir", type=Path, default=PUBLISH_DIR,
                        help="where runs.json and pilot.json live (default public/data)")
    parser.add_argument("--no-gamma", action="store_true", help="skip Gamma lookups (event titles, pilot condition ids)")
    parser.add_argument(
        "--deposits", type=float,
        default=(float(os.environ["WALLET_DEPOSITS_USD"]) if os.environ.get("WALLET_DEPOSITS_USD") else None),
        help="owner-declared total deposits in USD, verifiable on-chain via the wallet's USDC transfers "
             "(default: env WALLET_DEPOSITS_USD, else absent)",
    )
    parser.add_argument("--dump-raw", type=Path, default=None, help="also write the raw API rows to this JSON file")
    args = parser.parse_args(argv)
    wallet = args.wallet.strip().lower()

    print(f"wallet {wallet}")
    activity = fetch_paged("/activity", wallet)
    positions = fetch_paged("/positions", wallet)
    closed_desc = fetch_closed(wallet, "DESC")
    closed_asc = fetch_closed(wallet, "ASC")
    trades = fetch_paged("/trades", wallet)
    print(f"  activity {len(activity)} · positions {len(positions)} · closed desc {len(closed_desc)} / asc {len(closed_asc)} · trades {len(trades)}")

    runs_payload = load_publish_payload(args.publish_dir, "runs.json")
    pilot_payload = load_publish_payload(args.publish_dir, "pilot.json")
    if runs_payload is None:
        print("  [warn] runs.json not found — no bot attribution", file=sys.stderr)
    if pilot_payload is None:
        print("  [warn] pilot.json not found — no pilot attribution", file=sys.stderr)

    event_titles: dict[str, str] = {}
    pilot_cids: dict[str, str] = {}
    if not args.no_gamma:
        slugs = sorted({str(r.get("eventSlug") or "") for r in activity if r.get("eventSlug")})
        event_titles = gamma_event_titles(slugs)
        pilot_ids = sorted(wl.pilot_index(pilot_payload)["market_ids"])
        pilot_cids = gamma_condition_ids(pilot_ids)
        print(f"  gamma: {len(event_titles)}/{len(slugs)} event titles · {len(pilot_cids)}/{len(pilot_ids)} pilot condition ids")

    stand = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    ledger = wl.build_ledger(
        activity, positions, closed_desc, closed_asc,
        wallet=wallet, runs_payload=runs_payload, pilot_payload=pilot_payload,
        pilot_condition_ids=list(pilot_cids.values()), event_titles=event_titles, stand_utc=stand,
        einzahlungen_usd=args.deposits,
        quellen={
            "data_api": DATA_API,
            "activity_rows": len(activity), "positions_rows": len(positions),
            "closed_positions_desc_rows": len(closed_desc), "closed_positions_asc_rows": len(closed_asc),
            "trades_rows": len(trades),
            "gamma_event_titles": len(event_titles), "gamma_pilot_condition_ids": len(pilot_cids),
        },
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(ledger, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    if args.dump_raw:
        args.dump_raw.write_text(json.dumps({
            "activity": activity, "positions": positions, "closed_desc": closed_desc,
            "closed_asc": closed_asc, "trades": trades, "event_titles": event_titles, "pilot_cids": pilot_cids,
        }, ensure_ascii=False), encoding="utf-8")

    agg = ledger["aggregat"]
    print(f"written -> {args.out}")
    print(f"  events {agg['n_events']} · markets {agg['n_maerkte']} · trades {agg['n_trades']} "
          f"({agg['n_kaeufe']} buys, {agg['n_verkaeufe']} sells) · redeems {agg['n_einloesungen']}")
    print(f"  buys ${agg['kaeufe_usd']:,.2f} · sells ${agg['verkaeufe_usd']:,.2f} · redeems ${agg['einloesungen_usd']:,.2f} "
          f"· net cash flow {agg['netto_cashflow_usd']:+,.2f}")
    print(f"  positions won {agg['positionen_gewonnen']} · lost {agg['positionen_verloren']} "
          f"(worthless {agg['positionen_wertlos']}) · flat {agg['positionen_flat']} · open {agg['positionen_offen']}"
          f" · closed feed capped: {agg['closed_positions_capped']}")
    print(f"  window {agg['erste_aktivitaet_utc']} → {agg['letzte_aktivitaet_utc']}")
    for typ, v in agg["nach_typ"].items():
        print(f"  {typ:14s} events {v['events']:3d} · markets {v['maerkte']:3d} · stake ${v['einsatz_usd']:,.2f} · net {v['netto_cash_usd']:+,.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
