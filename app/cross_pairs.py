"""Cross-Venue-Paarung ueber die volle Marktbreite (Streamlit-frei, netzfrei).

``md.cross_venue_candidates`` kappt beide Seiten auf die Top-80 nach Volumen —
richtig fuer die interaktive Seite, aber zu eng, wenn sich die Top-Listen der
Venues kaum ueberlappen. Dieses Modul vergleicht die vollen Frames ueber einen
invertierten Token-Index (nur Paare mit mindestens zwei gemeinsamen Tokens
werden gescored) und benutzt dieselbe Aehnlichkeitsformel wie ``md``.

Das Ergebnis bleibt eine Titel-Heuristik: Paare sind NICHT verifiziert,
identisch aufzuloesen — dieselbe Frage kann auf beiden Venues verschieden
settlen. Der Abnehmer muss diesen Vorbehalt mit ausliefern.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from src import prediction_markets as md

MIN_SHARED_TOKENS = 2


def _series(frame: pd.DataFrame, name: str) -> list[Any]:
    if name in frame.columns:
        return list(frame[name])
    return [None] * len(frame)


def _rows(frame: pd.DataFrame) -> list[dict[str, Any]]:
    titles = _series(frame, "title")
    rows = []
    for title, key, ticker, yes, vol24, vol, url in zip(
        titles,
        _series(frame, "market_key"),
        _series(frame, "ticker"),
        _series(frame, "yes_price"),
        _series(frame, "volume_24h"),
        _series(frame, "activity_volume"),
        _series(frame, "url"),
    ):
        title = str(title or "").strip()
        try:
            yes_f = float(yes)
        except (TypeError, ValueError):
            continue
        if not title or not (0.0 < yes_f < 1.0):
            continue
        try:
            volume = float(vol24) if vol24 == vol24 and vol24 is not None else float(vol or 0.0)
        except (TypeError, ValueError):
            volume = 0.0
        rows.append({
            "title": title,
            "tokens": md._tokens(title),
            "market_key": str(key or ""),
            "ticker": str(ticker or ""),
            "yes": yes_f,
            "volume": volume,
            "url": str(url or ""),
        })
    return rows


def deep_cross_candidates(
    polymarket_markets: pd.DataFrame,
    kalshi_markets: pd.DataFrame,
    min_similarity: float = 0.2,
    max_pairs: int = 150,
) -> pd.DataFrame:
    """Beste Kalshi-Entsprechung je Polymarket-Markt, sortiert nach |Gap|.

    Rueckgabespalten entsprechen ``md.cross_venue_candidates`` (Teilmenge),
    damit nachgelagerte Mapper unveraendert funktionieren.
    """

    if polymarket_markets is None or kalshi_markets is None:
        return pd.DataFrame()
    if polymarket_markets.empty or kalshi_markets.empty:
        return pd.DataFrame()

    pm_rows = _rows(polymarket_markets)
    ks_rows = _rows(kalshi_markets)
    if not pm_rows or not ks_rows:
        return pd.DataFrame()

    token_index: dict[str, list[int]] = {}
    for idx, row in enumerate(ks_rows):
        for token in row["tokens"]:
            token_index.setdefault(token, []).append(idx)

    out: list[dict[str, Any]] = []
    for pm_row in pm_rows:
        shared_counts: dict[int, int] = {}
        for token in pm_row["tokens"]:
            for idx in token_index.get(token, ()):
                shared_counts[idx] = shared_counts.get(idx, 0) + 1
        best: dict[str, Any] | None = None
        for idx, shared in shared_counts.items():
            if shared < MIN_SHARED_TOKENS:
                continue
            ks_row = ks_rows[idx]
            similarity = md.market_similarity(pm_row["title"], ks_row["title"])
            if similarity < min_similarity:
                continue
            if best is None or similarity > best["similarity"]:
                best = {"similarity": similarity, "ks": ks_row}
        if best is None:
            continue
        ks_row = best["ks"]
        gap = pm_row["yes"] - ks_row["yes"]
        out.append({
            "similarity": best["similarity"],
            "gap": gap,
            "abs_gap": abs(gap),
            "polymarket_market_key": pm_row["market_key"],
            "kalshi_ticker": ks_row["ticker"],
            "polymarket_title": pm_row["title"],
            "kalshi_title": ks_row["title"],
            "polymarket_yes": pm_row["yes"],
            "kalshi_yes": ks_row["yes"],
            "polymarket_volume": pm_row["volume"],
            "kalshi_volume": ks_row["volume"],
            "polymarket_url": pm_row["url"],
            "kalshi_url": ks_row["url"],
        })

    if not out:
        return pd.DataFrame()
    frame = pd.DataFrame(out)
    frame = frame.sort_values(["abs_gap", "similarity"], ascending=[False, False])
    return frame.head(max_pairs).reset_index(drop=True)
