#!/usr/bin/env python3
"""JSON-Bruecke zwischen den vorhandenen Terminal-Modulen und dem Web-Frontend.

Start (aus dem Repo-Root):

    pip install fastapi uvicorn
    python api/server.py

Laeuft auf http://localhost:8787 und liefert dort auch das Frontend aus web/ aus.
Im Container: ``python -m uvicorn api.server:app --host 0.0.0.0 --port 8787``.

Umgebung (alles optional, Voreinstellung = lokale Entwicklung):

    API_HOST / API_PORT        Bind-Adresse fuer ``python api/server.py`` (127.0.0.1:8787)
    CORS_ORIGINS               Komma-Liste erlaubter Origins; ohne Angabe die lokalen
                               Adressen plus marketintel.dev (der dokumentierte
                               Pages-Host dieser API). Das Frontend vom selben Origin
                               braucht keinen Eintrag.
    CORS_ORIGIN_REGEX          Muster zusaetzlich zur Liste; ohne Angabe die
                               Vorschau-Domains dieses Projekts
                               (https://<branch>.prediction-market-terminal.pages.dev).
                               Die Variable ersetzt das Muster vollstaendig.
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
    COPY_DATA_DIR              Ordner der Papierbuecher (Voreinstellung data/); auf einem
                               PaaS ins gemountete Volume zeigen lassen (z. B. /data/copy_desk).
    COPY_DAEMON=1              Copy-Schleife im API-Prozess mitlaufen lassen (ein Dienst, ein
                               Volume). Lokal laeuft sie als eigener Prozess.
    COPY_DESK_PRIVATE=1        Auch Lesen von /api/copy nur mit Admin-Token.

Endpoints (read-only ausser POST /api/backtest, das nur simuliert, und dem
Paper-Copy-Desk unter /api/copy/*, der lokale Papierbuecher schreibt):

    GET  /healthz              (Alias von /api/health fuer Caddy und Compose)
    GET  /api/health
    GET  /api/overview
    GET  /api/markets?query=&category=&limit=250
    GET  /api/search?q=&limit=12   (Volltext ueber den ganzen Polymarket-Bestand
                                    plus Profile; das Universum steuert Kalshi bei)
    GET  /api/tape?limit=250&min_cash=0
    GET  /api/leaderboard?limit=100&period=ALL&order_by=PNL
    GET  /api/wallet/{wallet}      (0x + 40 hex; the whole wallet page, ~6 upstream calls,
                                    300 s cache, own per-IP limiter: 12/min, burst 6)
    GET  /api/wallet/{wallet}/similar  (top holders of its largest open markets, ~22 upstream
                                    calls cold, 600 s cache, same limiter)
    GET  /api/cross?query=&min_similarity=0.5&max_pairs=50   (gate: sim >= 0.5, volume on both venues)
    GET  /api/risk
    GET  /api/risk/book?market=<conditionId>&wallets=a,b&side=YES%20buys  (was die Wallets in dem
                                             Markt jetzt halten; hedge oder neue Wette)
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
    GET  /api/claims?lang=de|en   (Caveat-Register aus data/claims.yaml; das
                                    Frontend rendert seine Vorbehalte daraus)
    GET  /api/research/{name}
    POST /api/backtest

Nutzt ausschliesslich die bestehende Logik in app/ und src/ — keine eigene
Datenverarbeitung, nur Orchestrierung plus JSON-Mapping (app/api_views.py).
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import math
import os
import re
import sys
import threading
import time
from collections import OrderedDict
from contextlib import asynccontextmanager
from datetime import datetime, timezone
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
from app import claims as cl
from app import cross_pairs
from app import pilot_result
from app import scorecard as sc
from app import signals as sig
from app import track_record as trec
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
    """Erlaubte Origins aus CORS_ORIGINS; ohne Angabe lokale Entwicklung
    plus die produktive statische Auslieferung des Projekts.

    marketintel.dev ist der dokumentierte Pages-Host dieser API (README,
    split hosting) — dass er die eigene API rufen darf, ist ein Fakt des
    Projekts, keine Konfiguration. Vorher scheiterte genau daran das Live-
    Band: healthz antwortete, aber der Browser verwarf jede /api-Antwort
    mangels CORS-Header, und die Seite meldete API NOT REACHABLE. Die API
    bleibt read-only; die Schreibpfade des Copy-Desks schuetzt der
    Admin-Token, nicht die Origin-Liste.
    """

    raw = os.environ.get("CORS_ORIGINS", "")
    origins = [o.strip() for o in raw.split(",") if o.strip()]
    return origins or [
        "http://127.0.0.1:8787", "http://localhost:8787",
        "https://marketintel.dev", "https://www.marketintel.dev",
    ]


def _cors_origin_regex() -> str | None:
    """Origin-Muster aus CORS_ORIGIN_REGEX; ohne Angabe die Vorschau-Domains.

    Die feste Liste reicht nicht fuer Hosts, deren Vorschau-Origins wechseln:
    Cloudflare Pages erzeugt je Branch und je Commit eine eigene Subdomain
    unter prediction-market-terminal.pages.dev — auch das ein Fakt des
    Projekts. Die Umgebungsvariable ersetzt das Muster vollstaendig.
    """

    raw = os.environ.get("CORS_ORIGIN_REGEX", "").strip()
    return raw or r"https://[a-z0-9-]+\.prediction-market-terminal\.pages\.dev"


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    # Flag-Sampler (RISK_LOG_INTERVAL_MIN), siehe weiter unten; die Funktion
    # ist beim Start laengst definiert.
    start_risk_sampler()
    # Copy daemon in-process (COPY_DAEMON=1), see the paper copy desk section.
    start_copy_daemon()
    yield


app = FastAPI(title="Terminal API", version="0.2", lifespan=_lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_origin_regex=_cors_origin_regex(),
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


def _venue_frame(venue: str, fetch, sources: list[dict[str, Any]]) -> pd.DataFrame:
    """Eine Venue holen und ihr Ergebnis vermerken, statt es zu verschlucken.

    Vorher stand hier ``except Exception: print("[warn] ...")``. Die Zeile
    ging auf stdout eines Servers, den niemand liest, und die Antwort trug
    danach eine Venue weniger, ohne dass irgendetwas an ihr das sagte. Die
    Kopfzeile der Seite meldete weiter "LIVE, POLYMARKET + KALSHI": eine
    halbe Antwort, die sich als ganze ausgibt.

    Gefangen wird weiter, denn eine ausgefallene Venue soll die andere nicht
    mitnehmen. Aber der Ausfall wandert jetzt in ``sources`` und von dort in
    die Antwort, und die Oberflaeche kann ihn benennen.
    """

    try:
        frame = fetch()
    except Exception as exc:
        print(f"[warn] {venue}: {exc}")
        sources.append(apv.venue_source(venue, ok=False, error=f"{type(exc).__name__}: {exc}"))
        return pd.DataFrame()
    frame = pd.DataFrame() if frame is None else frame
    sources.append(apv.venue_source(venue, ok=True, rows=int(len(frame))))
    return frame


def load_universe(limit: int = 250) -> pd.DataFrame:
    def _load() -> pd.DataFrame:
        frames = []
        sources: list[dict[str, Any]] = []
        for name, fn in (("Polymarket", md.get_polymarket_markets), ("Kalshi", md.get_kalshi_markets)):
            frame = _venue_frame(name, lambda fn=fn: fn(limit=limit), sources)
            if not frame.empty:
                frames.append(frame.dropna(axis=1, how="all"))
        if not frames:
            return apv.with_venue_sources(pd.DataFrame(), sources)
        combined = pd.concat(frames, ignore_index=True, sort=False)
        combined = md.add_market_filter_metrics(combined)
        # Titelmuster des Tape-Klassifizierers auch fuers Universum: die
        # Rohkategorien sind fast leer (Kalshi-Parlays, Esports, Einzelspiele
        # sagen alle "Other"), die Marktseite bekam dadurch kaum Kategorien
        # zum Auswaehlen. Laeuft einmal je Cache-Fuellung, nicht je Request.
        return apv.with_venue_sources(apv.enrich_filter_categories(combined, TAPE_CLASSIFIER), sources)

    return cached(f"universe_{limit}", _load)


def load_tape(limit: int = 250, min_cash: float = 0.0) -> pd.DataFrame:
    def _load() -> pd.DataFrame:
        frames = []
        sources: list[dict[str, Any]] = []

        def _kalshi() -> pd.DataFrame:
            # Kalshi kennt keinen Cash-Filter; die 15-Minuten-Kryptomaerkte
            # drucken tausend Mikro-Trades in Sekunden. Bei einem Mindestbetrag
            # deshalb das ganze Fenster holen und hier filtern, sonst waere die
            # Kalshi-Seite des Tapes leer oder nur Staub.
            ks = md.get_kalshi_trades(limit=1000 if min_cash > 0 else limit)
            if not ks.empty and min_cash > 0 and "notional" in ks.columns:
                ks = ks[pd.to_numeric(ks["notional"], errors="coerce").fillna(0.0) >= float(min_cash)]
            if ks.empty:
                return ks
            # The feed carries tickers only (KXRTCOMPARE-INS26AUG24-INS);
            # one memoised markets lookup gives every consumer — tape,
            # risk cards, flag log — the question instead.
            return md.enrich_kalshi_tape(ks.head(limit))

        pm = _venue_frame("Polymarket", lambda: md.get_polymarket_trades(limit=limit, min_cash=min_cash), sources)
        if not pm.empty:
            frames.append(pm)
        ks = _venue_frame("Kalshi", _kalshi, sources)
        if not ks.empty:
            frames.append(ks)
        if not frames:
            return apv.with_venue_sources(pd.DataFrame(), sources)
        trades = pd.concat(frames, ignore_index=True, sort=False)
        if "time" in trades.columns:
            trades = trades.sort_values("time", ascending=False)
        return apv.with_venue_sources(trades, sources)

    return cached(f"tape_{limit}_{min_cash}", _load, ttl=45.0)


#: Kategorie fuer Tape-Zeilen ohne Treffer im Marktuniversum: erst die
#: Heuristik der Marktseite (Rohkategorie + Titel), dann die Titelmuster des
#: Risk-Screens (app.suspicion), die Matchups und Esports erkennen.
TAPE_CLASSIFIER = apv.chained_classifier(md.market_filter_category, apv.parlay_classifier, apv.context_group_classifier())


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
    quellen = apv.venue_sources(combined)
    if combined.empty:
        return {"kpis": {}, "movers": [], "anomalies": [], "ending_soon": [],
                "sources": quellen, "venues_missing": apv.missing_venues(quellen)}

    def col(name: str) -> pd.Series:
        return pd.to_numeric(combined.get(name), errors="coerce").fillna(0.0)

    vol24 = col("volume_24h")
    moves = col("change_1d")
    pm_count = int((combined.get("platform") == "Polymarket").sum())
    ks_count = int((combined.get("platform") == "Kalshi").sum())
    # Getrennt nach Einheit, nicht summiert: Polymarket meldet Dollar, Kalshi
    # zaehlt Kontrakte. Und ueber der Tagesspalte, nicht ueber dem Mischwert.
    # Beides entscheidet apv.venue_volume_24h, damit die Streamlit-Kachel
    # "Venue volume" dieselbe Groesse zeigt wie diese Kennzahl.
    vol_je_einheit = apv.venue_volume_24h(combined)

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
            # "volume_24h" stand hier als eine Summe ueber beide Venues, und
            # die war keine Groesse: Polymarket meldet Dollar, Kalshi zaehlt
            # Kontrakte (Beleg in app/venue_units.py). Zwei Felder, zwei
            # Einheiten, im Namen genannt.
            "volume_24h_usd_polymarket": float(vol_je_einheit["usd"]),
            "volume_24h_contracts_kalshi": float(vol_je_einheit["contracts"]),
            # Der Nenner der beiden Summen: wie viele der geladenen Maerkte
            # heute ueberhaupt gehandelt wurden. Ohne ihn liest sich eine
            # Tagessumme ueber ein Universum, das grossteils still lag, wie
            # ein Umsatz ueber alle.
            "markets_traded_today": int(vol_je_einheit["traded_today"]),
            "resolving_72h": int(soon_mask.sum()),
            "top_public_pnl": top_pnl,
        },
        "movers": df_records(movers[cols]),
        "anomalies": df_records(anomalies[cols]),
        "ending_soon": df_records(ending[cols]),
        # Die Venue-Kennzahlen daneben stehen je Einheit getrennt; ohne diese
        # Zeile saehe eine ausgefallene Venue aus wie eine mit null Umsatz.
        "sources": quellen,
        "venues_missing": apv.missing_venues(quellen),
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
    quellen = apv.venue_sources(combined)
    if combined.empty:
        return {"rows": [], "total": 0, "sources": quellen,
                "venues_missing": apv.missing_venues(quellen), "as_of": md.now_utc_label()}
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
    total = int(len(df))
    # Venue- UND kategorie-balanciert: rein nach Volumen bestand die Antwort
    # fast nur aus Sport-Parlays und einem einzigen Polymarket-Thema. Jede
    # (Venue, Kategorie)-Gruppe bekommt zuerst einen gleichen Anteil; was
    # eine Gruppe nicht fuellt, geht an die groesseren — innerhalb einer
    # Gruppe zaehlt weiter das Sortierkriterium.
    ordnung = sort if sort in df.columns else "volume_24h"
    if "platform" in df.columns:
        cat_col = "filter_category" if "filter_category" in df.columns else "category"
        gruppen = df["platform"].astype(str) + " · " + (df[cat_col].astype(str) if cat_col in df.columns else "")
        df = df.assign(_balance_gruppe=gruppen)
        df = apv.balanced_head(df, limit, group_col="_balance_gruppe", time_col=ordnung).drop(columns=["_balance_gruppe"])
    else:
        df = apv.balanced_head(df, limit, group_col="platform", time_col=ordnung)
    # Schlanke Zeilen: nur die Felder, die das Frontend liest (apv.MARKET_FIELDS).
    # Mit ``raw``, ``description`` und den Token-Blobs wog die Antwort fuer
    # 250 Zeilen ueber ein Megabyte, alle 30 Sekunden.
    return {"rows": apv.market_records(df, limit), "total": total, "sources": quellen,
            "venues_missing": apv.missing_venues(quellen), "as_of": md.now_utc_label()}


@app.get("/api/search")
def search(q: str = "", limit: int = Query(12, le=25)) -> dict[str, Any]:
    """Volltextsuche: Gamma public-search (ganzer Polymarket-Bestand, aktive
    Events, Profile) plus Titeltreffer aus dem gecachten Universum (bringt
    Kalshi mit). Die Suchleiste im Frontend filtert sonst nur die geladenen
    Top-Volumen-Maerkte — alles ausserhalb davon fand sie nie."""

    text = q.strip()
    if len(text) < 2:
        return {"markets": [], "wallets": [], "as_of": md.now_utc_label()}

    def _run() -> dict[str, Any]:
        markets_df, profiles = md.search_polymarket(text, limit_per_type=limit)
        rows = apv.market_records(markets_df, limit)
        try:
            universe = load_universe(1000)
        except Exception:
            universe = pd.DataFrame()
        if not universe.empty and "title" in universe.columns:
            mask = universe["title"].astype(str).str.contains(text, case=False, regex=False, na=False)
            uni_rows = apv.market_records(universe[mask], limit)
        else:
            uni_rows = []
        # Universum zuerst (traegt Kalshi und die frischeren Volumenfelder),
        # dann die reinen Gamma-Treffer; Dedupe ueber market_key.
        seen: set[str] = set()
        merged: list[dict[str, Any]] = []
        for row in uni_rows + rows:
            key = str(row.get("market_key") or row.get("ticker") or "")
            if key and key in seen:
                continue
            seen.add(key)
            merged.append(row)
            if len(merged) >= limit:
                break
        return {"markets": merged, "wallets": profiles[:limit]}

    try:
        payload = cached(f"search_{text.casefold()}_{limit}", _run, ttl=60.0)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"search unavailable: {exc}")
    return {**payload, "as_of": md.now_utc_label()}


@app.get("/api/tape")
def tape(limit: int = Query(250, le=1000), min_cash: float = 0.0) -> dict[str, Any]:
    trades = load_tape(limit=limit, min_cash=min_cash)
    # Welche Venue geantwortet hat, reist mit. Eine Antwort ohne Kalshi ist
    # ein anderer Zustand als eine Antwort, in der Kalshi nichts gedruckt
    # hat, und nur die Antwort selbst kann die beiden auseinanderhalten.
    quellen = apv.venue_sources(trades)
    if trades.empty:
        return {"rows": [], "total": 0, "sources": quellen,
                "venues_missing": apv.missing_venues(quellen),
                "categories": apv.category_coverage(pd.DataFrame()), "as_of": md.now_utc_label()}
    # Venue-balanciert statt reine Zeitreihenfolge: sonst verdraengen die
    # Kalshi-Mikro-Trades jeden Polymarket-Print aus dem Fenster.
    shown = apv.balanced_head(trades, limit)
    # Kategorie je Print: erst aus dem Marktuniversum (dieselbe Ableitung wie
    # /api/markets), sonst ueber die Titel-Heuristiken (Marktseite, dann die
    # Kontextmuster des Risk-Screens) bzw. das Kalshi-Serien-Praefix. Das
    # Universum ist ohnehin im Cache (das Frontend laedt es mit); faellt es
    # aus, bleibt das Tape ohne Universum-Treffer, aber nicht leer.
    # Faellt das Universum aus, faellt jede Zeile auf die Titel-Heuristik
    # zurueck. Das ergibt eine andere Kategorieverteilung, keine leere, und
    # die Kategorieleiste, der Filter und "Where the money flows" haengen
    # daran. Der Ausfall reist deshalb als ``categories`` mit, statt als
    # Zeile auf einem stdout zu enden, das niemand liest.
    try:
        universe = load_universe(250)
        kategorie_fehler = ""
    except Exception as exc:
        print(f"[warn] universe for tape categories: {exc}")
        universe = pd.DataFrame()
        kategorie_fehler = f"{type(exc).__name__}: {exc}"
    shown = apv.tape_rows_with_category(shown, universe, TAPE_CLASSIFIER)
    return {"rows": df_records(shown, limit), "total": int(len(trades)), "sources": quellen,
            "venues_missing": apv.missing_venues(quellen),
            "categories": apv.category_coverage(universe, error=kategorie_fehler),
            "as_of": md.now_utc_label()}


@app.get("/api/leaderboard")
def leaderboard(
    limit: int = Query(100, le=500),
    period: str = "ALL",
    order_by: str = "PNL",
) -> dict[str, Any]:
    try:
        lb = load_leaderboard(limit=limit, period=period, order_by=order_by)
    except Exception as exc:
        # Keine Zeilen UND ein Grund. Ohne den Grund liest sich der Ausfall
        # der Polymarket-Bestenliste wie eine Venue ohne Trader.
        print(f"[warn] leaderboard: {exc}")
        return {"rows": [], "total": 0, "error": f"{type(exc).__name__}: {exc}",
                "as_of": md.now_utc_label()}
    ranked = load_ranked()
    rows = apv.leaderboard_rows(lb, ranked)
    return {
        "rows": rows,
        "total": len(rows),
        "as_of": md.now_utc_label(),
        # Die beiden Volumenschwellen der Kohorte, gegen die der Score liest.
        # Sie gehoeren in die Antwort, weil sie Eigenschaften der bewerteten
        # Menge sind: das Frontend koennte sie nur schaetzen.
        "score_scale": apv.leaderboard_scale(ranked),
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
        # Dieselbe Basis und dieselbe Schwelle wie der Risk-Screen
        # (risk_screen_basis). Vorher las diese Seite ein Tape ohne
        # Mindestbetrag und ohne Kontextfilter und rechnete mit der
        # Standard-Schwelle 10.000 statt der eingestellten 2.500 — dieselbe
        # Wallet trug hier und auf dem Screen zwei verschiedene Zahlen.
        _roh, base, whale_threshold = risk_screen_basis()
        if base.empty:
            return None
        scores = md.whale_wallet_risk_scores(base, whale_threshold=whale_threshold)
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

    # Zeilen, deren realizedPnl dem eigenen Zahlungsstrom widerspricht
    # (curPrice 1 und volle Einloesung, trotzdem minus der ganze Einsatz),
    # werden aus der Aktivitaet neu gerechnet - vor allen Bloecken, damit
    # Track Record, Kalibrierung, Edge und die Closed-Tabelle dieselbe Zahl
    # sehen. Ohne Aktivitaet bleibt alles, wie die API es liefert.
    if not resolved.empty:
        try:
            resolved, korrigiert = trec.reconcile_resolved_with_activity(resolved, activity)
            if korrigiert:
                print(f"[info] {wallet}: {korrigiert} closed rows re-derived from the wallet's cash flow")
        except Exception as exc:
            print(f"[warn] resolved/activity reconciliation {wallet}: {exc}")

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


@app.get("/api/wallet/{wallet}/similar", dependencies=[Depends(wallet_route_limit)])
def wallet_similar(wallet: str) -> dict[str, Any]:
    """Wallets among the top holders of this wallet's largest open markets.

    Reads the (cached) wallet page for the open positions, then one /holders
    call per checked market and one /positions call per listed wallet — up to
    ~22 upstream reads on a cold cache, cached ten minutes. Same per-IP
    bucket as the wallet page.
    """
    from app import wallet_similar as ws

    wallet = wallet.strip().lower()
    if not WALLET_ADDRESS.match(wallet):
        raise HTTPException(status_code=400, detail="expected a Polymarket wallet address (0x + 40 hex characters)")

    def _build() -> dict[str, Any]:
        page = cached(f"wallet_page_{wallet}", build_wallet_detail, wallet, ttl=WALLET_CACHE_TTL)
        open_rows = (page.get("open_positions") or {}).get("rows") or []
        # Leaderboard rows by address for PnL / volume where the wallet is on it.
        lb: dict[str, dict[str, Any]] = {}
        try:
            frame = load_leaderboard(limit=250)
            if frame is not None and not frame.empty and "wallet" in frame:
                for _, row in frame.iterrows():
                    lb[str(row.get("wallet") or "").lower()] = row.to_dict()
        except Exception as exc:
            print(f"[warn] leaderboard for similar wallets: {exc}")
        out = ws.similar_wallets(wallet, open_rows, leaderboard=lb)
        out["as_of"] = md.now_utc_label()
        return out

    return cached(f"wallet_similar_{wallet}", _build, ttl=600.0)


#: Was /api/cross als "gate" mitmeldet, damit das Frontend den leeren Fall
#: benennen kann, ohne die Schwelle selbst zu kennen.
#: Lockere Matcher-Schranke fuer die Zaehlung "N of M candidates": was der
#: Matcher ueberhaupt fuer verwandt haelt, bevor die Schranke greift.
CROSS_CANDIDATE_FLOOR = 0.2

CROSS_GATE_NOTE = (
    "Only pairs with title similarity >= {sim:.2f} and volume on both venues are shown. "
    "Matched by title similarity — pairs are not verified to resolve identically "
    "(studies 08 and 11 in the microstructure report show two matched pairs that were different questions). "
    "A pair whose two sides ask in opposite directions, name different thresholds or resolve on "
    "different dates carries no numbers at all and is counted under 'suppressed' instead."
)

#: Wie viele Zeilen je Aufruf gegen die Buecher neu quotiert werden. Zwei
#: Abfragen je Zeile, und der Endpunkt blaettert ohnehin schon beide Boersen
#: durch; nachgeschlagen werden die Zeilen mit der groessten Netto-Spanne,
#: also die, auf die jemand reagieren wuerde.
CROSS_DEPTH_ROWS = 12


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
        if not frames:
            return pd.DataFrame()
        # Gamma sortiert nach 24h-Volumen, und diese Ordnung bewegt sich
        # zwischen den fuenf Aufrufen: derselbe Markt kann auf zwei Seiten
        # stehen und stuende dann zweimal in der Paarliste.
        zusammen = pd.concat(frames, ignore_index=True, sort=False)
        if "market_key" in zusammen.columns:
            zusammen = zusammen.drop_duplicates(subset=["market_key"], keep="first").reset_index(drop=True)
        return zusammen

    def _ks() -> pd.DataFrame:
        return md.get_kalshi_markets(limit=1000)

    try:
        pm = cached("cross_pm", _pm, ttl=300.0)
        ks = cached("cross_ks", _ks, ttl=300.0)
    except Exception as exc:
        # Die leere Antwort traegt sonst die Notiz "nichts hat die Schranke
        # genommen", also eine Messung, wo ein Abruf gescheitert ist.
        print(f"[warn] cross venue universes: {exc}")
        return {**leer, "error": f"{type(exc).__name__}: {exc}"}
    if pm.empty or ks.empty:
        return leer
    try:
        # Mit den verworfenen Paaren: was der Paar-Check aussortiert, wird
        # gezaehlt und benannt statt stillschweigend weggelassen.
        alle = cached(
            f"cross_cand_{min_similarity}_{max_pairs}",
            cross_pairs.deep_cross_candidates,
            pm,
            ks,
            min_similarity,
            max_pairs,
            True,
            ttl=300.0,
        )
        if alle is None or alle.empty or "pair_verdict" not in alle.columns:
            candidates, verworfen = (alle if alle is not None else pd.DataFrame()), pd.DataFrame()
        else:
            geprueft = alle["pair_verdict"].astype(str).eq(cross_pairs.PAIR_UNVERIFIED)
            candidates, verworfen = alle[geprueft], alle[~geprueft]
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
            def _treffer(frame: pd.DataFrame) -> pd.DataFrame:
                if frame is None or frame.empty:
                    return frame
                maske = (frame["polymarket_title"].str.contains(query.strip(), case=False, na=False)
                         | frame["kalshi_title"].str.contains(query.strip(), case=False, na=False))
                return frame[maske]
            candidates, verworfen = _treffer(candidates), _treffer(verworfen)
    except Exception as exc:
        print(f"[warn] cross venue: {exc}")
        return {**leer, "error": f"{type(exc).__name__}: {exc}"}
    categories = {}
    if "market_key" in pm.columns and "category" in pm.columns:
        categories = {
            str(key): str(cat)
            for key, cat in zip(pm["market_key"], pm["category"])
            if key is not None and cat
        }
    # Erst die Schranke, dann die Buecher: nachgeschlagen wird nur, was auch
    # angezeigt wird. Ohne diesen Schritt stand die Spanne fuer 100 Stueck
    # da, weil 100 der Clip der Gebuehrenkurve ist und nicht, weil jemand
    # nachgesehen haette, ob 100 Stueck an der Quote liegen.
    if candidates is not None and not candidates.empty:
        candidates = candidates[apv.cross_gate_mask(
            candidates, min_similarity=min_similarity, require_volume=True)]
        try:
            candidates = cached(
                f"cross_depth_{min_similarity}_{max_pairs}_{query.strip().lower()}",
                cross_pairs.with_book_depth,
                candidates,
                pm,
                ks,
                pm_book=md.get_polymarket_orderbook,
                ks_book=md.get_kalshi_orderbook,
                max_rows=CROSS_DEPTH_ROWS,
                ttl=120.0,
            )
        except Exception as exc:
            print(f"[warn] cross depth: {exc}")
    rows = apv.cross_rows(candidates, categories, min_similarity=min_similarity, require_volume=True)
    return {
        "rows": rows,
        "total": len(rows),
        "candidates_before_gate": int(len(vor_schranke)) if vor_schranke is not None else int(len(candidates)),
        "suppressed": apv.cross_suppressed(verworfen),
        "depth_rows": CROSS_DEPTH_ROWS,
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

    Genau das war das Problem an der alten Seitenschleife: sie brach bei der
    ersten Stoerung mit ``print("[warn] ...")`` ab und lieferte, was bis
    dahin da war. Vier von acht Seiten sind rund ein halber Tag, und der
    Risk-Screen schrieb daneben weiter "No co-trading cluster in the current
    window. That is a result, not a gap." Die Schleife steht deshalb jetzt in
    ``md.paged_polymarket_trades`` und fuehrt ihren Abbruch am Frame mit.
    """

    def _load() -> pd.DataFrame:
        zusammen = md.paged_polymarket_trades(min_cash, pages=seiten, page_size=1000)
        record = md.sample_coverage(zusammen)
        if zusammen.empty:
            leer = pd.DataFrame()
            leer.attrs[md.SAMPLE_ATTR] = record
            return leer
        schluessel = [s for s in ("transaction_hash", "wallet", "asset") if s in zusammen.columns]
        if schluessel:
            zusammen = zusammen.drop_duplicates(subset=schluessel, keep="first")
        zusammen = zusammen.reset_index(drop=True)
        record["rows"] = int(len(zusammen))
        zusammen.attrs[md.SAMPLE_ATTR] = record
        return zusammen

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


