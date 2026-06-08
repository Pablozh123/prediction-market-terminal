"""Public prediction-market data clients and analytics helpers.

The functions in this module intentionally use public APIs only. Polymarket
exposes wallet-level data through public proxy-wallet addresses; Kalshi public
market/trade endpoints do not expose trader identities.
"""

from __future__ import annotations

import json
import math
import re
import time
import calendar as calendar_lib
from urllib.parse import quote_plus, unquote, urlparse
from xml.etree import ElementTree as ET
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any, Iterable, Mapping

import pandas as pd
import requests


POLY_GAMMA = "https://gamma-api.polymarket.com"
POLY_DATA = "https://data-api.polymarket.com"
POLY_CLOB = "https://clob.polymarket.com"
PREDICTPARITY_API = "https://api-prod.predictparity.com/graphql"
KALSHI_API = "https://external-api.kalshi.com/trade-api/v2"

HTTP_HEADERS = {
    "User-Agent": "prediction-market-terminal/0.1 (+local research app)",
    "Accept": "application/json",
}

TITLE_TOKEN_RE = re.compile(r"[a-z0-9]+")
POLY_WALLET_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")
PREDICTPARITY_MONITOR_SIGNAL_TYPES = [
    "Fast mover",
    "Whale print",
    "Tight spread",
    "Holder concentration",
    "Ending soon",
    "Watched market",
]
PREDICTPARITY_SEARCH_RESULT_TYPES = ["Markets", "Traders", "Trades", "News", "Cross-Venue", "Alerts", "Tracked"]


class MarketDataError(RuntimeError):
    """Raised when a market data request fails."""


def _get_json(url: str, params: dict[str, Any] | None = None, timeout: int = 20) -> Any:
    try:
        response = requests.get(url, params=params, timeout=timeout, headers=HTTP_HEADERS)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        raise MarketDataError(f"{url} failed: {exc}") from exc
    except ValueError as exc:
        raise MarketDataError(f"{url} returned non-JSON data") from exc


def _post_json(url: str, payload: Mapping[str, Any], params: dict[str, Any] | None = None, timeout: int = 20) -> Any:
    try:
        response = requests.post(url, params=params, json=dict(payload), timeout=timeout, headers=HTTP_HEADERS)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        raise MarketDataError(f"{url} failed: {exc}") from exc
    except ValueError as exc:
        raise MarketDataError(f"{url} returned non-JSON data") from exc


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        if not value:
            return []
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return []
    return []


def _num(value: Any, default: float | None = None) -> float | None:
    if value is None or value == "":
        return default
    if isinstance(value, (int, float)):
        if isinstance(value, float) and math.isnan(value):
            return default
        return float(value)
    if isinstance(value, str):
        cleaned = value.strip().replace("$", "").replace(",", "").replace("%", "")
        if cleaned == "":
            return default
        try:
            return float(cleaned)
        except ValueError:
            return default
    return default


def _safe_ts(value: Any) -> pd.Timestamp | None:
    if value is None or value == "":
        return None
    try:
        if isinstance(value, (int, float)):
            # Polymarket uses epoch seconds; PredictParity chart points use epoch milliseconds.
            unit = "ms" if abs(float(value)) >= 1_000_000_000_000 else "s"
            return pd.to_datetime(value, unit=unit, utc=True)
        return pd.to_datetime(value, utc=True)
    except Exception:
        return None


def _first_nonempty(*values: Any) -> Any:
    for value in values:
        try:
            if pd.isna(value):
                continue
        except (TypeError, ValueError):
            pass
        if value not in (None, "", [], {}):
            return value
    return None


def _scalar_nonempty(value: Any) -> Any:
    if isinstance(value, pd.Series):
        for item in value.tolist():
            scalar = _scalar_nonempty(item)
            if scalar is not None:
                return scalar
        return None
    if isinstance(value, (list, tuple, set)):
        for item in value:
            scalar = _scalar_nonempty(item)
            if scalar is not None:
                return scalar
        return None
    if hasattr(value, "tolist") and not isinstance(value, (str, bytes, dict)):
        try:
            return _scalar_nonempty(value.tolist())
        except Exception:
            pass
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if value in (None, "", [], {}):
        return None
    return value


def dollars(value: Any) -> float:
    """Parse API dollar strings and numeric fields."""

    return float(_num(value, 0.0) or 0.0)


def cents(value: Any) -> float:
    parsed = _num(value, 0.0) or 0.0
    if parsed > 1.0:
        parsed = parsed / 100.0
    return max(0.0, min(parsed, 1.0))


def _outcome_price(market: dict[str, Any], index: int = 0) -> float | None:
    prices = _as_list(market.get("outcomePrices"))
    if len(prices) > index:
        return cents(prices[index])
    best_bid = _num(market.get("bestBid"))
    best_ask = _num(market.get("bestAsk"))
    if best_bid is not None and best_ask is not None:
        return cents((best_bid + best_ask) / 2)
    return cents(market.get("lastTradePrice")) if market.get("lastTradePrice") is not None else None


def _normalize_polymarket_market(market: Mapping[str, Any], parent_event: Mapping[str, Any] | None = None) -> dict[str, Any]:
    parent_event = parent_event or {}
    outcomes = _as_list(market.get("outcomes"))
    clob_tokens = _as_list(market.get("clobTokenIds"))
    events = market.get("events") if isinstance(market.get("events"), list) else []
    event_slug = _first_nonempty(
        market.get("eventSlug"),
        parent_event.get("slug"),
        events[0].get("slug") if events and isinstance(events[0], dict) else None,
        market.get("slug"),
    )
    probability = _outcome_price(market, 0)
    category = _first_nonempty(
        market.get("category"),
        parent_event.get("category"),
        parent_event.get("sport"),
        events[0].get("category") if events and isinstance(events[0], dict) else None,
        "Uncategorized",
    )
    return {
        "platform": "Polymarket",
        "market_key": market.get("conditionId") or str(market.get("id", "")),
        "id": str(market.get("id", "")),
        "ticker": market.get("conditionId") or str(market.get("id", "")),
        "slug": market.get("slug", ""),
        "event_slug": event_slug,
        "title": market.get("question", ""),
        "description": _first_nonempty(market.get("description"), parent_event.get("description"), ""),
        "category": category or "Uncategorized",
        "yes_price": probability,
        "no_price": 1 - probability if probability is not None else None,
        "best_bid": _num(market.get("bestBid")),
        "best_ask": _num(market.get("bestAsk")),
        "spread": _num(market.get("spread")),
        "last_price": _num(market.get("lastTradePrice")),
        "change_1h": _num(market.get("oneHourPriceChange"), 0.0),
        "change_1d": _num(market.get("oneDayPriceChange"), 0.0),
        "change_1w": _num(market.get("oneWeekPriceChange"), 0.0),
        "volume": dollars(_first_nonempty(market.get("volumeNum"), market.get("volume"))),
        "volume_1h": dollars(_first_nonempty(market.get("volume1hr"), market.get("volume1h"), market.get("volume1hrClob"))),
        "volume_24h": dollars(market.get("volume24hr")),
        "volume_1w": dollars(market.get("volume1wk")),
        "volume_1mo": dollars(market.get("volume1mo")),
        "liquidity": dollars(_first_nonempty(market.get("liquidityNum"), market.get("liquidity"), parent_event.get("openInterest"))),
        "start_time": _safe_ts(_first_nonempty(market.get("startDateIso"), market.get("startDate"), parent_event.get("startDate"))),
        "end_time": _safe_ts(_first_nonempty(market.get("endDateIso"), market.get("endDate"), parent_event.get("endDate"))),
        "created_at": _safe_ts(_first_nonempty(market.get("createdAt"), parent_event.get("createdAt"))),
        "updated_at": _safe_ts(_first_nonempty(market.get("updatedAt"), parent_event.get("updatedAt"))),
        "closed_time": _safe_ts(_first_nonempty(market.get("closedTime"), parent_event.get("closedTime"))),
        "active": bool(market.get("active")),
        "closed": bool(market.get("closed")),
        "image": _first_nonempty(market.get("icon"), market.get("image"), parent_event.get("icon"), parent_event.get("image"), ""),
        "outcomes": outcomes,
        "yes_token_id": clob_tokens[0] if clob_tokens else None,
        "no_token_id": clob_tokens[1] if len(clob_tokens) > 1 else None,
        "url": f"https://polymarket.com/event/{event_slug}" if event_slug else "https://polymarket.com",
        "raw": market,
    }


def _finalize_polymarket_markets(normalized: list[dict[str, Any]]) -> pd.DataFrame:
    df = pd.DataFrame(normalized)
    if not df.empty:
        df["activity_volume"] = df["volume_24h"].where(df["volume_24h"].fillna(0) > 0, df["volume"])
        df = df.sort_values(["activity_volume", "volume"], ascending=False).reset_index(drop=True)
    return df


def get_polymarket_markets(limit: int = 250, offset: int = 0, active_only: bool | None = True) -> pd.DataFrame:
    params = {
        "limit": limit,
        "offset": offset,
        "archived": "false",
    }
    if active_only is True:
        params.update({"active": "true", "closed": "false"})
    elif active_only is False:
        params.update({"closed": "true"})
    data = _get_json(f"{POLY_GAMMA}/markets", params=params)
    rows = data if isinstance(data, list) else data.get("data", [])
    return _finalize_polymarket_markets([_normalize_polymarket_market(market) for market in rows])


def polymarket_event_slug_from_url(value: str) -> str:
    """Extract a Polymarket event slug from an event URL or return the given slug."""

    text = str(value or "").strip()
    if not text:
        return ""
    parsed = urlparse(text)
    if parsed.netloc:
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) >= 2 and parts[0] == "event":
            return parts[1]
        return ""
    return text.strip("/")


def get_polymarket_event_markets(event_url_or_slug: str) -> pd.DataFrame:
    """Fetch all markets for one Polymarket event slug, useful for activity drilldowns."""

    slug = polymarket_event_slug_from_url(event_url_or_slug)
    if not slug:
        return pd.DataFrame()
    event = _get_json(f"{POLY_GAMMA}/events/slug/{slug}")
    if not isinstance(event, dict):
        return pd.DataFrame()
    rows = event.get("markets", []) if isinstance(event.get("markets"), list) else []
    return _finalize_polymarket_markets([_normalize_polymarket_market(market, event) for market in rows])


def get_polymarket_closed_markets(limit: int = 250) -> pd.DataFrame:
    df = get_polymarket_markets(limit=limit, active_only=False)
    if df.empty:
        return df
    df = df.copy()
    df["binary_market"] = df["outcomes"].map(lambda outcomes: [str(item).lower() for item in (outcomes or [])] == ["yes", "no"])
    df["final_yes_price"] = pd.to_numeric(df.get("yes_price"), errors="coerce")
    df["resolved_outcome"] = "Multi"
    binary = df["binary_market"].astype(bool)
    df.loc[binary, "resolved_outcome"] = df.loc[binary, "final_yes_price"].map(
        lambda value: "Yes" if pd.notna(value) and value >= 0.5 else ("No" if pd.notna(value) else "Unknown")
    )
    df["decisive_resolution"] = binary & ((df["final_yes_price"] <= 0.05) | (df["final_yes_price"] >= 0.95))
    return df.sort_values(["closed_time", "volume"], ascending=[False, False]).reset_index(drop=True)


def resolution_stats(closed_markets: pd.DataFrame) -> pd.DataFrame:
    if closed_markets.empty:
        return pd.DataFrame()
    if "binary_market" in closed_markets:
        df = closed_markets[closed_markets["binary_market"].astype(bool)].copy()
    else:
        df = closed_markets.copy()
    if df.empty:
        return pd.DataFrame()
    df["is_yes"] = df["resolved_outcome"].eq("Yes")
    grouped = (
        df.groupby("category", dropna=False)
        .agg(
            markets=("market_key", "count"),
            yes_rate=("is_yes", "mean"),
            decisive_rate=("decisive_resolution", "mean"),
            total_volume=("volume", "sum"),
            median_volume=("volume", "median"),
        )
        .reset_index()
        .sort_values(["markets", "total_volume"], ascending=False)
    )
    return grouped


def add_market_filter_metrics(markets: pd.DataFrame, now: pd.Timestamp | None = None) -> pd.DataFrame:
    """Add scanner metrics used by PredictParity-style filters."""

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
    now_ts = now if now is not None else pd.Timestamp.now(tz="UTC")
    now_ts = pd.to_datetime(now_ts, utc=True)

    created = (
        pd.to_datetime(enriched["created_at"], utc=True, errors="coerce")
        if "created_at" in enriched
        else pd.Series(pd.NaT, index=enriched.index, dtype="datetime64[ns, UTC]")
    )
    enriched["market_age_days"] = (now_ts - created).dt.total_seconds() / 86_400

    def numeric_series(column: str) -> pd.Series:
        if column not in enriched:
            return pd.Series(0.0, index=enriched.index, dtype="float64")
        return pd.to_numeric(enriched[column], errors="coerce").fillna(0.0)

    volume_1h = numeric_series("volume_1h")
    volume_24h = numeric_series("volume_24h")
    volume_1w = numeric_series("volume_1w")
    volume_1mo = numeric_series("volume_1mo")

    one_hour_baseline = volume_24h / 24
    enriched["volume_delta_1h"] = 0.0
    valid_1h = one_hour_baseline > 0
    enriched.loc[valid_1h, "volume_delta_1h"] = (volume_1h.loc[valid_1h] / one_hour_baseline.loc[valid_1h]) - 1

    daily_baseline = volume_1w / 7
    fallback_daily = volume_1mo / 30
    daily_baseline = daily_baseline.where(daily_baseline > 0, fallback_daily)
    enriched["volume_delta_24h"] = 0.0
    valid_24h = daily_baseline > 0
    enriched.loc[valid_24h, "volume_delta_24h"] = (volume_24h.loc[valid_24h] / daily_baseline.loc[valid_24h]) - 1

    enriched["price_delta_1h"] = numeric_series("change_1h")
    enriched["price_delta_24h"] = numeric_series("change_1d")
    return enriched


def resolution_yield_summary(
    yes_price: Any,
    end_time: Any,
    now: pd.Timestamp | None = None,
) -> dict[str, float | str | None]:
    """Return annualized payout yield for the higher-probability binary side."""

    yes = cents(yes_price)
    no = 1 - yes
    selected_side = "Yes" if yes >= no else "No"
    selected_price = yes if selected_side == "Yes" else no
    if selected_price <= 0 or selected_price >= 1:
        return {"side": selected_side, "price": selected_price, "apy": None, "days_to_end": None}
    end = _safe_ts(end_time)
    now_ts = pd.to_datetime(now if now is not None else pd.Timestamp.now(tz="UTC"), utc=True)
    if end is None:
        return {"side": selected_side, "price": selected_price, "apy": None, "days_to_end": None}
    days_to_end = max((end - now_ts).total_seconds() / 86_400, 0.0)
    if days_to_end <= 0:
        return {"side": selected_side, "price": selected_price, "apy": None, "days_to_end": days_to_end}
    payout_return = (1 / selected_price) - 1
    apy = payout_return * (365 / days_to_end)
    return {"side": selected_side, "price": selected_price, "apy": apy, "days_to_end": days_to_end}


def market_detail_header_metrics(row: Any, now: Any | None = None) -> dict[str, Any]:
    """Return the PredictParity-style metric set for a market detail header."""

    get = row.get if hasattr(row, "get") else lambda key, default=None: default

    def field(key: str) -> Any:
        return _scalar_nonempty(get(key))

    yes_price = cents(field("yes_price"))
    raw_no = field("no_price")
    no_price = cents(raw_no) if raw_no is not None else max(0.0, 1.0 - yes_price)
    volume_24h = dollars(_first_nonempty(field("volume_24h"), field("activity_volume"), field("volume")))
    liquidity = dollars(_first_nonempty(field("liquidity"), field("open_interest")))
    end_time = _safe_ts(field("end_time"))
    yield_summary = resolution_yield_summary(yes_price, end_time, now=pd.to_datetime(now, utc=True) if now is not None else None)
    side = yield_summary.get("side")
    return {
        "venue": str(_first_nonempty(field("platform"), "-")),
        "yes_price": yes_price,
        "no_price": no_price,
        "volume_1h": dollars(field("volume_1h")),
        "volume_24h": volume_24h,
        "liquidity_or_oi": liquidity,
        "end_time": end_time,
        "end_label": relative_time_label(end_time, now=now),
        "apy_label": f"{side} APY" if side not in {None, "-"} else "APY",
        "apy": yield_summary.get("apy"),
    }


def market_title_family_key(title: Any) -> str:
    tokens = TITLE_TOKEN_RE.findall(str(title or "").lower())
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
    core = [token for token in tokens if token not in stopwords and not token.isdigit()]
    return " ".join(core[:8])


def related_markets(markets: pd.DataFrame, current: pd.Series | dict[str, Any], include_current: bool = True, limit: int = 20) -> pd.DataFrame:
    if markets.empty:
        return pd.DataFrame()
    current_series = pd.Series(current)
    frame = markets.copy()
    current_key = str(current_series.get("market_key", "") or "")
    event_slug = str(current_series.get("event_slug", "") or "")
    if event_slug and "event_slug" in frame:
        related = frame[frame["event_slug"].astype(str).eq(event_slug)].copy()
    else:
        family = market_title_family_key(current_series.get("title", ""))
        if not family or "title" not in frame:
            return pd.DataFrame()
        frame["_family_key"] = frame["title"].map(market_title_family_key)
        related = frame[frame["_family_key"].eq(family)].drop(columns=["_family_key"], errors="ignore").copy()
    if not include_current and current_key and "market_key" in related:
        related = related[~related["market_key"].astype(str).eq(current_key)]
    if related.empty:
        return related
    if "end_time" in related:
        related["_end_sort"] = pd.to_datetime(related["end_time"], utc=True, errors="coerce")
    else:
        related["_end_sort"] = pd.NaT
    if "activity_volume" not in related:
        related["activity_volume"] = pd.to_numeric(related.get("volume_24h", 0), errors="coerce").fillna(0.0)
    if "closed" not in related:
        related["closed"] = False
    related = related.sort_values(["closed", "_end_sort", "activity_volume"], ascending=[True, True, False], na_position="last")
    return related.drop(columns=["_end_sort"], errors="ignore").head(limit).reset_index(drop=True)


def get_polymarket_price_history(token_id: str, days: int = 30, interval: str = "1d") -> pd.DataFrame:
    if not token_id:
        return pd.DataFrame(columns=["time", "price"])
    end_ts = int(time.time())
    start_ts = end_ts - int(days) * 86400
    try:
        data = _get_json(
            f"{POLY_CLOB}/prices-history",
            params={"market": token_id, "startTs": start_ts, "endTs": end_ts, "interval": interval, "fidelity": 100},
        )
    except MarketDataError:
        return pd.DataFrame(columns=["time", "price"])
    rows = data.get("history", data) if isinstance(data, dict) else data
    df = pd.DataFrame(rows or [])
    if df.empty or "t" not in df.columns or "p" not in df.columns:
        return pd.DataFrame(columns=["time", "price"])
    df["time"] = pd.to_datetime(df["t"], unit="s", utc=True)
    df["price"] = pd.to_numeric(df["p"], errors="coerce")
    return df[["time", "price"]].dropna().sort_values("time").reset_index(drop=True)


def get_polymarket_orderbook(token_id: str, depth: int = 25) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not token_id:
        empty = pd.DataFrame(columns=["price", "size", "notional", "side"])
        return empty.copy(), empty.copy()
    empty = pd.DataFrame(columns=["price", "size", "notional", "side"])
    try:
        data = _get_json(f"{POLY_CLOB}/book", params={"token_id": token_id})
    except MarketDataError:
        return empty.copy(), empty.copy()

    def normalize(levels: list[dict[str, Any]], side: str) -> pd.DataFrame:
        df = pd.DataFrame(levels or [])
        if df.empty:
            return pd.DataFrame(columns=["price", "size", "notional", "side"])
        df["price"] = pd.to_numeric(df["price"], errors="coerce")
        df["size"] = pd.to_numeric(df["size"], errors="coerce")
        df["notional"] = df["price"] * df["size"]
        df["side"] = side
        df = df.dropna().sort_values("price", ascending=(side == "ask")).head(depth)
        return df.reset_index(drop=True)

    return normalize(data.get("bids", []), "bid"), normalize(data.get("asks", []), "ask")


