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

# Groups the risk screen drops ENTIRELY — not damped, not behind a toggle.
# Sports odds and weather: game results and weather models cannot be
# insider-traded. Crypto & market prices: asset prices are public, so a whale
# there is a trader, not an insider — and the 15-minute up/down markets are
# the busiest on both venues, so left in they flood every output (events,
# wallets, fresh-wallet and timing clusters, the co-trading network) with
# noise. Every consumer (API /api/risk, Streamlit "Suspicious" page) filters
# with this tuple; ``INSIDER_PRONE_GROUPS`` is its complement.
EXCLUDED_CONTEXTS = (CONTEXT_SPORTS, CONTEXT_WEATHER, CONTEXT_MARKET_PRICES)

# The multipliers only matter for the groups that survive the exclusion above;
# the excluded groups keep a value so ``classify_insider_context`` stays total.
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

# Groups where insider knowledge is plausible — the only groups the screen shows.
INSIDER_PRONE_GROUPS = (CONTEXT_POLITICS, CONTEXT_AWARDS, CONTEXT_CORPORATE, CONTEXT_GENERAL)

_CATEGORY_GROUPS = (
    (("sport", "sports", "nba", "nfl", "mlb", "soccer", "football", "esports"), CONTEXT_SPORTS),
    (("crypto", "cryptocurrency", "finance", "stocks"), CONTEXT_MARKET_PRICES),
    # NOTE: "science" deliberately NOT here — tech/science markets are not
    # model-driven weather outcomes and must not be damped/excluded.
    (("weather", "climate"), CONTEXT_WEATHER),
    (("politic", "geopolitic", "election", "world", "global affairs"), CONTEXT_POLITICS),
    (("entertainment", "awards", "pop culture", "culture", "music", "movies", "tv"), CONTEXT_AWARDS),
    (("business", "companies", "tech", "earnings"), CONTEXT_CORPORATE),
)

# Order matters. STRONG sports markers (leagues, esports titles, betting
# jargon) win first — a "Counter-Strike: X vs Y" market is sports even though
# "strike" appears in the politics pattern. Then the insider-prone patterns
# (corporate/legal, awards, politics) are checked BEFORE the bare "vs" token,
# so "Epic vs Apple ruling" or "Zelensky vs Putin summit" land in
# Corporate/Politics instead of being silently dropped as sports. A naked
# "X vs Y" with no other signal stays a sports matchup.
_TITLE_PATTERNS = (
    (re.compile(r"\bw?nba\b|\bnfl\b|\bmlb\b|\bnhl\b|\bufc\b|\bfinals\b|\bgrand prix\b|\bpremier league\b|\bchampions league\b|\bbundesliga\b|\bserie a\b|\bla liga\b|\bsuper bowl\b|\bworld series\b|\bworld cup\b|\bplayoffs?\b|\bopen:\s|\bwimbledon\b|\bolympic|\bspread:?\b|\bmoneyline\b|\bover/under\b|\bo/u\b|\bexact score\b|\bat halftime\b|\bboth teams to score\b|\bwins? by over\b|\b\d+(?:\.\d+)?\s+goals?\b|\([+-]?\d+(?:\.5)\)|counter[- ]strike|\bcs2\b|\bcsgo\b|\bdota\b|\bvalorant\b|\bleague of legends\b|\besports?\b", re.I), CONTEXT_SPORTS),
    (re.compile(r"\bceo\b|\bacquisition\b|\bmerger\b|\bipo\b|\bearnings\b|\blawsuit\b|\bcourt\b|\bruling\b|\bverdict\b|\bindicted?\b|\bconvicted\b|\bpardon\b|\bresigns?\b|\bappoints?\b|\bnominee\b|\bnomination\b|\bcabinet\b|\bsteps? down\b|\bfired\b|\brelease date\b", re.I), CONTEXT_CORPORATE),
    (re.compile(r"\boscars?\b|\bgrammys?\b|\bemmys?\b|\bgolden globe\b|\baward\b|\balbum\b|\bbox office\b|\btrailer\b|\bseason finale\b|\brenewed\b|\beurovision\b|\bperson of the year\b|\bbillboard\b", re.I), CONTEXT_AWARDS),
    (re.compile(r"\btemperature\b|\brainfall\b|\bsnowfall\b|\bhurricane\b|\bstorm\b|\bheat wave\b|\bweather\b|\bdegrees\b|°[cf]\b", re.I), CONTEXT_WEATHER),
    # Public asset prices: crypto, indices, commodities, market caps. "Up or
    # Down" is Polymarket's price-series format (Bitcoin/BNB/WTI Up or Down -
    # <window>); "hit (HIGH) $" is its commodity/valuation ladder format.
    (re.compile(r"\bbitcoin\b|\bbtc\b|\bethereum\b|\beth\b|\bsolana\b|\bxrp\b|\bdogecoin\b|\bbnb\b|\bcrypto\b|\btoken\b|\bs&p\b|\bnasdaq\b|\bstock price\b|\bshare price\b|\bgold price\b|\boil price\b|\bgas prices?\b|\bsilver price\b|\bcrude oil\b|\bwti\b|\bbrent\b|\bmarket cap\b|\bup or down\b|\b(?:hit|reach) (?:\((?:high|low)\) )?\$", re.I), CONTEXT_MARKET_PRICES),
    # Kalshi price tickers. The API tape carries the raw ticker as title
    # (KXBTC15M-26AUG16-1345, KXETHD-…, KXWTI15M-…, KXINXD-…) and "\bbtc\b"
    # cannot see "btc" inside "KXBTC15M". Every KX…15M ticker is a 15-minute
    # price up/down market; the prefix set is explicit otherwise so
    # KXETHIOPIA-… does not turn into an Ethereum market.
    (re.compile(r"\bkx[a-z0-9]{1,12}15m(?=-|\b)|\bkx(?:btc|eth|sol|xrp|doge|bnb|inx|nasdaq100|wti|gold|silver)(?:15m|d|h|w|m|y|maxy?|miny?)?(?=-|\b)", re.I), CONTEXT_MARKET_PRICES),
    # Kalshi sports and weather series carry the same problem: the API tape
    # sees "KXWNBAGAME-26AUG16-…" or "KXHIGHTHOU-…" as the title, and "\bwnba\b"
    # cannot fire inside a ticker. Series names are league/format words glued
    # together, so match the known league prefixes and the GAME/MATCH/SET/MAP
    # suffix families for sports, and the HIGH/LOW/TEMP/RAIN/SNOW families for
    # weather. Both stay excluded from the insider screen for the same reason
    # as their Polymarket counterparts.
    (re.compile(r"\bkx(?:atp|wta|mlb|nba|wnba|nfl|nhl|ufc|mma|pga|lpga|f1|nascar|mls|epl|ucl|laliga|bundesliga|seriea|ligue1|valorant|cs2|csgo|lol|dota|tennis|golf|soccer|ncaa[a-z]*|mve[a-z]*|itf[a-z]*|[a-z0-9]*(?:game|match|set|map|series|round|race|fight))(?:[a-z0-9]*)?(?=-|\b)", re.I), CONTEXT_SPORTS),
    (re.compile(r"\bkx(?:high|low|temp|rain|snow|wind|hurr|precip|heat)[a-z0-9]*(?=-|\b)", re.I), CONTEXT_WEATHER),
    (re.compile(r"\bceasefire\b|\bsanctions?\b|\btariffs?\b|\btreaty\b|\bagreement\b|\bexecutive order\b|\bmilitary\b|(?<!-)\bstrikes?\b|\binvasion\b|\bnato\b|\bsummit\b|\belections?\b|\bpresident\b|\bminister\b|\bparliament\b|\bcongress\b|\bsenate\b|\bimpeach|\bputin\b|\bzelensky?y?\b|\bnetanyahu\b|\bxi jinping\b|\bkim jong\b", re.I), CONTEXT_POLITICS),
    # Spieltag-Untermaerkte ohne Kontexttitel. "Will FC Thun win on
    # 2026-08-06?" traegt kein Liga- oder Vereinswort, das der Katalog oben
    # kennt, und rutschte deshalb als "General" in den Insider-Screen. Diese
    # Regel steht bewusst hinter Politik und Konzernen: "Will the president
    # win on ..." soll weiterhin Politik bleiben, nicht Sport.
    (re.compile(r"\bfc\b|\bwin on \d{4}-\d{2}-\d{2}\b|\bwin their match\b|\bto lift the\b|^parlay · \d+ legs:", re.I), CONTEXT_SPORTS),
    (re.compile(r"\bvs\.?\b", re.I), CONTEXT_SPORTS),
)


