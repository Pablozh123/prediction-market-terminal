"""Read-only recorder for Kalshi order books and trades.

The counterpart to ``src/book_recorder.py``, so that cross-venue questions stop
being a model and become a measurement. Rows land in the same column layout as
the Polymarket recorder, which means ``src/imbalance_study.py``,
``src/orderflow_study.py`` and ``src/mm_pnl.py`` run on Kalshi data unchanged.

Two things about Kalshi's public API shape the design.

Book representation. Kalshi quotes one book per market with both sides
expressed as bids: ``yes_dollars`` are bids to buy YES, ``no_dollars`` are bids
to buy NO. A NO bid at 0.25 is therefore a YES offer at 0.75, and the ask side
has to be derived by reflection rather than read off. Getting that wrong
inverts every spread, so it has its own tests.

Discovery. The plain market listing is dominated by tens of thousands of
multi-game parlay markets (ticker prefix KXMVE) whose books are almost always
empty; paging it returns 25,000 rows before reaching anything liquid. Walking
the far smaller events endpoint with nested markets and ranking by 24h volume
reaches the real markets in about ten seconds.

Public endpoints only. The Kalshi WebSocket requires an API key and this repo
does not handle credentials, so the feed here is REST polling and the
resolution is correspondingly coarse - which is stated in every report built
on it rather than quietly assumed away.

Run once:  python -m src.kalshi_recorder --once
Loop:      python scripts/run_kalshi_recorder.py
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

from app import proc_lock
from app.proc_lock import AlreadyRunning
from src.book_recorder import append_csv

BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"
HEADERS = {
    "User-Agent": "prediction-market-terminal kalshi-recorder/1.0 (read-only)"
}

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT_DIR = REPO_ROOT / "data" / "microstructure"

TOP_N_MARKETS = 60
BOOK_LEVELS = 5
INTERVAL_SECONDS = 120
DISCOVERY_PAGES = 12
DISCOVERY_PAGE_SIZE = 200
TRADES_PER_MARKET = 100

#: Parlay-Maerkte: zehntausende Stueck, Buecher praktisch immer leer.
PARLAY_PREFIX = "KXMVE"

#: Gleiches Layout wie der Polymarket-Recorder, damit die Studien unveraendert
#: laufen. ``category`` kommt dazu, weil das Gebuehrenmodell sie braucht.
BOOK_FIELDS = [
    "ts_utc", "market_id", "slug", "outcome", "token_id", "best_bid",
    "best_ask", "spread", "mid", "bid_usd_top", "ask_usd_top",
    "imbalance_top", "bids_json", "asks_json", "category", "volume_24h",
    "exchange_index",
]
TRADE_FIELDS = [
    "seen_ts_utc", "trade_ts", "market_id", "slug", "token_id", "outcome",
    "side", "price", "size", "tx_hash", "exchange_index",
]


def _get_json(path: str, params: dict | None = None, timeout: int = 30):
    resp = requests.get(f"{BASE_URL}{path}", params=params or {},
                        headers=HEADERS, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def _num(value) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return 0.0
    return out


def is_parlay(ticker: str) -> bool:
    return str(ticker or "").startswith(PARLAY_PREFIX)


def discover_markets(get_json=_get_json, pages: int = DISCOVERY_PAGES,
                     page_size: int = DISCOVERY_PAGE_SIZE,
                     top_n: int = TOP_N_MARKETS) -> list[dict]:
    """Open markets ranked by 24h volume, parlays removed.

    Walks ``/events`` with nested markets rather than ``/markets``: the event
    list is orders of magnitude smaller and carries the category, which the
    market rows do not.
    """
    rows: list[dict] = []
    cursor = ""
    for _ in range(max(1, pages)):
        params = {"limit": page_size, "status": "open",
                  "with_nested_markets": "true"}
        if cursor:
            params["cursor"] = cursor
        payload = get_json("/events", params)
        events = payload.get("events") or []
        for event in events:
            for market in event.get("markets") or []:
                ticker = str(market.get("ticker") or "")
                if not ticker or is_parlay(ticker):
                    continue
                rows.append({
                    "ticker": ticker,
                    "event_ticker": event.get("event_ticker", ""),
                    "series_ticker": event.get("series_ticker", ""),
                    "category": event.get("category", ""),
                    "title": event.get("title", ""),
                    "subtitle": market.get("yes_sub_title")
                    or event.get("sub_title", ""),
                    "volume_24h": _num(market.get("volume_24h_fp")),
                    "open_interest": _num(market.get("open_interest_fp")),
                    # Preise kommen aus derselben Abfrage mit; sie hier
                    # mitzunehmen erspart der Cross-Venue-Suche einen zweiten
                    # Durchlauf ueber tausende Maerkte.
                    "yes_bid": _num(market.get("yes_bid_dollars")),
                    "yes_ask": _num(market.get("yes_ask_dollars")),
                    # Kalshi verteilt den Handel ab dem 2026-08-06 auf mehrere
                    # Matching-Engines. Die Kennung ist heute schon da; wer sie
                    # jetzt nicht mitschreibt, kann sie spaeter nicht
                    # nachtragen und keine Frage ueber Shards beantworten.
                    "exchange_index": market.get("exchange_index",
                                                 event.get("exchange_index")),
                })
        cursor = payload.get("cursor") or ""
        if not cursor or not events:
            break
    rows.sort(key=lambda m: (m["volume_24h"], m["open_interest"]), reverse=True)
    seen: set[str] = set()
    picked: list[dict] = []
    for row in rows:
        if row["ticker"] in seen:
            continue
        seen.add(row["ticker"])
        picked.append(row)
        if len(picked) >= top_n:
            break
    return picked


def _levels(raw: list, reflect: bool) -> list[tuple[float, float]]:
    """Parse one side of the book, optionally reflecting NO bids into YES asks."""
    out: list[tuple[float, float]] = []
    for level in raw or []:
        try:
            price, size = float(level[0]), float(level[1])
        except (TypeError, ValueError, IndexError, KeyError):
            continue
        if size <= 0:
            continue
        out.append((round(1.0 - price, 6) if reflect else round(price, 6), size))
    out.sort(key=lambda item: item[0], reverse=not reflect)
    return out


def parse_orderbook(payload: dict, levels: int = BOOK_LEVELS
                    ) -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
    """(yes bids, yes asks) from Kalshi's two-sided bid representation.

    ``no_dollars`` holds bids to buy NO. A NO bid at price p is an offer to sell
    YES at 1 - p, so the ask side is the reflection of that list. Reading it as
    a raw ask ladder would invert every spread in every downstream study.
    """
    book = (payload or {}).get("orderbook_fp") or (payload or {}).get("orderbook") or {}
    bids = _levels(book.get("yes_dollars") or book.get("yes"), reflect=False)
    asks = _levels(book.get("no_dollars") or book.get("no"), reflect=True)
    return bids[:levels], asks[:levels]


def level_usd(levels: list[tuple[float, float]]) -> float:
    return round(sum(price * size for price, size in levels), 2)


def book_row(ts_utc: str, market: dict, payload: dict,
             levels: int = BOOK_LEVELS) -> dict:
    """One flattened YES-side snapshot in the Polymarket recorder's layout."""
    bids, asks = parse_orderbook(payload, levels)
    best_bid = bids[0][0] if bids else None
    best_ask = asks[0][0] if asks else None
    spread = round(best_ask - best_bid, 6) if bids and asks else None
    mid = round((best_ask + best_bid) / 2.0, 6) if bids and asks else None
    bid_usd = level_usd(bids)
    ask_usd = level_usd(asks)
    total = bid_usd + ask_usd
    return {
        "ts_utc": ts_utc,
        "market_id": market["ticker"],
        "slug": market.get("event_ticker", ""),
        "outcome": "Yes",
        "token_id": market["ticker"],
        "best_bid": best_bid,
        "best_ask": best_ask,
        "spread": spread,
        "mid": mid,
        "bid_usd_top": bid_usd,
        "ask_usd_top": ask_usd,
        "imbalance_top": round(bid_usd / total, 6) if total > 0 else None,
        "bids_json": json.dumps(bids),
        "asks_json": json.dumps(asks),
        "category": market.get("category", ""),
        "volume_24h": market.get("volume_24h", 0.0),
        "exchange_index": market.get("exchange_index"),
    }