def orderbook_ladder(bids: pd.DataFrame, asks: pd.DataFrame, depth: int = 25) -> pd.DataFrame:
    """Build a Parity-style cumulative Price/Shares/Total orderbook ladder."""

    frames: list[pd.DataFrame] = []
    for side, source, ascending in (("Bid", bids, False), ("Ask", asks, True)):
        if source.empty:
            continue
        frame = source.copy()
        frame["price"] = pd.to_numeric(frame.get("price"), errors="coerce")
        frame["shares"] = pd.to_numeric(frame.get("size"), errors="coerce").fillna(0.0)
        if "notional" in frame:
            frame["notional"] = pd.to_numeric(frame["notional"], errors="coerce").fillna(frame["price"] * frame["shares"])
        else:
            frame["notional"] = frame["price"] * frame["shares"]
        frame = frame.dropna(subset=["price"]).sort_values("price", ascending=ascending).head(depth)
        if frame.empty:
            continue
        frame["side"] = side
        frame["total_shares"] = frame["shares"].cumsum()
        frame["total"] = frame["notional"].cumsum()
        frames.append(frame[["side", "price", "shares", "total_shares", "total"]])
    if not frames:
        return pd.DataFrame(columns=["side", "price", "shares", "total_shares", "total"])
    return pd.concat(frames, ignore_index=True).reset_index(drop=True)


def orderbook_summary(bids: pd.DataFrame, asks: pd.DataFrame) -> dict[str, float | None]:
    """Return best bid/ask, spread, midpoint, and visible depth stats."""

    best_bid = None
    best_ask = None
    if not bids.empty and "price" in bids:
        bid_prices = pd.to_numeric(bids["price"], errors="coerce").dropna()
        best_bid = float(bid_prices.max()) if not bid_prices.empty else None
    if not asks.empty and "price" in asks:
        ask_prices = pd.to_numeric(asks["price"], errors="coerce").dropna()
        best_ask = float(ask_prices.min()) if not ask_prices.empty else None
    spread = (best_ask - best_bid) if best_bid is not None and best_ask is not None else None
    midpoint = ((best_bid + best_ask) / 2) if best_bid is not None and best_ask is not None else None
    bid_depth = float(pd.to_numeric(bids.get("notional", pd.Series(dtype="float64")), errors="coerce").fillna(0.0).sum()) if not bids.empty else 0.0
    ask_depth = float(pd.to_numeric(asks.get("notional", pd.Series(dtype="float64")), errors="coerce").fillna(0.0).sum()) if not asks.empty else 0.0
    return {
        "best_bid": best_bid,
        "best_ask": best_ask,
        "spread": spread,
        "midpoint": midpoint,
        "bid_depth": bid_depth,
        "ask_depth": ask_depth,
    }


def get_polymarket_trades(
    limit: int = 250,
    min_cash: float = 0,
    user: str | None = None,
    market: str | None = None,
) -> pd.DataFrame:
    params: dict[str, Any] = {"limit": limit}
    if min_cash > 0:
        params["filterType"] = "CASH"
        params["filterAmount"] = min_cash
    if user:
        params["user"] = user
    if market:
        params["market"] = market
    data = _get_json(f"{POLY_DATA}/trades", params=params)
    df = pd.DataFrame(data if isinstance(data, list) else data.get("data", []))
    if df.empty:
        return pd.DataFrame()
    df["platform"] = "Polymarket"
    df["wallet"] = df.get("proxyWallet", "")
    df["trader"] = df.get("name", "").where(df.get("name", "") != "", df.get("pseudonym", ""))
    df["time"] = pd.to_datetime(df["timestamp"], unit="s", utc=True, errors="coerce")
    df["size"] = pd.to_numeric(df.get("size"), errors="coerce").fillna(0.0)
    df["price"] = pd.to_numeric(df.get("price"), errors="coerce").fillna(0.0)
    df["notional"] = df["size"] * df["price"]
    df["side"] = df.get("side", "")
    df["title"] = df.get("title", "")
    df["market_key"] = df.get("conditionId", "")
    df["asset"] = df.get("asset", "")
    df["timestamp"] = pd.to_numeric(df.get("timestamp"), errors="coerce").fillna(0).astype("int64")
    df["transaction_hash"] = df.get("transactionHash", "")
    df["outcome"] = df.get("outcome", "")
    df["slug"] = df.get("slug", "")
    df["url"] = "https://polymarket.com/event/" + df.get("eventSlug", df["slug"]).fillna(df["slug"]).astype(str)
    cols = [
        "platform",
        "time",
        "trader",
        "wallet",
        "side",
        "outcome",
        "title",
        "price",
        "size",
        "notional",
        "market_key",
        "asset",
        "timestamp",
        "transaction_hash",
        "slug",
        "url",
    ]
    return df[[c for c in cols if c in df.columns]].sort_values("time", ascending=False).reset_index(drop=True)


def is_polymarket_wallet(value: Any) -> bool:
    return bool(POLY_WALLET_RE.fullmatch(str(value or "").strip()))


def polygonscan_tx_url(tx_hash: Any) -> str:
    tx = str(tx_hash or "").strip()
    return f"https://polygonscan.com/tx/{tx}" if tx.startswith("0x") else ""


def polymarket_profile_url(wallet: Any) -> str:
    address = str(wallet or "").strip()
    return f"https://polymarket.com/profile/{address}" if is_polymarket_wallet(address) else ""


def x_profile_url(username: Any) -> str:
    handle = str(username or "").strip()
    if not handle:
        return ""
    url_match = re.search(r"(?:twitter\.com|x\.com)/@?([^/?#]+)", handle, flags=re.IGNORECASE)
    if url_match:
        handle = url_match.group(1)
    handle = handle.strip().strip("/").lstrip("@")
    return f"https://x.com/{handle}" if re.fullmatch(r"[A-Za-z0-9_]{1,15}", handle) else ""


def predictparity_trader_url(handle: Any) -> str:
    text = normalize_profile_query(handle)
    if not text or is_polymarket_wallet(text):
        return ""
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", text):
        return ""
    return f"https://predictparity.com/traders/p/@{quote_plus(text)}"


def normalize_profile_query(value: Any) -> str:
    """Normalize profile handles, URLs, and addresses for exact profile lookup."""
    text = str(value or "").strip()
    if not text:
        return ""
    url_match = re.search(r"/(?:profile|traders/p)/@?([^/?#]+)", text, flags=re.IGNORECASE)
    if url_match:
        text = url_match.group(1)
    return text.strip().strip("/").lstrip("@").lower()


def local_route_target(value: Any) -> dict[str, str]:
    """Parse local app routes into a workspace slug and optional profile target."""

    raw_value = str(value or "").strip()
    if not raw_value:
        return {"page_slug": "", "profile": "", "market": ""}
    parsed = urlparse(raw_value)
    path = parsed.path if parsed.scheme or parsed.netloc else raw_value
    parts = [unquote(part.strip()) for part in path.strip("/").split("/") if part.strip()]
    if not parts:
        return {"page_slug": "", "profile": "", "market": ""}

    first = parts[0].lower()
    if first == "traders" and len(parts) >= 3 and parts[1].lower() == "p":
        return {"page_slug": "wallets", "profile": normalize_profile_query(parts[2]), "market": ""}
    if first in {"wallets", "profile"} and len(parts) >= 2:
        return {"page_slug": "wallets", "profile": normalize_profile_query(parts[1]), "market": ""}
    if first == "markets" and len(parts) >= 2:
        return {"page_slug": "markets", "profile": "", "market": parts[1].strip()}
    return {"page_slug": first, "profile": "", "market": ""}


def local_auth_route_mode(value: Any) -> str:
    """Return the local auth-shell mode requested by a path route."""

    raw_value = str(value or "").strip()
    if not raw_value:
        return ""
    parsed = urlparse(raw_value)
    path = parsed.path if parsed.scheme or parsed.netloc else raw_value
    parts = [unquote(part.strip()).lower() for part in path.strip("/").split("/") if part.strip()]
    if not parts:
        return ""
    route = "/".join(parts[:2])
    sign_in_routes = {"sign-in", "signin", "login", "auth/sign-in", "auth/signin", "auth/login"}
    sign_up_routes = {"sign-up", "signup", "register", "auth/sign-up", "auth/signup", "auth/register"}
    if route in sign_in_routes or parts[0] in sign_in_routes:
        return "Sign In"
    if route in sign_up_routes or parts[0] in sign_up_routes:
        return "Sign Up"
    return ""


def _query_param_value(params: Mapping[str, Any], *names: str) -> str:
    lowered = {str(key).lower(): value for key, value in params.items()}
    for name in names:
        value = lowered.get(str(name).lower())
        if isinstance(value, list):
            value = value[0] if value else ""
        if value is not None and str(value).strip() != "":
            return str(value).strip()
    return ""


def _query_bool(params: Mapping[str, Any], *names: str) -> bool:
    value = _query_param_value(params, *names).lower()
    return value in {"1", "true", "yes", "y", "on"}


def _query_float(params: Mapping[str, Any], *names: str) -> float | None:
    value = _query_param_value(params, *names).replace(",", "")
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _query_list(params: Mapping[str, Any], *names: str) -> list[str]:
    value = _query_param_value(params, *names)
    if not value:
        return []
    return [item.strip() for item in re.split(r"[,|]", value) if item.strip()]


def _percent_param(value: float | None) -> int | None:
    if value is None:
        return None
    if 0 <= value <= 1:
        value *= 100
    return int(max(0, min(100, round(value))))


def predictparity_market_filter_view(params: Mapping[str, Any]) -> dict[str, Any]:
    """Translate PredictParity-style market query params into local filter state."""

    view: dict[str, Any] = {}
    query = _query_param_value(params, "q", "query", "search")
    if query:
        view["query"] = query

    view_mode = _query_param_value(params, "view", "mode").lower()
    view_map = {"table": "Table", "cards": "Card", "card": "Card", "calendar": "Calendar"}
    if view_mode in view_map:
        view["view"] = view_map[view_mode]

    quick = _query_param_value(params, "quick", "filter").lower().replace("-", " ")
    quick_map = {
        "trending": "Trending",
        "saved": "Saved",
        "my positions": "My Positions",
        "positions": "My Positions",
        "ending soon": "Ending Soon",
        "ending": "Ending Soon",
        "new": "New",
    }
    if quick in quick_map:
        view["quick"] = quick_map[quick]

    platforms = [item.capitalize() for item in _query_list(params, "platform", "platforms", "venue", "venues")]
    platforms = [item for item in platforms if item in {"Polymarket", "Kalshi"}]
    if platforms:
        view["platform_filter"] = platforms

    status = _query_param_value(params, "status").lower()
    status_map = {"active": "Active", "all": "All", "closed": "Closed", "resolved": "Closed"}
    if status in status_map:
        view["status_filter"] = status_map[status]

    include_categories = _query_list(params, "category", "categories", "includeCategory", "include")
    if include_categories:
        view["include_categories"] = include_categories
    exclude_categories = _query_list(params, "excludeCategory", "excludeCategories", "exclude")
    if exclude_categories:
        view["exclude_categories"] = exclude_categories

    prob_min = _percent_param(_query_float(params, "probMin", "priceMin", "minProbability"))
    prob_max = _percent_param(_query_float(params, "probMax", "priceMax", "maxProbability"))
    if prob_min is not None or prob_max is not None:
        view["prob_preset"] = "Custom"
        view["custom_prob"] = [prob_min if prob_min is not None else 0, prob_max if prob_max is not None else 100]

    volume_min = _query_float(params, "volumeMin", "volMin", "minVolume")
    if volume_min is not None:
        view["volume_preset"] = "Custom"
        view["custom_volume"] = float(volume_min)

    volume_1h_min = _query_float(params, "volume1hMin", "vol1hMin", "minVolume1h")
    if volume_1h_min is not None:
        view["volume_1h_preset"] = "Custom"
        view["custom_volume_1h"] = float(volume_1h_min)

    liquidity_min = _query_float(params, "liquidityMin", "liqMin", "minLiquidity")
    if liquidity_min is not None:
        view["liquidity_preset"] = "Custom"
        view["custom_liquidity"] = float(liquidity_min)

    spread_max = _query_float(params, "spreadMax", "maxSpread")
    if spread_max is not None:
        view["spread_preset"] = "Custom"
        view["custom_spread"] = round(float(spread_max * 100 if 0 < spread_max <= 1 else spread_max), 4)

    end_days = _query_float(params, "endDays", "endingDays", "maxDaysToEnd")
    if end_days is not None and end_days > 0:
        view["end_preset"] = "Custom"
        view["custom_days"] = int(end_days)

    age_days = _query_float(params, "ageDays", "maxAgeDays")
    if age_days is not None and age_days > 0:
        view["age_preset"] = "Custom"
        view["custom_age_days"] = int(age_days)

    sort = _query_param_value(params, "sort", "sortBy", "orderBy")
    if sort:
        view["sort_by"] = sort

    rows = _query_float(params, "rows", "limit")
    if rows is not None and rows > 0:
        view["limit_rows"] = int(rows)
    return view


def predictparity_overview_filter_view(params: Mapping[str, Any]) -> dict[str, Any]:
    """Translate PredictParity-style dashboard query params into local filter state."""

    view: dict[str, Any] = {}
    query = _query_param_value(params, "q", "query", "search", "market", "event")
    if query:
        view["query"] = query

    platforms = [item.capitalize() for item in _query_list(params, "platform", "platforms", "venue", "venues")]
    platforms = [item for item in platforms if item in {"Polymarket", "Kalshi"}]
    if platforms:
        view["platforms"] = platforms

    featured = _query_param_value(params, "featured", "featuredSource", "source").lower()
    if featured in {"polymarket", "poly", "pm"}:
        view["featured_source"] = "Polymarket"
    elif featured in {"any", "all"}:
        view["featured_source"] = "Any"

    rows = _query_float(params, "marketRows", "cards", "rows", "limit")
    if rows is not None and rows > 0:
        view["market_rows"] = int(rows)

    include_categories = _query_list(params, "category", "categories", "includeCategory", "include")
    if include_categories:
        view["include_categories"] = include_categories

    exclude_categories = _query_list(params, "excludeCategory", "excludeCategories", "exclude")
    if exclude_categories:
        view["exclude_categories"] = exclude_categories

    min_volume = _query_float(params, "minVolume", "volumeMin", "volMin")
    if min_volume is not None:
        view["min_volume"] = float(min_volume)

    min_liquidity = _query_float(params, "minLiquidity", "liquidityMin", "liqMin")
    if min_liquidity is not None:
        view["min_liquidity"] = float(min_liquidity)

    min_flow = _query_float(params, "minFlow", "flowMin", "minNotional", "notionalMin")
    if min_flow is not None:
        view["min_flow_notional"] = float(min_flow)

    active = _query_param_value(params, "active", "activeOnly", "activeMarkets").lower()
    if active:
        view["active_only"] = active in {"1", "true", "yes", "y", "on"}

    show_news = _query_param_value(params, "showNews", "news", "newsfeed").lower()
    if show_news:
        view["show_news"] = show_news in {"1", "true", "yes", "y", "on"}
    return view


def predictparity_search_filter_view(params: Mapping[str, Any]) -> dict[str, Any]:
    """Translate PredictParity-style search query params into local filter state."""

    view: dict[str, Any] = {}
    query = _query_param_value(params, "q", "query", "search")
    if query:
        view["query"] = query

    platforms = [item.capitalize() for item in _query_list(params, "platform", "platforms", "venue", "venues")]
    platforms = [item for item in platforms if item in {"Polymarket", "Kalshi"}]
    if platforms:
        view["platforms"] = platforms

    result_lookup = {item.lower().replace("_", " ").replace("-", " "): item for item in PREDICTPARITY_SEARCH_RESULT_TYPES}
    result_types: list[str] = []
    for item in _query_list(params, "type", "types", "result", "results"):
        key = item.lower().replace("_", " ").replace("-", " ")
        if key in result_lookup:
            result_types.append(result_lookup[key])
    if result_types:
        view["result_types"] = result_types

    min_value = _query_float(params, "minValue", "valueMin", "min", "minNotional")
    if min_value is not None:
        view["min_value"] = float(min_value)

    rows = _query_float(params, "rows", "limit")
    if rows is not None and rows > 0:
        view["rows"] = int(rows)

    active = _query_param_value(params, "active", "activeMarkets", "activeOnly").lower()
    if active:
        view["active_markets_only"] = active in {"1", "true", "yes", "y", "on"}

    if _query_bool(params, "tracked", "trackedOnly"):
        view["tracked_only"] = True

    broad_pairs = _query_param_value(params, "broadPairs", "fallbackPairs").lower()
    if broad_pairs:
        view["broad_pairs"] = broad_pairs in {"1", "true", "yes", "y", "on"}
    return view


def predictparity_trader_filter_view(params: Mapping[str, Any]) -> dict[str, Any]:
    """Translate PredictParity-style trader query params into local filter state."""

    view: dict[str, Any] = {}
    if _query_bool(params, "bot", "bots", "botLike"):
        view["bots_only"] = True
        view["trait_filter"] = ["Bot-like"]
        view["bot_score_min"] = int(_query_float(params, "botScoreMin", "botMin") or 65)

    active_positions_min = _query_float(params, "apMin", "activePositionsMin", "active_positions_min")
    if active_positions_min is not None and active_positions_min > 0:
        view["active_only"] = True
        view["enrich_positions"] = True
        view["active_positions_min"] = int(active_positions_min)

    pnl_min = _query_float(params, "pnlMin", "profitMin", "minPnl")
    if pnl_min is not None:
        view["pnl_preset"] = "Custom"
        view["custom_pnl"] = float(pnl_min)

    volume_min = _query_float(params, "volMin", "volumeMin", "minVolume")
    if volume_min is not None:
        view["volume_preset"] = "Custom"
        view["custom_volume"] = float(volume_min)

    query = _query_param_value(params, "q", "query", "search")
    if query:
        view["query"] = query

    period = _query_param_value(params, "period", "timePeriod").upper()
    if period in {"ALL", "MONTH", "WEEK", "DAY"}:
        view["period"] = period

    order_by = _query_param_value(params, "orderBy", "sort", "rankBy").upper()
    if order_by in {"PNL", "VOL"}:
        view["rank_by"] = order_by

    rows = _query_float(params, "rows", "limit")
    if rows is not None and rows > 0:
        view["rows"] = int(rows)
    return view


def predictparity_live_trade_filter_view(params: Mapping[str, Any]) -> dict[str, Any]:
    """Translate PredictParity-style live-trade query params into local filter state."""

    view: dict[str, Any] = {}
    query = _query_param_value(params, "q", "query", "search", "wallet", "market")
    if query:
        view["query"] = query

    platforms = [item.capitalize() for item in _query_list(params, "platform", "platforms", "venue", "venues")]
    platforms = [item for item in platforms if item in {"Polymarket", "Kalshi"}]
    if platforms:
        view["platforms"] = platforms

    side_values = [item.upper() for item in _query_list(params, "side", "sides", "outcome", "outcomes")]
    sides = [item for item in side_values if item in {"BUY", "SELL", "YES", "NO"}]
    if sides:
        view["sides"] = ["yes" if item == "YES" else "no" if item == "NO" else item for item in sides]

    min_notional = _query_float(params, "minNotional", "notionalMin", "min", "amountMin")
    if min_notional is not None:
        view["min_notional"] = float(min_notional)

    rows = _query_float(params, "rows", "limit")
    if rows is not None and rows > 0:
        view["rows"] = int(rows)

    if _query_bool(params, "large", "whale", "whales", "largeOnly"):
        view["large_only"] = True
    if _query_bool(params, "trackedMarkets", "tracked_markets", "marketsTracked"):
        view["tracked_markets_only"] = True
    if _query_bool(params, "trackedWallets", "tracked_wallets", "walletsTracked"):
        view["tracked_wallets_only"] = True
    return view


