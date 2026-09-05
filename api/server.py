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
                               (X-Forwarded-For). Traegt die Anfrage CF-Connecting-IP,
                               gewinnt der: Cloudflare setzt ihn am Rand selbst und
                               ueberschreibt, was ein Client mitschickt.
    RATE_LIMIT_TRUST_CF        0 schaltet diesen Vorrang ab (Voreinstellung 1).
                               Vertrauensmodell: der Vorrang ist nur richtig, wenn der
                               Ursprung ausschliesslich ueber den Cloudflare-Proxy
                               erreichbar ist — auf Railway heisst das: die Custom
                               Domain ist proxied und der erzeugte *.up.railway.app-
                               Host ist abgehaengt (docs/PRODUCTION_READINESS.md §8a).
                               Ist der Ursprung direkt erreichbar, kann jeder Client
                               den Header faelschen und bekommt je Anfrage einen
                               frischen Eimer; dann 0 setzen und nur den Header lesen,
                               den der eigene Proxy (Caddy) neu schreibt.
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
    ROUTE_WARM_MIN             > 0 haelt die kalten Routen warm: alle N Minuten laufen
                               /api/cross und, wenn der Flag-Sampler aus ist, die
                               Risk-Rechnung im Hintergrund (0 = aus; 4 passt zum
                               300-s-Cache). Der erste Besucher wartete sonst 20-25 s.

    COPY_ADMIN_TOKEN           Schreibzugriff auf den Paper-Copy-Desk (/api/copy/*): ohne
                               Token nur von dieser Maschine (Loopback, kein Proxy-Header);
                               mit Token nur mit Header X-Admin-Token, von ueberall.
                               Derselbe Token oeffnet GET /api/admin/backup, das Zip
                               des Volumes (.github/workflows/backup-volume.yml).
    COPY_DATA_DIR              Ordner der Papierbuecher (Voreinstellung data/); auf einem
                               PaaS ins gemountete Volume zeigen lassen (z. B. /data/copy_desk).
    COPY_DAEMON=1              Copy-Schleife im API-Prozess mitlaufen lassen (ein Dienst, ein
                               Volume). Lokal laeuft sie als eigener Prozess.
    COPY_DESK_PRIVATE=1        Auch Lesen von /api/copy nur mit Admin-Token.

Endpoints (read-only ausser POST /api/backtest, das nur simuliert, und dem
Paper-Copy-Desk unter /api/copy/*, der lokale Papierbuecher schreibt):

    GET  /healthz              (Alias von /api/health fuer Caddy und Compose)
    GET  /api/health
    GET  /api/overview             (nur JSON-API: das Web-Frontend unter web/ liest die
                                    Route nicht)
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
                                             Polymarket-Flags den Preis +30 min/+2 h/+24 h;
                                             Zeilen als kompakte Sicht, risk_log.compact_flags)
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
import sqlite3
import sys
import tempfile
import threading
import time
import zipfile
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
from app import ledger
from app import pilot_result
from app import scorecard as sc
from app import signals as sig
from app import study_datasets as sds
from app import track_record as trec
from app import venue_fees as vf
from app.analysis_views import load_publish_payload
from src import prediction_markets as md
from src import trade_store as ts
from app import wallet_origin as wo


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
    # Entity-Scan-Worker (ENTITY_SCAN_INTERVAL_H), fuer den Deploy-Host mit
    # Volume: dort gibt es keinen Taskplaner fuer den Wallet-Graphen.
    start_entity_scan_worker()
    # Kalte Routen warm halten (ROUTE_WARM_MIN), siehe Route-Waermer.
    start_route_warmer()
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
#: Trades und Aufloesungen eines Backtest-Fensters (je Wallet und Tage).
BACKTEST_DATA_TTL = 600.0


# Eine Sperre je Schluessel: zwei gleichzeitige Anfragen nach demselben
# Ergebnis (Doppelklick, zwei Tabs, der Variantenlauf direkt nach dem
# Hauptlauf) rechneten beide den vollen Weg — bei einem Backtest zweimal
# 30.000 Activity-Zeilen. Die zweite wartet jetzt auf die erste und liest
# dann aus dem Cache.
_INFLIGHT: dict[str, threading.Lock] = {}


def cached(key: str, fn, *args, ttl: float = CACHE_TTL, **kwargs):
    now = time.time()
    with _CACHE_LOCK:
        hit = _CACHE.get(key)
        if hit and now - hit[0] < ttl:
            _CACHE.move_to_end(key)
            return hit[1]
        sperre = _INFLIGHT.get(key)
        if sperre is None:
            sperre = _INFLIGHT[key] = threading.Lock()
    with sperre:
        # Waehrend des Wartens kann die erste Anfrage den Wert abgelegt haben.
        with _CACHE_LOCK:
            hit = _CACHE.get(key)
            if hit and time.time() - hit[0] < ttl:
                _CACHE.move_to_end(key)
                return hit[1]
        # Der Aufruf selbst laeuft ohne die globale Sperre: er wartet oft auf das Netz.
        try:
            value = fn(*args, **kwargs)
        finally:
            with _CACHE_LOCK:
                _INFLIGHT.pop(key, None)
        with _CACHE_LOCK:
            _CACHE[key] = (time.time(), value)
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
CF_CONNECTING_IP = "CF-Connecting-IP"
RATE_LIMIT_TRUST_CF = os.environ.get("RATE_LIMIT_TRUST_CF", "1").strip().lower() not in {"0", "false", "no", "off"}
EXPENSIVE_LIMITER = TokenBucketLimiter(
    per_minute=_env_float("RATE_LIMIT_PER_MIN", 6.0),
    burst=_env_int("RATE_LIMIT_BURST", 3),
)
GLOBAL_LIMITER = TokenBucketLimiter(
    per_minute=_env_float("RATE_LIMIT_GLOBAL_PER_MIN", 120.0),
    burst=_env_int("RATE_LIMIT_GLOBAL_BURST", 40),
)


def _forwarded_address(request: Request) -> str | None:
    """Besucheradresse aus dem Proxy-Header; None, wenn kein Proxy davor steht.

    Reihenfolge: CF-Connecting-IP vor dem konfigurierten Header. Cloudflare
    setzt CF-Connecting-IP am Rand selbst und ueberschreibt einen vom Client
    mitgeschickten — vertrauenswuerdig also genau dann, wenn der Ursprung
    nur ueber den Proxy erreichbar ist (Railway: Custom Domain proxied,
    *.up.railway.app abgehaengt; Compose: Port 8787 nie veroeffentlicht).
    Ohne Cloudflare davor waere der Header faelschbar, darum
    RATE_LIMIT_TRUST_CF=0 dort, wo Caddy allein am Rand steht und
    X-Forwarded-For fuer fremde Clients neu schreibt (api/ratelimit.py
    client_ip beschreibt dieses Modell).
    """

    if RATE_LIMIT_TRUST_CF:
        cf = (request.headers.get(CF_CONNECTING_IP) or "").strip()
        if cf:
            return cf
    return request.headers.get(RATE_LIMIT_IP_HEADER)


def _request_ip(request: Request) -> str:
    host = request.client.host if request.client else None
    return client_ip(_forwarded_address(request), host)


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


_URL_IN_FEHLER = re.compile(r"https?://([^/\s?#]+)[^\s]*")


def _oeffentlich(exc: BaseException | str) -> str:
    """Fehlertext fuer eine Antwort nach draussen: Upstream-URLs auf den Host gekuerzt.

    Vorher stand in /api/search die volle Gamma-URL samt der rohen Suchanfrage
    des Besuchers im Fehlertext und in /api/tape die Kalshi-Adresse mit allen
    Parametern — eine Karte der Upstreams, die kein Leser braucht. Der Host
    bleibt stehen, damit die Meldung noch sagt, welche Quelle fehlte.
    """

    return _URL_IN_FEHLER.sub(lambda m: m.group(1), str(exc))


SUCHTEXT_MAX = 200


def _suchtext_pruefen(text: str) -> str:
    """Suchstrings sind Filter, keine Dokumente: ueber 200 Zeichen 422.

    Als Query(max_length=...) am Parameter ginge es auch, aber die Routen
    werden in Tests und vom Route-Waermer direkt aufgerufen, und dann ist der
    Standardwert kein String mehr.
    """

    if len(text) > SUCHTEXT_MAX:
        raise HTTPException(status_code=422, detail=f"query too long (max {SUCHTEXT_MAX} characters)")
    return text


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
        sources.append(apv.venue_source(venue, ok=False, error=f"{type(exc).__name__}: {_oeffentlich(exc)}"))
        return pd.DataFrame()
    frame = pd.DataFrame() if frame is None else frame
    sources.append(apv.venue_source(venue, ok=True, rows=int(len(frame))))
    return frame


def load_universe(limit: int = 250) -> pd.DataFrame:
    def _load() -> pd.DataFrame:
        frames = []
        sources: list[dict[str, Any]] = []
        # Kalshi ueber /events mit verschachtelten Maerkten (get_kalshi_markets_deep):
        # /markets?limit=N ist EINE Seite in API-Reihenfolge und bestand
        # gemessen fast nur aus quotelosen KXMVE-Parlays mit 0 Kontrakten —
        # die Marktseite zeigte 95 Kalshi-Zeilen, alle tot, "0 contracts".
        # Derselbe Cache-Schluessel wie beim Cross-Venue-Scan, damit das
        # Universum einmal je fuenf Minuten geladen wird, nicht je Endpunkt.
        def _kalshi_universe(limit: int = limit) -> pd.DataFrame:
            frame = cached("cross_ks", lambda: md.get_kalshi_markets_deep(pages=12, page_size=200), ttl=300.0)
            if frame.empty:
                return frame
            # Nur Maerkte mit einem Preis, nach Tagesumsatz absteigend: die
            # balanced_head unten nimmt je Gruppe die Spitze dieser Ordnung.
            mit_preis = frame[pd.to_numeric(frame.get("yes_price"), errors="coerce").notna()]
            if "volume_24h" in mit_preis.columns:
                mit_preis = mit_preis.sort_values("volume_24h", ascending=False, na_position="last")
            return mit_preis.head(max(int(limit), 250) * 4).reset_index(drop=True)

        for name, fn in (("Polymarket", md.get_polymarket_markets), ("Kalshi", _kalshi_universe)):
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

    # Fuenf Minuten statt der 30-Sekunden-Vorgabe: das Universum haengt am
    # Kalshi-Events-Cursor (12 Seiten) und aendert sich nicht im Sekundentakt.
    return cached(f"universe_{limit}", _load, ttl=300.0)


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


# HEAD ausdruecklich dazu: Uptime-Monitore und ``curl -I`` fragen so, und ein
# @app.get allein antwortet darauf 404 — das sah einmal wie eine fehlende
# Route auf dem Deploy-Host aus, waehrend GET laengst 200 lieferte.
@app.api_route("/api/health", methods=["GET", "HEAD"])
@app.api_route("/healthz", methods=["GET", "HEAD"], include_in_schema=False)
def health() -> dict[str, Any]:
    # commit: der Git-Stand, aus dem Railway das Image gebaut hat
    # (RAILWAY_GIT_COMMIT_SHA, leer lokal). smoke-api.yml wartet darauf,
    # dass hier der gerade gepushte Stand steht, bevor es prueft.
    return {"ok": True, "time": md.now_utc_label(), "commit": os.environ.get("RAILWAY_GIT_COMMIT_SHA", "")}


@app.get("/api/overview")
def overview(limit: int = Query(250, ge=1, le=1000)) -> dict[str, Any]:
    """Unused by the web frontend (nothing under web/ reads it); kept for the JSON API only."""
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
    limit: int = Query(250, ge=1, le=1000),
) -> dict[str, Any]:
    query = _suchtext_pruefen(query)
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
def search(q: str = "", limit: int = Query(12, ge=1, le=25)) -> dict[str, Any]:
    """Volltextsuche: Gamma public-search (ganzer Polymarket-Bestand, aktive
    Events, Profile) plus Titeltreffer aus dem gecachten Universum (bringt
    Kalshi mit). Die Suchleiste im Frontend filtert sonst nur die geladenen
    Top-Volumen-Maerkte — alles ausserhalb davon fand sie nie."""
    q = _suchtext_pruefen(q)

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
        raise HTTPException(status_code=503, detail=f"search unavailable: {_oeffentlich(exc)}")
    return {**payload, "as_of": md.now_utc_label()}


@app.get("/api/tape")
def tape(limit: int = Query(250, ge=1, le=1000), min_cash: float = 0.0) -> dict[str, Any]:
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
    limit: int = Query(100, ge=1, le=500),
    period: str = "ALL",
    order_by: str = "PNL",
) -> dict[str, Any]:
    try:
        lb = load_leaderboard(limit=limit, period=period, order_by=order_by)
    except Exception as exc:
        # Keine Zeilen UND ein Grund. Ohne den Grund liest sich der Ausfall
        # der Polymarket-Bestenliste wie eine Venue ohne Trader.
        print(f"[warn] leaderboard: {exc}")
        return {"rows": [], "total": 0, "error": f"{type(exc).__name__}: {_oeffentlich(exc)}",
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
        # Mit derselben First-Seen-Map wie der Risk-Screen, sonst truege
        # dieselbe Wallet dort und hier wieder zwei verschiedene Zahlen.
        scores = md.whale_wallet_risk_scores(
            base, whale_threshold=whale_threshold,
            known_since=store_known_since(base["wallet"].astype(str)) if "wallet" in base else {})
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
    activity_error: str = ""
    try:
        activity, truncated = fetch_wallet_activity(wallet)
    except Exception as exc:
        # Frueher blieb es bei der Zeile auf stdout, und weiter unten ging
        # ``activity_truncated=False`` an die Ansicht: eine Behauptung von
        # Vollstaendigkeit ueber einem Abruf, der nie angekommen ist. Die
        # Seite las daraus null Trades, null Tage aktiv und ein leeres
        # Fenster, also dasselbe Bild wie eine Wallet ohne jede Aktivitaet.
        activity_error = f"{type(exc).__name__}: {exc}"
        print(f"[warn] activity {wallet}: {exc}")
    if not activity.empty:
        activity.attrs["window_truncated"] = bool(truncated)

    # Zeilen, deren realizedPnl dem eigenen Zahlungsstrom widerspricht
    # (curPrice 1 und volle Einloesung, trotzdem minus der ganze Einsatz),
    # werden aus der Aktivitaet neu gerechnet - vor allen Bloecken, damit
    # Track Record, Kalibrierung, Edge und die Closed-Tabelle dieselbe Zahl
    # sehen. Ohne Aktivitaet bleibt alles, wie die API es liefert.
    if not resolved.empty:
        try:
            resolved, korrigiert = trec.reconcile_resolved_with_activity(
                resolved, activity, window_truncated=bool(truncated or activity_error)
            )
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
    positions_error: str = ""
    pnl_error: str = ""
    try:
        positions = md.get_polymarket_positions(wallet, WALLET_POSITIONS_LIMIT)
    except Exception as exc:
        positions_error = f"{type(exc).__name__}: {exc}"
        print(f"[warn] positions {wallet}: {exc}")
    try:
        pnl = md.get_polymarket_user_pnl(wallet, "All")
    except Exception as exc:
        pnl_error = f"{type(exc).__name__}: {exc}"
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

    payload = apv.wallet_detail(
        card, positions, pnl, activity,
        resolved=resolved, resolved_capped=capped, activity_truncated=truncated, activity_error=activity_error,
        classify=TAPE_CLASSIFIER, pseudonym=pseudonym, as_of=md.now_utc_label(),
        pnl_window="All", positions_requested=WALLET_POSITIONS_LIMIT,
    )
    # Die Scorecard fuehrt ihre eigenen Ausfaelle in ``errors`` mit, und die
    # Seite zeigt sie unter "LIMITS OF THIS READ". Die drei Abrufe dieses
    # Endpunkts standen nur auf stdout: ein leerer Positionsblock sah aus wie
    # eine Wallet ohne offene Positionen. Sie gehen denselben Weg.
    fehler = dict(payload.get("errors") or {})
    for name, text in (("open positions", positions_error), ("profile pnl curve", pnl_error), ("activity", activity_error)):
        if text:
            fehler[name] = text
    payload["errors"] = fehler
    # Erster gespeicherter Print aus dem Tape-Store: eine Untergrenze des
    # Alters, kein Geburtsdatum. None heisst nur, dass der Store die Wallet
    # (noch) nicht gesehen hat — nicht, dass sie neu ist.
    erster = store_known_since([wallet]).get(wallet.lower())
    payload["store_first_seen"] = (
        datetime.fromtimestamp(int(erster), tz=timezone.utc).isoformat(timespec="seconds")
        if erster else None)
    return payload


@app.get("/api/wallet/{wallet}", dependencies=[Depends(wallet_route_limit)])
def wallet_detail(wallet: str) -> dict[str, Any]:
    wallet = wallet.strip()
    if not WALLET_ADDRESS.match(wallet):
        raise HTTPException(status_code=400, detail="expected a Polymarket wallet address (0x + 40 hex characters)")
    return cached(f"wallet_page_{wallet.lower()}", build_wallet_detail, wallet.lower(), ttl=WALLET_CACHE_TTL)


@app.get("/api/wallet/{wallet}/flows", dependencies=[Depends(expensive_route_limit)])
def wallet_flows(wallet: str) -> dict[str, Any]:
    """On-Chain-Geldfluesse der Wallet: app/onchain_flows hinter einer Route.

    Der Kern (Protokoll- vs. externe Fluesse, Funding-Spanne, Peak-Exposure)
    war fertig und getestet, aber nur per Einmal-Skript erreichbar. Hier
    liest ihn ein begrenzter Etherscan-Walk (app/flow_fetch): Antwort in
    Sekunden, und ``complete`` sagt, ob die Historie ganz gelesen wurde —
    eine gekappte Summe ist eine Untergrenze und heisst auch so. Ohne
    konfigurierten Key antwortet die Route 503, statt so zu tun, als gaebe
    es keine Fluesse. Eine Stunde Cache: die Chain-Historie einer Wallet
    aendert sich rueckwirkend nicht.
    """

    from app import flow_fetch as ff

    wallet = wallet.strip().lower()
    if not WALLET_ADDRESS.match(wallet):
        raise HTTPException(status_code=400, detail="expected a Polymarket wallet address (0x + 40 hex characters)")

    def _build() -> dict[str, Any]:
        api_key = ff.load_api_key(ROOT)
        if not api_key:
            raise ff.FlowFetchError("no Etherscan API key configured (ETHERSCAN_API_KEY)")
        report = ff.wallet_flow_report(wallet, api_key)
        erster = store_known_since([wallet]).get(wallet)
        report["store_first_seen"] = (
            datetime.fromtimestamp(int(erster), tz=timezone.utc).isoformat(timespec="seconds")
            if erster else None)
        report["as_of"] = md.now_utc_label()
        return report

    try:
        return cached(f"wallet_flows_{wallet}", _build, ttl=3600.0)
    except ff.FlowFetchError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


def _store_behavior(wallets: list[str] | None = None) -> dict[str, Any]:
    """Stufe-3-Verhalten aus dem lokalen Tape-Store; fail-soft leer.

    Verhalten wird angezeigt und fuehrt nie zusammen (Wallet-Graph Phase 3).
    Mit ``wallets`` filtert die Menge das ERGEBNIS, nicht das Band (der
    Komplementaer-Partner einer Entity-Wallet steht oft ausserhalb der
    Entity); ohne Menge kommt der Blick ueber das ganze gespeicherte Fenster,
    gekappt auf die groessten Wallets, wie die Detektoren es ausweisen.
    """

    from app import behavior as bhv

    leer = {"available": False, "fingerprints": [], "complementary_pairs": [],
            "note": "no trade store on this host, so no behaviour read"}
    try:
        ziel = ts.store_path()
        if not ziel.exists():
            return leer
        conn = ts.connect(ziel)
        try:
            fenster = ts.load_window(conn, days=ts.window_days())
        finally:
            conn.close()
        report = bhv.behavior_report(fenster, wallets=wallets)
    except Exception as exc:
        print(f"[warn] store behavior: {exc}")
        return leer
    report["available"] = True
    report["note"] = ("Tier 3 behaviour patterns from the stored tape: shown next to the "
                      "entities, never used to merge accounts.")
    return report


@app.get("/api/graph", dependencies=[Depends(wallet_route_limit)])
def graph_page() -> dict[str, Any]:
    """Die Wallet-Graph-Seite: Entities, Kandidaten und Verhalten in einer Antwort.

    Liest nur die lokal abgeleiteten Bestaende (Entity-Graph und Tape-Store),
    macht selbst keine Chain- oder Feed-Abrufe. Auf einem Host ohne die
    Dateien sagt die Antwort das, statt eine leere Flaeche zu zeigen, die
    wie "keine Verknuepfungen" aussieht.
    """

    from app import claims
    from app import entity_graph as eg

    def _build() -> dict[str, Any]:
        pfad = Path(os.environ.get("ENTITY_GRAPH_PATH", "").strip() or eg.DEFAULT_GRAPH_PATH)
        if not pfad.exists():
            return {"available": False,
                    "note": "no entity graph on this host; run scripts/run_entity_scan.py",
                    "behavior": _store_behavior(),
                    "as_of": md.now_utc_label()}
        conn = eg.connect(pfad)
        try:
            payload = eg.graph_overview(conn)
        finally:
            conn.close()
        payload["available"] = True
        payload["behavior"] = _store_behavior()
        payload["caveat"] = claims.disclaimer("screen_not_proof", "en")
        payload["as_of"] = md.now_utc_label()
        return payload

    try:
        return cached("graph_overview", _build, ttl=300.0)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"entity graph unavailable: {_oeffentlich(exc)}")


@app.get("/api/wallet/{wallet}/entity", dependencies=[Depends(wallet_route_limit)])
def wallet_entity(wallet: str) -> dict[str, Any]:
    """Die Entity einer Wallet aus dem lokalen Graphen (Wallet-Graph Phase 2).

    Liest nur die vom Scan-Runner (scripts/run_entity_scan.py) abgeleitete
    Datenbank, macht selbst keine Chain-Abrufe. Drei Antworten, sauber
    getrennt: kein Graph vorhanden (dieser Host verknuepft nicht), Wallet
    nicht gescannt (nicht untersucht ist kein Befund) und die Entity samt
    Kanten und Belegen. Stufe-2-Kandidaten heissen auch so; der Satz aus dem
    Claims-Register steht an jeder Antwort mit Inhalt.
    """

    from app import claims
    from app import entity_graph as eg

    wallet = wallet.strip().lower()
    if not WALLET_ADDRESS.match(wallet):
        raise HTTPException(status_code=400, detail="expected a Polymarket wallet address (0x + 40 hex characters)")

    def _build() -> dict[str, Any]:
        pfad = Path(os.environ.get("ENTITY_GRAPH_PATH", "").strip() or eg.DEFAULT_GRAPH_PATH)
        if not pfad.exists():
            return {"wallet": wallet, "available": False, "scanned": False,
                    "note": "no entity graph on this host; run scripts/run_entity_scan.py",
                    "as_of": md.now_utc_label()}
        conn = eg.connect(pfad)
        try:
            payload = eg.entity_view(conn, wallet)
            payload["stats"] = eg.graph_stats(conn)
        finally:
            conn.close()
        if payload.get("scanned"):
            payload["behavior"] = _store_behavior(list(payload.get("entity_wallets") or []) + [wallet])
        payload["available"] = True
        payload["caveat"] = claims.disclaimer("screen_not_proof", "en")
        payload["as_of"] = md.now_utc_label()
        return payload

    try:
        return cached(f"wallet_entity_{wallet}", _build, ttl=300.0)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"entity graph unavailable: {_oeffentlich(exc)}")


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
    "A pair whose two sides ask in opposite directions, name different thresholds or competitions, "
    "mix an election with its nomination, or resolve on different dates carries no numbers at all "
    "and is counted under 'suppressed' instead."
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
    max_pairs: int = Query(150, ge=1, le=150),
) -> dict[str, Any]:
    query = _suchtext_pruefen(query)
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
        # /markets?limit=1000 war EINE Seite in API-Reihenfolge und bestand
        # fast nur aus quotelosen Parlays (20 von 1000 Zeilen mit Preis,
        # Messung 2026-08-31); die Seite meldete dann monatelang "NO PAIR
        # CLEARS THE GATE" als waere das eine Eigenschaft des Marktes.
        # /events mit verschachtelten Maerkten blaettert das echte Universum
        # durch, wie src/kalshi_recorder.py es vormacht.
        return md.get_kalshi_markets_deep(pages=12, page_size=200)

    try:
        pm = cached("cross_pm", _pm, ttl=300.0)
        ks = cached("cross_ks", _ks, ttl=300.0)
    except Exception as exc:
        # Die leere Antwort traegt sonst die Notiz "nichts hat die Schranke
        # genommen", also eine Messung, wo ein Abruf gescheitert ist.
        print(f"[warn] cross venue universes: {exc}")
        return {**leer, "error": f"{type(exc).__name__}: {_oeffentlich(exc)}"}
    if pm.empty or ks.empty:
        return leer
    try:
        # EIN Matcher-Lauf fuer alles: an der lockeren Zaehl-Schranke und mit
        # den verworfenen Paaren. Die strengere Gate-Sicht ist eine reine
        # Teilmenge davon — die beste Entsprechung je Markt haengt nicht von
        # der Schranke ab, die Schranke filtert nur —, also waere ein zweiter
        # Lauf dieselben ~25 s Titelvergleich noch einmal. Seit das
        # Kalshi-Universum echt ist (20k Maerkte statt einer Parlay-Seite),
        # entscheiden diese Sekunden, ob der kalte Aufruf unter dem
        # Frontend-Timeout bleibt. Cap 1000 je Klasse heisst praktisch
        # "ungekappt"; gekappt wird je Sicht weiter unten.
        alle = cached(
            f"cross_cand_{CROSS_CANDIDATE_FLOOR}_full",
            cross_pairs.deep_cross_candidates,
            pm,
            ks,
            CROSS_CANDIDATE_FLOOR,
            1000,
            True,
            ttl=300.0,
        )
        vor_schranke_n = 0
        if alle is None or alle.empty or "pair_verdict" not in alle.columns:
            candidates, verworfen = (alle if alle is not None else pd.DataFrame()), pd.DataFrame()
        else:
            geprueft = alle["pair_verdict"].astype(str).eq(cross_pairs.PAIR_UNVERIFIED)
            sim = pd.to_numeric(alle["similarity"], errors="coerce").fillna(0.0)
            # Wie viele Paare der Matcher unterhalb der Schranke ueberhaupt
            # findet — damit die Seite "N of M candidates clear the gate"
            # sagen kann statt nur "nothing".
            vor_schranke_n = int(geprueft.sum())
            candidates = alle[geprueft & (sim >= min_similarity)].head(max_pairs)
            verworfen = alle[~geprueft & (sim >= min_similarity)].head(max_pairs)
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
        return {**leer, "error": f"{type(exc).__name__}: {_oeffentlich(exc)}"}
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
        "candidates_before_gate": vor_schranke_n,
        "suppressed": apv.cross_suppressed(verworfen),
        "depth_rows": CROSS_DEPTH_ROWS,
        "gate": gate,
        "as_of": md.now_utc_label(),
        "note": CROSS_GATE_NOTE.format(sim=min_similarity),
        # Der allgemeine Polymarket-Taker-Satz ist nicht eindeutig belegt, und
        # die NET-OF-FEES-Spalte ruht auf ihm. Der Satz steht als Konstante in
        # app/venue_fees.py und wird hier gereicht, nicht nacherzaehlt.
        "fee_note": vf.POLYMARKET_RATE_DISPUTE_NOTE,
        "fee_rate_documented": vf.POLYMARKET_DISPUTED_RATE,
        "fee_rate_low": vf.POLYMARKET_DISPUTED_RATE_LOW,
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

    Ein Tag ist trotzdem zu kurz, um Struktur zu sehen, die sich ueber
    Wochen aufbaut — deshalb faellt die Regelleiter so oft auf die unterste
    Sprosse. Liegt der persistente Speicher (src/trade_store.py, gefuellt
    von scripts/run_trade_ingest.py) vor, wird das Live-Band deshalb um
    dessen Fenster erweitert; die ``store_*``-Felder im Zuschnitt-Vermerk
    sagen, wie viel davon kam. Ohne Speicherdatei ist dieser Schritt ein
    Durchlauf ohne Wirkung.
    """

    def _load() -> pd.DataFrame:
        zusammen = md.paged_polymarket_trades(min_cash, pages=seiten, page_size=1000)
        record = md.sample_coverage(zusammen)
        if zusammen.empty:
            zusammen = pd.DataFrame()
            zusammen.attrs[md.SAMPLE_ATTR] = record
        else:
            schluessel = [s for s in ("transaction_hash", "wallet", "asset") if s in zusammen.columns]
            if schluessel:
                zusammen = zusammen.drop_duplicates(subset=schluessel, keep="first")
            zusammen = zusammen.reset_index(drop=True)
            record["rows"] = int(len(zusammen))
            zusammen.attrs[md.SAMPLE_ATTR] = record
            # TRADE_STORE_RECORD=1: was ohnehin geholt wurde, dem Speicher
            # geben — so waechst er auch auf dem API-Host, Standard aus.
            ts.maybe_record(zusammen)
        return ts.extend_tape(zusammen, min_cash=min_cash)

    return cached(f"deep_tape_{seiten}_{min_cash}", _load, ttl=300.0)


def store_known_since(wallets: Any) -> dict[str, int]:
    """Erster gespeicherter Print je Wallet aus dem Trade-Store; fail-soft leer.

    Untergrenze des Alters, kein Geburtsdatum: der Store kennt eine Wallet
    erst, seit der Ingest laeuft, und ``prune`` loescht nur Prints, nie die
    First-Seen-Tabelle. Fuer das Frische-Signal reicht genau diese Richtung
    (siehe ``md.whale_wallet_risk_scores``): wen der Store schon vor dem
    Tagesfenster kannte, der ist bewiesenermassen nicht neu.
    """

    try:
        ziel = ts.store_path()
        if not ziel.exists():
            return {}
        conn = ts.connect(ziel)
        try:
            return ts.first_seen_map(conn, wallets)
        finally:
            conn.close()
    except Exception as exc:
        print(f"[warn] trade store first-seen: {exc}")
        return {}


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
    # Two passes. The title pass drops nine prints in ten (sports, weather,
    # price ladders) at no cost; the parent-event titles (cached 10 min) are
    # then looked up only for what survived, and catch the sub-markets that
    # carry no sports word of their own ("Will Mexico win on 2026-06-11?").
    # Looking them up for the whole tape cost minutes per scan.
    vorfilter = susp.filter_insider_prone_trades(trades)
    if vorfilter is None or vorfilter.empty:
        return trades, pd.DataFrame(), whale_threshold
    screened = susp.filter_insider_prone_trades(vorfilter, _tape_categories(vorfilter))
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
        # Echter First-Seen aus dem Tape-Store: eine Wallet, die der Store
        # schon vor diesem Fenster kannte, ist nicht "sample-fresh", egal wie
        # spaet sie im Ein-Tages-Band auftaucht. Ohne Store bleibt die Map
        # leer und das Signal rechnet wie bisher.
        bekannt = store_known_since(base["wallet"].astype(str)) if "wallet" in base else {}
        # The measured first trade of every whale-sized wallet in the window
        # (app/wallet_origin.py): from the store when known, else one venue
        # call each within the budget. What the lookup did rides along in
        # the payload, so "no fresh wallet" and "did not ask" stay apart.
        origins: dict[str, Any] = {}
        origin_meta: dict[str, Any] = {}
        try:
            kandidaten = wo.origin_candidates(base, whale_threshold=whale_threshold)
            origins, origin_meta = wo.first_trade_map(kandidaten)
        except Exception as exc:
            print(f"[warn] wallet origins: {exc}")
            origin_meta = {"error": f"{type(exc).__name__}: {_oeffentlich(exc)}"[:200]}
        # One ladder for every surface (susp.screen_tape): base scores,
        # fresh-cluster and timing bonuses, first-trade points, the context
        # multiplier with the parent-event titles, then the flow details the
        # cards and the flag log need. Each step leaves its points in a
        # column (component_*), so the card can say WHY.
        ergebnis = susp.screen_tape(
            base, whale_threshold=whale_threshold, known_since=bekannt,
            origins=origins, market_categories=_tape_categories(base))
        wallet_scores, event_scores = ergebnis.wallets, ergebnis.events
        fresh, coord = ergebnis.fresh, ergebnis.coord
        payload = apv.risk_payload(wallet_scores, event_scores)
        payload["origin_lookup"] = {
            **origin_meta,
            "fresh_days": susp.fresh_trade_days(),
            "young_days": susp.YOUNG_TRADE_DAYS,
            "note": ("First trade per wallet from the venue, one call per wallet never asked before, "
                     "kept in the trade store. A wallet whose first trade lies under fresh_days before "
                     "its print is fresh; asked counts the whale-sized wallets of this window, skipped "
                     "the ones beyond the budget."),
        }
        try:
            # Der Netzwerk-Tape geht bewusst tiefer als der Screen-Tape: das
            # letzte Tausend Prints deckt auf dieser Venue rund eine Minute ab,
            # und in einer Minute teilt niemand mehr als einen Markt. Liegt
            # der persistente Trade-Store vor, hat load_deep_tape das Band
            # bereits um dessen Fenster erweitert (ts.extend_tape).
            netz_tape = load_deep_tape()
            # Wie tief die Stichprobe wirklich war, gehoert neben das Bild.
            # "Kein Cluster im aktuellen Fenster" ist ein Befund, solange das
            # Fenster steht; bricht die Seitenschleife auf halber Strecke ab,
            # ist es keiner mehr, und vorher war das nicht zu unterscheiden.
            vermerk = md.sample_coverage(netz_tape)
            payload["cluster_sample"] = {
                "note": " ".join(teil for teil in (md.sample_note(vermerk), ts.store_note(vermerk)) if teil),
                "error": "",
            }
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
                                         "error": f"{type(exc).__name__}: {_oeffentlich(exc)}"[:300]}
        return payload

    return cached("risk_payload", _build, ttl=300.0)


def _record_risk_flags(payload: dict[str, Any]) -> None:
    """Flag-Log fuettern; darf die Antwort nie kippen."""

    try:
        from app import risk_log

        result = risk_log.record_flags(payload.get("events") or [])
        if result.get("written") or result.get("updated"):
            print(f"[risk-log] {result['written']} new, {result['updated']} updated -> {result['path']}")
        # The wallets too: a single fresh wallet that clears the screen must
        # leave a trace even when its market's card did not.
        wallets = risk_log.record_wallet_flags(payload.get("wallets") or [])
        if wallets.get("written") or wallets.get("updated"):
            print(f"[risk-log] wallets: {wallets['written']} new, {wallets['updated']} updated -> {wallets['path']}")
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
        "note": ("open positions in this market from the public Data API, read now — not at flag time; "
                 "settled-but-unredeemed shares are reported as settled_shares and rows the feed did not "
                 "price as unpriced_shares, neither of them as a book"),
        "as_of": md.now_utc_label(),
    }


@app.get("/api/risk/log")
def risk_log_endpoint(limit: int = Query(100, ge=1, le=500), enrich: int = 0, since: str | None = None,
                      kind: str = "event") -> dict[str, Any]:
    from app import risk_log
    from app import suspicion as susp

    if str(kind or "event").lower() == "wallet":
        # The wallet log: one row per venue, wallet and UTC day at or above
        # the flag floor, with the measured first trade and the flags.
        wallet_rows = risk_log.read_wallet_flags(limit=limit, since=since)
        return {
            "kind": "wallet",
            "rows": wallet_rows,
            "count": len(wallet_rows),
            "score_name": susp.SCORE_NAME,
            "score_bands": susp.score_band_table(),
            "min_score": risk_log.min_score(),
            "dedupe_hours": risk_log.DEDUPE_HOURS,
            "sampler_interval_min": RISK_LOG_INTERVAL_MIN,
            "fresh_days": susp.fresh_trade_days(),
            "note": ("Every wallet the screen lists at or above min_score is logged once per venue, wallet and UTC "
                     "day with its score, flags, context group, the market it was mostly in and the measured first "
                     "trade (days before its last print here; the state says when nobody measured it)."),
            "as_of": md.now_utc_label(),
        }
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
    # Die Datei ist das Protokoll, die Antwort die Sicht: die Prosa der
    # Komponenten, side_split und flags liest die Log-Registerkarte nie,
    # sie waren aber zwei Drittel der Bytes (435 KB je Seitenaufruf). Erst
    # anreichern (price-after liest die volle Zeile), dann kuerzen.
    rows = risk_log.compact_flags(rows)
    return {
        "rows": rows,
        "count": len(rows),
        "enriched": enriched,
        "enrich_max": RISK_LOG_ENRICH_MAX,
        "wallets_max": risk_log.COMPACT_MAX_WALLETS,
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
                 "the flag - that move is real but no reader could have acted on it. Rows are the compact view "
                 "of the log: components carry key, label, value and max, top_wallets the wallets_max largest "
                 "by notional with wallets_total counting them all."),
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


# --- Route-Waermer (kalte Routen auf dem Deploy-Host) -------------------------
#: > 0 haelt die teuren Caches warm: alle N Minuten laufen /api/cross (zwei
#: Venue-Universen plus Matcher, rund 20 s kalt) und, wenn der Flag-Sampler
#: nicht laeuft, die Risk-Rechnung (rund 25 s kalt) einmal im Hintergrund.
#: Gemessen am 2026-09-04: der erste Besucher nach einer stillen Viertel-
#: stunde wartete genau diese Zeit. Unter dem 300-s-Cache-TTL rechnet ein
#: Intervall von vier Minuten jede Runde neu; laenger heisst gelegentlich kalt.
ROUTE_WARM_MIN = max(0.0, _env_float("ROUTE_WARM_MIN", 0.0))
_WARMER_STARTED = threading.Event()


def warm_routes_once() -> dict[str, str]:
    """Eine Runde: jede Route fuer sich, ein Fehler stoppt die anderen nicht."""

    schritte = [("cross", lambda: cross(query="", min_similarity=apv.CROSS_MIN_SIMILARITY, max_pairs=150))]
    if not _SAMPLER_STARTED.is_set():
        schritte.append(("risk", build_risk_payload))
    ergebnis: dict[str, str] = {}
    for name, fn in schritte:
        try:
            fn()
            ergebnis[name] = "ok"
        except Exception as exc:
            ergebnis[name] = f"{type(exc).__name__}: {exc}"
            print(f"[warm] {name}: {exc}")
    return ergebnis


def _route_warmer_loop(interval_s: float) -> None:
    print(f"[warm] routes every {interval_s / 60:.1f} min")
    while True:
        warm_routes_once()
        time.sleep(max(60.0, interval_s))


def start_route_warmer() -> bool:
    """Startet den Waermer genau einmal; False, wenn aus oder schon gestartet."""

    if ROUTE_WARM_MIN <= 0 or _WARMER_STARTED.is_set():
        return False
    _WARMER_STARTED.set()
    threading.Thread(
        target=_route_warmer_loop, args=(ROUTE_WARM_MIN * 60.0,), name="route-warmer", daemon=True).start()
    return True


# --- Entity-Scan-Worker (Wallet-Graph auf dem Deploy-Host) -------------------
#: > 0 startet den Entity-Scan als Worker-Thread im API-Prozess, alle N
#: Stunden ein Durchgang. Fuer den Deploy-Host gedacht: dort gibt es keinen
#: Taskplaner, die Graph-Datei liegt auf dem Volume (ENTITY_GRAPH_PATH), und
#: der API-Prozess ist der einzige, der dauerhaft laeuft - dasselbe Muster
#: wie Flag-Sampler und Copy-Daemon. Lokal bleibt der Schalter aus; dort
#: scannt die geplante Task MarketIntelEntityScan, und zwei Schreiber auf
#: demselben Graphen gibt es so nie.
ENTITY_SCAN_INTERVAL_H = max(0.0, _env_float("ENTITY_SCAN_INTERVAL_H", 0.0))
#: Wie viele auffaellige Wallets (Insider-Score, aus dem Tape-Store) je
#: Durchgang anstehen; die Rescan-Drossel im Scan haelt das billig.
ENTITY_SCAN_FLAGGED = max(1, _env_int("ENTITY_SCAN_FLAGGED", 40))
_ENTITY_SCAN_STARTED = threading.Event()


def _entity_scan_loop(interval_s: float) -> None:
    from app import entity_graph as eg
    from app import entity_scan as esc
    from app import flow_fetch as ff

    print(f"[entity-scan] worker every {interval_s / 3600.0:g} h, flagged {ENTITY_SCAN_FLAGGED}")
    while True:
        try:
            api_key = ff.load_api_key(ROOT)
            if not api_key:
                # Ohne Key kann der Durchgang nichts; der Worker bleibt am
                # Leben, denn der Key kann mit dem naechsten Deploy kommen.
                print("[warn] entity scan worker: no ETHERSCAN_API_KEY configured")
            else:
                pfad = Path(os.environ.get("ENTITY_GRAPH_PATH", "").strip() or eg.DEFAULT_GRAPH_PATH)
                esc.scan_pass(pfad, api_key, flagged=ENTITY_SCAN_FLAGGED)
        except Exception as exc:
            print(f"[warn] entity scan worker: {exc}")
        time.sleep(max(600.0, interval_s))


def start_entity_scan_worker() -> bool:
    """Startet den Scan-Worker genau einmal; False, wenn aus oder gestartet."""

    if ENTITY_SCAN_INTERVAL_H <= 0 or _ENTITY_SCAN_STARTED.is_set():
        return False
    _ENTITY_SCAN_STARTED.set()
    thread = threading.Thread(
        target=_entity_scan_loop, args=(ENTITY_SCAN_INTERVAL_H * 3600.0,),
        name="entity-scan-worker", daemon=True)
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


def _delivery_aggregates() -> dict[str, Any] | None:
    """Die Zahlen des Zustellprotokolls, oder None, wenn keines da ist.

    Ein fehlendes oder unlesbares Protokoll gibt None zurueck; die Ansicht
    sagt dann, dass sie nichts weiss, statt eine Null zu zeigen, die wie eine
    gemessene Null aussieht.
    """

    pfad = ROOT / ledger.DEFAULT_LEDGER_PATH
    if not pfad.exists():
        return None
    try:
        conn = ledger.init_ledger(pfad)
    except Exception:  # noqa: BLE001
        return None
    try:
        return ledger.delivery_aggregates(conn)
    except Exception:  # noqa: BLE001
        return None
    finally:
        try:
            conn.close()
        except Exception:
            pass


@app.get("/api/alerts")
def alerts(
    min_move: float = 0.03,
    max_spread: float = 0.07,
    min_whale: float = 0.0,
    ending_days: int = 7,
    min_holder: float = 0.25,
) -> dict[str, Any]:
    settings = cfg.load_settings()
    whale_threshold = min_whale or float(settings.get("whale_threshold", 2500))
    combined = load_universe(250)
    trades = load_tape(limit=250, min_cash=0.0)
    if combined.empty and trades.empty:
        raise HTTPException(status_code=503, detail="no market data available")

    # Die Halter-Pruefung lief hier fest auf 0 und wurde als "not evaluated by
    # this endpoint" gemeldet -- das liest sich wie eine Eigenschaft des
    # Endpunkts. Sie haengt an einer Einstellung, die es gibt, also laeuft sie
    # jetzt, wenn die Einstellung sie einschaltet, und der Hinweis nennt den
    # Schalter mit Namen und Wert, wenn sie aus ist. Jede Pruefung kostet
    # einen zusaetzlichen Holder-Aufruf, deshalb bleibt der Standard 0.
    holder = apv.holder_check_state(settings.get(apv.HOLDER_CHECK_SETTING, 0))
    holder_threshold = min(0.95, max(0.05, float(min_holder or 0.25)))

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
            holder_threshold=holder_threshold,
            holder_checks=holder["checks"],
            tracked_keys=tracked_keys,
            fetch_holders=(lambda market_key: md.get_polymarket_holders(market_key)) if holder["enabled"] else None,
        )
        return {
            "signals": apv.alert_rows(signals),
            "rule_counts": apv.alert_rule_counts(signals),
            "rules_not_evaluated": holder["rules_not_evaluated"],
        }

    # Die Watchlist gehoert in den Cache-Schluessel: sonst liefert ein Treffer
    # aus der Zeit vor der Aenderung noch eine Minute lang die alte Liste.
    watch_sig = hashlib.sha1("|".join(sorted(tracked_keys)).encode("utf-8")).hexdigest()[:12]
    key = (
        f"alerts_{min_move}_{max_spread}_{whale_threshold}_{ending_days}"
        f"_{holder['checks']}_{holder_threshold}_{watch_sig}"
    )
    state_path = ROOT / "data" / "alert_scanner_state.json"
    scanner_state: dict[str, Any] = {}
    if state_path.exists():
        try:
            geladen = json.loads(state_path.read_text(encoding="utf-8"))
            if isinstance(geladen, dict):
                scanner_state = geladen
        except (OSError, json.JSONDecodeError):
            pass
    gebaut = cached(key, _build, ttl=60.0)
    return {
        "signals": gebaut["signals"],
        "rule_counts": gebaut["rule_counts"],
        "rules_not_evaluated": gebaut["rules_not_evaluated"],
        "holder_check": holder,
        # Zwei verschiedene Zahlen, und die Seite braucht beide: page_size ist
        # der Seitenschritt der Tabelle, delivered_cap der Schnitt, hinter dem
        # der Endpunkt selbst nichts mehr schickt. shown_limit bleibt als
        # Seitenschritt stehen, damit ein aelteres Frontend weiterlaeuft.
        "shown_limit": apv.ALERT_ROW_LIMIT,
        "page_size": apv.ALERT_ROW_LIMIT,
        "delivered_cap": apv.ALERT_ROW_CAP,
        "deliveries": apv.alert_delivery_view(_delivery_aggregates(), scanner_state),
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
    # forwarding header (CF-Connecting-IP, the configured one or the plain
    # X-Forwarded-For) marks the request as remote — and a forged
    # "X-Forwarded-For: 127.0.0.1" must not talk its way in either, so the
    # forwarded address is only named, never trusted as loopback.
    forwarded = _forwarded_address(request) or request.headers.get("X-Forwarded-For")
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


# --- Sicherung des Volumes ------------------------------------------------------
# Auf dem Deploy-Host liegen Papierbuecher, Wallet-Graph und Flag-Log auf einem
# Volume, das sonst niemand sichert. /api/admin/backup packt sie in ein Zip —
# SQLite ueber die Backup-API, also konsistent, auch waehrend der Copy-Daemon
# schreibt — und verlangt denselben Token wie die Schreibpfade des Copy-Desks.
# .github/workflows/backup-volume.yml holt das Zip taeglich ab.
def backup_dateien() -> list[Path]:
    """Was gesichert wird: nur, was existiert, jede Datei einmal."""

    from app import entity_graph as eg
    from app import risk_log

    kandidaten = [
        COPY_DB_PATH, COPY_SETTINGS_PATH, COPY_STATUS_PATH,
        Path(os.environ.get("ENTITY_GRAPH_PATH", "").strip() or eg.DEFAULT_GRAPH_PATH),
        risk_log.log_path(),
    ]
    gesehen: set[Path] = set()
    dateien: list[Path] = []
    for pfad in kandidaten:
        pfad = Path(pfad)
        if pfad.is_file() and pfad.resolve() not in gesehen:
            gesehen.add(pfad.resolve())
            dateien.append(pfad)
    return dateien


def _sqlite_kopie(pfad: Path) -> bytes:
    """Konsistente Kopie ueber die Backup-API: eine Dateikopie mitten in einer
    Transaktion waere eine kaputte Datenbank."""

    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as tmp:
        tmp_pfad = Path(tmp.name)
    try:
        quelle = sqlite3.connect(str(pfad))
        kopie = sqlite3.connect(str(tmp_pfad))
        try:
            with kopie:
                quelle.backup(kopie)
        finally:
            kopie.close()
            quelle.close()
        return tmp_pfad.read_bytes()
    finally:
        tmp_pfad.unlink(missing_ok=True)


def backup_zip_schreiben(ziel: Path, dateien: list[Path]) -> dict[str, Any]:
    manifest: dict[str, Any] = {"created_utc": md.now_utc_label(), "files": []}
    namen: set[str] = set()
    with zipfile.ZipFile(ziel, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for pfad in dateien:
            name = pfad.name if pfad.name not in namen else f"{pfad.parent.name}__{pfad.name}"
            namen.add(name)
            daten = _sqlite_kopie(pfad) if pfad.suffix == ".sqlite" else pfad.read_bytes()
            zf.writestr(name, daten)
            manifest["files"].append({
                "name": name, "source": str(pfad), "bytes": len(daten),
                "sha256": hashlib.sha256(daten).hexdigest(),
            })
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))
    return manifest


@app.get("/api/admin/backup", dependencies=[Depends(copy_write_guard)], include_in_schema=False)
def admin_backup():
    from fastapi.responses import FileResponse
    from starlette.background import BackgroundTask

    dateien = backup_dateien()
    if not dateien:
        raise HTTPException(status_code=404, detail="nothing to back up: no data files on this host")
    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
        ziel = Path(tmp.name)
    manifest = backup_zip_schreiben(ziel, dateien)
    stempel = re.sub(r"[^0-9]", "", str(manifest["created_utc"]))[:12]
    return FileResponse(
        str(ziel), media_type="application/zip", filename=f"marketintel-volume-{stempel}.zip",
        background=BackgroundTask(lambda: ziel.unlink(missing_ok=True)))


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
        raise HTTPException(status_code=503, detail=f"copy state unavailable: {_oeffentlich(exc)}")
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
    if filename == "microstructure":
        # Die Datensaetze neben den Berichten werden beim Lesen nachgetragen,
        # nicht nur beim Publizieren: sonst zeigte eine Nutzlast, die vor
        # dieser Aenderung geschrieben wurde, die Links erst nach dem
        # naechsten Publish-Lauf. Verlinkt wird nur, was im Repo liegt.
        payload = sds.with_datasets(payload)
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
def resolved(limit: int = Query(250, ge=1, le=500)) -> dict[str, Any]:
    def _load() -> list[dict[str, Any]]:
        closed = md.get_polymarket_closed_markets(limit=limit)
        return apv.resolved_rows(closed)

    try:
        rows = cached(f"resolved_{limit}", _load, ttl=300.0)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"closed markets unavailable: {_oeffentlich(exc)}")
    return {
        "rows": rows,
        "total": len(rows),
        # Was der Feed hergibt und was nicht. Ohne diesen Satz sieht ein
        # Abrechnungspreis aus wie ein letzter Preis vor der Abrechnung.
        "price_note": apv.RESOLVED_PRICE_NOTE,
        "as_of": md.now_utc_label(),
    }


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
def market_history(market_key: str, days: int = Query(1, ge=1, le=90), interval: str = "5m") -> dict[str, Any]:
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
        raise HTTPException(status_code=503, detail=f"price history unavailable: {_oeffentlich(exc)}")
    return {"points": points, "as_of": md.now_utc_label()}


SIZING_MAP = {
    "fixed": (btr.SIZING_FIXED, "stake_fixed"),
    "pct": (btr.SIZING_PERCENT, "stake_pct"),
    "match": (btr.SIZING_PORTFOLIO, "stake_mult"),
    "kelly": (btr.SIZING_KELLY, "stake_kelly"),
}


def _trader_portfolio(wallet: str) -> dict[str, Any]:
    # Portfolio-Groesse der Quell-Wallet fuer "Match trader %": offene
    # Positionen zum Marktwert plus USDC-Kasse. Die Kasse kommt vom
    # Polygon-RPC; ist er nicht erreichbar, steht das im Ergebnis, statt
    # dass die Kasse still als null gilt.
    from src import copy_trading as ct

    positions = md.get_polymarket_positions(wallet, limit=250)
    positions_value = float(pd.to_numeric(positions["value"], errors="coerce").fillna(0.0).sum()) if positions is not None and not positions.empty and "value" in positions else 0.0
    cash: float | None
    try:
        cash = float(ct.fetch_polygon_usdc_balance(wallet))
    except Exception:
        cash = None
    return {
        "positions_value": positions_value,
        "cash": cash,
        "cash_read": cash is not None,
        "total": positions_value + (cash or 0.0),
        "open_positions": int(len(positions)) if positions is not None else 0,
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
    # "Match trader %" setzt die Portfolio-Groesse der Wallet voraus; ohne
    # sie waere jeder Einsatz null und jeder Kauf "out of cash".
    portfolio: dict[str, Any] | None = None
    if sizing_mode == btr.SIZING_PORTFOLIO:
        try:
            portfolio = cached(f"bt_portfolio_{wallet.lower()}", _trader_portfolio, wallet, ttl=BACKTEST_DATA_TTL)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"trader portfolio could not be read: {exc}")
        if float(portfolio.get("total", 0.0) or 0.0) <= 0.0:
            raise HTTPException(
                status_code=400,
                detail="this trader's portfolio size could not be read (no open positions, cash unreadable) — pick Fixed $ or % of bankroll",
            )
    config = btr.BacktestConfig(
        wallet=wallet,
        # Bis zu einem Jahr; der Zeilen-Deckel der Engine (30.000 Trades)
        # schneidet aktive Wallets frueher ab und sagt das im Ergebnis.
        days=max(1, min(365, int(body.get("window_days", 30)))),
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
        trader_portfolio_value=float(portfolio["total"]) if portfolio else 0.0,
    )
    key = "bt_" + "_".join(str(v) for v in dataclasses.astuple(config))
    # Die Daten des Fensters (Trades in Zeitscheiben, Aufloesungen) haengen
    # nur an Wallet und Fenster und bleiben zehn Minuten liegen: jede
    # Einstellung danach ist ein Replay in Sekunden statt ein neuer
    # Minutenlauf gegen die Data API.
    daten_key = f"bt_data_{wallet.lower()}_{config.days}"

    def _daten() -> btr.WindowData:
        return btr.load_window_data(config)

    def _run() -> dict[str, Any]:
        daten = cached(daten_key, _daten, ttl=BACKTEST_DATA_TTL)
        # Preisverlaeufe fuer die Bewertungskurve; sie bleiben im
        # WindowData-Cache, jeder weitere Lauf im Fenster liest sie dort.
        result = btr.run_backtest(config, data=daten, fetch_price_history=md.get_polymarket_price_history_lifetime)
        payload = apv.backtest_payload(result)
        payload["data_loaded_at"] = daten.loaded_at.isoformat()[:16] + "Z"
        payload["data_rows"] = int(len(daten.trades)) if daten.trades is not None else 0
        if portfolio:
            payload["trader_portfolio"] = portfolio
        return payload

    try:
        payload = cached(key, _run, ttl=120.0)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"backtest failed: {_oeffentlich(exc)}")
    if body.get("variants"):
        def _variants() -> list[dict[str, Any]]:
            daten = cached(daten_key, _daten, ttl=BACKTEST_DATA_TTL)
            return apv.variants_payload(btr.strategy_comparison(config, data=daten))

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


# Schutzheader der JSON-Antworten. Die Frontend-Dateien bekommen ihre Header
# am Rand (web/_headers auf Pages, deploy/Caddyfile selbstgehostet) und bleiben
# hier unberuehrt; die API ist auf api.marketintel.dev ein eigener Host, den
# keine der beiden Dateien erreicht. JSON braucht weder Skript noch Rahmen
# noch Referrer, also die engste Policy. Cache-Control bleibt Sache der Routen.
API_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
}


@app.middleware("http")
async def api_schutzheader(request, call_next):
    """Schutzheader auf alles unter /api/ und auf /healthz, sonst nichts.

    Dazu: auf einem api.-Host ist das mitgelieferte Frontend eine zweite,
    indexierbare Kopie der Seite (api.marketintel.dev/ lieferte die ganze
    SPA). Die Dateien bleiben erreichbar — lokal und selbstgehostet ist
    derselbe Prozess die Seite —, tragen dort aber X-Robots-Tag: noindex.
    """

    antwort = await call_next(request)
    pfad = request.url.path
    if pfad.startswith("/api/") or pfad == "/healthz":
        for name, wert in API_SECURITY_HEADERS.items():
            antwort.headers.setdefault(name, wert)
    elif request.headers.get("host", "").lower().startswith("api."):
        antwort.headers.setdefault("X-Robots-Tag", "noindex")
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
