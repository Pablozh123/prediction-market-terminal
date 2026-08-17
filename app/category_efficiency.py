"""Category efficiency: how well each market category prices things ahead of time.

For every resolved binary Polymarket market the YES price is read at fixed
horizons before its decision time (30, 14, 7, 3 and 1 days by default) and
scored against the outcome: Brier score, hit rate, and a calibration table
of predicted probability against realised frequency. Grouped by category.

The category comes from the Gamma event tags first (Sports, Politics, Crypto,
Pop Culture, Business, Science, ...), then from the title/tag classifier the
live market screens use (``market_filter_category`` in
src/prediction_markets.py). Mentions markets ("Will X say Y ...") are split
out because they are the subject of their own study on the research page.

Network-free: scripts/category_efficiency.py fetches events and price series
through src/prediction_markets.py and hands the raw payloads to this module.
Nothing here invents a price — a market without a price at a horizon simply
does not count at that horizon, and every figure carries its sample size.
"""

from __future__ import annotations

import math
import re
import statistics
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

import pandas as pd

from app import base_rate_study as brs
from app import quant
from src import prediction_markets as pm

PROVENIENZ = "terminal/category_efficiency"

#: Days before the decision time at which the YES price is read.
DEFAULT_HORIZONS: tuple[int, ...] = (30, 14, 7, 3, 1)

#: Calibration bins over the predicted probability (T-7 by default).
DEFAULT_BIN_EDGES: tuple[float, ...] = (0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0)

#: Output buckets, in display order.
CATEGORIES: tuple[str, ...] = (
    "Politics",
    "Sports",
    "Crypto",
    "Pop culture",
    "Business/Finance",
    "Science/Tech",
    "Weather",
    "Mentions",
    "Other",
)
OTHER = "Other"

