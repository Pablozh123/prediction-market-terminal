"""Continuously sync Swisstony paper-copy trades.

This runner is paper-only. It never places real Polymarket orders.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import copy_trading as ct


def write_status(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the local Swisstony paper-copy sync loop.")
    parser.add_argument("--interval", type=float, default=1.0, help="Fast on-chain polling interval in seconds.")
    parser.add_argument("--api-interval", type=float, default=30.0, help="Public Data API fallback interval in seconds.")
    parser.add_argument("--settlement-interval", type=float, default=180.0, help="Settlement/redeem recycling sync interval in seconds.")
    parser.add_argument("--limit", type=int, default=500, help="Recent Swisstony trades to inspect per API fallback poll.")
    parser.add_argument("--rpc-url", default=ct.POLYGON_RPC_URL, help="Polygon JSON-RPC endpoint for the fast on-chain path.")
    parser.add_argument("--lookback-blocks", type=int, default=1200, help="Blocks to scan on first fast start.")
    parser.add_argument("--max-block-span", type=int, default=2000, help="Maximum blocks to scan in one fast pass.")
    parser.add_argument("--confirmations", type=int, default=0, help="Blocks to wait before treating events as copyable.")
    parser.add_argument("--disable-fast", action="store_true", help="Disable on-chain OrderFilled polling and use API fallback only.")
    parser.add_argument("--db", default=str(ct.DEFAULT_DB_PATH), help="SQLite path for paper portfolio state.")
    parser.add_argument("--status-file", default=str(ct.DEFAULT_STATUS_PATH), help="JSON status file path.")
    parser.add_argument("--stop-file", default=str(ct.DEFAULT_STOP_PATH), help="Create this file to request shutdown.")
    parser.add_argument("--once", action="store_true", help="Run one sync and exit.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    interval = max(0.25, float(args.interval))
    api_interval = max(interval, float(args.api_interval))
    settlement_interval = max(api_interval, float(args.settlement_interval))
    db_path = Path(args.db)
    status_path = Path(args.status_file)
    stop_path = Path(args.stop_file)
    settings = ct.CopySettings(trade_limit=int(args.limit))
    pid = os.getpid()
    next_api_sync = 0.0
    next_settlement_sync = time.monotonic() + min(30.0, settlement_interval)
    last_fast_result_payload = None
    last_api_result_payload = None
    last_settlement_result_payload = None
    last_fast_sync_at_value = None
    last_api_sync_at_value = None
    last_settlement_sync_at_value = None

    write_status(
        status_path,
        {
            "running": True,
            "pid": pid,
            "mode": "paper_fast_chain" if not args.disable_fast else "paper_api",
            "target_wallet": settings.target_wallet,
            "interval_seconds": interval,
            "api_interval_seconds": api_interval,
            "settlement_interval_seconds": settlement_interval,
            "fast_enabled": not args.disable_fast,
            "rpc_url": args.rpc_url,
            "started_at": ct.utc_now(),
            "last_sync_at": None,
            "last_fast_sync_at": None,
            "last_api_sync_at": None,
            "last_settlement_sync_at": None,
            "last_fast_result": None,
            "last_api_result": None,
            "last_settlement_result": None,
            "last_result": None,
            "last_error": None,
        },
    )

    while True:
        fast_result = None
        api_result = None
        settlement_result = None
        errors: list[str] = []
        last_fast_sync_at = None
        last_api_sync_at = None
        last_settlement_sync_at = None

        if stop_path.exists():
            write_status(
                status_path,
                {
                    "running": False,
                    "pid": pid,
                    "mode": "paper_fast_chain" if not args.disable_fast else "paper_api",
                    "target_wallet": settings.target_wallet,
                    "interval_seconds": interval,
                    "api_interval_seconds": api_interval,
                    "settlement_interval_seconds": settlement_interval,
                    "fast_enabled": not args.disable_fast,
                    "stopped_at": ct.utc_now(),
                    "stop_reason": "stop_file",
                    "last_error": None,
                },
            )
            return 0

        try:
            if not args.disable_fast:
                fast_result = ct.sync_onchain_copy_trades(
                    settings.target_wallet,
                    settings=settings,
                    db_path=db_path,
                    rpc_url=args.rpc_url,
                    lookback_blocks=int(args.lookback_blocks),
                    max_block_span=int(args.max_block_span),
                    confirmations=int(args.confirmations),
                )
                last_fast_sync_at = ct.utc_now()
                if fast_result.errors:
                    errors.extend(fast_result.errors)
                last_fast_result_payload = asdict(fast_result)
                last_fast_sync_at_value = last_fast_sync_at

            due_api = args.once or time.monotonic() >= next_api_sync or args.disable_fast
            if due_api:
                api_result = ct.sync_copy_trades(settings.target_wallet, settings=settings, db_path=db_path)
                last_api_sync_at = ct.utc_now()
                next_api_sync = time.monotonic() + api_interval
                settlement_result = ct.sync_settlement_activity(
                    settings.target_wallet,
                    settings=settings,
                    db_path=db_path,
                    limit=500,
                    pages=1,
                    closed_pages=2,
                    metadata_pages=2,
                ) if args.once else None
                if settlement_result is not None:
                    last_settlement_sync_at = ct.utc_now()
                    if settlement_result.errors:
                        errors.extend(settlement_result.errors)
                    last_settlement_result_payload = asdict(settlement_result)
                    last_settlement_sync_at_value = last_settlement_sync_at

            due_settlement = (not args.once) and time.monotonic() >= next_settlement_sync
            if due_settlement:
                settlement_result = ct.sync_settlement_activity(
                    settings.target_wallet,
                    settings=settings,
                    db_path=db_path,
                    limit=500,
                    pages=1,
                    closed_pages=2,
                    metadata_pages=2,
                )
                last_settlement_sync_at = ct.utc_now()
                if settlement_result.errors:
                    errors.extend(settlement_result.errors)
                last_settlement_result_payload = asdict(settlement_result)
                last_settlement_sync_at_value = last_settlement_sync_at
                next_settlement_sync = time.monotonic() + settlement_interval

            if api_result is not None:
                if api_result.errors:
                    errors.extend(api_result.errors)
                last_api_result_payload = asdict(api_result)
                last_api_sync_at_value = last_api_sync_at

            snapshot = ct.value_paper_portfolio(db_path=db_path)
            dynamic_sizing = ct.get_dynamic_sizing_snapshot(db_path=db_path)
            latest_result = fast_result if fast_result is not None else (settlement_result if settlement_result is not None else api_result)
            write_status(
                status_path,
                {
                    "running": not args.once,
                    "pid": pid,
                    "mode": "paper_fast_chain" if not args.disable_fast else "paper_api",
                    "target_wallet": settings.target_wallet,
                    "interval_seconds": interval,
                    "api_interval_seconds": api_interval,
                    "settlement_interval_seconds": settlement_interval,
                    "fast_enabled": not args.disable_fast,
                    "rpc_url": args.rpc_url,
                    "last_sync_at": ct.utc_now(),
                    "last_fast_sync_at": last_fast_sync_at_value,
                    "last_api_sync_at": last_api_sync_at_value,
                    "last_settlement_sync_at": last_settlement_sync_at_value,
                    "last_fast_result": last_fast_result_payload,
                    "last_api_result": last_api_result_payload,
                    "last_settlement_result": last_settlement_result_payload,
                    "last_result": asdict(latest_result) if latest_result is not None else None,
                    "cash": snapshot.cash,
                    "equity": snapshot.equity,
                    "position_value": snapshot.position_value,
                    "realized_pnl": snapshot.realized_pnl,
                    "unrealized_pnl": snapshot.unrealized_pnl,
                    "open_positions": len(snapshot.positions),
                    "dynamic_sizing": dynamic_sizing,
                    "completed_once": args.once,
                    "last_error": "; ".join(errors[:5]) if errors else None,
                },
            )
        except Exception as exc:
            write_status(
                status_path,
                {
                    "running": True,
                    "pid": pid,
                    "mode": "paper_fast_chain" if not args.disable_fast else "paper_api",
                    "target_wallet": settings.target_wallet,
                    "interval_seconds": interval,
                    "api_interval_seconds": api_interval,
                    "settlement_interval_seconds": settlement_interval,
                    "fast_enabled": not args.disable_fast,
                    "rpc_url": args.rpc_url,
                    "last_sync_at": ct.utc_now(),
                    "last_result": None,
                    "last_error": str(exc),
                },
            )

        if args.once:
            return 0
        time.sleep(interval)


if __name__ == "__main__":
    raise SystemExit(main())
