"""Documented public cases of suspicious prediction-market flow, replayed through the screen.

The insider screen scores nine flow features plus the measured first trade
with hand-set caps, and ``score_validation()`` says plainly that no hit rate
exists for it. What CAN exist without a labelled outcome set is a list of
cases that the public record describes in enough detail to rebuild their
shape: the tracker posts of 2026 (one fresh wallet, one big print), the AP
analysis of the April ceasefire wallets, the ACDC "Orca" definition, and the
prints this repository's own trade store holds. ``data/insider_cases.yaml``
is that list, versioned like the claims register, with a source per case.

This module rebuilds each case as a small synthetic tape (the case prints
inside a window of ordinary background prints, the way the live screen sees
a market) and runs the exact production ladder, ``suspicion.screen_tape``,
over it. ``tests/test_insider_cases.py`` asserts each case's expectation, so
a change to the weights that would lose one of the documented patterns
turns red in CI. That makes the list a regression suite for the patterns.
It is not a hit rate: it says nothing about all the flow the screen flags
besides these cases, and the cases themselves are tracker posts and press
reports, not established findings.

Streamlit-free, network-free.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from app import risk_log
from app import suspicion as susp

ROOT = Path(__file__).resolve().parents[1]
CASES_PATH = ROOT / "data" / "insider_cases.yaml"

#: What a case may expect of the screen. ``flag``: the market's card clears
#: the flag floor. ``no_flag``: it stays below (a control). ``excluded``: the
#: context filter drops the market before scoring. ``open``: replayed and
#: reported, asserted nothing (the case is documented but the screen has no
#: stated position on it yet).
EXPECTATIONS = ("flag", "no_flag", "excluded", "open")
SOURCE_KINDS = ("tracker_post", "press", "research", "court", "store")
REQUIRED_FIELDS = ("id", "source", "source_kind", "date", "category", "market", "side", "price",
                   "notional", "wallets", "expectation")

#: The live screen's window, as measured on 2026-09-05: 1000 prints at or
#: above the tape floor covered about half an hour. The background prints of
#: a replay fill the same span so window-relative features (burst, timing
#: clusters, the sample-relative fresh proxy) see what they see live.
WINDOW_MINUTES = 34.0
BACKGROUND_PRINTS = 60
DEFAULT_WHALE_THRESHOLD = 2500.0


def load_cases(path: Path | str = CASES_PATH) -> list[dict[str, Any]]:
    """The case list, as dicts, in file order. Missing file: empty list."""

    target = Path(path)
    if not target.exists():
        return []
    with target.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    cases = data.get("cases") if isinstance(data, dict) else None
    return [dict(case) for case in (cases or []) if isinstance(case, dict)]


def validate_case(case: dict[str, Any]) -> list[str]:
    """Problems with one case, as sentences; empty when the case is usable."""

    problems: list[str] = []
    for field in REQUIRED_FIELDS:
        if case.get(field) in (None, ""):
            problems.append(f"missing {field}")
    if case.get("expectation") not in EXPECTATIONS:
        problems.append(f"expectation must be one of {EXPECTATIONS}")
    if case.get("source_kind") not in SOURCE_KINDS:
        problems.append(f"source_kind must be one of {SOURCE_KINDS}")
    try:
        price = float(case.get("price"))
        if not 0.0 < price < 1.0:
            problems.append("price must lie in (0, 1)")
    except (TypeError, ValueError):
        problems.append("price must be a number")
    try:
        if float(case.get("notional")) <= 0:
            problems.append("notional must be positive dollars")
    except (TypeError, ValueError):
        problems.append("notional must be a number")
    try:
        if int(case.get("wallets")) < 1:
            problems.append("wallets must be at least 1")
    except (TypeError, ValueError):
        problems.append("wallets must be an integer")
    if case_side(case) not in ("YES", "NO"):
        problems.append("side must be YES or NO")
    if not str(case.get("source") or "").startswith("http") and case.get("source_kind") != "store":
        problems.append("source must be a URL unless the case comes from the store")
    return problems


def case_side(case: dict[str, Any]) -> str:
    """The bought outcome as YES or NO. A bare ``YES``/``NO`` in YAML 1.1 is a
    boolean, so both spellings are accepted; anything else comes back as is."""

    raw = case.get("side")
    if isinstance(raw, bool):
        return "YES" if raw else "NO"
    return str(raw or "").strip().upper()


def _market_key(case_id: str) -> str:
    return "0x" + hashlib.sha1(str(case_id).encode("utf-8")).hexdigest()[:40]


def _print(t: pd.Timestamp, wallet: str, title: str, price: float, notional: float, *, outcome: str,
           side: str = "BUY", key: str, end: Any) -> dict[str, Any]:
    return {
        "platform": "Polymarket", "time": t, "trader": wallet[:8], "wallet": wallet, "side": side,
        "outcome": outcome, "title": title, "price": float(price), "size": float(notional) / float(price),
        "notional": float(notional), "market_key": key, "asset": "", "transaction_hash": "",
        "slug": "", "url": "", "end_time": end,
    }


def background_tape(now: pd.Timestamp, *, minutes: float = WINDOW_MINUTES, n: int = BACKGROUND_PRINTS,
                    seed: int = 1) -> list[dict[str, Any]]:
    """Ordinary whale-floor prints in neutral markets: what the screen sees
    around any case. Deterministic for a seed, no origins (unmeasured)."""

    rng = np.random.default_rng(seed)
    start = now - pd.Timedelta(minutes=float(minutes))
    titles = [f"Will item {i} be announced this month?" for i in range(40)]
    rows: list[dict[str, Any]] = []
    for _ in range(int(n)):
        t = start + pd.Timedelta(seconds=float(rng.uniform(0.0, float(minutes) * 60.0)))
        wallet = f"0xbg{int(rng.integers(0, 45)):03d}"
        title = titles[int(rng.integers(0, len(titles)))]
        price = round(float(rng.uniform(0.05, 0.95)), 2)
        notional = float(rng.choice([600.0, 900.0, 1500.0, 2500.0, 4000.0, 8000.0], p=[.35, .25, .2, .1, .07, .03]))
        rows.append(_print(t, wallet, title, price, notional, outcome=str(rng.choice(["Yes", "No"])),
                           side=str(rng.choice(["BUY", "SELL"], p=[.7, .3])), key=_market_key(title),
                           end=now + pd.Timedelta(days=30)))
    return rows


def case_now(case: dict[str, Any]) -> pd.Timestamp:
    """The replay clock: 18:00 UTC of the case's date (the exact minute is
    not documented for most cases and does not change the shape)."""

    day = pd.Timestamp(str(case.get("date"))).tz_localize("UTC") if pd.Timestamp(str(case.get("date"))).tzinfo is None \
        else pd.Timestamp(str(case.get("date")))
    return day.normalize() + pd.Timedelta(hours=18)


def case_tape(case: dict[str, Any], *, now: pd.Timestamp | None = None) -> tuple[pd.DataFrame, dict[str, Any], pd.Timestamp]:
    """Synthetic tape and origins for one case: the case prints inside the
    background window. Returns (tape, origins, now).

    The case prints are spread over its wallets round-robin, two minutes
    apart, the last one four minutes before ``now``; a wallet with a
    documented ``first_trade_days`` gets a measured origin that many days
    before its first case print, a wallet without stays unmeasured.
    """

    clock = case_now(case) if now is None else pd.Timestamp(now)
    wallets = max(1, int(case.get("wallets") or 1))
    prints = max(wallets, int(case.get("prints") or wallets))
    title = str(case.get("market"))
    key = _market_key(str(case.get("id")))
    outcome = "Yes" if case_side(case) == "YES" else "No"
    price = float(case.get("price"))
    total = float(case.get("notional"))
    per_print = total / prints
    end = clock + pd.Timedelta(minutes=float(case.get("minutes_before_end") or 14 * 24 * 60))
    case_id = str(case.get("id"))
    rows: list[dict[str, Any]] = []
    first_print_of: dict[str, pd.Timestamp] = {}
    for i in range(prints):
        wallet = f"0xcase{hashlib.sha1(f'{case_id}:{i % wallets}'.encode('utf-8')).hexdigest()[:12]}"
        t = clock - pd.Timedelta(minutes=4.0 + 2.0 * (prints - 1 - i))
        rows.append(_print(t, wallet, title, min(0.99, price + 0.005 * i), per_print, outcome=outcome, key=key, end=end))
        first_print_of.setdefault(wallet, t)
    origins: dict[str, Any] = {}
    age = case.get("first_trade_days")
    if age is not None:
        for wallet, t in first_print_of.items():
            origins[wallet] = {"first_trade_ts": int(t.timestamp() - float(age) * 86_400.0), "state": susp.ORIGIN_MEASURED}
    tape = pd.DataFrame(background_tape(clock) + rows)
    return tape, origins, clock


def replay_case(case: dict[str, Any], *, whale_threshold: float = DEFAULT_WHALE_THRESHOLD,
                now: pd.Timestamp | None = None) -> dict[str, Any]:
    """Run one case through ``suspicion.screen_tape`` and report what the screen made of it."""

    result: dict[str, Any] = {
        "id": str(case.get("id")), "expectation": str(case.get("expectation")), "category": str(case.get("category") or ""),
        "market": str(case.get("market")), "replayable": bool(case.get("replayable", True)),
        "context": None, "excluded": False, "event_score": None, "flagged": False, "wallet_score": None,
        "components": {}, "flags": [], "problems": validate_case(case),
    }
    if result["problems"] or not result["replayable"]:
        result["ok"] = not result["problems"]
        return result
    tape, origins, clock = case_tape(case, now=now)
    screen = susp.screen_tape(tape, whale_threshold=whale_threshold, now=clock, origins=origins)
    title = str(case.get("market"))
    context = susp.classify_insider_context(title)[0]
    result["context"] = context
    events = screen.events
    row = events[events["title"].eq(title)] if events is not None and not events.empty and "title" in events else pd.DataFrame()
    if row.empty:
        result["excluded"] = context in susp.EXCLUDED_CONTEXTS
    else:
        r = row.iloc[0]
        score = float(r.get("event_insider_score") or 0.0)
        result["event_score"] = score
        result["flagged"] = score >= risk_log.DEFAULT_MIN_SCORE
        result["components"] = {
            part["key"].replace("component_", ""): part["value"] for part in susp.event_components(r)
        }
        flags = str(r.get("event_insider_flags") or "")
        result["flags"] = [part.strip() for part in flags.split(";") if part.strip() and part.strip() != susp.WATCH_ONLY]
    wallets = screen.wallets
    if wallets is not None and not wallets.empty and "wallet" in wallets:
        mine = wallets[wallets["wallet"].astype(str).str.startswith("0xcase")]
        if not mine.empty:
            result["wallet_score"] = float(pd.to_numeric(mine["wallet_insider_score"], errors="coerce").max())
    result["ok"] = verdict(result)
    return result


def verdict(result: dict[str, Any]) -> bool:
    """Whether the replay met the case's expectation. ``open`` always does."""

    expectation = str(result.get("expectation"))
    if expectation == "flag":
        return bool(result.get("flagged"))
    if expectation == "no_flag":
        return not bool(result.get("flagged")) and not bool(result.get("excluded"))
    if expectation == "excluded":
        return bool(result.get("excluded"))
    return True


def replay_all(path: Path | str = CASES_PATH, *, whale_threshold: float = DEFAULT_WHALE_THRESHOLD) -> list[dict[str, Any]]:
    return [replay_case(case, whale_threshold=whale_threshold) for case in load_cases(path)]


def summary(path: Path | str = CASES_PATH) -> dict[str, Any]:
    """What the list is, for ``suspicion.score_validation``: path, count,
    counts per expectation, and what the list may be read as."""

    cases = load_cases(path)
    counts: dict[str, int] = {}
    for case in cases:
        key = str(case.get("expectation") or "")
        counts[key] = counts.get(key, 0) + 1
    try:
        rel = str(Path(path).resolve().relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        rel = str(path)
    return {
        "path": rel,
        "n": len(cases),
        "by_expectation": counts,
        "reads": ("documented public cases rebuilt as tapes and replayed through the screen: a regression "
                  "suite for the patterns, not a hit rate; it says nothing about the flow the screen flags besides them"),
    }