def predictparity_track_filter_view(params: Mapping[str, Any]) -> dict[str, Any]:
    """Translate PredictParity-style tracking hub query params into local filter state."""

    view: dict[str, Any] = {}
    query = _query_param_value(params, "q", "query", "search", "wallet", "market")
    if query:
        view["query"] = query

    platforms = [item.capitalize() for item in _query_list(params, "platform", "platforms", "venue", "venues")]
    platforms = [item for item in platforms if item in {"Polymarket", "Kalshi"}]
    if platforms:
        view["platforms"] = platforms

    min_watch_volume = _query_float(params, "minWatchVolume", "watchVolumeMin", "minVolume", "volumeMin")
    if min_watch_volume is not None:
        view["min_watch_volume"] = float(min_watch_volume)

    rows = _query_float(params, "rows", "limit")
    if rows is not None and rows > 0:
        view["rows"] = int(rows)

    signal_value = _query_param_value(params, "signal", "marketSignal", "signalFilter").lower().replace("_", " ").replace("-", " ")
    signal_lookup = {"fast move": "Fast move", "fast": "Fast move", "mover": "Fast move", "tight spread": "Tight spread", "spread": "Tight spread", "none": "None", "any": "Any"}
    if signal_value in signal_lookup:
        view["signal_filter"] = signal_lookup[signal_value]

    min_wallet_value = _query_float(params, "minWalletValue", "walletValueMin", "minOpenValue", "openValueMin")
    if min_wallet_value is not None:
        view["min_wallet_value"] = float(min_wallet_value)
    return view


def predictparity_whale_filter_view(params: Mapping[str, Any]) -> dict[str, Any]:
    """Translate PredictParity-style whale-flow query params into local filter state."""

    view = predictparity_live_trade_filter_view(params)

    min_notional = _query_float(params, "minNotional", "notionalMin", "minPrint", "printMin", "whaleMin")
    if min_notional is not None:
        view["min_notional"] = float(min_notional)

    min_wallet_notional = _query_float(params, "minWalletNotional", "walletNotionalMin", "walletMin")
    if min_wallet_notional is not None:
        view["min_wallet_notional"] = float(min_wallet_notional)

    min_wallet_trades = _query_float(params, "minWalletTrades", "walletTradesMin", "tradesMin")
    if min_wallet_trades is not None and min_wallet_trades > 0:
        view["min_wallet_trades"] = int(min_wallet_trades)

    bias_value = _query_param_value(params, "bias", "outcomeBias", "biasFilter").lower()
    bias_lookup = {"yes": "YES", "y": "YES", "no": "NO", "n": "NO", "mixed": "Mixed", "any": "Any"}
    if bias_value in bias_lookup:
        view["bias_filter"] = bias_lookup[bias_value]

    if _query_bool(params, "trackedWallets", "tracked_wallets", "walletsTracked", "watchedWallets"):
        view["tracked_wallets_only"] = True
    return view


def predictparity_cross_venue_filter_view(params: Mapping[str, Any]) -> dict[str, Any]:
    """Translate PredictParity-style cross-venue query params into local filter state."""

    view: dict[str, Any] = {}
    query = _query_param_value(params, "q", "query", "search", "market", "event")
    if query:
        view["query"] = query

    min_similarity = _query_float(params, "minSimilarity", "similarityMin", "minSim")
    if min_similarity is not None:
        view["min_similarity"] = float(min_similarity)

    max_pairs = _query_float(params, "maxPairs", "pairs", "rows", "limit")
    if max_pairs is not None and max_pairs > 0:
        view["max_pairs"] = int(max_pairs)

    gap_cents = _query_float(params, "minGapCents", "gapCentsMin", "minGap", "gapMin")
    if gap_cents is not None:
        view["min_gap_cents"] = round(float(gap_cents * 100 if 0 < gap_cents <= 1 else gap_cents), 4)

    pm_volume = _query_float(params, "minPolymarketVolume", "pmVolumeMin", "polyVolumeMin")
    if pm_volume is not None:
        view["min_pm_volume"] = float(pm_volume)

    ks_volume = _query_float(params, "minKalshiVolume", "ksVolumeMin", "kalshiVolumeMin")
    if ks_volume is not None:
        view["min_ks_volume"] = float(ks_volume)

    lower_value = _query_param_value(params, "lower", "lowerYes", "cheaper", "cheaperVenue").lower()
    lower_lookup = {
        "polymarket": "Polymarket",
        "poly": "Polymarket",
        "pm": "Polymarket",
        "kalshi": "Kalshi",
        "ks": "Kalshi",
        "any": "Any",
    }
    if lower_value in lower_lookup:
        view["lower_filter"] = lower_lookup[lower_value]

    price_min = _percent_param(_query_float(params, "minPrice", "priceMin", "probMin"))
    price_max = _percent_param(_query_float(params, "maxPrice", "priceMax", "probMax"))
    if price_min is not None:
        view["min_price_pct"] = price_min
    if price_max is not None:
        view["max_price_pct"] = price_max
    return view


def predictparity_monitor_filter_view(params: Mapping[str, Any]) -> dict[str, Any]:
    """Translate PredictParity-style monitor query params into local filter state."""

    view: dict[str, Any] = {}
    query = _query_param_value(params, "q", "query", "search", "wallet", "market")
    if query:
        view["query"] = query

    platforms = [item.capitalize() for item in _query_list(params, "platform", "platforms", "venue", "venues")]
    platforms = [item for item in platforms if item in {"Polymarket", "Kalshi"}]
    if platforms:
        view["platforms"] = platforms

    signal_lookup = {item.lower().replace("_", " ").replace("-", " "): item for item in PREDICTPARITY_MONITOR_SIGNAL_TYPES}
    signal_types: list[str] = []
    for item in _query_list(params, "signal", "signals", "type", "types"):
        key = item.lower().replace("_", " ").replace("-", " ")
        if key in signal_lookup:
            signal_types.append(signal_lookup[key])
    if signal_types:
        view["signal_types"] = signal_types

    rows = _query_float(params, "rows", "limit")
    if rows is not None and rows > 0:
        view["rows"] = int(rows)

    if _query_bool(params, "watched", "watchedOnly", "tracked", "trackedMarkets"):
        view["watched_only"] = True

    min_volume = _query_float(params, "minVolume", "volumeMin", "volMin")
    if min_volume is not None:
        view["min_volume"] = float(min_volume)

    min_liquidity = _query_float(params, "minLiquidity", "liquidityMin", "liqMin")
    if min_liquidity is not None:
        view["min_liquidity"] = float(min_liquidity)

    min_move = _query_float(params, "minMove", "moveMin", "changeMin")
    if min_move is not None:
        view["min_move"] = round(float(min_move * 100 if 0 < min_move <= 1 else min_move), 4)

    max_spread = _query_float(params, "maxSpread", "spreadMax")
    if max_spread is not None:
        view["max_spread"] = round(float(max_spread * 100 if 0 < max_spread <= 1 else max_spread), 4)

    min_whale = _query_float(params, "minWhale", "whaleMin", "minNotional", "notionalMin")
    if min_whale is not None:
        view["min_whale"] = float(min_whale)

    ending_days = _query_float(params, "endingDays", "endDays", "maxDaysToEnd")
    if ending_days is not None and ending_days > 0:
        view["ending_days"] = int(ending_days)

    holder_checks = _query_float(params, "holderChecks", "holders")
    if holder_checks is not None:
        view["holder_checks"] = int(holder_checks)

    holder_threshold = _query_float(params, "holderThreshold", "topHolder")
    if holder_threshold is not None:
        view["holder_threshold"] = float(holder_threshold / 100 if holder_threshold > 1 else holder_threshold)
    return view


def predictparity_alert_filter_view(params: Mapping[str, Any]) -> dict[str, Any]:
    """Translate PredictParity-style alert query params into local filter state."""

    view = predictparity_monitor_filter_view(params)
    hits_only = _query_param_value(params, "hitsOnly", "hits", "rulesOnly").lower()
    if hits_only:
        view["hits_only"] = hits_only in {"1", "true", "yes", "y", "on"}
    return view


def predictparity_resolved_filter_view(params: Mapping[str, Any]) -> dict[str, Any]:
    """Translate PredictParity-style resolved-market query params into local filter state."""

    view: dict[str, Any] = {}
    query = _query_param_value(params, "q", "query", "search", "market", "event")
    if query:
        view["query"] = query

    rows = _query_float(params, "rows", "limit", "sample")
    if rows is not None and rows > 0:
        view["rows"] = int(rows)

    outcome_lookup = {
        "yes": "Yes",
        "y": "Yes",
        "true": "Yes",
        "no": "No",
        "n": "No",
        "false": "No",
        "multi": "Multi",
        "multiple": "Multi",
        "unknown": "Unknown",
    }
    outcomes: list[str] = []
    for item in _query_list(params, "outcome", "outcomes", "resolution", "resolutions"):
        key = item.lower().replace("_", " ").replace("-", " ")
        if key in outcome_lookup:
            outcomes.append(outcome_lookup[key])
    if outcomes:
        view["outcomes"] = list(dict.fromkeys(outcomes))

    decisive = _query_param_value(params, "decisiveOnly", "decisive", "decisiveResolution").lower()
    if decisive:
        view["decisive_only"] = decisive in {"1", "true", "yes", "y", "on"}

    min_volume = _query_float(params, "minVolume", "volumeMin", "volMin")
    if min_volume is not None:
        view["min_volume"] = float(min_volume)

    min_liquidity = _query_float(params, "minLiquidity", "liquidityMin", "liqMin")
    if min_liquidity is not None:
        view["min_liquidity"] = float(min_liquidity)

    categories = _query_list(params, "category", "categories")
    if categories:
        view["category_filter"] = categories

    window_value = _query_param_value(params, "closedWindow", "window", "period", "days").lower().replace(" ", "")
    window_map = {
        "7": "<7d",
        "7d": "<7d",
        "<7d": "<7d",
        "30": "<30d",
        "30d": "<30d",
        "<30d": "<30d",
        "90": "<90d",
        "90d": "<90d",
        "<90d": "<90d",
        "365": "<365d",
        "365d": "<365d",
        "1y": "<365d",
        "<365d": "<365d",
        "all": "All",
    }
    if window_value in window_map:
        view["closed_window"] = window_map[window_value]

    final_min = _percent_param(_query_float(params, "finalYesMin", "finalPriceMin", "probMin", "priceMin"))
    final_max = _percent_param(_query_float(params, "finalYesMax", "finalPriceMax", "probMax", "priceMax"))
    if final_min is not None or final_max is not None:
        view["final_yes_range"] = [final_min if final_min is not None else 0, final_max if final_max is not None else 100]

    sort = _query_param_value(params, "sort", "sortBy", "orderBy")
    sort_lookup = {
        "closed": "closed_time",
        "closedtime": "closed_time",
        "closed_time": "closed_time",
        "volume": "volume",
        "liquidity": "liquidity",
        "final": "final_yes_price",
        "finalyes": "final_yes_price",
        "final_yes": "final_yes_price",
        "final_yes_price": "final_yes_price",
        "category": "category",
    }
    sort_key = sort.lower().replace("-", "_").replace(" ", "_")
    if sort_key in sort_lookup:
        view["sort_by"] = sort_lookup[sort_key]
    return view


def predictparity_portfolio_filter_view(params: Mapping[str, Any]) -> dict[str, Any]:
    """Translate PredictParity-style portfolio query params into local filter state."""

    view: dict[str, Any] = {}
    query = _query_param_value(params, "q", "query", "search", "wallet", "market")
    if query:
        view["query"] = query

    platforms = [item.capitalize() for item in _query_list(params, "platform", "platforms", "venue", "venues")]
    platforms = [item for item in platforms if item in {"Polymarket", "Kalshi"}]
    if platforms:
        view["platforms"] = platforms

    outcome_lookup = {"yes": "Yes", "y": "Yes", "no": "No", "n": "No"}
    outcomes: list[str] = []
    for item in _query_list(params, "outcome", "outcomes", "side", "sides"):
        key = item.lower()
        if key in outcome_lookup:
            outcomes.append(outcome_lookup[key])
    if outcomes:
        view["outcomes"] = list(dict.fromkeys(outcomes))

    rows = _query_float(params, "rows", "limit")
    if rows is not None and rows > 0:
        view["rows"] = int(rows)

    min_value = _query_float(params, "minValue", "valueMin", "minPositionValue", "positionValueMin")
    if min_value is not None:
        view["min_value"] = float(min_value)

    min_pnl = _query_float(params, "minPnl", "pnlMin", "profitMin")
    if min_pnl is not None:
        view["min_pnl"] = float(min_pnl)

    source_lookup = {"research": "Research", "copy": "Copy", "copytrade": "Copy", "copy trading": "Copy", "watchlist": "Watchlist", "history": "History"}
    sources: list[str] = []
    for item in _query_list(params, "source", "sources"):
        key = item.lower().replace("_", " ").replace("-", " ")
        if key in source_lookup:
            sources.append(source_lookup[key])
    if sources:
        view["sources"] = list(dict.fromkeys(sources))

    status_values = [item.lower().replace("_", " ").replace("-", " ") for item in _query_list(params, "copyStatus", "copyStatuses", "status", "statuses")]
    copy_statuses = [item for item in status_values if item in {"copied", "settled", "skipped", "baseline", "duplicate"}]
    if copy_statuses:
        view["copy_statuses"] = list(dict.fromkeys(copy_statuses))

    losers_only = _query_param_value(params, "losersOnly", "losingOnly", "lossesOnly").lower()
    if losers_only:
        view["losers_only"] = losers_only in {"1", "true", "yes", "y", "on"}
    return view


def copy_trade_filter_view(params: Mapping[str, Any]) -> dict[str, Any]:
    """Translate paper-copy-trade query params into local filter state."""

    view: dict[str, Any] = {}
    query = _query_param_value(params, "q", "query", "search", "market", "tx", "reason")
    if query:
        view["query"] = query

    sides = [item.upper() for item in _query_list(params, "side", "sides")]
    sides = [item for item in sides if item in {"BUY", "SELL"}]
    if sides:
        view["sides"] = list(dict.fromkeys(sides))

    statuses = [item.lower().replace("_", " ").replace("-", " ") for item in _query_list(params, "status", "statuses", "copyStatus", "copyStatuses")]
    statuses = [item for item in statuses if item in {"copied", "settled", "skipped", "baseline", "duplicate"}]
    if statuses:
        view["statuses"] = list(dict.fromkeys(statuses))

    rows = _query_float(params, "rows", "limit")
    if rows is not None and rows > 0:
        view["rows"] = int(rows)

    min_tony = _query_float(params, "minTonyNotional", "tonyNotionalMin", "minSourceNotional", "sourceNotionalMin")
    if min_tony is not None:
        view["min_tony_notional"] = float(min_tony)

    min_copy = _query_float(params, "minCopyNotional", "copyNotionalMin", "minPaperNotional", "paperNotionalMin")
    if min_copy is not None:
        view["min_copy_notional"] = float(min_copy)

    min_position = _query_float(params, "minPositionValue", "positionValueMin", "minValue", "valueMin")
    if min_position is not None:
        view["min_position_value"] = float(min_position)

    min_pnl = _query_float(params, "minPnl", "pnlMin")
    if min_pnl is not None:
        view["min_pnl"] = float(min_pnl)

    reason = _query_param_value(params, "reason", "reasonQuery", "contains")
    if reason:
        view["reason_query"] = reason

    latency_only = _query_param_value(params, "latencyOnly", "latency", "measuredLatency").lower()
    if latency_only:
        view["latency_only"] = latency_only in {"1", "true", "yes", "y", "on"}
    return view


def resolve_profile_query_to_wallet(value: Any, profiles: pd.DataFrame) -> str:
    """Resolve a wallet address or exact public trader handle to a Polymarket wallet."""
    text = str(value or "").strip()
    if is_polymarket_wallet(text):
        return text
    query = normalize_profile_query(text)
    if not query or profiles.empty or "wallet" not in profiles:
        return ""

    frame = profiles.copy()
    wallet = frame["wallet"].astype(str).str.strip()
    wallet_match = wallet.str.lower().eq(query)
    if wallet_match.any():
        match = wallet[wallet_match].iloc[0]
        return match if is_polymarket_wallet(match) else ""

    handle_columns = [column for column in ("trader", "userName", "x_username", "xUsername") if column in frame]
    for column in handle_columns:
        values = frame[column].astype(str).str.strip().str.lstrip("@").str.lower()
        matches = values.eq(query)
        if matches.any():
            match = wallet[matches].iloc[0]
            return match if is_polymarket_wallet(match) else ""
    return ""


def _short_identity(value: Any, width: int = 6) -> str:
    text = str(value or "").strip()
    if len(text) <= width * 2 + 3:
        return text
    return f"{text[:width]}...{text[-width:]}"


def _money_label(value: Any) -> str:
    amount = _num(value, 0.0) or 0.0
    return f"${amount:,.0f}" if abs(amount) >= 100 else f"${amount:,.2f}"


def trade_direction(side: Any, outcome: Any) -> str:
    """Normalize a binary-market fill into the direction it expresses."""
    side_text = str(side or "").strip().lower()
    outcome_text = str(outcome or "").strip().lower()
    if outcome_text not in {"yes", "no"}:
        return str(outcome or "").strip() or "-"
    if side_text == "sell":
        return "No" if outcome_text == "yes" else "Yes"
    return "Yes" if outcome_text == "yes" else "No"


def prepare_recent_trade_actions(
    trades: pd.DataFrame,
    limit: int = 120,
    now: Any | None = None,
) -> pd.DataFrame:
    """Add inspect/action fields for market recent-trade rows."""
    columns = [
        "time",
        "time_utc",
        "age_min",
        "trader",
        "trader_display",
        "wallet",
        "valid_wallet",
        "side",
        "outcome",
        "direction",
        "directional_share",
        "wallet_market_trades",
        "wallet_market_notional",
        "trader_badge",
        "title",
        "price",
        "size",
        "notional",
        "market_key",
        "transaction_hash",
        "tx_url",
        "wallet_url",
        "url",
        "action_label",
    ]
    if trades.empty:
        return pd.DataFrame(columns=columns)

    frame = trades.head(max(0, int(limit))).copy()
    for col, default in {
        "trader": "",
        "wallet": "",
        "side": "",
        "outcome": "",
        "title": "",
        "price": 0.0,
        "size": 0.0,
        "notional": 0.0,
        "market_key": "",
        "transaction_hash": "",
        "url": "",
    }.items():
        if col not in frame:
            frame[col] = default
    if "time" not in frame:
        frame["time"] = pd.NaT

    times = pd.to_datetime(frame["time"], utc=True, errors="coerce")
    now_ts = pd.Timestamp.now(tz="UTC") if now is None else pd.Timestamp(now)
    if now_ts.tzinfo is None:
        now_ts = now_ts.tz_localize("UTC")
    else:
        now_ts = now_ts.tz_convert("UTC")
    age_min = (now_ts - times).dt.total_seconds() / 60

    frame["time_utc"] = times.dt.strftime("%Y-%m-%d %H:%M:%S").fillna("-")
    frame["age_min"] = age_min.where(age_min >= 0)
    wallet = frame["wallet"].astype(str).str.strip()
    trader = frame["trader"].astype(str).str.strip()
    frame["trader_display"] = trader.where(trader.str.len() > 0, wallet.map(_short_identity))
    frame["valid_wallet"] = wallet.map(is_polymarket_wallet)
    frame["tx_url"] = frame["transaction_hash"].map(polygonscan_tx_url)
    frame["wallet_url"] = wallet.map(polymarket_profile_url)
    frame["direction"] = frame.apply(lambda item: trade_direction(item.get("side"), item.get("outcome")), axis=1)
    frame["notional"] = pd.to_numeric(frame["notional"], errors="coerce").fillna(0.0)

    known_wallets = wallet.where(wallet.str.len() > 0, "unknown")
    wallet_totals = frame.groupby(known_wallets)["notional"].transform("sum").replace({0: pd.NA})
    wallet_trades = frame.groupby(known_wallets)["notional"].transform("size")
    directional_totals = frame.groupby([known_wallets, frame["direction"].astype(str)])["notional"].transform("sum")
    frame["directional_share"] = (directional_totals / wallet_totals).fillna(0.0).clip(lower=0.0, upper=1.0)
    frame["wallet_market_trades"] = pd.to_numeric(wallet_trades, errors="coerce").fillna(0).astype("int64")
    frame["wallet_market_notional"] = wallet_totals.fillna(0.0)
    frame["trader_badge"] = frame.apply(
        lambda item: f"{float(item.get('directional_share') or 0.0) * 100:.0f}% {item.get('trader_display', 'Unknown')}",
        axis=1,
    )

    labels: list[str] = []
    for idx, item in frame.reset_index(drop=True).iterrows():
        trader_name = str(item.get("trader_badge", "") or item.get("trader_display", "") or "Unknown")
        side = str(item.get("side", "") or "-")
        outcome = str(item.get("outcome", "") or "-")
        title = str(item.get("title", "") or "")[:72]
        labels.append(f"{idx + 1}. {trader_name} | {side} {outcome} | {_money_label(item.get('notional'))} | {title}")
    frame["action_label"] = labels
    return frame[[c for c in columns if c in frame.columns]].reset_index(drop=True)


