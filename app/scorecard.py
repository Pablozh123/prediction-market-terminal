"""Canonical wallet scorecard: one wallet, one timestamped read (Streamlit-free).

Consistency principle
---------------------
A wallet has exactly one scorecard at a point in time. Every surface that
shows a wallet number consumes ``wallet_scorecard`` and names its snapshot
timestamp. New features (report card, OG cards, digests, API) build
exclusively on this function; no surface calls the four underlying systems
directly anymore. The four reads keep their own names and math — this module
deliberately does NOT combine them into one composite super-number.

The four systems (math unchanged, only orchestrated here):

- track record          -> ``app.track_record.track_record``
- entry calibration     -> ``app.calibration.calibration_report``
- realized edge verdict -> ``app.calibration.realized_edge``
- smart score / insider -> leaderboard smart-score row / whale-tape screen

All parts that read resolved positions are fed from ONE fetch, so no two
parts of a card can disagree about the data state. Sample quality is decided
here, once, from ``calib.MIN_SAMPLE`` and ``calib.MIN_VERDICT_EVENTS`` over
the netted event count (independent observations; per-leg counts would
inflate the sample) — UI code never compares against those constants itself.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable, Mapping

import pandas as pd

from app import calibration as calib
from app import track_record as trec

DEFAULT_TTL_SECONDS = 15 * 60.0

_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_CACHE_LOCK = threading.Lock()


def clear_cache() -> None:
    with _CACHE_LOCK:
        _CACHE.clear()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sample_quality(n_resolved: int) -> dict[str, Any]:
    """The one place the sample thresholds are evaluated.

    Below ``calib.MIN_SAMPLE`` resolved events the read is ``insufficient``;
    below ``calib.MIN_VERDICT_EVENTS`` it is ``developing``; from there on
    ``adequate``. Verdict language is allowed only on adequate samples.
    """

    n = max(0, int(n_resolved))
    if n < calib.MIN_SAMPLE:
        quality = "insufficient"
    elif n < calib.MIN_VERDICT_EVENTS:
        quality = "developing"
    else:
        quality = "adequate"
    return {"n_resolved": n, "quality": quality, "verdict_allowed": quality == "adequate"}


def _default_resolved_fetcher(wallet: str) -> tuple[pd.DataFrame, bool]:
    from src import prediction_markets as md

    return md.get_polymarket_resolved_positions(wallet)


def _default_smart_row_fetcher(wallet: str) -> Mapping[str, Any] | None:
    from src import copy_trading as ct
    from src import prediction_markets as md

    leaderboard = md.get_polymarket_leaderboard(limit=250, time_period="ALL", order_by="PNL")
    ranked = ct.rank_traders_by_smart_score(leaderboard)
    if ranked is None or ranked.empty or "wallet" not in ranked:
        return None
    match = ranked[ranked["wallet"].astype(str).str.lower() == wallet.lower()]
    if match.empty:
        return None
    return match.iloc[0].to_dict()


def _default_risk_row_fetcher(wallet: str) -> Mapping[str, Any] | None:
    from src import prediction_markets as md

    tape = md.get_polymarket_trades(limit=1000)
    scores = md.whale_wallet_risk_scores(tape)
    if scores is None or scores.empty or "wallet" not in scores:
        return None
    match = scores[scores["wallet"].astype(str).str.lower() == wallet.lower()]
    if match.empty:
        return None
    return match.iloc[0].to_dict()


def _smart_block(row: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    score = row.get("copy_smart_score")
    if score is None or (isinstance(score, float) and score != score):
        return None
    return {"copy_smart_score": float(score), "copy_grade": str(row.get("copy_grade", "") or "")}


def _risk_block(row: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    score = row.get("wallet_insider_score", row.get("wallet_risk_score"))
    if score is None or (isinstance(score, float) and score != score):
        return None
    flags = row.get("flags", row.get("wallet_flags", []))
    if isinstance(flags, str):
        flags = [flags] if flags.strip() else []
    return {
        "wallet_insider_score": float(score),
        "risk_level": str(row.get("wallet_insider_level", row.get("wallet_risk_level", "")) or ""),
        "flags": list(flags or []),
    }


def wallet_scorecard(
    wallet: str,
    *,
    fetchers: Mapping[str, Callable[..., Any]] | None = None,
    ttl_seconds: float = DEFAULT_TTL_SECONDS,
    refresh: bool = False,
) -> dict[str, Any]:
    """Build (or serve from the TTL cache) the canonical scorecard for one wallet.

    ``fetchers`` keys (all optional; defaults hit the public APIs directly):

    - ``resolved``:  wallet -> (resolved_positions_frame, capped: bool)
    - ``trades``:    wallet -> trades frame or None (track-record cross-check)
    - ``activity``:  wallet -> activity frame or None (track-record cross-check)
    - ``smart_row``: wallet -> leaderboard smart-score row (mapping) or None
    - ``risk_row``:  wallet -> whale-tape insider row (mapping) or None

    Partial failures never raise: a failing subsystem leaves its part ``None``
    (or an empty-shaped report for the resolved-based parts) and records the
    message under ``errors[<part>]``. Treat the returned dict as read-only.
    """

    wallet = str(wallet or "").strip()
    cache_key = wallet.lower()
    if not refresh and ttl_seconds > 0:
        with _CACHE_LOCK:
            hit = _CACHE.get(cache_key)
            if hit is not None and (time.monotonic() - hit[0]) < ttl_seconds:
                return hit[1]

    fetchers = dict(fetchers or {})
    fetch_resolved = fetchers.get("resolved", _default_resolved_fetcher)
    fetch_trades = fetchers.get("trades")
    fetch_activity = fetchers.get("activity")
    fetch_smart = fetchers.get("smart_row", _default_smart_row_fetcher)
    fetch_risk = fetchers.get("risk_row", _default_risk_row_fetcher)

    snapshot_at = _utc_now_iso()
    errors: dict[str, str] = {}

    resolved = pd.DataFrame()
    capped = False
    try:
        resolved, capped = fetch_resolved(wallet)
        if resolved is None:
            resolved = pd.DataFrame()
    except Exception as exc:  # noqa: BLE001 - partial failure beats a dead page
        errors["resolved"] = str(exc)
        resolved = pd.DataFrame()

    trades = None
    if fetch_trades is not None:
        try:
            trades = fetch_trades(wallet)
        except Exception as exc:  # noqa: BLE001
            errors["trades"] = str(exc)
    activity = None
    if fetch_activity is not None:
        try:
            activity = fetch_activity(wallet)
        except Exception as exc:  # noqa: BLE001
            errors["activity"] = str(exc)

    track: dict[str, Any] | None = None
    try:
        track = trec.track_record(resolved, trades, activity, resolved_capped=bool(capped))
    except Exception as exc:  # noqa: BLE001
        errors["track"] = str(exc)

    attribution: dict[str, Any] | None = None
    try:
        attribution = trec.pnl_attribution(resolved)
    except Exception as exc:  # noqa: BLE001
        errors["attribution"] = str(exc)

    calibration: dict[str, Any] | None = None
    realized: dict[str, Any] | None = None
    try:
        frame = calib.resolution_frame(resolved)
        calibration = calib.calibration_report(frame, capped=bool(capped))
        realized = calib.realized_edge(frame, capped=bool(capped))
    except Exception as exc:  # noqa: BLE001
        errors["calibration"] = str(exc)

    smart: dict[str, Any] | None = None
    try:
        smart = _smart_block(fetch_smart(wallet))
    except Exception as exc:  # noqa: BLE001
        errors["smart"] = str(exc)

    risk: dict[str, Any] | None = None
    try:
        risk = _risk_block(fetch_risk(wallet))
    except Exception as exc:  # noqa: BLE001
        errors["risk"] = str(exc)

    card: dict[str, Any] = {
        "wallet": wallet,
        "snapshot_at": snapshot_at,
        "data_window": {
            "trades": int(len(resolved)),
            "source": "polymarket_closed_positions",
        },
        "track": track,
        "calibration": calibration,
        "realized_edge": realized,
        "attribution": attribution,
        "smart": smart,
        "risk": risk,
        "sample": sample_quality(int(realized["n_events"]) if realized else 0),
        "errors": errors,
    }
    if ttl_seconds > 0:
        with _CACHE_LOCK:
            _CACHE[cache_key] = (time.monotonic(), card)
    return card
