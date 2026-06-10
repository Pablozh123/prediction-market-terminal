"""Suspicious-activity helpers layered on top of the whale insider risk scores.

Pure pandas, Streamlit-free. The base event/wallet scores come from
``src.prediction_markets.whale_event_risk_scores`` / ``whale_wallet_risk_scores``;
this module adds the signals those scores cannot see on their own:

- fresh-wallet clusters: several barely-seen wallets piling into the same market
  on the same side (the classic pattern public insider screens describe),
- real account age (when the caller fetched it) as a score bonus,
- plain-language one-line stories so a non-expert can read an event card.

Everything here is a best-effort public-data screen, not a legal finding.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from app.filters import numeric_col
from app.format import money, pct

RISK_BANDS = ((70, "High"), (55, "Medium"), (40, "Elevated"))
WATCH_ONLY = "watch only"


def risk_level(score: Any) -> str:
    try:
        value = float(score or 0.0)
    except (TypeError, ValueError):
        value = 0.0
    for threshold, label in RISK_BANDS:
        if value >= threshold:
            return label
    return "Low"


def _append_flag(flags: Any, new_flag: str) -> str:
    text = str(flags or "").strip()
    if not text or text == WATCH_ONLY:
        return new_flag
    return f"{text}; {new_flag}"


def fresh_wallet_clusters(
    trades: pd.DataFrame,
    *,
    whale_threshold: float,
    fresh_max_trades: int = 2,
    min_wallets: int = 2,
) -> pd.DataFrame:
    """Per market: how many barely-seen wallets bet meaningful size on the same side.

    "Fresh" is relative to the sampled tape (few trades in the sample but whale-sized
    notional) — the same proxy the base wallet score uses for its fresh-wallet flag.
    Returns columns: title, fresh_wallets, fresh_outcome, fresh_notional.
    """

    columns = ["title", "fresh_wallets", "fresh_outcome", "fresh_notional"]
    if trades is None or trades.empty or "wallet" not in trades or "title" not in trades:
        return pd.DataFrame(columns=columns)
    df = trades.copy()
    df["wallet"] = df["wallet"].astype(str).str.lower().str.strip()
    df = df[df["wallet"].ne("") & df["wallet"].ne("nan")]
    if df.empty:
        return pd.DataFrame(columns=columns)
    df["notional"] = numeric_col(df, "notional")
    per_wallet = df.groupby("wallet").agg(trade_count=("wallet", "size"), total_notional=("notional", "sum"))
    fresh_wallets = per_wallet[
        (per_wallet["trade_count"] <= int(fresh_max_trades)) & (per_wallet["total_notional"] >= float(whale_threshold))
    ].index
    fresh = df[df["wallet"].isin(fresh_wallets)].copy()
    if fresh.empty:
        return pd.DataFrame(columns=columns)
    fresh["outcome_label"] = fresh.get("outcome", pd.Series("", index=fresh.index)).astype(str).str.upper().str.strip()
    grouped = (
        fresh.groupby(["title", "outcome_label"], dropna=False)
        .agg(fresh_wallets=("wallet", "nunique"), fresh_notional=("notional", "sum"))
        .reset_index()
    )
    grouped = grouped.sort_values(["fresh_wallets", "fresh_notional"], ascending=False)
    best = grouped.drop_duplicates(subset=["title"], keep="first").rename(columns={"outcome_label": "fresh_outcome"})
    best = best[best["fresh_wallets"] >= int(min_wallets)]
    return best[columns].reset_index(drop=True)


def apply_fresh_wallet_bonus(event_risk: pd.DataFrame, clusters: pd.DataFrame, max_bonus: float = 10.0) -> pd.DataFrame:
    """Bump event scores where a fresh-wallet cluster sits on one side; add a flag."""

    if event_risk is None or event_risk.empty:
        return event_risk
    enriched = event_risk.copy()
    if clusters is None or clusters.empty:
        enriched["fresh_wallets"] = 0
        return enriched
    enriched = enriched.merge(clusters, on="title", how="left")
    enriched["fresh_wallets"] = pd.to_numeric(enriched.get("fresh_wallets"), errors="coerce").fillna(0).astype(int)
    has_cluster = enriched["fresh_wallets"] >= 2
    bonus = (enriched["fresh_wallets"].clip(upper=4) * (max_bonus / 4.0)).where(has_cluster, 0.0)
    enriched["event_insider_score"] = (numeric_col(enriched, "event_insider_score") + bonus).clip(0, 100).round(0)
    enriched["event_insider_level"] = enriched["event_insider_score"].map(risk_level)
    if "event_insider_flags" in enriched:
        cluster_rows = enriched.index[has_cluster]
        for idx in cluster_rows:
            count = int(enriched.at[idx, "fresh_wallets"])
            outcome = str(enriched.at[idx, "fresh_outcome"] or "").strip()
            label = f"{count} fresh wallets on {outcome}" if outcome else f"{count} fresh wallets same side"
            enriched.at[idx, "event_insider_flags"] = _append_flag(enriched.at[idx, "event_insider_flags"], label)
    return enriched


def apply_account_age_bonus(
    wallet_risk: pd.DataFrame,
    account_stats: pd.DataFrame,
    *,
    max_age_days: float = 14.0,
    bonus: float = 10.0,
) -> pd.DataFrame:
    """Bump wallet scores where the real on-chain account age is young; add a flag."""

    if wallet_risk is None or wallet_risk.empty:
        return wallet_risk
    if account_stats is None or account_stats.empty or "wallet" not in account_stats or "account_age_days" not in account_stats:
        return wallet_risk
    ages = account_stats[["wallet", "account_age_days"]].copy()
    ages["wallet"] = ages["wallet"].astype(str).str.lower().str.strip()
    ages["account_age_days"] = pd.to_numeric(ages["account_age_days"], errors="coerce")
    enriched = wallet_risk.copy()
    enriched["_wallet_key"] = enriched["wallet"].astype(str).str.lower().str.strip()
    enriched = enriched.merge(ages.rename(columns={"wallet": "_wallet_key"}), on="_wallet_key", how="left")
    young = enriched["account_age_days"].notna() & (enriched["account_age_days"] <= float(max_age_days))
    enriched["account_age_days"] = enriched["account_age_days"]
    enriched.loc[young, "wallet_insider_score"] = (
        numeric_col(enriched.loc[young], "wallet_insider_score") + float(bonus)
    ).clip(0, 100).round(0)
    enriched["wallet_insider_level"] = enriched["wallet_insider_score"].map(risk_level)
    if "wallet_insider_flags" in enriched:
        for idx in enriched.index[young]:
            age = float(enriched.at[idx, "account_age_days"])
            enriched.at[idx, "wallet_insider_flags"] = _append_flag(
                enriched.at[idx, "wallet_insider_flags"], f"new account ({age:.0f}d)"
            )
    return enriched.drop(columns=["_wallet_key"], errors="ignore")


def event_story(row: pd.Series) -> str:
    """One-line plain-language summary of why an event looks suspicious."""

    notional = float(row.get("notional", 0.0) or 0.0)
    wallets = int(row.get("unique_wallets", 0) or 0)
    parts: list[str] = []
    long_odds_share = float(row.get("long_odds_share", 0.0) or 0.0)
    if long_odds_share >= 0.4:
        parts.append(f"{pct(long_odds_share)} of it at long odds")
    late_share = float(row.get("late_share", 0.0) or 0.0)
    if late_share >= 0.4:
        parts.append("heavy flow close to resolution")
    top_wallet_share = float(row.get("top_wallet_share", 0.0) or 0.0)
    if top_wallet_share >= 0.5:
        parts.append(f"one wallet drives {pct(top_wallet_share)}")
    fresh = int(row.get("fresh_wallets", 0) or 0)
    if fresh >= 2:
        outcome = str(row.get("fresh_outcome", "") or "").strip()
        parts.append(f"{fresh} fresh wallets on {outcome}" if outcome else f"{fresh} fresh wallets on the same side")
    direction_share = float(row.get("event_directional_share", 0.0) or 0.0)
    direction_label = str(row.get("event_directional_label", "") or "").strip()
    if direction_share >= 0.8 and direction_label:
        parts.append(f"{pct(direction_share)} of flow is {direction_label}")
    price_move = float(row.get("price_move", 0.0) or 0.0)
    if price_move >= 0.03:
        parts.append(f"price moved {price_move * 100:+.0f}c behind the buys")
    base = f"{money(notional)} whale flow from {wallets} wallet{'s' if wallets != 1 else ''}"
    return f"{base} — {'; '.join(parts)}." if parts else f"{base}; no single dominant pattern."


def wallets_for_event(trades: pd.DataFrame, wallet_risk: pd.DataFrame, title: str) -> pd.DataFrame:
    """Wallet risk rows for every wallet that traded the given market in the tape."""

    if trades is None or trades.empty or wallet_risk is None or wallet_risk.empty:
        return pd.DataFrame()
    involved = (
        trades[trades.get("title", pd.Series("", index=trades.index)).astype(str).eq(str(title))]["wallet"]
        .astype(str)
        .str.lower()
        .str.strip()
    )
    involved = {wallet for wallet in involved if wallet and wallet != "nan"}
    if not involved:
        return pd.DataFrame()
    subset = wallet_risk[wallet_risk["wallet"].astype(str).str.lower().str.strip().isin(involved)]
    return subset.sort_values("wallet_insider_score", ascending=False).reset_index(drop=True)