def market_quick_trade_ticket(row: Mapping[str, Any] | pd.Series, outcome: str = "Yes") -> dict[str, Any]:
    """Build a compact paper-ticket payload from a market row."""
    selected_outcome = "No" if str(outcome or "").strip().lower() == "no" else "Yes"
    yes_price = _num(row.get("yes_price"), 0.0) or 0.0
    no_price = _num(row.get("no_price"), None)
    if no_price is None:
        no_price = (1 - yes_price) if yes_price > 0 else 0.0
    return {
        "platform": str(row.get("platform", "")),
        "market_key": str(row.get("market_key") or row.get("ticker") or row.get("title") or ""),
        "ticker": str(row.get("ticker", "")),
        "title": str(row.get("title", "")),
        "url": str(row.get("url", "")),
        "yes_price": float(yes_price),
        "no_price": float(no_price),
        "default_outcome": selected_outcome,
    }


def get_polymarket_leaderboard(
    limit: int = 100,
    time_period: str = "ALL",
    order_by: str = "PNL",
) -> pd.DataFrame:
    params = {"limit": limit, "timePeriod": time_period, "orderBy": order_by}
    data = _get_json(f"{POLY_DATA}/v1/leaderboard", params=params)
    df = pd.DataFrame(data if isinstance(data, list) else data.get("data", []))
    if df.empty:
        return pd.DataFrame()
    df["platform"] = "Polymarket"
    df["rank"] = pd.to_numeric(df.get("rank"), errors="coerce")
    df["wallet"] = df.get("proxyWallet", "")
    df["trader"] = df.get("userName", "").where(df.get("userName", "") != "", df["wallet"].astype(str).str.slice(0, 10))
    df["pnl"] = pd.to_numeric(df.get("pnl"), errors="coerce").fillna(0.0)
    df["volume"] = pd.to_numeric(df.get("vol"), errors="coerce").fillna(0.0)
    df["x_username"] = df.get("xUsername", "")
    df["verified"] = df.get("verifiedBadge", False)
    cols = ["rank", "platform", "trader", "wallet", "pnl", "volume", "x_username", "verified", "profileImage"]
    return df[[c for c in cols if c in df.columns]].sort_values("rank").reset_index(drop=True)


def get_predictparity_traders(
    limit: int = 100,
    offset: int = 0,
    sort_by: str = "pnl",
    sort_order: str = "desc",
    search: str = "",
    min_active_positions: float = 0.0,
    platform: str = "polymarket",
) -> pd.DataFrame:
    """Return PredictParity's public trader leaderboard rows."""

    clean_sort = str(sort_by or "pnl").strip().lower()
    if clean_sort in {"vol", "volume", "alltimevolume"}:
        clean_sort = "volume"
    elif clean_sort not in {"pnl", "volume"}:
        clean_sort = "pnl"
    clean_order = "asc" if str(sort_order or "").strip().lower() == "asc" else "desc"
    variables: dict[str, Any] = {
        "limit": max(1, int(limit)),
        "offset": max(0, int(offset)),
        "sortBy": clean_sort,
        "sortOrder": clean_order,
        "filtersInput": {
            "minActivePositions": max(0.0, float(min_active_positions)),
            "platforms": [str(platform or "polymarket").lower()],
        },
    }
    if str(search or "").strip():
        variables["search"] = str(search or "").strip()
    query = """
    query GetTraders($limit: Int, $offset: Int, $sortBy: String, $sortOrder: String, $search: String, $filtersInput: TraderFiltersInput) {
      traders(
        limit: $limit
        offset: $offset
        sortBy: $sortBy
        sortOrder: $sortOrder
        search: $search
        filtersInput: $filtersInput
      ) {
        data {
          id
          platform
          platformId
          username
          displayName
          customDisplayName
          profileImageUrl
          isVerified
          socialTwitter
          badges {
            isBot
            activePositionsCount
            assetLevelMicrodollars
            pnlLevelMicrodollars
          }
          analytics {
            allTimeVolume
            allTimePnl
            rank
          }
          onchain {
            usdcBalance
            accountAgeDays
          }
          traits {
            winRate { percentage }
            activePositions { microdollars }
            usdcBalanceMicrodollars
          }
        }
        hasMore
      }
    }
    """
    response = _post_json(
        PREDICTPARITY_API,
        {"operationName": "GetTraders", "variables": variables, "query": query},
        params={"op": "GetTraders"},
    )
    rows = ((((response or {}).get("data") or {}).get("traders") or {}).get("data") or [])
    normalized: list[dict[str, Any]] = []
    for item in rows:
        if not isinstance(item, Mapping):
            continue
        analytics = item.get("analytics") or {}
        onchain = item.get("onchain") or {}
        traits = item.get("traits") or {}
        badges = item.get("badges") or {}
        active = traits.get("activePositions") or {}
        wallet = str(item.get("platformId") or "")
        platform_name = str(item.get("platform") or platform or "polymarket")
        display_name = str(item.get("customDisplayName") or item.get("displayName") or item.get("username") or "")
        normalized.append(
            {
                "parity_id": item.get("id") or "",
                "rank": int(_num(analytics.get("rank"), len(normalized) + 1) or len(normalized) + 1),
                "platform": "Polymarket" if platform_name.lower() == "polymarket" else platform_name.title(),
                "username": str(item.get("username") or ""),
                "trader": display_name or _short_identity(wallet),
                "wallet": wallet,
                "pnl": _num(analytics.get("allTimePnl"), 0.0) or 0.0,
                "volume": _num(analytics.get("allTimeVolume"), 0.0) or 0.0,
                "x_username": str(item.get("socialTwitter") or ""),
                "verified": bool(item.get("isVerified") or badges.get("verified") or False),
                "profileImage": str(item.get("profileImageUrl") or ""),
                "win_rate": (_num((traits.get("winRate") or {}).get("percentage")) or 0.0) / 100.0,
                "positions_value": (_num(active.get("microdollars"), 0.0) or 0.0) / 1_000_000.0,
                "open_positions": int(_num(badges.get("activePositionsCount"), 0.0) or 0),
                "open_markets": int(_num(badges.get("activePositionsCount"), 0.0) or 0),
                "cash_balance": _num(onchain.get("usdcBalance"))
                if _num(onchain.get("usdcBalance")) is not None
                else (_num(traits.get("usdcBalanceMicrodollars"), 0.0) or 0.0) / 1_000_000.0,
                "account_age_days": _num(onchain.get("accountAgeDays")),
                "is_bot": bool(badges.get("isBot") or False),
                "source": "PredictParity",
            }
        )
    frame = pd.DataFrame(normalized)
    if frame.empty:
        return frame
    frame["assets_value"] = pd.to_numeric(frame["positions_value"], errors="coerce").fillna(0.0) + pd.to_numeric(
        frame["cash_balance"], errors="coerce"
    ).fillna(0.0)
    sort_column = "volume" if clean_sort == "volume" else "pnl"
    return frame.sort_values(sort_column, ascending=clean_order == "asc").reset_index(drop=True)


def get_predictparity_trader_profile(identifier: str, platform: str = "polymarket") -> dict[str, Any]:
    """Return public PredictParity trader-profile metrics for parity display."""

    clean_identifier = str(identifier or "").strip()
    if not clean_identifier:
        return {}
    resolve_payload = {
        "operationName": "ResolveTrader",
        "variables": {"identifier": clean_identifier, "platform": platform},
        "query": (
            "query ResolveTrader($identifier: String!, $platform: Platform) { "
            "resolveTrader(identifier: $identifier, platform: $platform) { id platform } }"
        ),
    }
    resolved = _post_json(PREDICTPARITY_API, resolve_payload, params={"op": "ResolveTrader"})
    trader_id = (((resolved or {}).get("data") or {}).get("resolveTrader") or {}).get("id")
    if not trader_id:
        return {}

    trader_query = """
    query GetTrader($id: ID!) {
      trader(id: $id) {
        id
        platform
        platformId
        username
        displayName
        platformAccountCreatedAt
        lastSyncedAt
        analytics { allTimeVolume allTimePnl rank }
        onchain {
          usdcBalance
          firstTransactionDate
          firstFundingAmount
          firstFundingSource
          firstFundingTxHash
          accountAgeDays
        }
        traits {
          winRate { percentage }
          activePositions { microdollars }
          usdcBalanceMicrodollars
        }
      }
    }
    """
    profile = _post_json(
        PREDICTPARITY_API,
        {"operationName": "GetTrader", "variables": {"id": trader_id}, "query": trader_query},
        params={"op": "GetTrader"},
    )
    trader = ((profile or {}).get("data") or {}).get("trader") or {}
    if not trader:
        return {}
    analytics = trader.get("analytics") or {}
    onchain = trader.get("onchain") or {}
    traits = trader.get("traits") or {}
    active = traits.get("activePositions") or {}
    return {
        "id": trader.get("id") or trader_id,
        "platform": trader.get("platform") or platform,
        "wallet": trader.get("platformId") or "",
        "username": trader.get("username") or "",
        "display_name": trader.get("displayName") or trader.get("username") or "",
        "account_created_at": _safe_ts(trader.get("platformAccountCreatedAt")),
        "last_synced_at": _safe_ts(trader.get("lastSyncedAt")),
        "all_time_volume": _num(analytics.get("allTimeVolume"), 0.0) or 0.0,
        "all_time_pnl": _num(analytics.get("allTimePnl"), 0.0) or 0.0,
        "rank": int(_num(analytics.get("rank"), 0.0) or 0),
        "usdc_balance": _num(onchain.get("usdcBalance")),
        "first_transaction_date": _safe_ts(onchain.get("firstTransactionDate")),
        "first_funding_amount": _num(onchain.get("firstFundingAmount")),
        "first_funding_source": str(onchain.get("firstFundingSource") or ""),
        "first_funding_tx_hash": str(onchain.get("firstFundingTxHash") or ""),
        "account_age_days": _num(onchain.get("accountAgeDays")),
        "win_rate": (_num((traits.get("winRate") or {}).get("percentage")) or 0.0) / 100.0,
        "active_positions_value": (_num(active.get("microdollars"), 0.0) or 0.0) / 1_000_000.0,
        "usdc_balance_from_traits": (_num(traits.get("usdcBalanceMicrodollars"), 0.0) or 0.0) / 1_000_000.0,
    }


def get_predictparity_trader_pnl_chart(trader_id: str, window: str = "1w") -> pd.DataFrame:
    """Return PredictParity's public trader PnL chart points."""

    clean_id = str(trader_id or "").strip()
    if not clean_id:
        return pd.DataFrame(columns=["time", "pnl", "series", "source"])
    range_value = str(window or "1w")
    if range_value.casefold() == "all":
        range_value = "all"
    if range_value not in {"1d", "1w", "1mo", "all"}:
        range_value = "1w"
    chart_query = """
    query GetTraderPnlChart($traderId: ID!, $range: String) {
      traderPnlChart(traderId: $traderId, range: $range) {
        range
        dataPoints {
          timestamp
          totalPnl
        }
      }
    }
    """
    response = _post_json(
        PREDICTPARITY_API,
        {
            "operationName": "GetTraderPnlChart",
            "variables": {"traderId": clean_id, "range": range_value},
            "query": chart_query,
        },
        params={"op": "GetTraderPnlChart"},
    )
    chart = (((response or {}).get("data") or {}).get("traderPnlChart") or {})
    points = chart.get("dataPoints") or []
    rows: list[dict[str, Any]] = []
    for point in points:
        if not isinstance(point, Mapping):
            continue
        rows.append(
            {
                "time": _safe_ts(point.get("timestamp")),
                "pnl": _num(point.get("totalPnl"), 0.0) or 0.0,
                "series": "Total PnL",
                "source": "PredictParity",
            }
        )
    frame = pd.DataFrame(rows, columns=["time", "pnl", "series", "source"])
    if frame.empty:
        return frame
    frame = frame.dropna(subset=["time"]).sort_values("time").reset_index(drop=True)
    return frame


def merge_profile_position_values(profiles: pd.DataFrame, position_values: pd.DataFrame) -> pd.DataFrame:
    """Attach open-position value columns to profile search/leaderboard rows."""

    if profiles.empty:
        return profiles.copy()
    frame = profiles.copy()
    defaults: dict[str, float | int] = {"positions_value": 0.0, "open_positions": 0, "open_markets": 0}
    if position_values.empty or "wallet" not in frame or "wallet" not in position_values:
        for column, default in defaults.items():
            if column not in frame:
                frame[column] = default
        return frame
    values = position_values[["wallet", *[column for column in defaults if column in position_values]]].copy()
    values["wallet_key"] = values["wallet"].astype(str).str.lower()
    values = values.drop_duplicates("wallet_key").drop(columns=["wallet"], errors="ignore")
    frame["wallet_key"] = frame["wallet"].astype(str).str.lower()
    frame = frame.merge(values, on="wallet_key", how="left", suffixes=("", "_fetched")).drop(columns=["wallet_key"], errors="ignore")
    for column, default in defaults.items():
        fetched = f"{column}_fetched"
        if fetched in frame:
            if column in frame:
                frame[column] = frame[fetched].combine_first(frame[column])
            else:
                frame[column] = frame[fetched]
            frame = frame.drop(columns=[fetched])
        if column not in frame:
            frame[column] = default
        frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(default)
    return frame


def wallet_profile_tab_labels(
    open_positions: pd.DataFrame,
    closed_positions: pd.DataFrame,
    trades: pd.DataFrame,
    activity: pd.DataFrame,
    cap: int = 100,
) -> list[str]:
    """Return PredictParity-style wallet profile tab labels with compact counts."""

    def label_count(value: int) -> str:
        count = max(0, int(value))
        return f"{cap}+" if cap > 0 and count >= cap else f"{count}"

    total_positions = len(open_positions) + len(closed_positions)
    return [
        f"POSITIONS ({label_count(total_positions)})",
        "Insights",
        f"Active positions ({label_count(len(open_positions))})",
        f"Closed positions ({label_count(len(closed_positions))})",
        f"Trades ({label_count(len(trades))})",
        f"ACTIVITY ({label_count(len(activity))})",
    ]


def wallet_position_status_value(status: Any) -> str:
    """Map Parity-facing wallet position statuses onto local row statuses."""

    text = str(status or "").strip().casefold()
    if text in {"active", "open"}:
        return "Open"
    if text == "closed":
        return "Closed"
    return "All"


def filter_wallet_positions_by_status(positions: pd.DataFrame, status: Any) -> pd.DataFrame:
    """Filter combined wallet positions by a PredictParity-style status label."""

    if positions.empty or "status" not in positions:
        return positions.copy()
    value = wallet_position_status_value(status)
    if value == "All":
        return positions.copy()
    return positions[positions["status"].astype(str).eq(value)].copy()


def market_calendar_days(
    markets: pd.DataFrame,
    month: Any | None = None,
    top_per_day: int = 5,
) -> pd.DataFrame:
    """Build a Monday-first month grid with top expiring markets per day."""

    columns = [
        "date",
        "day",
        "week",
        "weekday",
        "is_current_month",
        "markets",
        "volume",
        "median_prob",
        "top_markets",
        "more_count",
    ]
    month_ts = pd.Timestamp.now(tz="UTC") if month is None else pd.Timestamp(month)
    if month_ts.tzinfo is None:
        month_ts = month_ts.tz_localize("UTC")
    else:
        month_ts = month_ts.tz_convert("UTC")
    month_start = month_ts.replace(day=1).normalize()
    _, days_in_month = calendar_lib.monthrange(int(month_start.year), int(month_start.month))
    month_end = month_start.replace(day=days_in_month)
    grid_start = month_start - pd.Timedelta(days=int(month_start.weekday()))
    grid_end = month_end + pd.Timedelta(days=int(6 - month_end.weekday()))

    frame = markets.copy() if not markets.empty else pd.DataFrame()
    if not frame.empty:
        if "end_time" not in frame:
            frame["end_time"] = pd.NaT
        frame["_calendar_date"] = pd.to_datetime(frame["end_time"], utc=True, errors="coerce").dt.date
        for column in ("activity_volume", "volume_24h", "volume", "yes_price"):
            if column not in frame:
                frame[column] = 0.0
            frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0.0)
        sort_volume_col = "activity_volume" if "activity_volume" in frame else "volume_24h"
        frame = frame.sort_values(sort_volume_col, ascending=False, na_position="last")

    rows: list[dict[str, Any]] = []
    current = grid_start
    week = 0
    while current <= grid_end:
        day_date = current.date()
        day_markets = frame[frame["_calendar_date"].eq(day_date)] if not frame.empty else pd.DataFrame()
        top_rows: list[dict[str, Any]] = []
        if not day_markets.empty:
            for _, market in day_markets.head(max(0, int(top_per_day))).iterrows():
                top_rows.append(
                    {
                        "platform": str(market.get("platform", "")),
                        "title": str(market.get("title", "")),
                        "market_key": str(market.get("market_key", "") or market.get("ticker", "")),
                        "url": str(market.get("url", "")),
                        "yes_price": float(market.get("yes_price", 0.0) or 0.0),
                        "volume": float(market.get("activity_volume", market.get("volume_24h", market.get("volume", 0.0))) or 0.0),
                    }
                )
        rows.append(
            {
                "date": day_date.isoformat(),
                "day": int(current.day),
                "week": week,
                "weekday": int(current.weekday()),
                "is_current_month": current.month == month_start.month,
                "markets": int(len(day_markets)),
                "volume": float(day_markets["activity_volume"].sum()) if not day_markets.empty else 0.0,
                "median_prob": float(day_markets["yes_price"].median()) if not day_markets.empty else float("nan"),
                "top_markets": top_rows,
                "more_count": max(0, int(len(day_markets) - len(top_rows))),
            }
        )
        current += pd.Timedelta(days=1)
        if int(current.weekday()) == 0:
            week += 1

    return pd.DataFrame(rows, columns=columns)


def get_polymarket_positions(user: str, limit: int = 250) -> pd.DataFrame:
    if not user:
        return pd.DataFrame()
    data = _get_json(f"{POLY_DATA}/positions", params={"user": user, "limit": limit})
    df = pd.DataFrame(data if isinstance(data, list) else data.get("data", []))
    if df.empty:
        return pd.DataFrame()
    df["platform"] = "Polymarket"
    df["wallet"] = df.get("proxyWallet", user)
    df["title"] = df.get("title", "")
    df["outcome"] = df.get("outcome", "")
    df["asset"] = df.get("asset", "")
    df["size"] = pd.to_numeric(df.get("size", df.get("amount", 0)), errors="coerce").fillna(0.0)
    df["avg_price"] = pd.to_numeric(df.get("avgPrice", 0), errors="coerce").fillna(0.0)
    df["current_price"] = pd.to_numeric(df.get("curPrice", df.get("currentPrice", 0)), errors="coerce").fillna(0.0)
    df["value"] = pd.to_numeric(df.get("currentValue", df.get("value", df["size"] * df["current_price"])), errors="coerce").fillna(0.0)
    df["initial_value"] = df["size"] * df["avg_price"]
    df["unrealized_pnl"] = df["value"] - df["initial_value"]
    df["pnl_pct"] = df["unrealized_pnl"] / df["initial_value"].replace({0: pd.NA})
    df["end_time"] = pd.to_datetime(df.get("endDate"), utc=True, errors="coerce")
    df["market_key"] = df.get("conditionId", "")
    df["slug"] = df.get("slug", "")
    df["url"] = "https://polymarket.com/event/" + df.get("eventSlug", df["slug"]).fillna(df["slug"]).astype(str)
    cols = [
        "platform",
        "wallet",
        "title",
        "outcome",
        "asset",
        "size",
        "avg_price",
        "current_price",
        "value",
        "unrealized_pnl",
        "pnl_pct",
        "end_time",
        "market_key",
        "url",
    ]
    return df[[c for c in cols if c in df.columns]].sort_values("value", ascending=False).reset_index(drop=True)


