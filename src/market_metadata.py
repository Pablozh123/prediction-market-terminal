"""Shared market metadata helpers for the analysis scripts.

The project report needs stable, explainable output columns. Keeping this
logic in one place avoids small differences between bulk and detail runs.
"""

from __future__ import annotations

import re
from typing import Any

import pandas as pd


STOPWORDS = {
    "will", "would", "could", "should", "has", "have", "been", "the",
    "and", "are", "for", "was", "not", "with", "this", "that", "from",
    "its", "which", "when", "who", "how", "what", "why", "does", "did",
    "any", "all", "into", "over", "about", "than", "first", "there",
    "into", "onto", "under", "above", "below", "before", "after",
    "year", "end", "get", "per", "as", "at", "to", "in", "on", "by",
    "of", "a", "an", "or", "be", "is",
}

SHORT_CONTEXT_TOKENS = {
    "ai", "ar", "btc", "eth", "eu", "fbi", "fed", "fifa", "gdp", "gta",
    "ipo", "mlb", "nba", "nfl", "nhl", "uk", "un", "us", "vi", "who",
    "cup", "hit", "new", "no", "out", "san", "win",
}

NEGATIVE_QUESTION_WORDS = {
    "recession", "shutdown", "impeach", "invade", "invasion",
    "nuclear", "ban", "crash", "default", "hurricane", "attack",
    "sanction", "collapse", "convict", "indict", "conflict",
    "crisis", "fail", "war",
}

RELEVANT_KEYWORDS = [
    "trump", "fed", "rate", "tariff", "recession", "ukraine", "russia",
    "china", "taiwan", "election", "senate", "congress", "gdp", "inflation",
    "bitcoin", "crypto", "war", "trade", "stock", "nasdaq", "dollar",
    "gold", "oil", "iran", "nato", "ceasefire", "president", "democrat",
    "republican", "economy", "market", "bank", "debt", "deficit",
    "ethereum", "solana", "nvidia", "tesla", "openai", "regulation",
]

CATEGORY_KEYWORDS = {
    "Crypto": ["bitcoin", "btc", "crypto", "ethereum", "solana", "ether"],
    "Politics": [
        "trump", "biden", "election", "president", "democrat", "republican",
        "senate", "congress", "pardon", "impeach", "harris", "shutdown",
        "debt ceiling",
    ],
    "Geopolitics": [
        "ukraine", "russia", "china", "taiwan", "nato", "iran", "war",
        "ceasefire", "nuclear", "missile", "north korea", "military",
    ],
    "Sports": [
        "fifa", "world cup", "stanley", "hurricanes", "avalanche", "knights",
        "canadiens", "nba", "nfl", "finals", "thunder", "cavaliers", "knicks",
        "spurs", "england", "france", "brazil", "argentina", "germany",
        "portugal", "spain",
    ],
    "Legal": [
        "sentenced", "prison", "trial", "court", "convict", "indict",
        "harvey weinstein", "lawsuit",
    ],
    "Entertainment": [
        "rihanna", "album", "playboi", "carti", "gta", "film", "movie",
        "taylor", "swift",
    ],
    "Tech": [
        "openai", "ai ", "nvidia", "tesla", "apple", "google", "meta",
        "microsoft", "tech", "regulation", "software", "hardware", "model",
    ],
    "Economy": [
        "fed", "rate", "recession", "inflation", "gdp", "dollar", "nasdaq",
        "s&p", "gold", "oil", "stock", "economy", "tariff", "bank", "debt",
        "deficit",
    ],
    "Climate": ["climate", "paris", "temperature", "carbon", "emission", "hot year"],
    "Health": ["covid", "variant", "who", "drug", "weight-loss", "health"],
}


def _clean_value(value: Any, default: Any = "") -> Any:
    if value is None:
        return default
    try:
        if pd.isna(value):
            return default
    except (TypeError, ValueError):
        pass
    return value


