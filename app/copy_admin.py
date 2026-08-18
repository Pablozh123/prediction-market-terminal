"""The paper copy desk behind the web frontend.

Everything the Copy trade page can *do* — follow or pause a trader, change
the sizing settings, top up a sub-account, run one sync pass, read the
daemon's pulse — lives here as plain functions over ``src.copy_trading``.
``api/server.py`` wraps them in routes and adds nothing of its own, so the
behaviour is testable without HTTP and the same functions can serve a CLI or
the Streamlit page later.

Write access
------------
The public site is read-only; the desk is a local instrument. A request may
write when it comes from this machine (loopback) and no admin token is
configured, or when it carries the token from ``COPY_ADMIN_TOKEN``. Anything
else is refused with a reason the page can show. Nothing here ever places a
real order: ``live_trading_enabled`` is not an editable setting.
"""

from __future__ import annotations

import hmac
import json
import os
import re
import threading
import time
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

import pandas as pd

from src import copy_trading as ct
from src import prediction_markets as md

ADMIN_TOKEN_ENV = "COPY_ADMIN_TOKEN"
ADMIN_TOKEN_HEADER = "X-Admin-Token"
LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}
#: The daemon writes its status file every loop (interval 1 s, API poll 30 s);
#: a file older than this describes a process that stopped without saying so.
DAEMON_STALE_AFTER_S = 180.0

#: Settings the page may change, with the type they are coerced to. The
#: engine reads the file on every loop, so a change lands within one pass.
EDITABLE_SETTINGS: dict[str, type] = {
    "dynamic_sizing_enabled": bool,
    "dynamic_sizing_multiplier": float,
    "dynamic_scale_max": float,
    "dynamic_scale_min": float,
    "copy_scale": float,
    "max_order_equity_pct": float,
    "dynamic_order_cap_from_tony": bool,
    "cash_throttle_pct": float,
    "auto_top_up_enabled": bool,
    "auto_top_up_amount": float,
    "auto_top_up_threshold": float,
    "min_copy_notional": float,
    "trade_limit": int,
    "paper_start_cash": float,
}
#: Fractions of equity/cash: clamped to 0..1 so a "5" typed for 5 % cannot
#: turn into a five-fold order cap.
FRACTION_SETTINGS = {"dynamic_scale_max", "dynamic_scale_min", "max_order_equity_pct", "cash_throttle_pct"}


# --- write access -------------------------------------------------------------


@dataclass(frozen=True)
class WriteAccess:
    allowed: bool
    #: 'loopback' (local, no token needed), 'token' (a token is configured;
    #: allowed says whether this request carried it), 'locked' (remote, no
    #: token configured — writes are impossible from here).
    mode: str
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {"allowed": self.allowed, "mode": self.mode, "reason": self.reason}


def is_loopback(host: str | None) -> bool:
    value = str(host or "").strip().lower()
    if value.startswith("::ffff:"):
        value = value[7:]
    return value in LOOPBACK_HOSTS


def write_access(client_host: str | None, presented_token: str | None, configured_token: str | None) -> WriteAccess:
    """Decide whether a request may change the desk.

    A configured token wins over locality: once ``COPY_ADMIN_TOKEN`` is set,
    even local requests must carry it (one rule, no surprise when the site
    moves to a host). Without a token only loopback may write.
    """
    token = str(configured_token or "").strip()
    if token:
        presented = str(presented_token or "").strip()
        if presented and hmac.compare_digest(presented, token):
            return WriteAccess(True, "token", "admin token accepted")
        return WriteAccess(False, "token", f"admin token required ({ADMIN_TOKEN_HEADER} header)")
    if is_loopback(client_host):
        return WriteAccess(True, "loopback", "local request, no admin token configured")
    return WriteAccess(False, "locked", f"writes are accepted from this machine only unless {ADMIN_TOKEN_ENV} is set")


def configured_token() -> str:
    return os.environ.get(ADMIN_TOKEN_ENV, "").strip()


# --- wallet input -------------------------------------------------------------

_ADDRESS_RE = re.compile(r"0x[a-fA-F0-9]{40}")


