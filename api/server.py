#!/usr/bin/env python3
"""JSON-Bruecke zwischen den vorhandenen Terminal-Modulen und dem Web-Frontend.

Start (aus dem Repo-Root):

    pip install fastapi uvicorn
    python api/server.py

Laeuft auf http://localhost:8787 und liefert dort auch das Frontend aus web/ aus.
Im Container: ``python -m uvicorn api.server:app --host 0.0.0.0 --port 8787``.

Umgebung (alles optional, Voreinstellung = lokale Entwicklung):

    API_HOST / API_PORT        Bind-Adresse fuer ``python api/server.py`` (127.0.0.1:8787)
    CORS_ORIGINS               Komma-Liste erlaubter Origins; ohne Angabe nur die
                               beiden lokalen Adressen. Das Frontend kommt vom selben
                               Origin und braucht keinen Eintrag.
    RATE_LIMIT_PER_MIN         Deckel fuer /api/backtest und /api/risk je IP (6);
                               RATE_LIMIT_BURST Spitze davon (3); 0 schaltet ab.
    RATE_LIMIT_WALLET_PER_MIN  Eigener Deckel fuer /api/wallet je IP (12), Spitze
                               RATE_LIMIT_WALLET_BURST (6).
    RATE_LIMIT_GLOBAL_PER_MIN  Deckel fuer alles unter /api/ je IP (120), Spitze
                               RATE_LIMIT_GLOBAL_BURST (40); 0 schaltet ab.
    RATE_LIMIT_IP_HEADER       Header mit der Besucheradresse hinter dem Proxy
                               (X-Forwarded-For; hinter Cloudflare CF-Connecting-IP).
    CACHE_MAX_ENTRIES          Obergrenze des Prozess-Caches (512 Eintraege).
    RISK_LOG_DIR               Verzeichnis des Flag-Logs des Risk-Screens (app/risk_log.py,
                               Datei flags.jsonl); Voreinstellung data/risk_flags unter dem
                               Repo-Root. Auf Railway ist das Dateisystem fluechtig: das Log
                               ueberlebt ein Redeploy nur mit einem Volume unter /app/data
                               (oder RISK_LOG_DIR zeigt in eines). Nicht beschreibbar =>
                               Warnung auf stdout, kein Log, die Antwort bleibt heil.
    RISK_LOG_MIN_SCORE         Ab welchem Score ein Event geloggt wird (40 = Band "Elevated").
    RISK_LOG_INTERVAL_MIN      > 0 startet einen Daemon-Thread, der die Risk-Rechnung alle N
                               Minuten anstoesst und die Flags loggt, auch ohne Besucher
                               (0 = aus). Nutzt denselben 300-s-Cache wie /api/risk.

    COPY_ADMIN_TOKEN           Schreibzugriff auf den Paper-Copy-Desk (/api/copy/*): ohne
                               Token nur von dieser Maschine (Loopback, kein Proxy-Header);
                               mit Token nur mit Header X-Admin-Token, von ueberall.

Endpoints (read-only ausser POST /api/backtest, das nur simuliert, und dem
Paper-Copy-Desk unter /api/copy/*, der lokale Papierbuecher schreibt):

    GET  /healthz              (Alias von /api/health fuer Caddy und Compose)
    GET  /api/health
    GET  /api/overview
    GET  /api/markets?query=&category=&limit=250
    GET  /api/tape?limit=250&min_cash=0
    GET  /api/leaderboard?limit=100&period=ALL&order_by=PNL
    GET  /api/wallet/{wallet}      (0x + 40 hex; the whole wallet page, ~6 upstream calls,
                                    300 s cache, own per-IP limiter: 12/min, burst 6)
    GET  /api/cross?query=&min_similarity=0.5&max_pairs=50   (gate: sim >= 0.5, volume on both venues)
    GET  /api/risk
    GET  /api/risk/log?limit=100&enrich=1   (Flag-Log; enrich=1 haengt an die neuesten 30
                                             Polymarket-Flags den Preis +30 min/+2 h/+24 h)
    GET  /api/alerts
    GET  /api/copy                 (Buecher, Trader-Liste, Settings, Daemon-Puls, write_access)
    POST /api/copy/traders         {wallet|handle|profile URL, label, start_cash, note}
    POST /api/copy/traders/{w}     {active, label, note}   (Pause/Weiter, Umbenennen)
    POST /api/copy/traders/{w}/topup {amount}
    POST /api/copy/settings        (editierbare Untermenge von CopySettings)
    POST /api/copy/sync            (ein API+Settlement-Durchlauf im Hintergrund)
    GET  /api/copy/sync
    GET  /api/research/{name}
    POST /api/backtest

Nutzt ausschliesslich die bestehende Logik in app/ und src/ — keine eigene
Datenverarbeitung, nur Orchestrierung plus JSON-Mapping (app/api_views.py).
"""

from __future__ import annotations

import dataclasses
import json
import math
import os
import re
import sys
import threading
import time
from collections import OrderedDict
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

# Repo-Root importierbar machen, egal von wo gestartet wird.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd
from fastapi import Body, Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from api.ratelimit import RateLimited, TokenBucketLimiter, client_ip
from app import api_views as apv
from app import app_settings as cfg
from app import backtester as btr
from app import cross_pairs
from app import pilot_result
from app import scorecard as sc
from app import signals as sig
from app.analysis_views import load_publish_payload
from src import prediction_markets as md


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "").strip() or default)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    return int(_env_float(name, default))


def _cors_origins() -> list[str]:
    """Erlaubte Origins aus CORS_ORIGINS; ohne Angabe nur die lokalen Adressen.

    Das Frontend wird vom selben Origin ausgeliefert und braucht gar keinen
    CORS-Eintrag. Die Liste dient Entwicklern, die web/ von einem anderen
    Port aus bedienen, und darf deshalb ruhig eng sein.
    """

    raw = os.environ.get("CORS_ORIGINS", "")
    origins = [o.strip() for o in raw.split(",") if o.strip()]
    return origins or ["http://127.0.0.1:8787", "http://localhost:8787"]


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    # Flag-Sampler (RISK_LOG_INTERVAL_MIN), siehe weiter unten; die Funktion
    # ist beim Start laengst definiert.
    start_risk_sampler()
    yield


app = FastAPI(title="Terminal API", version="0.2", lifespan=_lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

PUBLISH_DIR = ROOT / "public" / "data"

# Prozess-Cache mit Obergrenze. Die Schluessel enthalten Wallets und
# Backtest-Parameter, also waechst er sonst mit jedem neuen Besucher; die
# aeltesten Eintraege fallen zuerst heraus (LRU).
CACHE_MAX_ENTRIES = max(16, _env_int("CACHE_MAX_ENTRIES", 512))
_CACHE: OrderedDict[str, tuple[float, Any]] = OrderedDict()
_CACHE_LOCK = threading.Lock()
CACHE_TTL = 30.0  # Sekunden (Standard; einzelne Endpoints setzen mehr)


def cached(key: str, fn, *args, ttl: float = CACHE_TTL, **kwargs):
    now = time.time()
    with _CACHE_LOCK:
        hit = _CACHE.get(key)
        if hit and now - hit[0] < ttl:
            _CACHE.move_to_end(key)
            return hit[1]
    # Der Aufruf selbst laeuft ohne Sperre: er wartet oft auf das Netz.
    value = fn(*args, **kwargs)
    with _CACHE_LOCK:
        _CACHE[key] = (now, value)
        _CACHE.move_to_end(key)
        while len(_CACHE) > CACHE_MAX_ENTRIES:
            _CACHE.popitem(last=False)
    return value


# --- Rate limiting -----------------------------------------------------------
# Zwei Eimer je Besucheradresse: ein enger fuer die beiden teuren Routen
# (/api/backtest rechnet, /api/risk zieht beim ersten Mal einen Tag Tape) und
# ein weiter fuer alles unter /api/. Beide sind reine In-Process-Bremsen; die
# eigentliche Abwehr sitzt in Cloudflare (siehe deploy/Caddyfile).
RATE_LIMIT_IP_HEADER = os.environ.get("RATE_LIMIT_IP_HEADER", "X-Forwarded-For").strip() or "X-Forwarded-For"
EXPENSIVE_LIMITER = TokenBucketLimiter(
    per_minute=_env_float("RATE_LIMIT_PER_MIN", 6.0),
    burst=_env_int("RATE_LIMIT_BURST", 3),
)
GLOBAL_LIMITER = TokenBucketLimiter(
    per_minute=_env_float("RATE_LIMIT_GLOBAL_PER_MIN", 120.0),
    burst=_env_int("RATE_LIMIT_GLOBAL_BURST", 40),
)


def _request_ip(request: Request) -> str:
    host = request.client.host if request.client else None
    return client_ip(request.headers.get(RATE_LIMIT_IP_HEADER), host)


def _rate_limited_response(retry_after_s: int) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"error": "rate_limited", "retry_after_s": int(retry_after_s)},
        headers={"Retry-After": str(int(retry_after_s))},
    )