#: Kantenregel fuer den Co-Trading-Graphen, von streng nach locker. Die
#: Leiter existiert, weil die strenge Regel auf einem Tagesband oft nichts
#: findet und ein leeres Bild keine Antwort ist. Sie ist damit aber Teil des
#: Befunds: ein Graph unter der untersten Sprosse sagt etwas anderes als
#: derselbe Graph unter der obersten. Deshalb steht die ganze Leiter in der
#: Nutzlast und nicht nur die Sprosse, die getragen hat.
CO_TRADING_LADDER: tuple[tuple[str, dict[str, Any]], ...] = (
    ("same side of at least 3 markets within 5 minutes, $10k paired notional",
     dict(window_minutes=5.0, min_shared=3, min_pair_notional=10_000.0)),
    ("same side of at least 2 markets within 5 minutes",
     dict(window_minutes=5.0, min_shared=2)),
    ("same side of at least 2 markets anywhere in the window, no simultaneity required",
     dict(window_minutes=None, min_shared=2)),
)


def co_trading_ladder(
    basis: pd.DataFrame,
    max_wallets: int = 300,
    leiter: tuple[tuple[str, dict[str, Any]], ...] = CO_TRADING_LADDER,
) -> tuple[pd.DataFrame, pd.DataFrame, list[dict[str, Any]]]:
    """Die Leiter ablaufen und offenlegen, welche Sprosse getragen hat.

    Zurueck kommen Knoten, Kanten und die Leiter selbst: je Sprosse die
    Regel im Klartext, ihre Parameter, ob sie ueberhaupt versucht wurde und
    was sie gefunden hat. Eine nicht versuchte Sprosse ist etwas anderes als
    eine, die nichts gefunden hat, und beides ist etwas anderes als die, die
    das Bild erzeugt hat — ohne diese Unterscheidung liest sich jede Grafik
    als Ergebnis der strengsten Regel.
    """

    from app import suspicion as susp

    nodes, edges = pd.DataFrame(), pd.DataFrame()
    sprossen: list[dict[str, Any]] = []
    fertig = False
    for beschreibung, kwargs in leiter:
        sprosse: dict[str, Any] = {
            "regel": beschreibung,
            "parameter": dict(kwargs),
            "versucht": not fertig,
            "wallets": None,
            "kanten": None,
            "gewaehlt": False,
        }
        if not fertig:
            treffer_nodes, treffer_edges = susp.co_trading_network(
                basis, max_wallets=max_wallets, **kwargs)
            sprosse["wallets"] = int(len(treffer_nodes))
            sprosse["kanten"] = int(len(treffer_edges))
            if not treffer_nodes.empty:
                nodes, edges = treffer_nodes, treffer_edges
                sprosse["gewaehlt"] = True
                fertig = True
        sprossen.append(sprosse)
    return nodes, edges, sprossen


