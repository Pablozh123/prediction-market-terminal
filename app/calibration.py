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

import math
from typing import Any

import pandas as pd

from app import quant
from app.track_record import _event_key

RESOLUTION_COLUMNS = ["forecast", "outcome", "stake", "title", "time", "market_key", "event_key"]

# Below this many resolved positions the Wilson interval is so wide that the
# edge number is a hint, not a verdict — flagged instead of hidden.
MIN_SAMPLE = 20

# Below this many resolved *events* the realized-edge CI is too wide to call a
# record skill or luck either way (binomial SE alone is ~9pp at n=30), so the
# verdict is "thin" rather than a false negative.
MIN_VERDICT_EVENTS = 30


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
    without a usable entry price are dropped. ``event_key`` groups the legs of
    one NegRisk event (their outcomes are mechanically correlated) so
    ``realized_edge`` can net them to a single observation.
    """

    if resolved is None or resolved.empty:
        return pd.DataFrame(columns=RESOLUTION_COLUMNS)
    df = resolved.copy()
    entry = _numeric(df, "avg_price")
    settle = _numeric(df, "current_price")
    pnl = _numeric(df, "realized_pnl").fillna(0.0)
    decisive = settle.notna() & ((settle <= 0.02) | (settle >= 0.98))
    won = (settle >= 0.5).where(decisive, pnl > 0.0)
    out = pd.DataFrame(
        {
            "forecast": entry,
            "outcome": won.astype(float),
            "stake": _numeric(df, "total_bought").fillna(0.0),
            "title": df.get("title", pd.Series("", index=df.index)).astype(str),
            "time": pd.to_datetime(df.get("time"), utc=True, errors="coerce"),
            "market_key": df.get("market_key", pd.Series("", index=df.index)).astype(str),
            "event_key": df.apply(_event_key, axis=1),
        }
    )
    out = out[(out["forecast"] > 0.0) & (out["forecast"] < 1.0)]
    return out.reset_index(drop=True)[RESOLUTION_COLUMNS]


def calibration_report(frame: pd.DataFrame, capped: bool = False) -> dict[str, Any]:
    """Scorecard over a ``resolution_frame``: hit rate vs. what entries implied.

    Keys: n, hit_rate, hit_low/hit_high (Wilson 95%), avg_entry,
    edge_per_share (hit_rate − avg_entry) with edge_low/edge_high,
    stake_weighted_edge (dollar-weighted, None without stakes), brier_entry,
    brier_baseline (always-predict-the-base-rate Brier, ``p̄(1−p̄)`` — beating
    it means entry prices carried real information about *these* outcomes),
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
        "brier_baseline": None,
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
        "brier_baseline": hit_rate * (1.0 - hit_rate),
        "log_loss_entry": quant.log_loss(frame["forecast"], frame["outcome"]),
        "buckets": quant.calibration_table(frame["forecast"], frame["outcome"], bins=5),
        "sample_ok": sample_ok,
        "capped": bool(capped),
        "note": note,
    }


# Two-sided 97.5% Student-t quantiles for small samples; beyond df=30 the
# 1.96 + 2.5/df tail approximation is within ±0.002 of the exact value.
_T_975 = {
    1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365,
    8: 2.306, 9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145,
    15: 2.131, 16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093, 20: 2.086,
    21: 2.080, 22: 2.074, 23: 2.069, 24: 2.064, 25: 2.060, 26: 2.056,
    27: 2.052, 28: 2.048, 29: 2.045, 30: 2.042,
}


def _t_quantile_975(df: int) -> float:
    if df <= 0:
        return float("inf")
    if df <= 30:
        return _T_975[df]
    return 1.96 + 2.5 / df