# Eigener Eimer fuer /api/wallet: die Route ist teuer (sechs Upstream-Rufe),
# aber sie darf sich den engen Burst von /api/risk und /api/backtest nicht
# teilen — wer den Risk-Screen oeffnet, eine Wallet anklickt und den
# Backtester startet, bekaeme sonst beim dritten Klick ein 429.
WALLET_LIMITER = TokenBucketLimiter(
    per_minute=_env_float("RATE_LIMIT_WALLET_PER_MIN", 12.0),
    burst=_env_int("RATE_LIMIT_WALLET_BURST", 6),
)


def wallet_route_limit(request: Request) -> None:
    """FastAPI-Dependency fuer /api/wallet; wirft RateLimited."""

    WALLET_LIMITER.hit(_request_ip(request))


def expensive_route_limit(request: Request) -> None:
    """FastAPI-Dependency fuer die teuren Routen; wirft RateLimited."""

    EXPENSIVE_LIMITER.hit(_request_ip(request))


@app.exception_handler(RateLimited)
async def _on_rate_limited(request: Request, exc: RateLimited) -> JSONResponse:
    return _rate_limited_response(exc.retry_after_s)


@app.middleware("http")
async def globale_bremse(request: Request, call_next):
    """Weiter Deckel je Adresse fuer alles unter /api/ (Frontend-Dateien nicht)."""

    if request.url.path.startswith("/api/"):
        allowed, wait = GLOBAL_LIMITER.check(_request_ip(request))
        if not allowed:
            return _rate_limited_response(max(1, math.ceil(wait)))
    return await call_next(request)


def df_records(df: pd.DataFrame, limit: int | None = None) -> list[dict[str, Any]]:
    if df is None or df.empty:
        return []
    if limit:
        df = df.head(limit)
    # to_json behandelt NaN -> null und Timestamps -> ISO sauber
    return json.loads(df.to_json(orient="records", date_format="iso"))


def load_universe(limit: int = 250) -> pd.DataFrame:
    def _load() -> pd.DataFrame:
        frames = []
        for name, fn in (("Polymarket", md.get_polymarket_markets), ("Kalshi", md.get_kalshi_markets)):
            try:
                frame = fn(limit=limit)
                if not frame.empty:
                    frames.append(frame.dropna(axis=1, how="all"))
            except Exception as exc:
                print(f"[warn] {name} markets: {exc}")
        if not frames:
            return pd.DataFrame()
        combined = pd.concat(frames, ignore_index=True, sort=False)
        return md.add_market_filter_metrics(combined)

    return cached(f"universe_{limit}", _load)


def load_tape(limit: int = 250, min_cash: float = 0.0) -> pd.DataFrame:
    def _load() -> pd.DataFrame:
        frames = []
        try:
            pm = md.get_polymarket_trades(limit=limit, min_cash=min_cash)
            if not pm.empty:
                frames.append(pm)
        except Exception as exc:
            print(f"[warn] polymarket trades: {exc}")
        try:
            # Kalshi kennt keinen Cash-Filter; die 15-Minuten-Kryptomaerkte
            # drucken tausend Mikro-Trades in Sekunden. Bei einem Mindestbetrag
            # deshalb das ganze Fenster holen und hier filtern, sonst waere die
            # Kalshi-Seite des Tapes leer oder nur Staub.
            ks = md.get_kalshi_trades(limit=1000 if min_cash > 0 else limit)
            if not ks.empty and min_cash > 0 and "notional" in ks.columns:
                ks = ks[pd.to_numeric(ks["notional"], errors="coerce").fillna(0.0) >= float(min_cash)]
            if not ks.empty:
                frames.append(ks.head(limit))
        except Exception as exc:
            print(f"[warn] kalshi trades: {exc}")
        if not frames:
            return pd.DataFrame()
        trades = pd.concat(frames, ignore_index=True, sort=False)
        if "time" in trades.columns:
            trades = trades.sort_values("time", ascending=False)
        return trades

    return cached(f"tape_{limit}_{min_cash}", _load, ttl=45.0)


#: Kategorie fuer Tape-Zeilen ohne Treffer im Marktuniversum: erst die
#: Heuristik der Marktseite (Rohkategorie + Titel), dann die Titelmuster des
#: Risk-Screens (app.suspicion), die Matchups und Esports erkennen.
TAPE_CLASSIFIER = apv.chained_classifier(md.market_filter_category, apv.context_group_classifier())


def load_leaderboard(limit: int = 100, period: str = "ALL", order_by: str = "PNL") -> pd.DataFrame:
    return cached(
        f"lb_{limit}_{period}_{order_by}",
        md.get_polymarket_leaderboard,
        limit,
        period,
        order_by,
        ttl=300.0,
    )


def load_ranked(limit: int = 250) -> pd.DataFrame:
    def _load() -> pd.DataFrame:
        from src import copy_trading as ct

        lb = load_leaderboard(limit=limit)
        try:
            return ct.rank_traders_by_smart_score(lb)
        except Exception as exc:
            print(f"[warn] smart score ranking: {exc}")
            return pd.DataFrame()

    return cached(f"ranked_{limit}", _load, ttl=300.0)


@app.get("/api/health")
@app.get("/healthz", include_in_schema=False)
def health() -> dict[str, Any]:
    return {"ok": True, "time": md.now_utc_label()}


