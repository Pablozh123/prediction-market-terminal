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
    resolved_capped: bool = False,
    min_resolved_markets: int = MIN_RESOLVED_MARKETS,
    min_span_days: float = MIN_SPAN_DAYS,
) -> dict[str, Any]:
    """Corrected scorecard for one wallet.

    ``closed_positions`` should be the UNIONED resolved set from
    ``get_polymarket_resolved_positions`` (winner tail + loser tail), so its
    ``realized_pnl`` gives a real per-market win/loss — not the winner-only view a
    single ``/closed-positions`` call returns. ``resolved_capped`` says both tails
    hit the ~50-row cap (hyperactive wallet; the middle is unreachable) → the win
    rate is then a lower-confidence extremes-only view. When not capped the set is
    complete and the win rate is real. ``activity`` is optional and only used to
    sanity-note round-trip PnL.
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

    # Real per-market win rate (netted). Reliable unless the feed capped both tails.
    headline_win_rate = event_win_rate if event_win_rate is not None else corrected_win_rate
    win_rate_reliable = bool(resolved_markets > 0 and not resolved_capped)

    if not resolved_markets:
        coverage_note = "No resolved positions found in the public feed for this wallet."
    elif resolved_capped:
        coverage_note = (
            "Extremes-only view: this wallet has more than ~50 wins AND ~50 losses, and the public "
            "closed-positions feed caps each tail at ~50 — so the middle results aren't reachable. "
            "Win rate here reflects the largest resolved positions, not the full history."
        )
    else:
        coverage_note = (
            "Complete resolved set: winners and losers unioned from the public closed-positions feed. "
            "Win rate is netted per market (and per NegRisk event), not per position leg."
        )

    # Optional activity cross-check (round-trip realized PnL). Not the headline.
    act = settled_from_activity(activity) if activity is not None else pd.DataFrame()
    act_exited = act[act["exited"] & (act["cost"] > 0)] if not act.empty else act
    exit_win_rate = None
    if not act_exited.empty:
        exit_win_rate = float((act_exited["win"].sum()) / len(act_exited))

    pnl_per_volume = (settled_pnl / volume) if volume > 0 else 0.0

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
    # Leg inflation: naive per-row rate vs event-netted rate (NegRisk correction).
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
    if resolved_capped:
        flags.append("extremes only — >50 wins and >50 losses; middle results beyond the public feed cap")
    if leg_inflation is not None and abs(leg_inflation - 1.0) >= 0.15:
        flags.append(f"naive win rate misleads ({(naive_win_rate or 0)*100:.0f}% raw vs {(headline_win_rate or 0)*100:.0f}% netted)")

    # Composite score (0-100). Uses win rate only when reliable (uncapped set),
    # alongside edge-per-volume and cross-market consistency; concentration penalised.
    if not sample_ok:
        score = min(30.0, 15.0 + resolved_markets)
    elif farmer_flag:
        score = 20.0
    else:
        edge_pts = max(0.0, min(1.0, pnl_per_volume / 0.20)) * 35
        consistency_pts = max(0.0, min(1.0, (risk_adjusted + 1.0) / 4.0)) * 35
        wr_for_score = headline_win_rate if win_rate_reliable else None
        winrate_pts = max(0.0, min(1.0, ((wr_for_score or 0.55) - 0.5) / 0.35)) * 20
        concentration_penalty = top_market_share * 15
        score = max(0.0, min(100.0, edge_pts + consistency_pts + winrate_pts + 10 - concentration_penalty))

    return {
        "resolved_markets": resolved_markets,
        "closed_positions_markets": resolved_markets,
        "resolved_events": resolved_events,
        "naive_legs": naive_legs,
        "naive_win_rate": naive_win_rate,
        "corrected_win_rate": corrected_win_rate,
        "event_win_rate": event_win_rate,
        "headline_win_rate": headline_win_rate,
        "exit_win_rate": exit_win_rate,
        "win_rate_reliable": win_rate_reliable,
        "resolved_capped": resolved_capped,
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