def risk_screen_basis() -> tuple[pd.DataFrame, pd.DataFrame, float]:
    """(Roh-Tape, gescreenter Basis-Tape, Whale-Schwelle) fuer den Insider-Score.

    EINE Definition fuer jede Oberflaeche, die einen Insider-Score zeigt. Die
    Wallet-Seite rechnete ihn bis hierher ueber ein anderes Tape (kein
    Mindestbetrag, kein Kontextfilter) und mit der Standard-Schwelle von
    10.000 statt der eingestellten — dieselbe Wallet trug auf dem Risk-Screen
    und auf ihrer eigenen Seite zwei verschiedene Zahlen unter demselben
    Namen.

    Mit ``min_cash=0`` fressen die Mikro-Prints das Fenster: 1000 Prints jeder
    Groesse decken auf dieser Venue Minuten ab, und fast jeder gescorte
    "Markt" war ein einzelner Kleinstbetrag. Der Boden ist derselbe, ab dem
    der Scorer Verteilungs-Signale voll zaehlt (distribution_size_floor) —
    dieselben 1000 Prints tragen dann Stunden relevanten Flows statt Staub.
    Sport, Wetter und Krypto-Kursmaerkte fallen ganz raus
    (susp.EXCLUDED_CONTEXTS); ein leerer Screen ist die ehrliche Antwort,
    kein Rueckfall auf das rohe Tape.
    """

    from app import suspicion as susp

    whale_threshold, tape_floor = susp.screen_thresholds(cfg.load_settings())
    trades = load_tape(limit=1000, min_cash=tape_floor)
    if trades.empty:
        return pd.DataFrame(), pd.DataFrame(), whale_threshold
    screened = susp.filter_insider_prone_trades(trades)
    return trades, (screened if screened is not None else pd.DataFrame()), whale_threshold


