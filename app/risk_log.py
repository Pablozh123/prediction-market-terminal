"""Flag log of the risk screen: every flagged event, persisted for later review.

The risk screen says "this looks like someone knew" and forgets it five
minutes later. The owner wants to come back afterwards — after the inflation
print, after the vote — and check whether the flagged side was right. So
each flagged event is appended here with the side, the price at that moment,
the wallets and the score components, and can be read back newest first.

Storage: one JSON object per line in ``<RISK_LOG_DIR>/flags.jsonl``; the
directory comes from the env var ``RISK_LOG_DIR`` (default ``data/risk_flags``
under the repository root). Stdlib + pandas only, no database.

Dedupe: a flag is identified by venue + market + dominant side + UTC day.
When the same flag id was logged within the last ``DEDUPE_HOURS`` the existing
row is updated (``last_seen``, ``times_seen``, the higher score) instead of a
duplicate line — the sampler runs every few minutes and would otherwise write
the same event twelve times an hour.

Deployment note: on Railway the container filesystem is ephemeral — the log
survives a redeploy only when a volume is mounted at ``/app/data`` (or
``RISK_LOG_DIR`` points into one). Without write access the log is skipped
with a printed warning; the request that produced the flags never fails
because of the log.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIR = "data/risk_flags"
FILE_NAME = "flags.jsonl"
DEDUPE_HOURS = 6.0
#: Below this score the screen calls a row "Low"; those are watch rows, not
#: flags, and would only bury the log. Env ``RISK_LOG_MIN_SCORE`` overrides.
DEFAULT_MIN_SCORE = 40.0
#: Hard cap on rows kept in the file (oldest dropped on rewrite).
MAX_ROWS = 20_000

_LOCK = threading.Lock()


def log_dir() -> Path:
    raw = os.environ.get("RISK_LOG_DIR", "").strip()
    path = Path(raw) if raw else Path(DEFAULT_DIR)
    return path if path.is_absolute() else ROOT / path


def log_path() -> Path:
    return log_dir() / FILE_NAME


def min_score() -> float:
    try:
        return float(os.environ.get("RISK_LOG_MIN_SCORE", "").strip() or DEFAULT_MIN_SCORE)
    except ValueError:
        return DEFAULT_MIN_SCORE


def _utc(value: Any = None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc).replace(microsecond=0)
    stamp = pd.to_datetime(value, utc=True, errors="coerce")
    if stamp is None or pd.isna(stamp):
        return datetime.now(timezone.utc).replace(microsecond=0)
    return stamp.to_pydatetime().replace(microsecond=0)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _num(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(out) or math.isinf(out):
        return None
    return out


def flag_id(venue: Any, market_key: Any, side: Any, day: Any) -> str:
    """Stable id of a flag: venue + market + dominant side + UTC day."""

    raw = "|".join(str(part or "").strip().lower() for part in (venue, market_key, side, day))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def flag_row(event: dict[str, Any], as_of: Any = None) -> dict[str, Any]:
    """Build the log row of one event as ``api_views.risk_event_row`` shapes it."""

    seen = _utc(as_of)
    venue = str(event.get("venue") or "")
    market_key = str(event.get("market_key") or "") or str(event.get("market") or "")
    side = str(event.get("side") or "")
    when = _iso(seen)
    return {
        "flag_id": flag_id(venue, market_key, side, seen.strftime("%Y-%m-%d")),
        "first_seen": when,
        "last_seen": when,
        "times_seen": 1,
        "venue": venue,
        "market_key": str(event.get("market_key") or ""),
        "title": str(event.get("market") or ""),
        "url": str(event.get("url") or ""),
        "category": str(event.get("category") or ""),
        "kind": str(event.get("kind") or ""),
        "flags": list(event.get("flags") or []),
        "side": side,
        "side_share": _num(event.get("side_share")),
        "side_notional": _num(event.get("side_notional")),
        "side_split": dict(event.get("side_split") or {}),
        "price_outcome": str(event.get("price_outcome") or ""),
        "price_at_flag": _num(event.get("price_last")),
        "price_min": _num(event.get("price_min")),
        "price_max": _num(event.get("price_max")),
        "notional": _num(event.get("notional_usd")),
        "unique_wallets": int(_num(event.get("wallets")) or 0),
        "prints": int(_num(event.get("prints")) or 0),
        "top_wallets": list(event.get("top_wallets") or []),
        # The first-trade reading at flag time (app/wallet_origin.py): how
        # many measured wallets were fresh, their money, the youngest first
        # trade in days, and how many wallets were measured at all.
        "first_trade_wallets": int(_num(event.get("first_trade_wallets")) or 0),
        "first_trade_notional": _num(event.get("first_trade_notional")),
        "first_trade_youngest_days": _num(event.get("first_trade_youngest_days")),
        "first_trade_measured": int(_num(event.get("first_trade_measured")) or 0),
        "score": _num(event.get("score")),
        "sev": str(event.get("sev") or ""),
        "components": list(event.get("components") or []),
        "window_start": str(event.get("first_print") or ""),
        "window_end": str(event.get("last_print") or ""),
        "window_minutes": _num(event.get("window_minutes")),
        "token_id": str(event.get("token_id") or ""),
    }


def _read_all(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                rows.append(row)
    return rows


def _write_all(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    os.replace(tmp, path)


#: What the stronger reading of a repeated flag overwrites. Identity fields
#: (flag_id, first_seen, venue, market, title) never move.
EVENT_UPDATE_KEYS = (
    "score", "sev", "kind", "flags", "components", "side", "side_share", "side_notional",
    "side_split", "price_outcome", "price_at_flag", "price_min", "price_max", "notional",
    "unique_wallets", "prints", "top_wallets", "window_start", "window_end",
    "window_minutes", "url", "token_id", "category",
    "first_trade_wallets", "first_trade_notional", "first_trade_youngest_days", "first_trade_measured",
)


def record_flags(
    events: Iterable[dict[str, Any]],
    as_of: Any = None,
    *,
    path: Path | str | None = None,
    min_score_value: float | None = None,
    dedupe_hours: float = DEDUPE_HOURS,
) -> dict[str, Any]:
    """Append the flagged events (score >= min score) to the log; dedupe within ``dedupe_hours``.

    Returns ``{"written": n_new, "updated": n_updated, "skipped": n_below, "path": str, "error": str | None}``.
    Never raises for I/O problems: a read-only or missing directory yields
    ``error`` and a printed warning.
    """

    target = Path(path) if path is not None else log_path()
    threshold = float(min_score_value) if min_score_value is not None else min_score()
    seen = _utc(as_of)
    incoming = [event for event in (events or []) if isinstance(event, dict)]
    candidates = [flag_row(event, seen) for event in incoming if (_num(event.get("score")) or 0.0) >= threshold]
    result: dict[str, Any] = {
        "written": 0, "updated": 0, "skipped": len(incoming) - len(candidates), "path": str(target), "error": None,
    }
    if not candidates:
        return result
    horizon = seen - timedelta(hours=float(dedupe_hours))
    with _LOCK:
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            rows = _read_all(target)
            by_id: dict[str, int] = {}
            for index, row in enumerate(rows):
                last = pd.to_datetime(row.get("last_seen"), utc=True, errors="coerce")
                if pd.isna(last):
                    continue
                if last.to_pydatetime() >= horizon:
                    by_id[str(row.get("flag_id"))] = index
            changed = False
            for candidate in candidates:
                index = by_id.get(candidate["flag_id"])
                if index is None:
                    rows.append(candidate)
                    by_id[candidate["flag_id"]] = len(rows) - 1
                    result["written"] += 1
                    changed = True
                    continue
                existing = rows[index]
                existing["last_seen"] = candidate["last_seen"]
                existing["times_seen"] = int(existing.get("times_seen") or 1) + 1
                old_score = _num(existing.get("score")) or 0.0
                new_score = _num(candidate.get("score")) or 0.0
                if new_score > old_score:
                    # The stronger reading wins, with the side/price/wallets
                    # of that reading — those are what a review needs.
                    for key in EVENT_UPDATE_KEYS:
                        existing[key] = candidate[key]
                result["updated"] += 1
                changed = True
            if changed:
                if len(rows) > MAX_ROWS:
                    rows = rows[-MAX_ROWS:]
                _write_all(target, rows)
        except OSError as exc:
            result["error"] = f"{type(exc).__name__}: {exc}"
            print(f"[warn] risk flag log not writable ({target}): {exc}")
    return result


# ---------------------------------------------------------------------------
# Wallet flags. The event log answers "which market looked wrong"; a wallet
# that clears the screen on its own (one fresh wallet, one big print) used to
# leave no trace unless its market did too. Every wallet row the screen
# hands out at or above the flag floor lands here, one line per venue,
# wallet and UTC day, with the measured first trade, the flags and the
# market it was mostly in, so the review afterwards can start from the who.
# ---------------------------------------------------------------------------

WALLET_FILE_NAME = "wallets.jsonl"

#: What a repeated wallet flag's stronger reading overwrites.
WALLET_UPDATE_KEYS = (
    "score", "sev", "band", "flags", "category", "top_market", "prints", "notional", "largest",
    "first_trade_days", "first_trade_state", "first_print", "latest_print",
)


def wallet_log_path() -> Path:
    return log_dir() / WALLET_FILE_NAME


def wallet_flag_id(venue: Any, wallet: Any, day: Any) -> str:
    """Stable id of a wallet flag: venue + wallet + UTC day."""

    raw = "|".join(str(part or "").strip().lower() for part in (venue, wallet, day))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def wallet_flag_row(wallet: dict[str, Any], as_of: Any = None) -> dict[str, Any]:
    """The log row of one wallet as ``api_views.risk_payload`` shapes it."""

    seen = _utc(as_of)
    venue = str(wallet.get("venue") or "Polymarket")
    address = str(wallet.get("address") or wallet.get("wallet") or "")
    when = _iso(seen)
    band = wallet.get("band")
    band_label = str(band.get("label") or "") if isinstance(band, dict) else str(band or "")
    score = _num(wallet.get("score"))
    return {
        "flag_id": wallet_flag_id(venue, address, seen.strftime("%Y-%m-%d")),
        "first_seen": when,
        "last_seen": when,
        "times_seen": 1,
        "venue": venue,
        "wallet": address,
        "name": str(wallet.get("wallet") or ""),
        "score": score,
        "sev": "high" if (score or 0.0) >= 70 else "medium" if (score or 0.0) >= 55 else "low",
        "band": band_label,
        "flags": list(wallet.get("flags") or []),
        "category": str(wallet.get("category") or ""),
        "top_market": str(wallet.get("context") or ""),
        "prints": int(_num(wallet.get("prints")) or 0),
        "notional": _num(wallet.get("notional_usd")),
        "largest": _num(wallet.get("largest_usd")),
        "first_trade_days": _num(wallet.get("first_trade_days")),
        "first_trade_state": str(wallet.get("first_trade_state") or ""),
        "first_print": str(wallet.get("firstSeen") or ""),
        "latest_print": str(wallet.get("latest_print") or ""),
    }


def record_wallet_flags(
    wallets: Iterable[dict[str, Any]],
    as_of: Any = None,
    *,
    path: Path | str | None = None,
    min_score_value: float | None = None,
    dedupe_hours: float = DEDUPE_HOURS,
) -> dict[str, Any]:
    """Append the wallet rows at or above the flag floor to the wallet log.

    Same contract as :func:`record_flags`: dedupe by id within
    ``dedupe_hours`` (the stronger reading wins), never raises for I/O.
    """

    target = Path(path) if path is not None else wallet_log_path()
    threshold = float(min_score_value) if min_score_value is not None else min_score()
    seen = _utc(as_of)
    incoming = [row for row in (wallets or []) if isinstance(row, dict)]
    candidates = [
        wallet_flag_row(row, seen) for row in incoming
        if (_num(row.get("score")) or 0.0) >= threshold and str(row.get("address") or row.get("wallet") or "").strip()
    ]
    return _upsert_rows(target, candidates, seen, dedupe_hours, WALLET_UPDATE_KEYS, len(incoming) - len(candidates))


def read_wallet_flags(limit: int = 200, since: Any = None, *, path: Path | str | None = None) -> list[dict[str, Any]]:
    """Wallet log rows newest first, like :func:`read_flags`."""

    return read_flags(limit=limit, since=since, path=Path(path) if path is not None else wallet_log_path())


def _upsert_rows(
    target: Path,
    candidates: list[dict[str, Any]],
    seen: datetime,
    dedupe_hours: float,
    update_keys: tuple[str, ...],
    skipped: int,
    strength_key: str = "score",
) -> dict[str, Any]:
    """Append or update rows by ``flag_id`` within the dedupe window; the
    reading with the higher ``strength_key`` overwrites ``update_keys``."""

    result: dict[str, Any] = {"written": 0, "updated": 0, "skipped": skipped, "path": str(target), "error": None}
    if not candidates:
        return result
    horizon = seen - timedelta(hours=float(dedupe_hours))
    with _LOCK:
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            rows = _read_all(target)
            by_id: dict[str, int] = {}
            for index, row in enumerate(rows):
                last = pd.to_datetime(row.get("last_seen"), utc=True, errors="coerce")
                if pd.isna(last):
                    continue
                if last.to_pydatetime() >= horizon:
                    by_id[str(row.get("flag_id"))] = index
            changed = False
            for candidate in candidates:
                index = by_id.get(candidate["flag_id"])
                if index is None:
                    rows.append(candidate)
                    by_id[candidate["flag_id"]] = len(rows) - 1
                    result["written"] += 1
                    changed = True
                    continue
                existing = rows[index]
                existing["last_seen"] = candidate["last_seen"]
                existing["times_seen"] = int(existing.get("times_seen") or 1) + 1
                if (_num(candidate.get(strength_key)) or 0.0) > (_num(existing.get(strength_key)) or 0.0):
                    for key in update_keys:
                        if key in candidate:
                            existing[key] = candidate[key]
                result["updated"] += 1
                changed = True
            if changed:
                if len(rows) > MAX_ROWS:
                    rows = rows[-MAX_ROWS:]
                _write_all(target, rows)
        except OSError as exc:
            result["error"] = f"{type(exc).__name__}: {exc}"
            print(f"[warn] risk flag log not writable ({target}): {exc}")
    return result


# ---------------------------------------------------------------------------
# Size outliers (app/outliers.py). No score: a wallet whose money in the
# window reached the rule's multiple of its market's own yardstick. One line
# per venue, market, wallet and UTC day, the reading with the higher ratio
# winning a repeat, so the review can ask afterwards whether the wallet was
# alone above the baseline and what the market did next.
# ---------------------------------------------------------------------------

OUTLIER_FILE_NAME = "outliers.jsonl"

OUTLIER_UPDATE_KEYS = (
    "total", "largest", "prints", "ratio", "yardstick", "baseline_n", "baseline_hours", "baseline_max",
    "elevated_wallets", "wallets_in_window", "verdict", "verdict_text", "side", "price", "share",
    "window_minutes", "window_volume_ratio", "first_print", "last_print",
    "first_trade_days", "first_trade_state", "url", "category", "name",
)


def outlier_log_path() -> Path:
    return log_dir() / OUTLIER_FILE_NAME


def outlier_flag_id(venue: Any, market_key: Any, wallet: Any, day: Any) -> str:
    """Stable id of an outlier flag: venue + market + wallet + UTC day."""

    raw = "|".join(str(part or "").strip().lower() for part in (venue, market_key, wallet, day))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def outlier_flag_row(row: dict[str, Any], as_of: Any = None) -> dict[str, Any]:
    """The log row of one outlier as ``outliers.size_outliers`` shapes it."""

    seen = _utc(as_of)
    venue = str(row.get("venue") or "Polymarket")
    market_key = str(row.get("market_key") or "")
    wallet = str(row.get("wallet") or "")
    when = _iso(seen)
    return {
        "flag_id": outlier_flag_id(venue, market_key, wallet, seen.strftime("%Y-%m-%d")),
        "first_seen": when,
        "last_seen": when,
        "times_seen": 1,
        "venue": venue,
        "market_key": market_key,
        "title": str(row.get("title") or ""),
        "url": str(row.get("url") or ""),
        "category": str(row.get("category") or ""),
        "wallet": wallet,
        "name": str(row.get("name") or ""),
        "total": _num(row.get("total")),
        "largest": _num(row.get("largest")),
        "prints": int(_num(row.get("prints")) or 0),
        "ratio": _num(row.get("ratio")),
        "yardstick": _num(row.get("yardstick")),
        "baseline_n": int(_num(row.get("baseline_n")) or 0),
        "baseline_hours": _num(row.get("baseline_hours")),
        "baseline_max": _num(row.get("baseline_max")),
        "elevated_wallets": int(_num(row.get("elevated_wallets")) or 0),
        "wallets_in_window": int(_num(row.get("wallets_in_window")) or 0),
        "verdict": str(row.get("verdict") or ""),
        "verdict_text": str(row.get("verdict_text") or ""),
        "side": str(row.get("side") or ""),
        "price": _num(row.get("price")),
        "share": _num(row.get("share")),
        "window_minutes": _num(row.get("window_minutes")),
        "window_volume_ratio": _num(row.get("window_volume_ratio")),
        "first_print": str(row.get("first_print") or ""),
        "last_print": str(row.get("last_print") or ""),
        "first_trade_days": _num(row.get("first_trade_days")),
        "first_trade_state": str(row.get("first_trade_state") or ""),
    }


def record_outlier_flags(
    rows: Iterable[dict[str, Any]],
    as_of: Any = None,
    *,
    path: Path | str | None = None,
    dedupe_hours: float = DEDUPE_HOURS,
) -> dict[str, Any]:
    """Append the outlier rows to the outlier log; every row is a flag
    already, so there is no floor. Same dedupe and I/O contract as
    :func:`record_flags`."""

    target = Path(path) if path is not None else outlier_log_path()
    seen = _utc(as_of)
    incoming = [row for row in (rows or []) if isinstance(row, dict)]
    candidates = [
        outlier_flag_row(row, seen) for row in incoming
        if str(row.get("wallet") or "").strip() and str(row.get("market_key") or "").strip()
    ]
    return _upsert_rows(target, candidates, seen, dedupe_hours, OUTLIER_UPDATE_KEYS,
                        len(incoming) - len(candidates), strength_key="ratio")


def read_outlier_flags(limit: int = 200, since: Any = None, *, path: Path | str | None = None) -> list[dict[str, Any]]:
    """Outlier log rows newest first, like :func:`read_flags`."""

    return read_flags(limit=limit, since=since, path=Path(path) if path is not None else outlier_log_path())


def read_flags(limit: int = 200, since: Any = None, *, path: Path | str | None = None) -> list[dict[str, Any]]:
    """Log rows newest first (by ``last_seen``), optionally only those seen since ``since``."""

    target = Path(path) if path is not None else log_path()
    with _LOCK:
        try:
            rows = _read_all(target)
        except OSError as exc:
            print(f"[warn] risk flag log not readable ({target}): {exc}")
            return []
    if since is not None:
        floor = pd.to_datetime(since, utc=True, errors="coerce")
        if not pd.isna(floor):
            rows = [row for row in rows if not pd.isna(pd.to_datetime(row.get("last_seen"), utc=True, errors="coerce"))
                    and pd.to_datetime(row.get("last_seen"), utc=True) >= floor]
    rows.sort(key=lambda row: str(row.get("last_seen") or ""), reverse=True)
    if limit is not None and int(limit) >= 0:
        rows = rows[: int(limit)]
    return rows


#: What the compact view keeps of every score component: the chip on the log
#: tab prints label, value and max (web/js/pages/trader_pages.js,
#: riskComponentsHtml). The prose columns -- measures, fact, rule, weight_note
#: -- were two thirds of a log row's bytes, and only the event cards of
#: /api/risk render them (riskScoreBreakdown); the log tab never does.
COMPACT_COMPONENT_KEYS = ("key", "label", "value", "max")
#: Row fields the log tab never reads: side_split feeds the flow bar of the
#: event cards, flags their "Why?" line. The log card shows neither.
COMPACT_DROP_FIELDS = ("side_split", "flags")
#: How many top wallets a compact row carries at most (the largest by notional).
COMPACT_MAX_WALLETS = 8


def compact_flags(rows: Iterable[dict[str, Any]], max_wallets: int = COMPACT_MAX_WALLETS) -> list[dict[str, Any]]:
    """The response view of log rows: the same rows minus what the log tab never renders.

    The file is the record and keeps everything; this is what the route
    returns. Per row the components lose their prose (``fact``, ``rule``,
    ``measures``, ``weight_note``), ``side_split`` and ``flags`` go, and
    ``top_wallets`` is cut to the ``max_wallets`` largest by notional, with
    ``wallets_total`` saying how many the record holds. A row with at most
    ``max_wallets`` wallets keeps its list as it is. The input rows are not
    touched; new dicts come back.
    """

    keep = max(0, int(max_wallets))
    out: list[dict[str, Any]] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        view = {key: value for key, value in row.items() if key not in COMPACT_DROP_FIELDS}
        components = row.get("components")
        if isinstance(components, list):
            view["components"] = [
                {key: part[key] for key in COMPACT_COMPONENT_KEYS if key in part} if isinstance(part, dict) else part
                for part in components
            ]
        wallets = row.get("top_wallets")
        if isinstance(wallets, list):
            view["wallets_total"] = len(wallets)
            if len(wallets) > keep:
                ranked = sorted(
                    wallets,
                    key=lambda wallet: -(_num(wallet.get("notional")) or 0.0) if isinstance(wallet, dict) else 0.0,
                )
                view["top_wallets"] = ranked[:keep]
            else:
                view["top_wallets"] = list(wallets)
        out.append(view)
    return out


def price_after(
    history: pd.DataFrame,
    flag_time: Any,
    price_at_flag: float | None,
    now: Any = None,
    known_at: Any = None,
) -> dict[str, Any] | None:
    """Price +30 min / +2 h / +24 h after ``flag_time`` from a (time, price) frame.

    Three outcomes per horizon, and they must not be confused:

    * ``None`` -- the horizon has not passed yet, so there is nothing to read.
    * ``{"price": None, "move_c": None, "no_print": True}`` -- the horizon
      passed, but nothing traded between the flag and it. This used to be
      ``None`` as well, so a day-old flag in a market that never traded again
      showed its +24 h cell as "not yet" -- a missing measurement dressed as a
      pending one.
    * a price and the move in cents of the same outcome the flag price refers to.

    ``known_at`` is when the flag became readable (the sampler wrote it). The
    horizons start at the last print of the flagged flow, which is earlier, so
    a horizon can already have passed by the time anyone could see the flag.
    Those entries are marked ``already_past``: the move is real, but no reader
    could have acted on it, and it must not be read as a live one.

    Returns ``None`` when the history is empty or the flag time is unknown.
    """

    if history is None or history.empty or "time" not in history.columns or "price" not in history.columns:
        return None
    start = pd.to_datetime(flag_time, utc=True, errors="coerce")
    if pd.isna(start):
        return None
    current = pd.to_datetime(now, utc=True, errors="coerce") if now is not None else pd.Timestamp.now(tz="UTC")
    if pd.isna(current):
        current = pd.Timestamp.now(tz="UTC")
    frame = history.copy()
    frame["time"] = pd.to_datetime(frame["time"], utc=True, errors="coerce")
    frame["price"] = pd.to_numeric(frame["price"], errors="coerce")
    frame = frame.dropna(subset=["time", "price"]).sort_values("time")
    after = frame[frame["time"] >= start]
    sichtbar_ab = pd.to_datetime(known_at, utc=True, errors="coerce") if known_at is not None else None
    if sichtbar_ab is not None and pd.isna(sichtbar_ab):
        sichtbar_ab = None
    out: dict[str, Any] = {}
    base = _num(price_at_flag)
    for label, delta in (("30m", timedelta(minutes=30)), ("2h", timedelta(hours=2)), ("24h", timedelta(hours=24))):
        horizon = start + delta
        if horizon > current:
            out[label] = None
            continue
        window = after[after["time"] <= horizon]
        if window.empty:
            out[label] = {"price": None, "move_c": None, "no_print": True}
            continue
        price = float(window["price"].iloc[-1])
        eintrag: dict[str, Any] = {
            "price": round(price, 4),
            "move_c": round((price - base) * 100.0, 1) if base is not None else None,
        }
        if sichtbar_ab is not None and horizon <= sichtbar_ab:
            eintrag["already_past"] = True
        out[label] = eintrag
    return out


#: Horizons the flag log measures, in the order the card shows them.
HORIZONS = ("30m", "2h", "24h")

#: Below this many measured flags a hit rate at one horizon is a hint, not a
#: read; from ``VERDICT_FLAGS`` on it may be stated as one. Same ladder as
#: ``scorecard.sample_quality`` uses for resolved events, so a reader meets
#: one vocabulary: insufficient / developing / adequate.
MIN_FLAGS = 10
VERDICT_FLAGS = 30


def _sample_badge(n: int) -> dict[str, Any]:
    quality = "insufficient" if n < MIN_FLAGS else "developing" if n < VERDICT_FLAGS else "adequate"
    return {"n": int(n), "quality": quality, "verdict_allowed": quality == "adequate"}


def flag_scoreboard(rows: Iterable[dict[str, Any]], *, as_of: Any = None,
                    enrich_max: int | None = None) -> dict[str, Any]:
    """How often the flagged side was higher afterwards, per horizon.

    The log showed the price move of every single flag and never added them
    up, so the only way to judge the screen was to count green cells by eye -
    and the cells on show are a selected subset (newest first, Polymarket
    only, capped at ``enrich_max``). This states the ratio together with what
    it rests on: n, a 95% Wilson interval, a sample badge, the snapshot time,
    and the denominators that were left out.

    A "hit" is narrow on purpose: the price of the side the screen named was
    higher at the horizon than at the flag. It is not evidence that anyone
    knew anything, and a flag whose price did not move counts as a tie, not
    as a hit.
    """

    from app import quant

    rows = [r for r in (rows or []) if isinstance(r, dict)]
    total = len(rows)
    venues: dict[str, int] = {}
    for row in rows:
        key = str(row.get("venue") or "unknown")
        venues[key] = venues.get(key, 0) + 1
    measured_ids: set[str] = set()
    per_horizon: dict[str, Any] = {}
    for label in HORIZONS:
        hits = ties = past = 0
        moves: list[float] = []
        for row in rows:
            after = row.get("after")
            cell = after.get(label) if isinstance(after, dict) else None
            move = _num(cell.get("move_c")) if isinstance(cell, dict) else None
            if move is None:
                continue
            measured_ids.add(str(row.get("flag_id") or id(row)))
            # Der Horizont lag schon hinter dem Moment, in dem der Flag
            # ueberhaupt lesbar wurde (price_after markiert das). Die
            # Bewegung ist echt, aber niemand haette auf sie reagieren
            # koennen - in einer Trefferquote waere sie Vorwissen.
            if isinstance(cell, dict) and cell.get("already_past"):
                past += 1
                continue
            moves.append(float(move))
            if move > 0:
                hits += 1
            elif move == 0:
                ties += 1
        decisive = len(moves) - ties
        low, high = quant.wilson_interval(hits, decisive) if decisive else (None, None)
        per_horizon[label] = {
            "n": len(moves),
            "n_decisive": decisive,
            "hits": hits,
            "ties": ties,
            "hit_rate": round(hits / decisive, 4) if decisive else None,
            "ci95": [round(low, 4), round(high, 4)] if low is not None else None,
            "avg_move_c": round(sum(moves) / len(moves), 2) if moves else None,
            "already_past": past,
            "sample": _sample_badge(decisive),
        }
    return {
        "as_of": _iso(_utc(as_of)),
        "flags_total": total,
        "flags_measured": len(measured_ids),
        "flags_by_venue": venues,
        "horizons": per_horizon,
        "basis": (
            "Hit = the price of the flagged side was higher at the horizon than at the flag; a flat price is a "
            "tie and leaves the ratio, both counted. Measured flags are a selected subset, not a sample: only "
            "Polymarket carries a readable price history"
            + (f", and only the newest {int(enrich_max)} flags are looked up" if enrich_max else "")
            + ". Rows whose horizon has not passed yet are not counted anywhere, and neither are horizons that "
            "were already behind the moment the flag became readable - the move is real there, but no reader "
            "could have acted on it."
        ),
        "multiplicity": (
            "Every market with a print in the tape is scored on every rule, and the screen re-runs every few "
            "minutes, so the flags are the extreme tail of many comparisons. Read one hit rate as the tail's "
            "behaviour, not as the accuracy of a single test."
        ),
    }
