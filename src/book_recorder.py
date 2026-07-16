"""Read-only microstructure recorder for Polymarket books and trades.

Snapshots top-of-book depth (top N levels, both outcome tokens) for the
most active binary markets plus the recent public trade tape, on a fixed
cadence. The output feeds book-imbalance / order-flow studies and a
paper market-making simulator.

Public endpoints only: no order path, no credentials, no wallet columns
in the output. Data lands under ``data/microstructure/`` (gitignored),
day-partitioned, append-only.

Run once:    python -m src.book_recorder --once
Run daemon:  python scripts/run_book_recorder.py
Autostart:   scripts/install_book_recorder_task.ps1
"""

from __future__ import annotations

import argparse
import csv
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

GAMMA_MARKETS_URL = "https://gamma-api.polymarket.com/markets"
CLOB_BOOK_URL = "https://clob.polymarket.com/book"
TRADES_URL = "https://data-api.polymarket.com/trades"
HEADERS = {
    "User-Agent": "prediction-market-terminal book-recorder/1.0 (read-only)"
}

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT_DIR = REPO_ROOT / "data" / "microstructure"

TOP_N_MARKETS = 60
BOOK_LEVELS = 5
INTERVAL_SECONDS = 120
TRADE_PAGE_SIZE = 500
TRADE_PAGES = 2

BOOK_FIELDS = [
    "ts_utc", "market_id", "slug", "outcome", "token_id", "best_bid",
    "best_ask", "spread", "mid", "bid_usd_top", "ask_usd_top",
    "imbalance_top", "bids_json", "asks_json",
]
TRADE_FIELDS = [
    "seen_ts_utc", "trade_ts", "market_id", "slug", "token_id", "outcome",
    "side", "price", "size", "tx_hash",
]


def _get_json(url: str, params: dict | None = None, timeout: int = 20):
    resp = requests.get(url, params=params or {}, headers=HEADERS, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def _json_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, str):
        try:
            return list(json.loads(value))
        except (ValueError, TypeError):
            return []
    return list(value)


def _volume(market: dict) -> float:
    for key in ("volume24hr", "volumeNum", "volume"):
        try:
            return float(market.get(key))
        except (TypeError, ValueError):
            continue
    return 0.0


def select_markets(raw_markets: list[dict], top_n: int = TOP_N_MARKETS) -> list[dict]:
    """Pick the most active binary markets that have order-book tokens.

    Returns compact tracking dicts: market_id, slug, question, and one
    entry per outcome token (outcome name + token id).
    """
    tracked: list[dict] = []
    for market in sorted(raw_markets, key=_volume, reverse=True):
        outcomes = [str(o) for o in _json_list(market.get("outcomes"))]
        tokens = [str(t) for t in _json_list(market.get("clobTokenIds"))]
        if len(outcomes) != 2 or len(tokens) != 2 or not all(tokens):
            continue
        tracked.append({
            "market_id": str(market.get("id")),
            "slug": market.get("slug", ""),
            "question": market.get("question", ""),
            "tokens": list(zip(outcomes, tokens)),
        })
        if len(tracked) >= top_n:
            break
    return tracked


def _sorted_levels(levels: list, descending: bool) -> list[tuple[float, float]]:
    parsed = []
    for level in levels or []:
        try:
            parsed.append((float(level["price"]), float(level["size"])))
        except (KeyError, TypeError, ValueError):
            continue
    return sorted(parsed, key=lambda x: x[0], reverse=descending)


def level_usd(levels: list[tuple[float, float]]) -> float:
    return round(sum(price * size for price, size in levels), 2)


def book_row(ts_utc: str, tracked: dict, outcome: str, token_id: str,
             book: dict, levels: int = BOOK_LEVELS) -> dict:
    """Flatten one order book into a CSV row with top-``levels`` depth."""
    bids = _sorted_levels(book.get("bids"), descending=True)[:levels]
    asks = _sorted_levels(book.get("asks"), descending=False)[:levels]
    best_bid = bids[0][0] if bids else None
    best_ask = asks[0][0] if asks else None
    spread = round(best_ask - best_bid, 4) if bids and asks else None
    mid = round((best_ask + best_bid) / 2.0, 4) if bids and asks else None
    bid_usd = level_usd(bids)
    ask_usd = level_usd(asks)
    total = bid_usd + ask_usd
    imbalance = round(bid_usd / total, 4) if total > 0 else None
    return {
        "ts_utc": ts_utc,
        "market_id": tracked["market_id"],
        "slug": tracked["slug"],
        "outcome": outcome,
        "token_id": token_id,
        "best_bid": best_bid,
        "best_ask": best_ask,
        "spread": spread,
        "mid": mid,
        "bid_usd_top": bid_usd,
        "ask_usd_top": ask_usd,
        "imbalance_top": imbalance,
        "bids_json": json.dumps(bids),
        "asks_json": json.dumps(asks),
    }


