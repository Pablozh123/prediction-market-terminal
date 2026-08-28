"""Monitor/alert signal building and rule matching, extracted from prediction_terminal.

Streamlit-free so the background alert scanner can reuse the exact same logic.
The holder-concentration check needs network data; callers inject ``fetch_holders``
(market_key -> holders frame) so the app can pass its cached loader and the
scanner can pass the raw API client or disable the check.
"""

from __future__ import annotations

import re
from typing import Any, Callable, Mapping

import pandas as pd

from app.filters import numeric_col
from app.format import cents, money, pct, signed_cents


#: Signalarten aus dem Trade-Tape. Nur sie tragen ein Notional und eine
#: gehandelte Seite; Buchtiefe fuehrt das Tape nicht, ihre ``liquidity`` ist
#: per Konstruktion 0.0.
TRADE_SIGNAL_TYPES = ("Whale print",)

#: Signalarten aus der Markttabelle. Sie tragen Liquiditaet und Spread, aber
#: kein Notional: ``_append_market_signal`` setzt es auf 0.0.
MARKET_SIGNAL_TYPES = (
    "Volume anomaly",
    "Fast mover",
    "Tight spread",
    "Ending soon",
    "Watched market",
    "Holder concentration",
)

#: Welche Arten eine Notional- bzw. Liquiditaets-Schwelle ueberhaupt
#: beantworten koennen. Regeln binden ihre Schwellen daran (siehe
#: ``monitor_rule_matches``).
NOTIONAL_SIGNAL_TYPES = TRADE_SIGNAL_TYPES
LIQUIDITY_SIGNAL_TYPES = MARKET_SIGNAL_TYPES


def _text(value: Any) -> str:
    """Zelleninhalt als Text; NaN und None werden leer, nicht "nan"."""

    if value is None:
        return ""
    try:
        if bool(pd.isna(value)):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def monitor_volume_col(df: pd.DataFrame) -> str:
    """Die Volumenspalte, gegen die der Monitor filtert und die er mitfuehrt.

    ``activity_volume`` ist ein Mischwert: der Tageswert, wenn der Markt heute
    gehandelt wurde, sonst das Lebensvolumen. Als Schwelle und als Spalte
    heisst das, dass ein Markt ohne Umsatz heute mit seinem Gesamtumsatz
    antritt. Wer die Zahl anzeigt, muss sie so benennen; "24h" waere falsch.
    """

    if "activity_volume" in df:
        return "activity_volume"
    if "volume_24h" in df:
        return "volume_24h"
    return "volume"


#: Felder, die eine Signalart per Konstruktion nicht messen kann, mit dem
#: Platzhalter, den ``build_monitor_signals`` dort einsetzt. Ein Trade-Signal
#: kommt aus dem Tape und kennt weder Marktvolumen noch Buchtiefe; ein
#: Marktsignal kommt aus der Markttabelle und hat kein Notional.
UNAVAILABLE_FIELDS: dict[tuple[str, ...], tuple[str, ...]] = {
    TRADE_SIGNAL_TYPES: ("volume", "liquidity"),
    MARKET_SIGNAL_TYPES: ("notional",),
}


def blank_structural_placeholders(signals: pd.DataFrame) -> pd.DataFrame:
    """Die Platzhalter-Nullen fuer die Anzeige leeren.

    ``build_monitor_signals`` schreibt 0.0 in die Felder, die eine Signalart
    nicht messen kann, damit der Frame saubere numerische Spalten hat. In
    einer Tabelle ist diese Null nicht als Platzhalter zu erkennen: im Signal
    Feed stand neben Marktsignalen mit echter Buchtiefe jeder Whale-Print mit
    "Volume 0" und "Liquidity $0" da, als waere sein Markt leer, und wer nach
    Liquiditaet sortierte, bekam alle Prints ans Ende gestellt. Die Schwellen
    binden ihre Vergleiche laengst an die Signalart
    (``monitor_rule_matches``); die Anzeige tat es nicht.

    Rechnende Pfade rufen das nicht auf: die Nullen bleiben im Frame, den der
    Scanner und das Ledger sehen.
    """

    if signals is None or signals.empty or "signal_type" not in signals:
        return signals
    out = signals.copy()
    art = out["signal_type"].astype(str)
    for arten, felder in UNAVAILABLE_FIELDS.items():
        maske = art.isin(arten)
        if not bool(maske.any()):
            continue
        for feld in felder:
            if feld in out:
                out[feld] = pd.to_numeric(out[feld], errors="coerce")
                out.loc[maske, feld] = float("nan")
    return out


