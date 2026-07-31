"""Pure presentation/formatting helpers extracted from prediction_terminal.

No Streamlit dependency — safe to import and unit-test in isolation.
"""

from __future__ import annotations

import re
from typing import Any

import pandas as pd


def money(value: Any) -> str:
    value = float(value or 0)
    sign = "-" if value < 0 else ""
    value = abs(value)
    if value >= 1_000_000_000:
        return f"{sign}${value / 1_000_000_000:.2f}b"
    if value >= 1_000_000:
        return f"{sign}${value / 1_000_000:.2f}m"
    if value >= 1_000:
        return f"{sign}${value / 1_000:.1f}k"
    return f"{sign}${value:,.0f}"


def markdown_money(value: Any) -> str:
    return money(value).replace("$", "\\$")


def pct(value: Any) -> str:
    if value is None or pd.isna(value):
        return "-"
    return f"{float(value) * 100:.1f}%"


def cents(value: Any) -> str:
    if value is None or pd.isna(value):
        return "-"
    return f"{float(value) * 100:.1f}c"


def signed_cents(value: Any) -> str:
    if value is None or pd.isna(value):
        return "-"
    return f"{float(value) * 100:+.1f}c"


def snapshot_label(value: Any) -> str:
    """Short UTC label for a scorecard snapshot timestamp, e.g. '2026-07-16 18:50 UTC'."""

    ts = pd.to_datetime(value, utc=True, errors="coerce")
    if pd.isna(ts):
        return "-"
    return ts.strftime("%Y-%m-%d %H:%M UTC")


def resolution_yield_summary(yes_price: Any, end_time: Any, now: pd.Timestamp | None = None) -> dict[str, Any]:
    try:
        yes = max(0.0, min(float(yes_price), 1.0))
    except (TypeError, ValueError):
        return {"side": "-", "price": None, "apy": None, "days_to_end": None}
    no = 1 - yes
    side = "Yes" if yes >= no else "No"
    price = yes if side == "Yes" else no
    if price <= 0 or price >= 1:
        return {"side": side, "price": price, "apy": None, "days_to_end": None}
    end = pd.to_datetime(end_time, utc=True, errors="coerce")
    if pd.isna(end):
        return {"side": side, "price": price, "apy": None, "days_to_end": None}
    now_ts = pd.to_datetime(now if now is not None else pd.Timestamp.now(tz="UTC"), utc=True)
    days_to_end = max((end - now_ts).total_seconds() / 86_400, 0.0)
    if days_to_end <= 0:
        return {"side": side, "price": price, "apy": None, "days_to_end": days_to_end}
    return {
        "side": side,
        "price": price,
        "apy": ((1 / price) - 1) * (365 / days_to_end),
        "days_to_end": days_to_end,
    }


def market_title_family_key(title: Any) -> str:
    tokens = re.findall(r"[a-z0-9]+", str(title or "").lower())
    stopwords = {
        "will",
        "the",
        "a",
        "an",
        "by",
        "before",
        "after",
        "in",
        "on",
        "of",
        "to",
        "and",
        "or",
        "yes",
        "no",
        "may",
        "june",
        "july",
        "august",
        "september",
        "october",
        "november",
        "december",
        "jan",
        "feb",
        "mar",
        "apr",
        "jun",
        "jul",
        "aug",
        "sep",
        "oct",
        "nov",
        "dec",
    }
    return " ".join([token for token in tokens if token not in stopwords and not token.isdigit()][:8])
