"""Continuous whale-tape ingest into the persistent tape store.

The co-trading graph needs weeks of tape; the public feed serves about a day.
This job closes that gap by running forever: every interval it reads the
newest pages of the Polymarket whale tape and appends what is new to
``data/tape_store.sqlite`` (app/tape_store.py). Overlap between runs is the
design, not a bug — the store de-duplicates on (transaction hash, wallet,
asset), and the loop stops paging as soon as a full page contains nothing new.

Run:
    python scripts/run_tape_ingest.py            # loop (default every 10 min)
    python scripts/run_tape_ingest.py --once     # single pass (for testing)

The tape floor defaults to the same screen floor every insider-score surface
uses (app.suspicion.screen_thresholds), so the stored tape is the same
universe the risk screen reads. Every pass writes a run record into the store
(pages read, rows inserted, floor, errors): the store must be able to say what
it is a sample of, or its graphs inherit the silent-truncation problem the
live tape used to have.

Single instance enforced via app/proc_lock (a second writer on the same WAL
database would be safe but pointless; on the run records it would interleave).
Stop with a ``data/tape_ingest.stop`` file, like the other background jobs.
Intended to run as the Scheduled Task ``MarketIntelTapeIngest``
(scripts/install_autostart.ps1) on the local machine — deliberately NOT on the
deployment host and its small volume.
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import app_settings as cfg  # noqa: E402
from app import proc_lock  # noqa: E402
from app import tape_store as ts  # noqa: E402
from app.suspicion import screen_thresholds  # noqa: E402
from src import prediction_markets as md  # noqa: E402

STOP_PATH = Path("data/tape_ingest.stop")
LOCK_NAME = "tape_ingest.lock"
DEFAULT_PAGES = 8
DEFAULT_PAGE_SIZE = 1000
DEFAULT_INTERVAL_MIN = 10.0


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ingest_once(conn, min_cash: float, pages: int, page_size: int, fetch=None) -> dict:
    """One pass over the newest tape pages; returns the run record it stored.

    Pages are read newest-first. The pass ends early in two honest ways: a
    short page (the feed itself ended) or a full page that inserted nothing
    (the pass reached tape the store already holds). A fetch error ends it
    too, but that one is recorded as ``truncated_by_error`` — a pass that
    dies on page 2 of 8 covered less tape, and the run record is where that
    stops being invisible.

    ``fetch`` is the page call and exists so tests can run without a network;
    without it, it is ``md.get_polymarket_trades``.
    """

    hole = fetch or md.get_polymarket_trades
    record = {
        "started_at": _now_iso(), "source": "polymarket_trades",
        "min_cash": float(min_cash), "pages_requested": int(pages), "pages_read": 0,
        "rows_fetched": 0, "rows_inserted": 0, "rows_skipped": 0,
        "oldest_ts": None, "newest_ts": None, "truncated_by_error": False, "error": "",
    }
    for page in range(max(1, int(pages))):
        try:
            frame = hole(limit=int(page_size), min_cash=float(min_cash),
                         offset=page * int(page_size))
        except Exception as exc:  # noqa: BLE001 - the loop must survive the feed
            record["truncated_by_error"] = True
            record["error"] = f"{type(exc).__name__}: {exc}"[:500]
            break
        if frame is None or frame.empty:
            break
        record["pages_read"] += 1
        result = ts.insert_tape(conn, frame)
        record["rows_fetched"] += result["fetched"]
        record["rows_inserted"] += result["inserted"]
        record["rows_skipped"] += result["skipped"]
        for key, pick in (("oldest_ts", min), ("newest_ts", max)):
            if result[key] is not None:
                record[key] = result[key] if record[key] is None else pick(record[key], result[key])
        if len(frame) >= int(page_size) and result["inserted"] == 0:
            break  # a full page of already-known prints: caught up with the store
        if len(frame) < int(page_size):
            break  # the feed ended before the page did
    record["finished_at"] = _now_iso()
    ts.record_run(conn, record)
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest the Polymarket whale tape into the persistent tape store.")
    parser.add_argument("--once", action="store_true", help="Run a single pass and exit.")
    parser.add_argument("--pages", type=int, default=DEFAULT_PAGES, help="Maximum feed pages per pass.")
    parser.add_argument("--page-size", type=int, default=DEFAULT_PAGE_SIZE, help="Prints per feed page.")
    parser.add_argument("--interval-min", type=float, default=DEFAULT_INTERVAL_MIN, help="Minutes between passes.")
    parser.add_argument("--min-cash", type=float, default=None,
                        help="Tape floor in dollars; default is the configured screen floor.")
    parser.add_argument("--db", default=str(ts.DEFAULT_STORE_PATH), help="Path of the store database.")
    args = parser.parse_args()

    db_path = Path(args.db)
    try:
        lock = proc_lock.acquire(db_path.parent, name=LOCK_NAME)
    except proc_lock.AlreadyRunning as exc:
        print(str(exc), file=sys.stderr)
        return 1
    conn = ts.connect(db_path)
    try:
        while True:
            if STOP_PATH.exists():
                STOP_PATH.unlink(missing_ok=True)
                print("stop file found, exiting")
                return 0
            if args.min_cash is not None:
                floor = float(args.min_cash)
            else:
                _whale, floor = screen_thresholds(cfg.load_settings())
            try:
                record = ingest_once(conn, floor, args.pages, args.page_size)
                cov = ts.coverage(conn)
                note = f", truncated: {record['error']}" if record["truncated_by_error"] else ""
                print(
                    f"pass done: {record['rows_inserted']} new of {record['rows_fetched']} fetched "
                    f"({record['pages_read']} pages from ${floor:,.0f}){note}; "
                    f"store: {cov['rows']:,} prints, {cov['window_days']:.1f} days, {cov['wallets']:,} wallets",
                    flush=True,
                )
            except Exception as exc:  # noqa: BLE001 - one bad pass must not kill the job
                print(f"pass failed: {exc}", file=sys.stderr, flush=True)
            if args.once:
                return 0
            deadline = time.monotonic() + max(1.0, float(args.interval_min)) * 60.0
            while time.monotonic() < deadline:
                if STOP_PATH.exists():
                    STOP_PATH.unlink(missing_ok=True)
                    print("stop file found, exiting")
                    return 0
                time.sleep(5)
    finally:
        conn.close()
        proc_lock.release(lock)


if __name__ == "__main__":
    raise SystemExit(main())
