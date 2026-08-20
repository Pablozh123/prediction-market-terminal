#!/usr/bin/env python3
"""Recompute public/data/kategorie_karte.json from resolved Polymarket markets.

    python scripts/category_efficiency.py
    python scripts/category_efficiency.py --max-per-category 250 --horizons 30,14,7,3,1
    python scripts/category_efficiency.py --offline        # recompute from the cache only
    python scripts/category_efficiency.py --rescore        # re-classify the cached sample, no network

Pages the highest-volume closed Gamma events (with their tags), keeps the
resolved binary markets, reads each market's YES price at fixed horizons
before its decision time from the CLOB price history, and hands everything
to app/category_efficiency.py for scoring. Read-only: public endpoints, no
keys, no order path.

Every network answer is cached under --cache-dir (data/, gitignored):
event pages trimmed to the fields the study needs, one JSON per token for
the price series, and the scored observations. A second run over the same
cache costs no requests, --offline forbids them outright.

Rate limits (docs/research/protokolle_referenz.md): Gamma /events 500 per
10 s, CLOB /prices-history 1,000 per 10 s, both IP-based and throttled
rather than rejected. This script stays two orders of magnitude below both:
a handful of workers, a pause between calls, and never more than two
history calls per market.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import pandas as pd  # noqa: E402

from app import category_efficiency as ce  # noqa: E402
from src import prediction_markets as pm  # noqa: E402

DEFAULT_OUT = REPO_ROOT / "public" / "data" / "kategorie_karte.json"
DEFAULT_CACHE = REPO_ROOT / "data" / "category_efficiency"

# Fields of a nested Gamma market the study reads; the rest (descriptions,
# images, fee schedules) is dropped from the cache to keep a page small.
MARKET_FIELDS = (
    "id", "conditionId", "question", "slug", "outcomes", "outcomePrices", "clobTokenIds", "closed",
    "closedTime", "endDate", "endDateIso", "createdAt", "startDate", "startDateIso", "volumeNum",
    "volume", "category", "umaResolutionStatus", "negRisk", "active",
)
EVENT_FIELDS = ("id", "slug", "title", "category", "endDate", "closedTime", "createdAt", "volume")

HOURLY_WINDOW_DAYS = 15  # the CLOB rejects explicit windows much beyond two weeks


def log(message: str) -> None:
    stamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[{stamp}] {message}", flush=True)


def trim_event(event: dict[str, Any]) -> dict[str, Any]:
    slim = {key: event.get(key) for key in EVENT_FIELDS}
    slim["tags"] = [
        {"label": str(t.get("label", "")), "slug": str(t.get("slug", ""))}
        for t in (event.get("tags") or []) if isinstance(t, dict)
    ]
    slim["markets"] = [
        {key: market.get(key) for key in MARKET_FIELDS}
        for market in (event.get("markets") or []) if isinstance(market, dict)
    ]
    return slim


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def dump_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, default=str), encoding="utf-8")
    tmp.replace(path)


GAMMA_OFFSET_CAP = 2000  # /events answers 422 "offset too large" beyond this; deeper needs /events/keyset


def month_windows(start: datetime, stop: datetime) -> list[tuple[str, str]]:
    """[start, start+1 month) ... up to ``stop`` as ISO strings for end_date_min/max.

    Gamma caps ``offset`` at 2,000 per query, so one sweep ordered by volume
    sees at most the 2,100 biggest closed events. Slicing the end-date range
    into months gives every month its own budget: the top events per month
    rather than the top events overall, which also spreads the sample in
    time instead of piling it on the last big tournament.
    """

    windows: list[tuple[str, str]] = []
    cursor = start.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if cursor < start:
        cursor = start.replace(hour=0, minute=0, second=0, microsecond=0)
    while cursor < stop:
        year, month = cursor.year + (cursor.month // 12), (cursor.month % 12) + 1
        nxt = cursor.replace(year=year, month=month, day=1, hour=0, minute=0, second=0, microsecond=0)
        windows.append((cursor.strftime("%Y-%m-%dT%H:%M:%SZ"), min(nxt, stop).strftime("%Y-%m-%dT%H:%M:%SZ")))
        cursor = nxt
    return windows


def fetch_event_page(cache_dir: Path, offset: int, window: tuple[str, str], offline: bool, pause: float) -> list[dict[str, Any]] | None:
    """One trimmed page of closed events for one end-date window. None = unavailable."""

    end_date_min, end_date_max = window
    path = cache_dir / "events" / f"{end_date_min[:10]}_{offset:06d}.json"
    cached = load_json(path)
    if (isinstance(cached, dict) and cached.get("end_date_min") == end_date_min
            and cached.get("end_date_max") == end_date_max and isinstance(cached.get("events"), list)):
        return cached["events"]
    if offline:
        return None
    try:
        events = pm.get_polymarket_closed_events(limit=100, offset=offset, end_date_min=end_date_min, end_date_max=end_date_max)
    except pm.MarketDataError as exc:
        log(f"  events {end_date_min[:10]} offset {offset}: {exc}")
        return None
    slim = [trim_event(e) for e in events]
    dump_json(path, {"end_date_min": end_date_min, "end_date_max": end_date_max,
                     "fetched_utc": datetime.now(timezone.utc).isoformat(), "events": slim})
    time.sleep(pause)
    return slim


def collect_candidates(args: argparse.Namespace, cache_dir: Path, windows: list[tuple[str, str]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Page every end-date window until its listing ends, then stop when the caps are full."""

    taken: dict[str, int] = {}
    candidates: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    events_seen = 0
    pages = 0
    resolved_seen = 0
    fenster_meta: list[dict[str, Any]] = []
    for window in windows:
        offset = 0
        events_in_window = 0
        vorher = len(candidates)
        while events_seen < args.max_events and offset <= GAMMA_OFFSET_CAP:
            page = fetch_event_page(cache_dir, offset, window, args.offline, args.pause)
            if page is None:
                if offset == 0:
                    log(f"  window {window[0][:10]}: no first page (offline or fetch failed) — skipped")
                break
            if not page:
                break
            pages += 1
            events_seen += len(page)
            events_in_window += len(page)
            for event in page:
                rows = ce.market_rows_from_event(event)
                resolved_seen += len(rows)
                picked = ce.select_markets(
                    rows, args.max_per_category, args.max_per_event, args.min_volume, taken,
                    min_life_days=args.min_life_days, long_life_days=7.0,
                    max_short_per_category=args.max_short_per_category,
                )
                for row in picked:
                    if row["market_key"] in seen_keys:
                        continue
                    seen_keys.add(row["market_key"])
                    candidates.append(row)
                    bucket = ce.sample_bucket(row, 7.0)
                    taken[bucket] = taken.get(bucket, 0) + 1
            offset += len(page)
            if len(page) < 100:
                break
        fenster_meta.append({"von": window[0][:10], "bis": window[1][:10], "events": events_in_window, "kandidaten": len(candidates) - vorher})
        counts = ", ".join(f"{k} {v}" for k, v in sorted(taken.items()))
        log(f"  window {window[0][:10]}: {events_in_window} events, +{len(candidates) - vorher} candidates ({len(candidates)} total, {events_seen} events seen) — {counts}")
        if ce.caps_reached(taken, args.max_per_category):
            log("  every category cap reached")
            break
        if events_seen >= args.max_events:
            log(f"  event budget of {args.max_events} reached")
            break
    meta = {
        "events_gesichtet": events_seen,
        "seiten": pages,
        "fenster": fenster_meta,
        "aufgeloeste_binaere_maerkte_gesehen": resolved_seen,
        "kandidaten": len(candidates),
        "je_bucket": dict(sorted(taken.items())),
    }
    return candidates, meta