# Gamma event tags -> bucket, in two tiers. Specific tags (a league, a coin,
# "Fed Rates", "Oscars") are checked first, in this order; the broad section
# tags ("Politics", "Sports", "Business", ...) only decide when no specific
# tag did. So an FOMC event tagged Politics + Fed Rates counts as
# business/finance, while a Fed-chair nomination tagged Trump + Fed Rates
# counts as politics because Trump sits ahead of Fed Rates in the specific
# tier. Labels are matched case-insensitively.
_SPECIFIC_TAG_RULES: tuple[tuple[str, frozenset[str]], ...] = (
    ("Sports", frozenset({
        "soccer", "football", "nfl", "nba", "mlb", "nhl", "wnba", "ncaa", "college football",
        "college basketball", "tennis", "golf", "ufc", "mma", "boxing", "f1", "formula 1", "nascar",
        "cricket", "rugby", "esports", "chess", "olympics", "fifa world cup", "world cup", "ucl",
        "champions league", "premier league", "la liga", "serie a", "bundesliga", "mls", "super bowl",
        "nba finals", "world series", "stanley cup", "march madness", "hockey", "baseball", "basketball",
        "cycling", "darts", "snooker", "athletics", "swimming", "table tennis", "volleyball", "handball",
        "games",
    })),
    ("Crypto", frozenset({
        "crypto prices", "bitcoin", "btc", "ethereum", "eth", "solana", "sol", "xrp", "doge",
        "dogecoin", "memecoins", "stablecoins", "defi", "airdrops", "hyperliquid", "fdv",
        "altcoins", "nft", "nfts", "binance", "coinbase", "microstrategy",
    })),
    ("Mentions", frozenset({"mentions", "mention markets"})),
    ("Politics", frozenset({
        "us politics", "elections", "election", "world elections", "global elections",
        "geopolitics", "trump", "trump presidency", "congress", "senate", "supreme court",
        "scotus", "middle east", "iran", "israel", "ukraine", "russia", "china", "taiwan", "gaza",
        "ceasefire", "peace deal", "nato", "uk politics",
        "governor", "mayor", "primary", "primaries", "midterms", "2026 midterms", "cabinet", "executive order",
        "tariffs", "government shutdown", "impeachment", "polls", "approval rating", "white house",
    })),
    ("Pop culture", frozenset({
        "movies", "movie", "music", "tv", "television", "celebrities", "celebrity",
        "awards", "oscars", "academy awards", "grammys", "emmys", "golden globes", "tonys", "box office",
        "reality tv", "video games", "gaming", "rotten tomatoes", "streaming", "netflix", "spotify",
        "billboard", "eurovision", "kardashians", "taylor swift", "drake", "kanye", "youtube", "tiktok",
        "twitch", "mrbeast", "anime", "comics", "marvel", "star wars", "wwe", "podcasts",
    })),
    ("Business/Finance", frozenset({
        "economic policy", "fed", "fed rates", "fomc",
        "interest rates", "rates", "inflation", "cpi", "gdp", "jobs report", "unemployment", "stocks",
        "stock market", "s&p 500", "spx", "nasdaq", "dow", "indices", "indicies", "earnings", "ipo", "companies", "tesla", "apple",
        "nvidia", "openai valuation", "macro", "commodities", "oil", "gold", "silver", "treasury", "bonds",
        "recession", "trade", "trade deal", "mergers", "m&a", "bankruptcy", "layoffs", "ceo", "startups",
    })),
    ("Science/Tech", frozenset({
        "ai", "artificial intelligence", "openai", "chatgpt", "gpt",
        "anthropic", "google", "gemini", "grok", "xai", "llm", "space", "spacex", "starship", "nasa",
        "moon", "mars", "rocket", "health", "medicine", "vaccine", "pandemic", "pandemics",
        "covid", "fda", "climate", "energy", "nuclear", "quantum", "robots", "robotics", "self-driving",
        "tesla robotaxi", "apple event", "iphone", "software", "cybersecurity",
    })),
    ("Weather", frozenset({"temperature", "hurricane", "hurricanes", "climate & weather", "rain", "snow"})),
)
_GENERIC_TAG_RULES: tuple[tuple[str, frozenset[str]], ...] = (
    ("Sports", frozenset({"sports"})),
    ("Crypto", frozenset({"crypto"})),
    ("Politics", frozenset({"politics", "world"})),
    ("Pop culture", frozenset({"pop culture", "culture"})),
    ("Business/Finance", frozenset({"business", "finance", "economy", "economics"})),
    ("Science/Tech", frozenset({"science", "tech", "technology"})),
    ("Weather", frozenset({"weather"})),
)
_TAG_RULES: tuple[tuple[str, frozenset[str]], ...] = _SPECIFIC_TAG_RULES + _GENERIC_TAG_RULES

# Tags Gamma attaches for its own UI, never a category signal.
_IGNORED_TAGS = frozenset({
    "all", "featured", "new", "trending", "recurring", "monthly", "weekly", "daily", "yearly",
    "hide from new", "parent for derivative", "pre-market", "2025 predictions", "2026 predictions",
    "best of 2025", "best of 2026", "hfc", "main election", "macro election 2", "breaking news",
})

_MENTION_RE = re.compile(r"\bsay\b.*?[\"“'‘]|\bmention(s|ed)?\b|\bwill .* say\b", re.IGNORECASE)

# What the live classifier answers -> our bucket. It never says pop culture,
# science or business/finance, hence the tag pass first.
_FILTER_TO_BUCKET = {
    "sports": "Sports",
    "crypto": "Crypto",
    "politics": "Politics",
    "weather": "Weather",
    "finance": "Business/Finance",
    "economy": "Business/Finance",
    "business": "Business/Finance",
    "pop culture": "Pop culture",
    "culture": "Pop culture",
    "science": "Science/Tech",
    "tech": "Science/Tech",
    "mentions": "Mentions",
}


