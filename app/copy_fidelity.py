"""Copy-fidelity accounting: how close is the paper copy to a 1:1 (scaled)
mirror of the source wallet, and which knob or constraint costs how much.

Streamlit-free. Two orthogonal factors, multiplied:

- **Config fidelity** — what the sizing SETTINGS aim for relative to the
  neutral portfolio ratio (our equity / source equity). Multiplier != 1,
  a binding scale cap, or fixed-scale mode all move this away from 1.0.
- **Execution fidelity** — what actually got filled relative to what the
  configured scale wanted (cash droughts, per-order caps, min-notional and
  cash-throttle clamps). Computed from ``desired_notional`` vs
  ``copy_notional`` on recorded orders.
"""

from __future__ import annotations

from typing import Any

import pandas as pd


def config_fidelity(
    our_equity: float,
    source_equity: float,
    *,
    dynamic_enabled: bool = True,
    multiplier: float = 1.0,
    scale_cap: float = 0.0,
    scale_floor: float = 0.0,
    fixed_scale: float = 0.01,
) -> dict[str, Any]:
    """Compare the configured sizing against the neutral 1:1 portfolio ratio.

    Returns ``neutral_scale``, ``effective_scale``, ``fidelity``
    (effective/neutral; 1.0 = faithful, <1 under-copy, >1 over-copy) and
    ``factors`` — (label, ratio) pairs for every deviation from neutral.
    """

    our_equity = max(0.0, float(our_equity))
    source_equity = max(0.0, float(source_equity))
    neutral = our_equity / source_equity if source_equity > 0 else 0.0
    factors: list[tuple[str, float]] = []

    if not dynamic_enabled:
        effective = max(0.0, float(fixed_scale))
        if neutral > 0:
            factors.append(("Fixed-scale mode (ignores both equities)", effective / neutral))
        return {
            "neutral_scale": neutral,
            "effective_scale": effective,
            "fidelity": effective / neutral if neutral > 0 else 0.0,
            "factors": factors,
        }

    effective = neutral * max(0.0, float(multiplier))
    if float(multiplier) != 1.0:
        factors.append((f"Multiplier {float(multiplier):.2f}x", float(multiplier)))
    if scale_cap and scale_cap > 0 and effective > scale_cap:
        factors.append((f"Scale cap {scale_cap * 100:.2f}% binds", scale_cap / effective))
        effective = float(scale_cap)
    if scale_floor and scale_floor > 0 and effective < scale_floor:
        factors.append((f"Scale floor {scale_floor * 100:.2f}% binds", scale_floor / effective if effective > 0 else 0.0))
        effective = float(scale_floor)
    return {
        "neutral_scale": neutral,
        "effective_scale": effective,
        "fidelity": effective / neutral if neutral > 0 else 0.0,
        "factors": factors,
    }


def execution_fidelity(orders: pd.DataFrame, window_hours: float = 24.0, now: Any | None = None) -> dict[str, Any]:
    """Filled vs desired notional over the recent window, with loss breakdown.

    Only rows that carry a positive ``desired_notional`` participate (recorded
    since the fidelity update); older rows are ignored rather than guessed.
    """

    empty = {
        "fidelity": None,
        "desired": 0.0,
        "filled": 0.0,
        "orders": 0,
        "lost_to_skips": {},
        "lost_to_clamps": 0.0,
    }
    if orders.empty or "desired_notional" not in orders or "created_at" not in orders:
        return empty
    frame = orders.copy()
    frame["desired_notional"] = pd.to_numeric(frame["desired_notional"], errors="coerce").fillna(0.0)
    frame["copy_notional"] = pd.to_numeric(frame.get("copy_notional"), errors="coerce").fillna(0.0)
    frame["time"] = pd.to_datetime(frame["created_at"], utc=True, errors="coerce")
    frame = frame.dropna(subset=["time"])
    current = pd.Timestamp.now(tz="UTC") if now is None else pd.Timestamp(now)
    if current.tzinfo is None:
        current = current.tz_localize("UTC")
    frame = frame[frame["time"] >= current - pd.Timedelta(hours=float(window_hours))]
    frame = frame[frame["desired_notional"] > 0]
    if frame.empty:
        return empty

    desired = float(frame["desired_notional"].sum())
    filled = float(frame["copy_notional"].sum())
    skipped = frame[frame["status"] == "skipped"]
    lost_to_skips = {
        str(reason): float(group["desired_notional"].sum())
        for reason, group in skipped.groupby(skipped["reason"].fillna("unknown"))
    }
    copied = frame[frame["status"].isin(["copied", "settled"])]
    lost_to_clamps = float((copied["desired_notional"] - copied["copy_notional"]).clip(lower=0.0).sum())
    return {
        "fidelity": filled / desired if desired > 0 else None,
        "desired": desired,
        "filled": filled,
        "orders": int(len(frame)),
        "lost_to_skips": lost_to_skips,
        "lost_to_clamps": lost_to_clamps,
    }


def pnl_overlay(
    equity_snaps: pd.DataFrame,
    source_pnl: pd.DataFrame,
    source_base_equity: float,
) -> pd.DataFrame:
    """Two comparable %-PnL series: the paper copy (from equity snapshots minus
    contributions, so top-ups never look like profit) and the source wallet
    (official PnL series scaled by its current equity). Both rebased to 0 at
    the start of the overlapping window. Returns [time, pct, series].
    """

    columns = ["time", "pct", "series"]
    ours = pd.DataFrame()
    if not equity_snaps.empty and {"snapshot_time", "equity", "contributions"} <= set(equity_snaps.columns):
        ours = equity_snaps.copy()
        ours["time"] = pd.to_datetime(ours["snapshot_time"], utc=True, errors="coerce")
        ours = ours.dropna(subset=["time"]).sort_values("time")
        ours["pnl"] = pd.to_numeric(ours["equity"], errors="coerce") - pd.to_numeric(ours["contributions"], errors="coerce")
        ours = ours.dropna(subset=["pnl"])
    theirs = pd.DataFrame()
    if not source_pnl.empty and {"time", "pnl"} <= set(source_pnl.columns):
        theirs = source_pnl.copy()
        theirs["time"] = pd.to_datetime(theirs["time"], utc=True, errors="coerce")
        theirs = theirs.dropna(subset=["time"]).sort_values("time")
    if ours.empty or theirs.empty:
        return pd.DataFrame(columns=columns)

    start = max(ours["time"].iloc[0], theirs["time"].iloc[0])
    ours = ours[ours["time"] >= start]
    theirs = theirs[theirs["time"] >= start]
    if ours.empty or theirs.empty:
        return pd.DataFrame(columns=columns)

    rows: list[dict[str, Any]] = []
    our_base = float(pd.to_numeric(ours["equity"], errors="coerce").iloc[0])
    our_pnl0 = float(ours["pnl"].iloc[0])
    if our_base > 0:
        rows.extend(
            {"time": row.time, "pct": (float(row.pnl) - our_pnl0) / our_base, "series": "Paper copy"}
            for row in ours.itertuples()
        )
    their_pnl0 = float(theirs["pnl"].iloc[0])
    base = max(0.0, float(source_base_equity))
    if base > 0:
        rows.extend(
            {"time": row.time, "pct": (float(row.pnl) - their_pnl0) / base, "series": "Source wallet"}
            for row in theirs.itertuples()
        )
    return pd.DataFrame(rows, columns=columns)