def series_to_list(frame: pd.DataFrame) -> list[list[float]]:
    if frame is None or frame.empty:
        return []
    return [[int(pd.Timestamp(t).timestamp()), float(p)] for t, p in zip(frame["time"], frame["price"])]


def list_to_series(rows: Any) -> pd.DataFrame:
    return pm.price_history_frame([{"t": r[0], "p": r[1]} for r in (rows or []) if isinstance(r, (list, tuple)) and len(r) == 2])


class HistoryFetcher:
    """Two CLOB calls per market at most, cached per token, counted for the log."""

    def __init__(self, cache_dir: Path, need_daily: bool, offline: bool, pause: float) -> None:
        self.dir = cache_dir / "history"
        self.need_daily = need_daily
        self.offline = offline
        self.pause = pause
        self.lock = threading.Lock()
        self.stats = {"cached": 0, "fetched": 0, "empty": 0, "unavailable": 0}

    def _count(self, key: str) -> None:
        with self.lock:
            self.stats[key] += 1

    def load(self, row: dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame]:
        token = str(row["yes_token_id"])
        decision = pd.Timestamp(row["decision_time"])
        path = self.dir / f"{token}.json"
        cached = load_json(path)
        if isinstance(cached, dict) and cached.get("decision") == decision.isoformat() and ("daily" in cached or not self.need_daily):
            self._count("cached")
            return list_to_series(cached.get("hourly")), list_to_series(cached.get("daily"))
        if self.offline:
            self._count("unavailable")
            return list_to_series(None), list_to_series(None)
        hourly = pm.get_polymarket_price_history(token, days=HOURLY_WINDOW_DAYS, interval="1h", end_time=decision)
        time.sleep(self.pause)
        daily = pd.DataFrame(columns=["time", "price"])
        if self.need_daily:
            daily = pm.get_polymarket_price_history_lifetime(token, interval="1d")
            time.sleep(self.pause)
        self._count("fetched")
        if hourly.empty and daily.empty:
            self._count("empty")
        dump_json(path, {"decision": decision.isoformat(), "hourly": series_to_list(hourly), "daily": series_to_list(daily)})
        return hourly, daily