def _tag_labels(tags: Iterable[Any] | None) -> list[str]:
    labels: list[str] = []
    for tag in tags or []:
        if isinstance(tag, Mapping):
            label = tag.get("label") or tag.get("slug") or ""
        else:
            label = tag
        text = str(label or "").strip().lower()
        if text and text not in _IGNORED_TAGS:
            labels.append(text)
    return labels


def is_mentions_market(title: Any) -> bool:
    """"Will Trump say 'tariff' during the address?" and friends."""

    text = str(title or "")
    return bool(_MENTION_RE.search(text))


def classify_category(title: Any, tags: Iterable[Any] | None = None, raw_category: Any = "") -> str:
    """One of ``CATEGORIES`` for a market, from its title, event tags and raw category.

    Order: mentions by title pattern (they sit inside politics or business
    events), then the specific event tags, then the broad section tags (see
    ``_TAG_RULES``), then the live classifier ``market_filter_category`` on
    raw category plus title, else ``Other``.
    """

    if is_mentions_market(title):
        return "Mentions"
    labels = _tag_labels(tags)
    for bucket, words in _TAG_RULES:
        if any(label in words for label in labels):
            return bucket
    live = str(pm.market_filter_category(raw_category, title) or "").strip().lower()
    return _FILTER_TO_BUCKET.get(live, OTHER)


def _settled_outcome(raw: Mapping[str, Any]) -> bool | None:
    """True/False when ``outcomePrices`` say Yes won/lost exactly, else None.

    Same rule as app.base_rate_study.event_lines: Polymarket writes "1" to the
    winner and "0" to the loser once resolved; anything else (0.5/0.5 refunds,
    still-trading prices) is not a settled outcome and is dropped.
    """

    outcomes = [str(v).strip().lower() for v in pm._as_list(raw.get("outcomes"))]
    prices = pm._as_list(raw.get("outcomePrices"))
    if outcomes[:2] != ["yes", "no"] or len(prices) < 2:
        return None
    try:
        yes_price = float(prices[0])
        no_price = float(prices[1])
    except (TypeError, ValueError):
        return None
    if (yes_price, no_price) == (1.0, 0.0):
        return True
    if (yes_price, no_price) == (0.0, 1.0):
        return False
    return None


def decision_time(end_time: Any, closed_time: Any) -> pd.Timestamp | None:
    """The earlier of end date and close time: when the question was decided.

    A market that resolves early (a team eliminated, a deadline met) closes
    long before its nominal end date, so ``endDate`` alone would read the
    price after the answer was known. A market that runs its full course
    closes one to three days after its end date (the UMA window), so
    ``closedTime`` alone would do the same. The minimum is the latest moment
    at which the outcome was still open. None without either stamp.
    """

    stamps = [s for s in (pm._safe_ts(end_time), pm._safe_ts(closed_time)) if s is not None]
    return min(stamps) if stamps else None


