"""Wallet ledger: everything one Polymarket wallet did, grouped by event.

Pure transformation over the raw rows of the public Polymarket Data API
(``/activity``, ``/positions``, ``/closed-positions`` in both sort
directions) plus the two published artefacts that say which of those trades
were the bot's (``public/data/runs.json``) and which were the pre-registered
pilot (``public/data/pilot.json``). No network here — ``scripts/wallet_ledger.py``
fetches and calls :func:`build_ledger`; the tests feed fixtures.

Attribution rules, stated once so the page can quote them:

* ``bot``: the market question AND side appear in a runs.json run log
  (``wetten[].frage`` / ``seite``) of the run whose ``event_slug`` is the
  event. The run profile is kept.
* ``pilot``: the market's condition id or exact question matches one of the
  pilot.json trades.
* ``discretionary``: everything else — placed by hand, not in any run log.

An event takes the type of its markets: bot if any market is bot, else pilot
if any is pilot, else discretionary; a mixed event says so in ``typ_mix``.

Every dollar figure is a sum over the API rows, rounded at the end. Deposits
are not derivable from the Data API and are published as ``null``.
"""

from __future__ import annotations

from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

WALLET = "0x29afe1bf37700768a640a08f1b35dad5f202f88d"
KENNZEICHNUNG = "wallet/public-api"
EVENT_URL = "https://polymarket.com/event/"

TYP_BOT = "bot"
TYP_DISKRETIONAER = "discretionary"
TYP_PILOT = "pilot"

#: The public ``/closed-positions`` feed returns at most ~50 rows per direction.
CLOSED_POSITIONS_CAP = 50

#: Event-level notes for things known outside the API. Keyed by a substring
#: of the event slug; the text is the note.
BEKANNTE_NOTIZEN: tuple[tuple[str, str], ...] = (
    (
        "president-curtis-season-1",
        "Forecasts pre-registered before airing: "
        "https://github.com/Pablozh123/multi-agent-orchestration-informational-efficiency/blob/main/docs/project/PREREG_CURTIS_E3_2026-08-07.md",
    ),
)

PILOT_NOTIZ = "Pre-registered small-stake pilot, rules frozen 2026-07-18; one of the 20 pilot trades of 2026-07-22."

#: Prefix of ``pnl_art`` for rows whose PnL was taken from the wallet's own
#: payments because the closed-positions feed contradicted itself.
KASSEN_KORREKTUR = "realised from the wallet's own cash flow"


# ----------------------------------------------------------------- helpers

