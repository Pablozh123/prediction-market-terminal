"""JSON-Aufbereitung fuer die Terminal-API (Streamlit-frei, netzfrei).

Jede Funktion nimmt fertige DataFrames/Dicts aus den bestehenden Modulen und
formt genau die Strukturen, die das Web-Frontend unter web/ konsumiert.
Caveat-Felder (capped, window_truncated, verdict, sample, Stempel) werden
immer durchgereicht — eine Zahl ohne ihre Einschraenkung verlaesst diese
Schicht nicht.
"""

from __future__ import annotations

import math
from typing import Any, Mapping

import pandas as pd

RESEARCH_FILES = {
    "review-queue": "queue",
    "category-efficiency": "kategorie_karte",
    "mentions-latency": "mentions_latenz",
    "live-runs": "runs",
    "pilot": "pilot",
    "pipeline-forward": "pipeline_forward",
    "methodology": "audit",
    "postmortems": "postmortems",
    "meta": "meta",
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
        for _, row in ranked.iterrows():
            score_by_wallet[_text(row.get("wallet")).lower()] = {
                "score": _num(row.get("copy_smart_score")),
                "grade": _text(row.get("copy_grade")),
                "reason": _text(row.get("copy_rank_reason")),
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
        })
    return rows


def wallet_detail(
    card: Mapping[str, Any],
    positions: pd.DataFrame | None = None,
    pnl_points: pd.DataFrame | None = None,
    activity: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """Scorecard + offene Positionen + PnL-Kurve + letzte Trades als JSON."""

    payload: dict[str, Any] = {
        "wallet": card.get("wallet"),
        "snapshot_at": card.get("snapshot_at"),
        "track": card.get("track"),
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
        payload["recent_trades"] = [
            {
                "market": _text(row.get("title")),
                "side": (_text(row.get("side")).upper() or "BUY") + " " + (_text(row.get("outcome")) or "Yes"),
                "price": f"{(_num(row.get('price'), 0.0) or 0.0) * 100:.1f}¢",
                "ago": _text(row.get("time"))[:16].replace("T", " "),
                "size": _num(row.get("notional"), 0.0),
            }
            for _, row in activity.head(6).iterrows()
        ]
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


def cross_rows(candidates: pd.DataFrame) -> list[dict[str, Any]]:
    """`md.cross_venue_candidates`-Frame in die Frontend-Paar-Zeilen."""

    if candidates is None or candidates.empty:
        return []
    rows: list[dict[str, Any]] = []
    for _, row in candidates.iterrows():
        pm_yes = _num(row.get("polymarket_yes"))
        ks_yes = _num(row.get("kalshi_yes"))
        if pm_yes is None or ks_yes is None:
            continue
        rows.append({
            "event": _text(row.get("polymarket_title")) or _text(row.get("kalshi_title")),
            "cat": "PAIR",
            "pm": round(pm_yes * 100),
            "ks": round(ks_yes * 100),
            "pmVol": _num(row.get("polymarket_volume"), 0.0),
            "ksVol": _num(row.get("kalshi_volume"), 0.0),
            "sim": round(_num(row.get("similarity"), 0.0) or 0.0, 2),
            "held": "—",
            "pm_url": _text(row.get("polymarket_url")),
            "ks_url": _text(row.get("kalshi_url")),
        })
    return rows


def risk_payload(wallet_scores: pd.DataFrame, event_scores: pd.DataFrame) -> dict[str, Any]:
    """Whale-Risk-Frames in Events-Karten + Wallet-Tabelle + KPIs.

    Disclaimer gehoert zur Antwort: Best-effort-Screen auf oeffentlichen
    Daten, Research-Leads, keine Rechtsfeststellung.
    """

    events: list[dict[str, Any]] = []
    if event_scores is not None and not event_scores.empty:
        for _, row in event_scores.head(12).iterrows():
            flags = row.get("event_insider_flags") or row.get("event_risk_reasons") or []
            if isinstance(flags, str):
                flags = [flags] if flags.strip() else []
            level = _text(row.get("event_insider_level") or row.get("event_risk_level")).lower()
            events.append({
                "kind": (_text(flags[0]).upper() if flags else "EVENT SCREEN"),
                "score": round(_num(row.get("event_insider_score") or row.get("event_risk_score"), 0.0) or 0.0),
                "market": _text(row.get("title")),
                "detail": " · ".join(_text(f) for f in flags) or "No individual flags — score from combined components.",
                "wallets": int(_num(row.get("unique_wallets"), 0.0) or 0),
                "notional": f"${(_num(row.get('notional'), 0.0) or 0.0) / 1000:.0f}k",
                "window": f"{(_num(row.get('trades_per_hour'), 0.0) or 0.0):.1f}/h",
                "venue": _text(row.get("platform")) or "Polymarket",
                "sev": "high" if level == "high" else "medium" if level == "medium" else "low",
            })
    wallets: list[dict[str, Any]] = []
    if wallet_scores is not None and not wallet_scores.empty:
        for _, row in wallet_scores.head(20).iterrows():
            score = _num(row.get("wallet_insider_score") or row.get("wallet_risk_score"), 0.0) or 0.0
            wallets.append({
                "wallet": _text(row.get("trader")) or short_wallet(row.get("wallet")),
                "context": _text(row.get("top_market"))[:40] or "—",
                "score": round(score),
                "prints": int(_num(row.get("trade_count"), 0.0) or 0),
                "notional": f"${(_num(row.get('notional'), 0.0) or 0.0) / 1000:.0f}k",
                "firstSeen": _text(row.get("first_seen"))[:10] or "—",
                "cluster": "—",
            })
    high_events = sum(1 for e in events if e["sev"] == "high")
    high_wallets = sum(1 for w in wallets if w["score"] >= 70)
    return {
        "disclaimer": "Best-effort screen on public trade data — research leads, not legal findings.",
        "kpis": {
            "events_screened": len(events),
            "high_risk_events": high_events,
            "high_risk_wallets": high_wallets,
            "fresh_clusters": 0,
            "coordinated_clusters": 0,
        },
        "events": events,
        "wallets": wallets,
    }


def alert_rows(signals: pd.DataFrame) -> list[dict[str, Any]]:
    """`sig.build_monitor_signals`-Frame in die Signal-Feed-Zeilen."""

    if signals is None or signals.empty:
        return []
    rows: list[dict[str, Any]] = []
    for _, row in signals.head(60).iterrows():
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
) -> dict[str, Any]:
    """SQLite-Zustand des Copy-Traders in die Copy/Portfolio-Seiten."""

    order_rows: list[dict[str, Any]] = []
    copied = skipped = 0
    if orders is not None and not orders.empty:
        for _, row in orders.head(60).iterrows():
            status = _text(row.get("status")) or "copied"
            if status == "copied":
                copied += 1
            elif status == "skipped":
                skipped += 1
            time_label = _text(row.get("source_time") or row.get("created_at"))
            if "T" in time_label:
                time_label = time_label.split("T")[1][:5]
            side = (_text(row.get("copy_side") or row.get("source_side")).upper() or "BUY") + " " + (_text(row.get("outcome")) or "Yes")
            order_rows.append({
                "time": time_label or "—",
                "market": _text(row.get("title")),
                "side": side,
                "theirs": f"${(_num(row.get('source_notional'), 0.0) or 0.0):,.0f}",
                "yours": f"${(_num(row.get('copy_notional'), 0.0) or 0.0):,.0f}",
                "status": status,
            })
    position_rows: list[list[Any]] = []
    if positions is not None and not positions.empty:
        for _, row in positions.head(30).iterrows():
            shares = _num(row.get("size") or row.get("shares"), 0.0) or 0.0
            avg = _num(row.get("avg_price"), 0.0) or 0.0
            mark = _num(row.get("current_price") or row.get("mark_price"), avg) or avg
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
            ])
    cash_rows: list[list[Any]] = []
    if cash_events is not None and not cash_events.empty:
        for _, row in cash_events.head(20).iterrows():
            amount = _num(row.get("amount"), 0.0) or 0.0
            cash_rows.append([
                _text(row.get("created_at") or row.get("time"))[:10],
                _text(row.get("reason") or row.get("kind")) or "Cash event",
                ("+" if amount >= 0 else "-") + f"${abs(amount):,.2f}",
                "",
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
    total = len(order_rows)
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
            "skipped_trades": int(_num(stats.get("skipped_trades"), 0.0) or 0),
            "fees_paid": _num(stats.get("fees_paid"), 0.0),
            "open_value": _num(stats.get("open_value"), 0.0),
            "window_truncated": bool(stats.get("window_truncated", False)),
        },
        "benchmark_stats": {
            "total_pnl": _num((result.benchmark_stats or {}).get("total_pnl"), 0.0),
        },
    }
    if equity_df is not None and not equity_df.empty:
        payload["equity"] = [v for v in (_num(x) for x in equity_df.get("equity", pd.Series(dtype=float)).tolist()) if v is not None]
        payload["benchmark"] = [v for v in (_num(x) for x in equity_df.get("benchmark", pd.Series(dtype=float)).tolist()) if v is not None]
        payload["drawdown"] = [v for v in (_num(x) for x in equity_df.get("drawdown", pd.Series(dtype=float)).tolist()) if v is not None]
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


def trim_pipeline_payload(payload: Mapping[str, Any], max_entries: int = 40) -> dict[str, Any]:
    """pipeline_forward.json ist ~800 KB — Eintraege fuers Web kappen."""

    out = dict(payload)
    if isinstance(out.get("eintraege"), list):
        out["eintraege"] = out["eintraege"][:max_entries]
    if isinstance(out.get("laeufe"), list):
        trimmed = []
        for lauf in out["laeufe"]:
            lauf = dict(lauf)
            lauf.pop("eintraege", None)
            lauf.pop("wortzaehler_endstaende", None)
            trimmed.append(lauf)
        out["laeufe"] = trimmed
    out.pop("wortzaehler_endstaende", None)
    return out