@app.get("/api/overview")
def overview(limit: int = Query(250, le=1000)) -> dict[str, Any]:
    combined = load_universe(limit)
    if combined.empty:
        return {"kpis": {}, "movers": [], "anomalies": [], "ending_soon": []}

    def col(name: str) -> pd.Series:
        return pd.to_numeric(combined.get(name), errors="coerce").fillna(0.0)

    vol24 = col("volume_24h")
    moves = col("change_1d")
    pm_count = int((combined.get("platform") == "Polymarket").sum())
    ks_count = int((combined.get("platform") == "Kalshi").sum())

    movers = combined.assign(_absmove=moves.abs()).sort_values("_absmove", ascending=False).head(8)
    baseline = (vol24 / 24.0).clip(lower=1.0)
    ratio = col("volume_1h") / baseline
    ratio = ratio.where(vol24 >= 10_000, 0.0)
    anomalies = combined.assign(_ratio=ratio).sort_values("_ratio", ascending=False)
    anomalies = anomalies[anomalies["_ratio"] >= 3.0].head(8)

    end_ts = pd.to_datetime(combined.get("end_time"), utc=True, errors="coerce")
    now = pd.Timestamp.now(tz="UTC")
    soon_mask = (end_ts >= now) & (end_ts <= now + pd.Timedelta(hours=72))
    ending = combined[soon_mask].sort_values("end_time").head(8)

    try:
        lb = load_leaderboard(limit=25)
        top_pnl = float(pd.to_numeric(lb.get("pnl"), errors="coerce").max()) if not lb.empty else 0.0
    except Exception:
        top_pnl = 0.0

    cols = [c for c in ("market_key", "title", "platform", "category", "yes_price", "volume_24h", "volume_1h", "change_1d", "end_time", "url") if c in combined.columns]
    return {
        "kpis": {
            "markets_total": int(len(combined)),
            "markets_pm": pm_count,
            "markets_ks": ks_count,
            "volume_24h": float(vol24.sum()),
            "resolving_72h": int(soon_mask.sum()),
            "top_public_pnl": top_pnl,
        },
        "movers": df_records(movers[cols]),
        "anomalies": df_records(anomalies[cols]),
        "ending_soon": df_records(ending[cols]),
        "as_of": md.now_utc_label(),
    }


@app.get("/api/markets")
def markets(
    query: str = "",
    category: str = "",
    platform: str = "",
    sort: str = "volume_24h",
    limit: int = Query(250, le=1000),
) -> dict[str, Any]:
    combined = load_universe(max(limit, 250))
    if combined.empty:
        return {"rows": [], "total": 0, "as_of": md.now_utc_label()}
    df = combined
    if query.strip():
        mask = df.get("title", pd.Series(dtype=str)).astype(str).str.contains(query.strip(), case=False, na=False)
        df = df[mask]
    if platform.strip():
        df = df[df.get("platform") == platform.strip()]
    if category.strip():
        cat_col = "filter_category" if "filter_category" in df.columns else "category"
        df = df[df.get(cat_col).astype(str).str.casefold() == category.strip().casefold()]
    if sort in df.columns:
        df = df.sort_values(sort, ascending=False, na_position="last")
    # Schlanke Zeilen: nur die Felder, die das Frontend liest (apv.MARKET_FIELDS).
    # Mit ``raw``, ``description`` und den Token-Blobs wog die Antwort fuer
    # 250 Zeilen ueber ein Megabyte, alle 30 Sekunden.
    return {"rows": apv.market_records(df, limit), "total": int(len(df)), "as_of": md.now_utc_label()}


@app.get("/api/tape")
def tape(limit: int = Query(250, le=1000), min_cash: float = 0.0) -> dict[str, Any]:
    trades = load_tape(limit=limit, min_cash=min_cash)
    if trades.empty:
        return {"rows": [], "total": 0, "as_of": md.now_utc_label()}
    # Venue-balanciert statt reine Zeitreihenfolge: sonst verdraengen die
    # Kalshi-Mikro-Trades jeden Polymarket-Print aus dem Fenster.
    shown = apv.balanced_head(trades, limit)
    # Kategorie je Print: erst aus dem Marktuniversum (dieselbe Ableitung wie
    # /api/markets), sonst ueber die Titel-Heuristiken (Marktseite, dann die
    # Kontextmuster des Risk-Screens) bzw. das Kalshi-Serien-Praefix. Das
    # Universum ist ohnehin im Cache (das Frontend laedt es mit); faellt es
    # aus, bleibt das Tape ohne Universum-Treffer, aber nicht leer.
    try:
        universe = load_universe(250)
    except Exception as exc:
        print(f"[warn] universe for tape categories: {exc}")
        universe = pd.DataFrame()
    shown = apv.tape_rows_with_category(shown, universe, TAPE_CLASSIFIER)
    return {"rows": df_records(shown, limit), "total": int(len(trades)), "as_of": md.now_utc_label()}


@app.get("/api/leaderboard")
def leaderboard(
    limit: int = Query(100, le=500),
    period: str = "ALL",
    order_by: str = "PNL",
) -> dict[str, Any]:
    try:
        lb = load_leaderboard(limit=limit, period=period, order_by=order_by)
    except Exception as exc:
        print(f"[warn] leaderboard: {exc}")
        return {"rows": [], "total": 0}
    ranked = load_ranked()
    rows = apv.leaderboard_rows(lb, ranked)
    return {
        "rows": rows,
        "total": len(rows),
        "as_of": md.now_utc_label(),
        "note": "Win rate and resolved bets appear per wallet with sample size and CI — see /api/wallet/{wallet}.",
    }


#: A Polymarket proxy wallet: 0x + 40 hex characters. Anything else is a 400,
#: not a fetch that comes back empty and reads as "this wallet did nothing".
WALLET_ADDRESS = re.compile(r"^0x[0-9a-fA-F]{40}$")
WALLET_ACTIVITY_PAGE = 500
WALLET_POSITIONS_LIMIT = 250
WALLET_CACHE_TTL = 300.0


def fetch_wallet_activity(wallet: str, page: int = WALLET_ACTIVITY_PAGE,
                          max_rows: int = apv.WALLET_ACTIVITY_MAX_ROWS) -> tuple[pd.DataFrame, bool]:
    """Walk /activity in pages until a short page or ``max_rows``; (frame, truncated)."""

    frames: list[pd.DataFrame] = []
    offset = 0
    truncated = False
    while True:
        chunk = md.get_polymarket_activity(wallet, limit=page, offset=offset)
        if chunk is None or chunk.empty:
            break
        frames.append(chunk)
        if len(chunk) < page:
            break
        offset += page
        if offset >= max_rows:
            truncated = True
            break
    if not frames:
        return pd.DataFrame(), False
    out = pd.concat(frames, ignore_index=True, sort=False)
    if "time" in out.columns:
        out = out.sort_values("time", ascending=False).reset_index(drop=True)
    return out, truncated


def build_wallet_detail(wallet: str) -> dict[str, Any]:
    """The whole wallet page from the public Data API: about six upstream calls.

    closed-positions (both tails), positions, the profile PnL curve and the
    activity pages; the leaderboard/ranked frame and the whale tape come from
    their own caches. Every part fails on its own — a missing curve leaves the
    curve empty, it does not take the track record with it.
    """

    def _smart_row(w: str):
        ranked = load_ranked()
        if ranked is None or ranked.empty or "wallet" not in ranked:
            return None
        match = ranked[ranked["wallet"].astype(str).str.lower() == w.lower()]
        return match.iloc[0].to_dict() if not match.empty else None

    def _risk_row(w: str):
        tape_df = load_tape(limit=1000, min_cash=0.0)
        if tape_df.empty:
            return None
        scores = md.whale_wallet_risk_scores(tape_df)
        if scores is None or scores.empty or "wallet" not in scores:
            return None
        match = scores[scores["wallet"].astype(str).str.lower() == w.lower()]
        return match.iloc[0].to_dict() if not match.empty else None

    resolved = pd.DataFrame()
    capped = False
    resolved_error: str | None = None
    try:
        resolved, capped = md.get_polymarket_resolved_positions(wallet)
        if resolved is None:
            resolved = pd.DataFrame()
    except Exception as exc:
        resolved_error = str(exc)
        print(f"[warn] resolved positions {wallet}: {exc}")

    activity = pd.DataFrame()
    truncated = False
    try:
        activity, truncated = fetch_wallet_activity(wallet)
    except Exception as exc:
        print(f"[warn] activity {wallet}: {exc}")

    def _resolved(_w: str):
        if resolved_error:
            raise RuntimeError(resolved_error)
        return resolved, capped

    # One resolved fetch feeds the scorecard and the page blocks, so the two
    # cannot disagree about the data state. refresh=True: the scorecard keeps
    # its own 15-minute cache, this endpoint has its own 300 s one.
    card = sc.wallet_scorecard(
        wallet,
        fetchers={"resolved": _resolved, "activity": lambda _w: activity, "smart_row": _smart_row, "risk_row": _risk_row},
        refresh=True,
    )
    positions = pd.DataFrame()
    pnl = pd.DataFrame()
    try:
        positions = md.get_polymarket_positions(wallet, WALLET_POSITIONS_LIMIT)
    except Exception as exc:
        print(f"[warn] positions {wallet}: {exc}")
    try:
        pnl = md.get_polymarket_user_pnl(wallet, "All")
    except Exception as exc:
        print(f"[warn] user pnl {wallet}: {exc}")

    pseudonym = ""
    try:
        lb = load_leaderboard(limit=100)
        if lb is not None and not lb.empty and "wallet" in lb:
            match = lb[lb["wallet"].astype(str).str.lower() == wallet.lower()]
            if not match.empty:
                pseudonym = str(match.iloc[0].get("trader") or "")
    except Exception as exc:
        print(f"[warn] leaderboard pseudonym {wallet}: {exc}")

    return apv.wallet_detail(
        card, positions, pnl, activity,
        resolved=resolved, resolved_capped=capped, activity_truncated=truncated,
        classify=TAPE_CLASSIFIER, pseudonym=pseudonym, as_of=md.now_utc_label(),
        pnl_window="All", positions_requested=WALLET_POSITIONS_LIMIT,
    )