def trade_rows(seen_ts_utc: str, market: dict, trades: list[dict]) -> list[dict]:
    """Public prints with the aggressor side, mapped to the shared layout.

    ``taker_side`` is which outcome the aggressor bought, so a taker buying YES
    is a BUY on the YES token and a taker buying NO is a SELL of it. That makes
    the signed order flow directly comparable to the Polymarket tape.
    """
    rows: list[dict] = []
    for trade in trades or []:
        if not isinstance(trade, dict):
            continue
        taker = str(trade.get("taker_side") or trade.get("taker_outcome_side") or "").lower()
        rows.append({
            "seen_ts_utc": seen_ts_utc,
            "trade_ts": trade.get("created_time"),
            "market_id": market["ticker"],
            "slug": market.get("event_ticker", ""),
            "token_id": market["ticker"],
            "outcome": "Yes",
            "side": "BUY" if taker == "yes" else "SELL",
            "price": trade.get("yes_price_dollars"),
            "size": trade.get("count_fp"),
            "tx_hash": trade.get("trade_id"),
            "exchange_index": market.get("exchange_index"),
        })
    return rows


def run_once(out_dir: Path | None = None, get_json=_get_json,
             top_n: int = TOP_N_MARKETS, now: datetime | None = None,
             markets: list[dict] | None = None) -> dict:
    """One pass: books and recent prints for the most active open markets."""
    out_dir = Path(out_dir or DEFAULT_OUT_DIR)
    now = now or datetime.now(timezone.utc)
    ts = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    day = now.strftime("%Y-%m-%d")

    tracked = markets if markets is not None else discover_markets(
        get_json=get_json, top_n=top_n)

    books: list[dict] = []
    prints: list[dict] = []
    book_errors = 0
    trade_errors = 0
    for market in tracked:
        try:
            payload = get_json(f"/markets/{market['ticker']}/orderbook",
                               {"depth": BOOK_LEVELS})
        except Exception:  # noqa: BLE001 - ein kaputtes Buch stoppt den Pass nicht
            book_errors += 1
        else:
            books.append(book_row(ts, market, payload))
        try:
            payload = get_json("/markets/trades",
                               {"ticker": market["ticker"],
                                "limit": TRADES_PER_MARKET})
        except Exception:  # noqa: BLE001
            trade_errors += 1
        else:
            prints.extend(trade_rows(ts, market, payload.get("trades") or []))

    append_csv(out_dir / f"kalshi_books_{day}.csv", BOOK_FIELDS, books)
    append_csv(out_dir / f"kalshi_trades_{day}.csv", TRADE_FIELDS, prints)

    summary = {
        "ts_utc": ts,
        "tracked_markets": len(tracked),
        "book_rows": len(books),
        "book_errors": book_errors,
        "trade_rows": len(prints),
        "trade_errors": trade_errors,
        "two_sided_books": sum(1 for row in books if row["mid"] is not None),
        "exchange_indexes": sorted({str(row.get("exchange_index"))
                                    for row in books}),
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "kalshi_recorder_status.json", "w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--interval", type=int, default=INTERVAL_SECONDS)
    parser.add_argument("--top-n", type=int, default=TOP_N_MARKETS)
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    args = parser.parse_args(argv)

    out_dir = Path(args.out_dir)
    try:
        lock = proc_lock.acquire(out_dir, "kalshi_recorder.lock")
    except AlreadyRunning as exc:
        print(f"[kalshi] {exc}", flush=True)
        return 1
    try:
        # Die Marktauswahl kostet rund zehn Sekunden; sie einmal pro Stunde zu
        # erneuern reicht und haelt den Pass kurz.
        markets: list[dict] = []
        last_discovery = 0.0
        while True:
            started = time.monotonic()
            try:
                if not markets or started - last_discovery > 3600:
                    markets = discover_markets(top_n=args.top_n)
                    last_discovery = started
                summary = run_once(out_dir=out_dir, top_n=args.top_n,
                                   markets=markets)
                print(f"[kalshi] {summary}", flush=True)
            except Exception as exc:  # noqa: BLE001 - Daemon bleibt am Leben
                print(f"[kalshi] pass failed: {exc}", flush=True)
                markets = []
            if not args.loop:
                return 0
            time.sleep(max(5.0, args.interval - (time.monotonic() - started)))
    finally:
        proc_lock.release(lock)


if __name__ == "__main__":
    raise SystemExit(main())