def realized_edge(frame: pd.DataFrame, capped: bool = False) -> dict[str, Any]:
    """Skill-or-luck verdict: mean (outcome − entry) per event with a 95% CI.

    Each resolved position contributes ``outcome − forecast`` — how much better
    that call settled than the market priced it at entry. Legs sharing an
    ``event_key`` (NegRisk outcomes of one event) are netted to their mean
    first: their settlements are mechanically correlated, and counting them
    separately would fake a tighter interval. The CI is a Student-t interval
    over those per-event observations.

    Verdicts:
    - ``positive`` / ``negative`` — the 95% CI clears zero; on this sample the
      record is unlikely to be pure variance (in that direction).
    - ``chance`` — the CI straddles zero; luck cannot be ruled out either way.
    - ``thin`` — fewer than ``MIN_VERDICT_EVENTS`` events; the interval is too
      wide to call skill *or* luck (still reported when computable).
    - ``capped`` — the public feed capped both tails, so the sample holds only
      the biggest wins and losses; edge over extremes is biased, no verdict.

    Descriptive of the past record, not a forecast.
    """

    empty: dict[str, Any] = {
        "n_positions": 0,
        "n_events": 0,
        "edge": None,
        "ci_low": None,
        "ci_high": None,
        "verdict": "none",
        "headline": "No resolved positions with a usable entry price.",
        "capped": bool(capped),
    }
    if frame is None or frame.empty:
        return empty

    df = frame.copy()
    df["_d"] = pd.to_numeric(df["outcome"], errors="coerce") - pd.to_numeric(df["forecast"], errors="coerce")
    df = df.dropna(subset=["_d"])
    if df.empty:
        return empty

    cluster = df.get("event_key", pd.Series("", index=df.index)).astype(str)
    fallback = df.get("market_key", pd.Series("", index=df.index)).astype(str)
    cluster = cluster.where(cluster.str.strip().ne(""), fallback)
    # Rows with no key at all stay their own observation instead of merging.
    blank = cluster.str.strip().eq("")
    cluster[blank] = [f"row:{i}" for i in df.index[blank]]

    per_event = df.groupby(cluster)["_d"].mean()
    n_positions = int(len(df))
    n_events = int(len(per_event))
    edge = float(per_event.mean())

    ci_low: float | None = None
    ci_high: float | None = None
    if n_events >= 2:
        sd = float(per_event.std(ddof=1))
        half = _t_quantile_975(n_events - 1) * sd / math.sqrt(n_events)
        ci_low, ci_high = edge - half, edge + half

    if capped:
        verdict = "capped"
        headline = (
            "Extremes-only sample: the public feed caps winners and losers at ~50 each, "
            "so this holds only the biggest positions — realized edge over extremes is "
            "biased, no verdict either way."
        )
    elif n_events < MIN_VERDICT_EVENTS:
        verdict = "thin"
        headline = f"Too few resolved events ({n_events} < {MIN_VERDICT_EVENTS}) to tell edge from chance either way."
        if ci_low is not None:
            headline += f" So far {edge * 100:+.1f}pp per share, 95% CI [{ci_low * 100:+.1f}, {ci_high * 100:+.1f}]pp."
    elif ci_low is not None and ci_low > 0:
        verdict = "positive"
        headline = (
            f"Edge beyond chance on this sample: entries settled {edge * 100:+.1f}pp per share "
            f"above their price, 95% CI [{ci_low * 100:+.1f}, {ci_high * 100:+.1f}]pp over {n_events} events."
        )
    elif ci_high is not None and ci_high < 0:
        verdict = "negative"
        headline = (
            f"Systematic negative edge: entries settled {edge * 100:+.1f}pp per share below "
            f"their price, 95% CI [{ci_low * 100:+.1f}, {ci_high * 100:+.1f}]pp over {n_events} events."
        )
    else:
        verdict = "chance"
        headline = (
            f"Not separable from chance: realized edge {edge * 100:+.1f}pp per share, but the "
            f"95% CI [{(ci_low or 0) * 100:+.1f}, {(ci_high or 0) * 100:+.1f}]pp includes zero over {n_events} events."
        )

    return {
        "n_positions": n_positions,
        "n_events": n_events,
        "edge": edge,
        "ci_low": ci_low,
        "ci_high": ci_high,
        "verdict": verdict,
        "headline": headline,
        "capped": bool(capped),
    }
