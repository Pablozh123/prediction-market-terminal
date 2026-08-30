"""Persistent whale-tape store (SQLite/WAL, Streamlit-free).

The co-trading graph on the risk screen is computed over the live trade feed,
and the feed only reaches back about a day. On one day of tape almost no wallet
pair shares three markets, which is why the edge-rule ladder exists: the strict
rule finds nothing, so the screen relaxes it until something shows. The ladder
is honest about that, but it is a workaround for a data problem, not a method.
The fix is depth, and depth requires keeping the tape: this module stores every
whale print the ingest job sees, so the graph can be computed over weeks under
the strict rule instead of over a day under a relaxed one.

The store also answers a question the live tape cannot: when a wallet was
really first seen. Inside a one-day sample every wallet that entered the window
late looks new, and the "sample-fresh large wallet" signal fires on age it
cannot know. With the store, "first seen" means first print since ingest began,
which only ever gets more right as the store grows.

Size, measured rather than guessed: a stored print costs ~850 bytes including
indexes (3,000 prints came to 2.5 MB). At the $500 screen floor the venue
printed at a pace of roughly 20-30k rows a day when this landed, which is a
few tens of MB per day and single-digit GB per year. That is nothing on a
local disk and out of the question on the deployment's 500 MB volume — so the
store lives locally next to the other SQLite files, and the API treats a
missing store as "no store" and falls back to the live tape.

Writer model: one writer (the ingest job in ``scripts/run_tape_ingest.py``,
guarded by ``app.proc_lock``), any number of readers via WAL — the same
arrangement as ``data/signal_ledger.sqlite``.

Re-ingesting the same page is the normal case, not an error: the feed is read
newest-first and every run overlaps the last one. A row is identified by
(transaction hash, wallet, asset) — the dedup key the paged live tape already
uses — and the wallet first/last-seen table is maintained with MIN/MAX, so
every write path is idempotent.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any, Iterable, Mapping

import pandas as pd

DEFAULT_STORE_PATH = Path("data/tape_store.sqlite")
SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS trades (
    tx_hash TEXT NOT NULL,
    wallet TEXT NOT NULL,
    asset TEXT NOT NULL DEFAULT '',
    timestamp INTEGER NOT NULL,
    market_key TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL DEFAULT '',
    outcome TEXT NOT NULL DEFAULT '',
    side TEXT NOT NULL DEFAULT '',
    price REAL NOT NULL DEFAULT 0.0,
    size REAL NOT NULL DEFAULT 0.0,
    notional REAL NOT NULL DEFAULT 0.0,
    trader TEXT NOT NULL DEFAULT '',
    slug TEXT NOT NULL DEFAULT '',
    url TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (tx_hash, wallet, asset)
);

CREATE INDEX IF NOT EXISTS idx_trades_timestamp ON trades (timestamp);
CREATE INDEX IF NOT EXISTS idx_trades_wallet ON trades (wallet, timestamp);

CREATE TABLE IF NOT EXISTS wallets (
    wallet TEXT PRIMARY KEY,
    first_seen INTEGER NOT NULL,
    last_seen INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS ingest_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'polymarket_trades',
    min_cash REAL NOT NULL DEFAULT 0.0,
    pages_requested INTEGER NOT NULL DEFAULT 0,
    pages_read INTEGER NOT NULL DEFAULT 0,
    rows_fetched INTEGER NOT NULL DEFAULT 0,
    rows_inserted INTEGER NOT NULL DEFAULT 0,
    rows_skipped INTEGER NOT NULL DEFAULT 0,
    oldest_ts INTEGER,
    newest_ts INTEGER,
    truncated_by_error INTEGER NOT NULL DEFAULT 0,
    error TEXT NOT NULL DEFAULT ''
);
"""

#: Column order of the frames ``load_tape_window`` returns. Deliberately the
#: shape of ``get_polymarket_trades``: everything downstream of the live tape
#: (screen filters, co-trading network, sample labels) reads these names, and
#: a store that returns a different shape would need its own consumers.
TAPE_COLUMNS = [
    "platform", "time", "trader", "wallet", "side", "outcome", "title",
    "price", "size", "notional", "market_key", "asset", "timestamp",
    "transaction_hash", "slug", "url",
]


def connect(path: Path | str = DEFAULT_STORE_PATH) -> sqlite3.Connection:
    """Open (and if needed create) the store; WAL on, schema applied."""

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.executescript(_SCHEMA)
    if int(conn.execute("PRAGMA user_version").fetchone()[0]) < SCHEMA_VERSION:
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    conn.commit()
    return conn


