"""Market intelligence terminal for Polymarket and Kalshi.

Run with:
    python -m streamlit run prediction_terminal.py
"""

from __future__ import annotations

import json
import html
import re
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

from src import copy_trading as ct
from src import prediction_markets as md


st.set_page_config(
    page_title="Market Intel Terminal",
    page_icon="P",
    layout="wide",
    initial_sidebar_state="expanded",
)


ACCENT = "#35d07f"
BLUE = "#49a5ff"
AMBER = "#f5b84b"
RED = "#ff5a68"
MUTED = "#8892a0"
PANEL = "#121922"
BG = "#080c11"
RESEARCH_START_CASH = 1000.0
WORKSPACES = [
    "Overview",
    "Search",
    "Markets",
    "Traders",
    "Track",
    "Live Trades",
    "Wallets",
    "Copy Trade",
    "Whale Flow",
    "Cross-Venue",
    "Monitor",
    "Alerts",
    "Resolved",
    "Portfolio",
]
SEARCH_RESULT_TYPES = ["Markets", "Traders", "Trades", "News", "Cross-Venue", "Alerts", "Tracked"]
COPY_SIDE_FILTERS = ["BUY", "SELL"]
COPY_ORDER_STATUS_FILTERS = ["copied", "settled", "skipped", "baseline", "duplicate"]
PREDICTPARITY_NAV = ["Markets", "Traders", "Track", "Live Trades", "Monitor", "Portfolio"]
PAGE_QUERY_SLUGS = {page: page.lower().replace(" ", "-") for page in WORKSPACES}
PAGE_BY_QUERY_SLUG = {slug: page for page, slug in PAGE_QUERY_SLUGS.items()}


def inject_css() -> None:
    st.markdown(
        f"""
        <style>
        .stApp {{
            background: {BG};
            color: #edf2f7;
        }}
        .block-container {{
            padding-top: 1.2rem;
            padding-bottom: 2.5rem;
            max-width: 1560px;
        }}
        [data-testid="stSidebar"] {{
            background: #0b1017;
            border-right: 1px solid #1c2633;
        }}
        [data-testid="stMetric"] {{
            background: {PANEL};
            border: 1px solid #202b39;
            border-radius: 8px;
            padding: 0.85rem 0.95rem;
        }}
        [data-testid="stMetricLabel"] p {{
            color: {MUTED};
            font-size: 0.74rem;
            text-transform: uppercase;
            letter-spacing: 0;
        }}
        [data-testid="stMetricValue"] {{
            font-family: "JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, monospace;
            font-size: 1.15rem;
        }}
        div[data-testid="stVerticalBlockBorderWrapper"] {{
            border-color: #202b39;
            border-radius: 8px;
            background: #101821;
        }}
        .terminal-kicker {{
            color: {MUTED};
            font-family: "JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, monospace;
            text-transform: uppercase;
            font-size: 0.78rem;
            letter-spacing: 0;
            margin-bottom: 0.15rem;
        }}
        .terminal-title {{
            font-size: 1.75rem;
            font-weight: 700;
            line-height: 1.1;
            margin-bottom: 0.2rem;
        }}
        .terminal-subtitle {{
            color: {MUTED};
            font-size: 0.95rem;
            margin-bottom: 1rem;
        }}
        .small-note {{
            color: {MUTED};
            font-size: 0.82rem;
            line-height: 1.4;
        }}
        .signal {{
            font-family: "JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, monospace;
            font-size: 0.78rem;
            color: {ACCENT};
            border: 1px solid #1f6d45;
            border-radius: 999px;
            padding: 0.2rem 0.45rem;
            display: inline-block;
            margin-right: 0.35rem;
        }}
        .warning-chip {{
            color: {AMBER};
            border-color: #71561f;
        }}
        .filter-strip {{
            display: flex;
            flex-wrap: wrap;
            gap: 0.4rem;
            margin: 0.45rem 0 0.75rem;
        }}
        .filter-chip {{
            color: #dce6ef;
            border: 1px solid #27364a;
            background: #0e151d;
            border-radius: 999px;
            padding: 0.22rem 0.55rem;
            font-size: 0.78rem;
            line-height: 1.2;
        }}
        .market-stats {{
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 0.55rem;
            margin: 0.85rem 0 0.9rem;
        }}
        .market-stat {{
            min-width: 0;
            border: 1px solid #202b39;
            background: #121922;
            border-radius: 7px;
            padding: 0.62rem 0.55rem;
        }}
        .market-stat span {{
            display: block;
            color: {MUTED};
            font-size: 0.66rem;
            text-transform: uppercase;
            margin-bottom: 0.3rem;
        }}
        .market-stat strong {{
            display: block;
            color: #edf2f7;
            font-family: "JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, monospace;
            font-size: 0.92rem;
            line-height: 1.15;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}
        .stTabs [data-baseweb="tab-list"] {{
            gap: 0.5rem;
        }}
        .stTabs [data-baseweb="tab"] {{
            border-radius: 7px;
            border: 1px solid #202b39;
            background: #0e151d;
            padding: 0.35rem 0.75rem;
        }}
        .stTabs [aria-selected="true"] {{
            background: #182536;
            border-color: #304158;
        }}
        .command-shell {{
            border: 1px solid #243044;
            background: #0d141d;
            border-radius: 8px;
            padding: 0.5rem 0.65rem;
            color: #dce6ef;
            margin-bottom: 0.85rem;
        }}
        .command-hint {{
            color: {MUTED};
            font-size: 0.78rem;
        }}
        .parity-nav-caption {{
            color: {MUTED};
            font-size: 0.68rem;
            text-transform: uppercase;
            margin: 0 0 0.15rem;
        }}
        .auth-note {{
            border: 1px solid #27364a;
            background: #0e151d;
            border-radius: 8px;
            padding: 0.7rem 0.8rem;
            color: #dce6ef;
            font-size: 0.86rem;
            line-height: 1.35;
            margin: 0.35rem 0 0.75rem;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


inject_css()


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


def related_market_group(markets: pd.DataFrame, current: pd.Series, include_current: bool = True, limit: int = 20) -> pd.DataFrame:
    if markets.empty:
        return pd.DataFrame()
    frame = markets.copy()
    current_key = str(current.get("market_key", "") or "")
    event_slug = str(current.get("event_slug", "") or "")
    if event_slug and "event_slug" in frame:
        related = frame[frame["event_slug"].astype(str).eq(event_slug)].copy()
    else:
        family = market_title_family_key(current.get("title", ""))
        if not family or "title" not in frame:
            return pd.DataFrame()
        frame["_family_key"] = frame["title"].map(market_title_family_key)
        related = frame[frame["_family_key"].eq(family)].drop(columns=["_family_key"], errors="ignore").copy()
    if not include_current and current_key and "market_key" in related:
        related = related[~related["market_key"].astype(str).eq(current_key)]
    if related.empty:
        return related
    related["_end_sort"] = pd.to_datetime(related.get("end_time"), utc=True, errors="coerce")
    if "activity_volume" not in related:
        related["activity_volume"] = numeric_col(related, "volume_24h")
    if "closed" not in related:
        related["closed"] = False
    return (
        related.sort_values(["closed", "_end_sort", "activity_volume"], ascending=[True, True, False], na_position="last")
        .drop(columns=["_end_sort"], errors="ignore")
        .head(limit)
        .reset_index(drop=True)
    )


def short_addr(value: str, width: int = 6) -> str:
    if not value:
        return "-"
    if len(value) <= width * 2 + 2:
        return value
    return f"{value[: width + 2]}...{value[-width:]}"


def x_profile_url(username: Any) -> str:
    if hasattr(md, "x_profile_url"):
        return md.x_profile_url(username)
    handle = str(username or "").strip()
    if not handle:
        return ""
    url_match = re.search(r"(?:twitter\.com|x\.com)/@?([^/?#]+)", handle, flags=re.IGNORECASE)
    if url_match:
        handle = url_match.group(1)
    handle = handle.strip().strip("/").lstrip("@")
    return f"https://x.com/{handle}" if re.fullmatch(r"[A-Za-z0-9_]{1,15}", handle) else ""


def predictparity_trader_url(handle: Any) -> str:
    if hasattr(md, "predictparity_trader_url"):
        return md.predictparity_trader_url(handle)
    text = str(handle or "").strip()
    url_match = re.search(r"/(?:profile|traders/p)/@?([^/?#]+)", text, flags=re.IGNORECASE)
    if url_match:
        text = url_match.group(1)
    text = text.strip().strip("/").lstrip("@").lower()
    if not text or re.fullmatch(r"0x[a-fA-F0-9]{40}", text):
        return ""
    return f"https://predictparity.com/traders/p/@{text}" if re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", text) else ""


def clean_table(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    if df.empty:
        return df
    return df[[c for c in columns if c in df.columns]].copy()


def dataframe_selected_row_index(event: Any) -> int | None:
    try:
        selection = getattr(event, "selection", None)
        if selection is None and isinstance(event, dict):
            selection = event.get("selection")
        rows = getattr(selection, "rows", None)
        if rows is None and isinstance(selection, dict):
            rows = selection.get("rows")
        if rows:
            return int(rows[0])
    except (TypeError, ValueError):
        return None
    return None


def render_filter_chips(labels: list[str]) -> None:
    if not labels:
        return
    chips = "".join(f'<span class="filter-chip">{html.escape(label)}</span>' for label in labels)
    st.markdown(f'<div class="filter-strip">{chips}</div>', unsafe_allow_html=True)


def render_filter_clear_buttons(actions: list[tuple[str, dict[str, Any]]], prefix: str) -> None:
    if not actions:
        return
    with st.expander("Remove filters", expanded=False):
        for start in range(0, len(actions), 4):
            cols = st.columns(4)
            for col, (label, updates) in zip(cols, actions[start : start + 4]):
                if col.button(f"Clear {label}", key=f"{prefix}_clear_{start}_{label}", width="stretch"):
                    st.session_state[f"{prefix}_clear_pending"] = updates
                    st.rerun()


def market_filter_defaults(categories: list[str], query: str = "") -> dict[str, Any]:
    default_excluded = [item for item in categories if md.market_category_label(item).casefold() in {"sports", "crypto"}]
    return {
        "markets_search": query,
        "markets_view_mode": "Table",
        "markets_quick_filter": "Trending",
        "markets_platform_filter": ["Polymarket", "Kalshi"],
        "markets_status_filter": "Active",
        "markets_include_categories": [],
        "markets_exclude_categories": default_excluded,
        "markets_prob_preset": "5-95%",
        "markets_custom_prob": (5, 95),
        "markets_spread_preset": "<7c",
        "markets_custom_spread": 7.0,
        "markets_liquidity_preset": "All",
        "markets_custom_liquidity": 0,
        "markets_end_preset": "Open",
        "markets_custom_days": 30,
        "markets_volume_1h_preset": "All",
        "markets_custom_volume_1h": 0,
        "markets_volume_preset": "All",
        "markets_custom_volume": 0,
        "markets_age_preset": "All",
        "markets_custom_age_days": 30,
        "markets_sort_by": "activity_volume",
        "markets_limit_rows": 80,
        "markets_volume_delta_1h_preset": "All",
        "markets_custom_volume_delta_1h": 25.0,
        "markets_volume_delta_24h_preset": "All",
        "markets_custom_volume_delta_24h": 25.0,
        "markets_change_preset": "All",
        "markets_custom_change": 1.0,
        "markets_change_24h_preset": "All",
        "markets_custom_change_24h": 1.0,
        "markets_show_more_categories": False,
    }


def reset_market_filter_widgets(categories: list[str]) -> None:
    """Reset market scanner controls to the current Parity-style defaults."""

    defaults = market_filter_defaults(categories)
    for key, value in defaults.items():
        st.session_state[key] = value


def trader_filter_defaults(query: str = "") -> dict[str, Any]:
    return {
        "trader_search": query,
        "trader_view_mode": "Table",
        "trader_column_preset": "Parity",
        "trader_time_period": "ALL",
        "trader_order_by": "PNL",
        "trader_rows": 100,
        "trader_active_only": True,
        "trader_bots_only": False,
        "trader_bot_score_min": 65,
        "trader_pnl_preset": "All",
        "trader_custom_pnl": 0,
        "trader_volume_preset": "All",
        "trader_custom_volume": 0,
        "trader_position_preset": ">$100",
        "trader_custom_position": 100,
        "trader_active_positions_min": 0,
        "trader_trait_filter": [],
        "trader_enrich_positions": True,
        "trader_win_rate_preset": "All",
        "trader_custom_win_rate": 50,
        "trader_enrich_win_rates": True,
        "trader_min_closed_positions": 5,
        "trader_assets_preset": "All",
        "trader_custom_assets": 0,
        "trader_balance_preset": "All",
        "trader_custom_balance": 0,
        "trader_account_age_preset": "All",
        "trader_custom_account_age": 365,
        "trader_enrich_accounts": False,
        "trader_account_enrich_rows": 15,
    }


def reset_trader_filter_widgets(query: str = "") -> None:
    for key, value in trader_filter_defaults(query).items():
        st.session_state[key] = value


def search_filter_defaults(query: str = "", rows: int = 80) -> dict[str, Any]:
    return {
        "search_query": query,
        "search_platforms": ["Polymarket", "Kalshi"],
        "search_rows": _bounded_int(rows, 80, 10, 250),
        "search_min_value": 0,
        "search_result_types": list(SEARCH_RESULT_TYPES),
        "search_active_markets_only": True,
        "search_tracked_only": False,
        "search_broad_pairs": True,
    }


def reset_search_filter_widgets(query: str = "", rows: int = 80) -> None:
    for key, value in search_filter_defaults(query, rows).items():
        st.session_state[key] = value


def live_trade_filter_defaults(query: str = "", rows: int = 250) -> dict[str, Any]:
    return {
        "live_search": query,
        "live_platforms": ["Polymarket", "Kalshi"],
        "live_sides": [],
        "live_min_notional": 0,
        "live_rows": _bounded_int(rows, 250, 50, 500),
        "live_tracked_markets_only": False,
        "live_tracked_wallets_only": False,
        "live_large_only": False,
    }


def reset_live_trade_filter_widgets(query: str = "", rows: int = 250) -> None:
    for key, value in live_trade_filter_defaults(query, rows).items():
        st.session_state[key] = value


def cross_venue_filter_defaults(query: str = "") -> dict[str, Any]:
    return {
        "cross_query": query,
        "cross_min_similarity": 0.22,
        "cross_max_pairs": 60,
        "cross_min_gap_cents": 0.0,
        "cross_min_pm_volume": 0,
        "cross_min_ks_volume": 0,
        "cross_lower_filter": "Any",
        "cross_min_price_pct": 1,
        "cross_max_price_pct": 99,
    }


def reset_cross_venue_filter_widgets(query: str = "") -> None:
    for key, value in cross_venue_filter_defaults(query).items():
        st.session_state[key] = value


def monitor_filter_defaults(query: str = "", rows: int = 100, min_whale_notional: int = 2500) -> dict[str, Any]:
    return {
        "monitor_search": query,
        "monitor_platforms": ["Polymarket", "Kalshi"],
        "monitor_signal_types": list(MONITOR_SIGNAL_TYPES),
        "monitor_rows": _bounded_int(rows, 100, 25, 250),
        "monitor_watched_only": False,
        "monitor_min_volume": 0,
        "monitor_min_liquidity": 0,
        "monitor_min_move": 3.0,
        "monitor_max_spread": 7.0,
        "monitor_min_whale": max(0, int(min_whale_notional)),
        "monitor_ending_days": 7,
        "monitor_holder_checks": 6,
        "monitor_holder_threshold": 0.25,
    }


def reset_monitor_filter_widgets(query: str = "", rows: int = 100, min_whale_notional: int = 2500) -> None:
    for key, value in monitor_filter_defaults(query, rows, min_whale_notional).items():
        st.session_state[key] = value


def alert_filter_defaults(query: str = "", rows: int = 100, min_whale_notional: int = 2500) -> dict[str, Any]:
    return {
        "alert_search": query,
        "alert_platforms": ["Polymarket", "Kalshi"],
        "alert_signal_types": list(MONITOR_SIGNAL_TYPES),
        "alert_rows": _bounded_int(rows, 100, 25, 250),
        "alert_hits_only": False,
        "alert_min_volume": 0,
        "alert_min_liquidity": 0,
        "alert_min_move": 3.0,
        "alert_max_spread": 7.0,
        "alert_min_whale": max(0, int(min_whale_notional)),
        "alert_ending_days": 7,
        "alert_holder_checks": 3,
        "alert_holder_threshold": 0.25,
    }


def reset_alert_filter_widgets(query: str = "", rows: int = 100, min_whale_notional: int = 2500) -> None:
    for key, value in alert_filter_defaults(query, rows, min_whale_notional).items():
        st.session_state[key] = value


def resolved_filter_defaults(query: str = "", rows: int = 250) -> dict[str, Any]:
    return {
        "resolved_search": query,
        "resolved_rows": _bounded_int(rows, 250, 50, 500),
        "resolved_outcomes": ["Yes", "No"],
        "resolved_decisive_only": False,
        "resolved_min_volume": 0,
        "resolved_min_liquidity": 0,
        "resolved_category_filter": [],
        "resolved_closed_window": "All",
        "resolved_final_yes_range": (0, 100),
        "resolved_sort_by": "closed_time",
    }


def reset_resolved_filter_widgets(query: str = "", rows: int = 250) -> None:
    for key, value in resolved_filter_defaults(query, rows).items():
        st.session_state[key] = value


def portfolio_filter_defaults(query: str = "", rows: int = 150) -> dict[str, Any]:
    return {
        "portfolio_search": query,
        "portfolio_platforms": ["Polymarket", "Kalshi"],
        "portfolio_outcomes": ["Yes", "No"],
        "portfolio_rows": _bounded_int(rows, 150, 25, 500),
        "portfolio_min_value": 0,
        "portfolio_min_pnl": -1_000_000,
        "portfolio_sources": ["Research", "Copy", "Watchlist", "History"],
        "portfolio_copy_statuses": list(COPY_ORDER_STATUS_FILTERS),
        "portfolio_losers_only": False,
    }


def reset_portfolio_filter_widgets(query: str = "", rows: int = 150) -> None:
    for key, value in portfolio_filter_defaults(query, rows).items():
        st.session_state[key] = value


def copy_trade_filter_defaults(query: str = "", rows: int = 150) -> dict[str, Any]:
    return {
        "copy_trade_search": query,
        "copy_trade_sides": list(COPY_SIDE_FILTERS),
        "copy_trade_statuses": list(COPY_ORDER_STATUS_FILTERS),
        "copy_trade_rows": _bounded_int(rows, 150, 25, 500),
        "copy_trade_min_tony_notional": 0,
        "copy_trade_min_copy_notional": 0,
        "copy_trade_min_position_value": 0,
        "copy_trade_min_pnl": -1_000_000,
        "copy_trade_reason_query": "",
        "copy_trade_latency_only": False,
    }


def reset_copy_trade_filter_widgets(query: str = "", rows: int = 150) -> None:
    for key, value in copy_trade_filter_defaults(query, rows).items():
        st.session_state[key] = value


def track_filter_defaults(query: str = "", rows: int = 80) -> dict[str, Any]:
    return {
        "track_search": query,
        "track_platforms": ["Polymarket", "Kalshi"],
        "track_min_watch_volume": 0,
        "track_rows": _bounded_int(rows, 80, 10, 250),
        "track_signal_filter": "Any",
        "track_min_wallet_value": 0,
    }


def reset_track_filter_widgets(query: str = "", rows: int = 80) -> None:
    for key, value in track_filter_defaults(query, rows).items():
        st.session_state[key] = value


def whale_flow_filter_defaults(query: str = "", rows: int = 200, min_notional: int = 2500) -> dict[str, Any]:
    return {
        "whale_query": query,
        "whale_platforms": ["Polymarket", "Kalshi"],
        "whale_sides": [],
        "whale_rows": _bounded_int(rows, 200, 50, 500),
        "whale_min_notional": max(0, int(min_notional)),
        "whale_min_wallet_notional": 0,
        "whale_min_wallet_trades": 1,
        "whale_bias_filter": "Any",
        "whale_tracked_wallets_only": False,
    }


def reset_whale_flow_filter_widgets(query: str = "", rows: int = 200, min_notional: int = 2500) -> None:
    for key, value in whale_flow_filter_defaults(query, rows, min_notional).items():
        st.session_state[key] = value


def overview_filter_defaults(query: str = "", rows: int = 6, min_flow: int = 2500, categories: list[str] | None = None) -> dict[str, Any]:
    default_excluded = [
        item
        for item in (categories or [])
        if md.market_category_label(item).casefold() in {"sports", "crypto"}
    ]
    return {
        "overview_search": query,
        "overview_platforms": ["Polymarket", "Kalshi"],
        "overview_featured_source": "Polymarket",
        "overview_market_rows": _bounded_int(rows, 6, 3, 24),
        "overview_include_categories": [],
        "overview_exclude_categories": default_excluded,
        "overview_min_volume": 0,
        "overview_min_liquidity": 0,
        "overview_min_flow_notional": max(0, int(min_flow)),
        "overview_active_only": True,
        "overview_show_news": True,
    }


def reset_overview_filter_widgets(query: str = "", rows: int = 6, min_flow: int = 2500, categories: list[str] | None = None) -> None:
    for key, value in overview_filter_defaults(query, rows, min_flow, categories).items():
        st.session_state[key] = value


def _choice(value: Any, options: list[str], default: str) -> str:
    text = str(value)
    return text if text in options else default


def _bounded_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _bounded_float(value: Any, default: float, minimum: float, maximum: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _choice_list(values: Any, options: list[str], default: list[str]) -> list[str]:
    selected = [str(item) for item in list(values or []) if str(item) in options]
    return selected if selected else list(default)


def _optional_choice_list(values: Any, options: list[str]) -> list[str]:
    return [str(item) for item in list(values or []) if str(item) in options]


def apply_overview_filter_view_widgets(view: dict[str, Any], categories: list[str] | None = None) -> None:
    category_options = list(categories or [])
    defaults = overview_filter_defaults(categories=category_options)
    values = {
        "overview_search": str(view.get("query", defaults["overview_search"])),
        "overview_platforms": _choice_list(view.get("platforms", defaults["overview_platforms"]), ["Polymarket", "Kalshi"], defaults["overview_platforms"]),
        "overview_featured_source": _choice(view.get("featured_source", defaults["overview_featured_source"]), ["Polymarket", "Any"], "Polymarket"),
        "overview_market_rows": _bounded_int(view.get("market_rows", defaults["overview_market_rows"]), 6, 3, 24),
        "overview_include_categories": _optional_choice_list(view.get("include_categories", defaults["overview_include_categories"]), category_options),
        "overview_exclude_categories": _optional_choice_list(view.get("exclude_categories", defaults["overview_exclude_categories"]), category_options),
        "overview_min_volume": int(_bounded_float(view.get("min_volume", defaults["overview_min_volume"]), 0.0, 0.0, 1_000_000_000.0)),
        "overview_min_liquidity": int(_bounded_float(view.get("min_liquidity", defaults["overview_min_liquidity"]), 0.0, 0.0, 1_000_000_000.0)),
        "overview_min_flow_notional": int(_bounded_float(view.get("min_flow_notional", defaults["overview_min_flow_notional"]), 0.0, 0.0, 1_000_000_000.0)),
        "overview_active_only": bool(view.get("active_only", defaults["overview_active_only"])),
        "overview_show_news": bool(view.get("show_news", defaults["overview_show_news"])),
    }
    for key, value in values.items():
        st.session_state[key] = value


def apply_search_filter_view_widgets(view: dict[str, Any]) -> None:
    defaults = search_filter_defaults()
    values = {
        "search_query": str(view.get("query", defaults["search_query"])),
        "search_platforms": _choice_list(view.get("platforms", defaults["search_platforms"]), ["Polymarket", "Kalshi"], defaults["search_platforms"]),
        "search_rows": _bounded_int(view.get("rows", defaults["search_rows"]), 80, 10, 250),
        "search_min_value": int(_bounded_float(view.get("min_value", defaults["search_min_value"]), 0.0, 0.0, 1_000_000_000.0)),
        "search_result_types": _choice_list(view.get("result_types", defaults["search_result_types"]), SEARCH_RESULT_TYPES, defaults["search_result_types"]),
        "search_active_markets_only": bool(view.get("active_markets_only", defaults["search_active_markets_only"])),
        "search_tracked_only": bool(view.get("tracked_only", defaults["search_tracked_only"])),
        "search_broad_pairs": bool(view.get("broad_pairs", defaults["search_broad_pairs"])),
    }
    for key, value in values.items():
        st.session_state[key] = value


def apply_live_trade_filter_view_widgets(view: dict[str, Any]) -> None:
    defaults = live_trade_filter_defaults()
    values = {
        "live_search": str(view.get("query", defaults["live_search"])),
        "live_platforms": _choice_list(view.get("platforms", defaults["live_platforms"]), ["Polymarket", "Kalshi"], defaults["live_platforms"]),
        "live_sides": _choice_list(view.get("sides", defaults["live_sides"]), ["BUY", "SELL", "yes", "no"], defaults["live_sides"]),
        "live_min_notional": int(_bounded_float(view.get("min_notional", defaults["live_min_notional"]), 0.0, 0.0, 1_000_000_000.0)),
        "live_rows": _bounded_int(view.get("rows", defaults["live_rows"]), 250, 50, 500),
        "live_tracked_markets_only": bool(view.get("tracked_markets_only", defaults["live_tracked_markets_only"])),
        "live_tracked_wallets_only": bool(view.get("tracked_wallets_only", defaults["live_tracked_wallets_only"])),
        "live_large_only": bool(view.get("large_only", defaults["live_large_only"])),
    }
    for key, value in values.items():
        st.session_state[key] = value


def apply_track_filter_view_widgets(view: dict[str, Any]) -> None:
    defaults = track_filter_defaults()
    values = {
        "track_search": str(view.get("query", defaults["track_search"])),
        "track_platforms": _choice_list(view.get("platforms", defaults["track_platforms"]), ["Polymarket", "Kalshi"], defaults["track_platforms"]),
        "track_min_watch_volume": int(_bounded_float(view.get("min_watch_volume", defaults["track_min_watch_volume"]), 0.0, 0.0, 1_000_000_000.0)),
        "track_rows": _bounded_int(view.get("rows", defaults["track_rows"]), 80, 10, 250),
        "track_signal_filter": _choice(view.get("signal_filter", defaults["track_signal_filter"]), ["Any", "Fast move", "Tight spread", "None"], "Any"),
        "track_min_wallet_value": int(_bounded_float(view.get("min_wallet_value", defaults["track_min_wallet_value"]), 0.0, 0.0, 1_000_000_000.0)),
    }
    for key, value in values.items():
        st.session_state[key] = value


def apply_whale_flow_filter_view_widgets(view: dict[str, Any]) -> None:
    defaults = whale_flow_filter_defaults()
    values = {
        "whale_query": str(view.get("query", defaults["whale_query"])),
        "whale_platforms": _choice_list(view.get("platforms", defaults["whale_platforms"]), ["Polymarket", "Kalshi"], defaults["whale_platforms"]),
        "whale_sides": _optional_choice_list(view.get("sides", defaults["whale_sides"]), ["BUY", "SELL", "yes", "no"]),
        "whale_rows": _bounded_int(view.get("rows", defaults["whale_rows"]), 200, 50, 500),
        "whale_min_notional": int(_bounded_float(view.get("min_notional", defaults["whale_min_notional"]), 0.0, 0.0, 1_000_000_000.0)),
        "whale_min_wallet_notional": int(_bounded_float(view.get("min_wallet_notional", defaults["whale_min_wallet_notional"]), 0.0, 0.0, 1_000_000_000.0)),
        "whale_min_wallet_trades": _bounded_int(view.get("min_wallet_trades", defaults["whale_min_wallet_trades"]), 1, 1, 500),
        "whale_bias_filter": _choice(view.get("bias_filter", defaults["whale_bias_filter"]), ["Any", "YES", "NO", "Mixed"], "Any"),
        "whale_tracked_wallets_only": bool(view.get("tracked_wallets_only", defaults["whale_tracked_wallets_only"])),
    }
    for key, value in values.items():
        st.session_state[key] = value


def apply_cross_venue_filter_view_widgets(view: dict[str, Any]) -> None:
    defaults = cross_venue_filter_defaults()
    values = {
        "cross_query": str(view.get("query", defaults["cross_query"])),
        "cross_min_similarity": _bounded_float(view.get("min_similarity", defaults["cross_min_similarity"]), 0.22, 0.10, 0.70),
        "cross_max_pairs": _bounded_int(view.get("max_pairs", defaults["cross_max_pairs"]), 60, 10, 150),
        "cross_min_gap_cents": _bounded_float(view.get("min_gap_cents", defaults["cross_min_gap_cents"]), 0.0, 0.0, 100.0),
        "cross_min_pm_volume": int(_bounded_float(view.get("min_pm_volume", defaults["cross_min_pm_volume"]), 0.0, 0.0, 1_000_000_000.0)),
        "cross_min_ks_volume": int(_bounded_float(view.get("min_ks_volume", defaults["cross_min_ks_volume"]), 0.0, 0.0, 1_000_000_000.0)),
        "cross_lower_filter": _choice(view.get("lower_filter", defaults["cross_lower_filter"]), ["Any", "Polymarket", "Kalshi"], "Any"),
        "cross_min_price_pct": _bounded_int(view.get("min_price_pct", defaults["cross_min_price_pct"]), 1, 0, 100),
        "cross_max_price_pct": _bounded_int(view.get("max_price_pct", defaults["cross_max_price_pct"]), 99, 0, 100),
    }
    for key, value in values.items():
        st.session_state[key] = value


def apply_monitor_filter_view_widgets(view: dict[str, Any]) -> None:
    defaults = monitor_filter_defaults()
    values = {
        "monitor_search": str(view.get("query", defaults["monitor_search"])),
        "monitor_platforms": _choice_list(view.get("platforms", defaults["monitor_platforms"]), ["Polymarket", "Kalshi"], defaults["monitor_platforms"]),
        "monitor_signal_types": _choice_list(view.get("signal_types", defaults["monitor_signal_types"]), MONITOR_SIGNAL_TYPES, defaults["monitor_signal_types"]),
        "monitor_rows": _bounded_int(view.get("rows", defaults["monitor_rows"]), 100, 25, 250),
        "monitor_watched_only": bool(view.get("watched_only", defaults["monitor_watched_only"])),
        "monitor_min_volume": int(_bounded_float(view.get("min_volume", defaults["monitor_min_volume"]), 0.0, 0.0, 1_000_000_000.0)),
        "monitor_min_liquidity": int(_bounded_float(view.get("min_liquidity", defaults["monitor_min_liquidity"]), 0.0, 0.0, 1_000_000_000.0)),
        "monitor_min_move": _bounded_float(view.get("min_move", defaults["monitor_min_move"]), 3.0, 0.0, 100.0),
        "monitor_max_spread": _bounded_float(view.get("max_spread", defaults["monitor_max_spread"]), 7.0, 0.1, 100.0),
        "monitor_min_whale": int(_bounded_float(view.get("min_whale", defaults["monitor_min_whale"]), 0.0, 0.0, 1_000_000_000.0)),
        "monitor_ending_days": _bounded_int(view.get("ending_days", defaults["monitor_ending_days"]), 7, 1, 3650),
        "monitor_holder_checks": _bounded_int(view.get("holder_checks", defaults["monitor_holder_checks"]), 6, 0, 20),
        "monitor_holder_threshold": _bounded_float(view.get("holder_threshold", defaults["monitor_holder_threshold"]), 0.25, 0.05, 0.80),
    }
    for key, value in values.items():
        st.session_state[key] = value


def apply_alert_filter_view_widgets(view: dict[str, Any]) -> None:
    defaults = alert_filter_defaults()
    values = {
        "alert_search": str(view.get("query", defaults["alert_search"])),
        "alert_platforms": _choice_list(view.get("platforms", defaults["alert_platforms"]), ["Polymarket", "Kalshi"], defaults["alert_platforms"]),
        "alert_signal_types": _choice_list(view.get("signal_types", defaults["alert_signal_types"]), MONITOR_SIGNAL_TYPES, defaults["alert_signal_types"]),
        "alert_rows": _bounded_int(view.get("rows", defaults["alert_rows"]), 100, 25, 250),
        "alert_hits_only": bool(view.get("hits_only", defaults["alert_hits_only"])),
        "alert_min_volume": int(_bounded_float(view.get("min_volume", defaults["alert_min_volume"]), 0.0, 0.0, 1_000_000_000.0)),
        "alert_min_liquidity": int(_bounded_float(view.get("min_liquidity", defaults["alert_min_liquidity"]), 0.0, 0.0, 1_000_000_000.0)),
        "alert_min_move": _bounded_float(view.get("min_move", defaults["alert_min_move"]), 3.0, 0.0, 100.0),
        "alert_max_spread": _bounded_float(view.get("max_spread", defaults["alert_max_spread"]), 7.0, 0.1, 100.0),
        "alert_min_whale": int(_bounded_float(view.get("min_whale", defaults["alert_min_whale"]), 0.0, 0.0, 1_000_000_000.0)),
        "alert_ending_days": _bounded_int(view.get("ending_days", defaults["alert_ending_days"]), 7, 1, 3650),
        "alert_holder_checks": _bounded_int(view.get("holder_checks", defaults["alert_holder_checks"]), 3, 0, 20),
        "alert_holder_threshold": _bounded_float(view.get("holder_threshold", defaults["alert_holder_threshold"]), 0.25, 0.05, 0.80),
    }
    for key, value in values.items():
        st.session_state[key] = value


def _prob_range(value: Any, default: tuple[int, int] = (5, 95)) -> tuple[int, int]:
    try:
        raw = list(value)
        low = _bounded_int(raw[0], default[0], 0, 100)
        high = _bounded_int(raw[1], default[1], 0, 100)
    except (TypeError, IndexError):
        return default
    if low > high:
        low, high = high, low
    return (low, high)


def apply_resolved_filter_view_widgets(view: dict[str, Any], category_options: list[str] | None = None) -> None:
    defaults = resolved_filter_defaults()
    raw_categories = [str(item) for item in list(view.get("category_filter", defaults["resolved_category_filter"]) or []) if str(item)]
    if category_options is not None:
        categories = [item for item in raw_categories if item in set(category_options)]
    else:
        categories = raw_categories
    values = {
        "resolved_search": str(view.get("query", defaults["resolved_search"])),
        "resolved_rows": _bounded_int(view.get("rows", defaults["resolved_rows"]), 250, 50, 500),
        "resolved_outcomes": _choice_list(view.get("outcomes", defaults["resolved_outcomes"]), ["Yes", "No", "Multi", "Unknown"], defaults["resolved_outcomes"]),
        "resolved_decisive_only": bool(view.get("decisive_only", defaults["resolved_decisive_only"])),
        "resolved_min_volume": int(_bounded_float(view.get("min_volume", defaults["resolved_min_volume"]), 0.0, 0.0, 1_000_000_000.0)),
        "resolved_min_liquidity": int(_bounded_float(view.get("min_liquidity", defaults["resolved_min_liquidity"]), 0.0, 0.0, 1_000_000_000.0)),
        "resolved_category_filter": categories,
        "resolved_closed_window": _choice(view.get("closed_window", defaults["resolved_closed_window"]), ["All", "<7d", "<30d", "<90d", "<365d"], "All"),
        "resolved_final_yes_range": _prob_range(view.get("final_yes_range", defaults["resolved_final_yes_range"]), defaults["resolved_final_yes_range"]),
        "resolved_sort_by": _choice(view.get("sort_by", defaults["resolved_sort_by"]), ["closed_time", "volume", "liquidity", "final_yes_price", "category"], "closed_time"),
    }
    for key, value in values.items():
        st.session_state[key] = value


def apply_portfolio_filter_view_widgets(view: dict[str, Any]) -> None:
    defaults = portfolio_filter_defaults()

    def list_value(key: str, options: list[str]) -> list[str]:
        if key not in view:
            return list(defaults[f"portfolio_{key}"])
        return _optional_choice_list(view.get(key, []), options)

    values = {
        "portfolio_search": str(view.get("query", defaults["portfolio_search"])),
        "portfolio_platforms": list_value("platforms", ["Polymarket", "Kalshi"]),
        "portfolio_outcomes": list_value("outcomes", ["Yes", "No"]),
        "portfolio_rows": _bounded_int(view.get("rows", defaults["portfolio_rows"]), 150, 25, 500),
        "portfolio_min_value": int(_bounded_float(view.get("min_value", defaults["portfolio_min_value"]), 0.0, 0.0, 1_000_000_000.0)),
        "portfolio_min_pnl": int(_bounded_float(view.get("min_pnl", defaults["portfolio_min_pnl"]), -1_000_000.0, -1_000_000_000.0, 1_000_000_000.0)),
        "portfolio_sources": list_value("sources", ["Research", "Copy", "Watchlist", "History"]),
        "portfolio_copy_statuses": list_value("copy_statuses", COPY_ORDER_STATUS_FILTERS),
        "portfolio_losers_only": bool(view.get("losers_only", defaults["portfolio_losers_only"])),
    }
    for key, value in values.items():
        st.session_state[key] = value


def apply_copy_trade_filter_view_widgets(view: dict[str, Any]) -> None:
    defaults = copy_trade_filter_defaults()

    def list_value(key: str, options: list[str]) -> list[str]:
        if key not in view:
            return list(defaults[f"copy_trade_{key}"])
        return _optional_choice_list(view.get(key, []), options)

    values = {
        "copy_trade_search": str(view.get("query", defaults["copy_trade_search"])),
        "copy_trade_sides": list_value("sides", COPY_SIDE_FILTERS),
        "copy_trade_statuses": list_value("statuses", COPY_ORDER_STATUS_FILTERS),
        "copy_trade_rows": _bounded_int(view.get("rows", defaults["copy_trade_rows"]), 150, 25, 500),
        "copy_trade_min_tony_notional": int(_bounded_float(view.get("min_tony_notional", defaults["copy_trade_min_tony_notional"]), 0.0, 0.0, 1_000_000_000.0)),
        "copy_trade_min_copy_notional": int(_bounded_float(view.get("min_copy_notional", defaults["copy_trade_min_copy_notional"]), 0.0, 0.0, 1_000_000_000.0)),
        "copy_trade_min_position_value": int(_bounded_float(view.get("min_position_value", defaults["copy_trade_min_position_value"]), 0.0, 0.0, 1_000_000_000.0)),
        "copy_trade_min_pnl": int(_bounded_float(view.get("min_pnl", defaults["copy_trade_min_pnl"]), -1_000_000.0, -1_000_000_000.0, 1_000_000_000.0)),
        "copy_trade_reason_query": str(view.get("reason_query", defaults["copy_trade_reason_query"])),
        "copy_trade_latency_only": bool(view.get("latency_only", defaults["copy_trade_latency_only"])),
    }
    for key, value in values.items():
        st.session_state[key] = value


def apply_wallet_view_widgets(view: dict[str, Any]) -> None:
    wallet = str(view.get("wallet", "") or "").strip()
    entry = str(view.get("entry", wallet) or "").strip()
    if entry:
        st.session_state["wallets_wallet_input"] = entry
    if re.fullmatch(r"0x[a-fA-F0-9]{40}", wallet):
        st.session_state["wallets_inspect_wallet"] = wallet


def apply_market_filter_view_widgets(view: dict[str, Any], categories: list[str]) -> None:
    defaults = market_filter_defaults(categories)
    platform_options = ["Polymarket", "Kalshi"]
    category_options = list(categories)
    sort_options = [
        "activity_volume",
        "volume_24h",
        "volume_1h",
        "volume",
        "volume_delta_1h",
        "volume_delta_24h",
        "liquidity",
        "yes_price",
        "spread",
        "price_delta_1h",
        "price_delta_24h",
        "end_time",
        "created_at",
        "market_age_days",
    ]
    values = {
        "markets_search": str(view.get("query", defaults["markets_search"])),
        "markets_view_mode": _choice(view.get("view", defaults["markets_view_mode"]), ["Table", "Card", "Calendar"], "Table"),
        "markets_quick_filter": _choice(view.get("quick", defaults["markets_quick_filter"]), ["Trending", "Saved", "My Positions", "Ending Soon", "New"], "Trending"),
        "markets_platform_filter": _choice_list(view.get("platform_filter", defaults["markets_platform_filter"]), platform_options, defaults["markets_platform_filter"]),
        "markets_status_filter": _choice(view.get("status_filter", defaults["markets_status_filter"]), ["Active", "All", "Closed"], "Active"),
        "markets_include_categories": _choice_list(view.get("include_categories", defaults["markets_include_categories"]), category_options, []),
        "markets_exclude_categories": _choice_list(view.get("exclude_categories", defaults["markets_exclude_categories"]), category_options, defaults["markets_exclude_categories"]),
        "markets_prob_preset": _choice(view.get("prob_preset", defaults["markets_prob_preset"]), ["All", "5-95%", "20-80%", ">80%", ">95%", ">99%", "Custom"], "5-95%"),
        "markets_custom_prob": _prob_range(view.get("custom_prob", defaults["markets_custom_prob"])),
        "markets_spread_preset": _choice(view.get("spread_preset", defaults["markets_spread_preset"]), ["All", "<3c", "<7c", "<10c", "Custom"], "<7c"),
        "markets_custom_spread": _bounded_float(view.get("custom_spread", defaults["markets_custom_spread"]), 7.0, 0.0, 100.0),
        "markets_liquidity_preset": _choice(view.get("liquidity_preset", defaults["markets_liquidity_preset"]), ["All", ">$1k", ">$10k", ">$100k", "Custom"], "All"),
        "markets_custom_liquidity": int(_bounded_float(view.get("custom_liquidity", defaults["markets_custom_liquidity"]), 0.0, 0.0, 1_000_000_000.0)),
        "markets_end_preset": _choice(view.get("end_preset", defaults["markets_end_preset"]), ["All", "Open", "Past due", "<1d", "<7d", "<30d", "Custom"], "Open"),
        "markets_custom_days": _bounded_int(view.get("custom_days", defaults["markets_custom_days"]), 30, 1, 10000),
        "markets_volume_1h_preset": _choice(view.get("volume_1h_preset", defaults["markets_volume_1h_preset"]), ["All", ">$1k", ">$10k", ">$100k", "Custom"], "All"),
        "markets_custom_volume_1h": int(_bounded_float(view.get("custom_volume_1h", defaults["markets_custom_volume_1h"]), 0.0, 0.0, 1_000_000_000.0)),
        "markets_volume_preset": _choice(view.get("volume_preset", defaults["markets_volume_preset"]), ["All", ">$1k", ">$10k", ">$100k", "Custom"], "All"),
        "markets_custom_volume": int(_bounded_float(view.get("custom_volume", defaults["markets_custom_volume"]), 0.0, 0.0, 1_000_000_000.0)),
        "markets_age_preset": _choice(view.get("age_preset", defaults["markets_age_preset"]), ["All", "<1d", "<7d", "<30d", ">365d", "Custom"], "All"),
        "markets_custom_age_days": _bounded_int(view.get("custom_age_days", defaults["markets_custom_age_days"]), 30, 1, 10000),
        "markets_sort_by": _choice(view.get("sort_by", defaults["markets_sort_by"]), sort_options, "activity_volume"),
        "markets_limit_rows": _bounded_int(view.get("limit_rows", defaults["markets_limit_rows"]), 80, 10, 250),
        "markets_volume_delta_1h_preset": _choice(view.get("volume_delta_1h_preset", defaults["markets_volume_delta_1h_preset"]), ["All", ">25%", ">50%", ">75%", ">100%", "Custom"], "All"),
        "markets_custom_volume_delta_1h": _bounded_float(view.get("custom_volume_delta_1h", defaults["markets_custom_volume_delta_1h"]), 25.0, 0.0, 100000.0),
        "markets_volume_delta_24h_preset": _choice(view.get("volume_delta_24h_preset", defaults["markets_volume_delta_24h_preset"]), ["All", ">25%", ">50%", ">75%", ">100%", "Custom"], "All"),
        "markets_custom_volume_delta_24h": _bounded_float(view.get("custom_volume_delta_24h", defaults["markets_custom_volume_delta_24h"]), 25.0, 0.0, 100000.0),
        "markets_change_preset": _choice(view.get("change_preset", defaults["markets_change_preset"]), ["All", ">1c", ">3c", ">5c", ">10c", "Custom"], "All"),
        "markets_custom_change": _bounded_float(view.get("custom_change", defaults["markets_custom_change"]), 1.0, 0.0, 100.0),
        "markets_change_24h_preset": _choice(view.get("change_24h_preset", defaults["markets_change_24h_preset"]), ["All", ">1c", ">3c", ">5c", ">10c", "Custom"], "All"),
        "markets_custom_change_24h": _bounded_float(view.get("custom_change_24h", defaults["markets_custom_change_24h"]), 1.0, 0.0, 100.0),
    }
    for key, value in values.items():
        st.session_state[key] = value


def apply_trader_filter_view_widgets(view: dict[str, Any]) -> None:
    defaults = trader_filter_defaults()
    values = {
        "trader_search": str(view.get("query", defaults["trader_search"])),
        "trader_view_mode": _choice(view.get("view_mode", defaults["trader_view_mode"]), ["Table", "List", "Card"], "Table"),
        "trader_column_preset": _choice(view.get("column_preset", defaults["trader_column_preset"]), ["Parity", "Research", "Flow"], "Parity"),
        "trader_time_period": _choice(view.get("period", defaults["trader_time_period"]), ["ALL", "MONTH", "WEEK", "DAY"], "ALL"),
        "trader_order_by": _choice(view.get("rank_by", defaults["trader_order_by"]), ["PNL", "VOL"], "PNL"),
        "trader_rows": _bounded_int(view.get("rows", defaults["trader_rows"]), 100, 25, 250),
        "trader_active_only": bool(view.get("active_only", defaults["trader_active_only"])),
        "trader_bots_only": bool(view.get("bots_only", defaults["trader_bots_only"])),
        "trader_bot_score_min": _bounded_int(view.get("bot_score_min", defaults["trader_bot_score_min"]), 65, 0, 100),
        "trader_pnl_preset": _choice(view.get("pnl_preset", defaults["trader_pnl_preset"]), ["All", ">$500k", ">$1m", ">$2m", "> -$10k", "> -$100k", "> -$500k", "Custom"], "All"),
        "trader_custom_pnl": int(float(view.get("custom_pnl", defaults["trader_custom_pnl"]) or 0)),
        "trader_volume_preset": _choice(view.get("volume_preset", defaults["trader_volume_preset"]), ["All", ">$10k", ">$100k", ">$1m", "Custom"], "All"),
        "trader_custom_volume": int(float(view.get("custom_volume", defaults["trader_custom_volume"]) or 0)),
        "trader_position_preset": _choice(view.get("position_preset", defaults["trader_position_preset"]), ["All", ">$100", ">$10k", ">$100k", "Custom"], ">$100"),
        "trader_custom_position": int(float(view.get("custom_position", defaults["trader_custom_position"]) or 100)),
        "trader_active_positions_min": _bounded_int(view.get("active_positions_min", defaults["trader_active_positions_min"]), 0, 0, 100000),
        "trader_trait_filter": [item for item in list(view.get("trait_filter", defaults["trader_trait_filter"]) or []) if item in {"Whales", "Bot-like", "Verified"}],
        "trader_enrich_positions": bool(view.get("enrich_positions", defaults["trader_enrich_positions"])),
        "trader_win_rate_preset": _choice(view.get("win_rate", defaults["trader_win_rate_preset"]), ["All", ">50%", ">70%", "Custom"], "All"),
        "trader_custom_win_rate": _bounded_int(view.get("custom_win_rate", defaults["trader_custom_win_rate"]), 50, 0, 100),
        "trader_enrich_win_rates": bool(view.get("enrich_win_rates", defaults["trader_enrich_win_rates"])),
        "trader_min_closed_positions": _bounded_int(view.get("min_closed_positions", defaults["trader_min_closed_positions"]), 5, 0, 500),
        "trader_assets_preset": _choice(view.get("assets_preset", defaults["trader_assets_preset"]), ["All", ">$100k", ">$1m", ">$2m", "Custom"], "All"),
        "trader_custom_assets": int(float(view.get("custom_assets", defaults["trader_custom_assets"]) or 0)),
        "trader_balance_preset": _choice(view.get("balance_preset", defaults["trader_balance_preset"]), ["All", ">$1k", ">$10k", ">$100k", "Custom"], "All"),
        "trader_custom_balance": int(float(view.get("custom_balance", defaults["trader_custom_balance"]) or 0)),
        "trader_account_age_preset": _choice(view.get("account_age_preset", defaults["trader_account_age_preset"]), ["All", "<14d", ">365d", "Custom"], "All"),
        "trader_custom_account_age": _bounded_int(view.get("custom_account_age", defaults["trader_custom_account_age"]), 365, 1, 10000),
        "trader_enrich_accounts": bool(view.get("enrich_accounts", defaults["trader_enrich_accounts"])),
        "trader_account_enrich_rows": _bounded_int(view.get("account_enrich_rows", defaults["trader_account_enrich_rows"]), 15, 5, 30),
    }
    for key, value in values.items():
        st.session_state[key] = value


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


def section_header(title: str, subtitle: str = "") -> None:
    st.markdown(f"<div class='terminal-kicker'>Live public market data</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='terminal-title'>{title}</div>", unsafe_allow_html=True)
    if subtitle:
        st.markdown(f"<div class='terminal-subtitle'>{subtitle}</div>", unsafe_allow_html=True)


def draw_empty(message: str) -> None:
    with st.container(border=True):
        st.markdown(f"<div class='small-note'>{message}</div>", unsafe_allow_html=True)


def plot_config() -> dict[str, Any]:
    return {"displayModeBar": False, "responsive": True}


def default_research_portfolio() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "platform": "Polymarket",
                "market": "",
                "market_key": "",
                "url": "",
                "outcome": "Yes",
                "shares": 0.0,
                "avg_price": 0.50,
                "current_price": 0.50,
            }
        ]
    )


def query_page_value() -> str:
    try:
        value = st.query_params.get("page", "")
    except Exception:
        return ""
    if isinstance(value, list):
        value = value[0] if value else ""
    return str(value or "").strip().lower()


def query_param_snapshot(names: list[str]) -> dict[str, str]:
    values: dict[str, str] = {}
    for name in names:
        try:
            value = st.query_params.get(name, "")
        except Exception:
            value = ""
        if isinstance(value, list):
            value = value[0] if value else ""
        values[name] = str(value or "").strip()
    return values


def path_page_value() -> str:
    try:
        current_url = str(st.context.url or "")
    except Exception:
        return ""
    return md.local_route_target(current_url).get("page_slug", "")


def path_profile_value() -> str:
    try:
        current_url = str(st.context.url or "")
    except Exception:
        return ""
    return md.local_route_target(current_url).get("profile", "")


def path_market_value() -> str:
    try:
        current_url = str(st.context.url or "")
    except Exception:
        return ""
    return md.local_route_target(current_url).get("market", "")


def path_auth_mode() -> str:
    try:
        current_url = str(st.context.url or "")
    except Exception:
        return ""
    return md.local_auth_route_mode(current_url)


def routed_page_value() -> str:
    query_slug = query_page_value()
    if query_slug:
        return query_slug
    return path_page_value()


def set_query_page(page: str) -> None:
    slug = PAGE_QUERY_SLUGS.get(page, "")
    if not slug:
        return
    try:
        if query_page_value() != slug:
            st.query_params["page"] = slug
    except Exception:
        return


def init_state() -> None:
    if "selected_page" not in st.session_state:
        st.session_state.selected_page = PAGE_BY_QUERY_SLUG.get(routed_page_value(), "Overview")
    if "global_search_query" not in st.session_state:
        st.session_state.global_search_query = ""
    if "command_palette_open" not in st.session_state:
        st.session_state.command_palette_open = False
    if "command_palette_query" not in st.session_state:
        st.session_state.command_palette_query = ""
    if "auth_dialog_mode" not in st.session_state:
        st.session_state.auth_dialog_mode = ""
    if "followed_wallets" not in st.session_state:
        st.session_state.followed_wallets = load_local_list("followed_wallets.json")
    if "watchlist" not in st.session_state:
        st.session_state.watchlist = load_local_list("watchlist.json")
    if "saved_overview_filters" not in st.session_state:
        st.session_state.saved_overview_filters = load_local_list("saved_overview_filters.json")
    if "saved_market_filters" not in st.session_state:
        st.session_state.saved_market_filters = load_local_list("saved_market_filters.json")
    if "saved_trader_filters" not in st.session_state:
        st.session_state.saved_trader_filters = load_local_list("saved_trader_filters.json")
    if "saved_search_filters" not in st.session_state:
        st.session_state.saved_search_filters = load_local_list("saved_search_filters.json")
    if "saved_wallet_filters" not in st.session_state:
        st.session_state.saved_wallet_filters = load_local_list("saved_wallet_filters.json")
    if "saved_copy_trade_filters" not in st.session_state:
        st.session_state.saved_copy_trade_filters = load_local_list("saved_copy_trade_filters.json")
    if "saved_live_filters" not in st.session_state:
        st.session_state.saved_live_filters = load_local_list("saved_live_filters.json")
    if "saved_track_filters" not in st.session_state:
        st.session_state.saved_track_filters = load_local_list("saved_track_filters.json")
    if "saved_whale_filters" not in st.session_state:
        st.session_state.saved_whale_filters = load_local_list("saved_whale_filters.json")
    if "saved_cross_filters" not in st.session_state:
        st.session_state.saved_cross_filters = load_local_list("saved_cross_filters.json")
    if "saved_monitor_filters" not in st.session_state:
        st.session_state.saved_monitor_filters = load_local_list("saved_monitor_filters.json")
    if "saved_alert_filters" not in st.session_state:
        st.session_state.saved_alert_filters = load_local_list("saved_alert_filters.json")
    if "saved_resolved_filters" not in st.session_state:
        st.session_state.saved_resolved_filters = load_local_list("saved_resolved_filters.json")
    if "saved_portfolio_filters" not in st.session_state:
        st.session_state.saved_portfolio_filters = load_local_list("saved_portfolio_filters.json")
    if "recent_searches" not in st.session_state:
        st.session_state.recent_searches = load_local_list("recent_searches.json")
    if "market_comments" not in st.session_state:
        st.session_state.market_comments = load_local_market_comments()
    if "monitor_rules" not in st.session_state:
        st.session_state.monitor_rules = load_local_monitor_rules()
    if "paper_trade_history" not in st.session_state:
        st.session_state.paper_trade_history = load_local_list("paper_trade_history.json")
    if "portfolio" not in st.session_state:
        st.session_state.portfolio = load_local_portfolio()
    if "research_cash" not in st.session_state:
        st.session_state.research_cash = load_local_research_cash()
    if "markets_show_more_categories" not in st.session_state:
        st.session_state.markets_show_more_categories = False


def _data_path(filename: str) -> Path:
    return Path("data") / filename


def load_local_list(filename: str) -> list[Any]:
    path = _data_path(filename)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def save_local_list(filename: str, items: list[Any]) -> None:
    path = _data_path(filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(items, indent=2, sort_keys=True, default=str), encoding="utf-8")


def load_local_research_cash() -> float:
    path = _data_path("research_cash.json")
    if not path.exists():
        return RESEARCH_START_CASH
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return max(float(data.get("cash", RESEARCH_START_CASH) or 0.0), 0.0)
        return max(float(data or 0.0), 0.0)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return RESEARCH_START_CASH


def save_local_research_cash(cash: float) -> None:
    path = _data_path("research_cash.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"cash": max(float(cash or 0.0), 0.0)}, indent=2, sort_keys=True), encoding="utf-8")


def load_local_portfolio() -> pd.DataFrame:
    rows = load_local_list("research_portfolio.json")
    if not rows:
        return default_research_portfolio()
    frame = pd.DataFrame([row for row in rows if isinstance(row, dict)])
    return frame if not frame.empty else default_research_portfolio()


def save_local_portfolio(portfolio: pd.DataFrame) -> None:
    frame = portfolio.copy() if isinstance(portfolio, pd.DataFrame) else default_research_portfolio()
    save_local_list("research_portfolio.json", frame.to_dict(orient="records"))


def merge_research_portfolio(existing: pd.DataFrame, imported: pd.DataFrame) -> pd.DataFrame:
    if imported.empty:
        return existing.copy() if isinstance(existing, pd.DataFrame) else default_research_portfolio()
    base = existing.copy() if isinstance(existing, pd.DataFrame) and not existing.empty else pd.DataFrame()
    for col in ["platform", "market", "market_key", "url", "outcome", "shares", "avg_price", "current_price"]:
        if col not in base:
            base[col] = "" if col in {"platform", "market", "market_key", "url", "outcome"} else 0.0
    imported = imported.copy()
    base["_merge_key"] = (
        base["platform"].astype(str).str.lower()
        + "|"
        + base["market_key"].astype(str).str.lower()
        + "|"
        + base["market"].astype(str).str.lower()
        + "|"
        + base["outcome"].astype(str).str.lower()
    )
    imported["_merge_key"] = (
        imported["platform"].astype(str).str.lower()
        + "|"
        + imported["market_key"].astype(str).str.lower()
        + "|"
        + imported["market"].astype(str).str.lower()
        + "|"
        + imported["outcome"].astype(str).str.lower()
    )
    base = base[~base["_merge_key"].isin(set(imported["_merge_key"]))]
    merged = pd.concat([base.drop(columns=["_merge_key"], errors="ignore"), imported.drop(columns=["_merge_key"], errors="ignore")], ignore_index=True, sort=False)
    return merged[merged["shares"].fillna(0).astype(float) > 1e-9].reset_index(drop=True)


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


def load_local_market_comments() -> dict[str, list[dict[str, str]]]:
    path = Path("data/market_comments.json")
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_local_market_comments(comments: dict[str, list[dict[str, str]]]) -> None:
    path = Path("data/market_comments.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(comments, indent=2, sort_keys=True), encoding="utf-8")


def load_local_monitor_rules() -> list[dict[str, Any]]:
    path = Path("data/monitor_rules.json")
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def save_local_monitor_rules(rules: list[dict[str, Any]]) -> None:
    path = Path("data/monitor_rules.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rules, indent=2, sort_keys=True, default=str), encoding="utf-8")


init_state()


@st.cache_data(ttl=60, show_spinner=False)
def load_polymarket_markets(limit: int) -> pd.DataFrame:
    return md.get_polymarket_markets(limit=limit)


@st.cache_data(ttl=180, show_spinner=False)
def load_polymarket_event_markets(event_url_or_slug: str) -> pd.DataFrame:
    return md.get_polymarket_event_markets(event_url_or_slug)


@st.cache_data(ttl=60, show_spinner=False)
def load_kalshi_markets(limit: int) -> pd.DataFrame:
    return md.get_kalshi_markets(limit=limit)


@st.cache_data(ttl=45, show_spinner=False)
def load_polymarket_trades(limit: int, min_cash: float, user: str | None = None, market: str | None = None) -> pd.DataFrame:
    return md.get_polymarket_trades(limit=limit, min_cash=min_cash, user=user, market=market)


@st.cache_data(ttl=45, show_spinner=False)
def load_kalshi_trades(limit: int, ticker: str | None = None) -> pd.DataFrame:
    return md.get_kalshi_trades(limit=limit, ticker=ticker)


@st.cache_data(ttl=300, show_spinner=False)
def load_leaderboard(limit: int, time_period: str, order_by: str) -> pd.DataFrame:
    if str(time_period or "").upper() == "ALL":
        try:
            parity = md.get_predictparity_traders(
                limit=limit,
                sort_by="volume" if str(order_by or "").upper() == "VOL" else "pnl",
                min_active_positions=0.0,
            )
            if not parity.empty:
                return parity
        except Exception:
            pass
    return md.get_polymarket_leaderboard(limit=limit, time_period=time_period, order_by=order_by)


@st.cache_data(ttl=120, show_spinner=False)
def load_wallet_bundle(wallet: str, limit: int) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    open_positions = md.get_polymarket_positions(wallet, limit=limit)
    closed_positions = md.get_polymarket_closed_positions(wallet, limit=limit)
    trades = md.get_polymarket_trades(limit=min(limit, 500), user=wallet)
    activity = md.get_polymarket_activity(wallet, limit=limit)
    return open_positions, closed_positions, trades, activity


@st.cache_data(ttl=180, show_spinner=False)
def load_price_history(token_id: str, days: int, interval: str = "1d") -> pd.DataFrame:
    return md.get_polymarket_price_history(token_id, days=days, interval=interval)


@st.cache_data(ttl=180, show_spinner=False)
def load_kalshi_candles(ticker: str, days: int, period_interval: int) -> pd.DataFrame:
    return md.get_kalshi_candlesticks(ticker=ticker, days=days, period_interval=period_interval)


@st.cache_data(ttl=45, show_spinner=False)
def load_polymarket_book(token_id: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    return md.get_polymarket_orderbook(token_id)


@st.cache_data(ttl=45, show_spinner=False)
def load_kalshi_book(ticker: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    return md.get_kalshi_orderbook(ticker)


@st.cache_data(ttl=180, show_spinner=False)
def load_holders(market_key: str) -> pd.DataFrame:
    return md.get_polymarket_holders(market_key, limit=80)


@st.cache_data(ttl=180, show_spinner=False)
def load_market_positions(market_key: str, status: str, sort_by: str, limit: int = 100) -> pd.DataFrame:
    return md.get_polymarket_market_positions(market_key, status=status, sort_by=sort_by, limit=limit)


@st.cache_data(ttl=300, show_spinner=False)
def load_market_news(query: str, limit: int = 20) -> pd.DataFrame:
    return md.get_market_news(query, limit=limit)


@st.cache_data(ttl=300, show_spinner=False)
def load_wallet_position_values(wallets: tuple[str, ...], limit: int = 120) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for wallet in wallets:
        positions = md.get_polymarket_positions(wallet, limit=limit)
        rows.append(
            {
                "wallet": wallet,
                "positions_value": float(positions["value"].sum()) if not positions.empty and "value" in positions else 0.0,
                "open_positions": int(len(positions)),
                "open_markets": int(positions["market_key"].astype(str).nunique()) if not positions.empty and "market_key" in positions else 0,
            }
        )
    return pd.DataFrame(rows)


@st.cache_data(ttl=900, show_spinner=False)
def load_wallet_account_stats(wallets: tuple[str, ...], activity_pages: int = 3, include_balance: bool = True) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    now = pd.Timestamp.now(tz="UTC")
    for wallet in wallets:
        activity_frames: list[pd.DataFrame] = []
        for page in range(max(1, int(activity_pages))):
            try:
                activity = md.get_polymarket_activity(wallet, limit=500, offset=page * 500)
            except Exception:
                break
            if activity.empty:
                break
            activity_frames.append(activity)
            if len(activity) < 500:
                break
        activity = pd.concat(activity_frames, ignore_index=True) if activity_frames else pd.DataFrame()
        times = pd.to_datetime(activity.get("time", pd.Series(dtype="datetime64[ns, UTC]")), utc=True, errors="coerce").dropna()
        oldest = times.min() if not times.empty else pd.NaT
        account_age_days = float((now - oldest).total_seconds() / 86_400) if pd.notna(oldest) else None
        try:
            balance = ct.fetch_polygon_usdc_balance(wallet) if include_balance else 0.0
        except Exception:
            balance = 0.0
        rows.append(
            {
                "wallet": wallet,
                "cash_balance": float(balance),
                "oldest_activity_time": oldest,
                "account_age_days": account_age_days,
                "activity_observations": int(len(activity)),
            }
        )
    return pd.DataFrame(rows)


@st.cache_data(ttl=600, show_spinner=False)
def load_predictparity_trader_profile(identifier: str) -> dict[str, Any]:
    return md.get_predictparity_trader_profile(identifier)


@st.cache_data(ttl=600, show_spinner=False)
def load_predictparity_pnl_chart(trader_id: str, window: str) -> pd.DataFrame:
    return md.get_predictparity_trader_pnl_chart(trader_id, window)


@st.cache_data(ttl=600, show_spinner=False)
def load_wallet_win_rates(wallets: tuple[str, ...], limit: int = 120) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for wallet in wallets:
        closed = md.get_polymarket_closed_positions(wallet, limit=limit)
        wins = int((closed["realized_pnl"] > 0).sum()) if not closed.empty and "realized_pnl" in closed else 0
        closed_count = int(len(closed))
        rows.append(
            {
                "wallet": wallet,
                "win_rate": wins / closed_count if closed_count else None,
                "closed_positions": closed_count,
                "winning_positions": wins,
                "closed_realized_pnl": float(closed["realized_pnl"].sum()) if not closed.empty and "realized_pnl" in closed else 0.0,
            }
        )
    return pd.DataFrame(rows)


@st.cache_data(ttl=600, show_spinner=False)
def load_closed_markets(limit: int) -> pd.DataFrame:
    return md.get_polymarket_closed_markets(limit=limit)


def safe_load(label: str, fn: Any, *args: Any, default: Any = None, **kwargs: Any) -> Any:
    try:
        return fn(*args, **kwargs)
    except Exception as exc:
        st.warning(f"{label} unavailable: {exc}")
        return pd.DataFrame() if default is None else default


def open_command_palette() -> None:
    st.session_state.command_palette_open = True
    if st.session_state.global_search_query and not st.session_state.command_palette_query:
        st.session_state.command_palette_query = st.session_state.global_search_query


def close_command_palette() -> None:
    st.session_state.command_palette_open = False


def queue_navigation(page: str, query: str | None = None) -> None:
    st.session_state.pending_selected_page = page
    if query is not None:
        st.session_state.pending_global_search_query = query.strip()


def apply_pending_navigation() -> None:
    target_page = st.session_state.pop("pending_selected_page", None)
    if target_page in WORKSPACES:
        st.session_state.selected_page = target_page
        set_query_page(target_page)
    if "pending_global_search_query" in st.session_state:
        st.session_state.global_search_query = st.session_state.pop("pending_global_search_query")


def apply_query_navigation() -> None:
    route_page = PAGE_BY_QUERY_SLUG.get(routed_page_value())
    if route_page in WORKSPACES and route_page != st.session_state.get("selected_page"):
        st.session_state.selected_page = route_page


def apply_auth_route() -> None:
    mode = path_auth_mode()
    if not mode:
        return
    signature = f"{mode}:{path_page_value()}"
    if st.session_state.get("auth_route_signature") == signature:
        return
    st.session_state["auth_route_signature"] = signature
    st.session_state.auth_dialog_mode = mode


def apply_profile_route() -> None:
    if query_page_value():
        return
    profile = path_profile_value()
    if not profile or st.session_state.get("wallets_route_profile_value") == profile:
        return
    st.session_state["wallets_route_profile_value"] = profile
    st.session_state["wallets_wallet_input"] = profile
    if re.fullmatch(r"0x[a-fA-F0-9]{40}", profile):
        st.session_state["wallets_inspect_wallet"] = profile
    else:
        st.session_state["wallets_route_pending_resolve"] = profile


def apply_market_route(combined: pd.DataFrame) -> None:
    if query_page_value():
        return
    market_value = path_market_value()
    if not market_value or st.session_state.get("markets_route_market_value") == market_value:
        return
    st.session_state["markets_route_market_value"] = market_value
    search_value = re.sub(r"[-_]+", " ", market_value).strip()
    if search_value:
        st.session_state["markets_search"] = search_value
    if not combined.empty:
        for column in ["market_key", "ticker", "slug"]:
            if column in combined:
                matches = combined[combined[column].astype(str).str.lower().eq(market_value.lower())]
                if not matches.empty:
                    st.session_state["markets_inspect_market_key"] = str(matches.iloc[0].get("market_key", "") or "")
                    break
    st.session_state["markets_route_message"] = "Loaded market filters from URL."


def open_palette_search(query: str) -> None:
    clean_query = query.strip()
    queue_navigation("Search", clean_query)
    st.session_state.command_palette_open = False
    if clean_query:
        st.session_state.recent_searches = [clean_query] + [
            item for item in st.session_state.recent_searches if str(item).lower() != clean_query.lower()
        ]
        st.session_state.recent_searches = st.session_state.recent_searches[:12]
        save_local_list("recent_searches.json", st.session_state.recent_searches)


def open_palette_market(market_key: str, query: str = "") -> None:
    queue_navigation("Markets", query)
    st.session_state.markets_inspect_market_key = str(market_key)
    st.session_state.command_palette_open = False


def open_palette_wallet(wallet: str, query: str = "") -> None:
    queue_navigation("Wallets", query)
    st.session_state.wallets_inspect_wallet = str(wallet)
    st.session_state.command_palette_open = False


def track_palette_wallet(wallet: str) -> None:
    st.session_state.followed_wallets, changed = md.upsert_followed_wallet(st.session_state.followed_wallets, wallet)
    if changed:
        save_local_list("followed_wallets.json", st.session_state.followed_wallets)


def market_status_masks(markets: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    if markets.empty:
        empty = pd.Series(dtype=bool)
        return empty, empty
    closed = (
        markets["closed"].astype("boolean").fillna(False).astype(bool)
        if "closed" in markets
        else pd.Series(False, index=markets.index, dtype=bool)
    )
    active = (
        markets["active"].astype("boolean").fillna(True).astype(bool)
        if "active" in markets
        else pd.Series(True, index=markets.index, dtype=bool)
    )
    end_source = markets["end_time"] if "end_time" in markets else pd.Series(pd.NaT, index=markets.index)
    end_time = pd.to_datetime(end_source, utc=True, errors="coerce")
    past_end = end_time.notna() & (end_time < pd.Timestamp.now(tz="UTC"))
    active_mask = active & ~closed & ~past_end
    ended_mask = closed | ~active | past_end
    return active_mask, ended_mask


def command_end_label(row: pd.Series) -> str:
    end = pd.to_datetime(row.get("end_time"), utc=True, errors="coerce")
    if pd.isna(end):
        return "Open"
    delta_days = (end - pd.Timestamp.now(tz="UTC")).total_seconds() / 86_400
    if delta_days < 0:
        return "Ended"
    if delta_days < 1:
        return "Ends <1d"
    return f"Ends in {int(delta_days) + 1}d"


def render_command_bar() -> None:
    st.markdown("<div class='parity-nav-caption'>PredictParity navigation</div>", unsafe_allow_html=True)
    nav_cols = st.columns(len(PREDICTPARITY_NAV))
    for idx, nav_page in enumerate(PREDICTPARITY_NAV):
        is_current = st.session_state.get("selected_page") == nav_page
        label = nav_page.upper()
        nav_cols[idx].link_button(
            label,
            f"/{PAGE_QUERY_SLUGS[nav_page]}",
            width="stretch",
            type="primary" if is_current else "secondary",
        )
    left, middle, right = st.columns([1.2, 4.6, 1.8])
    with middle:
        if st.button("Search Parity...                                      /", key="open_command_palette_main", width="stretch"):
            open_command_palette()
    with right:
        auth_cols = st.columns(2)
        if auth_cols[0].button("Sign In", key="open_sign_in_main", width="stretch"):
            st.session_state.auth_dialog_mode = "Sign In"
        if auth_cols[1].button("Sign Up", key="open_sign_up_main", width="stretch"):
            st.session_state.auth_dialog_mode = "Sign Up"


@st.dialog("Account access", width="small")
def render_auth_dialog() -> None:
    mode = st.session_state.get("auth_dialog_mode", "Sign In")
    st.markdown(f"### {mode}")
    st.markdown(
        "<div class='auth-note'>Local research mode: account providers are shown to mirror PredictParity's public app shell. "
        "This terminal does not send credentials or place live orders.</div>",
        unsafe_allow_html=True,
    )
    st.text_input("Email", placeholder="you@example.com", key="auth_email")
    primary = "Continue with email" if mode == "Sign In" else "Create research account"
    if st.button(primary, type="primary", width="stretch", key="auth_email_continue"):
        st.session_state.auth_dialog_mode = ""
        st.toast("Local research session only. Live account login is not connected.")
        st.rerun()
    provider_cols = st.columns(2)
    provider_cols[0].button("Google", width="stretch", key="auth_google", disabled=True)
    provider_cols[1].button("X / Twitter", width="stretch", key="auth_x", disabled=True)
    if st.button("Connect wallet", width="stretch", key="auth_wallet", disabled=True):
        pass
    if st.button("Close", width="stretch", key="auth_close"):
        st.session_state.auth_dialog_mode = ""
        st.rerun()


def render_global_hotkeys() -> None:
    components.html(
        """
        <script>
        (() => {
          if (window.parent.__marketIntelHotkeysInstalled) return;
          window.parent.__marketIntelHotkeysInstalled = true;
          const isTypingTarget = (node) => {
            if (!node) return false;
            const tag = (node.tagName || "").toLowerCase();
            return tag === "input" || tag === "textarea" || tag === "select" || node.isContentEditable;
          };
          window.parent.document.addEventListener("keydown", (event) => {
            if (event.key !== "/" || event.metaKey || event.ctrlKey || event.altKey || event.shiftKey) return;
            if (isTypingTarget(event.target)) return;
            const buttons = Array.from(window.parent.document.querySelectorAll("button"));
            const target = buttons.find((button) => (button.innerText || "").includes("Search Parity") && (button.innerText || "").includes("/"));
            if (!target) return;
            event.preventDefault();
            target.click();
          }, true);
        })();
        </script>
        """,
        height=0,
        width=0,
    )


@st.dialog("Search Parity", width="large")
def render_command_palette_dialog() -> None:
    query = st.text_input("Search markets, traders, trades, alerts, or news", key="command_palette_query", placeholder="market, topic, wallet, trader")

    pm, ks, combined = load_market_universe()
    markets = add_market_filter_metrics(combined) if not combined.empty else pd.DataFrame()
    markets = filter_text(markets, query)
    active_mask, ended_mask = market_status_masks(markets)

    palette_poly_trades = safe_load("Command palette Polymarket trades", load_polymarket_trades, 180, 0.0, None, None, default=pd.DataFrame())
    palette_kalshi_trades = safe_load("Command palette Kalshi trades", load_kalshi_trades, 120, None, default=pd.DataFrame())
    trades = combined_trade_table(palette_poly_trades, palette_kalshi_trades)
    trades = filter_text(trades, query).head(10).reset_index(drop=True) if not trades.empty else pd.DataFrame()
    tracked_keys = {str(item.get("market_key")) for item in st.session_state.watchlist if item.get("market_key")}
    alert_signals = build_monitor_signals(
        markets.copy(),
        trades.copy(),
        min_volume=0.0,
        min_liquidity=0.0,
        min_move=0.03,
        max_spread=0.07,
        min_whale_notional=float(min_whale),
        ending_days=7,
        holder_threshold=0.25,
        holder_checks=0,
        tracked_keys=tracked_keys,
    )
    alert_hits = build_monitor_alert_hits(alert_signals, st.session_state.monitor_rules)
    alerts = alert_hits if not alert_hits.empty else alert_signals
    alerts = alerts.head(8).reset_index(drop=True) if not alerts.empty else pd.DataFrame()
    news = safe_load("Command palette news", load_market_news, query, 8, default=pd.DataFrame()) if query.strip() else pd.DataFrame()

    leaderboard = safe_load("Command palette profiles", load_leaderboard, 50, "ALL", "VOL", default=pd.DataFrame())
    profiles = filter_text(leaderboard, query) if not leaderboard.empty else pd.DataFrame()
    if not profiles.empty:
        sort_profile = "volume" if "volume" in profiles else "pnl"
        profiles = profiles.sort_values(sort_profile, ascending=False, na_position="last")
        profile_wallets = tuple(profiles["wallet"].astype(str).head(12).tolist()) if "wallet" in profiles else ()
        if profile_wallets:
            profile_positions = safe_load("Command palette profile positions", load_wallet_position_values, profile_wallets, 80, default=pd.DataFrame())
            profiles = md.merge_profile_position_values(profiles, profile_positions)

    status_options = [
        f"All ({len(markets) + len(profiles) + len(trades) + len(alerts) + len(news)})",
        f"Active ({int(active_mask.sum()) if len(active_mask) else 0})",
        f"Ended ({int(ended_mask.sum()) if len(ended_mask) else 0})",
        f"Profiles ({len(profiles)})",
        f"Trades ({len(trades)})",
        f"Alerts ({len(alerts)})",
        f"News ({len(news)})",
    ]
    sort_label = st.radio("Sort", ["Sort by 24h volume", "Sort by end date"], horizontal=True, label_visibility="collapsed")
    status_label = st.radio("Result filter", status_options, horizontal=True, label_visibility="collapsed")
    status = status_label.split(" ", 1)[0]

    market_results = markets.copy()
    if status == "Active" and len(active_mask):
        market_results = market_results[active_mask]
    elif status == "Ended" and len(ended_mask):
        market_results = market_results[ended_mask]
    elif status == "Profiles":
        market_results = market_results.iloc[0:0]

    if not market_results.empty:
        if sort_label == "Sort by end date" and "end_time" in market_results:
            market_results = market_results.assign(_end_sort=pd.to_datetime(market_results["end_time"], utc=True, errors="coerce"))
            market_results = market_results.sort_values("_end_sort", ascending=True, na_position="last").drop(columns=["_end_sort"], errors="ignore")
        else:
            volume_col = "activity_volume" if "activity_volume" in market_results else "volume_24h"
            market_results = market_results.sort_values(volume_col, ascending=False, na_position="last")
        market_results = market_results.head(8).reset_index(drop=True)

    if status in {"Active", "Ended"}:
        profiles = profiles.iloc[0:0]
        trades = trades.iloc[0:0]
        alerts = alerts.iloc[0:0]
        news = news.iloc[0:0]
    elif status == "Profiles":
        trades = trades.iloc[0:0]
        alerts = alerts.iloc[0:0]
        news = news.iloc[0:0]
    elif status == "Trades":
        market_results = market_results.iloc[0:0]
        profiles = profiles.iloc[0:0]
        alerts = alerts.iloc[0:0]
        news = news.iloc[0:0]
    elif status == "Alerts":
        market_results = market_results.iloc[0:0]
        profiles = profiles.iloc[0:0]
        trades = trades.iloc[0:0]
        news = news.iloc[0:0]
    elif status == "News":
        market_results = market_results.iloc[0:0]
        profiles = profiles.iloc[0:0]
        trades = trades.iloc[0:0]
        alerts = alerts.iloc[0:0]
    else:
        profiles = profiles.head(6).reset_index(drop=True)
        trades = trades.head(6).reset_index(drop=True)
        alerts = alerts.head(6).reset_index(drop=True)
        news = news.head(6).reset_index(drop=True)

    action_cols = st.columns([1, 1, 4])
    if action_cols[0].button("Open full Search", key="palette_open_full_search", width="stretch"):
        open_palette_search(query)
        st.rerun()
    if action_cols[1].button("Close", key="palette_close", width="stretch"):
        close_command_palette()
        st.rerun()

    if market_results.empty and profiles.empty and trades.empty and alerts.empty and news.empty:
        draw_empty("No command-palette results for the current query and filter.")
        return

    if not market_results.empty:
        st.markdown(f"#### Markets ({len(market_results)})")
        for idx, row in market_results.iterrows():
            key = str(row.get("market_key", "") or row.get("ticker", "") or idx)
            safe_key = re.sub(r"[^a-zA-Z0-9_]", "_", key)[:60]
            title = str(row.get("title", "-"))
            platform = str(row.get("platform", "-"))
            price = cents(row.get("yes_price"))
            volume_col = "activity_volume" if "activity_volume" in row.index else "volume_24h"
            volume = markdown_money(row.get(volume_col, 0.0))
            with st.container(border=True):
                text_col, open_col, save_col = st.columns([3.4, 1, 1])
                text_col.markdown(f"**{platform}**  \n{title}")
                text_col.caption(f"{price} Yes | {command_end_label(row)} | Vol {volume}")
                if open_col.button(
                    "Open market",
                    key=f"palette_market_{idx}_{safe_key}",
                    width="stretch",
                ):
                    open_palette_market(key, query)
                    st.rerun()
                saved_keys = {str(item.get("market_key", "")).strip() for item in st.session_state.watchlist}
                if key in saved_keys:
                    if save_col.button("Unsave", key=f"palette_market_unsave_{idx}_{safe_key}", width="stretch"):
                        st.session_state.watchlist, changed = md.remove_watchlist_market(st.session_state.watchlist, key)
                        if changed:
                            save_local_list("watchlist.json", st.session_state.watchlist)
                        st.rerun()
                elif save_col.button("Save", key=f"palette_market_save_{idx}_{safe_key}", width="stretch"):
                    st.session_state.watchlist, changed = md.upsert_watchlist_market(st.session_state.watchlist, row.to_dict())
                    if changed:
                        save_local_list("watchlist.json", st.session_state.watchlist)
                    st.rerun()

    if not trades.empty:
        st.markdown(f"#### Trades ({len(trades)})")
        tracked_wallets = {str(item).lower() for item in st.session_state.followed_wallets}
        for idx, row in trades.iterrows():
            market_key = str(row.get("market_key", "") or row.get("ticker", "") or row.get("title", ""))
            wallet = str(row.get("wallet", ""))
            safe_key = re.sub(r"[^a-zA-Z0-9_]", "_", f"{market_key}_{wallet}_{idx}")[:70]
            with st.container(border=True):
                text_col, market_col, wallet_col = st.columns([3.3, 1, 1])
                text_col.markdown(f"**{row.get('platform', '-')} trade**  \n{str(row.get('title', '-'))[:120]}")
                text_col.caption(
                    f"{row.get('side', '-')} {row.get('outcome', '-')} | "
                    f"{markdown_money(row.get('notional', 0.0))} | "
                    f"{short_addr(wallet)} | {row.get('time', '-')}"
                )
                if market_col.button("Open market", key=f"palette_trade_market_{idx}_{safe_key}", width="stretch"):
                    open_palette_market(market_key, query)
                    st.rerun()
                if wallet.lower() in tracked_wallets:
                    wallet_col.button("Tracked", key=f"palette_trade_wallet_tracked_{idx}_{safe_key}", width="stretch", disabled=True)
                elif wallet_col.button("Track wallet", key=f"palette_trade_wallet_{idx}_{safe_key}", width="stretch"):
                    track_palette_wallet(wallet)
                    st.rerun()

    if not alerts.empty:
        st.markdown(f"#### Alerts ({len(alerts)})")
        for idx, row in alerts.iterrows():
            market_key = str(row.get("market_key", "") or row.get("title", ""))
            wallet = str(row.get("wallet", ""))
            safe_key = re.sub(r"[^a-zA-Z0-9_]", "_", f"{market_key}_{idx}")[:70]
            with st.container(border=True):
                text_col, market_col, alerts_col = st.columns([3.3, 1, 1])
                rule = str(row.get("rule_name", "") or row.get("signal_type", "Signal"))
                text_col.markdown(f"**{rule}**  \n{str(row.get('title', '-'))[:120]}")
                text_col.caption(f"{row.get('signal_type', '-')} | {row.get('reason', '-')} | {row.get('platform', '-')}")
                if market_col.button("Open market", key=f"palette_alert_market_{idx}_{safe_key}", width="stretch"):
                    open_palette_market(market_key, query)
                    st.rerun()
                if wallet and re.fullmatch(r"0x[a-fA-F0-9]{40}", wallet):
                    if alerts_col.button("Track wallet", key=f"palette_alert_wallet_{idx}_{safe_key}", width="stretch"):
                        track_palette_wallet(wallet)
                        st.rerun()
                elif alerts_col.button("Open Alerts", key=f"palette_alert_page_{idx}_{safe_key}", width="stretch"):
                    queue_navigation("Alerts", query)
                    st.session_state.command_palette_open = False
                    st.rerun()

    if not news.empty:
        st.markdown(f"#### News ({len(news)})")
        for idx, row in news.iterrows():
            safe_key = re.sub(r"[^a-zA-Z0-9_]", "_", f"{row.get('source', '')}_{idx}")[:70]
            with st.container(border=True):
                text_col, search_col, link_col = st.columns([3.4, 1, 1])
                text_col.markdown(f"**{row.get('source', 'News')}**  \n{str(row.get('title', '-'))[:150]}")
                text_col.caption(str(row.get("time", "-")))
                if search_col.button("Open Search", key=f"palette_news_search_{idx}_{safe_key}", width="stretch"):
                    open_palette_search(str(row.get("title", query)))
                    st.rerun()
                if str(row.get("url", "")):
                    link_col.link_button("Open", str(row.get("url", "")), width="stretch")

    if not profiles.empty:
        st.markdown(f"#### Profiles ({len(profiles)})")
        tracked_wallets = {str(item).lower() for item in st.session_state.followed_wallets}
        for idx, row in profiles.iterrows():
            wallet = str(row.get("wallet", ""))
            trader = str(row.get("trader", short_addr(wallet)) or short_addr(wallet))
            with st.container(border=True):
                text_col, open_col, track_col = st.columns([3.3, 1, 1])
                text_col.markdown(f"**{trader}**  \nPolymarket | {short_addr(wallet)}")
                text_col.caption(
                    f"PnL {markdown_money(row.get('pnl', 0.0))} | "
                    f"Pos {markdown_money(row.get('positions_value', 0.0))} | "
                    f"Vol {markdown_money(row.get('volume', 0.0))}"
                )
                if open_col.button(
                    "Open profile",
                    key=f"palette_profile_open_{idx}_{short_addr(wallet, 4)}",
                    width="stretch",
                ):
                    open_palette_wallet(wallet, query)
                    st.rerun()
                if wallet.lower() in tracked_wallets:
                    track_col.button("Tracked", key=f"palette_profile_tracked_{idx}_{short_addr(wallet, 4)}", width="stretch", disabled=True)
                elif track_col.button(
                    "Track",
                    key=f"palette_profile_track_{idx}_{short_addr(wallet, 4)}",
                    width="stretch",
                ):
                    before = len(st.session_state.followed_wallets)
                    track_palette_wallet(wallet)
                    if len(st.session_state.followed_wallets) > before:
                        st.toast("Wallet added to tracked wallets.")
                    st.rerun()


apply_query_navigation()
apply_auth_route()
apply_profile_route()
apply_pending_navigation()


with st.sidebar:
    st.markdown("## Market Intel")
    st.caption("Polymarket wallets, Kalshi markets, whale flow, and cross-venue research.")
    if st.button("Search Parity... /", key="open_command_palette_sidebar", width="stretch"):
        open_command_palette()
    auth_sidebar_cols = st.columns(2)
    if auth_sidebar_cols[0].button("Sign In", key="open_sign_in_sidebar", width="stretch"):
        st.session_state.auth_dialog_mode = "Sign In"
    if auth_sidebar_cols[1].button("Sign Up", key="open_sign_up_sidebar", width="stretch"):
        st.session_state.auth_dialog_mode = "Sign Up"
    page = st.radio(
        "Workspace",
        WORKSPACES,
        key="selected_page",
        label_visibility="collapsed",
    )
    set_query_page(page)
    st.divider()
    global_query = st.text_input("Global search", placeholder="bitcoin, fed, iran, election", key="global_search_query")
    market_limit = st.slider("Market sample", 50, 500, 250, 50)
    trade_limit = st.slider("Trade sample", 50, 500, 250, 50)
    min_whale = st.number_input("Whale threshold", min_value=0, max_value=1_000_000, value=2_500, step=500)
    if st.button("Refresh data", width="stretch"):
        st.cache_data.clear()
        st.rerun()
    st.divider()
    st.caption("Research mode only. This app does not place orders. Kalshi public feeds do not expose wallet identities.")
    st.caption(f"Last render: {md.now_utc_label()}")


def load_market_universe() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    pm = safe_load("Polymarket markets", load_polymarket_markets, market_limit)
    ks = safe_load("Kalshi markets", load_kalshi_markets, market_limit)
    combined = pd.concat([pm, ks], ignore_index=True) if not pm.empty or not ks.empty else pd.DataFrame()
    return pm, ks, combined


def render_metric_strip(pm: pd.DataFrame, ks: pd.DataFrame, trades: pd.DataFrame, leaderboard: pd.DataFrame) -> None:
    total_activity = 0.0
    if not pm.empty:
        volume_col = "activity_volume" if "activity_volume" in pm else "volume_24h"
        total_activity += float(pm[volume_col].fillna(0).sum())
    if not ks.empty:
        volume_col = "activity_volume" if "activity_volume" in ks else "volume_24h"
        total_activity += float(ks[volume_col].fillna(0).sum())
    top_pnl = float(leaderboard["pnl"].max()) if not leaderboard.empty and "pnl" in leaderboard else 0.0
    whale_count = len(trades[trades["notional"] >= float(min_whale)]) if not trades.empty and "notional" in trades else 0
    cols = st.columns(4)
    cols[0].metric("Markets loaded", f"{len(pm) + len(ks):,}", f"{len(pm):,} PM / {len(ks):,} KS")
    cols[1].metric("Loaded activity volume", money(total_activity))
    cols[2].metric("Whale prints", f"{whale_count:,}", f">= {money(min_whale)}")
    cols[3].metric("Top public PnL", money(top_pnl))


def market_tile(row: pd.Series) -> None:
    item = md.watchlist_market_item(row.to_dict())
    market_key = item["market_key"]
    safe_key = re.sub(r"[^a-zA-Z0-9_]", "_", market_key or str(row.name))[:80]
    with st.container(border=True):
        st.caption(f"{row.get('platform', '-')}: {row.get('category', '-')}")
        st.markdown(f"**{str(row.get('title', '-'))[:120]}**")
        change = row.get("change_1d") if row.get("platform") == "Polymarket" else None
        st.markdown(
            f"""
            <div class="market-stats">
              <div class="market-stat"><span>Yes</span><strong>{cents(row.get("yes_price"))}</strong></div>
              <div class="market-stat"><span>Vol</span><strong>{money(row.get("activity_volume", row.get("volume_24h")))}</strong></div>
              <div class="market-stat"><span>1d</span><strong>{signed_cents(change) if change is not None else "-"}</strong></div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        saved_keys = {str(saved.get("market_key", "")).strip() for saved in st.session_state.watchlist}
        action_cols = st.columns([1, 1, 1])
        if action_cols[0].button("Trade Now", type="primary", key=f"tile_inspect_{safe_key}", width="stretch", disabled=not bool(market_key)):
            st.session_state["markets_inspect_market_key"] = market_key
            queue_navigation("Markets", "")
            st.rerun()
        if market_key and market_key in saved_keys:
            if action_cols[1].button("Unsave", key=f"tile_unsave_{safe_key}", width="stretch"):
                st.session_state.watchlist, changed = md.remove_watchlist_market(st.session_state.watchlist, market_key)
                if changed:
                    save_local_list("watchlist.json", st.session_state.watchlist)
                st.rerun()
        else:
            if action_cols[1].button("Save", key=f"tile_save_{safe_key}", width="stretch", disabled=not bool(market_key)):
                st.session_state.watchlist, changed = md.upsert_watchlist_market(st.session_state.watchlist, row.to_dict())
                if changed:
                    save_local_list("watchlist.json", st.session_state.watchlist)
                st.rerun()
        action_cols[2].link_button("Open venue", row.get("url", "https://polymarket.com"), width="stretch")


def combined_trade_table(poly_trades: pd.DataFrame, kalshi_trades: pd.DataFrame) -> pd.DataFrame:
    rows = []
    if not poly_trades.empty:
        rows.append(poly_trades)
    if not kalshi_trades.empty:
        rows.append(kalshi_trades)
    if not rows:
        return pd.DataFrame()
    trades = pd.concat(rows, ignore_index=True, sort=False)
    trades = filter_text(trades, global_query)
    return trades.sort_values("time", ascending=False).reset_index(drop=True)


def market_top_traders(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty or "wallet" not in trades:
        return pd.DataFrame()
    grouped = (
        trades.groupby(["wallet", "trader"], dropna=False)
        .agg(
            trades=("wallet", "size"),
            notional=("notional", "sum"),
            avg_trade=("notional", "mean"),
            largest_trade=("notional", "max"),
            latest_trade=("time", "max"),
            buy_notional=("notional", lambda s: float(s[trades.loc[s.index, "side"].astype(str).str.upper().eq("BUY")].sum())),
            sell_notional=("notional", lambda s: float(s[trades.loc[s.index, "side"].astype(str).str.upper().eq("SELL")].sum())),
            outcomes=("outcome", lambda s: ", ".join(sorted({str(item) for item in s.dropna().head(4)}))),
        )
        .reset_index()
        .sort_values("notional", ascending=False)
    )
    return grouped


def wallet_identity(wallet: str, trades: pd.DataFrame) -> str:
    if not trades.empty and "trader" in trades:
        names = trades["trader"].dropna().astype(str)
        names = names[names.str.strip().ne("")]
        if not names.empty:
            return names.iloc[0]
    return short_addr(wallet)


def wallet_positions_frame(open_positions: pd.DataFrame, closed_positions: pd.DataFrame) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    if not open_positions.empty:
        open_frame = open_positions.copy()
        open_frame["status"] = "Open"
        open_frame["pnl"] = numeric_col(open_frame, "unrealized_pnl")
        open_frame["basis"] = numeric_col(open_frame, "size") * numeric_col(open_frame, "avg_price")
        open_frame["time"] = pd.to_datetime(open_frame.get("end_time"), utc=True, errors="coerce")
        frames.append(open_frame)
    if not closed_positions.empty:
        closed_frame = closed_positions.copy()
        closed_frame["status"] = "Closed"
        closed_frame["pnl"] = numeric_col(closed_frame, "realized_pnl")
        closed_frame["basis"] = numeric_col(closed_frame, "total_bought")
        avg_price = numeric_col(closed_frame, "avg_price").replace({0: pd.NA})
        if "size" not in closed_frame:
            closed_frame["size"] = (numeric_col(closed_frame, "total_bought") / avg_price).fillna(0.0)
        if "value" not in closed_frame:
            closed_frame["value"] = numeric_col(closed_frame, "total_bought") + numeric_col(closed_frame, "realized_pnl")
        if "pnl_pct" not in closed_frame:
            closed_frame["pnl_pct"] = numeric_col(closed_frame, "realized_pnl") / numeric_col(closed_frame, "total_bought").replace({0: pd.NA})
        frames.append(closed_frame)
    if not frames:
        return pd.DataFrame()
    positions = pd.concat(frames, ignore_index=True, sort=False)
    for col in ["platform", "market_key", "title", "outcome", "url"]:
        if col not in positions:
            positions[col] = ""
    return positions


def wallet_pnl_curve(open_positions: pd.DataFrame, closed_positions: pd.DataFrame) -> pd.DataFrame:
    realized = pd.DataFrame()
    if not closed_positions.empty and "time" in closed_positions and "realized_pnl" in closed_positions:
        realized = closed_positions[["time", "realized_pnl"]].copy()
        realized["time"] = pd.to_datetime(realized["time"], utc=True, errors="coerce")
        realized["realized_pnl"] = pd.to_numeric(realized["realized_pnl"], errors="coerce").fillna(0.0)
        realized = realized.dropna(subset=["time"]).sort_values("time")
    rows: list[dict[str, Any]] = []
    cumulative = 0.0
    if not realized.empty:
        grouped = realized.groupby("time", as_index=False)["realized_pnl"].sum().sort_values("time")
        grouped["cumulative"] = grouped["realized_pnl"].cumsum()
        rows.extend(
            {
                "time": row.time,
                "pnl": float(row.cumulative),
                "series": "Realized PnL",
            }
            for row in grouped.itertuples()
        )
        cumulative = float(grouped["cumulative"].iloc[-1])
    unrealized = float(open_positions["unrealized_pnl"].sum()) if not open_positions.empty and "unrealized_pnl" in open_positions else 0.0
    if rows or abs(unrealized) > 0:
        rows.append({"time": pd.Timestamp.utcnow(), "pnl": cumulative + unrealized, "series": "Realized + open PnL"})
    return pd.DataFrame(rows)


def filter_pnl_curve_window(curve: pd.DataFrame, window: str = "1w", now: Any | None = None) -> pd.DataFrame:
    if hasattr(md, "filter_pnl_curve_window"):
        try:
            return md.filter_pnl_curve_window(curve, window, now)
        except AttributeError:
            pass
    if curve.empty:
        return curve.copy()
    days_by_window = {"1d": 1, "1w": 7, "1mo": 30}
    if window not in days_by_window:
        return curve.copy().reset_index(drop=True)
    frame = curve.copy()
    frame["time"] = pd.to_datetime(frame.get("time"), utc=True, errors="coerce")
    frame = frame.dropna(subset=["time"]).sort_values("time")
    current = pd.Timestamp.now(tz="UTC") if now is None else pd.Timestamp(now)
    if current.tzinfo is None:
        current = current.tz_localize("UTC")
    else:
        current = current.tz_convert("UTC")
    return frame[frame["time"] >= current - pd.Timedelta(days=days_by_window[window])].reset_index(drop=True)


def wallet_pnl_calendar(closed_positions: pd.DataFrame, window: str = "1mo", now: Any | None = None) -> pd.DataFrame:
    if hasattr(md, "wallet_pnl_calendar"):
        try:
            return md.wallet_pnl_calendar(closed_positions, window, now)
        except AttributeError:
            pass
    columns = ["date", "realized_pnl", "closed_positions", "cumulative_realized_pnl", "weekday"]
    if closed_positions.empty or "time" not in closed_positions or "realized_pnl" not in closed_positions:
        return pd.DataFrame(columns=columns)
    frame = closed_positions[["time", "realized_pnl"]].copy()
    frame["time"] = pd.to_datetime(frame["time"], utc=True, errors="coerce")
    frame["realized_pnl"] = pd.to_numeric(frame["realized_pnl"], errors="coerce").fillna(0.0)
    frame = frame.dropna(subset=["time"]).sort_values("time")
    days_by_window = {"1d": 1, "1w": 7, "1mo": 30}
    if window in days_by_window:
        current = pd.Timestamp.now(tz="UTC") if now is None else pd.Timestamp(now)
        if current.tzinfo is None:
            current = current.tz_localize("UTC")
        else:
            current = current.tz_convert("UTC")
        frame = frame[frame["time"] >= current - pd.Timedelta(days=days_by_window[window])]
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


def enrich_activity_counterparties(activity: pd.DataFrame, public_trades: pd.DataFrame, wallet: str = "", max_seconds: int = 30) -> pd.DataFrame:
    if hasattr(md, "enrich_activity_counterparties"):
        try:
            return md.enrich_activity_counterparties(activity, public_trades, wallet, max_seconds)
        except AttributeError:
            pass
    if activity.empty:
        return activity.copy()
    frame = activity.copy()
    frame["counterparty"] = "Not public"
    frame["counterparty_wallet"] = ""
    frame["counterparty_confidence"] = 0.0
    frame["counterparty_time_delta_sec"] = pd.NA
    if public_trades.empty:
        return frame
    trades = public_trades.copy()
    for dataset in (frame, trades):
        dataset["time"] = pd.to_datetime(dataset.get("time"), utc=True, errors="coerce")
        dataset["price"] = numeric_col(dataset, "price")
        dataset["size"] = numeric_col(dataset, "size")
        dataset["side"] = dataset.get("side", pd.Series("", index=dataset.index)).fillna("").astype(str).str.upper()
        dataset["market_key"] = dataset.get("market_key", pd.Series("", index=dataset.index)).fillna("").astype(str)
        dataset["asset"] = dataset.get("asset", pd.Series("", index=dataset.index)).fillna("").astype(str)
        dataset["wallet"] = dataset.get("wallet", pd.Series("", index=dataset.index)).fillna("").astype(str)
        dataset["trader"] = dataset.get("trader", pd.Series("", index=dataset.index)).fillna("").astype(str)
    target_wallet = str(wallet or "").lower()
    if target_wallet:
        trades = trades[~trades["wallet"].str.lower().eq(target_wallet)]
    trades = trades.dropna(subset=["time"])
    for idx, row in frame.iterrows():
        if str(row.get("type", "")).upper() != "TRADE" or pd.isna(row.get("time")) or trades.empty:
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
        label = str(best.get("trader") or best.get("wallet") or "Counterparty hint")
        frame.at[idx, "counterparty"] = label
        frame.at[idx, "counterparty_wallet"] = str(best.get("wallet", ""))
        frame.at[idx, "counterparty_confidence"] = float(best.get("score", 0.0))
        frame.at[idx, "counterparty_time_delta_sec"] = float(best.get("time_delta", 0.0))
    return frame


def orderbook_ladder(bids: pd.DataFrame, asks: pd.DataFrame, depth: int = 25) -> pd.DataFrame:
    if hasattr(md, "orderbook_ladder"):
        try:
            return md.orderbook_ladder(bids, asks, depth)
        except AttributeError:
            pass
    frames: list[pd.DataFrame] = []
    for side, source, ascending in (("Bid", bids, False), ("Ask", asks, True)):
        if source.empty:
            continue
        frame = source.copy()
        frame["price"] = numeric_col(frame, "price")
        frame["shares"] = numeric_col(frame, "size")
        frame["notional"] = numeric_col(frame, "notional") if "notional" in frame else frame["price"] * frame["shares"]
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
    if hasattr(md, "orderbook_summary"):
        try:
            return md.orderbook_summary(bids, asks)
        except AttributeError:
            pass
    best_bid = float(numeric_col(bids, "price").max()) if not bids.empty and "price" in bids else None
    best_ask = float(numeric_col(asks, "price").min()) if not asks.empty and "price" in asks else None
    spread = (best_ask - best_bid) if best_bid is not None and best_ask is not None else None
    midpoint = ((best_bid + best_ask) / 2) if best_bid is not None and best_ask is not None else None
    return {
        "best_bid": best_bid,
        "best_ask": best_ask,
        "spread": spread,
        "midpoint": midpoint,
        "bid_depth": float(numeric_col(bids, "notional").sum()) if not bids.empty else 0.0,
        "ask_depth": float(numeric_col(asks, "notional").sum()) if not asks.empty else 0.0,
    }


def wallet_share_payload(wallet: str, name: str, summary: dict[str, Any], open_positions: pd.DataFrame) -> str:
    top_open = []
    if not open_positions.empty:
        top = open_positions.sort_values("value", ascending=False).head(5)
        for row in top.itertuples():
            top_open.append(f"- {getattr(row, 'title', '-')[:90]} | {getattr(row, 'outcome', '-')} | {money(getattr(row, 'value', 0.0))}")
    lines = [
        f"Trader: {name}",
        f"Wallet: {wallet}",
        f"Total PnL: {money(summary['realized_pnl'] + summary['unrealized_pnl'])}",
        f"Realized PnL: {money(summary['realized_pnl'])}",
        f"Unrealized PnL: {money(summary['unrealized_pnl'])}",
        f"Open value: {money(summary['open_value'])}",
        f"Win rate: {pct(summary['win_rate']) if summary['win_rate'] is not None else '-'}",
        f"Recent trade notional: {money(summary['trade_notional'])}",
        "",
        "Top open positions:",
        *(top_open or ["- none"]),
    ]
    return "\n".join(lines)


def render_market_news(title: str, key: str) -> None:
    query = st.text_input("News query", value=title, key=f"news_query_{key}")
    news = safe_load("Market news", load_market_news, query, 20)
    if news.empty:
        draw_empty("No public news results returned for this query.")
        return
    st.dataframe(
        clean_table(news, ["time", "source", "title", "url"]),
        width="stretch",
        height=430,
        column_config={"url": st.column_config.LinkColumn("URL")},
    )


def render_market_comments(market_key: str, title: str) -> None:
    key = str(market_key or title)
    comments = st.session_state.market_comments.get(key, [])
    if comments:
        st.dataframe(pd.DataFrame(comments), width="stretch", height=240)
    else:
        draw_empty("No local comments yet.")
    note = st.text_area("Add local comment", key=f"comment_text_{key}", height=110, placeholder="Write research notes, links, or thesis updates for this market.")
    if st.button("Save comment", key=f"save_comment_{key}", width="content") and note.strip():
        comments.append({"time": md.now_utc_label(), "comment": note.strip()})
        st.session_state.market_comments[key] = comments
        save_local_market_comments(st.session_state.market_comments)
        st.rerun()


def execute_research_trade(row: pd.Series, side: str, outcome: str, notional: float, price: float) -> None:
    if notional <= 0 or price <= 0:
        return
    market_key = str(row.get("market_key", "") or row.get("ticker", "") or row.get("title", ""))
    title = str(row.get("title", "") or market_key)
    platform = str(row.get("platform", ""))
    url = str(row.get("url", ""))
    portfolio = st.session_state.portfolio.copy()
    for col, default in {
        "platform": "",
        "market": "",
        "market_key": "",
        "url": "",
        "outcome": "",
        "shares": 0.0,
        "avg_price": 0.0,
        "current_price": 0.0,
    }.items():
        if col not in portfolio:
            portfolio[col] = default
    mask = (portfolio["market_key"].astype(str) == market_key) & (portfolio["outcome"].astype(str).str.lower() == outcome.lower())
    existing_shares = 0.0
    existing_avg = 0.0
    if mask.any():
        idx = portfolio[mask].index[0]
        existing_shares = float(portfolio.at[idx, "shares"] or 0.0)
        existing_avg = float(portfolio.at[idx, "avg_price"] or 0.0)
    cash_before = max(float(st.session_state.get("research_cash", RESEARCH_START_CASH) or 0.0), 0.0)
    executable_notional = research_trade_executable_notional(notional, cash_before, side)
    preview = research_trade_preview(existing_shares, existing_avg, side, executable_notional, price)
    executed_shares = float(preview["executed_shares"])
    executed_notional = float(preview["executed_notional"])
    if executed_shares <= 0:
        return
    side_label = "Sell" if str(side).lower() == "sell" else "Buy"
    if mask.any():
        idx = portfolio[mask].index[0]
        new_shares = float(preview["new_shares"])
        if side_label == "Buy" and new_shares > 0:
            portfolio.at[idx, "avg_price"] = float(preview["avg_price_after"])
        portfolio.at[idx, "shares"] = max(0.0, new_shares)
        portfolio.at[idx, "current_price"] = price
        portfolio.at[idx, "platform"] = platform
        portfolio.at[idx, "market"] = title
        portfolio.at[idx, "url"] = url
    else:
        portfolio = pd.concat(
            [
                portfolio,
                pd.DataFrame(
                    [
                        {
                            "platform": platform,
                            "market": title,
                            "market_key": market_key,
                            "url": url,
                            "outcome": outcome,
                            "shares": executed_shares,
                            "avg_price": float(preview["avg_price_after"]),
                            "current_price": price,
                        }
                    ]
                ),
            ],
            ignore_index=True,
        )
    portfolio = portfolio[portfolio["shares"].fillna(0).astype(float) > 1e-9].reset_index(drop=True)
    st.session_state.portfolio = portfolio
    save_local_portfolio(portfolio)
    cash_after = cash_before - executed_notional if side_label == "Buy" else cash_before + executed_notional
    cash_after = max(float(cash_after), 0.0)
    st.session_state.research_cash = cash_after
    save_local_research_cash(cash_after)
    st.session_state.paper_trade_history.append(
        {
            "time": md.now_utc_label(),
            "platform": platform,
            "market": title,
            "market_key": market_key,
            "side": side_label,
            "outcome": outcome,
            "price": price,
            "shares": executed_shares,
            "notional": executed_notional,
            "requested_notional": notional,
            "realized_pnl": float(preview["realized_pnl"]),
            "capped": bool(preview["capped"]),
            "cash_after": cash_after,
            "url": url,
        }
    )
    save_local_list("paper_trade_history.json", st.session_state.paper_trade_history)


def research_trade_preview(existing_shares: float, existing_avg_price: float, side: str, requested_notional: float, price: float) -> dict[str, float | str]:
    if hasattr(md, "research_trade_preview"):
        try:
            return md.research_trade_preview(existing_shares, existing_avg_price, side, requested_notional, price)
        except AttributeError:
            pass
    old_shares = max(float(existing_shares or 0.0), 0.0)
    old_avg = max(float(existing_avg_price or 0.0), 0.0)
    trade_price = max(float(price or 0.0), 0.0)
    requested = max(float(requested_notional or 0.0), 0.0)
    side_label = "Sell" if str(side).lower() == "sell" else "Buy"
    if requested <= 0 or trade_price <= 0:
        return {"side": side_label, "requested_notional": requested, "executed_notional": 0.0, "requested_shares": 0.0, "executed_shares": 0.0, "old_shares": old_shares, "new_shares": old_shares, "avg_price_after": old_avg, "realized_pnl": 0.0, "capped": 0.0}
    requested_shares = requested / trade_price
    if side_label == "Buy":
        new_shares = old_shares + requested_shares
        avg_after = ((old_shares * old_avg) + requested) / new_shares if new_shares else trade_price
        return {"side": side_label, "requested_notional": requested, "executed_notional": requested, "requested_shares": requested_shares, "executed_shares": requested_shares, "old_shares": old_shares, "new_shares": new_shares, "avg_price_after": avg_after, "realized_pnl": 0.0, "capped": 0.0}
    executed_shares = min(old_shares, requested_shares)
    executed_notional = executed_shares * trade_price
    new_shares = max(0.0, old_shares - executed_shares)
    return {"side": side_label, "requested_notional": requested, "executed_notional": executed_notional, "requested_shares": requested_shares, "executed_shares": executed_shares, "old_shares": old_shares, "new_shares": new_shares, "avg_price_after": old_avg if new_shares > 0 else 0.0, "realized_pnl": (trade_price - old_avg) * executed_shares, "capped": 1.0 if executed_shares < requested_shares else 0.0}


def research_trade_max_notional(available_cash: float, existing_shares: float, price: float, side: str) -> float:
    if hasattr(md, "research_trade_max_notional"):
        try:
            return float(md.research_trade_max_notional(available_cash, existing_shares, price, side))
        except AttributeError:
            pass
    if str(side).lower() == "sell":
        return max(float(existing_shares or 0.0), 0.0) * max(float(price or 0.0), 0.0)
    return max(float(available_cash or 0.0), 0.0)


def research_trade_executable_notional(requested_notional: float, available_cash: float, side: str) -> float:
    if hasattr(md, "research_trade_executable_notional"):
        try:
            return float(md.research_trade_executable_notional(requested_notional, available_cash, side))
        except AttributeError:
            pass
    requested = max(float(requested_notional or 0.0), 0.0)
    if str(side).lower() == "sell":
        return requested
    return min(requested, max(float(available_cash or 0.0), 0.0))


def render_research_trade_ticket(row: pd.Series, key_prefix: str = "ticket") -> None:
    st.markdown("### Paper trade ticket")
    yes_price = float(row.get("yes_price") or 0.0)
    no_price = float(row.get("no_price") or (1 - yes_price if yes_price else 0.0))
    market_key = str(row.get("market_key", "") or row.get("ticker", "") or row.get("title", ""))
    widget_key = re.sub(r"[^A-Za-z0-9_]+", "_", f"{key_prefix}_{market_key}")[:180]
    default_side = "Sell" if str(row.get("default_side", "Buy")).lower() == "sell" else "Buy"
    default_outcome = "No" if str(row.get("default_outcome", "Yes")).lower() == "no" else "Yes"
    portfolio = st.session_state.portfolio.copy()
    t1, t2, t3, t4 = st.columns([1, 1, 1, 1])
    side = t1.radio("Side", ["Buy", "Sell"], index=0 if default_side == "Buy" else 1, horizontal=True, key=f"{widget_key}_side")
    outcome = t2.radio("Outcome", ["Yes", "No"], index=0 if default_outcome == "Yes" else 1, horizontal=True, key=f"{widget_key}_outcome")
    preset = t3.radio("Amount", ["$5", "$10", "$50", "Custom", "Max"], horizontal=True, key=f"{widget_key}_amount")
    current_price = yes_price if outcome == "Yes" else no_price
    custom_notional = t4.number_input("Custom notional", min_value=0.0, value=25.0, step=5.0, disabled=preset != "Custom", key=f"{widget_key}_custom")
    position = pd.DataFrame()
    if not portfolio.empty and {"market_key", "outcome"}.issubset(portfolio.columns):
        position = portfolio[
            (portfolio["market_key"].astype(str).eq(market_key))
            & (portfolio["outcome"].astype(str).str.lower().eq(outcome.lower()))
        ].head(1)
    existing_shares = float(position.iloc[0].get("shares", 0.0)) if not position.empty else 0.0
    existing_avg = float(position.iloc[0].get("avg_price", 0.0)) if not position.empty else 0.0
    available_cash = max(float(st.session_state.get("research_cash", RESEARCH_START_CASH) or 0.0), 0.0)
    max_notional = research_trade_max_notional(available_cash, existing_shares, current_price, side)
    requested_notional = {"$5": 5.0, "$10": 10.0, "$50": 50.0, "Max": max_notional}.get(preset, float(custom_notional))
    notional = research_trade_executable_notional(requested_notional, available_cash, side)
    preview = research_trade_preview(existing_shares, existing_avg, side, float(notional), float(current_price))
    p1, p2, p3, p4, p5, p6 = st.columns(6)
    p1.metric("Research cash", money(available_cash))
    p2.metric("Max notional", money(max_notional))
    p3.metric("Reference price", cents(current_price))
    p4.metric("Current shares", f"{existing_shares:,.2f}", cents(existing_avg) if existing_avg else "")
    p5.metric("Executed shares", f"{float(preview['executed_shares']):,.2f}")
    p6.metric("Position after", f"{float(preview['new_shares']):,.2f}", cents(float(preview["avg_price_after"])) if float(preview["avg_price_after"]) else "")
    st.caption(f"Realized PnL on this paper order: {money(float(preview['realized_pnl']))}.")
    if side == "Buy" and float(requested_notional) > float(notional):
        st.warning("Buy size is capped to current research cash. Use Portfolio to add or reset research cash.")
    if side == "Sell" and float(preview["capped"]):
        st.warning("Sell size is capped to the current research position. The simulated order will not short the market.")
    elif side == "Sell" and float(preview["executed_shares"]) <= 0:
        st.warning("No current research shares to sell for this outcome.")
    if st.button("TRADE NOW (paper)", type="primary", key=f"{widget_key}_trade", width="content"):
        execute_research_trade(row, side, outcome, float(requested_notional), float(current_price))
        st.success(
            f"Paper {side.lower()} executed: {outcome} {money(float(preview['executed_notional']))} "
            f"at {cents(current_price)}."
        )
        st.rerun()


def render_market_quick_trade_bar(row: pd.Series, market_key: str, selected_outcome: str = "Yes") -> None:
    st.markdown("#### Quick paper trade")
    ticket_key = f"market_quick_trade_ticket_{market_key}"
    quick_cols = st.columns([1, 1, 1.15, 1.2])
    if quick_cols[0].button(f"YES {cents(row.get('yes_price'))}", key=f"quick_yes_{market_key}", width="stretch"):
        st.session_state[ticket_key] = md.market_quick_trade_ticket(row, "Yes")
        st.info("YES paper ticket staged below.")
    if quick_cols[1].button(f"NO {cents(row.get('no_price'))}", key=f"quick_no_{market_key}", width="stretch"):
        st.session_state[ticket_key] = md.market_quick_trade_ticket(row, "No")
        st.info("NO paper ticket staged below.")
    if quick_cols[2].button("TRADE NOW (paper)", type="primary", key=f"quick_trade_now_{market_key}", width="stretch"):
        st.session_state[ticket_key] = md.market_quick_trade_ticket(row, selected_outcome)
        st.info(f"{selected_outcome} paper ticket staged below.")
    quick_cols[3].link_button("Open venue", row.get("url", "https://polymarket.com"), width="stretch")
    if ticket_key in st.session_state:
        with st.expander("Quick paper ticket", expanded=True):
            render_research_trade_ticket(pd.Series(st.session_state[ticket_key]), key_prefix="market_quick_trade")


def _history_window_config(label: str) -> tuple[int, pd.Timedelta | None, str, str]:
    mapping = {
        "1hr": (1, pd.Timedelta(hours=1), "1h", "5min"),
        "6hr": (1, pd.Timedelta(hours=6), "1h", "15min"),
        "1d": (1, pd.Timedelta(days=1), "1h", "30min"),
        "1w": (7, pd.Timedelta(days=7), "1h", "2h"),
        "1mo": (30, pd.Timedelta(days=30), "1d", "1d"),
        "All": (180, None, "1d", "1d"),
    }
    return mapping.get(label, mapping["1mo"])


def open_featured_market(row: pd.Series, outcome: str | None = None) -> None:
    market_key = str(row.get("market_key") or row.get("ticker") or row.get("title") or "")
    if market_key:
        st.session_state["markets_inspect_market_key"] = market_key
    if outcome:
        st.session_state[f"detail_outcome_{market_key}"] = outcome
    queue_navigation("Markets", "")
    st.rerun()


def render_featured_market(row: pd.Series, position_label: str = "") -> None:
    header_cols = st.columns([2, 1, 1])
    header_cols[0].markdown("### Featured market")
    if position_label:
        header_cols[1].metric("Slot", position_label)
    header_cols[2].caption(f"{row.get('platform', '-')} | {row.get('category', '-')}")
    st.markdown(f"**{row.get('title', '-')}**")
    f1, f2, f3, f4 = st.columns(4)
    f1.metric("Vol 24h", money(row.get("activity_volume", row.get("volume_24h"))))
    f2.metric("Liq / OI", money(row.get("liquidity") or row.get("open_interest")))
    f3.metric("1h", signed_cents(row.get("change_1h")) if pd.notna(row.get("change_1h", pd.NA)) else "-")
    f4.metric("24h", signed_cents(row.get("change_1d")) if pd.notna(row.get("change_1d", pd.NA)) else "-")
    outcome_cols = st.columns([1, 1, 1, 1])
    if outcome_cols[0].button(f"Yes {pct(row.get('yes_price'))}", key=f"featured_yes_{row.get('market_key')}", width="stretch"):
        open_featured_market(row, "Yes")
    if outcome_cols[1].button(f"No {pct(row.get('no_price'))}", key=f"featured_no_{row.get('market_key')}", width="stretch"):
        open_featured_market(row, "No")
    if outcome_cols[2].button("Trade Now", type="primary", key=f"featured_trade_now_{row.get('market_key')}", width="stretch"):
        open_featured_market(row)
    outcome_cols[3].link_button("Open venue", row.get("url", "https://polymarket.com"), width="stretch")
    c1, c2 = st.columns([1, 1])
    chart_type = c1.radio("Chart", ["Line", "Candlestick"], horizontal=True, key=f"featured_chart_{row.get('market_key')}")
    window = c2.radio("Window", ["1hr", "6hr", "1d", "1w", "1mo", "All"], horizontal=True, key=f"featured_window_{row.get('market_key')}")

    if row.get("platform") == "Polymarket":
        days, since_delta, interval, candle_rule = _history_window_config(window)
        hist = safe_load("Featured price history", load_price_history, row.get("yes_token_id"), days, interval)
        if not hist.empty and since_delta is not None:
            hist = hist[pd.to_datetime(hist["time"], utc=True, errors="coerce") >= pd.Timestamp.utcnow() - since_delta]
        if hist.empty:
            draw_empty("No chart history returned for the featured market.")
        elif chart_type == "Candlestick":
            candles = (
                hist.set_index("time")["price"]
                .resample(candle_rule)
                .ohlc()
                .dropna()
                .reset_index()
            )
            fig = go.Figure(
                data=[
                    go.Candlestick(
                        x=candles["time"],
                        open=candles["open"],
                        high=candles["high"],
                        low=candles["low"],
                        close=candles["close"],
                        increasing_line_color=ACCENT,
                        decreasing_line_color=RED,
                    )
                ]
            )
            fig.update_layout(height=340, margin=dict(l=10, r=10, t=20, b=10), paper_bgcolor=BG, plot_bgcolor=BG, template="plotly_dark")
            st.plotly_chart(fig, width="stretch", config=plot_config())
        else:
            fig = px.line(hist, x="time", y="price", template="plotly_dark", labels={"price": "Yes price"})
            fig.update_traces(line_color=ACCENT, line_width=2)
            fig.update_layout(height=340, margin=dict(l=10, r=10, t=20, b=10), paper_bgcolor=BG, plot_bgcolor=BG)
            st.plotly_chart(fig, width="stretch", config=plot_config())
    else:
        days = 30 if window in {"1mo", "All"} else 7
        period = 60 if window in {"1hr", "6hr", "1d", "1w"} else 1440
        candles = safe_load("Featured Kalshi candles", load_kalshi_candles, row.get("ticker"), days, period)
        if candles.empty:
            draw_empty("No Kalshi chart history returned for the featured market.")
        elif chart_type == "Candlestick":
            fig = go.Figure(
                data=[
                    go.Candlestick(
                        x=candles["time"],
                        open=candles["open"],
                        high=candles["high"],
                        low=candles["low"],
                        close=candles["close"],
                        increasing_line_color=ACCENT,
                        decreasing_line_color=RED,
                    )
                ]
            )
            fig.update_layout(height=340, margin=dict(l=10, r=10, t=20, b=10), paper_bgcolor=BG, plot_bgcolor=BG, template="plotly_dark")
            st.plotly_chart(fig, width="stretch", config=plot_config())
        else:
            fig = px.line(candles, x="time", y="close", template="plotly_dark", labels={"close": "Yes price"})
            fig.update_traces(line_color=ACCENT, line_width=2)
            fig.update_layout(height=340, margin=dict(l=10, r=10, t=20, b=10), paper_bgcolor=BG, plot_bgcolor=BG)
            st.plotly_chart(fig, width="stretch", config=plot_config())
    with st.expander("Trade Now (paper)", expanded=False):
        render_research_trade_ticket(row)


def render_price_history_chart(hist: pd.DataFrame, chart_type: str, candle_rule: str, y_col: str = "price", label: str = "Yes price") -> None:
    if hist.empty:
        draw_empty("No price history returned for this selection.")
        return
    if chart_type == "Candlestick":
        candles = hist.set_index("time")[y_col].resample(candle_rule).ohlc().dropna().reset_index()
        if candles.empty:
            draw_empty("Not enough price points for candlesticks in this window.")
            return
        fig = go.Figure(
            data=[
                go.Candlestick(
                    x=candles["time"],
                    open=candles["open"],
                    high=candles["high"],
                    low=candles["low"],
                    close=candles["close"],
                    increasing_line_color=ACCENT,
                    decreasing_line_color=RED,
                    name=label,
                )
            ]
        )
        fig.update_layout(height=360, margin=dict(l=10, r=10, t=20, b=10), paper_bgcolor=BG, plot_bgcolor=BG, template="plotly_dark")
        st.plotly_chart(fig, width="stretch", config=plot_config())
        return
    fig = px.line(hist, x="time", y=y_col, template="plotly_dark", labels={y_col: label})
    fig.update_traces(line_color=ACCENT, line_width=2)
    fig.update_layout(height=360, margin=dict(l=10, r=10, t=20, b=10), paper_bgcolor=BG, plot_bgcolor=BG)
    st.plotly_chart(fig, width="stretch", config=plot_config())


def _holder_outcome_label(holder: pd.Series, yes_asset: str, no_asset: str) -> str:
    asset = str(holder.get("asset", ""))
    if yes_asset and asset == yes_asset:
        return "Yes"
    if no_asset and asset == no_asset:
        return "No"
    index = str(holder.get("outcome_index", ""))
    if index in {"0", "0.0"}:
        return "Yes"
    if index in {"1", "1.0"}:
        return "No"
    return "Unknown"


def enrich_market_holders(holders: pd.DataFrame, trades: pd.DataFrame, yes_price: Any, no_price: Any) -> pd.DataFrame:
    if hasattr(md, "enrich_market_holders"):
        try:
            return md.enrich_market_holders(holders, trades, yes_price, no_price)
        except AttributeError:
            pass
    if holders.empty:
        return holders
    df = holders.copy()
    if "outcome" not in df:
        df["outcome"] = ""
    df["wallet_key"] = df.get("wallet", pd.Series("", index=df.index)).astype(str).str.lower()
    df["shares"] = numeric_col(df, "amount")
    try:
        yes = float(yes_price or 0.0)
    except (TypeError, ValueError):
        yes = 0.0
    if yes > 1.0:
        yes /= 100.0
    try:
        no = float(no_price if no_price is not None else 1 - yes)
    except (TypeError, ValueError):
        no = 1 - yes
    if no > 1.0:
        no /= 100.0
    yes = max(0.0, min(yes, 1.0))
    no = max(0.0, min(no, 1.0))
    df["current_price"] = df["outcome"].map({"Yes": yes, "No": no}).fillna(0.0)
    df["value"] = df["shares"] * df["current_price"]
    df["avg_price_est"] = pd.NA
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
        tape["size"] = numeric_col(tape, "size")
        tape["price"] = numeric_col(tape, "price")
        tape["side"] = tape.get("side", pd.Series("", index=tape.index)).astype(str).str.upper()
        tape["time"] = pd.to_datetime(tape["time"] if "time" in tape else pd.Series(pd.NaT, index=tape.index), utc=True, errors="coerce")
        buys = tape[tape["side"].eq("BUY") & (tape["size"] > 0) & (tape["price"] > 0)].copy()
        if not buys.empty:
            buys["weighted_cost"] = buys["size"] * buys["price"]
            avg = buys.groupby(["wallet_key", "outcome"], as_index=False).agg(buy_size=("size", "sum"), weighted_cost=("weighted_cost", "sum"))
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
    cost_basis = df["shares"] * avg_price
    df["unrealized_pnl_est"] = df["value"] - cost_basis
    df["pnl_pct_est"] = df["unrealized_pnl_est"] / cost_basis.replace({0: pd.NA})
    activity_size = numeric_col(df, "activity_size")
    df["activity"] = df["activity_side"].fillna("").astype(str).str.title()
    df.loc[activity_size > 0, "activity"] = df.loc[activity_size > 0, "activity"] + " " + activity_size.loc[activity_size > 0].round(1).astype(str)
    return df.sort_values("value", ascending=False, na_position="last").reset_index(drop=True)


def holder_strength_summary(holders: pd.DataFrame) -> dict[str, Any]:
    if hasattr(md, "holder_strength_summary"):
        try:
            return md.holder_strength_summary(holders)
        except AttributeError:
            pass
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
    frame["value"] = numeric_col(frame, "value" if "value" in frame else "amount").clip(lower=0.0)
    frame["outcome"] = frame["outcome"].fillna("Unknown").astype(str)
    by_side = frame.groupby("outcome")["value"].sum()
    yes_value = float(by_side.get("Yes", 0.0))
    no_value = float(by_side.get("No", 0.0))
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
        "unknown_value": float(by_side.drop(labels=["Yes", "No"], errors="ignore").sum()),
        "yes_share": yes_share,
        "no_share": no_share,
        "dominant_side": dominant_side,
        "dominant_share": dominant_share,
        "skew": abs(yes_share - no_share),
        "top_10_share": top_10_value / total_value if total_value else 0.0,
        "holder_count": int(len(frame)),
    }


def render_holder_bubble_chart(display: pd.DataFrame, height: int = 330) -> None:
    if display.empty:
        draw_empty("No holders match the current bubble chart filter.")
        return
    bubble = display.head(150).copy()
    for col, default in {"wallet": "", "trader": "", "shares": 0.0, "avg_price_est": pd.NA, "unrealized_pnl_est": pd.NA, "activity": "", "verified": False}.items():
        if col not in bubble:
            bubble[col] = default
    bubble["wallet_short"] = bubble["wallet"].astype(str).map(short_addr)
    fig = px.scatter(
        bubble,
        x="outcome",
        y="value",
        size="shares",
        color="outcome",
        hover_data=["trader", "wallet_short", "shares", "avg_price_est", "unrealized_pnl_est", "activity", "verified"],
        template="plotly_dark",
        color_discrete_map={"Yes": ACCENT, "No": RED, "Unknown": MUTED},
    )
    fig.update_layout(height=height, margin=dict(l=10, r=10, t=15, b=10), paper_bgcolor=BG, plot_bgcolor=BG)
    st.plotly_chart(fig, width="stretch", config=plot_config())


@st.dialog("Holder Bubble Chart", width="large")
def render_holder_bubble_dialog(display: pd.DataFrame, title: str) -> None:
    st.caption(title)
    summary = holder_strength_summary(display)
    c1, c2, c3 = st.columns(3)
    c1.metric("Dominant side", str(summary["dominant_side"]), pct(summary["dominant_share"]))
    c2.metric("Top 10 share", pct(summary["top_10_share"]))
    c3.metric("Displayed value", money(summary["total_value"]))
    render_holder_bubble_chart(display, height=560)


def trader_insight_metrics(
    open_positions: pd.DataFrame,
    closed_positions: pd.DataFrame,
    trades: pd.DataFrame,
    activity: pd.DataFrame | None = None,
    cash_balance: float = 0.0,
    whale_threshold: float = 10_000.0,
) -> dict[str, float | None]:
    if hasattr(md, "trader_insight_metrics"):
        try:
            return md.trader_insight_metrics(open_positions, closed_positions, trades, activity, cash_balance, whale_threshold)
        except AttributeError:
            pass
    summary = md.wallet_summary(open_positions, closed_positions, trades)
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
    tape["price"] = numeric_col(tape, "price")
    tape["size"] = numeric_col(tape, "size")
    tape["notional"] = numeric_col(tape, "notional") if "notional" in tape else tape["price"] * tape["size"]
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


def page_overview() -> None:
    section_header(
        "Market intelligence terminal",
        "Live public data for prediction-market flow, top Polymarket wallets, and cross-venue price gaps.",
    )
    pm, ks, combined = load_market_universe()
    if not combined.empty:
        combined = add_market_filter_metrics(combined)
    overview_category_col = "filter_category" if "filter_category" in combined else "category"
    categories = sorted(
        [str(item) for item in combined.get(overview_category_col, pd.Series(dtype=str)).dropna().unique() if str(item)],
        key=lambda item: (md.market_category_label(item).casefold(), str(item).casefold()),
    )
    for key, value in overview_filter_defaults(global_query, 6, int(min_whale), categories).items():
        if key not in st.session_state:
            st.session_state[key] = value
    if st.session_state.pop("overview_filters_reset_pending", False):
        reset_overview_filter_widgets(global_query, 6, int(min_whale), categories)
    pending_overview_view = st.session_state.pop("pending_overview_filter_view", None)
    if isinstance(pending_overview_view, dict):
        apply_overview_filter_view_widgets(pending_overview_view, categories)
    pending_overview_clear = st.session_state.pop("overview_clear_pending", None)
    if isinstance(pending_overview_clear, dict):
        for key, value in pending_overview_clear.items():
            st.session_state[key] = value
    route_filter_params = query_param_snapshot(
        [
            "q",
            "query",
            "search",
            "market",
            "event",
            "platform",
            "platforms",
            "venue",
            "venues",
            "featured",
            "featuredSource",
            "source",
            "marketRows",
            "cards",
            "rows",
            "limit",
            "category",
            "categories",
            "includeCategory",
            "include",
            "excludeCategory",
            "excludeCategories",
            "exclude",
            "minVolume",
            "volumeMin",
            "volMin",
            "minLiquidity",
            "liquidityMin",
            "liqMin",
            "minFlow",
            "flowMin",
            "minNotional",
            "notionalMin",
            "active",
            "activeOnly",
            "activeMarkets",
            "showNews",
            "news",
            "newsfeed",
        ]
    )
    route_filter_signature = json.dumps(route_filter_params, sort_keys=True)
    route_filter_view = md.predictparity_overview_filter_view(route_filter_params)
    if route_filter_view and st.session_state.get("overview_route_filter_signature") != route_filter_signature:
        apply_overview_filter_view_widgets(route_filter_view, categories)
        st.session_state["overview_route_filter_signature"] = route_filter_signature
        st.session_state["overview_view_loaded_message"] = "Loaded overview filters from URL."

    leaderboard = safe_load("Polymarket leaderboard", load_leaderboard, 50, "ALL", "PNL")
    controls = st.columns([1.5, 1, 1, 1])
    overview_query = controls[0].text_input("Overview search", placeholder="market, category, trader, wallet", key="overview_search")
    overview_platforms = controls[1].multiselect("Platform", ["Polymarket", "Kalshi"], key="overview_platforms")
    featured_source = controls[2].radio("Featured", ["Polymarket", "Any"], horizontal=True, key="overview_featured_source")
    overview_market_rows = controls[3].slider("Market cards", min_value=3, max_value=24, step=3, key="overview_market_rows")
    with st.expander("Overview filters", expanded=False):
        f1, f2, f3, f4 = st.columns(4)
        overview_min_volume = f1.number_input("Min market volume", min_value=0, step=1000, key="overview_min_volume")
        overview_min_liquidity = f2.number_input("Min liquidity", min_value=0, step=1000, key="overview_min_liquidity")
        overview_min_flow = f3.number_input("Min flow notional", min_value=0, step=500, key="overview_min_flow_notional")
        active_only = f4.checkbox("Active markets only", key="overview_active_only")
        show_news = f4.checkbox("Show newsfeed", key="overview_show_news")
        overview_chip_source = combined.copy()
        if overview_category_col in overview_chip_source:
            overview_chip_source["category"] = overview_chip_source[overview_category_col]
        category_counts = md.market_category_counts(overview_chip_source)
        if category_counts:
            st.markdown("##### Category chips")
            show_all_categories = bool(st.session_state.get("overview_show_more_categories", False))
            category_chips = md.market_category_chip_options(
                overview_chip_source,
                st.session_state.get("overview_include_categories", []),
                st.session_state.get("overview_exclude_categories", []),
                limit=8,
                show_all=show_all_categories,
            )
            for chunk_start in range(0, len(category_chips), 4):
                chip_cols = st.columns(4)
                for offset, option in enumerate(category_chips[chunk_start : chunk_start + 4]):
                    category = str(option["category"])
                    slug = re.sub(r"[^a-zA-Z0-9]+", "_", category).strip("_").lower()[:32] or f"cat_{chunk_start + offset}"
                    if chip_cols[offset].button(
                        str(option["label"]),
                        key=f"overview_category_chip_{chunk_start + offset}_{slug}",
                        width="stretch",
                    ):
                        include_next, exclude_next = md.cycle_market_category_filter(
                            st.session_state.get("overview_include_categories", []),
                            st.session_state.get("overview_exclude_categories", []),
                            category,
                        )
                        st.session_state["overview_include_categories"] = include_next
                        st.session_state["overview_exclude_categories"] = exclude_next
                        st.rerun()
            if len(category_counts) > 8:
                if st.button("Show fewer categories" if show_all_categories else "Show more categories", key="overview_show_more_categories_button"):
                    st.session_state["overview_show_more_categories"] = not show_all_categories
                    st.rerun()
        cat_cols = st.columns(2)
        include_categories = cat_cols[0].multiselect("Include categories", categories, key="overview_include_categories", format_func=md.market_category_label)
        exclude_categories = cat_cols[1].multiselect("Exclude categories", categories, key="overview_exclude_categories", format_func=md.market_category_label)
        if st.button("Reset Filters", width="stretch", key="reset_overview_filters_button"):
            st.session_state["overview_filters_reset_pending"] = True
            st.rerun()

    save_cols = st.columns([2, 1, 1])
    saved_overview_name = save_cols[0].text_input("Saved overview view name", value=f"Overview {md.now_utc_label()}", key="saved_overview_view_name")
    save_overview_clicked = save_cols[1].button("Save Filter", width="stretch", key="save_overview_filter_button")
    if save_cols[2].button("Reset Overview View", width="stretch", key="reset_overview_view_button"):
        st.session_state["overview_filters_reset_pending"] = True
        st.rerun()
    loaded_overview_message = st.session_state.pop("overview_view_loaded_message", "")
    if loaded_overview_message:
        st.info(loaded_overview_message)
    if st.session_state.saved_overview_filters:
        load_cols = st.columns([2, 1, 1])
        saved_labels = [
            f"{i + 1}. {view.get('name') or view.get('query') or 'Overview view'}"
            for i, view in enumerate(st.session_state.saved_overview_filters)
        ]
        selected_saved_overview = load_cols[0].selectbox("Load saved overview view", saved_labels, key="load_saved_overview_view")
        selected_overview_view = st.session_state.saved_overview_filters[saved_labels.index(selected_saved_overview)]
        if load_cols[1].button("Load overview view", key="load_overview_view_button"):
            st.session_state["pending_overview_filter_view"] = selected_overview_view
            st.session_state["overview_view_loaded_message"] = f"Loaded saved overview view: {selected_overview_view.get('name', selected_saved_overview)}"
            st.rerun()
        if load_cols[2].button("Delete overview view", key="delete_overview_view_button"):
            st.session_state.saved_overview_filters.pop(saved_labels.index(selected_saved_overview))
            save_local_list("saved_overview_filters.json", st.session_state.saved_overview_filters)
            st.rerun()
    if save_overview_clicked:
        st.session_state.saved_overview_filters.append(
            {
                "name": saved_overview_name.strip() or f"Overview {md.now_utc_label()}",
                "created_at": md.now_utc_label(),
                "query": overview_query,
                "platforms": overview_platforms,
                "featured_source": featured_source,
                "market_rows": int(overview_market_rows),
                "include_categories": include_categories,
                "exclude_categories": exclude_categories,
                "min_volume": int(overview_min_volume),
                "min_liquidity": int(overview_min_liquidity),
                "min_flow_notional": int(overview_min_flow),
                "active_only": bool(active_only),
                "show_news": bool(show_news),
            }
        )
        save_local_list("saved_overview_filters.json", st.session_state.saved_overview_filters)
        st.success("Saved overview view.")

    overview_defaults = overview_filter_defaults(min_flow=int(min_whale), categories=categories)
    chips: list[str] = []
    if overview_query.strip():
        chips.append(f"Search: {overview_query.strip()}")
    if set(overview_platforms) != set(overview_defaults["overview_platforms"]):
        chips.append("Platform: " + (", ".join(overview_platforms) if overview_platforms else "none"))
    if featured_source != overview_defaults["overview_featured_source"]:
        chips.append(f"Featured: {featured_source}")
    if int(overview_market_rows) != int(overview_defaults["overview_market_rows"]):
        chips.append(f"Cards: {int(overview_market_rows)}")
    if include_categories:
        chips.append("Include: " + ", ".join(md.market_category_label(item) for item in include_categories[:3]) + ("..." if len(include_categories) > 3 else ""))
    if exclude_categories:
        chips.append("Exclude: " + ", ".join(md.market_category_label(item) for item in exclude_categories[:3]) + ("..." if len(exclude_categories) > 3 else ""))
    if int(overview_min_volume) > 0:
        chips.append(f"Volume >= {money(overview_min_volume)}")
    if int(overview_min_liquidity) > 0:
        chips.append(f"Liquidity >= {money(overview_min_liquidity)}")
    if int(overview_min_flow) > 0:
        chips.append(f"Flow >= {money(overview_min_flow)}")
    if active_only:
        chips.append("Active markets only")
    if not show_news:
        chips.append("News hidden")
    render_filter_chips(chips)

    clear_actions: list[tuple[str, dict[str, Any]]] = []
    if overview_query.strip():
        clear_actions.append(("search", {"overview_search": ""}))
    if set(overview_platforms) != set(overview_defaults["overview_platforms"]):
        clear_actions.append(("platform", {"overview_platforms": overview_defaults["overview_platforms"]}))
    if featured_source != overview_defaults["overview_featured_source"]:
        clear_actions.append(("featured", {"overview_featured_source": overview_defaults["overview_featured_source"]}))
    if int(overview_market_rows) != int(overview_defaults["overview_market_rows"]):
        clear_actions.append(("cards", {"overview_market_rows": overview_defaults["overview_market_rows"]}))
    if include_categories:
        clear_actions.append(("include", {"overview_include_categories": []}))
    if set(exclude_categories) != set(overview_defaults["overview_exclude_categories"]):
        clear_actions.append(("exclude", {"overview_exclude_categories": overview_defaults["overview_exclude_categories"]}))
    if int(overview_min_volume) > 0:
        clear_actions.append(("volume", {"overview_min_volume": 0}))
    if int(overview_min_liquidity) > 0:
        clear_actions.append(("liquidity", {"overview_min_liquidity": 0}))
    if int(overview_min_flow) > 0:
        clear_actions.append(("flow", {"overview_min_flow_notional": 0}))
    if active_only:
        clear_actions.append(("active markets", {"overview_active_only": False}))
    if not show_news:
        clear_actions.append(("news", {"overview_show_news": True}))
    render_filter_clear_buttons(clear_actions, "overview")
    if st.session_state.saved_overview_filters:
        st.caption(f"Saved overview views: {len(st.session_state.saved_overview_filters)}")
        with st.expander("Saved overview filters", expanded=False):
            st.dataframe(pd.DataFrame(st.session_state.saved_overview_filters), width="stretch", height=160)
            if st.button("Clear saved overview filters"):
                st.session_state.saved_overview_filters = []
                save_local_list("saved_overview_filters.json", st.session_state.saved_overview_filters)
                st.rerun()

    poly_trades = safe_load("Polymarket trades", load_polymarket_trades, trade_limit, 0.0, None, None)
    kalshi_trades = safe_load("Kalshi trades", load_kalshi_trades, trade_limit, None)
    trades = combined_trade_table(poly_trades, kalshi_trades)
    if not trades.empty:
        trades = filter_text(trades, overview_query)
        if overview_platforms:
            trades = trades[trades["platform"].isin(overview_platforms)]
        else:
            trades = trades.iloc[0:0]
        trades = trades[numeric_col(trades, "notional") >= float(overview_min_flow)]

    render_metric_strip(pm, ks, trades, leaderboard)
    st.divider()

    filtered = combined[combined["platform"].isin(overview_platforms)].copy() if not combined.empty and overview_platforms else pd.DataFrame()
    filtered = filter_text(filtered, overview_query)
    if include_categories and overview_category_col in filtered:
        filtered = filtered[filtered[overview_category_col].astype(str).isin(include_categories)]
    if exclude_categories and overview_category_col in filtered:
        filtered = filtered[~filtered[overview_category_col].astype(str).isin(exclude_categories)]
    if active_only and not filtered.empty:
        if "active" in filtered:
            filtered = filtered[filtered["active"].fillna(True).astype(bool)]
        if "closed" in filtered:
            filtered = filtered[~filtered["closed"].fillna(False).astype(bool)]
    if not filtered.empty:
        volume_filter_col = _monitor_volume_col(filtered)
        filtered = filtered[numeric_col(filtered, volume_filter_col) >= float(overview_min_volume)]
        if "liquidity" in filtered:
            filtered = filtered[numeric_col(filtered, "liquidity") >= float(overview_min_liquidity)]
    volume_col = "activity_volume" if "activity_volume" in filtered else "volume_24h"
    featured = filtered[filtered["platform"].eq("Polymarket")].head(3) if featured_source == "Polymarket" and not filtered.empty and "platform" in filtered else pd.DataFrame()
    if featured.empty:
        featured = filtered.sort_values(volume_col, ascending=False).head(3) if not filtered.empty else pd.DataFrame()
    if not featured.empty:
        featured = featured.reset_index(drop=True)
        current_featured_index = md.cycle_featured_index(st.session_state.get("overview_featured_index", 0), len(featured), 0)
        st.session_state["overview_featured_index"] = current_featured_index
        nav_prev, nav_label, nav_next, nav_view_all = st.columns([1, 2, 1, 1])
        if nav_prev.button("Prev", key="overview_featured_prev", width="stretch", disabled=len(featured) <= 1):
            st.session_state["overview_featured_index"] = md.cycle_featured_index(current_featured_index, len(featured), -1)
            st.rerun()
        nav_label.markdown(f"**FEATURED MARKET**  \n{current_featured_index + 1}/{len(featured)}")
        if nav_next.button("Next", key="overview_featured_next", width="stretch", disabled=len(featured) <= 1):
            st.session_state["overview_featured_index"] = md.cycle_featured_index(current_featured_index, len(featured), 1)
            st.rerun()
        if nav_view_all.button("View all ->", key="overview_featured_view_all", width="stretch"):
            queue_navigation("Markets", overview_query)
            st.rerun()
        featured_row = featured.iloc[current_featured_index]
        left, right = st.columns([1.35, 1])
        with left:
            render_featured_market(featured_row, f"{current_featured_index + 1}/{len(featured)}")
        with right:
            if show_news:
                st.markdown("### Newsfeed")
                news = safe_load("Featured market news", load_market_news, str(featured_row.get("title", "")), 12)
                if news.empty:
                    draw_empty("No public news results returned for this featured market.")
                else:
                    st.dataframe(
                        clean_table(news, ["time", "source", "title", "url"]).head(12),
                        width="stretch",
                        height=470,
                        column_config={"time": st.column_config.DatetimeColumn(format="YYYY-MM-DD HH:mm"), "url": st.column_config.LinkColumn("URL")},
                    )
            else:
                draw_empty("Newsfeed hidden by the current overview filters.")
        st.divider()

    top_markets = filtered.sort_values(volume_col, ascending=False).head(int(overview_market_rows)) if not filtered.empty else pd.DataFrame()
    trending_header, trending_action = st.columns([3, 1])
    trending_header.markdown("### TRENDING MARKETS")
    if trending_action.button("View all ->", key="overview_trending_view_all", width="stretch"):
        queue_navigation("Markets", overview_query)
        st.rerun()
    if top_markets.empty:
        draw_empty("No markets match the current filters.")
    else:
        for chunk_start in range(0, len(top_markets), 3):
            cols = st.columns(3)
            for col, (_, row) in zip(cols, top_markets.iloc[chunk_start : chunk_start + 3].iterrows()):
                with col:
                    market_tile(row)

    st.divider()
    left, right = st.columns([1.2, 1])
    with left:
        st.markdown("### Venue volume")
        if combined.empty:
            draw_empty("Volume chart unavailable.")
        else:
            volume_col = "activity_volume" if "activity_volume" in combined else "volume_24h"
            by_platform = combined.groupby("platform", as_index=False)[volume_col].sum()
            fig = px.bar(
                by_platform,
                x="platform",
                y=volume_col,
                color="platform",
                color_discrete_map={"Polymarket": ACCENT, "Kalshi": BLUE},
                template="plotly_dark",
                labels={volume_col: "loaded volume"},
            )
            fig.update_layout(height=330, margin=dict(l=10, r=10, t=20, b=10), paper_bgcolor=BG, plot_bgcolor=BG)
            st.plotly_chart(fig, width="stretch", config=plot_config())
    with right:
        st.markdown("### Recent large flow")
        if trades.empty:
            draw_empty("No recent trades returned.")
        else:
            display = clean_table(trades, ["platform", "time", "trader", "wallet", "side", "outcome", "title", "price", "size", "notional"])
            display["wallet"] = display["wallet"].astype(str).map(short_addr)
            st.download_button("Export overview flow CSV", trades.to_csv(index=False).encode("utf-8"), file_name="overview_large_flow.csv", mime="text/csv")
            st.dataframe(
                display.head(12),
                width="stretch",
                height=330,
                column_config={
                    "price": st.column_config.NumberColumn(format="%.3f"),
                    "size": st.column_config.NumberColumn(format="%.0f"),
                    "notional": st.column_config.NumberColumn(format="$%.0f"),
                },
            )


def page_search() -> None:
    section_header("Search", "Global Parity-style search across markets, traders, trades, news, cross-venue pairs, alerts, and tracked items.")
    query_default = global_query or (str(st.session_state.recent_searches[0]) if st.session_state.recent_searches else "")
    if "search_query" not in st.session_state:
        reset_search_filter_widgets(query_default)
    if st.session_state.pop("search_filters_reset_pending", False):
        reset_search_filter_widgets(query_default)
    pending_search_view = st.session_state.pop("pending_search_filter_view", None)
    if isinstance(pending_search_view, dict):
        apply_search_filter_view_widgets(pending_search_view)
    pending_search_clear = st.session_state.pop("search_clear_pending", None)
    if isinstance(pending_search_clear, dict):
        for key, value in pending_search_clear.items():
            st.session_state[key] = value
    route_filter_params = query_param_snapshot(
        [
            "q",
            "query",
            "search",
            "platform",
            "platforms",
            "venue",
            "venues",
            "type",
            "types",
            "result",
            "results",
            "minValue",
            "valueMin",
            "min",
            "minNotional",
            "rows",
            "limit",
            "active",
            "activeMarkets",
            "activeOnly",
            "tracked",
            "trackedOnly",
            "broadPairs",
            "fallbackPairs",
        ]
    )
    route_filter_signature = json.dumps(route_filter_params, sort_keys=True)
    route_filter_view = md.predictparity_search_filter_view(route_filter_params)
    if route_filter_view and st.session_state.get("search_route_filter_signature") != route_filter_signature:
        apply_search_filter_view_widgets(route_filter_view)
        st.session_state["search_route_filter_signature"] = route_filter_signature
        st.session_state["search_view_loaded_message"] = "Loaded search filters from URL."
    previous_search_types = set(st.session_state.get("search_result_types", []))
    if previous_search_types == {"Markets", "Traders", "Trades", "News", "Cross-Venue", "Tracked"}:
        st.session_state["search_result_types"] = list(SEARCH_RESULT_TYPES)

    top = st.columns([2.4, 1, 1, 1])
    query = top[0].text_input("Search Parity", placeholder="bitcoin, iran, election, wallet, trader", key="search_query")
    platforms = top[1].multiselect("Platform", ["Polymarket", "Kalshi"], key="search_platforms")
    rows = top[2].slider("Rows", min_value=10, max_value=250, step=10, key="search_rows")
    min_value = top[3].number_input("Min value", min_value=0, step=1000, key="search_min_value")
    with st.expander("Search filters", expanded=False):
        f1, f2, f3, f4 = st.columns(4)
        result_types = f1.multiselect(
            "Result types",
            SEARCH_RESULT_TYPES,
            key="search_result_types",
        )
        active_markets_only = f2.checkbox("Active markets only", key="search_active_markets_only")
        tracked_only = f3.checkbox("Tracked only", key="search_tracked_only")
        broad_pairs = f4.checkbox("Fallback broad pairs", key="search_broad_pairs")

    actions = st.columns([1, 1, 1, 1, 2])
    if actions[0].button("Run search", type="primary"):
        clean_query = query.strip()
        if clean_query:
            st.session_state.recent_searches = [clean_query] + [item for item in st.session_state.recent_searches if str(item).lower() != clean_query.lower()]
            st.session_state.recent_searches = st.session_state.recent_searches[:12]
            save_local_list("recent_searches.json", st.session_state.recent_searches)
            st.rerun()
    save_search_clicked = actions[1].button("Save Filter", width="stretch", key="save_search_filter_button")
    if actions[2].button("Reset Filters", width="stretch", key="reset_search_filters_button"):
        st.session_state["search_filters_reset_pending"] = True
        st.rerun()
    if actions[3].button("Clear recents"):
        st.session_state.recent_searches = []
        save_local_list("recent_searches.json", st.session_state.recent_searches)
        st.rerun()

    saved_search_name = st.text_input("Saved search view name", value=f"Search {md.now_utc_label()}", key="saved_search_view_name")
    loaded_search_message = st.session_state.pop("search_view_loaded_message", "")
    if loaded_search_message:
        st.info(loaded_search_message)
    if st.session_state.saved_search_filters:
        load_cols = st.columns([2, 1, 1])
        saved_labels = [
            f"{i + 1}. {view.get('name') or view.get('query') or 'Search view'}"
            for i, view in enumerate(st.session_state.saved_search_filters)
        ]
        selected_saved_search = load_cols[0].selectbox("Load saved search view", saved_labels, key="load_saved_search_view")
        selected_search_view = st.session_state.saved_search_filters[saved_labels.index(selected_saved_search)]
        if load_cols[1].button("Load search view", key="load_search_view_button"):
            st.session_state["pending_search_filter_view"] = selected_search_view
            st.session_state["search_view_loaded_message"] = f"Loaded saved search view: {selected_search_view.get('name', selected_saved_search)}"
            st.rerun()
        if load_cols[2].button("Delete search view", key="delete_search_view_button"):
            st.session_state.saved_search_filters.pop(saved_labels.index(selected_saved_search))
            save_local_list("saved_search_filters.json", st.session_state.saved_search_filters)
            st.rerun()
    if save_search_clicked:
        st.session_state.saved_search_filters.append(
            {
                "name": saved_search_name.strip() or f"Search {md.now_utc_label()}",
                "created_at": md.now_utc_label(),
                "query": query,
                "platforms": platforms,
                "rows": int(rows),
                "min_value": float(min_value),
                "result_types": result_types,
                "active_markets_only": bool(active_markets_only),
                "tracked_only": bool(tracked_only),
                "broad_pairs": bool(broad_pairs),
            }
        )
        save_local_list("saved_search_filters.json", st.session_state.saved_search_filters)
        st.success("Saved search view.")
    if st.session_state.recent_searches:
        st.caption("Recent searches: " + " | ".join(str(item) for item in st.session_state.recent_searches[:8]))

    pm, ks, combined = load_market_universe()
    markets = combined[combined["platform"].isin(platforms)].copy() if not combined.empty else pd.DataFrame()
    if active_markets_only and not markets.empty:
        if "active" in markets:
            markets = markets[markets["active"].fillna(True).astype(bool)]
        if "closed" in markets:
            markets = markets[~markets["closed"].fillna(False).astype(bool)]
    markets = filter_text(markets, query)
    if tracked_only and not markets.empty:
        tracked_market_keys = {str(item.get("market_key", "")) for item in st.session_state.watchlist}
        markets = markets[markets["market_key"].astype(str).isin(tracked_market_keys)] if tracked_market_keys else markets.iloc[0:0]
    if not markets.empty:
        volume_col = _monitor_volume_col(markets)
        markets = markets[numeric_col(markets, volume_col) >= float(min_value)]
        markets = markets.sort_values(volume_col, ascending=False).head(int(rows)).reset_index(drop=True)

    leaderboard = safe_load("Polymarket leaderboard", load_leaderboard, int(rows), "ALL", "PNL")
    recent_flow = safe_load("Recent Polymarket trader flow", load_polymarket_trades, 500, 0.0, None, None)
    flow_scores = md.trader_flow_scores(recent_flow, whale_threshold=float(min_whale))
    traders = leaderboard.merge(flow_scores, on="wallet", how="left") if not leaderboard.empty and not flow_scores.empty else leaderboard
    traders = filter_text(traders, query)
    if tracked_only and not traders.empty:
        tracked_wallets_lower = {str(item).lower() for item in st.session_state.followed_wallets}
        traders = traders[traders["wallet"].astype(str).str.lower().isin(tracked_wallets_lower)] if tracked_wallets_lower else traders.iloc[0:0]
    if not traders.empty:
        traders = traders[numeric_col(traders, "volume") >= float(min_value)].head(int(rows)).reset_index(drop=True)
        trader_wallets = tuple(traders["wallet"].astype(str).head(min(30, len(traders))).tolist()) if "wallet" in traders else ()
        if trader_wallets:
            trader_positions = safe_load("Search trader open positions", load_wallet_position_values, trader_wallets, 80, default=pd.DataFrame())
            traders = md.merge_profile_position_values(traders, trader_positions)

    poly_trades = safe_load("Polymarket trades", load_polymarket_trades, int(rows), 0.0, None, None)
    kalshi_trades = safe_load("Kalshi trades", load_kalshi_trades, int(rows), None)
    trades = combined_trade_table(poly_trades, kalshi_trades)
    if not trades.empty:
        trades = trades[trades["platform"].isin(platforms)]
        trades = filter_text(trades, query)
        if tracked_only:
            tracked_market_keys = {str(item.get("market_key", "")) for item in st.session_state.watchlist}
            tracked_wallets_lower = {str(item).lower() for item in st.session_state.followed_wallets}
            market_mask = trades.get("market_key", pd.Series("", index=trades.index)).astype(str).isin(tracked_market_keys)
            wallet_mask = trades.get("wallet", pd.Series("", index=trades.index)).astype(str).str.lower().isin(tracked_wallets_lower)
            trades = trades[market_mask | wallet_mask]
        trades = trades[numeric_col(trades, "notional") >= float(min_value)].head(int(rows)).reset_index(drop=True)

    news = safe_load("Search news", load_market_news, query, 30) if query.strip() else pd.DataFrame()
    pairs = md.cross_venue_candidates(pm, ks, query=query, min_similarity=0.25, max_pairs=min(int(rows), 100)) if query.strip() else pd.DataFrame()
    if pairs.empty and query.strip() and broad_pairs:
        pairs = md.cross_venue_candidates(pm, ks, query="", min_similarity=0.25, max_pairs=min(int(rows), 100))

    tracked_keys = {str(item.get("market_key")) for item in st.session_state.watchlist if item.get("market_key")}
    alert_signals = build_monitor_signals(
        markets.copy(),
        trades.copy(),
        min_volume=float(min_value),
        min_liquidity=0.0,
        min_move=0.03,
        max_spread=0.07,
        min_whale_notional=max(float(min_value), float(min_whale)),
        ending_days=7,
        holder_threshold=0.25,
        holder_checks=0,
        tracked_keys=tracked_keys,
    )
    alert_hits = build_monitor_alert_hits(alert_signals, st.session_state.monitor_rules)
    if not alert_hits.empty:
        alert_results = alert_hits.copy()
        alert_results["alert_source"] = "Rule hit"
    else:
        alert_results = alert_signals.copy()
        if not alert_results.empty:
            alert_results["rule_name"] = ""
            alert_results["rule_type"] = ""
            alert_results["alert_source"] = "Signal"
    if not alert_results.empty:
        alert_results = alert_results.head(int(rows)).reset_index(drop=True)

    tracked_markets = pd.DataFrame(st.session_state.watchlist)
    tracked_markets = filter_text(tracked_markets, query) if not tracked_markets.empty else tracked_markets
    tracked_wallets = pd.DataFrame({"wallet": st.session_state.followed_wallets})
    if not tracked_wallets.empty:
        tracked_wallets["wallet_short"] = tracked_wallets["wallet"].astype(str).map(short_addr)
        tracked_wallets = filter_text(tracked_wallets, query)

    if "Markets" not in result_types:
        markets = pd.DataFrame()
    if "Traders" not in result_types:
        traders = pd.DataFrame()
    if "Trades" not in result_types:
        trades = pd.DataFrame()
    if "News" not in result_types:
        news = pd.DataFrame()
    if "Cross-Venue" not in result_types:
        pairs = pd.DataFrame()
    if "Alerts" not in result_types:
        alert_results = pd.DataFrame()
        alert_hits = pd.DataFrame()
        alert_signals = pd.DataFrame()
    if "Tracked" not in result_types:
        tracked_markets = pd.DataFrame()
        tracked_wallets = pd.DataFrame()

    m1, m2, m3, m4, m5, m6, m7 = st.columns(7)
    m1.metric("Markets", f"{len(markets):,}")
    m2.metric("Traders", f"{len(traders):,}")
    m3.metric("Trades", f"{len(trades):,}")
    m4.metric("News", f"{len(news):,}")
    m5.metric("Pairs", f"{len(pairs):,}")
    m6.metric("Alerts", f"{len(alert_results):,}", delta=f"{len(alert_hits):,} hits" if len(alert_hits) else None)
    m7.metric("Tracked", f"{len(tracked_markets) + len(tracked_wallets):,}")
    search_chips: list[str] = []
    if query.strip():
        search_chips.append(f"Search: {query.strip()}")
    if platforms and set(platforms) != {"Polymarket", "Kalshi"}:
        search_chips.append("Platform: " + ", ".join(platforms))
    if result_types and set(result_types) != set(SEARCH_RESULT_TYPES):
        search_chips.append("Types: " + ", ".join(result_types))
    if min_value:
        search_chips.append(f"Min value: {money(min_value)}")
    if active_markets_only:
        search_chips.append("Active markets only")
    if tracked_only:
        search_chips.append("Tracked only")
    if broad_pairs and query.strip():
        search_chips.append("Broad pair fallback")
    search_chips.append(f"Rows: {rows}")
    render_filter_chips(search_chips)
    search_defaults = search_filter_defaults(query_default)
    all_search_types = set(search_defaults["search_result_types"])
    search_clear_actions: list[tuple[str, dict[str, Any]]] = []
    if query.strip():
        search_clear_actions.append(("search", {"search_query": ""}))
    if set(platforms) != set(search_defaults["search_platforms"]):
        search_clear_actions.append(("platform", {"search_platforms": search_defaults["search_platforms"]}))
    if set(result_types) != all_search_types:
        search_clear_actions.append(("result types", {"search_result_types": search_defaults["search_result_types"]}))
    if int(min_value) > 0:
        search_clear_actions.append(("min value", {"search_min_value": 0}))
    if active_markets_only:
        search_clear_actions.append(("active markets", {"search_active_markets_only": False}))
    if tracked_only:
        search_clear_actions.append(("tracked only", {"search_tracked_only": False}))
    if broad_pairs and query.strip():
        search_clear_actions.append(("broad pairs", {"search_broad_pairs": False}))
    if int(rows) != int(search_defaults["search_rows"]):
        search_clear_actions.append(("rows", {"search_rows": search_defaults["search_rows"]}))
    render_filter_clear_buttons(search_clear_actions, "search")
    if st.session_state.saved_search_filters:
        st.caption(f"Saved search views: {len(st.session_state.saved_search_filters)}")
        with st.expander("Saved search filters", expanded=False):
            st.dataframe(pd.DataFrame(st.session_state.saved_search_filters), width="stretch", height=160)
            if st.button("Clear saved search filters"):
                st.session_state.saved_search_filters = []
                save_local_list("saved_search_filters.json", st.session_state.saved_search_filters)
                st.rerun()

    tab_all, tab_markets, tab_traders, tab_trades, tab_news, tab_pairs, tab_alerts, tab_tracked = st.tabs(
        ["All", "Markets", "Traders", "Trades", "News", "Cross-Venue", "Alerts", "Tracked"]
    )
    market_cols = ["platform", "title", "category", "yes_price", "activity_volume", "volume_24h", "liquidity", "spread", "change_1h", "end_time", "url"]
    market_config = {
        "yes_price": st.column_config.NumberColumn(format="%.3f"),
        "activity_volume": st.column_config.NumberColumn(format="$%.0f"),
        "volume_24h": st.column_config.NumberColumn(format="$%.0f"),
        "liquidity": st.column_config.NumberColumn(format="$%.0f"),
        "spread": st.column_config.NumberColumn(format="%.3f"),
        "change_1h": st.column_config.NumberColumn(format="%+.3f"),
        "url": st.column_config.LinkColumn("URL"),
    }
    with tab_all:
        c1, c2 = st.columns([1, 1])
        with c1:
            st.markdown("### Top markets")
            if markets.empty:
                draw_empty("No market results.")
            else:
                st.dataframe(clean_table(markets, market_cols).head(12), width="stretch", height=320, column_config=market_config)
        with c2:
            st.markdown("### Recent trades")
            if trades.empty:
                draw_empty("No trade results.")
            else:
                display = clean_table(trades, ["platform", "time", "trader", "wallet", "side", "outcome", "title", "notional"])
                if "wallet" in display:
                    display["wallet"] = display["wallet"].astype(str).map(short_addr)
                st.dataframe(display.head(12), width="stretch", height=320, column_config={"notional": st.column_config.NumberColumn(format="$%.0f")})
        st.markdown("### News")
        if news.empty:
            draw_empty("No news results.")
        else:
            st.dataframe(clean_table(news, ["time", "source", "title", "url"]).head(10), width="stretch", height=260, column_config={"url": st.column_config.LinkColumn("URL")})
        st.markdown("### Alerts and signals")
        if alert_results.empty:
            draw_empty("No alert signals for this search.")
        else:
            display = clean_table(alert_results, ["alert_source", "rule_name", "time", "signal_type", "platform", "reason", "title", "value", "notional", "wallet", "url"]).head(10)
            if "wallet" in display:
                display["wallet"] = display["wallet"].astype(str).map(short_addr)
            st.dataframe(
                display,
                width="stretch",
                height=260,
                column_config={
                    "time": st.column_config.DatetimeColumn(format="YYYY-MM-DD HH:mm"),
                    "value": st.column_config.NumberColumn(format="%.4f"),
                    "notional": st.column_config.NumberColumn(format="$%.0f"),
                    "url": st.column_config.LinkColumn("URL"),
                },
            )
        st.markdown("### Top traders")
        if traders.empty:
            draw_empty("No trader results.")
        else:
            trader_preview = traders.copy()
            trader_preview["wallet_short"] = trader_preview.get("wallet", pd.Series("", index=trader_preview.index)).astype(str).map(short_addr)
            st.dataframe(
                clean_table(trader_preview, ["rank", "trader", "wallet_short", "pnl", "positions_value", "volume"]).head(10),
                width="stretch",
                height=240,
                column_config={
                    "pnl": st.column_config.NumberColumn(format="$%.0f"),
                    "positions_value": st.column_config.NumberColumn("Positions", format="$%.0f"),
                    "volume": st.column_config.NumberColumn(format="$%.0f"),
                },
            )
    with tab_markets:
        if markets.empty:
            draw_empty("No market results match the search.")
        else:
            st.download_button("Export market search CSV", clean_table(markets, market_cols).to_csv(index=False).encode("utf-8"), file_name="search_markets.csv", mime="text/csv")
            st.dataframe(clean_table(markets, market_cols).head(int(rows)), width="stretch", height=470, column_config=market_config)
            options = [f"{row.platform}: {str(row.title)[:100]}" for _, row in markets.iterrows()]
            selected = st.selectbox("Add result to watchlist", options, key="search_add_market")
            selected_row = markets.iloc[options.index(selected)]
            if st.button("Add selected market", key="search_add_market_button"):
                item = {
                    "platform": selected_row["platform"],
                    "market_key": selected_row["market_key"],
                    "title": selected_row["title"],
                    "url": selected_row["url"],
                }
                if item["market_key"] not in [w["market_key"] for w in st.session_state.watchlist]:
                    st.session_state.watchlist.append(item)
                    save_local_list("watchlist.json", st.session_state.watchlist)
                    st.success("Market added to watchlist.")
    with tab_traders:
        if traders.empty:
            draw_empty("No trader results match the search.")
        else:
            display = traders.copy()
            if "wallet" in display:
                display["wallet_short"] = display["wallet"].astype(str).map(short_addr)
            trader_cols = [
                "rank",
                "trader",
                "wallet",
                "pnl",
                "positions_value",
                "open_positions",
                "open_markets",
                "volume",
                "recent_trades",
                "recent_notional",
                "largest_trade",
                "markets",
                "verified",
            ]
            st.download_button("Export trader search CSV", clean_table(display, trader_cols).to_csv(index=False).encode("utf-8"), file_name="search_traders.csv", mime="text/csv")
            st.dataframe(
                clean_table(display, ["rank", "trader", "wallet_short", "pnl", "positions_value", "open_positions", "open_markets", "volume", "recent_trades", "recent_notional", "largest_trade", "markets", "verified"]).head(int(rows)),
                width="stretch",
                height=470,
                column_config={
                    "pnl": st.column_config.NumberColumn(format="$%.0f"),
                    "positions_value": st.column_config.NumberColumn("Positions", format="$%.0f"),
                    "open_positions": st.column_config.NumberColumn("Open", format="%.0f"),
                    "open_markets": st.column_config.NumberColumn("Markets", format="%.0f"),
                    "volume": st.column_config.NumberColumn(format="$%.0f"),
                    "recent_notional": st.column_config.NumberColumn(format="$%.0f"),
                    "largest_trade": st.column_config.NumberColumn(format="$%.0f"),
                },
            )
            trader_options = [
                f"{row.get('trader', row.get('wallet_short', 'Trader'))} | {short_addr(str(row.get('wallet', '')))} | {money(row.get('pnl', 0.0))}"
                for _, row in display.iterrows()
            ]
            selected_trader = st.selectbox("Track trader wallet", trader_options, key="search_track_trader")
            trader_row = display.iloc[trader_options.index(selected_trader)]
            trader_wallet = str(trader_row.get("wallet", ""))
            trader_actions = st.columns([1, 1, 1, 3])
            if trader_actions[0].button("Open selected wallet", key="search_open_trader_wallet", width="stretch"):
                st.session_state["wallets_inspect_wallet"] = trader_wallet
                queue_navigation("Wallets", query)
                st.rerun()
            tracked_wallet_set = {str(item).lower() for item in st.session_state.followed_wallets}
            if trader_wallet.lower() in tracked_wallet_set:
                trader_actions[1].button("Tracked", key="search_trader_wallet_tracked", width="stretch", disabled=True)
            elif trader_actions[1].button("Track selected wallet", key="search_track_trader_button", width="stretch"):
                st.session_state.followed_wallets, changed = md.upsert_followed_wallet(st.session_state.followed_wallets, trader_wallet)
                if changed:
                    save_local_list("followed_wallets.json", st.session_state.followed_wallets)
                    st.success("Trader wallet added to tracked wallets.")
                st.rerun()
            if re.fullmatch(r"0x[a-fA-F0-9]{40}", trader_wallet):
                trader_actions[2].link_button("Polymarket", f"https://polymarket.com/profile/{trader_wallet}", width="stretch")
    with tab_trades:
        if trades.empty:
            draw_empty("No trade results match the search.")
        else:
            display = clean_table(trades, ["platform", "time", "trader", "wallet", "side", "outcome", "title", "price", "size", "notional", "url"])
            if "wallet" in display:
                display["wallet"] = display["wallet"].astype(str).map(short_addr)
            st.download_button("Export trade search CSV", trades.to_csv(index=False).encode("utf-8"), file_name="search_trades.csv", mime="text/csv")
            st.dataframe(
                display.head(int(rows)),
                width="stretch",
                height=500,
                column_config={
                    "price": st.column_config.NumberColumn(format="%.4f"),
                    "size": st.column_config.NumberColumn(format="%.2f"),
                    "notional": st.column_config.NumberColumn(format="$%.0f"),
                    "url": st.column_config.LinkColumn("URL"),
                },
            )
            trade_options = [f"{row.platform}: {str(row.title)[:80]} | {money(row.notional)}" for _, row in trades.iterrows()]
            selected_trade = st.selectbox("Track trade source", trade_options, key="search_track_trade")
            trade_row = trades.iloc[trade_options.index(selected_trade)]
            track_cols = st.columns([1, 1])
            if track_cols[0].button("Track trade market", key="search_track_trade_market"):
                item = {
                    "platform": str(trade_row.get("platform", "")),
                    "market_key": str(trade_row.get("market_key", "") or trade_row.get("ticker", "") or trade_row.get("title", "")),
                    "title": str(trade_row.get("title", "")),
                    "url": str(trade_row.get("url", "")),
                }
                if item["market_key"] not in [w["market_key"] for w in st.session_state.watchlist]:
                    st.session_state.watchlist.append(item)
                    save_local_list("watchlist.json", st.session_state.watchlist)
                    st.success("Trade market added to watchlist.")
            if track_cols[1].button("Track trade wallet", key="search_track_trade_wallet"):
                trade_wallet = str(trade_row.get("wallet", ""))
                if re.fullmatch(r"0x[a-fA-F0-9]{40}", trade_wallet) and trade_wallet.lower() not in [w.lower() for w in st.session_state.followed_wallets]:
                    st.session_state.followed_wallets.append(trade_wallet)
                    save_local_list("followed_wallets.json", st.session_state.followed_wallets)
                    st.success("Trade wallet added to tracked wallets.")
    with tab_news:
        if news.empty:
            draw_empty("No public news results for this query.")
        else:
            st.download_button("Export news search CSV", clean_table(news, ["time", "source", "title", "url"]).to_csv(index=False).encode("utf-8"), file_name="search_news.csv", mime="text/csv")
            st.dataframe(clean_table(news, ["time", "source", "title", "url"]), width="stretch", height=500, column_config={"url": st.column_config.LinkColumn("URL")})
    with tab_pairs:
        if pairs.empty:
            draw_empty("No cross-venue pairs for this query.")
        else:
            table = pairs.copy()
            table["gap"] = table["gap"].map(lambda value: f"{value * 100:+.1f}c")
            table["polymarket_yes"] = table["polymarket_yes"].map(cents)
            table["kalshi_yes"] = table["kalshi_yes"].map(cents)
            st.dataframe(
                clean_table(table, ["similarity", "gap", "lower_yes", "polymarket_title", "kalshi_title", "polymarket_yes", "kalshi_yes", "polymarket_url", "kalshi_url"]),
                width="stretch",
                height=500,
                column_config={"polymarket_url": st.column_config.LinkColumn("Polymarket"), "kalshi_url": st.column_config.LinkColumn("Kalshi")},
            )
            pair_options = [f"{i + 1}. {row.lower_yes} lower | {str(row.polymarket_title)[:70]}" for i, row in pairs.head(int(rows)).iterrows()]
            selected_pair = st.selectbox("Track pair leg", pair_options, key="search_track_pair")
            pair_row = pairs.iloc[pair_options.index(selected_pair)]
            pair_cols = st.columns([1, 1])
            if pair_cols[0].button("Track Polymarket pair leg", key="search_track_pair_poly"):
                item = {
                    "platform": "Polymarket",
                    "market_key": str(pair_row.get("polymarket_market_key") or pair_row.get("polymarket_title", "")),
                    "title": str(pair_row.get("polymarket_title", "")),
                    "url": str(pair_row.get("polymarket_url", "")),
                }
                if item["market_key"] not in [w["market_key"] for w in st.session_state.watchlist]:
                    st.session_state.watchlist.append(item)
                    save_local_list("watchlist.json", st.session_state.watchlist)
                    st.success("Polymarket pair leg added to watchlist.")
            if pair_cols[1].button("Track Kalshi pair leg", key="search_track_pair_kalshi"):
                item = {
                    "platform": "Kalshi",
                    "market_key": str(pair_row.get("kalshi_market_key") or pair_row.get("kalshi_title", "")),
                    "title": str(pair_row.get("kalshi_title", "")),
                    "url": str(pair_row.get("kalshi_url", "")),
                }
                if item["market_key"] not in [w["market_key"] for w in st.session_state.watchlist]:
                    st.session_state.watchlist.append(item)
                    save_local_list("watchlist.json", st.session_state.watchlist)
                    st.success("Kalshi pair leg added to watchlist.")
    with tab_alerts:
        if alert_results.empty:
            draw_empty("No alert hits or monitor signals match the search.")
            if st.session_state.monitor_rules:
                st.caption("Saved alert rules exist, but none match this search right now.")
            else:
                st.caption("No saved alert rules yet. Signal rows still appear here when the search finds fast movers, whale prints, tight spreads, endings, or watched markets.")
        else:
            alert_cols = [
                "alert_source",
                "rule_name",
                "time",
                "signal_type",
                "platform",
                "reason",
                "title",
                "price",
                "value",
                "notional",
                "liquidity",
                "spread",
                "change_1h",
                "wallet",
                "url",
            ]
            st.download_button(
                "Export alert search CSV",
                clean_table(alert_results, alert_cols).to_csv(index=False).encode("utf-8"),
                file_name="search_alerts.csv",
                mime="text/csv",
            )
            display = clean_table(alert_results, alert_cols)
            if "wallet" in display:
                display["wallet"] = display["wallet"].astype(str).map(short_addr)
            st.dataframe(
                display.head(int(rows)),
                width="stretch",
                height=500,
                column_config={
                    "time": st.column_config.DatetimeColumn(format="YYYY-MM-DD HH:mm"),
                    "price": st.column_config.NumberColumn(format="%.4f"),
                    "value": st.column_config.NumberColumn(format="%.4f"),
                    "notional": st.column_config.NumberColumn(format="$%.0f"),
                    "liquidity": st.column_config.NumberColumn(format="$%.0f"),
                    "spread": st.column_config.NumberColumn(format="%.4f"),
                    "change_1h": st.column_config.NumberColumn(format="%+.4f"),
                    "url": st.column_config.LinkColumn("URL"),
                },
            )
            alert_options = [f"{i + 1}. {row.signal_type}: {str(row.title)[:80]}" for i, row in alert_results.head(int(rows)).iterrows()]
            selected_alert = st.selectbox("Track alert result", alert_options, key="search_track_alert")
            alert_row = alert_results.iloc[alert_options.index(selected_alert)]
            alert_actions = st.columns([1, 1, 2])
            if alert_actions[0].button("Track alert market", key="search_track_alert_market"):
                item = {
                    "platform": str(alert_row.get("platform", "")),
                    "market_key": str(alert_row.get("market_key", "") or alert_row.get("title", "")),
                    "title": str(alert_row.get("title", "")),
                    "url": str(alert_row.get("url", "")),
                }
                if item["market_key"] not in [w["market_key"] for w in st.session_state.watchlist]:
                    st.session_state.watchlist.append(item)
                    save_local_list("watchlist.json", st.session_state.watchlist)
                    st.success("Alert market added to watchlist.")
            if alert_actions[1].button("Track alert wallet", key="search_track_alert_wallet"):
                wallet_value = str(alert_row.get("wallet", ""))
                if re.fullmatch(r"0x[a-fA-F0-9]{40}", wallet_value) and wallet_value.lower() not in [w.lower() for w in st.session_state.followed_wallets]:
                    st.session_state.followed_wallets.append(wallet_value)
                    save_local_list("followed_wallets.json", st.session_state.followed_wallets)
                    st.success("Alert wallet added to tracked wallets.")
    with tab_tracked:
        t1, t2 = st.columns([1, 1])
        with t1:
            st.markdown("### Watched markets")
            if tracked_markets.empty:
                draw_empty("No watched markets match.")
            else:
                st.dataframe(tracked_markets, width="stretch", height=330, column_config={"url": st.column_config.LinkColumn("URL")})
        with t2:
            st.markdown("### Watched wallets")
            if tracked_wallets.empty:
                draw_empty("No watched wallets match.")
            else:
                st.dataframe(tracked_wallets, width="stretch", height=330)


def render_related_markets(row: pd.Series, market_universe: pd.DataFrame | None = None) -> None:
    if market_universe is None or market_universe.empty:
        return
    current_key = str(row.get("market_key", "") or "")
    related = related_market_group(market_universe, row, include_current=True, limit=16)
    if len(related) <= 1:
        return
    closed_related = pd.DataFrame()
    if row.get("platform") == "Polymarket":
        closed = safe_load("Resolved related markets", load_closed_markets, 250, default=pd.DataFrame())
        if not closed.empty:
            closed_related = related_market_group(closed, row, include_current=False, limit=40)

    st.markdown("#### Related markets")
    r1, r2, r3 = st.columns(3)
    active_count = int((~related.get("closed", pd.Series(False, index=related.index)).fillna(False).astype(bool)).sum())
    r1.metric("Related active", f"{active_count:,}")
    r2.metric("Resolved siblings", f"{len(closed_related):,}")
    r3.metric("Group volume", money(numeric_col(related, "activity_volume").sum()))

    preview = related.copy()
    preview["selected"] = preview["market_key"].astype(str).eq(current_key)
    preview["price"] = numeric_col(preview, "yes_price")
    preview["end"] = pd.to_datetime(preview.get("end_time"), utc=True, errors="coerce").dt.strftime("%Y-%m-%d").fillna("-")
    preview["status"] = preview.get("closed", pd.Series(False, index=preview.index)).fillna(False).map(lambda value: "Resolved" if bool(value) else "Active")
    for chunk_start in range(0, len(preview.head(12)), 4):
        cols = st.columns(4)
        for col, (_, item) in zip(cols, preview.head(12).iloc[chunk_start : chunk_start + 4].iterrows()):
            with col:
                with st.container(border=True):
                    st.caption(str(item.get("status", "Active")))
                    st.markdown(f"**{str(item.get('title', '-'))[:75]}**")
                    st.metric("Yes", cents(item.get("price")), signed_cents(item.get("change_1d", 0.0)))
                    st.caption(f"End {item.get('end', '-')} | Vol {money(item.get('activity_volume', 0.0))}")
                    if bool(item.get("selected", False)):
                        st.button("Current", key=f"related_current_{item.get('market_key')}", disabled=True, width="stretch")
                    elif st.button("Inspect", key=f"related_inspect_{item.get('market_key')}", width="stretch"):
                        st.session_state["markets_inspect_market_key"] = str(item.get("market_key", ""))
                        st.rerun()
                    if item.get("url"):
                        st.link_button("Open venue", str(item.get("url")), width="stretch")

    with st.expander("Related market table", expanded=False):
        table = clean_table(
            preview,
            ["selected", "status", "title", "yes_price", "no_price", "spread", "activity_volume", "volume_1h", "liquidity", "end", "url", "market_key"],
        )
        st.dataframe(
            table,
            width="stretch",
            height=260,
            column_config={
                "yes_price": st.column_config.NumberColumn("Yes", format="%.3f"),
                "no_price": st.column_config.NumberColumn("No", format="%.3f"),
                "spread": st.column_config.NumberColumn(format="%.3f"),
                "activity_volume": st.column_config.NumberColumn("Volume", format="$%.0f"),
                "volume_1h": st.column_config.NumberColumn("Vol 1h", format="$%.0f"),
                "liquidity": st.column_config.NumberColumn(format="$%.0f"),
                "url": st.column_config.LinkColumn("URL"),
            },
        )
    if not closed_related.empty:
        with st.expander("Resolved siblings", expanded=False):
            closed_display = closed_related.copy()
            closed_display["closed_date"] = pd.to_datetime(closed_display.get("closed_time"), utc=True, errors="coerce").dt.strftime("%Y-%m-%d").fillna("-")
            st.dataframe(
                clean_table(closed_display, ["closed_date", "title", "resolved_outcome", "final_yes_price", "volume", "url"]),
                width="stretch",
                height=220,
                column_config={
                    "final_yes_price": st.column_config.NumberColumn("Final Yes", format="%.3f"),
                    "volume": st.column_config.NumberColumn(format="$%.0f"),
                    "url": st.column_config.LinkColumn("URL"),
                },
            )


def render_market_series_strip(row: pd.Series, market_universe: pd.DataFrame | None = None) -> None:
    """Render a PredictParity-style quick selector for sibling contracts."""

    if market_universe is None or market_universe.empty:
        return
    current_key = str(row.get("market_key", "") or "")
    related = related_market_group(market_universe, row, include_current=True, limit=8)
    if len(related) <= 1:
        return

    closed_related = pd.DataFrame()
    if row.get("platform") == "Polymarket":
        closed = safe_load("Resolved related markets", load_closed_markets, 250, default=pd.DataFrame())
        if not closed.empty:
            closed_related = related_market_group(closed, row, include_current=False, limit=40)

    strip_key = re.sub(r"[^a-zA-Z0-9]+", "_", current_key).strip("_")[:48] or "market"
    show_resolved_key = f"show_resolved_series_{strip_key}"
    st.markdown("#### Related contracts")
    related_preview = related.head(6).copy()
    cols = st.columns(len(related_preview) + (1 if not closed_related.empty else 0))
    for idx, (_, item) in enumerate(related_preview.iterrows()):
        item_key = str(item.get("market_key", "") or "")
        end_time = pd.to_datetime(item.get("end_time"), utc=True, errors="coerce")
        if pd.notna(end_time):
            label = end_time.strftime("%b %d").replace(" 0", " ")
        else:
            label = str(item.get("title", "Contract"))[:18]
        price_label = cents(item.get("yes_price"))
        button_label = f"{label} {price_label}"
        if item_key == current_key:
            cols[idx].button(f"[ {button_label} ]", key=f"series_current_{strip_key}_{idx}", disabled=True, width="stretch")
        elif cols[idx].button(button_label, key=f"series_open_{strip_key}_{idx}", width="stretch"):
            st.session_state["markets_inspect_market_key"] = item_key
            st.rerun()
    if not closed_related.empty:
        resolved_col = cols[-1]
        if resolved_col.button(f"+{len(closed_related)} resolved", key=f"series_resolved_{strip_key}", width="stretch"):
            st.session_state[show_resolved_key] = not bool(st.session_state.get(show_resolved_key, False))
            st.rerun()
    if st.session_state.get(show_resolved_key, False) and not closed_related.empty:
        closed_display = closed_related.copy()
        closed_display["closed_date"] = pd.to_datetime(closed_display.get("closed_time"), utc=True, errors="coerce").dt.strftime("%Y-%m-%d").fillna("-")
        st.dataframe(
            clean_table(closed_display, ["closed_date", "title", "resolved_outcome", "final_yes_price", "volume", "url"]),
            width="stretch",
            height=220,
            column_config={
                "final_yes_price": st.column_config.NumberColumn("Final Yes", format="%.3f"),
                "volume": st.column_config.NumberColumn(format="$%.0f"),
                "url": st.column_config.LinkColumn("URL"),
            },
        )


def render_market_detail(row: pd.Series, market_universe: pd.DataFrame | None = None) -> None:
    st.markdown("### Market detail")
    market_key = str(row.get("market_key") or row.get("ticker") or row.get("title") or "")
    header_metrics = md.market_detail_header_metrics(row)
    top_cols = st.columns(4)
    top_cols[0].metric("Venue", header_metrics["venue"])
    top_cols[1].metric("Yes price", cents(header_metrics["yes_price"]))
    top_cols[2].metric("No price", cents(header_metrics["no_price"]))
    top_cols[3].metric("End", header_metrics["end_label"])
    flow_cols = st.columns(4)
    flow_cols[0].metric("1h volume", money(header_metrics["volume_1h"]))
    flow_cols[1].metric("24h volume", money(header_metrics["volume_24h"]))
    flow_cols[2].metric("Liquidity / OI", money(header_metrics["liquidity_or_oi"]))
    apy_value = header_metrics.get("apy")
    flow_cols[3].metric(header_metrics["apy_label"], pct(apy_value) if apy_value is not None else "-")
    st.markdown(f"**{row.get('title', '-')}**")
    yes_strength = max(0.0, min(float(row.get("yes_price") or 0.0), 1.0))
    no_strength = max(0.0, min(float(row.get("no_price") if row.get("no_price") is not None else 1 - yes_strength), 1.0))
    st.markdown("#### Market Strength")
    strength_cols = st.columns([1, 4, 1, 4])
    strength_cols[0].metric("Yes", pct(yes_strength))
    strength_cols[1].progress(yes_strength)
    strength_cols[2].metric("No", pct(no_strength))
    strength_cols[3].progress(no_strength)
    if row.get("description"):
        st.caption(str(row.get("description"))[:420])
    saved_keys = {str(item.get("market_key", "")).strip() for item in st.session_state.watchlist}
    action_cols = st.columns([1, 1, 1, 3])
    if market_key and market_key in saved_keys:
        if action_cols[0].button("Remove saved market", key=f"detail_unsave_{market_key}", width="stretch"):
            st.session_state.watchlist, removed = md.remove_watchlist_market(st.session_state.watchlist, market_key)
            if removed:
                save_local_list("watchlist.json", st.session_state.watchlist)
                st.toast("Market removed from Saved.")
            st.rerun()
    else:
        if action_cols[0].button("Save market", key=f"detail_save_{market_key}", width="stretch", disabled=not bool(market_key)):
            st.session_state.watchlist, changed = md.upsert_watchlist_market(st.session_state.watchlist, row.to_dict())
            if changed:
                save_local_list("watchlist.json", st.session_state.watchlist)
                st.toast("Market added to Saved.")
            st.rerun()
    action_cols[1].link_button("Open venue market", row.get("url", "https://polymarket.com"), width="stretch")
    render_market_series_strip(row, market_universe)
    render_related_markets(row, market_universe)
    with st.expander("Market rules", expanded=False):
        st.write(str(row.get("description") or "No market rules returned by the public API."))

    if row.get("platform") == "Polymarket":
        yes_asset = str(row.get("yes_token_id") or "")
        no_asset = str(row.get("no_token_id") or "")
        selected_outcome = st.radio("Outcome", ["Yes", "No"], horizontal=True, key=f"detail_outcome_{row.get('market_key')}")
        token = yes_asset if selected_outcome == "Yes" else no_asset
        selected_price = row.get("yes_price") if selected_outcome == "Yes" else row.get("no_price")
        d1, d2, d3 = st.columns(3)
        d1.metric("Selected outcome", selected_outcome)
        d2.metric("Outcome price", cents(selected_price))
        d3.metric("Token", short_addr(token, width=7))
        render_market_quick_trade_bar(row, market_key, selected_outcome)
        tab_history, tab_book, tab_holders, tab_top, tab_recent, tab_trade, tab_news, tab_comments = st.tabs(
            ["Price", "Orderbook", "Holders", "Top Traders", "Recent Trades", "Trade", "News", "Comments"]
        )
        recent = safe_load("Polymarket market trades", load_polymarket_trades, 250, 0.0, None, row.get("market_key"))
        with tab_history:
            h1, h2 = st.columns([1, 1.6])
            chart_type = h1.radio("Chart", ["Line", "Candlestick"], horizontal=True, key=f"detail_chart_{row.get('market_key')}_{selected_outcome}")
            window = h2.radio("Window", ["1hr", "6hr", "1d", "1w", "1mo", "All"], horizontal=True, key=f"detail_window_{row.get('market_key')}_{selected_outcome}")
            days, since_delta, interval, candle_rule = _history_window_config(window)
            hist = safe_load("Polymarket price history", load_price_history, token, days, interval)
            if not hist.empty and since_delta is not None:
                hist = hist[pd.to_datetime(hist["time"], utc=True, errors="coerce") >= pd.Timestamp.utcnow() - since_delta]
            render_price_history_chart(hist, chart_type, candle_rule, label=f"{selected_outcome} price")
        with tab_book:
            book_outcome = st.radio(
                "Orderbook outcome",
                ["Yes", "No"],
                index=0 if selected_outcome == "Yes" else 1,
                horizontal=True,
                key=f"book_outcome_{row.get('market_key')}",
            )
            book_token = yes_asset if book_outcome == "Yes" else no_asset
            bids, asks = safe_load("Polymarket order book", load_polymarket_book, book_token, default=(pd.DataFrame(), pd.DataFrame()))
            summary = orderbook_summary(bids, asks)
            st.caption(f"{book_outcome} token orderbook")
            b1, b2, b3, b4, b5, b6 = st.columns(6)
            b1.metric("Best bid", cents(summary["best_bid"]) if summary["best_bid"] is not None else "-")
            b2.metric("Best ask", cents(summary["best_ask"]) if summary["best_ask"] is not None else "-")
            b3.metric("Spread", cents(summary["spread"]) if summary["spread"] is not None else "-")
            b4.metric("Mid", cents(summary["midpoint"]) if summary["midpoint"] is not None else "-")
            b5.metric("Bid depth", money(summary["bid_depth"] or 0.0))
            b6.metric("Ask depth", money(summary["ask_depth"] or 0.0))
            ladder = orderbook_ladder(bids, asks, depth=40)
            ladder_view = st.radio("Orderbook view", ["Parity ladder", "Raw bid/ask"], horizontal=True, key=f"book_view_{row.get('market_key')}")
            if ladder_view == "Parity ladder":
                if ladder.empty:
                    draw_empty("No public CLOB orderbook levels returned for this outcome.")
                else:
                    st.dataframe(
                        clean_table(ladder, ["side", "price", "shares", "total_shares", "total"]),
                        width="stretch",
                        height=430,
                        column_config={
                            "side": st.column_config.TextColumn("Side"),
                            "price": st.column_config.NumberColumn("Price", format="%.4f"),
                            "shares": st.column_config.NumberColumn("Shares", format="%.2f"),
                            "total_shares": st.column_config.NumberColumn("Cum shares", format="%.2f"),
                            "total": st.column_config.NumberColumn("Total", format="$%.2f"),
                        },
                    )
            else:
                book_cols = st.columns(2)
                with book_cols[0]:
                    st.markdown("**Bids**")
                    st.dataframe(bids.head(30), width="stretch", height=330)
                with book_cols[1]:
                    st.markdown("**Asks**")
                    st.dataframe(asks.head(30), width="stretch", height=330)
        with tab_holders:
            holders = safe_load("Polymarket holders", load_holders, row.get("market_key"))
            if holders.empty:
                draw_empty("No holder data returned for this market.")
            else:
                holders = holders.copy()
                holders["outcome"] = holders.apply(lambda item: _holder_outcome_label(item, yes_asset, no_asset), axis=1)
                holders = enrich_market_holders(holders, recent, row.get("yes_price"), row.get("no_price"))
                outcome_filter = st.radio("Holder side", ["Selected", "Yes", "No", "All"], horizontal=True, key=f"holders_side_{row.get('market_key')}")
                filtered_holders = holders
                if outcome_filter == "Selected":
                    filtered_holders = holders[holders["outcome"].eq(selected_outcome)]
                elif outcome_filter in {"Yes", "No"}:
                    filtered_holders = holders[holders["outcome"].eq(outcome_filter)]
                total_all = numeric_col(holders, "value").sum()
                total = numeric_col(filtered_holders, "value").sum()
                top_10 = numeric_col(filtered_holders.head(10), "value").sum()
                by_side = holders.groupby("outcome", as_index=False)["value"].sum().sort_values("value", ascending=False)
                strength = holder_strength_summary(holders)
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Displayed holders", f"{len(filtered_holders):,}")
                m2.metric("Displayed value", money(total))
                m3.metric("Top 10 share", pct(top_10 / total if total else 0))
                m4.metric("Selected side share", pct(total / total_all if total_all else 0))
                st.markdown("### Market Strength")
                strength_cols = st.columns(4)
                strength_cols[0].metric("Dominant side", str(strength["dominant_side"]), pct(strength["dominant_share"]))
                strength_cols[1].metric("Yes holder value", money(strength["yes_value"]), pct(strength["yes_share"]))
                strength_cols[2].metric("No holder value", money(strength["no_value"]), pct(strength["no_share"]))
                strength_cols[3].metric("Holder skew", pct(strength["skew"]))
                st.progress(min(max(float(strength["dominant_share"]), 0.0), 1.0), text=f"{strength['dominant_side']} holder value share")
                if not by_side.empty:
                    fig = px.bar(
                        by_side,
                        x="outcome",
                        y="value",
                        color="outcome",
                        template="plotly_dark",
                        color_discrete_map={"Yes": ACCENT, "No": RED, "Unknown": MUTED},
                    )
                    fig.update_layout(height=220, margin=dict(l=10, r=10, t=15, b=10), paper_bgcolor=BG, plot_bgcolor=BG, showlegend=False)
                    st.plotly_chart(fig, width="stretch", config=plot_config())
                st.markdown("### Holder split")
                holder_panels = md.holder_side_panels(holders, top_n=25)
                split_cols = st.columns(2)
                for split_col, side_name in zip(split_cols, ["Yes", "No"]):
                    side_frame = holder_panels.get(side_name, pd.DataFrame()).copy()
                    with split_col:
                        st.markdown(f"**{side_name}**")
                        if side_frame.empty:
                            draw_empty(f"No {side_name} holders returned.")
                        else:
                            side_shares = float(numeric_col(side_frame, "shares").sum())
                            side_value = float(numeric_col(side_frame, "value").sum())
                            sm1, sm2, sm3 = st.columns(3)
                            sm1.metric("Holders", f"{len(side_frame):,}")
                            sm2.metric("Shares", f"{side_shares:,.1f}")
                            sm3.metric("Value", money(side_value))
                            side_display = side_frame.copy()
                            side_display["wallet"] = side_display["wallet"].astype(str).map(short_addr)
                            st.dataframe(
                                clean_table(side_display, ["trader", "shares", "activity", "value", "wallet", "verified"]).head(25),
                                width="stretch",
                                height=300,
                                column_config={
                                    "trader": st.column_config.TextColumn("Holder", width="medium"),
                                    "shares": st.column_config.NumberColumn("Shares", format="%.1f"),
                                    "activity": st.column_config.TextColumn("Activity"),
                                    "value": st.column_config.NumberColumn("Value", format="$%.2f"),
                                },
                            )
                bubble_cols = st.columns([1, 1, 3])
                show_bubble = bubble_cols[0].toggle("Bubble chart", value=False, key=f"holder_bubble_{row.get('market_key')}")
                if bubble_cols[1].button("Open bubble chart", key=f"open_holder_bubble_{row.get('market_key')}", width="stretch"):
                    render_holder_bubble_dialog(filtered_holders, str(row.get("title", "")))
                display = filtered_holders.copy()
                if show_bubble and not display.empty:
                    render_holder_bubble_chart(display, height=330)
                if not filtered_holders.empty:
                    st.download_button("Export holders CSV", filtered_holders.to_csv(index=False).encode("utf-8"), file_name="market_holders.csv", mime="text/csv")
                    holder_wallets = filtered_holders[filtered_holders["wallet"].astype(str).str.match(r"^0x[a-fA-F0-9]{40}$", na=False)] if "wallet" in filtered_holders else pd.DataFrame()
                    if not holder_wallets.empty:
                        holder_options = [
                            f"{i + 1}. {row.get('trader', '') or short_addr(str(row.get('wallet', '')))} | {row.get('outcome', '-')} | {money(row.get('value', 0.0))}"
                            for i, row in holder_wallets.head(80).iterrows()
                        ]
                        selected_holder = st.selectbox("Holder wallet action", holder_options, key=f"holder_action_{row.get('market_key')}")
                        holder_row = holder_wallets.iloc[holder_options.index(selected_holder)]
                        holder_cols = st.columns([1, 1, 3])
                        holder_wallet = str(holder_row.get("wallet", ""))
                        if holder_cols[0].button("Track holder wallet", key=f"track_holder_wallet_{row.get('market_key')}", width="stretch"):
                            if holder_wallet.lower() not in [w.lower() for w in st.session_state.followed_wallets]:
                                st.session_state.followed_wallets.append(holder_wallet)
                                save_local_list("followed_wallets.json", st.session_state.followed_wallets)
                                st.success("Holder wallet added to tracked wallets.")
                        holder_cols[1].link_button("Open holder", f"https://polymarket.com/profile/{holder_wallet}", width="stretch")
                        show_holder_wallet = st.toggle("Load holder wallet detail", value=False, key=f"load_holder_wallet_{row.get('market_key')}")
                        if show_holder_wallet:
                            render_wallet(holder_wallet)
                display["wallet"] = display["wallet"].astype(str).map(short_addr)
                st.dataframe(
                    clean_table(
                        display,
                        ["trader", "outcome", "avg_price_est", "shares", "current_price", "value", "unrealized_pnl_est", "pnl_pct_est", "activity", "activity_time", "wallet", "verified"],
                    ).head(80),
                    width="stretch",
                    height=430,
                    column_config={
                        "avg_price_est": st.column_config.NumberColumn("Avg", format="%.4f"),
                        "shares": st.column_config.NumberColumn("Shares", format="%.2f"),
                        "current_price": st.column_config.NumberColumn("Price", format="%.4f"),
                        "value": st.column_config.NumberColumn("Value", format="$%.2f"),
                        "unrealized_pnl_est": st.column_config.NumberColumn("U PnL", format="$%.2f"),
                        "pnl_pct_est": st.column_config.NumberColumn("U PnL %", format="%.2%"),
                    },
                )
        with tab_top:
            status_label = st.radio("Top trader status", ["All", "Active", "Closed"], horizontal=True, key=f"top_trader_status_{row.get('market_key')}")
            sort_label = st.selectbox(
                "Sort top traders",
                ["Total PnL", "Unrealized PnL", "Realized PnL", "Shares"],
                key=f"top_trader_sort_{row.get('market_key')}",
            )
            status_map = {"All": "ALL", "Active": "OPEN", "Closed": "CLOSED"}
            sort_map = {"Total PnL": "TOTAL_PNL", "Unrealized PnL": "CASH_PNL", "Realized PnL": "REALIZED_PNL", "Shares": "TOKENS"}
            market_positions = safe_load(
                "Market top-trader positions",
                load_market_positions,
                str(row.get("market_key", "")),
                status_map[status_label],
                sort_map[sort_label],
                100,
                default=pd.DataFrame(),
            )
            if market_positions.empty:
                draw_empty("No Polymarket market-position leaderboard returned for this market.")
            else:
                pnl = numeric_col(market_positions, "total_pnl")
                current_value = numeric_col(market_positions, "current_value")
                active_rows = int(market_positions["status"].eq("Active").sum()) if "status" in market_positions else 0
                p1, p2, p3, p4 = st.columns(4)
                p1.metric("Displayed traders", f"{len(market_positions):,}")
                p2.metric("Positive PnL", f"{int((pnl > 0).sum()):,}")
                p3.metric("Displayed PnL", money(float(pnl.sum())))
                p4.metric("Active value", money(float(current_value.sum())), f"{active_rows:,} active")
                st.download_button(
                    "Export market position leaderboard CSV",
                    market_positions.to_csv(index=False).encode("utf-8"),
                    file_name="market_position_leaderboard.csv",
                    mime="text/csv",
                )
                side_cols = st.columns(2)
                for side_name, side_col in zip(["Yes", "No"], side_cols):
                    side_positions = market_positions[market_positions["outcome"].astype(str).str.casefold().eq(side_name.casefold())].copy()
                    with side_col:
                        st.markdown(f"**{side_name}**")
                        if side_positions.empty:
                            draw_empty(f"No {side_name} trader positions returned.")
                        else:
                            side_display = side_positions.copy()
                            side_display["wallet"] = side_display["wallet"].astype(str).map(short_addr)
                            st.dataframe(
                                clean_table(
                                    side_display,
                                    ["trader", "avg_price", "size", "total_pnl", "cash_pnl", "realized_pnl", "current_value", "status", "wallet", "verified"],
                                ).head(50),
                                width="stretch",
                                height=360,
                                column_config={
                                    "avg_price": st.column_config.NumberColumn("Avg", format="%.4f"),
                                    "size": st.column_config.NumberColumn("Shares", format="%.0f"),
                                    "total_pnl": st.column_config.NumberColumn("PnL", format="$%.0f"),
                                    "cash_pnl": st.column_config.NumberColumn("U PnL", format="$%.0f"),
                                    "realized_pnl": st.column_config.NumberColumn("R PnL", format="$%.0f"),
                                    "current_value": st.column_config.NumberColumn("Value", format="$%.0f"),
                                },
                            )
                position_wallets = (
                    market_positions[market_positions["wallet"].astype(str).str.match(r"^0x[a-fA-F0-9]{40}$", na=False)]
                    if "wallet" in market_positions
                    else pd.DataFrame()
                )
                if not position_wallets.empty:
                    position_options = [
                        f"{idx + 1}. {pos.get('trader', '') or short_addr(str(pos.get('wallet', '')))} | {pos.get('outcome', '-')} | {money(pos.get('total_pnl', 0.0))} PnL"
                        for idx, pos in position_wallets.head(80).iterrows()
                    ]
                    selected_position = st.selectbox("Market-position wallet action", position_options, key=f"position_trader_action_{row.get('market_key')}")
                    position_row = position_wallets.iloc[position_options.index(selected_position)]
                    position_wallet = str(position_row.get("wallet", ""))
                    position_cols = st.columns([1, 1, 3])
                    if position_cols[0].button("Track position wallet", key=f"track_position_trader_{row.get('market_key')}", width="stretch"):
                        if position_wallet.lower() not in [w.lower() for w in st.session_state.followed_wallets]:
                            st.session_state.followed_wallets.append(position_wallet)
                            save_local_list("followed_wallets.json", st.session_state.followed_wallets)
                            st.success("Market-position wallet added to tracked wallets.")
                    position_cols[1].link_button("Open position trader", f"https://polymarket.com/profile/{position_wallet}", width="stretch")
                    show_position_wallet = st.toggle("Load position wallet detail", value=False, key=f"load_position_wallet_{row.get('market_key')}")
                    if show_position_wallet:
                        render_wallet(position_wallet)

            st.markdown("### Recent tape leaders")
            top_traders = market_top_traders(recent)
            if top_traders.empty:
                draw_empty("No market-specific trader tape returned.")
            else:
                st.download_button("Export market top traders CSV", top_traders.to_csv(index=False).encode("utf-8"), file_name="market_top_traders.csv", mime="text/csv")
                display = top_traders.copy()
                display["wallet"] = display["wallet"].astype(str).map(short_addr)
                st.dataframe(
                    clean_table(display, ["trader", "wallet", "trades", "notional", "avg_trade", "largest_trade", "buy_notional", "sell_notional", "outcomes", "latest_trade"]),
                    width="stretch",
                    height=430,
                    column_config={
                        "notional": st.column_config.NumberColumn(format="$%.0f"),
                        "avg_trade": st.column_config.NumberColumn(format="$%.0f"),
                        "largest_trade": st.column_config.NumberColumn(format="$%.0f"),
                        "buy_notional": st.column_config.NumberColumn(format="$%.0f"),
                        "sell_notional": st.column_config.NumberColumn(format="$%.0f"),
                    },
                )
                top_wallets = top_traders[top_traders["wallet"].astype(str).str.match(r"^0x[a-fA-F0-9]{40}$", na=False)] if "wallet" in top_traders else pd.DataFrame()
                if not top_wallets.empty:
                    top_options = [
                        f"{i + 1}. {row.get('trader', '') or short_addr(str(row.get('wallet', '')))} | {money(row.get('notional', 0.0))} | {int(row.get('trades', 0))} trades"
                        for i, row in top_wallets.head(80).iterrows()
                    ]
                    selected_top = st.selectbox("Top trader wallet action", top_options, key=f"top_trader_action_{row.get('market_key')}")
                    top_row = top_wallets.iloc[top_options.index(selected_top)]
                    top_wallet = str(top_row.get("wallet", ""))
                    top_cols = st.columns([1, 1, 3])
                    if top_cols[0].button("Track top trader wallet", key=f"track_top_trader_{row.get('market_key')}", width="stretch"):
                        if top_wallet.lower() not in [w.lower() for w in st.session_state.followed_wallets]:
                            st.session_state.followed_wallets.append(top_wallet)
                            save_local_list("followed_wallets.json", st.session_state.followed_wallets)
                            st.success("Top trader wallet added to tracked wallets.")
                    top_cols[1].link_button("Open trader", f"https://polymarket.com/profile/{top_wallet}", width="stretch")
                    show_top_wallet = st.toggle("Load top trader wallet detail", value=False, key=f"load_top_wallet_{row.get('market_key')}")
                    if show_top_wallet:
                        render_wallet(top_wallet)
        with tab_recent:
            if recent.empty:
                draw_empty("No recent market trades returned.")
            else:
                recent_actions = md.prepare_recent_trade_actions(recent, limit=120)
                st.download_button("Export market recent trades CSV", recent.to_csv(index=False).encode("utf-8"), file_name="market_recent_trades.csv", mime="text/csv")
                show_exact_time = st.toggle("Show exact timestamps", value=False, key=f"recent_exact_time_{row.get('market_key')}")
                time_col = "time_utc" if show_exact_time else "time"
                display = clean_table(
                    recent_actions,
                    [
                        time_col,
                        "age_min",
                        "trader_badge",
                        "wallet",
                        "side",
                        "outcome",
                        "direction",
                        "directional_share",
                        "price",
                        "size",
                        "notional",
                        "wallet_market_trades",
                        "wallet_market_notional",
                        "transaction_hash",
                        "tx_url",
                        "url",
                    ],
                )
                if "wallet" in display:
                    display["wallet"] = display["wallet"].astype(str).map(short_addr)
                if "transaction_hash" in display:
                    display["transaction_hash"] = display["transaction_hash"].astype(str).map(short_addr)
                st.dataframe(
                    display,
                    width="stretch",
                    height=430,
                    column_config={
                        "price": st.column_config.NumberColumn(format="%.4f"),
                        "size": st.column_config.NumberColumn(format="%.2f"),
                        "notional": st.column_config.NumberColumn(format="$%.2f"),
                        "age_min": st.column_config.NumberColumn("Age min", format="%.1f"),
                        "trader_badge": st.column_config.TextColumn("Trader"),
                        "directional_share": st.column_config.NumberColumn("Dir share", format="%.0%"),
                        "wallet_market_trades": st.column_config.NumberColumn("Wallet trades", format="%d"),
                        "wallet_market_notional": st.column_config.NumberColumn("Wallet flow", format="$%.0f"),
                        "tx_url": st.column_config.LinkColumn("TX"),
                        "url": st.column_config.LinkColumn("URL"),
                    },
                )
                actionable_trades = recent_actions[recent_actions["action_label"].astype(str).str.len() > 0].copy()
                if not actionable_trades.empty:
                    st.markdown("### Recent trade inspector")
                    trade_options = actionable_trades["action_label"].tolist()
                    selected_trade = st.selectbox("Recent trade action", trade_options, key=f"recent_trade_action_{row.get('market_key')}")
                    recent_row = actionable_trades.iloc[trade_options.index(selected_trade)]
                    r1, r2, r3, r4, r5 = st.columns(5)
                    r1.metric("Trader", str(recent_row.get("trader_display", "-"))[:24])
                    r2.metric("Direction", str(recent_row.get("direction", "-")), pct(recent_row.get("directional_share", 0.0)))
                    r3.metric("Price", cents(recent_row.get("price")))
                    r4.metric("Shares", f"{float(recent_row.get('size', 0.0) or 0.0):,.2f}")
                    r5.metric("Wallet flow", money(recent_row.get("wallet_market_notional", recent_row.get("notional", 0.0))), f"{int(recent_row.get('wallet_market_trades', 0) or 0)} trades")
                    wallet_value = str(recent_row.get("wallet", ""))
                    tx_value = str(recent_row.get("transaction_hash", ""))
                    recent_cols = st.columns([1, 1, 1, 1, 2])
                    if recent_cols[0].button(
                        "Track trader",
                        key=f"track_recent_trade_wallet_{row.get('market_key')}",
                        width="stretch",
                        disabled=not bool(recent_row.get("valid_wallet")),
                    ):
                        if wallet_value.lower() not in [w.lower() for w in st.session_state.followed_wallets]:
                            st.session_state.followed_wallets.append(wallet_value)
                            save_local_list("followed_wallets.json", st.session_state.followed_wallets)
                            st.success("Recent-trade wallet added to tracked wallets.")
                        else:
                            st.info("Recent-trade wallet is already tracked.")
                    wallet_url = str(recent_row.get("wallet_url", ""))
                    tx_url = str(recent_row.get("tx_url", ""))
                    market_url = str(recent_row.get("url", ""))
                    if wallet_url:
                        recent_cols[1].link_button("Open trader", wallet_url, width="stretch")
                    if tx_url:
                        recent_cols[2].link_button("Open tx", tx_url, width="stretch")
                    if market_url:
                        recent_cols[3].link_button("Open market", market_url, width="stretch")
                    if recent_cols[4].button("Paper trade this outcome", key=f"paper_recent_trade_{row.get('market_key')}", width="stretch"):
                        trade_outcome = str(recent_row.get("outcome", ""))
                        trade_price = float(recent_row.get("price", 0.0) or 0.0)
                        st.session_state[f"recent_trade_ticket_{market_key}"] = {
                            "platform": str(row.get("platform", "")),
                            "market_key": market_key,
                            "title": str(row.get("title", "")),
                            "url": str(row.get("url", "")),
                            "yes_price": trade_price if trade_outcome.lower() == "yes" else float(row.get("yes_price", 0.0) or 0.0),
                            "no_price": trade_price if trade_outcome.lower() == "no" else float(row.get("no_price", 0.0) or 0.0),
                        }
                        st.info("Paper ticket staged below. Adjust outcome and amount before submitting.")
                    ticket_key = f"recent_trade_ticket_{market_key}"
                    if ticket_key in st.session_state:
                        render_research_trade_ticket(pd.Series(st.session_state[ticket_key]), key_prefix="recent_trade_ticket")
                    show_recent_wallet = st.toggle(
                        "Load recent trader wallet detail",
                        value=False,
                        key=f"load_recent_trade_wallet_{row.get('market_key')}",
                        disabled=not bool(recent_row.get("valid_wallet")),
                    )
                    if show_recent_wallet and re.fullmatch(r"0x[a-fA-F0-9]{40}", wallet_value):
                        render_wallet(wallet_value)
        with tab_trade:
            render_research_trade_ticket(row)
        with tab_news:
            render_market_news(str(row.get("title", "")), str(row.get("market_key", "")))
        with tab_comments:
            render_market_comments(str(row.get("market_key", "")), str(row.get("title", "")))
    else:
        ticker = row.get("ticker")
        render_market_quick_trade_bar(row, market_key, "Yes")
        tab_history, tab_book, tab_recent, tab_trade, tab_news, tab_comments = st.tabs(["Price", "Orderbook", "Recent Trades", "Trade", "News", "Comments"])
        recent = safe_load("Kalshi market trades", load_kalshi_trades, 150, ticker)
        with tab_history:
            days = st.slider("History window", 7, 180, 30, key=f"kalshi_history_{row.get('market_key')}")
            period = 1440 if days > 60 else 60
            candles = safe_load("Kalshi candlesticks", load_kalshi_candles, ticker, days, period)
            if candles.empty:
                draw_empty("No Kalshi candlesticks returned for this market.")
            else:
                fig = go.Figure(
                    data=[
                        go.Candlestick(
                            x=candles["time"],
                            open=candles["open"],
                            high=candles["high"],
                            low=candles["low"],
                            close=candles["close"],
                            increasing_line_color=ACCENT,
                            decreasing_line_color=RED,
                            name="Kalshi yes price",
                        )
                    ]
                )
                fig.update_layout(height=360, margin=dict(l=10, r=10, t=20, b=10), paper_bgcolor=BG, plot_bgcolor=BG, template="plotly_dark")
                st.plotly_chart(fig, width="stretch", config=plot_config())
        with tab_book:
            bids, asks = safe_load("Kalshi order book", load_kalshi_book, ticker, default=(pd.DataFrame(), pd.DataFrame()))
            book_cols = st.columns(2)
            with book_cols[0]:
                st.markdown("**Yes-side levels**")
                st.dataframe(bids.head(20), width="stretch", height=280)
            with book_cols[1]:
                st.markdown("**Yes asks derived from No bids**")
                st.dataframe(asks.head(20), width="stretch", height=280)
        with tab_recent:
            if recent.empty:
                draw_empty("No Kalshi recent trades returned.")
            else:
                st.dataframe(
                    clean_table(recent, ["time", "ticker", "side", "outcome", "price", "size", "notional", "url"]).head(120),
                    width="stretch",
                    height=430,
                    column_config={
                        "price": st.column_config.NumberColumn(format="%.4f"),
                        "size": st.column_config.NumberColumn(format="%.2f"),
                        "notional": st.column_config.NumberColumn(format="$%.2f"),
                        "url": st.column_config.LinkColumn("URL"),
                    },
                )
        with tab_trade:
            render_research_trade_ticket(row)
        with tab_news:
            render_market_news(str(row.get("title", "")), str(row.get("market_key", "")))
        with tab_comments:
            render_market_comments(str(row.get("market_key", "")), str(row.get("title", "")))


def page_markets() -> None:
    section_header("Markets", "Parity-style market scanner with saved views, quick filters, table/card/calendar modes, and full market drilldown.")
    pm, ks, combined = load_market_universe()
    if combined.empty:
        draw_empty("No market data returned.")
        return
    combined = add_market_filter_metrics(combined)
    market_category_col = "filter_category" if "filter_category" in combined else "category"
    requested_activity_key = str(st.session_state.get("markets_inspect_market_key", "") or "")
    activity_event_url = str(st.session_state.get("markets_activity_event_url", "") or "")
    if requested_activity_key and activity_event_url and "market_key" in combined and not combined["market_key"].astype(str).eq(requested_activity_key).any():
        event_markets = safe_load("Activity event markets", load_polymarket_event_markets, activity_event_url, default=pd.DataFrame())
        if not event_markets.empty:
            event_markets = add_market_filter_metrics(event_markets)
            combined = (
                pd.concat([event_markets, combined], ignore_index=True, sort=False)
                .drop_duplicates(subset=["market_key"], keep="first")
                .reset_index(drop=True)
            )

    categories = sorted(
        [str(item) for item in combined.get(market_category_col, pd.Series(dtype=str)).dropna().unique() if str(item)],
        key=lambda item: (md.market_category_label(item).casefold(), str(item).casefold()),
    )
    if "markets_search" not in st.session_state:
        for key, value in market_filter_defaults(categories, global_query).items():
            st.session_state[key] = value
    if st.session_state.pop("markets_reset_pending", False):
        reset_market_filter_widgets(categories)
    pending_market_view = st.session_state.pop("pending_market_filter_view", None)
    if isinstance(pending_market_view, dict):
        apply_market_filter_view_widgets(pending_market_view, categories)
    pending_market_clear = st.session_state.pop("markets_clear_pending", None)
    if isinstance(pending_market_clear, dict):
        for key, value in pending_market_clear.items():
            st.session_state[key] = value
    route_filter_params = query_param_snapshot(
        [
            "q",
            "query",
            "search",
            "view",
            "mode",
            "quick",
            "filter",
            "platform",
            "platforms",
            "venue",
            "venues",
            "status",
            "category",
            "categories",
            "includeCategory",
            "include",
            "excludeCategory",
            "excludeCategories",
            "exclude",
            "probMin",
            "priceMin",
            "minProbability",
            "probMax",
            "priceMax",
            "maxProbability",
            "volumeMin",
            "volMin",
            "minVolume",
            "volume1hMin",
            "vol1hMin",
            "minVolume1h",
            "liquidityMin",
            "liqMin",
            "minLiquidity",
            "spreadMax",
            "maxSpread",
            "endDays",
            "endingDays",
            "maxDaysToEnd",
            "ageDays",
            "maxAgeDays",
            "sort",
            "sortBy",
            "orderBy",
            "rows",
            "limit",
        ]
    )
    route_filter_signature = json.dumps(route_filter_params, sort_keys=True)
    route_filter_view = md.predictparity_market_filter_view(route_filter_params)
    if route_filter_view and st.session_state.get("markets_route_filter_signature") != route_filter_signature:
        apply_market_filter_view_widgets(route_filter_view, categories)
        st.session_state["markets_route_filter_signature"] = route_filter_signature
        st.session_state["markets_route_message"] = "Loaded market filters from URL."
    apply_market_route(combined)
    loaded_market_route_message = st.session_state.pop("markets_route_message", "")
    if loaded_market_route_message:
        st.info(loaded_market_route_message)

    search_cols = st.columns([2.4, 1.2, 1.2, 1, 1])
    local_query = search_cols[0].text_input("Search markets", placeholder="Search markets", key="markets_search")
    view_mode = search_cols[1].radio("View", ["Table", "Card", "Calendar"], horizontal=True, label_visibility="collapsed", key="markets_view_mode")
    quick_filter = search_cols[2].radio("Quick filter", ["Trending", "Saved", "My Positions", "Ending Soon", "New"], horizontal=True, label_visibility="collapsed", key="markets_quick_filter")
    save_market_clicked = search_cols[3].button("Save Filter", width="stretch")
    if search_cols[4].button("Reset Filters", width="stretch", help="Restore the default market scanner filters and rerun."):
        st.session_state["markets_reset_pending"] = True
        st.rerun()

    with st.expander("Filter", expanded=True):
        f1, f2 = st.columns(2)
        platform_filter = f1.multiselect("Platform", ["Polymarket", "Kalshi"], key="markets_platform_filter")
        status_filter = f2.radio("Status", ["Active", "All", "Closed"], horizontal=True, key="markets_status_filter")

        market_chip_source = combined.copy()
        if market_category_col in market_chip_source:
            market_chip_source["category"] = market_chip_source[market_category_col]
        category_counts = md.market_category_counts(market_chip_source)
        if category_counts:
            st.markdown("##### Category chips")
            show_all_categories = bool(st.session_state.get("markets_show_more_categories", False))
            category_chips = md.market_category_chip_options(
                market_chip_source,
                st.session_state.get("markets_include_categories", []),
                st.session_state.get("markets_exclude_categories", []),
                limit=10,
                show_all=show_all_categories,
            )
            for chunk_start in range(0, len(category_chips), 5):
                chip_cols = st.columns(5)
                for offset, option in enumerate(category_chips[chunk_start : chunk_start + 5]):
                    category = str(option["category"])
                    slug = re.sub(r"[^a-zA-Z0-9]+", "_", category).strip("_").lower()[:32] or f"cat_{chunk_start + offset}"
                    state = str(option["state"])
                    help_text = "Click to include this category."
                    if state == "include":
                        help_text = "Click to exclude this category."
                    elif state == "exclude":
                        help_text = "Click to clear this category filter."
                    if chip_cols[offset].button(
                        str(option["label"]),
                        key=f"markets_category_chip_{chunk_start + offset}_{slug}",
                        help=help_text,
                        width="stretch",
                    ):
                        include_next, exclude_next = md.cycle_market_category_filter(
                            st.session_state.get("markets_include_categories", []),
                            st.session_state.get("markets_exclude_categories", []),
                            category,
                        )
                        st.session_state["markets_include_categories"] = include_next
                        st.session_state["markets_exclude_categories"] = exclude_next
                        st.rerun()
            if len(category_counts) > 10:
                if st.button(
                    "Show fewer" if show_all_categories else "Show more",
                    key="markets_show_more_categories_button",
                ):
                    st.session_state["markets_show_more_categories"] = not show_all_categories
                    st.rerun()
            st.caption("Category chips cycle neutral -> include -> exclude -> neutral. The lists below remain editable.")

        f3, f4 = st.columns(2)
        include_categories = f3.multiselect("Include categories", categories, key="markets_include_categories", format_func=md.market_category_label)
        exclude_categories = f4.multiselect("Exclude categories", categories, key="markets_exclude_categories", format_func=md.market_category_label)

        f5, f6, f7, f8 = st.columns(4)
        prob_preset = f5.radio("Probability", ["All", "5-95%", "20-80%", ">80%", ">95%", ">99%", "Custom"], horizontal=True, key="markets_prob_preset")
        custom_prob = f5.slider("Custom probability range", 0, 100, disabled=prob_preset != "Custom", key="markets_custom_prob")
        spread_preset = f6.radio("Spread", ["All", "<3c", "<7c", "<10c", "Custom"], horizontal=True, key="markets_spread_preset")
        custom_spread = f6.number_input("Custom max spread (cents)", min_value=0.0, max_value=100.0, step=0.5, disabled=spread_preset != "Custom", key="markets_custom_spread")
        liquidity_preset = f7.radio("Liquidity", ["All", ">$1k", ">$10k", ">$100k", "Custom"], horizontal=True, key="markets_liquidity_preset")
        custom_liquidity = f7.number_input("Custom min liquidity", min_value=0, step=1_000, disabled=liquidity_preset != "Custom", key="markets_custom_liquidity")
        end_preset = f8.radio("End date", ["All", "Open", "Past due", "<1d", "<7d", "<30d", "Custom"], horizontal=True, key="markets_end_preset")
        custom_days = f8.number_input("Custom days to expiry", min_value=1, step=1, disabled=end_preset != "Custom", key="markets_custom_days")

        f9, f10, f11, f12 = st.columns(4)
        volume_1h_preset = f9.radio("Vol 1h", ["All", ">$1k", ">$10k", ">$100k", "Custom"], horizontal=True, key="markets_volume_1h_preset")
        custom_volume_1h = f9.number_input("Custom min 1h volume", min_value=0, step=1_000, disabled=volume_1h_preset != "Custom", key="markets_custom_volume_1h")
        volume_preset = f10.radio("24h volume", ["All", ">$1k", ">$10k", ">$100k", "Custom"], horizontal=True, key="markets_volume_preset")
        custom_volume = f10.number_input("Custom min 24h volume", min_value=0, step=1_000, disabled=volume_preset != "Custom", key="markets_custom_volume")
        age_preset = f11.radio("Market age", ["All", "<1d", "<7d", "<30d", ">365d", "Custom"], horizontal=True, key="markets_age_preset")
        custom_age_days = f11.number_input("Custom max market age (days)", min_value=1, step=1, disabled=age_preset != "Custom", key="markets_custom_age_days")
        sort_by = f12.selectbox(
            "Sort",
            [
                "activity_volume",
                "volume_24h",
                "volume_1h",
                "volume",
                "volume_delta_1h",
                "volume_delta_24h",
                "liquidity",
                "yes_price",
                "spread",
                "price_delta_1h",
                "price_delta_24h",
                "end_time",
                "created_at",
                "market_age_days",
            ],
            key="markets_sort_by",
        )
        limit_rows = f12.slider("Rows", 10, 250, step=10, key="markets_limit_rows")

        f13, f14, f15, f16 = st.columns(4)
        volume_delta_1h_preset = f13.radio("Vol delta 1h", ["All", ">25%", ">50%", ">75%", ">100%", "Custom"], horizontal=True, key="markets_volume_delta_1h_preset")
        custom_volume_delta_1h = f13.number_input("Custom min 1h volume delta (%)", min_value=0.0, step=5.0, disabled=volume_delta_1h_preset != "Custom", key="markets_custom_volume_delta_1h")
        volume_delta_24h_preset = f14.radio("Vol delta 24h", ["All", ">25%", ">50%", ">75%", ">100%", "Custom"], horizontal=True, key="markets_volume_delta_24h_preset")
        custom_volume_delta_24h = f14.number_input("Custom min 24h volume delta (%)", min_value=0.0, step=5.0, disabled=volume_delta_24h_preset != "Custom", key="markets_custom_volume_delta_24h")
        change_preset = f15.radio("Price delta 1h", ["All", ">1c", ">3c", ">5c", ">10c", "Custom"], horizontal=True, key="markets_change_preset")
        custom_change = f15.number_input("Custom min 1h price move (cents)", min_value=0.0, step=0.5, disabled=change_preset != "Custom", key="markets_custom_change")
        change_24h_preset = f16.radio("Price delta 24h", ["All", ">1c", ">3c", ">5c", ">10c", "Custom"], horizontal=True, key="markets_change_24h_preset")
        custom_change_24h = f16.number_input("Custom min 24h price move (cents)", min_value=0.0, step=0.5, disabled=change_24h_preset != "Custom", key="markets_custom_change_24h")

    saved_market_name = st.text_input("Saved view name", value=f"Markets {md.now_utc_label()}", key="saved_market_view_name")
    loaded_market_message = st.session_state.pop("market_view_loaded_message", "")
    if loaded_market_message:
        st.info(loaded_market_message)
    if st.session_state.saved_market_filters:
        load_cols = st.columns([2, 1, 1])
        saved_labels = [
            f"{i + 1}. {view.get('name') or view.get('query') or 'Market view'}"
            for i, view in enumerate(st.session_state.saved_market_filters)
        ]
        selected_saved_market = load_cols[0].selectbox("Load saved market view", saved_labels, key="load_saved_market_view")
        selected_market_view = st.session_state.saved_market_filters[saved_labels.index(selected_saved_market)]
        if load_cols[1].button("Load saved view", key="load_market_view_button"):
            st.session_state["pending_market_filter_view"] = selected_market_view
            st.session_state["market_view_loaded_message"] = f"Loaded saved market view: {selected_market_view.get('name', selected_saved_market)}"
            st.rerun()
        if load_cols[2].button("Delete saved view", key="delete_market_view_button"):
            st.session_state.saved_market_filters.pop(saved_labels.index(selected_saved_market))
            save_local_list("saved_market_filters.json", st.session_state.saved_market_filters)
            st.rerun()
    if save_market_clicked:
        st.session_state.saved_market_filters.append(
            {
                "name": saved_market_name.strip() or f"Markets {md.now_utc_label()}",
                "created_at": md.now_utc_label(),
                "query": local_query,
                "view": view_mode,
                "quick": quick_filter,
                "platform_filter": platform_filter,
                "status_filter": status_filter,
                "include_categories": include_categories,
                "exclude_categories": exclude_categories,
                "prob_preset": prob_preset,
                "custom_prob": list(custom_prob),
                "spread_preset": spread_preset,
                "custom_spread": float(custom_spread),
                "liquidity_preset": liquidity_preset,
                "custom_liquidity": float(custom_liquidity),
                "end_preset": end_preset,
                "custom_days": int(custom_days),
                "volume_1h_preset": volume_1h_preset,
                "custom_volume_1h": float(custom_volume_1h),
                "volume_preset": volume_preset,
                "custom_volume": float(custom_volume),
                "age_preset": age_preset,
                "custom_age_days": int(custom_age_days),
                "volume_delta_1h_preset": volume_delta_1h_preset,
                "custom_volume_delta_1h": float(custom_volume_delta_1h),
                "volume_delta_24h_preset": volume_delta_24h_preset,
                "custom_volume_delta_24h": float(custom_volume_delta_24h),
                "change_preset": change_preset,
                "custom_change": float(custom_change),
                "change_24h_preset": change_24h_preset,
                "custom_change_24h": float(custom_change_24h),
                "sort_by": sort_by,
                "limit_rows": int(limit_rows),
            }
        )
        save_local_list("saved_market_filters.json", st.session_state.saved_market_filters)
        st.success("Saved market view.")

    filtered = filter_text(combined, local_query)
    filtered = filtered[filtered["platform"].isin(platform_filter)]
    if status_filter == "Active":
        if "active" in filtered:
            filtered = filtered[filtered["active"].fillna(False).astype(bool)]
        if "closed" in filtered:
            filtered = filtered[~filtered["closed"].fillna(False).astype(bool)]
    elif status_filter == "Closed" and "closed" in filtered:
        filtered = filtered[filtered["closed"].fillna(False).astype(bool)]
    if include_categories and market_category_col in filtered:
        filtered = filtered[filtered[market_category_col].astype(str).isin(include_categories)]
    if exclude_categories and market_category_col in filtered:
        filtered = filtered[~filtered[market_category_col].astype(str).isin(exclude_categories)]

    filtered = apply_probability_filter(filtered, prob_preset, custom_prob)
    filtered = apply_spread_filter(filtered, spread_preset, float(custom_spread))
    filtered = option_metric_filter(filtered, "liquidity", liquidity_preset, float(custom_liquidity))
    filtered = apply_end_date_filter(filtered, end_preset, int(custom_days))
    filtered = apply_market_age_filter(filtered, age_preset, int(custom_age_days))
    filter_volume_col = "activity_volume" if "activity_volume" in filtered else "volume_24h"
    filtered = option_metric_filter(filtered, "volume_1h", volume_1h_preset, float(custom_volume_1h))
    filtered = option_metric_filter(filtered, filter_volume_col, volume_preset, float(custom_volume))
    filtered = apply_percent_delta_filter(filtered, "volume_delta_1h", volume_delta_1h_preset, float(custom_volume_delta_1h))
    filtered = apply_percent_delta_filter(filtered, "volume_delta_24h", volume_delta_24h_preset, float(custom_volume_delta_24h))
    filtered = apply_price_delta_filter(filtered, "price_delta_1h", change_preset, float(custom_change))
    filtered = apply_price_delta_filter(filtered, "price_delta_24h", change_24h_preset, float(custom_change_24h))

    if quick_filter == "Saved":
        saved_keys = {str(item.get("market_key")) for item in st.session_state.watchlist}
        if saved_keys:
            filtered = filtered[filtered["market_key"].astype(str).isin(saved_keys)]
    elif quick_filter == "My Positions":
        paper_positions = safe_load("Paper positions", ct.get_positions)
        research_positions = st.session_state.portfolio.copy() if isinstance(st.session_state.portfolio, pd.DataFrame) else pd.DataFrame()
        held_markets = md.held_market_keys(research_positions, paper_positions)
        filtered = filtered[filtered["market_key"].astype(str).isin(held_markets)] if held_markets else filtered.iloc[0:0]
    elif quick_filter == "Ending Soon":
        filtered = apply_end_date_filter(filtered, "<7d", 7)
        sort_by = "end_time"
    elif quick_filter == "New" and "created_at" in filtered:
        sort_by = "created_at"

    ascending = sort_by in {"spread", "end_time", "market_age_days"}
    if sort_by not in filtered:
        sort_by = filter_volume_col
    filtered = filtered.sort_values(sort_by, ascending=ascending, na_position="last").head(limit_rows).reset_index(drop=True)

    metric_cols = st.columns(5)
    metric_cols[0].metric("Matches", f"{len(filtered):,}")
    metric_cols[1].metric("Loaded markets", f"{len(combined):,}")
    metric_cols[2].metric("24h volume", money(filtered[filter_volume_col].sum() if filter_volume_col in filtered else 0))
    metric_cols[3].metric("Median prob", cents(filtered["yes_price"].median() if "yes_price" in filtered and not filtered.empty else None))
    metric_cols[4].metric("Median spread", cents(filtered["spread"].median() if "spread" in filtered and not filtered.empty else None))
    chip_labels: list[str] = []
    if local_query.strip():
        chip_labels.append(f"Search: {local_query.strip()}")
    chip_labels.append(f"View: {view_mode}")
    chip_labels.append(f"Quick: {quick_filter}")
    if platform_filter and set(platform_filter) != {"Polymarket", "Kalshi"}:
        chip_labels.append("Platform: " + ", ".join(platform_filter))
    chip_labels.append(f"Status: {status_filter}")
    if include_categories:
        chip_labels.append("Include: " + ", ".join(md.market_category_label(item) for item in include_categories[:3]) + ("..." if len(include_categories) > 3 else ""))
    if exclude_categories:
        chip_labels.append("Exclude: " + ", ".join(md.market_category_label(item) for item in exclude_categories[:3]) + ("..." if len(exclude_categories) > 3 else ""))
    if prob_preset != "All":
        chip_labels.append(f"Probability: {prob_preset if prob_preset != 'Custom' else f'{custom_prob[0]}%-{custom_prob[1]}%'}")
    if spread_preset != "All":
        chip_labels.append(f"Spread: {spread_preset if spread_preset != 'Custom' else f'<{custom_spread:.1f}c'}")
    if liquidity_preset != "All":
        chip_labels.append(f"Liquidity: {liquidity_preset if liquidity_preset != 'Custom' else '>$' + f'{custom_liquidity:,.0f}'}")
    if end_preset != "All":
        chip_labels.append(f"End date: {end_preset if end_preset != 'Custom' else '<' + str(custom_days) + 'd'}")
    if age_preset != "All":
        chip_labels.append(f"Market age: {age_preset if age_preset != 'Custom' else '<' + str(custom_age_days) + 'd'}")
    if volume_1h_preset != "All":
        chip_labels.append(f"Vol 1h: {volume_1h_preset if volume_1h_preset != 'Custom' else '>$' + f'{custom_volume_1h:,.0f}'}")
    if volume_preset != "All":
        chip_labels.append(f"24h volume: {volume_preset if volume_preset != 'Custom' else '>$' + f'{custom_volume:,.0f}'}")
    if volume_delta_1h_preset != "All":
        chip_labels.append(f"Vol delta 1h: {volume_delta_1h_preset if volume_delta_1h_preset != 'Custom' else '>' + f'{custom_volume_delta_1h:.0f}%'}")
    if volume_delta_24h_preset != "All":
        chip_labels.append(f"Vol delta 24h: {volume_delta_24h_preset if volume_delta_24h_preset != 'Custom' else '>' + f'{custom_volume_delta_24h:.0f}%'}")
    if change_preset != "All":
        chip_labels.append(f"Price delta 1h: {change_preset if change_preset != 'Custom' else f'>{custom_change:.1f}c'}")
    if change_24h_preset != "All":
        chip_labels.append(f"Price delta 24h: {change_24h_preset if change_24h_preset != 'Custom' else f'>{custom_change_24h:.1f}c'}")
    chip_labels.append(f"Sort: {sort_by}")
    render_filter_chips(chip_labels)
    market_defaults = market_filter_defaults(categories)
    clear_actions: list[tuple[str, dict[str, Any]]] = []
    if local_query.strip():
        clear_actions.append(("search", {"markets_search": ""}))
    if view_mode != market_defaults["markets_view_mode"]:
        clear_actions.append(("view", {"markets_view_mode": market_defaults["markets_view_mode"]}))
    if quick_filter != market_defaults["markets_quick_filter"]:
        clear_actions.append(("quick", {"markets_quick_filter": market_defaults["markets_quick_filter"]}))
    if set(platform_filter) != set(market_defaults["markets_platform_filter"]):
        clear_actions.append(("platform", {"markets_platform_filter": market_defaults["markets_platform_filter"]}))
    if status_filter != market_defaults["markets_status_filter"]:
        clear_actions.append(("status", {"markets_status_filter": market_defaults["markets_status_filter"]}))
    if include_categories:
        clear_actions.append(("include", {"markets_include_categories": []}))
    if exclude_categories:
        clear_actions.append(("exclude", {"markets_exclude_categories": []}))
    if prob_preset != "All":
        clear_actions.append(("probability", {"markets_prob_preset": "All"}))
    if spread_preset != "All":
        clear_actions.append(("spread", {"markets_spread_preset": "All"}))
    if liquidity_preset != "All":
        clear_actions.append(("liquidity", {"markets_liquidity_preset": "All"}))
    if end_preset != "All":
        clear_actions.append(("end date", {"markets_end_preset": "All"}))
    if age_preset != "All":
        clear_actions.append(("market age", {"markets_age_preset": "All"}))
    if volume_1h_preset != "All":
        clear_actions.append(("1h volume", {"markets_volume_1h_preset": "All"}))
    if volume_preset != "All":
        clear_actions.append(("24h volume", {"markets_volume_preset": "All"}))
    if volume_delta_1h_preset != "All":
        clear_actions.append(("1h volume delta", {"markets_volume_delta_1h_preset": "All"}))
    if volume_delta_24h_preset != "All":
        clear_actions.append(("24h volume delta", {"markets_volume_delta_24h_preset": "All"}))
    if change_preset != "All":
        clear_actions.append(("1h price delta", {"markets_change_preset": "All"}))
    if change_24h_preset != "All":
        clear_actions.append(("24h price delta", {"markets_change_24h_preset": "All"}))
    if sort_by != market_defaults["markets_sort_by"]:
        clear_actions.append(("sort", {"markets_sort_by": market_defaults["markets_sort_by"]}))
    render_filter_clear_buttons(clear_actions, "markets")
    if st.session_state.saved_market_filters:
        st.caption(f"Saved market views: {len(st.session_state.saved_market_filters)}")
        with st.expander("Saved market filters", expanded=False):
            st.dataframe(pd.DataFrame(st.session_state.saved_market_filters), width="stretch", height=160)
            if st.button("Clear saved market filters"):
                st.session_state.saved_market_filters = []
                save_local_list("saved_market_filters.json", st.session_state.saved_market_filters)
                st.rerun()

    display_source = filtered.copy()
    display_source["market"] = display_source["platform"].astype(str) + " - " + display_source["title"].astype(str)
    display_source["prob"] = numeric_col(display_source, "yes_price") * 100
    display_source["prob_bar"] = display_source["prob"]
    display_source["spread_c"] = numeric_col(display_source, "spread") * 100
    display_source["vol_24h"] = numeric_col(display_source, "volume_24h")
    display_source["vol_delta_1h_pct"] = numeric_col(display_source, "volume_delta_1h") * 100
    display_source["vol_delta_24h_pct"] = numeric_col(display_source, "volume_delta_24h") * 100
    display_source["price_delta_1h_c"] = numeric_col(display_source, "price_delta_1h") * 100
    display_source["price_delta_24h_c"] = numeric_col(display_source, "price_delta_24h") * 100
    if "volume_1h" not in display_source:
        display_source["volume_1h"] = 0.0
    end_times = pd.to_datetime(display_source.get("end_time"), utc=True, errors="coerce")
    display_source["end_date"] = end_times.map(md.relative_time_label).fillna("-")
    display_source["end_at"] = end_times.dt.strftime("%Y-%m-%d %H:%M").fillna("-")
    display = clean_table(
        display_source,
        [
            "market",
            "prob",
            "prob_bar",
            "spread_c",
            "vol_24h",
            "volume_1h",
            "vol_delta_1h_pct",
            "vol_delta_24h_pct",
            "price_delta_1h_c",
            "price_delta_24h_c",
            "liquidity",
            "end_date",
            "end_at",
            "market_age_days",
            "platform",
            "title",
            "category",
            "yes_price",
            "activity_volume",
            "volume_24h",
            "volume",
            "best_bid",
            "best_ask",
            "spread",
            "change_1h",
            "change_1d",
            "created_at",
            "url",
        ],
    )
    table_config = {
        "market": st.column_config.TextColumn("Market", width="large"),
        "prob": st.column_config.NumberColumn("Prob", format="%.1f%%"),
        "prob_bar": st.column_config.ProgressColumn("Prob Bar", format="%.0f%%", min_value=0, max_value=100),
        "spread_c": st.column_config.NumberColumn("Spread", format="%.1fc"),
        "vol_24h": st.column_config.NumberColumn("Vol 24h", format="$%.0f"),
        "volume_1h": st.column_config.NumberColumn("Vol 1h", format="$%.0f"),
        "vol_delta_1h_pct": st.column_config.NumberColumn("Vol Delta 1h", format="%+.0f%%"),
        "vol_delta_24h_pct": st.column_config.NumberColumn("Vol Delta 24h", format="%+.0f%%"),
        "price_delta_1h_c": st.column_config.NumberColumn("Price Delta 1h", format="%+.1fc"),
        "price_delta_24h_c": st.column_config.NumberColumn("Price Delta 24h", format="%+.1fc"),
        "liquidity": st.column_config.NumberColumn("Liquidity", format="$%.0f"),
        "end_date": st.column_config.TextColumn("End Date"),
        "end_at": st.column_config.TextColumn("End At"),
        "market_age_days": st.column_config.NumberColumn("Age d", format="%.1f"),
        "yes_price": st.column_config.NumberColumn(format="%.3f"),
        "best_bid": st.column_config.NumberColumn(format="%.3f"),
        "best_ask": st.column_config.NumberColumn(format="%.3f"),
        "spread": st.column_config.NumberColumn(format="%.3f"),
        "change_1h": st.column_config.NumberColumn(format="%+.3f"),
        "change_1d": st.column_config.NumberColumn(format="%+.3f"),
        "activity_volume": st.column_config.NumberColumn(format="$%.0f"),
        "volume_24h": st.column_config.NumberColumn(format="$%.0f"),
        "volume": st.column_config.NumberColumn(format="$%.0f"),
        "liquidity": st.column_config.NumberColumn(format="$%.0f"),
        "url": st.column_config.LinkColumn("URL"),
    }
    scan_action_cols = st.columns([1.1, 1.1, 3])
    scan_action_cols[0].download_button(
        "Export filtered markets CSV",
        filtered.to_csv(index=False).encode("utf-8"),
        file_name="filtered_markets.csv",
        mime="text/csv",
        width="stretch",
    )
    if scan_action_cols[1].button("Track filtered page", key="markets_track_filtered_page", width="stretch", disabled=filtered.empty):
        st.session_state.watchlist, changed_count = md.upsert_watchlist_markets(st.session_state.watchlist, filtered)
        if changed_count:
            save_local_list("watchlist.json", st.session_state.watchlist)
            st.success(f"Tracked {changed_count} filtered markets.")
        else:
            st.info("Filtered markets are already tracked.")
    scan_action_cols[2].caption(f"Actions apply to the {len(filtered):,} markets currently shown after filters and row limit.")
    if view_mode == "Table":
        market_table_event = st.dataframe(
            display,
            width="stretch",
            height=430,
            column_config=table_config,
            key="markets_scanner_table",
            on_select="rerun",
            selection_mode="single-row",
        )
        selected_table_row = dataframe_selected_row_index(market_table_event)
        if selected_table_row is not None and selected_table_row < len(filtered):
            selected_key = str(filtered.iloc[selected_table_row].get("market_key", ""))
            if selected_key:
                st.session_state["markets_inspect_market_key"] = selected_key
                st.caption("Selected table row is opened in the market detail below.")
    elif view_mode == "Card":
        for chunk_start in range(0, len(filtered.head(24)), 3):
            cols = st.columns(3)
            for col, (_, row) in zip(cols, filtered.head(24).iloc[chunk_start : chunk_start + 3].iterrows()):
                with col:
                    market_tile(row)
    else:
        dated_markets = filtered.copy()
        end_source = dated_markets["end_time"] if "end_time" in dated_markets else pd.Series(pd.NaT, index=dated_markets.index)
        dated_end_times = pd.to_datetime(end_source, utc=True, errors="coerce")
        dated_markets = dated_markets[dated_end_times.notna()].copy()
        month_values = sorted(dated_end_times.dropna().dt.strftime("%Y-%m").unique().tolist())
        current_month = pd.Timestamp.now(tz="UTC").strftime("%Y-%m")
        if not month_values:
            draw_empty("No dated markets match the current calendar filters.")
        else:
            month_options = sorted(set(month_values + [current_month]))
            default_month = current_month if current_month in month_values else month_values[0]
            if st.session_state.get("markets_calendar_month") not in month_options:
                st.session_state["markets_calendar_month"] = default_month
            calendar_controls = st.columns([1.1, 1, 3])
            selected_month = calendar_controls[0].selectbox("Calendar month", month_options, key="markets_calendar_month")
            if calendar_controls[1].button("[ TODAY ]", key="markets_calendar_today", width="stretch"):
                st.session_state["markets_calendar_month"] = current_month
                st.rerun()
            month_title = pd.Timestamp(f"{selected_month}-01").strftime("%B, %Y")
            calendar_controls[2].caption("Click a market inside a day cell to open it in the detail panel below.")
            st.markdown(f"#### {month_title}")

            calendar_days = md.market_calendar_days(filtered, month=f"{selected_month}-01", top_per_day=5)
            header_cols = st.columns(7)
            for header_col, weekday in zip(header_cols, ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]):
                header_col.markdown(f"**{weekday}**")
            for _, week_frame in calendar_days.groupby("week", sort=True):
                day_cols = st.columns(7)
                for day_col, (_, day_row) in zip(day_cols, week_frame.sort_values("weekday").iterrows()):
                    with day_col:
                        with st.container(border=True):
                            current_day = bool(day_row.get("is_current_month"))
                            day_label = str(day_row.get("day", ""))
                            market_count = int(day_row.get("markets", 0) or 0)
                            day_volume = float(day_row.get("volume", 0.0) or 0.0)
                            if current_day:
                                st.markdown(f"**{day_label}**")
                            else:
                                st.caption(day_label)
                            if market_count:
                                st.caption(f"{market_count:,} markets | {money(day_volume)}")
                            else:
                                st.caption("No markets")
                            top_markets = day_row.get("top_markets", [])
                            if not isinstance(top_markets, list):
                                top_markets = []
                            for item_idx, item in enumerate(top_markets):
                                market_key = str(item.get("market_key", "") or "")
                                safe_key = re.sub(r"[^a-zA-Z0-9_]", "_", f"{day_row.get('date')}_{market_key}_{item_idx}")[:90]
                                title = str(item.get("title", "") or "Market")
                                platform = str(item.get("platform", "") or "-")
                                label = f"{platform} {title[:34]} {cents(item.get('yes_price'))}"
                                if st.button(label, key=f"calendar_market_{safe_key}", width="stretch", disabled=not bool(market_key)):
                                    st.session_state["markets_inspect_market_key"] = market_key
                                    st.rerun()
                            more_count = int(day_row.get("more_count", 0) or 0)
                            if more_count:
                                st.caption(f"+{more_count:,} more")
            st.markdown("##### Calendar table")
            calendar_summary = clean_table(calendar_days, ["date", "markets", "volume", "median_prob", "more_count"])
            st.dataframe(
                calendar_summary[calendar_summary["markets"] > 0],
                width="stretch",
                height=220,
                column_config={
                    "volume": st.column_config.NumberColumn(format="$%.0f"),
                    "median_prob": st.column_config.NumberColumn(format="%.3f"),
                },
            )
            st.dataframe(display, width="stretch", height=330, column_config=table_config)
    requested_key = str(st.session_state.get("markets_inspect_market_key", "") or "")
    inspect_frame = filtered.copy()
    if requested_key and "market_key" in combined and (inspect_frame.empty or requested_key not in set(inspect_frame["market_key"].astype(str))):
        override = combined[combined["market_key"].astype(str).eq(requested_key)].head(1)
        if not override.empty:
            inspect_frame = pd.concat([override, inspect_frame], ignore_index=True, sort=False)
            st.info("Inspecting a related market outside the current table filters.")
    if inspect_frame.empty:
        return
    inspect_frame = inspect_frame.reset_index(drop=True)
    options = [f"{i + 1}. {row.platform}: {str(row.title)[:95]}" for i, row in inspect_frame.iterrows()]
    default_index = 0
    if requested_key and "market_key" in inspect_frame:
        matches = inspect_frame.index[inspect_frame["market_key"].astype(str).eq(requested_key)].tolist()
        if matches:
            default_index = int(inspect_frame.index.get_loc(matches[0]))
            st.session_state["markets_inspect_market"] = options[default_index]
    if st.session_state.get("markets_inspect_market") not in options:
        st.session_state["markets_inspect_market"] = options[default_index]
    selected = st.selectbox("Inspect market", options, index=default_index, key="markets_inspect_market")
    index = options.index(selected)
    st.session_state["markets_inspect_market_key"] = str(inspect_frame.iloc[index].get("market_key", ""))
    render_market_detail(inspect_frame.iloc[index], combined)


def render_wallet(wallet: str) -> None:
    wallet = wallet.strip()
    if not wallet:
        draw_empty("Enter a Polymarket proxy-wallet address.")
        return
    if not re.fullmatch(r"0x[a-fA-F0-9]{40}", wallet):
        st.warning("Expected an EVM address like 0x...")
        return
    wallet_loaded_at = pd.Timestamp.now(tz="UTC")
    open_positions, closed_positions, trades, activity = safe_load(
        "Polymarket wallet",
        load_wallet_bundle,
        wallet,
        250,
        default=(pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()),
    )
    summary = md.wallet_summary(open_positions, closed_positions, trades)
    trader_name = wallet_identity(wallet, trades)
    total_pnl = float(summary["realized_pnl"]) + float(summary["unrealized_pnl"])
    wallet_key = re.sub(r"[^a-zA-Z0-9_]", "_", wallet.lower())
    account_stats = safe_load("Wallet account stats", load_wallet_account_stats, (wallet,), 3, True, default=pd.DataFrame())
    parity_profile = safe_load("PredictParity public trader profile", load_predictparity_trader_profile, wallet, default={})
    if not isinstance(parity_profile, dict):
        parity_profile = {}
    account_row = account_stats.iloc[0] if not account_stats.empty else pd.Series(dtype=object)
    cash_balance = float(pd.to_numeric(pd.Series([account_row.get("cash_balance", 0.0)]), errors="coerce").fillna(0.0).iloc[0])
    activity_observations = int(pd.to_numeric(pd.Series([account_row.get("activity_observations", 0)]), errors="coerce").fillna(0).iloc[0])
    oldest_activity_time = pd.to_datetime(account_row.get("oldest_activity_time"), utc=True, errors="coerce")
    account_created = oldest_activity_time.strftime("%b %d, %Y") if pd.notna(oldest_activity_time) else "-"
    first_activity = activity.sort_values("time", ascending=True).head(1) if not activity.empty and "time" in activity else pd.DataFrame()
    first_activity_row = first_activity.iloc[0] if not first_activity.empty else pd.Series(dtype=object)
    first_activity_tx = str(first_activity_row.get("transactionHash", "") or "")
    first_activity_notional = float(pd.to_numeric(pd.Series([first_activity_row.get("notional", 0.0)]), errors="coerce").fillna(0.0).iloc[0])
    if parity_profile:
        trader_name = str(parity_profile.get("display_name") or trader_name)
        profile_total_pnl = pd.to_numeric(pd.Series([parity_profile.get("all_time_pnl")]), errors="coerce").dropna()
        profile_volume = pd.to_numeric(pd.Series([parity_profile.get("all_time_volume")]), errors="coerce").dropna()
        profile_cash = pd.to_numeric(pd.Series([parity_profile.get("usdc_balance")]), errors="coerce").dropna()
        profile_first_funding = pd.to_numeric(pd.Series([parity_profile.get("first_funding_amount")]), errors="coerce").dropna()
        profile_active_value = pd.to_numeric(pd.Series([parity_profile.get("active_positions_value")]), errors="coerce").dropna()
        profile_win_rate = pd.to_numeric(pd.Series([parity_profile.get("win_rate")]), errors="coerce").dropna()
        if not profile_total_pnl.empty:
            total_pnl = float(profile_total_pnl.iloc[0])
        if not profile_cash.empty:
            cash_balance = float(profile_cash.iloc[0])
        if not profile_first_funding.empty:
            first_activity_notional = float(profile_first_funding.iloc[0])
        if str(parity_profile.get("first_funding_tx_hash") or "").startswith("0x"):
            first_activity_tx = str(parity_profile["first_funding_tx_hash"])
        profile_created_at = pd.to_datetime(parity_profile.get("account_created_at"), utc=True, errors="coerce")
        if pd.notna(profile_created_at):
            account_created = profile_created_at.strftime("%b %d, %Y")
        profile_last_synced_at = pd.to_datetime(parity_profile.get("last_synced_at"), utc=True, errors="coerce")
    else:
        profile_volume = pd.Series(dtype="float64")
        profile_active_value = pd.Series(dtype="float64")
        profile_win_rate = pd.Series(dtype="float64")
        profile_last_synced_at = pd.NaT
    insights = trader_insight_metrics(
        open_positions,
        closed_positions,
        trades,
        activity,
        cash_balance=cash_balance,
        whale_threshold=float(min_whale),
    )
    wallet_parity_url = predictparity_trader_url(
        (parity_profile.get("username") if parity_profile else "")
        or (parity_profile.get("display_name") if parity_profile else "")
        or trader_name
    )

    st.markdown(f"### {trader_name}")
    st.caption(f"Polymarket proxy wallet {wallet}")
    action_cols = st.columns([1, 1, 1, 1, 1, 1, 1.2, 1.4])
    if action_cols[0].button("Back", key=f"wallet_back_to_traders_{wallet_key}", width="stretch"):
        st.session_state["traders_inspect_wallet"] = wallet
        queue_navigation("Traders")
        st.rerun()
    tracked_wallets = {str(item).lower() for item in st.session_state.followed_wallets}
    if wallet.lower() in tracked_wallets:
        action_cols[1].button("Tracked", key=f"wallet_profile_tracked_{wallet_key}", width="stretch", disabled=True)
    elif action_cols[1].button("Track wallet", key=f"wallet_profile_track_{wallet_key}", width="stretch"):
        st.session_state.followed_wallets, changed = md.upsert_followed_wallet(st.session_state.followed_wallets, wallet)
        if changed:
            save_local_list("followed_wallets.json", st.session_state.followed_wallets)
            st.success("Wallet added to tracked wallets.")
        st.rerun()
    if wallet_parity_url:
        action_cols[2].link_button("Parity", wallet_parity_url, width="stretch")
    else:
        action_cols[2].button("Parity", key=f"wallet_profile_parity_disabled_{wallet_key}", width="stretch", disabled=True)
    action_cols[3].link_button("Polymarket", f"https://polymarket.com/profile/{wallet}", width="stretch")
    action_cols[4].link_button("Polygonscan", f"https://polygonscan.com/address/{wallet}", width="stretch")
    action_cols[5].link_button("Arkham", f"https://intel.arkm.com/explorer/address/{wallet}", width="stretch")
    action_cols[6].link_button("Relay", f"https://relay.link/transactions?address={wallet}", width="stretch")
    action_cols[7].download_button(
        "Share PnL",
        wallet_share_payload(wallet, trader_name, summary, open_positions).encode("utf-8"),
        file_name=f"{short_addr(wallet, width=4).replace('...', '_')}_pnl_snapshot.txt",
        mime="text/plain",
        width="stretch",
    )

    cols = st.columns(6)
    cols[0].metric("Total PnL", money(total_pnl))
    cols[1].metric("Volume", money(float(profile_volume.iloc[0]) if not profile_volume.empty else summary["trade_notional"]))
    cols[2].metric("USDC Balance", money(cash_balance))
    active_position_value = float(profile_active_value.iloc[0]) if not profile_active_value.empty else float(summary["open_value"])
    cols[3].metric("Active Positions", money(active_position_value), f"{len(open_positions):,} positions")
    win_rate_value = float(profile_win_rate.iloc[0]) if not profile_win_rate.empty else summary["win_rate"]
    cols[4].metric("Win Rate", pct(win_rate_value) if win_rate_value is not None else "-")
    cols[5].metric("Realized / Unrealized", f"{markdown_money(summary['realized_pnl'])} / {markdown_money(summary['unrealized_pnl'])}")
    info_cols = st.columns(3)
    info_cols[0].metric("First Funding", money(first_activity_notional) if first_activity_notional else "-", short_addr(first_activity_tx) if first_activity_tx else "")
    if first_activity_tx.startswith("0x"):
        info_cols[0].link_button("Open first tx", f"https://polygonscan.com/tx/{first_activity_tx}", width="stretch")
    info_cols[1].metric("Account Created", account_created)
    info_cols[2].metric("Activity observations", f"{activity_observations:,}")

    chart_controls = st.columns([1.2, 1.4, 2.4])
    pnl_window = chart_controls[0].radio("PnL window", ["1d", "1w", "1mo", "All"], index=1, horizontal=True, key=f"wallet_pnl_window_{wallet_key}")
    pnl_view = chart_controls[1].radio("PnL view", ["Chart view", "Calendar view"], horizontal=True, key=f"wallet_pnl_view_{wallet_key}")
    pnl_header, pnl_caption = st.columns([1, 5])
    pnl_header.markdown("### PNL")
    pnl_caption.caption(md.pnl_window_label(pnl_window))
    if pnl_view == "Chart view":
        parity_curve = pd.DataFrame()
        parity_trader_id = str(parity_profile.get("id", "") or "") if parity_profile else ""
        if parity_trader_id:
            parity_curve = safe_load("PredictParity PnL chart", load_predictparity_pnl_chart, parity_trader_id, pnl_window, default=pd.DataFrame())
        curve = parity_curve if isinstance(parity_curve, pd.DataFrame) and not parity_curve.empty else filter_pnl_curve_window(wallet_pnl_curve(open_positions, closed_positions), pnl_window)
        if curve.empty:
            draw_empty("No PnL history returned for this wallet and selected window.")
        else:
            fig = px.line(curve, x="time", y="pnl", color="series", markers=True, template="plotly_dark")
            fig.update_traces(line_width=2)
            fig.update_layout(height=320, margin=dict(l=10, r=10, t=20, b=10), paper_bgcolor=BG, plot_bgcolor=BG, yaxis_title="PnL", xaxis_title="")
            st.plotly_chart(fig, width="stretch", config=plot_config())
            if isinstance(curve, pd.DataFrame) and "source" in curve and curve["source"].astype(str).eq("PredictParity").any():
                st.caption("PNL chart sourced from PredictParity public trader data.")
    else:
        calendar = wallet_pnl_calendar(closed_positions, pnl_window)
        if calendar.empty:
            draw_empty("No closed-position PnL calendar returned for this wallet and selected window.")
        else:
            calendar = calendar.copy()
            calendar["result"] = calendar["realized_pnl"].map(lambda value: "Gain" if value >= 0 else "Loss")
            c1, c2, c3 = st.columns(3)
            c1.metric("Calendar days", f"{len(calendar):,}")
            c2.metric("Realized in window", money(float(calendar["realized_pnl"].sum())))
            c3.metric("Closed positions", f"{int(calendar['closed_positions'].sum()):,}")
            fig = px.bar(
                calendar,
                x="date",
                y="realized_pnl",
                color="result",
                template="plotly_dark",
                color_discrete_map={"Gain": ACCENT, "Loss": RED},
            )
            fig.update_layout(height=320, margin=dict(l=10, r=10, t=20, b=10), paper_bgcolor=BG, plot_bgcolor=BG, yaxis_title="Realized PnL", xaxis_title="")
            st.plotly_chart(fig, width="stretch", config=plot_config())
            st.dataframe(
                calendar,
                width="stretch",
                height=260,
                column_config={
                    "realized_pnl": st.column_config.NumberColumn("Realized PnL", format="$%.2f"),
                    "cumulative_realized_pnl": st.column_config.NumberColumn("Cumulative", format="$%.2f"),
                },
            )

    tabs = st.tabs(md.wallet_profile_tab_labels(open_positions, closed_positions, trades, activity))
    with tabs[0]:
        positions = wallet_positions_frame(open_positions, closed_positions)
        if positions.empty:
            draw_empty("No positions returned.")
        else:
            st.caption(f"Last synced {md.compact_elapsed_label(profile_last_synced_at if pd.notna(profile_last_synced_at) else wallet_loaded_at)}")
            pending_position_clear = st.session_state.pop(f"wallet_pos_{wallet_key}_clear_pending", None)
            if isinstance(pending_position_clear, dict):
                for key, value in pending_position_clear.items():
                    st.session_state[key] = value
            p1, p2, p3, p4, p5 = st.columns([1, 1.2, 1, 1, 1])
            position_status_key = f"wallet_position_status_{wallet_key}"
            position_search_key = f"wallet_position_search_{wallet_key}"
            position_min_value_key = f"wallet_position_min_value_{wallet_key}"
            position_min_pnl_key = f"wallet_position_min_pnl_{wallet_key}"
            position_sort_key = f"wallet_position_sort_{wallet_key}"
            status_filter = p1.radio("Position status", ["Active", "Closed", "All"], horizontal=True, key=position_status_key)
            position_query = p2.text_input("Position search", placeholder="market or outcome", key=position_search_key)
            min_value = p3.number_input("Min value", min_value=0, step=100, key=position_min_value_key)
            min_abs_pnl = p4.number_input("Min abs PnL", min_value=0, step=100, key=position_min_pnl_key)
            sort_by = p5.selectbox("Sort positions", ["value", "pnl", "pnl_pct", "size", "time"], key=f"wallet_position_sort_{wallet_key}")
            if st.button("Reset position filters", key=f"wallet_position_reset_{wallet_key}", width="stretch"):
                st.session_state[f"wallet_pos_{wallet_key}_clear_pending"] = {
                    position_status_key: "Active",
                    position_search_key: "",
                    position_min_value_key: 0,
                    position_min_pnl_key: 0,
                    position_sort_key: "value",
                }
                st.rerun()

            filtered_positions = md.filter_wallet_positions_by_status(positions, status_filter)
            filtered_positions = filter_text(filtered_positions, position_query)
            filtered_positions = filtered_positions[numeric_col(filtered_positions, "value") >= float(min_value)]
            if min_abs_pnl > 0:
                filtered_positions = filtered_positions[numeric_col(filtered_positions, "pnl").abs() >= float(min_abs_pnl)]
            if sort_by not in filtered_positions:
                sort_by = "value"
            filtered_positions = filtered_positions.sort_values(sort_by, ascending=False, na_position="last")
            render_filter_chips(
                [
                    f"Status: {status_filter}",
                    f"Rows: {len(filtered_positions):,}",
                    *(["Search: " + position_query.strip()] if position_query.strip() else []),
                    *(["Min value: " + money(min_value)] if min_value else []),
                    *(["Min abs PnL: " + money(min_abs_pnl)] if min_abs_pnl else []),
                    f"Sort: {sort_by}",
                ]
            )
            position_clear_actions: list[tuple[str, dict[str, Any]]] = []
            if status_filter != "Active":
                position_clear_actions.append(("status", {position_status_key: "Active"}))
            if position_query.strip():
                position_clear_actions.append(("search", {position_search_key: ""}))
            if int(min_value) > 0:
                position_clear_actions.append(("value", {position_min_value_key: 0}))
            if int(min_abs_pnl) > 0:
                position_clear_actions.append(("PnL", {position_min_pnl_key: 0}))
            if sort_by != "value":
                position_clear_actions.append(("sort", {position_sort_key: "value"}))
            render_filter_clear_buttons(position_clear_actions, f"wallet_pos_{wallet_key}")
            if filtered_positions.empty:
                draw_empty("No wallet positions match the current filters.")
            else:
                export = clean_table(filtered_positions, ["status", "title", "outcome", "size", "avg_price", "current_price", "value", "pnl", "pnl_pct", "time", "url"])
                st.download_button("Export wallet positions CSV", export.to_csv(index=False).encode("utf-8"), file_name="wallet_positions.csv", mime="text/csv")
                st.dataframe(
                    export.head(250),
                    width="stretch",
                    height=480,
                    column_config={
                        "title": st.column_config.TextColumn("Market", width="large"),
                        "avg_price": st.column_config.NumberColumn("Avg Entry", format="%.4f"),
                        "current_price": st.column_config.NumberColumn("Current", format="%.4f"),
                        "value": st.column_config.NumberColumn("Value", format="$%.2f"),
                        "pnl": st.column_config.NumberColumn("PnL", format="$%.2f"),
                        "pnl_pct": st.column_config.NumberColumn("PnL %", format="%.2%"),
                        "url": st.column_config.LinkColumn("URL"),
                    },
                )
                actionable_positions = filtered_positions[
                    filtered_positions.get("market_key", pd.Series("", index=filtered_positions.index)).fillna("").astype(str).str.strip().ne("")
                ].copy()
                if not actionable_positions.empty:
                    action_options = [
                        f"{idx + 1}. {str(item.get('title', '-'))[:90]} | {item.get('outcome', '-')} | {money(item.get('value', 0.0))}"
                        for idx, (_, item) in enumerate(actionable_positions.head(80).iterrows())
                    ]
                    selected_action = st.selectbox("Position market action", action_options, key=f"wallet_position_market_action_{wallet_key}")
                    selected_position = actionable_positions.head(80).iloc[action_options.index(selected_action)]
                    selected_market_key = str(selected_position.get("market_key", "") or "")
                    position_action_cols = st.columns([1, 1, 1, 3])
                    if position_action_cols[0].button("Open position market", key=f"wallet_open_position_market_{wallet_key}", width="stretch"):
                        st.session_state["markets_inspect_market_key"] = selected_market_key
                        queue_navigation("Markets", str(selected_position.get("title", "")))
                        st.rerun()
                    if position_action_cols[1].button("Track position market", key=f"wallet_track_position_market_{wallet_key}", width="stretch"):
                        st.session_state.watchlist, changed = md.upsert_watchlist_market(st.session_state.watchlist, selected_position.to_dict())
                        if changed:
                            save_local_list("watchlist.json", st.session_state.watchlist)
                            st.success("Position market added to tracked markets.")
                        st.rerun()
                    venue_url = str(selected_position.get("url", "") or "")
                    if venue_url:
                        position_action_cols[2].link_button("Open venue", venue_url, width="stretch")
    with tabs[1]:
        insight_cols = st.columns(6)
        insight_cols[0].metric("Win rate", pct(insights["win_rate"]) if insights["win_rate"] is not None else "-")
        insight_cols[1].metric("Contrarian", pct(insights["contrarian"]) if insights["contrarian"] is not None else "-")
        insight_cols[2].metric("Trend follower", pct(insights["trend_follower"]) if insights["trend_follower"] is not None else "-")
        insight_cols[3].metric("Lottery ticket", pct(insights["lottery_ticket"]) if insights["lottery_ticket"] is not None else "-")
        insight_cols[4].metric("Whale splash", pct(insights["whale_splash"]) if insights["whale_splash"] is not None else "-")
        insight_cols[5].metric("Exposure", pct(insights["exposure"]) if insights["exposure"] is not None else "-")
        behavior = pd.DataFrame(
            [
                {"metric": "Contrarian", "share": insights["contrarian"]},
                {"metric": "Trend follower", "share": insights["trend_follower"]},
                {"metric": "Lottery ticket", "share": insights["lottery_ticket"]},
                {"metric": "Whale splash", "share": insights["whale_splash"]},
                {"metric": "Exposure", "share": insights["exposure"]},
            ]
        ).dropna()
        if not behavior.empty:
            fig = px.bar(behavior, x="metric", y="share", template="plotly_dark", color="metric")
            fig.update_layout(height=260, margin=dict(l=10, r=10, t=15, b=10), paper_bgcolor=BG, plot_bgcolor=BG, showlegend=False, yaxis_tickformat=".0%")
            st.plotly_chart(fig, width="stretch", config=plot_config())
        if not open_positions.empty:
            concentration = open_positions.copy()
            concentration["value"] = numeric_col(concentration, "value")
            concentration = concentration.sort_values("value", ascending=False).head(15)
            st.dataframe(
                clean_table(concentration, ["title", "outcome", "value", "unrealized_pnl", "pnl_pct", "url"]),
                width="stretch",
                height=320,
                column_config={
                    "value": st.column_config.NumberColumn("Value", format="$%.2f"),
                    "unrealized_pnl": st.column_config.NumberColumn("U PnL", format="$%.2f"),
                    "pnl_pct": st.column_config.NumberColumn("PnL %", format="%.2%"),
                    "url": st.column_config.LinkColumn("URL"),
                },
            )
        elif behavior.empty:
            draw_empty("No wallet insight data returned.")
    with tabs[2]:
        if open_positions.empty:
            draw_empty("No open positions returned.")
        else:
            st.dataframe(
                clean_table(open_positions, ["title", "outcome", "size", "avg_price", "current_price", "value", "unrealized_pnl", "pnl_pct", "end_time", "url"]),
                width="stretch",
                height=420,
                column_config={"url": st.column_config.LinkColumn("URL")},
            )
    with tabs[3]:
        if closed_positions.empty:
            draw_empty("No closed positions returned.")
        else:
            fig = px.histogram(closed_positions, x="realized_pnl", nbins=30, template="plotly_dark")
            fig.update_traces(marker_color=ACCENT)
            fig.update_layout(height=260, margin=dict(l=10, r=10, t=20, b=10), paper_bgcolor=BG, plot_bgcolor=BG)
            st.plotly_chart(fig, width="stretch", config=plot_config())
            st.dataframe(
                clean_table(closed_positions, ["time", "title", "outcome", "avg_price", "current_price", "total_bought", "realized_pnl", "url"]),
                width="stretch",
                height=360,
                column_config={"url": st.column_config.LinkColumn("URL")},
            )
    with tabs[4]:
        if trades.empty:
            draw_empty("No recent trades returned.")
        else:
            st.dataframe(clean_table(trades, ["time", "side", "outcome", "title", "price", "size", "notional", "url"]), width="stretch", height=420)
    with tabs[5]:
        if activity.empty:
            draw_empty("No wallet activity returned.")
        else:
            act = activity.copy()
            act["time"] = pd.to_datetime(act.get("time"), utc=True, errors="coerce")
            act["notional"] = pd.to_numeric(act.get("notional", 0), errors="coerce").fillna(0.0)
            act["price"] = pd.to_numeric(act.get("price", 0), errors="coerce").fillna(0.0)
            act["size"] = pd.to_numeric(act.get("size", 0), errors="coerce").fillna(0.0)
            if "type_code" not in act:
                act["type_code"] = "[" + act.get("type", pd.Series("", index=act.index)).fillna("").astype(str).str[:1].str.upper().replace("", "?") + "]"
            counterparty_tape = safe_load("Public counterparty tape", load_polymarket_trades, 500, 0.0, None, None, default=pd.DataFrame())
            act = enrich_activity_counterparties(act, counterparty_tape, wallet)
            af1, af2, af3, af4, af5 = st.columns([1.5, 1, 1, 1, 1])
            type_options = sorted([item for item in act.get("type", pd.Series(dtype=str)).dropna().astype(str).unique().tolist() if item])
            side_options = sorted([item for item in act.get("side", pd.Series(dtype=str)).dropna().astype(str).unique().tolist() if item])
            activity_search_key = f"wallet_activity_search_{wallet_key}"
            activity_type_key = f"wallet_activity_type_{wallet_key}"
            activity_side_key = f"wallet_activity_side_{wallet_key}"
            activity_min_key = f"wallet_activity_min_{wallet_key}"
            activity_rows_key = f"wallet_activity_rows_{wallet_key}"
            pending_activity_clear = st.session_state.pop(f"wallet_act_{wallet_key}_clear_pending", None)
            if isinstance(pending_activity_clear, dict):
                for key, value in pending_activity_clear.items():
                    st.session_state[key] = value
            activity_query = af1.text_input("Activity search", placeholder="market or outcome", key=activity_search_key)
            selected_types = af2.multiselect("Activity type", type_options, default=type_options, key=activity_type_key)
            selected_sides = af3.multiselect("Activity side", side_options, default=side_options, key=activity_side_key)
            min_activity_notional = af4.number_input("Min activity notional", min_value=0, step=100, key=activity_min_key)
            activity_rows = af5.slider("Activity rows", min_value=25, max_value=250, step=25, key=activity_rows_key)
            if st.button("Reset activity filters", key=f"wallet_activity_reset_{wallet_key}", width="stretch"):
                st.session_state[f"wallet_act_{wallet_key}_clear_pending"] = {
                    activity_search_key: "",
                    activity_type_key: type_options,
                    activity_side_key: side_options,
                    activity_min_key: 0,
                    activity_rows_key: 100,
                }
                st.rerun()

            filtered_activity = filter_text(act, activity_query)
            if selected_types and "type" in filtered_activity:
                filtered_activity = filtered_activity[filtered_activity["type"].astype(str).isin(selected_types)]
            if selected_sides and "side" in filtered_activity:
                filtered_activity = filtered_activity[filtered_activity["side"].astype(str).isin(selected_sides)]
            filtered_activity = filtered_activity[numeric_col(filtered_activity, "notional") >= float(min_activity_notional)]
            filtered_activity = filtered_activity.sort_values("time", ascending=False, na_position="last").head(int(activity_rows)).reset_index(drop=True)
            activity_stats = wallet_activity_summary(filtered_activity)
            ac1, ac2, ac3, ac4, ac5 = st.columns(5)
            ac1.metric("Activity events", f"{int(activity_stats['events']):,}")
            ac2.metric("Activity notional", money(activity_stats["notional"]))
            ac3.metric("Buys", f"{int(activity_stats['buys']):,}")
            ac4.metric("Sells", f"{int(activity_stats['sells']):,}")
            ac5.metric("Settlements", f"{int(activity_stats['settlements']):,}")
            chips = [f"Rows: {activity_rows}"]
            if activity_query.strip():
                chips.append(f"Search: {activity_query.strip()}")
            if selected_types and set(selected_types) != set(type_options):
                chips.append("Type: " + ", ".join(selected_types))
            if selected_sides and set(selected_sides) != set(side_options):
                chips.append("Side: " + ", ".join(selected_sides))
            if min_activity_notional:
                chips.append(f"Min notional: {money(min_activity_notional)}")
            render_filter_chips(chips)
            activity_clear_actions: list[tuple[str, dict[str, Any]]] = []
            if int(activity_rows) != 100:
                activity_clear_actions.append(("rows", {activity_rows_key: 100}))
            if activity_query.strip():
                activity_clear_actions.append(("search", {activity_search_key: ""}))
            if set(selected_types) != set(type_options):
                activity_clear_actions.append(("type", {activity_type_key: type_options}))
            if set(selected_sides) != set(side_options):
                activity_clear_actions.append(("side", {activity_side_key: side_options}))
            if int(min_activity_notional) > 0:
                activity_clear_actions.append(("notional", {activity_min_key: 0}))
            render_filter_clear_buttons(activity_clear_actions, f"wallet_act_{wallet_key}")
            if filtered_activity.empty:
                draw_empty("No wallet activity matches the current filters.")
            else:
                chart = filtered_activity.copy()
                chart["bucket"] = chart["time"].dt.floor("h")
                by_type = chart.groupby(["bucket", "type"], dropna=False, as_index=False)["notional"].sum()
                if not by_type.empty:
                    fig = px.bar(by_type, x="bucket", y="notional", color="type", template="plotly_dark")
                    fig.update_layout(height=260, margin=dict(l=10, r=10, t=15, b=10), paper_bgcolor=BG, plot_bgcolor=BG, xaxis_title="", yaxis_title="notional")
                    st.plotly_chart(fig, width="stretch", config=plot_config())
                export = clean_table(filtered_activity, ["time", "title", "type_code", "type", "side", "outcome", "price", "notional", "size", "counterparty", "counterparty_confidence", "counterparty_time_delta_sec", "counterparty_wallet", "transactionHash", "url"])
                st.download_button("Export wallet activity CSV", export.to_csv(index=False).encode("utf-8"), file_name="wallet_activity.csv", mime="text/csv")
                if "counterparty_wallet" in export:
                    export["counterparty_url"] = export["counterparty_wallet"].astype(str).map(lambda value: f"https://polymarket.com/profile/{value}" if value.startswith("0x") else "")
                    export["counterparty_wallet"] = export["counterparty_wallet"].astype(str).map(short_addr)
                if "counterparty_confidence" in export:
                    export["counterparty_confidence_pct"] = pd.to_numeric(export["counterparty_confidence"], errors="coerce").fillna(0.0) * 100.0
                if "transactionHash" in export:
                    export["tx_url"] = export["transactionHash"].astype(str).map(lambda value: f"https://polygonscan.com/tx/{value}" if value.startswith("0x") else "")
                    export["transactionHash"] = export["transactionHash"].astype(str).map(short_addr)
                st.dataframe(
                    clean_table(export, ["time", "title", "type_code", "side", "outcome", "price", "notional", "size", "counterparty", "counterparty_confidence_pct", "counterparty_time_delta_sec", "counterparty_wallet", "counterparty_url", "transactionHash", "tx_url", "url"]),
                    width="stretch",
                    height=430,
                    column_config={
                        "title": st.column_config.TextColumn("Market", width="large"),
                        "type_code": st.column_config.TextColumn("Type"),
                        "price": st.column_config.NumberColumn(format="%.4f"),
                        "size": st.column_config.NumberColumn("Shares", format="%.2f"),
                        "notional": st.column_config.NumberColumn("Amount", format="$%.2f"),
                        "counterparty": st.column_config.TextColumn("Counterparty"),
                        "counterparty_confidence_pct": st.column_config.ProgressColumn("Counterparty confidence", format="%.0f%%", min_value=0, max_value=100),
                        "counterparty_time_delta_sec": st.column_config.NumberColumn("Match lag", format="%.1fs"),
                        "counterparty_url": st.column_config.LinkColumn("Counterparty URL"),
                        "tx_url": st.column_config.LinkColumn("TX"),
                        "url": st.column_config.LinkColumn("Market URL"),
                    },
                )
                actionable_activity = filtered_activity.head(120).copy()
                if not actionable_activity.empty:
                    action_options = [
                        (
                            f"{idx + 1}. {str(row.get('type', row.get('side', '-')) or '-')} "
                            f"{str(row.get('side', '') or '')} | {money(row.get('notional', 0.0))} | "
                            f"{str(row.get('title', '-'))[:90]}"
                        )
                        for idx, (_, row) in enumerate(actionable_activity.iterrows())
                    ]
                    selected_activity_action = st.selectbox(
                        "Activity row action",
                        action_options,
                        key=f"wallet_activity_row_action_{wallet_key}",
                    )
                    activity_row = actionable_activity.iloc[action_options.index(selected_activity_action)]
                    activity_market_key = str(activity_row.get("market_key", "") or "")
                    activity_title = str(activity_row.get("title", "") or "")
                    counterparty_wallet = str(activity_row.get("counterparty_wallet", "") or "")
                    tx_hash = str(activity_row.get("transactionHash", "") or "")
                    activity_cols = st.columns([1, 1, 1, 1, 2])
                    if activity_cols[0].button(
                        "Open activity market",
                        key=f"wallet_open_activity_market_{wallet_key}",
                        width="stretch",
                        disabled=not bool(activity_market_key),
                    ):
                        st.session_state["markets_inspect_market_key"] = activity_market_key
                        st.session_state["markets_activity_event_url"] = str(activity_row.get("url", "") or "")
                        queue_navigation("Markets", activity_title)
                        st.rerun()
                    if re.fullmatch(r"0x[a-fA-F0-9]{40}", counterparty_wallet):
                        if activity_cols[1].button("Track counterparty", key=f"wallet_track_counterparty_{wallet_key}", width="stretch"):
                            st.session_state.followed_wallets, changed = md.upsert_followed_wallet(
                                st.session_state.followed_wallets,
                                counterparty_wallet,
                            )
                            if changed:
                                save_local_list("followed_wallets.json", st.session_state.followed_wallets)
                                st.success("Counterparty wallet added to tracked wallets.")
                            st.rerun()
                        activity_cols[2].link_button("Open counterparty", f"https://polymarket.com/profile/{counterparty_wallet}", width="stretch")
                    else:
                        activity_cols[1].button("Track counterparty", key=f"wallet_track_counterparty_disabled_{wallet_key}", width="stretch", disabled=True)
                        activity_cols[2].button("Open counterparty", key=f"wallet_open_counterparty_disabled_{wallet_key}", width="stretch", disabled=True)
                    if tx_hash.startswith("0x"):
                        activity_cols[3].link_button("Open tx", f"https://polygonscan.com/tx/{tx_hash}", width="stretch")
                    else:
                        activity_cols[3].button("Open tx", key=f"wallet_open_activity_tx_disabled_{wallet_key}", width="stretch", disabled=True)


def page_traders() -> None:
    section_header("Traders", "Parity-style trader leaderboard with search, view modes, PnL/volume/position filters, and wallet drilldown.")
    if "trader_search" not in st.session_state:
        reset_trader_filter_widgets(global_query)
    if st.session_state.pop("trader_filters_reset_pending", False):
        reset_trader_filter_widgets(global_query)
    route_filter_params = query_param_snapshot(
        [
            "bot",
            "bots",
            "botLike",
            "botScoreMin",
            "botMin",
            "apMin",
            "activePositionsMin",
            "active_positions_min",
            "pnlMin",
            "profitMin",
            "minPnl",
            "volMin",
            "volumeMin",
            "minVolume",
            "q",
            "query",
            "search",
            "period",
            "timePeriod",
            "orderBy",
            "sort",
            "rankBy",
            "rows",
            "limit",
        ]
    )
    route_filter_signature = json.dumps(route_filter_params, sort_keys=True)
    route_filter_view = md.predictparity_trader_filter_view(route_filter_params)
    if route_filter_view and st.session_state.get("traders_route_filter_signature") != route_filter_signature:
        apply_trader_filter_view_widgets(route_filter_view)
        st.session_state["traders_route_filter_signature"] = route_filter_signature
        st.session_state["trader_view_loaded_message"] = "Loaded trader filters from URL."
    pending_trader_view = st.session_state.pop("pending_trader_filter_view", None)
    if isinstance(pending_trader_view, dict):
        apply_trader_filter_view_widgets(pending_trader_view)
    pending_trader_clear = st.session_state.pop("traders_clear_pending", None)
    if isinstance(pending_trader_clear, dict):
        for key, value in pending_trader_clear.items():
            st.session_state[key] = value

    top = st.columns([2.2, 1.1, 1, 0.8, 0.8, 1.05, 1.05, 1])
    trader_query = top[0].text_input("Search Name or Wallet", placeholder="Search Name or Wallet", key="trader_search")
    view_mode = top[1].radio("View", ["Table", "List", "Card"], horizontal=True, label_visibility="collapsed", key="trader_view_mode")
    column_preset = top[2].selectbox("Columns", ["Parity", "Research", "Flow"], key="trader_column_preset")
    active_only = top[3].toggle("Active", key="trader_active_only")
    bots_only = top[4].toggle("Bots", key="trader_bots_only", help="Show only bot-like wallets by the current recent-flow bot score.")
    time_period = top[5].selectbox("Period", ["ALL", "MONTH", "WEEK", "DAY"], key="trader_time_period")
    order_by = top[6].selectbox("Rank by", ["PNL", "VOL"], key="trader_order_by")
    rows = top[7].slider("Rows", min_value=25, max_value=250, step=25, key="trader_rows")

    with st.expander("Filter", expanded=True):
        f1, f2, f3, f4 = st.columns(4)
        pnl_preset = f1.radio("PnL", ["All", ">$500k", ">$1m", ">$2m", "> -$10k", "> -$100k", "> -$500k", "Custom"], horizontal=True, key="trader_pnl_preset")
        custom_pnl = f1.number_input("Custom min PnL", min_value=-10_000_000, max_value=50_000_000, step=10_000, disabled=pnl_preset != "Custom", key="trader_custom_pnl")
        volume_preset = f2.radio("Volume", ["All", ">$10k", ">$100k", ">$1m", "Custom"], horizontal=True, key="trader_volume_preset")
        custom_volume = f2.number_input("Custom min volume", min_value=0, step=10_000, disabled=volume_preset != "Custom", key="trader_custom_volume")
        position_preset = f3.radio("Positions", ["All", ">$100", ">$10k", ">$100k", "Custom"], horizontal=True, key="trader_position_preset")
        custom_position = f3.number_input("Custom min open value", min_value=0, step=1_000, disabled=position_preset != "Custom", key="trader_custom_position")
        active_positions_min = f3.number_input("Min active positions", min_value=0, max_value=100000, step=1, key="trader_active_positions_min")
        trait_filter = f4.multiselect("Traits", ["Whales", "Bot-like", "Verified"], key="trader_trait_filter")
        bot_score_min = f4.slider("Bot score min", min_value=0, max_value=100, step=5, disabled=not (bots_only or "Bot-like" in trait_filter), key="trader_bot_score_min")
        enrich_positions = f4.checkbox("Fetch open positions", key="trader_enrich_positions")
        w1, w2, w3 = st.columns([1.1, 1.1, 2.8])
        win_rate_preset = w1.radio("Win rate", ["All", ">50%", ">70%", "Custom"], horizontal=True, key="trader_win_rate_preset")
        custom_win_rate = w1.number_input("Custom min win rate %", min_value=0, max_value=100, step=5, disabled=win_rate_preset != "Custom", key="trader_custom_win_rate")
        enrich_win_rates = w2.checkbox("Fetch win rates", key="trader_enrich_win_rates")
        min_closed_positions = w2.number_input("Min closed", min_value=0, max_value=500, step=5, key="trader_min_closed_positions")
        a1, a2, a3, a4 = st.columns([1.1, 1.1, 1.1, 1.7])
        assets_preset = a1.radio("Assets", ["All", ">$100k", ">$1m", ">$2m", "Custom"], horizontal=True, key="trader_assets_preset")
        custom_assets = a1.number_input("Custom min assets", min_value=0, step=10_000, disabled=assets_preset != "Custom", key="trader_custom_assets")
        balance_preset = a2.radio("Balance", ["All", ">$1k", ">$10k", ">$100k", "Custom"], horizontal=True, key="trader_balance_preset")
        custom_balance = a2.number_input("Custom min balance", min_value=0, step=1_000, disabled=balance_preset != "Custom", key="trader_custom_balance")
        account_age_preset = a3.radio("Account age", ["All", "<14d", ">365d", "Custom"], horizontal=True, key="trader_account_age_preset")
        custom_account_age = a3.number_input("Custom min account age days", min_value=1, step=30, disabled=account_age_preset != "Custom", key="trader_custom_account_age")
        enrich_accounts = a4.checkbox("Fetch balances + account age", key="trader_enrich_accounts")
        account_enrich_rows = a4.slider("Account stat wallets", min_value=5, max_value=30, step=5, help="Limits slower balance and activity-age calls.", key="trader_account_enrich_rows")
        action_cols = st.columns([1, 1, 4])
        save_trader_clicked = action_cols[0].button("Save Filter", width="stretch", key="save_trader_filter_button")
        if action_cols[1].button("Reset Filters", width="stretch", key="reset_trader_filters_button"):
            st.session_state["trader_filters_reset_pending"] = True
            st.rerun()

    saved_trader_name = st.text_input("Saved trader view name", value=f"Traders {md.now_utc_label()}", key="saved_trader_view_name")
    loaded_trader_message = st.session_state.pop("trader_view_loaded_message", "")
    if loaded_trader_message:
        st.info(loaded_trader_message)
    if st.session_state.saved_trader_filters:
        load_cols = st.columns([2, 1, 1])
        saved_labels = [
            f"{i + 1}. {view.get('name') or view.get('query') or 'Trader view'}"
            for i, view in enumerate(st.session_state.saved_trader_filters)
        ]
        selected_saved_trader = load_cols[0].selectbox("Load saved trader view", saved_labels, key="load_saved_trader_view")
        selected_trader_view = st.session_state.saved_trader_filters[saved_labels.index(selected_saved_trader)]
        if load_cols[1].button("Load trader view", key="load_trader_view_button"):
            st.session_state["pending_trader_filter_view"] = selected_trader_view
            st.session_state["trader_view_loaded_message"] = f"Loaded saved trader view: {selected_trader_view.get('name', selected_saved_trader)}"
            st.rerun()
        if load_cols[2].button("Delete trader view", key="delete_trader_view_button"):
            st.session_state.saved_trader_filters.pop(saved_labels.index(selected_saved_trader))
            save_local_list("saved_trader_filters.json", st.session_state.saved_trader_filters)
            st.rerun()
    if save_trader_clicked:
        st.session_state.saved_trader_filters.append(
            {
                "name": saved_trader_name.strip() or f"Traders {md.now_utc_label()}",
                "created_at": md.now_utc_label(),
                "query": trader_query,
                "view_mode": view_mode,
                "column_preset": column_preset,
                "period": time_period,
                "rank_by": order_by,
                "rows": int(rows),
                "active_only": bool(active_only),
                "bots_only": bool(bots_only),
                "bot_score_min": int(bot_score_min),
                "pnl_preset": pnl_preset,
                "custom_pnl": float(custom_pnl),
                "volume_preset": volume_preset,
                "custom_volume": float(custom_volume),
                "position_preset": position_preset,
                "custom_position": float(custom_position),
                "active_positions_min": int(active_positions_min),
                "trait_filter": trait_filter,
                "enrich_positions": bool(enrich_positions),
                "win_rate": win_rate_preset,
                "custom_win_rate": float(custom_win_rate),
                "enrich_win_rates": bool(enrich_win_rates),
                "min_closed_positions": int(min_closed_positions),
                "assets_preset": assets_preset,
                "custom_assets": float(custom_assets),
                "balance_preset": balance_preset,
                "custom_balance": float(custom_balance),
                "account_age_preset": account_age_preset,
                "custom_account_age": int(custom_account_age),
                "enrich_accounts": bool(enrich_accounts),
                "account_enrich_rows": int(account_enrich_rows),
            }
        )
        save_local_list("saved_trader_filters.json", st.session_state.saved_trader_filters)
        st.success("Saved trader view.")

    leaderboard = safe_load("Polymarket leaderboard", load_leaderboard, rows, time_period, order_by)
    recent_flow = safe_load("Recent Polymarket trader flow", load_polymarket_trades, 500, 0.0, None, None)
    flow_scores = md.trader_flow_scores(recent_flow, whale_threshold=float(min_whale))
    if not leaderboard.empty and not flow_scores.empty:
        leaderboard = leaderboard.merge(
            clean_table(
                flow_scores,
                ["wallet", "recent_trades", "recent_notional", "avg_trade", "largest_trade", "markets", "trades_per_hour", "whale_score", "bot_score", "flow_trait"],
            ),
            on="wallet",
            how="left",
        )
    if not leaderboard.empty:
        for col in ["recent_trades", "recent_notional", "avg_trade", "largest_trade", "markets", "trades_per_hour", "whale_score", "bot_score"]:
            if col not in leaderboard:
                leaderboard[col] = 0
        leaderboard[
            ["recent_trades", "recent_notional", "avg_trade", "largest_trade", "markets", "trades_per_hour", "whale_score", "bot_score"]
        ] = leaderboard[
            ["recent_trades", "recent_notional", "avg_trade", "largest_trade", "markets", "trades_per_hour", "whale_score", "bot_score"]
        ].fillna(0)
        if "flow_trait" not in leaderboard:
            leaderboard["flow_trait"] = "Leaderboard"
        else:
            leaderboard["flow_trait"] = leaderboard["flow_trait"].fillna("Leaderboard")
        leaderboard["pnl_per_volume"] = leaderboard["pnl"] / leaderboard["volume"].replace({0: pd.NA})
        leaderboard = option_metric_filter(leaderboard, "pnl", pnl_preset, float(custom_pnl))
        leaderboard = option_metric_filter(leaderboard, "volume", volume_preset, float(custom_volume))
        leaderboard = md.apply_trader_trait_filters(
            leaderboard,
            trait_filter=trait_filter,
            bots_only=bool(bots_only),
            bot_score_min=float(bot_score_min),
        )
    has_native_parity_stats = (
        not leaderboard.empty
        and "source" in leaderboard
        and leaderboard["source"].astype(str).eq("PredictParity").any()
    )
    has_native_positions = has_native_parity_stats and "positions_value" in leaderboard
    has_native_win_rates = has_native_parity_stats and "win_rate" in leaderboard
    has_native_account_stats = has_native_parity_stats and {"cash_balance", "account_age_days"}.issubset(set(leaderboard.columns))
    if not leaderboard.empty and enrich_positions and not has_native_positions:
        wallets = tuple(leaderboard["wallet"].astype(str).head(min(30, len(leaderboard))).tolist())
        position_values = safe_load("Leaderboard open positions", load_wallet_position_values, wallets, default=pd.DataFrame())
        if not position_values.empty:
            leaderboard = md.merge_profile_position_values(leaderboard, position_values)
    if not leaderboard.empty:
        if "positions_value" not in leaderboard:
            leaderboard["positions_value"] = 0.0
        if "open_positions" not in leaderboard:
            leaderboard["open_positions"] = 0
        if "open_markets" not in leaderboard:
            leaderboard["open_markets"] = 0
        leaderboard[["positions_value", "open_positions", "open_markets"]] = leaderboard[["positions_value", "open_positions", "open_markets"]].fillna(0)
        if active_only:
            leaderboard = leaderboard[(leaderboard["positions_value"] > 0) | (leaderboard["recent_trades"].fillna(0) > 0)]
        if int(active_positions_min) > 0:
            leaderboard = leaderboard[pd.to_numeric(leaderboard["open_positions"], errors="coerce").fillna(0).astype(int) >= int(active_positions_min)]
        leaderboard = option_metric_filter(leaderboard, "positions_value", position_preset, float(custom_position))
    account_stats_needed = enrich_accounts or assets_preset != "All" or balance_preset != "All" or account_age_preset != "All"
    if not leaderboard.empty and account_stats_needed and not has_native_account_stats:
        wallets = tuple(leaderboard["wallet"].astype(str).head(min(int(account_enrich_rows), len(leaderboard))).tolist())
        account_stats = safe_load("Leaderboard balances and account ages", load_wallet_account_stats, wallets, 3, True, default=pd.DataFrame())
        if not account_stats.empty:
            leaderboard = leaderboard.merge(account_stats, on="wallet", how="left")
    if not leaderboard.empty:
        if "cash_balance" not in leaderboard:
            leaderboard["cash_balance"] = 0.0
        if "account_age_days" not in leaderboard:
            leaderboard["account_age_days"] = pd.NA
        if "activity_observations" not in leaderboard:
            leaderboard["activity_observations"] = 0
        leaderboard[["cash_balance", "activity_observations"]] = leaderboard[["cash_balance", "activity_observations"]].fillna(0)
        leaderboard["assets_value"] = numeric_col(leaderboard, "positions_value") + numeric_col(leaderboard, "cash_balance")
        leaderboard = option_metric_filter(leaderboard, "assets_value", assets_preset, float(custom_assets))
        leaderboard = option_metric_filter(leaderboard, "cash_balance", balance_preset, float(custom_balance))
        leaderboard = apply_account_age_filter(leaderboard, account_age_preset, int(custom_account_age))
    if not leaderboard.empty and enrich_win_rates and not has_native_win_rates:
        wallets = tuple(leaderboard["wallet"].astype(str).head(min(30, len(leaderboard))).tolist())
        win_rates = safe_load("Leaderboard win rates", load_wallet_win_rates, wallets, default=pd.DataFrame())
        if not win_rates.empty:
            leaderboard = leaderboard.merge(win_rates, on="wallet", how="left")
    if not leaderboard.empty:
        for col, default in {
            "win_rate": pd.NA,
            "closed_positions": 0,
            "winning_positions": 0,
            "closed_realized_pnl": 0.0,
        }.items():
            if col not in leaderboard:
                leaderboard[col] = default
        leaderboard[["closed_positions", "winning_positions", "closed_realized_pnl"]] = leaderboard[
            ["closed_positions", "winning_positions", "closed_realized_pnl"]
        ].fillna(0)
        if win_rate_preset != "All":
            threshold = (float(custom_win_rate) if win_rate_preset == "Custom" else float(win_rate_preset.replace(">", "").replace("%", ""))) / 100
            leaderboard = leaderboard[
                (numeric_col(leaderboard, "win_rate", -1.0) >= threshold)
                & (numeric_col(leaderboard, "closed_positions") >= float(min_closed_positions))
            ]
    leaderboard = filter_text(leaderboard, trader_query)
    if leaderboard.empty:
        draw_empty("No leaderboard data returned.")
        return
    metric_cols = st.columns(6)
    metric_cols[0].metric("Traders", f"{len(leaderboard):,}")
    metric_cols[1].metric("Total PnL", money(leaderboard["pnl"].sum() if "pnl" in leaderboard else 0))
    metric_cols[2].metric("Volume", money(leaderboard["volume"].sum() if "volume" in leaderboard else 0))
    metric_cols[3].metric("Open positions", money(leaderboard["positions_value"].sum() if "positions_value" in leaderboard else 0))
    known_win_rates = pd.to_numeric(leaderboard.get("win_rate", pd.Series(dtype="float64")), errors="coerce").dropna()
    metric_cols[4].metric("Median win rate", pct(known_win_rates.median()) if not known_win_rates.empty else "-")
    metric_cols[5].metric("Verified", f"{int(leaderboard['verified'].astype(bool).sum()) if 'verified' in leaderboard else 0:,}")
    if "source" in leaderboard and leaderboard["source"].astype(str).eq("PredictParity").any():
        st.caption("Trader leaderboard sourced from PredictParity public trader data with Polymarket fallback for unavailable periods.")
    trader_chips: list[str] = []
    if trader_query.strip():
        trader_chips.append(f"Search: {trader_query.strip()}")
    trader_chips.extend([f"View: {view_mode}", f"Columns: {column_preset}", f"Period: {time_period}", f"Rank by: {order_by}", f"Rows: {rows}"])
    if active_only:
        trader_chips.append("Active")
    if bots_only:
        trader_chips.append(f"Bots: score >= {int(bot_score_min)}")
    if pnl_preset != "All":
        trader_chips.append(f"PnL: {pnl_preset if pnl_preset != 'Custom' else '>$' + f'{custom_pnl:,.0f}'}")
    if volume_preset != "All":
        trader_chips.append(f"Volume: {volume_preset if volume_preset != 'Custom' else '>$' + f'{custom_volume:,.0f}'}")
    if position_preset != "All":
        trader_chips.append(f"Positions: {position_preset if position_preset != 'Custom' else '>$' + f'{custom_position:,.0f}'}")
    if int(active_positions_min) > 0:
        trader_chips.append(f"Active positions >= {int(active_positions_min)}")
    if assets_preset != "All":
        trader_chips.append(f"Assets: {assets_preset if assets_preset != 'Custom' else '>$' + f'{custom_assets:,.0f}'}")
    if balance_preset != "All":
        trader_chips.append(f"Balance: {balance_preset if balance_preset != 'Custom' else '>$' + f'{custom_balance:,.0f}'}")
    if account_age_preset != "All":
        trader_chips.append(f"Account age: {account_age_preset if account_age_preset != 'Custom' else '>' + str(custom_account_age) + 'd'}")
    if win_rate_preset != "All":
        trader_chips.append(f"Win rate: {win_rate_preset if win_rate_preset != 'Custom' else f'>{custom_win_rate:.0f}%'}")
    if trait_filter:
        trader_chips.append("Traits: " + ", ".join(trait_filter))
    if enrich_positions:
        trader_chips.append("Open positions enriched")
    if enrich_win_rates:
        trader_chips.append(f"Win rates enriched, min closed {min_closed_positions}")
    if account_stats_needed:
        trader_chips.append(f"Balance/account age enriched: {account_enrich_rows} wallets")
    render_filter_chips(trader_chips)
    trader_defaults = trader_filter_defaults()
    trader_clear_actions: list[tuple[str, dict[str, Any]]] = []
    if trader_query.strip():
        trader_clear_actions.append(("search", {"trader_search": ""}))
    if view_mode != trader_defaults["trader_view_mode"]:
        trader_clear_actions.append(("view", {"trader_view_mode": trader_defaults["trader_view_mode"]}))
    if column_preset != trader_defaults["trader_column_preset"]:
        trader_clear_actions.append(("columns", {"trader_column_preset": trader_defaults["trader_column_preset"]}))
    if time_period != trader_defaults["trader_time_period"]:
        trader_clear_actions.append(("period", {"trader_time_period": trader_defaults["trader_time_period"]}))
    if order_by != trader_defaults["trader_order_by"]:
        trader_clear_actions.append(("rank", {"trader_order_by": trader_defaults["trader_order_by"]}))
    if int(rows) != int(trader_defaults["trader_rows"]):
        trader_clear_actions.append(("rows", {"trader_rows": trader_defaults["trader_rows"]}))
    if active_only:
        trader_clear_actions.append(("active", {"trader_active_only": False}))
    if bots_only:
        trader_clear_actions.append(("bots", {"trader_bots_only": False}))
    if int(bot_score_min) != int(trader_defaults["trader_bot_score_min"]):
        trader_clear_actions.append(("bot score", {"trader_bot_score_min": trader_defaults["trader_bot_score_min"]}))
    if pnl_preset != "All":
        trader_clear_actions.append(("pnl", {"trader_pnl_preset": "All"}))
    if volume_preset != "All":
        trader_clear_actions.append(("volume", {"trader_volume_preset": "All"}))
    if position_preset != "All":
        trader_clear_actions.append(("positions", {"trader_position_preset": "All"}))
    if int(active_positions_min) > 0:
        trader_clear_actions.append(("active positions", {"trader_active_positions_min": 0}))
    if assets_preset != "All":
        trader_clear_actions.append(("assets", {"trader_assets_preset": "All"}))
    if balance_preset != "All":
        trader_clear_actions.append(("balance", {"trader_balance_preset": "All"}))
    if account_age_preset != "All":
        trader_clear_actions.append(("account age", {"trader_account_age_preset": "All"}))
    if win_rate_preset != "All":
        trader_clear_actions.append(("win rate", {"trader_win_rate_preset": "All"}))
    if trait_filter:
        trader_clear_actions.append(("traits", {"trader_trait_filter": []}))
    if enrich_accounts:
        trader_clear_actions.append(("account enrichment", {"trader_enrich_accounts": False}))
    render_filter_clear_buttons(trader_clear_actions, "traders")
    if st.session_state.saved_trader_filters:
        st.caption(f"Saved trader views: {len(st.session_state.saved_trader_filters)}")
        with st.expander("Saved trader filters", expanded=False):
            st.dataframe(pd.DataFrame(st.session_state.saved_trader_filters), width="stretch", height=160)
            if st.button("Clear saved trader filters"):
                st.session_state.saved_trader_filters = []
                save_local_list("saved_trader_filters.json", st.session_state.saved_trader_filters)
                st.rerun()
    if enrich_positions and has_native_positions:
        st.caption("Open-position values are sourced from PredictParity's public trader leaderboard.")
    elif enrich_positions:
        st.caption("Open-position values are fetched from public Polymarket wallet positions for the first 30 displayed leaderboard wallets.")
    if enrich_win_rates and has_native_win_rates:
        st.caption("Win rates are sourced from PredictParity's public trader leaderboard.")
    elif enrich_win_rates:
        st.caption("Win rates are estimated from public closed positions for the first 30 displayed leaderboard wallets.")
    if account_stats_needed and has_native_account_stats:
        st.caption("Balances and account age are sourced from PredictParity's public trader leaderboard.")
    elif account_stats_needed:
        st.caption("Assets are open-position value plus fetched Polygon USDC balance. Account age is the oldest public activity observed in the loaded activity pages.")

    display = leaderboard.copy()
    display["wallet_short"] = display["wallet"].astype(str).map(short_addr)
    display["profile_url"] = display["wallet"].astype(str).map(md.polymarket_profile_url)
    display["x_url"] = display.get("x_username", pd.Series("", index=display.index)).astype(str).map(x_profile_url)
    parity_handles = display.get("username", display.get("trader", pd.Series("", index=display.index))).astype(str)
    display["parity_url"] = parity_handles.map(predictparity_trader_url)
    missing_parity_url = display["parity_url"].astype(str).eq("")
    if missing_parity_url.any():
        display.loc[missing_parity_url, "parity_url"] = display.loc[missing_parity_url, "trader"].astype(str).map(predictparity_trader_url)
    display["trader_identity"] = (
        display["trader"].astype(str)
        + " | "
        + display.get("platform", pd.Series("Polymarket", index=display.index)).astype(str)
        + " | "
        + display["wallet_short"].astype(str)
    )
    display["win_rate_pct"] = pd.to_numeric(display.get("win_rate", pd.Series(dtype="float64")), errors="coerce") * 100
    display["account_age_display"] = pd.to_numeric(display.get("account_age_days", pd.Series(dtype="float64")), errors="coerce")
    trader_columns = [
        "trader_identity",
        "parity_url",
        "profile_url",
        "x_url",
        "pnl",
        "volume",
        "assets_value",
        "cash_balance",
        "account_age_display",
        "win_rate_pct",
        "positions_value",
        "pnl_per_volume",
        "closed_positions",
        "open_positions",
        "open_markets",
        "flow_trait",
        "recent_trades",
        "recent_notional",
        "largest_trade",
        "markets",
        "closed_realized_pnl",
        "whale_score",
        "bot_score",
        "x_username",
        "verified",
    ]
    parity_trader_columns = [
        "trader_identity",
        "pnl",
        "volume",
        "win_rate_pct",
        "positions_value",
    ]
    flow_trader_columns = [
        "trader_identity",
        "pnl",
        "volume",
        "positions_value",
        "recent_trades",
        "recent_notional",
        "largest_trade",
        "markets",
        "flow_trait",
        "whale_score",
        "bot_score",
    ]
    selected_trader_columns = {
        "Parity": parity_trader_columns,
        "Flow": flow_trader_columns,
        "Research": trader_columns,
    }.get(column_preset, parity_trader_columns)
    trader_config = {
        "trader_identity": st.column_config.TextColumn("Trader", width="large"),
        "parity_url": st.column_config.LinkColumn("Parity", display_text="Open Parity"),
        "profile_url": st.column_config.LinkColumn("Profile", display_text="Open profile"),
        "x_url": st.column_config.LinkColumn("X", display_text="X"),
        "pnl": st.column_config.NumberColumn("Total PnL", format="$%.0f"),
        "volume": st.column_config.NumberColumn("Volume", format="$%.0f"),
        "assets_value": st.column_config.NumberColumn("Assets", format="$%.0f"),
        "cash_balance": st.column_config.NumberColumn("Balance", format="$%.0f"),
        "account_age_display": st.column_config.NumberColumn("Account Age", format="%.0f d"),
        "pnl_per_volume": st.column_config.NumberColumn("PnL / Vol", format="%.2f"),
        "win_rate_pct": st.column_config.NumberColumn("Win Rate", format="%.1f%%"),
        "closed_positions": st.column_config.NumberColumn("Closed", format="%.0f"),
        "positions_value": st.column_config.NumberColumn("Positions", format="$%.0f"),
        "open_positions": st.column_config.NumberColumn("Open", format="%.0f"),
        "open_markets": st.column_config.NumberColumn("Markets", format="%.0f"),
        "closed_realized_pnl": st.column_config.NumberColumn("Closed PnL", format="$%.0f"),
        "recent_notional": st.column_config.NumberColumn(format="$%.0f"),
        "largest_trade": st.column_config.NumberColumn(format="$%.0f"),
        "whale_score": st.column_config.ProgressColumn(min_value=0, max_value=100),
        "bot_score": st.column_config.ProgressColumn(min_value=0, max_value=100),
    }
    trader_action_cols = st.columns([1.1, 1.1, 3])
    trader_action_cols[0].download_button(
        "Export traders CSV",
        clean_table(display, selected_trader_columns).to_csv(index=False).encode("utf-8"),
        file_name="traders_leaderboard.csv",
        mime="text/csv",
        width="stretch",
    )
    if trader_action_cols[1].button("Track visible traders", key="traders_track_visible", width="stretch", disabled=display.empty):
        st.session_state.followed_wallets, changed_count = md.upsert_followed_wallets(st.session_state.followed_wallets, display)
        if changed_count:
            save_local_list("followed_wallets.json", st.session_state.followed_wallets)
            st.success(f"Tracked {changed_count} visible trader wallets.")
        else:
            st.info("Visible trader wallets are already tracked.")
    trader_action_cols[2].caption(f"Actions apply to the {len(display):,} traders currently shown after filters and row limit.")
    selected_wallet_from_table = ""
    selected_trader_action_row: pd.Series | None = None
    if view_mode == "Table":
        trader_table = clean_table(display, selected_trader_columns)
        trader_table_event = st.dataframe(
            trader_table,
            width="stretch",
            height=440,
            column_config=trader_config,
            key="traders_leaderboard_table",
            on_select="rerun",
            selection_mode="single-row",
        )
        selected_trader_row = dataframe_selected_row_index(trader_table_event)
        if selected_trader_row is not None and selected_trader_row < len(display):
            selected_wallet_from_table = str(display.iloc[selected_trader_row].get("wallet", ""))
            selected_trader_action_row = display.iloc[selected_trader_row]
    elif view_mode == "List":
        trader_list = clean_table(display, selected_trader_columns)
        trader_list_event = st.dataframe(
            trader_list,
            width="stretch",
            height=520,
            column_config=trader_config,
            key="traders_leaderboard_list",
            on_select="rerun",
            selection_mode="single-row",
        )
        selected_trader_row = dataframe_selected_row_index(trader_list_event)
        if selected_trader_row is not None and selected_trader_row < len(display):
            selected_wallet_from_table = str(display.iloc[selected_trader_row].get("wallet", ""))
            selected_trader_action_row = display.iloc[selected_trader_row]
    else:
        for chunk_start in range(0, len(display.head(18)), 3):
            cols = st.columns(3)
            for col, (row_idx, row) in zip(cols, display.head(18).iloc[chunk_start : chunk_start + 3].iterrows()):
                with col:
                    with st.container(border=True):
                        wallet_value = str(row.get("wallet", "") or "")
                        safe_wallet_key = re.sub(r"[^a-zA-Z0-9_]", "_", f"{wallet_value}_{row_idx}")[:80]
                        rank_value = row.get("rank", 0)
                        rank_label = int(rank_value) if pd.notna(rank_value) else "-"
                        st.caption(f"Rank #{rank_label} | {short_addr(str(row.get('wallet', '')))}")
                        st.markdown(f"**{row.get('trader', '-')}**")
                        st.metric("PnL", money(row.get("pnl", 0.0)))
                        st.markdown(
                            f"Volume: **{money(row.get('volume', 0.0))}**  \n"
                            f"Assets: **{money(row.get('assets_value', row.get('positions_value', 0.0)))}**  \n"
                            f"Balance: **{money(row.get('cash_balance', 0.0))}**  \n"
                            f"Account age: **{int(row.get('account_age_days')) if pd.notna(row.get('account_age_days')) else '-'}d**  \n"
                            f"Win rate: **{pct(row.get('win_rate'))}**  \n"
                            f"Positions: **{money(row.get('positions_value', 0.0))}**"
                        )
                        action_cols = st.columns([1, 1, 1, 1, 1])
                        if action_cols[0].button("Open wallet", key=f"trader_card_open_{safe_wallet_key}", width="stretch", disabled=not bool(wallet_value)):
                            st.session_state["traders_inspect_wallet"] = wallet_value
                            st.rerun()
                        tracked_wallets = {str(item).lower() for item in st.session_state.followed_wallets}
                        if wallet_value.lower() in tracked_wallets:
                            action_cols[1].button("Tracked", key=f"trader_card_tracked_{safe_wallet_key}", width="stretch", disabled=True)
                        else:
                            if action_cols[1].button("Track", key=f"trader_card_track_{safe_wallet_key}", width="stretch", disabled=not bool(wallet_value)):
                                st.session_state.followed_wallets, changed = md.upsert_followed_wallet(st.session_state.followed_wallets, wallet_value)
                                if changed:
                                    save_local_list("followed_wallets.json", st.session_state.followed_wallets)
                                st.rerun()
                        parity_url = predictparity_trader_url(row.get("username", "") or row.get("trader", ""))
                        if parity_url:
                            action_cols[2].link_button("Parity", parity_url, width="stretch")
                        else:
                            action_cols[2].button("Parity", key=f"trader_card_parity_disabled_{safe_wallet_key}", width="stretch", disabled=True)
                        if re.fullmatch(r"0x[a-fA-F0-9]{40}", wallet_value):
                            action_cols[3].link_button("Polymarket", f"https://polymarket.com/profile/{wallet_value}", width="stretch")
                        else:
                            action_cols[3].button("Polymarket", key=f"trader_card_polymarket_disabled_{safe_wallet_key}", width="stretch", disabled=True)
                        x_url = x_profile_url(row.get("x_username", ""))
                        if x_url:
                            action_cols[4].link_button("X", x_url, width="stretch")
                        else:
                            action_cols[4].button("X", key=f"trader_card_x_disabled_{safe_wallet_key}", width="stretch", disabled=True)
    st.caption("Bot-like and whale scores are heuristics from the current recent-trade sample, not identity labels.")
    if selected_trader_action_row is not None:
        selected_wallet = str(selected_trader_action_row.get("wallet", "") or "")
        selected_name = str(selected_trader_action_row.get("trader", "") or short_addr(selected_wallet))
        st.markdown("### Selected trader actions")
        st.caption(
            f"{selected_name} | {short_addr(selected_wallet)} | "
            f"{money(selected_trader_action_row.get('pnl', 0.0))} PnL | "
            f"{money(selected_trader_action_row.get('positions_value', 0.0))} open"
        )
        action_cols = st.columns([1, 1, 1, 1, 1, 2])
        if action_cols[0].button("Open in Wallets", key="traders_selected_open_wallets", width="stretch", disabled=not bool(selected_wallet)):
            st.session_state["wallets_inspect_wallet"] = selected_wallet
            queue_navigation("Wallets", "")
            st.rerun()
        tracked_wallets = {str(item).lower() for item in st.session_state.followed_wallets}
        if selected_wallet.lower() in tracked_wallets:
            action_cols[1].button("Tracked", key="traders_selected_tracked", width="stretch", disabled=True)
        elif action_cols[1].button("Track selected", key="traders_selected_track", width="stretch", disabled=not bool(selected_wallet)):
            st.session_state.followed_wallets, changed = md.upsert_followed_wallet(st.session_state.followed_wallets, selected_wallet)
            if changed:
                save_local_list("followed_wallets.json", st.session_state.followed_wallets)
                st.success("Selected trader wallet added to tracked wallets.")
            else:
                st.info("Selected trader wallet is already tracked or invalid.")
        selected_parity_url = predictparity_trader_url(selected_trader_action_row.get("username", "") or selected_trader_action_row.get("trader", ""))
        if selected_parity_url:
            action_cols[2].link_button("Parity", selected_parity_url, width="stretch")
        else:
            action_cols[2].button("Parity", key="traders_selected_parity_disabled", width="stretch", disabled=True)
        if re.fullmatch(r"0x[a-fA-F0-9]{40}", selected_wallet):
            action_cols[3].link_button("Polymarket", f"https://polymarket.com/profile/{selected_wallet}", width="stretch")
        else:
            action_cols[3].button("Polymarket", key="traders_selected_polymarket_disabled", width="stretch", disabled=True)
        selected_x_url = x_profile_url(selected_trader_action_row.get("x_username", ""))
        if selected_x_url:
            action_cols[4].link_button("X", selected_x_url, width="stretch")
        else:
            action_cols[4].button("X", key="traders_selected_x_disabled", width="stretch", disabled=True)
        action_cols[5].caption("Use row selection in Table/List mode to inspect, track, or open a leaderboard wallet.")
    if selected_wallet_from_table:
        st.session_state["traders_inspect_wallet"] = selected_wallet_from_table
        st.caption("Selected table row is ready for wallet detail.")
    options = [f"{row.trader} | {short_addr(row.wallet)} | {money(row.pnl)} PnL" for _, row in leaderboard.iterrows()]
    default_wallet = str(st.session_state.get("traders_inspect_wallet", ""))
    default_index = 0
    if default_wallet:
        for idx, (_, item) in enumerate(leaderboard.iterrows()):
            if str(item.get("wallet", "")).lower() == default_wallet.lower():
                default_index = idx
                break
    detail_cols = st.columns([2, 1, 1, 1, 2])
    selected = detail_cols[0].selectbox("Wallet detail selector", options, index=default_index)
    row = leaderboard.iloc[options.index(selected)]
    detail_wallet = str(row["wallet"])
    load_detail = detail_cols[1].toggle("Load detail", value=bool(st.session_state.get("traders_load_wallet_detail", False)), key="traders_load_wallet_detail")
    parity_url = predictparity_trader_url(row.get("username", "") or row.get("trader", ""))
    if parity_url:
        detail_cols[2].link_button("Parity", parity_url, width="stretch")
    else:
        detail_cols[2].button("Parity", key="traders_open_parity_disabled", width="stretch", disabled=True)
    profile_url = md.polymarket_profile_url(detail_wallet)
    if profile_url:
        detail_cols[3].link_button("Polymarket", profile_url, width="stretch")
    else:
        detail_cols[3].button("Polymarket", key="traders_open_profile_disabled", width="stretch", disabled=True)
    detail_cols[4].caption("Select a trader, then load the wallet detail only when needed. This keeps the leaderboard fast and scan-first.")
    st.session_state["traders_inspect_wallet"] = detail_wallet
    if load_detail:
        render_wallet(detail_wallet)


def page_wallets() -> None:
    section_header("Wallets", "Track Polymarket proxy wallets, open positions, realized PnL, and recent activity.")
    default_wallet = st.session_state.get("wallets_inspect_wallet") or (st.session_state.followed_wallets[0] if st.session_state.followed_wallets else "")
    if "wallets_wallet_input" not in st.session_state:
        st.session_state["wallets_wallet_input"] = default_wallet
    pending_wallet_view = st.session_state.pop("pending_wallet_view", None)
    if isinstance(pending_wallet_view, dict):
        apply_wallet_view_widgets(pending_wallet_view)

    def resolve_wallet_entry(value: str) -> str:
        profiles = safe_load("Wallet profile lookup", load_leaderboard, 250, "ALL", "PNL", default=pd.DataFrame())
        resolved = md.resolve_profile_query_to_wallet(value, profiles)
        if resolved:
            return resolved
        profiles = safe_load("Wallet profile volume lookup", load_leaderboard, 250, "ALL", "VOL", default=pd.DataFrame())
        return md.resolve_profile_query_to_wallet(value, profiles)

    pending_route_profile = st.session_state.pop("wallets_route_pending_resolve", "")
    if pending_route_profile:
        resolved_wallet = resolve_wallet_entry(str(pending_route_profile))
        if resolved_wallet:
            st.session_state["wallets_inspect_wallet"] = resolved_wallet
            st.session_state["wallets_wallet_input"] = str(pending_route_profile)
            st.info(f"Loaded profile route for {short_addr(resolved_wallet)}.")
        else:
            st.warning("Profile route could not be resolved from the current public trader samples.")

    input_cols = st.columns([3.4, 0.8, 0.8])
    wallet_entry = input_cols[0].text_input(
        "Wallet address or profile",
        placeholder="0x..., swisstony, @swisstony, or profile URL",
        key="wallets_wallet_input",
    )
    if input_cols[1].button("Open", width="stretch"):
        resolved_wallet = resolve_wallet_entry(wallet_entry)
        if resolved_wallet:
            st.session_state["wallets_inspect_wallet"] = resolved_wallet
            st.success(f"Opened {short_addr(resolved_wallet)}.")
            st.rerun()
        else:
            st.warning("No exact Polymarket wallet/profile match found.")
    if input_cols[2].button("Follow", width="stretch"):
        resolved_wallet = resolve_wallet_entry(wallet_entry)
        if resolved_wallet:
            st.session_state["wallets_inspect_wallet"] = resolved_wallet
            st.session_state.followed_wallets, changed = md.upsert_followed_wallet(st.session_state.followed_wallets, resolved_wallet)
            if changed:
                save_local_list("followed_wallets.json", st.session_state.followed_wallets)
                st.success("Wallet added to followed wallets.")
            else:
                st.info("Wallet is already followed.")
            st.rerun()
        else:
            st.warning("No exact Polymarket wallet/profile match found.")

    wallet = st.session_state.get("wallets_inspect_wallet") or ""
    if not wallet and re.fullmatch(r"0x[a-fA-F0-9]{40}", str(wallet_entry).strip()):
        wallet = str(wallet_entry).strip()
    if not wallet and st.session_state.followed_wallets:
        wallet = st.session_state.followed_wallets[0]

    save_cols = st.columns([2, 1, 1])
    saved_wallet_name = save_cols[0].text_input("Saved wallet view name", value=f"Wallet {short_addr(wallet) if wallet else md.now_utc_label()}", key="saved_wallet_view_name")
    save_wallet_clicked = save_cols[1].button("Save Filter", width="stretch", key="save_wallet_filter_button")
    if save_cols[2].button("Reset Wallet View", width="stretch", key="reset_wallet_view_button"):
        st.session_state["wallets_wallet_input"] = default_wallet
        st.session_state["wallets_inspect_wallet"] = default_wallet
        st.rerun()
    loaded_wallet_message = st.session_state.pop("wallet_view_loaded_message", "")
    if loaded_wallet_message:
        st.info(loaded_wallet_message)
    if st.session_state.saved_wallet_filters:
        load_cols = st.columns([2, 1, 1])
        saved_labels = [
            f"{i + 1}. {view.get('name') or short_addr(str(view.get('wallet', ''))) or 'Wallet view'}"
            for i, view in enumerate(st.session_state.saved_wallet_filters)
        ]
        selected_saved_wallet = load_cols[0].selectbox("Load saved wallet view", saved_labels, key="load_saved_wallet_view")
        selected_wallet_view = st.session_state.saved_wallet_filters[saved_labels.index(selected_saved_wallet)]
        if load_cols[1].button("Load wallet view", key="load_wallet_view_button"):
            st.session_state["pending_wallet_view"] = selected_wallet_view
            st.session_state["wallet_view_loaded_message"] = f"Loaded saved wallet view: {selected_wallet_view.get('name', selected_saved_wallet)}"
            st.rerun()
        if load_cols[2].button("Delete wallet view", key="delete_wallet_view_button"):
            st.session_state.saved_wallet_filters.pop(saved_labels.index(selected_saved_wallet))
            save_local_list("saved_wallet_filters.json", st.session_state.saved_wallet_filters)
            st.rerun()
    if save_wallet_clicked:
        st.session_state.saved_wallet_filters.append(
            {
                "name": saved_wallet_name.strip() or f"Wallet {short_addr(wallet)}",
                "created_at": md.now_utc_label(),
                "entry": str(wallet_entry or ""),
                "wallet": str(wallet or ""),
            }
        )
        save_local_list("saved_wallet_filters.json", st.session_state.saved_wallet_filters)
        st.success("Saved wallet view.")
    if st.session_state.saved_wallet_filters:
        st.caption(f"Saved wallet views: {len(st.session_state.saved_wallet_filters)}")
        with st.expander("Saved wallet filters", expanded=False):
            display = pd.DataFrame(st.session_state.saved_wallet_filters)
            if not display.empty and "wallet" in display:
                display["wallet_short"] = display["wallet"].astype(str).map(short_addr)
            st.dataframe(display, width="stretch", height=160)
            if st.button("Clear saved wallet filters"):
                st.session_state.saved_wallet_filters = []
                save_local_list("saved_wallet_filters.json", st.session_state.saved_wallet_filters)
                st.rerun()

    if st.session_state.followed_wallets:
        selected_index = 0
        for idx, item in enumerate(st.session_state.followed_wallets):
            if str(item).lower() == str(wallet).lower():
                selected_index = idx
                break
        follow_cols = st.columns([3.4, 0.8, 0.8])
        selected = follow_cols[0].selectbox("Followed wallets", st.session_state.followed_wallets, index=selected_index, format_func=short_addr)
        if follow_cols[1].button("Open selected", width="stretch"):
            st.session_state["wallets_inspect_wallet"] = selected
            st.rerun()
        if follow_cols[2].button("Remove selected", width="stretch"):
            st.session_state.followed_wallets = [w for w in st.session_state.followed_wallets if w.lower() != selected.lower()]
            if str(wallet).lower() == str(selected).lower():
                st.session_state["wallets_inspect_wallet"] = st.session_state.followed_wallets[0] if st.session_state.followed_wallets else ""
            save_local_list("followed_wallets.json", st.session_state.followed_wallets)
            st.rerun()
    render_wallet(wallet)
    st.info("Kalshi wallet analytics are not shown because Kalshi public market data does not expose trader wallets.")


def page_track() -> None:
    section_header("Track", "Watch markets and wallets from one workspace, mirroring Parity's tracking hub with public data.")
    if "track_search" not in st.session_state:
        reset_track_filter_widgets(global_query)
    if st.session_state.pop("track_filters_reset_pending", False):
        reset_track_filter_widgets(global_query)
    pending_track_view = st.session_state.pop("pending_track_filter_view", None)
    if isinstance(pending_track_view, dict):
        apply_track_filter_view_widgets(pending_track_view)
    pending_track_clear = st.session_state.pop("track_clear_pending", None)
    if isinstance(pending_track_clear, dict):
        for key, value in pending_track_clear.items():
            st.session_state[key] = value
    route_filter_params = query_param_snapshot(
        [
            "q",
            "query",
            "search",
            "wallet",
            "market",
            "platform",
            "platforms",
            "venue",
            "venues",
            "minWatchVolume",
            "watchVolumeMin",
            "minVolume",
            "volumeMin",
            "rows",
            "limit",
            "signal",
            "marketSignal",
            "signalFilter",
            "minWalletValue",
            "walletValueMin",
            "minOpenValue",
            "openValueMin",
        ]
    )
    route_filter_signature = json.dumps(route_filter_params, sort_keys=True)
    route_filter_view = md.predictparity_track_filter_view(route_filter_params)
    if route_filter_view and st.session_state.get("track_route_filter_signature") != route_filter_signature:
        apply_track_filter_view_widgets(route_filter_view)
        st.session_state["track_route_filter_signature"] = route_filter_signature
        st.session_state["track_view_loaded_message"] = "Loaded track filters from URL."

    pm, ks, combined = load_market_universe()
    track_cols = st.columns([2, 1, 1, 1])
    track_query = track_cols[0].text_input("Track search", placeholder="market, wallet, trader", key="track_search")
    track_platforms = track_cols[1].multiselect("Track platforms", ["Polymarket", "Kalshi"], key="track_platforms")
    min_watch_volume = track_cols[2].number_input("Min watch volume", min_value=0, step=1000, key="track_min_watch_volume")
    watch_rows = track_cols[3].slider("Watch rows", min_value=10, max_value=250, step=10, key="track_rows")
    with st.expander("Track filters", expanded=False):
        f1, f2 = st.columns([1, 1])
        track_signal_filter = f1.radio("Market signal", ["Any", "Fast move", "Tight spread", "None"], horizontal=True, key="track_signal_filter")
        min_wallet_value = f2.number_input("Min wallet open value", min_value=0, step=500, key="track_min_wallet_value")
        if st.button("Reset Filters", width="stretch", key="reset_track_filters_button"):
            st.session_state["track_filters_reset_pending"] = True
            st.rerun()
    save_cols = st.columns([2, 1, 1])
    saved_track_name = save_cols[0].text_input("Saved track view name", value=f"Track {md.now_utc_label()}", key="saved_track_view_name")
    save_track_clicked = save_cols[1].button("Save Filter", width="stretch", key="save_track_filter_button")
    if save_cols[2].button("Reset Track View", width="stretch", key="reset_track_view_button"):
        st.session_state["track_filters_reset_pending"] = True
        st.rerun()
    loaded_track_message = st.session_state.pop("track_view_loaded_message", "")
    if loaded_track_message:
        st.info(loaded_track_message)
    if st.session_state.saved_track_filters:
        load_cols = st.columns([2, 1, 1])
        saved_labels = [
            f"{i + 1}. {view.get('name') or view.get('query') or 'Track view'}"
            for i, view in enumerate(st.session_state.saved_track_filters)
        ]
        selected_saved_track = load_cols[0].selectbox("Load saved track view", saved_labels, key="load_saved_track_view")
        selected_track_view = st.session_state.saved_track_filters[saved_labels.index(selected_saved_track)]
        if load_cols[1].button("Load track view", key="load_track_view_button"):
            st.session_state["pending_track_filter_view"] = selected_track_view
            st.session_state["track_view_loaded_message"] = f"Loaded saved track view: {selected_track_view.get('name', selected_saved_track)}"
            st.rerun()
        if load_cols[2].button("Delete track view", key="delete_track_view_button"):
            st.session_state.saved_track_filters.pop(saved_labels.index(selected_saved_track))
            save_local_list("saved_track_filters.json", st.session_state.saved_track_filters)
            st.rerun()
    if save_track_clicked:
        st.session_state.saved_track_filters.append(
            {
                "name": saved_track_name.strip() or f"Track {md.now_utc_label()}",
                "created_at": md.now_utc_label(),
                "query": track_query,
                "platforms": track_platforms,
                "min_watch_volume": float(min_watch_volume),
                "rows": int(watch_rows),
                "signal_filter": track_signal_filter,
                "min_wallet_value": float(min_wallet_value),
            }
        )
        save_local_list("saved_track_filters.json", st.session_state.saved_track_filters)
        st.success("Saved track view.")
    track_defaults = track_filter_defaults()
    track_chips: list[str] = []
    if track_query.strip():
        track_chips.append(f"Search: {track_query.strip()}")
    if set(track_platforms) != set(track_defaults["track_platforms"]):
        track_chips.append("Platform: " + (", ".join(track_platforms) if track_platforms else "none"))
    if min_watch_volume:
        track_chips.append(f"Min volume: {money(min_watch_volume)}")
    if int(watch_rows) != int(track_defaults["track_rows"]):
        track_chips.append(f"Rows: {int(watch_rows)}")
    if track_signal_filter != "Any":
        track_chips.append(f"Signal: {track_signal_filter}")
    if int(min_wallet_value) > 0:
        track_chips.append(f"Wallet value >= {money(min_wallet_value)}")
    track_chips.extend([f"Markets tracked: {len(st.session_state.watchlist)}", f"Wallets tracked: {len(st.session_state.followed_wallets)}"])
    render_filter_chips(track_chips)
    track_clear_actions: list[tuple[str, dict[str, Any]]] = []
    if track_query.strip():
        track_clear_actions.append(("search", {"track_search": ""}))
    if set(track_platforms) != set(track_defaults["track_platforms"]):
        track_clear_actions.append(("platform", {"track_platforms": track_defaults["track_platforms"]}))
    if int(min_watch_volume) > 0:
        track_clear_actions.append(("volume", {"track_min_watch_volume": 0}))
    if int(watch_rows) != int(track_defaults["track_rows"]):
        track_clear_actions.append(("rows", {"track_rows": track_defaults["track_rows"]}))
    if track_signal_filter != "Any":
        track_clear_actions.append(("signal", {"track_signal_filter": "Any"}))
    if int(min_wallet_value) > 0:
        track_clear_actions.append(("wallet value", {"track_min_wallet_value": 0}))
    render_filter_clear_buttons(track_clear_actions, "track")
    if st.session_state.saved_track_filters:
        st.caption(f"Saved track views: {len(st.session_state.saved_track_filters)}")
        with st.expander("Saved track filters", expanded=False):
            st.dataframe(pd.DataFrame(st.session_state.saved_track_filters), width="stretch", height=160)
            if st.button("Clear saved track filters"):
                st.session_state.saved_track_filters = []
                save_local_list("saved_track_filters.json", st.session_state.saved_track_filters)
                st.rerun()
    with st.expander("Import watchlists", expanded=False):
        import_cols = st.columns([1, 1])
        uploaded_markets = import_cols[0].file_uploader("Import tracked markets CSV", type=["csv"], key="track_import_markets")
        if uploaded_markets is not None:
            imported = pd.read_csv(uploaded_markets).fillna("")
            added = 0
            existing = {str(item.get("market_key", "")) for item in st.session_state.watchlist}
            for _, row in imported.iterrows():
                key = str(row.get("market_key", ""))
                if not key or key in existing:
                    continue
                st.session_state.watchlist.append(
                    {
                        "platform": str(row.get("platform", "")),
                        "market_key": key,
                        "title": str(row.get("title", "")),
                        "url": str(row.get("url", "")),
                    }
                )
                existing.add(key)
                added += 1
            if added:
                save_local_list("watchlist.json", st.session_state.watchlist)
                st.success(f"Imported {added} markets.")
                st.rerun()
        uploaded_wallets = import_cols[1].file_uploader("Import tracked wallets CSV", type=["csv"], key="track_import_wallets")
        if uploaded_wallets is not None:
            imported_wallets = pd.read_csv(uploaded_wallets).fillna("")
            wallet_values = imported_wallets["wallet"].astype(str).tolist() if "wallet" in imported_wallets else imported_wallets.iloc[:, 0].astype(str).tolist()
            existing_wallets = {item.lower() for item in st.session_state.followed_wallets}
            added_wallets = 0
            for wallet_value in wallet_values:
                value = wallet_value.strip()
                if re.fullmatch(r"0x[a-fA-F0-9]{40}", value) and value.lower() not in existing_wallets:
                    st.session_state.followed_wallets.append(value)
                    existing_wallets.add(value.lower())
                    added_wallets += 1
            if added_wallets:
                save_local_list("followed_wallets.json", st.session_state.followed_wallets)
                st.success(f"Imported {added_wallets} wallets.")
                st.rerun()

    tracked_wallet_tuple = tuple(str(item) for item in st.session_state.followed_wallets)
    tracked_traders = pd.DataFrame()
    tracked_recent_flow = pd.DataFrame()
    if tracked_wallet_tuple:
        tracked_leaderboard = safe_load("Tracked trader leaderboard", load_leaderboard, 250, "ALL", "PNL", default=pd.DataFrame())
        tracked_recent_flow = safe_load("Tracked trader recent flow", load_polymarket_trades, 500, 0.0, None, None, default=pd.DataFrame())
        tracked_flow_scores = md.trader_flow_scores(tracked_recent_flow, whale_threshold=float(min_whale)) if not tracked_recent_flow.empty else pd.DataFrame()
        tracked_position_values = safe_load("Tracked trader positions", load_wallet_position_values, tracked_wallet_tuple, 120, default=pd.DataFrame())
        tracked_traders = md.tracked_trader_rows(
            tracked_wallet_tuple,
            leaderboard=tracked_leaderboard,
            flow_scores=tracked_flow_scores,
            position_values=tracked_position_values,
        )
        tracked_traders = filter_text(tracked_traders, track_query)
        if not tracked_traders.empty:
            tracked_traders = tracked_traders[numeric_col(tracked_traders, "positions_value") >= float(min_wallet_value)].reset_index(drop=True)

    st.markdown("### Tracked traders")
    trader_metrics = st.columns(5)
    trader_metrics[0].metric("Tracked traders", f"{len(tracked_traders):,}")
    trader_metrics[1].metric("Open value", money(tracked_traders["positions_value"].sum() if not tracked_traders.empty else 0.0))
    trader_metrics[2].metric("Recent flow", money(tracked_traders["recent_notional"].sum() if not tracked_traders.empty else 0.0))
    trader_metrics[3].metric("Active", f"{int(tracked_traders['tracked_status'].eq('Active').sum()) if not tracked_traders.empty else 0:,}")
    trader_metrics[4].metric("Verified", f"{int(tracked_traders['verified'].astype(bool).sum()) if not tracked_traders.empty and 'verified' in tracked_traders else 0:,}")
    if not tracked_wallet_tuple:
        draw_empty("No tracked traders yet. Add a wallet below or from Traders, Live Trades, Market holders, or Wallet detail.")
    elif tracked_traders.empty:
        draw_empty("No tracked traders match the current Track filters.")
    else:
        tracked_display = tracked_traders.copy()
        tracked_display["wallet_short"] = tracked_display["wallet"].astype(str).map(short_addr)
        tracked_display["last_seen"] = pd.to_datetime(tracked_display.get("last_seen"), utc=True, errors="coerce")
        tracked_columns = [
            "tracked_status",
            "trader",
            "wallet_short",
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
            "flow_trait",
            "whale_score",
            "bot_score",
            "last_seen",
            "verified",
        ]
        st.download_button("Export tracked traders CSV", tracked_traders.to_csv(index=False).encode("utf-8"), file_name="tracked_traders.csv", mime="text/csv")
        st.dataframe(
            clean_table(tracked_display, tracked_columns),
            width="stretch",
            height=300,
            column_config={
                "pnl": st.column_config.NumberColumn("Total PnL", format="$%.0f"),
                "volume": st.column_config.NumberColumn(format="$%.0f"),
                "positions_value": st.column_config.NumberColumn("Positions", format="$%.0f"),
                "open_positions": st.column_config.NumberColumn("Open", format="%.0f"),
                "open_markets": st.column_config.NumberColumn("Markets", format="%.0f"),
                "recent_notional": st.column_config.NumberColumn(format="$%.0f"),
                "largest_trade": st.column_config.NumberColumn(format="$%.0f"),
                "trades_per_hour": st.column_config.NumberColumn(format="%.1f"),
                "whale_score": st.column_config.ProgressColumn(min_value=0, max_value=100),
                "bot_score": st.column_config.ProgressColumn(min_value=0, max_value=100),
                "last_seen": st.column_config.DatetimeColumn(format="YYYY-MM-DD HH:mm"),
            },
        )
        tracked_options = [
            f"{row.get('trader', short_addr(str(row.get('wallet', ''))))} | {short_addr(str(row.get('wallet', '')))} | {money(row.get('positions_value', 0.0))} open"
            for _, row in tracked_traders.iterrows()
        ]
        tracked_action_cols = st.columns([2, 1, 1, 1])
        selected_tracked = tracked_action_cols[0].selectbox("Tracked trader action", tracked_options, key="track_trader_action")
        tracked_row = tracked_traders.iloc[tracked_options.index(selected_tracked)]
        tracked_wallet = str(tracked_row.get("wallet", ""))
        if tracked_action_cols[1].button("Open profile", key="track_trader_open_profile", width="stretch"):
            st.session_state["wallets_inspect_wallet"] = tracked_wallet
            queue_navigation("Wallets", track_query)
            st.rerun()
        if tracked_action_cols[2].button("Remove trader", key="track_trader_remove", width="stretch"):
            st.session_state.followed_wallets = [wallet for wallet in st.session_state.followed_wallets if str(wallet).lower() != tracked_wallet.lower()]
            save_local_list("followed_wallets.json", st.session_state.followed_wallets)
            st.rerun()
        if re.fullmatch(r"0x[a-fA-F0-9]{40}", tracked_wallet):
            tracked_action_cols[3].link_button("Polymarket", f"https://polymarket.com/profile/{tracked_wallet}", width="stretch")

    st.markdown("### Tracked wallet live feed")
    tracked_feed = pd.DataFrame()
    if tracked_wallet_tuple and not tracked_recent_flow.empty and "wallet" in tracked_recent_flow:
        tracked_wallet_set = {wallet.lower() for wallet in tracked_wallet_tuple}
        tracked_feed = tracked_recent_flow[
            tracked_recent_flow["wallet"].astype(str).str.lower().isin(tracked_wallet_set)
        ].copy()
        tracked_feed = filter_text(tracked_feed, track_query)
        if "time" in tracked_feed:
            tracked_feed = tracked_feed.sort_values("time", ascending=False)
        tracked_feed = tracked_feed.head(int(watch_rows)).reset_index(drop=True)
    feed_metrics = st.columns(5)
    feed_metrics[0].metric("Tracked trades", f"{len(tracked_feed):,}")
    feed_metrics[1].metric("Feed notional", money(tracked_feed["notional"].sum() if not tracked_feed.empty and "notional" in tracked_feed else 0.0))
    feed_metrics[2].metric("Whale prints", f"{int((numeric_col(tracked_feed, 'notional') >= float(min_whale)).sum()) if not tracked_feed.empty else 0:,}")
    feed_metrics[3].metric("Markets", f"{tracked_feed['title'].nunique() if not tracked_feed.empty and 'title' in tracked_feed else 0:,}")
    feed_metrics[4].metric("Wallets", f"{tracked_feed['wallet'].nunique() if not tracked_feed.empty and 'wallet' in tracked_feed else 0:,}")
    if not tracked_wallet_tuple:
        draw_empty("No tracked wallet live feed yet. Track wallets from Traders, Live Trades, Market holders, or Wallet detail.")
    elif tracked_feed.empty:
        draw_empty("No recent public Polymarket trades from tracked wallets match the current Track filters.")
    else:
        feed_display = tracked_feed.copy()
        feed_display["wallet_short"] = feed_display["wallet"].astype(str).map(short_addr)
        st.download_button("Export tracked wallet feed CSV", tracked_feed.to_csv(index=False).encode("utf-8"), file_name="tracked_wallet_live_feed.csv", mime="text/csv")
        st.dataframe(
            clean_table(
                feed_display,
                ["time", "trader", "wallet_short", "side", "outcome", "title", "price", "size", "notional", "transaction_hash", "url"],
            ),
            width="stretch",
            height=320,
            column_config={
                "time": st.column_config.DatetimeColumn(format="YYYY-MM-DD HH:mm:ss"),
                "price": st.column_config.NumberColumn(format="%.4f"),
                "size": st.column_config.NumberColumn(format="%.2f"),
                "notional": st.column_config.NumberColumn(format="$%.0f"),
                "url": st.column_config.LinkColumn("URL"),
            },
        )
        feed_options = [
            f"{i + 1}. {short_addr(str(row.get('wallet', '')))} | {row.get('side', '-')} {row.get('outcome', '-')} | {money(row.get('notional', 0.0))} | {str(row.get('title', ''))[:80]}"
            for i, row in tracked_feed.head(100).iterrows()
        ]
        feed_action_cols = st.columns([2.4, 1, 1, 1])
        selected_feed_trade = feed_action_cols[0].selectbox("Tracked trade action", feed_options, key="track_feed_trade_action")
        feed_row = tracked_feed.iloc[feed_options.index(selected_feed_trade)]
        feed_wallet = str(feed_row.get("wallet", ""))
        feed_market_key = str(feed_row.get("market_key", "") or feed_row.get("ticker", "") or feed_row.get("title", ""))
        if feed_action_cols[1].button("Open wallet", key="track_feed_open_wallet", width="stretch"):
            st.session_state["wallets_inspect_wallet"] = feed_wallet
            queue_navigation("Wallets", track_query)
            st.rerun()
        if feed_action_cols[2].button("Track market", key="track_feed_track_market", width="stretch"):
            item = {
                "platform": str(feed_row.get("platform", "Polymarket")),
                "market_key": feed_market_key,
                "title": str(feed_row.get("title", "")),
                "url": str(feed_row.get("url", "")),
            }
            st.session_state.watchlist, changed = md.upsert_watchlist_market(st.session_state.watchlist, item)
            if changed:
                save_local_list("watchlist.json", st.session_state.watchlist)
                st.success("Tracked trade market added to watchlist.")
            else:
                st.info("Tracked trade market is already watched.")
        if feed_action_cols[3].button("Open Live Trades", key="track_feed_open_live_trades", width="stretch"):
            st.session_state["live_search"] = track_query
            st.session_state["live_tracked_wallets_only"] = True
            st.session_state["live_rows"] = max(50, min(500, int(watch_rows)))
            queue_navigation("Live Trades", track_query)
            st.rerun()
    st.divider()

    left, right = st.columns([1, 1])
    with left:
        st.markdown("### Watched markets")
        filtered = combined[combined["platform"].isin(track_platforms)].copy() if not combined.empty else pd.DataFrame()
        filtered = filter_text(filtered, track_query)
        if not filtered.empty:
            volume_col = _monitor_volume_col(filtered)
            filtered = filtered[numeric_col(filtered, volume_col) >= float(min_watch_volume)]
            filtered = filtered.sort_values(volume_col, ascending=False).head(150)
        if filtered.empty:
            draw_empty("No markets available to add.")
        else:
            options = [f"{row.platform}: {str(row.title)[:100]}" for _, row in filtered.iterrows()]
            selected = st.selectbox("Add market to track", options, key="track_add_market")
            selected_row = filtered.iloc[options.index(selected)]
            if st.button("Track market", key="track_market_button"):
                item = {
                    "platform": selected_row["platform"],
                    "market_key": selected_row["market_key"],
                    "title": selected_row["title"],
                    "url": selected_row["url"],
                }
                if item["market_key"] not in [w["market_key"] for w in st.session_state.watchlist]:
                    st.session_state.watchlist.append(item)
                    save_local_list("watchlist.json", st.session_state.watchlist)
        if not st.session_state.watchlist:
            draw_empty("No tracked markets yet.")
        else:
            watch = pd.DataFrame(st.session_state.watchlist)
            live = pd.concat([pm, ks], ignore_index=True) if not pm.empty or not ks.empty else pd.DataFrame()
            if not live.empty:
                watch = watch.merge(clean_table(live, ["market_key", "yes_price", "change_1h", "activity_volume", "volume_24h", "liquidity", "spread", "end_time"]), on="market_key", how="left")
            watch = filter_text(watch, track_query)
            if track_platforms and "platform" in watch:
                watch = watch[watch["platform"].isin(track_platforms)]
            if not watch.empty:
                volume_col = _monitor_volume_col(watch)
                watch = watch[numeric_col(watch, volume_col) >= float(min_watch_volume)].head(int(watch_rows))
                watch["watch_signal"] = watch.apply(
                    lambda row: "Fast move" if abs(float(row.get("change_1h") or 0.0)) >= 0.03 else ("Tight spread" if pd.notna(row.get("spread")) and float(row.get("spread") or 999.0) <= 0.03 else ""),
                    axis=1,
                )
                if track_signal_filter == "None":
                    watch = watch[~watch["watch_signal"].astype(bool)]
                elif track_signal_filter != "Any":
                    watch = watch[watch["watch_signal"].eq(track_signal_filter)]
                watch["end_date"] = pd.to_datetime(watch.get("end_time"), utc=True, errors="coerce").dt.strftime("%Y-%m-%d").fillna("-")
            market_metrics = st.columns(4)
            market_metrics[0].metric("Watched markets", f"{len(watch):,}")
            market_metrics[1].metric("24h volume", money(watch[_monitor_volume_col(watch)].sum() if not watch.empty else 0))
            market_metrics[2].metric("Median price", cents(watch["yes_price"].median() if not watch.empty and "yes_price" in watch else None))
            market_metrics[3].metric("Signals", f"{int(watch['watch_signal'].astype(bool).sum()) if not watch.empty and 'watch_signal' in watch else 0:,}")
            if watch.empty:
                draw_empty("No tracked markets match the current filters.")
            else:
                st.download_button("Export tracked markets CSV", watch.to_csv(index=False).encode("utf-8"), file_name="tracked_markets.csv", mime="text/csv")
            st.dataframe(
                clean_table(watch, ["platform", "title", "yes_price", "change_1h", "activity_volume", "volume_24h", "liquidity", "spread", "end_date", "watch_signal", "url", "market_key"]),
                width="stretch",
                height=340,
                column_config={
                    "yes_price": st.column_config.NumberColumn(format="%.3f"),
                    "change_1h": st.column_config.NumberColumn(format="%+.3f"),
                    "activity_volume": st.column_config.NumberColumn(format="$%.0f"),
                    "volume_24h": st.column_config.NumberColumn(format="$%.0f"),
                    "liquidity": st.column_config.NumberColumn(format="$%.0f"),
                    "spread": st.column_config.NumberColumn(format="%.3f"),
                    "url": st.column_config.LinkColumn("URL"),
                },
            )
            if st.button("Clear tracked markets", key="clear_tracked_markets"):
                st.session_state.watchlist = []
                save_local_list("watchlist.json", st.session_state.watchlist)
                st.rerun()
    with right:
        st.markdown("### Watched wallets")
        wallet = st.text_input("Wallet to track", placeholder="0x...", key="track_wallet_input")
        if st.button("Track wallet", key="track_wallet_button"):
            value = wallet.strip()
            if re.fullmatch(r"0x[a-fA-F0-9]{40}", value) and value.lower() not in [w.lower() for w in st.session_state.followed_wallets]:
                st.session_state.followed_wallets.append(value)
                save_local_list("followed_wallets.json", st.session_state.followed_wallets)
        if not st.session_state.followed_wallets:
            draw_empty("No tracked wallets yet.")
        else:
            rows = []
            wallet_filter = track_query.strip().lower()
            tracked_wallet_list = [
                item for item in st.session_state.followed_wallets
                if not wallet_filter or wallet_filter in item.lower() or wallet_filter in short_addr(item).lower()
            ]
            for item in tracked_wallet_list[: int(watch_rows)]:
                positions = safe_load("Tracked wallet positions", md.get_polymarket_positions, item, 80, default=pd.DataFrame())
                rows.append(
                    {
                        "wallet": item,
                        "wallet_short": short_addr(item),
                        "open_positions": len(positions),
                        "open_value": float(positions["value"].sum()) if not positions.empty and "value" in positions else 0.0,
                    }
                )
            wallet_frame = pd.DataFrame(rows)
            if not wallet_frame.empty:
                wallet_frame = wallet_frame[numeric_col(wallet_frame, "open_value") >= float(min_wallet_value)].head(int(watch_rows)).reset_index(drop=True)
            wallet_metrics = st.columns(3)
            wallet_metrics[0].metric("Watched wallets", f"{len(wallet_frame):,}")
            wallet_metrics[1].metric("Open value", money(wallet_frame["open_value"].sum() if not wallet_frame.empty else 0))
            wallet_metrics[2].metric("Open positions", f"{int(wallet_frame['open_positions'].sum()) if not wallet_frame.empty else 0:,}")
            if wallet_frame.empty:
                draw_empty("No tracked wallets match the current filters.")
            else:
                st.download_button("Export tracked wallets CSV", wallet_frame.to_csv(index=False).encode("utf-8"), file_name="tracked_wallets.csv", mime="text/csv")
                st.dataframe(wallet_frame, width="stretch", height=340, column_config={"open_value": st.column_config.NumberColumn(format="$%.0f")})
            selectable_wallets = wallet_frame["wallet"].astype(str).tolist() if not wallet_frame.empty and "wallet" in wallet_frame else tracked_wallet_list
            if selectable_wallets:
                selected = st.selectbox("Open tracked wallet", selectable_wallets, format_func=short_addr, key="track_open_wallet")
                remove_cols = st.columns([1, 1])
                if remove_cols[0].button("Remove tracked wallet", key="track_remove_wallet"):
                    st.session_state.followed_wallets = [w for w in st.session_state.followed_wallets if w.lower() != selected.lower()]
                    save_local_list("followed_wallets.json", st.session_state.followed_wallets)
                    st.rerun()
                if remove_cols[1].button("Clear tracked wallets", key="track_clear_wallets"):
                    st.session_state.followed_wallets = []
                    save_local_list("followed_wallets.json", st.session_state.followed_wallets)
                    st.rerun()
                render_wallet(selected)


def live_market_flow(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame()
    df = trades.copy()
    df["notional"] = pd.to_numeric(df.get("notional", 0.0), errors="coerce").fillna(0.0)
    df["side_upper"] = df.get("side", "").astype(str).str.upper()
    df["outcome_upper"] = df.get("outcome", "").astype(str).str.upper()
    if "market_key" not in df:
        df["market_key"] = df.get("ticker", df.get("title", ""))
    if "url" not in df:
        df["url"] = ""
    grouped = (
        df.groupby(["platform", "title"], dropna=False)
        .agg(
            trades=("title", "size"),
            notional=("notional", "sum"),
            avg_trade=("notional", "mean"),
            largest_trade=("notional", "max"),
            latest_trade=("time", "max"),
            unique_wallets=("wallet", lambda s: int(s.astype(str).nunique())),
            buy_notional=("notional", lambda s: float(s[df.loc[s.index, "side_upper"].eq("BUY")].sum())),
            sell_notional=("notional", lambda s: float(s[df.loc[s.index, "side_upper"].eq("SELL")].sum())),
            yes_notional=("notional", lambda s: float(s[df.loc[s.index, "outcome_upper"].eq("YES")].sum())),
            no_notional=("notional", lambda s: float(s[df.loc[s.index, "outcome_upper"].eq("NO")].sum())),
            market_key=("market_key", "first"),
            url=("url", "first"),
        )
        .reset_index()
    )
    grouped["net_buy_notional"] = grouped["buy_notional"] - grouped["sell_notional"]
    grouped["yes_share"] = grouped["yes_notional"] / grouped["notional"].replace({0: pd.NA})
    grouped["no_share"] = grouped["no_notional"] / grouped["notional"].replace({0: pd.NA})
    grouped["flow_bias"] = grouped["yes_share"].map(lambda value: "YES" if pd.notna(value) and value >= 0.55 else ("NO" if pd.notna(value) and value <= 0.45 else "Mixed"))
    return grouped.sort_values(["notional", "latest_trade"], ascending=[False, False]).reset_index(drop=True)


def page_live_trades() -> None:
    section_header("Live Trades", "Public real-time-style trade tape with Parity-style search, side, venue, notional, and whale filters.")
    if "live_search" not in st.session_state:
        reset_live_trade_filter_widgets(global_query, int(trade_limit))
    if st.session_state.pop("live_filters_reset_pending", False):
        reset_live_trade_filter_widgets(global_query, int(trade_limit))
    pending_live_view = st.session_state.pop("pending_live_filter_view", None)
    if isinstance(pending_live_view, dict):
        apply_live_trade_filter_view_widgets(pending_live_view)
    pending_live_clear = st.session_state.pop("live_clear_pending", None)
    if isinstance(pending_live_clear, dict):
        for key, value in pending_live_clear.items():
            st.session_state[key] = value
    route_filter_params = query_param_snapshot(
        [
            "q",
            "query",
            "search",
            "wallet",
            "market",
            "platform",
            "platforms",
            "venue",
            "venues",
            "side",
            "sides",
            "outcome",
            "outcomes",
            "minNotional",
            "notionalMin",
            "min",
            "amountMin",
            "rows",
            "limit",
            "large",
            "whale",
            "whales",
            "largeOnly",
            "trackedMarkets",
            "tracked_markets",
            "marketsTracked",
            "trackedWallets",
            "tracked_wallets",
            "walletsTracked",
        ]
    )
    route_filter_signature = json.dumps(route_filter_params, sort_keys=True)
    route_filter_view = md.predictparity_live_trade_filter_view(route_filter_params)
    if route_filter_view and st.session_state.get("live_route_filter_signature") != route_filter_signature:
        apply_live_trade_filter_view_widgets(route_filter_view)
        st.session_state["live_route_filter_signature"] = route_filter_signature
        st.session_state["live_view_loaded_message"] = "Loaded live trade filters from URL."

    controls = st.columns([2, 1, 1, 1, 1])
    query = controls[0].text_input("Search live trades", placeholder="market, wallet, trader, outcome", key="live_search")
    platforms = controls[1].multiselect("Platform", ["Polymarket", "Kalshi"], key="live_platforms")
    sides = controls[2].multiselect("Side", ["BUY", "SELL", "yes", "no"], key="live_sides")
    min_notional = controls[3].number_input("Min notional", min_value=0, step=100, key="live_min_notional")
    rows = controls[4].slider("Rows", min_value=50, max_value=500, step=50, key="live_rows")
    with st.expander("Live trade filters", expanded=False):
        f1, f2, f3, f4 = st.columns(4)
        tracked_markets_only = f1.checkbox("Tracked markets only", key="live_tracked_markets_only")
        tracked_wallets_only = f2.checkbox("Tracked wallets only", key="live_tracked_wallets_only")
        large_only = f3.checkbox("Whale prints only", key="live_large_only")
        if f4.button("Reset Filters", width="stretch", key="reset_live_filters_button"):
            st.session_state["live_filters_reset_pending"] = True
            st.rerun()

    save_cols = st.columns([2, 1, 1])
    saved_live_name = save_cols[0].text_input("Saved live view name", value=f"Live Trades {md.now_utc_label()}", key="saved_live_view_name")
    save_live_clicked = save_cols[1].button("Save Filter", width="stretch", key="save_live_filter_button")
    if save_cols[2].button("Reset Live View", width="stretch", key="reset_live_view_button"):
        st.session_state["live_filters_reset_pending"] = True
        st.rerun()
    loaded_live_message = st.session_state.pop("live_view_loaded_message", "")
    if loaded_live_message:
        st.info(loaded_live_message)
    if st.session_state.saved_live_filters:
        load_cols = st.columns([2, 1, 1])
        saved_labels = [
            f"{i + 1}. {view.get('name') or view.get('query') or 'Live view'}"
            for i, view in enumerate(st.session_state.saved_live_filters)
        ]
        selected_saved_live = load_cols[0].selectbox("Load saved live view", saved_labels, key="load_saved_live_view")
        selected_live_view = st.session_state.saved_live_filters[saved_labels.index(selected_saved_live)]
        if load_cols[1].button("Load live view", key="load_live_view_button"):
            st.session_state["pending_live_filter_view"] = selected_live_view
            st.session_state["live_view_loaded_message"] = f"Loaded saved live view: {selected_live_view.get('name', selected_saved_live)}"
            st.rerun()
        if load_cols[2].button("Delete live view", key="delete_live_view_button"):
            st.session_state.saved_live_filters.pop(saved_labels.index(selected_saved_live))
            save_local_list("saved_live_filters.json", st.session_state.saved_live_filters)
            st.rerun()
    if save_live_clicked:
        st.session_state.saved_live_filters.append(
            {
                "name": saved_live_name.strip() or f"Live Trades {md.now_utc_label()}",
                "created_at": md.now_utc_label(),
                "query": query,
                "platforms": platforms,
                "sides": sides,
                "min_notional": float(min_notional),
                "rows": int(rows),
                "tracked_markets_only": bool(tracked_markets_only),
                "tracked_wallets_only": bool(tracked_wallets_only),
                "large_only": bool(large_only),
            }
        )
        save_local_list("saved_live_filters.json", st.session_state.saved_live_filters)
        st.success("Saved live trade view.")

    poly_trades = safe_load("Polymarket trades", load_polymarket_trades, rows, 0.0, None, None)
    kalshi_trades = safe_load("Kalshi trades", load_kalshi_trades, rows, None)
    trades = pd.concat([df for df in [poly_trades, kalshi_trades] if not df.empty], ignore_index=True, sort=False) if not poly_trades.empty or not kalshi_trades.empty else pd.DataFrame()
    if trades.empty:
        draw_empty("No public trades returned.")
        return
    trades = filter_text(trades, query)
    trades = trades[trades["platform"].isin(platforms)]
    effective_min_notional = max(float(min_notional), float(min_whale) if large_only else 0.0)
    trades = trades[numeric_col(trades, "notional") >= effective_min_notional]
    if sides:
        side_mask = trades["side"].astype(str).str.upper().isin([item.upper() for item in sides])
        outcome_mask = trades.get("outcome", pd.Series("", index=trades.index)).astype(str).str.upper().isin([item.upper() for item in sides])
        trades = trades[side_mask | outcome_mask]
    if tracked_markets_only:
        tracked_keys = {str(item.get("market_key", "")) for item in st.session_state.watchlist}
        trades = trades[trades.get("market_key", pd.Series("", index=trades.index)).astype(str).isin(tracked_keys)] if tracked_keys else trades.iloc[0:0]
    if tracked_wallets_only:
        tracked_wallets = {str(item).lower() for item in st.session_state.followed_wallets}
        trades = trades[trades.get("wallet", pd.Series("", index=trades.index)).astype(str).str.lower().isin(tracked_wallets)] if tracked_wallets else trades.iloc[0:0]
    trades = trades.sort_values("time", ascending=False).head(rows).reset_index(drop=True)

    metrics = st.columns(5)
    metrics[0].metric("Trades", f"{len(trades):,}")
    metrics[1].metric("Notional", money(trades["notional"].sum() if "notional" in trades else 0))
    metrics[2].metric("Largest", money(trades["notional"].max() if "notional" in trades and not trades.empty else 0))
    metrics[3].metric("Markets", f"{trades['title'].nunique() if 'title' in trades else 0:,}")
    metrics[4].metric("Wallets", f"{trades['wallet'].nunique() if 'wallet' in trades else 0:,}")
    flow = live_market_flow(trades)
    live_chips: list[str] = []
    if query.strip():
        live_chips.append(f"Search: {query.strip()}")
    if platforms and set(platforms) != {"Polymarket", "Kalshi"}:
        live_chips.append("Platform: " + ", ".join(platforms))
    if sides:
        live_chips.append("Side/outcome: " + ", ".join(sides))
    if float(effective_min_notional) > 0:
        live_chips.append(f"Min notional: {money(effective_min_notional)}")
    live_chips.append(f"Rows: {rows}")
    if large_only:
        live_chips.append(f"Whale prints >= {money(min_whale)}")
    if tracked_markets_only:
        live_chips.append("Tracked markets only")
    if tracked_wallets_only:
        live_chips.append("Tracked wallets only")
    render_filter_chips(live_chips)
    live_defaults = live_trade_filter_defaults(rows=int(trade_limit))
    live_clear_actions: list[tuple[str, dict[str, Any]]] = []
    if query.strip():
        live_clear_actions.append(("search", {"live_search": ""}))
    if set(platforms) != set(live_defaults["live_platforms"]):
        live_clear_actions.append(("platform", {"live_platforms": live_defaults["live_platforms"]}))
    if sides:
        live_clear_actions.append(("side/outcome", {"live_sides": []}))
    if int(min_notional) > 0:
        live_clear_actions.append(("min notional", {"live_min_notional": 0}))
    if int(rows) != int(live_defaults["live_rows"]):
        live_clear_actions.append(("rows", {"live_rows": live_defaults["live_rows"]}))
    if large_only:
        live_clear_actions.append(("whale only", {"live_large_only": False}))
    if tracked_markets_only:
        live_clear_actions.append(("tracked markets", {"live_tracked_markets_only": False}))
    if tracked_wallets_only:
        live_clear_actions.append(("tracked wallets", {"live_tracked_wallets_only": False}))
    render_filter_clear_buttons(live_clear_actions, "live")
    if st.session_state.saved_live_filters:
        st.caption(f"Saved live views: {len(st.session_state.saved_live_filters)}")
        with st.expander("Saved live trade filters", expanded=False):
            st.dataframe(pd.DataFrame(st.session_state.saved_live_filters), width="stretch", height=160)
            if st.button("Clear saved live filters"):
                st.session_state.saved_live_filters = []
                save_local_list("saved_live_filters.json", st.session_state.saved_live_filters)
                st.rerun()
    if not trades.empty:
        live_action_cols = st.columns([1.1, 1.1, 1.1, 2.7])
        live_action_cols[0].download_button(
            "Export live trades CSV",
            trades.to_csv(index=False).encode("utf-8"),
            file_name="live_trades.csv",
            mime="text/csv",
            width="stretch",
        )
        if live_action_cols[1].button("Track tape wallets", key="live_track_tape_wallets", width="stretch"):
            st.session_state.followed_wallets, changed_wallets = md.upsert_followed_wallets(st.session_state.followed_wallets, trades)
            if changed_wallets:
                save_local_list("followed_wallets.json", st.session_state.followed_wallets)
                st.success(f"Tracked {changed_wallets} visible trade wallets.")
            else:
                st.info("Visible trade wallets are already tracked or unavailable.")
        if live_action_cols[2].button("Track tape markets", key="live_track_tape_markets", width="stretch"):
            st.session_state.watchlist, changed_markets = md.upsert_watchlist_markets(st.session_state.watchlist, trades)
            if changed_markets:
                save_local_list("watchlist.json", st.session_state.watchlist)
                st.success(f"Tracked {changed_markets} visible trade markets.")
            else:
                st.info("Visible trade markets are already tracked.")
        live_action_cols[3].caption(f"Actions apply to the {len(trades):,} trades currently shown after filters and row limit.")

    tab_tape, tab_inspect, tab_chart, tab_wallets, tab_markets, tab_bias, tab_track = st.tabs(["Trade tape", "Inspect Trade", "Flow chart", "Top wallets", "Market Flow", "Outcome Bias", "Track Actions"])
    with tab_tape:
        display_source = trades.copy()
        display_source["wallet_short"] = display_source.get("wallet", pd.Series("", index=display_source.index)).astype(str).map(short_addr)
        display_source["trader_display"] = display_source.get("trader", pd.Series("", index=display_source.index)).astype(str)
        display_source["trader_display"] = display_source["trader_display"].where(display_source["trader_display"].str.len() > 0, display_source["wallet_short"])
        display_source["market"] = display_source.get("platform", pd.Series("", index=display_source.index)).astype(str) + " - " + display_source.get("title", pd.Series("", index=display_source.index)).astype(str)
        display_source["price_c"] = numeric_col(display_source, "price") * 100
        display_source["notional_usd"] = numeric_col(display_source, "notional")
        trade_times = pd.to_datetime(display_source.get("time"), utc=True, errors="coerce")
        age_minutes = (pd.Timestamp.now(tz="UTC") - trade_times).dt.total_seconds() / 60
        display_source["age_min"] = age_minutes.where(age_minutes >= 0)
        display_source["time_utc"] = trade_times.dt.strftime("%Y-%m-%d %H:%M:%S").fillna("-")
        tx_hash = display_source.get("transaction_hash", pd.Series("", index=display_source.index)).astype(str)
        display_source["tx_url"] = tx_hash.map(lambda value: f"https://polygonscan.com/tx/{value}" if value.startswith("0x") else "")
        display = clean_table(
            display_source,
            [
                "platform",
                "time_utc",
                "age_min",
                "trader_display",
                "wallet_short",
                "side",
                "outcome",
                "market",
                "price_c",
                "size",
                "notional_usd",
                "tx_url",
                "url",
            ],
        )
        if "wallet" in display:
            display["wallet"] = display["wallet"].astype(str).map(short_addr)
        st.dataframe(
            display,
            width="stretch",
            height=520,
            column_config={
                "time_utc": st.column_config.TextColumn("Time UTC"),
                "age_min": st.column_config.NumberColumn("Age min", format="%.1f"),
                "trader_display": st.column_config.TextColumn("Trader", width="medium"),
                "wallet_short": st.column_config.TextColumn("Wallet"),
                "market": st.column_config.TextColumn("Market", width="large"),
                "price_c": st.column_config.NumberColumn("Price", format="%.1fc"),
                "size": st.column_config.NumberColumn(format="%.2f"),
                "notional_usd": st.column_config.NumberColumn("Notional", format="$%.0f"),
                "tx_url": st.column_config.LinkColumn("TX"),
                "url": st.column_config.LinkColumn("URL"),
            },
        )
    with tab_inspect:
        if trades.empty:
            draw_empty("No live trade is available to inspect.")
        else:
            inspect_options = [
                f"{i + 1}. {row.get('platform', '-')} | {row.get('side', '-')} {row.get('outcome', '-')} | {money(row.get('notional', 0.0))} | {str(row.get('title', ''))[:90]}"
                for i, row in trades.head(150).iterrows()
            ]
            selected_trade = st.selectbox("Inspect live trade", inspect_options, key="live_inspect_trade")
            trade_row = trades.iloc[inspect_options.index(selected_trade)]
            wallet_value = str(trade_row.get("wallet", ""))
            market_key = str(trade_row.get("market_key", "") or trade_row.get("ticker", "") or trade_row.get("title", ""))
            tx_value = str(trade_row.get("transaction_hash", ""))
            i1, i2, i3, i4, i5 = st.columns(5)
            i1.metric("Platform", str(trade_row.get("platform", "-")))
            i2.metric("Side", f"{trade_row.get('side', '-')} {trade_row.get('outcome', '')}".strip())
            i3.metric("Price", cents(trade_row.get("price")))
            i4.metric("Size", f"{float(trade_row.get('size', 0.0) or 0.0):,.2f}")
            i5.metric("Notional", money(trade_row.get("notional", 0.0)))
            st.markdown(f"**{trade_row.get('title', '-')}**")
            link_cols = st.columns([1, 1, 1, 3])
            if str(trade_row.get("url", "")):
                link_cols[0].link_button("Open market", str(trade_row.get("url", "")), width="stretch")
            if tx_value.startswith("0x"):
                link_cols[1].link_button("Open tx", f"https://polygonscan.com/tx/{tx_value}", width="stretch")
            if re.fullmatch(r"0x[a-fA-F0-9]{40}", wallet_value):
                link_cols[2].link_button("Open wallet", f"https://polymarket.com/profile/{wallet_value}", width="stretch")
            action_cols = st.columns([1, 1, 1, 3])
            if action_cols[0].button("Track inspected market", key="live_inspect_track_market", width="stretch"):
                item = {
                    "platform": str(trade_row.get("platform", "")),
                    "market_key": market_key,
                    "title": str(trade_row.get("title", "")),
                    "url": str(trade_row.get("url", "")),
                }
                if item["market_key"] not in [w["market_key"] for w in st.session_state.watchlist]:
                    st.session_state.watchlist.append(item)
                    save_local_list("watchlist.json", st.session_state.watchlist)
                    st.success("Inspected market added to watchlist.")
            if action_cols[1].button("Track inspected wallet", key="live_inspect_track_wallet", width="stretch"):
                if re.fullmatch(r"0x[a-fA-F0-9]{40}", wallet_value) and wallet_value.lower() not in [w.lower() for w in st.session_state.followed_wallets]:
                    st.session_state.followed_wallets.append(wallet_value)
                    save_local_list("followed_wallets.json", st.session_state.followed_wallets)
                    st.success("Inspected wallet added to tracked wallets.")
            if action_cols[2].button("Paper trade this market", key="live_inspect_paper_trade", width="stretch"):
                st.session_state.live_trade_ticket = {
                    "platform": str(trade_row.get("platform", "")),
                    "market_key": market_key,
                    "title": str(trade_row.get("title", "")),
                    "url": str(trade_row.get("url", "")),
                    "yes_price": float(trade_row.get("price", 0.0) or 0.0) if str(trade_row.get("outcome", "")).lower() == "yes" else 0.0,
                    "no_price": float(trade_row.get("price", 0.0) or 0.0) if str(trade_row.get("outcome", "")).lower() == "no" else 0.0,
                }
                st.info("Paper ticket staged below. Adjust side, outcome, and amount before submitting.")
            if "live_trade_ticket" in st.session_state:
                ticket = pd.Series(st.session_state.live_trade_ticket)
                render_research_trade_ticket(ticket)
            show_wallet_detail = st.toggle("Load inspected wallet detail", value=False, key="live_inspect_wallet_detail")
            if show_wallet_detail:
                if re.fullmatch(r"0x[a-fA-F0-9]{40}", wallet_value):
                    render_wallet(wallet_value)
                else:
                    draw_empty("This trade source does not expose a public Polymarket wallet.")
    with tab_chart:
        fig = px.scatter(
            trades,
            x="time",
            y="notional",
            color="platform",
            size="notional",
            hover_data=["trader", "wallet", "side", "outcome", "title"],
            template="plotly_dark",
            color_discrete_map={"Polymarket": ACCENT, "Kalshi": BLUE},
        )
        fig.update_layout(height=430, margin=dict(l=10, r=10, t=20, b=10), paper_bgcolor=BG, plot_bgcolor=BG)
        st.plotly_chart(fig, width="stretch", config=plot_config())
    with tab_wallets:
        wallets = md.whale_wallets(trades[trades["platform"].eq("Polymarket")]) if "platform" in trades else pd.DataFrame()
        if wallets.empty:
            draw_empty("No Polymarket wallet-level trades in the current tape.")
        else:
            display = wallets.head(40).copy()
            display["wallet"] = display["wallet"].astype(str).map(short_addr)
            st.dataframe(display, width="stretch", height=430, column_config={"notional": st.column_config.NumberColumn(format="$%.0f"), "avg_trade": st.column_config.NumberColumn(format="$%.0f")})
    with tab_markets:
        if flow.empty:
            draw_empty("No market-level flow available.")
        else:
            st.dataframe(
                clean_table(
                    flow,
                    [
                        "platform",
                        "title",
                        "trades",
                        "notional",
                        "avg_trade",
                        "largest_trade",
                        "unique_wallets",
                        "buy_notional",
                        "sell_notional",
                        "net_buy_notional",
                        "latest_trade",
                        "url",
                    ],
                ),
                width="stretch",
                height=460,
                column_config={
                    "notional": st.column_config.NumberColumn(format="$%.0f"),
                    "avg_trade": st.column_config.NumberColumn(format="$%.0f"),
                    "largest_trade": st.column_config.NumberColumn(format="$%.0f"),
                    "buy_notional": st.column_config.NumberColumn(format="$%.0f"),
                    "sell_notional": st.column_config.NumberColumn(format="$%.0f"),
                    "net_buy_notional": st.column_config.NumberColumn(format="$%.0f"),
                    "url": st.column_config.LinkColumn("URL"),
                },
            )
    with tab_bias:
        if flow.empty:
            draw_empty("No outcome-bias flow available.")
        else:
            bias = flow.copy()
            bias["yes_share_pct"] = pd.to_numeric(bias["yes_share"], errors="coerce") * 100
            bias["no_share_pct"] = pd.to_numeric(bias["no_share"], errors="coerce") * 100
            fig = px.bar(
                bias.head(25),
                x="title",
                y=["yes_notional", "no_notional"],
                template="plotly_dark",
                labels={"value": "notional", "title": "market"},
                color_discrete_map={"yes_notional": ACCENT, "no_notional": RED},
            )
            fig.update_layout(height=420, margin=dict(l=10, r=10, t=20, b=120), paper_bgcolor=BG, plot_bgcolor=BG)
            st.plotly_chart(fig, width="stretch", config=plot_config())
            st.dataframe(
                clean_table(bias, ["platform", "title", "flow_bias", "yes_share_pct", "no_share_pct", "yes_notional", "no_notional", "notional", "url"]).head(80),
                width="stretch",
                height=360,
                column_config={
                    "yes_share_pct": st.column_config.NumberColumn("Yes Share", format="%.1f%%"),
                    "no_share_pct": st.column_config.NumberColumn("No Share", format="%.1f%%"),
                    "yes_notional": st.column_config.NumberColumn(format="$%.0f"),
                    "no_notional": st.column_config.NumberColumn(format="$%.0f"),
                    "notional": st.column_config.NumberColumn(format="$%.0f"),
                    "url": st.column_config.LinkColumn("URL"),
                },
            )
    with tab_track:
        left, right = st.columns([1, 1])
        with left:
            st.markdown("### Track market from flow")
            if flow.empty:
                draw_empty("No market flow to track.")
            else:
                market_options = [f"{row.platform}: {str(row.title)[:100]} | {money(row.notional)}" for _, row in flow.head(80).iterrows()]
                selected_market = st.selectbox("Flow market", market_options, key="live_track_market")
                flow_row = flow.iloc[market_options.index(selected_market)]
                if st.button("Track selected market", key="live_track_market_button"):
                    item = {
                        "platform": str(flow_row.get("platform", "")),
                        "market_key": str(flow_row.get("market_key", "") or flow_row.get("title", "")),
                        "title": str(flow_row.get("title", "")),
                        "url": str(flow_row.get("url", "")),
                    }
                    if item["market_key"] not in [w["market_key"] for w in st.session_state.watchlist]:
                        st.session_state.watchlist.append(item)
                        save_local_list("watchlist.json", st.session_state.watchlist)
                        st.success("Market added to watchlist.")
        with right:
            st.markdown("### Track wallet from tape")
            wallet_rows = md.whale_wallets(trades[trades["platform"].eq("Polymarket")]) if "platform" in trades else pd.DataFrame()
            if wallet_rows.empty:
                draw_empty("No public Polymarket wallets in this filtered tape.")
            else:
                wallet_options = [
                    f"{short_addr(str(row.get('wallet', '')))} | {money(row.get('notional', 0.0))} | "
                    f"{int(row.get('trade_count', row.get('trades', 0)) or 0)} trades"
                    for _, row in wallet_rows.head(80).iterrows()
                ]
                selected_wallet = st.selectbox("Flow wallet", wallet_options, key="live_track_wallet")
                wallet_row = wallet_rows.iloc[wallet_options.index(selected_wallet)]
                wallet_value = str(wallet_row.get("wallet", ""))
                if st.button("Track selected wallet", key="live_track_wallet_button"):
                    if re.fullmatch(r"0x[a-fA-F0-9]{40}", wallet_value) and wallet_value.lower() not in [w.lower() for w in st.session_state.followed_wallets]:
                        st.session_state.followed_wallets.append(wallet_value)
                        save_local_list("followed_wallets.json", st.session_state.followed_wallets)
                        st.success("Wallet added to tracked wallets.")


def page_whale_flow() -> None:
    section_header("Whale Flow", "Recent large prints, wallet aggregation, and ticker-level Kalshi flow.")
    if "whale_query" not in st.session_state:
        reset_whale_flow_filter_widgets(global_query, 200, int(min_whale))
    if st.session_state.pop("whale_filters_reset_pending", False):
        reset_whale_flow_filter_widgets(global_query, 200, int(min_whale))
    pending_whale_view = st.session_state.pop("pending_whale_filter_view", None)
    if isinstance(pending_whale_view, dict):
        apply_whale_flow_filter_view_widgets(pending_whale_view)
    pending_whale_clear = st.session_state.pop("whale_clear_pending", None)
    if isinstance(pending_whale_clear, dict):
        for key, value in pending_whale_clear.items():
            st.session_state[key] = value
    route_filter_params = query_param_snapshot(
        [
            "q",
            "query",
            "search",
            "wallet",
            "market",
            "platform",
            "platforms",
            "venue",
            "venues",
            "side",
            "sides",
            "outcome",
            "outcomes",
            "rows",
            "limit",
            "minNotional",
            "notionalMin",
            "minPrint",
            "printMin",
            "whaleMin",
            "minWalletNotional",
            "walletNotionalMin",
            "walletMin",
            "minWalletTrades",
            "walletTradesMin",
            "tradesMin",
            "bias",
            "outcomeBias",
            "biasFilter",
            "trackedWallets",
            "tracked_wallets",
            "walletsTracked",
            "watchedWallets",
        ]
    )
    route_filter_signature = json.dumps(route_filter_params, sort_keys=True)
    route_filter_view = md.predictparity_whale_filter_view(route_filter_params)
    if route_filter_view and st.session_state.get("whale_route_filter_signature") != route_filter_signature:
        apply_whale_flow_filter_view_widgets(route_filter_view)
        st.session_state["whale_route_filter_signature"] = route_filter_signature
        st.session_state["whale_view_loaded_message"] = "Loaded whale-flow filters from URL."

    controls = st.columns([1.5, 1, 1, 1])
    whale_query = controls[0].text_input("Whale search", placeholder="market, wallet, trader, outcome", key="whale_query")
    whale_platforms = controls[1].multiselect("Platform", ["Polymarket", "Kalshi"], key="whale_platforms")
    whale_sides = controls[2].multiselect("Side / outcome", ["BUY", "SELL", "yes", "no"], key="whale_sides")
    whale_rows = controls[3].slider("Rows", min_value=50, max_value=500, step=50, key="whale_rows")
    with st.expander("Whale flow filters", expanded=True):
        f1, f2, f3, f4, f5 = st.columns(5)
        whale_min_notional = f1.number_input("Min print notional", min_value=0, step=500, key="whale_min_notional")
        whale_min_wallet_notional = f2.number_input("Min wallet notional", min_value=0, step=1000, key="whale_min_wallet_notional")
        whale_min_wallet_trades = f3.number_input("Min wallet trades", min_value=1, step=1, key="whale_min_wallet_trades")
        whale_bias_filter = f4.radio("Outcome bias", ["Any", "YES", "NO", "Mixed"], horizontal=True, key="whale_bias_filter")
        tracked_wallets_only = f5.checkbox("Tracked wallets only", key="whale_tracked_wallets_only")
        if st.button("Reset Filters", width="stretch", key="reset_whale_filters_button"):
            st.session_state["whale_filters_reset_pending"] = True
            st.rerun()

    save_cols = st.columns([2, 1, 1])
    saved_whale_name = save_cols[0].text_input("Saved whale view name", value=f"Whale Flow {md.now_utc_label()}", key="saved_whale_view_name")
    save_whale_clicked = save_cols[1].button("Save Filter", width="stretch", key="save_whale_filter_button")
    if save_cols[2].button("Reset Whale View", width="stretch", key="reset_whale_view_button"):
        st.session_state["whale_filters_reset_pending"] = True
        st.rerun()
    loaded_whale_message = st.session_state.pop("whale_view_loaded_message", "")
    if loaded_whale_message:
        st.info(loaded_whale_message)
    if st.session_state.saved_whale_filters:
        load_cols = st.columns([2, 1, 1])
        saved_labels = [
            f"{i + 1}. {view.get('name') or view.get('query') or 'Whale flow view'}"
            for i, view in enumerate(st.session_state.saved_whale_filters)
        ]
        selected_saved_whale = load_cols[0].selectbox("Load saved whale view", saved_labels, key="load_saved_whale_view")
        selected_whale_view = st.session_state.saved_whale_filters[saved_labels.index(selected_saved_whale)]
        if load_cols[1].button("Load whale view", key="load_whale_view_button"):
            st.session_state["pending_whale_filter_view"] = selected_whale_view
            st.session_state["whale_view_loaded_message"] = f"Loaded saved whale view: {selected_whale_view.get('name', selected_saved_whale)}"
            st.rerun()
        if load_cols[2].button("Delete whale view", key="delete_whale_view_button"):
            st.session_state.saved_whale_filters.pop(saved_labels.index(selected_saved_whale))
            save_local_list("saved_whale_filters.json", st.session_state.saved_whale_filters)
            st.rerun()
    if save_whale_clicked:
        st.session_state.saved_whale_filters.append(
            {
                "name": saved_whale_name.strip() or f"Whale Flow {md.now_utc_label()}",
                "created_at": md.now_utc_label(),
                "query": whale_query,
                "platforms": whale_platforms,
                "sides": whale_sides,
                "rows": int(whale_rows),
                "min_notional": int(whale_min_notional),
                "min_wallet_notional": int(whale_min_wallet_notional),
                "min_wallet_trades": int(whale_min_wallet_trades),
                "bias_filter": whale_bias_filter,
                "tracked_wallets_only": bool(tracked_wallets_only),
            }
        )
        save_local_list("saved_whale_filters.json", st.session_state.saved_whale_filters)
        st.success("Saved whale flow view.")

    poly_trades = safe_load("Polymarket trades", load_polymarket_trades, trade_limit, 0.0, None, None)
    kalshi_trades = safe_load("Kalshi trades", load_kalshi_trades, trade_limit, None)
    trades = combined_trade_table(poly_trades, kalshi_trades)
    if not trades.empty:
        trades = filter_text(trades, whale_query)
        if whale_platforms:
            trades = trades[trades["platform"].isin(whale_platforms)]
        else:
            trades = trades.iloc[0:0]
        if whale_sides:
            side_mask = trades["side"].astype(str).str.upper().isin([item.upper() for item in whale_sides])
            outcome_mask = trades.get("outcome", pd.Series("", index=trades.index)).astype(str).str.upper().isin([item.upper() for item in whale_sides])
            trades = trades[side_mask | outcome_mask]
        trades = trades[numeric_col(trades, "notional") >= float(whale_min_notional)]
        if tracked_wallets_only:
            tracked_wallets = {item.lower() for item in st.session_state.followed_wallets}
            trades = trades[trades.get("wallet", pd.Series("", index=trades.index)).astype(str).str.lower().isin(tracked_wallets)] if tracked_wallets else trades.iloc[0:0]
    flow = live_market_flow(trades)
    if whale_bias_filter != "Any" and not flow.empty:
        flow = flow[flow["flow_bias"].eq(whale_bias_filter)]
        keys = set(flow.get("market_key", pd.Series("", index=flow.index)).astype(str))
        titles = set(flow.get("title", pd.Series("", index=flow.index)).astype(str))
        if "market_key" in trades:
            trades = trades[trades["market_key"].astype(str).isin(keys) | trades["title"].astype(str).isin(titles)]
        elif "title" in trades:
            trades = trades[trades["title"].astype(str).isin(titles)]
    trades = trades.sort_values("time", ascending=False).head(int(whale_rows)).reset_index(drop=True) if not trades.empty and "time" in trades else trades.head(int(whale_rows))

    whale_defaults = whale_flow_filter_defaults(min_notional=int(min_whale))
    chips: list[str] = []
    if whale_query.strip():
        chips.append(f"Search: {whale_query.strip()}")
    if set(whale_platforms) != set(whale_defaults["whale_platforms"]):
        chips.append("Platform: " + (", ".join(whale_platforms) if whale_platforms else "none"))
    if whale_sides:
        chips.append("Side/outcome: " + ", ".join(whale_sides))
    if int(whale_rows) != int(whale_defaults["whale_rows"]):
        chips.append(f"Rows: {int(whale_rows)}")
    if int(whale_min_notional) > 0:
        chips.append(f"Print >= {money(whale_min_notional)}")
    if int(whale_min_wallet_notional) > 0:
        chips.append(f"Wallet notional >= {money(whale_min_wallet_notional)}")
    if int(whale_min_wallet_trades) > 1:
        chips.append(f"Wallet trades >= {int(whale_min_wallet_trades)}")
    if whale_bias_filter != "Any":
        chips.append(f"Bias: {whale_bias_filter}")
    if tracked_wallets_only:
        chips.append("Tracked wallets only")
    render_filter_chips(chips)

    clear_actions: list[tuple[str, dict[str, Any]]] = []
    if whale_query.strip():
        clear_actions.append(("search", {"whale_query": ""}))
    if set(whale_platforms) != set(whale_defaults["whale_platforms"]):
        clear_actions.append(("platform", {"whale_platforms": whale_defaults["whale_platforms"]}))
    if whale_sides:
        clear_actions.append(("side/outcome", {"whale_sides": []}))
    if int(whale_rows) != int(whale_defaults["whale_rows"]):
        clear_actions.append(("rows", {"whale_rows": whale_defaults["whale_rows"]}))
    if int(whale_min_notional) > 0:
        clear_actions.append(("print notional", {"whale_min_notional": 0}))
    if int(whale_min_wallet_notional) > 0:
        clear_actions.append(("wallet notional", {"whale_min_wallet_notional": 0}))
    if int(whale_min_wallet_trades) > 1:
        clear_actions.append(("wallet trades", {"whale_min_wallet_trades": 1}))
    if whale_bias_filter != "Any":
        clear_actions.append(("bias", {"whale_bias_filter": "Any"}))
    if tracked_wallets_only:
        clear_actions.append(("tracked wallets", {"whale_tracked_wallets_only": False}))
    render_filter_clear_buttons(clear_actions, "whale")
    if st.session_state.saved_whale_filters:
        st.caption(f"Saved whale views: {len(st.session_state.saved_whale_filters)}")
        with st.expander("Saved whale filters", expanded=False):
            st.dataframe(pd.DataFrame(st.session_state.saved_whale_filters), width="stretch", height=160)
            if st.button("Clear saved whale filters"):
                st.session_state.saved_whale_filters = []
                save_local_list("saved_whale_filters.json", st.session_state.saved_whale_filters)
                st.rerun()

    if trades.empty:
        draw_empty("No large trades match the current threshold.")
        return
    cols = st.columns(4)
    cols[0].metric("Large prints", f"{len(trades):,}")
    cols[1].metric("Combined notional", money(trades["notional"].sum()))
    cols[2].metric("Largest print", money(trades["notional"].max()))
    cols[3].metric("Markets touched", f"{trades['title'].nunique():,}")
    left, right = st.columns([1.3, 1])
    with left:
        fig = px.scatter(
            trades,
            x="time",
            y="notional",
            color="platform",
            size="notional",
            hover_data=["trader", "wallet", "side", "outcome", "title"],
            template="plotly_dark",
            color_discrete_map={"Polymarket": ACCENT, "Kalshi": BLUE},
        )
        fig.update_layout(height=390, margin=dict(l=10, r=10, t=20, b=10), paper_bgcolor=BG, plot_bgcolor=BG)
        st.plotly_chart(fig, width="stretch", config=plot_config())
    with right:
        wallets = md.whale_wallets(trades[trades["platform"].eq("Polymarket")]) if "platform" in trades else pd.DataFrame()
        if not wallets.empty:
            wallets = wallets[
                (numeric_col(wallets, "notional") >= float(whale_min_wallet_notional))
                & (numeric_col(wallets, "trade_count") >= float(whale_min_wallet_trades))
            ]
        st.markdown("### Top Polymarket whale wallets")
        if wallets.empty:
            draw_empty("No wallet-level Polymarket whale data returned.")
        else:
            display = wallets.head(20).copy()
            display["wallet"] = display["wallet"].astype(str).map(short_addr)
            st.download_button("Export whale wallets CSV", wallets.to_csv(index=False).encode("utf-8"), file_name="whale_wallets.csv", mime="text/csv")
            st.dataframe(
                display,
                width="stretch",
                height=390,
                column_config={"notional": st.column_config.NumberColumn(format="$%.0f"), "avg_trade": st.column_config.NumberColumn(format="$%.0f")},
            )

    tab_tape, tab_markets, tab_bias, tab_track = st.tabs(["Trade Tape", "Market Flow", "Outcome Bias", "Track Actions"])
    with tab_tape:
        st.markdown("### Trade tape")
        tape = clean_table(trades, ["platform", "time", "trader", "wallet", "side", "outcome", "title", "price", "size", "notional", "url"])
        if "wallet" in tape:
            tape["wallet"] = tape["wallet"].astype(str).map(short_addr)
        st.download_button("Export whale tape CSV", trades.to_csv(index=False).encode("utf-8"), file_name="whale_trade_tape.csv", mime="text/csv")
        st.dataframe(
            tape.head(int(whale_rows)),
            width="stretch",
            height=520,
            column_config={
                "time": st.column_config.DatetimeColumn(format="YYYY-MM-DD HH:mm"),
                "price": st.column_config.NumberColumn(format="%.4f"),
                "size": st.column_config.NumberColumn(format="%.2f"),
                "notional": st.column_config.NumberColumn(format="$%.0f"),
                "url": st.column_config.LinkColumn("URL"),
            },
        )
    with tab_markets:
        if flow.empty:
            draw_empty("No market-level whale flow matches the current filters.")
        else:
            st.download_button("Export whale market flow CSV", flow.to_csv(index=False).encode("utf-8"), file_name="whale_market_flow.csv", mime="text/csv")
            st.dataframe(
                clean_table(flow, ["platform", "title", "trades", "notional", "avg_trade", "largest_trade", "unique_wallets", "buy_notional", "sell_notional", "net_buy_notional", "latest_trade", "url"]).head(int(whale_rows)),
                width="stretch",
                height=460,
                column_config={
                    "notional": st.column_config.NumberColumn(format="$%.0f"),
                    "avg_trade": st.column_config.NumberColumn(format="$%.0f"),
                    "largest_trade": st.column_config.NumberColumn(format="$%.0f"),
                    "buy_notional": st.column_config.NumberColumn(format="$%.0f"),
                    "sell_notional": st.column_config.NumberColumn(format="$%.0f"),
                    "net_buy_notional": st.column_config.NumberColumn(format="$%.0f"),
                    "url": st.column_config.LinkColumn("URL"),
                },
            )
    with tab_bias:
        if flow.empty:
            draw_empty("No outcome-bias flow matches the current filters.")
        else:
            bias = flow.copy()
            bias["yes_share_pct"] = pd.to_numeric(bias["yes_share"], errors="coerce") * 100
            bias["no_share_pct"] = pd.to_numeric(bias["no_share"], errors="coerce") * 100
            st.dataframe(
                clean_table(bias, ["platform", "title", "flow_bias", "yes_share_pct", "no_share_pct", "yes_notional", "no_notional", "notional", "url"]).head(int(whale_rows)),
                width="stretch",
                height=430,
                column_config={
                    "yes_share_pct": st.column_config.NumberColumn("Yes Share", format="%.1f%%"),
                    "no_share_pct": st.column_config.NumberColumn("No Share", format="%.1f%%"),
                    "yes_notional": st.column_config.NumberColumn(format="$%.0f"),
                    "no_notional": st.column_config.NumberColumn(format="$%.0f"),
                    "notional": st.column_config.NumberColumn(format="$%.0f"),
                    "url": st.column_config.LinkColumn("URL"),
                },
            )
    with tab_track:
        c1, c2 = st.columns([1, 1])
        with c1:
            st.markdown("### Track market from whale flow")
            if flow.empty:
                draw_empty("No market flow to track.")
            else:
                market_options = [f"{row.platform}: {str(row.title)[:100]} | {money(row.notional)}" for _, row in flow.head(80).iterrows()]
                selected_market = st.selectbox("Whale market", market_options, key="whale_track_market")
                flow_row = flow.iloc[market_options.index(selected_market)]
                if st.button("Track selected whale market", key="whale_track_market_button"):
                    item = {
                        "platform": str(flow_row.get("platform", "")),
                        "market_key": str(flow_row.get("market_key", "") or flow_row.get("title", "")),
                        "title": str(flow_row.get("title", "")),
                        "url": str(flow_row.get("url", "")),
                    }
                    if item["market_key"] not in [w["market_key"] for w in st.session_state.watchlist]:
                        st.session_state.watchlist.append(item)
                        save_local_list("watchlist.json", st.session_state.watchlist)
                        st.success("Market added to watchlist.")
        with c2:
            st.markdown("### Track wallet from whale flow")
            if wallets.empty:
                draw_empty("No whale wallets to track.")
            else:
                wallet_options = [f"{short_addr(str(row.wallet))} | {money(row.notional)} | {int(row.trade_count)} trades" for _, row in wallets.head(80).iterrows()]
                selected_wallet = st.selectbox("Whale wallet", wallet_options, key="whale_track_wallet")
                wallet_row = wallets.iloc[wallet_options.index(selected_wallet)]
                wallet_value = str(wallet_row.get("wallet", ""))
                if st.button("Track selected whale wallet", key="whale_track_wallet_button"):
                    if re.fullmatch(r"0x[a-fA-F0-9]{40}", wallet_value) and wallet_value.lower() not in [w.lower() for w in st.session_state.followed_wallets]:
                        st.session_state.followed_wallets.append(wallet_value)
                        save_local_list("followed_wallets.json", st.session_state.followed_wallets)
                        st.success("Wallet added to tracked wallets.")


def page_cross_venue() -> None:
    section_header("Cross-Venue", "Find similar Polymarket and Kalshi contracts, then inspect yes-price gaps.")
    pm, ks, _combined = load_market_universe()
    if "cross_query" not in st.session_state:
        reset_cross_venue_filter_widgets(global_query)
    if st.session_state.pop("cross_filters_reset_pending", False):
        reset_cross_venue_filter_widgets(global_query)
    pending_cross_view = st.session_state.pop("pending_cross_filter_view", None)
    if isinstance(pending_cross_view, dict):
        apply_cross_venue_filter_view_widgets(pending_cross_view)
    pending_cross_clear = st.session_state.pop("cross_clear_pending", None)
    if isinstance(pending_cross_clear, dict):
        for key, value in pending_cross_clear.items():
            st.session_state[key] = value
    route_filter_params = query_param_snapshot(
        [
            "q",
            "query",
            "search",
            "market",
            "event",
            "minSimilarity",
            "similarityMin",
            "minSim",
            "maxPairs",
            "pairs",
            "rows",
            "limit",
            "minGapCents",
            "gapCentsMin",
            "minGap",
            "gapMin",
            "minPolymarketVolume",
            "pmVolumeMin",
            "polyVolumeMin",
            "minKalshiVolume",
            "ksVolumeMin",
            "kalshiVolumeMin",
            "lower",
            "lowerYes",
            "cheaper",
            "cheaperVenue",
            "minPrice",
            "maxPrice",
            "priceMin",
            "priceMax",
            "probMin",
            "probMax",
        ]
    )
    route_filter_signature = json.dumps(route_filter_params, sort_keys=True)
    route_filter_view = md.predictparity_cross_venue_filter_view(route_filter_params)
    if route_filter_view and st.session_state.get("cross_route_filter_signature") != route_filter_signature:
        apply_cross_venue_filter_view_widgets(route_filter_view)
        st.session_state["cross_route_filter_signature"] = route_filter_signature
        st.session_state["cross_view_loaded_message"] = "Loaded cross-venue filters from URL."

    col1, col2, col3 = st.columns([2, 1, 1])
    query = col1.text_input("Pairing query", placeholder="bitcoin, fed, iran, election", key="cross_query")
    min_similarity = col2.slider("Min similarity", min_value=0.10, max_value=0.70, step=0.02, key="cross_min_similarity")
    max_pairs = col3.slider("Max pairs", min_value=10, max_value=150, step=10, key="cross_max_pairs")
    with st.expander("Cross-venue filters", expanded=True):
        f1, f2, f3, f4, f5, f6 = st.columns(6)
        min_gap_cents = f1.number_input("Min gap (c)", min_value=0.0, step=0.5, key="cross_min_gap_cents")
        min_pm_volume = f2.number_input("Min Polymarket volume", min_value=0, step=1000, key="cross_min_pm_volume")
        min_ks_volume = f3.number_input("Min Kalshi volume", min_value=0, step=1000, key="cross_min_ks_volume")
        lower_filter = f4.radio("Lower yes", ["Any", "Polymarket", "Kalshi"], horizontal=True, key="cross_lower_filter")
        min_price_pct = f5.slider("Min yes price", min_value=0, max_value=100, step=1, key="cross_min_price_pct")
        max_price_pct = f5.slider("Max yes price", min_value=0, max_value=100, step=1, key="cross_max_price_pct")
        if f6.button("Reset Filters", width="stretch", key="reset_cross_filters_button"):
            st.session_state["cross_filters_reset_pending"] = True
            st.rerun()
    save_cols = st.columns([2, 1, 1])
    saved_cross_name = save_cols[0].text_input("Saved cross-venue view name", value=f"Cross-Venue {md.now_utc_label()}", key="saved_cross_view_name")
    save_cross_clicked = save_cols[1].button("Save Filter", width="stretch", key="save_cross_filter_button")
    if save_cols[2].button("Reset Cross View", width="stretch", key="reset_cross_view_button"):
        st.session_state["cross_filters_reset_pending"] = True
        st.rerun()
    loaded_cross_message = st.session_state.pop("cross_view_loaded_message", "")
    if loaded_cross_message:
        st.info(loaded_cross_message)
    if st.session_state.saved_cross_filters:
        load_cols = st.columns([2, 1, 1])
        saved_labels = [
            f"{i + 1}. {view.get('name') or view.get('query') or 'Cross-venue view'}"
            for i, view in enumerate(st.session_state.saved_cross_filters)
        ]
        selected_saved_cross = load_cols[0].selectbox("Load saved cross-venue view", saved_labels, key="load_saved_cross_view")
        selected_cross_view = st.session_state.saved_cross_filters[saved_labels.index(selected_saved_cross)]
        if load_cols[1].button("Load cross view", key="load_cross_view_button"):
            st.session_state["pending_cross_filter_view"] = selected_cross_view
            st.session_state["cross_view_loaded_message"] = f"Loaded saved cross-venue view: {selected_cross_view.get('name', selected_saved_cross)}"
            st.rerun()
        if load_cols[2].button("Delete cross view", key="delete_cross_view_button"):
            st.session_state.saved_cross_filters.pop(saved_labels.index(selected_saved_cross))
            save_local_list("saved_cross_filters.json", st.session_state.saved_cross_filters)
            st.rerun()
    if save_cross_clicked:
        st.session_state.saved_cross_filters.append(
            {
                "name": saved_cross_name.strip() or f"Cross-Venue {md.now_utc_label()}",
                "created_at": md.now_utc_label(),
                "query": query,
                "min_similarity": float(min_similarity),
                "max_pairs": int(max_pairs),
                "min_gap_cents": float(min_gap_cents),
                "min_pm_volume": int(min_pm_volume),
                "min_ks_volume": int(min_ks_volume),
                "lower_filter": lower_filter,
                "min_price_pct": int(min_price_pct),
                "max_price_pct": int(max_price_pct),
            }
        )
        save_local_list("saved_cross_filters.json", st.session_state.saved_cross_filters)
        st.success("Saved cross-venue view.")
    min_price = min(float(min_price_pct), float(max_price_pct)) / 100
    max_price = max(float(min_price_pct), float(max_price_pct)) / 100
    candidates = md.cross_venue_candidates(pm, ks, query=query, min_similarity=min_similarity, max_pairs=max_pairs)
    fallback_used = False
    if candidates.empty and query.strip():
        candidates = md.cross_venue_candidates(pm, ks, query="", min_similarity=min_similarity, max_pairs=max_pairs)
        fallback_used = not candidates.empty
    if not candidates.empty:
        candidates = candidates[numeric_col(candidates, "abs_gap") >= float(min_gap_cents) / 100]
        candidates = candidates[numeric_col(candidates, "polymarket_volume") >= float(min_pm_volume)]
        candidates = candidates[numeric_col(candidates, "kalshi_volume") >= float(min_ks_volume)]
        candidates = candidates[
            (numeric_col(candidates, "polymarket_yes") >= min_price)
            & (numeric_col(candidates, "polymarket_yes") <= max_price)
            & (numeric_col(candidates, "kalshi_yes") >= min_price)
            & (numeric_col(candidates, "kalshi_yes") <= max_price)
        ]
        if lower_filter != "Any":
            candidates = candidates[candidates["lower_yes"].eq(lower_filter)]
        candidates = candidates.sort_values(["abs_gap", "similarity"], ascending=False).reset_index(drop=True)
    cross_defaults = cross_venue_filter_defaults()
    cross_chips: list[str] = []
    if query.strip():
        cross_chips.append(f"Search: {query.strip()}")
    if abs(float(min_similarity) - float(cross_defaults["cross_min_similarity"])) > 1e-9:
        cross_chips.append(f"Min similarity: {float(min_similarity):.2f}")
    if int(max_pairs) != int(cross_defaults["cross_max_pairs"]):
        cross_chips.append(f"Max pairs: {int(max_pairs)}")
    if float(min_gap_cents) > 0:
        cross_chips.append(f"Min gap: {float(min_gap_cents):.1f}c")
    if int(min_pm_volume) > 0:
        cross_chips.append(f"Polymarket volume: >{money(min_pm_volume)}")
    if int(min_ks_volume) > 0:
        cross_chips.append(f"Kalshi volume: >{money(min_ks_volume)}")
    if lower_filter != "Any":
        cross_chips.append(f"Lower yes: {lower_filter}")
    if int(min_price_pct) != int(cross_defaults["cross_min_price_pct"]) or int(max_price_pct) != int(cross_defaults["cross_max_price_pct"]):
        cross_chips.append(f"Yes price: {int(min_price_pct)}%-{int(max_price_pct)}%")
    render_filter_chips(cross_chips)
    cross_clear_actions: list[tuple[str, dict[str, Any]]] = []
    if query.strip():
        cross_clear_actions.append(("search", {"cross_query": ""}))
    if abs(float(min_similarity) - float(cross_defaults["cross_min_similarity"])) > 1e-9:
        cross_clear_actions.append(("similarity", {"cross_min_similarity": cross_defaults["cross_min_similarity"]}))
    if int(max_pairs) != int(cross_defaults["cross_max_pairs"]):
        cross_clear_actions.append(("max pairs", {"cross_max_pairs": cross_defaults["cross_max_pairs"]}))
    if float(min_gap_cents) > 0:
        cross_clear_actions.append(("gap", {"cross_min_gap_cents": 0.0}))
    if int(min_pm_volume) > 0:
        cross_clear_actions.append(("Polymarket volume", {"cross_min_pm_volume": 0}))
    if int(min_ks_volume) > 0:
        cross_clear_actions.append(("Kalshi volume", {"cross_min_ks_volume": 0}))
    if lower_filter != "Any":
        cross_clear_actions.append(("lower yes", {"cross_lower_filter": "Any"}))
    if int(min_price_pct) != int(cross_defaults["cross_min_price_pct"]) or int(max_price_pct) != int(cross_defaults["cross_max_price_pct"]):
        cross_clear_actions.append(
            (
                "yes price",
                {
                    "cross_min_price_pct": cross_defaults["cross_min_price_pct"],
                    "cross_max_price_pct": cross_defaults["cross_max_price_pct"],
                },
            )
        )
    render_filter_clear_buttons(cross_clear_actions, "cross")
    if st.session_state.saved_cross_filters:
        st.caption(f"Saved cross-venue views: {len(st.session_state.saved_cross_filters)}")
        with st.expander("Saved cross-venue filters", expanded=False):
            st.dataframe(pd.DataFrame(st.session_state.saved_cross_filters), width="stretch", height=160)
            if st.button("Clear saved cross-venue filters"):
                st.session_state.saved_cross_filters = []
                save_local_list("saved_cross_filters.json", st.session_state.saved_cross_filters)
                st.rerun()
    if candidates.empty:
        draw_empty("No cross-venue candidates matched. Try a broader query or lower the similarity threshold.")
        return
    if fallback_used:
        st.info("No pairs matched the current query on both venues, so broad cross-venue candidates are shown.")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Candidate pairs", f"{len(candidates):,}")
    c2.metric("Largest gap", signed_cents(candidates["gap"].iloc[candidates["abs_gap"].idxmax()]))
    c3.metric("Median similarity", f"{candidates['similarity'].median():.2f}")
    c4.metric("Median abs gap", cents(candidates["abs_gap"].median()))
    fig = px.scatter(
        candidates,
        x="similarity",
        y="abs_gap",
        color="lower_yes",
        hover_data=["polymarket_title", "kalshi_title", "polymarket_yes", "kalshi_yes"],
        template="plotly_dark",
        color_discrete_map={"Polymarket": ACCENT, "Kalshi": BLUE},
        labels={"abs_gap": "absolute yes-price gap"},
    )
    fig.update_layout(height=340, margin=dict(l=10, r=10, t=20, b=10), paper_bgcolor=BG, plot_bgcolor=BG)
    st.plotly_chart(fig, width="stretch", config=plot_config())
    st.download_button("Export cross-venue CSV", candidates.to_csv(index=False).encode("utf-8"), file_name="cross_venue_candidates.csv", mime="text/csv")
    table = candidates.copy()
    table["gap"] = table["gap"].map(lambda value: f"{value * 100:+.1f}c")
    table["polymarket_yes"] = table["polymarket_yes"].map(cents)
    table["kalshi_yes"] = table["kalshi_yes"].map(cents)
    st.dataframe(
        clean_table(
            table,
            [
                "similarity",
                "gap",
                "lower_yes",
                "higher_yes",
                "polymarket_ticker",
                "kalshi_ticker",
                "polymarket_title",
                "kalshi_title",
                "polymarket_yes",
                "kalshi_yes",
                "polymarket_volume",
                "kalshi_volume",
                "polymarket_url",
                "kalshi_url",
            ],
        ),
        width="stretch",
        height=460,
        column_config={
            "polymarket_volume": st.column_config.NumberColumn(format="$%.0f"),
            "kalshi_volume": st.column_config.NumberColumn(format="$%.0f"),
            "polymarket_url": st.column_config.LinkColumn("Polymarket"),
            "kalshi_url": st.column_config.LinkColumn("Kalshi"),
        },
    )
    st.markdown("### Pair actions")
    options = [
        f"{i + 1}. {row.lower_yes} lower | {row.gap * 100:+.1f}c | {str(row.polymarket_title)[:70]}"
        for i, row in candidates.head(80).iterrows()
    ]
    selected_pair = st.selectbox("Select pair", options)
    pair = candidates.iloc[options.index(selected_pair)]
    a1, a2 = st.columns([1, 1])
    if a1.button("Track Polymarket leg"):
        item = {
            "platform": "Polymarket",
            "market_key": str(pair.get("polymarket_market_key") or pair.get("polymarket_title", "")),
            "title": str(pair.get("polymarket_title", "")),
            "url": str(pair.get("polymarket_url", "")),
        }
        existing_keys = {str(w.get("market_key", "")) for w in st.session_state.watchlist}
        if item["market_key"] not in existing_keys:
            st.session_state.watchlist.append(item)
            save_local_list("watchlist.json", st.session_state.watchlist)
            st.success("Polymarket leg added to watchlist.")
    if a2.button("Track Kalshi leg"):
        item = {
            "platform": "Kalshi",
            "market_key": str(pair.get("kalshi_market_key") or pair.get("kalshi_title", "")),
            "title": str(pair.get("kalshi_title", "")),
            "url": str(pair.get("kalshi_url", "")),
        }
        existing_keys = {str(w.get("market_key", "")) for w in st.session_state.watchlist}
        if item["market_key"] not in existing_keys:
            st.session_state.watchlist.append(item)
            save_local_list("watchlist.json", st.session_state.watchlist)
            st.success("Kalshi leg added to watchlist.")
    st.caption("Price gaps are research leads, not guaranteed arbitrage. Resolution rules, fees, settlement timing, and access restrictions can break apparent parity.")


MONITOR_SIGNAL_TYPES = ["Fast mover", "Whale print", "Tight spread", "Holder concentration", "Ending soon", "Watched market"]


def _monitor_volume_col(df: pd.DataFrame) -> str:
    if "activity_volume" in df:
        return "activity_volume"
    if "volume_24h" in df:
        return "volume_24h"
    return "volume"


def _append_market_signal(rows: list[dict[str, Any]], row: pd.Series, signal_type: str, value: float, reason: str, severity: str = "info") -> None:
    rows.append(
        {
            "signal_type": signal_type,
            "severity": severity,
            "time": row.get("updated_at") or row.get("created_at") or row.get("end_time"),
            "platform": row.get("platform", ""),
            "title": row.get("title", ""),
            "category": row.get("category", ""),
            "outcome": "Yes",
            "price": row.get("yes_price"),
            "value": value,
            "reason": reason,
            "volume": row.get("activity_volume", row.get("volume_24h", row.get("volume", 0.0))),
            "liquidity": row.get("liquidity", 0.0),
            "spread": row.get("spread"),
            "change_1h": row.get("change_1h", 0.0),
            "market_key": row.get("market_key", ""),
            "wallet": "",
            "trader": "",
            "notional": 0.0,
            "url": row.get("url", ""),
        }
    )


def build_monitor_signals(
    markets: pd.DataFrame,
    trades: pd.DataFrame,
    *,
    min_volume: float,
    min_liquidity: float,
    min_move: float,
    max_spread: float,
    min_whale_notional: float,
    ending_days: int,
    holder_threshold: float,
    holder_checks: int,
    tracked_keys: set[str],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    market_frame = markets.copy()
    if not market_frame.empty:
        volume_col = _monitor_volume_col(market_frame)
        market_frame = market_frame[
            (numeric_col(market_frame, volume_col) >= float(min_volume))
            & (numeric_col(market_frame, "liquidity") >= float(min_liquidity))
        ].copy()
        if "change_1h" in market_frame:
            movers = market_frame[numeric_col(market_frame, "change_1h").abs() >= float(min_move)]
            movers = movers.sort_values("change_1h", key=lambda series: series.abs(), ascending=False)
            for _, row in movers.head(120).iterrows():
                value = float(row.get("change_1h") or 0.0)
                _append_market_signal(rows, row, "Fast mover", value, f"1h move {signed_cents(value)}", "warning")
        if "spread" in market_frame:
            tight = market_frame[numeric_col(market_frame, "spread", 999.0) <= float(max_spread)]
            tight = tight.sort_values(["spread", volume_col], ascending=[True, False])
            for _, row in tight.head(120).iterrows():
                value = float(row.get("spread") or 0.0)
                _append_market_signal(rows, row, "Tight spread", value, f"spread {cents(value)}")
        if "end_time" in market_frame:
            end_time = pd.to_datetime(market_frame["end_time"], utc=True, errors="coerce")
            now = pd.Timestamp.utcnow()
            soon = market_frame[end_time.notna() & (end_time >= now) & (end_time <= now + pd.Timedelta(days=int(ending_days)))]
            soon = soon.assign(_end_time=end_time.loc[soon.index]).sort_values("_end_time")
            for _, row in soon.head(120).iterrows():
                _append_market_signal(rows, row, "Ending soon", float(row.get("yes_price") or 0.0), f"ends {row.get('end_time')}", "warning")
        if tracked_keys:
            watched = market_frame[market_frame["market_key"].astype(str).isin(tracked_keys)]
            for _, row in watched.head(120).iterrows():
                _append_market_signal(rows, row, "Watched market", float(row.get("yes_price") or 0.0), "on local watchlist")
        if holder_checks > 0:
            holder_candidates = market_frame[market_frame["platform"].eq("Polymarket")].sort_values(volume_col, ascending=False).head(int(holder_checks))
            for _, row in holder_candidates.iterrows():
                holders = safe_load("Polymarket holders", load_holders, str(row.get("market_key", "")), default=pd.DataFrame())
                if holders.empty or "amount" not in holders:
                    continue
                total = float(pd.to_numeric(holders["amount"], errors="coerce").fillna(0.0).sum())
                if total <= 0:
                    continue
                top_share = float(pd.to_numeric(holders["amount"], errors="coerce").fillna(0.0).max() / total)
                top10_share = float(pd.to_numeric(holders.head(10)["amount"], errors="coerce").fillna(0.0).sum() / total)
                if top_share >= float(holder_threshold):
                    _append_market_signal(
                        rows,
                        row,
                        "Holder concentration",
                        top_share,
                        f"top holder {pct(top_share)}; top 10 {pct(top10_share)}",
                        "warning",
                    )
    if not trades.empty:
        whale_trades = trades[numeric_col(trades, "notional") >= float(min_whale_notional)].sort_values("time", ascending=False)
        for _, row in whale_trades.head(180).iterrows():
            rows.append(
                {
                    "signal_type": "Whale print",
                    "severity": "warning",
                    "time": row.get("time"),
                    "platform": row.get("platform", ""),
                    "title": row.get("title", ""),
                    "category": "",
                    "outcome": row.get("outcome", ""),
                    "price": row.get("price"),
                    "value": row.get("notional", 0.0),
                    "reason": f"{row.get('side', '')} {money(row.get('notional', 0.0))}",
                    "volume": 0.0,
                    "liquidity": 0.0,
                    "spread": None,
                    "change_1h": None,
                    "market_key": row.get("market_key", row.get("ticker", "")),
                    "wallet": row.get("wallet", ""),
                    "trader": row.get("trader", ""),
                    "notional": row.get("notional", 0.0),
                    "url": row.get("url", ""),
                }
            )
    if not rows:
        return pd.DataFrame()
    signals = pd.DataFrame(rows)
    signals["time"] = pd.to_datetime(signals["time"], utc=True, errors="coerce")
    return signals.sort_values(["severity", "time", "value"], ascending=[False, False, False]).reset_index(drop=True)


def monitor_rule_matches(signals: pd.DataFrame, rule: dict[str, Any]) -> pd.DataFrame:
    if signals.empty:
        return pd.DataFrame()
    filtered = signals.copy()
    signal_type = str(rule.get("signal_type", "Any"))
    if signal_type != "Any":
        filtered = filtered[filtered["signal_type"].eq(signal_type)]
    platforms = rule.get("platforms") or []
    if platforms:
        filtered = filtered[filtered["platform"].isin(platforms)]
    query = str(rule.get("query", "") or "").strip().lower()
    if query:
        searchable = filtered.get("title", pd.Series("", index=filtered.index)).astype(str).str.lower()
        searchable = searchable + " " + filtered.get("wallet", pd.Series("", index=filtered.index)).astype(str).str.lower()
        searchable = searchable + " " + filtered.get("trader", pd.Series("", index=filtered.index)).astype(str).str.lower()
        searchable = searchable + " " + filtered.get("reason", pd.Series("", index=filtered.index)).astype(str).str.lower()
        filtered = filtered[searchable.str.contains(re.escape(query), na=False)]
    min_notional = float(rule.get("min_notional", 0.0) or 0.0)
    if min_notional:
        filtered = filtered[numeric_col(filtered, "notional") >= min_notional]
    min_move = float(rule.get("min_move", 0.0) or 0.0)
    if min_move:
        filtered = filtered[(filtered["signal_type"].ne("Fast mover")) | (numeric_col(filtered, "value").abs() >= min_move)]
    max_spread = float(rule.get("max_spread", 0.0) or 0.0)
    if max_spread:
        filtered = filtered[(filtered["signal_type"].ne("Tight spread")) | (numeric_col(filtered, "spread", 999.0) <= max_spread)]
    min_liquidity = float(rule.get("min_liquidity", 0.0) or 0.0)
    if min_liquidity:
        filtered = filtered[numeric_col(filtered, "liquidity") >= min_liquidity]
    return filtered.reset_index(drop=True)


def monitor_rule_match_count(signals: pd.DataFrame, rule: dict[str, Any]) -> int:
    return int(len(monitor_rule_matches(signals, rule)))


def build_monitor_alert_hits(signals: pd.DataFrame, rules: list[dict[str, Any]]) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    for idx, rule in enumerate(rules):
        if not bool(rule.get("active", True)):
            continue
        matches = monitor_rule_matches(signals, rule)
        if matches.empty:
            continue
        matches = matches.copy()
        matches["rule_name"] = str(rule.get("name") or f"Rule {idx + 1}")
        matches["rule_type"] = str(rule.get("signal_type", "Any"))
        rows.append(matches)
    if not rows:
        return pd.DataFrame()
    hits = pd.concat(rows, ignore_index=True, sort=False)
    return hits.sort_values(["time", "value"], ascending=[False, False], na_position="last").reset_index(drop=True)


def page_monitor() -> None:
    section_header("Monitor", "Parity-style signal monitor for fast movers, whale prints, spreads, holder risk, endings, and saved alert rules.")
    if "monitor_search" not in st.session_state:
        reset_monitor_filter_widgets(global_query, 100, int(min_whale))
    if st.session_state.pop("monitor_filters_reset_pending", False):
        reset_monitor_filter_widgets(global_query, 100, int(min_whale))
    pending_monitor_view = st.session_state.pop("pending_monitor_filter_view", None)
    if isinstance(pending_monitor_view, dict):
        apply_monitor_filter_view_widgets(pending_monitor_view)
    pending_monitor_clear = st.session_state.pop("monitor_clear_pending", None)
    if isinstance(pending_monitor_clear, dict):
        for key, value in pending_monitor_clear.items():
            st.session_state[key] = value
    route_filter_params = query_param_snapshot(
        [
            "q",
            "query",
            "search",
            "wallet",
            "market",
            "platform",
            "platforms",
            "venue",
            "venues",
            "signal",
            "signals",
            "type",
            "types",
            "rows",
            "limit",
            "watched",
            "watchedOnly",
            "tracked",
            "trackedMarkets",
            "minVolume",
            "volumeMin",
            "volMin",
            "minLiquidity",
            "liquidityMin",
            "liqMin",
            "minMove",
            "moveMin",
            "changeMin",
            "maxSpread",
            "spreadMax",
            "minWhale",
            "whaleMin",
            "minNotional",
            "notionalMin",
            "endingDays",
            "endDays",
            "maxDaysToEnd",
            "holderChecks",
            "holders",
            "holderThreshold",
            "topHolder",
        ]
    )
    route_filter_signature = json.dumps(route_filter_params, sort_keys=True)
    route_filter_view = md.predictparity_monitor_filter_view(route_filter_params)
    if route_filter_view and st.session_state.get("monitor_route_filter_signature") != route_filter_signature:
        apply_monitor_filter_view_widgets(route_filter_view)
        st.session_state["monitor_route_filter_signature"] = route_filter_signature
        st.session_state["monitor_view_loaded_message"] = "Loaded monitor filters from URL."

    pm, ks, combined_markets = load_market_universe()
    poly_trades = safe_load("Polymarket trades", load_polymarket_trades, trade_limit, 0.0, None, None)
    kalshi_trades = safe_load("Kalshi trades", load_kalshi_trades, trade_limit, None)
    trades = combined_trade_table(poly_trades, kalshi_trades)

    controls = st.columns([1.5, 1, 1, 1, 1])
    query = controls[0].text_input("Monitor search", placeholder="market, wallet, trader, category", key="monitor_search")
    platforms = controls[1].multiselect("Platform", ["Polymarket", "Kalshi"], key="monitor_platforms")
    signal_types = controls[2].multiselect("Signals", MONITOR_SIGNAL_TYPES, key="monitor_signal_types")
    rows = controls[3].slider("Rows", min_value=25, max_value=250, step=25, key="monitor_rows")
    watched_only = controls[4].toggle("Watched only", key="monitor_watched_only")

    filters = st.expander("Monitor filters", expanded=True)
    with filters:
        f1, f2, f3, f4, f5, f6 = st.columns(6)
        min_volume = f1.number_input("Min 24h volume", min_value=0, step=1000, key="monitor_min_volume")
        min_liquidity = f2.number_input("Min liquidity", min_value=0, step=1000, key="monitor_min_liquidity")
        min_move_cents = f3.number_input("Min 1h move (c)", min_value=0.0, step=0.5, key="monitor_min_move")
        max_spread_cents = f4.number_input("Max spread (c)", min_value=0.1, step=0.5, key="monitor_max_spread")
        min_whale_notional = f5.number_input("Whale notional", min_value=0, step=500, key="monitor_min_whale")
        ending_days = f6.number_input("Ending within days", min_value=1, step=1, key="monitor_ending_days")
        h1, h2 = st.columns([1, 1])
        holder_checks = h1.slider("Holder checks", min_value=0, max_value=20, step=1, key="monitor_holder_checks", help="Checks top Polymarket markets only because holder calls are slower.")
        holder_threshold = h2.slider("Top holder threshold", min_value=0.05, max_value=0.80, step=0.05, key="monitor_holder_threshold")
        if st.button("Reset Filters", width="stretch", key="reset_monitor_filters_button"):
            st.session_state["monitor_filters_reset_pending"] = True
            st.rerun()

    save_cols = st.columns([2, 1, 1])
    saved_monitor_name = save_cols[0].text_input("Saved monitor view name", value=f"Monitor {md.now_utc_label()}", key="saved_monitor_view_name")
    save_monitor_clicked = save_cols[1].button("Save Filter", width="stretch", key="save_monitor_filter_button")
    if save_cols[2].button("Reset Monitor View", width="stretch", key="reset_monitor_view_button"):
        st.session_state["monitor_filters_reset_pending"] = True
        st.rerun()
    loaded_monitor_message = st.session_state.pop("monitor_view_loaded_message", "")
    if loaded_monitor_message:
        st.info(loaded_monitor_message)
    if st.session_state.saved_monitor_filters:
        load_cols = st.columns([2, 1, 1])
        saved_labels = [
            f"{i + 1}. {view.get('name') or view.get('query') or 'Monitor view'}"
            for i, view in enumerate(st.session_state.saved_monitor_filters)
        ]
        selected_saved_monitor = load_cols[0].selectbox("Load saved monitor view", saved_labels, key="load_saved_monitor_view")
        selected_monitor_view = st.session_state.saved_monitor_filters[saved_labels.index(selected_saved_monitor)]
        if load_cols[1].button("Load monitor view", key="load_monitor_view_button"):
            st.session_state["pending_monitor_filter_view"] = selected_monitor_view
            st.session_state["monitor_view_loaded_message"] = f"Loaded saved monitor view: {selected_monitor_view.get('name', selected_saved_monitor)}"
            st.rerun()
        if load_cols[2].button("Delete monitor view", key="delete_monitor_view_button"):
            st.session_state.saved_monitor_filters.pop(saved_labels.index(selected_saved_monitor))
            save_local_list("saved_monitor_filters.json", st.session_state.saved_monitor_filters)
            st.rerun()
    if save_monitor_clicked:
        st.session_state.saved_monitor_filters.append(
            {
                "name": saved_monitor_name.strip() or f"Monitor {md.now_utc_label()}",
                "created_at": md.now_utc_label(),
                "query": query,
                "platforms": platforms,
                "signal_types": signal_types,
                "rows": int(rows),
                "watched_only": bool(watched_only),
                "min_volume": float(min_volume),
                "min_liquidity": float(min_liquidity),
                "min_move": float(min_move_cents),
                "max_spread": float(max_spread_cents),
                "min_whale": float(min_whale_notional),
                "ending_days": int(ending_days),
                "holder_checks": int(holder_checks),
                "holder_threshold": float(holder_threshold),
            }
        )
        save_local_list("saved_monitor_filters.json", st.session_state.saved_monitor_filters)
        st.success("Saved monitor view.")

    markets = combined_markets.copy()
    if not markets.empty:
        markets = markets[markets["platform"].isin(platforms)]
        markets = filter_text(markets, query)
    if not trades.empty:
        trades = trades[trades["platform"].isin(platforms)]
        trades = filter_text(trades, query)
    tracked_keys = {str(item.get("market_key")) for item in st.session_state.watchlist if item.get("market_key")}
    if watched_only and not markets.empty:
        markets = markets[markets["market_key"].astype(str).isin(tracked_keys)]
        if not trades.empty and "market_key" in trades:
            trades = trades[trades["market_key"].astype(str).isin(tracked_keys)]

    all_signals = build_monitor_signals(
        markets,
        trades,
        min_volume=float(min_volume),
        min_liquidity=float(min_liquidity),
        min_move=float(min_move_cents) / 100.0,
        max_spread=float(max_spread_cents) / 100.0,
        min_whale_notional=float(min_whale_notional),
        ending_days=int(ending_days),
        holder_threshold=float(holder_threshold),
        holder_checks=int(holder_checks),
        tracked_keys=tracked_keys,
    )
    signals = all_signals.copy()
    if not signals.empty:
        if signal_types:
            signals = signals[signals["signal_type"].isin(signal_types)]
        else:
            signals = signals.iloc[0:0]
        signals = signals.head(int(rows)).reset_index(drop=True)
    alert_hits = build_monitor_alert_hits(all_signals, st.session_state.monitor_rules)

    monitor_defaults = monitor_filter_defaults(rows=100, min_whale_notional=int(min_whale))
    monitor_chips: list[str] = []
    if query.strip():
        monitor_chips.append(f"Search: {query.strip()}")
    if platforms and set(platforms) != set(monitor_defaults["monitor_platforms"]):
        monitor_chips.append("Platform: " + ", ".join(platforms))
    if not platforms:
        monitor_chips.append("Platform: none")
    if signal_types and set(signal_types) != set(MONITOR_SIGNAL_TYPES):
        monitor_chips.append("Signals: " + ", ".join(signal_types))
    if not signal_types:
        monitor_chips.append("Signals: none")
    if int(rows) != int(monitor_defaults["monitor_rows"]):
        monitor_chips.append(f"Rows: {int(rows)}")
    if watched_only:
        monitor_chips.append("Watched only")
    if int(min_volume) > 0:
        monitor_chips.append(f"Volume >= {money(min_volume)}")
    if int(min_liquidity) > 0:
        monitor_chips.append(f"Liquidity >= {money(min_liquidity)}")
    if float(min_move_cents) > 0:
        monitor_chips.append(f"1h move >= {float(min_move_cents):.1f}c")
    if float(max_spread_cents) < 100.0:
        monitor_chips.append(f"Spread <= {float(max_spread_cents):.1f}c")
    if int(min_whale_notional) > 0:
        monitor_chips.append(f"Whale >= {money(min_whale_notional)}")
    if int(ending_days) < 3650:
        monitor_chips.append(f"Ending <= {int(ending_days)}d")
    if int(holder_checks) > 0:
        monitor_chips.append(f"Holder checks: {int(holder_checks)}")
        monitor_chips.append(f"Top holder >= {pct(holder_threshold)}")
    render_filter_chips(monitor_chips)

    monitor_clear_actions: list[tuple[str, dict[str, Any]]] = []
    if query.strip():
        monitor_clear_actions.append(("search", {"monitor_search": ""}))
    if set(platforms) != set(monitor_defaults["monitor_platforms"]):
        monitor_clear_actions.append(("platform", {"monitor_platforms": monitor_defaults["monitor_platforms"]}))
    if set(signal_types) != set(MONITOR_SIGNAL_TYPES):
        monitor_clear_actions.append(("signals", {"monitor_signal_types": list(MONITOR_SIGNAL_TYPES)}))
    if int(rows) != int(monitor_defaults["monitor_rows"]):
        monitor_clear_actions.append(("rows", {"monitor_rows": monitor_defaults["monitor_rows"]}))
    if watched_only:
        monitor_clear_actions.append(("watched only", {"monitor_watched_only": False}))
    if int(min_volume) > 0:
        monitor_clear_actions.append(("volume", {"monitor_min_volume": 0}))
    if int(min_liquidity) > 0:
        monitor_clear_actions.append(("liquidity", {"monitor_min_liquidity": 0}))
    if float(min_move_cents) > 0:
        monitor_clear_actions.append(("1h move", {"monitor_min_move": 0.0}))
    if float(max_spread_cents) < 100.0:
        monitor_clear_actions.append(("spread", {"monitor_max_spread": 100.0}))
    if int(min_whale_notional) > 0:
        monitor_clear_actions.append(("whale", {"monitor_min_whale": 0}))
    if int(ending_days) < 3650:
        monitor_clear_actions.append(("ending", {"monitor_ending_days": 3650}))
    if int(holder_checks) > 0:
        monitor_clear_actions.append(("holder risk", {"monitor_holder_checks": 0, "monitor_holder_threshold": monitor_defaults["monitor_holder_threshold"]}))
    render_filter_clear_buttons(monitor_clear_actions, "monitor")
    if st.session_state.saved_monitor_filters:
        st.caption(f"Saved monitor views: {len(st.session_state.saved_monitor_filters)}")
        with st.expander("Saved monitor filters", expanded=False):
            st.dataframe(pd.DataFrame(st.session_state.saved_monitor_filters), width="stretch", height=160)
            if st.button("Clear saved monitor filters"):
                st.session_state.saved_monitor_filters = []
                save_local_list("saved_monitor_filters.json", st.session_state.saved_monitor_filters)
                st.rerun()
    if not signals.empty:
        st.download_button("Export signal feed CSV", signals.to_csv(index=False).encode("utf-8"), file_name="monitor_signal_feed.csv", mime="text/csv")

    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric("Signals", f"{len(signals):,}")
    m2.metric("Fast movers", f"{int(signals['signal_type'].eq('Fast mover').sum()) if not signals.empty else 0:,}")
    m3.metric("Whale prints", f"{int(signals['signal_type'].eq('Whale print').sum()) if not signals.empty else 0:,}")
    m4.metric("Tight spreads", f"{int(signals['signal_type'].eq('Tight spread').sum()) if not signals.empty else 0:,}")
    m5.metric("Alert rules", f"{len(st.session_state.monitor_rules):,}")
    m6.metric("Alert hits", f"{len(alert_hits):,}")

    tab_feed, tab_alerts, tab_movers, tab_whales, tab_spreads, tab_holders, tab_ending, tab_rules = st.tabs(
        ["Signal Feed", "Alert Hits", "Fast Movers", "Whale Prints", "Tight Spreads", "Holder Risk", "Ending Soon", "Alert Rules"]
    )
    signal_columns = ["time", "signal_type", "platform", "reason", "title", "price", "value", "volume", "liquidity", "spread", "change_1h", "wallet", "url"]
    signal_config = {
        "time": st.column_config.DatetimeColumn(format="YYYY-MM-DD HH:mm"),
        "price": st.column_config.NumberColumn(format="%.4f"),
        "value": st.column_config.NumberColumn(format="%.4f"),
        "volume": st.column_config.NumberColumn(format="$%.0f"),
        "liquidity": st.column_config.NumberColumn(format="$%.0f"),
        "spread": st.column_config.NumberColumn(format="%.4f"),
        "change_1h": st.column_config.NumberColumn(format="%+.4f"),
        "url": st.column_config.LinkColumn("URL"),
    }
    with tab_feed:
        if signals.empty:
            draw_empty("No monitor signals match the current filters.")
        else:
            display = clean_table(signals, signal_columns)
            if "wallet" in display:
                display["wallet"] = display["wallet"].astype(str).map(short_addr)
            st.dataframe(display, width="stretch", height=540, column_config=signal_config)
    with tab_alerts:
        if alert_hits.empty:
            draw_empty("No active alert rules match the current signal set.")
        else:
            st.download_button("Export alert hits CSV", alert_hits.to_csv(index=False).encode("utf-8"), file_name="monitor_alert_hits.csv", mime="text/csv")
            display = clean_table(
                alert_hits,
                ["rule_name", "time", "signal_type", "platform", "reason", "title", "price", "value", "notional", "liquidity", "spread", "change_1h", "wallet", "url"],
            )
            if "wallet" in display:
                display["wallet"] = display["wallet"].astype(str).map(short_addr)
            st.dataframe(
                display.head(200),
                width="stretch",
                height=420,
                column_config={
                    **signal_config,
                    "notional": st.column_config.NumberColumn(format="$%.0f"),
                },
            )
            action_cols = st.columns([2, 1, 1])
            hit_options = [
                f"{i + 1}. {row.rule_name}: {row.signal_type} | {str(row.title)[:80]}"
                for i, row in alert_hits.head(100).iterrows()
            ]
            selected_hit = action_cols[0].selectbox("Alert action target", hit_options, key="monitor_alert_action_target")
            hit_row = alert_hits.iloc[hit_options.index(selected_hit)]
            if action_cols[1].button("Track alert market", key="monitor_track_alert_market"):
                item = {
                    "platform": str(hit_row.get("platform", "")),
                    "market_key": str(hit_row.get("market_key", "") or hit_row.get("title", "")),
                    "title": str(hit_row.get("title", "")),
                    "url": str(hit_row.get("url", "")),
                }
                if item["market_key"] not in [w["market_key"] for w in st.session_state.watchlist]:
                    st.session_state.watchlist.append(item)
                    save_local_list("watchlist.json", st.session_state.watchlist)
                    st.success("Alert market added to watchlist.")
            if action_cols[2].button("Track alert wallet", key="monitor_track_alert_wallet"):
                wallet_value = str(hit_row.get("wallet", ""))
                if re.fullmatch(r"0x[a-fA-F0-9]{40}", wallet_value) and wallet_value.lower() not in [w.lower() for w in st.session_state.followed_wallets]:
                    st.session_state.followed_wallets.append(wallet_value)
                    save_local_list("followed_wallets.json", st.session_state.followed_wallets)
                    st.success("Alert wallet added to tracked wallets.")
    with tab_movers:
        movers = signals[signals["signal_type"].eq("Fast mover")] if not signals.empty else pd.DataFrame()
        if movers.empty:
            draw_empty("No fast movers match the current thresholds.")
        else:
            st.dataframe(clean_table(movers, signal_columns).head(80), width="stretch", height=460, column_config=signal_config)
    with tab_whales:
        whales = signals[signals["signal_type"].eq("Whale print")] if not signals.empty else pd.DataFrame()
        if whales.empty:
            draw_empty("No whale prints match the current thresholds.")
        else:
            display = clean_table(whales, ["time", "platform", "trader", "wallet", "outcome", "reason", "title", "price", "notional", "url"])
            if "wallet" in display:
                display["wallet"] = display["wallet"].astype(str).map(short_addr)
            st.dataframe(
                display.head(100),
                width="stretch",
                height=460,
                column_config={"time": st.column_config.DatetimeColumn(format="YYYY-MM-DD HH:mm"), "price": st.column_config.NumberColumn(format="%.4f"), "notional": st.column_config.NumberColumn(format="$%.0f"), "url": st.column_config.LinkColumn("URL")},
            )
    with tab_spreads:
        spreads = signals[signals["signal_type"].eq("Tight spread")] if not signals.empty else pd.DataFrame()
        if spreads.empty:
            draw_empty("No tight spreads match the current thresholds.")
        else:
            st.dataframe(clean_table(spreads, signal_columns).head(100), width="stretch", height=460, column_config=signal_config)
    with tab_holders:
        holder_risk = signals[signals["signal_type"].eq("Holder concentration")] if not signals.empty else pd.DataFrame()
        if holder_risk.empty:
            draw_empty("No holder concentration signals. Increase holder checks or lower the threshold.")
        else:
            st.dataframe(clean_table(holder_risk, signal_columns).head(60), width="stretch", height=330, column_config=signal_config)
        if not pm.empty:
            st.markdown("### Manual holder check")
            options = [f"{i + 1}. {str(row.title)[:95]}" for i, row in pm.head(80).iterrows()]
            selected = st.selectbox("Polymarket market", options, key="monitor_holder_market")
            row = pm.iloc[options.index(selected)]
            holders = safe_load("Polymarket holders", load_holders, row["market_key"])
            if holders.empty:
                draw_empty("No holder data returned.")
            else:
                total = holders["amount"].sum()
                holders["share"] = holders["amount"] / total if total else 0
                h1, h2, h3 = st.columns(3)
                h1.metric("Displayed holders", f"{len(holders):,}")
                h2.metric("Top holder", pct(holders["share"].max()))
                h3.metric("Top 10 concentration", pct(holders.head(10)["amount"].sum() / total if total else 0))
                display = holders.copy()
                display["wallet"] = display["wallet"].astype(str).map(short_addr)
                st.dataframe(display.head(50), width="stretch", height=320)
    with tab_ending:
        ending = signals[signals["signal_type"].eq("Ending soon")] if not signals.empty else pd.DataFrame()
        if ending.empty:
            draw_empty("No ending-soon markets match the current filters.")
        else:
            st.dataframe(clean_table(ending, signal_columns).head(100), width="stretch", height=460, column_config=signal_config)
    with tab_rules:
        st.markdown("### Saved alert rules")
        with st.form("monitor_rule_form"):
            r1, r2, r3 = st.columns([1.2, 1, 1])
            name = r1.text_input("Rule name", placeholder="Large Tony-like politics whale")
            rule_type = r2.selectbox("Signal type", ["Any"] + MONITOR_SIGNAL_TYPES)
            rule_platforms = r3.multiselect("Platforms", ["Polymarket", "Kalshi"], default=platforms)
            r4, r5, r6, r7 = st.columns(4)
            rule_query = r4.text_input("Query", value=query)
            rule_min_notional = r5.number_input("Min notional", min_value=0, value=int(min_whale_notional), step=500)
            rule_min_move = r6.number_input("Min move (c)", min_value=0.0, value=float(min_move_cents), step=0.5)
            rule_max_spread = r7.number_input("Max spread (c)", min_value=0.0, value=float(max_spread_cents), step=0.5)
            r8, r9 = st.columns([1, 3])
            rule_min_liquidity = r8.number_input("Min liquidity", min_value=0, value=int(min_liquidity), step=1000)
            active = r9.checkbox("Active", value=True)
            submitted = st.form_submit_button("Save alert rule")
            if submitted and name.strip():
                st.session_state.monitor_rules.append(
                    {
                        "name": name.strip(),
                        "signal_type": rule_type,
                        "platforms": rule_platforms,
                        "query": rule_query.strip(),
                        "min_notional": float(rule_min_notional),
                        "min_move": float(rule_min_move) / 100.0,
                        "max_spread": float(rule_max_spread) / 100.0,
                        "min_liquidity": float(rule_min_liquidity),
                        "active": bool(active),
                        "created_at": md.now_utc_label(),
                    }
                )
                save_local_monitor_rules(st.session_state.monitor_rules)
                st.rerun()
        if not st.session_state.monitor_rules:
            draw_empty("No saved alert rules yet.")
        else:
            rules = pd.DataFrame(st.session_state.monitor_rules)
            rules["matched_now"] = [monitor_rule_match_count(all_signals, rule) for rule in st.session_state.monitor_rules]
            st.dataframe(rules, width="stretch", height=310)
            remove_options = [f"{i + 1}. {rule.get('name', 'Unnamed')}" for i, rule in enumerate(st.session_state.monitor_rules)]
            c1, c2 = st.columns([2, 1])
            selected_rule = c1.selectbox("Remove rule", remove_options)
            if c2.button("Delete selected rule"):
                idx = remove_options.index(selected_rule)
                st.session_state.monitor_rules.pop(idx)
                save_local_monitor_rules(st.session_state.monitor_rules)
                st.rerun()


def page_alerts() -> None:
    section_header("Alerts", "Dedicated alert center for saved rules, current hits, signal feed triage, and tracking actions.")
    if "alert_search" not in st.session_state:
        reset_alert_filter_widgets(global_query, 100, int(min_whale))
    if st.session_state.pop("alert_filters_reset_pending", False):
        reset_alert_filter_widgets(global_query, 100, int(min_whale))
    pending_alert_view = st.session_state.pop("pending_alert_filter_view", None)
    if isinstance(pending_alert_view, dict):
        apply_alert_filter_view_widgets(pending_alert_view)
    pending_alert_clear = st.session_state.pop("alert_clear_pending", None)
    if isinstance(pending_alert_clear, dict):
        for key, value in pending_alert_clear.items():
            st.session_state[key] = value
    route_filter_params = query_param_snapshot(
        [
            "q",
            "query",
            "search",
            "wallet",
            "market",
            "platform",
            "platforms",
            "venue",
            "venues",
            "signal",
            "signals",
            "type",
            "types",
            "rows",
            "limit",
            "watched",
            "watchedOnly",
            "tracked",
            "trackedMarkets",
            "minVolume",
            "volumeMin",
            "volMin",
            "minLiquidity",
            "liquidityMin",
            "liqMin",
            "minMove",
            "moveMin",
            "changeMin",
            "maxSpread",
            "spreadMax",
            "minWhale",
            "whaleMin",
            "minNotional",
            "notionalMin",
            "endingDays",
            "endDays",
            "maxDaysToEnd",
            "holderChecks",
            "holders",
            "holderThreshold",
            "topHolder",
            "hitsOnly",
            "hits",
            "rulesOnly",
        ]
    )
    route_filter_signature = json.dumps(route_filter_params, sort_keys=True)
    route_filter_view = md.predictparity_alert_filter_view(route_filter_params)
    if route_filter_view and st.session_state.get("alert_route_filter_signature") != route_filter_signature:
        apply_alert_filter_view_widgets(route_filter_view)
        st.session_state["alert_route_filter_signature"] = route_filter_signature
        st.session_state["alert_view_loaded_message"] = "Loaded alert filters from URL."

    pm, ks, combined_markets = load_market_universe()
    poly_trades = safe_load("Polymarket trades", load_polymarket_trades, trade_limit, 0.0, None, None)
    kalshi_trades = safe_load("Kalshi trades", load_kalshi_trades, trade_limit, None)
    trades = combined_trade_table(poly_trades, kalshi_trades)

    controls = st.columns([1.7, 1, 1, 1, 1])
    query = controls[0].text_input("Alert search", placeholder="market, wallet, trader, rule", key="alert_search")
    platforms = controls[1].multiselect("Platform", ["Polymarket", "Kalshi"], key="alert_platforms")
    signal_types = controls[2].multiselect("Signals", MONITOR_SIGNAL_TYPES, key="alert_signal_types")
    rows = controls[3].slider("Rows", min_value=25, max_value=250, step=25, key="alert_rows")
    hits_only = controls[4].toggle("Hits only", key="alert_hits_only")

    with st.expander("Alert scan filters", expanded=True):
        f1, f2, f3, f4, f5, f6 = st.columns(6)
        min_volume = f1.number_input("Min 24h volume", min_value=0, step=1000, key="alert_min_volume")
        min_liquidity = f2.number_input("Min liquidity", min_value=0, step=1000, key="alert_min_liquidity")
        min_move_cents = f3.number_input("Min 1h move (c)", min_value=0.0, step=0.5, key="alert_min_move")
        max_spread_cents = f4.number_input("Max spread (c)", min_value=0.1, step=0.5, key="alert_max_spread")
        min_whale_notional = f5.number_input("Whale notional", min_value=0, step=500, key="alert_min_whale")
        ending_days = f6.number_input("Ending within days", min_value=1, step=1, key="alert_ending_days")
        h1, h2, h3 = st.columns([1, 1, 2])
        holder_checks = h1.slider("Holder checks", min_value=0, max_value=20, step=1, key="alert_holder_checks")
        holder_threshold = h2.slider("Top holder threshold", min_value=0.05, max_value=0.80, step=0.05, key="alert_holder_threshold")
        if h3.button("Reset Filters", width="stretch", key="reset_alert_filters_button"):
            st.session_state["alert_filters_reset_pending"] = True
            st.rerun()

    save_cols = st.columns([2, 1, 1])
    saved_alert_name = save_cols[0].text_input("Saved alert view name", value=f"Alerts {md.now_utc_label()}", key="saved_alert_view_name")
    save_alert_clicked = save_cols[1].button("Save Filter", width="stretch", key="save_alert_filter_button")
    if save_cols[2].button("Reset Alert View", width="stretch", key="reset_alert_view_button"):
        st.session_state["alert_filters_reset_pending"] = True
        st.rerun()
    loaded_alert_message = st.session_state.pop("alert_view_loaded_message", "")
    if loaded_alert_message:
        st.info(loaded_alert_message)
    if st.session_state.saved_alert_filters:
        load_cols = st.columns([2, 1, 1])
        saved_labels = [
            f"{i + 1}. {view.get('name') or view.get('query') or 'Alert view'}"
            for i, view in enumerate(st.session_state.saved_alert_filters)
        ]
        selected_saved_alert = load_cols[0].selectbox("Load saved alert view", saved_labels, key="load_saved_alert_view")
        selected_alert_view = st.session_state.saved_alert_filters[saved_labels.index(selected_saved_alert)]
        if load_cols[1].button("Load alert view", key="load_alert_view_button"):
            st.session_state["pending_alert_filter_view"] = selected_alert_view
            st.session_state["alert_view_loaded_message"] = f"Loaded saved alert view: {selected_alert_view.get('name', selected_saved_alert)}"
            st.rerun()
        if load_cols[2].button("Delete alert view", key="delete_alert_view_button"):
            st.session_state.saved_alert_filters.pop(saved_labels.index(selected_saved_alert))
            save_local_list("saved_alert_filters.json", st.session_state.saved_alert_filters)
            st.rerun()
    if save_alert_clicked:
        st.session_state.saved_alert_filters.append(
            {
                "name": saved_alert_name.strip() or f"Alerts {md.now_utc_label()}",
                "created_at": md.now_utc_label(),
                "query": query,
                "platforms": platforms,
                "signal_types": signal_types,
                "rows": int(rows),
                "hits_only": bool(hits_only),
                "min_volume": float(min_volume),
                "min_liquidity": float(min_liquidity),
                "min_move": float(min_move_cents),
                "max_spread": float(max_spread_cents),
                "min_whale": float(min_whale_notional),
                "ending_days": int(ending_days),
                "holder_checks": int(holder_checks),
                "holder_threshold": float(holder_threshold),
            }
        )
        save_local_list("saved_alert_filters.json", st.session_state.saved_alert_filters)
        st.success("Saved alert view.")

    markets = combined_markets.copy()
    if not markets.empty:
        markets = markets[markets["platform"].isin(platforms)] if platforms else markets.iloc[0:0]
        markets = filter_text(markets, query)
    if not trades.empty:
        trades = trades[trades["platform"].isin(platforms)] if platforms else trades.iloc[0:0]
        trades = filter_text(trades, query)
    tracked_keys = {str(item.get("market_key")) for item in st.session_state.watchlist if item.get("market_key")}

    all_signals = build_monitor_signals(
        markets,
        trades,
        min_volume=float(min_volume),
        min_liquidity=float(min_liquidity),
        min_move=float(min_move_cents) / 100.0,
        max_spread=float(max_spread_cents) / 100.0,
        min_whale_notional=float(min_whale_notional),
        ending_days=int(ending_days),
        holder_threshold=float(holder_threshold),
        holder_checks=int(holder_checks),
        tracked_keys=tracked_keys,
    )
    alert_hits = build_monitor_alert_hits(all_signals, st.session_state.monitor_rules)
    signals = all_signals.copy()
    if not signals.empty:
        signals = signals[signals["signal_type"].isin(signal_types)] if signal_types else signals.iloc[0:0]
        signals = signals.head(int(rows)).reset_index(drop=True)
    if not alert_hits.empty:
        alert_hits = alert_hits[alert_hits["signal_type"].isin(signal_types)] if signal_types else alert_hits.iloc[0:0]
        alert_hits = alert_hits.head(int(rows)).reset_index(drop=True)

    defaults = alert_filter_defaults(rows=100, min_whale_notional=int(min_whale))
    chips: list[str] = []
    if query.strip():
        chips.append(f"Search: {query.strip()}")
    if platforms and set(platforms) != set(defaults["alert_platforms"]):
        chips.append("Platform: " + ", ".join(platforms))
    if not platforms:
        chips.append("Platform: none")
    if signal_types and set(signal_types) != set(MONITOR_SIGNAL_TYPES):
        chips.append("Signals: " + ", ".join(signal_types))
    if not signal_types:
        chips.append("Signals: none")
    if int(rows) != int(defaults["alert_rows"]):
        chips.append(f"Rows: {int(rows)}")
    if hits_only:
        chips.append("Hits only")
    if int(min_volume) > 0:
        chips.append(f"Volume >= {money(min_volume)}")
    if int(min_liquidity) > 0:
        chips.append(f"Liquidity >= {money(min_liquidity)}")
    if float(min_move_cents) > 0:
        chips.append(f"1h move >= {float(min_move_cents):.1f}c")
    if float(max_spread_cents) < 100.0:
        chips.append(f"Spread <= {float(max_spread_cents):.1f}c")
    if int(min_whale_notional) > 0:
        chips.append(f"Whale >= {money(min_whale_notional)}")
    if int(ending_days) < 3650:
        chips.append(f"Ending <= {int(ending_days)}d")
    if int(holder_checks) > 0:
        chips.append(f"Holder checks: {int(holder_checks)}")
    render_filter_chips(chips)

    clear_actions: list[tuple[str, dict[str, Any]]] = []
    if query.strip():
        clear_actions.append(("search", {"alert_search": ""}))
    if set(platforms) != set(defaults["alert_platforms"]):
        clear_actions.append(("platform", {"alert_platforms": defaults["alert_platforms"]}))
    if set(signal_types) != set(MONITOR_SIGNAL_TYPES):
        clear_actions.append(("signals", {"alert_signal_types": list(MONITOR_SIGNAL_TYPES)}))
    if int(rows) != int(defaults["alert_rows"]):
        clear_actions.append(("rows", {"alert_rows": defaults["alert_rows"]}))
    if hits_only:
        clear_actions.append(("hits only", {"alert_hits_only": False}))
    if int(min_volume) > 0:
        clear_actions.append(("volume", {"alert_min_volume": 0}))
    if int(min_liquidity) > 0:
        clear_actions.append(("liquidity", {"alert_min_liquidity": 0}))
    if float(min_move_cents) > 0:
        clear_actions.append(("1h move", {"alert_min_move": 0.0}))
    if float(max_spread_cents) < 100.0:
        clear_actions.append(("spread", {"alert_max_spread": 100.0}))
    if int(min_whale_notional) > 0:
        clear_actions.append(("whale", {"alert_min_whale": 0}))
    if int(ending_days) < 3650:
        clear_actions.append(("ending", {"alert_ending_days": 3650}))
    if int(holder_checks) > 0:
        clear_actions.append(("holder checks", {"alert_holder_checks": 0, "alert_holder_threshold": defaults["alert_holder_threshold"]}))
    render_filter_clear_buttons(clear_actions, "alert")
    if st.session_state.saved_alert_filters:
        st.caption(f"Saved alert views: {len(st.session_state.saved_alert_filters)}")
        with st.expander("Saved alert filters", expanded=False):
            st.dataframe(pd.DataFrame(st.session_state.saved_alert_filters), width="stretch", height=160)
            if st.button("Clear saved alert filters"):
                st.session_state.saved_alert_filters = []
                save_local_list("saved_alert_filters.json", st.session_state.saved_alert_filters)
                st.rerun()

    active_rules = [rule for rule in st.session_state.monitor_rules if bool(rule.get("active", True))]
    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric("Active rules", f"{len(active_rules):,}")
    m2.metric("Alert hits", f"{len(alert_hits):,}")
    m3.metric("Signals", f"{len(signals):,}")
    m4.metric("Whales", f"{int(signals['signal_type'].eq('Whale print').sum()) if not signals.empty else 0:,}")
    m5.metric("Fast movers", f"{int(signals['signal_type'].eq('Fast mover').sum()) if not signals.empty else 0:,}")
    m6.metric("Watched hits", f"{int(alert_hits['signal_type'].eq('Watched market').sum()) if not alert_hits.empty else 0:,}")

    signal_columns = ["time", "signal_type", "platform", "reason", "title", "price", "value", "notional", "volume", "liquidity", "spread", "change_1h", "wallet", "url"]
    signal_config = {
        "time": st.column_config.DatetimeColumn(format="YYYY-MM-DD HH:mm"),
        "price": st.column_config.NumberColumn(format="%.4f"),
        "value": st.column_config.NumberColumn(format="%.4f"),
        "notional": st.column_config.NumberColumn(format="$%.0f"),
        "volume": st.column_config.NumberColumn(format="$%.0f"),
        "liquidity": st.column_config.NumberColumn(format="$%.0f"),
        "spread": st.column_config.NumberColumn(format="%.4f"),
        "change_1h": st.column_config.NumberColumn(format="%+.4f"),
        "url": st.column_config.LinkColumn("URL"),
    }
    tab_hits, tab_feed, tab_builder, tab_rules, tab_coverage = st.tabs(["Alert Hits", "Signal Feed", "Create Rule", "Saved Rules", "Coverage"])
    with tab_hits:
        if alert_hits.empty:
            draw_empty("No saved alert rule matches the current signal set.")
        else:
            st.download_button("Export alert hits CSV", alert_hits.to_csv(index=False).encode("utf-8"), file_name="alert_hits.csv", mime="text/csv")
            display = clean_table(alert_hits, ["rule_name", *signal_columns])
            if "wallet" in display:
                display["wallet"] = display["wallet"].astype(str).map(short_addr)
            st.dataframe(display, width="stretch", height=460, column_config=signal_config)
            action_cols = st.columns([2.4, 1, 1, 1])
            options = [
                f"{i + 1}. {row.get('rule_name', '-')}: {row.get('signal_type', '-')} | {str(row.get('title', ''))[:90]}"
                for i, row in alert_hits.head(100).iterrows()
            ]
            selected_hit = action_cols[0].selectbox("Hit action target", options, key="alerts_hit_action_target")
            hit_row = alert_hits.iloc[options.index(selected_hit)]
            if action_cols[1].button("Track market", key="alerts_track_hit_market"):
                item = {
                    "platform": str(hit_row.get("platform", "")),
                    "market_key": str(hit_row.get("market_key", "") or hit_row.get("title", "")),
                    "title": str(hit_row.get("title", "")),
                    "url": str(hit_row.get("url", "")),
                }
                st.session_state.watchlist, changed = md.upsert_watchlist_market(st.session_state.watchlist, item)
                if changed:
                    save_local_list("watchlist.json", st.session_state.watchlist)
                    st.success("Alert market added to watchlist.")
                else:
                    st.info("Alert market is already tracked.")
            if action_cols[2].button("Track wallet", key="alerts_track_hit_wallet"):
                wallet_value = str(hit_row.get("wallet", ""))
                st.session_state.followed_wallets, changed = md.upsert_followed_wallet(st.session_state.followed_wallets, wallet_value)
                if changed:
                    save_local_list("followed_wallets.json", st.session_state.followed_wallets)
                    st.success("Alert wallet added to tracked wallets.")
                else:
                    st.info("Alert wallet is already tracked or unavailable.")
            if str(hit_row.get("url", "")):
                action_cols[3].link_button("Open market", str(hit_row.get("url", "")), width="stretch")
    with tab_feed:
        source = alert_hits if hits_only else signals
        if source.empty:
            draw_empty("No alert feed rows match the current filters.")
        else:
            file_name = "alert_hits_feed.csv" if hits_only else "alert_signal_feed.csv"
            st.download_button("Export feed CSV", source.to_csv(index=False).encode("utf-8"), file_name=file_name, mime="text/csv")
            display = clean_table(source, ["rule_name", *signal_columns])
            if "wallet" in display:
                display["wallet"] = display["wallet"].astype(str).map(short_addr)
            st.dataframe(display, width="stretch", height=520, column_config=signal_config)
    with tab_builder:
        st.markdown("### Create alert rule")
        with st.form("alerts_rule_form"):
            r1, r2, r3 = st.columns([1.3, 1, 1])
            name = r1.text_input("Rule name", placeholder="Iran whale print or fast mover")
            rule_type = r2.selectbox("Signal type", ["Any"] + MONITOR_SIGNAL_TYPES)
            rule_platforms = r3.multiselect("Platforms", ["Polymarket", "Kalshi"], default=platforms or ["Polymarket", "Kalshi"])
            r4, r5, r6, r7 = st.columns(4)
            rule_query = r4.text_input("Query", value=query)
            rule_min_notional = r5.number_input("Min notional", min_value=0, value=int(min_whale_notional), step=500)
            rule_min_move = r6.number_input("Min move (c)", min_value=0.0, value=float(min_move_cents), step=0.5)
            rule_max_spread = r7.number_input("Max spread (c)", min_value=0.0, value=float(max_spread_cents), step=0.5)
            r8, r9 = st.columns([1, 3])
            rule_min_liquidity = r8.number_input("Min liquidity", min_value=0, value=int(min_liquidity), step=1000)
            active = r9.checkbox("Active", value=True)
            submitted = st.form_submit_button("Save alert rule")
            if submitted and name.strip():
                st.session_state.monitor_rules.append(
                    {
                        "name": name.strip(),
                        "signal_type": rule_type,
                        "platforms": rule_platforms,
                        "query": rule_query.strip(),
                        "min_notional": float(rule_min_notional),
                        "min_move": float(rule_min_move) / 100.0,
                        "max_spread": float(rule_max_spread) / 100.0,
                        "min_liquidity": float(rule_min_liquidity),
                        "active": bool(active),
                        "created_at": md.now_utc_label(),
                    }
                )
                save_local_monitor_rules(st.session_state.monitor_rules)
                st.success("Alert rule saved.")
                st.rerun()
        st.caption("Rules are evaluated against the current public signal set and persist locally in data/monitor_rules.json.")
    with tab_rules:
        if not st.session_state.monitor_rules:
            draw_empty("No saved alert rules yet.")
        else:
            rules = pd.DataFrame(st.session_state.monitor_rules)
            rules["matched_now"] = [monitor_rule_match_count(all_signals, rule) for rule in st.session_state.monitor_rules]
            st.download_button("Export rules CSV", rules.to_csv(index=False).encode("utf-8"), file_name="alert_rules.csv", mime="text/csv")
            st.dataframe(rules, width="stretch", height=330)
            options = [f"{i + 1}. {rule.get('name', 'Unnamed')}" for i, rule in enumerate(st.session_state.monitor_rules)]
            c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
            selected_rule = c1.selectbox("Rule action", options, key="alerts_rule_action")
            idx = options.index(selected_rule)
            selected_rule_data = st.session_state.monitor_rules[idx]
            if c2.button("Pause" if bool(selected_rule_data.get("active", True)) else "Resume", key="alerts_toggle_rule"):
                st.session_state.monitor_rules[idx]["active"] = not bool(selected_rule_data.get("active", True))
                save_local_monitor_rules(st.session_state.monitor_rules)
                st.rerun()
            if c3.button("Duplicate", key="alerts_duplicate_rule"):
                clone = dict(selected_rule_data)
                clone["name"] = f"{clone.get('name', 'Rule')} copy"
                clone["created_at"] = md.now_utc_label()
                st.session_state.monitor_rules.append(clone)
                save_local_monitor_rules(st.session_state.monitor_rules)
                st.rerun()
            if c4.button("Delete", key="alerts_delete_rule"):
                st.session_state.monitor_rules.pop(idx)
                save_local_monitor_rules(st.session_state.monitor_rules)
                st.rerun()
    with tab_coverage:
        if alert_hits.empty:
            draw_empty("No alert-hit coverage to chart.")
        else:
            by_rule = alert_hits.groupby(["rule_name", "signal_type"], as_index=False).size().rename(columns={"size": "hits"})
            fig = px.bar(
                by_rule,
                x="rule_name",
                y="hits",
                color="signal_type",
                template="plotly_dark",
                labels={"rule_name": "rule", "hits": "hits"},
            )
            fig.update_layout(height=380, margin=dict(l=10, r=10, t=20, b=120), paper_bgcolor=BG, plot_bgcolor=BG)
            st.plotly_chart(fig, width="stretch", config=plot_config())
            st.dataframe(by_rule, width="stretch", height=260)


def page_resolved() -> None:
    section_header("Resolved Markets", "Review closed Polymarket outcomes and category-level resolution history.")
    if "resolved_search" not in st.session_state:
        reset_resolved_filter_widgets(global_query)
    if st.session_state.pop("resolved_filters_reset_pending", False):
        reset_resolved_filter_widgets(global_query)
    pending_resolved_view = st.session_state.pop("pending_resolved_filter_view", None)
    if isinstance(pending_resolved_view, dict):
        apply_resolved_filter_view_widgets(pending_resolved_view)
    pending_resolved_clear = st.session_state.pop("resolved_clear_pending", None)
    if isinstance(pending_resolved_clear, dict):
        for key, value in pending_resolved_clear.items():
            st.session_state[key] = value
    route_filter_params = query_param_snapshot(
        [
            "q",
            "query",
            "search",
            "market",
            "event",
            "rows",
            "limit",
            "sample",
            "outcome",
            "outcomes",
            "resolution",
            "resolutions",
            "decisiveOnly",
            "decisive",
            "decisiveResolution",
            "minVolume",
            "volumeMin",
            "volMin",
            "minLiquidity",
            "liquidityMin",
            "liqMin",
            "category",
            "categories",
            "closedWindow",
            "window",
            "period",
            "days",
            "finalYesMin",
            "finalYesMax",
            "finalPriceMin",
            "finalPriceMax",
            "probMin",
            "probMax",
            "priceMin",
            "priceMax",
            "sort",
            "sortBy",
            "orderBy",
        ]
    )
    route_filter_signature = json.dumps(route_filter_params, sort_keys=True)
    route_filter_view = md.predictparity_resolved_filter_view(route_filter_params)
    if route_filter_view and st.session_state.get("resolved_route_filter_signature") != route_filter_signature:
        apply_resolved_filter_view_widgets(route_filter_view)
        st.session_state["resolved_route_filter_signature"] = route_filter_signature
        st.session_state["resolved_view_loaded_message"] = "Loaded resolved filters from URL."

    controls = st.columns([1.5, 1, 1, 1])
    query = controls[0].text_input("Resolved search", placeholder="market, category, outcome", key="resolved_search")
    rows = controls[1].slider("Closed market sample", min_value=50, max_value=500, step=50, key="resolved_rows")
    outcome_filter = controls[2].multiselect("Outcome", ["Yes", "No", "Multi", "Unknown"], key="resolved_outcomes")
    decisive_only = controls[3].toggle("Decisive only", key="resolved_decisive_only")
    closed = safe_load("Closed Polymarket markets", load_closed_markets, rows)

    category_options = []
    if not closed.empty and "category" in closed:
        category_options = sorted([str(item) for item in closed["category"].dropna().unique() if str(item).strip()])
    if category_options:
        st.session_state["resolved_category_filter"] = [
            item for item in list(st.session_state.get("resolved_category_filter", [])) if item in category_options
        ]
    with st.expander("Resolved filters", expanded=True):
        f1, f2, f3, f4, f5 = st.columns(5)
        min_volume = f1.number_input("Min resolved volume", min_value=0, step=1000, key="resolved_min_volume")
        min_liquidity = f2.number_input("Min liquidity", min_value=0, step=1000, key="resolved_min_liquidity")
        category_filter = f3.multiselect("Category", category_options, key="resolved_category_filter")
        closed_window = f4.radio("Closed window", ["All", "<7d", "<30d", "<90d", "<365d"], horizontal=True, key="resolved_closed_window")
        sort_options = ["closed_time", "volume", "liquidity", "final_yes_price", "category"]
        sort_by = f5.selectbox("Sort by", sort_options, key="resolved_sort_by")
        g1, g2 = st.columns([2, 1])
        final_yes_range = g1.slider("Final yes price", min_value=0, max_value=100, step=1, key="resolved_final_yes_range")
        if g2.button("Reset Filters", width="stretch", key="reset_resolved_filters_button"):
            st.session_state["resolved_filters_reset_pending"] = True
            st.rerun()

    save_cols = st.columns([2, 1, 1])
    saved_resolved_name = save_cols[0].text_input("Saved resolved view name", value=f"Resolved {md.now_utc_label()}", key="saved_resolved_view_name")
    save_resolved_clicked = save_cols[1].button("Save Filter", width="stretch", key="save_resolved_filter_button")
    if save_cols[2].button("Reset Resolved View", width="stretch", key="reset_resolved_view_button"):
        st.session_state["resolved_filters_reset_pending"] = True
        st.rerun()
    loaded_resolved_message = st.session_state.pop("resolved_view_loaded_message", "")
    if loaded_resolved_message:
        st.info(loaded_resolved_message)
    if st.session_state.saved_resolved_filters:
        load_cols = st.columns([2, 1, 1])
        saved_labels = [
            f"{i + 1}. {view.get('name') or view.get('query') or 'Resolved view'}"
            for i, view in enumerate(st.session_state.saved_resolved_filters)
        ]
        selected_saved_resolved = load_cols[0].selectbox("Load saved resolved view", saved_labels, key="load_saved_resolved_view")
        selected_resolved_view = st.session_state.saved_resolved_filters[saved_labels.index(selected_saved_resolved)]
        if load_cols[1].button("Load resolved view", key="load_resolved_view_button"):
            st.session_state["pending_resolved_filter_view"] = selected_resolved_view
            st.session_state["resolved_view_loaded_message"] = f"Loaded saved resolved view: {selected_resolved_view.get('name', selected_saved_resolved)}"
            st.rerun()
        if load_cols[2].button("Delete resolved view", key="delete_resolved_view_button"):
            st.session_state.saved_resolved_filters.pop(saved_labels.index(selected_saved_resolved))
            save_local_list("saved_resolved_filters.json", st.session_state.saved_resolved_filters)
            st.rerun()
    if save_resolved_clicked:
        st.session_state.saved_resolved_filters.append(
            {
                "name": saved_resolved_name.strip() or f"Resolved {md.now_utc_label()}",
                "created_at": md.now_utc_label(),
                "query": query,
                "rows": int(rows),
                "outcomes": outcome_filter,
                "decisive_only": bool(decisive_only),
                "min_volume": int(min_volume),
                "min_liquidity": int(min_liquidity),
                "category_filter": category_filter,
                "closed_window": closed_window,
                "final_yes_range": list(final_yes_range),
                "sort_by": sort_by,
            }
        )
        save_local_list("saved_resolved_filters.json", st.session_state.saved_resolved_filters)
        st.success("Saved resolved view.")

    resolved_defaults = resolved_filter_defaults()
    chips: list[str] = []
    if query.strip():
        chips.append(f"Search: {query.strip()}")
    if int(rows) != int(resolved_defaults["resolved_rows"]):
        chips.append(f"Rows: {int(rows)}")
    if set(outcome_filter) != set(resolved_defaults["resolved_outcomes"]):
        chips.append("Outcome: " + (", ".join(outcome_filter) if outcome_filter else "none"))
    if decisive_only:
        chips.append("Decisive only")
    if int(min_volume) > 0:
        chips.append(f"Volume >= {money(min_volume)}")
    if int(min_liquidity) > 0:
        chips.append(f"Liquidity >= {money(min_liquidity)}")
    if category_filter:
        chips.append("Category: " + ", ".join(category_filter[:3]) + ("..." if len(category_filter) > 3 else ""))
    if closed_window != "All":
        chips.append(f"Closed: {closed_window}")
    final_low, final_high = [int(value) for value in list(final_yes_range)]
    if (final_low, final_high) != tuple(resolved_defaults["resolved_final_yes_range"]):
        chips.append(f"Final yes: {final_low}%-{final_high}%")
    if sort_by != resolved_defaults["resolved_sort_by"]:
        chips.append(f"Sort: {sort_by}")
    render_filter_chips(chips)

    clear_actions: list[tuple[str, dict[str, Any]]] = []
    if query.strip():
        clear_actions.append(("search", {"resolved_search": ""}))
    if int(rows) != int(resolved_defaults["resolved_rows"]):
        clear_actions.append(("rows", {"resolved_rows": resolved_defaults["resolved_rows"]}))
    if set(outcome_filter) != set(resolved_defaults["resolved_outcomes"]):
        clear_actions.append(("outcome", {"resolved_outcomes": resolved_defaults["resolved_outcomes"]}))
    if decisive_only:
        clear_actions.append(("decisive", {"resolved_decisive_only": False}))
    if int(min_volume) > 0:
        clear_actions.append(("volume", {"resolved_min_volume": 0}))
    if int(min_liquidity) > 0:
        clear_actions.append(("liquidity", {"resolved_min_liquidity": 0}))
    if category_filter:
        clear_actions.append(("category", {"resolved_category_filter": []}))
    if closed_window != "All":
        clear_actions.append(("closed window", {"resolved_closed_window": "All"}))
    if (final_low, final_high) != tuple(resolved_defaults["resolved_final_yes_range"]):
        clear_actions.append(("final yes", {"resolved_final_yes_range": resolved_defaults["resolved_final_yes_range"]}))
    if sort_by != resolved_defaults["resolved_sort_by"]:
        clear_actions.append(("sort", {"resolved_sort_by": resolved_defaults["resolved_sort_by"]}))
    render_filter_clear_buttons(clear_actions, "resolved")
    if st.session_state.saved_resolved_filters:
        st.caption(f"Saved resolved views: {len(st.session_state.saved_resolved_filters)}")
        with st.expander("Saved resolved filters", expanded=False):
            st.dataframe(pd.DataFrame(st.session_state.saved_resolved_filters), width="stretch", height=160)
            if st.button("Clear saved resolved filters"):
                st.session_state.saved_resolved_filters = []
                save_local_list("saved_resolved_filters.json", st.session_state.saved_resolved_filters)
                st.rerun()

    closed = filter_text(closed, query)
    if not closed.empty:
        closed = closed[closed["volume"].fillna(0) >= float(min_volume)]
        closed = closed[closed["liquidity"].fillna(0) >= float(min_liquidity)]
        closed = closed[closed["resolved_outcome"].isin(outcome_filter)]
        if decisive_only:
            closed = closed[closed["decisive_resolution"].astype(bool)]
        if category_filter and "category" in closed:
            closed = closed[closed["category"].astype(str).isin(category_filter)]
        if "final_yes_price" in closed:
            final_low_dec = final_low / 100
            final_high_dec = final_high / 100
            closed = closed[(numeric_col(closed, "final_yes_price") >= final_low_dec) & (numeric_col(closed, "final_yes_price") <= final_high_dec)]
        if closed_window != "All" and "closed_time" in closed:
            days = int(closed_window.strip("<d"))
            cutoff = pd.Timestamp.utcnow() - pd.Timedelta(days=days)
            closed_times = pd.to_datetime(closed["closed_time"], utc=True, errors="coerce")
            closed = closed[closed_times >= cutoff]
        if sort_by in closed:
            ascending = sort_by in {"final_yes_price", "category"}
            closed = closed.sort_values(sort_by, ascending=ascending, na_position="last").reset_index(drop=True)
    if closed.empty:
        draw_empty("No resolved markets match the current filters.")
        return

    stats = md.resolution_stats(closed)
    binary_closed = closed[closed["binary_market"].astype(bool)] if "binary_market" in closed else closed
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Resolved markets", f"{len(closed):,}")
    m2.metric("Binary yes rate", pct((binary_closed["resolved_outcome"] == "Yes").mean()) if not binary_closed.empty else "-")
    m3.metric("Decisive closes", pct(binary_closed["decisive_resolution"].mean()) if not binary_closed.empty else "-")
    m4.metric("Resolved volume", money(closed["volume"].sum()))

    left, right = st.columns([1.1, 1])
    with left:
        st.markdown("### Category history")
        if stats.empty:
            draw_empty("No category stats available.")
        else:
            fig = px.bar(
                stats.head(20),
                x="category",
                y="markets",
                color="yes_rate",
                template="plotly_dark",
                color_continuous_scale=["#ff5a68", "#f5b84b", "#35d07f"],
                labels={"markets": "resolved markets", "yes_rate": "yes rate"},
            )
            fig.update_layout(height=360, margin=dict(l=10, r=10, t=20, b=80), paper_bgcolor=BG, plot_bgcolor=BG)
            st.plotly_chart(fig, width="stretch", config=plot_config())
    with right:
        st.markdown("### Resolution mix")
        mix = closed.groupby("resolved_outcome", as_index=False)["market_key"].count().rename(columns={"market_key": "markets"})
        fig = px.pie(
            mix,
            values="markets",
            names="resolved_outcome",
            template="plotly_dark",
            color="resolved_outcome",
            color_discrete_map={"Yes": ACCENT, "No": RED, "Unknown": MUTED},
        )
        fig.update_layout(height=360, margin=dict(l=10, r=10, t=20, b=10), paper_bgcolor=BG)
        st.plotly_chart(fig, width="stretch", config=plot_config())

    st.markdown("### Closed market archive")
    table = clean_table(
        closed,
        ["closed_time", "platform", "title", "category", "resolved_outcome", "final_yes_price", "volume", "liquidity", "url"],
    )
    st.dataframe(
        table.head(250),
        width="stretch",
        height=520,
        column_config={
            "final_yes_price": st.column_config.NumberColumn(format="%.3f"),
            "volume": st.column_config.NumberColumn(format="$%.0f"),
            "liquidity": st.column_config.NumberColumn(format="$%.0f"),
            "url": st.column_config.LinkColumn("URL"),
        },
    )
    st.download_button("Export resolved markets CSV", closed.to_csv(index=False).encode("utf-8"), file_name="resolved_markets.csv", mime="text/csv")
    st.caption("Closed-market outcomes are inferred from final Polymarket outcome prices returned by the public Gamma API.")


def copy_price_lookup(asset: str) -> float | None:
    bids, asks = safe_load("Polymarket order book", load_polymarket_book, asset, default=(pd.DataFrame(), pd.DataFrame()))
    best_bid = float(bids["price"].max()) if not bids.empty and "price" in bids else None
    best_ask = float(asks["price"].min()) if not asks.empty and "price" in asks else None
    if best_bid is not None and best_ask is not None:
        return (best_bid + best_ask) / 2
    return best_bid if best_bid is not None else best_ask


def load_copy_daemon_status() -> dict[str, Any]:
    path = Path(ct.DEFAULT_STATUS_PATH)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def page_copy_trade() -> None:
    settings = ct.CopySettings()
    if "copy_trade_search" not in st.session_state:
        reset_copy_trade_filter_widgets(global_query)
    if st.session_state.pop("copy_trade_filters_reset_pending", False):
        reset_copy_trade_filter_widgets(global_query)
    pending_copy_trade_view = st.session_state.pop("pending_copy_trade_filter_view", None)
    if isinstance(pending_copy_trade_view, dict):
        apply_copy_trade_filter_view_widgets(pending_copy_trade_view)
    pending_copy_trade_clear = st.session_state.pop("copy_trade_clear_pending", None)
    if isinstance(pending_copy_trade_clear, dict):
        for key, value in pending_copy_trade_clear.items():
            st.session_state[key] = value
    route_filter_params = query_param_snapshot(
        [
            "q",
            "query",
            "search",
            "market",
            "tx",
            "reason",
            "side",
            "sides",
            "status",
            "statuses",
            "copyStatus",
            "copyStatuses",
            "rows",
            "limit",
            "minTonyNotional",
            "tonyNotionalMin",
            "minSourceNotional",
            "sourceNotionalMin",
            "minCopyNotional",
            "copyNotionalMin",
            "minPaperNotional",
            "paperNotionalMin",
            "minPositionValue",
            "positionValueMin",
            "minValue",
            "valueMin",
            "minPnl",
            "pnlMin",
            "reasonQuery",
            "contains",
            "latencyOnly",
            "latency",
            "measuredLatency",
        ]
    )
    route_filter_signature = json.dumps(route_filter_params, sort_keys=True)
    route_filter_view = md.copy_trade_filter_view(route_filter_params)
    if route_filter_view and st.session_state.get("copy_trade_route_filter_signature") != route_filter_signature:
        apply_copy_trade_filter_view_widgets(route_filter_view)
        st.session_state["copy_trade_route_filter_signature"] = route_filter_signature
        st.session_state["copy_trade_view_loaded_message"] = "Loaded copy-trade filters from URL."

    section_header(
        "Copy Trade",
        "Paper-only Swisstony copier with dynamic wallet-relative sizing and settlement recycling.",
    )
    st.info("Paper mode only. This page observes public Polymarket wallet activity and does not place real orders.")

    controls = st.columns([1, 1, 1, 1, 1])
    if controls[0].button("Sync now", type="primary", width="stretch"):
        with st.spinner("Syncing Swisstony public trades, settlements, and redeems..."):
            try:
                result = ct.sync_copy_trades(settings.target_wallet, settings=settings)
                settlement_result = None
                if not result.seeded:
                    settlement_result = ct.sync_settlement_activity(
                        settings.target_wallet,
                        settings=settings,
                        limit=500,
                        pages=1,
                        closed_pages=4,
                        metadata_pages=2,
                    )
                if result.seeded:
                    st.success(f"Baseline created from Swisstony's current wallet state. Observed {result.processed} existing trades; future new trades will be paper-copied.")
                else:
                    st.success(
                        f"Sync complete: {result.copied} copied, {result.skipped} skipped, {result.duplicates} duplicates. "
                        f"Settlements/redeems: {settlement_result.copied if settlement_result else 0} realized/recycled, "
                        f"{settlement_result.skipped if settlement_result else 0} skipped."
                    )
                errors = list(result.errors)
                if settlement_result is not None:
                    errors.extend(settlement_result.errors)
                if errors:
                    st.warning("; ".join(errors[:3]))
            except Exception as exc:
                st.error(f"Copy sync failed: {exc}")
    if controls[1].button("Reset paper portfolio", width="stretch"):
        ct.reset_paper_portfolio(start_cash=settings.paper_start_cash)
        st.warning("Paper portfolio reset to $1,000. Sync again to create a fresh Swisstony baseline.")
    if controls[2].button("Add $1,000 cash", width="stretch"):
        try:
            new_cash = ct.add_paper_cash(1000.0, reason="manual_copy_cash_top_up", note="Copy Trade page")
            st.success(f"Paper cash topped up to {money(new_cash)} without closing open positions.")
        except Exception as exc:
            st.error(f"Cash top-up failed: {exc}")
    controls[3].metric("Max scale", f"{settings.dynamic_scale_max * 100:.2f}% of Tony")
    controls[4].metric("Base cap", f"{settings.max_order_equity_pct * 100:.1f}% equity")
    if settings.auto_top_up_enabled:
        st.caption(
            f"Auto top-up is active: when a trader sub-account has at or below USD {settings.auto_top_up_threshold:,.0f} cash, "
            f"the copier adds USD {settings.auto_top_up_amount:,.0f} paper cash and continues copying."
        )
    use_live_midpoints = st.toggle(
        "Value open copy positions with live orderbook midpoints",
        value=False,
        help="Off by default so the page stays fast with hundreds of copied positions. When off, valuation uses the last known trade/copy price.",
    )

    snapshot = ct.value_paper_portfolio(price_lookup=copy_price_lookup if use_live_midpoints else None)
    orders = ct.get_paper_orders()
    cash_events = ct.get_cash_events()
    positions = snapshot.positions
    meta = ct.get_meta_snapshot()
    dynamic_sizing = ct.get_dynamic_sizing_snapshot()
    base_copy_rows = int(st.session_state.get("copy_trade_rows", 150) or 150)
    recent = safe_load("Swisstony trades", load_polymarket_trades, max(100, base_copy_rows), 0.0, settings.target_wallet, None)
    daemon_status = load_copy_daemon_status()

    filter_cols = st.columns([1.6, 1, 1, 1, 1])
    copy_trade_query = filter_cols[0].text_input("Copy search", placeholder="market, outcome, tx, reason", key="copy_trade_search")
    copy_trade_sides = filter_cols[1].multiselect("Side", COPY_SIDE_FILTERS, key="copy_trade_sides")
    copy_trade_statuses = filter_cols[2].multiselect("Copy status", COPY_ORDER_STATUS_FILTERS, key="copy_trade_statuses")
    copy_trade_rows = filter_cols[3].slider("Rows", min_value=25, max_value=500, step=25, key="copy_trade_rows")
    copy_trade_min_tony_notional = filter_cols[4].number_input("Min Tony notional", min_value=0, step=25, key="copy_trade_min_tony_notional")
    with st.expander("Copy trade filters", expanded=False):
        f1, f2, f3, f4 = st.columns(4)
        copy_trade_min_copy_notional = f1.number_input("Min paper notional", min_value=0, step=5, key="copy_trade_min_copy_notional")
        copy_trade_min_position_value = f2.number_input("Min position value", min_value=0, step=5, key="copy_trade_min_position_value")
        copy_trade_min_pnl = f3.number_input("Min realized/unrealized PnL", step=25, key="copy_trade_min_pnl")
        copy_trade_reason_query = f4.text_input("Reason contains", placeholder="baseline, sell, redeem", key="copy_trade_reason_query")
        copy_trade_latency_only = st.checkbox("Only orders with measurable copy latency", key="copy_trade_latency_only")
        if st.button("Reset Filters", width="stretch", key="reset_copy_trade_filters_button"):
            st.session_state["copy_trade_filters_reset_pending"] = True
            st.rerun()

    save_cols = st.columns([2, 1, 1])
    saved_copy_name = save_cols[0].text_input("Saved copy view name", value=f"Copy Trade {md.now_utc_label()}", key="saved_copy_trade_view_name")
    save_copy_clicked = save_cols[1].button("Save Filter", width="stretch", key="save_copy_trade_filter_button")
    if save_cols[2].button("Reset Copy View", width="stretch", key="reset_copy_trade_view_button"):
        st.session_state["copy_trade_filters_reset_pending"] = True
        st.rerun()
    loaded_copy_message = st.session_state.pop("copy_trade_view_loaded_message", "")
    if loaded_copy_message:
        st.info(loaded_copy_message)
    if st.session_state.saved_copy_trade_filters:
        load_cols = st.columns([2, 1, 1])
        saved_labels = [
            f"{i + 1}. {view.get('name') or view.get('query') or 'Copy view'}"
            for i, view in enumerate(st.session_state.saved_copy_trade_filters)
        ]
        selected_saved_copy = load_cols[0].selectbox("Load saved copy view", saved_labels, key="load_saved_copy_trade_view")
        selected_copy_view = st.session_state.saved_copy_trade_filters[saved_labels.index(selected_saved_copy)]
        if load_cols[1].button("Load copy view", key="load_copy_trade_view_button"):
            st.session_state["pending_copy_trade_filter_view"] = selected_copy_view
            st.session_state["copy_trade_view_loaded_message"] = f"Loaded saved copy view: {selected_copy_view.get('name', selected_saved_copy)}"
            st.rerun()
        if load_cols[2].button("Delete copy view", key="delete_copy_trade_view_button"):
            st.session_state.saved_copy_trade_filters.pop(saved_labels.index(selected_saved_copy))
            save_local_list("saved_copy_trade_filters.json", st.session_state.saved_copy_trade_filters)
            st.rerun()
    if save_copy_clicked:
        st.session_state.saved_copy_trade_filters.append(
            {
                "name": saved_copy_name.strip() or f"Copy Trade {md.now_utc_label()}",
                "created_at": md.now_utc_label(),
                "query": copy_trade_query,
                "sides": copy_trade_sides,
                "statuses": copy_trade_statuses,
                "rows": int(copy_trade_rows),
                "min_tony_notional": int(copy_trade_min_tony_notional),
                "min_copy_notional": int(copy_trade_min_copy_notional),
                "min_position_value": int(copy_trade_min_position_value),
                "min_pnl": float(copy_trade_min_pnl),
                "reason_query": copy_trade_reason_query,
                "latency_only": bool(copy_trade_latency_only),
            }
        )
        save_local_list("saved_copy_trade_filters.json", st.session_state.saved_copy_trade_filters)
        st.success("Saved copy trade view.")

    filtered_orders = apply_copy_trade_order_filters(
        orders,
        query=copy_trade_query,
        sides=copy_trade_sides,
        statuses=copy_trade_statuses,
        min_tony_notional=float(copy_trade_min_tony_notional),
        min_copy_notional=float(copy_trade_min_copy_notional),
        min_pnl=float(copy_trade_min_pnl),
        reason_query=copy_trade_reason_query,
        latency_only=bool(copy_trade_latency_only),
        rows=int(copy_trade_rows),
    )
    filtered_positions = apply_copy_trade_position_filters(
        positions,
        query=copy_trade_query,
        min_value=float(copy_trade_min_position_value),
        min_pnl=float(copy_trade_min_pnl),
        rows=int(copy_trade_rows),
    )
    filtered_recent = filter_text(recent.copy(), copy_trade_query) if not recent.empty else recent.copy()
    if not filtered_recent.empty and "side" in filtered_recent:
        if copy_trade_sides:
            filtered_recent = filtered_recent[filtered_recent["side"].astype(str).str.upper().isin([item.upper() for item in copy_trade_sides])]
        else:
            filtered_recent = filtered_recent.iloc[0:0]
    if not filtered_recent.empty and "notional" in filtered_recent:
        filtered_recent = filtered_recent[numeric_col(filtered_recent, "notional") >= float(copy_trade_min_tony_notional)]
    filtered_recent = filtered_recent.head(int(copy_trade_rows)).reset_index(drop=True)
    filtered_cash_events = filter_text(cash_events.copy(), copy_trade_query).head(int(copy_trade_rows)).reset_index(drop=True) if not cash_events.empty else cash_events.copy()

    copy_defaults = copy_trade_filter_defaults()
    copy_chips: list[str] = []
    if copy_trade_query.strip():
        copy_chips.append(f"Search: {copy_trade_query.strip()}")
    if set(copy_trade_sides) != set(copy_defaults["copy_trade_sides"]):
        copy_chips.append("Side: " + (", ".join(copy_trade_sides) if copy_trade_sides else "none"))
    if set(copy_trade_statuses) != set(copy_defaults["copy_trade_statuses"]):
        copy_chips.append("Status: " + (", ".join(copy_trade_statuses) if copy_trade_statuses else "none"))
    if int(copy_trade_rows) != int(copy_defaults["copy_trade_rows"]):
        copy_chips.append(f"Rows: {int(copy_trade_rows)}")
    if int(copy_trade_min_tony_notional) > 0:
        copy_chips.append(f"Tony notional >= {money(copy_trade_min_tony_notional)}")
    if int(copy_trade_min_copy_notional) > 0:
        copy_chips.append(f"Paper notional >= {money(copy_trade_min_copy_notional)}")
    if int(copy_trade_min_position_value) > 0:
        copy_chips.append(f"Position value >= {money(copy_trade_min_position_value)}")
    if float(copy_trade_min_pnl) != float(copy_defaults["copy_trade_min_pnl"]):
        copy_chips.append(f"PnL >= {money(copy_trade_min_pnl)}")
    if copy_trade_reason_query.strip():
        copy_chips.append(f"Reason: {copy_trade_reason_query.strip()}")
    if copy_trade_latency_only:
        copy_chips.append("Latency measured")
    render_filter_chips(copy_chips)

    copy_clear_actions: list[tuple[str, dict[str, Any]]] = []
    if copy_trade_query.strip():
        copy_clear_actions.append(("search", {"copy_trade_search": ""}))
    if set(copy_trade_sides) != set(copy_defaults["copy_trade_sides"]):
        copy_clear_actions.append(("side", {"copy_trade_sides": copy_defaults["copy_trade_sides"]}))
    if set(copy_trade_statuses) != set(copy_defaults["copy_trade_statuses"]):
        copy_clear_actions.append(("status", {"copy_trade_statuses": copy_defaults["copy_trade_statuses"]}))
    if int(copy_trade_rows) != int(copy_defaults["copy_trade_rows"]):
        copy_clear_actions.append(("rows", {"copy_trade_rows": copy_defaults["copy_trade_rows"]}))
    if int(copy_trade_min_tony_notional) > 0:
        copy_clear_actions.append(("Tony notional", {"copy_trade_min_tony_notional": 0}))
    if int(copy_trade_min_copy_notional) > 0:
        copy_clear_actions.append(("paper notional", {"copy_trade_min_copy_notional": 0}))
    if int(copy_trade_min_position_value) > 0:
        copy_clear_actions.append(("position value", {"copy_trade_min_position_value": 0}))
    if float(copy_trade_min_pnl) != float(copy_defaults["copy_trade_min_pnl"]):
        copy_clear_actions.append(("PnL", {"copy_trade_min_pnl": copy_defaults["copy_trade_min_pnl"]}))
    if copy_trade_reason_query.strip():
        copy_clear_actions.append(("reason", {"copy_trade_reason_query": ""}))
    if copy_trade_latency_only:
        copy_clear_actions.append(("latency", {"copy_trade_latency_only": False}))
    render_filter_clear_buttons(copy_clear_actions, "copy_trade")
    if st.session_state.saved_copy_trade_filters:
        st.caption(f"Saved copy views: {len(st.session_state.saved_copy_trade_filters)}")
        with st.expander("Saved copy filters", expanded=False):
            st.dataframe(pd.DataFrame(st.session_state.saved_copy_trade_filters), width="stretch", height=160)
            if st.button("Clear saved copy filters"):
                st.session_state.saved_copy_trade_filters = []
                save_local_list("saved_copy_trade_filters.json", st.session_state.saved_copy_trade_filters)
                st.rerun()

    st.markdown(f"Target wallet: [`{settings.target_wallet}`](https://polygonscan.com/address/{settings.target_wallet})")
    if meta.get("tony_seeded_at"):
        st.caption(f"Baseline seeded at {meta['tony_seeded_at']}. Live trading enabled: {meta.get('live_trading_enabled', 'false')}.")
    else:
        st.caption("No baseline yet. Click Sync now once before paper-copying new Swisstony trades.")

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Cash", money(snapshot.cash))
    m2.metric("Equity", money(snapshot.equity))
    m3.metric("Positions", money(snapshot.position_value))
    m4.metric("Realized PnL", money(snapshot.realized_pnl))
    m5.metric("Unrealized PnL", money(snapshot.unrealized_pnl))

    st.markdown("### Dynamic sizing")
    s1, s2, s3, s4, s5 = st.columns(5)
    s1.metric("Effective scale", pct(dynamic_sizing.get("effective_copy_scale", settings.copy_scale)))
    s2.metric("Tony equity", money(dynamic_sizing.get("tony_visible_equity", 0.0)))
    s3.metric("Tony avg position", money(dynamic_sizing.get("tony_mean_market_position", 0.0)), pct(dynamic_sizing.get("tony_mean_market_position_pct", 0.0)))
    s4.metric("Tony p95 position", money(dynamic_sizing.get("tony_p95_market_position", 0.0)), pct(dynamic_sizing.get("tony_p95_market_position_pct", 0.0)))
    s5.metric("Effective cap", pct(dynamic_sizing.get("effective_max_order_equity_pct", settings.max_order_equity_pct)))
    if dynamic_sizing.get("tony_wallet_stats_updated_at"):
        st.caption(
            f"Tony wallet stats: {dynamic_sizing.get('tony_open_markets', '-')} markets, "
            f"{dynamic_sizing.get('tony_open_positions', '-')} outcome positions, "
            f"updated {dynamic_sizing.get('tony_wallet_stats_updated_at')}."
        )
    if dynamic_sizing.get("tony_wallet_stats_error"):
        st.warning(f"Tony wallet stats error: {dynamic_sizing['tony_wallet_stats_error']}")

    st.markdown("### Auto-sync runner")
    if daemon_status:
        fast_result = daemon_status.get("last_fast_result") or {}
        api_result = daemon_status.get("last_api_result") or {}
        settlement_result = daemon_status.get("last_settlement_result") or {}
        active_result = daemon_status.get("last_result") or {}
        d1, d2, d3, d4, d5, d6 = st.columns(6)
        d1.metric("Runner", "Active" if daemon_status.get("running") else "Stopped")
        d2.metric("Mode", "Fast chain" if daemon_status.get("fast_enabled") else "API")
        d3.metric("Chain poll", f"{float(daemon_status.get('interval_seconds', 0)):.1f}s")
        d4.metric("Fast copied", str(fast_result.get("copied", active_result.get("copied", "-"))))
        d5.metric("API copied", str(api_result.get("copied", "-")))
        d6.metric("Recycled", str(settlement_result.get("copied", "-")))
        daemon_sizing = daemon_status.get("dynamic_sizing") or {}
        if daemon_sizing:
            st.caption(
                f"Dynamic copy scale: {pct(daemon_sizing.get('effective_copy_scale'))} | "
                f"Tony visible equity: {money(daemon_sizing.get('tony_visible_equity', 0.0))} | "
                f"mode: {daemon_sizing.get('copy_scale_mode', '-')}"
            )
        if daemon_status.get("last_sync_at"):
            st.caption(f"Last auto-sync: {daemon_status['last_sync_at']} | PID: {daemon_status.get('pid', '-')}")
        if fast_result:
            st.caption(
                f"Fast path scanned blocks {fast_result.get('from_block', '-')}-{fast_result.get('to_block', '-')} "
                f"of {fast_result.get('latest_block', '-')}; logs seen: {fast_result.get('logs_seen', '-')}; "
                f"duplicates: {fast_result.get('duplicates', '-')}; skipped: {fast_result.get('skipped', '-')}."
            )
        if settlement_result:
            st.caption(
                f"Settlement sync: {settlement_result.get('copied', '-')} recycled, "
                f"{settlement_result.get('skipped', '-')} skipped, {settlement_result.get('duplicates', '-')} duplicates."
            )
        if daemon_status.get("last_error"):
            st.warning(f"Auto-sync error: {daemon_status['last_error']}")
    else:
        draw_empty("Auto-sync runner has not written a status file yet. Manual Sync now still works.")

    if not filtered_orders.empty:
        csv = filtered_orders.to_csv(index=False).encode("utf-8")
        st.download_button("Export filtered CSV", csv, file_name="swisstony_paper_copy_orders.csv", mime="text/csv")

    tab_live, tab_orders, tab_positions, tab_settled, tab_cash, tab_skipped = st.tabs(["Tony live trades", "Paper copy orders", "Paper positions", "Settlements", "Cash events", "Skipped / baseline"])
    with tab_live:
        if filtered_recent.empty:
            draw_empty("No Swisstony trades returned.")
        else:
            live = clean_table(
                filtered_recent,
                ["time", "side", "outcome", "title", "price", "size", "notional", "asset", "transaction_hash", "url"],
            )
            if "asset" in live:
                live["asset"] = live["asset"].astype(str).map(short_addr)
            if "transaction_hash" in live:
                live["transaction_hash"] = live["transaction_hash"].astype(str).map(short_addr)
            st.dataframe(
                live.head(100),
                width="stretch",
                height=430,
                column_config={
                    "price": st.column_config.NumberColumn(format="%.4f"),
                    "size": st.column_config.NumberColumn(format="%.2f"),
                    "notional": st.column_config.NumberColumn(format="$%.2f"),
                    "url": st.column_config.LinkColumn("URL"),
                },
            )
    with tab_orders:
        copied = filtered_orders[filtered_orders["status"] == "copied"].copy() if not filtered_orders.empty else pd.DataFrame()
        if copied.empty:
            draw_empty("No copied paper orders yet. After the initial baseline, new Swisstony trades will appear here.")
        else:
            copied["copy_latency_sec"] = (
                pd.to_datetime(copied["created_at"], utc=True, errors="coerce")
                - pd.to_datetime(copied["source_time"], utc=True, errors="coerce")
            ).dt.total_seconds()
            copied["asset"] = copied["asset"].astype(str).map(short_addr)
            copied["source_tx"] = copied["source_tx"].astype(str).map(short_addr)
            st.dataframe(
                clean_table(
                    copied,
                    [
                        "source_time",
                        "source_side",
                        "outcome",
                        "title",
                        "source_price",
                        "source_notional",
                        "copy_size",
                        "copy_notional",
                        "realized_pnl",
                        "copy_latency_sec",
                        "reason",
                        "asset",
                        "source_tx",
                    ],
                ),
                width="stretch",
                height=430,
                column_config={
                    "source_price": st.column_config.NumberColumn(format="%.4f"),
                    "source_notional": st.column_config.NumberColumn(format="$%.2f"),
                    "copy_size": st.column_config.NumberColumn(format="%.4f"),
                    "copy_notional": st.column_config.NumberColumn(format="$%.2f"),
                    "realized_pnl": st.column_config.NumberColumn(format="$%.2f"),
                    "copy_latency_sec": st.column_config.NumberColumn(format="%.1fs"),
                },
            )
    with tab_positions:
        if filtered_positions.empty:
            draw_empty("No open paper positions.")
        else:
            display_positions = filtered_positions.copy()
            display_positions["asset"] = display_positions["asset"].astype(str).map(short_addr)
            st.dataframe(
                clean_table(
                    display_positions,
                    ["title", "outcome", "shares", "avg_price", "current_price", "cost_basis", "value", "unrealized_pnl", "pnl_pct", "asset"],
                ),
                width="stretch",
                height=430,
                column_config={
                    "shares": st.column_config.NumberColumn(format="%.4f"),
                    "avg_price": st.column_config.NumberColumn(format="%.4f"),
                    "current_price": st.column_config.NumberColumn(format="%.4f"),
                    "cost_basis": st.column_config.NumberColumn(format="$%.2f"),
                    "value": st.column_config.NumberColumn(format="$%.2f"),
                    "unrealized_pnl": st.column_config.NumberColumn(format="$%.2f"),
                    "pnl_pct": st.column_config.NumberColumn(format="%.2f"),
                },
            )
    with tab_settled:
        settled = filtered_orders[filtered_orders["status"] == "settled"].copy() if not filtered_orders.empty else pd.DataFrame()
        st.caption("Redeems and resolved markets remove the paper position from unrealized PnL and book payout minus cost basis into realized PnL. Losing outcomes add a negative realized PnL.")
        if settled.empty:
            draw_empty("No paper settlements or complete-set merges recycled yet.")
        else:
            settled_pnl = pd.to_numeric(settled.get("realized_pnl"), errors="coerce").fillna(0.0)
            settled_cash = pd.to_numeric(settled.get("copy_notional"), errors="coerce").fillna(0.0)
            sm1, sm2, sm3 = st.columns(3)
            sm1.metric("Settled orders", f"{len(settled):,}")
            sm2.metric("Realized from settlements", money(float(settled_pnl.sum())))
            sm3.metric("Cash recycled", money(float(settled_cash.sum())))
            settled["source_tx"] = settled["source_tx"].astype(str).map(short_addr)
            st.dataframe(
                clean_table(
                    settled,
                    [
                        "source_time",
                        "reason",
                        "title",
                        "source_size",
                        "source_notional",
                        "copy_size",
                        "copy_notional",
                        "realized_pnl",
                        "source_tx",
                    ],
                ),
                width="stretch",
                height=430,
                column_config={
                    "source_size": st.column_config.NumberColumn(format="%.4f"),
                    "source_notional": st.column_config.NumberColumn(format="$%.2f"),
                    "copy_size": st.column_config.NumberColumn(format="%.4f"),
                    "copy_notional": st.column_config.NumberColumn(format="$%.2f"),
                    "realized_pnl": st.column_config.NumberColumn(format="$%.2f"),
                },
            )
    with tab_cash:
        if filtered_cash_events.empty:
            draw_empty("No manual paper cash top-ups recorded.")
        else:
            st.download_button("Export cash events CSV", filtered_cash_events.to_csv(index=False).encode("utf-8"), file_name="paper_cash_events.csv", mime="text/csv")
            st.dataframe(
                clean_table(filtered_cash_events, ["event_time", "amount", "cash_before", "cash_after", "reason", "note"]),
                width="stretch",
                height=360,
                column_config={
                    "amount": st.column_config.NumberColumn(format="$%.2f"),
                    "cash_before": st.column_config.NumberColumn(format="$%.2f"),
                    "cash_after": st.column_config.NumberColumn(format="$%.2f"),
                },
            )
    with tab_skipped:
        skipped = filtered_orders[~filtered_orders["status"].isin(["copied", "settled"])].copy() if not filtered_orders.empty else pd.DataFrame()
        if skipped.empty:
            draw_empty("No skipped or baseline trades.")
        else:
            skipped["asset"] = skipped["asset"].astype(str).map(short_addr)
            skipped["source_tx"] = skipped["source_tx"].astype(str).map(short_addr)
            st.dataframe(
                clean_table(
                    skipped,
                    ["source_time", "status", "reason", "source_side", "outcome", "title", "source_price", "source_notional", "asset", "source_tx"],
                ),
                width="stretch",
                height=430,
                column_config={
                    "source_price": st.column_config.NumberColumn(format="%.4f"),
                    "source_notional": st.column_config.NumberColumn(format="$%.2f"),
                },
            )


def page_portfolio() -> None:
    section_header("Portfolio", "Parity-style portfolio dashboard for research positions, copy-trading equity, exposure, history, and watchlist.")
    if "portfolio_search" not in st.session_state:
        reset_portfolio_filter_widgets(global_query)
    if st.session_state.pop("portfolio_filters_reset_pending", False):
        reset_portfolio_filter_widgets(global_query)
    pending_portfolio_view = st.session_state.pop("pending_portfolio_filter_view", None)
    if isinstance(pending_portfolio_view, dict):
        apply_portfolio_filter_view_widgets(pending_portfolio_view)
    pending_portfolio_clear = st.session_state.pop("portfolio_clear_pending", None)
    if isinstance(pending_portfolio_clear, dict):
        for key, value in pending_portfolio_clear.items():
            st.session_state[key] = value
    route_filter_params = query_param_snapshot(
        [
            "q",
            "query",
            "search",
            "wallet",
            "market",
            "platform",
            "platforms",
            "venue",
            "venues",
            "outcome",
            "outcomes",
            "side",
            "sides",
            "rows",
            "limit",
            "minValue",
            "valueMin",
            "minPositionValue",
            "positionValueMin",
            "minPnl",
            "pnlMin",
            "profitMin",
            "source",
            "sources",
            "copyStatus",
            "copyStatuses",
            "status",
            "statuses",
            "losersOnly",
            "losingOnly",
            "lossesOnly",
        ]
    )
    route_filter_signature = json.dumps(route_filter_params, sort_keys=True)
    route_filter_view = md.predictparity_portfolio_filter_view(route_filter_params)
    if route_filter_view and st.session_state.get("portfolio_route_filter_signature") != route_filter_signature:
        apply_portfolio_filter_view_widgets(route_filter_view)
        st.session_state["portfolio_route_filter_signature"] = route_filter_signature
        st.session_state["portfolio_view_loaded_message"] = "Loaded portfolio filters from URL."

    enriched, metrics = md.portfolio_metrics(st.session_state.portfolio)
    try:
        copy_snapshot = ct.value_paper_portfolio()
        copy_orders = ct.get_paper_orders()
        cash_events = ct.get_cash_events()
    except Exception as exc:
        st.warning(f"Copy portfolio unavailable: {exc}")
        copy_snapshot = None
        copy_orders = pd.DataFrame()
        cash_events = pd.DataFrame()

    copy_positions = copy_snapshot.positions if copy_snapshot is not None else pd.DataFrame()
    research_cash = max(float(st.session_state.get("research_cash", RESEARCH_START_CASH) or 0.0), 0.0)
    total_marked_value = research_cash + float(metrics["value"]) + (float(copy_snapshot.equity) if copy_snapshot is not None else 0.0)
    total_pnl = float(metrics["pnl"]) + (float(copy_snapshot.realized_pnl + copy_snapshot.unrealized_pnl) if copy_snapshot is not None else 0.0)

    controls = st.columns([1.5, 1, 1, 1, 1])
    portfolio_query = controls[0].text_input("Portfolio search", placeholder="market, outcome, wallet, reason", key="portfolio_search")
    portfolio_platforms = controls[1].multiselect("Platform", ["Polymarket", "Kalshi"], key="portfolio_platforms")
    portfolio_outcomes = controls[2].multiselect("Outcome", ["Yes", "No"], key="portfolio_outcomes")
    portfolio_rows = controls[3].slider("Rows", min_value=25, max_value=500, step=25, key="portfolio_rows")
    portfolio_min_value = controls[4].number_input("Min value", min_value=0, step=100, key="portfolio_min_value")
    with st.expander("Portfolio filters", expanded=False):
        f1, f2, f3, f4 = st.columns(4)
        portfolio_sources = f1.multiselect("Sources", ["Research", "Copy", "Watchlist", "History"], key="portfolio_sources")
        portfolio_min_pnl = f2.number_input("Min PnL", step=100, key="portfolio_min_pnl")
        portfolio_copy_statuses = f3.multiselect("Copy order status", COPY_ORDER_STATUS_FILTERS, key="portfolio_copy_statuses")
        portfolio_losers_only = f4.checkbox("Losing rows only", key="portfolio_losers_only")
        if st.button("Reset Filters", width="stretch", key="reset_portfolio_filters_button"):
            st.session_state["portfolio_filters_reset_pending"] = True
            st.rerun()

    save_cols = st.columns([2, 1, 1])
    saved_portfolio_name = save_cols[0].text_input("Saved portfolio view name", value=f"Portfolio {md.now_utc_label()}", key="saved_portfolio_view_name")
    save_portfolio_clicked = save_cols[1].button("Save Filter", width="stretch", key="save_portfolio_filter_button")
    if save_cols[2].button("Reset Portfolio View", width="stretch", key="reset_portfolio_view_button"):
        st.session_state["portfolio_filters_reset_pending"] = True
        st.rerun()
    loaded_portfolio_message = st.session_state.pop("portfolio_view_loaded_message", "")
    if loaded_portfolio_message:
        st.info(loaded_portfolio_message)
    if st.session_state.saved_portfolio_filters:
        load_cols = st.columns([2, 1, 1])
        saved_labels = [
            f"{i + 1}. {view.get('name') or view.get('query') or 'Portfolio view'}"
            for i, view in enumerate(st.session_state.saved_portfolio_filters)
        ]
        selected_saved_portfolio = load_cols[0].selectbox("Load saved portfolio view", saved_labels, key="load_saved_portfolio_view")
        selected_portfolio_view = st.session_state.saved_portfolio_filters[saved_labels.index(selected_saved_portfolio)]
        if load_cols[1].button("Load portfolio view", key="load_portfolio_view_button"):
            st.session_state["pending_portfolio_filter_view"] = selected_portfolio_view
            st.session_state["portfolio_view_loaded_message"] = f"Loaded saved portfolio view: {selected_portfolio_view.get('name', selected_saved_portfolio)}"
            st.rerun()
        if load_cols[2].button("Delete portfolio view", key="delete_portfolio_view_button"):
            st.session_state.saved_portfolio_filters.pop(saved_labels.index(selected_saved_portfolio))
            save_local_list("saved_portfolio_filters.json", st.session_state.saved_portfolio_filters)
            st.rerun()
    if save_portfolio_clicked:
        st.session_state.saved_portfolio_filters.append(
            {
                "name": saved_portfolio_name.strip() or f"Portfolio {md.now_utc_label()}",
                "created_at": md.now_utc_label(),
                "query": portfolio_query,
                "platforms": portfolio_platforms,
                "outcomes": portfolio_outcomes,
                "rows": int(portfolio_rows),
                "min_value": int(portfolio_min_value),
                "min_pnl": float(portfolio_min_pnl),
                "sources": portfolio_sources,
                "copy_statuses": portfolio_copy_statuses,
                "losers_only": bool(portfolio_losers_only),
            }
        )
        save_local_list("saved_portfolio_filters.json", st.session_state.saved_portfolio_filters)
        st.success("Saved portfolio view.")

    def _filter_position_rows(
        frame: pd.DataFrame,
        *,
        platform_col: str = "platform",
        outcome_col: str = "outcome",
        value_col: str = "value",
        pnl_col: str = "pnl",
    ) -> pd.DataFrame:
        filtered = frame.copy()
        if filtered.empty:
            return filtered
        filtered = filter_text(filtered, portfolio_query)
        if platform_col in filtered and portfolio_platforms:
            filtered = filtered[filtered[platform_col].astype(str).isin(portfolio_platforms)]
        elif platform_col in filtered and not portfolio_platforms:
            filtered = filtered.iloc[0:0]
        if outcome_col in filtered and portfolio_outcomes:
            filtered = filtered[filtered[outcome_col].astype(str).isin(portfolio_outcomes)]
        elif outcome_col in filtered and not portfolio_outcomes:
            filtered = filtered.iloc[0:0]
        if value_col in filtered:
            filtered = filtered[numeric_col(filtered, value_col) >= float(portfolio_min_value)]
        if pnl_col in filtered:
            filtered = filtered[numeric_col(filtered, pnl_col) >= float(portfolio_min_pnl)]
            if portfolio_losers_only:
                filtered = filtered[numeric_col(filtered, pnl_col) < 0]
        return filtered.head(int(portfolio_rows)).reset_index(drop=True)

    filtered_research = _filter_position_rows(enriched)
    filtered_copy_positions = copy_positions.copy()
    if not filtered_copy_positions.empty:
        filtered_copy_positions["platform"] = "Polymarket"
        filtered_copy_positions = _filter_position_rows(filtered_copy_positions, pnl_col="unrealized_pnl")
    filtered_copy_orders = copy_orders.copy()
    if not filtered_copy_orders.empty:
        filtered_copy_orders["platform"] = "Polymarket"
        filtered_copy_orders = _filter_position_rows(filtered_copy_orders, outcome_col="outcome", value_col="copy_notional", pnl_col="realized_pnl")
        if portfolio_copy_statuses:
            status_buckets = [
                copy_order_status_bucket(status, reason)
                for status, reason in zip(
                    filtered_copy_orders.get("status", pd.Series("", index=filtered_copy_orders.index)).tolist(),
                    filtered_copy_orders.get("reason", pd.Series("", index=filtered_copy_orders.index)).tolist(),
                )
            ]
            filtered_copy_orders = filtered_copy_orders.assign(status_bucket=status_buckets)
            filtered_copy_orders = filtered_copy_orders[filtered_copy_orders["status_bucket"].isin([item.lower() for item in portfolio_copy_statuses])]
        else:
            filtered_copy_orders = filtered_copy_orders.iloc[0:0]

    portfolio_defaults = portfolio_filter_defaults()
    portfolio_chips: list[str] = []
    if portfolio_query.strip():
        portfolio_chips.append(f"Search: {portfolio_query.strip()}")
    if set(portfolio_platforms) != set(portfolio_defaults["portfolio_platforms"]):
        portfolio_chips.append("Platform: " + (", ".join(portfolio_platforms) if portfolio_platforms else "none"))
    if set(portfolio_outcomes) != set(portfolio_defaults["portfolio_outcomes"]):
        portfolio_chips.append("Outcome: " + (", ".join(portfolio_outcomes) if portfolio_outcomes else "none"))
    if int(portfolio_rows) != int(portfolio_defaults["portfolio_rows"]):
        portfolio_chips.append(f"Rows: {int(portfolio_rows)}")
    if int(portfolio_min_value) > 0:
        portfolio_chips.append(f"Value >= {money(portfolio_min_value)}")
    if set(portfolio_sources) != set(portfolio_defaults["portfolio_sources"]):
        portfolio_chips.append("Sources: " + (", ".join(portfolio_sources) if portfolio_sources else "none"))
    if float(portfolio_min_pnl) != float(portfolio_defaults["portfolio_min_pnl"]):
        portfolio_chips.append(f"PnL >= {money(portfolio_min_pnl)}")
    if set(portfolio_copy_statuses) != set(portfolio_defaults["portfolio_copy_statuses"]):
        portfolio_chips.append("Copy status: " + (", ".join(portfolio_copy_statuses) if portfolio_copy_statuses else "none"))
    if portfolio_losers_only:
        portfolio_chips.append("Losing rows only")
    render_filter_chips(portfolio_chips)

    portfolio_clear_actions: list[tuple[str, dict[str, Any]]] = []
    if portfolio_query.strip():
        portfolio_clear_actions.append(("search", {"portfolio_search": ""}))
    if set(portfolio_platforms) != set(portfolio_defaults["portfolio_platforms"]):
        portfolio_clear_actions.append(("platform", {"portfolio_platforms": portfolio_defaults["portfolio_platforms"]}))
    if set(portfolio_outcomes) != set(portfolio_defaults["portfolio_outcomes"]):
        portfolio_clear_actions.append(("outcome", {"portfolio_outcomes": portfolio_defaults["portfolio_outcomes"]}))
    if int(portfolio_rows) != int(portfolio_defaults["portfolio_rows"]):
        portfolio_clear_actions.append(("rows", {"portfolio_rows": portfolio_defaults["portfolio_rows"]}))
    if int(portfolio_min_value) > 0:
        portfolio_clear_actions.append(("value", {"portfolio_min_value": 0}))
    if set(portfolio_sources) != set(portfolio_defaults["portfolio_sources"]):
        portfolio_clear_actions.append(("sources", {"portfolio_sources": portfolio_defaults["portfolio_sources"]}))
    if float(portfolio_min_pnl) != float(portfolio_defaults["portfolio_min_pnl"]):
        portfolio_clear_actions.append(("PnL", {"portfolio_min_pnl": portfolio_defaults["portfolio_min_pnl"]}))
    if set(portfolio_copy_statuses) != set(portfolio_defaults["portfolio_copy_statuses"]):
        portfolio_clear_actions.append(("copy status", {"portfolio_copy_statuses": portfolio_defaults["portfolio_copy_statuses"]}))
    if portfolio_losers_only:
        portfolio_clear_actions.append(("losing only", {"portfolio_losers_only": False}))
    render_filter_clear_buttons(portfolio_clear_actions, "portfolio")
    if st.session_state.saved_portfolio_filters:
        st.caption(f"Saved portfolio views: {len(st.session_state.saved_portfolio_filters)}")
        with st.expander("Saved portfolio filters", expanded=False):
            st.dataframe(pd.DataFrame(st.session_state.saved_portfolio_filters), width="stretch", height=160)
            if st.button("Clear saved portfolio filters"):
                st.session_state.saved_portfolio_filters = []
                save_local_list("saved_portfolio_filters.json", st.session_state.saved_portfolio_filters)
                st.rerun()

    p1, p2, p3, p4, p5, p6 = st.columns(6)
    p1.metric("Marked value", money(total_marked_value))
    p2.metric("Research cash", money(research_cash))
    p3.metric("Research PnL", money(metrics["pnl"]), pct(metrics["pnl_pct"]))
    p4.metric("Copy equity", money(copy_snapshot.equity if copy_snapshot is not None else 0.0))
    p5.metric("Copy PnL", money(copy_snapshot.realized_pnl + copy_snapshot.unrealized_pnl if copy_snapshot is not None else 0.0))
    p6.metric("Total PnL", money(total_pnl))

    tab_summary, tab_research, tab_wallet_import, tab_copy, tab_exposure, tab_cash_events, tab_history, tab_watchlist = st.tabs(
        ["Summary", "Research Portfolio", "Wallet Import", "Copy Portfolio", "Exposure", "Cash Events", "Paper History", "Watchlist"]
    )
    with tab_summary:
        left, right = st.columns([1, 1])
        with left:
            st.markdown("### Portfolio mix")
            mix_rows = [
                {"bucket": "Research cash", "value": research_cash},
                {"bucket": "Research positions", "value": float(metrics["value"])},
                {"bucket": "Copy cash", "value": float(copy_snapshot.cash if copy_snapshot is not None else 0.0)},
                {"bucket": "Copy positions", "value": float(copy_snapshot.position_value if copy_snapshot is not None else 0.0)},
            ]
            mix = pd.DataFrame(mix_rows)
            fig = px.pie(mix, values="value", names="bucket", template="plotly_dark", color_discrete_sequence=[ACCENT, BLUE, AMBER])
            fig.update_layout(height=320, margin=dict(l=10, r=10, t=20, b=10), paper_bgcolor=BG)
            st.plotly_chart(fig, width="stretch", config=plot_config())
        with right:
            st.markdown("### PnL split")
            pnl_rows = [
                {"bucket": "Research unrealized", "pnl": float(metrics["pnl"])},
                {"bucket": "Copy realized", "pnl": float(copy_snapshot.realized_pnl if copy_snapshot is not None else 0.0)},
                {"bucket": "Copy unrealized", "pnl": float(copy_snapshot.unrealized_pnl if copy_snapshot is not None else 0.0)},
            ]
            pnl_frame = pd.DataFrame(pnl_rows)
            fig = px.bar(pnl_frame, x="bucket", y="pnl", color="bucket", template="plotly_dark", color_discrete_sequence=[ACCENT, BLUE, AMBER])
            fig.update_layout(height=320, margin=dict(l=10, r=10, t=20, b=80), paper_bgcolor=BG, plot_bgcolor=BG, showlegend=False)
            st.plotly_chart(fig, width="stretch", config=plot_config())
        st.markdown("### Top copy positions")
        if "Copy" not in portfolio_sources:
            draw_empty("Copy source is hidden by the portfolio filters.")
        elif filtered_copy_positions.empty:
            draw_empty("No copy positions currently open.")
        else:
            top_copy = clean_table(filtered_copy_positions, ["title", "outcome", "shares", "avg_price", "current_price", "cost_basis", "value", "unrealized_pnl"]).head(15)
            st.dataframe(
                top_copy,
                width="stretch",
                height=300,
                column_config={
                    "shares": st.column_config.NumberColumn(format="%.2f"),
                    "avg_price": st.column_config.NumberColumn(format="%.4f"),
                    "current_price": st.column_config.NumberColumn(format="%.4f"),
                    "cost_basis": st.column_config.NumberColumn(format="$%.2f"),
                    "value": st.column_config.NumberColumn(format="$%.2f"),
                    "unrealized_pnl": st.column_config.NumberColumn(format="$%.2f"),
                },
            )

    with tab_research:
        st.markdown("### Research portfolio")
        cash_cols = st.columns([1, 1, 1, 3])
        cash_cols[0].metric("Research cash", money(research_cash))
        if cash_cols[1].button("Add $1,000 research cash", key="portfolio_add_research_cash", width="stretch"):
            research_cash = max(float(st.session_state.get("research_cash", RESEARCH_START_CASH) or 0.0), 0.0) + 1000.0
            st.session_state.research_cash = research_cash
            save_local_research_cash(research_cash)
            st.success(f"Research cash topped up to {money(research_cash)}.")
            st.rerun()
        if cash_cols[2].button("Reset research cash", key="portfolio_reset_research_cash", width="stretch"):
            research_cash = RESEARCH_START_CASH
            st.session_state.research_cash = research_cash
            save_local_research_cash(research_cash)
            st.warning(f"Research cash reset to {money(research_cash)}. Open research positions stay unchanged.")
            st.rerun()
        edited = st.data_editor(
            st.session_state.portfolio,
            width="stretch",
            num_rows="dynamic",
            column_config={
                "platform": st.column_config.SelectboxColumn(options=["Polymarket", "Kalshi"]),
                "outcome": st.column_config.SelectboxColumn(options=["Yes", "No"]),
                "shares": st.column_config.NumberColumn(min_value=0.0, step=1.0),
                "avg_price": st.column_config.NumberColumn(min_value=0.0, max_value=1.0, step=0.01),
                "current_price": st.column_config.NumberColumn(min_value=0.0, max_value=1.0, step=0.01),
                "url": st.column_config.LinkColumn("URL"),
            },
        )
        st.session_state.portfolio = edited
        save_local_portfolio(edited)
        enriched, metrics = md.portfolio_metrics(edited)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Cost", money(metrics["cost"]))
        c2.metric("Current value", money(metrics["value"]))
        c3.metric("PnL", money(metrics["pnl"]))
        c4.metric("PnL %", pct(metrics["pnl_pct"]))
        filtered_research = _filter_position_rows(enriched)
        if "Research" not in portfolio_sources:
            draw_empty("Research source is hidden by the portfolio filters.")
        elif not filtered_research.empty:
            st.download_button("Export research portfolio CSV", filtered_research.to_csv(index=False).encode("utf-8"), file_name="research_portfolio.csv", mime="text/csv")
            st.dataframe(filtered_research, width="stretch", height=360, column_config={"url": st.column_config.LinkColumn("URL")})
        else:
            draw_empty("No research rows match the current portfolio filters.")

    with tab_wallet_import:
        st.markdown("### Wallet portfolio import")
        default_wallet = st.session_state.followed_wallets[0] if st.session_state.followed_wallets else ct.COPY_TARGET_WALLET
        import_wallet = st.text_input("Polymarket wallet", value=default_wallet, placeholder="0x...", key="portfolio_import_wallet")
        if not re.fullmatch(r"0x[a-fA-F0-9]{40}", import_wallet.strip()):
            st.warning("Enter a valid Polymarket proxy-wallet address.")
        else:
            open_positions, closed_positions, trades, activity = safe_load(
                "Portfolio wallet import",
                load_wallet_bundle,
                import_wallet.strip(),
                250,
                default=(pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()),
            )
            imported = wallet_positions_to_research_portfolio(open_positions)
            wallet_stats = md.wallet_summary(open_positions, closed_positions, trades)
            w1, w2, w3, w4, w5 = st.columns(5)
            w1.metric("Open value", money(wallet_stats["open_value"]))
            w2.metric("Open positions", f"{len(open_positions):,}")
            w3.metric("Realized PnL", money(wallet_stats["realized_pnl"]))
            w4.metric("Unrealized PnL", money(wallet_stats["unrealized_pnl"]))
            w5.metric("Win rate", pct(wallet_stats["win_rate"]) if wallet_stats["win_rate"] is not None else "-")
            import_cols = st.columns([1, 1, 3])
            if import_cols[0].button("Merge open positions", key="portfolio_merge_wallet_positions", width="stretch", disabled=imported.empty):
                st.session_state.portfolio = merge_research_portfolio(st.session_state.portfolio, imported)
                save_local_portfolio(st.session_state.portfolio)
                st.success(f"Imported {len(imported)} open wallet positions into the research portfolio.")
                st.rerun()
            if import_cols[1].button("Track wallet", key="portfolio_import_track_wallet", width="stretch"):
                value = import_wallet.strip()
                if value.lower() not in [w.lower() for w in st.session_state.followed_wallets]:
                    st.session_state.followed_wallets.append(value)
                    save_local_list("followed_wallets.json", st.session_state.followed_wallets)
                    st.success("Wallet added to tracked wallets.")
            if imported.empty:
                draw_empty("No open positions returned for this wallet.")
            else:
                st.download_button("Export wallet import CSV", imported.to_csv(index=False).encode("utf-8"), file_name="wallet_import_positions.csv", mime="text/csv")
                st.dataframe(
                    imported.head(250),
                    width="stretch",
                    height=430,
                    column_config={
                        "market": st.column_config.TextColumn("Market", width="large"),
                        "shares": st.column_config.NumberColumn(format="%.2f"),
                        "avg_price": st.column_config.NumberColumn(format="%.4f"),
                        "current_price": st.column_config.NumberColumn(format="%.4f"),
                        "url": st.column_config.LinkColumn("URL"),
                    },
                )
            with st.expander("Closed positions and recent wallet activity", expanded=False):
                a1, a2 = st.tabs(["Closed positions", "Recent activity"])
                with a1:
                    if closed_positions.empty:
                        draw_empty("No closed positions returned.")
                    else:
                        st.dataframe(
                            clean_table(closed_positions, ["time", "title", "outcome", "avg_price", "current_price", "total_bought", "realized_pnl", "url"]).head(150),
                            width="stretch",
                            height=360,
                            column_config={"url": st.column_config.LinkColumn("URL")},
                        )
                with a2:
                    if activity.empty:
                        draw_empty("No wallet activity returned.")
                    else:
                        st.dataframe(clean_table(activity, ["time", "type", "side", "outcome", "title", "price", "size", "notional", "transactionHash"]).head(150), width="stretch", height=360)

    with tab_copy:
        st.markdown("### Copy portfolio")
        if copy_snapshot is None:
            draw_empty("Copy portfolio unavailable.")
        elif "Copy" not in portfolio_sources:
            draw_empty("Copy source is hidden by the portfolio filters.")
        else:
            cash_controls = st.columns([1, 4])
            if cash_controls[0].button("Add $1,000 cash", key="portfolio_add_copy_cash", width="stretch"):
                try:
                    new_cash = ct.add_paper_cash(1000.0, reason="manual_portfolio_cash_top_up", note="Portfolio page")
                    st.success(f"Paper cash topped up to {money(new_cash)} without closing copy positions.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Cash top-up failed: {exc}")
            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("Cash", money(copy_snapshot.cash))
            c2.metric("Equity", money(copy_snapshot.equity))
            c3.metric("Position value", money(copy_snapshot.position_value))
            c4.metric("Realized PnL", money(copy_snapshot.realized_pnl))
            c5.metric("Unrealized PnL", money(copy_snapshot.unrealized_pnl))
            if not filtered_copy_positions.empty:
                st.download_button("Export copy positions CSV", filtered_copy_positions.to_csv(index=False).encode("utf-8"), file_name="copy_positions.csv", mime="text/csv")
                display = filtered_copy_positions.copy()
                if "asset" in display:
                    display["asset"] = display["asset"].astype(str).map(short_addr)
                st.dataframe(
                    clean_table(display, ["title", "outcome", "shares", "avg_price", "current_price", "cost_basis", "value", "unrealized_pnl", "pnl_pct", "asset"]),
                    width="stretch",
                    height=420,
                    column_config={
                        "shares": st.column_config.NumberColumn(format="%.2f"),
                        "avg_price": st.column_config.NumberColumn(format="%.4f"),
                        "current_price": st.column_config.NumberColumn(format="%.4f"),
                        "cost_basis": st.column_config.NumberColumn(format="$%.2f"),
                        "value": st.column_config.NumberColumn(format="$%.2f"),
                        "unrealized_pnl": st.column_config.NumberColumn(format="$%.2f"),
                        "pnl_pct": st.column_config.NumberColumn(format="%.2f"),
                    },
                )
            else:
                draw_empty("No copy positions match the current portfolio filters.")
            if not filtered_copy_orders.empty:
                st.markdown("### Recent copy orders")
                st.download_button("Export copy orders CSV", filtered_copy_orders.to_csv(index=False).encode("utf-8"), file_name="copy_orders.csv", mime="text/csv")
                st.dataframe(clean_table(filtered_copy_orders, ["source_time", "status", "reason", "source_side", "title", "source_price", "source_notional", "copy_notional", "realized_pnl"]).head(int(portfolio_rows)), width="stretch", height=360)

    with tab_exposure:
        st.markdown("### Exposure")
        exposure_rows: list[dict[str, Any]] = []
        if "Research" in portfolio_sources and not filtered_research.empty:
            for _, row in filtered_research.iterrows():
                exposure_rows.append(
                    {
                        "source": "Research",
                        "platform": row.get("platform", ""),
                        "market": row.get("market", ""),
                        "outcome": row.get("outcome", ""),
                        "value": float(row.get("value", 0.0) or 0.0),
                        "pnl": float(row.get("pnl", 0.0) or 0.0),
                    }
                )
        if "Copy" in portfolio_sources and not filtered_copy_positions.empty:
            for _, row in filtered_copy_positions.iterrows():
                exposure_rows.append(
                    {
                        "source": "Copy",
                        "platform": "Polymarket",
                        "market": row.get("title", ""),
                        "outcome": row.get("outcome", ""),
                        "value": float(row.get("value", 0.0) or 0.0),
                        "pnl": float(row.get("unrealized_pnl", 0.0) or 0.0),
                    }
                )
        exposure = pd.DataFrame(exposure_rows)
        if exposure.empty:
            draw_empty("No research or copy exposure available.")
        else:
            total_exposure = float(exposure["value"].sum())
            top_exposure = float(exposure["value"].max()) if not exposure.empty else 0.0
            e1, e2, e3 = st.columns(3)
            e1.metric("Gross exposure", money(total_exposure))
            e2.metric("Largest position", money(top_exposure), pct(top_exposure / total_exposure if total_exposure else 0))
            e3.metric("Positions", f"{len(exposure):,}")
            by_source = exposure.groupby(["source", "platform"], as_index=False)["value"].sum()
            fig = px.bar(by_source, x="platform", y="value", color="source", template="plotly_dark", color_discrete_map={"Research": ACCENT, "Copy": BLUE})
            fig.update_layout(height=320, margin=dict(l=10, r=10, t=20, b=40), paper_bgcolor=BG, plot_bgcolor=BG)
            st.plotly_chart(fig, width="stretch", config=plot_config())
            st.dataframe(exposure.sort_values("value", ascending=False).head(int(portfolio_rows)), width="stretch", height=430, column_config={"value": st.column_config.NumberColumn(format="$%.2f"), "pnl": st.column_config.NumberColumn(format="$%.2f")})

    with tab_cash_events:
        st.markdown("### Copy cash events")
        if cash_events.empty:
            draw_empty("No manual copy-cash top-ups have been recorded.")
        else:
            st.download_button("Export copy cash events CSV", cash_events.to_csv(index=False).encode("utf-8"), file_name="copy_cash_events.csv", mime="text/csv")
            st.dataframe(
                clean_table(cash_events, ["event_time", "amount", "cash_before", "cash_after", "reason", "note"]),
                width="stretch",
                height=430,
                column_config={
                    "amount": st.column_config.NumberColumn(format="$%.2f"),
                    "cash_before": st.column_config.NumberColumn(format="$%.2f"),
                    "cash_after": st.column_config.NumberColumn(format="$%.2f"),
                },
            )

    with tab_history:
        st.markdown("### Paper trade history")
        if "History" not in portfolio_sources:
            draw_empty("History source is hidden by the portfolio filters.")
        elif st.session_state.paper_trade_history:
            history = pd.DataFrame(st.session_state.paper_trade_history)
            history = _filter_position_rows(history, value_col="notional", pnl_col="realized_pnl")
            if history.empty:
                draw_empty("No paper history rows match the current portfolio filters.")
            else:
                st.download_button("Export paper history CSV", history.to_csv(index=False).encode("utf-8"), file_name="paper_trade_history.csv", mime="text/csv")
                st.dataframe(
                    history.sort_values("time", ascending=False).head(int(portfolio_rows)),
                    width="stretch",
                    height=430,
                    column_config={
                        "price": st.column_config.NumberColumn(format="%.4f"),
                        "shares": st.column_config.NumberColumn(format="%.2f"),
                        "notional": st.column_config.NumberColumn(format="$%.2f"),
                        "url": st.column_config.LinkColumn("URL"),
                    },
                )
            if st.button("Clear paper trade history"):
                st.session_state.paper_trade_history = []
                save_local_list("paper_trade_history.json", st.session_state.paper_trade_history)
                st.rerun()
        else:
            draw_empty("No local paper trade history yet.")

    with tab_watchlist:
        st.markdown("### Market watchlist")
        pm, ks, combined = load_market_universe()
        filtered = filter_text(combined, portfolio_query).head(int(portfolio_rows))
        if filtered.empty:
            draw_empty("No markets available for watchlist.")
        else:
            options = [f"{row.platform}: {str(row.title)[:100]}" for _, row in filtered.iterrows()]
            selected = st.selectbox("Add market", options)
            selected_row = filtered.iloc[options.index(selected)]
            if st.button("Add to watchlist"):
                item = {
                    "platform": selected_row["platform"],
                    "market_key": selected_row["market_key"],
                    "title": selected_row["title"],
                    "url": selected_row["url"],
                }
                if item["market_key"] not in [w["market_key"] for w in st.session_state.watchlist]:
                    st.session_state.watchlist.append(item)
                    save_local_list("watchlist.json", st.session_state.watchlist)
                    st.success("Market added to watchlist.")
        if "Watchlist" not in portfolio_sources:
            draw_empty("Watchlist source is hidden by the portfolio filters.")
        elif not st.session_state.watchlist:
            draw_empty("No watched markets yet.")
        else:
            watch = pd.DataFrame(st.session_state.watchlist)
            live = pd.concat([pm, ks], ignore_index=True) if not pm.empty or not ks.empty else pd.DataFrame()
            if not live.empty:
                watch = watch.merge(clean_table(live, ["market_key", "yes_price", "change_1h", "activity_volume", "volume_24h", "liquidity"]), on="market_key", how="left")
            watch = _filter_position_rows(watch, value_col="activity_volume", pnl_col="change_1h")
            if watch.empty:
                draw_empty("No watched markets match the current portfolio filters.")
            else:
                st.download_button("Export watchlist CSV", watch.to_csv(index=False).encode("utf-8"), file_name="watchlist.csv", mime="text/csv")
                st.dataframe(watch, width="stretch", height=330, column_config={"url": st.column_config.LinkColumn("URL")})
                remove_options = [f"{i + 1}. {str(item.get('title', '-'))[:100]}" for i, item in enumerate(st.session_state.watchlist)]
                r1, r2 = st.columns([2, 1])
                selected_remove = r1.selectbox("Remove watched market", remove_options)
                if r2.button("Remove selected market"):
                    st.session_state.watchlist.pop(remove_options.index(selected_remove))
                    save_local_list("watchlist.json", st.session_state.watchlist)
                    st.rerun()
                if st.button("Clear watchlist"):
                    st.session_state.watchlist = []
                    save_local_list("watchlist.json", st.session_state.watchlist)
                    st.rerun()


PAGES = {
    "Overview": page_overview,
    "Search": page_search,
    "Markets": page_markets,
    "Traders": page_traders,
    "Track": page_track,
    "Live Trades": page_live_trades,
    "Wallets": page_wallets,
    "Copy Trade": page_copy_trade,
    "Whale Flow": page_whale_flow,
    "Cross-Venue": page_cross_venue,
    "Monitor": page_monitor,
    "Alerts": page_alerts,
    "Resolved": page_resolved,
    "Portfolio": page_portfolio,
}


render_global_hotkeys()
render_command_bar()
if st.session_state.command_palette_open:
    render_command_palette_dialog()
if st.session_state.auth_dialog_mode:
    render_auth_dialog()


PAGES[page]()