def get_polymarket_closed_positions(user: str, limit: int = 250) -> pd.DataFrame:
    if not user:
        return pd.DataFrame()
    data = _get_json(f"{POLY_DATA}/closed-positions", params={"user": user, "limit": limit})
    df = pd.DataFrame(data if isinstance(data, list) else data.get("data", []))
    if df.empty:
        return pd.DataFrame()
    df["platform"] = "Polymarket"
    df["wallet"] = df.get("proxyWallet", user)
    df["title"] = df.get("title", "")
    df["outcome"] = df.get("outcome", "")
    df["avg_price"] = pd.to_numeric(df.get("avgPrice", 0), errors="coerce").fillna(0.0)
    df["current_price"] = pd.to_numeric(df.get("curPrice", 0), errors="coerce").fillna(0.0)
    df["total_bought"] = pd.to_numeric(df.get("totalBought", 0), errors="coerce").fillna(0.0)
    df["realized_pnl"] = pd.to_numeric(df.get("realizedPnl", 0), errors="coerce").fillna(0.0)
    df["time"] = pd.to_datetime(df.get("timestamp"), unit="s", utc=True, errors="coerce")
    df["market_key"] = df.get("conditionId", "")
    df["slug"] = df.get("slug", "")
    df["url"] = "https://polymarket.com/event/" + df.get("eventSlug", df["slug"]).fillna(df["slug"]).astype(str)
    cols = [
        "platform",
        "wallet",
        "time",
        "title",
        "outcome",
        "avg_price",
        "current_price",
        "total_bought",
        "realized_pnl",
        "market_key",
        "url",
    ]
    return df[[c for c in cols if c in df.columns]].sort_values("realized_pnl", ascending=False).reset_index(drop=True)


def get_polymarket_activity(user: str, limit: int = 250, offset: int = 0) -> pd.DataFrame:
    if not user:
        return pd.DataFrame()
    data = _get_json(f"{POLY_DATA}/activity", params={"user": user, "limit": limit, "offset": offset})
    df = pd.DataFrame(data if isinstance(data, list) else data.get("data", []))
    if df.empty:
        return pd.DataFrame()
    df["platform"] = "Polymarket"
    df["time"] = pd.to_datetime(df.get("timestamp"), unit="s", utc=True, errors="coerce")
    df["notional"] = pd.to_numeric(df.get("usdcSize", df.get("size", 0)), errors="coerce").fillna(0.0)
    df["price"] = pd.to_numeric(df.get("price", 0), errors="coerce").fillna(0.0)
    df["size"] = pd.to_numeric(df.get("size", 0), errors="coerce").fillna(0.0)
    df["title"] = df.get("title", "")
    df["type"] = df.get("type", "")
    df["side"] = df.get("side", "")
    df["outcome"] = df.get("outcome", "")
    df["wallet"] = df.get("proxyWallet", user)
    df["trader"] = df.get("name", "").where(df.get("name", "") != "", df.get("pseudonym", ""))
    df["market_key"] = df.get("conditionId", "")
    df["asset"] = df.get("asset", "")
    df["slug"] = df.get("slug", "")
    df["event_slug"] = df.get("eventSlug", df["slug"])
    df["url"] = "https://polymarket.com/event/" + df["event_slug"].fillna(df["slug"]).astype(str)
    df["type_code"] = "[" + df["type"].fillna("").astype(str).str[:1].str.upper().replace("", "?") + "]"
    cols = [
        "platform",
        "time",
        "type",
        "type_code",
        "side",
        "outcome",
        "title",
        "price",
        "size",
        "notional",
        "wallet",
        "trader",
        "market_key",
        "asset",
        "slug",
        "url",
        "transactionHash",
    ]
    return df[[c for c in cols if c in df.columns]].sort_values("time", ascending=False).reset_index(drop=True)


def get_polymarket_holders(market: str, limit: int = 100) -> pd.DataFrame:
    if not market:
        return pd.DataFrame()
    try:
        data = _get_json(f"{POLY_DATA}/holders", params={"market": market, "limit": limit})
    except MarketDataError:
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    for token_group in data if isinstance(data, list) else []:
        for holder in token_group.get("holders", []) or []:
            rows.append(
                {
                    "wallet": holder.get("proxyWallet", ""),
                    "trader": _first_nonempty(holder.get("name"), holder.get("pseudonym"), holder.get("proxyWallet", "")),
                    "outcome_index": holder.get("outcomeIndex"),
                    "amount": dollars(holder.get("amount")),
                    "asset": holder.get("asset", token_group.get("token", "")),
                    "verified": holder.get("verified", False),
                }
            )
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("amount", ascending=False).reset_index(drop=True)
    return df


def get_polymarket_market_positions(
    market: str,
    status: str = "ALL",
    sort_by: str = "TOTAL_PNL",
    sort_direction: str = "DESC",
    limit: int = 100,
    offset: int = 0,
) -> pd.DataFrame:
    """Fetch PredictParity-style top market positions grouped by outcome.

    Polymarket's v1 market-positions endpoint returns current and historical
    participants for one condition ID, including realized, unrealized, and total
    PnL fields. That makes it a better top-trader source than recent tape alone.
    """

    columns = [
        "wallet",
        "trader",
        "asset",
        "market_key",
        "outcome",
        "outcome_index",
        "status",
        "avg_price",
        "size",
        "current_price",
        "current_value",
        "cash_pnl",
        "realized_pnl",
        "total_pnl",
        "total_bought",
        "verified",
        "profile_image",
    ]
    if not market:
        return pd.DataFrame(columns=columns)

    status = str(status or "ALL").upper()
    if status not in {"OPEN", "CLOSED", "ALL"}:
        status = "ALL"
    sort_by = str(sort_by or "TOTAL_PNL").upper()
    if sort_by not in {"TOKENS", "CASH_PNL", "REALIZED_PNL", "TOTAL_PNL"}:
        sort_by = "TOTAL_PNL"
    sort_direction = str(sort_direction or "DESC").upper()
    if sort_direction not in {"ASC", "DESC"}:
        sort_direction = "DESC"

    params = {
        "market": market,
        "status": status,
        "sortBy": sort_by,
        "sortDirection": sort_direction,
        "limit": max(0, min(int(limit), 500)),
        "offset": max(0, int(offset)),
    }
    try:
        data = _get_json(f"{POLY_DATA}/v1/market-positions", params=params)
    except MarketDataError:
        return pd.DataFrame(columns=columns)

    groups = data if isinstance(data, list) else data.get("data", []) if isinstance(data, dict) else []
    rows: list[dict[str, Any]] = []
    for token_group in groups:
        token = str(token_group.get("token", "") or "") if isinstance(token_group, dict) else ""
        positions = token_group.get("positions", []) if isinstance(token_group, dict) else []
        for position in positions or []:
            if not isinstance(position, dict):
                continue
            size = dollars(position.get("size"))
            rows.append(
                {
                    "wallet": position.get("proxyWallet", ""),
                    "trader": _first_nonempty(position.get("name"), position.get("pseudonym"), position.get("proxyWallet", "")),
                    "asset": str(position.get("asset", token) or token),
                    "market_key": position.get("conditionId", market),
                    "outcome": str(position.get("outcome", "") or ""),
                    "outcome_index": position.get("outcomeIndex"),
                    "status": "Active" if size > 0.01 else "Closed",
                    "avg_price": cents(position.get("avgPrice")),
                    "size": size,
                    "current_price": cents(position.get("currPrice")),
                    "current_value": dollars(position.get("currentValue")),
                    "cash_pnl": dollars(position.get("cashPnl")),
                    "realized_pnl": dollars(position.get("realizedPnl")),
                    "total_pnl": dollars(position.get("totalPnl")),
                    "total_bought": dollars(position.get("totalBought")),
                    "verified": bool(position.get("verified", False)),
                    "profile_image": str(position.get("profileImage", "") or ""),
                }
            )

    df = pd.DataFrame(rows, columns=columns)
    if df.empty:
        return pd.DataFrame(columns=columns)
    sort_map = {
        "TOKENS": "size",
        "CASH_PNL": "cash_pnl",
        "REALIZED_PNL": "realized_pnl",
        "TOTAL_PNL": "total_pnl",
    }
    sort_col = sort_map.get(sort_by, "total_pnl")
    df[sort_col] = pd.to_numeric(df[sort_col], errors="coerce").fillna(0.0)
    return df.sort_values(sort_col, ascending=sort_direction == "ASC").reset_index(drop=True)


def enrich_market_holders(
    holders: pd.DataFrame,
    trades: pd.DataFrame,
    yes_price: Any,
    no_price: Any,
) -> pd.DataFrame:
    """Add PredictParity-style holder metrics from public holder and trade data."""

    if holders.empty:
        return holders
    df = holders.copy()
    if "outcome" not in df:
        df["outcome"] = ""
    df["wallet_key"] = df.get("wallet", pd.Series("", index=df.index)).astype(str).str.lower()
    amount_source = df["amount"] if "amount" in df else pd.Series(0.0, index=df.index)
    df["shares"] = pd.to_numeric(amount_source, errors="coerce").fillna(0.0)
    yes = cents(yes_price)
    no = cents(no_price)
    df["current_price"] = df["outcome"].map({"Yes": yes, "No": no}).fillna(0.0)
    df["value"] = df["shares"] * df["current_price"]
    df["avg_price_est"] = pd.NA
    df["cost_basis_est"] = pd.NA
    df["unrealized_pnl_est"] = pd.NA
    df["pnl_pct_est"] = pd.NA
    df["activity_side"] = ""
    df["activity_size"] = 0.0
    df["activity_time"] = pd.NaT
    df["activity"] = ""

    if not trades.empty and {"wallet", "outcome", "size", "price"}.issubset(trades.columns):
        tape = trades.copy()
        tape["wallet_key"] = tape["wallet"].astype(str).str.lower()
        tape["outcome"] = tape["outcome"].astype(str)
        tape["size"] = pd.to_numeric(tape["size"], errors="coerce").fillna(0.0)
        tape["price"] = pd.to_numeric(tape["price"], errors="coerce").fillna(0.0)
        tape["side"] = tape.get("side", pd.Series("", index=tape.index)).astype(str).str.upper()
        time_source = tape["time"] if "time" in tape else pd.Series(pd.NaT, index=tape.index)
        tape["time"] = pd.to_datetime(time_source, utc=True, errors="coerce")
        buys = tape[tape["side"].eq("BUY") & (tape["size"] > 0) & (tape["price"] > 0)].copy()
        if not buys.empty:
            buys["weighted_cost"] = buys["size"] * buys["price"]
            avg = buys.groupby(["wallet_key", "outcome"], as_index=False).agg(
                buy_size=("size", "sum"),
                weighted_cost=("weighted_cost", "sum"),
            )
            avg["avg_price_est"] = avg["weighted_cost"] / avg["buy_size"].replace({0: pd.NA})
            df = df.merge(avg[["wallet_key", "outcome", "avg_price_est"]], on=["wallet_key", "outcome"], how="left", suffixes=("", "_trade"))
            df["avg_price_est"] = df["avg_price_est_trade"].combine_first(df["avg_price_est"])
            df = df.drop(columns=["avg_price_est_trade"], errors="ignore")

        latest = (
            tape.sort_values("time", ascending=False, na_position="last")
            .drop_duplicates(["wallet_key", "outcome"])
            [["wallet_key", "outcome", "side", "size", "time"]]
            .rename(columns={"side": "activity_side", "size": "activity_size", "time": "activity_time"})
        )
        if not latest.empty:
            df = df.merge(latest, on=["wallet_key", "outcome"], how="left", suffixes=("", "_latest"))
            df["activity_side"] = df["activity_side_latest"].combine_first(df["activity_side"])
            df["activity_size"] = df["activity_size_latest"].combine_first(df["activity_size"])
            df["activity_time"] = df["activity_time_latest"].combine_first(df["activity_time"])
            df = df.drop(columns=["activity_side_latest", "activity_size_latest", "activity_time_latest"], errors="ignore")

    avg_price = pd.to_numeric(df["avg_price_est"], errors="coerce")
    df["cost_basis_est"] = df["shares"] * avg_price
    df["unrealized_pnl_est"] = df["value"] - df["cost_basis_est"]
    df["pnl_pct_est"] = df["unrealized_pnl_est"] / df["cost_basis_est"].replace({0: pd.NA})
    activity_size = pd.to_numeric(df["activity_size"], errors="coerce").fillna(0.0)
    df["activity"] = df["activity_side"].fillna("").astype(str).str.title()
    df.loc[activity_size > 0, "activity"] = df.loc[activity_size > 0, "activity"] + " " + activity_size.loc[activity_size > 0].round(1).astype(str)
    return df.sort_values("value", ascending=False, na_position="last").reset_index(drop=True)


def holder_side_panels(holders: pd.DataFrame, top_n: int = 25) -> dict[str, pd.DataFrame]:
    """Split enriched holder rows into PredictParity-style Yes/No panels."""
    panel_columns = ["trader", "wallet", "outcome", "shares", "value", "activity", "activity_time", "verified"]
    empty = pd.DataFrame(columns=panel_columns)
    if holders.empty:
        return {"Yes": empty.copy(), "No": empty.copy()}
    frame = holders.copy()
    for column, default in {
        "trader": "",
        "wallet": "",
        "outcome": "",
        "shares": 0.0,
        "value": 0.0,
        "activity": "",
        "activity_time": pd.NaT,
        "verified": False,
    }.items():
        if column not in frame:
            frame[column] = default
    frame["shares"] = pd.to_numeric(frame["shares"], errors="coerce").fillna(0.0)
    frame["value"] = pd.to_numeric(frame["value"], errors="coerce").fillna(0.0)
    panels: dict[str, pd.DataFrame] = {}
    for side in ("Yes", "No"):
        side_frame = frame[frame["outcome"].astype(str).str.casefold().eq(side.casefold())].copy()
        side_frame = side_frame.sort_values(["shares", "value"], ascending=False, na_position="last").head(max(0, int(top_n)))
        panels[side] = side_frame[[column for column in panel_columns if column in side_frame.columns]].reset_index(drop=True)
    return panels


def holder_strength_summary(holders: pd.DataFrame) -> dict[str, Any]:
    """Summarize holder-side value concentration for a market detail view."""

    if holders.empty:
        return {
            "total_value": 0.0,
            "yes_value": 0.0,
            "no_value": 0.0,
            "unknown_value": 0.0,
            "yes_share": 0.0,
            "no_share": 0.0,
            "dominant_side": "Unknown",
            "dominant_share": 0.0,
            "skew": 0.0,
            "top_10_share": 0.0,
            "holder_count": 0,
        }
    frame = holders.copy()
    if "outcome" not in frame:
        frame["outcome"] = "Unknown"
    value_source = frame["value"] if "value" in frame else frame["amount"] if "amount" in frame else pd.Series(0.0, index=frame.index)
    frame["value"] = pd.to_numeric(value_source, errors="coerce").fillna(0.0).clip(lower=0.0)
    frame["outcome"] = frame["outcome"].fillna("Unknown").astype(str)
    by_side = frame.groupby("outcome")["value"].sum()
    yes_value = float(by_side.get("Yes", 0.0))
    no_value = float(by_side.get("No", 0.0))
    unknown_value = float(by_side.drop(labels=["Yes", "No"], errors="ignore").sum())
    total_value = float(frame["value"].sum())
    yes_share = yes_value / total_value if total_value else 0.0
    no_share = no_value / total_value if total_value else 0.0
    if yes_share > no_share:
        dominant_side = "Yes"
        dominant_share = yes_share
    elif no_share > yes_share:
        dominant_side = "No"
        dominant_share = no_share
    else:
        dominant_side = "Balanced" if total_value else "Unknown"
        dominant_share = yes_share
    top_10_value = float(frame.sort_values("value", ascending=False)["value"].head(10).sum())
    return {
        "total_value": total_value,
        "yes_value": yes_value,
        "no_value": no_value,
        "unknown_value": unknown_value,
        "yes_share": yes_share,
        "no_share": no_share,
        "dominant_side": dominant_side,
        "dominant_share": dominant_share,
        "skew": abs(yes_share - no_share),
        "top_10_share": top_10_value / total_value if total_value else 0.0,
        "holder_count": int(len(frame)),
    }


def get_market_news(query: str, limit: int = 20) -> pd.DataFrame:
    if not query:
        return pd.DataFrame(columns=["time", "source", "title", "url"])
    rss_url = f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=en-US&gl=US&ceid=US:en"
    try:
        response = requests.get(rss_url, timeout=15, headers=HTTP_HEADERS)
        response.raise_for_status()
        root = ET.fromstring(response.content)
    except (requests.RequestException, ET.ParseError):
        return pd.DataFrame(columns=["time", "source", "title", "url"])
    rows: list[dict[str, Any]] = []
    for item in root.findall(".//item")[: max(1, int(limit))]:
        source = item.find("source")
        rows.append(
            {
                "time": _safe_ts(item.findtext("pubDate")),
                "source": source.text if source is not None and source.text else "",
                "title": item.findtext("title") or "",
                "url": item.findtext("link") or "",
            }
        )
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("time", ascending=False, na_position="last").reset_index(drop=True)
    return df


def get_kalshi_markets(limit: int = 250, status: str = "open", cursor: str | None = None) -> pd.DataFrame:
    params: dict[str, Any] = {"limit": limit, "status": status}
    if cursor:
        params["cursor"] = cursor
    data = _get_json(f"{KALSHI_API}/markets", params=params)
    rows = data.get("markets", []) if isinstance(data, dict) else []
    normalized: list[dict[str, Any]] = []
    for market in rows:
        yes_bid = cents(_first_nonempty(market.get("yes_bid_dollars"), market.get("yes_bid")))
        yes_ask = cents(_first_nonempty(market.get("yes_ask_dollars"), market.get("yes_ask")))
        last_price = cents(_first_nonempty(market.get("last_price_dollars"), market.get("last_price")))
        if yes_bid and yes_ask:
            yes_price = (yes_bid + yes_ask) / 2
        else:
            yes_price = last_price
        ticker = market.get("ticker", "")
        normalized.append(
            {
                "platform": "Kalshi",
                "market_key": ticker,
                "id": ticker,
                "ticker": ticker,
                "slug": ticker,
                "event_slug": market.get("event_ticker", ""),
                "title": _first_nonempty(market.get("title"), market.get("subtitle"), ticker),
                "description": _first_nonempty(market.get("rules_primary"), market.get("rules_secondary"), ""),
                "category": _first_nonempty(market.get("category"), market.get("event_ticker", "").split("-")[0], "Uncategorized"),
                "yes_price": yes_price,
                "no_price": 1 - yes_price if yes_price is not None else None,
                "best_bid": yes_bid,
                "best_ask": yes_ask,
                "spread": max(0.0, yes_ask - yes_bid) if yes_bid and yes_ask else None,
                "last_price": last_price,
                "volume": dollars(_first_nonempty(market.get("volume_fp"), market.get("volume"), market.get("volume_dollars"))),
                "volume_1h": dollars(_first_nonempty(market.get("volume_1h_fp"), market.get("volume_1h"), market.get("volume_1h_dollars"))),
                "volume_24h": dollars(
                    _first_nonempty(market.get("volume_24h_fp"), market.get("volume_24h"), market.get("volume_24h_dollars"))
                ),
                "liquidity": dollars(_first_nonempty(market.get("liquidity_dollars"), market.get("liquidity"), market.get("open_interest_fp"))),
                "open_interest": dollars(_first_nonempty(market.get("open_interest_fp"), market.get("open_interest"))),
                "end_time": _safe_ts(_first_nonempty(market.get("close_time"), market.get("expiration_time"))),
                "image": "",
                "outcomes": ["Yes", "No"],
                "yes_token_id": None,
                "no_token_id": None,
                "url": f"https://kalshi.com/markets/{ticker}" if ticker else "https://kalshi.com/markets",
                "raw": market,
            }
        )
    df = pd.DataFrame(normalized)
    if not df.empty:
        df["activity_volume"] = df["volume_24h"].where(df["volume_24h"].fillna(0) > 0, df["volume"])
        df = df.sort_values(["activity_volume", "volume"], ascending=False).reset_index(drop=True)
    return df