def _text(value: Any) -> str:
    if value is None or (isinstance(value, float) and value != value):
        return ""
    return str(value)


def _num(value: Any) -> float:
    """Scalar to float; None/NaN/garbage become 0.0 (NaN is truthy, so no ``or``)."""
    number = pd.to_numeric(value, errors="coerce")
    try:
        number = float(number)
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if number != number else number


def _rows_from_frame(frame: pd.DataFrame) -> tuple[list[tuple], int]:
    """Tape frame -> insertable rows, plus how many rows had no identity.

    A print without a transaction hash, wallet or timestamp cannot be
    de-duplicated against later fetches, so storing it would turn every
    re-ingest into growth. Such rows are counted, not stored: the count goes
    into the run record, where a rising number is a feed problem worth seeing.
    """

    frame = frame.reset_index(drop=True)
    rows: list[tuple] = []
    skipped = 0
    tx = frame.get("transaction_hash", pd.Series("", index=frame.index))
    wallet = frame.get("wallet", pd.Series("", index=frame.index))
    stamp = pd.to_numeric(frame.get("timestamp", pd.Series(0, index=frame.index)), errors="coerce").fillna(0)
    for i in frame.index:
        tx_hash = _text(tx.get(i)).strip()
        w = _text(wallet.get(i)).strip().lower()
        ts = int(stamp.get(i, 0) or 0)
        if not tx_hash or not w or ts <= 0:
            skipped += 1
            continue
        row = frame.loc[i]
        rows.append((
            tx_hash, w, _text(row.get("asset")).strip(), ts,
            _text(row.get("market_key")), _text(row.get("title")),
            _text(row.get("outcome")), _text(row.get("side")),
            _num(row.get("price")), _num(row.get("size")), _num(row.get("notional")),
            _text(row.get("trader")), _text(row.get("slug")), _text(row.get("url")),
        ))
    return rows, skipped


def insert_tape(conn: sqlite3.Connection, frame: pd.DataFrame) -> dict[str, Any]:
    """Insert one tape fetch; returns fetched/inserted/skipped and the span.

    ``INSERT OR IGNORE`` on the (tx_hash, wallet, asset) key makes overlap
    free, and the wallet first/last-seen upsert uses MIN/MAX, so inserting the
    same frame twice changes nothing. ``inserted`` counts rows that were
    actually new — the ingest loop uses a zero here on a full page as its
    "caught up with the store" signal.
    """

    result = {"fetched": int(0 if frame is None else len(frame)), "inserted": 0,
              "skipped": 0, "oldest_ts": None, "newest_ts": None}
    if frame is None or frame.empty:
        return result
    rows, skipped = _rows_from_frame(frame)
    result["skipped"] = skipped
    if not rows:
        return result
    before = conn.total_changes
    conn.executemany(
        "INSERT OR IGNORE INTO trades (tx_hash, wallet, asset, timestamp, market_key, title,"
        " outcome, side, price, size, notional, trader, slug, url)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    result["inserted"] = conn.total_changes - before
    stamps = [row[3] for row in rows]
    result["oldest_ts"] = min(stamps)
    result["newest_ts"] = max(stamps)
    seen: dict[str, tuple[int, int]] = {}
    for row in rows:
        first, last = seen.get(row[1], (row[3], row[3]))
        seen[row[1]] = (min(first, row[3]), max(last, row[3]))
    conn.executemany(
        "INSERT INTO wallets (wallet, first_seen, last_seen) VALUES (?, ?, ?)"
        " ON CONFLICT(wallet) DO UPDATE SET"
        " first_seen = MIN(first_seen, excluded.first_seen),"
        " last_seen = MAX(last_seen, excluded.last_seen)",
        [(wallet, first, last) for wallet, (first, last) in seen.items()],
    )
    conn.commit()
    return result


def record_run(conn: sqlite3.Connection, record: Mapping[str, Any]) -> None:
    """Append one ingest-run row; this is the store's own sample record.

    Coverage claims about the store ("N days of stored tape from $X") lean on
    these rows: the floor each run was fetched at, whether the page loop was
    cut short, and what the error was. A store without run records could not
    say what it is a sample OF, which is the same silent-truncation problem
    the live tape had before ``sample_coverage``.
    """

    conn.execute(
        "INSERT INTO ingest_runs (started_at, finished_at, source, min_cash, pages_requested,"
        " pages_read, rows_fetched, rows_inserted, rows_skipped, oldest_ts, newest_ts,"
        " truncated_by_error, error)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            _text(record.get("started_at")), _text(record.get("finished_at")),
            _text(record.get("source")) or "polymarket_trades",
            float(record.get("min_cash") or 0.0),
            int(record.get("pages_requested") or 0), int(record.get("pages_read") or 0),
            int(record.get("rows_fetched") or 0), int(record.get("rows_inserted") or 0),
            int(record.get("rows_skipped") or 0),
            record.get("oldest_ts"), record.get("newest_ts"),
            1 if record.get("truncated_by_error") else 0,
            _text(record.get("error"))[:500],
        ),
    )
    conn.commit()


