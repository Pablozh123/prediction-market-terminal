"""Corrected, verifiable trader track records.

Naive Polymarket leaderboards mislead in four documented ways; this module
fixes each so a wallet's scorecard reflects repeatable skill, not variance or
gamed metrics. It is Streamlit-free and operates on the public closed-position
and trade frames the app already fetches, so every number is auditable.

The four corrections (see docs/DIFFERENTIATION_STRATEGY.md):

1. NegRisk / leg inflation — naive tools count each outcome token of a
   multi-outcome market as its own position, roughly doubling the apparent win
   rate. We net to one record per resolved market (``conditionId``) and, for
   NegRisk events, one record per event, so a single correct call counts once.
2. Auto-redeem sign flip — winning positions are auto-redeemed to USDC and
   vanish from the ``/positions`` endpoint, so naive PnL that sums only visible
   positions can show a loss on a real profit. We use ``/closed-positions``
   (which retains resolved/redeemed rows) and sum ``realized_pnl`` there.
3. Wash-trading / airdrop farmers — ~25% of Polymarket volume is self-churn to
   farm rankings. We flag wallets whose realized edge per dollar of volume is
   negligible despite heavy volume.
4. Survivorship / one-hit wonders — a top-of-leaderboard wallet may just be the
   lucky tail. We gate on sample size and time span, measure profit
   concentration, and score risk-adjusted (Sharpe-like) return, not raw PnL.
"""

from __future__ import annotations

import math
import re
from typing import Any

import pandas as pd


# Survivorship gate: below these a track record is "insufficient sample", not a
# verdict. A handful of resolved markets over a few days is indistinguishable
# from variance.
MIN_RESOLVED_MARKETS = 10
MIN_SPAN_DAYS = 14.0
# Farmer heuristic: heavy volume with near-zero realized edge per dollar.
FARMER_MIN_VOLUME = 25_000.0
FARMER_MAX_EDGE = 0.005  # |settled_pnl| / volume below this looks like churn, not trading.


def _numeric(frame: pd.DataFrame, column: str, default: float = 0.0) -> pd.Series:
    if column not in frame:
        return pd.Series([default] * len(frame), index=frame.index, dtype="float64")
    return pd.to_numeric(frame[column], errors="coerce").fillna(default)


def _event_key(row: pd.Series) -> str:
    """Group key for NegRisk events: the event slug from the market url, else the market key.

    Polymarket closed-position rows carry ``url`` like
    ``https://polymarket.com/event/<eventSlug>``; every outcome/condition of one
    multi-outcome event shares that slug, which is exactly what we net over.
    """

    url = str(row.get("url", "") or "")
    match = re.search(r"/event/([^/?#]+)", url)
    if match and match.group(1):
        return f"event:{match.group(1)}"
    key = str(row.get("market_key", "") or "").strip()
    if key:
        return f"market:{key}"
    return f"title:{str(row.get('title', '') or '').strip().lower()}"


def market_records(closed_positions: pd.DataFrame) -> pd.DataFrame:
    """One netted row per resolved market (``conditionId``), killing leg inflation.

    Returns columns: market_key, net_pnl, volume, win (net_pnl > 0), return
    (net_pnl / volume), time.
    """

    columns = ["market_key", "net_pnl", "volume", "win", "return", "time"]
    if closed_positions is None or closed_positions.empty:
        return pd.DataFrame(columns=columns)
    df = closed_positions.copy()
    df["_pnl"] = _numeric(df, "realized_pnl")
    df["_vol"] = _numeric(df, "total_bought")
    df["_key"] = df.get("market_key", pd.Series("", index=df.index)).astype(str)
    df.loc[df["_key"].str.strip().eq(""), "_key"] = df.get("title", pd.Series("", index=df.index)).astype(str)
    if "time" in df:
        df["_time"] = pd.to_datetime(df["time"], utc=True, errors="coerce")
    else:
        df["_time"] = pd.NaT
    grouped = df.groupby("_key", dropna=False).agg(
        net_pnl=("_pnl", "sum"),
        volume=("_vol", "sum"),
        time=("_time", "max"),
    ).reset_index().rename(columns={"_key": "market_key"})
    grouped["win"] = grouped["net_pnl"] > 0
    grouped["return"] = grouped["net_pnl"] / grouped["volume"].replace({0.0: pd.NA})
    grouped["return"] = grouped["return"].fillna(0.0)
    return grouped[columns]


