"""SQLite-backed paper copy-trading for one public Polymarket wallet.

This module is intentionally paper-only. It observes a target wallet's public
trades, scales them into a local simulated portfolio, and never places orders.
"""

from __future__ import annotations

import collections
import json
import math
import queue
import sqlite3
import threading
import time
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import pandas as pd
import requests

try:  # websocket-client — optional; the listener degrades gracefully when absent.
    import websocket as _websocket
except Exception:  # pragma: no cover - import guard
    _websocket = None

from src import prediction_markets as md


COPY_TARGET_WALLET = "0x204f72f35326db932158cba6adff0b9a1da95e14"
SWISSTONY_LABEL = "Swisstony"
DEFAULT_DB_PATH = Path("data/copy_trading.sqlite")
DEFAULT_SETTINGS_PATH = Path("data/copy_settings.json")
PER_TRADER_START_CASH = 1000.0
# ROI-ranking thresholds for the discovery list (spec §4.2). Total completed
# trades are not exposed by the public leaderboard feed, so traded volume is
# used as the activity proxy alongside a positive-ROI floor.
ROI_MIN_VOLUME = 1000.0
ROI_MIN_WIN_RATE = 0.0
DEFAULT_STATUS_PATH = Path("data/copy_trader_status.json")
DEFAULT_STOP_PATH = Path("data/copy_trader.stop")
MIN_COPY_NOTIONAL = 0.01
POLYGON_RPC_URL = "https://polygon-pokt.nodies.app"
POLYGON_BLOCK_SECONDS = 2
# Polymarket real-time data stream. The off-chain match is broadcast here the
# instant it happens — earlier than the on-chain OrderFilled log the slow path
# reads (which only appears ~one Polygon block / ~2s after the match).
RTDS_WS_URL = "wss://ws-live-data.polymarket.com"
POLYMARKET_EXCHANGE_ADDRESSES = (
    "0xe111180000d2663c0091e4f400237545b87b996b",
    "0xe2222d279d744050d28e00520010520000310f59",
)
ORDER_FILLED_TOPIC = "0xd543adfd945773f1a62f74f0ee55a5e3b9b1a28262980ba90b1a89f2ea84d8ee"
TOKEN_DECIMALS = 1_000_000
LOG_BLOCK_CHUNK = 100
POLYGON_USDC_CONTRACTS = (
    "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174",
    "0x3c499c542cef5e3811e1192ce70d8cc03d5c3359",
)


@dataclass(frozen=True)
class CopySettings:
    target_wallet: str = COPY_TARGET_WALLET
    paper_start_cash: float = 1000.0
    copy_scale: float = 0.01
    max_order_equity_pct: float = 0.05
    live_trading_enabled: bool = False
    trade_limit: int = 250
    dynamic_sizing_enabled: bool = True
    dynamic_sizing_multiplier: float = 1.0
    dynamic_stats_refresh_seconds: int = 300
    dynamic_scale_max: float = 0.01
    dynamic_scale_min: float = 0.0
    dynamic_order_cap_from_tony: bool = True
    auto_top_up_enabled: bool = True
    auto_top_up_amount: float = 1000.0
    auto_top_up_threshold: float = 1.0
    min_copy_notional: float = MIN_COPY_NOTIONAL


@dataclass(frozen=True)
class PaperOrder:
    dedup_key: str
    status: str
    reason: str
    side: str
    source_notional: float
    copy_notional: float = 0.0
    copy_size: float = 0.0
    realized_pnl: float = 0.0


@dataclass(frozen=True)
class SyncResult:
    processed: int = 0
    copied: int = 0
    skipped: int = 0
    duplicates: int = 0
    seeded: bool = False
    source: str = "api"
    logs_seen: int = 0
    latest_block: int = 0
    from_block: int = 0
    to_block: int = 0
    errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class PortfolioSnapshot:
    cash: float
    position_value: float
    equity: float
    realized_pnl: float
    unrealized_pnl: float
    positions: pd.DataFrame


@dataclass(frozen=True)
class TonyWalletStats:
    updated_at: str
    position_value: float
    cash: float
    visible_equity: float
    open_positions: int
    open_markets: int
    mean_market_position: float
    median_market_position: float
    p75_market_position: float
    p90_market_position: float
    p95_market_position: float
    max_market_position: float
    mean_market_position_pct: float
    median_market_position_pct: float
    p75_market_position_pct: float
    p90_market_position_pct: float
    p95_market_position_pct: float
    max_market_position_pct: float


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_copy_settings(
    path: str | Path = DEFAULT_SETTINGS_PATH,
    default: CopySettings | None = None,
) -> CopySettings:
    base = asdict(default or CopySettings())
    settings_path = Path(path)
    if settings_path.exists():
        try:
            payload = json.loads(settings_path.read_text(encoding="utf-8"))
            if isinstance(payload, Mapping):
                for key in base:
                    if key in payload:
                        base[key] = payload[key]
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            pass
    bool_fields = {"live_trading_enabled", "dynamic_sizing_enabled", "dynamic_order_cap_from_tony", "auto_top_up_enabled"}
    int_fields = {"trade_limit", "dynamic_stats_refresh_seconds"}
    cleaned: dict[str, Any] = {}
    for key, value in base.items():
        if key in bool_fields:
            if isinstance(value, str):
                cleaned[key] = value.strip().lower() in {"1", "true", "yes", "on"}
            else:
                cleaned[key] = bool(value)
        elif key in int_fields:
            try:
                cleaned[key] = max(0, int(float(value)))
            except (TypeError, ValueError):
                cleaned[key] = int(getattr(CopySettings(), key))
        elif key == "target_wallet":
            cleaned[key] = str(value or COPY_TARGET_WALLET).strip().lower()
        else:
            try:
                cleaned[key] = max(0.0, float(value))
            except (TypeError, ValueError):
                cleaned[key] = float(getattr(CopySettings(), key))
    cleaned["dynamic_sizing_multiplier"] = max(0.0, float(cleaned.get("dynamic_sizing_multiplier", 1.0)))
    cleaned["max_order_equity_pct"] = min(float(cleaned.get("max_order_equity_pct", 0.0)), 1.0)
    cleaned["dynamic_scale_max"] = min(float(cleaned.get("dynamic_scale_max", 0.0)), 1.0)
    cleaned["dynamic_scale_min"] = min(float(cleaned.get("dynamic_scale_min", 0.0)), 1.0)
    return CopySettings(**cleaned)


def save_copy_settings(settings: CopySettings, path: str | Path = DEFAULT_SETTINGS_PATH) -> None:
    settings_path = Path(path)
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(asdict(settings), indent=2, sort_keys=True), encoding="utf-8")


