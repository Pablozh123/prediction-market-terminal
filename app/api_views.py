"""JSON-Aufbereitung fuer die Terminal-API (Streamlit-frei, netzfrei).

Jede Funktion nimmt fertige DataFrames/Dicts aus den bestehenden Modulen und
formt genau die Strukturen, die das Web-Frontend unter web/ konsumiert.
Caveat-Felder (capped, window_truncated, verdict, sample, Stempel) werden
immer durchgereicht — eine Zahl ohne ihre Einschraenkung verlaesst diese
Schicht nicht.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Callable, Mapping

import pandas as pd

from app import perf_metrics as perf
from app import quant
from app import risk_log
from app import suspicion as susp
from app import track_record as trec

RESEARCH_FILES = {
    "review-queue": "queue",
    "category-efficiency": "kategorie_karte",
    "mentions-latency": "mentions_latenz",
    "live-runs": "runs",
    "pilot": "pilot",
    "pipeline-forward": "pipeline_forward",
    "methodology": "audit",
    "microstructure": "microstructure",
    "postmortems": "postmortems",
    "field-notes": "field_notes",
    "meta": "meta",
    # Everything the trading wallet did, by event — rebuilt from the public
    # Data API by scripts/wallet_ledger.py. Also merged into the live-runs
    # extras so the runs page needs no second request when the API answers.
    "wallet-ledger": "wallet_ledger",
}


def _num(value: Any, default: float | None = None) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(out) or math.isinf(out):
        return default
    return out


def _text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    return "" if text.lower() == "nan" else text


def short_wallet(value: Any) -> str:
    text = _text(value)
    if len(text) > 12:
        return text[:6] + "…" + text[-4:]
    return text


def balanced_head(
    frame: pd.DataFrame,
    limit: int,
    group_col: str = "platform",
    time_col: str = "time",
) -> pd.DataFrame:
    """Die neuesten ``limit`` Zeilen, ohne dass eine Venue die andere verdraengt.

    Ein reines ``sort_values(time).head(limit)`` liefert auf dem Tape nur noch
    Kalshi: die 15-Minuten-Kryptomaerkte drucken tausend Mikro-Trades in
    wenigen Sekunden und schieben jeden Polymarket-Print aus dem Fenster.
    Hier bekommt jede Venue zunaechst einen gleichen Anteil an ``limit``;
    was eine Venue nicht fuellt, geht an die anderen. Innerhalb einer Venue
    zaehlt weiterhin die Zeit, und das Ergebnis ist wieder nach Zeit sortiert.
    """
    if frame is None or frame.empty or limit <= 0:
        return frame.iloc[0:0] if frame is not None else pd.DataFrame()
    if group_col not in frame.columns:
        out = frame
        if time_col in out.columns:
            out = out.sort_values(time_col, ascending=False)
        return out.head(limit)
    ordered = frame.sort_values(time_col, ascending=False) if time_col in frame.columns else frame
    groups = {key: part for key, part in ordered.groupby(group_col, sort=False, dropna=False)}
    if not groups:
        return ordered.head(limit)
    quota = {key: 0 for key in groups}
    remaining = limit
    open_keys = list(groups)
    # Runde fuer Runde gleich verteilen; wer voll ist, faellt aus der Runde.
    while remaining > 0 and open_keys:
        share = max(1, remaining // len(open_keys))
        progressed = False
        for key in list(open_keys):
            available = len(groups[key]) - quota[key]
            take = min(share, available, remaining)
            if take <= 0:
                open_keys.remove(key)
                continue
            quota[key] += take
            remaining -= take
            progressed = True
            if quota[key] >= len(groups[key]):
                open_keys.remove(key)
            if remaining <= 0:
                break
        if not progressed:
            break
    parts = [groups[key].head(n) for key, n in quota.items() if n > 0]
    out = pd.concat(parts, ignore_index=False) if parts else ordered.iloc[0:0]
    if time_col in out.columns:
        out = out.sort_values(time_col, ascending=False)
    return out.head(limit)


#: Was als Kategorie nichts sagt und deshalb "Other" heisst. "Cross Category"
#: ist Kalshis Sammelserie fuer Multi-Event-Parlays (KXMVECROSSCATEGORY): ein
#: Behaelter, keine Kategorie, und darf nicht als Reiter erscheinen.
_LEERE_KATEGORIEN = {"", "uncategorized", "other", "nan", "none", "cross category", "cross-category"}


#: Felder einer Markt-Zeile, die das Frontend liest (web/js/util.js mapMarket
#: und die Detailansicht). Alles andere — ``raw`` (das komplette Gamma-Objekt),
#: ``description``, ``image``, Outcome- und Token-Blobs — bleibt im Server.
#: 250 Zeilen mit ``raw`` wogen ueber ein Megabyte; ohne liegen sie bei rund
#: 100 KB. Die Token-IDs braucht nur /api/market/{key}/history, und das liest
#: sie serverseitig aus dem Universum.
MARKET_FIELDS = (
    "market_key",
    "ticker",
    "title",
    "platform",
    "category",
    "filter_category",
    "yes_price",
    "spread",
    "change_1d",
    "volume_24h",
    # ``activity_volume`` ist ein Hybrid (24h, sonst Gesamtvolumen) und taugt
    # nur zum Sortieren. Das Frontend zeigt daneben das echte Gesamtvolumen,
    # damit unter der Ueberschrift "Volume 24h" nur der Tageswert steht.
    "activity_volume",
    "volume",
    "liquidity",
    "end_time",
    "market_age_days",
    "url",
)


def market_records(markets: pd.DataFrame, limit: int | None = None) -> list[dict[str, Any]]:
    """Markt-Zeilen fuer /api/markets: nur die Felder aus ``MARKET_FIELDS``.

    NaN wird null, Zeitstempel werden ISO, und ``filter_category`` laeuft
    durch ``clean_category`` — damit "Cross Category" und rohe Seriencodes
    nicht als Kategorie-Reiter im Frontend landen.
    """

    if markets is None or markets.empty:
        return []
    frame = markets.head(limit) if limit else markets
    keep = [c for c in MARKET_FIELDS if c in frame.columns]
    slim = frame[keep].copy()
    if "filter_category" in slim.columns:
        slim["filter_category"] = [clean_category(v) for v in slim["filter_category"].tolist()]
    if "category" in slim.columns:
        slim["category"] = [clean_category(v) for v in slim["category"].tolist()]
    return json.loads(slim.to_json(orient="records", date_format="iso"))


def kalshi_series(ticker: Any) -> str:
    """Serien-Praefix eines Kalshi-Tickers: KXBTC15M-26AUG17-1030-T115 -> KXBTC15M."""

    text = _text(ticker).strip()
    return text.split("-", 1)[0].upper() if text else ""


def clean_category(label: Any) -> str:
    """Kategorie-Label bereinigen; alles Nichtssagende wird "Other".

    Ein roher Kalshi-Seriencode (KXHIGHNY) ist keine Kategorie, sondern das
    Fehlen einer — er darf nicht als solche in der Spalte MOSTLY IN stehen.
    """

    text = _text(label).strip()
    if text.casefold() in _LEERE_KATEGORIEN:
        return "Other"
    if text.isupper() and text.startswith("KX"):
        return "Other"
    return text


#: Insider-Kontextgruppen aus app.suspicion -> Kategorie-Label des Tapes.
#: "General" fehlt absichtlich: das ist keine Kategorie, sondern "Other".
CONTEXT_GROUP_CATEGORY = {
    susp.CONTEXT_SPORTS: "Sports",
    susp.CONTEXT_MARKET_PRICES: "Finance",
    susp.CONTEXT_WEATHER: "Weather",
    susp.CONTEXT_POLITICS: "Politics",
    susp.CONTEXT_AWARDS: "Entertainment",
    susp.CONTEXT_CORPORATE: "Business",
}


def context_group_classifier(classify_context: Callable[..., Any] = susp.classify_insider_context) -> Callable[[Any, Any], str]:
    """``app.suspicion.classify_insider_context`` als Kategorie-Klassifizierer.

    Die Titelmuster dort kennen, was die Markt-Heuristik in
    ``md.market_filter_category`` nicht kennt: "LoL: X vs Y", "Dota 2: ...",
    "Will CF Thun win on 2026-08-06?" — genau die Prints, die das Tape
    dominieren. Die Gruppe wird auf das Kategorie-Vokabular der Marktseite
    abgebildet; "General" bleibt leer und wird damit "Other".
    """

    def classify(raw: Any, title: Any) -> str:
        group = classify_context(title, raw)[0]
        return CONTEXT_GROUP_CATEGORY.get(str(group), "")

    return classify


def parlay_classifier(raw: Any, title: Any) -> str:
    """Kalshi-Parlays ("Parlay · 2 legs: …") als eigene Kategorie.

    Als "Sports" klassifiziert fluteten mehrere hundert Parlay-Kombis die
    Kategorie und verdraengten jede echte Einzelspiel-Zeile aus dem Chip —
    ein Parlay ist ein eigenes Genre, und wer es nicht sehen will, blendet
    genau diese Kategorie aus.
    """

    return "Parlays" if _text(title).strip().casefold().startswith("parlay") else ""


def chained_classifier(*classifiers: Callable[[Any, Any], Any]) -> Callable[[Any, Any], str]:
    """Der erste Klassifizierer, der etwas anderes als "Other" sagt, gewinnt."""

    def classify(raw: Any, title: Any) -> str:
        for fn in classifiers:
            label = clean_category(fn(raw, title))
            if label != "Other":
                return label
        return "Other"

    return classify


def enrich_filter_categories(markets: pd.DataFrame, classify_fn: Callable[[Any, Any], Any]) -> pd.DataFrame:
    """``filter_category`` fuer Zeilen nachziehen, die noch "Other" heissen.

    Die Rohkategorien des Universums sind fast leer (Kalshi-Parlays, Esports,
    Einzelspiele — zuletzt sagten 907 von 1000 Zeilen "Other"), waehrend die
    Titelmuster des Tape-Klassifizierers genau diese Formen kennen. Nur
    Zeilen ohne Namen laufen durch ``classify_fn``; was danach immer noch
    keinen hat, bleibt ehrlich "Other". Die Eingabe bleibt unberuehrt.
    """

    if markets is None or markets.empty or "title" not in markets.columns:
        return markets
    out = markets.copy()
    raw = out["category"] if "category" in out.columns else pd.Series("", index=out.index)
    fine = out["filter_category"] if "filter_category" in out.columns else pd.Series("", index=out.index)
    neu = []
    for r, f, t in zip(raw.tolist(), fine.tolist(), out["title"].tolist()):
        label = clean_category(f)
        neu.append(label if label != "Other" else clean_category(classify_fn(r, t)))
    out["filter_category"] = neu
    return out


def tape_rows_with_category(
    trades: pd.DataFrame,
    universe: pd.DataFrame | None = None,
    classify_fn: Callable[[Any, Any], Any] | None = None,
) -> pd.DataFrame:
    """Jede Tape-Zeile bekommt eine ``category``-Spalte; die Eingabe bleibt unberuehrt.

    Das Frontend hat den Markt bisher ueber den Titel in seinen 250 geladenen
    Maerkten gesucht — die meisten Prints des Tapes sind dort nicht dabei,
    also stand fast ueberall "Other". Hier wird je Zeile in dieser
    Reihenfolge nachgeschlagen:

    1. Marktuniversum ueber ``market_key`` (Polymarket conditionId bzw.
       Kalshi-Ticker), dann ``slug``, dann exakter Titel. Traegt der Treffer
       ein ``filter_category`` (hat die Titel-Heuristik schon durchlaufen),
       gilt das; sonst laeuft seine rohe ``category`` mit dem Titel durch
       ``classify_fn``.
    2. Ohne Treffer: ``classify_fn(rohkategorie, titel)`` — bei Polymarket
       ohne Rohkategorie nur ueber den Titel, bei Kalshi ueber das
       Serien-Praefix des Tickers (KXBTC15M sagt Crypto, KXNBA sagt Sports).
    3. Was danach noch keinen Namen hat, heisst "Other".

    ``classify_fn`` ist im Server ``chained_classifier(md.market_filter_category,
    context_group_classifier())``; hier bleibt es ein Parameter, damit die
    Funktion netz- und modulfrei testbar ist.
    """

    if trades is None:
        return pd.DataFrame()
    out = trades.copy()
    if out.empty:
        if "category" not in out.columns:
            out["category"] = pd.Series(dtype=object)
        return out
    classify = classify_fn or (lambda raw, title: raw)

    # Nachschlagetabellen aus dem Universum: Schluessel -> (roh, filter).
    lookup: dict[str, tuple[str, str]] = {}
    if universe is not None and not universe.empty:
        raw_col = universe["category"] if "category" in universe.columns else pd.Series("", index=universe.index)
        fine_col = universe["filter_category"] if "filter_category" in universe.columns else pd.Series("", index=universe.index)
        for key_col in ("market_key", "slug", "title"):
            if key_col not in universe.columns:
                continue
            for key, raw, fine in zip(universe[key_col].tolist(), raw_col.tolist(), fine_col.tolist()):
                key_text = _text(key).strip()
                if key_text and key_text not in lookup:
                    lookup[key_text] = (_text(raw).strip(), _text(fine).strip())

    def _column(name: str) -> list[str]:
        if name in out.columns:
            return [_text(v).strip() for v in out[name].tolist()]
        return [""] * len(out)

    platforms = _column("platform")
    keys = _column("market_key")
    tickers = _column("ticker")
    slugs = _column("slug")
    titles = _column("title")

    categories: list[str] = []
    for platform, key, ticker, slug, title in zip(platforms, keys, tickers, slugs, titles):
        hit = None
        for candidate in (key, ticker, slug, title):
            if candidate and candidate in lookup:
                hit = lookup[candidate]
                break
        if hit is not None:
            raw, fine = hit
            label = fine if fine.casefold() not in _LEERE_KATEGORIEN else classify(raw, title)
        elif platform.casefold() == "kalshi":
            label = classify(kalshi_series(ticker or key or title), title)
        else:
            label = classify("", title)
        categories.append(clean_category(label))
    out["category"] = categories
    return out


def leaderboard_rows(leaderboard: pd.DataFrame, ranked: pd.DataFrame | None = None) -> list[dict[str, Any]]:
    """Leaderboard plus Smart-Score-Spalten, ohne teure Per-Wallet-Fetches.

    Win rate und resolved bets fehlen hier bewusst (None): sie erfordern den
    Resolved-Union-Fetch je Wallet und kommen erst im Wallet-Detail mit n und
    CI. Das Frontend zeigt dann einen Strich statt einer unbelegten Zahl.
    """

    if leaderboard is None or leaderboard.empty:
        return []
    score_by_wallet: dict[str, dict[str, Any]] = {}
    if ranked is not None and not ranked.empty and "wallet" in ranked:
        cohort_n = int(len(ranked))
        for _, row in ranked.iterrows():
            parts = score_parts(row)
            score_by_wallet[_text(row.get("wallet")).lower()] = {
                "score": _num(row.get("copy_smart_score")),
                "grade": _text(row.get("copy_grade")),
                "reason": _text(row.get("copy_rank_reason")),
                "parts": parts,
                "basis": score_basis(parts, cohort_n),
            }
    rows: list[dict[str, Any]] = []
    for _, row in leaderboard.iterrows():
        wallet = _text(row.get("wallet"))
        smart = score_by_wallet.get(wallet.lower(), {})
        score = smart.get("score")
        rows.append({
            "name": _text(row.get("trader")) or short_wallet(wallet) or "—",
            "wallet": wallet,
            "pnl": _num(row.get("pnl"), 0.0),
            "vol": _num(row.get("volume"), 0.0),
            "win": None,
            "resolved": None,
            "score": round(score, 1) if score is not None else None,
            "grade": smart.get("grade") or None,
            "tags": smart.get("reason") or "",
            # Die Bestandteile des Scores als Liste, damit das Frontend sie
            # beschriftet zeigt statt den rohen Begruendungs-String zu leaken.
            "score_parts": smart.get("parts") or [],
            # Worauf der Score ruht: welcher Anteil seines Gewichts gemessen
            # ist und welcher aus einem Ersatzwert stammt.
            "score_basis": smart.get("basis") or None,
        })
    return rows


#: Bestandteile des Smart-Scores (src/copy_trading.rank_traders_by_smart_score)
#: mit ihrem Gewicht und einem kurzen Label fuer die Oberflaeche.
SCORE_PART_COLUMNS = (
    ("copy_return_score", "return", 0.35),
    ("copy_sharpe_proxy", "sharpe proxy", 0.20),
    ("copy_drawdown_proxy", "drawdown proxy", 0.15),
    ("copy_win_score", "win", 0.10),
    ("copy_recency_score", "recency", 0.10),
    ("copy_volume_score", "volume", 0.10),
)


def score_parts(row: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Score-Bestandteile einer Ranked-Zeile als ``[{label, value, weight, imputed}]``.

    Nur Spalten, die wirklich da sind — fehlt eine, fehlt sie in der Liste,
    statt als 0 zu erscheinen. ``imputed`` sagt, ob der Wert aus echten
    Eingaben stammt oder aus dem Ersatzwert, den
    ``copy_trading.rank_traders_by_smart_score`` in ``copy_score_imputed``
    vermerkt; ein Ersatzwert ist fuer jede Wallet dieselbe Konstante und darf
    in der Oberflaeche nicht als Messung erscheinen.
    """

    imputed_columns = {name.strip() for name in _text(row.get("copy_score_imputed")).split(",") if name.strip()}
    parts: list[dict[str, Any]] = []
    for column, label, weight in SCORE_PART_COLUMNS:
        try:
            value = _num(row.get(column))
        except AttributeError:
            value = None
        if value is None:
            continue
        parts.append({
            "label": label,
            "value": round(value),
            "weight": weight,
            "imputed": column in imputed_columns,
        })
    return parts