def classify_insider_context(title: Any, category: Any = "", context_text: Any = "") -> tuple[str, float, str]:
    """Map a market to an insider-plausibility group: (group, multiplier, note).

    Title keywords win over the coarse category field so that e.g. a "CEO
    resigns" market filed under Business stays insider-prone while a generic
    sports matchup is damped even when the category is missing.
    ``context_text`` (e.g. the parent event title — "Mexico vs. South Africa")
    is scanned with the same title patterns: sub-market titles like
    "Will Mexico win on 2026-06-11?" carry no sports keyword themselves.
    """

    title_text = f"{str(title or '')} {str(context_text or '')}".strip()
    for pattern, group in _TITLE_PATTERNS:
        if pattern.search(title_text):
            return group, CONTEXT_MULTIPLIERS[group], CONTEXT_NOTES[group]
    category_text = str(category or "").strip().lower()
    if category_text:
        for keys, group in _CATEGORY_GROUPS:
            if any(key in category_text for key in keys):
                return group, CONTEXT_MULTIPLIERS[group], CONTEXT_NOTES[group]
    return CONTEXT_GENERAL, CONTEXT_MULTIPLIERS[CONTEXT_GENERAL], CONTEXT_NOTES[CONTEXT_GENERAL]


def _category_context_maps(market_categories: pd.DataFrame | None) -> tuple[dict[str, str], dict[str, str]]:
    """Build market_key -> category and market_key -> context_text lookups."""

    if market_categories is None or market_categories.empty or not {"market_key", "category"}.issubset(market_categories.columns):
        return {}, {}
    keys = market_categories["market_key"].astype(str)
    category_map = dict(zip(keys, market_categories["category"].fillna("").astype(str)))
    context_map: dict[str, str] = {}
    if "context_text" in market_categories.columns:
        context_map = dict(zip(keys, market_categories["context_text"].fillna("").astype(str)))
    return category_map, context_map


_KALSHI_TICKER_RE = re.compile(r"^KX[A-Z0-9]+(?:-[A-Z0-9.]+)+$", re.I)


