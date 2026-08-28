"""What a flagged wallet actually holds in the flagged market.

The risk screen names the wallets behind a burst of prints and the side they
bought. That alone misreads a hedge: a wallet sitting on 12k NO that buys YES
is closing (or merging) its NO, not opening a YES bet — the tape shows "YES
buys", the book says "net NO". This module reads the wallet's open positions
in that one market from the public Data API and states the relation between
the flagged flow and the book, so the card can say "reduces a NO book" instead
of leaving the reader to guess.

Streamlit-free; ``api/server.py`` serves it as ``GET /api/risk/book``. Only
Polymarket exposes wallets, so this is Polymarket-only by construction.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

from src import prediction_markets as md

#: How many wallets one call looks up (a card names at most three).
MAX_WALLETS = 5

#: A shares gap smaller than this share of the larger side reads as balanced.
BALANCED_TOLERANCE = 0.10

_ADDRESS = re.compile(r"^0x[a-fA-F0-9]{40}$")


def _num(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    return out if out == out else default


def _field(row: Mapping[str, Any], *names: str) -> Any:
    """Erster Schluessel, der wirklich einen Wert traegt.

    ``row.get("curPrice", row.get("current_price"))`` nimmt den camelCase-Wert
    auch dann, wenn er ``null`` ist, und wirft die zweite Schreibweise weg.
    Genau an dieser Stelle entscheidet sich, ob eine Zeile keinen Preis hat
    oder ob der Preis nur unter dem anderen Namen steht.
    """

    for name in names:
        value = row.get(name)
        if value is not None:
            return value
    return None


def _outcome_side(outcome: Any) -> str:
    text = str(outcome or "").strip().upper()
    if text in {"YES", "Y"}:
        return "YES"
    if text in {"NO", "N"}:
        return "NO"
    return text


def fetch_market_positions(wallet: str, market_key: str, limit: int = 100) -> list[dict[str, Any]]:
    """Open positions of ``wallet`` in ``market_key`` (conditionId), raw rows.

    The Data API filters by market itself (``market=<conditionId>``); the
    result is filtered once more here in case the upstream ignores it.
    Raises ``md.MarketDataError`` on network failure so the caller can say
    "not read" instead of "no position".
    """

    wallet = str(wallet or "").strip().lower()
    market_key = str(market_key or "").strip()
    if not _ADDRESS.match(wallet) or not market_key:
        return []
    data = md._get_json(f"{md.POLY_DATA}/positions", params={"user": wallet, "market": market_key, "limit": int(limit)})
    rows = data if isinstance(data, list) else (data or {}).get("data", [])
    out: list[dict[str, Any]] = []
    for row in rows or []:
        if not isinstance(row, Mapping):
            continue
        cid = str(row.get("conditionId") or row.get("market_key") or "")
        if cid and cid != market_key:
            continue
        out.append(dict(row))
    return out


def summarize_book(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Shares and value per side of one market, plus the net reading.

    A position that resolved against the wallet stays in ``/positions``
    forever when nobody redeems it: size unchanged, ``curPrice`` 0,
    ``currentValue`` 0. Counting those shares as a book turns a dead side
    into a live one — the reference wallet's ten leftover rows would read as
    "holds 228 NO now" in a market that settled on 2026-07-29. They are
    reported as ``settled_shares`` and kept out of the sides and the net.

    A row the feed never priced is not one of those. ``curPrice: null`` read
    as 0.0 looked exactly like the measured zero and was counted as a
    settled total loss, so a gap in the feed became a loss on the card. The state
    comes from ``md.position_price_state`` — the same three-way predicate the
    wallet page reads — and the third state gets its own numbers,
    ``unpriced_shares`` and ``unpriced_positions``: in no side, in no net and
    in no settled figure.
    """

    yes_shares = no_shares = yes_value = no_value = 0.0
    yes_avg_num = no_avg_num = 0.0
    other = 0
    settled_shares = 0.0
    settled_n = 0
    unpriced_shares = 0.0
    unpriced_n = 0
    for row in rows or []:
        side = _outcome_side(row.get("outcome"))
        shares = _num(_field(row, "size", "shares"))
        if shares <= 0:
            continue
        # Erst der Zustand, dann die Zahlen: die Rohwerte gehen ungefiltert in
        # das Praedikat, denn ein Ersatzwert 0.0 waere schon die Antwort, die
        # hier erst gesucht wird.
        roh_preis = _field(row, "curPrice", "current_price")
        roh_wert = _field(row, "currentValue", "value")
        zustand = md.position_price_state(roh_preis, roh_wert)
        if zustand == md.POSITION_PRICE_WORTHLESS:
            settled_shares += shares
            settled_n += 1
            continue
        if zustand == md.POSITION_PRICE_UNKNOWN:
            # Weder Buch noch abgerechnet: der Feed hat diese Zeile nicht
            # bepreist. Sie steht mit eigener Zahl daneben, damit die Luecke
            # sichtbar bleibt, statt eine der beiden Summen zu faerben.
            unpriced_shares += shares
            unpriced_n += 1
            continue
        cur = _num(roh_preis)
        value = _num(roh_wert)
        if value <= 0:
            value = shares * cur
        avg = _num(_field(row, "avgPrice", "avg_price"))
        if side == "YES":
            yes_shares += shares
            yes_value += value
            yes_avg_num += avg * shares
        elif side == "NO":
            no_shares += shares
            no_value += value
            no_avg_num += avg * shares
        else:
            other += 1
    larger = max(yes_shares, no_shares)
    if larger <= 0:
        net = "none"
    elif abs(yes_shares - no_shares) <= BALANCED_TOLERANCE * larger:
        net = "balanced"
    else:
        net = "YES" if yes_shares > no_shares else "NO"
    return {
        "yes_shares": round(yes_shares, 2),
        "no_shares": round(no_shares, 2),
        "yes_value": round(yes_value, 2),
        "no_value": round(no_value, 2),
        "yes_avg": round(yes_avg_num / yes_shares, 4) if yes_shares > 0 else None,
        "no_avg": round(no_avg_num / no_shares, 4) if no_shares > 0 else None,
        "net": net,
        "net_shares": round(abs(yes_shares - no_shares), 2),
        "other_outcomes": other,
        "settled_shares": round(settled_shares, 2),
        "settled_positions": settled_n,
        "unpriced_shares": round(unpriced_shares, 2),
        "unpriced_positions": unpriced_n,
    }


