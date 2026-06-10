"""Pure dataframe filter/metric helpers extracted from prediction_terminal.

No Streamlit dependency — safe to import and unit-test in isolation.
"""

from __future__ import annotations

import re
from typing import Any

import pandas as pd

from src import prediction_markets as md

COPY_ORDER_STATUS_FILTERS = ["copied", "settled", "skipped", "baseline", "duplicate"]


def filter_text(df: pd.DataFrame, query: str) -> pd.DataFrame:
    if df.empty or not query:
        return df
    query = query.strip().lower()
    if not query:
        return df
    fields = [
        c
        for c in [
            "title",
            "category",
            "ticker",
            "trader",
            "wallet",
            "outcome",
            "status",
            "reason",
            "source_side",
            "side",
            "source_tx",
            "transaction_hash",
            "asset",
            "condition_id",
            "note",
            "event_time",
        ]
        if c in df.columns
    ]
    if not fields:
        return df
    mask = pd.Series(False, index=df.index)
    for field in fields:
        mask = mask | df[field].astype(str).str.lower().str.contains(re.escape(query), na=False)
    return df[mask]


def copy_order_status_bucket(status: Any, reason: Any = "") -> str:
    status_text = str(status or "").strip().lower()
    reason_text = str(reason or "").strip().lower()
    if status_text in {"seed_observed", "baseline"} or reason_text == "initial_baseline":
        return "baseline"
    if status_text in COPY_ORDER_STATUS_FILTERS:
        return status_text
    return status_text or "-"


def apply_copy_trade_order_filters(
    orders: pd.DataFrame,
    *,
    query: str,
    sides: list[str],
    statuses: list[str],
    min_tony_notional: float,
    min_copy_notional: float,
    min_pnl: float,
    reason_query: str,
    latency_only: bool,
    rows: int,
) -> pd.DataFrame:
    filtered = orders.copy()
    if filtered.empty:
        return filtered
    filtered = filter_text(filtered, query)
    if reason_query.strip() and "reason" in filtered:
        needle = reason_query.strip().lower()
        filtered = filtered[filtered["reason"].astype(str).str.lower().str.contains(re.escape(needle), na=False)]
    if "source_side" in filtered:
        side_text = filtered["source_side"].astype(str).str.upper()
        if sides:
            filtered = filtered[side_text.isin([item.upper() for item in sides])]
        else:
            filtered = filtered.iloc[0:0]
    if "status" in filtered:
        buckets = [
            copy_order_status_bucket(status, reason)
            for status, reason in zip(
                filtered["status"].tolist(),
                filtered["reason"].tolist() if "reason" in filtered else [""] * len(filtered),
            )
        ]
        filtered = filtered.assign(status_bucket=buckets)
        if statuses:
            filtered = filtered[filtered["status_bucket"].isin([item.lower() for item in statuses])]
        else:
            filtered = filtered.iloc[0:0]
    if "source_notional" in filtered:
        filtered = filtered[numeric_col(filtered, "source_notional") >= float(min_tony_notional)]
    if "copy_notional" in filtered:
        filtered = filtered[numeric_col(filtered, "copy_notional") >= float(min_copy_notional)]
    if "realized_pnl" in filtered:
        filtered = filtered[numeric_col(filtered, "realized_pnl") >= float(min_pnl)]
    if latency_only and {"created_at", "source_time"}.issubset(filtered.columns):
        latency = (
            pd.to_datetime(filtered["created_at"], utc=True, errors="coerce")
            - pd.to_datetime(filtered["source_time"], utc=True, errors="coerce")
        ).dt.total_seconds()
        filtered = filtered[latency.notna()]
    return filtered.head(int(rows)).reset_index(drop=True)


def apply_copy_trade_position_filters(
    positions: pd.DataFrame,
    *,
    query: str,
    min_value: float,
    min_pnl: float,
    rows: int,
) -> pd.DataFrame:
    filtered = positions.copy()
    if filtered.empty:
        return filtered
    filtered = filter_text(filtered, query)
    if "value" in filtered:
        filtered = filtered[numeric_col(filtered, "value") >= float(min_value)]
    if "unrealized_pnl" in filtered:
        filtered = filtered[numeric_col(filtered, "unrealized_pnl") >= float(min_pnl)]
    return filtered.head(int(rows)).reset_index(drop=True)


