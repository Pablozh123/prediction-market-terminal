"""Aufloesung der Papier-Trades des Arbitrage-Scanners gegen Polymarket.

Der Scanner (Repo prediction-alpha-bot) schreibt seine Papier-Trades in eine
SQLite-Datei und publiziert die juengsten fuenfzig als ``paper_positions`` in
``public/data/arb_scan.json``. Seine eigene Aufloesungs-Routine fragt Gamma
mit ``/markets?slug=`` ab, und dieser Endpunkt liefert geschlossene Maerkte
nur mit ``closed=true``. Ohne den Parameter bekam der Scanner fuer jeden
abgerechneten Markt "nicht gefunden", und so standen 167 Trades drei Monate
lang auf "open", obwohl die Maerkte laengst abgerechnet waren.

Seit 2026-09-05 fragt der Bot selbst mit ``closed=true`` und schliesst
Fills nach dem Close mit Grund statt Zahl (prediction-alpha-bot#4). Dieser
Lauf bleibt als unabhaengige Gegenprobe ueber dasselbe Journal.

Dieses Modul macht die Aufloesung nachtraeglich und ohne den Bot anzufassen:
je Trade den Markt nachschlagen (mit ``closed=true``), den Abrechnungspreis
der gehandelten Seite lesen, daraus Auszahlung, Gewinn und Haltedauer
rechnen, und die Trades zu ihren Koerben gruppieren. Die Rechenregel ist die
des Bots (``calculatePaperPnlOnlyIfResolutionKnown``): Stueckzahl ist
``size_shares`` oder ``size_usd / entry_price``, Auszahlung ist Stueckzahl
mal Abrechnungspreis, Gewinn ist Auszahlung minus Einsatz. Ein Trade ohne
gueltigen Einstiegspreis bekommt keinen Gewinn, sondern einen Grund.

Zwei Dinge sagt das Ergebnis ausdruecklich, weil die Zahlen sonst luegen:

* Ein Korb ist nur dann ein NegRisk-Korb, wenn seine Maerkte einander
  ausschliessen (Gamma: ``negRisk`` am Ereignis). Mehrere der gefeuerten
  Koerbe lagen auf gestaffelten Fristen ("bis 31. Mai", "bis 30. Juni", "bis
  31. Dezember"), die sich nicht ausschliessen, sondern ineinander liegen.
  Dort ist "NO auf alles" kein Arbitrage, und das Ergebnis zeigt es.
* Ein Markt kann mit 0.5/0.5 abrechnen. Dann zahlt jede Seite fuenfzig Cent,
  und das steht als eigene Abrechnungsart dabei, statt als Sieg oder
  Niederlage.

Streamlit-frei; nur Standardbibliothek. Netzaufrufe laufen ueber eine
injizierbare ``fetch_json``-Funktion, damit alles ohne Netz testbar ist.
"""

from __future__ import annotations

import json
import sqlite3
import urllib.parse
import urllib.request
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

GAMMA = "https://gamma-api.polymarket.com"
USER_AGENT = "marketintel-arb-resolution/1.0"
CLOB = "https://clob.polymarket.com"
#: Seit E5 (2026-09-05) feuert der Scanner Cross-Venue-Paare paper und
#: journaliert das Kalshi-Bein unter diesem Slug-Praefix. Gamma kennt es
#: nicht; der Scanner rechnet es selbst gegen das Kalshi-Marktergebnis ab.
KALSHI_PAPER_SLUG_PREFIX = "kalshi:"
KALSHI_LEG_REASON = "kalshi_leg_not_resolved_here"
#: Toleranz fuer den Abgleich Einstiegspreis gegen den CLOB-Tagespreis, in
#: Preis-Einheiten (0..1). Ein Tagespunkt liegt bis zu zwoelf Stunden neben
#: dem Fill, und in der Zeit bewegt sich ein Preis um ein paar Cent.
ENTRY_TOLERANCE = 0.05
#: Ein Tagespunkt, der weiter als anderthalb Tage vom Fill entfernt liegt,
#: sagt nichts mehr ueber den Fill.
CLOB_MAX_HOURS = 36.0

#: Abrechnungsarten. "split" ist die 0.5/0.5-Abrechnung, bei der keine Seite
#: gewonnen hat und jede Seite fuenfzig Cent zurueckbekommt.
RESOLVED_YES_NO = "yes_no"
RESOLVED_SPLIT = "split"