def score_basis(parts: list[dict[str, Any]], cohort_n: int = 0) -> dict[str, Any]:
    """Wie viel Gewicht des Composite gemessen ist und wie viel geschaetzt.

    Der Score bleibt der Score aus ``rank_traders_by_smart_score``; hier wird
    nur benannt, worauf er ruht. Auf der oeffentlichen Leaderboard-Antwort
    sind das 0.45 gemessen (Rendite und Volumen) gegen 0.55 geschaetzt.

    ``cohort_n`` ist die Zahl der gemeinsam bewerteten Wallets. Das ist das n
    dieses Scores: der Volumen-Bestandteil ist eine Log-Skala gegen das
    95.-Perzentil derselben Menge (``copy_trading._log_score``), also haengt
    er von der Groesse der Menge ab und ist keine wallet-eigene Messung.
    """

    measured = round(sum(float(p.get("weight") or 0.0) for p in parts if not p.get("imputed")), 4)
    imputed = round(sum(float(p.get("weight") or 0.0) for p in parts if p.get("imputed")), 4)
    return {
        "measured_weight": measured,
        "imputed_weight": imputed,
        "imputed": [str(p.get("label")) for p in parts if p.get("imputed")],
        "cohort_n": int(max(0, cohort_n)),
    }


#: Wie viele Trades der Wallet-Seite im Aktivitaetsblock stehen und wie viele
#: geschlossene Positionen in der Tabelle; der Rest wird gezaehlt, nicht gezeigt.
WALLET_TRADES_SHOWN = 60
WALLET_CLOSED_SHOWN = 100
WALLET_POSITIONS_SHOWN = 100

#: Der Wallet-Endpunkt liest die Aktivitaet seitenweise (500 je Seite) bis zu
#: dieser Zeilenzahl; danach heisst es ``window_truncated``. Die Data API
#: nimmt hoehere Offsets, aber jede Seite ist ein weiterer Aufruf, und die
#: Antwort soll in Sekunden stehen, nicht in Minuten.
WALLET_ACTIVITY_MAX_ROWS = 2000

#: Ehrliche Grenzen des Wallet-Endpunkts, wie die Seite sie zitiert.
WALLET_LIMITS = [
    "Resolved positions come from the public /closed-positions feed, read in both sort directions "
    "(biggest winners, biggest losers) with ~50 rows per tail. When both tails hit the cap ('capped'), "
    "the middle of the record is unreachable and win rate, edge and PnL describe the extremes only.",
    f"Trades come from the public /activity feed in pages of 500 up to {WALLET_ACTIVITY_MAX_ROWS:,} rows "
    "('window_truncated' when the cap was hit). Trade counts, categories and context shares cover that window.",
    "The PnL curve is the profile curve from user-pnl-api.polymarket.com (daily fidelity, all time). That API's history "
    "begins in late 2024, so a wallet that stopped trading before then, or has not moved since, is a flat line there; "
    "the page then charts our own settled curve — the closed rows' realised PnL summed in resolution order — and says so. "
    "Sharpe, Sortino and Calmar are computed in dollars per day without a capital base and annualised on 365 days.",
    "Positions that resolved against the wallet and were never redeemed stay in /positions at price 0; "
    "they are counted as 'worthless', not as closed.",
    "No on-chain reconstruction runs here: deposits, withdrawals and transfers between wallets are not read. "
    "Everything is a read of the public Data API at request time, cached for 300 s.",
]


def _wilson(wins: int, n: int) -> list[float] | None:
    if not n:
        return None
    lo, hi = quant.wilson_interval(int(wins), int(n))
    return [round(float(lo), 4), round(float(hi), 4)]


def _classify_titles(titles: list[str], classify: Callable[[Any, Any], Any] | None) -> list[str]:
    if classify is None:
        return ["Other"] * len(titles)
    out: list[str] = []
    for title in titles:
        try:
            out.append(clean_category(classify("", title)))
        except Exception:  # noqa: BLE001 - a classifier hiccup must not sink the page
            out.append("Other")
    return out


def _wallet_identity(
    wallet: str,
    activity: pd.DataFrame | None,
    pseudonym: str,
    activity_truncated: bool,
) -> dict[str, Any]:
    first = last = ""
    days_active: float | None = None
    n_rows = 0
    if activity is not None and not activity.empty and "time" in activity:
        times = pd.to_datetime(activity["time"], utc=True, errors="coerce").dropna()
        n_rows = int(len(activity))
        if not times.empty:
            first = _iso(times.min())
            last = _iso(times.max())
            days_active = round(float((times.max() - times.min()).total_seconds()) / 86400.0, 1)
        if not pseudonym and "trader" in activity:
            names = [t for t in (_text(v).strip() for v in activity["trader"].tolist()) if t]
            pseudonym = names[0] if names else ""
    return {
        "address": wallet,
        "short": short_wallet(wallet),
        "pseudonym": pseudonym or "",
        "profile_url": f"https://polymarket.com/profile/{wallet}",
        "polygonscan_url": f"https://polygonscan.com/address/{wallet}",
        "first_activity": first,
        "last_activity": last,
        # Days between the oldest and newest activity row in the window read
        # — for a truncated window that is a lower bound.
        "days_active": days_active,
        "n_activity_rows": n_rows,
        "activity_truncated": bool(activity_truncated),
    }


def _wallet_track_record(
    track: Mapping[str, Any] | None,
    resolved: pd.DataFrame | None,
    capped: bool,
    as_of: str,
) -> dict[str, Any] | None:
    if not track:
        return None
    naive_n = int(track.get("naive_legs") or 0)
    naive_rate = _num(track.get("naive_win_rate"))
    naive_wins = int(round(naive_rate * naive_n)) if naive_rate is not None else 0
    events_n = int(track.get("resolved_events") or 0)
    event_rate = _num(track.get("event_win_rate"))
    event_wins = int(round(event_rate * events_n)) if event_rate is not None else 0
    markets_n = int(track.get("resolved_markets") or 0)
    market_rate = _num(track.get("corrected_win_rate"))
    market_wins = int(round(market_rate * markets_n)) if market_rate is not None else 0

    # Profit concentration beyond the single best market: the top three
    # markets' share of gross profit, with their titles.
    top3: list[dict[str, Any]] = []
    top3_share: float | None = None
    if resolved is not None and not resolved.empty:
        markets = trec.market_records(resolved)
        titles: dict[str, str] = {}
        if "market_key" in resolved and "title" in resolved:
            for key, title in zip(resolved["market_key"].tolist(), resolved["title"].tolist()):
                titles.setdefault(_text(key), _text(title))
        positive = markets[markets["net_pnl"] > 0].sort_values("net_pnl", ascending=False)
        gross = float(positive["net_pnl"].sum()) if not positive.empty else 0.0
        if gross > 0:
            head = positive.head(3)
            top3_share = round(float(head["net_pnl"].sum()) / gross, 4)
            top3 = [
                {"title": titles.get(_text(r["market_key"]), _text(r["market_key"])), "pnl": round(float(r["net_pnl"]), 2),
                 "share": round(float(r["net_pnl"]) / gross, 4)}
                for _, r in head.iterrows()
            ]
    return {
        "as_of": as_of,
        "source": "polymarket /closed-positions, winner and loser tails unioned",
        "capped": bool(capped),
        "naive": {
            "label": "per position leg (what the leaderboard implies)",
            "win_rate": naive_rate, "wins": naive_wins, "n": naive_n, "ci95": _wilson(naive_wins, naive_n),
        },
        "corrected": {
            "label": "per event, NegRisk legs netted",
            "win_rate": event_rate, "wins": event_wins, "n": events_n, "ci95": _wilson(event_wins, events_n),
        },
        "per_market": {
            "label": "per market (conditionId), legs netted",
            "win_rate": market_rate, "wins": market_wins, "n": markets_n, "ci95": _wilson(market_wins, markets_n),
        },
        "legs_netted": max(0, naive_n - events_n),
        "leg_inflation": _num(track.get("leg_inflation")),
        "win_rate_reliable": bool(track.get("win_rate_reliable")),
        "settled_pnl": _num(track.get("settled_pnl")),
        "volume": _num(track.get("volume")),
        "pnl_per_volume": _num(track.get("pnl_per_volume")),
        "exit_win_rate": _num(track.get("exit_win_rate")),
        "wash_flag": {
            "flag": bool(track.get("farmer_flag")),
            "rule": (f"volume >= ${trec.FARMER_MIN_VOLUME:,.0f} and |settled PnL| / volume < "
                     f"{trec.FARMER_MAX_EDGE * 100:.1f}% over >= 5 resolved markets"),
        },
        "survivorship_gate": {
            "ok": bool(track.get("sample_ok")),
            "resolved_markets": markets_n,
            "span_days": _num(track.get("span_days")),
            "min_markets": trec.MIN_RESOLVED_MARKETS,
            "min_span_days": trec.MIN_SPAN_DAYS,
        },
        "concentration": {
            "top_market_share": _num(track.get("top_market_share")),
            "top3_share": top3_share,
            "top3": top3,
            "one_hit_flag": bool(track.get("one_hit_flag")),
        },
        "risk_adjusted": _num(track.get("risk_adjusted")),
        "score": _num(track.get("score")),
        "grade": _text(track.get("grade")),
        "score_components": list(track.get("score_components") or []),
        "flags": list(track.get("flags") or []),
        "coverage_note": _text(track.get("coverage_note")),
    }


def _curve_stats(frame: pd.DataFrame) -> dict[str, Any] | None:
    """perf.summarize_curve on a [time, pnl] frame, JSON-safe; None when it fails."""

    try:
        stats = perf.summarize_curve(frame[[c for c in ("time", "pnl") if c in frame.columns]])
    except Exception:  # noqa: BLE001 - a bad curve leaves the stats empty, not the page dead
        return None
    # Floats through _num (NaN/inf -> null), counts stay integers.
    return {k: (_num(v) if isinstance(v, float) else v) for k, v in stats.items()}


def _settled_curve(resolved: pd.DataFrame | None, capped: bool) -> dict[str, Any] | None:
    """Cumulative realised PnL from the closed-positions rows, in resolution
    order — our own curve, for wallets whose profile curve carries nothing.

    The series starts at $0 one day before the first resolution (a cumulative
    curve needs an opening level, and the feed has none), then steps by each
    row's realised PnL at the row's time. With capped tails only the biggest
    winners and losers are in it, and the block says so.
    """

    if resolved is None or resolved.empty or "realized_pnl" not in resolved or "time" not in resolved:
        return None
    df = pd.DataFrame({
        "time": pd.to_datetime(resolved["time"], utc=True, errors="coerce"),
        "pnl": pd.to_numeric(resolved["realized_pnl"], errors="coerce"),
    }).dropna(subset=["time", "pnl"]).sort_values("time")
    if len(df) < 1:
        return None
    n_rows = int(len(df))
    start = df["time"].iloc[0] - pd.Timedelta(1, unit="D")
    curve = pd.DataFrame({
        "time": [start, *df["time"].tolist()],
        "pnl": [0.0, *df["pnl"].cumsum().tolist()],
    })
    points = [{"t": _iso(row["time"]), "pnl": round(float(row["pnl"]), 2)} for _, row in curve.iterrows()]
    note = (
        f"Realised PnL of the {n_rows:,} closed-position rows summed in resolution order, starting at $0 the day before "
        "the first resolution. Open positions' unrealised PnL is not in it. "
        + ("Capped tails: only the ~50 biggest winners and ~50 biggest losers are in the sum, so the middle of the record "
           "is missing and the swings are the extremes only." if capped else "Complete resolved set (both tails).")
    )
    return {
        "points": points,
        "n_points": len(points),
        "n_rows": n_rows,
        "first": _iso(df["time"].iloc[0]),
        "last": _iso(df["time"].iloc[-1]),
        "total": round(float(df["pnl"].sum()), 2),
        "capped": bool(capped),
        "stats": _curve_stats(curve),
        "source": "polymarket /closed-positions, both sort directions, summed by our code",
        "note": note,
    }


