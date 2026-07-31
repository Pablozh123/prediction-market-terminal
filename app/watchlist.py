"""Markets both stream recorders must always record, whatever the volume says.

Both recorders pick what to watch by ranking on volume. That is right for
microstructure work and wrong for cross-venue work, because the pairs that
trade on both venues are long-dated and thin: the 2028 election markets, the
Eurovision host market. They never rank, so they were never recorded, so the
question they exist to answer - how long a cross-venue gap stays open - could
never be measured no matter how long the recorders ran.

This is the same idea as ``PRIORITY_SLOTS`` in ``src/book_recorder.py``, which
reserves capacity for templated long-tail markets for the base-rate study. A
recorder that only ever sees the busiest markets answers only the questions the
busiest markets can answer.

The file is ``data/cross_venue_watchlist.json``, written from the confirmed
pairs of a cross-venue run and deliberately kept out of the code: which pairs
are worth pinning is a research decision that changes, not a constant.

Streamlit-free, no network.
"""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATH = REPO_ROOT / "data" / "cross_venue_watchlist.json"


def load(path: Path | str = DEFAULT_PATH) -> dict:
    """The watchlist, or an empty one when the file is absent or broken.

    Never raises: a missing watchlist must degrade a recorder to its normal
    volume-ranked selection, not stop it from recording at all.
    """
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"paare": []}
    if not isinstance(payload, dict) or not isinstance(payload.get("paare"), list):
        return {"paare": []}
    return payload


def kalshi_tickers(path: Path | str = DEFAULT_PATH) -> list[str]:
    """Kalshi tickers to pin, in file order, without duplicates."""
    seen: dict[str, None] = {}
    for pair in load(path).get("paare", []):
        ticker = str((pair or {}).get("kalshi_ticker") or "").strip()
        if ticker:
            seen.setdefault(ticker, None)
    return list(seen)


def polymarket_token_ids(path: Path | str = DEFAULT_PATH) -> list[str]:
    """Polymarket token ids to pin, both outcomes per market."""
    seen: dict[str, None] = {}
    for pair in load(path).get("paare", []):
        for token in (pair or {}).get("polymarket_token_ids") or []:
            token = str(token).strip()
            if token:
                seen.setdefault(token, None)
    return list(seen)


def merge_pinned(pinned: list[str], ranked: list[str], limit: int) -> list[str]:
    """Pinned entries first, then the ranked ones, deduplicated and capped.

    The pinned markets take their slots off the top rather than being appended,
    because a cap applied afterwards would drop exactly the entries the pinning
    was meant to protect.
    """
    cap = max(0, int(limit))
    out: list[str] = []
    seen: set[str] = set()
    for value in list(pinned) + list(ranked):
        if len(out) >= cap:
            break
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out