@app.get("/api/wallet/{wallet}", dependencies=[Depends(wallet_route_limit)])
def wallet_detail(wallet: str) -> dict[str, Any]:
    wallet = wallet.strip()
    if not WALLET_ADDRESS.match(wallet):
        raise HTTPException(status_code=400, detail="expected a Polymarket wallet address (0x + 40 hex characters)")
    return cached(f"wallet_page_{wallet.lower()}", build_wallet_detail, wallet.lower(), ttl=WALLET_CACHE_TTL)


#: Was /api/cross als "gate" mitmeldet, damit das Frontend den leeren Fall
#: benennen kann, ohne die Schwelle selbst zu kennen.
#: Lockere Matcher-Schranke fuer die Zaehlung "N of M candidates": was der
#: Matcher ueberhaupt fuer verwandt haelt, bevor die Schranke greift.
CROSS_CANDIDATE_FLOOR = 0.2

CROSS_GATE_NOTE = (
    "Only pairs with title similarity >= {sim:.2f} and volume on both venues are shown. "
    "Matched by title similarity — pairs are not verified to resolve identically "
    "(studies 08 and 11 in the microstructure report show two matched pairs that were different questions)."
)


@app.get("/api/cross")
def cross(
    query: str = "",
    min_similarity: float = Query(apv.CROSS_MIN_SIMILARITY, ge=0.0, le=1.0),
    max_pairs: int = Query(150, le=150),
) -> dict[str, Any]:
    # Ehrlichkeits-Schranke: unter 0.5 Aehnlichkeit war ein Paar bisher oft
    # zwei verschiedene Fragen (Studien 08 und 11), und ohne Volumen auf
    # beiden Seiten gibt es keinen Preis, den man vergleichen koennte. Der
    # Parameter kann die Schranke anheben, nicht senken.
    min_similarity = max(float(min_similarity), apv.CROSS_MIN_SIMILARITY)
    gate = {"min_similarity": min_similarity, "require_volume_both": True}
    leer = {"rows": [], "total": 0, "gate": gate, "as_of": md.now_utc_label(),
            "note": CROSS_GATE_NOTE.format(sim=min_similarity)}
    # Eigenes, tiefes Universum je Venue: Gamma liefert max. 100 je Seite,
    # also paginieren; der Matcher in app/cross_pairs.py vergleicht die volle
    # Breite statt der Top-80.
    def _pm() -> pd.DataFrame:
        frames = []
        for offset in (0, 100, 200, 300, 400):
            page = md.get_polymarket_markets(limit=100, offset=offset)
            if page.empty:
                break
            frames.append(page)
        return pd.concat(frames, ignore_index=True, sort=False) if frames else pd.DataFrame()

    def _ks() -> pd.DataFrame:
        return md.get_kalshi_markets(limit=1000)

    try:
        pm = cached("cross_pm", _pm, ttl=300.0)
        ks = cached("cross_ks", _ks, ttl=300.0)
    except Exception as exc:
        print(f"[warn] cross venue universes: {exc}")
        return leer
    if pm.empty or ks.empty:
        return leer
    try:
        candidates = cached(
            f"cross_cand_{min_similarity}_{max_pairs}",
            cross_pairs.deep_cross_candidates,
            pm,
            ks,
            min_similarity,
            max_pairs,
            ttl=300.0,
        )
        # Wie viele Paare der Matcher unterhalb der Schranke ueberhaupt
        # findet — damit die Seite "N of M candidates clear the gate" sagen
        # kann statt nur "nothing". Gleicher Matcher, lockere Schranke.
        vor_schranke = cached(
            f"cross_cand_{CROSS_CANDIDATE_FLOOR}_150",
            cross_pairs.deep_cross_candidates,
            pm,
            ks,
            CROSS_CANDIDATE_FLOOR,
            150,
            ttl=300.0,
        )
        if query.strip():
            mask = candidates["polymarket_title"].str.contains(query.strip(), case=False, na=False) | candidates["kalshi_title"].str.contains(query.strip(), case=False, na=False)
            candidates = candidates[mask]
    except Exception as exc:
        print(f"[warn] cross venue: {exc}")
        return leer
    categories = {}
    if "market_key" in pm.columns and "category" in pm.columns:
        categories = {
            str(key): str(cat)
            for key, cat in zip(pm["market_key"], pm["category"])
            if key is not None and cat
        }
    rows = apv.cross_rows(candidates, categories, min_similarity=min_similarity, require_volume=True)
    return {
        "rows": rows,
        "total": len(rows),
        "candidates_before_gate": int(len(vor_schranke)) if vor_schranke is not None else int(len(candidates)),
        "gate": gate,
        "as_of": md.now_utc_label(),
        "note": CROSS_GATE_NOTE.format(sim=min_similarity),
    }


def load_deep_tape(seiten: int = 8, min_cash: float = 1000.0) -> pd.DataFrame:
    """Whale-Prints ueber mehrere Seiten, fuer das Co-Trading-Netzwerk.

    Der Feed liefert die juengsten Prints, und tausend davon decken auf
    dieser Venue nur Minuten ab. In Minuten teilt niemand zwei Maerkte, das
    Netzwerk waere also leer, weil das Fenster zu kurz ist und nicht weil
    keine Struktur da ist. Acht Seiten ergeben rund einen Tag.
    """

    def _load() -> pd.DataFrame:
        teile: list[pd.DataFrame] = []
        for seite in range(seiten):
            try:
                block = md.get_polymarket_trades(
                    limit=1000, min_cash=min_cash, offset=seite * 1000)
            except Exception as exc:
                print(f"[warn] deep tape page {seite}: {exc}")
                break
            if block is None or block.empty:
                break
            teile.append(block)
        if not teile:
            return pd.DataFrame()
        zusammen = pd.concat(teile, ignore_index=True, sort=False)
        schluessel = [s for s in ("transaction_hash", "wallet", "asset") if s in zusammen.columns]
        if schluessel:
            zusammen = zusammen.drop_duplicates(subset=schluessel, keep="first")
        return zusammen.reset_index(drop=True)

    return cached(f"deep_tape_{seiten}_{min_cash}", _load, ttl=300.0)


