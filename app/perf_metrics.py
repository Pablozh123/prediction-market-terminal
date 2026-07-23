"""Risk-adjusted performance metrics for a wallet's PnL curve.

A headline profit number says nothing about how it was earned. These functions
turn a cumulative PnL series into the ratios that make two track records
comparable: volatility, Sharpe, Sortino, maximum drawdown, Calmar.

Two deliberate design choices, both about not overstating a record:

1. Everything is computed on a *cumulative* curve differenced into daily PnL, so
   a wallet that reports profit in dollars rather than returns can still be
   scored. Where a capital base is supplied the same metrics are additionally
   expressed as returns; where it is not, the dollar Sharpe is reported and
   labelled as such rather than silently annualised against an assumed stake.
2. Sharpe on a self-selected survivor is not evidence of skill. ``sharpe_ratio``
   therefore reports the raw number and callers are expected to pair it with a
   sample-size gate; ``summarize_curve`` returns ``n_days`` for exactly that.

Streamlit-free and network-free.
"""

from __future__ import annotations

import math
from typing import Any

import pandas as pd

TRADING_DAYS = 365  # prediction markets settle every day, including weekends


def daily_pnl(curve: Any, time_column: str = "time", value_column: str = "pnl") -> pd.Series:
    """Cumulative PnL curve -> daily PnL changes, indexed by date.

    Resamples to one point per day and differences. The first day is dropped
    because a cumulative series carries no information about the change that
    produced its opening level.
    """

    if curve is None or len(curve) == 0:
        return pd.Series(dtype="float64")
    frame = pd.DataFrame(curve).copy()
    if time_column not in frame or value_column not in frame:
        return pd.Series(dtype="float64")
    frame[time_column] = pd.to_datetime(frame[time_column], utc=True, errors="coerce")
    frame[value_column] = pd.to_numeric(frame[value_column], errors="coerce")
    frame = frame.dropna(subset=[time_column, value_column]).sort_values(time_column)
    if frame.empty:
        return pd.Series(dtype="float64")
    daily = frame.set_index(time_column)[value_column].resample("1D").last().ffill()
    return daily.diff().dropna()


def max_drawdown(curve: Any) -> tuple[float, float]:
    """Deepest peak-to-trough fall of a cumulative PnL curve.

    Returns (absolute drawdown in currency, relative drawdown against the running
    peak). The relative figure is None-safe rather than exact when the curve goes
    through zero: a peak of zero has no meaningful percentage, so it is reported
    as 0.0 and the absolute number carries the message.
    """

    values = pd.to_numeric(pd.Series(curve), errors="coerce").dropna()
    if values.empty:
        return 0.0, 0.0
    running_peak = values.cummax()
    drop = running_peak - values
    absolute = float(drop.max())
    peak_at_worst = float(running_peak.iloc[int(drop.argmax())])
    relative = absolute / peak_at_worst if peak_at_worst > 0 else 0.0
    return absolute, relative


def sharpe_ratio(pnl: Any, periods_per_year: int = TRADING_DAYS) -> float | None:
    """Annualised Sharpe of a PnL series (risk-free rate assumed zero).

    None when there are fewer than two points or the series never moves, since a
    zero-variance record produces an infinite ratio that reads as perfection.
    """

    values = pd.to_numeric(pd.Series(pnl), errors="coerce").dropna()
    if len(values) < 2:
        return None
    std = float(values.std(ddof=1))
    if std <= 0:
        return None
    return float(values.mean() / std * math.sqrt(periods_per_year))


def sortino_ratio(pnl: Any, periods_per_year: int = TRADING_DAYS) -> float | None:
    """Like Sharpe but penalising downside deviation only.

    None when nothing negative ever happened: a record with no losing day has no
    measurable downside risk, and reporting a huge number there would invent
    precision the sample cannot support.
    """

    values = pd.to_numeric(pd.Series(pnl), errors="coerce").dropna()
    if len(values) < 2:
        return None
    downside = values[values < 0]
    if downside.empty:
        return None
    deviation = float(math.sqrt((downside ** 2).mean()))
    if deviation <= 0:
        return None
    return float(values.mean() / deviation * math.sqrt(periods_per_year))


def calmar_ratio(pnl: Any, curve: Any, periods_per_year: int = TRADING_DAYS) -> float | None:
    """Annualised PnL divided by the worst drawdown. None when never in drawdown."""

    values = pd.to_numeric(pd.Series(pnl), errors="coerce").dropna()
    if values.empty:
        return None
    absolute, _ = max_drawdown(curve)
    if absolute <= 0:
        return None
    return float(values.mean() * periods_per_year / absolute)


