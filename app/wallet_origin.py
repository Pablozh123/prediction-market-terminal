"""First trade of a wallet: the freshness the risk screen measures.

The screen used to call a wallet "fresh" when it had at most two prints in
the sampled window, a print of twice the whale threshold, and its first
appearance in the younger half of that window. That is the shape of the
sample, not of the wallet: on a 34-minute window every wallet that arrived
late looked new, and of fourteen wallets the persistent store had first seen
within an hour of a big print, eleven had been trading for months.

What the public cases describe is different and cheap to measure: a wallet
whose FIRST TRADE on the venue lies hours or days before the print in
question. The Data API answers that in one call per wallet
(``/activity?user=<addr>&type=TRADE&limit=1&sortDirection=ASC``), the answer
never changes once it exists, and the persistent trade store keeps it, so a
wallet is asked about once. How old the address itself is does not matter: a
wallet funded a year ago that trades for the first time into a strike market
is exactly the pattern.

Streamlit-free. The API server, the Streamlit page and the case replay use
the same functions; the network call is injectable so every rule is testable
without it.
"""

from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

import pandas as pd

from src import prediction_markets as md
from src import trade_store as ts

#: States of an origin row. ``measured``: the venue named a first trade.
#: ``none``: the venue returned no trade at all (a lag, or a wallet that only
#: split or merged); the screen treats it as unmeasured. ``error``: the call
#: failed; retried after ``RETRY_HOURS``.
ORIGIN_MEASURED = "measured"
ORIGIN_NONE = "none"
ORIGIN_ERROR = "error"

#: How many wallets one scan may ask the venue about. Each is one HTTP call
#: of about 200 ms; the store remembers every answer, so a steady host only
#: pays for wallets it has never seen. Env ``RISK_ORIGIN_LOOKUPS`` overrides.
DEFAULT_LOOKUP_BUDGET = 40
#: A ``none`` or ``error`` answer is asked again after this many hours.
RETRY_HOURS = 24.0


def lookup_budget() -> int:
    try:
        value = int(float(os.environ.get("RISK_ORIGIN_LOOKUPS", "").strip() or DEFAULT_LOOKUP_BUDGET))
    except ValueError:
        value = DEFAULT_LOOKUP_BUDGET
    return max(0, value)


def _key(wallet: Any) -> str:
    return str(wallet or "").strip().lower()


def fetch_first_trade(wallet: str, *, get_json: Callable[..., Any] | None = None) -> dict[str, Any]:
    """Ask the Data API for the wallet's first trade. Never raises.

    Returns ``{wallet, first_trade_ts, state, detail}`` with the wallet
    lowercased. ``first_trade_ts`` is Unix seconds or None.
    """

    key = _key(wallet)
    if not key:
        return {"wallet": "", "first_trade_ts": None, "state": ORIGIN_ERROR, "detail": "empty wallet"}
    getter = get_json or md._get_json
    try:
        data = getter(
            f"{md.POLY_DATA}/activity",
            params={"user": key, "limit": 1, "type": "TRADE", "sortDirection": "ASC"},
        )
    except Exception as exc:  # noqa: BLE001 - a failed lookup is a state, not a crash
        return {"wallet": key, "first_trade_ts": None, "state": ORIGIN_ERROR, "detail": f"{type(exc).__name__}: {exc}"[:200]}
    rows = data if isinstance(data, list) else (data.get("data", []) if isinstance(data, dict) else [])
    if not rows or not isinstance(rows[0], dict):
        return {"wallet": key, "first_trade_ts": None, "state": ORIGIN_NONE, "detail": "no trade returned"}
    try:
        stamp = int(float(rows[0].get("timestamp")))
    except (TypeError, ValueError):
        return {"wallet": key, "first_trade_ts": None, "state": ORIGIN_ERROR, "detail": "timestamp unreadable"}
    return {"wallet": key, "first_trade_ts": stamp, "state": ORIGIN_MEASURED, "detail": ""}


def origin_candidates(trades: pd.DataFrame, *, whale_threshold: float, limit: int | None = None) -> list[str]:
    """Wallets worth asking about: every identified wallet whose prints in the
    tape add up to the whale threshold or more, largest single print first.

    The tape handed in should already be the screened one (sports, weather
    and price markets removed), so the budget is not spent on a sports whale.
    The sum, not the largest print, decides who is asked: a wallet that
    reaches the wallet table through twenty small prints is a wallet too.
    """

    if trades is None or trades.empty or "wallet" not in trades.columns:
        return []
    df = trades[["wallet"] + (["notional"] if "notional" in trades.columns else [])].copy()
    df["wallet"] = df["wallet"].astype(str).str.strip().str.lower()
    df = df[md.identified_wallets(df["wallet"])]
    if df.empty:
        return []
    df["notional"] = pd.to_numeric(df.get("notional", 0.0), errors="coerce").fillna(0.0)
    per_wallet = df.groupby("wallet")["notional"].agg(["max", "sum"])
    per_wallet = per_wallet[per_wallet["sum"] >= float(whale_threshold)].sort_values(["max", "sum"], ascending=False)
    wallets = [str(w) for w in per_wallet.index]
    if limit is not None:
        wallets = wallets[: max(0, int(limit))]
    return wallets


