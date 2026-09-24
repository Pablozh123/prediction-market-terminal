"""Reproducible, read-only FOMC comparison. All rates are in basis points."""
from __future__ import annotations

import csv
import io
import math
import re
from bisect import bisect_right
from datetime import datetime, time
from statistics import mean
from zoneinfo import ZoneInfo

DAY = 86400


def ts(value: str) -> int:
    return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp())


def probability(value) -> float:
    p = float(value)
    if not math.isfinite(p) or not 0 <= p <= 1:
        raise ValueError("Invalid probability")
    return p


def bucket_definition(label: str) -> dict:
    if label == "No change":
        return {"key": "hold", "label": label, "min": 0, "max": 0}
    match = re.fullmatch(r"(25|50)(\+)? bps (decrease|increase)", label)
    if not match:
        raise ValueError(f"Unknown outcome bucket: {label}")
    amount, tail, direction = match.groups()
    amount = int(amount) * (-1 if direction == "decrease" else 1)
    return {"key": ("cut" if amount < 0 else "hike") + str(abs(amount)) + ("plus" if tail else ""),
            "label": label, "min": None if tail and amount < 0 else amount,
            "max": None if tail and amount > 0 else amount}


def bucket_for(change: int, buckets: list[dict]) -> str | None:
    matches = [b["key"] for b in buckets if (b["min"] is None or change >= b["min"])
               and (b["max"] is None or change <= b["max"])]
    return matches[0] if len(matches) == 1 else None


def parse_cme_csv(content: str, baseline: int | None, buckets: list[dict]) -> list[dict]:
    if baseline is None:
        return []
    reader = csv.DictReader(io.StringIO(content.lstrip("\ufeff")))
    headers = reader.fieldnames or []
    columns = [(h, re.fullmatch(r"\((\d+)-(\d+)\)", h)) for h in headers if h != "Date"]
    if "Date" not in headers or not columns or any(m is None for _, m in columns):
        raise ValueError("Expected CME Date,(lower-upper),... CSV")
    result = []
    for row in reader:
        date = datetime.strptime(row["Date"], "%m/%d/%Y").date()
        # CSV gives a trading date, not a tick time. End-of-day is a conservative
        # availability bound; never let the meeting-day close enter a backtest.
        stamp = int(datetime.combine(date, time(23, 59, 59), ZoneInfo("America/Chicago")).timestamp())
        probs = dict.fromkeys((b["key"] for b in buckets), 0.0)
        for header, match in columns:
            # Export leaves unreachable tails blank on some dates. Accept only
            # when the nonblank mass below still constitutes a full distribution.
            p = 0.0 if row[header] == "" else probability(row[header])
            key = bucket_for(int(match[2]) - baseline, buckets)
            if key is None:
                raise ValueError("CME rate range does not map to one outcome")
            probs[key] += p
        if abs(sum(probs.values()) - 1) > .001:
            raise ValueError("CME probabilities do not sum to one")
        result.append({"t": stamp, "date": date.isoformat(), "probabilities": probs})
    return sorted(result, key=lambda r: r["t"])


def asof(rows: list[dict], cutoff: int, max_age: int) -> dict | None:
    index = bisect_right(rows, cutoff, key=lambda r: r["t"]) - 1
    if index < 0 or cutoff - rows[index]["t"] > max_age:
        return None
    return rows[index]


def brier(probs: dict, actual: str) -> float:
    if actual not in probs or abs(sum(probs.values()) - 1) > .001:
        raise ValueError("Brier requires an exhaustive probability distribution")
    return sum((probability(p) - int(k == actual))**2 for k, p in probs.items())


def pm_vector(meeting: dict, cutoff: int) -> tuple[dict | None, float | None]:
    values = {}
    for b in meeting["buckets"]:
        point = asof(meeting["polymarket"].get(b["key"], []), cutoff, 2*3600)
        if point is None:
            return None, None
        values[b["key"]] = probability(point["p"])
    total = sum(values.values())
    if not .9 <= total <= 1.1:
        return None, total
    return {k: p / total for k, p in values.items()}, total


def checkpoint(meeting: dict, days: int) -> dict:
    cutoff = meeting["decision_ts"] - days*DAY
    empty = {"days": days, "cutoff": cutoff, "asof": None, "pm_brier": None, "cme_brier": None}
    after = meeting.get("comparable_after")
    if after is None or cutoff < after or meeting.get("actual") is None:
        return empty
    for cme in reversed(meeting["cme"]):
        if cme["t"] > cutoff or cme["t"] >= meeting["decision_ts"]:
            continue
        if cme["t"] < max(after, cutoff-4*DAY):
            break
        probs, total = pm_vector(meeting, cme["t"])
        if probs is not None:
            return {**empty, "asof": cme["t"], "age_hours": (cutoff-cme["t"])/3600,
                    "pm_sum": total, "pm_probabilities": probs, "cme_probabilities": cme["probabilities"],
                    "pm_brier": brier(probs, meeting["actual"]),
                    "cme_brier": brier(cme["probabilities"], meeting["actual"])}
    return empty


def evaluate(meetings: list[dict]) -> list[dict]:
    output = []
    for days in (30, 7, 1):
        rows = [{"meeting": m["date"], "actual": m["actual"], **checkpoint(m, days)}
                for m in meetings if m.get("actual") is not None]
        paired = [r for r in rows if r["pm_brier"] is not None and r["cme_brier"] is not None]
        reliability = {}
        for source in ("pm", "cme"):
            bins = [[] for _ in range(5)]
            for r in paired:
                for key, p in r[source + "_probabilities"].items():
                    bins[min(4, int(p*5))].append((p, int(key == r["actual"])))
            reliability[source] = [{"lower": i*.2, "upper": (i+1)*.2, "n": len(b),
                                    "forecast": mean(p for p, y in b) if b else None,
                                    "observed": mean(y for p, y in b) if b else None}
                                   for i, b in enumerate(bins)]
        output.append({"days": days, "n": len(paired), "rows": rows,
                       "pm_brier": mean(r["pm_brier"] for r in paired) if paired else None,
                       "cme_brier": mean(r["cme_brier"] for r in paired) if paired else None,
                       "reliability": reliability})
    return output
