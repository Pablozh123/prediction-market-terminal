"""Universe base rates: does a price band pay out at the rate it implies?

A single wallet's calibration only tells you about the lines that wallet chose.
To decide whether an apparent edge is a property of the *market* or of the
*trader's selection*, you have to price every line of an event, including the
ones nobody good touched.

This module does that for Polymarket events whose sub-markets share a template.
The motivating case is football "Exact Score" events: one event carries ~17
mutually exclusive scoreline markets, each a Yes/No pair, and the No side sits
in the 0.80-0.99 band. If the whole band were mispriced, every No line would pay
above its price. If only a picked subset does, the edge lives in the picking.

Streamlit-free and network-free: callers fetch the Gamma event payloads and the
CLOB price history, this module parses, buckets and scores them.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Iterable, Mapping, Sequence
from statistics import NormalDist
from typing import Any

import pandas as pd

from app import quant

# One observation = one line of one event, priced at a fixed lead time.
OBSERVATION_COLUMNS = [
    "event_slug",
    "market_key",
    "question",
    "token_id",
    "outcome",
    "price",
    "won",
    "end_time",
]

DEFAULT_PRICE_BUCKETS: tuple[float, ...] = (0.0, 0.5, 0.8, 0.9, 0.95, 1.0)


def event_slug_from_url(value: Any) -> str:
    """``https://polymarket.com/event/<slug>`` -> ``<slug>`` (empty when absent)."""

    match = re.search(r"/event/([^/?#]+)", str(value or ""))
    return match.group(1) if match else ""


def event_slugs_from_urls(urls: Iterable[Any]) -> list[str]:
    """De-duplicated event slugs, order preserved."""

    seen: dict[str, None] = {}
    for url in urls:
        slug = event_slug_from_url(url)
        if slug:
            seen.setdefault(slug, None)
    return list(seen)


def is_exact_score_question(question: Any) -> bool:
    return str(question or "").strip().lower().startswith("exact score")


def _json_list(value: Any) -> list[Any]:
    if isinstance(value, (list, tuple)):
        return list(value)
    try:
        parsed = json.loads(str(value))
    except (TypeError, ValueError):
        return []
    return list(parsed) if isinstance(parsed, list) else []


def event_lines(event: Mapping[str, Any], outcome: str = "No") -> pd.DataFrame:
    """Every resolved line of one Gamma event, from ``outcome``'s point of view.

    Reads ``outcomePrices`` for the settled result: Polymarket writes "1" to the
    winning outcome and "0" to the loser, so the flag is exact rather than
    inferred. Unresolved or malformed markets are dropped, since a base rate
    computed over markets that have not settled is not a base rate.

    Columns: event_slug, market_key, question, token_id, outcome, won, end_time.
    """

    slug = str(event.get("slug", "") or "")
    rows: list[dict[str, Any]] = []
    for market in event.get("markets", []) or []:
        if not isinstance(market, Mapping) or not market.get("closed"):
            continue
        outcomes = [str(value) for value in _json_list(market.get("outcomes"))]
        tokens = [str(value) for value in _json_list(market.get("clobTokenIds"))]
        prices = [str(value) for value in _json_list(market.get("outcomePrices"))]
        if outcome not in outcomes or len(tokens) != len(outcomes) or len(prices) != len(outcomes):
            continue
        index = outcomes.index(outcome)
        try:
            settled = float(prices[index])
        except (TypeError, ValueError):
            continue
        if settled not in (0.0, 1.0):  # still trading, or a refunded market
            continue
        rows.append(
            {
                "event_slug": slug,
                "market_key": str(market.get("conditionId", "") or ""),
                "question": str(market.get("question", "") or ""),
                "token_id": tokens[index],
                "outcome": outcome,
                "won": settled == 1.0,
                "end_time": market.get("endDate"),
            }
        )
    frame = pd.DataFrame(rows, columns=[c for c in OBSERVATION_COLUMNS if c != "price"])
    if not frame.empty:
        frame["end_time"] = pd.to_datetime(frame["end_time"], utc=True, errors="coerce")
    return frame


def price_at_lead_time(history: pd.DataFrame, end_time: Any, hours_before: float) -> float | None:
    """Last traded price at least ``hours_before`` hours ahead of ``end_time``.

    Returns None when the history does not reach back that far, which must stay
    distinguishable from a real price: dropping those rows keeps the sample
    honest, defaulting them to anything invents data.
    """

    if history is None or history.empty or "time" not in history or "price" not in history:
        return None
    cutoff = pd.to_datetime(end_time, utc=True, errors="coerce")
    if pd.isna(cutoff):
        return None
    stamps = pd.to_datetime(history["time"], utc=True, errors="coerce")
    window = history.loc[stamps <= cutoff - pd.Timedelta(hours=float(hours_before))]
    if window.empty:
        return None
    value = pd.to_numeric(window["price"], errors="coerce").dropna()
    return float(value.iloc[-1]) if not value.empty else None


