"""The paper copy daemon loop, importable.

``scripts/run_copy_trader.py`` parses the command line and calls :func:`run`;
``api/server.py`` starts the same loop in a background thread when
``COPY_DAEMON=1`` (one Railway service, one volume — a second process could
not share the SQLite file). Behaviour is identical either way: WebSocket
detection with a dedicated apply thread, on-chain reconciliation, the public
API as fallback, settlement recycling, equity snapshots, a status file the
Copy trade page reads, and a stop file that ends the loop.
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from src import copy_trading as ct


@dataclass
class DaemonConfig:
    """Mirrors the CLI flags of scripts/run_copy_trader.py, name for name."""

    interval: float = 1.0
    api_interval: float = 30.0
    settlement_interval: float = 90.0
    limit: int = 500
    rpc_url: str = ct.POLYGON_RPC_URL
    lookback_blocks: int = 1200
    max_block_span: int = 2000
    confirmations: int = 0
    disable_fast: bool = False
    disable_ws: bool = False
    reconcile_interval: float = 30.0
    db: str = str(ct.DEFAULT_DB_PATH)
    status_file: str = str(ct.DEFAULT_STATUS_PATH)
    stop_file: str = str(ct.DEFAULT_STOP_PATH)
    min_copy_notional: float = ct.MIN_COPY_NOTIONAL
    once: bool = False


def write_status(path: Path, payload: dict[str, Any], attempts: int = 8) -> None:
    """Atomic status write, best effort.

    On Windows ``os.replace`` fails with "access denied" while another process
    (the API answering /api/copy) has the file open for reading — a race
    that killed the daemon once, in the very second the page was refreshed.
    Retry briefly; a status write that still fails is dropped, never fatal:
    the books are in SQLite, the status file is only the pulse.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    for attempt in range(max(1, attempts)):
        try:
            tmp.replace(path)
            return
        except PermissionError:
            time.sleep(0.05 * (attempt + 1))
        except OSError:
            break
    try:
        # Last resort: overwrite in place (not atomic, but a reader that
        # catches a half-written file simply retries next time).
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    except OSError:
        pass


