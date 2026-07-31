#!/usr/bin/env python3
"""JSON-Bruecke zwischen den vorhandenen Terminal-Modulen und dem Web-Frontend.

Start (aus dem Repo-Root):

    pip install fastapi uvicorn
    python api/server.py

Laeuft auf http://localhost:8787 und liefert dort auch das Frontend aus web/ aus.
Endpoints (alle read-only ausser POST /api/backtest, das nur simuliert):

    GET  /api/health
    GET  /api/overview
    GET  /api/markets?query=&category=&limit=250
    GET  /api/tape?limit=250&min_cash=0
    GET  /api/leaderboard?limit=100&period=ALL&order_by=PNL
    GET  /api/wallet/{wallet}
    GET  /api/cross?query=&min_similarity=0.3&max_pairs=50
    GET  /api/risk
    GET  /api/alerts
    GET  /api/copy
    GET  /api/research/{name}
    POST /api/backtest

Nutzt ausschliesslich die bestehende Logik in app/ und src/ — keine eigene
Datenverarbeitung, nur Orchestrierung plus JSON-Mapping (app/api_views.py).
"""

from __future__ import annotations

import dataclasses
import json
import sys
import time
from pathlib import Path
from typing import Any

# Repo-Root importierbar machen, egal von wo gestartet wird.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd
from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app import api_views as apv
from app import app_settings as cfg
from app import backtester as btr
from app import scorecard as sc
from app import signals as sig
from app.analysis_views import load_publish_payload
from src import prediction_markets as md

app = FastAPI(title="Terminal API", version="0.2")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

PUBLISH_DIR = ROOT / "public" / "data"

_CACHE: dict[str, tuple[float, Any]] = {}
CACHE_TTL = 30.0  # Sekunden (Standard; einzelne Endpoints setzen mehr)


def cached(key: str, fn, *args, ttl: float = CACHE_TTL, **kwargs):
    now = time.time()
    hit = _CACHE.get(key)
    if hit and now - hit[0] < ttl:
        return hit[1]
    value = fn(*args, **kwargs)
    _CACHE[key] = (now, value)
    return value


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
            ks = md.get_kalshi_trades(limit=limit)
            if not ks.empty:
                frames.append(ks)
        except Exception as exc:
            print(f"[warn] kalshi trades: {exc}")
        if not frames:
            return pd.DataFrame()
        trades = pd.concat(frames, ignore_index=True, sort=False)
        if "time" in trades.columns:
            trades = trades.sort_values("time", ascending=False)
        return trades

    return cached(f"tape_{limit}_{min_cash}", _load, ttl=45.0)


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
        return {"rows": [], "total": 0}
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
    return {"rows": df_records(df, limit), "total": int(len(df)), "as_of": md.now_utc_label()}


@app.get("/api/tape")
def tape(limit: int = Query(250, le=1000), min_cash: float = 0.0) -> dict[str, Any]:
    trades = load_tape(limit=limit, min_cash=min_cash)
    if trades.empty:
        return {"rows": [], "total": 0}
    return {"rows": df_records(trades, limit), "total": int(len(trades)), "as_of": md.now_utc_label()}


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


@app.get("/api/wallet/{wallet}")
def wallet_detail(wallet: str) -> dict[str, Any]:
    wallet = wallet.strip()
    if not wallet.startswith("0x") or len(wallet) < 20:
        raise HTTPException(status_code=400, detail="expected a Polymarket wallet address")

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

    card = sc.wallet_scorecard(wallet, fetchers={"smart_row": _smart_row, "risk_row": _risk_row})
    positions = pd.DataFrame()
    pnl = pd.DataFrame()
    activity = pd.DataFrame()
    try:
        positions = cached(f"pos_{wallet.lower()}", md.get_polymarket_positions, wallet, 25, ttl=120.0)
    except Exception as exc:
        print(f"[warn] positions {wallet}: {exc}")
    try:
        pnl = cached(f"pnl_{wallet.lower()}", md.get_polymarket_user_pnl, wallet, "1mo", ttl=300.0)
    except Exception as exc:
        print(f"[warn] user pnl {wallet}: {exc}")
    try:
        activity = cached(f"act_{wallet.lower()}", md.get_polymarket_activity, wallet, 25, ttl=120.0)
    except Exception as exc:
        print(f"[warn] activity {wallet}: {exc}")
    return apv.wallet_detail(card, positions, pnl, activity)