def _num(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    if out != out:  # NaN
        return default
    return out


def _text(value: Any) -> str:
    return "" if value is None else str(value)


def _iso(ts: Any) -> str:
    """Unix seconds -> ISO-8601 UTC string; empty when missing."""

    try:
        stamp = int(float(ts))
    except (TypeError, ValueError):
        return ""
    if stamp <= 0:
        return ""
    return datetime.fromtimestamp(stamp, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _r2(value: float) -> float:
    return round(float(value), 2) or 0.0   # `or 0.0` folds -0.0 into 0.0


def _r4(value: float) -> float:
    return round(float(value), 4) or 0.0


def _seite(value: Any) -> str:
    """Outcome label as YES/NO for matching (the API says "Yes"/"No")."""

    return _text(value).strip().upper()


def humanize_slug(slug: str) -> str:
    """Fallback event title from the slug: trailing numeric id dropped, words capitalised."""

    parts = [p for p in _text(slug).split("-") if p]
    if parts and parts[-1].isdigit() and len(parts[-1]) >= 12:
        parts = parts[:-1]
    text = " ".join(parts)
    return text[:1].upper() + text[1:] if text else _text(slug)


# ------------------------------------------------------- attribution indices

def bot_bets_index(runs_payload: Mapping[str, Any] | None) -> dict[str, dict[str, Any]]:
    """{event_slug: {"profil": str, "bets": {(question, SIDE): bet}}} from runs.json.

    A run without an event slug cannot be matched and is skipped; a run with
    no bets is still recorded (with an empty ``bets`` map) so the ledger can
    say "the bot covered this event but placed nothing".
    """

    out: dict[str, dict[str, Any]] = {}
    for run in (runs_payload or {}).get("runs", []) or []:
        if not isinstance(run, Mapping):
            continue
        slug = _text(run.get("event_slug")).strip()
        if not slug:
            continue
        slot = out.setdefault(slug, {"profil": _text(run.get("profil")), "bets": {}})
        if not slot["profil"]:
            slot["profil"] = _text(run.get("profil"))
        for bet in run.get("wetten", []) or []:
            if not isinstance(bet, Mapping):
                continue
            key = (_text(bet.get("frage")).strip(), _seite(bet.get("seite")))
            slot["bets"].setdefault(key, dict(bet))
    return out


def pilot_index(pilot_payload: Mapping[str, Any] | None,
                condition_ids: Iterable[str] | None = None) -> dict[str, Any]:
    """Titles and condition ids of the pilot trades, plus the freeze date."""

    titles: set[str] = set()
    market_ids: set[str] = set()
    for trade in (pilot_payload or {}).get("trades", []) or []:
        if not isinstance(trade, Mapping):
            continue
        title = _text(trade.get("markt_frage")).strip()
        if title:
            titles.add(title)
        mid = _text(trade.get("markt_id")).strip()
        if mid:
            market_ids.add(mid)
    protokoll = (pilot_payload or {}).get("protokoll") or {}
    return {
        "titles": titles,
        "market_ids": market_ids,
        "condition_ids": {str(c).lower() for c in (condition_ids or []) if c},
        "regel_freeze_datum": _text(protokoll.get("regel_freeze_datum")) if isinstance(protokoll, Mapping) else "",
        "n_trades": len((pilot_payload or {}).get("trades", []) or []),
    }


def resolved_positions_union(closed_desc: Iterable[Mapping[str, Any]] | None,
                             closed_asc: Iterable[Mapping[str, Any]] | None) -> tuple[list[dict[str, Any]], bool]:
    """Union of the winner and loser tails by (conditionId, outcome); capped when both tails hit ~50."""

    desc = [dict(r) for r in (closed_desc or []) if isinstance(r, Mapping)]
    asc = [dict(r) for r in (closed_asc or []) if isinstance(r, Mapping)]
    union: "OrderedDict[tuple[str, str], dict[str, Any]]" = OrderedDict()
    for row in desc + asc:
        key = (_text(row.get("conditionId")).lower(), _seite(row.get("outcome")))
        union.setdefault(key, row)
    capped = len(desc) >= CLOSED_POSITIONS_CAP and len(asc) >= CLOSED_POSITIONS_CAP
    return list(union.values()), capped


# ---------------------------------------------------------------- the ledger

def _market_status(closed_row: Mapping[str, Any] | None, open_row: Mapping[str, Any] | None,
                   kasse: Mapping[str, Any] | None = None) -> tuple[str, float | None, str]:
    """(status, pnl_usd, pnl_art) for one market from the two position feeds.

    ``kasse`` is the market's own cash flow as the activity feed recorded it
    (``kauf_usd``, ``verkauf_usd``, ``einloesung_usd``). It settles a
    contradiction the closed-positions feed produces for redeemed positions:
    ``curPrice`` 1 means the outcome the wallet held settled at one dollar, and
    a redemption paying one dollar per share confirms it, yet the feed still
    reports ``realizedPnl = minus the whole stake``. Six of this wallet's 45
    resolved rows look like that (for example "Will Anthropic have the #2 AI
    model at the end of July 2026?": 5.3191 shares bought for $5.01, redeemed
    for $5.32, feed says −$5.01). Where the feed contradicts itself the
    wallet's own payments decide, because they are what actually moved.
    """

    if closed_row is not None:
        pnl = _num(closed_row.get("realizedPnl"))
        art = "realised (API realizedPnl)"
        kauf = _num((kasse or {}).get("kauf_usd"))
        verkauf = _num((kasse or {}).get("verkauf_usd"))
        einloesung = _num((kasse or {}).get("einloesung_usd"))
        if _num(closed_row.get("curPrice")) >= 1.0 and pnl < 0 and einloesung > 0 and kauf > 0:
            pnl = verkauf + einloesung - kauf
            art = KASSEN_KORREKTUR + " — the API's realizedPnl contradicts curPrice 1 and a full redemption"
        if pnl > 0:
            return "won", pnl, art
        if pnl < 0:
            return "lost", pnl, art
        return "flat", pnl, art
    if open_row is not None:
        cur = _num(open_row.get("curPrice"))
        value = _num(open_row.get("currentValue"))
        pnl = _num(open_row.get("cashPnl"))
        if cur <= 0 and value <= 0:
            return "worthless", pnl, "position resolved against and not redeemed (API cashPnl)"
        return "open", pnl, "unrealised (API cashPnl at curPrice)"
    return "unknown", None, "not in /positions or /closed-positions"


def build_ledger(
    activity: Iterable[Mapping[str, Any]],
    positions: Iterable[Mapping[str, Any]] | None = None,
    closed_desc: Iterable[Mapping[str, Any]] | None = None,
    closed_asc: Iterable[Mapping[str, Any]] | None = None,
    *,
    wallet: str = WALLET,
    runs_payload: Mapping[str, Any] | None = None,
    pilot_payload: Mapping[str, Any] | None = None,
    pilot_condition_ids: Iterable[str] | None = None,
    event_titles: Mapping[str, str] | None = None,
    stand_utc: str | None = None,
    quellen: Mapping[str, Any] | None = None,
    einzahlungen_usd: float | None = None,
) -> dict[str, Any]:
    """The published ledger: header, ``aggregat`` and ``events[]``."""

    wallet = _text(wallet).lower()
    stand = stand_utc or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    bots = bot_bets_index(runs_payload)
    pilot = pilot_index(pilot_payload, pilot_condition_ids)
    closed, capped = resolved_positions_union(closed_desc, closed_asc)
    closed_by = {(_text(r.get("conditionId")).lower(), _seite(r.get("outcome"))): r for r in closed}
    open_by = {(_text(r.get("conditionId")).lower(), _seite(r.get("outcome"))): dict(r)
               for r in (positions or []) if isinstance(r, Mapping)}
    titles = dict(event_titles or {})

    # ---- pass 1: per event / per market accumulation from the activity feed
    events: "OrderedDict[str, dict[str, Any]]" = OrderedDict()
    n_trades = n_buys = n_sells = n_redeems = 0
    buys_usd = sells_usd = redeems_usd = 0.0
    first_ts: int | None = None
    last_ts: int | None = None
    n_ignored = 0
    rows: list[Mapping[str, Any]] = [r for r in (activity or []) if isinstance(r, Mapping)]
    # The feed is newest-first. Trades go first so a redemption can be attached
    # to the position it closes: a redeem row on a lost side pays $0 and the
    # API stamps it with the *winning* outcome, which would otherwise open a
    # phantom market with no stake.
    ordnung = {"TRADE": 0, "REDEEM": 1}
    rows.sort(key=lambda r: (ordnung.get(_text(r.get("type")).upper(), 2), _num(r.get("timestamp"))))
    for row in rows:
        typ = _text(row.get("type")).upper()
        slug = _text(row.get("eventSlug")).strip() or _text(row.get("slug")).strip()
        if typ not in ("TRADE", "REDEEM") or not slug:
            n_ignored += 1
            continue
        try:
            ts = int(float(row.get("timestamp") or 0))
        except (TypeError, ValueError):
            ts = 0
        usd = _num(row.get("usdcSize"))
        shares = _num(row.get("size"))
        cid = _text(row.get("conditionId")).lower()
        side = _seite(row.get("outcome"))
        ev = events.setdefault(slug, {
            "event_slug": slug, "maerkte": OrderedDict(), "first": None, "last": None,
            "n_trades": 0, "n_kaeufe": 0, "n_verkaeufe": 0, "n_einloesungen": 0,
            "kaeufe_usd": 0.0, "verkaeufe_usd": 0.0, "einloesungen_usd": 0.0,
        })
        key = (cid, side)
        if typ == "REDEEM" and key not in ev["maerkte"]:
            gleiche = [k for k in ev["maerkte"] if k[0] == cid]
            if len(gleiche) == 1:
                key = gleiche[0]
        mk = ev["maerkte"].setdefault(key, {
            "condition_id": cid, "titel": _text(row.get("title")), "slug": _text(row.get("slug")),
            "seite": _text(row.get("outcome")) or "—", "kauf_usd": 0.0, "kauf_shares": 0.0,
            "verkauf_usd": 0.0, "verkauf_shares": 0.0, "einloesung_usd": 0.0,
            "n_trades": 0, "n_einloesungen": 0, "first": None, "last": None,
        })
        if ts:
            for slot in (ev, mk):
                slot["first"] = ts if slot["first"] is None else min(slot["first"], ts)
                slot["last"] = ts if slot["last"] is None else max(slot["last"], ts)
            first_ts = ts if first_ts is None else min(first_ts, ts)
            last_ts = ts if last_ts is None else max(last_ts, ts)
        if typ == "TRADE":
            n_trades += 1
            ev["n_trades"] += 1
            mk["n_trades"] += 1
            if _text(row.get("side")).upper() == "SELL":
                n_sells += 1
                sells_usd += usd
                ev["n_verkaeufe"] += 1
                ev["verkaeufe_usd"] += usd
                mk["verkauf_usd"] += usd
                mk["verkauf_shares"] += shares
            else:
                n_buys += 1
                buys_usd += usd
                ev["n_kaeufe"] += 1
                ev["kaeufe_usd"] += usd
                mk["kauf_usd"] += usd
                mk["kauf_shares"] += shares
        else:
            n_redeems += 1
            redeems_usd += usd
            ev["n_einloesungen"] += 1
            ev["einloesungen_usd"] += usd
            mk["einloesung_usd"] += usd
            mk["n_einloesungen"] += 1

    # ---- pass 2: attribution, status, per-event roll-up
    status_zaehler = {"won": 0, "lost": 0, "flat": 0, "worthless": 0, "open": 0, "unknown": 0}
    typ_zaehler: dict[str, dict[str, Any]] = {
        t: {"events": 0, "maerkte": 0, "einsatz_usd": 0.0, "netto_cash_usd": 0.0}
        for t in (TYP_BOT, TYP_DISKRETIONAER, TYP_PILOT)
    }
    realisiert_api = 0.0
    wertlos_pnl = 0.0
    offen_pnl = 0.0
    n_korrigiert = 0
    out_events: list[dict[str, Any]] = []
    seen_positions: set[tuple[str, str]] = set()
    for slug, ev in events.items():
        run = bots.get(slug)
        maerkte_out: list[dict[str, Any]] = []
        zuordnungen: list[str] = []
        pnl_sum = 0.0
        pnl_offen = 0.0
        pnl_known = False
        ev_status = {"won": 0, "lost": 0, "flat": 0, "worthless": 0, "open": 0, "unknown": 0}
        for key, mk in ev["maerkte"].items():
            seen_positions.add(key)
            title = mk["titel"].strip()
            side = key[1]
            zuordnung = TYP_DISKRETIONAER
            run_profil = ""
            if run is not None and (title, side) in run["bets"]:
                zuordnung = TYP_BOT
                run_profil = run["profil"]
            elif key[0] in pilot["condition_ids"] or title in pilot["titles"]:
                zuordnung = TYP_PILOT
            zuordnungen.append(zuordnung)
            status, pnl, pnl_art = _market_status(closed_by.get(key), open_by.get(key), mk)
            status_zaehler[status] += 1
            ev_status[status] += 1
            if pnl_art.startswith(KASSEN_KORREKTUR):
                n_korrigiert += 1
            if pnl is not None:
                pnl_sum += pnl
                pnl_known = True
                if closed_by.get(key) is not None:
                    realisiert_api += pnl
                elif status == "worthless":
                    wertlos_pnl += pnl
                elif status == "open":
                    offen_pnl += pnl
                    pnl_offen += pnl
            avg = mk["kauf_usd"] / mk["kauf_shares"] if mk["kauf_shares"] > 0 else None
            typ_zaehler[zuordnung]["maerkte"] += 1
            typ_zaehler[zuordnung]["einsatz_usd"] += mk["kauf_usd"]
            typ_zaehler[zuordnung]["netto_cash_usd"] += mk["verkauf_usd"] + mk["einloesung_usd"] - mk["kauf_usd"]
            maerkte_out.append({
                "titel": title,
                "seite": mk["seite"],
                "condition_id": mk["condition_id"],
                "slug": mk["slug"],
                "zuordnung": zuordnung,
                "run_profil": run_profil,
                "avg_preis": _r4(avg) if avg is not None else None,
                "shares": _r2(mk["kauf_shares"]),
                "einsatz_usd": _r2(mk["kauf_usd"]),
                "verkauft_usd": _r2(mk["verkauf_usd"]),
                "eingeloest_usd": _r2(mk["einloesung_usd"]),
                "netto_cash_usd": _r2(mk["verkauf_usd"] + mk["einloesung_usd"] - mk["kauf_usd"]),
                "pnl_usd": _r2(pnl) if pnl is not None else None,
                "pnl_art": pnl_art,
                "status": status,
                "n_trades": mk["n_trades"],
                "n_einloesungen": mk["n_einloesungen"],
                "erster_trade_utc": _iso(mk["first"]),
                "letzter_trade_utc": _iso(mk["last"]),
            })
        # Event type from its markets; a mixed event says so.
        arten = []
        for t in (TYP_BOT, TYP_PILOT, TYP_DISKRETIONAER):
            if t in zuordnungen:
                arten.append(t)
        typ = arten[0] if arten else TYP_DISKRETIONAER
        typ_zaehler[typ]["events"] += 1
        notes: list[str] = []
        if run is not None and TYP_BOT not in zuordnungen:
            notes.append(
                f"Bot run '{run['profil']}' covered this event but its log records no fill here; "
                "these trades are not in the run log."
            )
        elif len(arten) > 1:
            n_other = sum(1 for z in zuordnungen if z != TYP_BOT)
            notes.append(
                f"{n_other} of {len(zuordnungen)} markets are not in the run log of '{run['profil'] if run else ''}' "
                "(discretionary)."
            )
        if TYP_PILOT in zuordnungen:
            notes.append(PILOT_NOTIZ)
        for needle, note in BEKANNTE_NOTIZEN:
            if needle in slug:
                notes.append(note)
        titel = _text(titles.get(slug)).strip()
        titel_quelle = "gamma" if titel else "slug"
        if not titel:
            titel = humanize_slug(slug)
        status_text = " · ".join(f"{n} {label}" for label, n in ev_status.items() if n)
        out_events.append({
            "event_slug": slug,
            "titel": titel,
            "titel_quelle": titel_quelle,
            "url": EVENT_URL + slug,
            "typ": typ,
            "typ_mix": " + ".join(arten) if len(arten) > 1 else "",
            "run_profil": run["profil"] if run is not None else "",
            "run_im_log": bool(run is not None and TYP_BOT in zuordnungen),
            "von_utc": _iso(ev["first"]),
            "bis_utc": _iso(ev["last"]),
            "n_maerkte": len(maerkte_out),
            "n_trades": ev["n_trades"],
            "n_kaeufe": ev["n_kaeufe"],
            "n_verkaeufe": ev["n_verkaeufe"],
            "n_einloesungen": ev["n_einloesungen"],
            "einsatz_usd": _r2(ev["kaeufe_usd"]),
            "verkaeufe_usd": _r2(ev["verkaeufe_usd"]),
            "einloesungen_usd": _r2(ev["einloesungen_usd"]),
            "netto_cash_usd": _r2(ev["verkaeufe_usd"] + ev["einloesungen_usd"] - ev["kaeufe_usd"]),
            "pnl_usd": _r2(pnl_sum) if pnl_known else None,
            # Der unrealisierte Teil derselben Summe. ``pnl_usd`` mischt den
            # abgerechneten PnL aufgeloester Maerkte mit dem Buchgewinn noch
            # offener Positionen; ohne diese Zahl kann die Seite den Titel
            # "API realised PnL" nicht ehrlich fuehren.
            "pnl_offen_usd": _r2(pnl_offen) if ev_status["open"] else None,
            "status": ev_status,
            "status_text": status_text or "—",
            "notes": notes,
            "maerkte": maerkte_out,
        })
    out_events.sort(key=lambda e: (e["von_utc"], e["event_slug"]), reverse=True)

    # Positions the two position feeds know but the activity feed does not
    # (should be none for a wallet whose whole history fits in the feed).
    n_positions_ohne_activity = sum(1 for k in list(closed_by) + list(open_by) if k not in seen_positions)

    aggregat = {
        # Einzahlungen sieht das oeffentliche Data API nicht. Der Betreiber
        # kann sie deklarieren (per USDC-Transfers der Wallet on-chain
        # nachpruefbar); der Hinweis sagt dann, woher die Zahl stammt.
        "einzahlungen_usd": _r2(einzahlungen_usd) if einzahlungen_usd is not None else None,
        "einzahlungen_hinweis": (
            "declared by the wallet owner; verifiable on-chain via the wallet's USDC transfers, "
            "not derivable from the public Data API"
            if einzahlungen_usd is not None
            else "not derivable from the public Data API (needs an on-chain USDC transfer scan)"
        ),
        "kaeufe_usd": _r2(buys_usd),
        "verkaeufe_usd": _r2(sells_usd),
        "einloesungen_usd": _r2(redeems_usd),
        "rueckfluss_usd": _r2(sells_usd + redeems_usd),
        "netto_cashflow_usd": _r2(sells_usd + redeems_usd - buys_usd),
        "realisierter_pnl_api_usd": _r2(realisiert_api),
        # Der PnL der aufgeloesten, aber nie eingeloesten Positionen. Er steht
        # NICHT in ``realisierter_pnl_api_usd``: die stehen im /positions-Feed
        # und tauchen in /closed-positions nie auf. Es sind ausschliesslich
        # Verluste, die Summe oben ist also nach oben verzerrt — bei dieser
        # Wallet um 113,86 Dollar auf 55 Positionen. ``abgerechneter_pnl_usd``
        # ist die Zahl, die sich nicht mehr bewegen kann.
        "wertlos_pnl_usd": _r2(wertlos_pnl),
        "abgerechneter_pnl_usd": _r2(realisiert_api + wertlos_pnl),
        "offener_pnl_usd": _r2(offen_pnl),
        # Zeilen, deren realizedPnl dem eigenen Zahlungsstrom widersprach und
        # aus ihm neu gerechnet wurde (siehe ``_market_status``).
        "positionen_kassenkorrigiert": n_korrigiert,
        "n_events": len(out_events),
        "n_maerkte": sum(e["n_maerkte"] for e in out_events),
        "n_trades": n_trades,
        "n_kaeufe": n_buys,
        "n_verkaeufe": n_sells,
        "n_einloesungen": n_redeems,
        "n_activity_ignoriert": n_ignored,
        "positionen": dict(status_zaehler),
        "positionen_gewonnen": status_zaehler["won"],
        "positionen_verloren": status_zaehler["lost"] + status_zaehler["worthless"],
        "positionen_wertlos": status_zaehler["worthless"],
        "positionen_offen": status_zaehler["open"],
        "positionen_flat": status_zaehler["flat"],
        "positionen_ohne_activity": n_positions_ohne_activity,
        "closed_positions_capped": capped,
        "erste_aktivitaet_utc": _iso(first_ts),
        "letzte_aktivitaet_utc": _iso(last_ts),
        "nach_typ": {
            t: {"events": v["events"], "maerkte": v["maerkte"], "einsatz_usd": _r2(v["einsatz_usd"]),
                "netto_cash_usd": _r2(v["netto_cash_usd"])}
            for t, v in typ_zaehler.items()
        },
    }

    hinweis = (
        "Every trade and redemption of the trading wallet on Polymarket, grouped by event, rebuilt "
        "read-only from the public Polymarket Data API (/activity, /positions, /closed-positions in both "
        "sort directions). Anyone can rerun scripts/wallet_ledger.py for this address and get the same "
        "file. Type: bot = market and side appear in a runs.json run log; pilot = one of the pre-registered "
        "pilot trades in pilot.json; discretionary = placed by hand, in no run log. Dollar figures are sums "
        "over the API rows; realised PnL per market is the API's realizedPnl and can differ from the cash "
        "flow of an event. Where that field contradicts the settlement price and the redemption the wallet "
        "received, the wallet's own payments decide (pnl_art says so per market). realisierter_pnl_api_usd "
        "covers the closed-positions feed only; resolved positions that were never redeemed sit in /positions "
        "and are exclusively losses, so abgerechneter_pnl_usd (realised + worthless) is the settled total. "
        "Deposits are not in the Data API. A record of process, not a return claim."
    )
    return {
        "hinweis": hinweis,
        "stand_utc": stand,
        "wallet": wallet,
        "kennzeichnung": KENNZEICHNUNG,
        "regeln": {
            "bot": "market question and side appear in runs.json wetten[] of the run with this event_slug",
            "pilot": "condition id or exact question matches a pilot.json trade"
                     + (f" (rules frozen {pilot['regel_freeze_datum']})" if pilot["regel_freeze_datum"] else ""),
            "discretionary": "everything else",
        },
        "quellen": dict(quellen or {}),
        "abgleich": {
            "runs_json_stand_utc": _text((runs_payload or {}).get("stand_utc")),
            "runs_json_n_runs": len((runs_payload or {}).get("runs", []) or []),
            "pilot_json_stand_utc": _text((pilot_payload or {}).get("stand_utc")),
            "pilot_json_n_trades": pilot["n_trades"],
            "pilot_condition_ids_aufgeloest": len(pilot["condition_ids"]),
        },
        "aggregat": aggregat,
        "events": out_events,
    }