FetchJson = Callable[[str], Any]


def fetch_json(url: str, timeout: float = 40.0) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - feste https-Hosts
        return json.loads(resp.read().decode("utf-8"))


# ---------------------------------------------------------------- Gamma lesen

def _liste(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            geladen = json.loads(value)
        except (ValueError, TypeError):
            return []
        return geladen if isinstance(geladen, list) else []
    return []


def _zeit(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    text = text.replace("Z", "+00:00")
    # Gamma schreibt "2026-08-01 07:10:29+00": ohne Minuten im Offset.
    if text.endswith("+00"):
        text = text + ":00"
    try:
        stamp = datetime.fromisoformat(text)
    except ValueError:
        return None
    return stamp if stamp.tzinfo else stamp.replace(tzinfo=timezone.utc)


def parse_market(raw: Any) -> dict[str, Any] | None:
    """Ein Gamma-Marktobjekt auf das, was die Aufloesung braucht."""

    if not isinstance(raw, dict):
        return None
    outcomes = [str(o) for o in _liste(raw.get("outcomes"))]
    prices_roh = _liste(raw.get("outcomePrices"))
    prices: list[float | None] = []
    for p in prices_roh:
        try:
            prices.append(float(p))
        except (TypeError, ValueError):
            prices.append(None)
    events = raw.get("events") if isinstance(raw.get("events"), list) else []
    event = events[0] if events and isinstance(events[0], dict) else {}
    neg_risk = raw.get("negRisk")
    if neg_risk is None:
        neg_risk = event.get("negRisk")
    return {
        "slug": str(raw.get("slug") or ""),
        "question": str(raw.get("question") or ""),
        "condition_id": str(raw.get("conditionId") or ""),
        "closed": bool(raw.get("closed")),
        "uma_status": str(raw.get("umaResolutionStatus") or ""),
        "closed_time": raw.get("closedTime"),
        "end_date": raw.get("endDate"),
        "outcomes": outcomes,
        "prices": prices,
        "event_slug": str(event.get("slug") or ""),
        "event_title": str(event.get("title") or ""),
        "neg_risk": bool(neg_risk) if neg_risk is not None else None,
    }


def lookup_market(slug: str, token_id: str = "", fetch: FetchJson = fetch_json) -> dict[str, Any] | None:
    """Den Markt zu einem Trade finden, geschlossene zuerst.

    Reihenfolge: ``/markets?slug=&closed=true`` (das ist der Aufruf, den der
    Bot nie gemacht hat), dann derselbe ohne ``closed`` fuer noch offene
    Maerkte, dann dasselbe Paar ueber die CLOB-Token-ID.
    """

    versuche: list[str] = []
    if slug:
        q = urllib.parse.quote(slug)
        versuche += [f"{GAMMA}/markets?slug={q}&closed=true", f"{GAMMA}/markets?slug={q}"]
    if token_id:
        q = urllib.parse.quote(str(token_id))
        versuche += [f"{GAMMA}/markets?clob_token_ids={q}&closed=true", f"{GAMMA}/markets?clob_token_ids={q}"]
    for url in versuche:
        try:
            daten = fetch(url)
        except Exception:  # noqa: BLE001 - ein toter Weg, der naechste folgt
            continue
        if isinstance(daten, list) and daten:
            kandidat = None
            if slug:
                kandidat = next((m for m in daten if isinstance(m, dict) and m.get("slug") == slug), None)
            if kandidat is None:
                kandidat = daten[0]
            markt = parse_market(kandidat)
            if markt:
                return markt
    return None


def clob_price_near(token_id: str, when: datetime | None, fetch: FetchJson = fetch_json,
                    history: list[dict[str, Any]] | None = None) -> dict[str, Any] | None:
    """Der CLOB-Tagespreis des gehandelten Tokens am naechsten zum Fill.

    Quelle: ``/prices-history?market=<token>&interval=max&fidelity=1440``,
    ein Punkt je Tag. Rueckgabe ``{"price", "at", "hours_off"}`` oder None,
    wenn es keinen Punkt innerhalb von CLOB_MAX_HOURS gibt.
    """

    if not token_id or when is None:
        return None
    if history is None:
        history = _clob_history(str(token_id), fetch)
    punkte = []
    for h in history or []:
        try:
            punkte.append((float(h["t"]), float(h["p"])))
        except (KeyError, TypeError, ValueError):
            continue
    if not punkte:
        return None
    ziel = when.timestamp()
    t_nah, p_nah = min(punkte, key=lambda tp: abs(tp[0] - ziel))
    stunden = (t_nah - ziel) / 3600.0
    if abs(stunden) > CLOB_MAX_HOURS:
        return None
    return {"price": p_nah, "at": datetime.fromtimestamp(t_nah, tz=timezone.utc).isoformat(), "hours_off": round(stunden, 1)}


def _clob_history(token: str, fetch: FetchJson) -> list[dict[str, Any]]:
    url = f"{CLOB}/prices-history?market={urllib.parse.quote(token)}&interval=max&fidelity=1440"
    try:
        daten = fetch(url)
    except Exception:  # noqa: BLE001 - ohne Verlauf gibt es keinen Abgleich, sonst nichts
        return []
    verlauf = daten.get("history") if isinstance(daten, dict) else None
    return verlauf if isinstance(verlauf, list) else []


def entry_check(entry: Any, day_price: float | None) -> str:
    """Passt der Einstiegspreis zum Tagespreis der gehandelten Seite?

    ``entry``: passt so wie aufgezeichnet. ``complement``: passt erst als
    1 minus Einstieg, das Journal hat also den Preis der Gegenseite
    gespeichert. ``neither``: keins von beidem. ``no_data``: kein Tagespreis.
    Bei Preisen um 0.5 passen beide; dann gilt die Aufzeichnung.
    """

    if day_price is None:
        return "no_data"
    try:
        e = float(entry)
    except (TypeError, ValueError):
        return "no_data"
    if abs(e - day_price) <= ENTRY_TOLERANCE:
        return "entry"
    if abs((1.0 - e) - day_price) <= ENTRY_TOLERANCE:
        return "complement"
    return "neither"


def _fill_zeit(trade: dict[str, Any]) -> datetime | None:
    opened = _zeit(trade.get("opened_at"))
    if opened is None and trade.get("timestamp") is not None:
        try:
            opened = datetime.fromtimestamp(float(trade["timestamp"]) / 1000.0, tz=timezone.utc)
        except (TypeError, ValueError, OverflowError):
            opened = None
    return opened


def _korrigierter_einstieg(trade: dict[str, Any], pruefung: str) -> float | None:
    """Der Einstieg, den der Tagespreis stuetzt: 1 minus Einstieg, wenn das
    Journal die Gegenseite gespeichert hat, sonst der Einstieg selbst. None
    fuer Zeilen mit Stueckzahl (deren Einstieg passt ohnehin) und ohne
    brauchbaren Einstieg."""

    if trade.get("size_shares") is not None:
        return None
    try:
        e = float(trade.get("entry_price"))
    except (TypeError, ValueError):
        return None
    if pruefung == "complement":
        return round(1.0 - e, 6)
    return e


# ---------------------------------------------------------------- rechnen

def settlement(markt: dict[str, Any] | None, side: str) -> dict[str, Any]:
    """Abrechnungspreis der gehandelten Seite, wenn der Markt abgerechnet ist.

    Rueckgabe: ``{"status": "resolved"|"open"|"unknown", "price": float|None,
    "kind": "yes_no"|"split"|None, "reason": str}``.
    """

    if markt is None:
        return {"status": "unknown", "price": None, "kind": None, "reason": "market_not_found"}
    if not markt.get("closed"):
        return {"status": "open", "price": None, "kind": None, "reason": "market_open"}
    outcomes = [o.strip().lower() for o in markt.get("outcomes") or []]
    prices = markt.get("prices") or []
    gesucht = str(side or "").strip().lower()
    if gesucht not in outcomes or len(prices) != len(outcomes):
        return {"status": "unknown", "price": None, "kind": None, "reason": "outcome_not_in_market"}
    preis = prices[outcomes.index(gesucht)]
    if preis is None:
        return {"status": "unknown", "price": None, "kind": None, "reason": "price_missing"}
    # Abgerechnet heisst: Preise stehen auf 0/1 oder 0.5/0.5. Alles andere ist
    # ein geschlossener, aber noch nicht aufgeloester Markt.
    gueltig = all(p is not None and abs(p - round(p * 2) / 2) < 1e-9 for p in prices)
    uma = str(markt.get("uma_status") or "").lower()
    if not gueltig or (uma and uma != "resolved"):
        return {"status": "open", "price": None, "kind": None, "reason": f"closed_but_{uma or 'unsettled'}"}
    art = RESOLVED_SPLIT if abs(preis - 0.5) < 1e-9 else RESOLVED_YES_NO
    return {"status": "resolved", "price": float(preis), "kind": art, "reason": "gamma_outcome_prices"}


def _stueck(trade: dict[str, Any]) -> tuple[float | None, str]:
    size_usd = trade.get("size_usd")
    entry = trade.get("entry_price")
    shares = trade.get("size_shares")
    try:
        size_usd = float(size_usd)
    except (TypeError, ValueError):
        return None, "invalid_trade_size"
    if not size_usd > 0:
        return None, "invalid_trade_size"
    if shares is not None:
        try:
            shares = float(shares)
        except (TypeError, ValueError):
            return None, "invalid_trade_size"
        if shares > 0:
            return shares, ""
        return None, "invalid_trade_size"
    try:
        entry = float(entry)
    except (TypeError, ValueError):
        return None, "invalid_entry_price"
    if not (0.0 < entry <= 1.0):
        return None, "invalid_entry_price"
    return size_usd / entry, ""


def resolve_trade(trade: dict[str, Any], markt: dict[str, Any] | None, now: datetime | None = None,
                  day: dict[str, Any] | None = None) -> dict[str, Any]:
    """Ein Papier-Trade mit seinem Markt: Status, Auszahlung, Gewinn, Dauer.

    ``day`` ist der CLOB-Tagespreis aus ``clob_price_near``. Mit ihm bekommt
    der Trade eine zweite Rechnung: dieselbe Regel, aber mit dem Einstieg,
    den der Tagespreis stuetzt. Fuer Zeilen, deren Einstieg nur als
    Gegenseite passt, ist das 1 minus Einstieg. Zeilen mit Stueckzahl
    (die verknuepften) behalten ihren Einstieg; er passt ohnehin.
    """

    now = now or datetime.now(timezone.utc)
    abr = settlement(markt, str(trade.get("side") or ""))
    opened = _fill_zeit(trade)
    resolved_at = _zeit(markt.get("closed_time")) if markt and abr["status"] == "resolved" else None
    shares, grund = _stueck(trade)
    tagespreis = float(day["price"]) if day and day.get("price") is not None else None
    pruefung = entry_check(trade.get("entry_price"), tagespreis)
    korrigiert = _korrigierter_einstieg(trade, pruefung)
    if korrigiert is None:
        shares_korr, grund_korr = shares, grund
    else:
        shares_korr, grund_korr = _stueck({**trade, "entry_price": korrigiert})
    zeile: dict[str, Any] = {
        "trade_id": str(trade.get("trade_id") or trade.get("id") or ""),
        "opportunity_id": str(trade.get("opportunity_id") or "") or None,
        "strategy": str(trade.get("strategy") or ""),
        "slug": str(trade.get("slug") or trade.get("title") or ""),
        "question": (markt or {}).get("question") or str(trade.get("question") or ""),
        "event_slug": (markt or {}).get("event_slug") or None,
        "event_neg_risk": (markt or {}).get("neg_risk"),
        "side": str(trade.get("side") or ""),
        "entry_price": trade.get("entry_price"),
        "size_usd": trade.get("size_usd"),
        "shares": round(shares, 6) if shares is not None else None,
        "size_shares_recorded": trade.get("size_shares") is not None,
        "clob_day_price": tagespreis,
        "clob_day_at": day.get("at") if day else None,
        "clob_hours_off": day.get("hours_off") if day else None,
        "entry_check": pruefung,
        "entry_price_corrected": korrigiert,
        "opened_at": opened.isoformat() if opened else None,
        "status": abr["status"],
        "resolution_kind": abr["kind"],
        "settlement_price": abr["price"],
        "resolved_at": resolved_at.isoformat() if resolved_at else None,
        "days_held": None,
        "filled_after_close": False,
        "payout_usd": None,
        "pnl_usd": None,
        "pnl_reason": abr["reason"],
        "payout_corrected_usd": None,
        "pnl_corrected_usd": None,
        "pnl_corrected_reason": abr["reason"],
    }
    if abr["status"] == "resolved":
        if opened and resolved_at:
            zeile["days_held"] = round((resolved_at - opened).total_seconds() / 86400.0, 2)
            zeile["filled_after_close"] = resolved_at < opened
        if shares is None:
            zeile["pnl_reason"] = grund
        else:
            payout = shares * float(abr["price"])
            zeile["payout_usd"] = round(payout, 4)
            zeile["pnl_usd"] = round(payout - float(trade["size_usd"]), 4)
        # Die zweite Rechnung gibt es nur, wo sie etwas wert ist: der Markt
        # war beim Fill noch offen, und der Tagespreis stuetzt den Einstieg
        # (so wie aufgezeichnet oder als Gegenseite). Sonst steht ein Grund.
        if zeile["filled_after_close"]:
            zeile["pnl_corrected_reason"] = "filled_after_close"
        elif pruefung == "neither":
            zeile["pnl_corrected_reason"] = "entry_unsupported_by_day_price"
        elif pruefung == "no_data" and not trade.get("size_shares"):
            zeile["pnl_corrected_reason"] = "no_day_price"
        elif shares_korr is None:
            zeile["pnl_corrected_reason"] = grund_korr
        else:
            payout_korr = shares_korr * float(abr["price"])
            zeile["payout_corrected_usd"] = round(payout_korr, 4)
            zeile["pnl_corrected_usd"] = round(payout_korr - float(trade["size_usd"]), 4)
    elif abr["status"] == "open" and opened:
        zeile["days_held"] = round((now - opened).total_seconds() / 86400.0, 2)
    return zeile


def _korb_schluessel(zeile: dict[str, Any]) -> str:
    return zeile.get("opportunity_id") or ("event:" + (zeile.get("event_slug") or zeile.get("slug") or ""))


def baskets(zeilen: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Trades zu Koerben: verknuepft ueber opportunity_id, sonst ueber das
    Ereignis, zu dem der Markt gehoert."""

    gruppen: "OrderedDict[str, list[dict[str, Any]]]" = OrderedDict()
    for z in zeilen:
        gruppen.setdefault(_korb_schluessel(z), []).append(z)
    raus = []
    for key, trades in gruppen.items():
        kosten = sum(float(t["size_usd"]) for t in trades if t.get("size_usd") is not None)
        mit_pnl = [t for t in trades if t.get("pnl_usd") is not None]
        auszahlung = sum(float(t["payout_usd"]) for t in mit_pnl)
        pnl = sum(float(t["pnl_usd"]) for t in mit_pnl)
        mit_korr = [t for t in trades if t.get("pnl_corrected_usd") is not None]
        auszahlung_korr = sum(float(t["payout_corrected_usd"]) for t in mit_korr)
        pnl_korr = sum(float(t["pnl_corrected_usd"]) for t in mit_korr)
        neg = [t.get("event_neg_risk") for t in trades if t.get("event_neg_risk") is not None]
        exklusiv = all(neg) if neg else None
        raus.append({
            "key": key,
            "linked": not key.startswith("event:"),
            "event_slug": next((t.get("event_slug") for t in trades if t.get("event_slug")), None),
            "legs": len(trades),
            "resolved_legs": sum(1 for t in trades if t.get("status") == "resolved"),
            "open_legs": sum(1 for t in trades if t.get("status") == "open"),
            "unknown_legs": sum(1 for t in trades if t.get("status") == "unknown"),
            "legs_with_pnl": len(mit_pnl),
            "cost_usd": round(kosten, 4),
            "payout_usd": round(auszahlung, 4) if mit_pnl else None,
            "pnl_usd": round(pnl, 4) if mit_pnl else None,
            "legs_with_corrected_pnl": len(mit_korr),
            "payout_corrected_usd": round(auszahlung_korr, 4) if mit_korr else None,
            "pnl_corrected_usd": round(pnl_korr, 4) if mit_korr else None,
            "entry_checks": _zaehle(t.get("entry_check") for t in trades),
            "filled_after_close": sum(1 for t in trades if t.get("filled_after_close")),
            # Ein NO-auf-alles-Korb ist nur dann ein Korb, wenn seine Maerkte
            # einander ausschliessen. Gestaffelte Fristen tun das nicht.
            "mutually_exclusive": exklusiv,
            "opened_at": min((t["opened_at"] for t in trades if t.get("opened_at")), default=None),
            "resolved_at": max((t["resolved_at"] for t in trades if t.get("resolved_at")), default=None)
            if all(t.get("status") == "resolved" for t in trades) else None,
        })
    return raus


def summary(zeilen: list[dict[str, Any]], koerbe: list[dict[str, Any]]) -> dict[str, Any]:
    resolved = [z for z in zeilen if z.get("status") == "resolved"]
    mit_pnl = [z for z in resolved if z.get("pnl_usd") is not None]
    mit_korr = [z for z in resolved if z.get("pnl_corrected_usd") is not None]
    nach_schluss = [z for z in resolved if z.get("filled_after_close")]
    dauern = [z["days_held"] for z in resolved if z.get("days_held") is not None and not z.get("filled_after_close")]
    return {
        "trades": len(zeilen),
        "resolved": len(resolved),
        "open": sum(1 for z in zeilen if z.get("status") == "open"),
        "unknown": sum(1 for z in zeilen if z.get("status") == "unknown"),
        "with_pnl": len(mit_pnl),
        "without_pnl_reasons": _zaehle(z["pnl_reason"] for z in resolved if z.get("pnl_usd") is None),
        "won": sum(1 for z in mit_pnl if z["pnl_usd"] > 0),
        "lost": sum(1 for z in mit_pnl if z["pnl_usd"] < 0),
        "flat": sum(1 for z in mit_pnl if z["pnl_usd"] == 0),
        "split_settlements": sum(1 for z in resolved if z.get("resolution_kind") == RESOLVED_SPLIT),
        "cost_usd": round(sum(float(z["size_usd"]) for z in mit_pnl), 4),
        "payout_usd": round(sum(float(z["payout_usd"]) for z in mit_pnl), 4),
        "pnl_usd": round(sum(float(z["pnl_usd"]) for z in mit_pnl), 4),
        # Haltedauer nur ueber Fills vor Marktschluss; ein Fill nach dem
        # Schluss hat keine Dauer, sondern ist ein Befund fuer sich.
        "filled_after_close": len(nach_schluss),
        "days_held_n": len(dauern),
        "mean_days_held": round(sum(dauern) / len(dauern), 2) if dauern else None,
        "median_days_held": _median(dauern),
        # Zweite Rechnung mit dem Einstieg, den der CLOB-Tagespreis stuetzt.
        "entry_checks": _zaehle(z.get("entry_check") for z in resolved),
        "with_corrected_pnl": len(mit_korr),
        "without_corrected_pnl_reasons": _zaehle(z["pnl_corrected_reason"] for z in resolved if z.get("pnl_corrected_usd") is None),
        "won_corrected": sum(1 for z in mit_korr if z["pnl_corrected_usd"] > 0),
        "lost_corrected": sum(1 for z in mit_korr if z["pnl_corrected_usd"] < 0),
        "flat_corrected": sum(1 for z in mit_korr if z["pnl_corrected_usd"] == 0),
        "cost_corrected_usd": round(sum(float(z["size_usd"]) for z in mit_korr), 4),
        "payout_corrected_usd": round(sum(float(z["payout_corrected_usd"]) for z in mit_korr), 4),
        "pnl_corrected_usd": round(sum(float(z["pnl_corrected_usd"]) for z in mit_korr), 4),
        "baskets": len(koerbe),
        "baskets_resolved": sum(1 for k in koerbe if k["resolved_legs"] == k["legs"]),
        "baskets_not_exclusive": sum(1 for k in koerbe if k.get("mutually_exclusive") is False),
        "baskets_pnl_usd": round(sum(float(k["pnl_usd"]) for k in koerbe if k.get("pnl_usd") is not None), 4),
        "baskets_pnl_corrected_usd": round(sum(float(k["pnl_corrected_usd"]) for k in koerbe if k.get("pnl_corrected_usd") is not None), 4),
    }


def _zaehle(werte: Any) -> dict[str, int]:
    raus: dict[str, int] = {}
    for w in werte:
        raus[str(w)] = raus.get(str(w), 0) + 1
    return raus


def _median(werte: list[float]) -> float | None:
    if not werte:
        return None
    s = sorted(werte)
    n = len(s)
    return round(s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0, 2)


# ---------------------------------------------------------------- Quellen

def trades_from_bot_db(pfad: str | Path) -> list[dict[str, Any]]:
    """Die Papier-Trades aus der SQLite-Datei des Scanners, nur lesend."""

    uri = "file:" + str(Path(pfad).resolve()).replace("\\", "/") + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT id, strategy, slug, question, token_id, side, size_usd, entry_price, size_shares, "
            "timestamp, opportunity_id, link_status FROM paper_trades ORDER BY timestamp"
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def trades_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Die publizierten ``paper_positions``: ohne Einstiegspreis und Seite,
    also nur fuer Status und Dauer gut, nicht fuer den Gewinn."""

    raus = []
    for p in payload.get("paper_positions") or []:
        if not isinstance(p, dict):
            continue
        raus.append({
            "id": p.get("trade_id"), "strategy": p.get("strategy"), "slug": p.get("title"),
            "question": "", "token_id": "", "side": "NO", "size_usd": p.get("capital_usd"),
            "entry_price": None, "size_shares": None, "opened_at": p.get("opened_at"),
            "opportunity_id": p.get("opportunity_id"), "link_status": None,
        })
    return raus


# ---------------------------------------------------------------- Lauf

def resolve_all(trades: list[dict[str, Any]], fetch: FetchJson = fetch_json,
                cache: dict[str, Any] | None = None, now: datetime | None = None,
                with_clob: bool = True) -> dict[str, Any]:
    """Alle Trades aufloesen. ``cache`` (slug -> Gamma-Markt, "clob:<token>"
    -> Tagesverlauf) spart Abrufe. ``with_clob=False`` laesst den Abgleich
    des Einstiegs gegen den Tagespreis weg."""

    cache = cache if cache is not None else {}
    now = now or datetime.now(timezone.utc)
    zeilen = []
    for t in trades:
        slug = str(t.get("slug") or t.get("title") or "")
        kalshi_bein = slug.startswith(KALSHI_PAPER_SLUG_PREFIX)
        if kalshi_bein:
            # Kein Gamma-Markt und kein CLOB-Token: der Scanner rechnet das
            # Bein selbst ab, hier bleibt es mit Grund unbekannt.
            cache.setdefault(slug, None)
        elif slug not in cache:
            cache[slug] = lookup_market(slug, str(t.get("token_id") or ""), fetch)
        token = str(t.get("token_id") or "")
        tag = None
        if token and with_clob and not kalshi_bein:
            schluessel = "clob:" + token
            if schluessel not in cache:
                cache[schluessel] = _clob_history(token, fetch)
            tag = clob_price_near(token, _fill_zeit(t), fetch, history=cache[schluessel])
        zeile = resolve_trade(t, cache[slug], now, day=tag)
        if kalshi_bein:
            zeile["pnl_reason"] = KALSHI_LEG_REASON
            zeile["pnl_corrected_reason"] = KALSHI_LEG_REASON
        zeilen.append(zeile)
    koerbe = baskets(zeilen)
    return {
        "schema": "arb_resolutions/1",
        "generated_at": now.isoformat(),
        "source": "Polymarket Gamma /markets with closed=true, read per trade slug",
        "method": (
            "Shares are size_shares or size_usd / entry_price; payout is shares times the settlement price of "
            "the traded side (1, 0, or 0.5 on a split settlement); PnL is payout minus stake, before any fee. "
            "Days held run from the paper fill to the market's closedTime. A trade without a valid entry price "
            "gets no PnL and a reason, as in the scanner's own rule. A second computation (corrected) uses the "
            "entry the CLOB day price supports: where the journal's entry only matches as 1 minus entry, the "
            "journal stored the other side's price and the corrected entry is 1 minus the recorded one. A leg whose "
            "entry matches neither side, has no day price, or was filled after the market's closedTime gets no "
            "corrected PnL, only the reason. A Kalshi leg (slug kalshi:<ticker>, paper-fired by the scanner since "
            "2026-09-05) is settled by the scanner against Kalshi's own result and stays unknown here."
        ),
        "trades": zeilen,
        "baskets": koerbe,
        "summary": summary(zeilen, koerbe),
    }