def build_risk_payload() -> dict[str, Any]:
    """Der komplette Risk-Screen (Events, Wallets, Cluster, Netzwerk), 300 s gecacht.

    Von ``/api/risk`` und vom Flag-Sampler gemeinsam genutzt, damit beide
    dieselbe Rechnung und denselben Cache sehen. Wirft ``LookupError``, wenn
    kein Tape da ist.
    """

    from app import suspicion as susp

    trades, base, whale_threshold = risk_screen_basis()
    if trades.empty:
        raise LookupError("no trade tape available")

    def _build() -> dict[str, Any]:
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
            # Wie tief die Stichprobe wirklich war, gehoert neben das Bild.
            # "Kein Cluster im aktuellen Fenster" ist ein Befund, solange das
            # Fenster steht; bricht die Seitenschleife auf halber Strecke ab,
            # ist es keiner mehr, und vorher war das nicht zu unterscheiden.
            payload["cluster_sample"] = {"note": md.sample_note(md.sample_coverage(netz_tape)), "error": ""}
            # Kategorien mitgeben: ein Untermarkt heisst "Will FC Thun win on
            # 2026-08-06?" und traegt selbst kein Sportwort. Ohne den
            # Elterntitel landen ganze Spieltage als "General" im Screen.
            netz_basis = susp.filter_insider_prone_trades(
                netz_tape, _tape_categories(netz_tape))
            if netz_basis is None or netz_basis.empty:
                netz_basis = base

            nodes, edges, sprossen = co_trading_ladder(netz_basis)
            gewaehlt = next((s for s in sprossen if s["gewaehlt"]), sprossen[-1])
            regel = gewaehlt["regel"]
            regel_kwargs: dict[str, Any] = dict(gewaehlt["parameter"])

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
                # Dieselbe Regel auf einer gemischten Wallet-Spalte: was sie
                # dort noch findet, findet sie auf nichts. Darf die Antwort
                # nicht kippen, die Kontrolle ist teurer als der Graph selbst.
                try:
                    nullmodell = susp.null_model_reference(
                        netz_basis, runs=2, max_wallets=300, **regel_kwargs)
                except Exception as exc:
                    print(f"[warn] cluster null model: {exc}")
                    nullmodell = None
                payload["graph"] = apv.network_graph(
                    susp.cluster_layout(nodes), edges,
                    regel=regel, leiter=sprossen, modularitaet=modularitaet,
                    nullmodell=nullmodell,
                    wallets_im_tape=int(netz_basis["wallet"].astype(str).nunique()),
                    stand_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"))
                payload["graph"]["fenster"] = apv.tape_window_label(netz_basis)
                payload["graph"]["stichprobe"] = payload.get("cluster_sample", {}).get("note", "")
                payload["matrix"] = apv.overlap_matrix(netz_basis, nodes)
        except Exception as exc:
            # Vorher ging der ganze Block auf stdout und die Seite zeigte
            # "kein Cluster gefunden". Ein abgestuerzter Rechenweg und ein
            # leeres Ergebnis sahen gleich aus; jetzt trennt sie ein Feld.
            print(f"[warn] suspicion clusters: {exc}")
            payload["cluster_sample"] = {"note": payload.get("cluster_sample", {}).get("note", ""),
                                         "error": f"{type(exc).__name__}: {exc}"[:300]}
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
        # Die Horizonte laufen ab dem letzten Print des geflaggten Flusses,
        # lesbar wurde das Flag erst, als der Sampler es schrieb. Dazwischen
        # liegt mindestens ein Sampler-Intervall, ein +30-min-Punkt kann also
        # schon vorbei sein, bevor ihn jemand sehen konnte. price_after
        # markiert diese Eintraege, statt sie wie frische zu zeigen.
        return risk_log.price_after(
            history, start, row.get("price_at_flag"), known_at=row.get("first_seen"))

    return cached(f"flag_after_{row.get('flag_id')}_{token_id}", _load, ttl=300.0)


@app.get("/api/risk/book")
def risk_book(
    market: str = Query(..., min_length=3, max_length=120),
    wallets: str = Query(..., min_length=42, max_length=400),
    side: str = Query("", max_length=20),
) -> dict[str, Any]:
    """What the flagged wallets hold in the flagged market, read now.

    ``wallets`` is a comma list of addresses (at most five are read), ``side``
    the flagged flow ("YES buys") so the answer can say whether that flow adds
    to, reduces or hedges the wallet's book. Cached five minutes per
    (market, wallet); the market's answer is assembled from those.
    """
    from app import wallet_book as wb

    market_key = market.strip()
    if not re.fullmatch(r"0x[a-fA-F0-9]{64}", market_key):
        raise HTTPException(status_code=400, detail="market must be a Polymarket conditionId (0x + 64 hex)")
    addresses = [w.strip().lower() for w in wallets.split(",") if w.strip()]
    if not all(re.fullmatch(r"0x[a-fA-F0-9]{40}", w) for w in addresses):
        raise HTTPException(status_code=400, detail="wallets must be 0x + 40 hex addresses, comma-separated")
    flagged = side.strip()
    books = [
        cached(f"risk_book_{market_key}_{w}_{flagged.lower()}", wb.wallet_book, w, market_key, flagged, ttl=300.0)
        for w in addresses[: wb.MAX_WALLETS]
    ]
    return {
        "market_key": market_key,
        "flagged_side": flagged,
        "wallets": books,
        "dropped": max(0, len(addresses) - wb.MAX_WALLETS),
        "note": "open positions in this market from the public Data API, read now — not at flag time",
        "as_of": md.now_utc_label(),
    }


@app.get("/api/risk/log")
def risk_log_endpoint(limit: int = Query(100, ge=1, le=500), enrich: int = 0, since: str | None = None) -> dict[str, Any]:
    from app import risk_log
    from app import suspicion as susp

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
        # Die Einzelbewegungen waren da, die Quote nie: wer den Screen
        # beurteilen wollte, musste gruene Zellen zaehlen. Sie steht jetzt
        # mit n, 95-Prozent-Intervall, Sample-Badge, Stand und den
        # weggelassenen Nennern daneben.
        "scoreboard": risk_log.flag_scoreboard(rows, as_of=None, enrich_max=RISK_LOG_ENRICH_MAX) if enrich else None,
        # Dieselbe Beschriftung wie auf den Event-Karten (susp.SCORE_BANDS):
        # ein Log-Eintrag mit 72 Punkten darf hier nicht anders heissen als
        # dieselbe Zahl eine Registerkarte weiter.
        "score_name": susp.SCORE_NAME,
        "score_bands": susp.score_band_table(),
        "min_score": risk_log.min_score(),
        "dedupe_hours": risk_log.DEDUPE_HOURS,
        "sampler_interval_min": RISK_LOG_INTERVAL_MIN,
        "note": ("Every event the screen flags (score >= min_score) is logged with side, price and wallets at that "
                 "moment; 'after' is the price of the flagged side +30 min / +2 h / +24 h after the last print of "
                 "the flagged flow (Polymarket only). A horizon is null while it has not passed, carries no_print "
                 "when it passed without a trade, and already_past when it had elapsed before the sampler wrote "
                 "the flag - that move is real but no reader could have acted on it."),
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


def _read_json_list(path: Path) -> list[Any]:
    """Eine lokal gespeicherte JSON-Liste, oder eine leere. Nie eine Ausnahme:
    eine fehlende oder kaputte Liste darf einen Endpunkt nicht kippen."""

    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return data if isinstance(data, list) else []


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

    # Die lokal gespeicherte Watchlist, dieselbe Datei, die /api/track liest.
    # Hier stand eine leere Menge, also konnte kein "Watched market"-Signal
    # entstehen und der Filter SCOPE = "Watched only" lieferte immer null
    # Zeilen -- auch bei voller Liste.
    tracked_keys = apv.watchlist_market_keys(_read_json_list(ROOT / "data" / "watchlist.json"))

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
            tracked_keys=tracked_keys,
        )
        return {
            "signals": apv.alert_rows(signals),
            "rule_counts": apv.alert_rule_counts(signals),
            "rules_not_evaluated": nicht_geprueft,
        }

    # Die Watchlist gehoert in den Cache-Schluessel: sonst liefert ein Treffer
    # aus der Zeit vor der Aenderung noch eine Minute lang die alte Liste.
    watch_sig = hashlib.sha1("|".join(sorted(tracked_keys)).encode("utf-8")).hexdigest()[:12]
    key = f"alerts_{min_move}_{max_spread}_{whale_threshold}_{ending_days}_{watch_sig}"
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
#
# COPY_DATA_DIR    where the books live (default data/ under the repo). On a
#                  PaaS point it into the mounted volume, e.g. /data/copy_desk,
#                  or the desk forgets everything on the next deploy.
# COPY_DAEMON=1    run the copy loop inside this process (app/copy_daemon.py):
#                  the one-service, one-volume way to have the daemon on a
#                  host like Railway. Off by default — locally the daemon is
#                  its own process (scripts/run_copy_trader.py).
# COPY_DESK_PRIVATE=1  reads of /api/copy need the admin token as well; by
#                  default the books are readable by everyone, writable by
#                  the token holder — like the rest of the site, public read.
COPY_DATA_DIR = Path(os.environ.get("COPY_DATA_DIR", "").strip() or (ROOT / "data"))
COPY_DB_PATH = COPY_DATA_DIR / "copy_trading.sqlite"
COPY_SETTINGS_PATH = COPY_DATA_DIR / "copy_settings.json"
COPY_STATUS_PATH = COPY_DATA_DIR / "copy_trader_status.json"
COPY_STOP_PATH = COPY_DATA_DIR / "copy_trader.stop"
COPY_DAEMON_IN_PROCESS = os.environ.get("COPY_DAEMON", "").strip().lower() in {"1", "true", "yes", "on"}
COPY_DESK_PRIVATE = os.environ.get("COPY_DESK_PRIVATE", "").strip().lower() in {"1", "true", "yes", "on"}
_COPY_DAEMON_THREAD: threading.Thread | None = None


