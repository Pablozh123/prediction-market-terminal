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
                    for key in ("score", "sev", "kind", "flags", "components", "side", "side_share", "side_notional",
                                "side_split", "price_outcome", "price_at_flag", "price_min", "price_max", "notional",
                                "unique_wallets", "prints", "top_wallets", "window_start", "window_end",
                                "window_minutes", "url", "token_id"):
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


def price_after(history: pd.DataFrame, flag_time: Any, price_at_flag: float | None, now: Any = None) -> dict[str, Any] | None:
    """Price +30 min / +2 h / +24 h after ``flag_time`` from a (time, price) frame.

    A horizon that lies in the future is ``None`` ("not yet"); a horizon with no
    print between the flag and the horizon is ``None`` too. Moves are in cents
    of the same outcome the flag price refers to. Returns ``None`` when the
    history is empty or the flag time unknown.
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
    out: dict[str, Any] = {}
    base = _num(price_at_flag)
    for label, delta in (("30m", timedelta(minutes=30)), ("2h", timedelta(hours=2)), ("24h", timedelta(hours=24))):
        horizon = start + delta
        if horizon > current:
            out[label] = None
            continue
        window = after[after["time"] <= horizon]
        if window.empty:
            out[label] = None
            continue
        price = float(window["price"].iloc[-1])
        out[label] = {
            "price": round(price, 4),
            "move_c": round((price - base) * 100.0, 1) if base is not None else None,
        }
    return out