def _keys_with_ticker(frame: pd.DataFrame) -> pd.Series:
    """market_key per row, or the Kalshi ticker where the key is empty —
    Kalshi prints carry no market_key, the ticker is their key."""

    keys = frame.get("market_key", pd.Series("", index=frame.index)).fillna("").astype(str)
    if "ticker" in frame.columns:
        ticker = frame["ticker"].fillna("").astype(str)
        keys = keys.where(keys.str.strip().ne("") & keys.str.lower().ne("nan"), ticker)
    return keys


def _row_key(row: Any) -> str:
    """market_key of one row, or its Kalshi ticker when the key is missing
    or NaN (a frame with both kinds of rows has NaN in the other column)."""

    for field in ("market_key", "ticker"):
        value = row.get(field, "") if hasattr(row, "get") else ""
        text = "" if value is None else str(value).strip()
        if text and text.lower() != "nan":
            return text
    return ""


def _context_with_ticker(key: Any, context_map: dict[str, str]) -> str:
    """Context text for a market key: the parent-event text, plus the key
    itself when it is a Kalshi ticker.

    The tape used to carry the Kalshi ticker as the title, and the KX…
    patterns above read it there. Now the title is the market's question
    ("Silver price up in next 15 mins?") and the ticker lives only in
    market_key — so the ticker rides along as context, and KXSILVER15M still
    says "market price", KXHIGHMIA still says "weather", whatever the
    question's wording.
    """

    key_text = str(key or "")
    extra = context_map.get(key_text, "")
    if _KALSHI_TICKER_RE.match(key_text):
        return f"{extra} {key_text}".strip()
    return extra


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

    columns = ["platform", "title", "fresh_wallets", "fresh_outcome", "fresh_notional"]
    if trades is None or trades.empty or "wallet" not in trades or "title" not in trades:
        return pd.DataFrame(columns=columns)
    df = trades.copy()
    df["wallet"] = df["wallet"].astype(str).str.lower().str.strip()
    df = df[df["wallet"].ne("") & df["wallet"].ne("nan")]
    if df.empty:
        return pd.DataFrame(columns=columns)
    # Clusters are wallet evidence — they must stay on the venue that produced
    # them. event_risk rows are keyed (platform, title); merging on title alone
    # would let a Polymarket cluster inflate a same-titled Kalshi row.
    df["platform"] = df.get("platform", pd.Series("", index=df.index)).fillna("").astype(str)
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
        fresh.groupby(["platform", "title", "outcome_label"], dropna=False)
        .agg(fresh_wallets=("wallet", "nunique"), fresh_notional=("notional", "sum"))
        .reset_index()
    )
    grouped = grouped.sort_values(["fresh_wallets", "fresh_notional"], ascending=False)
    best = grouped.drop_duplicates(subset=["platform", "title"], keep="first").rename(columns={"outcome_label": "fresh_outcome"})
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
    merge_keys = ["platform", "title"] if "platform" in enriched.columns and "platform" in clusters.columns else ["title"]
    enriched = enriched.merge(clusters.drop(columns=[c for c in ("platform",) if c not in merge_keys and c in clusters.columns]), on=merge_keys, how="left")
    enriched["fresh_wallets"] = pd.to_numeric(enriched.get("fresh_wallets"), errors="coerce").fillna(0).astype(int)
    has_cluster = enriched["fresh_wallets"] >= 2
    bonus = (enriched["fresh_wallets"].clip(upper=4) * (max_bonus / 4.0)).where(has_cluster, 0.0)
    enriched["component_fresh_wallets"] = bonus.round(1)
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


def filter_insider_prone_trades(
    trades: pd.DataFrame,
    market_categories: pd.DataFrame | None = None,
    excluded: tuple[str, ...] = EXCLUDED_CONTEXTS,
) -> pd.DataFrame:
    """Drop trades whose market classifies into an excluded context group.

    This is the single entry gate of the risk screen: run it over the tape
    BEFORE scoring, and sports, weather and crypto/market-price prints never
    reach events, wallets, fresh-wallet or timing clusters or the co-trading
    network. (The network needs it doubly: the crypto up/down markets are the
    busiest on the venue, so dozens of wallets touch the same handful of
    markets within minutes as a matter of course and produced the largest
    cluster on the screen purely by volume.)
    """

    if trades is None or trades.empty or "title" not in trades.columns:
        return trades if trades is not None else pd.DataFrame()
    category_map, context_map = _category_context_maps(market_categories)
    keys = _keys_with_ticker(trades)
    cache: dict[tuple[str, str, str], str] = {}
    groups = [
        cache.setdefault(
            (title, category_map.get(key, ""), _context_with_ticker(key, context_map)),
            classify_insider_context(title, category_map.get(key, ""), _context_with_ticker(key, context_map))[0],
        )
        for title, key in zip(trades["title"].astype(str), keys)
    ]
    mask = [group not in excluded for group in groups]
    return trades[pd.Series(mask, index=trades.index)].reset_index(drop=True)


def exclude_contexts(frame: pd.DataFrame, excluded: tuple[str, ...] = EXCLUDED_CONTEXTS) -> pd.DataFrame:
    """Drop scored rows (events or wallets) whose ``insider_context`` is excluded.

    Second gate for callers that score the full tape first and attach the
    context afterwards (``apply_category_context`` /
    ``apply_wallet_category_context``): the same tuple as
    ``filter_insider_prone_trades`` so the two never disagree.
    """

    if frame is None or frame.empty or "insider_context" not in frame.columns:
        return frame
    return frame[~frame["insider_context"].isin(excluded)].reset_index(drop=True)