def start_copy_daemon() -> None:
    """Start the in-process copy loop when COPY_DAEMON is set (once)."""
    global _COPY_DAEMON_THREAD
    if not COPY_DAEMON_IN_PROCESS or (_COPY_DAEMON_THREAD is not None and _COPY_DAEMON_THREAD.is_alive()):
        return
    from app import copy_admin as ca
    from app import copy_daemon as cd

    # A desk that never had books starts with nobody active (the migration's
    # seed row is paused) — the daemon must not copy a wallet nobody chose.
    created = ca.ensure_desk(COPY_DB_PATH)
    config = cd.DaemonConfig(
        api_interval=30.0,
        settlement_interval=90.0,
        min_copy_notional=0.0,
        db=str(COPY_DB_PATH),
        status_file=str(COPY_STATUS_PATH),
        stop_file=str(COPY_STOP_PATH),
    )
    _COPY_DAEMON_THREAD = cd.start_thread(config)
    print(f"[copy-daemon] running in-process; books at {COPY_DB_PATH}" + (" (created fresh, seed trader paused)" if created else ""))


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

    access = _copy_write_access(request)
    if COPY_DESK_PRIVATE and not access.allowed:
        raise HTTPException(status_code=403, detail="this desk is private — reads need the admin token too")
    # A host without books where nobody may write: say so instead of conjuring
    # an empty desk. Where writes are allowed, a missing database is a desk
    # nobody has used yet: create it (seed row paused) so the form has
    # somewhere to go.
    if not COPY_DB_PATH.exists():
        if not access.allowed:
            raise HTTPException(status_code=503, detail="no paper copy desk on this host — the books live where the copy daemon runs")
        ca.ensure_desk(COPY_DB_PATH)

    def _build() -> dict[str, Any]:
        conn = ct.connect(COPY_DB_PATH)
        try:
            orders = ct.get_paper_orders(conn=conn)
            positions = ct.get_positions(conn=conn)
            cash_events = ct.get_cash_events(conn=conn)
            equity = ct.get_equity_snapshots(conn=conn)
            source_books = ct.get_source_positions(conn=conn)
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
        payload = apv.copy_payload(orders, positions, cash_events, equity, portfolio, contributions, source_wallet, source_label, sizing, source_positions=source_books)
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
    payload["write_access"] = access.as_dict()
    payload["sync"] = ca.sync_state()
    payload["daemon"] = dict(payload.get("daemon") or {}, in_process=COPY_DAEMON_IN_PROCESS)
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


@app.get("/api/claims")
def claims_register(lang: str = "") -> dict[str, Any]:
    """Das Caveat-Register aus data/claims.yaml.

    Ohne ``lang`` beide Sprachen, sonst nur die verlangte. Kein Cache-Eintrag:
    die Datei ist wenige Kilobyte gross und app.claims haelt sie ohnehin nach
    Aenderungszeit vor.
    """

    code = str(lang or "").strip().lower()
    if code and code not in cl.LANGS:
        raise HTTPException(status_code=400, detail=f"unknown language '{lang}'")
    return apv.claims_payload(code or None)


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
    followed = _read_json_list(ROOT / "data" / "followed_wallets.json")
    watchlist = _read_json_list(ROOT / "data" / "watchlist.json")
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
        # Einsatz automatisch an das Tempo der Wallet anpassen (Engine misst
        # die Hoechstzahl gleichzeitig offener Quell-Positionen).
        auto_fit=bool(body.get("auto_fit", False)),
        # Manuelle Folge-Schwelle: nur Quell-Trades ab diesem Notional
        # kopieren. Der Auto-Fit setzt bei Bedarf seine eigene.
        min_follow_notional=max(0.0, float(body.get("min_notional", 0.0))),
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