def _needs_lookup(row: Mapping[str, Any] | None, now_ts: int, retry_hours: float) -> bool:
    if row is None:
        return True
    if str(row.get("state")) == ORIGIN_MEASURED:
        return False
    try:
        fetched = int(row.get("fetched_at") or 0)
    except (TypeError, ValueError):
        fetched = 0
    return (now_ts - fetched) >= retry_hours * 3600.0


def first_trade_map(
    wallets: Iterable[Any],
    *,
    path: Path | str | None = None,
    budget: int | None = None,
    fetch: Callable[[str], dict[str, Any]] | None = None,
    now: Any = None,
    retry_hours: float = RETRY_HOURS,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Origins for the given wallets: from the store when known, else from the
    venue up to ``budget`` calls, and the fresh answers go back into the store.

    Returns ``(origins, meta)``. ``origins`` maps the lowercased wallet to
    ``{first_trade_ts, state, fetched_at}``; wallets nobody has answered for
    are absent, never invented. ``meta`` says how the answers came about
    (asked, cached, fetched, errors, budget, skipped), so a surface can tell
    "no fresh wallet" from "did not ask".
    """

    fetcher = fetch or fetch_first_trade
    limit = lookup_budget() if budget is None else max(0, int(budget))
    if now is None:
        now_ts = int(time.time())
    elif isinstance(now, (int, float)):
        # Unix seconds, as the store keeps them; a bare number handed to
        # pd.Timestamp would be read as nanoseconds.
        now_ts = int(now)
    else:
        stamp = pd.Timestamp(now)
        now_ts = int(stamp.tz_localize("UTC").timestamp() if stamp.tzinfo is None else stamp.timestamp())
    keys: list[str] = []
    seen: set[str] = set()
    for wallet in wallets or []:
        key = _key(wallet)
        if key and key not in seen and bool(md.identified_wallets(pd.Series([key])).iloc[0]):
            seen.add(key)
            keys.append(key)
    meta: dict[str, Any] = {"asked": len(keys), "cached": 0, "fetched": 0, "errors": 0,
                            "budget": limit, "skipped": 0, "store": ""}
    if not keys:
        return {}, meta

    conn: sqlite3.Connection | None = None
    cache: dict[str, dict[str, Any]] = {}
    target = Path(path) if path is not None else ts.store_path()
    try:
        conn = ts.connect(target)
        cache = ts.origin_map(conn, keys)
        meta["store"] = str(target)
    except (sqlite3.Error, OSError) as exc:
        print(f"[warn] wallet origin store: {exc}")
        conn = None
        cache = {}
    meta["cached"] = len(cache)

    pending = [key for key in keys if _needs_lookup(cache.get(key), now_ts, retry_hours)]
    meta["skipped"] = max(0, len(pending) - limit)
    fetched: list[dict[str, Any]] = []
    for key in pending[:limit]:
        row = dict(fetcher(key))
        row["wallet"] = key
        row["fetched_at"] = now_ts
        if row.get("state") == ORIGIN_ERROR:
            meta["errors"] += 1
        fetched.append(row)
    meta["fetched"] = len(fetched)
    if conn is not None:
        try:
            if fetched:
                ts.record_origins(conn, fetched)
        except sqlite3.Error as exc:
            print(f"[warn] wallet origin record: {exc}")
        finally:
            try:
                conn.close()
            except sqlite3.Error:
                pass

    origins: dict[str, dict[str, Any]] = {key: dict(cache[key]) for key in keys if key in cache}
    for row in fetched:
        origins[row["wallet"]] = {"first_trade_ts": row.get("first_trade_ts"), "state": row.get("state"),
                                  "fetched_at": row.get("fetched_at")}
    return origins, meta


def age_days(first_trade_ts: Any, at: Any) -> float | None:
    """Days between a first trade and a moment ``at`` (Timestamp or Unix
    seconds), clipped at zero; None when either side is missing."""

    try:
        start = float(first_trade_ts)
    except (TypeError, ValueError):
        return None
    if isinstance(at, (int, float)):
        end = float(at)
    else:
        stamp = pd.Timestamp(at)
        if pd.isna(stamp):
            return None
        end = float(stamp.tz_localize("UTC").timestamp() if stamp.tzinfo is None else stamp.timestamp())
    return max(0.0, (end - start) / 86_400.0)