def coverage(conn: sqlite3.Connection) -> dict[str, Any]:
    """What the store holds and how it was filled — the honest sample record.

    ``ingest_floor`` is the highest floor any run fetched at: below that
    notional the store makes no completeness claim, whatever a query asks for.
    ``newest_ts`` doubles as the staleness check — a store whose newest print
    is hours old means the ingest job is down, and a graph computed over it
    would silently freeze while looking current.
    """

    rows, oldest, newest = conn.execute(
        "SELECT COUNT(*), MIN(timestamp), MAX(timestamp) FROM trades").fetchone()
    wallets = conn.execute("SELECT COUNT(*) FROM wallets").fetchone()[0]
    floor_row = conn.execute("SELECT MAX(min_cash), COUNT(*) FROM ingest_runs").fetchone()
    last = conn.execute(
        "SELECT finished_at, error, truncated_by_error FROM ingest_runs ORDER BY id DESC LIMIT 1"
    ).fetchone()
    window_days = 0.0
    if oldest and newest and newest > oldest:
        window_days = (newest - oldest) / 86400.0
    return {
        "rows": int(rows or 0),
        "wallets": int(wallets or 0),
        "oldest_ts": int(oldest) if oldest else None,
        "newest_ts": int(newest) if newest else None,
        "window_days": float(window_days),
        "ingest_floor": float(floor_row[0] or 0.0),
        "runs": int(floor_row[1] or 0),
        "last_run_at": str(last[0]) if last else "",
        "last_run_error": str(last[1]) if last else "",
        "last_run_truncated": bool(last[2]) if last else False,
    }


def load_tape_window(
    conn: sqlite3.Connection,
    days: float,
    min_cash: float = 0.0,
    now_ts: int | None = None,
) -> pd.DataFrame:
    """The last ``days`` of stored tape, in the live tape's column shape.

    ``min_cash`` filters on notional like the feed parameter of the same name;
    a floor below ``coverage()['ingest_floor']`` returns rows but no
    completeness — the store never fetched below its ingest floor, so the
    caller's sample note must quote the higher of the two.
    """

    reference = int(now_ts if now_ts is not None else time.time())
    cutoff = reference - int(float(days) * 86400)
    frame = pd.read_sql_query(
        "SELECT tx_hash AS transaction_hash, wallet, asset, timestamp, market_key, title,"
        " outcome, side, price, size, notional, trader, slug, url"
        " FROM trades WHERE timestamp >= ? AND notional >= ? ORDER BY timestamp",
        conn,
        params=(cutoff, float(min_cash)),
    )
    if frame.empty:
        return pd.DataFrame(columns=TAPE_COLUMNS)
    frame["platform"] = "Polymarket"
    frame["time"] = pd.to_datetime(frame["timestamp"], unit="s", utc=True, errors="coerce")
    return frame[TAPE_COLUMNS]


def first_seen_map(
    conn: sqlite3.Connection, wallets: Iterable[str] | None = None
) -> dict[str, int]:
    """Wallet -> first stored print (unix seconds), lowercased keys.

    "First seen" here means first seen since ingest began — a floor on the
    wallet's age, not its birthday. That is exactly the direction the fresh-
    wallet signal needs: a wallet the store has known for weeks is provably
    not new, while a wallet the store meets today may still be old.
    """

    if wallets is None:
        cursor = conn.execute("SELECT wallet, first_seen FROM wallets")
        return {str(w): int(ts) for w, ts in cursor.fetchall()}
    keys = sorted({str(w).strip().lower() for w in wallets if str(w).strip()})
    out: dict[str, int] = {}
    for start in range(0, len(keys), 500):
        chunk = keys[start:start + 500]
        marks = ",".join("?" for _ in chunk)
        cursor = conn.execute(
            f"SELECT wallet, first_seen FROM wallets WHERE wallet IN ({marks})", chunk)
        out.update({str(w): int(ts) for w, ts in cursor.fetchall()})
    return out