def _remove_market_benchmarks(question: str) -> str:
    """Remove market-specific comparator phrases that hurt Reddit search.

    Polymarket sometimes phrases markets as "X before GTA VI". The benchmark is
    useful for resolving the market, but Reddit posts about X rarely contain the
    exact phrase "before GTA VI". If the market itself is about GTA VI, keep it.
    """
    text = str(question)
    if re.search(r"\bbefore\s+gta\s+vi\b", text, flags=re.IGNORECASE) and not re.match(
        r"\s*gta\s+vi\b", text, flags=re.IGNORECASE
    ):
        text = re.sub(r"\bbefore\s+gta\s+vi\b.*", "", text, flags=re.IGNORECASE).strip()
    return text


def extract_keywords(question: str, n: int = 8) -> str:
    """Extract a compact, recall-oriented Reddit search query.

    The query keeps entities, numbers/years and short acronyms (GTA, VI, US,
    FIFA), but removes generic question words and weak temporal connectors.
    """
    cleaned_question = _remove_market_benchmarks(str(question))
    tokens = re.findall(r"\$?\d+(?:\.\d+)?[A-Za-z]*|[A-Za-z]+", cleaned_question)
    keywords: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        normalized = token.strip("$")
        lower = normalized.lower()
        has_digit = any(char.isdigit() for char in normalized)
        is_short_context = lower in SHORT_CONTEXT_TOKENS
        if lower == "who" and normalized != "WHO":
            is_short_context = False
        if lower in STOPWORDS and not has_digit and not is_short_context:
            continue
        if len(normalized) < 4 and not has_digit and not is_short_context:
            continue
        if lower in seen:
            continue
        keywords.append(normalized)
        seen.add(lower)
        if len(keywords) >= n:
            break
    return " ".join(keywords) if keywords else cleaned_question[:50]


def question_polarity(question: str) -> int:
    """Return +1 for positive-framed and -1 for negative-framed questions."""
    words = set(re.findall(r"[a-z]+", str(question).lower()))
    return -1 if words & NEGATIVE_QUESTION_WORDS else +1


def infer_category(question: str) -> str:
    """Infer a stable category when the Polymarket API omits one."""
    question_lower = str(question).lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(keyword in question_lower for keyword in keywords):
            return category
    return "Other"


def normalize_category(question: str, category: Any) -> str:
    """Prefer an API category, otherwise use the keyword taxonomy."""
    clean_category = str(_clean_value(category, "")).strip()
    if clean_category and clean_category.lower() not in {"unknown", "none", "nan", "-"}:
        return clean_category
    return infer_category(question)


def filter_relevant_markets(df: pd.DataFrame, n: int) -> pd.DataFrame:
    """Keep relevant politics/economy/crypto/geopolitics markets first."""
    if df.empty:
        return df
    mask = df["question"].str.lower().apply(
        lambda q: any(keyword in set(re.findall(r"[a-z]+", q)) for keyword in RELEVANT_KEYWORDS)
    )
    relevant = df[mask]
    if len(relevant) >= n:
        return relevant.head(n)
    rest = df[~mask].head(n - len(relevant))
    return pd.concat([relevant, rest]).head(n)


def stable_market_fields(
    row: pd.Series,
    position: int,
    api_source: str,
    collected_at_utc: str,
) -> dict[str, Any]:
    """Return stable market columns used by all generated CSV outputs."""
    question = str(_clean_value(row.get("question"), ""))
    probability = _clean_value(row.get("probability"), None)
    try:
        probability = float(probability) if probability is not None else None
    except (TypeError, ValueError):
        probability = None

    market_id = _clean_value(row.get("id"), f"demo_{position:02d}")
    clob_token_id = _clean_value(row.get("clob_token_id"), "")

    return {
        "market_rank": position,
        "api_source": api_source,
        "is_demo_market": api_source == "demo_fallback",
        "collected_at_utc": collected_at_utc,
        "market_id": market_id,
        "clob_token_id": clob_token_id,
        "market_url": _clean_value(row.get("url"), ""),
        "question": question,
        "probability": probability,
        "category": normalize_category(question, row.get("category")),
        "volume": _clean_value(row.get("volume"), ""),
        "end_date": _clean_value(row.get("end_date"), ""),
    }
