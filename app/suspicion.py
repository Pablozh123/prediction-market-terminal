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

import math
import re
from typing import Any

import pandas as pd

from app.filters import numeric_col
from app.format import money, pct

try:
    import networkx as nx
except ImportError:  # pragma: no cover - networkx ships with the environment
    nx = None

RISK_BANDS = ((70, "High"), (55, "Medium"), (40, "Elevated"))
WATCH_ONLY = "watch only"

# Insider-plausibility context: in some market categories there is nothing to
# "know" early (game results, weather models, public asset prices) — big flow
# there is high-roller action, not insider trading. In others the outcome is
# literally known to a small group before the public (award juries, boards,
# courts), which is where documented prediction-market insider cases happened.
CONTEXT_SPORTS = "Sports odds"
CONTEXT_MARKET_PRICES = "Crypto & market prices"
CONTEXT_WEATHER = "Weather & climate"
CONTEXT_POLITICS = "Politics & geopolitics"
CONTEXT_AWARDS = "Awards & entertainment"
CONTEXT_CORPORATE = "Corporate & legal"
CONTEXT_GENERAL = "General"

CONTEXT_MULTIPLIERS = {
    CONTEXT_SPORTS: 0.6,
    CONTEXT_MARKET_PRICES: 0.6,
    CONTEXT_WEATHER: 0.5,
    CONTEXT_POLITICS: 1.1,
    CONTEXT_AWARDS: 1.15,
    CONTEXT_CORPORATE: 1.15,
    CONTEXT_GENERAL: 1.0,
}

CONTEXT_NOTES = {
    CONTEXT_SPORTS: "public-odds arena — big flow here is usually high rollers, not insiders",
    CONTEXT_MARKET_PRICES: "asset prices are public — whales here are traders, not insiders",
    CONTEXT_WEATHER: "model-driven outcome — insider knowledge is implausible",
    CONTEXT_POLITICS: "decisions, talks and announcements are known to officials before the public",
    CONTEXT_AWARDS: "results are known to juries and production staff early — documented insider territory",
    CONTEXT_CORPORATE: "decisions are known internally before announcement",
    CONTEXT_GENERAL: "",
}

# Groups where insider knowledge is plausible — the page focuses on these by default.
INSIDER_PRONE_GROUPS = (CONTEXT_POLITICS, CONTEXT_AWARDS, CONTEXT_CORPORATE, CONTEXT_GENERAL)

_CATEGORY_GROUPS = (
    (("sport", "sports", "nba", "nfl", "mlb", "soccer", "football", "esports"), CONTEXT_SPORTS),
    (("crypto", "cryptocurrency", "finance", "stocks"), CONTEXT_MARKET_PRICES),
    (("weather", "climate", "science"), CONTEXT_WEATHER),
    (("politic", "geopolitic", "election", "world", "global affairs"), CONTEXT_POLITICS),
    (("entertainment", "awards", "pop culture", "culture", "music", "movies", "tv"), CONTEXT_AWARDS),
    (("business", "companies", "tech", "earnings"), CONTEXT_CORPORATE),
)