#: Wie viele unabhaengige Events ein Bucket mindestens braucht, bevor sein
#: Ergebnis "significant" heissen darf. Siebzehn Linien eines einzigen
#: Fussballspiels sind siebzehn Zeilen und ein Ereignis: genau eine davon kann
#: gewinnen, die uebrigen sechzehn folgen daraus.
MIN_EVENTS_FOR_SIGNIFICANCE = 5


def _bonferroni_z(familie: int, alpha: float = 0.05) -> float:
    """z fuer ein zweiseitiges Intervall, das ``familie`` Tests mittraegt."""

    familie = max(1, int(familie))
    return float(NormalDist().inv_cdf(1.0 - alpha / (2.0 * familie)))


def base_rate_table(
    observations: pd.DataFrame,
    buckets: Sequence[float] = DEFAULT_PRICE_BUCKETS,
    *,
    alpha: float = 0.05,
) -> pd.DataFrame:
    """Implied vs realised rate per price bucket, with a Wilson interval.

    ``gap_pp`` is realised minus implied in percentage points: positive means the
    band paid out more often than its price said, i.e. buying it was cheap.

    Two things decide whether a row may be read as a finding, and both are
    columns rather than assumptions.

    ``events`` counts the distinct events behind the lines. The motivating
    sample is football Exact Score: one match contributes about seventeen
    mutually exclusive lines, and exactly one of them can win, so the other
    sixteen follow from that single draw. A bucket with n = 170 and events = 10
    is not 170 independent observations, and the table now says which it is.

    ``significant`` is judged against a Bonferroni-widened interval over the
    buckets actually tested, not against the nominal 95 percent. With the five
    default buckets each tested at 95 percent, a universe priced exactly right
    produced at least one "significant" band in 22 percent of runs. The nominal
    interval stays in ``ci_low`` / ``ci_high``; the widened one that the flag
    uses is in ``ci_low_adj`` / ``ci_high_adj``.
    """

    columns = ["bucket", "n", "markets", "events", "implied", "realised",
               "ci_low", "ci_high", "ci_low_adj", "ci_high_adj",
               "gap_pp", "significant", "family"]
    if observations is None or observations.empty:
        return pd.DataFrame(columns=columns)
    frame = observations.dropna(subset=["price"]).copy()
    frame["price"] = pd.to_numeric(frame["price"], errors="coerce")
    frame = frame.dropna(subset=["price"])
    if frame.empty:
        return pd.DataFrame(columns=columns)
    frame["won"] = frame["won"].astype(bool)
    frame["_bucket"] = pd.cut(frame["price"], list(buckets), include_lowest=True)
    gruppen = list(frame.groupby("_bucket", observed=True))
    familie = len(gruppen)
    z_adj = _bonferroni_z(familie, alpha)
    rows: list[dict[str, Any]] = []
    for bucket, group in gruppen:
        n = len(group)
        hits = int(group["won"].sum())
        implied = float(group["price"].mean())
        realised = hits / n if n else 0.0
        low, high = quant.wilson_interval(hits, n)
        low_adj, high_adj = quant.wilson_interval(hits, n, z=z_adj)
        events = int(group["event_slug"].nunique()) if "event_slug" in group else n
        rows.append(
            {
                "bucket": str(bucket),
                "n": n,
                "markets": int(group["market_key"].nunique()) if "market_key" in group else n,
                "events": events,
                "implied": implied,
                "realised": realised,
                "ci_low": low,
                "ci_high": high,
                "ci_low_adj": low_adj,
                "ci_high_adj": high_adj,
                "gap_pp": (realised - implied) * 100.0,
                "significant": bool(
                    events >= MIN_EVENTS_FOR_SIGNIFICANCE
                    and (low_adj > implied or high_adj < implied)
                ),
                "family": familie,
            }
        )
    return pd.DataFrame(rows, columns=columns)


def conviction_split(
    observations: pd.DataFrame, stake_column: str = "stake", quantile: float = 0.8
) -> pd.DataFrame:
    """Split a wallet's lines into its big and small bets, and score each half.

    A line-weighted comparison cannot see a sizing edge: if a wallet is right
    about *which* lines to load up on, every line still counts once. This splits
    on stake so the two halves can be read against the same universe base rate.
    Each half carries ``events`` and a Wilson interval on its realised rate.
    Without them the two ``gap_pp`` numbers invite a sizing story out of ten
    lines, which is the same mistake this module exists to catch one level up.

    Returns one row per half with ``half``, ``stake``, ``n``, ``events``,
    ``implied``, ``realised``, ``ci_low``, ``ci_high`` and ``gap_pp``.
    """

    columns = ["half", "n", "events", "stake", "implied", "realised",
               "ci_low", "ci_high", "gap_pp"]
    if observations is None or observations.empty or stake_column not in observations:
        return pd.DataFrame(columns=columns)
    frame = observations.dropna(subset=["price", stake_column]).copy()
    frame["price"] = pd.to_numeric(frame["price"], errors="coerce")
    frame[stake_column] = pd.to_numeric(frame[stake_column], errors="coerce")
    frame = frame.dropna(subset=["price", stake_column])
    if frame.empty:
        return pd.DataFrame(columns=columns)
    frame["won"] = frame["won"].astype(bool)
    cutoff = frame[stake_column].quantile(quantile)
    rows = []
    for label, part in (("big", frame[frame[stake_column] >= cutoff]),
                        ("small", frame[frame[stake_column] < cutoff])):
        if part.empty:
            continue
        implied = float(part["price"].mean())
        realised = float(part["won"].mean())
        # Zwei Haelften sind zwei Tests, also traegt jede das gemeinsame
        # Intervall der Familie mit.
        low, high = quant.wilson_interval(int(part["won"].sum()), len(part),
                                          z=_bonferroni_z(2))
        rows.append(
            {
                "half": label,
                "n": len(part),
                "events": int(part["event_slug"].nunique()) if "event_slug" in part else len(part),
                "stake": float(part[stake_column].sum()),
                "implied": implied,
                "realised": realised,
                "ci_low": low,
                "ci_high": high,
                "gap_pp": (realised - implied) * 100.0,
            }
        )
    return pd.DataFrame(rows, columns=columns)