def _tape_categories(trades: pd.DataFrame) -> pd.DataFrame:
    """Kategorien und Elterntitel fuer die Maerkte eines Tapes.

    Fail-soft: ohne die Tabelle klassifiziert `classify_insider_context`
    weiter ueber Titelmuster, nur eben grober. Ein Netzwerkfehler darf den
    Risk-Screen nicht kippen.
    """

    if trades is None or trades.empty or "market_key" not in trades.columns:
        return pd.DataFrame()
    keys = tuple(sorted({str(k) for k in trades["market_key"].dropna().astype(str) if k}))
    if not keys:
        return pd.DataFrame()

    def _load() -> pd.DataFrame:
        return md.market_category_frame(list(keys))

    try:
        return cached(f"tape_categories_{hash(keys)}", _load, ttl=600.0)
    except Exception as exc:
        print(f"[warn] market categories: {exc}")
        return pd.DataFrame()


def build_risk_payload() -> dict[str, Any]:
    """Der komplette Risk-Screen (Events, Wallets, Cluster, Netzwerk), 300 s gecacht.

    Von ``/api/risk`` und vom Flag-Sampler gemeinsam genutzt, damit beide
    dieselbe Rechnung und denselben Cache sehen. Wirft ``LookupError``, wenn
    kein Tape da ist.
    """

    from app import suspicion as susp

    settings = cfg.load_settings()
    whale_threshold = float(settings.get("whale_threshold", 2500))
    trades = load_tape(limit=1000, min_cash=0.0)
    if trades.empty:
        raise LookupError("no trade tape available")

    def _build() -> dict[str, Any]:
        # Sports, weather and crypto/market prices are excluded from the
        # screen entirely (susp.EXCLUDED_CONTEXTS). No fallback to the raw
        # tape: when the last thousand prints are all 15-minute crypto
        # markets the honest answer is an empty screen, not a crypto screen.
        screened = susp.filter_insider_prone_trades(trades)
        base = screened if screened is not None else pd.DataFrame()
        wallet_scores = md.whale_wallet_risk_scores(base, whale_threshold=whale_threshold)
        event_scores = md.whale_event_risk_scores(base, whale_threshold=whale_threshold)
        fresh = pd.DataFrame()
        coord = pd.DataFrame()
        try:
            fresh = susp.fresh_wallet_clusters(base, whale_threshold=whale_threshold)
            coord = susp.coordinated_clusters(base)
            # Same ladder as the Streamlit "Suspicious" page: fresh-wallet and
            # timing bonuses, then the insider-plausibility multiplier of the
            # market's context group. Each step leaves its points in a column
            # (component_*), so the card and the flag log can say WHY.
            event_scores = susp.apply_fresh_wallet_bonus(event_scores, fresh)
            event_scores = susp.apply_coordination_bonus(event_scores, coord)
            event_scores = susp.apply_category_context(event_scores)
            # Side of the flow, price range, first/last print, top wallets,
            # market link — what a review of the flag needs afterwards.
            event_scores = susp.enrich_event_flow(
                event_scores, base, whale_threshold=whale_threshold)
        except Exception as exc:
            print(f"[warn] event flow details: {exc}")
        payload = apv.risk_payload(wallet_scores, event_scores)
        try:
            # Der Netzwerk-Tape geht bewusst tiefer als der Screen-Tape: das
            # letzte Tausend Prints deckt auf dieser Venue rund eine Minute ab,
            # und in einer Minute teilt niemand mehr als einen Markt.
            netz_tape = load_deep_tape()
            # Kategorien mitgeben: ein Untermarkt heisst "Will FC Thun win on
            # 2026-08-06?" und traegt selbst kein Sportwort. Ohne den
            # Elterntitel landen ganze Spieltage als "General" im Screen.
            netz_basis = susp.filter_insider_prone_trades(
                netz_tape, _tape_categories(netz_tape))
            if netz_basis is None or netz_basis.empty:
                netz_basis = base

            # Regelleiter von streng nach locker. Welche Stufe gegriffen hat,
            # geht mit in die Nutzlast: die Grafik ist nur so viel wert wie
            # die Regel, die unter ihr steht, und die faellt hier nachweislich
            # oft auf die unterste Stufe.
            LEITER = (
                ("same side of at least 3 markets within 5 minutes, $10k paired notional",
                 dict(window_minutes=5.0, min_shared=3, min_pair_notional=10_000.0)),
                ("same side of at least 2 markets within 5 minutes",
                 dict(window_minutes=5.0, min_shared=2)),
                ("same side of at least 2 markets anywhere in the window, no simultaneity required",
                 dict(window_minutes=None, min_shared=2)),
            )
            regel = LEITER[-1][0]
            nodes, edges = susp.co_trading_network(netz_basis, max_wallets=300)
            for beschreibung, kwargs in LEITER:
                nodes, edges = susp.co_trading_network(netz_basis, max_wallets=300, **kwargs)
                if not nodes.empty:
                    regel = beschreibung
                    break

            payload.update(apv.cluster_payload(
                fresh, coord, nodes, edges,
                lambda cn, ce: susp.cluster_story(cn, ce, netz_basis),
            ))
            payload["kpis"].update(payload.pop("kpis_clusters", {}))

            if not nodes.empty:
                try:
                    modularitaet = susp.network_modularity(nodes, edges)
                except Exception:
                    modularitaet = None
                payload["graph"] = apv.network_graph(
                    susp.cluster_layout(nodes), edges,
                    regel=regel, modularitaet=modularitaet)
                payload["graph"]["fenster"] = apv.tape_window_label(netz_basis)
                payload["matrix"] = apv.overlap_matrix(netz_basis, nodes)
        except Exception as exc:
            print(f"[warn] suspicion clusters: {exc}")
        return payload

    return cached("risk_payload", _build, ttl=300.0)


def _record_risk_flags(payload: dict[str, Any]) -> None:
    """Flag-Log fuettern; darf die Antwort nie kippen."""

    try:
        from app import risk_log

        result = risk_log.record_flags(payload.get("events") or [])
        if result.get("written") or result.get("updated"):
            print(f"[risk-log] {result['written']} new, {result['updated']} updated -> {result['path']}")
    except Exception as exc:
        print(f"[warn] risk flag log: {exc}")


@app.get("/api/risk", dependencies=[Depends(expensive_route_limit)])
def risk() -> dict[str, Any]:
    try:
        payload = build_risk_payload()
    except LookupError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    _record_risk_flags(payload)
    payload["as_of"] = md.now_utc_label()
    return payload


#: Wie viele der neuesten Polymarket-Flags /api/risk/log?enrich=1 mit dem
#: Preis danach versieht (ein CLOB-Aufruf je Flag, 300 s gecacht).
RISK_LOG_ENRICH_MAX = 30


def _flag_price_after(row: dict[str, Any]) -> dict[str, Any] | None:
    """Preis +30 min / +2 h / +24 h nach dem Flag fuer ein Polymarket-Flag.

    Der Token ist das Asset der dominanten Seite (aus den Prints), der Preis
    also in derselben Outcome-Waehrung wie ``price_at_flag``. Ohne Token oder
    ohne Historie ehrlich ``None``.
    """

    from app import risk_log

    if str(row.get("venue") or "").lower() != "polymarket":
        return None
    token_id = str(row.get("token_id") or "").strip()
    flag_time = row.get("window_end") or row.get("first_seen")
    if not token_id or not flag_time:
        return None
    start = pd.to_datetime(flag_time, utc=True, errors="coerce")
    if pd.isna(start):
        return None
    # Zwei Tage ab 23 h vor dem Flag: deckt +24 h ab, bleibt unter dem CLOB-
    # Fensterdeckel und liefert Fuenf-Minuten-Kerzen fuer den +30-min-Punkt.
    end_time = min(start + pd.Timedelta(hours=25), pd.Timestamp.now(tz="UTC"))

    def _load() -> dict[str, Any] | None:
        history = md.get_polymarket_price_history(token_id, days=2, interval="5m", end_time=end_time)
        return risk_log.price_after(history, start, row.get("price_at_flag"))

    return cached(f"flag_after_{row.get('flag_id')}_{token_id}", _load, ttl=300.0)