def market_rows_from_event(event: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Resolved binary markets of one raw Gamma event, ready for pricing.

    Each row: market_key, question, event_slug, event_title, tags, category,
    yes_token_id, won, decision_time, created_at, volume. Markets without a
    settled Yes/No outcome, without a YES token or without a decision time
    are left out — none of them can be scored.
    """

    tags = list(event.get("tags") or []) if isinstance(event, Mapping) else []
    rows: list[dict[str, Any]] = []
    for market in pm.normalize_polymarket_event_markets(event):
        raw = market.get("raw") or {}
        if not raw.get("closed") and not market.get("closed"):
            continue
        won = _settled_outcome(raw)
        if won is None:
            continue
        token = market.get("yes_token_id")
        if not token:
            continue
        decided = decision_time(market.get("end_time"), market.get("closed_time"))
        if decided is None:
            continue
        title = str(market.get("title") or "")
        rows.append(
            {
                "market_key": str(market.get("market_key") or ""),
                "question": title,
                "event_slug": str(market.get("event_slug") or event.get("slug") or ""),
                "event_title": str(event.get("title") or ""),
                "tags": [str(t.get("label", "")) if isinstance(t, Mapping) else str(t) for t in tags],
                "category": classify_category(title, tags, market.get("category")),
                "yes_token_id": str(token),
                "won": bool(won),
                "decision_time": decided,
                "created_at": market.get("created_at") or market.get("start_time"),
                "volume": float(market.get("volume") or 0.0),
            }
        )
    return rows


def lifetime_days(row: Mapping[str, Any]) -> float | None:
    """Days between creation and decision time; None when either stamp is missing."""

    created = pm._safe_ts(row.get("created_at"))
    decided = pm._safe_ts(row.get("decision_time"))
    if created is None or decided is None:
        return None
    return float((decided - created).total_seconds()) / 86400.0


def sample_bucket(row: Mapping[str, Any], long_life_days: float) -> str:
    """Counting key for the per-category caps: ``<category>`` or ``<category>|short``.

    Markets that lived at least ``long_life_days`` can carry a T-7 price and
    fill the main cap; shorter-lived ones (a game created three days out, a
    daily price line) count only at the near horizons and get their own,
    smaller cap so they neither crowd out the long-lived sample nor vanish.
    """

    category = str(row.get("category") or OTHER)
    life = lifetime_days(row)
    if life is not None and life < float(long_life_days):
        return f"{category}|short"
    return category


def select_markets(
    rows: Iterable[Mapping[str, Any]],
    max_per_category: int,
    max_per_event: int,
    min_volume: float,
    taken: Mapping[str, int] | None = None,
    *,
    min_life_days: float = 1.0,
    long_life_days: float = 7.0,
    max_short_per_category: int | None = None,
) -> list[dict[str, Any]]:
    """Cap one event's markets per event and per category, highest volume first.

    ``taken`` is the running count per sample bucket across earlier events
    (see ``sample_bucket``); the caller carries it forward from the return
    value. The per-event cap keeps a 60-line "World Cup winner" event from
    filling the sports bucket with correlated long shots; the per-category
    caps bound the price fetch. Markets that lived less than
    ``min_life_days`` cannot have a price at any horizon and are skipped;
    ``max_short_per_category`` (default half the main cap) bounds the
    short-lived bucket.
    """

    taken = dict(taken or {})
    short_cap = int(max_short_per_category) if max_short_per_category is not None else max(1, int(max_per_category) // 2)
    ordered = sorted(rows, key=lambda r: float(r.get("volume") or 0.0), reverse=True)
    picked: list[dict[str, Any]] = []
    per_event = 0
    for row in ordered:
        if per_event >= max_per_event:
            break
        if float(row.get("volume") or 0.0) < float(min_volume):
            continue
        life = lifetime_days(row)
        if life is not None and life < float(min_life_days):
            continue
        bucket = sample_bucket(row, long_life_days)
        cap = short_cap if bucket.endswith("|short") else int(max_per_category)
        if taken.get(bucket, 0) >= cap:
            continue
        picked.append(dict(row))
        taken[bucket] = taken.get(bucket, 0) + 1
        per_event += 1
    return picked


def caps_reached(taken: Mapping[str, int], max_per_category: int, categories: Sequence[str] = CATEGORIES) -> bool:
    """True once every named category (Other excluded) holds ``max_per_category`` long-lived markets."""

    return all(int(taken.get(c, 0)) >= int(max_per_category) for c in categories if c != OTHER)


def price_at_horizon(history: pd.DataFrame | None, decision: Any, days: float) -> float | None:
    """Last price at or before ``days`` days ahead of ``decision`` (None if unknown)."""

    return brs.price_at_lead_time(history, decision, float(days) * 24.0)


def horizon_prices(
    hourly: pd.DataFrame | None,
    daily: pd.DataFrame | None,
    decision: Any,
    horizons: Sequence[int],
) -> dict[int, float | None]:
    """YES price per horizon: hourly series first, daily whole-life series as fallback."""

    out: dict[int, float | None] = {}
    for days in horizons:
        price = price_at_horizon(hourly, decision, days)
        if price is None:
            price = price_at_horizon(daily, decision, days)
        out[int(days)] = price
    return out


def _brier(price: float, won: bool) -> float:
    return (float(price) - (1.0 if won else 0.0)) ** 2


def _hit(price: float, won: bool) -> bool:
    return (float(price) >= 0.5) == bool(won)


def _round(value: float | None, digits: int = 4) -> float | None:
    if value is None or (isinstance(value, float) and (math.isnan(value) or math.isinf(value))):
        return None
    return round(float(value), digits)


#: A YES price at or beyond these bounds means the market already treated
#: the question as settled; the share of such markets is reported next to
#: every Brier score because a bucket of 0.01 long shots scores near-perfect
#: without anyone having forecast anything.
DECIDED_BOUNDS = (0.05, 0.95)


def _priced(obs: Sequence[Mapping[str, Any]], days: int) -> list[tuple[float, bool]]:
    out: list[tuple[float, bool]] = []
    for o in obs:
        price = (o.get("prices") or {}).get(days)
        if price is None:
            price = (o.get("prices") or {}).get(str(days))
        if price is not None:
            out.append((float(price), bool(o["won"])))
    return out


def _horizon_stats(obs: Sequence[Mapping[str, Any]], days: int) -> dict[str, Any]:
    priced = _priced(obs, days)
    n = len(priced)
    if not n:
        return {"horizont_tage": int(days), "brier": None, "trefferquote": None, "n": 0,
                "anteil_entschieden": None}
    brier = sum(_brier(p, w) for p, w in priced) / n
    hits = sum(1 for p, w in priced if _hit(p, w))
    low, high = quant.wilson_interval(hits, n)
    decided = sum(1 for p, _ in priced if p <= DECIDED_BOUNDS[0] or p >= DECIDED_BOUNDS[1])
    return {
        "horizont_tage": int(days),
        "brier": _round(brier),
        "trefferquote": _round(hits / n),
        "trefferquote_ci95": [_round(low), _round(high)],
        "n": n,
        "anteil_entschieden": _round(decided / n),
    }


def calibration_bins(
    obs: Sequence[Mapping[str, Any]], days: int = 7, edges: Sequence[float] = DEFAULT_BIN_EDGES
) -> list[dict[str, Any]]:
    """Predicted (mean price) vs realised (share won) per probability bin, with n.

    Bins are left-closed, the last one closed on both ends. Empty bins are
    omitted rather than shown as zero — a bin nobody priced in has no
    realised frequency.
    """

    rows: list[dict[str, Any]] = []
    priced = _priced(obs, days)
    for i in range(len(edges) - 1):
        lo, hi = float(edges[i]), float(edges[i + 1])
        last = i == len(edges) - 2
        members = [(p, w) for p, w in priced if (lo <= p < hi) or (last and p == hi)]
        if not members:
            continue
        n = len(members)
        wins = sum(1 for _, w in members if w)
        low, high = quant.wilson_interval(wins, n)
        rows.append(
            {
                "von": lo,
                "bis": hi,
                "vorhergesagt": _round(sum(p for p, _ in members) / n),
                "realisiert": _round(wins / n),
                "realisiert_ci95": [_round(low), _round(high)],
                "n": n,
            }
        )
    return rows


def category_table(
    obs: Sequence[Mapping[str, Any]],
    horizons: Sequence[int] = DEFAULT_HORIZONS,
    min_markets: int = 1,
    calibration_horizon: int = 7,
) -> list[dict[str, Any]]:
    """One row per category with the legacy keys plus ``horizonte`` and ``kalibrierung``.

    ``obs`` rows: ``{"category", "won", "volume", "prices": {days: price|None}}``.
    A market counts for a category when it has a price at at least one
    horizon; categories under ``min_markets`` are folded into ``Other`` so a
    three-market bucket cannot top the best/worst list. Legacy keys
    (``brier_t7`` etc.) are None when that horizon has no observation.
    """

    horizons = [int(h) for h in horizons]
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for o in obs:
        if not any(_priced([o], h) for h in horizons):
            continue
        grouped.setdefault(str(o.get("category") or OTHER), []).append(o)

    # Fold thin categories into Other before scoring.
    folded: dict[str, list[Mapping[str, Any]]] = {}
    for name, members in grouped.items():
        target = name if (len(members) >= int(min_markets) or name == OTHER) else OTHER
        folded.setdefault(target, []).extend(members)

    rows: list[dict[str, Any]] = []
    order = {name: i for i, name in enumerate(CATEGORIES)}
    for name in sorted(folded, key=lambda k: (order.get(k, len(order)), k)):
        members = folded[name]
        stats = {h: _horizon_stats(members, h) for h in horizons}
        volumes = [float(m.get("volume") or 0.0) for m in members]
        median_vol = statistics.median(volumes) if volumes else None
        t7 = stats.get(7, _horizon_stats(members, 7))
        t1 = stats.get(1, _horizon_stats(members, 1))
        rows.append(
            {
                "kategorie": name,
                "brier_t7": t7["brier"],
                "trefferquote_t7": t7["trefferquote"],
                "brier_t1": t1["brier"],
                "trefferquote_t1": t1["trefferquote"],
                "n_maerkte": len(members),
                "n_t7": t7["n"],
                "n_t1": t1["n"],
                "anteil_entschieden_t7": t7.get("anteil_entschieden"),
                "median_volumen_usd": _round(median_vol, 2),
                "horizonte": [stats[h] for h in horizons],
                "kalibrierung": {
                    "horizont_tage": int(calibration_horizon),
                    "bins": calibration_bins(members, calibration_horizon),
                },
            }
        )
    return rows


def compose_payload(
    kategorien: Sequence[Mapping[str, Any]],
    previous: Mapping[str, Any] | None,
    *,
    stand_utc: str,
    horizons: Sequence[int],
    quelle: Mapping[str, Any],
    hinweis: str,
) -> dict[str, Any]:
    """The published kategorie_karte.json: new table, thesis figures preserved.

    ``beispiele`` (the pricing-speed examples the mentions page reads) are
    copied unchanged from ``previous``. The old ``kategorien`` and ``hinweis``
    move to ``thesis_snapshot`` — once. A re-run that finds a snapshot already
    there keeps that snapshot instead of snapshotting its own output.
    """

    previous = dict(previous or {})
    snapshot = previous.get("thesis_snapshot")
    if not isinstance(snapshot, Mapping):
        snapshot = {
            "hinweis": previous.get("hinweis"),
            "stand_utc": previous.get("stand_utc"),
            "kategorien": list(previous.get("kategorien") or []),
        }
    return {
        "hinweis": str(hinweis),
        "stand_utc": str(stand_utc),
        "provenienz": PROVENIENZ,
        "horizonte_tage": [int(h) for h in horizons],
        "quelle": dict(quelle),
        "kategorien": [dict(k) for k in kategorien],
        "beispiele": list(previous.get("beispiele") or []),
        "thesis_snapshot": dict(snapshot),
    }


def sample_summary(kategorien: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Totals for the log line and the ``quelle`` block: markets and n per horizon."""

    total = sum(int(k.get("n_maerkte") or 0) for k in kategorien)
    per_horizon: dict[str, int] = {}
    for k in kategorien:
        for h in k.get("horizonte") or []:
            key = f"T-{int(h.get('horizont_tage', 0))}"
            per_horizon[key] = per_horizon.get(key, 0) + int(h.get("n") or 0)
    return {"n_maerkte": total, "n_kategorien": len(kategorien), "n_je_horizont": per_horizon}