def run(args: DaemonConfig | Any) -> int:
    """Run the loop until the stop file appears (or once, with ``once``)."""
    interval = max(0.25, float(args.interval))
    api_interval = max(interval, float(args.api_interval))
    settlement_interval = max(api_interval, float(args.settlement_interval))
    db_path = Path(args.db)
    status_path = Path(args.status_file)
    stop_path = Path(args.stop_file)
    base_settings = ct.CopySettings(trade_limit=int(args.limit), min_copy_notional=max(0.0, float(args.min_copy_notional)))
    settings = ct.load_copy_settings(default=base_settings)
    pid = os.getpid()
    next_api_sync = 0.0
    next_settlement_sync = time.monotonic() + min(30.0, settlement_interval)
    last_fast_result_payload = None
    last_api_result_payload = None
    last_settlement_result_payload = None
    last_ws_result_payload = None
    last_fast_sync_at_value = None
    last_api_sync_at_value = None
    last_settlement_sync_at_value = None
    last_ws_sync_at_value = None

    # RTDS WebSocket detection: sees the off-chain match instantly, ahead of the
    # on-chain OrderFilled log. The on-chain poll stays on as a slower
    # reconciliation/fallback layer; cross-detection fill dedup prevents double
    # copies. Disabled with --disable-ws or when websocket-client is missing.
    # Latency telemetry compares the local clock against exchange-stamped trade
    # times; measure the offset so an unsynchronized system clock (seen live:
    # +68s, W32Time free-running) doesn't poison every number.
    clock_offset_holder: dict[str, Any] = {"value": ct.measure_clock_offset_seconds(), "measured_at": time.monotonic()}

    def refresh_clock_offset() -> None:
        if time.monotonic() - clock_offset_holder["measured_at"] >= 1800.0:
            offset = ct.measure_clock_offset_seconds()
            if offset is not None:
                clock_offset_holder["value"] = offset
            clock_offset_holder["measured_at"] = time.monotonic()

    ws_enabled = not args.disable_ws and ct.RtdsTradeListener.available()
    ws_listener = None
    ws_worker = None
    if ws_enabled:
        ws_listener = ct.RtdsTradeListener(ct.active_trader_wallets(db_path=db_path))
        ws_enabled = ws_listener.start()
    if ws_enabled and not args.once:
        # Dedicated apply thread: detection-to-booking latency must not wait on
        # the blocking reconciliation syncs in this loop (live: median 105s).
        ws_worker = ct.WsApplyWorker(
            ws_listener,
            db_path=db_path,
            settings_loader=lambda: ct.load_copy_settings(default=base_settings),
            clock_offset_provider=lambda: clock_offset_holder["value"],
        )
        ws_worker.start()
    reconcile_interval = max(interval, float(args.reconcile_interval))
    next_reconcile = 0.0
    rpc_fail_streak = 0

    def mode_label() -> str:
        if ws_enabled:
            return "paper_ws_chain" if not args.disable_fast else "paper_ws"
        return "paper_fast_chain" if not args.disable_fast else "paper_api"

    write_status(
        status_path,
        {
            "running": True,
            "pid": pid,
            "mode": mode_label(),
            "target_wallet": settings.target_wallet,
            "interval_seconds": interval,
            "api_interval_seconds": api_interval,
            "settlement_interval_seconds": settlement_interval,
            "reconcile_interval_seconds": reconcile_interval,
            "fast_enabled": not args.disable_fast,
            "ws_enabled": ws_enabled,
            "ws_url": ct.RTDS_WS_URL,
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
        settings = ct.load_copy_settings(default=base_settings)
        fast_result = None
        api_result = None
        settlement_result = None
        ws_result = None
        errors: list[str] = []
        last_fast_sync_at = None
        last_api_sync_at = None
        last_settlement_sync_at = None
        last_ws_sync_at = None

        if stop_path.exists():
            if ws_worker is not None:
                ws_worker.stop()
            if ws_listener is not None:
                ws_listener.stop()
            write_status(
                status_path,
                {
                    "running": False,
                    "pid": pid,
                    "mode": mode_label(),
                    "target_wallet": settings.target_wallet,
                    "interval_seconds": interval,
                    "api_interval_seconds": api_interval,
                    "settlement_interval_seconds": settlement_interval,
                    "fast_enabled": not args.disable_fast,
                    "ws_enabled": ws_enabled,
                    "stopped_at": ct.utc_now(),
                    "stop_reason": "stop_file",
                    "last_error": None,
                },
            )
            return 0

        try:
            refresh_clock_offset()
            if ws_listener is not None:
                ws_listener.set_wallets(ct.active_trader_wallets(db_path=db_path))
                if ws_worker is not None:
                    worker_status = ws_worker.status()
                    if worker_status.get("last_result"):
                        last_ws_result_payload = worker_status["last_result"]
                        last_ws_sync_at_value = worker_status.get("last_apply_at")
                else:
                    # --once: drain synchronously so the single pass is complete.
                    ws_trades = ws_listener.drain()
                    if ws_trades:
                        ws_result = ct.aggregate_sync_results(ct.apply_ws_trades(ws_trades, settings=settings, db_path=db_path))
                        last_ws_sync_at = ct.utc_now()
                        if ws_result.errors:
                            errors.extend(ws_result.errors)
                        last_ws_result_payload = asdict(ws_result)
                        last_ws_sync_at_value = last_ws_sync_at

            # With the WebSocket connected, the on-chain scan is demoted from
            # every-tick polling to a slower reconciliation sweep — the WS sees
            # fills ~2s earlier; the chain pass just catches anything missed.
            ws_connected = bool(ws_listener is not None and ws_listener.status().get("connected"))
            chain_due = args.once or not ws_connected or time.monotonic() >= next_reconcile
            if not args.disable_fast and chain_due:
                # Best-effort reconciliation behind the WebSocket: never let a
                # flaky/rate-limited RPC abort the loop and starve the WS status write.
                try:
                    fast_result = ct.aggregate_sync_results(
                        ct.sync_active_onchain_copy_trades(
                            settings=settings,
                            db_path=db_path,
                            rpc_url=args.rpc_url,
                            lookback_blocks=int(args.lookback_blocks),
                            max_block_span=int(args.max_block_span),
                            confirmations=int(args.confirmations),
                        )
                    )
                except Exception as exc:
                    fast_result = ct.SyncResult(source="chain", errors=(f"reconcile failed: {exc}",))
                # Back off exponentially while the free RPC rate-limits: a pass
                # every 30s against a 429ing endpoint blocks the loop for nothing.
                if fast_result.errors and all("rpc unavailable" in err or "reconcile failed" in err for err in fast_result.errors):
                    rpc_fail_streak += 1
                else:
                    rpc_fail_streak = 0
                next_reconcile = time.monotonic() + ct.reconcile_backoff_seconds(rpc_fail_streak, reconcile_interval)
                last_fast_sync_at = ct.utc_now()
                if fast_result.errors:
                    errors.extend(fast_result.errors)
                last_fast_result_payload = asdict(fast_result)
                last_fast_sync_at_value = last_fast_sync_at

            due_api = args.once or time.monotonic() >= next_api_sync or args.disable_fast
            if due_api:
                api_result = ct.aggregate_sync_results(ct.sync_active_copy_trades(settings=settings, db_path=db_path))
                last_api_sync_at = ct.utc_now()
                next_api_sync = time.monotonic() + api_interval
                settlement_result = ct.aggregate_sync_results(
                    ct.sync_active_settlement_activity(
                        settings=settings,
                        db_path=db_path,
                        limit=500,
                        pages=1,
                        closed_pages=2,
                        metadata_pages=2,
                    )
                ) if args.once else None
                if settlement_result is not None:
                    last_settlement_sync_at = ct.utc_now()
                    if settlement_result.errors:
                        errors.extend(settlement_result.errors)
                    last_settlement_result_payload = asdict(settlement_result)
                    last_settlement_sync_at_value = last_settlement_sync_at

            due_settlement = (not args.once) and time.monotonic() >= next_settlement_sync
            if due_settlement:
                settlement_result = ct.aggregate_sync_results(
                    ct.sync_active_settlement_activity(
                        settings=settings,
                        db_path=db_path,
                        limit=500,
                        pages=1,
                        closed_pages=2,
                        metadata_pages=2,
                    )
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
            try:
                ct.record_equity_snapshot(db_path=db_path, snapshot=snapshot, min_interval_seconds=60.0)
                # One curve per trader — the comparison the multi-trader test is about.
                ct.record_trader_equity_snapshots(db_path=db_path, min_interval_seconds=60.0)
            except Exception:
                pass  # history is best-effort; never stall the copy loop for it
            dynamic_sizing = ct.get_dynamic_sizing_snapshot(db_path=db_path)
            latest_result = next(
                (result for result in (ws_result, fast_result, settlement_result, api_result) if result is not None),
                None,
            )
            write_status(
                status_path,
                {
                    "running": not args.once,
                    "pid": pid,
                    "mode": mode_label(),
                    "target_wallet": settings.target_wallet,
                    "trader_wallets": ct.active_trader_wallets(db_path=db_path),
                    "interval_seconds": interval,
                    "api_interval_seconds": api_interval,
                    "settlement_interval_seconds": settlement_interval,
                    "reconcile_interval_seconds": reconcile_interval,
                    "fast_enabled": not args.disable_fast,
                    "ws_enabled": ws_enabled,
                    "ws_connected": ws_connected,
                    "ws_status": ws_listener.status() if ws_listener is not None else None,
                    "ws_worker": ws_worker.status() if ws_worker is not None else None,
                    "rpc_fail_streak": rpc_fail_streak,
                    "clock_offset_seconds": clock_offset_holder["value"],
                    "rpc_url": args.rpc_url,
                    "last_sync_at": ct.utc_now(),
                    "last_ws_sync_at": last_ws_sync_at_value,
                    "last_fast_sync_at": last_fast_sync_at_value,
                    "last_api_sync_at": last_api_sync_at_value,
                    "last_settlement_sync_at": last_settlement_sync_at_value,
                    "last_ws_result": last_ws_result_payload,
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
                    "copy_settings": asdict(settings),
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
                    "mode": mode_label(),
                    "target_wallet": settings.target_wallet,
                    "interval_seconds": interval,
                    "api_interval_seconds": api_interval,
                    "settlement_interval_seconds": settlement_interval,
                    "fast_enabled": not args.disable_fast,
                    "ws_enabled": ws_enabled,
                    "rpc_url": args.rpc_url,
                    "last_sync_at": ct.utc_now(),
                    "last_result": None,
                    "last_error": str(exc),
                },
            )

        if args.once:
            if ws_worker is not None:
                ws_worker.stop()
            if ws_listener is not None:
                ws_listener.stop()
            return 0
        time.sleep(interval)


def start_thread(config: DaemonConfig, name: str = "copy-daemon") -> threading.Thread:
    """Run the loop in a daemon thread of the current process (the API host).

    A stale stop file from an earlier run is cleared first, otherwise the loop
    would exit on its first tick. The thread dies with the process; the books
    are in SQLite, so nothing is lost across a restart.
    """
    stop = Path(config.stop_file)
    if stop.exists():
        try:
            stop.unlink()
        except OSError:
            pass
    thread = threading.Thread(target=run, args=(config,), name=name, daemon=True)
    thread.start()
    return thread