def connect(db_path: str | Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute("PRAGMA journal_mode = WAL")
    init_db(conn)
    return conn


def init_db(conn: sqlite3.Connection, start_cash: float = 1000.0) -> None:
    conn.executescript(
        f"""
        CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS paper_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dedup_key TEXT UNIQUE NOT NULL,
            source_wallet TEXT NOT NULL,
            source_tx TEXT,
            source_time TEXT,
            market_key TEXT,
            asset TEXT,
            title TEXT,
            outcome TEXT,
            source_side TEXT,
            source_price REAL,
            source_size REAL,
            source_notional REAL,
            copy_side TEXT,
            copy_price REAL,
            copy_size REAL,
            copy_notional REAL,
            realized_pnl REAL DEFAULT 0,
            status TEXT NOT NULL,
            reason TEXT,
            source_json TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS positions (
            trader_wallet TEXT NOT NULL DEFAULT '{COPY_TARGET_WALLET}',
            asset TEXT NOT NULL,
            market_key TEXT,
            title TEXT,
            outcome TEXT,
            shares REAL NOT NULL,
            avg_price REAL NOT NULL,
            cost_basis REAL NOT NULL,
            last_price REAL NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (trader_wallet, asset)
        );

        CREATE TABLE IF NOT EXISTS tony_positions (
            asset TEXT PRIMARY KEY,
            market_key TEXT,
            title TEXT,
            outcome TEXT,
            shares REAL NOT NULL,
            avg_price REAL,
            last_price REAL,
            seeded_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS cash_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_time TEXT NOT NULL,
            amount REAL NOT NULL,
            cash_before REAL NOT NULL,
            cash_after REAL NOT NULL,
            reason TEXT NOT NULL,
            trader_wallet TEXT NOT NULL DEFAULT '{COPY_TARGET_WALLET}',
            note TEXT
        );

        CREATE TABLE IF NOT EXISTS traders (
            wallet TEXT PRIMARY KEY,
            label TEXT,
            active INTEGER NOT NULL DEFAULT 1,
            start_cash REAL NOT NULL DEFAULT 0,
            cash REAL NOT NULL DEFAULT 0,
            copy_scale_override REAL,
            rank_score REAL NOT NULL DEFAULT 0,
            added_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS source_positions (
            wallet TEXT NOT NULL,
            asset TEXT NOT NULL,
            market_key TEXT,
            title TEXT,
            outcome TEXT,
            shares REAL NOT NULL,
            avg_price REAL,
            last_price REAL,
            seeded_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (wallet, asset)
        );

        CREATE TABLE IF NOT EXISTS trader_stats (
            wallet TEXT PRIMARY KEY,
            roi REAL,
            pnl REAL,
            win_rate REAL,
            trades INTEGER,
            volume REAL,
            last_refresh TEXT
        );
        """
    )
    if _get_meta(conn, "cash") is None:
        _set_meta(conn, "cash", f"{float(start_cash):.10f}")
    if _get_meta(conn, "paper_start_cash") is None:
        _set_meta(conn, "paper_start_cash", f"{float(start_cash):.10f}")
    if _get_meta(conn, "live_trading_enabled") is None:
        _set_meta(conn, "live_trading_enabled", "false")
    _migrate_to_multitrader(conn, start_cash)
    conn.commit()


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row["name"]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _migrate_positions_to_sub_accounts(conn: sqlite3.Connection) -> None:
    """Rebuild ``positions`` with the composite ``(trader_wallet, asset)`` key.

    SQLite cannot ALTER a primary key, so single-wallet databases (``asset`` PK)
    are rebuilt once. Idempotent: a no-op once the key is already composite.
    """
    info = conn.execute("PRAGMA table_info(positions)").fetchall()
    pk_cols = {str(row["name"]) for row in info if row["pk"]}
    if pk_cols == {"trader_wallet", "asset"}:
        return
    conn.executescript(
        f"""
        CREATE TABLE positions_migrated (
            trader_wallet TEXT NOT NULL DEFAULT '{COPY_TARGET_WALLET}',
            asset TEXT NOT NULL,
            market_key TEXT,
            title TEXT,
            outcome TEXT,
            shares REAL NOT NULL,
            avg_price REAL NOT NULL,
            cost_basis REAL NOT NULL,
            last_price REAL NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (trader_wallet, asset)
        );
        INSERT OR IGNORE INTO positions_migrated
            (trader_wallet, asset, market_key, title, outcome, shares, avg_price, cost_basis, last_price, updated_at)
        SELECT trader_wallet, asset, market_key, title, outcome, shares, avg_price, cost_basis, last_price, updated_at
        FROM positions;
        DROP TABLE positions;
        ALTER TABLE positions_migrated RENAME TO positions;
        """
    )


def _migrate_to_multitrader(conn: sqlite3.Connection, start_cash: float = 1000.0) -> None:
    """Bring single-wallet databases up to the multi-trader schema.

    Idempotent and safe to run on every ``init_db``:
    - adds the ``trader_wallet`` column to legacy ``positions`` / ``cash_events``
      tables (backfilling existing rows to Swisstony via the column default),
    - seeds Swisstony as the first trader (decision #4 in the spec), carrying the
      current global cash/start-cash so the prior history is preserved,
    - mirrors the existing ``tony_positions`` into ``source_positions`` once.

    The engine still runs on the single-wallet code paths; this only lays down
    the sub-portfolio scaffolding so later steps can generalise onto it.
    """
    for table in ("positions", "cash_events"):
        if "trader_wallet" not in _table_columns(conn, table):
            conn.execute(
                f"ALTER TABLE {table} ADD COLUMN trader_wallet TEXT NOT NULL DEFAULT '{COPY_TARGET_WALLET}'"
            )
    _migrate_positions_to_sub_accounts(conn)

    if conn.execute("SELECT 1 FROM traders LIMIT 1").fetchone() is None:
        now = utc_now()
        seed_start_cash = _get_float_meta(conn, "paper_start_cash", float(start_cash))
        seed_cash = _get_float_meta(conn, "cash", seed_start_cash)
        conn.execute(
            """
            INSERT OR IGNORE INTO traders
                (wallet, label, active, start_cash, cash, copy_scale_override, rank_score, added_at, updated_at)
            VALUES (?, ?, 1, ?, ?, NULL, 0, ?, ?)
            """,
            (COPY_TARGET_WALLET, SWISSTONY_LABEL, seed_start_cash, seed_cash, now, now),
        )

    if _get_meta(conn, "source_positions_migrated_at") is None:
        conn.execute(
            """
            INSERT OR IGNORE INTO source_positions
                (wallet, asset, market_key, title, outcome, shares, avg_price, last_price, seeded_at, updated_at)
            SELECT ?, asset, market_key, title, outcome, shares, avg_price, last_price, seeded_at, updated_at
            FROM tony_positions
            """,
            (COPY_TARGET_WALLET,),
        )
        _set_meta(conn, "source_positions_migrated_at", utc_now())

    if _get_meta(conn, "trade_dedup_wallet_prefixed_at") is None:
        # Trade dedup keys now lead with the source wallet so two wallets with an
        # empty/shared tx hash can't false-collide. Prefix the pre-existing
        # 6-field BUY/SELL keys (settlement REDEEM/MERGE and resolution_* keys
        # keep their own formats) so they still match the new derivation.
        conn.execute(
            """
            UPDATE paper_orders
            SET dedup_key = source_wallet || '|' || dedup_key
            WHERE source_wallet <> ''
              AND (LENGTH(dedup_key) - LENGTH(REPLACE(dedup_key, '|', ''))) = 5
              AND (dedup_key LIKE '%|BUY|%' OR dedup_key LIKE '%|SELL|%')
            """
        )
        _set_meta(conn, "trade_dedup_wallet_prefixed_at", utc_now())


def reset_paper_portfolio(start_cash: float = 1000.0, db_path: str | Path = DEFAULT_DB_PATH) -> None:
    path = Path(db_path)
    if path.exists():
        path.unlink()
    conn = connect(path)
    try:
        _set_meta(conn, "cash", f"{float(start_cash):.10f}")
        _set_meta(conn, "paper_start_cash", f"{float(start_cash):.10f}")
        conn.execute(
            "UPDATE traders SET cash = ?, start_cash = ?, updated_at = ?",
            (float(start_cash), float(start_cash), utc_now()),
        )
        conn.commit()
    finally:
        conn.close()


def add_paper_cash(
    amount: float = 1000.0,
    db_path: str | Path = DEFAULT_DB_PATH,
    reason: str = "manual_top_up",
    note: str = "",
    wallet: str = COPY_TARGET_WALLET,
) -> float:
    """Top up a trader's sub-account cash and record the movement."""
    conn = connect(db_path)
    try:
        _ensure_trader(conn, wallet, _get_float_meta(conn, "paper_start_cash", 1000.0))
        cash_after = _record_trader_cash_event(conn, wallet, amount, reason, note)
        conn.commit()
        return cash_after
    finally:
        conn.close()


def _record_trader_cash_event(conn: sqlite3.Connection, wallet: str, amount: float, reason: str, note: str = "") -> float:
    amount = float(amount)
    if amount <= 0:
        raise ValueError("cash top-up amount must be positive")
    cash_before = _get_trader_cash(conn, wallet, 1000.0)
    cash_after = cash_before + amount
    _set_trader_cash(conn, wallet, cash_after)
    conn.execute(
        """
        INSERT INTO cash_events (event_time, amount, cash_before, cash_after, reason, trader_wallet, note)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (utc_now(), amount, cash_before, cash_after, reason, wallet, note),
    )
    return cash_after


def _auto_top_up_if_needed(
    conn: sqlite3.Connection,
    wallet: str,
    cash: float,
    settings: CopySettings,
    phase: str,
    parsed: Mapping[str, Any],
) -> float:
    if not settings.auto_top_up_enabled:
        return cash
    threshold = max(0.0, float(settings.auto_top_up_threshold))
    if cash > threshold:
        return cash
    note = (
        f"{phase}: cash {cash:.4f} <= threshold {threshold:.4f}; "
        f"source {parsed.get('side', '')} {float(parsed.get('source_notional', 0.0) or 0.0):.2f}; "
        f"tx {parsed.get('source_tx', '')}"
    )
    return _record_trader_cash_event(conn, wallet, settings.auto_top_up_amount, "auto_copy_cash_top_up", note)


def get_cash_events(db_path: str | Path = DEFAULT_DB_PATH, conn: sqlite3.Connection | None = None) -> pd.DataFrame:
    should_close = conn is None
    conn = conn or connect(db_path)
    try:
        return pd.read_sql_query("SELECT * FROM cash_events ORDER BY id DESC", conn)
    finally:
        if should_close:
            conn.close()


def fetch_source_trades(wallet: str, limit: int = 250) -> pd.DataFrame:
    return md.get_polymarket_trades(limit=limit, min_cash=0.0, user=wallet)


def fetch_source_activity(wallet: str, limit: int = 500, pages: int = 1) -> pd.DataFrame:
    if not wallet:
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    limit = max(1, min(int(limit), 500))
    for page in range(max(1, int(pages))):
        params = {"user": wallet, "limit": limit, "offset": page * limit}
        try:
            response = requests.get(f"{md.POLY_DATA}/activity", params=params, timeout=20, headers=md.HTTP_HEADERS)
            response.raise_for_status()
            data = response.json()
        except (requests.RequestException, ValueError):
            break
        batch = data if isinstance(data, list) else data.get("data", [])
        if not batch:
            break
        rows.extend(batch)
        if len(batch) < limit:
            break
    return pd.DataFrame(rows)


def fetch_closed_position_assets(wallet: str, pages: int = 4, limit: int = 50) -> dict[str, set[str]]:
    winners: dict[str, set[str]] = {}
    unresolved_conditions: set[str] = set()
    limit = max(1, min(int(limit), 50))
    for page in range(max(1, int(pages))):
        params = {"user": wallet, "limit": limit, "offset": page * limit}
        try:
            response = requests.get(f"{md.POLY_DATA}/closed-positions", params=params, timeout=20, headers=md.HTTP_HEADERS)
            response.raise_for_status()
            data = response.json()
        except (requests.RequestException, ValueError):
            break
        batch = data if isinstance(data, list) else data.get("data", [])
        if not batch:
            break
        for row in batch:
            condition = str(row.get("conditionId", "") or "")
            asset = str(row.get("asset", "") or "")
            cur_price = _to_float(row.get("curPrice"), 0.0)
            if condition and asset and cur_price >= 0.99:
                winners.setdefault(condition, set()).add(asset)
            elif condition:
                unresolved_conditions.add(condition)
        if len(batch) < limit:
            break
    missing = unresolved_conditions.difference(winners)
    if missing:
        _merge_winner_assets(winners, fetch_closed_market_winner_assets(missing))
    return winners


def fetch_closed_market_winner_assets(condition_ids: Any, max_conditions: int = 250) -> dict[str, set[str]]:
    """Resolve closed-market winner token IDs directly from the CLOB market API.

    Wallet closed-position rows only identify a winner when that wallet held the
    winning token. For copy trading we also need loser-only expiries, so this
    fallback asks the market itself which token settled at 1.00.
    """

    winners: dict[str, set[str]] = {}
    seen: set[str] = set()
    conditions = []
    for condition in condition_ids or []:
        value = str(condition or "").strip()
        if value and value not in seen:
            seen.add(value)
            conditions.append(value)
        if len(conditions) >= max_conditions:
            break

    for condition in conditions:
        try:
            response = requests.get(f"{md.POLY_CLOB}/markets/{condition}", timeout=20, headers=md.HTTP_HEADERS)
            response.raise_for_status()
            market = response.json()
        except (requests.RequestException, ValueError):
            continue
        if not isinstance(market, dict) or not bool(market.get("closed")):
            continue
        tokens = market.get("tokens") if isinstance(market.get("tokens"), list) else []
        for token in tokens:
            if not isinstance(token, Mapping):
                continue
            token_id = str(_first(token, "token_id", "tokenId", "asset", "id") or "")
            price = _to_float(token.get("price"), 0.0)
            is_winner = bool(token.get("winner")) or price >= 0.99
            if token_id and is_winner:
                winners.setdefault(condition, set()).add(token_id)
    return winners


def _merge_winner_assets(target: dict[str, set[str]], extra: Mapping[str, set[str]]) -> dict[str, set[str]]:
    for condition, assets in extra.items():
        clean_assets = {str(asset) for asset in assets if str(asset)}
        if clean_assets:
            target.setdefault(str(condition), set()).update(clean_assets)
    return target


def fetch_position_metadata(wallet: str, pages: int = 12, closed_pages: int = 4) -> dict[str, dict[str, Any]]:
    metadata: dict[str, dict[str, Any]] = {}
    for endpoint, limit, max_pages in (("positions", 50, pages), ("closed-positions", 50, closed_pages)):
        for page in range(max(1, int(max_pages))):
            params = {"user": wallet, "limit": limit, "offset": page * limit}
            try:
                response = requests.get(f"{md.POLY_DATA}/{endpoint}", params=params, timeout=20, headers=md.HTTP_HEADERS)
                response.raise_for_status()
                data = response.json()
            except (requests.RequestException, ValueError):
                break
            batch = data if isinstance(data, list) else data.get("data", [])
            if not batch:
                break
            for row in batch:
                asset = str(row.get("asset", "") or "")
                if not asset:
                    continue
                metadata[asset] = {
                    "asset": asset,
                    "market_key": str(row.get("conditionId", "") or ""),
                    "title": str(row.get("title", "") or ""),
                    "outcome": str(row.get("outcome", "") or ""),
                    "last_price": _to_float(_first(row, "curPrice", "currentPrice"), 0.0),
                }
            if len(batch) < limit:
                break
    return metadata


def fetch_tony_wallet_stats(
    wallet: str = COPY_TARGET_WALLET,
    pages: int = 4,
    limit: int = 500,
    rpc_url: str = POLYGON_RPC_URL,
) -> TonyWalletStats:
    """Fetch current visible wallet value and open-position distribution.

    The Polymarket value endpoint covers open conditional-token positions.
    Polygon USDC balances are added as visible idle cash for the proxy wallet.
    """
    positions: list[dict[str, Any]] = []
    limit = max(1, min(int(limit), 500))
    for page in range(max(1, int(pages))):
        params = {"user": wallet, "limit": limit, "offset": page * limit}
        response = requests.get(f"{md.POLY_DATA}/positions", params=params, timeout=20, headers=md.HTTP_HEADERS)
        if response.status_code >= 400:
            break
        data = response.json()
        batch = data if isinstance(data, list) else data.get("data", [])
        if not batch:
            break
        positions.extend(batch)
        if len(batch) < limit:
            break

    position_value = _fetch_wallet_position_value(wallet)
    if position_value <= 0:
        position_value = sum(_position_row_value(row) for row in positions)
    cash = _fetch_polygon_usdc_balance(wallet, rpc_url=rpc_url)
    visible_equity = position_value + cash

    by_market: dict[str, float] = {}
    for row in positions:
        key = str(_first(row, "conditionId", "market", "slug", "asset") or "")
        value = _position_row_value(row)
        if key and value > 0:
            by_market[key] = by_market.get(key, 0.0) + value
    stats = _position_value_stats(list(by_market.values()))
    equity = visible_equity if visible_equity > 0 else 0.0

    return TonyWalletStats(
        updated_at=utc_now(),
        position_value=position_value,
        cash=cash,
        visible_equity=visible_equity,
        open_positions=len(positions),
        open_markets=len(by_market),
        mean_market_position=stats["mean"],
        median_market_position=stats["median"],
        p75_market_position=stats["p75"],
        p90_market_position=stats["p90"],
        p95_market_position=stats["p95"],
        max_market_position=stats["max"],
        mean_market_position_pct=stats["mean"] / equity if equity else 0.0,
        median_market_position_pct=stats["median"] / equity if equity else 0.0,
        p75_market_position_pct=stats["p75"] / equity if equity else 0.0,
        p90_market_position_pct=stats["p90"] / equity if equity else 0.0,
        p95_market_position_pct=stats["p95"] / equity if equity else 0.0,
        max_market_position_pct=stats["max"] / equity if equity else 0.0,
    )


def refresh_tony_wallet_stats(
    conn: sqlite3.Connection,
    wallet: str = COPY_TARGET_WALLET,
    settings: CopySettings | None = None,
    force: bool = False,
    rpc_url: str = POLYGON_RPC_URL,
) -> TonyWalletStats | None:
    settings = settings or CopySettings(target_wallet=wallet)
    if not settings.dynamic_sizing_enabled:
        return None
    now_ts = datetime.now(timezone.utc).timestamp()
    last_ts = _get_float_meta(conn, f"wallet_stat:{wallet}:ts", _get_float_meta(conn, "tony_wallet_stats_ts", 0.0))
    refresh_seconds = max(0, int(settings.dynamic_stats_refresh_seconds))
    if not force and last_ts > 0 and now_ts - last_ts < refresh_seconds:
        return _read_tony_wallet_stats(conn)
    try:
        stats = fetch_tony_wallet_stats(wallet, rpc_url=rpc_url)
    except Exception as exc:
        _set_meta(conn, "tony_wallet_stats_error", str(exc)[:500])
        return _read_tony_wallet_stats(conn)
    _store_tony_wallet_stats(conn, stats, now_ts, wallet)
    return stats


def sync_copy_trades(
    wallet: str = COPY_TARGET_WALLET,
    settings: CopySettings | None = None,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> SyncResult:
    settings = settings or CopySettings(target_wallet=wallet)
    trades = fetch_source_trades(wallet, limit=settings.trade_limit)
    conn = connect(db_path)
    try:
        refresh_tony_wallet_stats(conn, wallet, settings=settings)
        seeded = _get_meta(conn, "tony_seeded_at") is not None
        if not seeded:
            seed_positions = md.get_polymarket_positions(wallet, limit=500)
            seed_tony_positions(conn, seed_positions)
            seed_source_positions(conn, wallet, seed_positions)
            seed_count = _mark_existing_trades_as_seed(conn, trades, wallet)
            baseline_cutoff = int(_sort_source_trades(trades)["timestamp"].max()) if not trades.empty else 0
            _set_meta(conn, "target_wallet", wallet)
            _set_meta(conn, "tony_seeded_at", utc_now())
            _set_meta(conn, "baseline_cutoff_ts", str(baseline_cutoff))
            _set_meta(conn, "baseline_trade_limit", str(settings.trade_limit))
            _set_meta(conn, "last_sync_at", utc_now())
            conn.commit()
            return SyncResult(processed=seed_count, skipped=seed_count, seeded=True)

        copied = skipped = duplicates = processed = 0
        errors: list[str] = []
        ordered = _sort_source_trades(trades)
        baseline_cutoff = int(_get_float_meta(conn, "baseline_cutoff_ts", 0.0))
        for _, row in ordered.iterrows():
            try:
                if int(row.get("timestamp") or 0) <= baseline_cutoff:
                    parsed = parse_source_trade(row.to_dict(), wallet)
                    if not conn.execute("SELECT 1 FROM paper_orders WHERE dedup_key = ?", (parsed["dedup_key"],)).fetchone():
                        order = PaperOrder(
                            parsed["dedup_key"],
                            "seed_observed",
                            "pre_baseline_cutoff",
                            parsed["side"],
                            parsed["source_notional"],
                        )
                        _insert_order(conn, parsed, order, row.to_dict())
                        processed += 1
                        skipped += 1
                    else:
                        duplicates += 1
                    continue
                order = apply_paper_trade(conn, row.to_dict(), settings)
                if order.status == "duplicate":
                    _merge_trade_metadata(conn, row.to_dict(), wallet)
                    duplicates += 1
                else:
                    processed += 1
                    if order.status == "copied":
                        copied += 1
                    else:
                        skipped += 1
            except Exception as exc:  # Keep one bad row from stopping the sync.
                errors.append(str(exc))
        _set_meta(conn, "last_sync_at", utc_now())
        conn.commit()
        return SyncResult(processed=processed, copied=copied, skipped=skipped, duplicates=duplicates, errors=tuple(errors))
    finally:
        conn.close()


def sync_settlement_activity(
    wallet: str = COPY_TARGET_WALLET,
    settings: CopySettings | None = None,
    db_path: str | Path = DEFAULT_DB_PATH,
    limit: int = 500,
    pages: int = 1,
    closed_pages: int = 4,
    metadata_pages: int = 2,
) -> SyncResult:
    settings = settings or CopySettings(target_wallet=wallet)
    activity = fetch_source_activity(wallet, limit=limit, pages=pages)
    conn = connect(db_path)
    try:
        backfill_position_metadata(conn, wallet, pages=metadata_pages, closed_pages=closed_pages)
        winners_by_condition = fetch_closed_position_assets(wallet, pages=closed_pages)
        open_conditions = _open_paper_conditions(conn, wallet)
        missing_open_conditions = open_conditions.difference(winners_by_condition)
        if missing_open_conditions:
            _merge_winner_assets(winners_by_condition, fetch_closed_market_winner_assets(missing_open_conditions))
        processed = copied = skipped = duplicates = 0
        errors: list[str] = []
        reconciled = _reconcile_resolved_loser_positions(conn, winners_by_condition, wallet)
        processed += reconciled
        copied += reconciled
        if not activity.empty:
            ordered = _sort_activity(activity)
            for _, row in ordered.iterrows():
                source = row.to_dict()
                typ = str(source.get("type", "") or "").upper()
                if typ not in {"REDEEM", "MERGE"}:
                    continue
                dedup_key = settlement_dedup_key(source)
                if conn.execute("SELECT 1 FROM paper_orders WHERE dedup_key = ?", (dedup_key,)).fetchone():
                    duplicates += 1
                    continue
                try:
                    parsed = parse_settlement_activity(source, wallet)
                    if typ == "REDEEM":
                        order, asset = _apply_redeem(conn, parsed, winners_by_condition)
                    else:
                        order, asset = _apply_merge(conn, parsed)
                    parsed["asset"] = asset
                    _insert_order(conn, parsed, order, source)
                    processed += 1
                    if order.status == "settled":
                        copied += 1
                    else:
                        skipped += 1
                except Exception as exc:
                    errors.append(str(exc))
        reconciled_winners = _reconcile_resolved_winner_positions(conn, winners_by_condition, wallet)
        processed += reconciled_winners
        copied += reconciled_winners
        _set_meta(conn, "settlement_last_sync_at", utc_now())
        conn.commit()
        return SyncResult(processed=processed, copied=copied, skipped=skipped, duplicates=duplicates, source="settlement", errors=tuple(errors))
    finally:
        conn.close()


def sync_onchain_copy_trades(
    wallet: str = COPY_TARGET_WALLET,
    settings: CopySettings | None = None,
    db_path: str | Path = DEFAULT_DB_PATH,
    rpc_url: str = POLYGON_RPC_URL,
    lookback_blocks: int = 1200,
    max_block_span: int = 2000,
    confirmations: int = 0,
) -> SyncResult:
    """Copy target-wallet fills from Polygon OrderFilled logs.

    This is the low-latency path. It watches Polymarket exchange events where
    the target wallet is the maker, because those logs directly encode the
    wallet's signed order side, token id, filled size, and price.
    """
    settings = settings or CopySettings(target_wallet=wallet)
    conn = connect(db_path)
    try:
        if _get_meta(conn, "tony_seeded_at") is None:
            conn.close()
            seed_result = sync_copy_trades(wallet, settings=settings, db_path=db_path)
            conn = connect(db_path)
            if seed_result.errors:
                return SyncResult(seeded=seed_result.seeded, source="chain", errors=seed_result.errors)

        refresh_tony_wallet_stats(conn, wallet, settings=settings, rpc_url=rpc_url)

        # The on-chain path is now a best-effort reconciliation layer behind the
        # WebSocket. A rate-limited or flaky free RPC must degrade to a soft error,
        # never crash the daemon loop (which would skip the WebSocket status write).
        try:
            latest_raw = _rpc_call(rpc_url, "eth_blockNumber", [])
        except (requests.RequestException, RuntimeError, ValueError) as exc:
            return SyncResult(source="chain", errors=(f"rpc unavailable: {exc}",))
        latest_block = max(0, int(str(latest_raw), 16) - max(0, confirmations))
        previous = _get_meta(conn, "fast_last_block")
        if previous is None:
            from_block = max(0, latest_block - max(0, lookback_blocks) + 1)
        else:
            from_block = int(float(previous)) + 1
        to_block = min(latest_block, from_block + max(1, max_block_span) - 1)
        if from_block > to_block:
            _set_meta(conn, "fast_last_seen_at", utc_now())
            _set_meta(conn, "fast_latest_block", str(latest_block))
            conn.commit()
            return SyncResult(source="chain", latest_block=latest_block, from_block=from_block, to_block=to_block)

        try:
            logs = _fetch_order_filled_logs(rpc_url, wallet, from_block, to_block)
            logs = sorted(
                logs,
                key=lambda log: (
                    _hex_to_int(log.get("blockNumber")),
                    _hex_to_int(log.get("transactionIndex")),
                    _hex_to_int(log.get("logIndex")),
                ),
            )
            block_timestamps = _block_timestamps(rpc_url, {int(log["blockNumber"], 16) for log in logs if log.get("blockNumber")})
        except (requests.RequestException, RuntimeError, ValueError) as exc:
            return SyncResult(source="chain", latest_block=latest_block, from_block=from_block, to_block=to_block, errors=(f"rpc unavailable: {exc}",))
        baseline_cutoff = int(_get_float_meta(conn, "baseline_cutoff_ts", 0.0))
        copied = skipped = duplicates = processed = 0
        errors: list[str] = []

        for log in logs:
            try:
                source_trade = decode_order_filled_log(log, wallet, block_timestamps)
                if not source_trade:
                    skipped += 1
                    continue
                if int(source_trade["timestamp"]) <= baseline_cutoff:
                    parsed = parse_source_trade(source_trade, wallet)
                    if conn.execute("SELECT 1 FROM paper_orders WHERE dedup_key = ?", (parsed["dedup_key"],)).fetchone():
                        duplicates += 1
                    else:
                        order = PaperOrder(
                            parsed["dedup_key"],
                            "seed_observed",
                            "pre_baseline_cutoff",
                            parsed["side"],
                            parsed["source_notional"],
                        )
                        _insert_order(conn, parsed, order, source_trade)
                        processed += 1
                        skipped += 1
                    continue
                order = apply_paper_trade(conn, source_trade, settings)
                if order.status == "duplicate":
                    duplicates += 1
                else:
                    processed += 1
                    if order.status == "copied":
                        copied += 1
                    else:
                        skipped += 1
            except Exception as exc:
                errors.append(str(exc))

        _set_meta(conn, "fast_last_block", str(to_block))
        _set_meta(conn, "fast_latest_block", str(latest_block))
        _set_meta(conn, "fast_last_seen_at", utc_now())
        _set_meta(conn, "fast_rpc_url", rpc_url)
        conn.commit()
        return SyncResult(
            processed=processed,
            copied=copied,
            skipped=skipped,
            duplicates=duplicates,
            source="chain",
            logs_seen=len(logs),
            latest_block=latest_block,
            from_block=from_block,
            to_block=to_block,
            errors=tuple(errors),
        )
    finally:
        try:
            conn.close()
        except Exception:
            pass


def sync_active_copy_trades(
    settings: CopySettings | None = None,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> dict[str, SyncResult]:
    """Run the public-API copy sync once per active trader.

    Generalises the single ``target_wallet`` entry point onto the active
    ``traders`` list; each trader is synced against its own wallet so trades
    land in that trader's sub-account.
    """
    results: dict[str, SyncResult] = {}
    for wallet in active_trader_wallets(db_path=db_path):
        wallet_settings = replace(settings, target_wallet=wallet) if settings is not None else CopySettings(target_wallet=wallet)
        results[wallet] = sync_copy_trades(wallet, settings=wallet_settings, db_path=db_path)
    return results


def sync_active_onchain_copy_trades(
    settings: CopySettings | None = None,
    db_path: str | Path = DEFAULT_DB_PATH,
    **kwargs: Any,
) -> dict[str, SyncResult]:
    """Run the low-latency on-chain copy sync once per active trader."""
    results: dict[str, SyncResult] = {}
    for wallet in active_trader_wallets(db_path=db_path):
        wallet_settings = replace(settings, target_wallet=wallet) if settings is not None else CopySettings(target_wallet=wallet)
        results[wallet] = sync_onchain_copy_trades(wallet, settings=wallet_settings, db_path=db_path, **kwargs)
    return results


def rtds_subscribe_payload() -> dict[str, Any]:
    """Subscribe message for the RTDS global trade firehose.

    The per-wallet/per-market filters are broken upstream (only an empty filter
    returns data), so we subscribe to every trade and match the target wallets
    client-side in :func:`decode_rtds_trade`.
    """

    return {"action": "subscribe", "subscriptions": [{"topic": "activity", "type": "trades", "filters": ""}]}


def decode_rtds_trade(message: Any, target_wallets: Iterable[str]) -> dict[str, Any] | None:
    """Normalize one RTDS ``activity/trades`` message into a source-trade dict.

    Returns the same shape as :func:`decode_order_filled_log` so the existing
    paper pipeline can consume it unchanged. Returns ``None`` when the message is
    not a trade for a tracked wallet, or is malformed. Detection happens at the
    off-chain match instant — earlier than the on-chain log the slow path reads.
    """

    if not isinstance(message, Mapping):
        return None
    topic = str(message.get("topic", "") or "")
    msg_type = str(message.get("type", "") or "")
    if topic and topic != "activity":
        return None
    if msg_type and msg_type not in {"trades", "trade"}:
        return None
    payload = message.get("payload")
    trade = payload if isinstance(payload, Mapping) else message
    targets = {_normalize_address(str(wallet)) for wallet in target_wallets if str(wallet).strip()}
    wallet = _normalize_address(str(trade.get("proxyWallet", "") or trade.get("wallet", "") or ""))
    if not wallet or wallet not in targets:
        return None
    side = str(trade.get("side", "") or "").upper()
    if side not in {"BUY", "SELL"}:
        return None
    asset = str(trade.get("asset", "") or "")
    price = _to_float(trade.get("price"), 0.0)
    size = _to_float(trade.get("size"), 0.0)
    if not asset or price <= 0 or size <= 0:
        return None
    timestamp = _timestamp_value(trade)
    source_time = datetime.fromtimestamp(timestamp, timezone.utc).isoformat() if timestamp else ""
    title = str(trade.get("title", "") or "")
    return {
        "platform": "Polymarket",
        "source": "rtds_ws",
        "wallet": wallet,
        "transaction_hash": str(trade.get("transactionHash", "") or ""),
        "timestamp": timestamp,
        "time": source_time,
        "side": side,
        "asset": asset,
        "price": price,
        "size": size,
        "notional": price * size,
        "market_key": str(_first(trade, "market_key", "conditionId") or ""),
        "title": title or f"Polymarket token {asset[:10]}...",
        "outcome": str(trade.get("outcome", "") or ""),
    }


class RtdsTradeListener:
    """Background WebSocket listener for the Polymarket RTDS trade firehose.

    Connects to :data:`RTDS_WS_URL`, subscribes to the global trade feed, matches
    the tracked wallets client-side and buffers decoded trades for the copy
    daemon to drain each loop. Degrades to a no-op when ``websocket-client`` is
    not installed, so importing this module never requires the dependency.
    """

    def __init__(self, wallets: Iterable[str], *, url: str = RTDS_WS_URL, ping_interval: float = 5.0) -> None:
        self._url = url
        self._ping_interval = max(1.0, float(ping_interval))
        self._lock = threading.Lock()
        self._wallets = {_normalize_address(str(w)) for w in wallets if str(w).strip()}
        self._queue: "queue.Queue[dict[str, Any]]" = queue.Queue()
        self._seen: "collections.deque[str]" = collections.deque(maxlen=8192)
        self._seen_set: set[str] = set()
        self._app: Any = None
        self._thread: threading.Thread | None = None
        self._running = False
        self._connected = False
        self._last_message_at: float | None = None
        self._last_error: str | None = None
        self._messages = 0
        self._matched = 0

    @staticmethod
    def available() -> bool:
        return _websocket is not None

    def set_wallets(self, wallets: Iterable[str]) -> None:
        with self._lock:
            self._wallets = {_normalize_address(str(w)) for w in wallets if str(w).strip()}

    def _wallets_snapshot(self) -> set[str]:
        with self._lock:
            return set(self._wallets)

    def start(self) -> bool:
        if _websocket is None:
            self._last_error = "websocket-client not installed"
            return False
        if self._running:
            return True
        self._running = True
        self._thread = threading.Thread(target=self._run, name="rtds-trade-listener", daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        self._running = False
        app = self._app
        if app is not None:
            try:
                app.close()
            except Exception:
                pass

    def drain(self) -> list[dict[str, Any]]:
        trades: list[dict[str, Any]] = []
        while True:
            try:
                trades.append(self._queue.get_nowait())
            except queue.Empty:
                break
        return trades

    def status(self) -> dict[str, Any]:
        return {
            "available": _websocket is not None,
            "running": self._running,
            "connected": self._connected,
            "messages": self._messages,
            "matched": self._matched,
            "queued": self._queue.qsize(),
            "last_message_at": self._last_message_at,
            "last_error": self._last_error,
        }

    def _run(self) -> None:
        while self._running:
            try:
                self._app = _websocket.WebSocketApp(
                    self._url,
                    on_open=self._on_open,
                    on_message=self._on_message,
                    on_error=self._on_error,
                    on_close=self._on_close,
                )
                self._app.run_forever(ping_interval=self._ping_interval, ping_timeout=self._ping_interval - 1)
            except Exception as exc:  # pragma: no cover - network resilience
                self._last_error = str(exc)
            self._connected = False
            if self._running:
                time.sleep(2.0)

    def _on_open(self, ws: Any) -> None:  # pragma: no cover - network callback
        self._connected = True
        self._last_error = None
        try:
            ws.send(json.dumps(rtds_subscribe_payload()))
        except Exception as exc:
            self._last_error = str(exc)

    def _on_message(self, ws: Any, raw: Any) -> None:  # pragma: no cover - thin wrapper over handle_message
        self.handle_message(raw)

    def handle_message(self, raw: Any) -> int:
        """Decode a raw WS frame and enqueue matched trades. Returns count enqueued."""

        self._messages += 1
        self._last_message_at = time.monotonic()
        try:
            data = json.loads(raw) if isinstance(raw, (str, bytes, bytearray)) else raw
        except (ValueError, TypeError):
            return 0
        messages = data if isinstance(data, list) else [data]
        # Tolerate both envelope shapes: payload as a single trade object or as
        # a list of trade objects.
        expanded: list[Any] = []
        for message in messages:
            payload = message.get("payload") if isinstance(message, Mapping) else None
            if isinstance(payload, list):
                expanded.extend({**message, "payload": item} for item in payload if isinstance(item, Mapping))
            else:
                expanded.append(message)
        wallets = self._wallets_snapshot()
        enqueued = 0
        for message in expanded:
            trade = decode_rtds_trade(message, wallets)
            if not trade:
                continue
            key = trade_dedup_key(trade, trade["wallet"])
            with self._lock:
                if key in self._seen_set:
                    continue
                if len(self._seen) == self._seen.maxlen:
                    self._seen_set.discard(self._seen[0])
                self._seen.append(key)
                self._seen_set.add(key)
            self._queue.put(trade)
            self._matched += 1
            enqueued += 1
        return enqueued

    def _on_error(self, ws: Any, error: Any) -> None:  # pragma: no cover - network callback
        self._last_error = str(error)

    def _on_close(self, ws: Any, *args: Any) -> None:  # pragma: no cover - network callback
        self._connected = False


def apply_ws_trades(
    trades: list[Mapping[str, Any]],
    settings: CopySettings | None = None,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> dict[str, SyncResult]:
    """Apply already-decoded WebSocket trades into each tracked wallet's sub-account.

    Mirrors the on-chain fast path's per-fill loop: trades at or before the
    baseline cutoff are recorded as observed (not copied); a wallet that has not
    been seeded yet is skipped (the on-chain/API path seeds it, WS copying
    resumes on the next drain). The cross-detection fill dedup in
    :func:`apply_paper_trade` keeps the slower on-chain reconciliation from
    re-copying anything applied here.
    """

    by_wallet: dict[str, list[Mapping[str, Any]]] = {}
    for trade in trades:
        wallet = _normalize_address(str(trade.get("wallet", "") or trade.get("source_wallet", "")))
        if wallet:
            by_wallet.setdefault(wallet, []).append(trade)
    results: dict[str, SyncResult] = {}
    if not by_wallet:
        return results
    conn = connect(db_path)
    try:
        active = {_normalize_address(w) for w in active_trader_wallets(db_path=db_path, conn=conn)}
        seeded = _get_meta(conn, "tony_seeded_at") is not None
        baseline_cutoff = int(_get_float_meta(conn, "baseline_cutoff_ts", 0.0))
        for wallet, wallet_trades in by_wallet.items():
            if active and wallet not in active:
                continue
            if not seeded:
                results[wallet] = SyncResult(source="ws", skipped=len(wallet_trades))
                continue
            wallet_settings = replace(settings, target_wallet=wallet) if settings is not None else CopySettings(target_wallet=wallet)
            copied = skipped = duplicates = processed = 0
            errors: list[str] = []
            for trade in sorted(wallet_trades, key=lambda item: _timestamp_value(item)):
                try:
                    if int(_timestamp_value(trade)) <= baseline_cutoff:
                        parsed = parse_source_trade(trade, wallet)
                        if conn.execute("SELECT 1 FROM paper_orders WHERE dedup_key = ?", (parsed["dedup_key"],)).fetchone():
                            duplicates += 1
                        else:
                            order = PaperOrder(parsed["dedup_key"], "seed_observed", "pre_baseline_cutoff", parsed["side"], parsed["source_notional"])
                            _insert_order(conn, parsed, order, trade)
                            processed += 1
                            skipped += 1
                        continue
                    order = apply_paper_trade(conn, trade, wallet_settings)
                    if order.status == "duplicate":
                        duplicates += 1
                    else:
                        processed += 1
                        if order.status == "copied":
                            copied += 1
                        else:
                            skipped += 1
                except Exception as exc:
                    errors.append(str(exc))
            results[wallet] = SyncResult(
                processed=processed,
                copied=copied,
                skipped=skipped,
                duplicates=duplicates,
                source="ws",
                errors=tuple(errors),
            )
        conn.commit()
    finally:
        conn.close()
    return results


def sync_active_settlement_activity(
    settings: CopySettings | None = None,
    db_path: str | Path = DEFAULT_DB_PATH,
    **kwargs: Any,
) -> dict[str, SyncResult]:
    """Run the settlement/redeem recycling sync once per active trader."""
    results: dict[str, SyncResult] = {}
    for wallet in active_trader_wallets(db_path=db_path):
        wallet_settings = replace(settings, target_wallet=wallet) if settings is not None else CopySettings(target_wallet=wallet)
        results[wallet] = sync_settlement_activity(wallet, settings=wallet_settings, db_path=db_path, **kwargs)
    return results


def aggregate_sync_results(results: Mapping[str, SyncResult] | list[SyncResult]) -> SyncResult:
    """Combine per-trader sync results into one summary for status reporting."""
    items = list(results.values()) if isinstance(results, Mapping) else list(results)
    if not items:
        return SyncResult()
    return SyncResult(
        processed=sum(r.processed for r in items),
        copied=sum(r.copied for r in items),
        skipped=sum(r.skipped for r in items),
        duplicates=sum(r.duplicates for r in items),
        seeded=any(r.seeded for r in items),
        source=items[0].source,
        logs_seen=sum(r.logs_seen for r in items),
        latest_block=max((r.latest_block for r in items), default=0),
        errors=tuple(err for r in items for err in r.errors),
    )


def apply_paper_trade(
    conn: sqlite3.Connection,
    source_trade: Mapping[str, Any],
    settings: CopySettings | None = None,
) -> PaperOrder:
    settings = settings or CopySettings()
    init_db(conn, settings.paper_start_cash)
    dedup_key = trade_dedup_key(source_trade, settings.target_wallet)
    existing = conn.execute("SELECT status FROM paper_orders WHERE dedup_key = ?", (dedup_key,)).fetchone()
    if existing:
        return PaperOrder(dedup_key=dedup_key, status="duplicate", reason="duplicate", side="", source_notional=0.0)
    # Cross-detection dedup: the WebSocket reports a fill at off-chain match time
    # while the on-chain log reports it at block time, so the timestamp-bearing
    # dedup_key differs between the two paths for the same economic fill. Match on
    # the stable fill identity (wallet, tx, asset, side) so the slow on-chain
    # reconciliation never re-copies a fill the WebSocket already applied.
    if _fill_already_recorded(conn, source_trade, settings.target_wallet):
        return PaperOrder(dedup_key=dedup_key, status="duplicate", reason="duplicate_fill", side="", source_notional=0.0)

    parsed = parse_source_trade(source_trade, settings.target_wallet)
    if parsed["price"] <= 0 or parsed["size"] <= 0 or parsed["source_notional"] <= 0 or not parsed["asset"]:
        order = PaperOrder(
            dedup_key=dedup_key,
            status="skipped",
            reason="invalid_trade",
            side=parsed["side"],
            source_notional=parsed["source_notional"],
        )
        _insert_order(conn, parsed, order, source_trade)
        return order

    if parsed["side"] == "BUY":
        order = _apply_buy(conn, parsed, settings)
    elif parsed["side"] == "SELL":
        order = _apply_sell(conn, parsed)
    else:
        order = PaperOrder(
            dedup_key=dedup_key,
            status="skipped",
            reason="unsupported_side",
            side=parsed["side"],
            source_notional=parsed["source_notional"],
        )
    _insert_order(conn, parsed, order, source_trade)
    return order


def _snapshot_from_positions(
    cash: float,
    positions: pd.DataFrame,
    realized: float,
    price_lookup: Callable[[str], float | None] | None,
) -> PortfolioSnapshot:
    if positions.empty:
        return PortfolioSnapshot(cash=cash, position_value=0.0, equity=cash, realized_pnl=realized, unrealized_pnl=0.0, positions=positions)

    valued = positions.copy()
    current_prices: list[float] = []
    for _, row in valued.iterrows():
        looked_up = price_lookup(str(row["asset"])) if price_lookup else None
        price = float(looked_up) if looked_up is not None else float(row.get("last_price") or row.get("avg_price") or 0.0)
        current_prices.append(price)
    valued["current_price"] = current_prices
    valued["value"] = valued["shares"] * valued["current_price"]
    valued["unrealized_pnl"] = valued["value"] - valued["cost_basis"]
    valued["pnl_pct"] = valued["unrealized_pnl"] / valued["cost_basis"].replace({0: pd.NA})
    position_value = float(valued["value"].sum())
    unrealized = float(valued["unrealized_pnl"].sum())
    return PortfolioSnapshot(
        cash=cash,
        position_value=position_value,
        equity=cash + position_value,
        realized_pnl=realized,
        unrealized_pnl=unrealized,
        positions=valued.sort_values("value", ascending=False).reset_index(drop=True),
    )


def value_paper_portfolio(
    db_path: str | Path = DEFAULT_DB_PATH,
    price_lookup: Callable[[str], float | None] | None = None,
    conn: sqlite3.Connection | None = None,
) -> PortfolioSnapshot:
    """Aggregate snapshot across every sub-account (total cash + all positions)."""
    owns_conn = conn is None
    conn = connect(db_path) if conn is None else conn
    try:
        return _snapshot_from_positions(_total_cash(conn), get_positions(conn=conn), _realized_pnl(conn), price_lookup)
    finally:
        if owns_conn:
            conn.close()


def value_sub_account(
    wallet: str,
    db_path: str | Path = DEFAULT_DB_PATH,
    price_lookup: Callable[[str], float | None] | None = None,
    conn: sqlite3.Connection | None = None,
) -> PortfolioSnapshot:
    """Snapshot for a single trader's sub-account (its own cash + positions)."""
    owns_conn = conn is None
    conn = connect(db_path) if conn is None else conn
    try:
        cash = _get_trader_cash(conn, wallet, _get_float_meta(conn, "paper_start_cash", 1000.0))
        positions = pd.read_sql_query(
            "SELECT * FROM positions WHERE trader_wallet = ? ORDER BY updated_at DESC", conn, params=(wallet,)
        )
        return _snapshot_from_positions(cash, positions, _realized_pnl(conn, wallet), price_lookup)
    finally:
        if owns_conn:
            conn.close()


def seed_tony_positions(conn: sqlite3.Connection, positions: pd.DataFrame) -> int:
    if positions.empty:
        return 0
    now = utc_now()
    seeded = 0
    for _, row in positions.iterrows():
        asset = str(row.get("asset", "") or "")
        shares = _to_float(row.get("size"), 0.0)
        if not asset or shares <= 0:
            continue
        conn.execute(
            """
            INSERT INTO tony_positions (asset, market_key, title, outcome, shares, avg_price, last_price, seeded_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(asset) DO UPDATE SET
                market_key = excluded.market_key,
                title = excluded.title,
                outcome = excluded.outcome,
                shares = excluded.shares,
                avg_price = excluded.avg_price,
                last_price = excluded.last_price,
                updated_at = excluded.updated_at
            """,
            (
                asset,
                str(row.get("market_key", "") or ""),
                str(row.get("title", "") or ""),
                str(row.get("outcome", "") or ""),
                shares,
                _to_float(row.get("avg_price"), 0.0),
                _to_float(row.get("current_price"), 0.0),
                now,
                now,
            ),
        )
        seeded += 1
    return seeded


def seed_source_positions(conn: sqlite3.Connection, wallet: str, positions: pd.DataFrame) -> int:
    """Seed a source wallet's real open positions into ``source_positions``.

    Wallet-scoped generalisation of :func:`seed_tony_positions`; keyed on
    ``(wallet, asset)`` so every followed trader keeps its own mirror.
    """
    if not wallet or positions.empty:
        return 0
    now = utc_now()
    seeded = 0
    for _, row in positions.iterrows():
        asset = str(row.get("asset", "") or "")
        shares = _to_float(row.get("size"), 0.0)
        if not asset or shares <= 0:
            continue
        conn.execute(
            """
            INSERT INTO source_positions (wallet, asset, market_key, title, outcome, shares, avg_price, last_price, seeded_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(wallet, asset) DO UPDATE SET
                market_key = excluded.market_key,
                title = excluded.title,
                outcome = excluded.outcome,
                shares = excluded.shares,
                avg_price = excluded.avg_price,
                last_price = excluded.last_price,
                updated_at = excluded.updated_at
            """,
            (
                wallet,
                asset,
                str(row.get("market_key", "") or ""),
                str(row.get("title", "") or ""),
                str(row.get("outcome", "") or ""),
                shares,
                _to_float(row.get("avg_price"), 0.0),
                _to_float(row.get("current_price"), 0.0),
                now,
                now,
            ),
        )
        seeded += 1
    return seeded


def get_paper_orders(db_path: str | Path = DEFAULT_DB_PATH, conn: sqlite3.Connection | None = None) -> pd.DataFrame:
    owns_conn = conn is None
    conn = connect(db_path) if conn is None else conn
    try:
        return pd.read_sql_query("SELECT * FROM paper_orders ORDER BY id DESC", conn)
    finally:
        if owns_conn:
            conn.close()


def get_positions(db_path: str | Path = DEFAULT_DB_PATH, conn: sqlite3.Connection | None = None) -> pd.DataFrame:
    owns_conn = conn is None
    conn = connect(db_path) if conn is None else conn
    try:
        return pd.read_sql_query("SELECT * FROM positions ORDER BY updated_at DESC", conn)
    finally:
        if owns_conn:
            conn.close()


def get_tony_positions(db_path: str | Path = DEFAULT_DB_PATH, conn: sqlite3.Connection | None = None) -> pd.DataFrame:
    owns_conn = conn is None
    conn = connect(db_path) if conn is None else conn
    try:
        return pd.read_sql_query("SELECT * FROM tony_positions ORDER BY updated_at DESC", conn)
    finally:
        if owns_conn:
            conn.close()


def get_traders(db_path: str | Path = DEFAULT_DB_PATH, conn: sqlite3.Connection | None = None) -> pd.DataFrame:
    owns_conn = conn is None
    conn = connect(db_path) if conn is None else conn
    try:
        return pd.read_sql_query("SELECT * FROM traders ORDER BY added_at ASC", conn)
    finally:
        if owns_conn:
            conn.close()


def get_source_positions(db_path: str | Path = DEFAULT_DB_PATH, conn: sqlite3.Connection | None = None) -> pd.DataFrame:
    owns_conn = conn is None
    conn = connect(db_path) if conn is None else conn
    try:
        return pd.read_sql_query("SELECT * FROM source_positions ORDER BY updated_at DESC", conn)
    finally:
        if owns_conn:
            conn.close()


def active_trader_wallets(db_path: str | Path = DEFAULT_DB_PATH, conn: sqlite3.Connection | None = None) -> list[str]:
    """Return the wallets the engine should copy, in follow order.

    Falls back to the legacy single target wallet if the ``traders`` table is
    empty (e.g. a database created before the multi-trader migration).
    """
    owns_conn = conn is None
    conn = connect(db_path) if conn is None else conn
    try:
        rows = conn.execute("SELECT wallet FROM traders WHERE active = 1 ORDER BY added_at ASC, wallet ASC").fetchall()
        wallets = [str(row["wallet"]) for row in rows if str(row["wallet"] or "")]
        return wallets or [COPY_TARGET_WALLET]
    finally:
        if owns_conn:
            conn.close()


def follow_trader(
    wallet: str,
    label: str = "",
    start_cash: float = PER_TRADER_START_CASH,
    copy_scale_override: float | None = None,
    db_path: str | Path = DEFAULT_DB_PATH,
    conn: sqlite3.Connection | None = None,
) -> bool:
    """Open (or re-activate) a sub-account for ``wallet``.

    Returns True when a new trader row is created, False when an existing one is
    re-activated. Each new sub-account starts with the same ``start_cash`` so
    traders share a fair starting line (spec §4.3).
    """
    wallet = str(wallet or "").strip().lower()
    if not wallet:
        raise ValueError("wallet is required to follow a trader")
    owns_conn = conn is None
    conn = connect(db_path) if conn is None else conn
    try:
        now = utc_now()
        existing = conn.execute("SELECT wallet FROM traders WHERE wallet = ?", (wallet,)).fetchone()
        if existing is None:
            conn.execute(
                """
                INSERT INTO traders
                    (wallet, label, active, start_cash, cash, copy_scale_override, rank_score, added_at, updated_at)
                VALUES (?, ?, 1, ?, ?, ?, 0, ?, ?)
                """,
                (wallet, label or wallet, float(start_cash), float(start_cash), copy_scale_override, now, now),
            )
            conn.commit()
            return True
        conn.execute(
            "UPDATE traders SET active = 1, label = CASE WHEN ? <> '' THEN ? ELSE label END, updated_at = ? WHERE wallet = ?",
            (label, label, now, wallet),
        )
        conn.commit()
        return False
    finally:
        if owns_conn:
            conn.close()


def unfollow_trader(wallet: str, db_path: str | Path = DEFAULT_DB_PATH, conn: sqlite3.Connection | None = None) -> bool:
    """Deactivate a trader's sub-account, keeping its history. True if a row changed."""
    owns_conn = conn is None
    conn = connect(db_path) if conn is None else conn
    try:
        cursor = conn.execute(
            "UPDATE traders SET active = 0, updated_at = ? WHERE wallet = ? AND active = 1",
            (utc_now(), str(wallet or "").strip().lower()),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        if owns_conn:
            conn.close()


def compute_roi(pnl: Any, volume: Any) -> float:
    """Return on traded volume — a capital-size-independent skill proxy (spec §4.2)."""
    pnl_value = _to_float(pnl, 0.0)
    volume_value = _to_float(volume, 0.0)
    return pnl_value / volume_value if volume_value > 0 else 0.0


def _numeric_series(frame: pd.DataFrame, column: str, default: float = 0.0) -> pd.Series:
    if column not in frame:
        return pd.Series(default, index=frame.index, dtype="float64")
    return pd.to_numeric(frame[column], errors="coerce").fillna(default)


def _bool_series(frame: pd.DataFrame, column: str, default: bool = False) -> pd.Series:
    if column not in frame:
        return pd.Series(default, index=frame.index, dtype="bool")
    values = frame[column].fillna(default).to_numpy(dtype=object)
    return pd.Series(values, index=frame.index).astype(bool)


def _log_score(values: pd.Series, floor: float, cap: float | None = None) -> pd.Series:
    """Map a positive numeric series to 0..100 on a log scale."""
    numeric = pd.to_numeric(values, errors="coerce").fillna(0.0).clip(lower=0.0)
    clean_floor = max(float(floor), 1.0)
    observed_cap = float(numeric.quantile(0.95)) if len(numeric) else clean_floor
    clean_cap = max(float(cap) if cap is not None else observed_cap, clean_floor * 1.01)
    lower = math.log10(clean_floor + 1.0)
    upper = math.log10(clean_cap + 1.0)
    if upper <= lower:
        return pd.Series(0.0, index=values.index, dtype="float64")
    return (((numeric + 1.0).map(math.log10) - lower) / (upper - lower) * 100.0).clip(lower=0.0, upper=100.0)


def rank_traders_by_smart_score(
    traders: pd.DataFrame,
    min_volume: float = ROI_MIN_VOLUME,
    require_positive_roi: bool = True,
    min_win_rate: float = ROI_MIN_WIN_RATE,
    exclude_bots: bool = True,
) -> pd.DataFrame:
    """Rank wallets with a transparent PolyHuntr-style smart score.

    PolyHuntr publicly describes a six-factor score built from returns, Sharpe,
    drawdown, win rate, recency, and volume. Public leaderboard rows do not
    expose full 90-day equity curves for every wallet, so this implementation
    keeps the same factor structure and uses explicit proxy columns where the
    exact metric is unavailable.
    """
    if traders is None or traders.empty:
        return pd.DataFrame()
    df = traders.copy()
    pnl = _numeric_series(df, "pnl")
    volume = _numeric_series(df, "volume")
    df["roi"] = [compute_roi(p, v) for p, v in zip(pnl, volume)]
    win_rate_raw = _numeric_series(df, "win_rate", 0.0)
    closed_positions = _numeric_series(df, "closed_positions", 0.0)
    open_positions = _numeric_series(df, "open_positions", 0.0)
    recent_trades = _numeric_series(df, "recent_trades", 0.0)
    recent_notional = _numeric_series(df, "recent_notional", 0.0)
    trades_per_hour = _numeric_series(df, "trades_per_hour", 0.0)
    positions_value = _numeric_series(df, "positions_value", 0.0)
    cash_balance = _numeric_series(df, "cash_balance", 0.0)
    assets_value = _numeric_series(df, "assets_value", 0.0)
    bot_score = _numeric_series(df, "bot_score", 0.0)
    if "assets_value" not in df:
        assets_value = positions_value + cash_balance

    known_win_rate = (win_rate_raw > 0) | (closed_positions > 0)
    win_rate = win_rate_raw.where(known_win_rate, 0.50).clip(lower=0.0, upper=1.0)

    mask = volume >= float(min_volume)
    if require_positive_roi:
        mask = mask & (df["roi"] > 0)
    if min_win_rate > 0:
        mask = mask & (win_rate >= float(min_win_rate))
    if exclude_bots:
        mask = mask & (~_bool_series(df, "is_bot", False))
    ranked = df[mask].copy()
    if ranked.empty:
        return ranked

    pnl = pnl.loc[ranked.index]
    volume = volume.loc[ranked.index]
    roi = pd.to_numeric(ranked["roi"], errors="coerce").fillna(0.0)
    win_rate = win_rate.loc[ranked.index]
    win_rate_raw = win_rate_raw.loc[ranked.index]
    closed_positions = closed_positions.loc[ranked.index]
    open_positions = open_positions.loc[ranked.index]
    recent_trades = recent_trades.loc[ranked.index]
    recent_notional = recent_notional.loc[ranked.index]
    trades_per_hour = trades_per_hour.loc[ranked.index]
    positions_value = positions_value.loc[ranked.index]
    assets_value = assets_value.loc[ranked.index]
    bot_score = bot_score.loc[ranked.index]

    ranked["copy_return_score"] = ((roi.clip(lower=0.0) / 0.30).clip(upper=1.0) * 100.0).round(1)
    sample_factor = ((closed_positions + open_positions + recent_trades) / 50.0).clip(lower=0.25, upper=1.0)
    ranked["copy_sharpe_proxy"] = (
        (((roi.clip(lower=0.0) / 0.20).clip(upper=1.0) * 70.0) + (win_rate * 30.0)) * sample_factor
    ).clip(lower=0.0, upper=100.0).round(1)
    assets_denominator = assets_value.mask(assets_value.eq(0), pd.NA)
    concentration = (positions_value / assets_denominator).fillna(0.0).clip(lower=0.0, upper=2.0)
    drawdown_penalty = (
        (pnl < 0).astype(float) * 45.0
        + (win_rate.lt(0.45) & ((closed_positions > 0) | (win_rate_raw > 0))).astype(float) * 20.0
        + (concentration > 0.85).astype(float) * 20.0
        + (bot_score > 75).astype(float) * 15.0
    )
    ranked["copy_drawdown_proxy"] = (100.0 - drawdown_penalty).clip(lower=0.0, upper=100.0).round(1)
    ranked["copy_win_score"] = (win_rate * 100.0).clip(lower=0.0, upper=100.0).round(1)
    if recent_trades.gt(0).any() or recent_notional.gt(0).any() or trades_per_hour.gt(0).any():
        ranked["copy_recency_score"] = (
            (recent_trades / 25.0).clip(upper=1.0) * 35.0
            + (trades_per_hour / 6.0).clip(upper=1.0) * 35.0
            + _log_score(recent_notional, floor=100.0) * 0.30
        ).clip(lower=0.0, upper=100.0).round(1)
    else:
        ranked["copy_recency_score"] = 50.0
    ranked["copy_volume_score"] = _log_score(volume, floor=max(float(min_volume), 1.0)).round(1)
    ranked["copy_smart_score"] = (
        ranked["copy_return_score"] * 0.35
        + ranked["copy_sharpe_proxy"] * 0.20
        + ranked["copy_drawdown_proxy"] * 0.15
        + ranked["copy_win_score"] * 0.10
        + ranked["copy_recency_score"] * 0.10
        + ranked["copy_volume_score"] * 0.10
    ).clip(lower=0.0, upper=100.0).round(0)
    ranked["rank_score"] = ranked["copy_smart_score"]

    def _grade(score: Any) -> str:
        value = _to_float(score, 0.0)
        if value >= 85:
            return "A"
        if value >= 70:
            return "B"
        if value >= 55:
            return "C"
        if value >= 40:
            return "Watch"
        return "Avoid"

    ranked["copy_grade"] = ranked["copy_smart_score"].map(_grade)
    ranked["copy_rank_reason"] = ranked.apply(
        lambda row: (
            f"return {float(row.get('copy_return_score', 0.0)):.0f}, "
            f"sharpe-proxy {float(row.get('copy_sharpe_proxy', 0.0)):.0f}, "
            f"drawdown-proxy {float(row.get('copy_drawdown_proxy', 0.0)):.0f}, "
            f"win {float(row.get('copy_win_score', 0.0)):.0f}, "
            f"recency {float(row.get('copy_recency_score', 0.0)):.0f}, "
            f"volume {float(row.get('copy_volume_score', 0.0)):.0f}"
        ),
        axis=1,
    )
    ranked = ranked.sort_values(["copy_smart_score", "roi", "volume"], ascending=[False, False, False]).reset_index(drop=True)
    ranked["copy_rank"] = range(1, len(ranked) + 1)
    return ranked


def rank_traders_by_roi(
    traders: pd.DataFrame,
    min_volume: float = ROI_MIN_VOLUME,
    require_positive_roi: bool = True,
    min_win_rate: float = ROI_MIN_WIN_RATE,
    exclude_bots: bool = True,
) -> pd.DataFrame:
    """Rank leaderboard rows by ROI, applying the discovery thresholds.

    Expects ``pnl`` and ``volume`` columns (as produced by
    ``prediction_markets.get_polymarket_leaderboard``);
    ``win_rate`` and ``is_bot`` are honoured when present.
    """
    if traders is None or traders.empty:
        return pd.DataFrame()
    df = traders.copy()
    pnl = pd.to_numeric(df.get("pnl"), errors="coerce").fillna(0.0)
    volume = pd.to_numeric(df.get("volume"), errors="coerce").fillna(0.0)
    win_rate = pd.to_numeric(df.get("win_rate"), errors="coerce").fillna(0.0)
    df["roi"] = [compute_roi(p, v) for p, v in zip(pnl, volume)]
    mask = volume >= float(min_volume)
    if require_positive_roi:
        mask = mask & (df["roi"] > 0)
    if min_win_rate > 0:
        mask = mask & (win_rate >= float(min_win_rate))
    if exclude_bots and "is_bot" in df.columns:
        mask = mask & (~df["is_bot"].fillna(False).astype(bool))
    ranked = df[mask].copy()
    if ranked.empty:
        return ranked
    ranked = ranked.sort_values("roi", ascending=False).reset_index(drop=True)
    ranked["rank_score"] = ranked["roi"]
    return ranked


def suggest_traders(
    limit: int = 50,
    min_volume: float = ROI_MIN_VOLUME,
    require_positive_roi: bool = True,
    min_win_rate: float = ROI_MIN_WIN_RATE,
    exclude_bots: bool = True,
) -> pd.DataFrame:
    """Fetch the public leaderboard and rank it by smart score for discovery."""
    traders = md.get_polymarket_leaderboard(limit=limit, time_period="ALL", order_by="PNL")
    return rank_traders_by_smart_score(
        traders,
        min_volume=min_volume,
        require_positive_roi=require_positive_roi,
        min_win_rate=min_win_rate,
        exclude_bots=exclude_bots,
    )


def refresh_trader_stats(conn: sqlite3.Connection, traders: pd.DataFrame) -> int:
    """Upsert ranked leaderboard rows into ``trader_stats`` and mirror the score."""
    if traders is None or traders.empty:
        return 0
    now = utc_now()
    updated = 0
    for _, row in traders.iterrows():
        wallet = str(row.get("wallet", "") or "")
        if not wallet:
            continue
        roi = _to_float(row.get("roi"), compute_roi(row.get("pnl"), row.get("volume")))
        rank_score = _to_float(row.get("copy_smart_score"), _to_float(row.get("rank_score"), roi))
        pnl = _to_float(row.get("pnl"), 0.0)
        win_rate = _to_float(row.get("win_rate"), 0.0)
        volume = _to_float(row.get("volume"), 0.0)
        trades = int(_to_float(row.get("trades"), _to_float(row.get("open_positions"), 0.0)))
        conn.execute(
            """
            INSERT INTO trader_stats (wallet, roi, pnl, win_rate, trades, volume, last_refresh)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(wallet) DO UPDATE SET
                roi = excluded.roi,
                pnl = excluded.pnl,
                win_rate = excluded.win_rate,
                trades = excluded.trades,
                volume = excluded.volume,
                last_refresh = excluded.last_refresh
            """,
            (wallet, roi, pnl, win_rate, trades, volume, now),
        )
        conn.execute("UPDATE traders SET rank_score = ?, updated_at = ? WHERE wallet = ?", (rank_score, now, wallet))
        updated += 1
    return updated


def get_trader_stats(db_path: str | Path = DEFAULT_DB_PATH, conn: sqlite3.Connection | None = None) -> pd.DataFrame:
    owns_conn = conn is None
    conn = connect(db_path) if conn is None else conn
    try:
        return pd.read_sql_query("SELECT * FROM trader_stats ORDER BY roi DESC", conn)
    finally:
        if owns_conn:
            conn.close()


def get_meta_snapshot(db_path: str | Path = DEFAULT_DB_PATH) -> dict[str, str]:
    conn = connect(db_path)
    try:
        rows = conn.execute("SELECT key, value FROM meta ORDER BY key").fetchall()
        return {str(row["key"]): str(row["value"]) for row in rows}
    finally:
        conn.close()


def backfill_position_metadata(
    conn: sqlite3.Connection,
    wallet: str = COPY_TARGET_WALLET,
    pages: int = 12,
    closed_pages: int = 4,
) -> int:
    metadata = fetch_position_metadata(wallet, pages=pages, closed_pages=closed_pages)
    updated = 0
    for asset, values in metadata.items():
        market_key = str(values.get("market_key", "") or "")
        title = str(values.get("title", "") or "")
        outcome = str(values.get("outcome", "") or "")
        last_price = _to_float(values.get("last_price"), 0.0)
        for table in ("positions", "tony_positions", "source_positions"):
            conn.execute(
                f"""
                UPDATE {table}
                SET market_key = CASE WHEN market_key = '' OR market_key IS NULL THEN ? ELSE market_key END,
                    title = CASE WHEN title = '' OR title LIKE 'On-chain Polymarket token %' THEN ? ELSE title END,
                    outcome = CASE WHEN outcome = '' OR outcome IS NULL THEN ? ELSE outcome END,
                    last_price = CASE WHEN ? > 0 THEN ? ELSE last_price END,
                    updated_at = CASE WHEN market_key = '' OR market_key IS NULL THEN ? ELSE updated_at END
                WHERE asset = ?
                """,
                (market_key, title, outcome, last_price, last_price, utc_now(), asset),
            )
        conn.execute(
            """
            UPDATE paper_orders
            SET market_key = CASE WHEN market_key = '' OR market_key IS NULL THEN ? ELSE market_key END,
                title = CASE WHEN title = '' OR title LIKE 'On-chain Polymarket token %' THEN ? ELSE title END,
                outcome = CASE WHEN outcome = '' OR outcome IS NULL THEN ? ELSE outcome END
            WHERE asset = ?
            """,
            (market_key, title, outcome, asset),
        )
        updated += 1
    _set_meta(conn, "metadata_backfilled_at", utc_now())
    return updated


def _fill_already_recorded(conn: sqlite3.Connection, source_trade: Mapping[str, Any], wallet: str) -> bool:
    """True if a fill with the same stable identity (wallet, tx, asset, side) exists.

    Stable across detection paths because it omits the timestamp and price, which
    drift between the off-chain WebSocket match and the on-chain settlement log.
    """
    tx = str(_first(source_trade, "transaction_hash", "transactionHash") or "").strip().lower()
    if not tx:
        return False
    wallet_key = str(wallet or source_trade.get("source_wallet", "") or source_trade.get("wallet", "") or "")
    asset = str(source_trade.get("asset", "") or "")
    side = str(source_trade.get("side", "") or "").upper()
    row = conn.execute(
        """
        SELECT 1 FROM paper_orders
        WHERE LOWER(source_wallet) = LOWER(?) AND LOWER(source_tx) = ? AND asset = ? AND source_side = ?
        LIMIT 1
        """,
        (wallet_key, tx, asset, side),
    ).fetchone()
    return row is not None


def trade_dedup_key(source_trade: Mapping[str, Any], wallet: str = "") -> str:
    wallet_key = str(wallet or source_trade.get("source_wallet", "") or source_trade.get("wallet", "") or "")
    tx = str(_first(source_trade, "transaction_hash", "transactionHash") or "")
    asset = str(source_trade.get("asset", "") or "")
    side = str(source_trade.get("side", "") or "").upper()
    size = _to_float(source_trade.get("size"), 0.0)
    price = _to_float(source_trade.get("price"), 0.0)
    timestamp = _timestamp_value(source_trade)
    return f"{wallet_key}|{tx}|{asset}|{side}|{size:.8f}|{price:.8f}|{timestamp}"


def settlement_dedup_key(source_activity: Mapping[str, Any]) -> str:
    tx = str(_first(source_activity, "transaction_hash", "transactionHash") or "")
    condition = str(_first(source_activity, "market_key", "conditionId") or "")
    typ = str(source_activity.get("type", "") or "").upper()
    size = _to_float(source_activity.get("size"), 0.0)
    usdc = _to_float(_first(source_activity, "usdcSize", "notional"), 0.0)
    timestamp = _timestamp_value(source_activity)
    return f"{tx}|{condition}|{typ}|{size:.8f}|{usdc:.8f}|{timestamp}"


def parse_source_trade(source_trade: Mapping[str, Any], wallet: str) -> dict[str, Any]:
    price = _to_float(source_trade.get("price"), 0.0)
    size = _to_float(source_trade.get("size"), 0.0)
    timestamp = _timestamp_value(source_trade)
    source_time = _source_time(source_trade, timestamp)
    return {
        "dedup_key": trade_dedup_key(source_trade, wallet),
        "source_wallet": wallet,
        "source_tx": str(_first(source_trade, "transaction_hash", "transactionHash") or ""),
        "source_time": source_time,
        "market_key": str(_first(source_trade, "market_key", "conditionId") or ""),
        "asset": str(source_trade.get("asset", "") or ""),
        "title": str(source_trade.get("title", "") or ""),
        "outcome": str(source_trade.get("outcome", "") or ""),
        "side": str(source_trade.get("side", "") or "").upper(),
        "price": price,
        "size": size,
        "source_notional": price * size,
    }


def parse_settlement_activity(source_activity: Mapping[str, Any], wallet: str) -> dict[str, Any]:
    timestamp = _timestamp_value(source_activity)
    size = _to_float(source_activity.get("size"), 0.0)
    usdc = _to_float(_first(source_activity, "usdcSize", "notional"), 0.0)
    payout_price = usdc / size if size > 0 else 0.0
    return {
        "dedup_key": settlement_dedup_key(source_activity),
        "source_wallet": wallet,
        "source_tx": str(_first(source_activity, "transaction_hash", "transactionHash") or ""),
        "source_time": _source_time(source_activity, timestamp),
        "market_key": str(_first(source_activity, "market_key", "conditionId") or ""),
        "asset": str(source_activity.get("asset", "") or ""),
        "title": str(source_activity.get("title", "") or ""),
        "outcome": str(source_activity.get("outcome", "") or ""),
        "side": str(source_activity.get("type", "") or "").upper(),
        "price": payout_price,
        "size": size,
        "source_notional": usdc,
    }


def _apply_redeem(
    conn: sqlite3.Connection,
    parsed: dict[str, Any],
    winners_by_condition: Mapping[str, set[str]],
) -> tuple[PaperOrder, str]:
    wallet = parsed["source_wallet"]
    condition = parsed["market_key"]
    winner_assets = set(winners_by_condition.get(condition, set()))
    candidates = _paper_positions_for_resolution(conn, wallet, condition, winner_assets)
    if not candidates:
        return PaperOrder(parsed["dedup_key"], "skipped", "redeem_no_paper_position", parsed["side"], parsed["source_notional"]), ""
    if len(candidates) > 1 and not winner_assets:
        return PaperOrder(parsed["dedup_key"], "skipped", "redeem_unmatched_winner", parsed["side"], parsed["source_notional"]), ""

    cash_added = 0.0
    realized_pnl = 0.0
    settled_shares = 0.0
    settled_assets: list[str] = []
    winning_payout_price = parsed["price"] if parsed["price"] > 0 else 1.0
    for position in candidates:
        asset = str(position["asset"])
        paper_before = float(position["shares"])
        if paper_before <= 0:
            continue
        is_known_loser = bool(winner_assets) and asset not in winner_assets
        payout_price = 0.0 if is_known_loser else winning_payout_price
        source_position = _get_source_position(conn, wallet, asset)
        if is_known_loser:
            redeem_ratio = 1.0
        elif source_position and float(source_position["shares"]) > 0:
            redeem_ratio = min(parsed["size"] / float(source_position["shares"]), 1.0) if parsed["size"] > 0 else 1.0
        else:
            redeem_ratio = 1.0
        paper_settle = min(paper_before * redeem_ratio, paper_before)
        if paper_settle <= 0:
            continue
        cash_value = paper_settle * payout_price
        avg_price = float(position["avg_price"])
        cost_settled = avg_price * paper_settle
        _reduce_position(conn, wallet, asset, paper_settle, payout_price)
        if source_position:
            source_reduce = float(source_position["shares"]) if is_known_loser else parsed["size"]
            _decrease_source_position(conn, wallet, asset, source_reduce, payout_price)
        cash_added += cash_value
        realized_pnl += cash_value - cost_settled
        settled_shares += paper_settle
        settled_assets.append(asset)

    if settled_shares <= 0:
        return PaperOrder(parsed["dedup_key"], "skipped", "redeem_no_paper_position", parsed["side"], parsed["source_notional"]), ""
    if cash_added > 0:
        cash = _get_trader_cash(conn, wallet, 1000.0)
        _set_trader_cash(conn, wallet, cash + cash_added)
    return (
        PaperOrder(parsed["dedup_key"], "settled", "redeem_resolution", parsed["side"], parsed["source_notional"], cash_added, settled_shares, realized_pnl),
        ",".join(settled_assets),
    )


def _apply_merge(conn: sqlite3.Connection, parsed: dict[str, Any]) -> tuple[PaperOrder, str]:
    wallet = parsed["source_wallet"]
    condition = parsed["market_key"]
    positions = _paper_positions_for_market(conn, wallet, condition)
    if len(positions) < 2:
        return PaperOrder(parsed["dedup_key"], "skipped", "merge_no_complete_set", parsed["side"], parsed["source_notional"]), ""

    source_positions = _source_positions_for_market(conn, wallet, condition)
    if len(source_positions) >= 2:
        source_complete_sets = min(float(row["shares"]) for row in source_positions)
        merge_ratio = min(parsed["size"] / source_complete_sets, 1.0) if source_complete_sets > 0 and parsed["size"] > 0 else 1.0
    else:
        merge_ratio = 1.0

    paper_complete_sets = min(float(row["shares"]) for row in positions)
    paper_merge = min(paper_complete_sets * merge_ratio, paper_complete_sets)
    if paper_merge <= 0:
        return PaperOrder(parsed["dedup_key"], "skipped", "merge_no_complete_set", parsed["side"], parsed["source_notional"]), ""

    realized_pnl = 0.0
    assets: list[str] = []
    for position in positions:
        asset = str(position["asset"])
        avg_price = float(position["avg_price"])
        _reduce_position(conn, wallet, asset, paper_merge, 0.0)
        _decrease_source_position(conn, wallet, asset, parsed["size"], 0.0)
        realized_pnl -= avg_price * paper_merge
        assets.append(asset)
    cash_added = paper_merge
    realized_pnl += cash_added
    cash = _get_trader_cash(conn, wallet, 1000.0)
    _set_trader_cash(conn, wallet, cash + cash_added)
    return (
        PaperOrder(parsed["dedup_key"], "settled", "merge_complete_set", parsed["side"], parsed["source_notional"], cash_added, paper_merge, realized_pnl),
        ",".join(assets),
    )


def _reconcile_resolved_loser_positions(
    conn: sqlite3.Connection,
    winners_by_condition: Mapping[str, set[str]],
    wallet: str,
) -> int:
    settled = 0
    for condition, winner_assets in winners_by_condition.items():
        if not condition or not winner_assets:
            continue
        for position in _paper_positions_for_market(conn, wallet, condition):
            asset = str(position["asset"])
            if asset in winner_assets:
                continue
            shares = float(position["shares"])
            if shares <= 0:
                continue
            cost_basis = float(position["cost_basis"])
            dedup_key = f"resolution_loser_loss|{condition}|{asset}"
            if conn.execute("SELECT 1 FROM paper_orders WHERE dedup_key = ?", (dedup_key,)).fetchone():
                continue
            parsed = {
                "dedup_key": dedup_key,
                "source_wallet": wallet,
                "source_tx": "",
                "source_time": utc_now(),
                "market_key": condition,
                "asset": asset,
                "title": str(position["title"] or ""),
                "outcome": str(position["outcome"] or ""),
                "side": "RESOLUTION",
                "price": 0.0,
                "size": shares,
                "source_notional": 0.0,
            }
            order = PaperOrder(
                dedup_key,
                "settled",
                "resolution_loser_loss",
                "RESOLUTION",
                0.0,
                0.0,
                shares,
                -cost_basis,
            )
            _reduce_position(conn, wallet, asset, shares, 0.0)
            source_position = _get_source_position(conn, wallet, asset)
            if source_position:
                _decrease_source_position(conn, wallet, asset, float(source_position["shares"]), 0.0)
            _insert_order(conn, parsed, order, parsed)
            settled += 1
    return settled


def _reconcile_resolved_winner_positions(
    conn: sqlite3.Connection,
    winners_by_condition: Mapping[str, set[str]],
    wallet: str,
) -> int:
    settled = 0
    for condition, winner_assets in winners_by_condition.items():
        if not condition or not winner_assets:
            continue
        for position in _paper_positions_for_market(conn, wallet, condition):
            asset = str(position["asset"])
            if asset not in winner_assets:
                continue
            shares = float(position["shares"])
            if shares <= 0:
                continue
            cost_basis = float(position["cost_basis"])
            cash_added = shares
            realized_pnl = cash_added - cost_basis
            dedup_key = f"resolution_winner_payout|{condition}|{asset}"
            if conn.execute("SELECT 1 FROM paper_orders WHERE dedup_key = ?", (dedup_key,)).fetchone():
                continue
            parsed = {
                "dedup_key": dedup_key,
                "source_wallet": wallet,
                "source_tx": "",
                "source_time": utc_now(),
                "market_key": condition,
                "asset": asset,
                "title": str(position["title"] or ""),
                "outcome": str(position["outcome"] or ""),
                "side": "RESOLUTION",
                "price": 1.0,
                "size": shares,
                "source_notional": 0.0,
            }
            order = PaperOrder(
                dedup_key,
                "settled",
                "resolution_winner_payout",
                "RESOLUTION",
                0.0,
                cash_added,
                shares,
                realized_pnl,
            )
            _reduce_position(conn, wallet, asset, shares, 1.0)
            source_position = _get_source_position(conn, wallet, asset)
            if source_position:
                _decrease_source_position(conn, wallet, asset, float(source_position["shares"]), 1.0)
            cash = _get_trader_cash(conn, wallet, 1000.0)
            _set_trader_cash(conn, wallet, cash + cash_added)
            _insert_order(conn, parsed, order, parsed)
            settled += 1
    return settled


def _apply_buy(conn: sqlite3.Connection, parsed: dict[str, Any], settings: CopySettings) -> PaperOrder:
    wallet = parsed["source_wallet"]
    _ensure_trader(conn, wallet, settings.paper_start_cash)
    _increase_source_position(conn, wallet, parsed)
    cash = _get_trader_cash(conn, wallet, settings.paper_start_cash)
    cash = _auto_top_up_if_needed(conn, wallet, cash, settings, "before_buy", parsed)
    snapshot = value_sub_account(wallet, conn=conn)
    effective_scale = _effective_copy_scale(conn, snapshot, settings)
    effective_cap_pct = _effective_max_order_equity_pct(conn, settings)
    desired = parsed["source_notional"] * effective_scale
    cap = max(snapshot.equity, 0.0) * effective_cap_pct
    copy_notional = min(desired, cap, cash)
    min_copy_notional = max(0.0, float(settings.min_copy_notional))
    if copy_notional < min_copy_notional:
        reason = "insufficient_cash" if cash < min_copy_notional else "below_min_copy_notional"
        return PaperOrder(parsed["dedup_key"], "skipped", reason, parsed["side"], parsed["source_notional"])

    copy_size = copy_notional / parsed["price"]
    position = _get_position(conn, wallet, parsed["asset"])
    now = utc_now()
    if position:
        old_shares = float(position["shares"])
        old_cost = float(position["cost_basis"])
        new_shares = old_shares + copy_size
        new_cost = old_cost + copy_notional
        avg_price = new_cost / new_shares if new_shares else parsed["price"]
    else:
        new_shares = copy_size
        new_cost = copy_notional
        avg_price = parsed["price"]
    conn.execute(
        """
        INSERT INTO positions (trader_wallet, asset, market_key, title, outcome, shares, avg_price, cost_basis, last_price, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(trader_wallet, asset) DO UPDATE SET
            market_key = excluded.market_key,
            title = excluded.title,
            outcome = excluded.outcome,
            shares = excluded.shares,
            avg_price = excluded.avg_price,
            cost_basis = excluded.cost_basis,
            last_price = excluded.last_price,
            updated_at = excluded.updated_at
        """,
        (
            wallet,
            parsed["asset"],
            parsed["market_key"],
            parsed["title"],
            parsed["outcome"],
            new_shares,
            avg_price,
            new_cost,
            parsed["price"],
            now,
        ),
    )
    cash_after_trade = cash - copy_notional
    _set_trader_cash(conn, wallet, cash_after_trade)
    _auto_top_up_if_needed(conn, wallet, cash_after_trade, settings, "after_buy", parsed)
    return PaperOrder(parsed["dedup_key"], "copied", "buy_scaled", parsed["side"], parsed["source_notional"], copy_notional, copy_size)


def _apply_sell(conn: sqlite3.Connection, parsed: dict[str, Any]) -> PaperOrder:
    wallet = parsed["source_wallet"]
    source_position = _get_source_position(conn, wallet, parsed["asset"])
    if not source_position or float(source_position["shares"]) <= 0:
        return PaperOrder(parsed["dedup_key"], "skipped", "skipped_unmatched_sell", parsed["side"], parsed["source_notional"])

    source_before = float(source_position["shares"])
    sell_ratio = min(parsed["size"] / source_before, 1.0)
    _decrease_source_position(conn, wallet, parsed["asset"], parsed["size"], parsed["price"])

    position = _get_position(conn, wallet, parsed["asset"])
    if not position or float(position["shares"]) <= 0:
        return PaperOrder(parsed["dedup_key"], "skipped", "skipped_no_paper_position", parsed["side"], parsed["source_notional"])

    paper_before = float(position["shares"])
    sell_shares = min(paper_before * sell_ratio, paper_before)
    if sell_shares <= 0:
        return PaperOrder(parsed["dedup_key"], "skipped", "skipped_no_paper_position", parsed["side"], parsed["source_notional"])

    avg_price = float(position["avg_price"])
    copy_notional = sell_shares * parsed["price"]
    realized_pnl = (parsed["price"] - avg_price) * sell_shares
    remaining_shares = paper_before - sell_shares
    remaining_cost = max(0.0, float(position["cost_basis"]) - (avg_price * sell_shares))
    cash = _get_trader_cash(conn, wallet, 1000.0)
    _set_trader_cash(conn, wallet, cash + copy_notional)

    if remaining_shares <= 1e-9:
        conn.execute("DELETE FROM positions WHERE trader_wallet = ? AND asset = ?", (wallet, parsed["asset"]))
    else:
        conn.execute(
            """
            UPDATE positions
            SET shares = ?, cost_basis = ?, avg_price = ?, last_price = ?, updated_at = ?
            WHERE trader_wallet = ? AND asset = ?
            """,
            (remaining_shares, remaining_cost, avg_price, parsed["price"], utc_now(), wallet, parsed["asset"]),
        )
    return PaperOrder(
        parsed["dedup_key"],
        "copied",
        "sell_ratio_scaled",
        parsed["side"],
        parsed["source_notional"],
        copy_notional,
        sell_shares,
        realized_pnl,
    )


def _insert_order(conn: sqlite3.Connection, parsed: dict[str, Any], order: PaperOrder, source_trade: Mapping[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO paper_orders (
            dedup_key, source_wallet, source_tx, source_time, market_key, asset, title, outcome,
            source_side, source_price, source_size, source_notional, copy_side, copy_price,
            copy_size, copy_notional, realized_pnl, status, reason, source_json, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            parsed["dedup_key"],
            parsed["source_wallet"],
            parsed["source_tx"],
            parsed["source_time"],
            parsed["market_key"],
            parsed["asset"],
            parsed["title"],
            parsed["outcome"],
            parsed["side"],
            parsed["price"],
            parsed["size"],
            parsed["source_notional"],
            parsed["side"] if order.status in ("copied", "settled") else "",
            parsed["price"] if order.status in ("copied", "settled") else 0.0,
            order.copy_size,
            order.copy_notional,
            order.realized_pnl,
            order.status,
            order.reason,
            _json_source(source_trade),
            utc_now(),
        ),
    )


def _mark_existing_trades_as_seed(conn: sqlite3.Connection, trades: pd.DataFrame, wallet: str) -> int:
    count = 0
    for _, row in _sort_source_trades(trades).iterrows():
        parsed = parse_source_trade(row.to_dict(), wallet)
        if conn.execute("SELECT 1 FROM paper_orders WHERE dedup_key = ?", (parsed["dedup_key"],)).fetchone():
            continue
        order = PaperOrder(parsed["dedup_key"], "seed_observed", "initial_baseline", parsed["side"], parsed["source_notional"])
        _insert_order(conn, parsed, order, row.to_dict())
        count += 1
    return count


def _get_source_position(conn: sqlite3.Connection, wallet: str, asset: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM source_positions WHERE wallet = ? AND asset = ?", (wallet, asset)).fetchone()


def _source_positions_for_market(conn: sqlite3.Connection, wallet: str, condition: str) -> list[sqlite3.Row]:
    if not condition:
        return []
    return list(
        conn.execute(
            "SELECT * FROM source_positions WHERE wallet = ? AND market_key = ? AND shares > 0 ORDER BY asset",
            (wallet, condition),
        ).fetchall()
    )


def _increase_source_position(conn: sqlite3.Connection, wallet: str, parsed: dict[str, Any]) -> None:
    now = utc_now()
    existing = _get_source_position(conn, wallet, parsed["asset"])
    shares = parsed["size"] + (float(existing["shares"]) if existing else 0.0)
    conn.execute(
        """
        INSERT INTO source_positions (wallet, asset, market_key, title, outcome, shares, avg_price, last_price, seeded_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(wallet, asset) DO UPDATE SET
            market_key = excluded.market_key,
            title = excluded.title,
            outcome = excluded.outcome,
            shares = excluded.shares,
            last_price = excluded.last_price,
            updated_at = excluded.updated_at
        """,
        (wallet, parsed["asset"], parsed["market_key"], parsed["title"], parsed["outcome"], shares, parsed["price"], parsed["price"], now, now),
    )


def _decrease_source_position(conn: sqlite3.Connection, wallet: str, asset: str, source_size: float, last_price: float) -> None:
    existing = _get_source_position(conn, wallet, asset)
    if not existing:
        return
    shares = max(0.0, float(existing["shares"]) - source_size)
    if shares <= 1e-9:
        conn.execute("DELETE FROM source_positions WHERE wallet = ? AND asset = ?", (wallet, asset))
    else:
        conn.execute(
            "UPDATE source_positions SET shares = ?, last_price = ?, updated_at = ? WHERE wallet = ? AND asset = ?",
            (shares, last_price, utc_now(), wallet, asset),
        )


def _reduce_position(conn: sqlite3.Connection, wallet: str, asset: str, shares_to_remove: float, last_price: float) -> None:
    existing = _get_position(conn, wallet, asset)
    if not existing:
        return
    shares_before = float(existing["shares"])
    remove = min(max(shares_to_remove, 0.0), shares_before)
    remaining = shares_before - remove
    avg_price = float(existing["avg_price"])
    remaining_cost = max(0.0, float(existing["cost_basis"]) - avg_price * remove)
    if remaining <= 1e-9:
        conn.execute("DELETE FROM positions WHERE trader_wallet = ? AND asset = ?", (wallet, asset))
    else:
        conn.execute(
            """
            UPDATE positions
            SET shares = ?, cost_basis = ?, avg_price = ?, last_price = ?, updated_at = ?
            WHERE trader_wallet = ? AND asset = ?
            """,
            (remaining, remaining_cost, avg_price, last_price, utc_now(), wallet, asset),
        )


def _paper_positions_for_market(conn: sqlite3.Connection, wallet: str, condition: str) -> list[sqlite3.Row]:
    if not condition:
        return []
    return list(
        conn.execute(
            "SELECT * FROM positions WHERE trader_wallet = ? AND market_key = ? AND shares > 0 ORDER BY asset",
            (wallet, condition),
        ).fetchall()
    )


def _open_paper_conditions(conn: sqlite3.Connection, wallet: str) -> set[str]:
    rows = conn.execute(
        "SELECT DISTINCT market_key FROM positions WHERE trader_wallet = ? AND shares > 0 AND market_key IS NOT NULL AND market_key <> ''",
        (wallet,),
    ).fetchall()
    return {str(row["market_key"]) for row in rows if str(row["market_key"] or "")}


def _paper_positions_for_settlement(conn: sqlite3.Connection, wallet: str, condition: str, winner_assets: set[str]) -> list[sqlite3.Row]:
    rows: list[sqlite3.Row] = []
    if winner_assets:
        for asset in sorted(winner_assets):
            row = _get_position(conn, wallet, asset)
            if row and float(row["shares"]) > 0:
                rows.append(row)
        if rows:
            return rows
    market_rows = _paper_positions_for_market(conn, wallet, condition)
    if winner_assets:
        return [row for row in market_rows if str(row["asset"]) in winner_assets]
    return market_rows


def _paper_positions_for_resolution(conn: sqlite3.Connection, wallet: str, condition: str, winner_assets: set[str]) -> list[sqlite3.Row]:
    market_rows = _paper_positions_for_market(conn, wallet, condition)
    if winner_assets and market_rows:
        return market_rows
    return _paper_positions_for_settlement(conn, wallet, condition, winner_assets)


def _merge_trade_metadata(conn: sqlite3.Connection, source_trade: Mapping[str, Any], wallet: str) -> None:
    parsed = parse_source_trade(source_trade, wallet)
    if not parsed["asset"]:
        return
    updates = {
        "market_key": parsed["market_key"],
        "title": parsed["title"],
        "outcome": parsed["outcome"],
    }
    if any(updates.values()):
        conn.execute(
            """
            UPDATE paper_orders
            SET market_key = CASE WHEN market_key = '' OR market_key IS NULL THEN ? ELSE market_key END,
                title = CASE WHEN title = '' OR title LIKE 'On-chain Polymarket token %' THEN ? ELSE title END,
                outcome = CASE WHEN outcome = '' OR outcome IS NULL THEN ? ELSE outcome END
            WHERE dedup_key = ?
            """,
            (updates["market_key"], updates["title"], updates["outcome"], parsed["dedup_key"]),
        )
        conn.execute(
            """
            UPDATE positions
            SET market_key = CASE WHEN market_key = '' OR market_key IS NULL THEN ? ELSE market_key END,
                title = CASE WHEN title = '' OR title LIKE 'On-chain Polymarket token %' THEN ? ELSE title END,
                outcome = CASE WHEN outcome = '' OR outcome IS NULL THEN ? ELSE outcome END
            WHERE asset = ?
            """,
            (updates["market_key"], updates["title"], updates["outcome"], parsed["asset"]),
        )
        for table in ("tony_positions", "source_positions"):
            conn.execute(
                f"""
                UPDATE {table}
                SET market_key = CASE WHEN market_key = '' OR market_key IS NULL THEN ? ELSE market_key END,
                    title = CASE WHEN title = '' OR title LIKE 'On-chain Polymarket token %' THEN ? ELSE title END,
                    outcome = CASE WHEN outcome = '' OR outcome IS NULL THEN ? ELSE outcome END
                WHERE asset = ?
                """,
                (updates["market_key"], updates["title"], updates["outcome"], parsed["asset"]),
            )


def get_dynamic_sizing_snapshot(db_path: str | Path = DEFAULT_DB_PATH, conn: sqlite3.Connection | None = None) -> dict[str, float | int | str | bool]:
    owns_conn = conn is None
    conn = connect(db_path) if conn is None else conn
    try:
        keys = (
            "dynamic_sizing_enabled",
            "dynamic_sizing_multiplier",
            "effective_copy_scale",
            "effective_max_order_equity_pct",
            "tony_visible_equity",
            "tony_position_value",
            "tony_cash_estimate",
            "tony_open_positions",
            "tony_open_markets",
            "tony_mean_market_position",
            "tony_median_market_position",
            "tony_p75_market_position",
            "tony_p90_market_position",
            "tony_p95_market_position",
            "tony_max_market_position",
            "tony_mean_market_position_pct",
            "tony_median_market_position_pct",
            "tony_p75_market_position_pct",
            "tony_p90_market_position_pct",
            "tony_p95_market_position_pct",
            "tony_max_market_position_pct",
            "tony_wallet_stats_updated_at",
            "tony_wallet_stats_error",
            "copy_scale_mode",
        )
        snapshot: dict[str, float | int | str | bool] = {}
        for key in keys:
            value = _get_meta(conn, key)
            if value is None:
                continue
            if key in {"dynamic_sizing_enabled"}:
                snapshot[key] = value.lower() == "true"
            elif key in {"tony_open_positions", "tony_open_markets"}:
                snapshot[key] = int(float(value))
            elif key.endswith("_at") or key.endswith("_error") or key == "copy_scale_mode":
                snapshot[key] = value
            else:
                snapshot[key] = _to_float(value, 0.0)
        return snapshot
    finally:
        if owns_conn:
            conn.close()


def _get_wallet_float_stat(conn: sqlite3.Connection, wallet: str, name: str, default: float) -> float:
    """Per-source-wallet sizing stat, falling back to the legacy global value."""
    value = _get_meta(conn, f"wallet_stat:{wallet}:{name}")
    if value is not None:
        return _to_float(value, default)
    return _get_float_meta(conn, f"tony_{name}", default)


def _effective_copy_scale(conn: sqlite3.Connection, snapshot: PortfolioSnapshot, settings: CopySettings) -> float:
    if not settings.dynamic_sizing_enabled:
        scale = max(0.0, settings.copy_scale)
        _set_meta(conn, "copy_scale_mode", "fixed")
    else:
        tony_equity = _get_wallet_float_stat(conn, settings.target_wallet, "visible_equity", 0.0)
        if tony_equity <= 0 or snapshot.equity <= 0:
            scale = max(0.0, settings.copy_scale)
            _set_meta(conn, "copy_scale_mode", "fixed_fallback_no_tony_equity")
        else:
            scale = (snapshot.equity / tony_equity) * max(0.0, float(settings.dynamic_sizing_multiplier))
            if settings.dynamic_scale_max > 0:
                scale = min(scale, settings.dynamic_scale_max)
            if settings.dynamic_scale_min > 0:
                scale = max(scale, settings.dynamic_scale_min)
            _set_meta(conn, "copy_scale_mode", "dynamic_wallet_equity")
    _set_meta(conn, "dynamic_sizing_enabled", "true" if settings.dynamic_sizing_enabled else "false")
    _set_meta(conn, "dynamic_sizing_multiplier", f"{max(0.0, float(settings.dynamic_sizing_multiplier)):.10f}")
    _set_meta(conn, "effective_copy_scale", f"{scale:.10f}")
    _set_meta(conn, "effective_copy_scale_updated_at", utc_now())
    return scale


def _effective_max_order_equity_pct(conn: sqlite3.Connection, settings: CopySettings) -> float:
    cap = max(0.0, settings.max_order_equity_pct)
    if settings.dynamic_sizing_enabled and settings.dynamic_order_cap_from_tony:
        tony_max_pct = _get_wallet_float_stat(conn, settings.target_wallet, "max_market_position_pct", 0.0)
        if tony_max_pct > 0:
            cap = max(cap, tony_max_pct)
    cap = min(cap, 1.0)
    _set_meta(conn, "effective_max_order_equity_pct", f"{cap:.10f}")
    return cap


def _read_tony_wallet_stats(conn: sqlite3.Connection) -> TonyWalletStats | None:
    updated_at = _get_meta(conn, "tony_wallet_stats_updated_at")
    visible_equity = _get_float_meta(conn, "tony_visible_equity", 0.0)
    if not updated_at or visible_equity <= 0:
        return None
    return TonyWalletStats(
        updated_at=updated_at,
        position_value=_get_float_meta(conn, "tony_position_value", 0.0),
        cash=_get_float_meta(conn, "tony_cash_estimate", 0.0),
        visible_equity=visible_equity,
        open_positions=int(_get_float_meta(conn, "tony_open_positions", 0.0)),
        open_markets=int(_get_float_meta(conn, "tony_open_markets", 0.0)),
        mean_market_position=_get_float_meta(conn, "tony_mean_market_position", 0.0),
        median_market_position=_get_float_meta(conn, "tony_median_market_position", 0.0),
        p75_market_position=_get_float_meta(conn, "tony_p75_market_position", 0.0),
        p90_market_position=_get_float_meta(conn, "tony_p90_market_position", 0.0),
        p95_market_position=_get_float_meta(conn, "tony_p95_market_position", 0.0),
        max_market_position=_get_float_meta(conn, "tony_max_market_position", 0.0),
        mean_market_position_pct=_get_float_meta(conn, "tony_mean_market_position_pct", 0.0),
        median_market_position_pct=_get_float_meta(conn, "tony_median_market_position_pct", 0.0),
        p75_market_position_pct=_get_float_meta(conn, "tony_p75_market_position_pct", 0.0),
        p90_market_position_pct=_get_float_meta(conn, "tony_p90_market_position_pct", 0.0),
        p95_market_position_pct=_get_float_meta(conn, "tony_p95_market_position_pct", 0.0),
        max_market_position_pct=_get_float_meta(conn, "tony_max_market_position_pct", 0.0),
    )


def _store_tony_wallet_stats(
    conn: sqlite3.Connection, stats: TonyWalletStats, timestamp: float, wallet: str | None = None
) -> None:
    if wallet:
        # Per-source-wallet copies of the values the sizing reads, so each
        # followed trader is sized against its own source wallet (spec §4.3).
        _set_meta(conn, f"wallet_stat:{wallet}:ts", f"{timestamp:.6f}")
        _set_meta(conn, f"wallet_stat:{wallet}:visible_equity", f"{stats.visible_equity:.10f}")
        _set_meta(conn, f"wallet_stat:{wallet}:max_market_position_pct", f"{stats.max_market_position_pct:.10f}")
    _set_meta(conn, "tony_wallet_stats_ts", f"{timestamp:.6f}")
    _set_meta(conn, "tony_wallet_stats_json", json.dumps(asdict(stats), sort_keys=True))
    _set_meta(conn, "tony_wallet_stats_updated_at", stats.updated_at)
    _set_meta(conn, "tony_position_value", f"{stats.position_value:.10f}")
    _set_meta(conn, "tony_cash_estimate", f"{stats.cash:.10f}")
    _set_meta(conn, "tony_visible_equity", f"{stats.visible_equity:.10f}")
    _set_meta(conn, "tony_open_positions", str(stats.open_positions))
    _set_meta(conn, "tony_open_markets", str(stats.open_markets))
    _set_meta(conn, "tony_mean_market_position", f"{stats.mean_market_position:.10f}")
    _set_meta(conn, "tony_median_market_position", f"{stats.median_market_position:.10f}")
    _set_meta(conn, "tony_p75_market_position", f"{stats.p75_market_position:.10f}")
    _set_meta(conn, "tony_p90_market_position", f"{stats.p90_market_position:.10f}")
    _set_meta(conn, "tony_p95_market_position", f"{stats.p95_market_position:.10f}")
    _set_meta(conn, "tony_max_market_position", f"{stats.max_market_position:.10f}")
    _set_meta(conn, "tony_mean_market_position_pct", f"{stats.mean_market_position_pct:.10f}")
    _set_meta(conn, "tony_median_market_position_pct", f"{stats.median_market_position_pct:.10f}")
    _set_meta(conn, "tony_p75_market_position_pct", f"{stats.p75_market_position_pct:.10f}")
    _set_meta(conn, "tony_p90_market_position_pct", f"{stats.p90_market_position_pct:.10f}")
    _set_meta(conn, "tony_p95_market_position_pct", f"{stats.p95_market_position_pct:.10f}")
    _set_meta(conn, "tony_max_market_position_pct", f"{stats.max_market_position_pct:.10f}")
    _set_meta(conn, "tony_wallet_stats_error", "")


def _position_row_value(row: Mapping[str, Any]) -> float:
    value = _to_float(_first(row, "currentValue", "value"), 0.0)
    if value > 0:
        return value
    size = _to_float(_first(row, "size", "amount"), 0.0)
    price = _to_float(_first(row, "curPrice", "currentPrice"), 0.0)
    return max(0.0, size * price)


def _position_value_stats(values: list[float]) -> dict[str, float]:
    clean = sorted(value for value in values if value > 0)
    if not clean:
        return {"mean": 0.0, "median": 0.0, "p75": 0.0, "p90": 0.0, "p95": 0.0, "max": 0.0}

    def quantile(q: float) -> float:
        if len(clean) == 1:
            return clean[0]
        pos = (len(clean) - 1) * q
        low = int(pos)
        high = min(low + 1, len(clean) - 1)
        if low == high:
            return clean[low]
        return clean[low] * (high - pos) + clean[high] * (pos - low)

    return {
        "mean": sum(clean) / len(clean),
        "median": quantile(0.5),
        "p75": quantile(0.75),
        "p90": quantile(0.9),
        "p95": quantile(0.95),
        "max": clean[-1],
    }


def _fetch_wallet_position_value(wallet: str) -> float:
    try:
        response = requests.get(f"{md.POLY_DATA}/value", params={"user": wallet}, timeout=20, headers=md.HTTP_HEADERS)
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError):
        return 0.0
    rows = data if isinstance(data, list) else data.get("data", [])
    if not rows:
        return 0.0
    return _to_float(rows[0].get("value") if isinstance(rows[0], Mapping) else None, 0.0)


def _fetch_polygon_usdc_balance(wallet: str, rpc_url: str = POLYGON_RPC_URL) -> float:
    total = 0.0
    for contract in POLYGON_USDC_CONTRACTS:
        try:
            total += _erc20_balance_of(rpc_url, contract, wallet, decimals=6)
        except Exception:
            continue
    return total


def fetch_polygon_usdc_balance(wallet: str, rpc_url: str = POLYGON_RPC_URL) -> float:
    return _fetch_polygon_usdc_balance(wallet, rpc_url=rpc_url)


def _erc20_balance_of(rpc_url: str, contract: str, wallet: str, decimals: int = 6) -> float:
    address = wallet.lower().replace("0x", "").rjust(64, "0")
    result = _rpc_call(
        rpc_url,
        "eth_call",
        [{"to": contract, "data": "0x70a08231" + address}, "latest"],
    )
    return int(str(result or "0x0"), 16) / (10**decimals)


def _get_position(conn: sqlite3.Connection, wallet: str, asset: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM positions WHERE trader_wallet = ? AND asset = ?", (wallet, asset)).fetchone()


def _realized_pnl(conn: sqlite3.Connection, wallet: str | None = None) -> float:
    if wallet is None:
        row = conn.execute(
            "SELECT COALESCE(SUM(realized_pnl), 0) AS value FROM paper_orders WHERE status IN ('copied', 'settled')"
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT COALESCE(SUM(realized_pnl), 0) AS value FROM paper_orders WHERE status IN ('copied', 'settled') AND source_wallet = ?",
            (wallet,),
        ).fetchone()
    return float(row["value"] if row else 0.0)


def _ensure_trader(conn: sqlite3.Connection, wallet: str, start_cash: float) -> None:
    """Create a sub-account for ``wallet`` if one does not exist yet."""
    if conn.execute("SELECT 1 FROM traders WHERE wallet = ?", (wallet,)).fetchone():
        return
    now = utc_now()
    seed = float(start_cash)
    conn.execute(
        """
        INSERT OR IGNORE INTO traders
            (wallet, label, active, start_cash, cash, copy_scale_override, rank_score, added_at, updated_at)
        VALUES (?, ?, 1, ?, ?, NULL, 0, ?, ?)
        """,
        (wallet, wallet, seed, seed, now, now),
    )


def _get_trader_cash(conn: sqlite3.Connection, wallet: str, default: float) -> float:
    row = conn.execute("SELECT cash FROM traders WHERE wallet = ?", (wallet,)).fetchone()
    return float(row["cash"]) if row is not None else float(default)


def _set_trader_cash(conn: sqlite3.Connection, wallet: str, cash: float) -> None:
    conn.execute("UPDATE traders SET cash = ?, updated_at = ? WHERE wallet = ?", (float(cash), utc_now(), wallet))


def _total_cash(conn: sqlite3.Connection) -> float:
    row = conn.execute("SELECT COALESCE(SUM(cash), 0) AS total, COUNT(*) AS n FROM traders").fetchone()
    if row is None or int(row["n"]) == 0:
        return _get_float_meta(conn, "cash", 1000.0)
    return float(row["total"] or 0.0)


def _get_meta(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return str(row["value"]) if row else None


def _set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute("INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))


def _get_float_meta(conn: sqlite3.Connection, key: str, default: float) -> float:
    value = _get_meta(conn, key)
    try:
        return float(value) if value is not None else default
    except ValueError:
        return default


def decode_order_filled_log(
    log: Mapping[str, Any],
    wallet: str,
    block_timestamps: Mapping[int, int] | None = None,
) -> dict[str, Any] | None:
    topics = [str(topic).lower() for topic in log.get("topics", [])]
    if len(topics) < 4 or topics[0] != ORDER_FILLED_TOPIC:
        return None
    maker = _topic_to_address(topics[2])
    if maker != _normalize_address(wallet):
        return None

    data_words = _decode_uint_words(str(log.get("data", "0x")))
    if len(data_words) < 5:
        return None
    maker_asset_id, taker_asset_id, maker_amount, taker_amount, fee = data_words[:5]
    if maker_asset_id == 0 and taker_asset_id > 0:
        side = "BUY"
        asset = str(taker_asset_id)
        size = taker_amount / TOKEN_DECIMALS
        notional = maker_amount / TOKEN_DECIMALS
    elif taker_asset_id == 0 and maker_asset_id > 0:
        side = "SELL"
        asset = str(maker_asset_id)
        size = maker_amount / TOKEN_DECIMALS
        notional = taker_amount / TOKEN_DECIMALS
    else:
        return None
    if size <= 0 or notional <= 0:
        return None

    block_number = _hex_to_int(log.get("blockNumber"))
    timestamp = int((block_timestamps or {}).get(block_number, 0))
    source_time = datetime.fromtimestamp(timestamp, timezone.utc).isoformat() if timestamp else ""
    return {
        "platform": "Polymarket",
        "source": "polygon_order_filled",
        "wallet": _normalize_address(wallet),
        "transaction_hash": str(log.get("transactionHash", "")),
        "block_number": block_number,
        "transaction_index": _hex_to_int(log.get("transactionIndex")),
        "log_index": _hex_to_int(log.get("logIndex")),
        "exchange_address": str(log.get("address", "")).lower(),
        "timestamp": timestamp,
        "time": source_time,
        "side": side,
        "asset": asset,
        "price": notional / size,
        "size": size,
        "notional": notional,
        "market_key": "",
        "title": f"On-chain Polymarket token {asset[:10]}...",
        "outcome": "",
        "fee": fee / TOKEN_DECIMALS,
    }


def _fetch_order_filled_logs(rpc_url: str, wallet: str, from_block: int, to_block: int) -> list[dict[str, Any]]:
    logs: list[dict[str, Any]] = []
    maker_topic = _address_topic(wallet)
    for chunk_start in range(from_block, to_block + 1, LOG_BLOCK_CHUNK):
        chunk_end = min(to_block, chunk_start + LOG_BLOCK_CHUNK - 1)
        for address in POLYMARKET_EXCHANGE_ADDRESSES:
            result = _rpc_call(
                rpc_url,
                "eth_getLogs",
                [
                    {
                        "fromBlock": hex(chunk_start),
                        "toBlock": hex(chunk_end),
                        "address": address,
                        "topics": [ORDER_FILLED_TOPIC, None, maker_topic],
                    }
                ],
            )
            if isinstance(result, list):
                logs.extend(result)
    return logs


def _block_timestamps(rpc_url: str, block_numbers: set[int]) -> dict[int, int]:
    timestamps: dict[int, int] = {}
    for block_number in sorted(block_numbers):
        block = _rpc_call(rpc_url, "eth_getBlockByNumber", [hex(block_number), False])
        if isinstance(block, dict) and block.get("timestamp"):
            timestamps[block_number] = int(str(block["timestamp"]), 16)
    return timestamps


def _rpc_call(rpc_url: str, method: str, params: list[Any]) -> Any:
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    response = requests.post(rpc_url, json=payload, timeout=15, headers=md.HTTP_HEADERS)
    response.raise_for_status()
    data = response.json()
    if data.get("error"):
        raise RuntimeError(f"{method} RPC error: {data['error']}")
    return data.get("result")


def _decode_uint_words(data: str) -> list[int]:
    raw = data[2:] if data.startswith("0x") else data
    if not raw:
        return []
    return [int(raw[index : index + 64], 16) for index in range(0, len(raw), 64) if raw[index : index + 64]]


def _address_topic(address: str) -> str:
    normalized = _normalize_address(address).removeprefix("0x")
    return "0x" + ("0" * 24) + normalized


def _topic_to_address(topic: str) -> str:
    return "0x" + str(topic).removeprefix("0x")[-40:].lower()


def _normalize_address(address: str) -> str:
    value = str(address or "").strip().lower()
    return value if value.startswith("0x") else f"0x{value}"


def _hex_to_int(value: Any) -> int:
    if value in (None, ""):
        return 0
    if isinstance(value, int):
        return value
    try:
        return int(str(value), 16)
    except ValueError:
        try:
            return int(float(str(value)))
        except ValueError:
            return 0


def _sort_source_trades(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return trades
    df = trades.copy()
    if "timestamp" not in df:
        if "time" in df:
            df["timestamp"] = pd.to_datetime(df["time"], utc=True, errors="coerce").astype("int64") // 1_000_000_000
        else:
            df["timestamp"] = 0
    return df.sort_values(["timestamp", "transaction_hash"], ascending=[True, True]).reset_index(drop=True)


def _sort_activity(activity: pd.DataFrame) -> pd.DataFrame:
    if activity.empty:
        return activity
    df = activity.copy()
    if "timestamp" not in df:
        df["timestamp"] = 0
    tx_col = "transactionHash" if "transactionHash" in df else "transaction_hash"
    if tx_col not in df:
        df[tx_col] = ""
    return df.sort_values(["timestamp", tx_col], ascending=[True, True]).reset_index(drop=True)


def _source_time(source_trade: Mapping[str, Any], timestamp: int) -> str:
    value = source_trade.get("time")
    if value is not None and not pd.isna(value):
        try:
            return pd.to_datetime(value, utc=True).isoformat()
        except Exception:
            pass
    if timestamp:
        return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()
    return ""


def _timestamp_value(source_trade: Mapping[str, Any]) -> int:
    value = source_trade.get("timestamp")
    if value is None or (isinstance(value, float) and pd.isna(value)):
        time_value = source_trade.get("time")
        if time_value is None or pd.isna(time_value):
            return 0
        try:
            return int(pd.to_datetime(time_value, utc=True).timestamp())
        except Exception:
            return 0
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _json_source(source_trade: Mapping[str, Any]) -> str:
    cleaned = {}
    for key, value in source_trade.items():
        if isinstance(value, pd.Timestamp):
            cleaned[key] = value.isoformat()
        elif pd.isna(value) if not isinstance(value, (list, dict, tuple)) else False:
            cleaned[key] = None
        else:
            cleaned[key] = value
    return json.dumps(cleaned, default=str, sort_keys=True)


def _first(source: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = source.get(key)
        if value not in (None, ""):
            return value
    return None


def _to_float(value: Any, default: float) -> float:
    try:
        if value is None or pd.isna(value):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default