def dominant_context_map(trades: pd.DataFrame, market_categories: pd.DataFrame | None = None) -> dict[str, str]:
    """Map wallet (lowercase) -> dominant insider-context group of its flow, weighted by notional."""

    if trades is None or trades.empty or not {"wallet", "title"}.issubset(trades.columns):
        return {}
    df = trades.copy()
    df["wallet"] = df["wallet"].astype(str).str.lower().str.strip()
    df = df[df["wallet"].ne("") & df["wallet"].ne("nan")]
    if df.empty:
        return {}
    category_map, context_map = _category_context_maps(market_categories)
    title_groups: dict[tuple[str, str, str], str] = {}
    keys = _keys_with_ticker(df)
    df["_group"] = [
        title_groups.setdefault(
            (title, category_map.get(key, ""), _context_with_ticker(key, context_map)),
            classify_insider_context(title, category_map.get(key, ""), _context_with_ticker(key, context_map))[0],
        )
        for title, key in zip(df["title"].astype(str), keys)
    ]
    df["_notional"] = numeric_col(df, "notional").clip(lower=0.0)
    weighted = df.groupby(["wallet", "_group"])["_notional"].sum().reset_index()
    dominant = weighted.sort_values("_notional", ascending=False).drop_duplicates(subset=["wallet"], keep="first")
    return dict(zip(dominant["wallet"], dominant["_group"]))


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

    columns = ["platform", "title", "coordinated_wallets", "coordinated_outcome", "coordinated_span_minutes", "coordinated_notional"]
    if trades is None or trades.empty or not {"wallet", "title", "time"}.issubset(trades.columns):
        return pd.DataFrame(columns=columns)
    df = trades.copy()
    df["wallet"] = df["wallet"].astype(str).str.lower().str.strip()
    df = df[df["wallet"].ne("") & df["wallet"].ne("nan")]
    df["time"] = pd.to_datetime(df["time"], utc=True, errors="coerce")
    df = df.dropna(subset=["time"])
    if df.empty:
        return pd.DataFrame(columns=columns)
    df["platform"] = df.get("platform", pd.Series("", index=df.index)).fillna("").astype(str)
    df["outcome_label"] = df.get("outcome", pd.Series("", index=df.index)).astype(str).str.upper().str.strip()
    df["notional"] = numeric_col(df, "notional")
    window = pd.Timedelta(minutes=float(window_minutes))
    rows: list[dict[str, Any]] = []
    for (platform, title, outcome), group in df.groupby(["platform", "title", "outcome_label"], dropna=False):
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
                    "platform": str(platform),
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
    return result.drop_duplicates(subset=["platform", "title"], keep="first").reset_index(drop=True)


def apply_coordination_bonus(event_risk: pd.DataFrame, clusters: pd.DataFrame, max_bonus: float = 10.0) -> pd.DataFrame:
    """Bump event scores where several wallets hit the same side within minutes."""

    if event_risk is None or event_risk.empty or clusters is None or clusters.empty:
        return event_risk
    merge_keys = ["platform", "title"] if "platform" in event_risk.columns and "platform" in clusters.columns else ["title"]
    enriched = event_risk.merge(clusters.drop(columns=[c for c in ("platform",) if c not in merge_keys and c in clusters.columns]), on=merge_keys, how="left")
    enriched["coordinated_wallets"] = pd.to_numeric(enriched.get("coordinated_wallets"), errors="coerce").fillna(0).astype(int)
    has_cluster = enriched["coordinated_wallets"] >= 3
    bonus = (enriched["coordinated_wallets"].clip(upper=5) * (max_bonus / 5.0)).where(has_cluster, 0.0)
    # The base event score already pays for the same timing artifact via
    # cluster_score (+10, flag "multi-wallet burst") and burst_score — halve
    # this bonus where that flag is present to avoid triple-counting one burst.
    if "event_insider_flags" in enriched.columns:
        already_bursty = enriched["event_insider_flags"].fillna("").astype(str).str.contains("multi-wallet burst")
        bonus = bonus.where(~already_bursty, bonus / 2.0)
    enriched["component_coordination"] = bonus.round(1)
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
    min_pair_notional: float = 0.0,
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
        if len(markets) >= int(min_shared) and pair_notional.get((a, b), 0.0) >= float(min_pair_notional)
    ]
    if not edge_rows:
        return empty
    edges = pd.DataFrame(edge_rows, columns=edge_columns)

    members: list[set[str]]
    if nx is not None:
        graph = nx.Graph()
        for row in edge_rows:
            # Dollar-weighted edges: strong-money pairs bind communities tighter
            # than weak-money pairs (falls back to shared-market count if $0).
            graph.add_edge(row["wallet_a"], row["wallet_b"], weight=float(row["pair_notional"]) or float(row["shared_markets"]))
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


def network_modularity(nodes: pd.DataFrame, edges: pd.DataFrame) -> float | None:
    """Weighted modularity of the detected partition (>0.3 ≈ meaningful structure)."""

    if nx is None or nodes is None or nodes.empty or edges is None or edges.empty:
        return None
    graph = nx.Graph()
    for _, edge in edges.iterrows():
        graph.add_edge(edge["wallet_a"], edge["wallet_b"], weight=float(edge["pair_notional"]) or float(edge["shared_markets"]))
    communities: dict[Any, set[str]] = {}
    for _, node in nodes.iterrows():
        communities.setdefault(node["cluster_id"], set()).add(node["wallet"])
    partition = [members for members in communities.values() if members]
    covered = set().union(*partition) if partition else set()
    for orphan in set(graph.nodes) - covered:
        partition.append({orphan})
    try:
        return float(nx.community.modularity(graph, partition, weight="weight"))
    except Exception:
        return None