def _wallet_pnl(pnl_points: pd.DataFrame | None, as_of: str, window: str,
                resolved: pd.DataFrame | None = None, capped: bool = False) -> dict[str, Any]:
    """The PnL-curve block: the profile curve from user-pnl-api (points, stats)
    plus our own settled curve from the closed rows, and ``shown`` — which of
    the two carries information.

    The user-pnl API's history begins late 2024; a wallet whose trading ended
    before that (or that has not moved since) gets a flat line there — 630
    identical points, zero drawdown, no Sharpe. ``flat`` names that case and
    ``shown`` points the page at the settled curve instead, so the ratios come
    from a series that actually changes.
    """

    settled = _settled_curve(resolved, capped)
    if pnl_points is None or pnl_points.empty or "pnl" not in pnl_points:
        return {"as_of": as_of, "window": window, "points": [], "n_points": 0, "stats": None,
                "flat": False, "first": "", "last": "",
                "source": "user-pnl-api.polymarket.com", "note": "The profile PnL curve did not answer.",
                "settled": settled,
                "shown": "settled" if settled and settled["n_points"] >= 2 else "none"}
    frame = pnl_points.copy()
    frame["pnl"] = pd.to_numeric(frame["pnl"], errors="coerce")
    if "time" in frame:
        frame["time"] = pd.to_datetime(frame["time"], utc=True, errors="coerce")
    frame = frame.dropna(subset=["pnl"])
    points = [
        {"t": _iso(row.get("time")) if "time" in frame else "", "pnl": round(float(row["pnl"]), 2)}
        for _, row in frame.iterrows()
    ]
    stats = _curve_stats(frame)
    values = frame["pnl"].astype(float)
    flat = bool(len(values) >= 1 and float(values.max() - values.min()) < 0.005)
    first = points[0]["t"] if points else ""
    last = points[-1]["t"] if points else ""
    if len(points) >= 2 and not flat:
        shown = "profile"
    elif settled and settled["n_points"] >= 2:
        shown = "settled"
    elif len(points) >= 2:
        shown = "profile"
    else:
        shown = "none"
    note = "Ratios in dollars per day, no capital base, annualised on 365 days; n_days is the sample."
    if flat and points:
        level = points[-1]["pnl"]
        note = (
            f"The profile curve is a flat line at ${level:,.0f} over its {len(points):,} points"
            + (f" ({first[:10]} to {last[:10]})" if first and last else "")
            + ": user-pnl-api's history for this wallet begins there and nothing has changed since — "
            "no daily change, so no Sharpe, drawdown or win-day share can come out of it."
        )
    return {
        "as_of": as_of,
        "window": window,
        "source": "user-pnl-api.polymarket.com (the curve polymarket.com shows on the profile)",
        "points": points,
        "n_points": len(points),
        "stats": stats,
        "flat": flat,
        "first": first,
        "last": last,
        "note": note,
        "settled": settled,
        "shown": shown,
    }


def _wallet_edge(
    resolved: pd.DataFrame | None,
    realized: Mapping[str, Any] | None,
    capped: bool,
    classify: Callable[[Any, Any], Any] | None,
    as_of: str,
) -> dict[str, Any]:
    per_dollar: dict[str, Any] = {"edge": None, "ci_low": None, "ci_high": None, "groups": 0, "significant": False}
    by_category: list[dict[str, Any]] = []
    if resolved is not None and not resolved.empty:
        df = resolved.copy()
        df["cost"] = pd.to_numeric(df.get("total_bought"), errors="coerce").fillna(0.0)
        df["payout"] = df["cost"] + pd.to_numeric(df.get("realized_pnl"), errors="coerce").fillna(0.0)
        df["group"] = df.apply(trec._event_key, axis=1)
        try:
            per_dollar = perf.cluster_bootstrap_edge(df, "group", cost_column="cost", payout_column="payout")
        except Exception:  # noqa: BLE001
            pass
        titles = [_text(v) for v in df.get("title", pd.Series("", index=df.index)).tolist()]
        df["category"] = _classify_titles(titles, classify)
        for category, part in df.groupby("category", sort=False):
            groups = int(part["group"].nunique())
            cost = float(part["cost"].sum())
            if cost <= 0:
                continue
            row: dict[str, Any] = {
                "category": str(category), "groups": groups, "positions": int(len(part)),
                "cost": round(cost, 2), "pnl": round(float((part["payout"] - part["cost"]).sum()), 2),
                "edge": round(float(part["payout"].sum() / cost - 1.0), 4), "ci_low": None, "ci_high": None,
            }
            if groups >= 3:
                try:
                    boot = perf.cluster_bootstrap_edge(part, "group", cost_column="cost", payout_column="payout", draws=2000)
                    row["ci_low"] = _num(boot.get("ci_low"))
                    row["ci_high"] = _num(boot.get("ci_high"))
                except Exception:  # noqa: BLE001
                    pass
            by_category.append(row)
        by_category.sort(key=lambda r: -r["cost"])
    return {
        "as_of": as_of,
        "capped": bool(capped),
        "per_dollar": {
            "edge": _num(per_dollar.get("edge")),
            "ci_low": _num(per_dollar.get("ci_low")),
            "ci_high": _num(per_dollar.get("ci_high")),
            "groups": int(per_dollar.get("groups") or 0),
            "significant": bool(per_dollar.get("significant")),
            "method": "payout / cost - 1 over resolved positions; 95% CI from a cluster bootstrap "
                      "resampling whole events (4000 draws)",
        },
        "per_share": dict(realized) if realized else None,
        "by_category": by_category,
    }


def _wallet_positions(positions: pd.DataFrame | None, as_of: str, requested: int) -> dict[str, Any]:
    if positions is None or positions.empty:
        return {"as_of": as_of, "rows": [], "n": 0, "shown": 0, "capped": False, "total_exposure": 0.0,
                "total_cost": 0.0, "unrealized_pnl": 0.0, "worthless_n": 0,
                "worthless_pnl": 0.0, "worthless_cost": 0.0,
                "note": "No open positions in the public /positions feed."}
    rows: list[dict[str, Any]] = []
    exposure = cost = unreal = 0.0
    worthless_pnl = worthless_cost = 0.0
    worthless = 0
    for _, row in positions.iterrows():
        size = _num(row.get("size"), 0.0) or 0.0
        avg = _num(row.get("avg_price"), 0.0) or 0.0
        cur = _num(row.get("current_price"), 0.0) or 0.0
        value = _num(row.get("value"), 0.0) or 0.0
        pnl = _num(row.get("unrealized_pnl"), 0.0) or 0.0
        end_time = _iso(row.get("end_time"))
        resolved_worthless = cur <= 0.0 and value <= 0.0
        # Eine wertlose Position ist gegen die Wallet aufgeloest und wurde nur
        # nicht eingeloest — ihr Verlust ist realisiert und bewegt sich nie
        # wieder. Bis hierher lief er in dieselbe Summe wie der Buchgewinn
        # der offenen Positionen und stand auf der Seite unter "UNREALISED
        # (open)". Beide Toepfe werden jetzt getrennt gefuehrt.
        if resolved_worthless:
            worthless += 1
            worthless_pnl += pnl
            worthless_cost += size * avg
        else:
            exposure += value
            cost += size * avg
            unreal += pnl
        rows.append({
            "title": _text(row.get("title")),
            "outcome": _text(row.get("outcome")),
            "size": round(size, 4),
            "avg_price": round(avg, 4),
            "current_price": round(cur, 4),
            "value": round(value, 2),
            "cost": round(size * avg, 2),
            "unrealized_pnl": round(pnl, 2),
            "pnl_pct": _num(row.get("pnl_pct")),
            "end_time": end_time,
            "market_key": _text(row.get("market_key")),
            "url": market_url("Polymarket", _text(row.get("market_key")), _text(row.get("url"))),
            "image": _image_url(row.get("image")),
            "status": "worthless" if resolved_worthless else "open",
        })
    rows.sort(key=lambda r: -r["value"])
    return {
        "as_of": as_of,
        "rows": rows[:WALLET_POSITIONS_SHOWN],
        "n": len(rows),
        "shown": min(len(rows), WALLET_POSITIONS_SHOWN),
        "capped": len(rows) >= int(requested),
        # Exposure, Kostenbasis und Buchgewinn nur ueber die wirklich offenen
        # Zeilen; die wertlosen stehen mit eigener Summe daneben.
        "total_exposure": round(exposure, 2),
        "total_cost": round(cost, 2),
        "unrealized_pnl": round(unreal, 2),
        "worthless_n": worthless,
        "worthless_pnl": round(worthless_pnl, 2),
        "worthless_cost": round(worthless_cost, 2),
        "note": ("Value at the current price; positions at price 0 past their end date resolved against "
                 "the wallet and were not redeemed ('worthless'). Their loss is settled, not unrealised, "
                 "so it is reported separately and is not in 'unrealized_pnl', 'total_cost' or "
                 "'total_exposure'."),
    }


def _wallet_closed(resolved: pd.DataFrame | None, capped: bool, worthless_n: int, as_of: str,
                   coverage_note: str) -> dict[str, Any]:
    if resolved is None or resolved.empty:
        return {"as_of": as_of, "capped": bool(capped), "n": 0, "shown": 0, "won": 0, "lost": 0, "flat": 0,
                "worthless_not_redeemed": int(worthless_n), "rows": [], "realized_pnl": 0.0, "note": coverage_note,
                "source": "polymarket /closed-positions, both sort directions, ~50 rows per tail"}
    df = resolved.copy()
    df["_pnl"] = pd.to_numeric(df.get("realized_pnl"), errors="coerce").fillna(0.0)
    won = int((df["_pnl"] > 0).sum())
    lost = int((df["_pnl"] < 0).sum())
    flat = int(len(df) - won - lost)
    df = df.reindex(df["_pnl"].abs().sort_values(ascending=False).index)
    rows = [
        {
            "title": _text(row.get("title")),
            "outcome": _text(row.get("outcome")),
            "avg_price": _num(row.get("avg_price")),
            "current_price": _num(row.get("current_price")),
            "total_bought": _num(row.get("total_bought")),
            "realized_pnl": round(float(row["_pnl"]), 2),
            "time": _iso(row.get("time")),
            "market_key": _text(row.get("market_key")),
            "url": market_url("Polymarket", _text(row.get("market_key")), _text(row.get("url"))),
            "image": _image_url(row.get("image")),
            "result": "won" if row["_pnl"] > 0 else "lost" if row["_pnl"] < 0 else "flat",
        }
        for _, row in df.head(WALLET_CLOSED_SHOWN).iterrows()
    ]
    return {
        "as_of": as_of,
        "capped": bool(capped),
        "n": int(len(df)),
        "shown": len(rows),
        "won": won,
        "lost": lost,
        "flat": flat,
        "worthless_not_redeemed": int(worthless_n),
        "realized_pnl": round(float(df["_pnl"].sum()), 2),
        "rows": rows,
        "note": coverage_note,
        "source": "polymarket /closed-positions, both sort directions, ~50 rows per tail",
    }


def _wallet_activity(activity: pd.DataFrame | None, truncated: bool, as_of: str) -> dict[str, Any]:
    empty = {"as_of": as_of, "n_rows": 0, "n_trades": 0, "n_redeems": 0, "window_truncated": bool(truncated),
             "first": "", "last": "", "span_days": None, "trades": [], "shown": 0, "buy_n": 0, "sell_n": 0,
             "buy_notional": 0.0, "sell_notional": 0.0, "redeem_notional": 0.0, "net_cash_flow": 0.0,
             "volume_traded": 0.0, "avg_trade_size": None, "trades_per_day": None, "source": "polymarket /activity"}
    if activity is None or activity.empty:
        return empty
    df = activity.copy()
    df["_type"] = df.get("type", pd.Series("", index=df.index)).astype(str).str.upper()
    df["_side"] = df.get("side", pd.Series("", index=df.index)).astype(str).str.upper()
    df["_usd"] = pd.to_numeric(df.get("notional"), errors="coerce").fillna(0.0)
    df["_time"] = pd.to_datetime(df.get("time"), utc=True, errors="coerce")
    trades = df[df["_type"].eq("TRADE")]
    times = df["_time"].dropna()
    span_days = round(float((times.max() - times.min()).total_seconds()) / 86400.0, 2) if len(times) >= 2 else 0.0
    buys = trades[trades["_side"].eq("BUY")]
    sells = trades[trades["_side"].eq("SELL")]
    redeems = df[df["_type"].isin(["REDEEM", "MERGE"])]
    n_trades = int(len(trades))
    volume = float(trades["_usd"].sum())
    buy_usd = float(buys["_usd"].sum())
    sell_usd = float(sells["_usd"].sum())
    redeem_usd = float(redeems["_usd"].sum())
    shown = trades.sort_values("_time", ascending=False).head(WALLET_TRADES_SHOWN)
    rows = [
        {
            "time": _iso(row.get("_time")),
            "type": _text(row.get("type")),
            "side": _text(row.get("side")).upper(),
            "outcome": _text(row.get("outcome")),
            "price": _num(row.get("price")),
            "size": _num(row.get("size")),
            "notional": round(float(row["_usd"]), 2),
            "title": _text(row.get("title")),
            "market_key": _text(row.get("market_key")),
            "url": market_url("Polymarket", _text(row.get("market_key")), _text(row.get("url")), _text(row.get("slug"))),
        }
        for _, row in shown.iterrows()
    ]
    return {
        "as_of": as_of,
        "n_rows": int(len(df)),
        "n_trades": n_trades,
        "n_redeems": int(df["_type"].eq("REDEEM").sum()),
        "window_truncated": bool(truncated),
        "first": _iso(times.min()) if not times.empty else "",
        "last": _iso(times.max()) if not times.empty else "",
        "span_days": span_days,
        "trades": rows,
        "shown": len(rows),
        "buy_n": int(len(buys)),
        "sell_n": int(len(sells)),
        "buy_notional": round(buy_usd, 2),
        "sell_notional": round(sell_usd, 2),
        "redeem_notional": round(redeem_usd, 2),
        # Cash view of the window: what came back (sells + redemptions) minus
        # what went in (buys). Open positions and unredeemed winners are not in it.
        "net_cash_flow": round(sell_usd + redeem_usd - buy_usd, 2),
        "volume_traded": round(volume, 2),
        "avg_trade_size": round(volume / n_trades, 2) if n_trades else None,
        "trades_per_day": round(n_trades / max(span_days, 1.0), 3) if n_trades else None,
        "source": "polymarket /activity",
    }


def _band(value: float | None, rules: list[tuple[float, str]], below: str) -> str:
    """First label whose threshold the value reaches (rules sorted high→low)."""

    if value is None:
        return ""
    for threshold, label in rules:
        if value >= threshold:
            return label
    return below