def numeric_col(df: pd.DataFrame, column: str, default: float = 0.0) -> pd.Series:
    if column not in df:
        return pd.Series(default, index=df.index, dtype="float64")
    return pd.to_numeric(df[column], errors="coerce").fillna(default)


def bool_mask(values: Any, default: bool = False, index: pd.Index | None = None) -> pd.Series:
    """Return a warning-free boolean mask from a Series or scalar value."""
    if isinstance(values, pd.Series):
        series = values
    else:
        series = pd.Series(values, index=index)
    values = series.to_numpy(dtype=object, na_value=default)
    return pd.Series(values, index=series.index, name=series.name).astype(bool)


def option_metric_filter(df: pd.DataFrame, column: str, preset: str, custom_min: float | None = None) -> pd.DataFrame:
    if df.empty or column not in df or preset == "All":
        return df
    values = numeric_col(df, column)
    thresholds = {
        ">$100": 100.0,
        ">$1k": 1_000.0,
        ">$10k": 10_000.0,
        ">$100k": 100_000.0,
        ">$500k": 500_000.0,
        ">$1m": 1_000_000.0,
        ">$2m": 2_000_000.0,
        "> -$10k": -10_000.0,
        "> -$100k": -100_000.0,
        "> -$500k": -500_000.0,
    }
    threshold = float(custom_min or 0.0) if preset == "Custom" else thresholds.get(preset)
    if threshold is None:
        return df
    return df[values >= threshold]


def apply_probability_filter(df: pd.DataFrame, preset: str, custom_range: tuple[float, float]) -> pd.DataFrame:
    if df.empty or "yes_price" not in df or preset == "All":
        return df
    price = numeric_col(df, "yes_price")
    ranges = {
        "5-95%": (0.05, 0.95),
        "20-80%": (0.20, 0.80),
        ">80%": (0.80, 1.0),
        ">95%": (0.95, 1.0),
        ">99%": (0.99, 1.0),
    }
    low, high = (custom_range[0] / 100, custom_range[1] / 100) if preset == "Custom" else ranges.get(preset, (0.0, 1.0))
    return df[(price >= low) & (price <= high)]


def apply_spread_filter(df: pd.DataFrame, preset: str, custom_cents: float) -> pd.DataFrame:
    if df.empty or "spread" not in df or preset == "All":
        return df
    thresholds = {"<3c": 0.03, "<7c": 0.07, "<10c": 0.10}
    threshold = float(custom_cents) / 100 if preset == "Custom" else thresholds.get(preset)
    if threshold is None:
        return df
    return df[numeric_col(df, "spread", 999.0) <= threshold]


def apply_end_date_filter(df: pd.DataFrame, preset: str, custom_days: int) -> pd.DataFrame:
    if df.empty or "end_time" not in df or preset == "All":
        return df
    end_time = pd.to_datetime(df["end_time"], utc=True, errors="coerce")
    now = pd.Timestamp.utcnow()
    if preset == "Open":
        return df[end_time.isna() | (end_time >= now)]
    if preset == "Past due":
        return df[end_time.notna() & (end_time < now)]
    days = {"<1d": 1, "<7d": 7, "<30d": 30}.get(preset, int(custom_days))
    return df[end_time.notna() & (end_time >= now) & (end_time <= now + pd.Timedelta(days=days))]


def apply_market_age_filter(df: pd.DataFrame, preset: str, custom_days: int) -> pd.DataFrame:
    if df.empty or "market_age_days" not in df or preset == "All":
        return df
    age = numeric_col(df, "market_age_days", 999_999.0)
    if preset == "Custom":
        return df[age <= int(custom_days)]
    days = {"<1d": 1, "<7d": 7, "<30d": 30}.get(preset)
    if days is not None:
        return df[age <= days]
    if preset == ">365d":
        return df[age >= 365]
    return df


def apply_percent_delta_filter(df: pd.DataFrame, column: str, preset: str, custom_pct: float) -> pd.DataFrame:
    if df.empty or column not in df or preset == "All":
        return df
    values = numeric_col(df, column)
    thresholds = {">25%": 0.25, ">50%": 0.50, ">75%": 0.75, ">100%": 1.0}
    threshold = (float(custom_pct) / 100) if preset == "Custom" else thresholds.get(preset)
    if threshold is None:
        return df
    return df[values >= threshold]


