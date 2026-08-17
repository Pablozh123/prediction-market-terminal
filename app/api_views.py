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
    "microstructure": "microstructure",
    "postmortems": "postmortems",
    "field-notes": "field_notes",
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


def cross_rows(candidates: pd.DataFrame, categories: Mapping[str, str] | None = None) -> list[dict[str, Any]]:
    """`md.cross_venue_candidates`-Frame in die Frontend-Paar-Zeilen.

    ``categories`` mappt Polymarket ``market_key`` auf eine Kategorie, damit
    die Zeile die echte Markt-Kategorie statt eines Platzhalters traegt.
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
        pm_key = _text(row.get("polymarket_market_key"))
        rows.append({
            "event": _text(row.get("polymarket_title")) or _text(row.get("kalshi_title")),
            "cat": (_text(categories.get(pm_key)) or "PAIR").upper(),
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
            "copied_trades": int(_num(row.get("copied_trades"), 0.0) or 0),
            "skipped_trades": int(_num(row.get("skipped_trades"), 0.0) or 0),
        }
        for _, row in comparison.iterrows()
    ]


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


def live_runs_extras(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Sizing-Simulation, Kalibrierung, Timing-Decay und Monatsbilanz aus
    runs.json — dieselben Module wie die Streamlit-Seite (app/run_sim.py)."""

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
            slot = monthly.setdefault(month, {"runs": set(), "bets": 0, "stake": 0.0, "net": 0.0})
            slot["runs"].add(_text(run.get("profil")))
            slot["bets"] += 1
            slot["stake"] += _num(bet.get("einsatz_usd"), 0.0) or 0.0
            if bet.get("aufgeloest"):
                slot["net"] += _num(bet.get("pnl_usd"), 0.0) or 0.0
    if monthly:
        out["monthly"] = [
            {"month": month, "runs": len(slot["runs"]), "bets": slot["bets"], "stake": round(slot["stake"], 2), "net": round(slot["net"], 2)}
            for month, slot in sorted(monthly.items(), reverse=True)
        ]
    return out


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
            fresh_rows.append({
                "tag": "FRESH WALLETS · SAME SIDE",
                "score": count,
                "market": _text(row.get("title")),
                "detail": f"{count} wallets with at most two prior trades took {_text(row.get('fresh_outcome')) or 'the same side'} for {money_label(notional)} combined.",
                "wallets": [],
            })
    out["fresh"] = fresh_rows
    timing_rows: list[dict[str, Any]] = []
    if coord is not None and not coord.empty:
        for _, row in coord.head(10).iterrows():
            span = _num(row.get("coordinated_span_minutes"), 0.0) or 0.0
            timing_rows.append({
                "market": _text(row.get("title")),
                "wallets": int(_num(row.get("coordinated_wallets"), 0.0) or 0),
                "window": f"{span:.0f} min" if span >= 1 else f"{span * 60:.0f} s",
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
            network_rows.append({
                "name": f"Cluster C-{int(cluster_id) + 1}" if str(cluster_id).isdigit() else f"Cluster {cluster_id}",
                "size": int(len(group)),
                "shared": str(int(_num(group.get("shared_markets", pd.Series(dtype=float)).max(), 0.0) or 0)),
                "notional": money_label(float(pd.to_numeric(group.get("volume"), errors="coerce").fillna(0.0).sum())),
                "story": _text(story.get("headline")) or _text(story.get("pattern")) or "Co-trading pattern on shared markets.",
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