def _wallet_risk_profile(resolved: pd.DataFrame | None, capped: bool, activity: pd.DataFrame | None, as_of: str) -> dict[str, Any]:
    """Profit factor, risk/reward, streaks, conviction and the trading-hours
    heatmap — the "Risk" tab. Every figure names its n; with capped tails
    the closed set holds the extremes only, so the block says PARTIAL and
    the reader knows the middle of the record is not in these numbers.
    """

    out: dict[str, Any] = {
        "as_of": as_of,
        "partial": bool(capped),
        "n_rows": 0,
        "profit_factor": None, "risk_reward": None, "conviction": None,
        "win_streak": 0, "loss_streak": 0, "current_streak": 0, "current_streak_kind": "",
        "n_win": 0, "n_loss": 0, "avg_win": None, "avg_loss": None, "largest_win": None, "largest_loss": None,
        "avg_stake_win": None, "avg_stake_loss": None,
        "bands": {}, "note": "",
        "rules": {
            "profit_factor": "sum of winning rows' realised PnL / |sum of losing rows'|",
            "risk_reward": "average winning row / average losing row (absolute)",
            "conviction": "average $ bought on winning rows / average $ bought on losing rows — above 1 means the wallet sized up when it was right",
            "streaks": "longest run of consecutive winning / losing resolved rows in time order",
        },
        "heatmap": {"counts": [[0] * 24 for _ in range(7)], "notional": [[0.0] * 24 for _ in range(7)], "n": 0, "tz": "UTC",
                     "busiest": None, "note": "trades in the activity window by weekday (Mon–Sun) and UTC hour"},
    }
    if resolved is not None and not resolved.empty:
        df = resolved.copy()
        df["_pnl"] = pd.to_numeric(df.get("realized_pnl"), errors="coerce").fillna(0.0)
        df["_stake"] = pd.to_numeric(df.get("total_bought"), errors="coerce").fillna(0.0)
        df["_time"] = pd.to_datetime(df.get("time"), utc=True, errors="coerce")
        wins = df[df["_pnl"] > 0]
        losses = df[df["_pnl"] < 0]
        gross_win = float(wins["_pnl"].sum())
        gross_loss = float(-losses["_pnl"].sum())
        out["n_rows"] = int(len(df))
        out["n_win"] = int(len(wins))
        out["n_loss"] = int(len(losses))
        out["profit_factor"] = round(gross_win / gross_loss, 2) if gross_loss > 0 else None
        out["avg_win"] = round(gross_win / len(wins), 2) if len(wins) else None
        out["avg_loss"] = round(gross_loss / len(losses), 2) if len(losses) else None
        out["risk_reward"] = round(out["avg_win"] / out["avg_loss"], 2) if out["avg_win"] and out["avg_loss"] else None
        out["largest_win"] = round(float(wins["_pnl"].max()), 2) if len(wins) else None
        out["largest_loss"] = round(float(losses["_pnl"].min()), 2) if len(losses) else None
        stake_w = float(wins["_stake"].mean()) if len(wins) and wins["_stake"].gt(0).any() else None
        stake_l = float(losses["_stake"].mean()) if len(losses) and losses["_stake"].gt(0).any() else None
        out["avg_stake_win"] = round(stake_w, 2) if stake_w is not None else None
        out["avg_stake_loss"] = round(stake_l, 2) if stake_l is not None else None
        out["conviction"] = round(stake_w / stake_l, 2) if stake_w and stake_l else None
        ordered = df.dropna(subset=["_time"]).sort_values("_time")
        best_w = best_l = run = 0
        kind = ""
        for pnl in ordered["_pnl"].tolist():
            k = "win" if pnl > 0 else "loss" if pnl < 0 else ""
            if not k:
                continue
            run = run + 1 if k == kind else 1
            kind = k
            if k == "win":
                best_w = max(best_w, run)
            else:
                best_l = max(best_l, run)
        out["win_streak"] = int(best_w)
        out["loss_streak"] = int(best_l)
        out["current_streak"] = int(run)
        out["current_streak_kind"] = kind
        out["bands"] = {
            "profit_factor": _band(out["profit_factor"], [(2.0, "strong"), (1.2, "positive"), (1.0, "thin")], "losing") if out["profit_factor"] is not None else ("no losing row" if len(wins) and not len(losses) else ""),
            "risk_reward": _band(out["risk_reward"], [(1.5, "wins bigger than losses"), (0.8, "about even")], "losses bigger than wins"),
            "conviction": _band(out["conviction"], [(1.2, "sizes up when right"), (0.8, "even sizing")], "sizes up when wrong"),
        }
        out["note"] = ("closed rows: both tails of the /closed-positions feed" + (" — CAPPED at ~50 per tail, so profit factor, streaks and conviction describe the biggest winners and losers only" if capped else "")
                       + f"; n {len(df)} rows, {len(wins)} won, {len(losses)} lost")
    if activity is not None and not activity.empty:
        df = activity.copy()
        typ = df.get("type", pd.Series("", index=df.index)).astype(str).str.upper()
        trades = df[typ.eq("TRADE")].copy()
        trades["_time"] = pd.to_datetime(trades.get("time"), utc=True, errors="coerce")
        trades["_usd"] = pd.to_numeric(trades.get("notional"), errors="coerce").fillna(0.0)
        trades = trades.dropna(subset=["_time"])
        counts = [[0] * 24 for _ in range(7)]
        usd = [[0.0] * 24 for _ in range(7)]
        for t, n in zip(trades["_time"].tolist(), trades["_usd"].tolist()):
            counts[t.weekday()][t.hour] += 1
            usd[t.weekday()][t.hour] += float(n)
        best = None
        for wd in range(7):
            for hr in range(24):
                if counts[wd][hr] and (best is None or counts[wd][hr] > best[2]):
                    best = (wd, hr, counts[wd][hr])
        out["heatmap"] = {
            "counts": counts,
            "notional": [[round(v, 2) for v in row] for row in usd],
            "n": int(len(trades)),
            "tz": "UTC",
            "busiest": {"weekday": best[0], "hour": best[1], "trades": best[2]} if best else None,
            "note": "trades in the activity window by weekday (Mon–Sun) and UTC hour",
        }
    return out


def _wallet_categories(
    activity: pd.DataFrame | None,
    resolved: pd.DataFrame | None,
    classify: Callable[[Any, Any], Any] | None,
    as_of: str,
) -> dict[str, Any]:
    stake: dict[str, dict[str, Any]] = {}

    def _slot(label: str) -> dict[str, Any]:
        return stake.setdefault(label, {"category": label, "stake": 0.0, "trades": 0, "pnl": 0.0, "resolved_markets": 0})

    if activity is not None and not activity.empty:
        df = activity.copy()
        df["_type"] = df.get("type", pd.Series("", index=df.index)).astype(str).str.upper()
        df["_side"] = df.get("side", pd.Series("", index=df.index)).astype(str).str.upper()
        df["_usd"] = pd.to_numeric(df.get("notional"), errors="coerce").fillna(0.0)
        trades = df[df["_type"].eq("TRADE")]
        labels = _classify_titles([_text(v) for v in trades.get("title", pd.Series("", index=trades.index)).tolist()], classify)
        for label, side, usd in zip(labels, trades["_side"].tolist(), trades["_usd"].tolist()):
            slot = _slot(label)
            slot["trades"] += 1
            if side == "BUY":
                slot["stake"] += float(usd)
    if resolved is not None and not resolved.empty:
        markets = trec.market_records(resolved)
        titles: dict[str, str] = {}
        if "market_key" in resolved and "title" in resolved:
            for key, title in zip(resolved["market_key"].tolist(), resolved["title"].tolist()):
                titles.setdefault(_text(key), _text(title))
        labels = _classify_titles([titles.get(_text(k), "") for k in markets["market_key"].tolist()], classify)
        for label, pnl in zip(labels, markets["net_pnl"].tolist()):
            slot = _slot(label)
            slot["pnl"] += float(pnl)
            slot["resolved_markets"] += 1
    rows = sorted(stake.values(), key=lambda r: (-r["stake"], -r["trades"]))
    for row in rows:
        row["stake"] = round(row["stake"], 2)
        row["pnl"] = round(row["pnl"], 2)
    return {
        "as_of": as_of,
        "rows": rows,
        "classifier": "market_filter_category, then the insider-context title patterns (app.suspicion)",
        "note": "Stake = BUY notional in the activity window; PnL = settled PnL of resolved markets, netted per market.",
    }


def _wallet_context(activity: pd.DataFrame | None, as_of: str) -> dict[str, Any]:
    if activity is None or activity.empty:
        return {"as_of": as_of, "n_trades": 0, "notional": 0.0, "groups": [], "insider_prone_share": None,
                "excluded_share": None, "note": "No trades in the activity window to classify."}
    df = activity.copy()
    df["_type"] = df.get("type", pd.Series("", index=df.index)).astype(str).str.upper()
    df["_usd"] = pd.to_numeric(df.get("notional"), errors="coerce").fillna(0.0)
    trades = df[df["_type"].eq("TRADE")]
    totals: dict[str, dict[str, Any]] = {}
    for title, usd in zip(trades.get("title", pd.Series("", index=trades.index)).tolist(), trades["_usd"].tolist()):
        group, _mult, note = susp.classify_insider_context(_text(title), "")
        slot = totals.setdefault(group, {"group": group, "notional": 0.0, "trades": 0, "note": note,
                                         "insider_prone": group in susp.INSIDER_PRONE_GROUPS})
        slot["notional"] += float(usd)
        slot["trades"] += 1
    notional = float(trades["_usd"].sum())
    groups = sorted(totals.values(), key=lambda g: -g["notional"])
    for g in groups:
        g["notional"] = round(g["notional"], 2)
        g["share"] = round(g["notional"] / notional, 4) if notional > 0 else None
    prone = sum(g["notional"] for g in groups if g["insider_prone"])
    return {
        "as_of": as_of,
        "n_trades": int(len(trades)),
        "notional": round(notional, 2),
        "groups": groups,
        "insider_prone_share": round(prone / notional, 4) if notional > 0 else None,
        "excluded_share": round(1.0 - prone / notional, 4) if notional > 0 else None,
        "note": ("Share of traded notional by insider-plausibility group (app.suspicion.classify_insider_context). "
                 "Sports odds, weather and crypto/market prices are the groups the risk screen excludes."),
    }


def wallet_detail(
    card: Mapping[str, Any],
    positions: pd.DataFrame | None = None,
    pnl_points: pd.DataFrame | None = None,
    activity: pd.DataFrame | None = None,
    *,
    resolved: pd.DataFrame | None = None,
    resolved_capped: bool | None = None,
    activity_truncated: bool = False,
    classify: Callable[[Any, Any], Any] | None = None,
    pseudonym: str = "",
    as_of: str = "",
    pnl_window: str = "All",
    positions_requested: int = 250,
) -> dict[str, Any]:
    """Scorecard + offene Positionen + PnL-Kurve + letzte Trades als JSON.

    Die alten Schluessel (``track``, ``pnl_curve``, ``positions`` als Liste,
    ``recent_trades`` …) bleiben, die Detail-Lade liest sie. Dazu kommen die
    Bloecke der Wallet-Seite: ``identity``, ``track_record``, ``pnl``,
    ``edge``, ``open_positions``, ``closed``, ``activity``, ``categories``,
    ``context``, ``limits`` — jeder mit ``as_of`` und seinen Stichproben- und
    ``capped``/``window_truncated``-Angaben. ``resolved`` ist der Frame, aus
    dem die Scorecard gerechnet wurde (beide Tails); ohne ihn bleiben die
    Bloecke, die ihn brauchen, leer statt geraten.
    """

    wallet = _text(card.get("wallet"))
    track = card.get("track") if isinstance(card.get("track"), Mapping) else None
    capped = bool(resolved_capped) if resolved_capped is not None else bool(track and track.get("resolved_capped"))
    stamp = as_of or _text(card.get("snapshot_at"))
    payload: dict[str, Any] = {
        "wallet": wallet,
        "snapshot_at": card.get("snapshot_at"),
        "as_of": stamp,
        "track": track,
        "calibration": _strip_frames(card.get("calibration")),
        "realized_edge": card.get("realized_edge"),
        "attribution": card.get("attribution"),
        "smart": card.get("smart"),
        "risk": card.get("risk"),
        "sample": card.get("sample"),
        "errors": card.get("errors", {}),
    }
    if pnl_points is not None and not pnl_points.empty and "pnl" in pnl_points:
        payload["pnl_curve"] = [v for v in (_num(x) for x in pnl_points["pnl"].tolist()) if v is not None]
    if positions is not None and not positions.empty:
        payload["positions"] = [
            {
                "market": _text(row.get("title")),
                "outcome": _text(row.get("outcome")),
                "size": _num(row.get("size")),
                "avg_price": _num(row.get("avg_price")),
                "current_price": _num(row.get("current_price")),
                "value": _num(row.get("value")),
                "unrealized_pnl": _num(row.get("unrealized_pnl")),
            }
            for _, row in positions.head(25).iterrows()
        ]
    if activity is not None and not activity.empty:
        recent = activity
        if "type" in activity:
            only_trades = activity[activity["type"].astype(str).str.upper().eq("TRADE")]
            recent = only_trades if not only_trades.empty else activity
        payload["recent_trades"] = [
            {
                "market": _text(row.get("title")),
                "side": (_text(row.get("side")).upper() or "BUY") + " " + (_text(row.get("outcome")) or "Yes"),
                "price": f"{(_num(row.get('price'), 0.0) or 0.0) * 100:.1f}¢",
                "ago": _text(row.get("time"))[:16].replace("T", " "),
                "size": _num(row.get("notional"), 0.0),
            }
            for _, row in recent.head(6).iterrows()
        ]

    realized = card.get("realized_edge") if isinstance(card.get("realized_edge"), Mapping) else None
    open_block = _wallet_positions(positions, stamp, positions_requested)
    payload["identity"] = _wallet_identity(wallet, activity, pseudonym, activity_truncated)
    payload["track_record"] = _wallet_track_record(track, resolved, capped, stamp)
    payload["pnl"] = _wallet_pnl(pnl_points, stamp, pnl_window, resolved, capped)
    payload["edge"] = _wallet_edge(resolved, realized, capped, classify, stamp)
    payload["open_positions"] = open_block
    payload["closed"] = _wallet_closed(resolved, capped, open_block["worthless_n"], stamp,
                                       _text(track.get("coverage_note")) if track else "")
    payload["activity"] = _wallet_activity(activity, activity_truncated, stamp)
    payload["risk_profile"] = _wallet_risk_profile(resolved, capped, activity, stamp)
    if activity_truncated and payload["risk_profile"]["heatmap"]["n"]:
        payload["risk_profile"]["heatmap"]["note"] += " — the window was truncated at the page cap"
    payload["categories"] = _wallet_categories(activity, resolved, classify, stamp)
    payload["context"] = _wallet_context(activity, stamp)
    payload["limits"] = list(WALLET_LIMITS)
    return payload


def _strip_frames(block: Any) -> Any:
    """DataFrames (z.B. Kalibrierungs-Buckets) JSON-tauglich machen."""

    if not isinstance(block, Mapping):
        return block
    out: dict[str, Any] = {}
    for key, value in block.items():
        if isinstance(value, pd.DataFrame):
            out[key] = value.where(value.notna(), None).to_dict(orient="records")
        else:
            out[key] = value
    return out


#: Ehrlichkeits-Schranke fuer Cross-Venue-Paare. Studie 08 und 11 in
#: public/data/microstructure.json haben gezeigt, dass die beiden 79¢/64¢
#: "Kanten" verschiedene Fragen waren; unter 0.5 Aehnlichkeit ist ein Paar
#: eine Vermutung, und ohne Volumen auf beiden Seiten gibt es keinen Preis,
#: den man vergleichen koennte.
CROSS_MIN_SIMILARITY = 0.5