def apply_price_delta_filter(df: pd.DataFrame, column: str, preset: str, custom_cents: float) -> pd.DataFrame:
    if df.empty or column not in df or preset == "All":
        return df
    values = numeric_col(df, column).abs()
    thresholds = {">1c": 0.01, ">3c": 0.03, ">5c": 0.05, ">10c": 0.10}
    threshold = (float(custom_cents) / 100) if preset == "Custom" else thresholds.get(preset)
    if threshold is None:
        return df
    return df[values >= threshold]


def apply_account_age_filter(df: pd.DataFrame, preset: str, custom_days: int) -> pd.DataFrame:
    if df.empty or "account_age_days" not in df or preset == "All":
        return df
    age = numeric_col(df, "account_age_days", -1.0)
    if preset == "<14d":
        return df[(age >= 0) & (age <= 14)]
    if preset == ">365d":
        return df[age >= 365]
    if preset == "Custom":
        return df[age >= int(custom_days)]
    return df


def market_filter_category(category: Any, title: Any = "") -> str:
    if hasattr(md, "market_filter_category"):
        return md.market_filter_category(category, title)
    label = md.market_category_label(category)
    text = f"{category or ''} {title or ''}".upper()
    keyword_labels = (
        (("SPORT", "NBA", "NFL", "MLB", "NHL", "FIFA", "WORLD CUP", "SOCCER", "TENNIS", "GOLF", "UFC", "MMA", "FORMULA 1", " F1 ", "CRICKET"), "Sports"),
        (("CRYPTO", "BITCOIN", "BTC", "ETHEREUM", " ETH ", "SOLANA", "DOGE", "XRP"), "Crypto"),
        (("ELECTION", "POLITIC", "TRUMP", "BIDEN", "CONGRESS", "SENATE", "PRESIDENT", "MAYORAL", "GOVERNOR"), "Politics"),
        (("WEATHER", "TEMP", "HURRICANE", "RAIN", "SNOW"), "Weather"),
        (("STOCK", "NASDAQ", "SPY", "S&P", "DOW", "FED", "INFLATION", "RATE", "WTI", "CRUDE OIL", "IPO"), "Finance"),
    )
    for keywords, inferred in keyword_labels:
        if any(keyword in text for keyword in keywords):
            return inferred
    return label


def add_market_filter_metrics(markets: pd.DataFrame, now: pd.Timestamp | None = None) -> pd.DataFrame:
    if markets.empty:
        return markets
    enriched = markets.copy()
    categories = (
        enriched["category"].fillna("").astype(str)
        if "category" in enriched
        else pd.Series("", index=enriched.index, dtype="string")
    )
    titles = (
        enriched["title"].fillna("").astype(str)
        if "title" in enriched
        else pd.Series("", index=enriched.index, dtype="string")
    )
    enriched["filter_category"] = [
        market_filter_category(category, title)
        for category, title in zip(categories.tolist(), titles.tolist())
    ]
    now_ts = pd.to_datetime(now if now is not None else pd.Timestamp.now(tz="UTC"), utc=True)
    created = (
        pd.to_datetime(enriched["created_at"], utc=True, errors="coerce")
        if "created_at" in enriched
        else pd.Series(pd.NaT, index=enriched.index, dtype="datetime64[ns, UTC]")
    )
    enriched["market_age_days"] = (now_ts - created).dt.total_seconds() / 86_400
    volume_1h = numeric_col(enriched, "volume_1h")
    volume_24h = numeric_col(enriched, "volume_24h")
    volume_1w = numeric_col(enriched, "volume_1w")
    volume_1mo = numeric_col(enriched, "volume_1mo")

    one_hour_baseline = volume_24h / 24
    enriched["volume_delta_1h"] = 0.0
    valid_1h = one_hour_baseline > 0
    enriched.loc[valid_1h, "volume_delta_1h"] = (volume_1h.loc[valid_1h] / one_hour_baseline.loc[valid_1h]) - 1

    daily_baseline = (volume_1w / 7).where(volume_1w > 0, volume_1mo / 30)
    enriched["volume_delta_24h"] = 0.0
    valid_24h = daily_baseline > 0
    enriched.loc[valid_24h, "volume_delta_24h"] = (volume_24h.loc[valid_24h] / daily_baseline.loc[valid_24h]) - 1
    enriched["price_delta_1h"] = numeric_col(enriched, "change_1h")
    enriched["price_delta_24h"] = numeric_col(enriched, "change_1d")
    return enriched