def cluster_layout(nodes: pd.DataFrame) -> pd.DataFrame:
    """Organic island layout: cluster centers on a golden-angle spiral, members on
    a ring around each center with deterministic radial jitter.

    Bigger clusters get bigger rings; the spiral keeps islands from overlapping
    without needing a force simulation, and everything is reproducible (no RNG).
    """

    if nodes is None or nodes.empty:
        return nodes
    placed = nodes.copy()
    placed["x"] = 0.0
    placed["y"] = 0.0
    sizes = placed.groupby("cluster_id")["wallet"].size().sort_values(ascending=False)
    cluster_ids = list(sizes.index)
    golden_angle = math.pi * (3.0 - math.sqrt(5.0))
    ring_radius = {cid: 1.4 + 0.55 * math.sqrt(int(sizes[cid])) for cid in cluster_ids}
    centers: dict[Any, tuple[float, float]] = {}
    spread = 0.0
    for index, cluster_id in enumerate(cluster_ids):
        if index == 0:
            centers[cluster_id] = (0.0, 0.0)
            spread = ring_radius[cluster_id]
            continue
        angle = index * golden_angle
        distance = spread + ring_radius[cluster_id] + 2.5 + 1.1 * math.sqrt(index)
        centers[cluster_id] = (distance * math.cos(angle), distance * math.sin(angle))
        spread = max(spread, 0.55 * distance)
    for cluster_id in cluster_ids:
        center_x, center_y = centers[cluster_id]
        member_index = placed.index[placed["cluster_id"] == cluster_id]
        count = len(member_index)
        radius = ring_radius[cluster_id]
        for position, node_idx in enumerate(member_index):
            angle = (2 * math.pi * position) / max(count, 1)
            wallet = str(placed.at[node_idx, "wallet"])
            jitter = 0.82 + 0.36 * ((hash(wallet) % 1000) / 1000.0)
            placed.at[node_idx, "x"] = center_x + radius * jitter * math.cos(angle)
            placed.at[node_idx, "y"] = center_y + radius * jitter * math.sin(angle)
    return placed