def resolve_wallet(text: Any, leaderboard_loader: Callable[..., pd.DataFrame] | None = None) -> str:
    """Turn what someone pasted into a lower-case proxy wallet, or ``""``.

    Accepts a bare address, a Polymarket profile URL carrying one, or — when
    a leaderboard loader is given — an exact public handle (``swisstony``,
    ``@swisstony``) found in the top PnL/volume slices. Handles that are not
    on those slices resolve to nothing; the page then asks for the address.
    """
    raw = str(text or "").strip()
    if not raw:
        return ""
    found = _ADDRESS_RE.search(raw)
    if found:
        return found.group(0).lower()
    if leaderboard_loader is None:
        return ""
    for order_by in ("PNL", "VOL"):
        try:
            profiles = leaderboard_loader(250, "ALL", order_by)
        except Exception:
            continue
        if profiles is None or getattr(profiles, "empty", True):
            continue
        wallet = md.resolve_profile_query_to_wallet(raw, profiles)
        if wallet:
            return str(wallet).lower()
    return ""


# --- follow / pause / resume --------------------------------------------------


def _seed_now(wallet: str, db_path: str | Path, settings: ct.CopySettings | None) -> tuple[dict[str, Any] | None, str | None]:
    """Seed one wallet's baseline; returns (result, error). Network errors are
    reported, not raised: the daemon seeds an unseeded wallet on its first
    pass anyway, the page just cannot promise the cutoff yet."""
    try:
        result = ct.seed_trader_baseline(wallet, settings=settings, db_path=db_path)
    except Exception as exc:  # noqa: BLE001 - surfaced to the caller as text
        return None, f"{type(exc).__name__}: {exc}"
    return asdict(result), None


def follow(
    wallet: str,
    *,
    label: str = "",
    start_cash: float = ct.PER_TRADER_START_CASH,
    note: str = "",
    db_path: str | Path = ct.DEFAULT_DB_PATH,
    settings: ct.CopySettings | None = None,
    seed: bool = True,
) -> dict[str, Any]:
    """Open (or resume) a sub-account and lay down its baseline now.

    Seeding at follow time is what makes the first daemon pass honest: the
    wallet's open positions are mirrored and its recent trades recorded as
    observed, so only what it does from this moment on is copied.
    """
    wallet = str(wallet or "").strip().lower()
    if not md.is_polymarket_wallet(wallet):
        raise ValueError("a Polymarket proxy wallet is required (0x + 40 hex characters)")
    cash = float(start_cash)
    if not cash > 0:
        raise ValueError("start cash must be positive")
    added = ct.follow_trader(wallet, label=str(label or "").strip(), start_cash=cash, note=str(note or "").strip(), db_path=db_path)
    seed_result = seed_error = None
    if seed:
        seed_result, seed_error = _seed_now(wallet, db_path, settings)
    return {
        "wallet": wallet,
        "added": bool(added),
        "resumed": not bool(added),
        "seeded": seed_result is not None,
        "seed": seed_result,
        "seed_error": seed_error,
    }


def set_trader(
    wallet: str,
    *,
    active: bool | None = None,
    label: str | None = None,
    note: str | None = None,
    db_path: str | Path = ct.DEFAULT_DB_PATH,
    settings: ct.CopySettings | None = None,
    seed_on_resume: bool = True,
) -> dict[str, Any]:
    """Pause/resume or relabel a followed trader.

    Resuming re-seeds the baseline: the trades the source made while paused
    are recorded as observed instead of being copied at stale prints on the
    next pass. Pausing keeps everything (positions keep marking to market).
    """
    wallet = str(wallet or "").strip().lower()
    was_active = None
    traders = ct.get_traders(db_path=db_path)
    if traders is not None and not traders.empty and "wallet" in traders:
        rows = traders[traders["wallet"].astype(str).str.lower().eq(wallet)]
        if not rows.empty:
            was_active = int(rows.iloc[0].get("active", 0) or 0) == 1
    if was_active is None:
        raise KeyError(f"{wallet} is not a followed trader")
    ct.update_trader(wallet, active=active, label=label, note=note, db_path=db_path)
    seed_result = seed_error = None
    resumed = active is True and was_active is False
    if resumed and seed_on_resume:
        seed_result, seed_error = _seed_now(wallet, db_path, settings)
    return {
        "wallet": wallet,
        "active": was_active if active is None else bool(active),
        "resumed": resumed,
        "seeded": seed_result is not None,
        "seed": seed_result,
        "seed_error": seed_error,
    }


def top_up(wallet: str, amount: float, db_path: str | Path = ct.DEFAULT_DB_PATH, note: str = "web desk") -> dict[str, Any]:
    wallet = str(wallet or "").strip().lower()
    value = float(amount)
    if not value > 0:
        raise ValueError("top-up amount must be positive")
    cash_after = ct.add_paper_cash(value, db_path=db_path, reason="manual_top_up", note=note, wallet=wallet)
    return {"wallet": wallet, "amount": value, "cash_after": cash_after}


