"""Which reward markets are worth quoting, and why it is a selection problem.

The MM study measured what a quoting engine earns and loses. It left one
income stream at its most conservative setting: liquidity rewards were priced
at the median pool of 3 USD per market per day, with no market selection at
all. That understates the stream badly, because the pool distribution is
extremely right skewed - median 3, mean 14.55, largest 1000 - and because a
maker chooses which markets to stand in.

So the question this module answers is not "how much do rewards pay" but
"where". The reward score is quadratic in closeness to the mid and normalised
against every other maker in the same market, so what matters is not the pool
alone but the pool relative to the competition already standing inside the
qualifying spread. A large pool in a crowded book is worth less than a modest
pool in an empty one.

Competition cannot be observed directly: the venue publishes neither maker
scores nor their identities. What is observable is the resting depth inside
the qualifying spread, which is the same thing the scoring rule weights by, so
it is used as the proxy and named as one. Everything downstream is reported as
a ranking rather than an expected payout, because a payout number would imply
a precision this data does not support.

Read-only research tooling: public endpoints, no order path, no credentials.

Usage:
  python -m src.reward_selection --tag 2026-07-31
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import requests

from app import liquidity_rewards as lr

REPO_ROOT = Path(__file__).resolve().parents[1]
RESEARCH_DIR = REPO_ROOT / "docs" / "research"

SAMPLING_URL = "https://clob.polymarket.com/sampling-markets"
BOOK_URL = "https://clob.polymarket.com/book"
HEADERS = {"User-Agent": "prediction-market-terminal research/1.0 (read-only)"}

#: Wie viele der groessten Pools gegen ihr Buch geprueft werden. Die Tiefe
#: kostet einen Abruf je Markt, deshalb nicht das ganze Universum.
DEFAULT_PROBE = 60
#: Unter dieser Quote-Groesse zaehlt eine Order im Programm gar nicht mit.
DEFAULT_QUOTE_SHARES = 100.0

# Validierte Referenzpalette (dataviz-Skill), Light-Mode
COLOR_POS = "#1baf7a"
COLOR_NEUTRAL = "#2a78d6"
COLOR_SURFACE = "#fcfcfb"
COLOR_TEXT = "#0b0b0b"
COLOR_TEXT_2 = "#52514e"
COLOR_GRID = "#e5e4e0"


def _get(url: str, params: dict | None = None, timeout: int = 30):
    resp = requests.get(url, params=params or {}, headers=HEADERS, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def _num(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def reward_config(market: dict) -> dict | None:
    """Pool, qualifying spread and minimum size for one market, or None."""
    rewards = market.get("rewards") or {}
    pool = 0.0
    for rate in rewards.get("rates") or []:
        pool += _num(rate.get("rewards_daily_rate"))
    if pool <= 0:
        return None
    tokens = [str(t.get("token_id") or "") for t in market.get("tokens") or []]
    return {
        "condition_id": str(market.get("condition_id") or ""),
        "question": str(market.get("question") or "")[:120],
        "pool_usd_per_day": round(pool, 4),
        "max_spread_cents": _num(rewards.get("max_spread")) or lr.MAX_SPREAD_CENTS_MODE,
        "min_size_shares": _num(rewards.get("min_size")) or lr.MIN_SIZE_SHARES_MODE,
        "token_ids": [t for t in tokens if t],
    }


def fetch_reward_markets(get_json=_get, max_pages: int = 40) -> list[dict]:
    """Every market that currently carries a reward pool."""
    out: list[dict] = []
    cursor = ""
    for _ in range(max_pages):
        params = {"next_cursor": cursor} if cursor else {}
        payload = get_json(SAMPLING_URL, params)
        batch = payload.get("data") or []
        for market in batch:
            config = reward_config(market)
            if config is not None:
                out.append(config)
        cursor = payload.get("next_cursor") or ""
        if not batch or cursor in ("", "LTE="):
            break
    return out


def qualifying_depth(bids: list, asks: list, mid: float,
                     max_spread_cents: float,
                     min_size_shares: float) -> tuple[float, float]:
    """(shares, orders) already resting inside the qualifying spread.

    This is the competition proxy. The scoring rule weights each order by size
    and by closeness to the mid, so the shares standing inside the band are the
    observable part of what our own score would be measured against.
    """
    shares = 0.0
    orders = 0
    for levels in (bids, asks):
        for level in levels or []:
            try:
                price = float(level.get("price") if isinstance(level, dict) else level[0])
                size = float(level.get("size") if isinstance(level, dict) else level[1])
            except (TypeError, ValueError, KeyError, IndexError):
                continue
            if size < min_size_shares:
                continue
            distance = abs(price - mid) * 100.0
            if distance < max_spread_cents:
                shares += size
                orders += 1
    return round(shares, 2), orders


def book_snapshot(token_id: str, get_json=_get) -> dict | None:
    """Top of book plus the depth inside the band, or None when unusable."""
    try:
        payload = get_json(BOOK_URL, {"token_id": token_id})
    except Exception:  # noqa: BLE001 - ein kaputtes Buch stoppt den Lauf nicht
        return None
    bids = payload.get("bids") or []
    asks = payload.get("asks") or []
    if not bids or not asks:
        return None
    try:
        best_bid = max(float(b["price"]) for b in bids)
        best_ask = min(float(a["price"]) for a in asks)
    except (TypeError, ValueError, KeyError):
        return None
    if not 0 < best_bid < best_ask < 1:
        return None
    return {"bids": bids, "asks": asks, "best_bid": best_bid,
            "best_ask": best_ask, "mid": (best_bid + best_ask) / 2.0}


def score_market(config: dict, book: dict,
                 quote_shares: float = DEFAULT_QUOTE_SHARES) -> dict:
    """Rank one market by pool against the competition already standing there.

    ``pool_per_competing_share`` is the ranking number: how many reward dollars
    per day are on offer for each share already inside the band. It is a
    ranking, not a payout - our realised share depends on scores we cannot see.
    """
    competing_shares, competing_orders = qualifying_depth(
        book["bids"], book["asks"], book["mid"],
        config["max_spread_cents"], config["min_size_shares"])
    # Eigener Score, wenn wir mittig und knapp innerhalb der Spanne stehen.
    own = lr.quote_score(
        bid_spread_cents=config["max_spread_cents"] / 4.0,
        ask_spread_cents=config["max_spread_cents"] / 4.0,
        size_shares=quote_shares, midpoint=book["mid"],
        max_spread_cents=config["max_spread_cents"],
        min_size_shares=config["min_size_shares"])
    denominator = competing_shares if competing_shares > 0 else quote_shares
    return {
        **{k: v for k, v in config.items() if k != "token_ids"},
        "mid": round(book["mid"], 4),
        "spread_cents": round((book["best_ask"] - book["best_bid"]) * 100.0, 3),
        "competing_shares": competing_shares,
        "competing_orders": competing_orders,
        "own_score": round(own, 4),
        "pool_per_competing_share": round(
            config["pool_usd_per_day"] / max(1.0, denominator), 6),
        "empty_band": competing_orders == 0,
    }


def run_study(probe: int = DEFAULT_PROBE, quote_shares: float = DEFAULT_QUOTE_SHARES,
              get_json=_get) -> dict:
    """Rank the largest reward pools by how crowded their qualifying band is."""
    configs = fetch_reward_markets(get_json=get_json)
    pools = sorted((c["pool_usd_per_day"] for c in configs), reverse=True)
    ranked = sorted(configs, key=lambda c: c["pool_usd_per_day"], reverse=True)
    rows: list[dict] = []
    for config in ranked[:max(0, probe)]:
        token = (config.get("token_ids") or [None])[0]
        if not token:
            continue
        book = book_snapshot(token, get_json=get_json)
        if book is None:
            continue
        rows.append(score_market(config, book, quote_shares))
    rows.sort(key=lambda r: r["pool_per_competing_share"], reverse=True)
    total = sum(pools)
    return {
        "markets_with_pool": len(configs),
        "total_pool_usd_per_day": round(total, 2),
        "median_pool_usd": pools[len(pools) // 2] if pools else 0.0,
        "max_pool_usd": pools[0] if pools else 0.0,
        "top_100_share": round(sum(pools[:100]) / total, 4) if total else None,
        "probed": len(rows),
        "empty_band_markets": sum(1 for r in rows if r["empty_band"]),
        "quote_shares": quote_shares,
        "snapshot_date": lr.REWARD_SNAPSHOT_DATE,
        "rows": rows,
    }


def _fmt(value, spec="{:.2f}") -> str:
    return "-" if value is None else spec.format(value)


def _markdown(results: dict, tag: str) -> str:
    lines = [
        f"# Reward market selection ({tag})",
        "",
        f"{results['markets_with_pool']:,} markets carry a pool, "
        f"{results['total_pool_usd_per_day']:,.0f} USD per day in total. Median "
        f"{_fmt(results['median_pool_usd'])}, largest "
        f"{_fmt(results['max_pool_usd'])}. The top 100 hold "
        f"{_fmt(results['top_100_share'], '{:.1%}')} of the pot.",
        "",
        f"The {results['probed']} largest pools were probed against their "
        f"current book, quote size {results['quote_shares']:.0f} shares. "
        f"Of those, with a completely empty qualifying band: "
        f"{results['empty_band_markets']}.",
        "",
        "| Market | Pool/day | Band (c) | Spread (c) | Competition (shares) | "
        "Orders | Pool per competing share |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in results["rows"][:25]:
        lines.append(
            f"| {row['question'][:44]} | {_fmt(row['pool_usd_per_day'])} | "
            f"{_fmt(row['max_spread_cents'], '{:.1f}')} | "
            f"{_fmt(row['spread_cents'], '{:.2f}')} | "
            f"{_fmt(row['competing_shares'], '{:,.0f}')} | "
            f"{row['competing_orders']} | "
            f"{_fmt(row['pool_per_competing_share'], '{:.5f}')} |")
    lines += [
        "",
        "## How to read this",
        "",
        "The last column is the ranking number: how many reward dollars per "
        "day fall on each share already standing inside the qualifying band. "
        "It is a ranking, not a payout. Your own share depends on the scores "
        "of every other maker in the same market, and the exchange does not "
        "publish those.",
        "",
        "Competition is measured through resting depth inside the band. That "
        "is a proxy, but not an arbitrary one: the scoring rule weights every "
        "order by size and closeness to the mid, so exactly that depth is the "
        "observable part of what your own score is normalised against.",
        "",
        "A large pool in a crowded book is worth less than a medium one in an "
        "empty book. That is why the ranking here is by ratio rather than by "
        "pool size - sorting by pool alone would be precisely the mistake this "
        "analysis exists to expose.",
        "",
        "**An empty band is not an invitation, it is a warning.** In the run "
        "of 2026-07-31 the markets with the largest pools and zero competition "
        "are esports markets throughout, whose actual spread runs 4 to 64 "
        "cents while the qualifying band is 2.5 cents. Nobody stands there "
        "because nobody wants to stand there. Whoever collects the premium "
        "quotes many times tighter than the whole market and is thereby the "
        "cheapest target in the book for anyone informed. With the large pot "
        "the exchange is buying exactly the liquidity that does not otherwise "
        "exist, and the price of that is adverse selection. What it costs is "
        "measured by mm_pnl, not by this analysis - and there, at a two-minute "
        "requote interval, it ran two to five times the spread earned.",
        "",
        "Limits: a snapshot, not a history. Anyone standing in a market "
        "permanently changes the competition they measured. Depth comes from a "
        "single fetch per market, and a volatile book can look different "
        "seconds later. And rewards are only one revenue line: what stands "
        "against them in adverse selection is measured by the MM study, not by "
        "this one.",
        "",
        "Read-only research. Not trading advice.",
    ]
    return "\n".join(lines)


def write_outputs(results: dict, tag: str,
                  research_dir: Path = RESEARCH_DIR) -> dict[str, Path]:
    research_dir.mkdir(parents=True, exist_ok=True)
    json_path = research_dir / f"reward_selection_{tag}.json"
    json_path.write_text(json.dumps(results, indent=2), encoding="utf-8")

    csv_path = research_dir / f"reward_selection_{tag}.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["question", "pool_usd_per_day", "max_spread_cents",
                         "spread_cents", "competing_shares", "competing_orders",
                         "pool_per_competing_share", "empty_band"])
        for row in results["rows"]:
            writer.writerow([row["question"], row["pool_usd_per_day"],
                             row["max_spread_cents"], row["spread_cents"],
                             row["competing_shares"], row["competing_orders"],
                             row["pool_per_competing_share"], row["empty_band"]])

    md_path = research_dir / f"reward_selection_{tag}.md"
    md_path.write_text(_markdown(results, tag), encoding="utf-8")
    return {"json": json_path, "csv": csv_path, "md": md_path}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tag", required=True)
    parser.add_argument("--probe", type=int, default=DEFAULT_PROBE)
    parser.add_argument("--quote-shares", type=float, default=DEFAULT_QUOTE_SHARES)
    args = parser.parse_args(argv)

    results = run_study(probe=args.probe, quote_shares=args.quote_shares)
    paths = write_outputs(results, args.tag)
    print({k: v for k, v in results.items() if k != "rows"})
    print({key: str(path) for key, path in paths.items()})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
