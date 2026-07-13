"""Probability and sizing math for binary contracts (prediction markets).

Streamlit-free and dependency-light so the terminal pages, the backtester and
the tests share one implementation. This is the quant layer the roadmap called
"was 70% really 70%?" (docs/PROJECT_OVERVIEW.md §7.4).

Conventions: prices and probabilities live in (0, 1). A share of the bought
side costs ``price`` and pays 1.0 when that side wins. Buying NO at YES-price
``p`` is the same contract at price ``1 - p``, so every function is expressed
on the bought side and works for either side.
"""

from __future__ import annotations

import math
from typing import Any

import pandas as pd

EPS = 1e-9


def _unit(value: Any) -> float | None:
    """Coerce to float in the open interval (0, 1); None when invalid/NaN."""

    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or not (EPS < number < 1.0 - EPS):
        return None
    return number


def kelly_binary(price: Any, prob: Any) -> float:
    """Kelly-optimal bankroll fraction for a binary contract.

    Maximising expected log growth with net odds ``b = (1 - price) / price``
    gives ``f* = (prob - price) / (1 - price)``. Returns 0.0 for invalid inputs
    or a non-positive edge; capped at 1.0. Betting past f* lowers growth — at
    2×f* the expected log growth is back to zero — which is why callers apply
    a fraction (quarter-Kelly by default) on top, pricing in that ``prob`` is
    an estimate and that platform/resolution risk lives outside the model.
    """

    p = _unit(price)
    q = _unit(prob)
    if p is None or q is None or q <= p:
        return 0.0
    return min(1.0, (q - p) / (1.0 - p))


def bayes_posterior(prior: Any, likelihood_ratio: Any) -> float:
    """Posterior probability from prior odds × likelihood ratio.

    ``likelihood_ratio`` = P(observing this evidence | YES) / P(observing it | NO).
    LR 1 leaves the prior unchanged; the same LR moves a 50% market much more
    than a 5% or 95% one (odds are multiplicative, probabilities are not).
    Returns NaN for invalid inputs.
    """

    p = _unit(prior)
    try:
        lr = float(likelihood_ratio)
    except (TypeError, ValueError):
        return float("nan")
    if p is None or lr <= 0.0 or lr != lr:
        return float("nan")
    odds = p / (1.0 - p) * lr
    return odds / (1.0 + odds)


def implied_likelihood_ratio(price_before: Any, price_after: Any) -> float:
    """The LR the market implicitly assigned to whatever moved the price.

    Ratio of posterior to prior odds. Compare it with your own read of the
    information: if the market's implied LR understates the evidence, the
    remaining gap is the trade. Returns NaN for invalid inputs.
    """

    p0 = _unit(price_before)
    p1 = _unit(price_after)
    if p0 is None or p1 is None:
        return float("nan")
    return (p1 / (1.0 - p1)) / (p0 / (1.0 - p0))


def _pairs(forecasts: Any, outcomes: Any) -> pd.DataFrame:
    frame = pd.DataFrame(
        {
            "forecast": pd.to_numeric(pd.Series(forecasts), errors="coerce"),
            "outcome": pd.to_numeric(pd.Series(outcomes), errors="coerce"),
        }
    ).dropna()
    frame = frame[(frame["forecast"] >= 0.0) & (frame["forecast"] <= 1.0)]
    frame["outcome"] = (frame["outcome"] > 0.5).astype(float)
    return frame.reset_index(drop=True)


def brier_score(forecasts: Any, outcomes: Any) -> float | None:
    """Mean squared error of probabilistic forecasts against 0/1 outcomes.

    0 is perfect; always saying 50% scores 0.25. Lower than the market's own
    Brier on the same events = measurable forecasting edge. None when empty.
    """

    frame = _pairs(forecasts, outcomes)
    if frame.empty:
        return None
    return float(((frame["forecast"] - frame["outcome"]) ** 2).mean())


def log_loss(forecasts: Any, outcomes: Any) -> float | None:
    """Cross-entropy of forecasts against outcomes; punishes confident misses.

    Forecasts are clipped away from 0/1 so a single bad call stays finite.
    None when empty.
    """

    frame = _pairs(forecasts, outcomes)
    if frame.empty:
        return None
    clipped = frame["forecast"].clip(EPS, 1.0 - EPS)
    y = frame["outcome"]
    losses = -(y * clipped.map(math.log) + (1.0 - y) * (1.0 - clipped).map(math.log))
    return float(losses.mean())


def wilson_interval(wins: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion (default 95%).

    The honest companion to any hit rate: 18/30 spans roughly 42%–75%, so a
    "60% win rate" on 30 trades does not exclude a coin flip. Returns (0, 1)
    when n is 0.
    """

    if n <= 0:
        return 0.0, 1.0
    wins = max(0, min(int(wins), int(n)))
    ph = wins / n
    z2 = z * z
    half = z * math.sqrt(ph * (1.0 - ph) / n + z2 / (4.0 * n * n))
    denom = 1.0 + z2 / n
    lo = (ph + z2 / (2.0 * n) - half) / denom
    hi = (ph + z2 / (2.0 * n) + half) / denom
    return max(0.0, lo), min(1.0, hi)


def calibration_table(forecasts: Any, outcomes: Any, bins: int = 5) -> pd.DataFrame:
    """Bucketed calibration: for each forecast band, how often did it hit?

    Columns: bucket, n, avg_forecast, hit_rate, edge (hit_rate − avg_forecast),
    hit_low, hit_high (Wilson 95%). Empty buckets are dropped. A point above
    the diagonal means those forecasts were too cheap — settled more often
    than priced.
    """

    columns = ["bucket", "n", "avg_forecast", "hit_rate", "edge", "hit_low", "hit_high"]
    frame = _pairs(forecasts, outcomes)
    if frame.empty or bins < 1:
        return pd.DataFrame(columns=columns)
    edges = [i / bins for i in range(bins + 1)]
    labels = [f"{int(edges[i] * 100)}–{int(edges[i + 1] * 100)}%" for i in range(bins)]
    frame["_bin"] = pd.cut(frame["forecast"], bins=edges, labels=labels, include_lowest=True)
    rows: list[dict[str, Any]] = []
    for label, group in frame.groupby("_bin", observed=True):
        n = int(len(group))
        if not n:
            continue
        hits = int(group["outcome"].sum())
        lo, hi = wilson_interval(hits, n)
        avg_forecast = float(group["forecast"].mean())
        hit_rate = hits / n
        rows.append(
            {
                "bucket": str(label),
                "n": n,
                "avg_forecast": avg_forecast,
                "hit_rate": hit_rate,
                "edge": hit_rate - avg_forecast,
                "hit_low": lo,
                "hit_high": hi,
            }
        )
    return pd.DataFrame(rows, columns=columns)