def cluster_story(
    cluster_nodes: pd.DataFrame,
    cluster_edges: pd.DataFrame,
    trades: pd.DataFrame,
    *,
    window_minutes: float | None = 5.0,
    min_shared: int = 2,
) -> dict[str, Any]:
    """Plain-language explanation of one cluster: what it is, why it clusters, how to read it.

    Returns {headline, pattern, reasons (list[str]), top_markets (list[str]), density}.
    """

    if cluster_nodes is None or cluster_nodes.empty:
        return {"headline": "", "pattern": "", "reasons": [], "top_markets": [], "density": 0.0}
    count = int(len(cluster_nodes))
    volume = float(numeric_col(cluster_nodes, "volume").sum())
    edge_count = int(len(cluster_edges)) if cluster_edges is not None else 0
    possible_edges = count * (count - 1) / 2 or 1
    density = edge_count / possible_edges
    shared_avg = float(numeric_col(cluster_edges, "shared_markets").mean()) if cluster_edges is not None and not cluster_edges.empty else 0.0
    shared_max = float(numeric_col(cluster_edges, "shared_markets").max()) if cluster_edges is not None and not cluster_edges.empty else 0.0

    members = set(cluster_nodes["wallet"].astype(str))
    top_markets: list[str] = []
    distinct_markets = 0
    if trades is not None and not trades.empty and {"wallet", "title"}.issubset(trades.columns):
        flow = trades.copy()
        flow["_wallet_key"] = flow["wallet"].astype(str).str.lower().str.strip()
        flow = flow[flow["_wallet_key"].isin(members)]
        if not flow.empty:
            flow["notional"] = numeric_col(flow, "notional")
            distinct_markets = int(flow["title"].nunique())
            top = flow.groupby("title")["notional"].sum().sort_values(ascending=False).head(3)
            top_markets = [f"{str(title)[:70]} ({money(value)})" for title, value in top.items()]

    window_text = f"within {window_minutes:.0f} minutes of each other" if window_minutes else "in the sampled tape"
    reasons = [
        f"Every line connects two wallets that bought the same side of at least {int(min_shared)} shared markets {window_text} — "
        f"on average {shared_avg:.1f} shared markets per linked pair (max {shared_max:.0f}).",
    ]
    if density >= 0.5:
        pattern = "Tight clique"
        reasons.append(
            f"{edge_count} of {possible_edges:.0f} possible pairs are linked ({density:.0%} density): the same wallets move together "
            "again and again — the strongest coordination pattern (syndicate-like or one operator splitting orders)."
        )
    elif density >= 0.15:
        pattern = "Connected group"
        reasons.append(
            f"{edge_count} links across {count} wallets ({density:.0%} density): a core of wallets co-moves repeatedly while others "
            "attach loosely — consistent with a coordinated core plus followers."
        )
    else:
        pattern = "Loose chain"
        reasons.append(
            f"Only {edge_count} links across {count} wallets ({density:.0%} density): wallets are chained through a few common trades — "
            "this can be herd behavior around hot markets rather than real coordination. Weakest evidence tier."
        )
    if distinct_markets:
        reasons.append(
            f"The flow concentrates in {distinct_markets} distinct markets; the heaviest shared bets are listed below — "
            "the narrower and more obscure these markets, the harder the pattern is to explain as coincidence."
        )
    headline = f"{count} wallets · {money(volume)} combined whale volume · {pattern.lower()}"
    return {"headline": headline, "pattern": pattern, "reasons": reasons, "top_markets": top_markets, "density": density}


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
    category_map, context_map = _category_context_maps(market_categories)
    contexts = [
        classify_insider_context(
            row.get("title", ""),
            category_map.get(str(row.get("market_key", "")), ""),
            _context_with_ticker(_row_key(row), context_map),
        )
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
    damped here and then dropped by ``exclude_contexts`` (high roller, not
    insider); flow concentrated in insider-prone categories keeps or gains
    weight. Adds insider_context (dominant group), context_multiplier
    (weighted) and wallet_score_raw.
    """

    if wallet_risk is None or wallet_risk.empty or trades is None or trades.empty:
        return wallet_risk
    df = trades.copy()
    df["wallet"] = df["wallet"].astype(str).str.lower().str.strip()
    df = df[df["wallet"].ne("") & df["wallet"].ne("nan")]
    if df.empty:
        return wallet_risk
    category_map, context_map = _category_context_maps(market_categories)
    contexts = [
        classify_insider_context(
            row.get("title", ""),
            category_map.get(str(row.get("market_key", "")), ""),
            _context_with_ticker(_row_key(row), context_map),
        )
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


#: Unter so vielen gesampelten Prints sind Verteilungs-Aussagen (Konzentration,
#: Einseitigkeit, Anteile) trivial -- ein einzelner Trade ist immer "100%".
EVENT_MIN_DISTRIBUTION_PRINTS = 3


def event_story(row: pd.Series) -> str:
    """One-line plain-language summary of why an event looks suspicious."""

    notional = float(row.get("notional", 0.0) or 0.0)
    wallets = int(row.get("unique_wallets", 0) or 0)
    trades = int(row.get("trades", 0) or 0)
    sample_ok = trades >= EVENT_MIN_DISTRIBUTION_PRINTS
    parts: list[str] = []
    long_odds_share = float(row.get("long_odds_share", 0.0) or 0.0)
    if long_odds_share >= 0.4:
        parts.append(
            f"{pct(long_odds_share)} of it at long odds" if sample_ok else "placed at long odds"
        )
    late_share = float(row.get("late_share", 0.0) or 0.0)
    if late_share >= 0.4:
        parts.append(
            "heavy flow close to resolution" if sample_ok else "placed close to resolution"
        )
    top_wallet_share = float(row.get("top_wallet_share", 0.0) or 0.0)
    if sample_ok and top_wallet_share >= 0.5:
        parts.append(f"one wallet drives {pct(top_wallet_share)}")
    fresh = int(row.get("fresh_wallets", 0) or 0)
    if fresh >= 2:
        outcome = str(row.get("fresh_outcome", "") or "").strip()
        parts.append(f"{fresh} fresh wallets on {outcome}" if outcome else f"{fresh} fresh wallets on the same side")
    direction_share = float(row.get("event_directional_share", 0.0) or 0.0)
    direction_label = str(row.get("event_directional_label", "") or "").strip()
    if sample_ok and direction_share >= 0.8 and direction_label:
        parts.append(f"{pct(direction_share)} of flow is {direction_label}")
    price_move = float(row.get("price_move", 0.0) or 0.0)
    if price_move >= 0.03:
        parts.append(f"price moved {price_move * 100:+.0f}c behind the buys")
    if not sample_ok and trades > 0:
        parts.append("too few sampled prints to judge the flow pattern")
    print_teil = (
        f"{trades} sampled print{'s' if trades != 1 else ''}" if trades > 0 else "sampled prints"
    )
    if wallets > 0:
        base = f"{money(notional)} whale flow from {wallets} wallet{'s' if wallets != 1 else ''} ({print_teil})"
    else:
        base = f"{money(notional)} whale flow ({print_teil}; wallet identities not public on this venue)"
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


# ---------------------------------------------------------------------------
# Flow details per event: which side, at what price, from whom, when.
#
# The base event score says "something is off here"; the owner reviewing a
# flag afterwards needs to know WHICH side the money went to, at what price,
# from which wallets and in which minutes — the market link and the price
# afterwards decide whether the flag meant anything. Everything below is a
# pure aggregation of the same trades frame the scores came from.
# ---------------------------------------------------------------------------

#: Order of the side buckets and their plain labels. "buys" of an outcome are
#: exposure to that outcome; sells are the taker leaving it.
SIDE_BUCKETS = (
    ("buy_yes", "YES buys"),
    ("buy_no", "NO buys"),
    ("sell_yes", "YES sells"),
    ("sell_no", "NO sells"),
)

#: Wallet placeholders of venues that publish no identities.
_NO_WALLET = {"", "nan", "none", "not public"}


def _side_bucket(side: Any, outcome: Any) -> str:
    """Map a print to buy_yes / buy_no / sell_yes / sell_no.

    Polymarket carries side BUY/SELL and outcome Yes/No. Kalshi carries the
    taker side (yes/no) as ``side`` and the same as ``outcome``: the taker
    took that outcome, i.e. bought it.
    """

    side_text = str(side or "").strip().upper()
    outcome_text = str(outcome or "").strip().upper()
    if outcome_text not in ("YES", "NO"):
        outcome_text = side_text if side_text in ("YES", "NO") else ""
    if not outcome_text:
        return ""
    verb = "sell" if side_text == "SELL" else "buy"
    return f"{verb}_{outcome_text.lower()}"


def _prep_flow_frame(trades: pd.DataFrame) -> pd.DataFrame:
    df = trades.copy()
    df["platform"] = df.get("platform", pd.Series("", index=df.index)).fillna("").astype(str)
    df["title"] = df.get("title", pd.Series("", index=df.index)).fillna("").astype(str)
    df = df[df["title"].str.strip().ne("")]
    if df.empty:
        return df
    df["_wallet"] = df.get("wallet", pd.Series("", index=df.index)).fillna("").astype(str).str.lower().str.strip()
    df.loc[df["_wallet"].isin(_NO_WALLET), "_wallet"] = ""
    df["_notional"] = numeric_col(df, "notional").clip(lower=0.0)
    df["_price"] = pd.to_numeric(df.get("price", pd.Series(dtype=float)), errors="coerce")
    df["_time"] = pd.to_datetime(df.get("time", pd.Series(pd.NaT, index=df.index)), utc=True, errors="coerce")
    sides = df.get("side", pd.Series("", index=df.index))
    outcomes = df.get("outcome", pd.Series("", index=df.index))
    df["_bucket"] = [_side_bucket(s, o) for s, o in zip(sides, outcomes)]
    df["_bucket_label"] = df["_bucket"].map(dict(SIDE_BUCKETS)).fillna("")
    return df


def event_flow_details(
    trades: pd.DataFrame,
    *,
    top_n: int = 3,
    fresh_max_trades: int = 2,
    whale_threshold: float | None = None,
) -> pd.DataFrame:
    """Per (platform, title): side split, dominant side, prices, window, top wallets, link.

    Columns: platform, title, side_buy_yes, side_buy_no, side_sell_yes,
    side_sell_no (notional per bucket), side (label of the dominant bucket,
    e.g. "NO buys"), side_notional, side_share, price_outcome (YES/NO — the
    outcome the prices refer to), price_first, price_last, price_min,
    price_max (over the dominant-side prints, in that outcome's price),
    first_print, last_print (UTC), window_minutes, top_wallets (list of
    {wallet, notional, share, side, fresh}), url, slug, token_id (asset of the
    latest dominant-side print, Polymarket only).

    ``fresh`` per wallet uses the same tape-relative proxy as
    :func:`fresh_wallet_clusters` (few prints in the whole tape, whale-sized
    total) and is only computed when ``whale_threshold`` is given; otherwise
    it is ``None`` — the payload says "not computed" rather than "no".
    """

    columns = [
        "platform", "title", "side_buy_yes", "side_buy_no", "side_sell_yes", "side_sell_no",
        "side", "side_notional", "side_share", "price_outcome", "price_first", "price_last",
        "price_min", "price_max", "first_print", "last_print", "window_minutes", "top_wallets",
        "url", "slug", "token_id",
    ]
    if trades is None or trades.empty or "title" not in trades.columns:
        return pd.DataFrame(columns=columns)
    df = _prep_flow_frame(trades)
    if df.empty:
        return pd.DataFrame(columns=columns)

    fresh_set: set[str] | None = None
    if whale_threshold is not None:
        with_wallet = df[df["_wallet"].ne("")]
        if not with_wallet.empty:
            per_wallet = with_wallet.groupby("_wallet").agg(n=("_wallet", "size"), total=("_notional", "sum"))
            fresh_set = set(per_wallet[(per_wallet["n"] <= int(fresh_max_trades)) & (per_wallet["total"] >= float(whale_threshold))].index)
        else:
            fresh_set = set()

    rows: list[dict[str, Any]] = []
    for (platform, title), group in df.groupby(["platform", "title"], dropna=False, sort=False):
        total = float(group["_notional"].sum())
        split = group.groupby("_bucket")["_notional"].sum()
        buckets = {key: float(split.get(key, 0.0)) for key, _ in SIDE_BUCKETS}
        dominant_key = ""
        dominant_value = 0.0
        for key, _ in SIDE_BUCKETS:
            if buckets[key] > dominant_value:
                dominant_key, dominant_value = key, buckets[key]
        side_label = dict(SIDE_BUCKETS).get(dominant_key, "")
        dominant = group[group["_bucket"].eq(dominant_key)] if dominant_key else group.iloc[0:0]
        priced = dominant[dominant["_price"].notna() & (dominant["_price"] > 0)].sort_values("_time")
        price_first = float(priced["_price"].iloc[0]) if not priced.empty else None
        price_last = float(priced["_price"].iloc[-1]) if not priced.empty else None
        price_min = float(priced["_price"].min()) if not priced.empty else None
        price_max = float(priced["_price"].max()) if not priced.empty else None
        price_outcome = dominant_key.split("_")[-1].upper() if dominant_key else ""

        times = group["_time"].dropna()
        first_print = times.min() if not times.empty else pd.NaT
        last_print = times.max() if not times.empty else pd.NaT
        window_minutes = float((last_print - first_print).total_seconds() / 60.0) if not times.empty else None

        top_wallets: list[dict[str, Any]] = []
        with_wallet = group[group["_wallet"].ne("")]
        if not with_wallet.empty:
            per_wallet = with_wallet.groupby("_wallet")["_notional"].sum().sort_values(ascending=False).head(int(top_n))
            for wallet, value in per_wallet.items():
                own = with_wallet[with_wallet["_wallet"].eq(wallet)]
                own_split = own.groupby("_bucket_label")["_notional"].sum().sort_values(ascending=False)
                own_side = str(own_split.index[0]) if not own_split.empty and str(own_split.index[0]) else ""
                top_wallets.append({
                    "wallet": str(wallet),
                    "notional": float(value),
                    "share": float(value / total) if total > 0 else 0.0,
                    "side": own_side,
                    "fresh": (wallet in fresh_set) if fresh_set is not None else None,
                })

        url = ""
        slug = ""
        if "url" in group.columns:
            urls = group["url"].dropna().astype(str)
            urls = urls[urls.str.strip().ne("") & urls.str.lower().ne("nan")]
            url = str(urls.iloc[0]) if not urls.empty else ""
        if "slug" in group.columns:
            slugs = group["slug"].dropna().astype(str)
            slugs = slugs[slugs.str.strip().ne("") & slugs.str.lower().ne("nan")]
            slug = str(slugs.iloc[0]) if not slugs.empty else ""
        token_id = ""
        if "asset" in dominant.columns and not dominant.empty:
            assets = dominant.sort_values("_time", ascending=False)["asset"].dropna().astype(str)
            assets = assets[assets.str.strip().ne("") & assets.str.lower().ne("nan")]
            token_id = str(assets.iloc[0]) if not assets.empty else ""

        rows.append({
            "platform": str(platform),
            "title": str(title),
            "side_buy_yes": buckets["buy_yes"],
            "side_buy_no": buckets["buy_no"],
            "side_sell_yes": buckets["sell_yes"],
            "side_sell_no": buckets["sell_no"],
            "side": side_label,
            "side_notional": dominant_value,
            "side_share": (dominant_value / total) if total > 0 else 0.0,
            "price_outcome": price_outcome,
            "price_first": price_first,
            "price_last": price_last,
            "price_min": price_min,
            "price_max": price_max,
            "first_print": first_print,
            "last_print": last_print,
            "window_minutes": window_minutes,
            "top_wallets": top_wallets,
            "url": url,
            "slug": slug,
            "token_id": token_id,
        })
    return pd.DataFrame(rows, columns=columns)


def enrich_event_flow(event_risk: pd.DataFrame, trades: pd.DataFrame, **kwargs: Any) -> pd.DataFrame:
    """Attach :func:`event_flow_details` to the scored event frame (by platform + title).

    The details win over same-named base columns (the base ``side_share`` is
    the BUY-vs-SELL share, the flow ``side_share`` the share of the dominant
    YES/NO bucket — the latter is what the card and the log mean by "side").
    Only ``url`` keeps the base value when the details carry none.
    """

    if event_risk is None or event_risk.empty:
        return event_risk
    details = event_flow_details(trades, **kwargs)
    if details.empty:
        return event_risk
    merge_keys = ["platform", "title"] if "platform" in event_risk.columns else ["title"]
    if "platform" not in event_risk.columns:
        details = details.drop(columns=["platform"])
    overlap = [c for c in details.columns if c in event_risk.columns and c not in merge_keys]
    enriched = event_risk.merge(details.rename(columns={c: f"{c}__flow" for c in overlap}), on=merge_keys, how="left")
    for column in overlap:
        flow_col = f"{column}__flow"
        base = enriched[column]
        flow = enriched[flow_col]
        if column == "url":
            base_empty = base.isna() | base.astype(str).str.strip().eq("") | base.astype(str).str.lower().eq("nan")
            enriched[column] = base.where(~base_empty, flow)
        else:
            enriched[column] = flow.where(flow.notna(), base)
        enriched = enriched.drop(columns=[flow_col])
    return enriched


#: Score components an event row can carry, with label and cap. The base
#: components come from ``whale_event_risk_scores`` (component_* columns),
#: the bonuses from apply_fresh_wallet_bonus / apply_coordination_bonus.
EVENT_COMPONENTS = (
    ("component_notional", "notional", 15.0),
    ("component_largest", "largest print", 10.0),
    ("component_long_odds", "long odds", 10.0),
    ("component_concentration", "top-wallet concentration", 15.0),
    ("component_direction", "one-sided flow", 10.0),
    ("component_burst", "burst", 15.0),
    ("component_late", "late flow", 15.0),
    ("price_move_score", "price move", 10.0),
    ("component_cluster", "multi-wallet burst", 10.0),
    ("component_fresh_wallets", "fresh-wallet cluster", 10.0),
    ("component_coordination", "timing cluster", 10.0),
)


def event_components(row: Any) -> list[dict[str, Any]]:
    """Labelled score components of one event row: [{key, label, value, max}].

    Only columns present on the row are listed (an older frame without the
    component columns yields an empty list, never invented zeros). The
    context multiplier is appended as its own entry when the row carries one.
    """

    getter = row.get if hasattr(row, "get") else (lambda key, default=None: default)
    parts: list[dict[str, Any]] = []
    for key, label, cap in EVENT_COMPONENTS:
        value = getter(key, None)
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if math.isnan(number):
            continue
        parts.append({"key": key, "label": label, "value": round(number, 1), "max": cap})
    multiplier = getter("context_multiplier", None)
    try:
        factor = float(multiplier)
    except (TypeError, ValueError):
        factor = None
    if factor is not None and not math.isnan(factor):
        parts.append({"key": "context_multiplier", "label": "context multiplier", "value": round(factor, 2), "max": None})
    return parts