_TITLE_PATTERNS = (
    (re.compile(r"\bvs\.?\b|\bnba\b|\bnfl\b|\bmlb\b|\bnhl\b|\bufc\b|\bgrand prix\b|\bpremier league\b|\bchampions league\b|\bbundesliga\b|\bserie a\b|\bla liga\b|\bsuper bowl\b|\bworld series\b|\bplayoffs?\b|\bopen:\s|\bwimbledon\b|\bolympic|\bspread:?\b|\bmoneyline\b|\bover/under\b|\bo/u\b|\([+-]?\d+(?:\.5)\)", re.I), CONTEXT_SPORTS),
    (re.compile(r"\bbitcoin\b|\bbtc\b|\bethereum\b|\beth\b|\bsolana\b|\bxrp\b|\bdogecoin\b|\bcrypto\b|\btoken\b|\bs&p\b|\bnasdaq\b|\bstock price\b|\bshare price\b|\bgold price\b|\boil price\b|\bhit \$|\breach \$", re.I), CONTEXT_MARKET_PRICES),
    (re.compile(r"\btemperature\b|\brainfall\b|\bsnowfall\b|\bhurricane\b|\bstorm\b|\bheat wave\b|\bweather\b|\bdegrees\b|°[cf]\b", re.I), CONTEXT_WEATHER),
    (re.compile(r"\boscars?\b|\bgrammys?\b|\bemmys?\b|\bgolden globe\b|\baward\b|\balbum\b|\bbox office\b|\btrailer\b|\bseason finale\b|\brenewed\b|\beurovision\b|\bperson of the year\b|\bbillboard\b", re.I), CONTEXT_AWARDS),
    (re.compile(r"\bceo\b|\bacquisition\b|\bmerger\b|\bipo\b|\bearnings\b|\blawsuit\b|\bcourt\b|\bruling\b|\bverdict\b|\bindicted?\b|\bconvicted\b|\bpardon\b|\bresigns?\b|\bappoints?\b|\bnominee\b|\bnomination\b|\bcabinet\b|\bsteps? down\b|\bfired\b|\brelease date\b", re.I), CONTEXT_CORPORATE),
    (re.compile(r"\bceasefire\b|\bsanctions?\b|\btariffs?\b|\btreaty\b|\bagreement\b|\bexecutive order\b|\bmilitary\b|\bstrikes?\b|\binvasion\b|\bnato\b|\bsummit\b|\belections?\b|\bpresident\b|\bminister\b|\bparliament\b|\bcongress\b|\bsenate\b|\bimpeach", re.I), CONTEXT_POLITICS),
)


def classify_insider_context(title: Any, category: Any = "") -> tuple[str, float, str]:
    """Map a market to an insider-plausibility group: (group, multiplier, note).

    Title keywords win over the coarse category field so that e.g. a "CEO
    resigns" market filed under Business stays insider-prone while a generic
    sports matchup is damped even when the category is missing.
    """

    title_text = str(title or "")
    for pattern, group in _TITLE_PATTERNS:
        if pattern.search(title_text):
            return group, CONTEXT_MULTIPLIERS[group], CONTEXT_NOTES[group]
    category_text = str(category or "").strip().lower()
    if category_text:
        for keys, group in _CATEGORY_GROUPS:
            if any(key in category_text for key in keys):
                return group, CONTEXT_MULTIPLIERS[group], CONTEXT_NOTES[group]
    return CONTEXT_GENERAL, CONTEXT_MULTIPLIERS[CONTEXT_GENERAL], CONTEXT_NOTES[CONTEXT_GENERAL]


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


def coordinated_clusters(
    trades: pd.DataFrame,
    *,
    window_minutes: float = 30.0,
    min_wallets: int = 3,
) -> pd.DataFrame:
    """Per market: most distinct wallets hitting the same side within a tight time window.

    Public cluster exposés describe wallets that trade within minutes of each
    other on the same side — this is the tape-level approximation of that
    pattern. Returns: title, coordinated_wallets, coordinated_outcome,
    coordinated_span_minutes, coordinated_notional.
    """

    columns = ["title", "coordinated_wallets", "coordinated_outcome", "coordinated_span_minutes", "coordinated_notional"]
    if trades is None or trades.empty or not {"wallet", "title", "time"}.issubset(trades.columns):
        return pd.DataFrame(columns=columns)
    df = trades.copy()
    df["wallet"] = df["wallet"].astype(str).str.lower().str.strip()
    df = df[df["wallet"].ne("") & df["wallet"].ne("nan")]
    df["time"] = pd.to_datetime(df["time"], utc=True, errors="coerce")
    df = df.dropna(subset=["time"])
    if df.empty:
        return pd.DataFrame(columns=columns)
    df["outcome_label"] = df.get("outcome", pd.Series("", index=df.index)).astype(str).str.upper().str.strip()
    df["notional"] = numeric_col(df, "notional")
    window = pd.Timedelta(minutes=float(window_minutes))
    rows: list[dict[str, Any]] = []
    for (title, outcome), group in df.groupby(["title", "outcome_label"], dropna=False):
        events = group.sort_values("time")[["time", "wallet", "notional"]].to_records(index=False)
        if len(events) < min_wallets:
            continue
        best_count = 0
        best_span = 0.0
        best_notional = 0.0
        left = 0
        for right in range(len(events)):
            while events[right][0] - events[left][0] > window:
                left += 1
            in_window = events[left : right + 1]
            wallets = {record[1] for record in in_window}
            if len(wallets) > best_count:
                best_count = len(wallets)
                best_span = (events[right][0] - events[left][0]).total_seconds() / 60
                best_notional = float(sum(record[2] for record in in_window))
        if best_count >= min_wallets:
            rows.append(
                {
                    "title": str(title),
                    "coordinated_wallets": int(best_count),
                    "coordinated_outcome": str(outcome),
                    "coordinated_span_minutes": round(best_span, 1),
                    "coordinated_notional": best_notional,
                }
            )
    if not rows:
        return pd.DataFrame(columns=columns)
    result = pd.DataFrame(rows).sort_values(["coordinated_wallets", "coordinated_notional"], ascending=False)
    return result.drop_duplicates(subset=["title"], keep="first").reset_index(drop=True)