@app.get("/api/risk/log")
def risk_log_endpoint(limit: int = Query(100, ge=1, le=500), enrich: int = 0, since: str | None = None) -> dict[str, Any]:
    from app import risk_log

    rows = risk_log.read_flags(limit=limit, since=since)
    enriched = 0
    if enrich:
        budget = RISK_LOG_ENRICH_MAX
        for row in rows:
            row["after"] = None
            if budget <= 0:
                continue
            if str(row.get("venue") or "").lower() != "polymarket":
                continue
            budget -= 1
            try:
                row["after"] = _flag_price_after(row)
                enriched += 1 if row["after"] else 0
            except Exception as exc:
                print(f"[warn] flag price after: {exc}")
                row["after"] = None
    return {
        "rows": rows,
        "count": len(rows),
        "enriched": enriched,
        "enrich_max": RISK_LOG_ENRICH_MAX,
        "min_score": risk_log.min_score(),
        "dedupe_hours": risk_log.DEDUPE_HOURS,
        "sampler_interval_min": RISK_LOG_INTERVAL_MIN,
        "note": ("Every event the screen flags (score >= min_score) is logged with side, price and wallets at that "
                 "moment; 'after' is the price of the flagged side +30 min / +2 h / +24 h later (Polymarket only, "
                 "null where the horizon has not passed or no history is available)."),
        "as_of": md.now_utc_label(),
    }


# --- Flag-Sampler ------------------------------------------------------------
# RISK_LOG_INTERVAL_MIN > 0 startet EINEN Daemon-Thread, der die Risk-Rechnung
# alle N Minuten anstoesst und die Flags loggt — auch wenn niemand die Seite
# oeffnet. Er nutzt denselben 300-s-Cache wie /api/risk; ein Intervall unter
# fuenf Minuten rechnet also nicht oefter, es liest nur oefter den Cache.
RISK_LOG_INTERVAL_MIN = max(0.0, _env_float("RISK_LOG_INTERVAL_MIN", 0.0))
_SAMPLER_STARTED = threading.Event()


def _risk_sampler_loop(interval_s: float) -> None:
    print(f"[risk-log] sampler every {interval_s / 60:.1f} min")
    while True:
        try:
            payload = build_risk_payload()
            _record_risk_flags(payload)
        except Exception as exc:
            print(f"[warn] risk sampler: {exc}")
        time.sleep(max(30.0, interval_s))


def start_risk_sampler() -> bool:
    """Startet den Sampler genau einmal; False, wenn aus oder schon gestartet."""

    if RISK_LOG_INTERVAL_MIN <= 0 or _SAMPLER_STARTED.is_set():
        return False
    _SAMPLER_STARTED.set()
    thread = threading.Thread(
        target=_risk_sampler_loop, args=(RISK_LOG_INTERVAL_MIN * 60.0,), name="risk-flag-sampler", daemon=True)
    thread.start()
    return True


@app.get("/api/alerts")
def alerts(
    min_move: float = 0.03,
    max_spread: float = 0.07,
    min_whale: float = 0.0,
    ending_days: int = 7,
) -> dict[str, Any]:
    settings = cfg.load_settings()
    whale_threshold = min_whale or float(settings.get("whale_threshold", 2500))
    combined = load_universe(250)
    trades = load_tape(limit=250, min_cash=0.0)
    if combined.empty and trades.empty:
        raise HTTPException(status_code=503, detail="no market data available")

    # Welche Regeln dieser Endpunkt gar nicht auswertet. Die Regelkarten
    # bewerben sechs Regeln; ohne diesen Hinweis liest sich eine nicht
    # gepruefte Regel wie eine gepruefte ohne Treffer.
    holder_checks = 0
    nicht_geprueft = ["HOLDER CONCENTRATION"] if holder_checks == 0 else []

    def _build() -> dict[str, Any]:
        signals = sig.build_monitor_signals(
            combined.copy(),
            trades.copy(),
            min_volume=0.0,
            min_liquidity=0.0,
            min_move=min_move,
            max_spread=max_spread,
            min_whale_notional=whale_threshold,
            ending_days=ending_days,
            holder_threshold=0.25,
            holder_checks=holder_checks,
            tracked_keys=set(),
        )
        return {
            "signals": apv.alert_rows(signals),
            "rule_counts": apv.alert_rule_counts(signals),
            "rules_not_evaluated": nicht_geprueft,
        }

    key = f"alerts_{min_move}_{max_spread}_{whale_threshold}_{ending_days}"
    state_path = ROOT / "data" / "alert_scanner_state.json"
    deliveries: dict[str, Any] = {"available": False, "note": "No delivery log on this machine — the alert scanner keeps only a dedupe state, not a send history."}
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
            deliveries = {
                "available": False,
                "note": "The scanner keeps no per-message log; last scan shown from its dedupe state.",
                "last_scan_at": state.get("last_scan_at"),
                "last_hits": state.get("last_hits"),
                "last_sent": state.get("last_sent"),
            }
        except (OSError, json.JSONDecodeError):
            pass
    gebaut = cached(key, _build, ttl=60.0)
    return {
        "signals": gebaut["signals"],
        "rule_counts": gebaut["rule_counts"],
        "rules_not_evaluated": gebaut["rules_not_evaluated"],
        "shown_limit": apv.ALERT_ROW_LIMIT,
        "deliveries": deliveries,
        "as_of": md.now_utc_label(),
    }


# --- Paper copy desk -----------------------------------------------------------
# The Copy trade page reads /api/copy and, from this machine (or with
# COPY_ADMIN_TOKEN), writes through the routes below: follow/pause traders,
# settings, top-ups, one sync pass. app/copy_admin.py holds the behaviour;
# these routes only map HTTP onto it. The daemon (scripts/run_copy_trader.py)
# is still the thing that copies continuously; the desk configures it and can
# run a single pass without it.
COPY_DB_PATH = ROOT / "data" / "copy_trading.sqlite"
COPY_SETTINGS_PATH = ROOT / "data" / "copy_settings.json"
COPY_STATUS_PATH = ROOT / "data" / "copy_trader_status.json"


def _copy_write_access(request: Request):
    from app import copy_admin as ca

    host = request.client.host if request.client else None
    # A proxied request is never "local", whatever the socket peer says: with
    # Caddy on the same box the peer is loopback for every visitor. Any
    # forwarding header (the configured one or the plain X-Forwarded-For)
    # marks the request as remote — and a forged "X-Forwarded-For: 127.0.0.1"
    # must not talk its way in either, so the forwarded address is only named,
    # never trusted as loopback.
    forwarded = request.headers.get(RATE_LIMIT_IP_HEADER) or request.headers.get("X-Forwarded-For")
    if forwarded:
        host = "proxied:" + client_ip(forwarded, host)
    return ca.write_access(host, request.headers.get(ca.ADMIN_TOKEN_HEADER), ca.configured_token())


def copy_write_guard(request: Request) -> None:
    """FastAPI dependency: 403 with the reason when this request may not write."""
    access = _copy_write_access(request)
    if not access.allowed:
        raise HTTPException(status_code=403, detail=access.reason)


def _copy_cache_drop() -> None:
    with _CACHE_LOCK:
        _CACHE.pop("copy_payload", None)


def _copy_settings_for_engine():
    from src import copy_trading as ct

    return ct.load_copy_settings(COPY_SETTINGS_PATH)


