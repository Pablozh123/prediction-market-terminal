"""Append-only signal ledger with a SHA-256 hash chain (Streamlit-free).

Every monitor signal the pipeline emits is persisted once in
``data/signal_ledger.sqlite`` (WAL mode, separate from the copy-trading DB so
the audit log stays independent of trading state). Rows are chained: each row
stores the payload hash of the previous row (genesis: 64 zeros) and a row hash
over (payload_hash + prev_hash + emitted_at + methodology_version), so any
edit or deletion of a historical row breaks ``verify_chain``.

Counting rules (these are the public explanation of every aggregate):

- Only source-confirmed resolutions count. A signal is marked resolved only
  when the resolution source reports a decisive settle price for its market.
- Voided or ambiguous outcomes are excluded from the hit-rate denominator;
  they are never counted as losses.
- A resolution whose modeled PnL is zero or cannot be computed counts as not
  profitable.
- Modeled PnL is frozen at the emit price (per 100 dollars staked). Later
  price moves never change a recorded row.

Only signals that carry both a ``market_key`` and an ``outcome`` are
resolvable; all other rows stay pending forever and are reported as
``not_resolvable`` in the aggregates.

The ledger assumes a single writer (the background scanner); readers may open
the database concurrently thanks to WAL.
"""

from __future__ import annotations

import hashlib
import json
import math
import numbers
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

import pandas as pd

METHODOLOGY_VERSION = "monitor-v1.0"
DEFAULT_LEDGER_PATH = Path("data/signal_ledger.sqlite")
GENESIS_HASH = "0" * 64

# A settle price at or above the win floor counts as won, at or below the loss
# ceiling as lost. Anything in between is ambiguous (mirrors the decisive
# resolution bands used for closed Polymarket markets elsewhere in the repo).
DECISIVE_WIN_FLOOR = 0.95
DECISIVE_LOSS_CEILING = 0.05

_SCHEMA = """
CREATE TABLE IF NOT EXISTS signals_emitted (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    emitted_at TEXT NOT NULL,
    methodology_version TEXT NOT NULL,
    signal_type TEXT NOT NULL DEFAULT '',
    severity TEXT NOT NULL DEFAULT '',
    platform TEXT NOT NULL DEFAULT '',
    market_key TEXT NOT NULL DEFAULT '',
    outcome TEXT NOT NULL DEFAULT '',
    price_at_emit REAL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    prev_hash TEXT NOT NULL,
    row_hash TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_signals_emitted_dedup
    ON signals_emitted (payload_hash, substr(emitted_at, 1, 10));

CREATE INDEX IF NOT EXISTS idx_signals_emitted_market
    ON signals_emitted (market_key);

CREATE TABLE IF NOT EXISTS signals_resolved (
    signal_id INTEGER PRIMARY KEY REFERENCES signals_emitted(id),
    resolved_at TEXT NOT NULL,
    resolution_source TEXT NOT NULL,
    outcome_result TEXT NOT NULL,
    price_at_resolution REAL,
    pnl_modeled REAL,
    resolution_hash TEXT NOT NULL
);
"""


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _normalize_value(value: Any) -> Any:
    """Make a payload value JSON-canonical: NaN/NaT/inf become None, numpy
    scalars become plain Python numbers, containers are normalized recursively.
    Anything else is left for json.dumps(default=str)."""

    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, numbers.Integral):
        return int(value)
    if isinstance(value, numbers.Real):
        number = float(value)
        if math.isnan(number) or math.isinf(number):
            return None
        return number
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        return {str(key): _normalize_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_normalize_value(item) for item in value]
    try:
        if bool(pd.isna(value)):
            return None
    except (TypeError, ValueError):
        pass
    return value


def canonical_payload_json(payload: Mapping[str, Any]) -> str:
    """Canonical JSON of one signal row: sorted keys, compact separators,
    NaN normalized to null so the hash is reproducible across processes."""

    normalized = {str(key): _normalize_value(value) for key, value in payload.items()}
    return json.dumps(normalized, sort_keys=True, separators=(",", ":"), default=str)


def payload_hash_for(payload: Mapping[str, Any]) -> str:
    return _sha256(canonical_payload_json(payload))