def _candlestick_price(row: dict[str, Any], field: str) -> float | None:
    price = row.get("price") if isinstance(row.get("price"), dict) else {}
    return _num(_first_nonempty(price.get(f"{field}_dollars"), price.get(field)))


def get_kalshi_candlesticks(ticker: str, days: int = 30, period_interval: int = 60) -> pd.DataFrame:
    if not ticker:
        return pd.DataFrame(columns=["time", "open", "high", "low", "close", "volume", "open_interest"])
    end_ts = int(time.time())
    start_ts = end_ts - int(days) * 86400
    period_interval = 1440 if period_interval not in {1, 60, 1440} else period_interval
    series_ticker = ticker.split("-", 1)[0]
    params = {"start_ts": start_ts, "end_ts": end_ts, "period_interval": period_interval}
    try:
        data = _get_json(f"{KALSHI_API}/series/{series_ticker}/markets/{ticker}/candlesticks", params=params)
    except MarketDataError:
        try:
            data = _get_json(f"{KALSHI_API}/markets/candlesticks", params={**params, "market_tickers": ticker})
            markets = data.get("markets", []) if isinstance(data, dict) else []
            data = markets[0] if markets else {}
        except MarketDataError:
            return pd.DataFrame(columns=["time", "open", "high", "low", "close", "volume", "open_interest"])
    rows = data.get("candlesticks", []) if isinstance(data, dict) else []
    normalized: list[dict[str, Any]] = []
    for row in rows:
        normalized.append(
            {
                "time": pd.to_datetime(row.get("end_period_ts"), unit="s", utc=True, errors="coerce"),
                "open": _candlestick_price(row, "open"),
                "high": _candlestick_price(row, "high"),
                "low": _candlestick_price(row, "low"),
                "close": _candlestick_price(row, "close"),
                "volume": dollars(_first_nonempty(row.get("volume_fp"), row.get("volume"))),
                "open_interest": dollars(_first_nonempty(row.get("open_interest_fp"), row.get("open_interest"))),
            }
        )
    df = pd.DataFrame(normalized)
    if df.empty:
        return pd.DataFrame(columns=["time", "open", "high", "low", "close", "volume", "open_interest"])
    return df.dropna(subset=["time"]).sort_values("time").reset_index(drop=True)


def get_kalshi_trades(limit: int = 250, ticker: str | None = None) -> pd.DataFrame:
    params: dict[str, Any] = {"limit": limit}
    if ticker:
        params["ticker"] = ticker
    data = _get_json(f"{KALSHI_API}/markets/trades", params=params)
    df = pd.DataFrame(data.get("trades", []) if isinstance(data, dict) else [])
    if df.empty:
        return pd.DataFrame()
    df["platform"] = "Kalshi"
    df["time"] = pd.to_datetime(df.get("created_time"), utc=True, errors="coerce")
    df["ticker"] = df.get("ticker", "")
    df["side"] = df.get("taker_side", "")
    df["outcome"] = df.get("taker_outcome_side", df["side"])
    df["price"] = pd.to_numeric(df.get("yes_price_dollars", 0), errors="coerce").fillna(0.0)
    df["size"] = pd.to_numeric(df.get("count_fp", 0), errors="coerce").fillna(0.0)
    df["notional"] = df["size"] * df["price"]
    df["title"] = df["ticker"]
    df["wallet"] = "Not public"
    df["trader"] = "Not public"
    df["url"] = "https://kalshi.com/markets/" + df["ticker"].astype(str)
    cols = ["platform", "time", "trader", "wallet", "side", "outcome", "title", "ticker", "price", "size", "notional", "url"]
    return df[[c for c in cols if c in df.columns]].sort_values("time", ascending=False).reset_index(drop=True)