def price_candidates(candidates: list[dict[str, Any]], horizons: list[int], fetcher: HistoryFetcher, workers: int) -> list[dict[str, Any]]:
    total = len(candidates)
    done = 0
    observations: list[dict[str, Any]] = []
    started = time.time()

    def work(row: dict[str, Any]) -> dict[str, Any]:
        hourly, daily = fetcher.load(row)
        prices = ce.horizon_prices(hourly, daily, row["decision_time"], horizons)
        return {
            "market_key": row["market_key"],
            "question": row["question"],
            "event_slug": row["event_slug"],
            "category": row["category"],
            "einpreisungstyp": row.get("einpreisungstyp"),
            "vorzeitig": row.get("vorzeitig"),
            "tags": list(row.get("tags") or []),
            "won": bool(row["won"]),
            "volume": float(row["volume"]),
            "decision_time": pd.Timestamp(row["decision_time"]).isoformat(),
            "lifetime_days": ce.lifetime_days(row),
            "prices": {int(k): v for k, v in prices.items()},
        }

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = [pool.submit(work, row) for row in candidates]
        for future in as_completed(futures):
            done += 1
            try:
                observations.append(future.result())
            except Exception as exc:  # noqa: BLE001 - one bad market must not stop the sweep
                log(f"  market failed: {type(exc).__name__}: {exc}")
            if done % 50 == 0 or done == total:
                elapsed = time.time() - started
                rate = done / elapsed if elapsed else 0.0
                eta = (total - done) / rate if rate else 0.0
                priced = sum(1 for o in observations if any(v is not None for v in o["prices"].values()))
                log(f"  priced {done}/{total} ({priced} with at least one horizon) — {fetcher.stats} — eta {eta/60:.1f} min")
    return observations