def _observed_at(row: pd.Series, now: Any) -> Any:
    """When the signal was observed.

    First stamp the row actually carries, else the scan time. ``or`` alone is
    not enough: in a frame that mixes venues the Kalshi rows get an
    ``updated_at`` column full of NaN from the Polymarket rows, and NaN is
    truthy, so the chain used to stop there and hand out NaT.
    """

    for column in ("updated_at", "created_at"):
        value = row.get(column)
        if value is None:
            continue
        try:
            if bool(pd.isna(value)):
                continue
        except (TypeError, ValueError):
            pass
        if value != "":
            return value
    return now


def _append_market_signal(
    rows: list[dict[str, Any]],
    row: pd.Series,
    signal_type: str,
    value: float,
    reason: str,
    severity: str = "info",
    now: Any = None,
) -> None:
    rows.append(
        {
            "signal_type": signal_type,
            "severity": severity,
            # Wann das Signal beobachtet wurde. Die Kalshi-Zeilen fuehren
            # weder updated_at noch created_at, und der frueher hier
            # stehende Rueckfall auf end_time schrieb den SCHLUSSTERMIN des
            # Marktes hinein: ein Signal von heute trug den Zeitstempel
            # 2027, sortierte damit vor jedes frische Signal und landete so
            # auch im Ledger. Ohne eigenen Stempel gilt die Scan-Zeit.
            "time": _observed_at(row, now if now is not None else pd.Timestamp.now(tz="UTC")),
            "platform": row.get("platform", ""),
            "title": row.get("title", ""),
            "category": row.get("category", ""),
            "outcome": "Yes",
            # Ein Marktsignal nimmt keine Seite; das Feld existiert, damit der
            # Frame eine saubere Spalte hat und nicht NaN neben "BUY"/"SELL".
            "side": "",
            "tx": "",
            "price": row.get("yes_price"),
            "value": value,
            "reason": reason,
            "volume": row.get("activity_volume", row.get("volume_24h", row.get("volume", 0.0))),
            "liquidity": row.get("liquidity", 0.0),
            "spread": row.get("spread"),
            "change_1h": row.get("change_1h", 0.0),
            "market_key": row.get("market_key", ""),
            "wallet": "",
            "trader": "",
            "notional": 0.0,
            "url": row.get("url", ""),
        }
    )