def get_kalshi_orderbook(ticker: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not ticker:
        empty = pd.DataFrame(columns=["price", "size", "notional", "side"])
        return empty.copy(), empty.copy()
    empty = pd.DataFrame(columns=["price", "size", "notional", "side"])
    try:
        data = _get_json(f"{KALSHI_API}/markets/{ticker}/orderbook")
    except MarketDataError:
        return empty.copy(), empty.copy()
    book = data.get("orderbook_fp") or data.get("orderbook") or {}

    def normalize(levels: list[Any], side: str) -> pd.DataFrame:
        rows: list[dict[str, float | str]] = []
        for level in levels or []:
            if isinstance(level, dict):
                price = cents(_first_nonempty(level.get("price"), level.get("price_dollars")))
                size = dollars(_first_nonempty(level.get("size"), level.get("count"), level.get("count_fp")))
            elif isinstance(level, list) and len(level) >= 2:
                price = cents(level[0])
                size = dollars(level[1])
            else:
                continue
            if side == "ask":
                price = 1 - price
            rows.append({"price": price, "size": size, "notional": price * size, "side": side})
        df = pd.DataFrame(rows)
        if not df.empty:
            df = df.sort_values("price", ascending=(side == "ask")).reset_index(drop=True)
        return df

    return normalize(book.get("yes_dollars", []), "bid"), normalize(book.get("no_dollars", []), "ask")


def wallet_summary(open_positions: pd.DataFrame, closed_positions: pd.DataFrame, trades: pd.DataFrame) -> dict[str, Any]:
    open_value = float(open_positions["value"].sum()) if not open_positions.empty and "value" in open_positions else 0.0
    unrealized = (
        float(open_positions["unrealized_pnl"].sum())
        if not open_positions.empty and "unrealized_pnl" in open_positions
        else 0.0
    )
    realized = (
        float(closed_positions["realized_pnl"].sum())
        if not closed_positions.empty and "realized_pnl" in closed_positions
        else 0.0
    )
    closed_count = len(closed_positions)
    wins = (
        int((closed_positions["realized_pnl"] > 0).sum())
        if not closed_positions.empty and "realized_pnl" in closed_positions
        else 0
    )
    trade_notional = float(trades["notional"].sum()) if not trades.empty and "notional" in trades else 0.0
    return {
        "open_value": open_value,
        "unrealized_pnl": unrealized,
        "realized_pnl": realized,
        "closed_count": closed_count,
        "win_rate": wins / closed_count if closed_count else None,
        "trade_count": len(trades),
        "trade_notional": trade_notional,
    }


def trader_insight_metrics(
    open_positions: pd.DataFrame,
    closed_positions: pd.DataFrame,
    trades: pd.DataFrame,
    activity: pd.DataFrame | None = None,
    cash_balance: float = 0.0,
    whale_threshold: float = 10_000.0,
) -> dict[str, float | None]:
    """Estimate trader behavior metrics from public wallet data."""

    summary = wallet_summary(open_positions, closed_positions, trades)
    tape = trades.copy() if isinstance(trades, pd.DataFrame) else pd.DataFrame()
    if tape.empty and isinstance(activity, pd.DataFrame):
        tape = activity.copy()
    open_value = float(summary["open_value"])
    denominator = open_value + max(float(cash_balance or 0.0), 0.0)
    exposure = open_value / denominator if denominator else None
    if tape.empty:
        return {
            "win_rate": summary["win_rate"],
            "contrarian": None,
            "trend_follower": None,
            "lottery_ticket": None,
            "whale_splash": None,
            "exposure": exposure,
        }

    tape["price"] = pd.to_numeric(tape.get("price", 0.0), errors="coerce").fillna(0.0)
    tape["size"] = pd.to_numeric(tape.get("size", 0.0), errors="coerce").fillna(0.0)
    if "notional" in tape:
        tape["notional"] = pd.to_numeric(tape["notional"], errors="coerce").fillna(0.0)
    else:
        tape["notional"] = tape["price"] * tape["size"]
    tape["side"] = tape.get("side", pd.Series("", index=tape.index)).fillna("").astype(str).str.upper()
    weighted_base = float(tape["notional"].clip(lower=0.0).sum())
    if weighted_base <= 0:
        weighted_base = float(len(tape))
        tape["notional"] = 1.0

    buy = tape["side"].eq("BUY")
    sell = tape["side"].eq("SELL")
    contrarian_mask = (buy & (tape["price"] <= 0.35)) | (sell & (tape["price"] >= 0.65))
    trend_mask = (buy & (tape["price"] >= 0.65)) | (sell & (tape["price"] <= 0.35))
    lottery_mask = buy & (tape["price"] <= 0.15)
    whale_mask = tape["notional"] >= float(whale_threshold)
    return {
        "win_rate": summary["win_rate"],
        "contrarian": float(tape.loc[contrarian_mask, "notional"].sum()) / weighted_base,
        "trend_follower": float(tape.loc[trend_mask, "notional"].sum()) / weighted_base,
        "lottery_ticket": float(tape.loc[lottery_mask, "notional"].sum()) / weighted_base,
        "whale_splash": float(tape.loc[whale_mask, "notional"].sum()) / weighted_base,
        "exposure": exposure,
    }


def _utc_timestamp(value: Any | None = None) -> pd.Timestamp:
    timestamp = pd.Timestamp.now(tz="UTC") if value is None else pd.Timestamp(value)
    if timestamp.tzinfo is None:
        return timestamp.tz_localize("UTC")
    return timestamp.tz_convert("UTC")


def relative_time_label(value: Any, now: Any | None = None) -> str:
    """Format timestamps as compact scanner labels like "in 2 days"."""

    timestamp = _safe_ts(value)
    if timestamp is None or pd.isna(timestamp):
        return "-"
    now_ts = _utc_timestamp(now)
    seconds = int((timestamp - now_ts).total_seconds())
    if abs(seconds) < 60:
        return "now"

    past = seconds < 0
    remaining = abs(seconds)
    if remaining < 3_600:
        amount = max(1, round(remaining / 60))
        unit = "minute"
    elif remaining < 86_400:
        amount = max(1, round(remaining / 3_600))
        unit = "hour"
    elif remaining < 86_400 * 60:
        amount = max(1, round(remaining / 86_400))
        unit = "day"
    elif remaining < 86_400 * 365:
        amount = max(1, round(remaining / (86_400 * 30)))
        unit = "month"
    else:
        amount = max(1, round(remaining / (86_400 * 365)))
        unit = "year"
    label = f"{amount} {unit}{'' if amount == 1 else 's'}"
    return f"{label} ago" if past else f"in {label}"


def compact_elapsed_label(value: Any, now: Any | None = None) -> str:
    """Format elapsed time for Parity-style labels like "now" or "3m"."""

    timestamp = _safe_ts(value)
    if timestamp is None or pd.isna(timestamp):
        return "-"
    now_ts = _utc_timestamp(now)
    seconds = max(0, int((now_ts - timestamp).total_seconds()))
    if seconds < 60:
        return "now"
    if seconds < 3_600:
        return f"{max(1, round(seconds / 60))}m"
    if seconds < 86_400:
        return f"{max(1, round(seconds / 3_600))}h"
    if seconds < 86_400 * 365:
        return f"{max(1, round(seconds / 86_400))}d"
    return f"{max(1, round(seconds / (86_400 * 365)))}y"


def filter_pnl_curve_window(curve: pd.DataFrame, window: str = "1w", now: Any | None = None) -> pd.DataFrame:
    """Filter wallet PnL curve rows to a PredictParity-style chart window."""

    if curve.empty:
        return curve.copy()
    window = str(window or "All")
    days_by_window = {"1d": 1, "1w": 7, "1mo": 30}
    if window not in days_by_window:
        return curve.copy().reset_index(drop=True)
    frame = curve.copy()
    frame["time"] = pd.to_datetime(frame.get("time"), utc=True, errors="coerce")
    frame = frame.dropna(subset=["time"]).sort_values("time")
    cutoff = _utc_timestamp(now) - pd.Timedelta(days=days_by_window[window])
    return frame[frame["time"] >= cutoff].reset_index(drop=True)


def pnl_window_label(window: Any) -> str:
    """Return the human label PredictParity shows above profile PnL charts."""

    labels = {
        "1d": "Past day",
        "1w": "Past week",
        "1mo": "Past month",
        "All": "All time",
    }
    return labels.get(str(window or "1w"), "Past week")


def wallet_pnl_calendar(closed_positions: pd.DataFrame, window: str = "1mo", now: Any | None = None) -> pd.DataFrame:
    """Aggregate closed-position realized PnL into daily calendar buckets."""

    columns = ["date", "realized_pnl", "closed_positions", "cumulative_realized_pnl", "weekday"]
    if closed_positions.empty or "time" not in closed_positions or "realized_pnl" not in closed_positions:
        return pd.DataFrame(columns=columns)
    frame = closed_positions[["time", "realized_pnl"]].copy()
    frame["time"] = pd.to_datetime(frame["time"], utc=True, errors="coerce")
    frame["realized_pnl"] = pd.to_numeric(frame["realized_pnl"], errors="coerce").fillna(0.0)
    frame = frame.dropna(subset=["time"]).sort_values("time")
    window = str(window or "All")
    days_by_window = {"1d": 1, "1w": 7, "1mo": 30}
    if window in days_by_window:
        cutoff = _utc_timestamp(now) - pd.Timedelta(days=days_by_window[window])
        frame = frame[frame["time"] >= cutoff]
    if frame.empty:
        return pd.DataFrame(columns=columns)
    frame["date"] = frame["time"].dt.date
    calendar = (
        frame.groupby("date", as_index=False)
        .agg(realized_pnl=("realized_pnl", "sum"), closed_positions=("realized_pnl", "size"))
        .sort_values("date")
    )
    calendar["cumulative_realized_pnl"] = calendar["realized_pnl"].cumsum()
    calendar["weekday"] = pd.to_datetime(calendar["date"]).dt.day_name()
    return calendar[columns].reset_index(drop=True)


def enrich_activity_counterparties(
    activity: pd.DataFrame,
    public_trades: pd.DataFrame,
    wallet: str = "",
    max_seconds: int = 30,
) -> pd.DataFrame:
    """Add public counterparty hints to wallet activity rows.

    Polymarket's public activity endpoint does not expose the exact counterparty.
    This uses the public trade tape as a best-effort match by market, asset,
    opposite side, and timestamp proximity.
    """

    if activity.empty:
        return activity.copy()
    frame = activity.copy()
    for col, default in {
        "counterparty": "Not public",
        "counterparty_wallet": "",
        "counterparty_confidence": 0.0,
        "counterparty_time_delta_sec": pd.NA,
    }.items():
        frame[col] = default
    if public_trades.empty:
        return frame

    trades = public_trades.copy()
    for dataset in (frame, trades):
        dataset["time"] = pd.to_datetime(dataset.get("time"), utc=True, errors="coerce")
        dataset["price"] = pd.to_numeric(dataset.get("price", 0.0), errors="coerce").fillna(0.0)
        dataset["size"] = pd.to_numeric(dataset.get("size", 0.0), errors="coerce").fillna(0.0)
        dataset["side"] = dataset.get("side", pd.Series("", index=dataset.index)).fillna("").astype(str).str.upper()
        dataset["market_key"] = dataset.get("market_key", pd.Series("", index=dataset.index)).fillna("").astype(str)
        dataset["asset"] = dataset.get("asset", pd.Series("", index=dataset.index)).fillna("").astype(str)
        dataset["wallet"] = dataset.get("wallet", pd.Series("", index=dataset.index)).fillna("").astype(str)
        dataset["trader"] = dataset.get("trader", pd.Series("", index=dataset.index)).fillna("").astype(str)

    target_wallet = str(wallet or "").lower()
    if target_wallet:
        trades = trades[~trades["wallet"].str.lower().eq(target_wallet)]
    trades = trades.dropna(subset=["time"])
    if trades.empty:
        return frame

    for idx, row in frame.iterrows():
        if str(row.get("type", "")).upper() != "TRADE" or pd.isna(row.get("time")):
            continue
        candidates = trades.copy()
        market_key = str(row.get("market_key", "") or "")
        asset = str(row.get("asset", "") or "")
        if market_key:
            candidates = candidates[candidates["market_key"].eq(market_key)]
        if asset:
            asset_matches = candidates[candidates["asset"].eq(asset)]
            if not asset_matches.empty:
                candidates = asset_matches
        opposite_side = "SELL" if str(row.get("side", "")).upper() == "BUY" else "BUY" if str(row.get("side", "")).upper() == "SELL" else ""
        if opposite_side:
            opposite = candidates[candidates["side"].eq(opposite_side)]
            if not opposite.empty:
                candidates = opposite
        if candidates.empty:
            continue
        candidates = candidates.copy()
        candidates["time_delta"] = (candidates["time"] - row["time"]).dt.total_seconds().abs()
        candidates = candidates[candidates["time_delta"] <= max_seconds]
        if candidates.empty:
            continue
        price = float(row.get("price") or 0.0)
        size = float(row.get("size") or 0.0)
        candidates["price_gap"] = (candidates["price"] - price).abs()
        candidates["size_gap_ratio"] = (candidates["size"] - size).abs() / max(size, 1.0)
        candidates["score"] = (
            1.0
            - (candidates["time_delta"] / max(float(max_seconds), 1.0) * 0.55)
            - candidates["price_gap"].clip(upper=0.25) * 1.0
            - candidates["size_gap_ratio"].clip(upper=1.0) * 0.20
        ).clip(lower=0.0, upper=1.0)
        best = candidates.sort_values(["score", "time_delta"], ascending=[False, True]).iloc[0]
        label = _first_nonempty(best.get("trader"), best.get("wallet"), "Counterparty hint")
        frame.at[idx, "counterparty"] = label
        frame.at[idx, "counterparty_wallet"] = str(best.get("wallet", ""))
        frame.at[idx, "counterparty_confidence"] = float(best.get("score", 0.0))
        frame.at[idx, "counterparty_time_delta_sec"] = float(best.get("time_delta", 0.0))
    return frame


def whale_wallets(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty or "wallet" not in trades:
        return pd.DataFrame()
    grouped = (
        trades.groupby(["wallet", "trader"], dropna=False)
        .agg(
            trade_count=("wallet", "size"),
            notional=("notional", "sum"),
            avg_trade=("notional", "mean"),
            latest_trade=("time", "max"),
            markets=("title", pd.Series.nunique),
        )
        .reset_index()
        .sort_values("notional", ascending=False)
    )
    return grouped


def _df_col(df: pd.DataFrame, column: str, default: Any = "") -> pd.Series:
    if column in df:
        return df[column]
    return pd.Series(default, index=df.index)


def _risk_level(score: Any) -> str:
    value = float(_num(score, 0.0) or 0.0)
    if value >= 70:
        return "High"
    if value >= 55:
        return "Medium"
    if value >= 40:
        return "Elevated"
    return "Low"


def _dominant_bucket(
    df: pd.DataFrame,
    group_cols: list[str],
    bucket_col: str,
    *,
    bucket_name: str,
    share_name: str,
    notional_name: str,
) -> pd.DataFrame:
    if df.empty or bucket_col not in df or "notional" not in df:
        return pd.DataFrame(columns=group_cols + [bucket_name, share_name, notional_name])
    work = df[group_cols + [bucket_col, "notional"]].copy()
    work[bucket_col] = work[bucket_col].fillna("").astype(str)
    work = work[work[bucket_col].str.strip().ne("")]
    if work.empty:
        return pd.DataFrame(columns=group_cols + [bucket_name, share_name, notional_name])
    bucketed = work.groupby(group_cols + [bucket_col], dropna=False)["notional"].sum().reset_index()
    totals = work.groupby(group_cols, dropna=False)["notional"].sum().reset_index(name="_total_notional")
    bucketed = bucketed.merge(totals, on=group_cols, how="left")
    bucketed[share_name] = bucketed["notional"] / bucketed["_total_notional"].replace({0: pd.NA})
    bucketed = bucketed.sort_values(group_cols + [share_name, "notional"], ascending=[True] * len(group_cols) + [False, False])
    bucketed = bucketed.drop_duplicates(group_cols, keep="first")
    return bucketed.rename(columns={bucket_col: bucket_name, "notional": notional_name})[
        group_cols + [bucket_name, share_name, notional_name]
    ]


def _risk_reasons(row: pd.Series, rules: list[tuple[bool, str]]) -> str:
    reasons = [label for condition, label in rules if bool(condition)]
    return "; ".join(reasons[:4]) if reasons else "watch only"


def _prepare_whale_risk_trades(trades: pd.DataFrame, now: Any | None = None) -> tuple[pd.DataFrame, pd.Timestamp]:
    current_time = pd.to_datetime(now, utc=True, errors="coerce") if now is not None else pd.Timestamp.now(tz="UTC")
    if pd.isna(current_time):
        current_time = pd.Timestamp.now(tz="UTC")
    if trades.empty:
        return trades.copy(), current_time
    df = trades.copy()
    df["time"] = pd.to_datetime(_df_col(df, "time", pd.NaT), utc=True, errors="coerce")
    df["end_time"] = pd.to_datetime(_df_col(df, "end_time", pd.NaT), utc=True, errors="coerce")
    df["notional"] = pd.to_numeric(_df_col(df, "notional", 0.0), errors="coerce").fillna(0.0).clip(lower=0.0)
    df["size"] = pd.to_numeric(_df_col(df, "size", 0.0), errors="coerce").fillna(0.0).clip(lower=0.0)
    df["platform"] = _df_col(df, "platform", "").fillna("").astype(str)
    df["title"] = _df_col(df, "title", "").fillna("").astype(str)
    df["market_key"] = _df_col(df, "market_key", "").fillna("").astype(str)
    df["wallet"] = _df_col(df, "wallet", "").fillna("").astype(str)
    df["trader"] = _df_col(df, "trader", "").fillna("").astype(str)
    df["side_upper"] = _df_col(df, "side", "").fillna("").astype(str).str.upper()
    df["outcome_upper"] = _df_col(df, "outcome", "").fillna("").astype(str).str.upper()
    df["hours_to_end"] = (df["end_time"] - current_time).dt.total_seconds() / 3600
    df["late_notional"] = df["notional"].where(df["hours_to_end"].between(0, 48, inclusive="both"), 0.0)
    return df, current_time


def whale_wallet_risk_scores(trades: pd.DataFrame, whale_threshold: float = 10_000.0, now: Any | None = None) -> pd.DataFrame:
    """Score wallet-level whale-flow risk signals from the current public trade tape.

    The score is a heuristic signal, not proof of manipulation or inside information.
    """

    df, _current_time = _prepare_whale_risk_trades(trades, now)
    if df.empty or "wallet" not in df:
        return pd.DataFrame()
    df = df[df["wallet"].str.strip().ne("")]
    df = df[df["wallet"].str.lower().ne("nan")]
    if df.empty:
        return pd.DataFrame()

    grouped = (
        df.groupby("wallet", dropna=False)
        .agg(
            trader=("trader", lambda s: str(_first_nonempty(*s.tolist()) or "")),
            trade_count=("wallet", "size"),
            notional=("notional", "sum"),
            avg_trade=("notional", "mean"),
            largest_trade=("notional", "max"),
            markets=("title", pd.Series.nunique),
            first_seen=("time", "min"),
            latest_trade=("time", "max"),
            late_notional=("late_notional", "sum"),
        )
        .reset_index()
    )
    span_minutes = (grouped["latest_trade"] - grouped["first_seen"]).dt.total_seconds().fillna(0.0) / 60
    grouped["trades_per_hour"] = grouped["trade_count"] / (span_minutes.clip(lower=5) / 60)

    top_market = _dominant_bucket(
        df,
        ["wallet"],
        "title",
        bucket_name="top_market",
        share_name="top_market_share",
        notional_name="top_market_notional",
    )
    top_outcome = _dominant_bucket(
        df[df["outcome_upper"].isin(["YES", "NO"])],
        ["wallet"],
        "outcome_upper",
        bucket_name="dominant_outcome",
        share_name="outcome_share",
        notional_name="dominant_outcome_notional",
    )
    top_side = _dominant_bucket(
        df[df["side_upper"].isin(["BUY", "SELL"])],
        ["wallet"],
        "side_upper",
        bucket_name="dominant_side",
        share_name="side_share",
        notional_name="dominant_side_notional",
    )

    grouped = grouped.merge(top_market, on="wallet", how="left").merge(top_outcome, on="wallet", how="left").merge(top_side, on="wallet", how="left")
    for column in ["top_market_share", "outcome_share", "side_share", "late_notional"]:
        if column in grouped:
            grouped[column] = pd.to_numeric(grouped[column], errors="coerce").fillna(0.0)
    grouped["directional_share"] = grouped[["outcome_share", "side_share"]].max(axis=1)
    grouped["directional_label"] = grouped["dominant_outcome"].where(grouped["outcome_share"] >= grouped["side_share"], grouped["dominant_side"]).fillna("")
    grouped["late_share"] = grouped["late_notional"] / grouped["notional"].replace({0: pd.NA})
    grouped["late_share"] = grouped["late_share"].fillna(0.0)

    whale_base = max(float(whale_threshold or 0.0), 1_000.0)
    notional_score = (grouped["notional"] / (whale_base * 20)).clip(upper=1.0) * 25
    largest_score = (grouped["largest_trade"] / (whale_base * 5)).clip(upper=1.0) * 25
    concentration_score = grouped["top_market_share"].fillna(0.0).clip(upper=1.0) * 20
    direction_score = ((grouped["directional_share"].fillna(0.0) - 0.55) / 0.45).clip(lower=0.0, upper=1.0) * 15
    burst_score = (grouped["trades_per_hour"] / 30).clip(upper=1.0) * 10
    late_score = grouped["late_share"].fillna(0.0).clip(upper=1.0) * 5
    grouped["wallet_risk_score"] = (notional_score + largest_score + concentration_score + direction_score + burst_score + late_score).round(0).clip(0, 100)
    grouped["wallet_risk_level"] = grouped["wallet_risk_score"].map(_risk_level)
    grouped["wallet_risk_reasons"] = grouped.apply(
        lambda row: _risk_reasons(
            row,
            [
                (float(row.get("largest_trade", 0.0) or 0.0) >= whale_base * 5, "large print"),
                (float(row.get("top_market_share", 0.0) or 0.0) >= 0.6 and int(row.get("trade_count", 0) or 0) >= 2, "single-market concentration"),
                (float(row.get("directional_share", 0.0) or 0.0) >= 0.8, "one-sided flow"),
                (float(row.get("trades_per_hour", 0.0) or 0.0) >= 20, "fast burst"),
                (float(row.get("late_share", 0.0) or 0.0) >= 0.5, "late-market flow"),
            ],
        ),
        axis=1,
    )
    return grouped.sort_values(["wallet_risk_score", "notional", "latest_trade"], ascending=[False, False, False]).reset_index(drop=True)


def whale_event_risk_scores(trades: pd.DataFrame, whale_threshold: float = 10_000.0, now: Any | None = None) -> pd.DataFrame:
    """Score market/event-level whale-flow risk signals from recent public trades."""

    df, _current_time = _prepare_whale_risk_trades(trades, now)
    if df.empty or "title" not in df:
        return pd.DataFrame()
    df = df[df["title"].str.strip().ne("")]
    if df.empty:
        return pd.DataFrame()

    grouped = (
        df.groupby(["platform", "title"], dropna=False)
        .agg(
            trades=("title", "size"),
            notional=("notional", "sum"),
            avg_trade=("notional", "mean"),
            largest_trade=("notional", "max"),
            first_seen=("time", "min"),
            latest_trade=("time", "max"),
            unique_wallets=("wallet", lambda s: int(s.astype(str).str.strip().replace("", pd.NA).dropna().nunique())),
            late_notional=("late_notional", "sum"),
            market_key=("market_key", "first"),
            url=("url", "first") if "url" in df else ("title", "first"),
        )
        .reset_index()
    )
    span_minutes = (grouped["latest_trade"] - grouped["first_seen"]).dt.total_seconds().fillna(0.0) / 60
    grouped["trades_per_hour"] = grouped["trades"] / (span_minutes.clip(lower=5) / 60)

    top_wallet = _dominant_bucket(
        df[df["wallet"].str.strip().ne("")],
        ["platform", "title"],
        "wallet",
        bucket_name="top_wallet",
        share_name="top_wallet_share",
        notional_name="top_wallet_notional",
    )
    top_outcome = _dominant_bucket(
        df[df["outcome_upper"].isin(["YES", "NO"])],
        ["platform", "title"],
        "outcome_upper",
        bucket_name="dominant_outcome",
        share_name="outcome_share",
        notional_name="dominant_outcome_notional",
    )
    top_side = _dominant_bucket(
        df[df["side_upper"].isin(["BUY", "SELL"])],
        ["platform", "title"],
        "side_upper",
        bucket_name="dominant_side",
        share_name="side_share",
        notional_name="dominant_side_notional",
    )

    grouped = grouped.merge(top_wallet, on=["platform", "title"], how="left").merge(top_outcome, on=["platform", "title"], how="left").merge(top_side, on=["platform", "title"], how="left")
    for column in ["top_wallet_share", "outcome_share", "side_share", "late_notional"]:
        if column in grouped:
            grouped[column] = pd.to_numeric(grouped[column], errors="coerce").fillna(0.0)
    grouped["event_directional_share"] = grouped[["outcome_share", "side_share"]].max(axis=1)
    grouped["event_directional_label"] = grouped["dominant_outcome"].where(grouped["outcome_share"] >= grouped["side_share"], grouped["dominant_side"]).fillna("")
    grouped["late_share"] = grouped["late_notional"] / grouped["notional"].replace({0: pd.NA})
    grouped["late_share"] = grouped["late_share"].fillna(0.0)

    whale_base = max(float(whale_threshold or 0.0), 1_000.0)
    notional_score = (grouped["notional"] / (whale_base * 40)).clip(upper=1.0) * 25
    largest_score = (grouped["largest_trade"] / (whale_base * 5)).clip(upper=1.0) * 15
    wallet_concentration_score = grouped["top_wallet_share"].fillna(0.0).clip(upper=1.0) * 20
    direction_score = ((grouped["event_directional_share"].fillna(0.0) - 0.55) / 0.45).clip(lower=0.0, upper=1.0) * 15
    burst_score = (grouped["trades_per_hour"] / 30).clip(upper=1.0) * 15
    late_score = grouped["late_share"].fillna(0.0).clip(upper=1.0) * 10
    grouped["event_risk_score"] = (notional_score + largest_score + wallet_concentration_score + direction_score + burst_score + late_score).round(0).clip(0, 100)
    grouped["event_risk_level"] = grouped["event_risk_score"].map(_risk_level)
    grouped["event_risk_reasons"] = grouped.apply(
        lambda row: _risk_reasons(
            row,
            [
                (float(row.get("largest_trade", 0.0) or 0.0) >= whale_base * 5, "large print"),
                (float(row.get("top_wallet_share", 0.0) or 0.0) >= 0.5, "wallet concentration"),
                (float(row.get("event_directional_share", 0.0) or 0.0) >= 0.8, "one-sided flow"),
                (float(row.get("trades_per_hour", 0.0) or 0.0) >= 20, "fast burst"),
                (float(row.get("late_share", 0.0) or 0.0) >= 0.5, "late-market flow"),
                (int(row.get("unique_wallets", 0) or 0) >= 5 and float(row.get("trades_per_hour", 0.0) or 0.0) >= 10, "multi-wallet burst"),
            ],
        ),
        axis=1,
    )
    return grouped.sort_values(["event_risk_score", "notional", "latest_trade"], ascending=[False, False, False]).reset_index(drop=True)


def trader_flow_scores(trades: pd.DataFrame, whale_threshold: float = 2500) -> pd.DataFrame:
    if trades.empty or "wallet" not in trades:
        return pd.DataFrame()
    df = trades.copy()
    if "time" in df:
        df["time"] = pd.to_datetime(df["time"], utc=True, errors="coerce")
    grouped = (
        df.groupby(["wallet", "trader"], dropna=False)
        .agg(
            recent_trades=("wallet", "size"),
            recent_notional=("notional", "sum"),
            avg_trade=("notional", "mean"),
            largest_trade=("notional", "max"),
            markets=("title", pd.Series.nunique),
            outcomes=("outcome", pd.Series.nunique),
            first_seen=("time", "min"),
            last_seen=("time", "max"),
        )
        .reset_index()
    )
    span_minutes = (grouped["last_seen"] - grouped["first_seen"]).dt.total_seconds().fillna(0) / 60
    grouped["trades_per_hour"] = grouped["recent_trades"] / (span_minutes.clip(lower=5) / 60)
    whale_base = max(float(whale_threshold), 1.0)
    grouped["whale_score"] = (
        (grouped["recent_notional"] / (whale_base * 20)).clip(upper=1) * 55
        + (grouped["largest_trade"] / (whale_base * 5)).clip(upper=1) * 30
        + (grouped["markets"] / 8).clip(upper=1) * 15
    ).round(0)
    grouped["bot_score"] = (
        (grouped["recent_trades"] / 30).clip(upper=1) * 35
        + (grouped["markets"] / 15).clip(upper=1) * 25
        + (grouped["trades_per_hour"] / 40).clip(upper=1) * 25
        + (1 - (grouped["avg_trade"] / max(whale_base, 1)).clip(upper=1)) * 15
    ).round(0)
    grouped["flow_trait"] = "Active"
    grouped.loc[grouped["whale_score"] >= 65, "flow_trait"] = "Whale"
    grouped.loc[grouped["bot_score"] >= 65, "flow_trait"] = "Bot-like"
    grouped.loc[(grouped["whale_score"] >= 65) & (grouped["bot_score"] >= 65), "flow_trait"] = "Whale bot-like"
    return grouped.sort_values(["whale_score", "recent_notional"], ascending=False).reset_index(drop=True)


def apply_trader_trait_filters(
    leaderboard: pd.DataFrame,
    trait_filter: Iterable[str] | None = None,
    bots_only: bool = False,
    bot_score_min: float = 65,
    whale_score_min: float = 65,
    whale_volume_min: float = 1_000_000,
) -> pd.DataFrame:
    """Apply PredictParity-style quick trader trait filters."""

    if leaderboard.empty:
        return leaderboard.copy()
    frame = leaderboard.copy()
    selected = {str(item) for item in (trait_filter or [])}
    if "volume" not in frame:
        frame["volume"] = 0.0
    if "whale_score" not in frame:
        frame["whale_score"] = 0.0
    if "bot_score" not in frame:
        frame["bot_score"] = 0.0
    if "verified" not in frame:
        frame["verified"] = False

    bot_score = pd.to_numeric(frame["bot_score"], errors="coerce").fillna(0.0)
    missing_bot_score = bot_score <= 0
    if missing_bot_score.any():
        volume = pd.to_numeric(frame["volume"], errors="coerce").fillna(0.0).clip(lower=0.0)
        pnl = pd.to_numeric(frame.get("pnl", pd.Series(0.0, index=frame.index)), errors="coerce").fillna(0.0).abs()
        max_volume = max(float(volume.max()), 1.0)
        volume_score = ((volume + 1).map(math.log10) / math.log10(max_volume + 1)).clip(upper=1.0) * 55
        pnl_to_volume = (pnl / volume.replace({0: pd.NA})).fillna(1.0)
        turnover_score = (1 - (pnl_to_volume / 0.08).clip(upper=1.0)) * 25
        scale_score = (volume / 250_000_000).clip(upper=1.0) * 10
        anonymous_score = (~frame["verified"].fillna(False).astype(bool)).astype(float) * 10
        fallback_score = (volume_score + turnover_score + scale_score + anonymous_score).round(0).clip(lower=0.0, upper=100.0)
        frame.loc[missing_bot_score, "bot_score"] = fallback_score.loc[missing_bot_score]

    if "Whales" in selected:
        frame = frame[
            (pd.to_numeric(frame["volume"], errors="coerce").fillna(0.0) >= float(whale_volume_min))
            | (pd.to_numeric(frame["whale_score"], errors="coerce").fillna(0.0) >= float(whale_score_min))
        ]
    if bots_only or "Bot-like" in selected:
        frame = frame[pd.to_numeric(frame["bot_score"], errors="coerce").fillna(0.0) >= float(bot_score_min)]
    if "Verified" in selected:
        frame = frame[frame["verified"].fillna(False).astype(bool)]
    return frame.reset_index(drop=True)


def cycle_featured_index(current_index: Any, total_items: int, step: int = 0) -> int:
    """Return a wrapped carousel index for a PredictParity-style featured strip."""

    if total_items <= 0:
        return 0
    try:
        current = int(current_index)
    except (TypeError, ValueError):
        current = 0
    return (current + int(step)) % int(total_items)


TOKEN_RE = re.compile(r"[a-z0-9]+")
STOPWORDS = {
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
    "for",
    "and",
    "or",
    "is",
    "be",
    "this",
    "market",
    "resolve",
    "yes",
    "no",
}


def _tokens(text: str) -> set[str]:
    return {token for token in TOKEN_RE.findall((text or "").lower()) if token not in STOPWORDS and len(token) > 2}


def market_similarity(left: str, right: str) -> float:
    left_tokens = _tokens(left)
    right_tokens = _tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    jaccard = len(left_tokens & right_tokens) / len(left_tokens | right_tokens)
    sequence = SequenceMatcher(None, " ".join(sorted(left_tokens)), " ".join(sorted(right_tokens))).ratio()
    return round((jaccard * 0.65) + (sequence * 0.35), 4)


def cross_venue_candidates(
    polymarket_markets: pd.DataFrame,
    kalshi_markets: pd.DataFrame,
    query: str = "",
    min_similarity: float = 0.28,
    max_pairs: int = 80,
) -> pd.DataFrame:
    if polymarket_markets.empty or kalshi_markets.empty:
        return pd.DataFrame()
    pm = polymarket_markets.copy()
    ks = kalshi_markets.copy()
    if query:
        pattern = re.escape(query.lower())
        pm = pm[pm["title"].str.lower().str.contains(pattern, na=False)]
        ks = ks[ks["title"].str.lower().str.contains(pattern, na=False)]
    if pm.empty or ks.empty:
        return pd.DataFrame()

    pm_sort = "activity_volume" if "activity_volume" in pm else "volume_24h"
    ks_sort = "activity_volume" if "activity_volume" in ks else "volume_24h"
    pm = pm.sort_values(pm_sort, ascending=False).head(80)
    ks = ks.sort_values(ks_sort, ascending=False).head(80)
    rows: list[dict[str, Any]] = []
    for _, p_row in pm.iterrows():
        for _, k_row in ks.iterrows():
            similarity = market_similarity(str(p_row["title"]), str(k_row["title"]))
            if similarity < min_similarity:
                continue
            pm_price = _num(p_row.get("yes_price"))
            ks_price = _num(k_row.get("yes_price"))
            if pm_price is None or ks_price is None:
                continue
            gap = pm_price - ks_price
            rows.append(
                {
                    "similarity": similarity,
                    "gap": gap,
                    "abs_gap": abs(gap),
                    "lower_yes": "Kalshi" if gap > 0 else "Polymarket",
                    "higher_yes": "Polymarket" if gap > 0 else "Kalshi",
                    "polymarket_market_key": str(p_row.get("market_key") or p_row.get("id") or p_row.get("ticker") or p_row.get("title") or ""),
                    "kalshi_market_key": str(k_row.get("market_key") or k_row.get("id") or k_row.get("ticker") or k_row.get("title") or ""),
                    "polymarket_ticker": str(p_row.get("ticker") or p_row.get("id") or ""),
                    "kalshi_ticker": str(k_row.get("ticker") or k_row.get("id") or ""),
                    "polymarket_title": p_row["title"],
                    "kalshi_title": k_row["title"],
                    "polymarket_yes": pm_price,
                    "kalshi_yes": ks_price,
                    "polymarket_volume": p_row.get("activity_volume", p_row.get("volume_24h", 0)),
                    "kalshi_volume": k_row.get("activity_volume", k_row.get("volume_24h", 0)),
                    "polymarket_url": p_row.get("url", ""),
                    "kalshi_url": k_row.get("url", ""),
                }
            )
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values(["abs_gap", "similarity"], ascending=False).head(max_pairs).reset_index(drop=True)
    return df


def portfolio_metrics(portfolio: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, float]]:
    if portfolio.empty:
        return portfolio, {"cost": 0.0, "value": 0.0, "pnl": 0.0, "pnl_pct": 0.0}
    df = portfolio.copy()
    for col in ["shares", "avg_price", "current_price"]:
        df[col] = pd.to_numeric(df.get(col, 0), errors="coerce").fillna(0.0)
    df["cost"] = df["shares"] * df["avg_price"]
    df["value"] = df["shares"] * df["current_price"]
    df["pnl"] = df["value"] - df["cost"]
    df["pnl_pct"] = df["pnl"] / df["cost"].replace({0: pd.NA})
    metrics = {
        "cost": float(df["cost"].sum()),
        "value": float(df["value"].sum()),
        "pnl": float(df["pnl"].sum()),
        "pnl_pct": float(df["pnl"].sum() / df["cost"].sum()) if df["cost"].sum() else 0.0,
    }
    return df, metrics


def research_trade_preview(
    existing_shares: float,
    existing_avg_price: float,
    side: str,
    requested_notional: float,
    price: float,
) -> dict[str, float | str]:
    """Preview a paper research trade against an existing position."""

    old_shares = max(float(existing_shares or 0.0), 0.0)
    old_avg = max(float(existing_avg_price or 0.0), 0.0)
    trade_price = max(float(price or 0.0), 0.0)
    requested = max(float(requested_notional or 0.0), 0.0)
    side_label = "Sell" if str(side).lower() == "sell" else "Buy"
    if requested <= 0 or trade_price <= 0:
        return {
            "side": side_label,
            "requested_notional": requested,
            "executed_notional": 0.0,
            "requested_shares": 0.0,
            "executed_shares": 0.0,
            "old_shares": old_shares,
            "new_shares": old_shares,
            "avg_price_after": old_avg,
            "realized_pnl": 0.0,
            "capped": 0.0,
        }
    requested_shares = requested / trade_price
    if side_label == "Buy":
        new_shares = old_shares + requested_shares
        avg_after = ((old_shares * old_avg) + requested) / new_shares if new_shares else trade_price
        return {
            "side": side_label,
            "requested_notional": requested,
            "executed_notional": requested,
            "requested_shares": requested_shares,
            "executed_shares": requested_shares,
            "old_shares": old_shares,
            "new_shares": new_shares,
            "avg_price_after": avg_after,
            "realized_pnl": 0.0,
            "capped": 0.0,
        }
    executed_shares = min(old_shares, requested_shares)
    executed_notional = executed_shares * trade_price
    new_shares = max(0.0, old_shares - executed_shares)
    realized_pnl = (trade_price - old_avg) * executed_shares
    return {
        "side": side_label,
        "requested_notional": requested,
        "executed_notional": executed_notional,
        "requested_shares": requested_shares,
        "executed_shares": executed_shares,
        "old_shares": old_shares,
        "new_shares": new_shares,
        "avg_price_after": old_avg if new_shares > 0 else 0.0,
        "realized_pnl": realized_pnl,
        "capped": 1.0 if executed_shares < requested_shares else 0.0,
    }


def research_trade_max_notional(
    available_cash: float,
    existing_shares: float,
    price: float,
    side: str,
) -> float:
    """Return the executable Max amount for a local paper research ticket."""

    cash = max(float(available_cash or 0.0), 0.0)
    shares = max(float(existing_shares or 0.0), 0.0)
    trade_price = max(float(price or 0.0), 0.0)
    side_label = "Sell" if str(side).lower() == "sell" else "Buy"
    if side_label == "Sell":
        return shares * trade_price
    return cash


def research_trade_executable_notional(
    requested_notional: float,
    available_cash: float,
    side: str,
) -> float:
    """Cap local research buys to cash while leaving sells capped by shares."""

    requested = max(float(requested_notional or 0.0), 0.0)
    side_label = "Sell" if str(side).lower() == "sell" else "Buy"
    if side_label == "Buy":
        return min(requested, max(float(available_cash or 0.0), 0.0))
    return requested


def wallet_positions_to_research_portfolio(open_positions: pd.DataFrame) -> pd.DataFrame:
    cols = ["platform", "market", "market_key", "url", "outcome", "shares", "avg_price", "current_price"]
    if open_positions.empty:
        return pd.DataFrame(columns=cols)
    df = open_positions.copy()
    result = pd.DataFrame(
        {
            "platform": df.get("platform", "Polymarket"),
            "market": df.get("title", ""),
            "market_key": df.get("market_key", ""),
            "url": df.get("url", ""),
            "outcome": df.get("outcome", ""),
            "shares": pd.to_numeric(df.get("size", 0), errors="coerce").fillna(0.0),
            "avg_price": pd.to_numeric(df.get("avg_price", 0), errors="coerce").fillna(0.0),
            "current_price": pd.to_numeric(df.get("current_price", df.get("avg_price", 0)), errors="coerce").fillna(0.0),
        }
    )
    result = result[result["shares"] > 0].copy()
    return result[cols].reset_index(drop=True)


def held_market_keys(*position_frames: pd.DataFrame) -> set[str]:
    """Return market ids with positive position size from any portfolio source."""

    keys: set[str] = set()
    for frame in position_frames:
        if not isinstance(frame, pd.DataFrame) or frame.empty or "market_key" not in frame:
            continue
        shares = pd.to_numeric(frame.get("shares", 0), errors="coerce").fillna(0.0)
        active = frame[shares > 0]
        keys.update(
            value
            for value in active["market_key"].fillna("").astype(str).str.strip()
            if value
        )
    return keys


def market_category_counts(markets: pd.DataFrame, column: str = "category") -> list[dict[str, Any]]:
    """Return non-empty market categories sorted by descending frequency."""

    if not isinstance(markets, pd.DataFrame) or markets.empty or column not in markets:
        return []
    categories = markets[column].fillna("").astype(str).str.strip()
    categories = categories[categories.ne("")]
    if categories.empty:
        return []
    counts = categories.value_counts()
    return [{"category": str(category), "count": int(count)} for category, count in counts.items()]


def market_category_label(category: Any) -> str:
    """Display raw Polymarket/Kalshi category identifiers as readable filter labels."""

    raw = str(category or "").strip()
    if not raw:
        return "Uncategorized"
    normalized = raw.replace("_", " ").replace("-", " ").strip()
    simple = normalized.casefold()
    if simple in {"uncategorized", "other"}:
        return normalized.title()
    exact = {
        "KXMVESPORTSMULTIGAMEEXTENDED": "Sports",
        "KXMVECROSSCATEGORY": "Cross Category",
    }
    upper = re.sub(r"[^A-Z0-9]", "", raw.upper())
    if upper in exact:
        return exact[upper]
    keyword_labels = (
        (("SPORT", "NBA", "NFL", "MLB", "NHL", "FIFA", "SOCCER", "TENNIS", "GOLF", "UFC", "MMA"), "Sports"),
        (("CRYPTO", "BITCOIN", "BTC", "ETH", "SOLANA"), "Crypto"),
        (("ELECTION", "POLITIC", "TRUMP", "BIDEN", "CONGRESS", "SENATE", "PRESIDENT"), "Politics"),
        (("WEATHER", "TEMP", "HURRICANE", "RAIN", "SNOW"), "Weather"),
        (("STOCK", "NASDAQ", "SPY", "DOW", "FED", "INFLATION", "RATE"), "Finance"),
    )
    for keywords, label in keyword_labels:
        if any(keyword in upper for keyword in keywords):
            return label
    if raw.isupper() and upper.startswith("KX"):
        return raw
    return normalized.title() if normalized.islower() or normalized.isupper() else normalized


def market_filter_category(category: Any, title: Any = "") -> str:
    """Infer a practical scanner category from raw category plus market title."""

    label = market_category_label(category)
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


def market_category_chip_options(
    markets: pd.DataFrame,
    include_categories: list[str] | tuple[str, ...] | set[str],
    exclude_categories: list[str] | tuple[str, ...] | set[str],
    *,
    limit: int = 10,
    show_all: bool = False,
    column: str = "category",
) -> list[dict[str, Any]]:
    """Build PredictParity-style category chip labels with include/exclude state."""

    include = {str(item).strip() for item in include_categories if str(item).strip()}
    exclude = {str(item).strip() for item in exclude_categories if str(item).strip()}
    rows = market_category_counts(markets, column=column)
    if not show_all:
        rows = rows[: max(0, int(limit))]
    chips: list[dict[str, Any]] = []
    for row in rows:
        category = str(row["category"])
        if category in include:
            state = "include"
            prefix = "+ "
        elif category in exclude:
            state = "exclude"
            prefix = "- "
        else:
            state = "neutral"
            prefix = ""
        chips.append(
            {
                "category": category,
                "display": market_category_label(category),
                "count": int(row["count"]),
                "state": state,
                "label": f"{prefix}{market_category_label(category)} {int(row['count']):,}",
            }
        )
    return chips


def cycle_market_category_filter(
    include_categories: list[str] | tuple[str, ...] | set[str],
    exclude_categories: list[str] | tuple[str, ...] | set[str],
    category: str,
) -> tuple[list[str], list[str]]:
    """Cycle a category chip through neutral -> include -> exclude -> neutral."""

    value = str(category or "").strip()
    include = [str(item).strip() for item in include_categories if str(item).strip()]
    exclude = [str(item).strip() for item in exclude_categories if str(item).strip()]
    if not value:
        return include, exclude

    include_set = set(include)
    exclude_set = set(exclude)
    if value in include_set:
        include = [item for item in include if item != value]
        if value not in exclude_set:
            exclude.append(value)
    elif value in exclude_set:
        exclude = [item for item in exclude if item != value]
    else:
        include.append(value)
        exclude = [item for item in exclude if item != value]
    return include, exclude


def watchlist_market_item(row: Mapping[str, Any]) -> dict[str, str]:
    """Normalize a market row into the local saved-market/watchlist shape."""

    market_key = str(_first_nonempty(row.get("market_key"), row.get("ticker"), row.get("title"), "") or "").strip()
    return {
        "platform": str(_first_nonempty(row.get("platform"), "") or "").strip(),
        "market_key": market_key,
        "title": str(_first_nonempty(row.get("title"), "") or "").strip(),
        "url": str(_first_nonempty(row.get("url"), "") or "").strip(),
    }


def upsert_watchlist_market(watchlist: list[Mapping[str, Any]], row: Mapping[str, Any]) -> tuple[list[dict[str, str]], bool]:
    """Add or refresh one market in a saved-market list, deduped by market_key."""

    item = watchlist_market_item(row)
    key = item["market_key"]
    if not key:
        return [dict(existing) for existing in watchlist], False

    updated: list[dict[str, str]] = []
    changed = False
    seen = False
    for existing in watchlist:
        current = dict(existing)
        if str(current.get("market_key", "")).strip() == key:
            merged = {
                "platform": item["platform"] or str(current.get("platform", "")),
                "market_key": key,
                "title": item["title"] or str(current.get("title", "")),
                "url": item["url"] or str(current.get("url", "")),
            }
            updated.append(merged)
            changed = changed or merged != current
            seen = True
        else:
            updated.append(current)
    if not seen:
        updated.append(item)
        changed = True
    return updated, changed


def upsert_watchlist_markets(
    watchlist: list[Mapping[str, Any]],
    rows: pd.DataFrame | Iterable[Mapping[str, Any]],
) -> tuple[list[dict[str, str]], int]:
    """Bulk-add or refresh market rows in a saved-market list."""

    iterable: Iterable[Mapping[str, Any]]
    if isinstance(rows, pd.DataFrame):
        iterable = rows.to_dict("records")
    else:
        iterable = rows
    updated: list[dict[str, str]] = [dict(item) for item in watchlist]
    changed = 0
    for row in iterable:
        updated, row_changed = upsert_watchlist_market(updated, row)
        if row_changed:
            changed += 1
    return updated, changed


def remove_watchlist_market(watchlist: list[Mapping[str, Any]], market_key: str) -> tuple[list[dict[str, Any]], bool]:
    """Remove a saved market by market_key."""

    key = str(market_key or "").strip()
    updated = [dict(item) for item in watchlist if str(item.get("market_key", "")).strip() != key]
    return updated, len(updated) != len(watchlist)


def upsert_followed_wallet(wallets: list[str], wallet: str) -> tuple[list[str], bool]:
    """Add a valid EVM wallet once, case-insensitive, preserving existing order."""

    value = str(wallet or "").strip()
    if not re.fullmatch(r"0x[a-fA-F0-9]{40}", value):
        return list(wallets), False
    existing = {str(item).lower() for item in wallets}
    if value.lower() in existing:
        return list(wallets), False
    return [str(item) for item in wallets] + [value], True


def upsert_followed_wallets(
    wallets: list[str],
    rows: pd.DataFrame | Iterable[Mapping[str, Any] | str],
    wallet_column: str = "wallet",
) -> tuple[list[str], int]:
    """Bulk-add valid EVM wallets, case-insensitive, preserving order."""

    if isinstance(rows, pd.DataFrame):
        iterable: Iterable[Any] = rows[wallet_column].tolist() if wallet_column in rows else []
    else:
        iterable = rows
    updated = [str(item) for item in wallets]
    changed = 0
    for item in iterable:
        value = item.get(wallet_column, "") if isinstance(item, Mapping) else item
        try:
            if pd.isna(value):
                continue
        except (TypeError, ValueError):
            pass
        updated, row_changed = upsert_followed_wallet(updated, str(value))
        if row_changed:
            changed += 1
    return updated, changed


def tracked_trader_rows(
    wallets: Iterable[str],
    leaderboard: pd.DataFrame | None = None,
    flow_scores: pd.DataFrame | None = None,
    position_values: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Build a PredictParity-style tracked-trader table from followed wallets."""

    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, wallet in enumerate(wallets):
        value = str(wallet or "").strip()
        if not re.fullmatch(r"0x[a-fA-F0-9]{40}", value):
            continue
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        rows.append({"tracked_order": index + 1, "wallet": value, "wallet_key": key})
    if not rows:
        return pd.DataFrame(
            columns=[
                "tracked_order",
                "wallet",
                "trader",
                "pnl",
                "volume",
                "positions_value",
                "open_positions",
                "open_markets",
                "recent_trades",
                "recent_notional",
                "largest_trade",
                "markets",
                "trades_per_hour",
                "whale_score",
                "bot_score",
                "flow_trait",
                "last_seen",
                "tracked_status",
                "verified",
            ]
        )

    frame = pd.DataFrame(rows)
    for source, columns in (
        (
            leaderboard,
            ["wallet", "rank", "platform", "trader", "pnl", "volume", "x_username", "verified", "profileImage"],
        ),
        (
            flow_scores,
            [
                "wallet",
                "trader",
                "recent_trades",
                "recent_notional",
                "avg_trade",
                "largest_trade",
                "markets",
                "trades_per_hour",
                "whale_score",
                "bot_score",
                "flow_trait",
                "first_seen",
                "last_seen",
            ],
        ),
        (
            position_values,
            ["wallet", "positions_value", "open_positions", "open_markets"],
        ),
    ):
        if source is None or source.empty or "wallet" not in source:
            continue
        available = [column for column in columns if column in source.columns]
        values = source[available].copy()
        values["wallet_key"] = values["wallet"].astype(str).str.lower()
        values = values.drop_duplicates("wallet_key").drop(columns=["wallet"], errors="ignore")
        frame = frame.merge(values, on="wallet_key", how="left", suffixes=("", "_source"))
        for column in set(values.columns).difference({"wallet_key"}):
            fetched = f"{column}_source"
            if fetched in frame:
                if column in frame:
                    frame[column] = frame[column].combine_first(frame[fetched])
                else:
                    frame[column] = frame[fetched]
                frame = frame.drop(columns=[fetched])

    for column, default in {
        "trader": "",
        "platform": "Polymarket",
        "flow_trait": "Tracked",
        "x_username": "",
        "profileImage": "",
    }.items():
        if column not in frame:
            frame[column] = default
        frame[column] = frame[column].fillna(default)
    frame["trader"] = frame["trader"].where(frame["trader"].astype(str).str.strip().ne(""), frame["wallet"].astype(str).str.slice(0, 10))

    for column in [
        "rank",
        "pnl",
        "volume",
        "positions_value",
        "open_positions",
        "open_markets",
        "recent_trades",
        "recent_notional",
        "avg_trade",
        "largest_trade",
        "markets",
        "trades_per_hour",
        "whale_score",
        "bot_score",
    ]:
        if column not in frame:
            frame[column] = 0.0
        frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0.0)
    if "verified" not in frame:
        frame["verified"] = False
    frame["verified"] = frame["verified"].fillna(False).astype(bool)
    if "last_seen" in frame:
        frame["last_seen"] = pd.to_datetime(frame["last_seen"], utc=True, errors="coerce")
    else:
        frame["last_seen"] = pd.NaT
    frame["tracked_status"] = "Idle"
    frame.loc[(frame["positions_value"] > 0) | (frame["recent_trades"] > 0), "tracked_status"] = "Active"
    frame = frame.drop(columns=["wallet_key"], errors="ignore")
    return frame.sort_values(["tracked_status", "positions_value", "recent_notional"], ascending=[True, False, False]).reset_index(drop=True)


def market_watch_signal(
    row: Mapping[str, Any],
    *,
    now: Any | None = None,
    move_threshold: float = 0.03,
    spread_threshold: float = 0.03,
    ending_days: int = 7,
) -> str:
    """Classify a watched market into the strongest Track-page signal."""

    change = abs(_num(row.get("change_1h"), 0.0) or 0.0)
    if change >= float(move_threshold):
        return "Fast move"
    spread = _num(row.get("spread"))
    if spread is not None and float(spread) <= float(spread_threshold):
        return "Tight spread"
    end = _safe_ts(row.get("end_time"))
    if end is not None:
        now_ts = _utc_timestamp(now)
        seconds = (end - now_ts).total_seconds()
        if 0 <= seconds <= max(int(ending_days), 0) * 86_400:
            return "Ending soon"
    return ""


def add_market_watch_signals(
    markets: pd.DataFrame,
    *,
    now: Any | None = None,
    move_threshold: float = 0.03,
    spread_threshold: float = 0.03,
    ending_days: int = 7,
) -> pd.DataFrame:
    """Add Track-page watch_signal labels to a market frame."""

    if markets.empty:
        result = markets.copy()
        result["watch_signal"] = pd.Series(dtype=str)
        return result
    result = markets.copy()
    result["watch_signal"] = result.apply(
        lambda row: market_watch_signal(
            row,
            now=now,
            move_threshold=move_threshold,
            spread_threshold=spread_threshold,
            ending_days=ending_days,
        ),
        axis=1,
    )
    return result


def wallet_activity_summary(activity: pd.DataFrame) -> dict[str, float]:
    if activity.empty:
        return {"events": 0.0, "notional": 0.0, "buys": 0.0, "sells": 0.0, "settlements": 0.0}
    df = activity.copy()
    notional = pd.to_numeric(df.get("notional", 0), errors="coerce").fillna(0.0)
    type_text = df.get("type", pd.Series("", index=df.index)).astype(str).str.upper()
    side_text = df.get("side", pd.Series("", index=df.index)).astype(str).str.upper()
    return {
        "events": float(len(df)),
        "notional": float(notional.sum()),
        "buys": float((side_text.eq("BUY") | type_text.eq("BUY")).sum()),
        "sells": float((side_text.eq("SELL") | type_text.eq("SELL")).sum()),
        "settlements": float(type_text.isin(["REDEEM", "MERGE", "SPLIT"]).sum()),
    }


def now_utc_label() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
