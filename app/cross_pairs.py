"""Cross-Venue-Paarung ueber die volle Marktbreite (Streamlit-frei, netzfrei).

``md.cross_venue_candidates`` kappt beide Seiten auf die Top-80 nach Volumen —
richtig fuer die interaktive Seite, aber zu eng, wenn sich die Top-Listen der
Venues kaum ueberlappen. Dieses Modul vergleicht die vollen Frames ueber einen
invertierten Token-Index (nur Paare mit mindestens zwei gemeinsamen Tokens
werden gescored) und benutzt dieselbe Aehnlichkeitsformel wie ``md``.

Das Ergebnis bleibt eine Titel-Heuristik: Paare sind NICHT verifiziert,
identisch aufzuloesen — dieselbe Frage kann auf beiden Venues verschieden
settlen. Der Abnehmer muss diesen Vorbehalt mit ausliefern.

Neben der Luecke zwischen den beiden Mittelkursen liefert das Modul, was von
ihr uebrig bleibt, wenn man sie tatsaechlich nimmt. Das sind drei
verschiedene Zahlen, und nur die letzte ist eine Aussage ueber Geld:

* ``gap`` ist die Differenz der Mittelkurse. Handelbar ist sie nicht: gekauft
  wird zum Brief, verkauft zum Geld.
* ``gross_edge_cents`` ist die ausfuehrbare Spanne. Wer YES auf der billigen
  Venue zum Brief kauft und NO auf der teuren (also YES verkauft zum Geld),
  zahlt zusammen ``ask + (1 - bid)`` und bekommt bei Aufloesung 1.00, also
  bleibt ``bid_teuer - ask_billig``. Das ist immer hoechstens die
  Mittelkurs-Luecke und meist deutlich weniger.
* ``net_edge_cents`` zieht beide Gebuehrenkurven ab (``app/venue_fees.py``).
  Erst diese Zahl darf als Vorteil gelesen werden.

Ohne beidseitige Quote auf beiden Venues bleiben die letzten beiden ``None``.
Unbekannt ist nicht null.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from app import venue_fees as vf
from src import prediction_markets as md

MIN_SHARED_TOKENS = 2

#: Clip, auf dem die Gebuehrenkurven ausgewertet werden. Beide Venues rechnen
#: die Gebuehr auf die Varianz des Ausgangs, Kalshi rundet die Order auf den
#: naechsten Cent auf; auf 100 Stueck faellt diese Rundung nicht ins Gewicht.
FEE_CLIP_SHARES = 100.0


def _series(frame: pd.DataFrame, name: str) -> list[Any]:
    if name in frame.columns:
        return list(frame[name])
    return [None] * len(frame)


def _quote(value: Any) -> float | None:
    """Eine Quote in (0, 1), oder None wenn keine da ist.

    Beide Venues schreiben 0.0 in best_bid/best_ask, wenn die Seite leer ist.
    Eine leere Seite ist keine Quote zu null Cent.
    """

    try:
        preis = float(value)
    except (TypeError, ValueError):
        return None
    if preis != preis or not (0.0 < preis < 1.0):
        return None
    return preis


def _rows(frame: pd.DataFrame) -> list[dict[str, Any]]:
    titles = _series(frame, "title")
    rows = []
    for title, key, ticker, yes, bid, ask, vol24, vol, category, url in zip(
        titles,
        _series(frame, "market_key"),
        _series(frame, "ticker"),
        _series(frame, "yes_price"),
        _series(frame, "best_bid"),
        _series(frame, "best_ask"),
        _series(frame, "volume_24h"),
        _series(frame, "activity_volume"),
        _series(frame, "category"),
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
            "bid": _quote(bid),
            "ask": _quote(ask),
            "volume": volume,
            "category": str(category or ""),
            "url": str(url or ""),
        })
    return rows


def basket_edge(pm_row: dict[str, Any], ks_row: dict[str, Any],
                shares: float = FEE_CLIP_SHARES) -> dict[str, Any]:
    """Die ausfuehrbare Spanne des Paares, brutto und nach beiden Gebuehren.

    Geprueft werden beide Richtungen: YES auf Polymarket gegen NO auf Kalshi
    und umgekehrt. Wer YES zum Brief kauft und auf der anderen Venue NO zum
    Brief (also ``1 - bid``), zahlt zusammen ``ask + 1 - bid`` und bekommt bei
    Aufloesung genau 1.00 je Paar. Brutto bleibt also ``bid - ask`` ueber die
    Venues hinweg. Beide Vorzeichen sind erlaubt: eine negative Spanne ist die
    Antwort "nicht handelbar", keine fehlende Antwort.

    Ohne beidseitige Quote auf beiden Venues gibt es nichts zu rechnen, dann
    bleibt alles ``None``.
    """

    leer = {"gross_edge_cents": None, "fee_band_cents": None,
            "net_edge_cents": None, "edge_direction": ""}
    richtungen = (
        ("buy Polymarket, sell Kalshi", pm_row.get("ask"), "polymarket",
         pm_row.get("category"), ks_row.get("bid"), "kalshi", ks_row.get("category")),
        ("buy Kalshi, sell Polymarket", ks_row.get("ask"), "kalshi",
         ks_row.get("category"), pm_row.get("bid"), "polymarket", pm_row.get("category")),
    )
    bestes: dict[str, Any] | None = None
    for name, ask, kauf_venue, kauf_cat, bid, verkauf_venue, verkauf_cat in richtungen:
        if ask is None or bid is None:
            continue
        # Das zweite Bein ist NO zum Preis 1 - bid; die Gebuehrenkurve ist in
        # p symmetrisch, der Preis des Beins gehoert trotzdem hier hin.
        economics = vf.basket_economics(
            vf.BasketLeg(kauf_venue, ask, category=kauf_cat),
            vf.BasketLeg(verkauf_venue, 1.0 - bid, category=verkauf_cat),
            shares=shares,
        )
        kandidat = {
            "gross_edge_cents": round(economics["gross_edge_cents"], 4),
            "fee_band_cents": round(economics["breakeven_gap_cents"], 4),
            "net_edge_cents": round(economics["net_edge_cents"], 4),
            "edge_direction": name,
        }
        if bestes is None or kandidat["net_edge_cents"] > bestes["net_edge_cents"]:
            bestes = kandidat
    return bestes or leer


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
            "polymarket_bid": pm_row["bid"],
            "polymarket_ask": pm_row["ask"],
            "kalshi_bid": ks_row["bid"],
            "kalshi_ask": ks_row["ask"],
            "polymarket_volume": pm_row["volume"],
            "kalshi_volume": ks_row["volume"],
            "polymarket_url": pm_row["url"],
            "kalshi_url": ks_row["url"],
            **basket_edge(pm_row, ks_row),
        })

    if not out:
        return pd.DataFrame()
    frame = pd.DataFrame(out)
    frame = frame.sort_values(["abs_gap", "similarity"], ascending=[False, False])
    return frame.head(max_pairs).reset_index(drop=True)