# --- settings -----------------------------------------------------------------


def _coerce(value: Any, kind: type) -> Any:
    if kind is bool:
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)
    if kind is int:
        return max(0, int(float(value)))
    return float(value)


def update_settings(patch: Mapping[str, Any], path: str | Path = ct.DEFAULT_SETTINGS_PATH) -> ct.CopySettings:
    """Apply the editable subset of ``patch`` to the saved settings and return
    the result. Unknown keys are ignored (never ``live_trading_enabled``);
    a value that does not parse raises ``ValueError`` naming the field."""
    current = ct.load_copy_settings(path)
    changes: dict[str, Any] = {}
    for key, kind in EDITABLE_SETTINGS.items():
        if key not in patch or patch[key] is None:
            continue
        try:
            value = _coerce(patch[key], kind)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{key}: {patch[key]!r} is not a valid {kind.__name__}") from exc
        if kind is float and value < 0:
            raise ValueError(f"{key} must not be negative")
        if key in FRACTION_SETTINGS and value > 1:
            raise ValueError(f"{key} is a fraction (0..1), got {value}")
        changes[key] = value
    updated = replace(current, **changes) if changes else current
    updated = replace(updated, live_trading_enabled=False)
    ct.save_copy_settings(updated, path)
    return updated


def settings_view(settings: ct.CopySettings) -> dict[str, Any]:
    view = asdict(settings)
    view["editable"] = sorted(EDITABLE_SETTINGS)
    return view


# --- overview -----------------------------------------------------------------


def _iso_age_seconds(value: Any, now: datetime | None = None) -> float | None:
    if not value:
        return None
    try:
        stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return max(0.0, ((now or datetime.now(timezone.utc)) - stamp).total_seconds())


def traders_overview(
    db_path: str | Path = ct.DEFAULT_DB_PATH,
    conn: Any = None,
    curve_points: int = 400,
) -> list[dict[str, Any]]:
    """One row per followed trader with its sub-account read.

    Cash, equity, PnL and the order counts come from that trader's own books
    (``value_sub_account``, ``paper_orders.source_wallet``); ``pnl`` is
    equity minus what was put in, so a top-up never reads as profit.
    """
    owns = conn is None
    conn = ct.connect(db_path) if conn is None else conn
    try:
        traders = ct.get_traders(conn=conn)
        orders = ct.get_paper_orders(conn=conn)
        rows: list[dict[str, Any]] = []
        if traders is None or traders.empty:
            return rows
        order_wallet = orders["source_wallet"].astype(str).str.lower() if orders is not None and not orders.empty and "source_wallet" in orders else None
        for _, trader in traders.iterrows():
            wallet = str(trader.get("wallet", "") or "").strip().lower()
            if not wallet:
                continue
            snap = ct.value_sub_account(wallet, conn=conn)
            contributions = ct.trader_contributions(conn, wallet)
            counts = {"copied": 0, "skipped": 0, "settled": 0, "observed": 0, "total": 0}
            last_copy_at = None
            if order_wallet is not None:
                mine = orders[order_wallet.eq(wallet)]
                if not mine.empty:
                    status = mine["status"].astype(str)
                    counts["copied"] = int(status.eq("copied").sum())
                    counts["skipped"] = int(status.eq("skipped").sum())
                    counts["settled"] = int(status.eq("settled").sum())
                    counts["observed"] = int(status.eq("seed_observed").sum())
                    counts["total"] = int(len(mine))
                    acted = mine[status.isin(["copied", "settled"])]
                    if not acted.empty and "created_at" in acted:
                        last_copy_at = str(acted["created_at"].max())
            curve_frame = ct.get_trader_equity_snapshots(wallet, conn=conn, limit=curve_points)
            curve = [float(v) for v in curve_frame["equity"].tolist()] if not curve_frame.empty else []
            open_positions = int((snap.positions["shares"] > 0).sum()) if not snap.positions.empty and "shares" in snap.positions else 0
            pnl = float(snap.equity) - float(contributions)
            # The source wallet's visible equity as the sizing refresh last saw
            # it (positions value + USDC), and the neutral ratio that follows:
            # sub-account equity / source equity — "his 1 % is your 1 %".
            source_equity = ct._get_wallet_float_stat(conn, wallet, "visible_equity", 0.0)
            neutral_ratio = (float(snap.equity) / source_equity) if source_equity > 0 and snap.equity > 0 else None
            rows.append({
                "wallet": wallet,
                "label": str(trader.get("label", "") or "") or wallet,
                "note": str(trader.get("note", "") or ""),
                "active": int(trader.get("active", 0) or 0) == 1,
                "start_cash": float(trader.get("start_cash", 0.0) or 0.0),
                "cash": float(snap.cash),
                "position_value": float(snap.position_value),
                "equity": float(snap.equity),
                "contributions": float(contributions),
                "pnl": pnl,
                "pnl_pct": (pnl / contributions * 100.0) if contributions else 0.0,
                "realized_pnl": float(snap.realized_pnl),
                "unrealized_pnl": float(snap.unrealized_pnl),
                "orders": counts,
                "open_positions": open_positions,
                "last_copy_at": last_copy_at,
                "added_at": str(trader.get("added_at", "") or ""),
                "seeded_at": ct.wallet_seeded_at(conn, wallet),
                "baseline_cutoff_ts": ct.wallet_baseline_cutoff(conn, wallet) or None,
                "equity_curve": curve,
                "profile_url": md.polymarket_profile_url(wallet),
                "source_equity": source_equity if source_equity > 0 else None,
                "neutral_ratio": neutral_ratio,
            })
        return rows
    finally:
        if owns:
            conn.close()