def apply_coordination_bonus(event_risk: pd.DataFrame, clusters: pd.DataFrame, max_bonus: float = 10.0) -> pd.DataFrame:
    """Bump event scores where several wallets hit the same side within minutes."""

    if event_risk is None or event_risk.empty or clusters is None or clusters.empty:
        return event_risk
    enriched = event_risk.merge(clusters, on="title", how="left")
    enriched["coordinated_wallets"] = pd.to_numeric(enriched.get("coordinated_wallets"), errors="coerce").fillna(0).astype(int)
    has_cluster = enriched["coordinated_wallets"] >= 3
    bonus = (enriched["coordinated_wallets"].clip(upper=5) * (max_bonus / 5.0)).where(has_cluster, 0.0)
    enriched["event_insider_score"] = (numeric_col(enriched, "event_insider_score") + bonus).clip(0, 100).round(0)
    enriched["event_insider_level"] = enriched["event_insider_score"].map(risk_level)
    if "event_insider_flags" in enriched:
        for idx in enriched.index[has_cluster]:
            count = int(enriched.at[idx, "coordinated_wallets"])
            span = float(enriched.at[idx, "coordinated_span_minutes"] or 0.0)
            outcome = str(enriched.at[idx, "coordinated_outcome"] or "").strip()
            label = f"{count} wallets within {span:.0f}min on {outcome}" if outcome else f"{count} wallets within {span:.0f}min"
            enriched.at[idx, "event_insider_flags"] = _append_flag(enriched.at[idx, "event_insider_flags"], label)
    return enriched