def build_hinweis(args: argparse.Namespace, summary: dict[str, Any], fetch_stats: dict[str, int], end_date_min: str, horizons: list[int], rescore: bool = False) -> str:
    # A rescore keeps the cached sweep, whose ordering is recorded in
    # quelle.datenfenster — the note must not claim the monthly windows then.
    sweep_wortlaut = "highest-volume closed events" if rescore else "highest-volume closed events per month"
    text = (
        "Brier score, hit rate and calibration of the Polymarket YES price at fixed horizons before "
        f"each market's decision time, per category. Sample: resolved binary markets from the "
        f"{sweep_wortlaut} with an end date from {end_date_min[:10]}, at most {args.max_per_event} "
        f"markets per event and {args.max_per_category} long-lived markets per category "
        f"({summary['n_maerkte']} markets, {summary['n_kategorien']} categories). A market counts at a horizon "
        "only if it had a price then, so n differs by horizon; every figure carries its n. Prices are hourly "
        "for T-14 and nearer and daily for T-30. Each horizon also carries brier_offen over genuinely open "
        "prices (0.05 < p < 0.95) — the comparable figure across categories — and each category a `typen` "
        "split by pricing mechanism (threshold, tally, in-play game, series, scheduled reveal, news). "
        "These horizons measure forecast quality, never pricing-in speed: in-play moves and news reactions "
        "happen between T-1 and the decision and are invisible here — per-category detail in `quelle.messlogik`. "
        "Sample selection and its caveats are in `quelle`; the thesis "
        "figures this replaces are kept under `thesis_snapshot`; the pricing-speed examples (`beispiele`) are unchanged."
    )
    if rescore:
        text += (
            " This file was re-scored from the cached sample: categories and mechanism types were re-derived "
            "from the cached tags and titles; prices, outcomes and the sample itself are unchanged from the "
            "cached sweep (whose caps applied under the previous, coarser taxonomy)."
        )
    horizon_line = ", ".join(f"T-{h}: {summary['n_je_horizont'].get(f'T-{h}', 0)}" for h in horizons)
    text += f" Observations per horizon — {horizon_line}."
    if fetch_stats.get("unavailable"):
        text += (
            f" {fetch_stats['unavailable']} markets had no cached price series and the run was offline, "
            "so they are missing from the sample."
        )
    empties = fetch_stats.get("empty", 0)
    fetched = fetch_stats.get("fetched", 0)
    if fetched and empties / fetched > 0.3:
        text += (
            f" Caution: {empties} of {fetched} fetched price series came back empty, which points at the CLOB "
            "throttling or refusing the history endpoint during this run; the sample is smaller than planned."
        )
    return text


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--horizons", default=",".join(str(h) for h in ce.DEFAULT_HORIZONS),
                        help="Days before the decision time at which to read the YES price (comma-separated)")
    parser.add_argument("--max-per-category", type=int, default=250, help="Long-lived (>=7 d) markets per category")
    parser.add_argument("--max-short-per-category", type=int, default=None,
                        help="Markets that lived under 7 days per category (default: half the main cap)")
    parser.add_argument("--max-per-event", type=int, default=6, help="Markets per event, highest volume first")
    parser.add_argument("--min-volume", type=float, default=1000.0, help="Minimum lifetime volume in USD")
    parser.add_argument("--min-life-days", type=float, default=1.0, help="Skip markets that lived less than this")
    parser.add_argument("--min-markets", type=int, default=30, help="Categories below this fold into Other")
    parser.add_argument("--max-events", type=int, default=30000, help="Stop paging after this many events")
    parser.add_argument("--end-date-min", default=None, help="Earliest event end date (default: 365 days ago)")
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--pause", type=float, default=0.05, help="Seconds between requests per worker")
    parser.add_argument("--cache-dir", default=str(DEFAULT_CACHE))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--offline", action="store_true", help="Cache only, no network")
    parser.add_argument("--rescore", action="store_true",
                        help="Re-classify the cached candidates/observations under the current taxonomy and "
                             "typology and re-score; no network, sample and prices unchanged")
    args = parser.parse_args()

    horizons = sorted({int(h.strip()) for h in str(args.horizons).split(",") if h.strip()}, reverse=True)
    if not horizons:
        parser.error("--horizons needs at least one day count")
    cache_dir = Path(args.cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    end_date_min = args.end_date_min or (now - timedelta(days=365)).strftime("%Y-%m-%dT00:00:00Z")
    out = Path(args.out)
    previous = load_json(out) if out.exists() else None

    if args.rescore:
        # No sweep, no fetch: the cached sample is re-read, categories and
        # mechanism types re-derived from the cached tags/titles, prices kept.
        cands = load_json(cache_dir / "candidates.json")
        obs_raw = load_json(cache_dir / "observations.json")
        if not isinstance(cands, list) or not isinstance(obs_raw, list) or not cands or not obs_raw:
            log("rescore: no cached candidates.json/observations.json — run once without --rescore first")
            return 1
        observations = ce.rescore_observations(cands, obs_raw)
        fetch_stats = {"cached": len(observations), "fetched": 0, "empty": 0, "unavailable": 0}
        vorher = previous.get("quelle") if isinstance(previous, dict) else None
        sweep_meta = dict((vorher or {}).get("datenfenster") or {}) if isinstance(vorher, dict) else {}
        if sweep_meta.get("end_date_min"):
            end_date_min = str(sweep_meta["end_date_min"])
        sweep_meta["modus"] = (
            "rescore: Kategorien und Einpreisungstypen neu aus dem Cache bewertet; Stichprobe, Preise und "
            "Outcomes unveraendert (die Kategorie-Caps des Sweeps galten unter der frueheren, groeberen Taxonomie)"
        )
        log(f"category efficiency — rescore of {len(observations)} cached observations, no network")
    else:
        log(f"category efficiency — horizons {horizons}, cap {args.max_per_category}/category, "
            f"{args.max_per_event}/event, min volume ${args.min_volume:,.0f}, events since {end_date_min[:10]}"
            f"{' (offline)' if args.offline else ''}")
        # Placeholder end dates ("by end of 2026") sit far past today even for
        # markets that resolved months ago, so the windows run a year ahead.
        start = datetime.strptime(end_date_min, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        windows = month_windows(start, now + timedelta(days=400))
        log(f"sweeping closed events in {len(windows)} monthly end-date windows")
        candidates, sweep_meta = collect_candidates(args, cache_dir, windows)
        if not candidates:
            log("no candidates — nothing written")
            return 1
        dump_json(cache_dir / "candidates.json", candidates)

        log(f"reading price series for {len(candidates)} markets ({args.workers} workers)")
        fetcher = HistoryFetcher(cache_dir, need_daily=max(horizons) > HOURLY_WINDOW_DAYS - 1, offline=args.offline, pause=args.pause)
        observations = price_candidates(candidates, horizons, fetcher, args.workers)
        dump_json(cache_dir / "observations.json", observations)
        fetch_stats = fetcher.stats
        log(f"price series: {fetch_stats}")

    kategorien = ce.category_table(observations, horizons, min_markets=args.min_markets)
    summary = ce.sample_summary(kategorien)
    for k in kategorien:
        line = ", ".join(f"T-{h['horizont_tage']} n={h['n']} brier={h['brier']}" for h in k["horizonte"])
        log(f"  {k['kategorie']}: {k['n_maerkte']} markets — {line}")
    log(f"total: {summary}")

    quelle = {
        "methode": (
            "YES price at T-N days before the decision time (min of closedTime and endDate) versus the "
            "settled outcome from outcomePrices; Brier = mean (p - y)^2, hit = (p >= 0.5) == y, both per "
            "category and horizon with n; calibration bins of the T-7 price against the realised share won. "
            "brier_offen/trefferquote_offen restrict each horizon to genuinely open prices (0.05 < p < 0.95): "
            "the cross-category comparison belongs there, because a bucket full of near-settled prices scores "
            "an excellent Brier without anyone having forecast anything."
        ),
        "typologie": (
            "einpreisungstyp per market, heuristic from title/tags/lifetime: schwelle (price tracks an "
            "observable underlying against a level — an option delta, not judgement), zaehler (public running "
            "tally, converges mechanically), spielverlauf (single fixture, outcome forms live in play), serie "
            "(season/tournament future, repriced stepwise after each scheduled sub-event), stichtag (answer "
            "appears at a known moment: election night, data print, award), nachrichten (undated events decide). "
            "The per-category `typen` split shows which mix produced each category's figures."
        ),
        "kategorisierung": (
            "Gamma event tags in a fixed priority (Sports, Crypto, Mentions, Tweets/Social, Elections, "
            "Geopolitics, Politics, Pop culture, Business/Finance, Science/Tech, Weather), mentions and "
            "tweet-count markets by title pattern first, election tags by word match on the label, then the "
            "live title/tag classifier market_filter_category, else Other. Elections, Geopolitics and "
            "Tweets/Social were split out 2026-08: each prices by a different mechanism (scheduled count "
            "night, unscheduled news, public tally) and the sample carried enough of each."
        ),
        "datenfenster": {
            "abgerufen_utc": now.isoformat(timespec="seconds"),
            "end_date_min": end_date_min,
            "reihenfolge": "Gamma /events closed=true, one monthly end-date window at a time, each ordered by lifetime volume descending (Gamma caps a listing at 2,100 events)",
            **sweep_meta,
        },
        "auswahl": {
            "max_per_event": args.max_per_event,
            "max_per_category_long_lived": args.max_per_category,
            "max_per_category_short_lived": args.max_short_per_category if args.max_short_per_category is not None else max(1, args.max_per_category // 2),
            "min_volume_usd": args.min_volume,
            "min_life_days": args.min_life_days,
            "min_markets_per_category": args.min_markets,
        },
        "preise": {
            "hourly": f"CLOB /prices-history, {HOURLY_WINDOW_DAYS}-day window ending at the decision time, fidelity 60 min",
            "daily": "CLOB /prices-history interval=max, fidelity 1440 min (whole life), fallback and T-30",
            "abrufe": fetch_stats,
        },
        "raten": "Gamma /events 500 per 10 s, CLOB /prices-history 1,000 per 10 s (IP-based, throttled); this run stays far below both",
        "stichprobe": summary,
        "messlogik": ce.MESSLOGIK,
        "einschraenkungen": [
            "Highest-volume events of each month first, so the sample over-represents liquid markets; per-event cap of "
            f"{args.max_per_event} favours each event's most-traded lines.",
            "n differs by horizon: a market only counts where it had a price, and short-lived markets never reach T-7.",
            "Decision time is min(closedTime, endDate); a market that kept trading past its nominal end date is read at that end date.",
            "Markets that resolved early anchor at closedTime, which lags the real deciding event by hours to days — "
            "short horizons there can read prices that already knew the answer. anteil_entschieden and anteil_vorzeitig "
            "make the share visible; they do not repair it.",
            "The fixed horizons measure forecast quality, never pricing-in speed: in-play moves (a goal, a data print, "
            "an announcement) happen between T-1 and the decision and are invisible here. quelle.messlogik states per "
            "category what a proper event-anchored latency study would need.",
            "The headline Brier mixes open and effectively settled markets; brier_offen is the comparable figure.",
            "einpreisungstyp is a title/tag heuristic, not a human label; the `typen` split is context, not a finding.",
            "Weather is empty because the volume-first sweep never reaches the small daily markets — a sampling gap, "
            "not a statement about the category.",
            "Category is the event's tag, not a human label; ambiguous events follow the fixed tag priority.",
            "Descriptive of the past sample; not a forecast of any category's future pricing.",
        ],
    }
    payload = ce.compose_payload(
        kategorien, previous,
        stand_utc=now.isoformat(timespec="seconds"),
        horizons=horizons,
        quelle=quelle,
        hinweis=build_hinweis(args, summary, fetch_stats, end_date_min, horizons, rescore=args.rescore),
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    log(f"wrote {out} ({summary['n_maerkte']} markets, {summary['n_kategorien']} categories)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