# --- daemon -------------------------------------------------------------------


def daemon_status(status_path: str | Path = ct.DEFAULT_STATUS_PATH, now: datetime | None = None, stale_after_s: float = DAEMON_STALE_AFTER_S) -> dict[str, Any]:
    """What ``scripts/run_copy_trader.py`` last wrote, judged for freshness.

    ``running`` is True only when the file says so *and* it was written
    recently — a daemon that died mid-loop leaves ``running: true`` behind
    forever, and the page must not repeat that. None means no status file at
    all (the daemon has never run against this checkout).
    """
    path = Path(status_path)
    if not path.exists():
        return {"running": None, "reason": f"no status file at {path.as_posix()} — the daemon has not run here yet", "file": path.as_posix()}
    payload: Any = None
    last_exc: Exception | None = None
    # The daemon replaces the file atomically once a second; on Windows a
    # read can land between its write and its rename. One short retry.
    for attempt in range(3):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            break
        except (OSError, ValueError) as exc:
            last_exc = exc
            time.sleep(0.05 * (attempt + 1))
    if payload is None and last_exc is not None:
        return {"running": None, "reason": f"status file unreadable: {last_exc}", "file": path.as_posix()}
    if not isinstance(payload, Mapping):
        return {"running": None, "reason": "status file has no object", "file": path.as_posix()}
    heartbeat = payload.get("last_sync_at") or payload.get("started_at")
    age = _iso_age_seconds(heartbeat, now)
    claims_running = bool(payload.get("running"))
    stale = age is None or age > float(stale_after_s)
    running = claims_running and not stale
    if not claims_running:
        reason = f"stopped ({payload.get('stop_reason') or 'daemon reported running=false'})"
    elif stale:
        reason = f"status file is {int(age) if age is not None else '?'} s old — the daemon claims to run but has not written since; treat as stopped"
    else:
        reason = "heartbeat fresh"
    return {
        "running": running,
        "claims_running": claims_running,
        "stale": stale,
        "age_seconds": age,
        "reason": reason,
        "file": path.as_posix(),
        "pid": payload.get("pid"),
        "mode": payload.get("mode"),
        "ws_connected": payload.get("ws_connected"),
        "trader_wallets": payload.get("trader_wallets"),
        "started_at": payload.get("started_at"),
        "last_sync_at": payload.get("last_sync_at"),
        "last_ws_sync_at": payload.get("last_ws_sync_at"),
        "last_api_sync_at": payload.get("last_api_sync_at"),
        "last_settlement_sync_at": payload.get("last_settlement_sync_at"),
        "last_error": payload.get("last_error"),
        "clock_offset_seconds": payload.get("clock_offset_seconds"),
    }


# --- one-shot sync ------------------------------------------------------------

_SYNC_LOCK = threading.Lock()
_SYNC_STATE: dict[str, Any] = {"running": False, "started_at": None, "finished_at": None, "result": None, "error": None}


def _summarise(results: Mapping[str, ct.SyncResult]) -> dict[str, Any]:
    combined = ct.aggregate_sync_results(results)
    return {
        "wallets": len(results),
        "processed": combined.processed,
        "copied": combined.copied,
        "skipped": combined.skipped,
        "duplicates": combined.duplicates,
        "seeded": combined.seeded,
        "errors": list(combined.errors),
        "per_wallet": {w: asdict(r) for w, r in results.items()},
    }