@app.get("/api/copy")
def copy_state(request: Request) -> dict[str, Any]:
    from app import copy_admin as ca
    from src import copy_trading as ct

    # The public host has no books and nobody may write there: say so instead
    # of conjuring an empty desk with a seed trader in it. Where writes are
    # allowed (this machine), a missing database is a desk nobody has used yet
    # and connect() lays down the schema so the follow form has somewhere to go.
    if not COPY_DB_PATH.exists() and not _copy_write_access(request).allowed:
        raise HTTPException(status_code=503, detail="no paper copy desk on this host — the books live where the copy daemon runs")

    def _build() -> dict[str, Any]:
        conn = ct.connect(COPY_DB_PATH)
        try:
            orders = ct.get_paper_orders(conn=conn)
            positions = ct.get_positions(conn=conn)
            cash_events = ct.get_cash_events(conn=conn)
            equity = ct.get_equity_snapshots(conn=conn)
            snapshot = ct.value_paper_portfolio(conn=conn)
            portfolio = {
                "cash": snapshot.cash,
                "position_value": snapshot.position_value,
                "equity": snapshot.equity,
                "realized_pnl": snapshot.realized_pnl,
                "unrealized_pnl": snapshot.unrealized_pnl,
            }
            contributions = ct.total_contributions(conn=conn)
            try:
                sizing = ct.get_dynamic_sizing_snapshot(conn=conn)
            except Exception:
                sizing = {}
            desk = ca.desk_state(db_path=COPY_DB_PATH, settings_path=COPY_SETTINGS_PATH, status_path=COPY_STATUS_PATH)
        finally:
            conn.close()
        active = [t for t in desk["traders"] if t["active"]]
        # The status line names the active traders (or says none is), not a
        # wallet fixed in the code.
        if active:
            source_label = ", ".join(t["label"] for t in active[:3]) + (f" +{len(active) - 3}" if len(active) > 3 else "")
            source_wallet = active[0]["wallet"]
        else:
            source_label = "no active trader"
            source_wallet = ""
        payload = apv.copy_payload(orders, positions, cash_events, equity, portfolio, contributions, source_wallet, source_label, sizing)
        payload["status"]["source"] = source_label
        payload["status"]["running"] = desk["daemon"].get("running")
        payload["status"]["auto_topup"] = bool(desk["settings"].get("auto_top_up_enabled"))
        payload.update({k: desk[k] for k in ("traders", "active_count", "settings", "daemon", "totals")})
        payload["sync"] = desk["sync"]
        # The source PnL overlay follows the first active trader (one curve
        # per wallet lives in each trader row's equity_curve for the paper side).
        if source_wallet:
            try:
                source_pnl = md.get_polymarket_user_pnl(source_wallet, "1mo")
                if source_pnl is not None and not source_pnl.empty and "pnl" in source_pnl:
                    curve = [float(v) for v in source_pnl["pnl"].tolist() if v == v]
                    if curve:
                        payload["source_curve"] = curve
                        # PnL-Kurve ohne Kapitalbasis: Delta in Dollar, kein Prozent.
                        payload["kpis"]["source_pnl_delta"] = curve[-1] - curve[0]
            except Exception as exc:
                print(f"[warn] source pnl curve: {exc}")
        fidelity = apv.fidelity_block(orders, portfolio, sizing)
        if fidelity:
            payload["fidelity_detail"] = fidelity
            execution = (fidelity.get("execution") or {}).get("fidelity")
            config = (fidelity.get("config") or {}).get("fidelity")
            if execution is not None:
                payload["kpis"]["exec_fidelity"] = round(execution * 100)
            if config is not None:
                payload["kpis"]["config_fidelity"] = round(config * 100)
            if execution is not None and config is not None:
                payload["kpis"]["fidelity"] = round(execution * config * 100)
            elif execution is not None:
                payload["kpis"]["fidelity"] = round(execution * 100)
        return payload

    try:
        payload = dict(cached("copy_payload", _build, ttl=15.0))
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"copy state unavailable: {exc}")
    # Per request, never cached: who is asking decides whether they may write,
    # and the sync state changes underneath the cache.
    payload["write_access"] = _copy_write_access(request).as_dict()
    payload["sync"] = ca.sync_state()
    payload["as_of"] = md.now_utc_label()
    return payload


@app.post("/api/copy/traders", dependencies=[Depends(copy_write_guard)])
def copy_follow(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Follow a wallet: open its sub-account and seed its baseline now."""
    from app import copy_admin as ca
    from src import copy_trading as ct

    wallet = ca.resolve_wallet(body.get("wallet", ""), load_leaderboard)
    if not wallet:
        raise HTTPException(status_code=400, detail="no Polymarket wallet found in the input — paste the 0x… proxy address (or an exact handle from the leaderboard)")
    try:
        result = ca.follow(
            wallet,
            label=str(body.get("label", "") or ""),
            start_cash=float(body.get("start_cash") or 0) or ct.PER_TRADER_START_CASH,
            note=str(body.get("note", "") or ""),
            db_path=COPY_DB_PATH,
            settings=_copy_settings_for_engine(),
            seed=bool(body.get("seed", True)),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    _copy_cache_drop()
    return result


@app.post("/api/copy/traders/{wallet}", dependencies=[Depends(copy_write_guard)])
def copy_set_trader(wallet: str, body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    """Pause/resume or relabel one followed trader (``active``, ``label``, ``note``)."""
    from app import copy_admin as ca

    if not re.fullmatch(r"0x[a-fA-F0-9]{40}", wallet or ""):
        raise HTTPException(status_code=400, detail="expected a 0x… wallet in the path")
    active = body.get("active")
    try:
        result = ca.set_trader(
            wallet,
            active=None if active is None else bool(active),
            label=None if body.get("label") is None else str(body.get("label")),
            note=None if body.get("note") is None else str(body.get("note")),
            db_path=COPY_DB_PATH,
            settings=_copy_settings_for_engine(),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc.args[0] if exc.args else exc))
    _copy_cache_drop()
    return result


@app.post("/api/copy/traders/{wallet}/topup", dependencies=[Depends(copy_write_guard)])
def copy_top_up(wallet: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    from app import copy_admin as ca

    if not re.fullmatch(r"0x[a-fA-F0-9]{40}", wallet or ""):
        raise HTTPException(status_code=400, detail="expected a 0x… wallet in the path")
    try:
        result = ca.top_up(wallet, float(body.get("amount") or 0), db_path=COPY_DB_PATH)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    _copy_cache_drop()
    return result


@app.post("/api/copy/settings", dependencies=[Depends(copy_write_guard)])
def copy_settings(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Change the sizing/cash settings the daemon reads on every pass."""
    from app import copy_admin as ca

    try:
        updated = ca.update_settings(body, COPY_SETTINGS_PATH)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    _copy_cache_drop()
    return {"settings": ca.settings_view(updated)}


@app.post("/api/copy/sync", dependencies=[Depends(copy_write_guard)])
def copy_sync() -> dict[str, Any]:
    """Run one API + settlement pass over the active traders in the background."""
    from app import copy_admin as ca

    settings = _copy_settings_for_engine()

    def _pass() -> dict[str, Any]:
        try:
            return ca.run_sync_pass(db_path=COPY_DB_PATH, settings=settings)
        finally:
            # The books changed underneath the cached read; the next
            # /api/copy must rebuild instead of serving the pre-sync state.
            _copy_cache_drop()

    started = ca.start_sync(runner=_pass)
    _copy_cache_drop()
    return started


@app.get("/api/copy/sync")
def copy_sync_state() -> dict[str, Any]:
    from app import copy_admin as ca

    return ca.sync_state()


@app.get("/api/research/{name}")
def research(name: str) -> dict[str, Any]:
    name = name.strip().lower()
    filename = apv.RESEARCH_FILES.get(name)
    if not filename:
        raise HTTPException(status_code=404, detail=f"unknown study '{name}'")
    payload = load_publish_payload(PUBLISH_DIR, filename + ".json")
    if payload is None:
        raise HTTPException(status_code=404, detail=f"no published data for '{name}'")
    if filename == "pipeline_forward":
        payload = apv.trim_pipeline_payload(payload)
    if filename == "pilot":
        # Die Auswertung wird aus den Trades gerechnet, nicht mitpubliziert:
        # so ueberschreibt ein neuer Publish-Lauf sie nicht.
        payload = dict(payload)
        try:
            payload["auswertung"] = pilot_result.evaluate(payload)
        except Exception as exc:
            print(f"[warn] pilot evaluation: {exc}")
    if filename == "runs":
        def _extras() -> dict[str, Any]:
            return apv.live_runs_extras(payload)

        payload = dict(payload)
        try:
            payload["extras"] = cached("live_runs_extras", _extras, ttl=300.0)
        except Exception as exc:
            print(f"[warn] live runs extras: {exc}")
    return payload


@app.get("/api/resolved")
def resolved(limit: int = Query(250, le=500)) -> dict[str, Any]:
    def _load() -> list[dict[str, Any]]:
        closed = md.get_polymarket_closed_markets(limit=limit)
        return apv.resolved_rows(closed)

    try:
        rows = cached(f"resolved_{limit}", _load, ttl=300.0)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"closed markets unavailable: {exc}")
    return {"rows": rows, "total": len(rows), "as_of": md.now_utc_label()}