def cross_rows(
    candidates: pd.DataFrame,
    categories: Mapping[str, str] | None = None,
    *,
    min_similarity: float = CROSS_MIN_SIMILARITY,
    require_volume: bool = True,
) -> list[dict[str, Any]]:
    """`md.cross_venue_candidates`-Frame in die Frontend-Paar-Zeilen.

    ``categories`` mappt Polymarket ``market_key`` auf eine Kategorie, damit
    die Zeile die echte Markt-Kategorie statt eines Platzhalters traegt.
    Es bleiben nur Paare mit ``similarity >= min_similarity`` und — bei
    ``require_volume`` — mit Volumen groesser null auf beiden Venues.

    ``gross``/``band``/``net`` sind Cent je Stueck und kommen aus
    ``app/cross_pairs.py``: die ausfuehrbare Spanne (Brief gegen Geld, nicht
    Mitte gegen Mitte), die Gebuehrenschwelle beider Venues und was danach
    bleibt. Ohne beidseitige Quote bleiben sie ``None``, damit das Frontend
    einen Strich zeigen kann statt einer gemessenen Null.

    ``pmVolUsd`` sind Dollar, ``ksVolContracts`` sind Kontrakte. Die beiden
    hiessen einmal ``pmVol`` und ``ksVol``, und das Frontend hat sie addiert.
    Sie sind nicht addierbar (Beleg in ``app/venue_units.py``).
    """

    if candidates is None or candidates.empty:
        return []
    categories = categories or {}
    rows: list[dict[str, Any]] = []
    for _, row in candidates.iterrows():
        pm_yes = _num(row.get("polymarket_yes"))
        ks_yes = _num(row.get("kalshi_yes"))
        if pm_yes is None or ks_yes is None:
            continue
        sim = _num(row.get("similarity"), 0.0) or 0.0
        if sim < float(min_similarity):
            continue
        pm_vol = _num(row.get("polymarket_volume_usd"), 0.0) or 0.0
        ks_vol = _num(row.get("kalshi_volume_contracts"), 0.0) or 0.0
        if require_volume and (pm_vol <= 0 or ks_vol <= 0):
            continue
        pm_key = _text(row.get("polymarket_market_key"))
        rows.append({
            "event": _text(row.get("polymarket_title")) or _text(row.get("kalshi_title")),
            "cat": (_text(categories.get(pm_key)) or "PAIR").upper(),
            "pm": round(pm_yes * 100),
            "ks": round(ks_yes * 100),
            # Zwei Schluessel, zwei Einheiten. Polymarket meldet Dollar,
            # Kalshi Kontrakte; das Frontend darf sie nicht in eine Zahl
            # legen, also stehen sie hier nicht unter einem gemeinsamen
            # Namen (Beleg in app/venue_units.py).
            "pmVolUsd": pm_vol,
            "ksVolContracts": ks_vol,
            "sim": round(sim, 2),
            "gross": _num(row.get("gross_edge_cents")),
            "band": _num(row.get("fee_band_cents")),
            "net": _num(row.get("net_edge_cents")),
            "dir": _text(row.get("edge_direction")),
            "pm_url": _text(row.get("polymarket_url")),
            "ks_url": _text(row.get("kalshi_url")),
        })
    return rows


#: Wie viele Event-Karten der Risk-Screen zeigt (und loggt).
RISK_EVENT_LIMIT = 12


def _iso(value: Any) -> str:
    """Zeitstempel als ISO-8601 UTC ('' wenn leer/ungueltig)."""

    stamp = pd.to_datetime(value, utc=True, errors="coerce")
    if stamp is None or pd.isna(stamp):
        return ""
    return stamp.strftime("%Y-%m-%dT%H:%M:%SZ")


def _image_url(value: Any) -> str:
    """The market image URL as the public feed carries it — only an absolute
    https URL passes; anything else renders as no image."""

    text = _text(value).strip()
    return text if text.startswith("https://") else ""


def market_url(venue: str, market_key: str, url: str = "", slug: str = "") -> str:
    """Direkter Link zum Markt: Polymarket-Event-Slug oder Kalshi-Ticker.

    Bevorzugt die URL, die die Trades tragen (Polymarket-Trades fuehren den
    Event-Slug); ohne sie den Markt-Slug; bei Kalshi den Ticker. Kein Link
    ist besser als ein geratener.
    """

    url = _text(url).strip()
    # A print without eventSlug leaves "https://polymarket.com/event/" behind:
    # a link to nothing. Fall through to the slug or nothing at all.
    if url.startswith("http") and not url.rstrip("/").endswith("/event"):
        return url
    slug = _text(slug).strip()
    if slug:
        return f"https://polymarket.com/event/{slug}"
    key = _text(market_key).strip()
    if str(venue).lower() == "kalshi" and key:
        return f"https://kalshi.com/markets/{key}"
    return ""


def wallet_profile_url(venue: str, wallet: str) -> str:
    address = _text(wallet).strip()
    if str(venue).lower() == "polymarket" and address.startswith("0x"):
        return f"https://polymarket.com/profile/{address}"
    return ""


def _split_from_row(row: Any) -> dict[str, float]:
    return {
        key: round(_num(row.get(f"side_{key}"), 0.0) or 0.0, 2)
        for key, _label in susp.SIDE_BUCKETS
    }


def risk_event_row(row: Any) -> dict[str, Any]:
    """Eine Event-Zeile des Risk-Screens mit Seite, Preis, Wallets, Fenster, Komponenten.

    Felder ohne Messung bleiben ``None`` bzw. leer (Preis ohne Prints,
    Wallets auf Kalshi, Komponenten eines aelteren Frames) — die Oberflaeche
    sagt dann "n/a" statt eine Zahl zu erfinden.
    """

    flags = row.get("event_insider_flags") or row.get("event_risk_reasons") or []
    if isinstance(flags, str):
        # Der Score-Kern liefert die Flags als "; "-Kette; hier werden sie zu
        # einzelnen Eintraegen, damit die Karte eine Art nennt und die Liste
        # der Gruende getrennt zeigt. "watch only" ist kein Flag.
        flags = [part.strip() for part in flags.split(";") if part.strip() and part.strip() != susp.WATCH_ONLY]
    level = _text(row.get("event_insider_level") or row.get("event_risk_level")).lower()
    venue = _text(row.get("platform")) or "Polymarket"
    # Kalshi prints carry the ticker, not a market_key; the ticker IS the key.
    market_key = _text(row.get("market_key")) or _text(row.get("ticker")) or (
        _text(row.get("title")) if venue.lower() == "kalshi" else "")
    notional = _num(row.get("notional"), 0.0) or 0.0
    top_wallets_raw = row.get("top_wallets")
    top_wallets: list[dict[str, Any]] = []
    if isinstance(top_wallets_raw, (list, tuple)):
        for item in top_wallets_raw:
            if not isinstance(item, dict):
                continue
            address = _text(item.get("wallet"))
            fresh = item.get("fresh")
            top_wallets.append({
                "wallet": address,
                "short": short_wallet(address),
                "notional": round(_num(item.get("notional"), 0.0) or 0.0, 2),
                "share": round(_num(item.get("share"), 0.0) or 0.0, 4),
                "side": _text(item.get("side")),
                "fresh": bool(fresh) if fresh is not None else None,
                "url": wallet_profile_url(venue, address),
            })
    window_minutes = _num(row.get("window_minutes"))
    # Position jedes Prints im Fenster (0..1, von event_flow_details): die
    # Karte zeichnet daraus die Tick-Leiste. Fehlt die Spalte (aelterer
    # Frame), bleibt die Liste leer und die Karte zeigt nur den Text.
    offsets_raw = row.get("print_offsets")
    print_offsets = (
        [round(_num(value, 0.0) or 0.0, 4) for value in offsets_raw]
        if isinstance(offsets_raw, (list, tuple)) else []
    )
    return {
        "kind": (_text(flags[0]).upper() if flags else "EVENT SCREEN"),
        "score": round(_num(row.get("event_insider_score") or row.get("event_risk_score"), 0.0) or 0.0),
        "market": _text(row.get("title")),
        "market_key": market_key,
        "url": market_url(venue, market_key, _text(row.get("url")), _text(row.get("slug"))),
        "detail": " · ".join(_text(f) for f in flags) or "No individual flags — score from combined components.",
        "flags": [_text(f) for f in flags],
        "wallets": int(_num(row.get("unique_wallets"), 0.0) or 0),
        "notional": f"${notional / 1000:.0f}k",
        "notional_usd": round(notional, 2),
        "window": f"{(_num(row.get('trades_per_hour'), 0.0) or 0.0):.1f}/h",
        "venue": venue,
        "sev": "high" if level == "high" else "medium" if level == "medium" else "low",
        "category": _text(row.get("insider_context")),
        "context_note": _text(row.get("context_note")),
        "side": _text(row.get("side")),
        "side_notional": round(_num(row.get("side_notional"), 0.0) or 0.0, 2),
        "side_share": round(_num(row.get("side_share"), 0.0) or 0.0, 4),
        "side_split": _split_from_row(row),
        "price_outcome": _text(row.get("price_outcome")),
        "price_first": _num(row.get("price_first")),
        "price_last": _num(row.get("price_last")),
        "price_min": _num(row.get("price_min")),
        "price_max": _num(row.get("price_max")),
        "first_print": _iso(row.get("first_print")),
        "last_print": _iso(row.get("last_print")),
        "window_minutes": round(window_minutes, 1) if window_minutes is not None else None,
        "print_offsets": print_offsets,
        "prints": int(_num(row.get("trades"), 0.0) or 0),
        "top_wallets": top_wallets,
        "components": susp.event_components(row),
        "token_id": _text(row.get("token_id")),
    }


def risk_payload(
    wallet_scores: pd.DataFrame,
    event_scores: pd.DataFrame,
    min_event_score: float | None = None,
) -> dict[str, Any]:
    """Whale-Risk-Frames in Events-Karten + Wallet-Tabelle + KPIs.

    Karten gibt es nur ab der Flag-Schwelle des Logs (``risk_log.min_score()``,
    Standard 40): der Scorer bewertet JEDEN Markt mit einem Print im Tape, und
    ohne Boden fuellten "0/100"-Zeilen das Grid auf, sobald das gefilterte Tape
    duenn war. Was unter der Schwelle liegt, wird gezaehlt statt gezeigt
    (``events_below_min``) — dieselbe Definition von "Flag" wie im Log.

    Disclaimer gehoert zur Antwort: Best-effort-Screen auf oeffentlichen
    Daten, Research-Leads, keine Rechtsfeststellung.
    """

    threshold = float(min_event_score) if min_event_score is not None else risk_log.min_score()
    events: list[dict[str, Any]] = []
    events_screened = 0
    events_below_min = 0
    if event_scores is not None and not event_scores.empty:
        events_screened = int(len(event_scores))
        for _, row in event_scores.iterrows():
            score = _num(row.get("event_insider_score") or row.get("event_risk_score"), 0.0) or 0.0
            if score < threshold:
                events_below_min += 1
            elif len(events) < RISK_EVENT_LIMIT:
                events.append(risk_event_row(row))
    wallets: list[dict[str, Any]] = []
    if wallet_scores is not None and not wallet_scores.empty:
        for _, row in wallet_scores.head(20).iterrows():
            score = _num(row.get("wallet_insider_score") or row.get("wallet_risk_score"), 0.0) or 0.0
            # The plain-language reasons the scorer recorded ("long-odds big
            # bet; late-market flow") — without them the row is a bare number
            # nobody can check. "watch only" means no pattern fired.
            flags = [t.strip() for t in _text(row.get("wallet_insider_flags") or row.get("wallet_risk_reasons")).split(";") if t.strip()]
            largest = _num(row.get("largest_trade"), 0.0) or 0.0
            wallets.append({
                "wallet": _text(row.get("trader")) or short_wallet(row.get("wallet")),
                # The full address, so the wallet page can be opened from the row.
                "address": _text(row.get("wallet")),
                "context": _text(row.get("top_market"))[:60] or "—",
                "score": round(score),
                "flags": flags,
                "prints": int(_num(row.get("trade_count"), 0.0) or 0),
                # money_label, not a k-rounder: a $450 wallet showed as "$0k".
                "notional": money_label(_num(row.get("notional"), 0.0) or 0.0),
                "largest": money_label(largest) if largest > 0 else "",
                "firstSeen": _text(row.get("first_seen"))[:10] or "—",
            })
    high_events = sum(1 for e in events if e["sev"] == "high")
    high_wallets = sum(1 for w in wallets if w["score"] >= 70)
    return {
        "disclaimer": "Best-effort screen on public trade data — research leads, not legal findings.",
        # Was der Screen gar nicht erst anschaut (susp.EXCLUDED_CONTEXTS):
        # Sportquoten, Wetter, Krypto/Marktpreise — dort gibt es nichts
        # frueher zu wissen, und die 15-Minuten-Kryptomaerkte waeren nur Rauschen.
        "scope": "Sports odds, weather and crypto/market prices are excluded from this screen — nothing to know early there.",
        # Die Schwelle und die Zahl darunter gehen mit: die Oberflaeche sagt
        # "N weitere Maerkte unter 40 — watch only" statt Null-Karten zu zeigen.
        "event_min_score": round(threshold),
        "events_below_min": events_below_min,
        "kpis": {
            # Alle gescorten Maerkte, nicht die Kartenanzahl: vorher stand hier
            # len(events) — mit 12 Karten log die Zahl, mit Floor erst recht.
            "events_screened": events_screened,
            "events_flagged": events_screened - events_below_min,
            "high_risk_events": high_events,
            "high_risk_wallets": high_wallets,
            "fresh_clusters": 0,
            "coordinated_clusters": 0,
        },
        "events": events,
        "wallets": wallets,
    }


#: Wie viele Signalzeilen der Feed hoechstens ausliefert.
ALERT_ROW_LIMIT = 60


def alert_rule_counts(signals: pd.DataFrame) -> dict[str, int]:
    """Treffer je Signalart ueber den ganzen Frame, nicht ueber die Anzeige.

    ``alert_rows`` schneidet nach 60 Zeilen ab. Wer die Treffer aus der
    angezeigten Tabelle zaehlt, zaehlt den Schnitt mit und meldet fuer eine
    Regel null, obwohl der Scanner sie hundertfach ausgeloest hat.
    """
    if signals is None or signals.empty or "signal_type" not in signals:
        return {}
    zaehlung = signals["signal_type"].astype(str).str.upper().value_counts()
    return {str(art): int(anzahl) for art, anzahl in zaehlung.items()}