def event_records(closed_positions: pd.DataFrame) -> pd.DataFrame:
    """One netted row per event (NegRisk-aware) — the finest leg-inflation fix.

    A multi-outcome (NegRisk) event spans several ``conditionId`` markets; a
    trader who backed the eventual winner made one correct call, so we net the
    whole event to a single win/loss.
    """

    columns = ["event_key", "net_pnl", "volume", "win"]
    if closed_positions is None or closed_positions.empty:
        return pd.DataFrame(columns=columns)
    df = closed_positions.copy()
    df["_pnl"] = _numeric(df, "realized_pnl")
    df["_vol"] = _numeric(df, "total_bought")
    df["_event"] = df.apply(_event_key, axis=1)
    grouped = df.groupby("_event", dropna=False).agg(
        net_pnl=("_pnl", "sum"),
        volume=("_vol", "sum"),
    ).reset_index().rename(columns={"_event": "event_key"})
    grouped["win"] = grouped["net_pnl"] > 0
    return grouped[columns]


def settled_from_activity(activity: pd.DataFrame) -> pd.DataFrame:
    """Reconstruct per-market realized PnL from the raw activity feed.

    More complete than ``/closed-positions`` (which Polymarket caps at the top
    ~50 winners): activity is time-ordered and includes markets sold at a loss.
    Per market: cost = BUY notional; proceeds = SELL + REDEEM + MERGE notional;
    realized = proceeds - cost. Only markets with a recorded exit (sell/redeem/
    merge) are returned — a position that expired worthless leaves no exit event,
    so those losses are invisible in public data (the honest blind spot).

    Columns: market_key, cost, proceeds, net_pnl, win, exited(bool).
    """

    columns = ["market_key", "cost", "proceeds", "net_pnl", "win", "exited"]
    if activity is None or activity.empty or "market_key" not in activity:
        return pd.DataFrame(columns=columns)
    df = activity.copy()
    df["_key"] = df["market_key"].astype(str)
    df["_usd"] = _numeric(df, "notional")
    df["_side"] = df.get("side", pd.Series("", index=df.index)).astype(str).str.upper()
    df["_type"] = df.get("type", pd.Series("", index=df.index)).astype(str).str.upper()
    df["_is_buy"] = df["_side"].eq("BUY")
    df["_is_exit"] = df["_side"].eq("SELL") | df["_type"].isin(["REDEEM", "MERGE"])
    grouped = df.groupby("_key", dropna=False).apply(
        lambda g: pd.Series(
            {
                "cost": float(g.loc[g["_is_buy"], "_usd"].sum()),
                "proceeds": float(g.loc[g["_is_exit"], "_usd"].sum()),
                "exited": bool(g["_is_exit"].any()),
            }
        ),
        include_groups=False,
    ).reset_index().rename(columns={"_key": "market_key"})
    grouped["net_pnl"] = grouped["proceeds"] - grouped["cost"]
    grouped["win"] = grouped["net_pnl"] > 0
    return grouped[columns]


def _risk_adjusted(returns: pd.Series) -> float:
    """Sharpe-like ratio on per-market returns; rewards consistency over one big hit."""

    clean = pd.to_numeric(returns, errors="coerce").dropna()
    if len(clean) < 2:
        return 0.0
    std = float(clean.std(ddof=1))
    mean = float(clean.mean())
    if std <= 1e-9:
        return 0.0
    return mean / std * math.sqrt(len(clean))


