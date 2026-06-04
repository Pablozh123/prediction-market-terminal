"""Pure copy-follow helpers extracted from prediction_terminal."""

from __future__ import annotations

import re
from typing import Any

import pandas as pd

from app.filters import bool_mask
from src import prediction_markets as md


def active_wallet_set(traders: pd.DataFrame | None) -> set[str]:
    if traders is None or traders.empty or "wallet" not in traders:
        return set()
    active = bool_mask(traders.get("active", pd.Series(False, index=traders.index)), False)
    wallets = (str(wallet).strip().lower() for wallet in traders.loc[active, "wallet"].tolist())
    return {wallet for wallet in wallets if md.is_polymarket_wallet(wallet)}


def stats_by_wallet(stats: pd.DataFrame | None) -> dict[str, pd.Series]:
    if stats is None or stats.empty or "wallet" not in stats:
        return {}
    return {str(row.get("wallet", "") or "").strip().lower(): row for _, row in stats.iterrows()}


def status_label(wallet: Any, active_wallets: set[str]) -> str:
    return "Following" if str(wallet or "").strip().lower() in active_wallets else ""


def safe_key(*parts: Any, limit: int = 90) -> str:
    text = "_".join(str(part or "") for part in parts)
    return re.sub(r"[^a-zA-Z0-9_]", "_", text)[:limit]