def row_hash_for(payload_hash: str, prev_hash: str, emitted_at: str, methodology_version: str) -> str:
    return _sha256(payload_hash + prev_hash + emitted_at + methodology_version)


def resolution_hash_for(
    signal_id: int,
    outcome_result: str,
    price_at_resolution: float | None,
    resolved_at: str,
    emit_row_hash: str,
) -> str:
    price_text = "" if price_at_resolution is None else f"{float(price_at_resolution):.6f}"
    return _sha256(str(int(signal_id)) + outcome_result + price_text + resolved_at + emit_row_hash)


def modeled_pnl_per_100(price_at_emit: float | None, outcome_result: str) -> float | None:
    """Modeled PnL for a 100 dollar stake bought at the emit price.

    won:  100 * (1 - p) / p  (shares 100/p settle at 1)
    lost: -100
    Anything else (voided, unknown, missing or degenerate emit price) has no
    modeled PnL and returns None.
    """

    if outcome_result not in ("won", "lost"):
        return None
    if price_at_emit is None:
        return None
    price = float(price_at_emit)
    if math.isnan(price) or not 0.0 < price < 1.0:
        return None
    if outcome_result == "won":
        return 100.0 * (1.0 - price) / price
    return -100.0


def init_ledger(db_path: str | Path = DEFAULT_LEDGER_PATH) -> sqlite3.Connection:
    """Open (and create if needed) the ledger database in WAL mode."""

    path_text = str(db_path)
    if path_text != ":memory:":
        Path(path_text).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path_text, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.executescript(_SCHEMA)
    conn.commit()
    return conn


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    try:
        if bool(pd.isna(value)):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def _clean_price(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def emit_signals(
    conn: sqlite3.Connection,
    signals_df: pd.DataFrame,
    methodology_version: str = METHODOLOGY_VERSION,
) -> int:
    """Append new signal rows to the chained ledger. Returns the number of
    rows written.

    Idempotent per UTC day: a payload whose canonical hash already exists with
    the same emitted_at date is skipped, so re-scanning the same signals never
    duplicates ledger rows.
    """

    if signals_df is None or signals_df.empty:
        return 0
    emitted_at = _utc_now_iso()
    today = emitted_at[:10]
    with conn:
        seen_today = {
            str(row["payload_hash"])
            for row in conn.execute(
                "SELECT payload_hash FROM signals_emitted WHERE substr(emitted_at, 1, 10) = ?",
                (today,),
            )
        }
        last = conn.execute("SELECT payload_hash FROM signals_emitted ORDER BY id DESC LIMIT 1").fetchone()
        prev_hash = str(last["payload_hash"]) if last is not None else GENESIS_HASH
        written = 0
        for _, row in signals_df.iterrows():
            payload = {str(key): value for key, value in row.items()}
            payload_json = canonical_payload_json(payload)
            payload_hash = _sha256(payload_json)
            if payload_hash in seen_today:
                continue
            row_hash = row_hash_for(payload_hash, prev_hash, emitted_at, methodology_version)
            conn.execute(
                """
                INSERT INTO signals_emitted (
                    emitted_at, methodology_version, signal_type, severity, platform,
                    market_key, outcome, price_at_emit, payload_json, payload_hash,
                    prev_hash, row_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    emitted_at,
                    methodology_version,
                    _clean_text(row.get("signal_type")),
                    _clean_text(row.get("severity")),
                    _clean_text(row.get("platform")).lower(),
                    _clean_text(row.get("market_key")),
                    _clean_text(row.get("outcome")),
                    _clean_price(row.get("price")),
                    payload_json,
                    payload_hash,
                    prev_hash,
                    row_hash,
                ),
            )
            seen_today.add(payload_hash)
            prev_hash = payload_hash
            written += 1
    return written


def safe_emit_signals(
    signals_df: pd.DataFrame,
    db_path: str | Path = DEFAULT_LEDGER_PATH,
    methodology_version: str = METHODOLOGY_VERSION,
) -> tuple[int, str]:
    """Best-effort emit for background jobs: never raises. Returns
    (rows written, error detail or empty string)."""

    try:
        conn = init_ledger(db_path)
    except Exception as exc:  # noqa: BLE001 - deliberately broad: logging must not kill the scan
        return 0, f"ledger open failed: {exc}"
    try:
        return emit_signals(conn, signals_df, methodology_version), ""
    except Exception as exc:  # noqa: BLE001
        return 0, f"ledger write failed: {exc}"
    finally:
        try:
            conn.close()
        except Exception:
            pass


def pending_market_keys(conn: sqlite3.Connection) -> list[str]:
    """Distinct market keys of resolvable signals that have no resolution yet."""

    rows = conn.execute(
        """
        SELECT DISTINCT market_key FROM signals_emitted
        WHERE market_key != '' AND outcome != ''
          AND id NOT IN (SELECT signal_id FROM signals_resolved)
        ORDER BY market_key
        """
    ).fetchall()
    return [str(row["market_key"]) for row in rows]


def resolve_pending(
    conn: sqlite3.Connection,
    fetch_resolved_fn: Callable[[list[str]], Mapping[str, Mapping[str, Any]]],
) -> int:
    """Join open resolvable signals against source resolutions.

    ``fetch_resolved_fn`` receives the distinct pending market keys and returns
    a mapping ``market_key -> {"status": "resolved"|"voided"|"open",
    "outcome_prices": {outcome_lowercase: settle_price}, "source": str}``.
    Markets that are missing from the mapping or reported as "open" stay
    pending and are retried on the next run.

    Outcome classification for resolved markets: settle >= 0.95 is won,
    settle <= 0.05 is lost, anything else (including an outcome name the
    source cannot map) is recorded as unknown and excluded from the hit rate,
    like voided. Returns the number of newly resolved signals.
    """

    keys = pending_market_keys(conn)
    if not keys:
        return 0
    resolutions = fetch_resolved_fn(keys)
    if not resolutions:
        return 0
    pending_rows = conn.execute(
        """
        SELECT id, market_key, outcome, price_at_emit, row_hash FROM signals_emitted
        WHERE market_key != '' AND outcome != ''
          AND id NOT IN (SELECT signal_id FROM signals_resolved)
        ORDER BY id
        """
    ).fetchall()
    resolved_at = _utc_now_iso()
    written = 0
    with conn:
        for row in pending_rows:
            market = resolutions.get(str(row["market_key"]))
            if not market:
                continue
            status = str(market.get("status", "")).lower()
            if status not in ("resolved", "voided"):
                continue
            source = _clean_text(market.get("source")) or "unknown"
            outcome_prices = market.get("outcome_prices") or {}
            settle = _clean_price(outcome_prices.get(str(row["outcome"]).strip().lower()))
            if status == "voided":
                outcome_result = "voided"
            elif settle is None:
                outcome_result = "unknown"
            elif settle >= DECISIVE_WIN_FLOOR:
                outcome_result = "won"
            elif settle <= DECISIVE_LOSS_CEILING:
                outcome_result = "lost"
            else:
                outcome_result = "unknown"
            pnl = modeled_pnl_per_100(_clean_price(row["price_at_emit"]), outcome_result)
            conn.execute(
                """
                INSERT INTO signals_resolved (
                    signal_id, resolved_at, resolution_source, outcome_result,
                    price_at_resolution, pnl_modeled, resolution_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(row["id"]),
                    resolved_at,
                    source,
                    outcome_result,
                    settle,
                    pnl,
                    resolution_hash_for(int(row["id"]), outcome_result, settle, resolved_at, str(row["row_hash"])),
                ),
            )
            written += 1
    return written


def verify_chain(conn: sqlite3.Connection) -> tuple[bool, int]:
    """Walk the emit chain from genesis. Returns (ok, rows checked); stops at
    the first broken row."""

    prev_hash = GENESIS_HASH
    checked = 0
    for row in conn.execute(
        """
        SELECT emitted_at, methodology_version, payload_json, payload_hash, prev_hash, row_hash
        FROM signals_emitted ORDER BY id
        """
    ):
        checked += 1
        if _sha256(str(row["payload_json"])) != str(row["payload_hash"]):
            return False, checked
        if str(row["prev_hash"]) != prev_hash:
            return False, checked
        expected_row_hash = row_hash_for(
            str(row["payload_hash"]),
            str(row["prev_hash"]),
            str(row["emitted_at"]),
            str(row["methodology_version"]),
        )
        if expected_row_hash != str(row["row_hash"]):
            return False, checked
        prev_hash = str(row["payload_hash"])
    return True, checked


def ledger_aggregates(conn: sqlite3.Connection) -> dict[str, Any]:
    """Aggregate ledger counters. Invariant:
    emitted = resolved + pending + not_resolvable."""

    emitted = int(conn.execute("SELECT COUNT(*) AS n FROM signals_emitted").fetchone()["n"])
    resolvable = int(
        conn.execute(
            "SELECT COUNT(*) AS n FROM signals_emitted WHERE market_key != '' AND outcome != ''"
        ).fetchone()["n"]
    )
    resolved = int(conn.execute("SELECT COUNT(*) AS n FROM signals_resolved").fetchone()["n"])
    decisive = int(
        conn.execute(
            "SELECT COUNT(*) AS n FROM signals_resolved WHERE outcome_result IN ('won', 'lost')"
        ).fetchone()["n"]
    )
    hits = int(
        conn.execute(
            """
            SELECT COUNT(*) AS n FROM signals_resolved
            WHERE outcome_result IN ('won', 'lost') AND pnl_modeled IS NOT NULL AND pnl_modeled > 0
            """
        ).fetchone()["n"]
    )
    pnl_sum_row = conn.execute(
        "SELECT SUM(pnl_modeled) AS total FROM signals_resolved WHERE outcome_result IN ('won', 'lost')"
    ).fetchone()
    bounds = conn.execute("SELECT MIN(emitted_at) AS first, MAX(emitted_at) AS last FROM signals_emitted").fetchone()
    chain_ok, chain_checked = verify_chain(conn)
    return {
        "emitted": emitted,
        "resolvable": resolvable,
        "not_resolvable": emitted - resolvable,
        "resolved": resolved,
        "pending": resolvable - resolved,
        "decisive": decisive,
        "hit_rate": (hits / decisive) if decisive else None,
        "pnl_modeled_sum": float(pnl_sum_row["total"]) if pnl_sum_row["total"] is not None else 0.0,
        "first_emit": bounds["first"],
        "last_emit": bounds["last"],
        "chain_ok": chain_ok,
        "chain_checked": chain_checked,
    }


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, (list, tuple)):
        return list(value)
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        return parsed if isinstance(parsed, list) else []
    return []