def alert_rows(signals: pd.DataFrame) -> list[dict[str, Any]]:
    """`sig.build_monitor_signals`-Frame in die Signal-Feed-Zeilen."""

    if signals is None or signals.empty:
        return []
    rows: list[dict[str, Any]] = []
    for _, row in signals.head(ALERT_ROW_LIMIT).iterrows():
        time_label = _text(row.get("time"))
        if "T" in time_label:
            time_label = time_label.split("T")[1][:5]
        elif " " in time_label:
            time_label = time_label.split(" ")[-1][:5]
        raw_value = _num(row.get("value"))
        signal_type = _text(row.get("signal_type"))
        if raw_value is None:
            notional = _num(row.get("notional"))
            value = f"${notional:,.0f}" if notional else _text(row.get("reason"))[:24]
        elif signal_type in ("Whale print",):
            value = f"${raw_value:,.0f}"
        # Nicht jede Zahl unter 1.0 ist ein Preis. Der Anteil des groessten
        # Halters stand als "62.0¢" da, obwohl er 62 Prozent bedeutet, und
        # das Volumenverhaeltnis stand ohne Einheit neben Cent-Werten.
        elif signal_type == "Holder concentration":
            value = f"{raw_value * 100:.0f}%"
        elif signal_type == "Volume anomaly":
            value = f"{raw_value:,.1f}x"
        elif abs(raw_value) <= 1.0:
            value = f"{raw_value * 100:+.1f}¢" if signal_type == "Fast mover" else f"{raw_value * 100:.1f}¢"
        else:
            value = f"{raw_value:,.1f}"
        rows.append({
            "time": time_label or "—",
            "rule": _text(row.get("signal_type")).upper(),
            "market": _text(row.get("title")),
            "value": value,
            "venue": _text(row.get("platform")) or "Polymarket",
            "watched": _text(row.get("signal_type")) == "Watched market",
        })
    return rows


#: What a paper order row *is*, from its source side and reason. The source
#: side of a settlement row is the activity type (MERGE, REDEEM), of a
#: resolution row the synthetic reason; a bare "MERGE Yes" in the list read
#: like a bet on YES when it was the opposite — both sides handed back for
#: cash. The kind and the sentence say what happened, in words.
ORDER_KINDS: dict[str, tuple[str, str]] = {
    "BUY": ("BUY", "the source bought {outcome}; the copy scaled it into the sub-account"),
    "SELL": ("SELL", "the source sold {outcome}; the copy sold the same share of its position"),
    "MERGE": (
        "MERGE",
        "the source handed equal YES + NO shares back to the venue for $1 each — that closes exposure on both sides "
        "(a hedge unwound or an exit), it is not a bet on {outcome}",
    ),
    "REDEEM": ("REDEEM", "the market resolved; the source redeemed its winning shares for cash"),
    "SPLIT": ("SPLIT", "the source split cash into equal YES + NO shares (no direction yet)"),
    "CONVERT": ("CONVERT", "the source converted shares between outcomes of a multi-outcome market"),
}


def order_kind(row: Mapping[str, Any]) -> tuple[str, str]:
    """Kind label and explanation for one paper_orders row."""

    reason = _text(row.get("reason")).lower()
    outcome = _text(row.get("outcome")) or "Yes"
    if reason.startswith("resolution_winner"):
        return "RESOLUTION", f"the market resolved for {outcome}; the paper position paid out $1 a share"
    if reason.startswith("resolution_loser"):
        return "RESOLUTION", f"the market resolved against {outcome}; the paper position went to zero"
    if reason.startswith("redeem"):
        return "REDEEM", ORDER_KINDS["REDEEM"][1]
    if reason == "seed_position":
        return "SEED", (
            "follow started: the source already held this position, so the copy bought it at the current price, "
            "scaled like every later order — without it the source's exits could not be mirrored"
        )
    side = _text(row.get("source_side")).upper() or _text(row.get("copy_side")).upper() or "BUY"
    label, sentence = ORDER_KINDS.get(side, (side, "source activity of type " + side))
    return label, sentence.format(outcome=outcome)


def _source_book_index(source_positions: pd.DataFrame | None) -> dict[tuple[str, str], dict[str, float]]:
    """(wallet, market_key) -> {yes, no} shares the source holds now, from the
    engine's mirror of the source wallets' books (source_positions)."""

    index: dict[tuple[str, str], dict[str, float]] = {}
    if source_positions is None or source_positions.empty:
        return index
    for _, row in source_positions.iterrows():
        wallet = _text(row.get("wallet")).lower()
        market_key = _text(row.get("market_key"))
        shares = _num(row.get("shares"), 0.0) or 0.0
        if not wallet or not market_key or shares <= 0:
            continue
        outcome = _text(row.get("outcome")).upper()
        entry = index.setdefault((wallet, market_key), {"yes": 0.0, "no": 0.0})
        if outcome == "YES":
            entry["yes"] += shares
        elif outcome == "NO":
            entry["no"] += shares
    return index


def source_book_line(book: Mapping[str, float] | None) -> str:
    """"his book now: 12.0k NO / 0 YES → net NO" from a {yes, no} entry."""

    if not book:
        return ""
    yes = float(book.get("yes", 0.0) or 0.0)
    no = float(book.get("no", 0.0) or 0.0)
    if yes <= 0 and no <= 0:
        return "source book now: flat in this market"

    def fmt(v: float) -> str:
        return f"{v / 1000:.1f}k" if v >= 1000 else f"{v:.0f}"

    larger = max(yes, no)
    net = "balanced" if abs(yes - no) <= 0.10 * larger else ("net YES" if yes > no else "net NO")
    return f"source book now: {fmt(yes)} YES / {fmt(no)} NO → {net}"


def _usd_compact(value: Any) -> str:
    """Dollar label that keeps cents while they are the whole story.

    A $1k sub-account copying a whale at the neutral ratio trades pennies;
    whole-dollar rounding showed every one of those fills as "$0" and the
    Orders tab looked broken. Small amounts keep two decimals, sub-half-cent
    fills say "<$0.01" (only an exact zero shows "$0"), large amounts stay
    thousands-grouped without decimals.
    """
    v = float(_num(value, 0.0) or 0.0)
    if v == 0.0:
        return "$0"
    if abs(v) < 0.005:
        return "<$0.01"
    if abs(v) < 100:
        return f"${v:,.2f}"
    return f"${v:,.0f}"


