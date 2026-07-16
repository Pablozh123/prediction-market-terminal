"""Daily resolution join for the append-only signal ledger.

Loads resolved Polymarket markets for every pending resolvable signal, writes
the resolutions into data/signal_ledger.sqlite via app/ledger.py, verifies the
hash chain, and drops a status line into data/ledger_status.json (last run
time, newly resolved count, chain_ok) so the run is observable.

Run:
    python scripts/run_ledger_resolution.py            # daily loop
    python scripts/run_ledger_resolution.py --once     # single run (for testing)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import ledger
from src import prediction_markets as md


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

STATUS_PATH = Path("data/ledger_status.json")
STOP_PATH = Path("data/ledger_resolution.stop")
INTERVAL_SECONDS = 24 * 60 * 60
CONDITION_ID_PATTERN = re.compile(r"^0x[0-9a-fA-F]{64}$")


def fetch_polymarket_resolutions(market_keys: list[str]) -> dict[str, dict[str, Any]]:
    """resolve_pending contract, backed by the Gamma markets API. Keys that are
    not Polymarket conditionIds (e.g. Kalshi tickers) are skipped and stay
    pending."""

    condition_ids = [key for key in market_keys if CONDITION_ID_PATTERN.match(str(key or ""))]
    if not condition_ids:
        return {}
    return ledger.polymarket_resolution_map(md.get_polymarket_markets_by_condition_ids(condition_ids))


def write_status(payload: dict[str, Any]) -> None:
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATUS_PATH.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def resolve_once() -> tuple[int, bool]:
    """Run one resolution join. Returns (newly resolved, chain_ok)."""

    conn = ledger.init_ledger(ledger.DEFAULT_LEDGER_PATH)
    try:
        new_resolved = ledger.resolve_pending(conn, fetch_polymarket_resolutions)
        stats = ledger.ledger_aggregates(conn)
    finally:
        conn.close()
    write_status(
        {
            "last_run_at": utc_now_iso(),
            "new_resolved": int(new_resolved),
            "chain_ok": bool(stats["chain_ok"]),
            "emitted": int(stats["emitted"]),
            "resolved": int(stats["resolved"]),
            "pending": int(stats["pending"]),
            "not_resolvable": int(stats["not_resolvable"]),
        }
    )
    return int(new_resolved), bool(stats["chain_ok"])


def main() -> int:
    parser = argparse.ArgumentParser(description="Join pending ledger signals against resolved market data.")
    parser.add_argument("--once", action="store_true", help="Run a single resolution join and exit.")
    args = parser.parse_args()

    while True:
        if STOP_PATH.exists():
            print("stop file found, exiting")
            STOP_PATH.unlink(missing_ok=True)
            return 0
        try:
            new_resolved, chain_ok = resolve_once()
            print(f"resolution run complete: {new_resolved} newly resolved, chain_ok={chain_ok}")
        except Exception as exc:
            print(f"resolution run failed: {exc}", file=sys.stderr)
            try:
                write_status({"last_run_at": utc_now_iso(), "error": str(exc)})
            except OSError:
                pass
        if args.once:
            return 0
        deadline = time.monotonic() + INTERVAL_SECONDS
        while time.monotonic() < deadline:
            if STOP_PATH.exists():
                STOP_PATH.unlink(missing_ok=True)
                print("stop file found, exiting")
                return 0
            time.sleep(5)


if __name__ == "__main__":
    raise SystemExit(main())
