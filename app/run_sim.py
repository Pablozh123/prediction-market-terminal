"""Sizing simulation and calibration over the bot's own published runs.

Works on the ``runs.json`` payload the daily pipeline publishes (one run per
episode/event, each with its placed bets). Two questions, both answered from
recorded data only:

- "What if the bot had sized differently?" — replay every RESOLVED bet with a
  chosen stake rule at its recorded average fill price. No compounding: each
  bet is sized against the same bankroll, because a handful of bets carries no
  meaningful equity path. Open bets are excluded (no outcome, no PnL).
- "Were the bot's entries honest prices?" — score each resolved bet like a
  forecast (fill price vs. settlement), reusing ``app.calibration``.

Streamlit-free, like the rest of ``app/``.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from app.quant import kelly_binary

SIM_AS_EXECUTED = "as_executed"
SIM_FIXED = "fixed"
SIM_KELLY = "kelly"
SIM_MODES = (SIM_AS_EXECUTED, SIM_FIXED, SIM_KELLY)

BET_COLUMNS = [
    "profil", "frage", "seite", "fill_preis", "einsatz_usd", "shares",
    "aufgeloest", "gewonnen", "pnl_usd",
]


def _num(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if number != number else number


def bets_frame(payload: dict[str, Any] | None) -> pd.DataFrame:
    """All placed bets across runs, one row per bet.

    ``fill_preis`` is the recorded average fill price (the price actually
    paid); falls back to the decision price when no fill price was recorded.
    """

    rows: list[dict[str, Any]] = []
    for run in (payload or {}).get("runs", []) or []:
        profil = str(run.get("profil", "") or "")
        for bet in run.get("wetten", []) or []:
            fill = _num(bet.get("avg_fill_preis"))
            if fill is None or not (0.0 < fill < 1.0):
                fill = _num(bet.get("entscheidungs_preis"))
            rows.append(
                {
                    "profil": profil,
                    "frage": str(bet.get("frage", "") or ""),
                    "seite": str(bet.get("seite", "") or ""),
                    "fill_preis": fill,
                    "einsatz_usd": _num(bet.get("einsatz_usd")) or 0.0,
                    "shares": _num(bet.get("shares")) or 0.0,
                    "aufgeloest": bool(bet.get("aufgeloest")),
                    "gewonnen": bet.get("gewonnen"),
                    "pnl_usd": _num(bet.get("pnl_usd")),
                }
            )
    return pd.DataFrame(rows, columns=BET_COLUMNS)


def _sim_stake(mode: str, row: pd.Series, *, bankroll: float, fixed_stake: float,
               kelly_edge_pt: float, kelly_fraction: float) -> float:
    price = float(row["fill_preis"])
    if mode == SIM_AS_EXECUTED:
        return float(row["einsatz_usd"])
    if mode == SIM_FIXED:
        return max(0.0, float(fixed_stake))
    if mode == SIM_KELLY:
        prob = min(0.999, price + max(0.0, float(kelly_edge_pt)) / 100.0)
        fraction = kelly_binary(price, prob) * max(0.0, float(kelly_fraction))
        return max(0.0, float(bankroll)) * fraction
    raise ValueError(f"unknown sim mode: {mode!r}")


def simulate_sizing(
    bets: pd.DataFrame,
    mode: str = SIM_AS_EXECUTED,
    *,
    bankroll: float = 100.0,
    fixed_stake: float = 5.0,
    kelly_edge_pt: float = 10.0,
    kelly_fraction: float = 0.25,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Replay every resolved bet with the chosen stake rule.

    Returns (per-bet frame, summary). Per-bet columns add ``sim_stake``,
    ``sim_shares`` and ``sim_pnl`` (win pays shares × (1 − price), loss costs
    the stake — fills assumed at the recorded average fill price). The
    summary compares real vs. simulated totals over resolved bets only.
    """

    if mode not in SIM_MODES:
        raise ValueError(f"unknown sim mode: {mode!r}")
    if bets is None or bets.empty:
        empty = pd.DataFrame(columns=BET_COLUMNS + ["sim_stake", "sim_shares", "sim_pnl"])
        return empty, {
            "mode": mode, "n_resolved": 0, "n_open": 0,
            "real_stake": 0.0, "real_pnl": None, "real_roi_pct": None,
            "sim_stake": 0.0, "sim_pnl": None, "sim_roi_pct": None,
        }
    work = bets.copy()
    resolved_mask = work["aufgeloest"].fillna(False).astype(bool) & work["gewonnen"].notna() & work["fill_preis"].notna()
    resolved = work[resolved_mask].copy()
    n_open = int(len(work) - len(resolved))
    if resolved.empty:
        empty = resolved.assign(sim_stake=pd.Series(dtype=float), sim_shares=pd.Series(dtype=float), sim_pnl=pd.Series(dtype=float))
        return empty, {
            "mode": mode, "n_resolved": 0, "n_open": n_open,
            "real_stake": 0.0, "real_pnl": None, "real_roi_pct": None,
            "sim_stake": 0.0, "sim_pnl": None, "sim_roi_pct": None,
        }

    stakes, shares_col, pnls = [], [], []
    for _, row in resolved.iterrows():
        stake = _sim_stake(mode, row, bankroll=bankroll, fixed_stake=fixed_stake,
                           kelly_edge_pt=kelly_edge_pt, kelly_fraction=kelly_fraction)
        price = float(row["fill_preis"])
        shares = stake / price if price > 0 else 0.0
        won = bool(row["gewonnen"])
        pnl = shares * (1.0 - price) if won else -stake
        stakes.append(stake)
        shares_col.append(shares)
        pnls.append(pnl)
    resolved["sim_stake"] = stakes
    resolved["sim_shares"] = shares_col
    resolved["sim_pnl"] = pnls

    real_stake = float(resolved["einsatz_usd"].sum())
    real_pnl_series = resolved["pnl_usd"].dropna()
    real_pnl = float(real_pnl_series.sum()) if not real_pnl_series.empty else None
    sim_stake = float(resolved["sim_stake"].sum())
    sim_pnl = float(resolved["sim_pnl"].sum())
    summary = {
        "mode": mode,
        "n_resolved": int(len(resolved)),
        "n_open": n_open,
        "real_stake": real_stake,
        "real_pnl": real_pnl,
        "real_roi_pct": (real_pnl / real_stake * 100.0) if real_pnl is not None and real_stake > 0 else None,
        "sim_stake": sim_stake,
        "sim_pnl": sim_pnl,
        "sim_roi_pct": (sim_pnl / sim_stake * 100.0) if sim_stake > 0 else None,
    }
    return resolved, summary


def bot_resolution_frame(bets: pd.DataFrame) -> pd.DataFrame:
    """Resolved bets in the shape ``app.calibration.calibration_report`` scores.

    forecast = recorded fill price (what the market charged the bot),
    outcome = settlement, stake = fill stake.
    """

    columns = ["forecast", "outcome", "stake", "title", "time", "market_key"]
    if bets is None or bets.empty:
        return pd.DataFrame(columns=columns)
    resolved = bets[bets["aufgeloest"].fillna(False).astype(bool) & bets["gewonnen"].notna() & bets["fill_preis"].notna()]
    if resolved.empty:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(
        {
            "forecast": resolved["fill_preis"].astype(float),
            "outcome": resolved["gewonnen"].astype(bool).astype(int),
            "stake": resolved["einsatz_usd"].astype(float),
            "title": resolved["frage"].astype(str),
            "time": pd.NaT,
            "market_key": resolved["frage"].astype(str),
        }
    ).reset_index(drop=True)