def cluster_bootstrap_edge(frame: Any, group_column: str, cost_column: str = "cost",
                           payout_column: str = "payout", draws: int = 4000,
                           seed: int = 12345, alpha: float = 0.05) -> dict[str, Any]:
    """Confidence interval for realised edge, resampling whole groups.

    Trades in the same market are not independent observations: one resolution
    decides all of them at once. Treating each fill as its own sample shrinks the
    interval by roughly the square root of the fills-per-market, which is how a
    coin-flip record ends up looking significant. Resampling whole markets keeps
    the interval honest.

    Returns edge (payout/cost - 1), the interval bounds, the number of groups,
    and whether the interval excludes zero.
    """

    data = pd.DataFrame(frame)
    required = {group_column, cost_column, payout_column}
    if data.empty or not required.issubset(data.columns):
        return {"edge": None, "ci_low": None, "ci_high": None, "groups": 0, "significant": False}
    grouped = data.groupby(group_column)[[cost_column, payout_column]].sum()
    cost = pd.to_numeric(grouped[cost_column], errors="coerce").fillna(0.0).to_numpy()
    payout = pd.to_numeric(grouped[payout_column], errors="coerce").fillna(0.0).to_numpy()
    groups = len(cost)
    if groups == 0 or cost.sum() <= 0:
        return {"edge": None, "ci_low": None, "ci_high": None, "groups": groups, "significant": False}
    point = float(payout.sum() / cost.sum() - 1.0)
    try:
        import numpy as np
    except ImportError:  # pragma: no cover - numpy ships with pandas
        return {"edge": point, "ci_low": None, "ci_high": None, "groups": groups, "significant": False}
    rng = np.random.default_rng(seed)
    picks = rng.integers(0, groups, size=(int(draws), groups))
    costs = cost[picks].sum(axis=1)
    payouts = payout[picks].sum(axis=1)
    valid = costs > 0
    if not valid.any():
        return {"edge": point, "ci_low": None, "ci_high": None, "groups": groups, "significant": False}
    edges = payouts[valid] / costs[valid] - 1.0
    low, high = np.percentile(edges, [alpha / 2 * 100, (1 - alpha / 2) * 100])
    return {
        "edge": point,
        "ci_low": float(low),
        "ci_high": float(high),
        "groups": groups,
        "significant": bool(low > 0 or high < 0),
    }


def summarize_curve(curve: Any, capital: float | None = None,
                    time_column: str = "time", value_column: str = "pnl") -> dict[str, Any]:
    """Full metric set for one cumulative PnL curve.

    ``capital`` is optional. When given, the dollar metrics are additionally
    expressed as returns on that base; the ratios themselves are scale-invariant
    and do not change. When omitted, return fields stay None rather than assuming
    a stake, because a Sharpe quoted against an invented capital base is a
    fabricated number.
    """

    pnl = daily_pnl(curve, time_column=time_column, value_column=value_column)
    frame = pd.DataFrame(curve)
    values = pd.to_numeric(frame.get(value_column), errors="coerce").dropna() if len(frame) else pd.Series(dtype=float)
    absolute_dd, relative_dd = max_drawdown(values)
    total = float(values.iloc[-1] - values.iloc[0]) if len(values) >= 2 else 0.0
    wins = int((pnl > 0).sum())
    losses = int((pnl < 0).sum())
    result: dict[str, Any] = {
        "n_days": int(len(pnl)),
        "total_pnl": total,
        "best_day": float(pnl.max()) if len(pnl) else 0.0,
        "worst_day": float(pnl.min()) if len(pnl) else 0.0,
        "mean_day": float(pnl.mean()) if len(pnl) else 0.0,
        "daily_vol": float(pnl.std(ddof=1)) if len(pnl) > 1 else 0.0,
        "winning_days": wins,
        "losing_days": losses,
        "win_day_rate": wins / (wins + losses) if (wins + losses) else None,
        "max_drawdown": absolute_dd,
        "max_drawdown_pct": relative_dd,
        "sharpe": sharpe_ratio(pnl),
        "sortino": sortino_ratio(pnl),
        "calmar": calmar_ratio(pnl, values),
        "capital": capital,
        "return_on_capital": None,
        "annualised_return": None,
    }
    if capital and capital > 0:
        result["return_on_capital"] = total / capital
        if result["n_days"] > 0:
            result["annualised_return"] = (total / capital) * (TRADING_DAYS / result["n_days"])
    return result