def relate_flow_to_book(flagged_side: str, book: Mapping[str, Any]) -> dict[str, str]:
    """How the flagged flow ("YES buys", "NO sells", …) sits against the book.

    Returns ``relation`` (one of new_bet, adds, reduces, hedge, exit,
    unpriced, unknown) and a one-line ``text`` for the card.
    "reduces"/"hedge": the flow works against the larger side of the book —
    the wallet is closing or hedging, not opening. "adds": same direction as
    the book. "new_bet": no position left on either side (the flow *is* the
    position, or it was closed since). "unpriced": nothing priced is left,
    but the feed did not price every row, so "nothing held" would be a claim
    about rows nobody read.
    """

    side = str(flagged_side or "").strip().upper()
    m = re.match(r"^(YES|NO)\s+(BUYS|SELLS)$", side)
    net = str(book.get("net") or "none")
    yes_s = _num(book.get("yes_shares"))
    no_s = _num(book.get("no_shares"))
    hold = f"holds {_fmt(yes_s)} YES / {_fmt(no_s)} NO now"
    # Aufgeloeste, nie eingeloeste Anteile stehen weiter im Feed. Sie sind
    # kein Buch, aber sie erklaeren, warum hier nichts mehr steht. Zeilen ohne
    # Preis erklaeren das Gegenteil: dort steht moeglicherweise etwas, das der
    # Feed nur nicht bepreist hat.
    settled = _num(book.get("settled_shares"))
    unpriced = _num(book.get("unpriced_shares"))
    noten = []
    if settled > 0:
        noten.append(f"{_fmt(settled)} shares of a settled position left unredeemed")
    if unpriced > 0:
        noten.append(f"{_fmt(unpriced)} shares in rows the feed did not price")
    tot = f" ({'; '.join(noten)})" if noten else ""
    if not m:
        return {"relation": "unknown", "text": hold + tot + " — flagged side not readable"}
    outcome, action = m.group(1), m.group(2)
    buying = action == "BUYS"
    if net == "none":
        # Ohne Preis ist die Zeile weder Buch noch abgerechnet. "Nichts mehr
        # offen" waere hier eine Aussage ueber Zeilen, die niemand lesen
        # konnte, also sagt die Karte genau das.
        if unpriced > 0:
            return {"relation": "unpriced", "text": "no priced position left in this market" + tot
                    + f" — the flagged {outcome} {action.lower()} cannot be related to a book the feed did not price"}
        leer = "no open position left in this market" + tot
        if buying:
            return {"relation": "new_bet", "text": leer + " — the flagged " + outcome + " buys are not held (closed, merged or redeemed since), or the book is empty"}
        return {"relation": "exit", "text": leer + " — the flagged " + outcome + " sells closed it out"}
    if net == "balanced":
        return {"relation": "hedge", "text": hold + tot + " — both sides held in about equal size: a hedge or a merge in progress, not a directional bet"}
    # net is YES or NO
    if buying:
        if outcome == net:
            return {"relation": "adds", "text": hold + tot + f" — net {net}; the flagged {outcome} buys add to that side"}
        return {"relation": "reduces", "text": hold + tot + f" — net {net}; the flagged {outcome} buys work against a {net} book (hedge / closing / merging), not a new {outcome} bet"}
    # selling
    if outcome == net:
        return {"relation": "exit", "text": hold + tot + f" — net {net}; the flagged {outcome} sells reduce that position (taking profit / exiting)"}
    return {"relation": "reduces", "text": hold + tot + f" — net {net}; selling the smaller {outcome} side leaves the {net} book as it is"}