def copy_payload(
    orders: pd.DataFrame,
    positions: pd.DataFrame,
    cash_events: pd.DataFrame,
    equity_snapshots: pd.DataFrame,
    portfolio: Mapping[str, Any],
    contributions: float,
    source_wallet: str,
    source_label: str,
    sizing: Mapping[str, Any] | None = None,
    source_positions: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """SQLite-Zustand des Copy-Traders in die Copy/Portfolio-Seiten.

    Jede Order-Zeile traegt ``wallet`` (die Quell-Wallet, klein geschrieben),
    jede Positions- und Kassenzeile die Wallet als letztes Listenelement — so
    kann die Seite nach Trader filtern, ohne dass die aelteren Spalten
    wandern. Die Zaehler in ``kpis`` gehen ueber alle Orders, nicht nur ueber
    die gezeigten Zeilen. Mit ``source_positions`` (Spiegel der Quell-Buecher)
    traegt jede Order-Zeile den aktuellen Bestand der Quelle in dem Markt.
    """

    order_rows: list[dict[str, Any]] = []
    copied = skipped = 0
    total_orders = 0
    books = _source_book_index(source_positions)
    if orders is not None and not orders.empty:
        total_orders = int(len(orders))
        if "status" in orders:
            status_all = orders["status"].astype(str)
            copied = int(status_all.eq("copied").sum())
            skipped = int(status_all.eq("skipped").sum())
        for _, row in orders.head(200).iterrows():
            status = _text(row.get("status")) or "copied"
            time_label = _text(row.get("source_time") or row.get("created_at"))
            if "T" in time_label:
                time_label = time_label.split("T")[1][:5]
            side = (_text(row.get("copy_side") or row.get("source_side")).upper() or "BUY") + " " + (_text(row.get("outcome")) or "Yes")
            kind, explain = order_kind(row)
            wallet = _text(row.get("source_wallet")).lower()
            book = books.get((wallet, _text(row.get("market_key"))))
            order_rows.append({
                "time": time_label or "—",
                "market": _text(row.get("title")),
                "side": side,
                "kind": kind,
                "outcome": _text(row.get("outcome")) or "Yes",
                "explain": explain,
                "book": source_book_line(book),
                "shares": round(_num(row.get("source_size"), 0.0) or 0.0, 2),
                "price": _num(row.get("source_price")),
                "realized": round(_num(row.get("realized_pnl"), 0.0) or 0.0, 2),
                "theirs": _usd_compact(row.get("source_notional")),
                "yours": _usd_compact(row.get("copy_notional")),
                "status": status,
                "reason": _text(row.get("reason")),
                "wallet": wallet,
                "at": _text(row.get("source_time") or row.get("created_at")),
            })
    position_rows: list[list[Any]] = []
    if positions is not None and not positions.empty:
        for _, row in positions.head(60).iterrows():
            shares = _num(row.get("size") or row.get("shares"), 0.0) or 0.0
            avg = _num(row.get("avg_price"), 0.0) or 0.0
            mark = _num(row.get("current_price") or row.get("mark_price") or row.get("last_price"), avg) or avg
            value = shares * mark
            pnl = value - shares * avg
            position_rows.append([
                _text(row.get("title")),
                _text(row.get("outcome")) or "Yes",
                f"{shares:.1f}",
                f"{avg:.3f}",
                f"{mark:.3f}",
                f"${value:.2f}",
                ("+" if pnl >= 0 else "-") + f"${abs(pnl):.2f}",
                _text(row.get("trader_wallet") or row.get("wallet")).lower(),
            ])
    cash_rows: list[list[Any]] = []
    if cash_events is not None and not cash_events.empty:
        for _, row in cash_events.head(40).iterrows():
            amount = _num(row.get("amount"), 0.0) or 0.0
            cash_after = _num(row.get("cash_after"))
            cash_rows.append([
                _text(row.get("event_time") or row.get("created_at") or row.get("time"))[:10],
                _text(row.get("reason") or row.get("kind")) or "Cash event",
                ("+" if amount >= 0 else "-") + f"${abs(amount):,.2f}",
                f"${cash_after:,.2f}" if cash_after is not None else "",
                _text(row.get("trader_wallet")).lower(),
            ])
    history_rows: list[list[Any]] = []
    if orders is not None and not orders.empty:
        settled = orders[orders.get("status").astype(str) == "settled"] if "status" in orders else orders.iloc[0:0]
        for _, row in settled.head(30).iterrows():
            pnl = _num(row.get("realized_pnl"), 0.0) or 0.0
            entry = _num(row.get("copy_price"), 0.0) or 0.0
            history_rows.append([
                _text(row.get("source_time") or row.get("created_at"))[:10],
                _text(row.get("title")),
                (_text(row.get("outcome")) or "Yes").upper(),
                f"{entry * 100:.0f}¢",
                "—",
                ("+" if pnl >= 0 else "-") + f"${abs(pnl):,.2f}",
            ])
    curve: list[float] = []
    if equity_snapshots is not None and not equity_snapshots.empty:
        col = "equity" if "equity" in equity_snapshots else None
        if col:
            curve = [v for v in (_num(x) for x in equity_snapshots[col].tolist()) if v is not None]
    equity = _num(portfolio.get("equity"), 0.0) or 0.0
    cash = _num(portfolio.get("cash"), 0.0) or 0.0
    contributions = _num(contributions, 0.0) or 0.0
    pnl = equity - contributions
    total = total_orders
    fidelity = round(copied / total * 100) if total else 100
    scale = _num((sizing or {}).get("effective_copy_scale"), 1.0) or 1.0
    return {
        "status": {
            "running": True,
            "source": f"{short_wallet(source_wallet)} · {source_label}",
            "scale": scale,
            "cash": cash,
            "auto_topup": False,
        },
        "kpis": {
            "equity": equity,
            "contributions": contributions,
            "pnl": pnl,
            "pnl_pct": (pnl / contributions * 100) if contributions else 0.0,
            "source_return_pct": 0.0,
            "mirrored": copied,
            "total": total,
            "skipped": skipped,
            "fidelity": fidelity,
            "config_fidelity": fidelity,
            "exec_fidelity": fidelity,
            "cash": cash,
            "unrealized": _num(portfolio.get("unrealized_pnl"), 0.0) or 0.0,
            "open_positions": len(position_rows),
        },
        "orders": order_rows,
        "positions": position_rows,
        "cash_events": cash_rows,
        "history": history_rows,
        "equity_curve": curve,
    }


def backtest_payload(result: Any) -> dict[str, Any]:
    """`btr.BacktestResult` in die Backtester-Ansicht (inkl. Caveats)."""

    stats = dict(result.stats or {})
    equity_df: pd.DataFrame = result.equity
    payload: dict[str, Any] = {
        "stats": {
            "final_equity": _num(stats.get("final_equity"), 0.0),
            "roi": _num(stats.get("roi"), 0.0),
            "total_pnl": _num(stats.get("total_pnl"), 0.0),
            "win_rate": _num(stats.get("win_rate"), 0.0),
            "wins": int(_num(stats.get("wins"), 0.0) or 0),
            "losses": int(_num(stats.get("losses"), 0.0) or 0),
            "max_drawdown": _num(stats.get("max_drawdown"), 0.0),
            "copied_trades": int(_num(stats.get("copied_trades"), 0.0) or 0),
            # Der Nenner der Trefferquote: geschlossene Kopien (SELL und
            # RESOLVE). Ohne ihn rechnete die Oberflaeche wins/copied_trades
            # und liess jede noch offene Kopie die Quote druecken.
            "closed_trades": int(_num(stats.get("closed_trades"), 0.0) or 0),
            "skipped_trades": int(_num(stats.get("skipped_trades"), 0.0) or 0),
            "fees_paid": _num(stats.get("fees_paid"), 0.0),
            "open_value": _num(stats.get("open_value"), 0.0),
            # Wie viel des Gesamtergebnisses noch gar nicht entschieden ist:
            # Positionen in Maerkten, die am Fensterende offen waren, gehen
            # zum letzten Preis in total_pnl ein.
            "realized_pnl": _num(stats.get("realized_pnl"), 0.0),
            "unrealized_pnl": _num(stats.get("unrealized_pnl"), 0.0),
            "open_positions": int(_num(stats.get("open_positions"), 0.0) or 0),
            "window_truncated": bool(stats.get("window_truncated", False)),
            # Bis wohin die Daten wirklich zurueckreichen. Bei einem
            # abgeschnittenen Fenster ist das die ehrliche Fensterkante.
            "effective_start": _text(stats.get("effective_start"))[:10],
            # Gemessene Skip-Gruende (Kasse leer, Exposure-Deckel, fremder
            # Verkauf, kaputte Zeile) — die Seite nennt die Anteile statt
            # einer nackten Summe.
            "skip_reasons": {
                key: int(_num(value, 0.0) or 0)
                for key, value in (stats.get("skip_reasons") or {}).items()
            },
            # Bewusst nicht gefolgte Trades (Folge-Schwelle, fremde
            # Verkaeufe) — getrennt von den echten Fehlschlaegen.
            "filtered_trades": int(_num(stats.get("filtered_trades"), 0.0) or 0),
            # Auto-Fit: was die Engine gemessen und ggf. angewendet hat —
            # Modus (Folge-Schwelle oder geschrumpfter Einsatz), Einsatz je
            # Copy, Schwelle, gefolgte Positionen und das rohe Tempo der
            # Wallet (Hoechstzahl gleichzeitig offener Positionen).
            "auto_fit": {
                "applied": bool((stats.get("auto_fit") or {}).get("applied", False)),
                "mode": _text((stats.get("auto_fit") or {}).get("mode")) or None,
                "stake": _num((stats.get("auto_fit") or {}).get("stake")),
                "follow_threshold": _num((stats.get("auto_fit") or {}).get("follow_threshold")),
                "followed_positions": int(_num((stats.get("auto_fit") or {}).get("followed_positions"), 0.0) or 0),
                "capacity": int(_num((stats.get("auto_fit") or {}).get("capacity"), 0.0) or 0),
                "peak_concurrent": int(_num((stats.get("auto_fit") or {}).get("peak_concurrent"), 0.0) or 0),
                # Auto-Fit liest das ganze Fenster, bevor der erste Trade
                # kopiert wird — die Seite muss das sagen duerfen.
                "hindsight": bool((stats.get("auto_fit") or {}).get("hindsight", False)),
                "note": _text((stats.get("auto_fit") or {}).get("note")),
            },
        },
        "benchmark_stats": {
            "total_pnl": _num((result.benchmark_stats or {}).get("total_pnl"), 0.0),
        },
    }
    if equity_df is not None and not equity_df.empty:
        payload["equity"] = [v for v in (_num(x) for x in equity_df.get("equity", pd.Series(dtype=float)).tolist()) if v is not None]
        payload["benchmark"] = [v for v in (_num(x) for x in equity_df.get("benchmark", pd.Series(dtype=float)).tolist()) if v is not None]
        payload["drawdown"] = [v for v in (_num(x) for x in equity_df.get("drawdown", pd.Series(dtype=float)).tolist()) if v is not None]
        # Was die Kurve wirklich abdeckt: bei einem abgeschnittenen Fenster
        # beginnt sie an der Datenkante, nicht am angefragten Starttag. Die
        # Achsenbeschriftung darf nicht "30d ago" behaupten, wenn die erste
        # Stuetzstelle von vorgestern ist.
        zeiten = pd.to_datetime(equity_df.get("time", pd.Series(dtype="datetime64[ns, UTC]")), utc=True, errors="coerce").dropna()
        if not zeiten.empty:
            payload["curve_start"] = zeiten.min().isoformat()[:16]
            payload["curve_end"] = zeiten.max().isoformat()[:16]
    ledger: pd.DataFrame = result.ledger
    if ledger is not None and not ledger.empty:
        payload["log"] = [
            {
                "time": _text(row.get("time"))[5:16].replace("T", " "),
                "action": _text(row.get("action")),
                "status": _text(row.get("status")),
                "market": _text(row.get("title")),
                "side": _text(row.get("outcome")),
                "trader_amt": _num(row.get("source_notional"), 0.0),
                "stake": _num(row.get("stake"), 0.0),
                "fill": _num(row.get("exec_price"), 0.0),
                "fee": _num(row.get("fee"), 0.0),
                "equity": _num(row.get("equity_after"), 0.0),
            }
            for _, row in ledger.head(40).iterrows()
        ]
    open_df: pd.DataFrame = result.open_positions
    if open_df is not None and not open_df.empty:
        payload["open"] = [
            {
                "market": _text(row.get("title")),
                "side": _text(row.get("outcome")) or "Yes",
                "shares": _num(row.get("shares"), 0.0),
                "avg": _num(row.get("avg_price"), 0.0),
                "mark": _num(row.get("current_price"), 0.0),
            }
            for _, row in open_df.head(20).iterrows()
        ]
    return payload


def variants_payload(comparison: pd.DataFrame) -> list[dict[str, Any]]:
    """`btr.strategy_comparison`-Frame in die Sizing-Simulator-Zeilen."""

    if comparison is None or comparison.empty:
        return []
    return [
        {
            "name": _text(row.get("strategy")),
            "final_equity": _num(row.get("final_equity"), 0.0),
            "roi": _num(row.get("roi"), 0.0),
            "max_drawdown": _num(row.get("max_drawdown"), 0.0),
            "win_rate": _num(row.get("win_rate"), 0.0),
            "closed_trades": int(_num(row.get("closed_trades"), 0.0) or 0),
            "copied_trades": int(_num(row.get("copied_trades"), 0.0) or 0),
            "skipped_trades": int(_num(row.get("skipped_trades"), 0.0) or 0),
        }
        for _, row in comparison.iterrows()
    ]


def trim_pipeline_payload(payload: Mapping[str, Any], max_entries: int = 40) -> dict[str, Any]:
    """pipeline_forward.json ist ~800 KB — fuers Web schlank machen, nicht kappen.

    Die Seite zaehlt den Entscheidungs-Trichter ueber ALLE Laeufe; dafuer
    braucht jeder Lauf-Eintrag nur action und reason. Preise, Groessen und
    die Wortzaehler-Endstaende bleiben der publizierten Datei vorbehalten.
    Frueher flogen die Lauf-Eintraege komplett raus und der Client fiel auf
    die gekappte Spiegel-Liste EINES Laufs zurueck — die Kopfzeile sagte
    "1 von 40 Checks", die Tabelle darunter "21 Laeufe, 3.370 Checks".
    """

    out = dict(payload)
    if isinstance(out.get("eintraege"), list):
        out["eintraege"] = out["eintraege"][:max_entries]
    if isinstance(out.get("laeufe"), list):
        trimmed = []
        for lauf in out["laeufe"]:
            lauf = dict(lauf)
            if isinstance(lauf.get("eintraege"), list):
                lauf["eintraege"] = [
                    {"action": e.get("action"), "reason": e.get("reason")} if isinstance(e, Mapping) else e
                    for e in lauf["eintraege"]
                ]
            lauf.pop("wortzaehler_endstaende", None)
            trimmed.append(lauf)
        out["laeufe"] = trimmed
    out.pop("wortzaehler_endstaende", None)
    return out


def resolved_rows(closed: pd.DataFrame, limit: int = 120) -> list[dict[str, Any]]:
    """`md.get_polymarket_closed_markets`-Frame in die Resolved-Zeilen.

    Nur binaere Maerkte mit bekanntem Ausgang; ``err`` ist der letzte Preis
    gegen die Antwort — das, was die Menge falsch hatte.
    """

    if closed is None or closed.empty:
        return []
    rows: list[dict[str, Any]] = []
    now = pd.Timestamp.now(tz="UTC")
    for _, row in closed.iterrows():
        outcome = _text(row.get("resolved_outcome"))
        if outcome not in ("Yes", "No"):
            continue
        last = _num(row.get("final_yes_price"))
        if last is None:
            continue
        last_cents = round(last * 100)
        closed_ts = pd.to_datetime(row.get("closed_time"), utc=True, errors="coerce")
        hours = float((now - closed_ts).total_seconds() / 3600.0) if closed_ts is not None and not pd.isna(closed_ts) else 9999.0
        when = "—"
        if hours < 9999.0:
            when = f"{hours:.0f} h ago" if hours < 48 else f"{hours / 24:.0f} d ago"
        volume = _num(row.get("volume"), 0.0) or 0.0
        rows.append({
            "title": _text(row.get("title")),
            "meta": (_text(row.get("platform")) or "Polymarket").upper() + " · " + (_text(row.get("category")) or "—").upper(),
            "yes": outcome == "Yes",
            "last": last_cents,
            "err": (100 - last_cents) if outcome == "Yes" else last_cents,
            "vol": money_label(volume),
            "when": when,
            "hours": round(hours, 1),
            "decisive": bool(row.get("decisive_resolution")),
        })
        if len(rows) >= limit:
            break
    return rows


def money_label(value: float) -> str:
    if value >= 1_000_000:
        return f"${value / 1_000_000:.1f}m"
    if value >= 1_000:
        return f"${value / 1_000:.1f}k"
    return f"${value:.0f}"


def watchlist_market_keys(watchlist: Any) -> set[str]:
    """Die market_keys der lokal gespeicherten Watchlist.

    ``build_monitor_signals`` erzeugt "Watched market"-Signale nur fuer die
    Keys, die es hier bekommt. Der Alarm-Endpunkt uebergab eine leere Menge,
    und damit lieferte der Filter SCOPE = "Watched only" der Seite immer
    null Zeilen -- nicht weil nichts auf der Liste stand, sondern weil die
    Liste nie gelesen wurde.
    """

    keys: set[str] = set()
    for item in watchlist or []:
        if not isinstance(item, Mapping):
            continue
        key = _text(item.get("market_key")).strip()
        if key:
            keys.add(key)
    return keys


def track_payload(
    followed: list[Any],
    watchlist: list[Any],
    ranked: pd.DataFrame | None = None,
    leaderboard: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """Lokal persistierte Follows/Watchlist als JSON (read-only)."""

    lb_by_wallet: dict[str, dict[str, Any]] = {}
    if leaderboard is not None and not leaderboard.empty and "wallet" in leaderboard:
        for _, row in leaderboard.iterrows():
            lb_by_wallet[_text(row.get("wallet")).lower()] = {
                "name": _text(row.get("trader")),
                "pnl": _num(row.get("pnl")),
            }
    grade_by_wallet: dict[str, str] = {}
    if ranked is not None and not ranked.empty and "wallet" in ranked:
        for _, row in ranked.iterrows():
            grade_by_wallet[_text(row.get("wallet")).lower()] = _text(row.get("copy_grade"))
    wallets = []
    for item in followed or []:
        wallet = _text(item).strip()
        if not wallet:
            continue
        lb = lb_by_wallet.get(wallet.lower(), {})
        wallets.append({
            "wallet": wallet,
            "name": lb.get("name") or short_wallet(wallet),
            "pnl": lb.get("pnl"),
            "grade": grade_by_wallet.get(wallet.lower()) or None,
        })
    markets = []
    for item in watchlist or []:
        if not isinstance(item, Mapping):
            continue
        markets.append({
            "platform": _text(item.get("platform")),
            "market_key": _text(item.get("market_key")),
            "title": _text(item.get("title")),
            "url": _text(item.get("url")),
        })
    return {"wallets": wallets, "watchlist": markets}


def live_runs_extras(payload: Mapping[str, Any], publish_dir: Path | None = None) -> dict[str, Any]:
    """Sizing-Simulation, Kalibrierung, Timing-Decay und Monatsbilanz aus
    runs.json — dieselben Module wie die Streamlit-Seite (app/run_sim.py) —
    plus the wallet ledger from ``publish_dir`` (default public/data)."""

    from app import calibration as calib
    from app import run_sim as rsim

    out: dict[str, Any] = {}
    bets = rsim.bets_frame(dict(payload))
    if bets is not None and not bets.empty:
        sims = []
        for mode, label in ((rsim.SIM_AS_EXECUTED, "As executed"), (rsim.SIM_FIXED, "Flat $5 per bet"), (rsim.SIM_KELLY, "Kelly ¼ on +10pt edge")):
            try:
                _, summary = rsim.simulate_sizing(bets, mode, bankroll=100.0, fixed_stake=5.0, kelly_edge_pt=10.0, kelly_fraction=0.25)
            except Exception:
                continue
            sims.append({
                "name": label,
                "net": _num(summary.get("sim_pnl"), 0.0),
                "roi": _num(summary.get("sim_roi_pct"), 0.0),
                "stake": _num(summary.get("sim_stake"), 0.0),
                "bets": int(_num(summary.get("n_resolved"), 0.0) or 0),
            })
        if sims:
            out["sims"] = sims
        try:
            report = calib.calibration_report(rsim.bot_resolution_frame(bets), capped=False)
            buckets = report.get("buckets")
            rows = []
            if isinstance(buckets, pd.DataFrame) and not buckets.empty:
                for _, row in buckets.iterrows():
                    rows.append({
                        "band": _text(row.get("bucket")) or _text(row.get("band")),
                        "n": int(_num(row.get("n"), 0.0) or 0),
                        "paid": round((_num(row.get("avg_forecast"), 0.0) or 0.0) * 100),
                        "settled": round((_num(row.get("hit_rate"), 0.0) or 0.0) * 100),
                    })
            out["calibration"] = {
                "n": int(_num(report.get("n"), 0.0) or 0),
                "hit_rate": _num(report.get("hit_rate")),
                "hit_low": _num(report.get("hit_low")),
                "hit_high": _num(report.get("hit_high")),
                "brier_entry": _num(report.get("brier_entry")),
                "sample_ok": bool(report.get("sample_ok")),
                "rows": rows,
            }
        except Exception:
            pass
    try:
        decay = rsim.timing_decay_summary(dict(payload))
        if decay is not None and not decay.empty:
            out["timing_decay"] = decay.where(decay.notna(), None).to_dict(orient="records")
    except Exception:
        pass
    monthly: dict[str, dict[str, Any]] = {}
    for run in payload.get("runs", []) or []:
        for bet in run.get("wetten", []) or []:
            ts = _text(bet.get("fill_ts_utc"))
            if len(ts) < 7:
                continue
            month = ts[:7]
            slot = monthly.setdefault(
                month, {"runs": set(), "bets": 0, "stake": 0.0, "net": 0.0, "settled_bets": 0, "settled_stake": 0.0})
            slot["runs"].add(_text(run.get("profil")))
            slot["bets"] += 1
            einsatz = _num(bet.get("einsatz_usd"), 0.0) or 0.0
            slot["stake"] += einsatz
            # Der Zaehler zaehlt nur aufgeloeste Wetten, also darf der Nenner
            # nicht die noch offenen mitzaehlen: sonst druecken offene
            # Einsaetze jede Quote nach unten. ``settled_stake`` ist der
            # Einsatz, zu dem es ueberhaupt ein Ergebnis gibt.
            if bet.get("aufgeloest"):
                slot["settled_bets"] += 1
                slot["settled_stake"] += einsatz
                slot["net"] += _num(bet.get("pnl_usd"), 0.0) or 0.0
    if monthly:
        out["monthly"] = [
            {
                "month": month,
                "runs": len(slot["runs"]),
                "bets": slot["bets"],
                "stake": round(slot["stake"], 2),
                "net": round(slot["net"], 2),
                "settled_bets": slot["settled_bets"],
                "settled_stake": round(slot["settled_stake"], 2),
            }
            for month, slot in sorted(monthly.items(), reverse=True)
        ]
    # The wallet ledger (public/data/wallet_ledger.json, scripts/wallet_ledger.py)
    # rides along so the runs page shows "everything the wallet did" from the
    # same response; the static site fetches the file itself. Absent file →
    # no key, and the page names the file it is missing.
    ledger = wallet_ledger_payload(publish_dir)
    if ledger is not None:
        out["wallet_ledger"] = ledger
    return out


#: Where the published payloads live; api/server.py reads the same directory.
PUBLISH_DIR = Path(__file__).resolve().parents[1] / "public" / "data"


def wallet_ledger_payload(publish_dir: Path | None = None) -> dict[str, Any] | None:
    """public/data/wallet_ledger.json as published, or None when it is not there."""

    from app.analysis_views import load_publish_payload

    return load_publish_payload(Path(publish_dir) if publish_dir is not None else PUBLISH_DIR, "wallet_ledger.json")


def fidelity_block(orders: pd.DataFrame, portfolio: Mapping[str, Any], sizing: Mapping[str, Any]) -> dict[str, Any]:
    """Config-/Execution-Fidelity und Drift-Kosten via app/copy_fidelity."""

    from app import copy_fidelity as cfy

    out: dict[str, Any] = {}
    try:
        execution = cfy.execution_fidelity(orders, window_hours=24.0)
        if execution.get("fidelity") is not None:
            out["execution"] = {
                "fidelity": _num(execution.get("fidelity")),
                "desired": _num(execution.get("desired"), 0.0),
                "filled": _num(execution.get("filled"), 0.0),
                "orders": int(_num(execution.get("orders"), 0.0) or 0),
                "lost_to_skips": {str(k): _num(v, 0.0) for k, v in (execution.get("lost_to_skips") or {}).items()},
                "lost_to_clamps": _num(execution.get("lost_to_clamps"), 0.0),
            }
    except Exception:
        pass
    try:
        # Beide Fidelity-Zahlen sind reine Notional-Zahlen. Verzoegerung und
        # Preis gehoeren daneben, sonst liest sich "Net mirror" als Aussage
        # ueber den ganzen Nachbau.
        delay = cfy.latency_and_price_gap(orders, window_hours=24.0)
        if delay.get("n"):
            out["delay"] = {
                "orders": int(_num(delay.get("n"), 0.0) or 0),
                "median_latency_s": _num(delay.get("median_latency_s")),
                "p90_latency_s": _num(delay.get("p90_latency_s")),
                "mean_price_gap_cents": _num(delay.get("mean_price_gap_cents")),
                "models_price_impact": bool(delay.get("models_price_impact")),
                "copied_shares": _num(delay.get("copied_shares"), 0.0),
            }
    except Exception:
        pass
    try:
        source_equity = _num(sizing.get("tony_visible_equity"))
        if source_equity:
            config = cfy.config_fidelity(
                _num(portfolio.get("equity"), 0.0) or 0.0,
                source_equity,
                dynamic_enabled=str(sizing.get("dynamic_sizing_enabled", "")).lower() in ("1", "true", "yes"),
                multiplier=_num(sizing.get("dynamic_sizing_multiplier"), 1.0) or 1.0,
                scale_cap=_num(sizing.get("dynamic_scale_max"), 0.0) or 0.0,
                scale_floor=_num(sizing.get("dynamic_scale_min"), 0.0) or 0.0,
                fixed_scale=_num(sizing.get("copy_scale"), 0.01) or 0.01,
            )
            out["config"] = {
                "fidelity": _num(config.get("fidelity")),
                "factors": [[str(label), _num(ratio, 0.0)] for label, ratio in (config.get("factors") or [])],
            }
    except Exception:
        pass
    return out


def cluster_payload(
    fresh: pd.DataFrame,
    coord: pd.DataFrame,
    nodes: pd.DataFrame,
    edges: pd.DataFrame,
    story_fn: Any = None,
) -> dict[str, Any]:
    """Suspicion-Cluster (fresh/timing/network) in die Risk-Screen-Tabs."""

    out: dict[str, Any] = {}
    fresh_rows: list[dict[str, Any]] = []
    if fresh is not None and not fresh.empty:
        for _, row in fresh.head(8).iterrows():
            count = int(_num(row.get("fresh_wallets"), 0.0) or 0)
            notional = _num(row.get("fresh_notional"), 0.0) or 0.0
            side = _text(row.get("fresh_outcome")).upper()
            fresh_rows.append({
                # count, not "score": the number is how many barely-seen
                # wallets met on this side, and the page says so.
                "count": count,
                "side": side,
                "market": _text(row.get("title")),
                "venue": _text(row.get("platform")),
                "notional": money_label(notional),
                "detail": f"{count} wallets with at most two prior trades in this tape took {side or 'the same side'} for {money_label(notional)} combined.",
            })
    out["fresh"] = fresh_rows
    timing_rows: list[dict[str, Any]] = []
    if coord is not None and not coord.empty:
        for _, row in coord.head(10).iterrows():
            span = _num(row.get("coordinated_span_minutes"), 0.0) or 0.0
            timing_rows.append({
                "market": _text(row.get("title")),
                "venue": _text(row.get("platform")),
                "wallets": int(_num(row.get("coordinated_wallets"), 0.0) or 0),
                "window": f"{span:.0f} min" if span >= 1 else f"{span * 60:.0f} s",
                "span_minutes": round(span, 1),
                "side": _text(row.get("coordinated_outcome")).upper(),
                "notional": money_label(_num(row.get("coordinated_notional"), 0.0) or 0.0),
                "same": bool(_text(row.get("coordinated_outcome"))),
            })
    out["timing"] = timing_rows
    network_rows: list[dict[str, Any]] = []
    if nodes is not None and not nodes.empty and "cluster_id" in nodes:
        for cluster_id, group in nodes.groupby("cluster_id"):
            if len(group) < 2:
                continue
            cluster_edges = edges
            if edges is not None and not edges.empty:
                members = set(group["wallet"].astype(str))
                cluster_edges = edges[edges["wallet_a"].astype(str).isin(members) & edges["wallet_b"].astype(str).isin(members)]
            story = {}
            if story_fn is not None:
                try:
                    story = story_fn(group, cluster_edges) or {}
                except Exception:
                    story = {}
            # Members and shared markets ride along so the cluster card can
            # name who is in the group (clickable) and where they met —
            # the bare "C-2 · 2 wallets · $63.8k" card explained nothing.
            member_rows = [
                {"kurz": short_wallet(w), "wallet": str(w)}
                for w in group.sort_values("volume", ascending=False)["wallet"].astype(str)
            ] if "volume" in group else [
                {"kurz": short_wallet(w), "wallet": str(w)} for w in group["wallet"].astype(str)
            ]
            network_rows.append({
                "id": int(_num(cluster_id, 0.0) or 0),
                "name": f"Cluster C-{int(cluster_id) + 1}" if str(cluster_id).isdigit() else f"Cluster {cluster_id}",
                "size": int(len(group)),
                "shared": str(int(_num(group.get("shared_markets", pd.Series(dtype=float)).max(), 0.0) or 0)),
                "notional": money_label(float(pd.to_numeric(group.get("volume"), errors="coerce").fillna(0.0).sum())),
                "story": _text(story.get("headline")) or _text(story.get("pattern")) or "Co-trading pattern on shared markets.",
                "pattern": _text(story.get("pattern")),
                "members": member_rows[:8],
                "members_total": int(len(group)),
                "markets": list(story.get("markets") or [])[:3],
            })
    network_rows.sort(key=lambda r: r["size"], reverse=True)
    out["network"] = network_rows[:6]
    out["kpis_clusters"] = {"fresh_clusters": len(fresh_rows), "coordinated_clusters": len(timing_rows)}
    return out


def network_graph(
    nodes: pd.DataFrame,
    edges: pd.DataFrame,
    *,
    regel: str = "",
    modularitaet: float | None = None,
) -> dict[str, Any]:
    """Den Co-Trading-Graphen zeichenfertig machen.

    ``nodes`` muss bereits durch ``suspicion.cluster_layout`` gelaufen sein und
    x/y tragen. Kanten referenzieren Knoten ueber ihren Index, damit die
    Nutzlast klein bleibt und das Frontend nichts nachschlagen muss.

    ``regel`` beschreibt, welche Kantenregel diesen Graphen erzeugt hat. Das
    gehoert in die Nutzlast und nicht in einen festen Text im Frontend: die
    Regel faellt auf eine lockerere zurueck, wenn die strenge nichts findet,
    und ein Bild, das die falsche Regel behauptet, ist wertlos.
    """

    leer: dict[str, Any] = {"knoten": [], "kanten": [], "cluster": []}
    if nodes is None or nodes.empty or "x" not in nodes.columns:
        return leer

    index_je_wallet: dict[str, int] = {}
    knoten: list[dict[str, Any]] = []
    for position, (_, row) in enumerate(nodes.iterrows()):
        wallet = _text(row.get("wallet"))
        index_je_wallet[wallet] = position
        knoten.append({
            "wallet": wallet,
            "kurz": short_wallet(wallet),
            "x": round(_num(row.get("x"), 0.0) or 0.0, 4),
            "y": round(_num(row.get("y"), 0.0) or 0.0, 4),
            "cluster": int(_num(row.get("cluster_id"), 0.0) or 0),
            "volumen": _num(row.get("volume"), 0.0) or 0.0,
            "maerkte": int(_num(row.get("markets"), 0.0) or 0),
            "trades": int(_num(row.get("trades"), 0.0) or 0),
            "geteilt": int(_num(row.get("shared_markets"), 0.0) or 0),
        })

    kanten: list[dict[str, Any]] = []
    if edges is not None and not edges.empty:
        for _, row in edges.iterrows():
            a = index_je_wallet.get(_text(row.get("wallet_a")))
            b = index_je_wallet.get(_text(row.get("wallet_b")))
            if a is None or b is None:
                continue
            kanten.append({
                "a": a, "b": b,
                "geteilt": int(_num(row.get("shared_markets"), 0.0) or 0),
                "notional": _num(row.get("pair_notional"), 0.0) or 0.0,
            })

    cluster: list[dict[str, Any]] = []
    for cluster_id, gruppe in nodes.groupby("cluster_id"):
        volumen = float(pd.to_numeric(gruppe.get("volume"), errors="coerce").fillna(0.0).sum())
        cluster.append({
            "id": int(_num(cluster_id, 0.0) or 0),
            "name": f"C-{int(_num(cluster_id, 0.0) or 0)}",
            "groesse": int(len(gruppe)),
            "volumen": volumen,
            "volumen_label": money_label(volumen),
        })
    cluster.sort(key=lambda c: c["groesse"], reverse=True)

    xs = [k["x"] for k in knoten] or [0.0]
    ys = [k["y"] for k in knoten] or [0.0]
    ergebnis: dict[str, Any] = {
        "knoten": knoten,
        "kanten": kanten,
        "cluster": cluster,
        "spanne": {"x": [min(xs), max(xs)], "y": [min(ys), max(ys)]},
        "kennzahl": {
            "wallets": len(knoten),
            "kanten": len(kanten),
            "cluster": len(cluster),
        },
    }
    if regel:
        ergebnis["regel"] = regel
    if modularitaet is not None:
        ergebnis["kennzahl"]["modularitaet"] = round(float(modularitaet), 3)
    return ergebnis


def overlap_matrix(
    trades: pd.DataFrame,
    nodes: pd.DataFrame,
    *,
    max_wallets: int = 14,
    max_maerkte: int = 14,
) -> dict[str, Any]:
    """Wallet-mal-Markt-Raster fuer den groessten Cluster.

    Der Netzwerkgraph zeigt, wer mit wem verbunden ist. Diese Matrix zeigt
    warum: welche Wallet welchen Markt auf welcher Seite angefasst hat. Eine
    Kante im Graphen ist genau eine Zeile, die sich mit einer anderen in
    mindestens zwei Spalten trifft.

    Gefuellt wird mit dem Notional, damit sichtbar bleibt, ob eine
    Ueberschneidung Gewicht hat oder nur ein Streifschuss war.
    """

    leer: dict[str, Any] = {"wallets": [], "maerkte": [], "zellen": []}
    if nodes is None or nodes.empty or trades is None or trades.empty:
        return leer
    if "cluster_id" not in nodes.columns or "title" not in trades.columns:
        return leer

    groessen = nodes.groupby("cluster_id").size().sort_values(ascending=False)
    if groessen.empty:
        return leer
    cluster_id = groessen.index[0]
    gruppe = nodes[nodes["cluster_id"] == cluster_id]
    mitglieder = [_text(w) for w in gruppe["wallet"].astype(str)]
    if len(mitglieder) < 2:
        return leer

    teil = trades[trades["wallet"].astype(str).isin(mitglieder)].copy()
    if teil.empty:
        return leer
    teil["_seite"] = teil.get("outcome", pd.Series("", index=teil.index)).astype(str)
    teil["_schluessel"] = teil["title"].astype(str) + " | " + teil["_seite"]
    teil["_notional"] = pd.to_numeric(teil.get("notional"), errors="coerce").fillna(0.0)

    # Nur Maerkte, in denen sich mindestens zwei Wallets treffen: allein
    # gehandelte Maerkte erklaeren keine einzige Kante.
    je_markt = teil.groupby("_schluessel")["wallet"].nunique().sort_values(ascending=False)
    spalten = [k for k, n in je_markt.items() if n >= 2][:max_maerkte]
    if not spalten:
        return leer

    volumen_je_wallet = teil.groupby("wallet")["_notional"].sum().sort_values(ascending=False)
    zeilen = [w for w in volumen_je_wallet.index if _text(w) in mitglieder][:max_wallets]
    if len(zeilen) < 2:
        return leer

    summe = teil.groupby(["wallet", "_schluessel"])["_notional"].sum()
    zellen: list[list[float]] = []
    for wallet in zeilen:
        zellen.append([round(float(summe.get((wallet, spalte), 0.0)), 2) for spalte in spalten])

    cluster_nummer = int(_num(cluster_id, 0.0) or 0)
    treffer = sum(1 for reihe in zellen for wert in reihe if wert > 0)
    return {
        "cluster": f"C-{cluster_nummer}",
        "wallets": [
            {"wallet": _text(w), "kurz": short_wallet(_text(w)),
             "volumen": round(float(volumen_je_wallet.get(w, 0.0)), 2)}
            for w in zeilen
        ],
        "maerkte": [
            {
                "label": str(spalte),
                "markt": str(spalte).rsplit(" | ", 1)[0],
                "seite": str(spalte).rsplit(" | ", 1)[-1],
                "wallets": int(je_markt.get(spalte, 0)),
            }
            for spalte in spalten
        ],
        "zellen": zellen,
        "belegt": treffer,
        "felder": len(zeilen) * len(spalten),
    }


def tape_window_label(trades: pd.DataFrame) -> str:
    """Beobachtungsfenster eines Tapes als Text.

    Gehoert zu jedem Bild, das aus diesem Tape entsteht. Der oeffentliche
    Trade-Feed liefert die juengsten N Prints, und wie lange die abdecken,
    haengt an der Aktivitaet: mal Stunden, mal eine Minute. Ohne diese
    Angabe ist ein Cluster-Bild nicht einzuordnen.
    """

    if trades is None or trades.empty or "time" not in trades.columns:
        return ""
    zeiten = pd.to_datetime(trades["time"], utc=True, errors="coerce").dropna()
    if zeiten.empty:
        return ""
    von, bis = zeiten.min(), zeiten.max()
    minuten = (bis - von).total_seconds() / 60.0
    if minuten < 1:
        spanne = f"{(bis - von).total_seconds():.0f} s"
    elif minuten < 90:
        spanne = f"{minuten:.0f} min"
    else:
        spanne = f"{minuten / 60:.1f} h"
    return f"{von.strftime('%Y-%m-%d %H:%M')} to {bis.strftime('%H:%M')} UTC · {spanne} · {len(trades):,} prints"