@app.get("/api/track")
def track() -> dict[str, Any]:
    def _read_list(name: str) -> list[Any]:
        path = ROOT / "data" / name
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        return data if isinstance(data, list) else []

    followed = _read_list("followed_wallets.json")
    watchlist = _read_list("watchlist.json")
    try:
        ranked = load_ranked()
    except Exception:
        ranked = pd.DataFrame()
    try:
        lb = load_leaderboard(limit=250)
    except Exception:
        lb = pd.DataFrame()
    payload = apv.track_payload(followed, watchlist, ranked, lb)
    payload["as_of"] = md.now_utc_label()
    return payload


@app.get("/api/market/{market_key}/history")
def market_history(market_key: str, days: int = Query(1, le=90), interval: str = "5m") -> dict[str, Any]:
    combined = load_universe(250)
    token_id = ""
    if not combined.empty and "market_key" in combined.columns:
        match = combined[combined["market_key"].astype(str) == market_key]
        if not match.empty:
            token_id = str(match.iloc[0].get("yes_token_id") or "")
    if not token_id:
        raise HTTPException(status_code=404, detail="market not in the loaded universe or no token id")

    def _load() -> list[float]:
        history = md.get_polymarket_price_history(token_id, days=days, interval=interval)
        if history is None or history.empty:
            return []
        return [float(v) * 100 for v in history["price"].tolist() if v == v]

    try:
        points = cached(f"hist_{token_id}_{days}_{interval}", _load, ttl=120.0)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"price history unavailable: {exc}")
    return {"points": points, "as_of": md.now_utc_label()}


SIZING_MAP = {
    "fixed": (btr.SIZING_FIXED, "stake_fixed"),
    "pct": (btr.SIZING_PERCENT, "stake_pct"),
    "match": (btr.SIZING_PORTFOLIO, "stake_mult"),
    "kelly": (btr.SIZING_KELLY, "stake_kelly"),
}


@app.post("/api/backtest", dependencies=[Depends(expensive_route_limit)])
def backtest(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    wallet = str(body.get("wallet", "")).strip()
    if not wallet.startswith("0x") or len(wallet) < 20:
        raise HTTPException(status_code=400, detail="expected a Polymarket wallet address")
    mode_key = str(body.get("sizing_mode", "fixed"))
    sizing_mode, stake_field = SIZING_MAP.get(mode_key, SIZING_MAP["fixed"])
    stake_value = float(body.get(stake_field, 25.0))
    strategy = btr.STRATEGY_FADE if str(body.get("strategy", "copy")) == "fade" else btr.STRATEGY_COPY
    config = btr.BacktestConfig(
        wallet=wallet,
        days=int(body.get("window_days", 30)),
        bankroll=float(body.get("bankroll", 1000.0)),
        sizing_mode=sizing_mode,
        stake_value=stake_value,
        max_stake=float(body.get("cap", 250.0)),
        fee_bps=float(body.get("fee_bps", 20.0)),
        # Voreinstellung ist das Venue-Modell. Der pauschale bps-Satz wirkt
        # nur, wenn er ausdruecklich verlangt wird.
        fee_model=(btr.FEE_MODEL_FLAT
                   if str(body.get("fee_model", "")).strip().lower() == btr.FEE_MODEL_FLAT
                   else btr.FEE_MODEL_CURVE),
        slippage_bps=float(body.get("slippage_bps", 15.0)),
        strategy=strategy,
        max_exposure_pct=float(body.get("exposure_pct", 100.0)),
    )
    key = "bt_" + "_".join(str(v) for v in dataclasses.astuple(config))

    def _run() -> dict[str, Any]:
        result = btr.run_backtest(config)
        return apv.backtest_payload(result)

    try:
        payload = cached(key, _run, ttl=120.0)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"backtest failed: {exc}")
    if body.get("variants"):
        def _variants() -> list[dict[str, Any]]:
            return apv.variants_payload(btr.strategy_comparison(config))

        try:
            payload = dict(payload)
            payload["variants"] = cached(key + "_variants", _variants, ttl=300.0)
        except Exception as exc:
            print(f"[warn] strategy comparison: {exc}")
    payload["as_of"] = md.now_utc_label()
    return payload


@app.middleware("http")
async def kein_frontend_cache(request, call_next):
    """Frontend-Dateien nie cachen lassen.

    Der Browser haelt ES-Module hartnaeckig fest: nach einer JS-Aenderung
    zeigt die Seite den alten Stand, ohne Fehler, und man debuggt Code, der
    gar nicht laeuft. Das hat hier schon zweimal Zeit gekostet. Die API
    behaelt ihr eigenes Caching, das sitzt serverseitig in `cached`.
    """

    antwort = await call_next(request)
    if not request.url.path.startswith("/api/"):
        antwort.headers["Cache-Control"] = "no-store, must-revalidate"
    return antwort


# Die publizierten Nutzlasten unter /data ausliefern. Damit erreicht das
# Frontend sie auch ohne laufende API ueber denselben relativen Pfad, und eine
# statisch ausgelieferte Fassung braucht nur web/ plus public/data/ als data/.
if PUBLISH_DIR.exists():
    app.mount("/data", StaticFiles(directory=str(PUBLISH_DIR)), name="publish")

# Frontend ausliefern (nach den API-Routen mounten, sonst schluckt es /api/*).
WEB_DIR = ROOT / "web"
if WEB_DIR.exists():
    app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")


if __name__ == "__main__":
    import uvicorn

    # Lokal bleibt es bei 127.0.0.1:8787; der Container setzt API_HOST=0.0.0.0.
    # PaaS-Hosts (Railway, Heroku, Fly) geben nur PORT vor und erwarten, dass
    # der Prozess auf allen Schnittstellen lauscht — PORT gesetzt heisst also
    # 0.0.0.0, solange API_HOST nichts anderes sagt.
    paas_port = os.environ.get("PORT", "").strip()
    host = os.environ.get("API_HOST", "").strip() or ("0.0.0.0" if paas_port else "127.0.0.1")
    port = _env_int("API_PORT", int(paas_port) if paas_port.isdigit() else 8787)
    print(f"Terminal API auf http://{host}:{port} — Strg+C zum Beenden")
    uvicorn.run(app, host=host, port=port)