@app.get("/api/cross")
def cross(
    query: str = "",
    min_similarity: float = 0.3,
    max_pairs: int = Query(50, le=150),
) -> dict[str, Any]:
    combined = load_universe(250)
    if combined.empty:
        return {"rows": [], "total": 0}
    pm = combined[combined.get("platform") == "Polymarket"]
    ks = combined[combined.get("platform") == "Kalshi"]
    try:
        candidates = md.cross_venue_candidates(pm, ks, query=query, min_similarity=min_similarity, max_pairs=max_pairs)
    except Exception as exc:
        print(f"[warn] cross venue: {exc}")
        return {"rows": [], "total": 0}
    rows = apv.cross_rows(candidates)
    return {
        "rows": rows,
        "total": len(rows),
        "as_of": md.now_utc_label(),
        "note": "Matched by title similarity — pairs are not verified to resolve identically.",
    }


@app.get("/api/risk")
def risk() -> dict[str, Any]:
    settings = cfg.load_settings()
    whale_threshold = float(settings.get("whale_threshold", 2500))
    trades = load_tape(limit=1000, min_cash=0.0)
    if trades.empty:
        raise HTTPException(status_code=503, detail="no trade tape available")

    def _build() -> dict[str, Any]:
        wallet_scores = md.whale_wallet_risk_scores(trades, whale_threshold=whale_threshold)
        event_scores = md.whale_event_risk_scores(trades, whale_threshold=whale_threshold)
        return apv.risk_payload(wallet_scores, event_scores)

    payload = cached("risk_payload", _build, ttl=60.0)
    payload["as_of"] = md.now_utc_label()
    return payload


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

    def _build() -> list[dict[str, Any]]:
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
            holder_checks=0,
            tracked_keys=set(),
        )
        return apv.alert_rows(signals)

    key = f"alerts_{min_move}_{max_spread}_{whale_threshold}_{ending_days}"
    return {"signals": cached(key, _build, ttl=60.0), "as_of": md.now_utc_label()}


@app.get("/api/copy")
def copy_state() -> dict[str, Any]:
    from src import copy_trading as ct

    db_path = ROOT / "data" / "copy_trading.sqlite"
    if not db_path.exists():
        raise HTTPException(status_code=503, detail="copy trading database not found")

    def _build() -> dict[str, Any]:
        conn = ct.connect(db_path)
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
        finally:
            conn.close()
        return apv.copy_payload(
            orders,
            positions,
            cash_events,
            equity,
            portfolio,
            contributions,
            ct.COPY_TARGET_WALLET,
            ct.SWISSTONY_LABEL,
            sizing,
        )

    try:
        payload = cached("copy_payload", _build, ttl=30.0)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"copy state unavailable: {exc}")
    payload["as_of"] = md.now_utc_label()
    return payload


@app.get("/api/research/{name}")
def research(name: str) -> dict[str, Any]:
    filename = apv.RESEARCH_FILES.get(name.strip().lower())
    if not filename:
        raise HTTPException(status_code=404, detail=f"unknown study '{name}'")
    payload = load_publish_payload(PUBLISH_DIR, filename + ".json")
    if payload is None:
        raise HTTPException(status_code=404, detail=f"no published data for '{name}'")
    if filename == "pipeline_forward":
        payload = apv.trim_pipeline_payload(payload)
    return payload


SIZING_MAP = {
    "fixed": (btr.SIZING_FIXED, "stake_fixed"),
    "pct": (btr.SIZING_PERCENT, "stake_pct"),
    "match": (btr.SIZING_PORTFOLIO, "stake_mult"),
    "kelly": (btr.SIZING_KELLY, "stake_kelly"),
}


@app.post("/api/backtest")
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
    payload["as_of"] = md.now_utc_label()
    return payload


# Frontend ausliefern (nach den API-Routen mounten, sonst schluckt es /api/*).
WEB_DIR = ROOT / "web"
if WEB_DIR.exists():
    app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")


if __name__ == "__main__":
    import uvicorn

    print("Terminal API auf http://localhost:8787 — Strg+C zum Beenden")
    uvicorn.run(app, host="127.0.0.1", port=8787)
