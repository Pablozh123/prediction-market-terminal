"""Entry-price calibration for one wallet's resolved Polymarket positions.

"Was a 70% entry really 70%?" — every resolved position is scored like a
forecast: the entry price (``avg_price``) is what the market said the bought
side was worth, the settlement is the outcome. A wallet with real selection
skill wins more often than its entry prices imply; that gap (hit rate minus
average entry price) is edge per share, before fees.

Honest limits (also stated on the page):

- Selection bias by design: only markets the wallet chose to trade are scored.
  That measures skill *in its chosen spots* — which is what a desk cares
  about — not general forecasting ability.
- The public closed-positions feed caps each tail at ~50 rows (see
  ``get_polymarket_resolved_positions``); ``capped`` marks the extremes-only view.
- Entry price only: later scaling, hedging or early exits are not modelled;
  every resolved position counts 0/1 at its average entry price.

Streamlit-free, like the rest of ``app/``.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from app import quant

RESOLUTION_COLUMNS = ["forecast", "outcome", "stake", "title", "time", "market_key"]

# Below this many resolved positions the Wilson interval is so wide that the
# edge number is a hint, not a verdict — flagged instead of hidden.
MIN_SAMPLE = 20


def _numeric(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame:
        return pd.Series([float("nan")] * len(frame), index=frame.index, dtype="float64")
    return pd.to_numeric(frame[column], errors="coerce")


def resolution_frame(resolved: pd.DataFrame) -> pd.DataFrame:
    """(forecast, outcome) pairs from a resolved-positions frame.

    ``forecast`` is the average entry price of the side held; ``outcome`` is
    1.0 when that side settled as the winner. Settlement is read from
    ``current_price`` when it is decisive (≤ 0.02 or ≥ 0.98, i.e. a resolved
    token) and falls back to the sign of ``realized_pnl`` otherwise. Rows
    without a usable entry price are dropped.
    """

    if resolved is None or resolved.empty:
        return pd.DataFrame(columns=RESOLUTION_COLUMNS)
    df = resolved.copy()
    entry = _numeric(df, "avg_price")
    settle = _numeric(df, "current_price")
    pnl = _numeric(df, "realized_pnl").fillna(0.0)
    decisive = settle.notna() & ((settle <= 0.02) | (settle >= 0.98))
    won = pd.Series(False, index=df.index)
    won[decisive] = settle[decisive] >= 0.5
    won[~decisive] = pnl[~decisive] > 0.0
    out = pd.DataFrame(
        {
            "forecast": entry,
            "outcome": won.astype(float),
            "stake": _numeric(df, "total_bought").fillna(0.0),
            "title": df.get("title", pd.Series("", index=df.index)).astype(str),
            "time": pd.to_datetime(df.get("time"), utc=True, errors="coerce"),
            "market_key": df.get("market_key", pd.Series("", index=df.index)).astype(str),
        }
    )
    out = out[(out["forecast"] > 0.0) & (out["forecast"] < 1.0)]
    return out.reset_index(drop=True)[RESOLUTION_COLUMNS]


def calibration_report(frame: pd.DataFrame, capped: bool = False) -> dict[str, Any]:
    """Scorecard over a ``resolution_frame``: hit rate vs. what entries implied.

    Keys: n, hit_rate, hit_low/hit_high (Wilson 95%), avg_entry,
    edge_per_share (hit_rate − avg_entry) with edge_low/edge_high,
    stake_weighted_edge (dollar-weighted, None without stakes), brier_entry,
    log_loss_entry, buckets (calibration table), sample_ok, capped, note.
    """

    empty: dict[str, Any] = {
        "n": 0,
        "hit_rate": None,
        "hit_low": None,
        "hit_high": None,
        "avg_entry": None,
        "edge_per_share": None,
        "edge_low": None,
        "edge_high": None,
        "stake_weighted_edge": None,
        "brier_entry": None,
        "log_loss_entry": None,
        "buckets": pd.DataFrame(),
        "sample_ok": False,
        "capped": bool(capped),
        "note": "No resolved positions with a usable entry price.",
    }
    if frame is None or frame.empty:
        return empty

    n = int(len(frame))
    hits = int(frame["outcome"].sum())
    hit_rate = hits / n
    hit_low, hit_high = quant.wilson_interval(hits, n)
    avg_entry = float(frame["forecast"].mean())

    stake_weighted_edge = None
    stakes = pd.to_numeric(frame["stake"], errors="coerce").fillna(0.0)
    if float(stakes.sum()) > 0.0:
        weighted = ((frame["outcome"] - frame["forecast"]) * stakes).sum() / stakes.sum()
        stake_weighted_edge = float(weighted)

    sample_ok = n >= MIN_SAMPLE
    if capped:
        note = (
            "Extremes-only view: the public feed caps winners and losers at ~50 each, "
            "so this scores the largest resolved positions, not the full history."
        )
    elif not sample_ok:
        note = (
            f"Small sample ({n} resolved positions): the interval around the hit rate "
            "is wide — read the edge as a hint, not a verdict."
        )
    else:
        note = "Complete resolved set from the public feed (winners and losers unioned)."

    return {
        "n": n,
        "hit_rate": hit_rate,
        "hit_low": hit_low,
        "hit_high": hit_high,
        "avg_entry": avg_entry,
        "edge_per_share": hit_rate - avg_entry,
        "edge_low": hit_low - avg_entry,
        "edge_high": hit_high - avg_entry,
        "stake_weighted_edge": stake_weighted_edge,
        "brier_entry": quant.brier_score(frame["forecast"], frame["outcome"]),
        "log_loss_entry": quant.log_loss(frame["forecast"], frame["outcome"]),
        "buckets": quant.calibration_table(frame["forecast"], frame["outcome"], bins=5),
        "sample_ok": sample_ok,
        "capped": bool(capped),
        "note": note,
    }
