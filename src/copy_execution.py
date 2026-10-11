"""Conservative, paper-only taker fills against a post-trade CLOB snapshot."""
from __future__ import annotations

import hashlib
import json
import math
import time
import threading
from datetime import datetime

import requests

from src import copy_trading as ct

_http = threading.local()


def init_db(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS copy_executions (
        dedup_key TEXT PRIMARY KEY, wallet TEXT, asset TEXT, observed_at TEXT,
        filled_at TEXT, book_time REAL, desired_size REAL, filled_size REAL,
        latency_seconds REAL, evidence_json TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS copy_liquidity (
        asset TEXT, side TEXT, price REAL, observed REAL, remaining REAL,
        PRIMARY KEY(asset, side, price))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS copy_book_clock (
        asset TEXT, side TEXT, timestamp REAL, fingerprint TEXT, PRIMARY KEY(asset, side))""")
    conn.execute("CREATE INDEX IF NOT EXISTS copy_execution_latest ON copy_executions(wallet, asset, observed_at)")


def fetch_book(asset):
    if not hasattr(_http, "session"):
        _http.session = requests.Session()
    response = _http.session.get("https://clob.polymarket.com/book",
                            params={"token_id": asset}, timeout=3)
    response.raise_for_status()
    return response.json()


def levels(book, side):
    result = {}
    for row in book.get(side, []):
        price, size = float(row["price"]), float(row["size"])
        if not math.isfinite(price) or not math.isfinite(size) or not 0 < price < 1 or size < 0:
            raise ValueError("invalid level")
        result[price] = result.get(price, 0) + size
    return sorted(result.items(), reverse=side == "bids")


def apply(conn, parsed, settings, book, observed_at):
    init_db(conn)
    wallet, asset, side = parsed["source_wallet"], parsed["asset"], parsed["side"]
    try:
        source_time = datetime.fromisoformat(parsed["source_time"].replace("Z", "+00:00")).timestamp()
    except (ValueError, TypeError):
        return ct.PaperOrder(parsed["dedup_key"], "skipped", "invalid_source_time",
                             side, parsed["source_notional"])
    ct._ensure_trader(conn, wallet, settings.paper_start_cash)
    if side == "BUY":
        ct._increase_source_position(conn, wallet, parsed)
    else:
        ct._decrease_source_position(conn, wallet, asset, parsed["size"], parsed["price"])
    position = ct._get_position(conn, wallet, asset)
    wanted = parsed["size"]
    available_position = float(position["shares"]) if position else 0
    requested = wanted if side == "BUY" else min(wanted, available_position)
    filled = notional = realized = 0.0
    book_time = None
    consumed = []
    reason = "book_unavailable"
    filled_at = None
    try:
        book_time = float(book["timestamp"]) / 1000
        now = time.time()
        if str(book["asset_id"]) != asset or not math.isfinite(book_time):
            raise ValueError("wrong asset or timestamp")
        if not (source_time + (1 if source_time.is_integer() else 0)) <= book_time <= now + 1 or now - book_time > 5:
            reason = "book_stale_or_pre_fill"
        else:
            bids, asks = levels(book, "bids"), levels(book, "asks")
            if bids and asks and bids[0][0] >= asks[0][0]:
                raise ValueError("crossed book")
            fingerprint = hashlib.sha256(json.dumps([bids, asks]).encode()).hexdigest()
            previous = conn.execute("SELECT timestamp, fingerprint FROM copy_book_clock WHERE asset=? AND side=?",
                                    (asset, side)).fetchone()
            if previous and (book_time < previous["timestamp"] or (book_time == previous["timestamp"] and fingerprint != previous["fingerprint"])):
                raise ValueError("out-of-order book")
            minimum = float(book.get("min_order_size", 0))
            if not math.isfinite(minimum) or minimum < 0:
                raise ValueError("invalid minimum size")
            requested = math.floor(requested * 100 + 1e-9) / 100
            if requested < minimum:
                requested = 0
            conn.execute("INSERT OR REPLACE INTO copy_book_clock VALUES (?, ?, ?, ?)", (asset, side, book_time, fingerprint))
            ladder = asks if side == "BUY" else bids
            # Conservative shadow depth: only observed size increases replenish
            # used liquidity. A same-size replacement cannot be proven by REST.
            prior = {float(r["price"]): r for r in conn.execute(
                "SELECT * FROM copy_liquidity WHERE asset=? AND side=?", (asset, side))}
            conn.execute("DELETE FROM copy_liquidity WHERE asset=? AND side=?", (asset, side))
            for price, size in ladder:
                old = prior.get(price)
                replenished = max(0, size-float(old["observed"])) if old and (not previous or book_time > previous["timestamp"]) else 0
                remaining = size if old is None else min(size, float(old["remaining"]) + replenished)
                take = min(max(0, requested-filled), remaining)
                filled += take
                notional += take * price
                if take:
                    consumed.append({"price": price, "size": take})
                conn.execute("INSERT INTO copy_liquidity VALUES (?, ?, ?, ?, ?)",
                             (asset, side, price, size, remaining-take))
            reason = "book_full" if filled >= wanted-1e-9 else "book_partial" if filled else "book_no_liquidity"
            if side == "SELL" and requested == 0:
                reason = "skipped_no_paper_position"
            elif requested == 0:
                reason = "book_below_min_size"
            filled_at = ct.utc_now() if filled else None
    except (requests.RequestException, ValueError, TypeError, KeyError, OverflowError):
        reason = "book_unavailable"

    if filled:
        price = notional / filled
        cash = ct._get_trader_cash(conn, wallet, settings.paper_start_cash)
        if side == "BUY":
            if notional > cash:
                cash = ct._record_trader_cash_event(conn, wallet, notional-cash,
                    "research_1to1_funding", "Required paper capital for observed order-book fill")
            shares = available_position + filled
            cost = (float(position["cost_basis"]) if position else 0) + notional
            conn.execute("""INSERT INTO positions
                (trader_wallet, asset, market_key, title, outcome, shares, avg_price, cost_basis, last_price, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(trader_wallet, asset) DO UPDATE SET shares=excluded.shares,
                avg_price=excluded.avg_price, cost_basis=excluded.cost_basis,
                last_price=excluded.last_price, updated_at=excluded.updated_at""",
                (wallet, asset, parsed["market_key"], parsed["title"], parsed["outcome"],
                 shares, cost/shares, cost, bids[0][0] if bids else price, ct.utc_now()))
            ct._set_trader_cash(conn, wallet, cash-notional)
        else:
            realized = notional - float(position["avg_price"])*filled
            ct._reduce_position(conn, wallet, asset, filled, price)
            ct._set_trader_cash(conn, wallet, cash+notional)
    latency = datetime.fromisoformat(filled_at).timestamp()-source_time if filled_at else None
    conn.execute("INSERT INTO copy_executions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (parsed["dedup_key"], wallet, asset, observed_at, filled_at, book_time, wanted,
         filled, latency, json.dumps({"book": book, "levels": consumed, "reason": reason})))
    return ct.PaperOrder(parsed["dedup_key"], "copied" if filled else "skipped", reason,
                        side, parsed["source_notional"], notional, filled, realized,
                        desired_notional=parsed["source_notional"])