def polymarket_resolution_map(raw_markets: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Map raw Gamma market payloads to the resolve_pending contract.

    A market only counts as resolved once its settle prices are decisive
    (some outcome at or above the win floor); a closed market whose prices all
    sit at 0.5, or whose UMA status says voided/cancelled, is voided. Closed
    markets with indecisive prices stay "open" so they are retried instead of
    being recorded prematurely.
    """

    resolutions: dict[str, dict[str, Any]] = {}
    for market in raw_markets:
        if not isinstance(market, dict):
            continue
        key = str(market.get("conditionId") or "").strip()
        if not key:
            continue
        outcome_prices: dict[str, float] = {}
        outcomes = _as_list(market.get("outcomes"))
        prices = _as_list(market.get("outcomePrices"))
        for index, name in enumerate(outcomes):
            label = str(name or "").strip().lower()
            price = _clean_price(prices[index]) if index < len(prices) else None
            if label and price is not None:
                outcome_prices[label] = price
        uma_status = str(market.get("umaResolutionStatus") or "").lower()
        explicitly_voided = any(marker in uma_status for marker in ("void", "cancel", "refund"))
        all_half = bool(outcome_prices) and all(abs(price - 0.5) <= 1e-6 for price in outcome_prices.values())
        decisive = any(price >= DECISIVE_WIN_FLOOR for price in outcome_prices.values())
        if not bool(market.get("closed")):
            status = "open"
        elif explicitly_voided or all_half:
            status = "voided"
        elif decisive:
            status = "resolved"
        else:
            status = "open"
        resolutions[key] = {
            "status": status,
            "outcome_prices": outcome_prices,
            "source": "polymarket_gamma",
        }
    return resolutions