def co_trading_network(
    trades: pd.DataFrame,
    *,
    window_minutes: float | None = None,
    min_shared: int = 2,
    max_wallets: int = 200,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build the co-trading graph and its communities from the whale tape.

    Edge rule (the pattern public cluster trackers describe): two wallets are
    connected when they took the same side of at least ``min_shared`` markets —
    optionally only counting hits that landed within ``window_minutes`` of each
    other. Communities come from Louvain (weight = shared markets), which
    separates tight syndicates from incidental co-movers better than plain
    connected components; if networkx is unavailable, components are the
    fallback.

    Returns (nodes, edges):
    - nodes: wallet, cluster_id, cluster_size, shared_markets, volume, markets, trades
    - edges: wallet_a, wallet_b, shared_markets, pair_notional
    """

    node_columns = ["wallet", "cluster_id", "cluster_size", "shared_markets", "volume", "markets", "trades"]
    edge_columns = ["wallet_a", "wallet_b", "shared_markets", "pair_notional"]
    empty = (pd.DataFrame(columns=node_columns), pd.DataFrame(columns=edge_columns))
    if trades is None or trades.empty or not {"wallet", "title"}.issubset(trades.columns):
        return empty
    df = trades.copy()
    df["wallet"] = df["wallet"].astype(str).str.lower().str.strip()
    df = df[df["wallet"].ne("") & df["wallet"].ne("nan")]
    if df.empty:
        return empty
    df["outcome_label"] = df.get("outcome", pd.Series("", index=df.index)).astype(str).str.upper().str.strip()
    df["notional"] = numeric_col(df, "notional")
    by_size = df.groupby("wallet")["notional"].sum().sort_values(ascending=False)
    keep = set(by_size.head(int(max_wallets)).index)
    df = df[df["wallet"].isin(keep)]
    if df.empty:
        return empty

    use_window = window_minutes is not None and "time" in df.columns
    if use_window:
        df["time"] = pd.to_datetime(df["time"], utc=True, errors="coerce")
        df = df.dropna(subset=["time"])
        window = pd.Timedelta(minutes=float(window_minutes))

    pair_markets: dict[tuple[str, str], set[str]] = {}
    pair_notional: dict[tuple[str, str], float] = {}
    for (title, _outcome), group in df.groupby(["title", "outcome_label"], dropna=False):
        if use_window:
            records = group.sort_values("time")[["time", "wallet", "notional"]].to_records(index=False)
            left = 0
            for right in range(len(records)):
                while records[right][0] - records[left][0] > window:
                    left += 1
                for mid in range(left, right):
                    a, b = records[mid][1], records[right][1]
                    if a == b:
                        continue
                    key = (a, b) if a < b else (b, a)
                    pair_markets.setdefault(key, set()).add(str(title))
                    pair_notional[key] = pair_notional.get(key, 0.0) + float(records[mid][2]) + float(records[right][2])
        else:
            wallets_here = sorted(group.groupby("wallet")["notional"].sum().items())
            for i in range(len(wallets_here)):
                for j in range(i + 1, len(wallets_here)):
                    key = (wallets_here[i][0], wallets_here[j][0])
                    pair_markets.setdefault(key, set()).add(str(title))
                    pair_notional[key] = pair_notional.get(key, 0.0) + float(wallets_here[i][1]) + float(wallets_here[j][1])

    edge_rows = [
        {"wallet_a": a, "wallet_b": b, "shared_markets": len(markets), "pair_notional": pair_notional.get((a, b), 0.0)}
        for (a, b), markets in pair_markets.items()
        if len(markets) >= int(min_shared)
    ]
    if not edge_rows:
        return empty
    edges = pd.DataFrame(edge_rows, columns=edge_columns)

    members: list[set[str]]
    if nx is not None:
        graph = nx.Graph()
        for row in edge_rows:
            graph.add_edge(row["wallet_a"], row["wallet_b"], weight=row["shared_markets"])
        try:
            members = [set(community) for community in nx.community.louvain_communities(graph, weight="weight", seed=42)]
        except Exception:
            members = [set(component) for component in nx.connected_components(graph)]
    else:
        parent: dict[str, str] = {}

        def find(node: str) -> str:
            parent.setdefault(node, node)
            while parent[node] != node:
                parent[node] = parent[parent[node]]
                node = parent[node]
            return node

        for row in edge_rows:
            parent[find(row["wallet_a"])] = find(row["wallet_b"])
        grouped: dict[str, set[str]] = {}
        for node in parent:
            grouped.setdefault(find(node), set()).add(node)
        members = list(grouped.values())

    wallet_stats = df.groupby("wallet").agg(volume=("notional", "sum"), markets=("title", pd.Series.nunique), trades=("wallet", "size"))
    overlap: dict[str, int] = {}
    for row in edge_rows:
        overlap[row["wallet_a"]] = max(overlap.get(row["wallet_a"], 0), row["shared_markets"])
        overlap[row["wallet_b"]] = max(overlap.get(row["wallet_b"], 0), row["shared_markets"])

    communities = [community for community in members if len(community) >= 2]
    communities.sort(key=lambda community: -float(wallet_stats.loc[wallet_stats.index.isin(community), "volume"].sum()))
    node_rows = []
    for cluster_no, community in enumerate(communities, start=1):
        for wallet in sorted(community):
            stats = wallet_stats.loc[wallet] if wallet in wallet_stats.index else None
            node_rows.append(
                {
                    "wallet": wallet,
                    "cluster_id": cluster_no,
                    "cluster_size": len(community),
                    "shared_markets": overlap.get(wallet, 0),
                    "volume": float(stats["volume"]) if stats is not None else 0.0,
                    "markets": int(stats["markets"]) if stats is not None else 0,
                    "trades": int(stats["trades"]) if stats is not None else 0,
                }
            )
    if not node_rows:
        return empty
    nodes = pd.DataFrame(node_rows, columns=node_columns)
    keep_wallets = set(nodes["wallet"])
    edges = edges[edges["wallet_a"].isin(keep_wallets) & edges["wallet_b"].isin(keep_wallets)].reset_index(drop=True)
    return nodes, edges


def cluster_layout(nodes: pd.DataFrame) -> pd.DataFrame:
    """Island layout: clusters on a grid, members on a circle around each center."""

    if nodes is None or nodes.empty:
        return nodes
    placed = nodes.copy()
    placed["x"] = 0.0
    placed["y"] = 0.0
    cluster_ids = list(placed["cluster_id"].drop_duplicates())
    grid_cols = max(1, math.ceil(math.sqrt(len(cluster_ids))))
    spacing = 10.0
    for index, cluster_id in enumerate(cluster_ids):
        center_x = (index % grid_cols) * spacing
        center_y = -(index // grid_cols) * spacing
        member_index = placed.index[placed["cluster_id"] == cluster_id]
        count = len(member_index)
        radius = 1.2 + 0.45 * math.sqrt(count)
        for position, node_idx in enumerate(member_index):
            angle = (2 * math.pi * position) / max(count, 1)
            placed.at[node_idx, "x"] = center_x + radius * math.cos(angle)
            placed.at[node_idx, "y"] = center_y + radius * math.sin(angle)
    return placed


def wallet_co_trading_clusters(trades: pd.DataFrame, *, min_shared: int = 2, max_wallets: int = 200) -> pd.DataFrame:
    """Legacy simple view of the co-trading communities (no timing constraint).

    Returns wallet -> cluster_id, cluster_size, shared_markets; kept as the
    stable surface for the wallet-score bonus.
    """

    nodes, _edges = co_trading_network(trades, window_minutes=None, min_shared=min_shared, max_wallets=max_wallets)
    if nodes.empty:
        return pd.DataFrame(columns=["wallet", "cluster_id", "cluster_size", "shared_markets"])
    return nodes[["wallet", "cluster_id", "cluster_size", "shared_markets"]].copy()


def apply_cluster_bonus(wallet_risk: pd.DataFrame, clusters: pd.DataFrame, bonus: float = 5.0) -> pd.DataFrame:
    """Bump wallet scores for cluster members and flag them as possibly linked."""

    if wallet_risk is None or wallet_risk.empty or clusters is None or clusters.empty:
        return wallet_risk
    enriched = wallet_risk.copy()
    enriched["_wallet_key"] = enriched["wallet"].astype(str).str.lower().str.strip()
    enriched = enriched.merge(clusters.rename(columns={"wallet": "_wallet_key"}), on="_wallet_key", how="left")
    member = enriched["cluster_id"].notna()
    enriched.loc[member, "wallet_insider_score"] = (
        numeric_col(enriched.loc[member], "wallet_insider_score") + float(bonus)
    ).clip(0, 100).round(0)
    enriched["wallet_insider_level"] = enriched["wallet_insider_score"].map(risk_level)
    if "wallet_insider_flags" in enriched:
        for idx in enriched.index[member]:
            size = int(enriched.at[idx, "cluster_size"])
            enriched.at[idx, "wallet_insider_flags"] = _append_flag(
                enriched.at[idx, "wallet_insider_flags"], f"moves with {size - 1} other wallet{'s' if size > 2 else ''}"
            )
    return enriched.drop(columns=["_wallet_key"], errors="ignore")


def apply_category_context(event_risk: pd.DataFrame, market_categories: pd.DataFrame | None = None) -> pd.DataFrame:
    """Scale event scores by insider plausibility of the market category.

    Adds columns: insider_context, context_multiplier, context_note,
    event_score_raw (pre-context score). Re-sorts by the adjusted score.
    """

    if event_risk is None or event_risk.empty:
        return event_risk
    enriched = event_risk.copy()
    category_map: dict[str, str] = {}
    if market_categories is not None and not market_categories.empty and {"market_key", "category"}.issubset(market_categories.columns):
        keys = market_categories["market_key"].astype(str)
        category_map = dict(zip(keys, market_categories["category"].astype(str)))
    contexts = [
        classify_insider_context(row.get("title", ""), category_map.get(str(row.get("market_key", "")), ""))
        for _, row in enriched.iterrows()
    ]
    enriched["insider_context"] = [group for group, _, _ in contexts]
    enriched["context_multiplier"] = [multiplier for _, multiplier, _ in contexts]
    enriched["context_note"] = [note for _, _, note in contexts]
    enriched["event_score_raw"] = numeric_col(enriched, "event_insider_score")
    enriched["event_insider_score"] = (enriched["event_score_raw"] * enriched["context_multiplier"]).clip(0, 100).round(0)
    enriched["event_insider_level"] = enriched["event_insider_score"].map(risk_level)
    return enriched.sort_values(["event_insider_score", "notional"], ascending=False).reset_index(drop=True)


def apply_wallet_category_context(
    wallet_risk: pd.DataFrame,
    trades: pd.DataFrame,
    market_categories: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Scale wallet scores by the notional-weighted insider plausibility of their flow.

    A wallet whose whale flow sits mostly in sports/crypto/weather markets is
    damped (high roller, not insider); flow concentrated in insider-prone
    categories keeps or gains weight. Adds insider_context (dominant group),
    context_multiplier (weighted) and wallet_score_raw.
    """

    if wallet_risk is None or wallet_risk.empty or trades is None or trades.empty:
        return wallet_risk
    df = trades.copy()
    df["wallet"] = df["wallet"].astype(str).str.lower().str.strip()
    df = df[df["wallet"].ne("") & df["wallet"].ne("nan")]
    if df.empty:
        return wallet_risk
    category_map: dict[str, str] = {}
    if market_categories is not None and not market_categories.empty and {"market_key", "category"}.issubset(market_categories.columns):
        keys = market_categories["market_key"].astype(str)
        category_map = dict(zip(keys, market_categories["category"].astype(str)))
    contexts = [
        classify_insider_context(row.get("title", ""), category_map.get(str(row.get("market_key", "")), ""))
        for _, row in df.iterrows()
    ]
    df["_group"] = [group for group, _, _ in contexts]
    df["_multiplier"] = [multiplier for _, multiplier, _ in contexts]
    df["_notional"] = numeric_col(df, "notional").clip(lower=0.0)
    df["_weighted"] = df["_multiplier"] * df["_notional"]
    per_wallet = df.groupby("wallet").agg(_weighted=("_weighted", "sum"), _notional=("_notional", "sum"))
    per_wallet["context_multiplier"] = (per_wallet["_weighted"] / per_wallet["_notional"].replace({0: pd.NA})).fillna(1.0)
    dominant = (
        df.groupby(["wallet", "_group"])["_notional"].sum().reset_index().sort_values("_notional", ascending=False).drop_duplicates(subset=["wallet"], keep="first")
    )
    per_wallet = per_wallet.merge(dominant.rename(columns={"_group": "insider_context"})[["wallet", "insider_context"]], on="wallet", how="left")

    enriched = wallet_risk.copy()
    enriched["_wallet_key"] = enriched["wallet"].astype(str).str.lower().str.strip()
    enriched = enriched.merge(
        per_wallet.rename(columns={"wallet": "_wallet_key"})[["_wallet_key", "context_multiplier", "insider_context"]],
        on="_wallet_key",
        how="left",
    )
    enriched["context_multiplier"] = pd.to_numeric(enriched["context_multiplier"], errors="coerce").fillna(1.0)
    enriched["insider_context"] = enriched["insider_context"].fillna(CONTEXT_GENERAL)
    enriched["wallet_score_raw"] = numeric_col(enriched, "wallet_insider_score")
    enriched["wallet_insider_score"] = (enriched["wallet_score_raw"] * enriched["context_multiplier"]).clip(0, 100).round(0)
    enriched["wallet_insider_level"] = enriched["wallet_insider_score"].map(risk_level)
    if "wallet_insider_flags" in enriched:
        damped = enriched["context_multiplier"] <= 0.8
        boosted = enriched["context_multiplier"] >= 1.1
        for idx in enriched.index[damped]:
            group = str(enriched.at[idx, "insider_context"])
            enriched.at[idx, "wallet_insider_flags"] = _append_flag(enriched.at[idx, "wallet_insider_flags"], f"flow mostly in {group.lower()}")
        for idx in enriched.index[boosted]:
            enriched.at[idx, "wallet_insider_flags"] = _append_flag(enriched.at[idx, "wallet_insider_flags"], "insider-prone categories")
    return (
        enriched.drop(columns=["_wallet_key"], errors="ignore")
        .sort_values(["wallet_insider_score", "notional"], ascending=False)
        .reset_index(drop=True)
    )


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