def selection_gap(
    universe: pd.DataFrame, picked_keys: Iterable[Any], key_column: str = "token_id"
) -> dict[str, Any]:
    """The wallet's lines against the lines it left alone, on disjoint halves.

    ``compare_to_wallet`` subtracts two gaps whose samples overlap: the wallet's
    lines are inside the universe, so the difference has no interval anyone can
    write down. This splits the same universe into picked and not-picked, which
    are disjoint, and reports the difference of the two realised-minus-implied
    gaps with a 95 percent interval from the two independent halves.

    A ``selection_pp`` interval that spans zero means the picking is not
    separable from standing in the band.
    """

    leer = {"n_picked": 0, "n_rest": 0, "picked_gap_pp": None, "rest_gap_pp": None,
            "selection_pp": None, "ci_low": None, "ci_high": None, "separable": False}
    if universe is None or universe.empty or key_column not in universe:
        return leer
    frame = universe.dropna(subset=["price"]).copy()
    frame["price"] = pd.to_numeric(frame["price"], errors="coerce")
    frame = frame.dropna(subset=["price"])
    if frame.empty:
        return leer
    frame["won"] = frame["won"].astype(bool)
    schluessel = {str(k) for k in picked_keys}
    gewaehlt = frame[frame[key_column].astype(str).isin(schluessel)]
    rest = frame[~frame[key_column].astype(str).isin(schluessel)]
    if gewaehlt.empty or rest.empty:
        return dict(leer, n_picked=int(len(gewaehlt)), n_rest=int(len(rest)))

    def luecke(teil: pd.DataFrame) -> tuple[float, float]:
        realisiert = float(teil["won"].mean())
        return realisiert - float(teil["price"].mean()), realisiert

    picked_gap, picked_rate = luecke(gewaehlt)
    rest_gap, rest_rate = luecke(rest)
    differenz = picked_gap - rest_gap
    streuung = math.sqrt(
        picked_rate * (1 - picked_rate) / len(gewaehlt)
        + rest_rate * (1 - rest_rate) / len(rest)
    )
    halb = 1.96 * streuung
    return {
        "n_picked": int(len(gewaehlt)),
        "n_rest": int(len(rest)),
        "events_picked": int(gewaehlt["event_slug"].nunique()) if "event_slug" in gewaehlt else int(len(gewaehlt)),
        "picked_gap_pp": picked_gap * 100.0,
        "rest_gap_pp": rest_gap * 100.0,
        "selection_pp": differenz * 100.0,
        "ci_low": (differenz - halb) * 100.0,
        "ci_high": (differenz + halb) * 100.0,
        "separable": bool((differenz - halb) > 0 or (differenz + halb) < 0),
    }


def compare_to_wallet(universe: pd.DataFrame, wallet: pd.DataFrame) -> pd.DataFrame:
    """Join a universe base-rate table to the same table computed on one wallet.

    The decisive column is ``selection_pp``: the wallet's gap minus the
    universe's gap in the same band. Near zero means the wallet is simply
    standing in a mispriced band that anyone could have stood in.

    ``selection_pp`` carries no interval here on purpose: the wallet's lines sit
    *inside* the universe, so the two samples overlap and the difference of the
    two gaps has no clean standard error. For a difference that can be given an
    interval, use ``selection_gap``, which compares the picked lines against the
    ones the wallet left alone.
    """

    if universe is None or universe.empty or wallet is None or wallet.empty:
        return pd.DataFrame(columns=["bucket", "universe_gap_pp", "wallet_gap_pp", "selection_pp"])
    merged = universe.merge(wallet, on="bucket", how="inner", suffixes=("_universe", "_wallet"))
    merged["selection_pp"] = merged["gap_pp_wallet"] - merged["gap_pp_universe"]
    return merged.rename(columns={"gap_pp_universe": "universe_gap_pp", "gap_pp_wallet": "wallet_gap_pp"})[
        ["bucket", "n_universe", "n_wallet", "universe_gap_pp", "wallet_gap_pp", "selection_pp"]
    ]