def build_monitor_signals(
    markets: pd.DataFrame,
    trades: pd.DataFrame,
    *,
    min_volume: float,
    min_liquidity: float,
    min_move: float,
    max_spread: float,
    min_whale_notional: float,
    ending_days: int,
    holder_threshold: float,
    holder_checks: int,
    tracked_keys: set[str],
    fetch_holders: Callable[[str], pd.DataFrame] | None = None,
    now: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """Signal rows for the monitor and the alert scanner.

    ``now`` is the scan time. It is the observation stamp for every market
    signal whose row carries no timestamp of its own (Kalshi rows carry
    none), and it is the reference for the ending-soon window. Injectable so
    tests do not depend on the wall clock.
    """

    now = pd.Timestamp.now(tz="UTC") if now is None else pd.Timestamp(now)
    if now.tzinfo is None:
        now = now.tz_localize("UTC")
    rows: list[dict[str, Any]] = []
    market_frame = markets.copy()
    if not market_frame.empty:
        volume_col = monitor_volume_col(market_frame)
        market_frame = market_frame[
            (numeric_col(market_frame, volume_col) >= float(min_volume))
            & (numeric_col(market_frame, "liquidity") >= float(min_liquidity))
        ].copy()
        if "volume_1h" in market_frame and "volume_24h" in market_frame:
            anomaly_vol_1h = numeric_col(market_frame, "volume_1h")
            anomaly_vol_24h = numeric_col(market_frame, "volume_24h")
            anomaly_baseline = (anomaly_vol_24h / 24.0).clip(lower=1.0)
            anomaly_ratio = anomaly_vol_1h / anomaly_baseline
            anomalies = market_frame[(anomaly_vol_24h >= 10_000) & (anomaly_ratio >= 3.0)].copy()
            if not anomalies.empty:
                anomalies["_ratio"] = anomaly_ratio.loc[anomalies.index]
                anomalies = anomalies.sort_values("_ratio", ascending=False)
                for _, row in anomalies.head(60).iterrows():
                    _append_market_signal(
                        rows,
                        row,
                        "Volume anomaly",
                        float(row["_ratio"]),
                        f"1h volume {float(row['_ratio']):.1f}x the 24h baseline",
                        "warning",
                        now=now,
                    )
        if "change_1h" in market_frame:
            movers = market_frame[numeric_col(market_frame, "change_1h").abs() >= float(min_move)]
            movers = movers.sort_values("change_1h", key=lambda series: series.abs(), ascending=False)
            for _, row in movers.head(120).iterrows():
                value = float(row.get("change_1h") or 0.0)
                _append_market_signal(rows, row, "Fast mover", value, f"1h move {signed_cents(value)}", "warning", now=now)
        if "spread" in market_frame:
            tight = market_frame[numeric_col(market_frame, "spread", 999.0) <= float(max_spread)]
            tight = tight.sort_values(["spread", volume_col], ascending=[True, False])
            for _, row in tight.head(120).iterrows():
                value = float(row.get("spread") or 0.0)
                _append_market_signal(rows, row, "Tight spread", value, f"spread {cents(value)}", now=now)
        if "end_time" in market_frame:
            end_time = pd.to_datetime(market_frame["end_time"], utc=True, errors="coerce")
            soon = market_frame[end_time.notna() & (end_time >= now) & (end_time <= now + pd.Timedelta(days=int(ending_days)))]
            soon = soon.assign(_end_time=end_time.loc[soon.index]).sort_values("_end_time")
            for _, row in soon.head(120).iterrows():
                _append_market_signal(rows, row, "Ending soon", float(row.get("yes_price") or 0.0), f"ends {row.get('end_time')}", "warning", now=now)
        if tracked_keys:
            watched = market_frame[market_frame["market_key"].astype(str).isin(tracked_keys)]
            for _, row in watched.head(120).iterrows():
                _append_market_signal(rows, row, "Watched market", float(row.get("yes_price") or 0.0), "on local watchlist", now=now)
        if holder_checks > 0 and fetch_holders is not None:
            holder_candidates = market_frame[market_frame["platform"].eq("Polymarket")].sort_values(volume_col, ascending=False).head(int(holder_checks))
            for _, row in holder_candidates.iterrows():
                try:
                    holders = fetch_holders(str(row.get("market_key", "")))
                except Exception:
                    continue
                if holders is None or holders.empty or "amount" not in holders:
                    continue
                total = float(pd.to_numeric(holders["amount"], errors="coerce").fillna(0.0).sum())
                if total <= 0:
                    continue
                top_share = float(pd.to_numeric(holders["amount"], errors="coerce").fillna(0.0).max() / total)
                top10_share = float(pd.to_numeric(holders.head(10)["amount"], errors="coerce").fillna(0.0).sum() / total)
                if top_share >= float(holder_threshold):
                    _append_market_signal(
                        rows,
                        row,
                        "Holder concentration",
                        top_share,
                        f"top holder {pct(top_share)}; top 10 {pct(top10_share)}",
                        "warning",
                        now=now,
                    )
    if not trades.empty:
        whale_trades = trades[numeric_col(trades, "notional") >= float(min_whale_notional)].sort_values("time", ascending=False)
        for _, row in whale_trades.head(180).iterrows():
            rows.append(
                {
                    "signal_type": "Whale print",
                    "severity": "warning",
                    "time": row.get("time"),
                    "platform": row.get("platform", ""),
                    "title": row.get("title", ""),
                    "category": "",
                    "outcome": row.get("outcome", ""),
                    # Die genommene Seite als eigenes Feld, nicht nur als Wort
                    # im Begruendungstext: das Ledger modelliert einen KAUF zum
                    # Emit-Preis, und ein Verkaufsdruck ist damit nicht
                    # bewertbar (siehe app/ledger.py::emit_signals).
                    "side": str(row.get("side", "") or ""),
                    # Der Trade selbst, nicht nur sein Markt: der Scanner
                    # erkennt daran zwei Clips derselben Wallet in derselben
                    # Minute als zwei Ereignisse.
                    "tx": _text(row.get("transaction_hash")),
                    "price": row.get("price"),
                    "value": row.get("notional", 0.0),
                    "reason": f"{row.get('side', '')} {money(row.get('notional', 0.0))}",
                    "volume": 0.0,
                    "liquidity": 0.0,
                    "spread": None,
                    "change_1h": None,
                    "market_key": row.get("market_key", row.get("ticker", "")),
                    "wallet": row.get("wallet", ""),
                    "trader": row.get("trader", ""),
                    "notional": row.get("notional", 0.0),
                    "url": row.get("url", ""),
                }
            )
    if not rows:
        return pd.DataFrame()
    signals = pd.DataFrame(rows)
    signals["time"] = pd.to_datetime(signals["time"], utc=True, errors="coerce")
    return signals.sort_values(["severity", "time", "value"], ascending=[False, False, False]).reset_index(drop=True)


#: Wie lange dieselbe Marktbeobachtung nach einer Zustellung ruht. Ein
#: Marktsignal hat kein Ereignis, an dem seine Identitaet haengt: es beschreibt
#: einen Zustand, den jeder Scan neu misst. Wie oft dieser Zustand gemeldet
#: wird, ist deshalb eine Entscheidung des Scanners und steht hier als Zahl,
#: nicht verborgen in einem Zeitstempel, den eine fremde API setzt.
MARKET_SIGNAL_COOLDOWN_MINUTES = 60


def signal_dedupe_key(row: Mapping[str, Any]) -> str:
    """Identitaet eines Signals fuer das Zustellprotokoll des Scanners.

    Der Schluessel bestand aus Art, Markt, Wallet und der Minute. Damit fielen
    zwei verschiedene Prints derselben Wallet im selben Markt und derselben
    Minute zusammen: der Kauf von Yes ueber 9.000 Dollar und der Verkauf von
    No ueber 4.000 trugen denselben Schluessel, also ging nur der erste raus
    und nur der erste kam ins Ledger. Der gehandelte Ausgang gehoert hinein,
    und bei einem Print zusaetzlich der Trade selbst.

    Bei einem Print ist die Zeit Teil des Ereignisses und bleibt im
    Schluessel. Bei einem Marktsignal war sie es nie: ``_observed_at``
    schreibt dort den ``updated_at`` des Marktes hinein, also den Zeitpunkt,
    an dem die Venue ihren Datensatz zuletzt angefasst hat. Dieser Stempel
    wandert unter einem aktiv umbepreisten Markt, und der Schluessel wanderte
    mit. Gerechnet, bei Scan-Intervall 10 Minuten und unveraendertem 1h-Move
    von 8 Cent:

        Scan 14:25 -> updated_at 14:23:07 -> Schluessel ...|14:23 -> Alert 1
        Scan 14:35 -> updated_at 14:34:51 -> Schluessel ...|14:34 -> Alert 2
        Scan 14:45 -> updated_at 14:44:02 -> Schluessel ...|14:44 -> Alert 3

    Drei Alerts und drei Ledger-Zeilen fuer eine unveraenderte Beobachtung,
    waehrend der Nachbarmarkt mit demselben Move, den die Venue seit 09:12
    nicht neu gestempelt hat, genau einen erzeugt: ueber die Zustellhaeufigkeit
    entschied die Buchhaltung der Venue.

    Deshalb traegt ein Marktsignal jetzt nur noch seine Identitaet (Art,
    Markt, Ausgang). Wie oft diese Identitaet gemeldet werden darf, entscheidet
    ``due_for_delivery`` ueber das Zustellprotokoll, also ueber die Zeitpunkte,
    die der Scanner selbst geschrieben hat.
    """

    art = _text(row.get("signal_type"))
    teile = [
        art,
        _text(row.get("market_key")),
        _text(row.get("outcome")),
        _text(row.get("wallet")),
    ]
    if art in TRADE_SIGNAL_TYPES:
        teile.append(_text(row.get("time"))[:16])
        tx = _text(row.get("tx"))
        if tx:
            teile.append(tx)
        else:
            # Ohne Transaktions-Hash (Kalshi liefert keinen) trennen Seite,
            # Groesse und Preis die Clips.
            notional = _text(row.get("notional"))
            teile.append(f"{_text(row.get('side'))}:{notional}@{_text(row.get('price'))}")
    return "|".join(teile)


def delivery_cooldown_minutes(signal_type: Any) -> int:
    """Ruhezeit einer Signalart nach einer Zustellung, in Minuten.

    Ein Print ist ein einzelnes Ereignis: sein Schluessel wiederholt sich nur,
    wenn es derselbe Trade ist, also gibt es fuer ihn genau eine Zustellung
    und keine Ruhezeit (0). Ein Marktsignal beschreibt einen fortdauernden
    Zustand und ruht ``MARKET_SIGNAL_COOLDOWN_MINUTES`` lang.
    """

    return 0 if _text(signal_type) in TRADE_SIGNAL_TYPES else int(MARKET_SIGNAL_COOLDOWN_MINUTES)


def due_for_delivery(row: Mapping[str, Any], last_delivered_at: Any, now: Any = None) -> bool:
    """Ob diese Zeile jetzt (wieder) zugestellt werden darf.

    ``last_delivered_at`` ist der Zeitpunkt, zu dem derselbe Schluessel
    zuletzt zugestellt wurde (aus dem Protokoll in ``app/ledger.py``), oder
    None, wenn er noch nie zugestellt wurde. Reine Funktion, damit die Regel
    ohne Datenbank pruefbar ist.
    """

    if last_delivered_at is None or (isinstance(last_delivered_at, str) and not last_delivered_at.strip()):
        return True
    ruhe = delivery_cooldown_minutes(row.get("signal_type"))
    if ruhe <= 0:
        return False
    letzte = pd.to_datetime(last_delivered_at, utc=True, errors="coerce")
    if pd.isna(letzte):
        # Ein unlesbarer Stempel darf nicht dauerhaft blockieren; er ist
        # kein Nachweis, dass etwas rausging.
        return True
    jetzt = pd.Timestamp.now(tz="UTC") if now is None else pd.Timestamp(now)
    if jetzt.tzinfo is None:
        jetzt = jetzt.tz_localize("UTC")
    return (jetzt - letzte) >= pd.Timedelta(minutes=ruhe)


def monitor_rule_matches(signals: pd.DataFrame, rule: dict[str, Any]) -> pd.DataFrame:
    if signals.empty:
        return pd.DataFrame()
    filtered = signals.copy()
    signal_type = str(rule.get("signal_type", "Any"))
    if signal_type != "Any":
        filtered = filtered[filtered["signal_type"].eq(signal_type)]
    platforms = rule.get("platforms") or []
    if platforms:
        filtered = filtered[filtered["platform"].isin(platforms)]
    query = str(rule.get("query", "") or "").strip().lower()
    if query:
        searchable = filtered.get("title", pd.Series("", index=filtered.index)).astype(str).str.lower()
        searchable = searchable + " " + filtered.get("wallet", pd.Series("", index=filtered.index)).astype(str).str.lower()
        searchable = searchable + " " + filtered.get("trader", pd.Series("", index=filtered.index)).astype(str).str.lower()
        searchable = searchable + " " + filtered.get("reason", pd.Series("", index=filtered.index)).astype(str).str.lower()
        filtered = filtered[searchable.str.contains(re.escape(query), na=False)]
    # Jede Schwelle gilt nur fuer die Signalarten, die das gemessene Feld
    # ueberhaupt fuehren. Ohne diese Bindung loescht eine Schwelle die
    # anderen Arten restlos aus, weil deren Feld per Konstruktion 0.0 ist
    # (Marktsignale tragen notional 0.0, Trade-Signale liquidity 0.0) -- und
    # das Regelformular fuellt "Min notional" mit der Whale-Schwelle vor.
    min_notional = float(rule.get("min_notional", 0.0) or 0.0)
    if min_notional:
        filtered = filtered[
            ~filtered["signal_type"].isin(NOTIONAL_SIGNAL_TYPES)
            | (numeric_col(filtered, "notional") >= min_notional)
        ]
    min_move = float(rule.get("min_move", 0.0) or 0.0)
    if min_move:
        filtered = filtered[(filtered["signal_type"].ne("Fast mover")) | (numeric_col(filtered, "value").abs() >= min_move)]
    max_spread = float(rule.get("max_spread", 0.0) or 0.0)
    if max_spread:
        filtered = filtered[(filtered["signal_type"].ne("Tight spread")) | (numeric_col(filtered, "spread", 999.0) <= max_spread)]
    min_liquidity = float(rule.get("min_liquidity", 0.0) or 0.0)
    if min_liquidity:
        filtered = filtered[
            ~filtered["signal_type"].isin(LIQUIDITY_SIGNAL_TYPES)
            | (numeric_col(filtered, "liquidity") >= min_liquidity)
        ]
    return filtered.reset_index(drop=True)


def monitor_rule_match_count(signals: pd.DataFrame, rule: dict[str, Any]) -> int:
    return int(len(monitor_rule_matches(signals, rule)))


def build_monitor_alert_hits(signals: pd.DataFrame, rules: list[dict[str, Any]]) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    for idx, rule in enumerate(rules):
        if not bool(rule.get("active", True)):
            continue
        matches = monitor_rule_matches(signals, rule)
        if matches.empty:
            continue
        matches = matches.copy()
        matches["rule_name"] = str(rule.get("name") or f"Rule {idx + 1}")
        matches["rule_type"] = str(rule.get("signal_type", "Any"))
        rows.append(matches)
    if not rows:
        return pd.DataFrame()
    hits = pd.concat(rows, ignore_index=True, sort=False)
    return hits.sort_values(["time", "value"], ascending=[False, False], na_position="last").reset_index(drop=True)
