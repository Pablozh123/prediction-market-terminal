"""Continuously sync paper-copy trades for every active trader.

This runner is paper-only. It never places real Polymarket orders. It copies
every wallet marked active in the ``traders`` table (the list the Copy trade
page edits), each into its own sub-account; with every trader paused it idles.
Only a database with no trader rows at all falls back to the legacy Swisstony
wallet. The loop itself lives in app/copy_daemon.py (the API can host it too).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.copy_daemon import DaemonConfig, run, write_status  # noqa: F401 - write_status re-exported for callers/tests
from src import copy_trading as ct


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the local paper-copy sync loop over every active trader.")
    parser.add_argument("--interval", type=float, default=1.0, help="Fast on-chain polling interval in seconds.")
    parser.add_argument("--api-interval", type=float, default=30.0, help="Public Data API fallback interval in seconds.")
    # 90s: cash recycling is the copy's scarce resource — the source wallet
    # redeploys settlement proceeds within minutes, so we re-sync at least as fast.
    parser.add_argument("--settlement-interval", type=float, default=90.0, help="Settlement/redeem recycling sync interval in seconds.")
    parser.add_argument("--limit", type=int, default=500, help="Recent source trades to inspect per trader and API fallback poll.")
    parser.add_argument("--rpc-url", default=ct.POLYGON_RPC_URL, help="Polygon JSON-RPC endpoint for the fast on-chain path.")
    parser.add_argument("--lookback-blocks", type=int, default=1200, help="Blocks to scan on first fast start.")
    parser.add_argument("--max-block-span", type=int, default=2000, help="Maximum blocks to scan in one fast pass.")
    parser.add_argument("--confirmations", type=int, default=0, help="Blocks to wait before treating events as copyable.")
    parser.add_argument("--disable-fast", action="store_true", help="Disable on-chain OrderFilled polling and use API fallback only.")
    parser.add_argument("--disable-ws", action="store_true", help="Disable the RTDS WebSocket detection path (on-chain stays primary).")
    parser.add_argument(
        "--reconcile-interval",
        type=float,
        default=30.0,
        help="On-chain reconciliation interval in seconds while the WebSocket is connected (runs every tick when it is not).",
    )
    parser.add_argument("--db", default=str(ct.DEFAULT_DB_PATH), help="SQLite path for paper portfolio state.")
    parser.add_argument("--status-file", default=str(ct.DEFAULT_STATUS_PATH), help="JSON status file path.")
    parser.add_argument("--stop-file", default=str(ct.DEFAULT_STOP_PATH), help="Create this file to request shutdown.")
    parser.add_argument("--min-copy-notional", type=float, default=ct.MIN_COPY_NOTIONAL, help="Minimum paper order notional before a BUY is skipped.")
    parser.add_argument("--once", action="store_true", help="Run one sync and exit.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    return run(DaemonConfig(**vars(args)))


if __name__ == "__main__":
    raise SystemExit(main())