def trades_rows(seen_ts_utc: str, token_map: dict[str, dict],
                trades: list[dict]) -> list[dict]:
    """Filter the public tape to tracked tokens. No wallet columns."""
    rows: list[dict] = []
    for trade in trades:
        token_id = str(trade.get("asset") or trade.get("asset_id") or "")
        info = token_map.get(token_id)
        if info is None:
            continue
        rows.append({
            "seen_ts_utc": seen_ts_utc,
            "trade_ts": trade.get("timestamp"),
            "market_id": info["market_id"],
            "slug": info["slug"],
            "token_id": token_id,
            "outcome": info["outcome"],
            "side": trade.get("side"),
            "price": trade.get("price"),
            "size": trade.get("size"),
            "tx_hash": trade.get("transactionHash"),
        })
    return rows


def append_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    is_new = not path.exists()
    with open(path, "a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        if is_new:
            writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in fields})


def fetch_active_markets(get_json=_get_json, pages: int = 3,
                         page_size: int = 100) -> list[dict]:
    """Active, open markets ordered by 24h volume (server caps limit at 100)."""
    markets: list[dict] = []
    for page in range(pages):
        batch = get_json(GAMMA_MARKETS_URL, params={
            "active": "true", "closed": "false",
            "order": "volume24hr", "ascending": "false",
            "limit": page_size, "offset": page * page_size,
        })
        if not batch:
            break
        markets.extend(batch)
    return markets


def fetch_recent_trades(get_json=_get_json, pages: int = TRADE_PAGES,
                        page_size: int = TRADE_PAGE_SIZE) -> list[dict]:
    trades: list[dict] = []
    for page in range(pages):
        batch = get_json(TRADES_URL, params={
            "limit": page_size, "offset": page * page_size,
        })
        if not batch:
            break
        trades.extend(batch)
    return trades


def run_once(out_dir: Path | None = None, get_json=_get_json,
             top_n: int = TOP_N_MARKETS, now: datetime | None = None) -> dict:
    """One recording pass: books for tracked markets plus recent tape."""
    out_dir = Path(out_dir or DEFAULT_OUT_DIR)
    now = now or datetime.now(timezone.utc)
    ts = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    day = now.strftime("%Y-%m-%d")

    tracked = select_markets(fetch_active_markets(get_json=get_json), top_n=top_n)
    token_map = {
        token_id: {"market_id": t["market_id"], "slug": t["slug"], "outcome": outcome}
        for t in tracked for outcome, token_id in t["tokens"]
    }

    book_rows: list[dict] = []
    book_errors = 0
    for t in tracked:
        for outcome, token_id in t["tokens"]:
            try:
                book = get_json(CLOB_BOOK_URL, params={"token_id": token_id})
            except Exception:  # noqa: BLE001 - one bad book must not stop the pass
                book_errors += 1
                continue
            book_rows.append(book_row(ts, t, outcome, token_id, book))

    try:
        tape = fetch_recent_trades(get_json=get_json)
    except Exception:  # noqa: BLE001
        tape = []
    trade_rows = trades_rows(ts, token_map, tape)

    append_csv(out_dir / f"books_{day}.csv", BOOK_FIELDS, book_rows)
    append_csv(out_dir / f"trades_{day}.csv", TRADE_FIELDS, trade_rows)

    summary = {
        "ts_utc": ts, "tracked_markets": len(tracked),
        "book_rows": len(book_rows), "book_errors": book_errors,
        "trade_rows": len(trade_rows),
    }
    with open(out_dir / "recorder_status.json", "w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--once", action="store_true",
                        help="single pass (default when --loop is absent)")
    parser.add_argument("--loop", action="store_true",
                        help="run forever with a fixed interval")
    parser.add_argument("--interval", type=int, default=INTERVAL_SECONDS)
    parser.add_argument("--top-n", type=int, default=TOP_N_MARKETS)
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    args = parser.parse_args(argv)

    out_dir = Path(args.out_dir)
    while True:
        started = time.monotonic()
        try:
            summary = run_once(out_dir=out_dir, top_n=args.top_n)
            print(f"[recorder] {summary}", flush=True)
        except Exception as exc:  # noqa: BLE001 - keep the daemon alive
            print(f"[recorder] pass failed: {exc}", flush=True)
        if not args.loop:
            return 0
        elapsed = time.monotonic() - started
        time.sleep(max(5.0, args.interval - elapsed))


if __name__ == "__main__":
    raise SystemExit(main())
