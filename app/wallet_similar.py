"""Wallets that hold the same markets — the "Similar wallets" tab.

What can be known from public data: for each of the wallet's largest open
markets the Data API lists the top holders of every outcome token
(``/holders?market=<conditionId>``, about twenty per token). Counting which
addresses recur across those lists gives an overlap — "of your N biggest
open markets, this wallet sits among the top holders in k". Same side or
the opposite side is known too, from the outcome index. That is the whole
basis; it is not "all wallets that ever traded these markets" (the API does
not offer that) and it says so in ``basis``.

For the top overlapping wallets one more public read each: their open
positions (count and value now) and, when the wallet is on the cached
leaderboard, its PnL and volume. Streamlit-free; ``api/server.py`` serves
it as ``GET /api/wallet/{wallet}/similar``.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping
from typing import Any

import pandas as pd

from src import prediction_markets as md

_ADDRESS = re.compile(r"^0x[a-fA-F0-9]{40}$")
_CONDITION = re.compile(r"^0x[a-fA-F0-9]{64}$")

#: How many of the wallet's open markets are checked (largest by value first)
#: and how many holders per outcome token the API is asked for.
DEFAULT_MAX_MARKETS = 12
DEFAULT_HOLDERS_PER_TOKEN = 20
DEFAULT_TOP = 10


def _num(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    return out if out == out else default


def _outcome_index(outcome: Any) -> int | None:
    text = str(outcome or "").strip().upper()
    if text in {"YES", "Y"}:
        return 0
    if text in {"NO", "N"}:
        return 1
    return None


def fetch_market_holders(market_key: str, limit: int = DEFAULT_HOLDERS_PER_TOKEN) -> list[dict[str, Any]]:
    """Top holders per outcome token of one market: [{token, holders:[…]}]."""

    market_key = str(market_key or "").strip()
    if not _CONDITION.match(market_key):
        return []
    data = md._get_json(f"{md.POLY_DATA}/holders", params={"market": market_key, "limit": int(limit)})
    return [dict(t) for t in (data if isinstance(data, list) else []) if isinstance(t, Mapping)]


def fetch_open_summary(wallet: str, limit: int = 500) -> dict[str, Any]:
    """Count and value of a wallet's open positions now (one Data API read).

    ``/positions`` keeps a position that resolved against the wallet until
    someone redeems it (price 0, value 0). Those rows are settled, not open;
    counting them inflates "positions" for exactly the wallets that never
    clean up. They are reported as ``settled`` instead — the value column
    already reads 0 for them, so only the count was ever wrong.
    """

    frame = md.get_polymarket_positions(wallet, limit=limit)
    if frame is None or frame.empty:
        return {"positions": 0, "value": 0.0, "settled": 0, "unpriced": 0, "read": True}
    # Dieselbe Regel wie ueberall sonst (src/prediction_markets.py). Das
    # frueher hier stehende ``fillna(0.0)`` zaehlte jede Zeile, die der Feed
    # nicht bepreist hat, als abgerechnet — dieselbe Verwechslung von
    # fehlender Zahl und gemessener Null.
    tot = md.worthless_position_mask(frame)
    ohne_preis = md.unknown_price_mask(frame)
    offen = frame[~(tot | ohne_preis)]
    return {
        "positions": int(len(offen)),
        "value": round(float(pd.to_numeric(offen["value"], errors="coerce").fillna(0.0).sum()), 2)
        if "value" in offen else 0.0,
        "settled": int(tot.sum()),
        # Weder offen noch abgerechnet: der Feed hat nichts geliefert.
        "unpriced": int(ohne_preis.sum()),
        "read": True,
    }


def tally_overlaps(
    wallet: str,
    markets: Iterable[Mapping[str, Any]],
    holders_by_market: Mapping[str, list[Mapping[str, Any]]],
) -> list[dict[str, Any]]:
    """Per other wallet: in how many of ``markets`` it is a top holder, and on
    which side relative to ours. ``markets`` rows carry market_key, title,
    outcome (ours); ``holders_by_market`` the raw /holders answer per key."""

    me = str(wallet or "").strip().lower()
    tally: dict[str, dict[str, Any]] = {}
    for m in markets:
        key = str(m.get("market_key") or "")
        mine = _outcome_index(m.get("outcome"))
        seen_here: set[str] = set()
        for token in holders_by_market.get(key, []) or []:
            for h in token.get("holders", []) or []:
                addr = str(h.get("proxyWallet") or "").strip().lower()
                if not _ADDRESS.match(addr) or addr == me or _num(h.get("amount")) <= 0:
                    continue
                entry = tally.setdefault(addr, {
                    "wallet": addr, "name": "", "shared": 0, "same_side": 0, "opposite_side": 0, "unknown_side": 0, "markets": [],
                })
                if not entry["name"]:
                    # The feed puts the address itself in ``name`` when the
                    # holder has none; that is not a name.
                    cand = str(h.get("name") or h.get("pseudonym") or "").strip()
                    entry["name"] = "" if re.match(r"^0[xX][a-fA-F0-9]{40}$", cand) else cand
                if addr in seen_here:
                    # Holds both tokens of this market: count the market once,
                    # but as both-sided.
                    continue
                seen_here.add(addr)
                entry["shared"] += 1
                idx = h.get("outcomeIndex")
                try:
                    idx = int(idx)
                except (TypeError, ValueError):
                    idx = None
                if mine is None or idx is None:
                    entry["unknown_side"] += 1
                    side = "unknown"
                elif idx == mine:
                    entry["same_side"] += 1
                    side = "same"
                else:
                    entry["opposite_side"] += 1
                    side = "opposite"
                entry["markets"].append({"market_key": key, "title": str(m.get("title") or ""), "side": side})
    rows = sorted(tally.values(), key=lambda r: (-r["shared"], -r["same_side"], r["wallet"]))
    return rows


def similar_wallets(
    wallet: str,
    open_rows: Iterable[Mapping[str, Any]],
    *,
    max_markets: int = DEFAULT_MAX_MARKETS,
    holders_per_token: int = DEFAULT_HOLDERS_PER_TOKEN,
    top: int = DEFAULT_TOP,
    leaderboard: Mapping[str, Mapping[str, Any]] | None = None,
    holders_fetcher: Callable[[str, int], list[dict[str, Any]]] | None = None,
    summary_fetcher: Callable[[str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """The tab's payload. ``open_rows`` are the wallet page's open positions
    (largest value first); ``leaderboard`` maps lowercase wallet -> row with
    pnl / volume / name when known."""

    wallet = str(wallet or "").strip().lower()
    holders_fetcher = holders_fetcher or fetch_market_holders
    summary_fetcher = summary_fetcher or fetch_open_summary
    rows = [r for r in open_rows if _CONDITION.match(str(r.get("market_key") or ""))]
    rows.sort(key=lambda r: -_num(r.get("value")))
    checked = rows[: max(0, int(max_markets))]
    holders_by_market: dict[str, list[dict[str, Any]]] = {}
    errors: list[str] = []
    for m in checked:
        key = str(m.get("market_key"))
        try:
            holders_by_market[key] = holders_fetcher(key, int(holders_per_token))
        except md.MarketDataError as exc:
            errors.append(f"{key[:10]}…: {str(exc)[:80]}")
            holders_by_market[key] = []
    tally = tally_overlaps(wallet, checked, holders_by_market)
    n_checked = len(checked)
    # Nenner der Ueberschneidung sind die Maerkte, deren Holder-Liste wirklich
    # gelesen wurde. Ein fehlgeschlagener Abruf kann keinen Treffer liefern;
    # ihn trotzdem mitzuzaehlen drueckt jede Quote um die Fehlerrate. Bei sechs
    # von zwoelf gescheiterten Abrufen zeigte ein Wallet, das in allen sechs
    # lesbaren Maerkten sass, 50 Prozent statt 100.
    n_read = sum(1 for m in checked if holders_by_market.get(str(m.get("market_key"))))
    # Basisrate der Aehnlichkeit: wie viele Maerkte ein Kandidat ueblicherweise
    # teilt. Ohne sie liest sich jede Zeile als Fund, obwohl die Holder-Listen
    # nach Groesse sortiert sind und dieselben grossen Wallets ueberall stehen.
    geteilt_alle = sorted((int(e["shared"]) for e in tally), reverse=True)
    median_geteilt = (
        float(geteilt_alle[len(geteilt_alle) // 2]) if geteilt_alle else 0.0
    )
    out_rows: list[dict[str, Any]] = []
    for entry in tally[: max(0, int(top))]:
        addr = entry["wallet"]
        try:
            summary = summary_fetcher(addr)
        except md.MarketDataError as exc:
            summary = {"positions": None, "value": None, "read": False, "error": str(exc)[:80]}
        lb = (leaderboard or {}).get(addr) if leaderboard else None
        out_rows.append({
            "wallet": addr,
            "short": addr[:6] + "…" + addr[-4:],
            "name": entry["name"] or (str(lb.get("name") or lb.get("pseudonym") or "") if lb else ""),
            "shared": entry["shared"],
            "same_side": entry["same_side"],
            "opposite_side": entry["opposite_side"],
            "overlap": round(entry["shared"] / n_read, 4) if n_read else 0.0,
            # Wie weit ueber dem ueblichen Kandidaten diese Zeile liegt.
            "shared_vs_median": round(entry["shared"] / median_geteilt, 2) if median_geteilt > 0 else None,
            "markets": entry["markets"],
            "their_positions": summary.get("positions"),
            "their_value": summary.get("value"),
            "their_settled": summary.get("settled"),
            "summary_read": bool(summary.get("read")),
            "lb_pnl": _num(lb.get("pnl")) if lb and lb.get("pnl") is not None else None,
            "lb_volume": _num(lb.get("volume", lb.get("vol"))) if lb and (lb.get("volume") is not None or lb.get("vol") is not None) else None,
            "on_leaderboard": bool(lb),
            "profile_url": md.polymarket_profile_url(addr),
        })
    return {
        "wallet": wallet,
        "rows": out_rows,
        "candidates": len(tally),
        "basis": {
            "markets_checked": n_checked,
            # Der Nenner, gegen den die Quote gerechnet ist.
            "markets_read": n_read,
            "markets_available": len(rows),
            "holders_per_token": int(holders_per_token),
            "top": int(top),
            "median_shared": median_geteilt,
            "note": (f"overlap among the top {holders_per_token} holders per outcome of this wallet's {n_checked} largest open markets, "
                     f"counted against the {n_read} whose holder list was actually read (public /holders feed) — not every wallet that ever "
                     "traded them; a wallet holding both sides counts once, as both-sided. That feed ranks holders by size, so the same large "
                     f"wallets recur across markets: the median candidate here shares {median_geteilt:g}, which is the rate to read a row "
                     "against. PnL and volume only where the wallet is on the cached leaderboard; win rates are not read for other wallets."),
            "errors": errors,
        },
    }