def run_sync_pass(db_path: str | Path = ct.DEFAULT_DB_PATH, settings: ct.CopySettings | None = None) -> dict[str, Any]:
    """One API + settlement pass over every active trader, then a snapshot.

    This is what the daemon does every 30 s / 90 s; the page offers it so a
    fresh follow can be checked without waiting, and so the desk works at all
    when the daemon is not running (slower, but the same books).
    """
    settings = settings or ct.load_copy_settings()
    api = ct.sync_active_copy_trades(settings=settings, db_path=db_path)
    settle = ct.sync_active_settlement_activity(settings=settings, db_path=db_path, limit=500, pages=1, closed_pages=2, metadata_pages=2)
    try:
        snapshot = ct.value_paper_portfolio(db_path=db_path)
        ct.record_equity_snapshot(db_path=db_path, snapshot=snapshot, min_interval_seconds=0.0)
        ct.record_trader_equity_snapshots(db_path=db_path, min_interval_seconds=0.0)
    except Exception:  # noqa: BLE001 - snapshots are best effort
        pass
    return {"api": _summarise(api), "settlement": _summarise(settle)}


def start_sync(
    db_path: str | Path = ct.DEFAULT_DB_PATH,
    settings: ct.CopySettings | None = None,
    runner: Callable[[], dict[str, Any]] | None = None,
    in_thread: bool = True,
) -> dict[str, Any]:
    """Kick off one sync pass unless one is already running (single flight).

    Returns ``{"started": True}`` or ``{"started": False, "busy": True}``;
    the outcome lands in :func:`sync_state` when the pass finishes.
    """
    if not _SYNC_LOCK.acquire(blocking=False):
        return {"started": False, "busy": True, "state": sync_state()}
    _SYNC_STATE.update({"running": True, "started_at": ct.utc_now(), "finished_at": None, "result": None, "error": None})

    def _work() -> None:
        try:
            result = runner() if runner is not None else run_sync_pass(db_path=db_path, settings=settings)
            _SYNC_STATE.update({"result": result, "error": None})
        except Exception as exc:  # noqa: BLE001 - reported through sync_state
            _SYNC_STATE.update({"result": None, "error": f"{type(exc).__name__}: {exc}"})
        finally:
            _SYNC_STATE.update({"running": False, "finished_at": ct.utc_now()})
            _SYNC_LOCK.release()

    if in_thread:
        threading.Thread(target=_work, name="copy-desk-sync", daemon=True).start()
    else:
        _work()
    return {"started": True, "state": sync_state()}


def sync_state() -> dict[str, Any]:
    return dict(_SYNC_STATE)


# --- a fresh desk -------------------------------------------------------------


def ensure_desk(db_path: str | Path = ct.DEFAULT_DB_PATH) -> bool:
    """Create the books if they do not exist yet; a fresh desk copies nobody.

    ``init_db`` seeds the legacy Swisstony wallet as the first trader (the
    migration rule for databases that already followed it). On a desk that
    never had books that would mean copying a wallet nobody asked for the
    moment the daemon starts — so the seed row is created **paused**, with a
    note saying why. Returns True when the database was created here.
    """
    path = Path(db_path)
    if path.exists():
        return False
    conn = ct.connect(path)
    try:
        ct.update_trader(
            ct.COPY_TARGET_WALLET,
            active=False,
            note="seed row from the migration — paused; resume only if you mean to copy this wallet",
            conn=conn,
        )
    finally:
        conn.close()
    return True


# --- the whole desk in one read -----------------------------------------------


def desk_state(
    db_path: str | Path = ct.DEFAULT_DB_PATH,
    settings_path: str | Path = ct.DEFAULT_SETTINGS_PATH,
    status_path: str | Path = ct.DEFAULT_STATUS_PATH,
) -> dict[str, Any]:
    traders = traders_overview(db_path=db_path)
    active = [t for t in traders if t["active"]]
    return {
        "traders": traders,
        "active_count": len(active),
        "settings": settings_view(ct.load_copy_settings(settings_path)),
        "daemon": daemon_status(status_path),
        "sync": sync_state(),
        "totals": {
            "equity": sum(t["equity"] for t in traders),
            "contributions": sum(t["contributions"] for t in traders),
            "cash": sum(t["cash"] for t in traders),
        },
    }