def _grade(score: float) -> str:
    for threshold, label in ((80, "A"), (65, "B"), (50, "C"), (35, "D")):
        if score >= threshold:
            return label
    return "F"


def track_record(
    closed_positions: pd.DataFrame,
    trades: pd.DataFrame | None = None,
    activity: pd.DataFrame | None = None,
    *,
    min_resolved_markets: int = MIN_RESOLVED_MARKETS,
    min_span_days: float = MIN_SPAN_DAYS,
) -> dict[str, Any]:
    """Corrected scorecard for one wallet.

    ``closed_positions`` is the public ``/closed-positions`` frame — but that
    endpoint returns only the top ~50 winners (PnL-sorted, capped), so its win
    rate is structurally ~100% and must NOT be presented as skill. When
    ``activity`` is given we reconstruct realized PnL per market from it (which
    includes markets sold at a loss), a more complete picture; we still cannot
    see positions that expired worthless (no exit event), so ``win_rate_reliable``
    is False and the coverage caveat is always attached. Honesty about this blind
    spot is the point — competitors headline the fake 100%.
    """

    naive_legs = int(len(closed_positions)) if closed_positions is not None else 0
    naive_wins = 0
    if closed_positions is not None and not closed_positions.empty and "realized_pnl" in closed_positions:
        naive_wins = int((_numeric(closed_positions, "realized_pnl") > 0).sum())
    naive_win_rate = (naive_wins / naive_legs) if naive_legs else None

    markets = market_records(closed_positions)
    events = event_records(closed_positions)

    resolved_markets = int(len(markets))
    settled_pnl = float(markets["net_pnl"].sum()) if resolved_markets else 0.0
    volume = float(markets["volume"].sum()) if resolved_markets else 0.0
    market_wins = int(markets["win"].sum()) if resolved_markets else 0
    corrected_win_rate = (market_wins / resolved_markets) if resolved_markets else None

    resolved_events = int(len(events))
    event_wins = int(events["win"].sum()) if resolved_events else 0
    event_win_rate = (event_wins / resolved_events) if resolved_events else None

    # /closed-positions returns only the top ~50 winners (PnL-sorted, capped), so
    # a win rate from it is structurally ~100%. Detect that so we never headline it.
    closed_winner_capped = bool(resolved_markets >= 5 and market_wins == resolved_markets)

    # Activity reconstruction: more complete PnL incl. markets exited at a loss.
    # Require cost > 0 so we only count complete round-trips visible in the window
    # (a redeem whose buy predates the window would count proceeds with no cost and
    # wildly overstate PnL/edge).
    act = settled_from_activity(activity) if activity is not None else pd.DataFrame()
    act_exited = act[act["exited"] & (act["cost"] > 0)] if not act.empty else act
    if not act_exited.empty:
        settled_pnl = float(act_exited["net_pnl"].sum())
        volume = float(act_exited["cost"].sum())
        act_markets = int(len(act_exited))
        act_wins = int(act_exited["win"].sum())
        exit_win_rate = (act_wins / act_markets) if act_markets else None
        # Prefer activity view for headline PnL/markets (it shows real losses).
        resolved_markets_effective = act_markets
    else:
        exit_win_rate = None
        resolved_markets_effective = resolved_markets

    pnl_per_volume = (settled_pnl / volume) if volume > 0 else 0.0

    # A true win rate is not derivable from public feeds: worthless-expiry losses
    # leave no exit event, and closed-positions is winner-capped. Always caveat it.
    win_rate_reliable = False
    coverage_note = (
        "Win rate can't be fully verified from public data: Polymarket's closed-positions feed "
        "returns only top winners, and positions that expired worthless leave no exit event. "
        "PnL/markets below are reconstructed from the activity feed (includes losses that were sold)."
    )

    # The strongest leg-inflation fix is event-level (NegRisk outcomes are
    # separate conditionIds). Use it as the headline corrected win rate when it
    # differs from the naive per-row rate.
    headline_win_rate = event_win_rate if event_win_rate is not None else corrected_win_rate

    # Profit concentration: share of gross profit from the single best market.
    positive = markets[markets["net_pnl"] > 0]["net_pnl"] if resolved_markets else pd.Series(dtype="float64")
    gross_profit = float(positive.sum())
    top_market_share = (float(positive.max()) / gross_profit) if gross_profit > 0 else 0.0

    risk_adjusted = _risk_adjusted(markets["return"]) if resolved_markets else 0.0

    span_days = 0.0
    if resolved_markets and markets["time"].notna().any():
        span = markets["time"].max() - markets["time"].min()
        span_days = float(span.total_seconds()) / 86400.0 if pd.notna(span) else 0.0

    sample_ok = resolved_markets >= int(min_resolved_markets) and span_days >= float(min_span_days)

    farmer_flag = bool(volume >= FARMER_MIN_VOLUME and abs(pnl_per_volume) < FARMER_MAX_EDGE and resolved_markets >= 5)
    one_hit_flag = bool(resolved_markets >= 5 and top_market_share >= 0.6)
    # Ratio of naive per-row win rate to the event-netted rate. Materially != 1
    # in either direction means the naive leaderboard number is misleading.
    leg_inflation = None
    if headline_win_rate is not None and naive_win_rate is not None and headline_win_rate > 0:
        leg_inflation = naive_win_rate / headline_win_rate

    flags: list[str] = []
    if not sample_ok:
        flags.append(f"insufficient sample ({resolved_markets} markets / {span_days:.0f}d)")
    if farmer_flag:
        flags.append("wash/farm pattern: heavy volume, ~zero edge")
    if one_hit_flag:
        flags.append(f"one-hit wonder: {top_market_share*100:.0f}% of profit from one market")
    if closed_winner_capped:
        flags.append("public closed-positions feed returns only top winners — raw win rate is not real")
    if leg_inflation is not None and abs(leg_inflation - 1.0) >= 0.15:
        flags.append(f"naive win rate misleads ({(naive_win_rate or 0)*100:.0f}% raw vs {(headline_win_rate or 0)*100:.0f}% netted)")

    # Composite score (0-100). Win rate is deliberately NOT a big input — it is
    # unverifiable from public feeds — so the score leans on edge-per-volume and
    # cross-market consistency, penalising concentration. Thin/farmed records cap low.
    if not sample_ok:
        score = min(30.0, 15.0 + resolved_markets_effective)
    elif farmer_flag:
        score = 20.0
    else:
        edge_pts = max(0.0, min(1.0, pnl_per_volume / 0.20)) * 45  # 20% edge on volume -> full
        consistency_pts = max(0.0, min(1.0, (risk_adjusted + 1.0) / 4.0)) * 45
        concentration_penalty = top_market_share * 15
        score = max(0.0, min(100.0, edge_pts + consistency_pts + 10 - concentration_penalty))

    return {
        "resolved_markets": resolved_markets_effective,
        "closed_positions_markets": resolved_markets,
        "resolved_events": resolved_events,
        "naive_legs": naive_legs,
        "naive_win_rate": naive_win_rate,
        "corrected_win_rate": corrected_win_rate,
        "event_win_rate": event_win_rate,
        "exit_win_rate": exit_win_rate,
        "win_rate_reliable": win_rate_reliable,
        "closed_winner_capped": closed_winner_capped,
        "coverage_note": coverage_note,
        "leg_inflation": leg_inflation,
        "settled_pnl": settled_pnl,
        "volume": volume,
        "pnl_per_volume": pnl_per_volume,
        "top_market_share": top_market_share,
        "risk_adjusted": risk_adjusted,
        "span_days": span_days,
        "sample_ok": sample_ok,
        "farmer_flag": farmer_flag,
        "one_hit_flag": one_hit_flag,
        "score": round(score, 1),
        "grade": _grade(score),
        "flags": flags,
    }