def _fmt(shares: float) -> str:
    if shares >= 10_000:
        return f"{shares / 1000:.1f}k"
    if shares >= 1000:
        return f"{shares / 1000:.2f}k"
    return f"{shares:.0f}"


def wallet_book(wallet: str, market_key: str, flagged_side: str = "") -> dict[str, Any]:
    """One wallet's book in one market, read now, related to the flagged flow."""

    wallet = str(wallet or "").strip().lower()
    short = wallet[:6] + "…" + wallet[-4:] if len(wallet) > 12 else wallet
    try:
        rows = fetch_market_positions(wallet, market_key)
    except md.MarketDataError as exc:
        return {"wallet": wallet, "short": short, "read": False, "error": str(exc)[:200]}
    book = summarize_book(rows)
    relation = relate_flow_to_book(flagged_side, book)
    return {
        "wallet": wallet,
        "short": short,
        "read": True,
        "positions": len(rows),
        **book,
        **relation,
    }


def market_books(market_key: str, wallets: Iterable[str], flagged_side: str = "", max_wallets: int = MAX_WALLETS) -> dict[str, Any]:
    """Books of up to ``max_wallets`` wallets in one market (parallel reads)."""

    from concurrent.futures import ThreadPoolExecutor

    seen: list[str] = []
    for w in wallets or []:
        w = str(w or "").strip().lower()
        if _ADDRESS.match(w) and w not in seen:
            seen.append(w)
    dropped = max(0, len(seen) - int(max_wallets))
    seen = seen[: int(max_wallets)]
    books: list[dict[str, Any]] = []
    if seen:
        with ThreadPoolExecutor(max_workers=min(4, len(seen))) as pool:
            books = list(pool.map(lambda w: wallet_book(w, market_key, flagged_side), seen))
    return {
        "market_key": str(market_key or ""),
        "flagged_side": str(flagged_side or ""),
        "wallets": books,
        "dropped": dropped,
        "note": ("open positions in this market from the public Data API, read now — not at flag time; "
                 "shares of a position that already settled against the wallet and was never redeemed stay in "
                 "that feed at price 0 and are reported as settled_shares, not as a book; rows the feed did "
                 "not price at all are reported as unpriced_shares and count as neither"),
    }
