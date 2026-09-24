#!/usr/bin/env python3
"""Archive public source data and publish the FOMC comparison.

python scripts/collect_fed_comparison.py              # refresh sources
python scripts/collect_fed_comparison.py --offline    # rebuild from archive
python scripts/collect_fed_comparison.py --cme-dir PATH # use authentic CSV exports
Raw source files stay local; the derived, provenance-labelled JSON uses the
existing research publication path. No orders, accounts or subscriptions.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.fed_comparison import DAY, bucket_definition, bucket_for, evaluate, parse_cme_csv, probability

# Reviewed against the Federal Reserve calendar and statements on 2026-09-24.
# Future baselines stay unknown until the preceding statement is verified.
MEETINGS = [
    ("2026-03-18", "2026-01-28", 375, 0, "fed-decision-in-march-885"),
    ("2026-04-29", "2026-03-18", 375, 0, "fed-decision-in-april"),
    ("2026-06-17", "2026-04-29", 375, 0, "fed-decision-in-june-825"),
    ("2026-07-29", "2026-06-17", 375, 0, "fed-decision-in-july-181"),
    ("2026-09-16", "2026-07-29", 375, 25, "fed-decision-in-september-762"),
    ("2026-10-28", "2026-09-16", 400, None, "fed-decision-in-october-20260617190323537"),
    ("2026-12-09", "2026-10-28", None, None, "fed-decision-in-december-20260729232808632"),
]
CME_PAGE = "https://www.cmegroup.com/markets/interest-rates/cme-fedwatch-tool.html"
CME_EXPORT = "https://cmegroup-tools.quikstrike.net/User/Export/FedWatch/MeetingExport.aspx"


def atomic_write(path: Path, content: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_bytes(content)
    temp.replace(path)


def save_json(path: Path, value):
    atomic_write(path, json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode())


def decision_ts(date: str) -> int:
    return int(datetime.fromisoformat(date + "T14:00:00").replace(tzinfo=ZoneInfo("America/New_York")).timestamp())


def cme_session():
    # Normal public embedded-tool session, with its actual embedding page as
    # referrer. Do not hardcode browser cookies or a transient session ID.
    session = requests.Session()
    response = session.get("https://cmegroup-tools.quikstrike.net/User/QuikStrikeTools.aspx",
                           params={"viewitemid": "IntegratedFedWatchTool", "userId": "lwolf"},
                           headers={"Referer": CME_PAGE}, timeout=25)
    response.raise_for_status()
    params = parse_qs(urlparse(response.url).query)
    if not all(k in params for k in ("insid", "qsid")):
        raise ValueError("Public CME session unavailable; import downloaded CSV files")
    return session, {k: params[k][0] for k in ("insid", "qsid")}


def collect(raw: Path, offline=False, cme_dir: Path | None = None):
    now = datetime.now(timezone.utc)
    now_ts = int(now.timestamp())
    raw.mkdir(parents=True, exist_ok=True)
    manifest_path = raw / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    errors = []
    cme_client = None
    if not offline and cme_dir is None:
        try:
            cme_client = cme_session()
        except (requests.RequestException, ValueError):
            errors.append("The CME connection could not be refreshed. Stored CSV files have been retained.")

    def archive(path, content, source):
        atomic_write(path, content)
        manifest[path.name] = {"source": source, "retrieved_at": now.isoformat(),
                               "sha256": hashlib.sha256(content).hexdigest()}

    def history(token, start, end):
        points = {}
        for left in range(start, end, 7*DAY):
            right = min(end, left + 7*DAY)
            response = requests.get("https://clob.polymarket.com/prices-history",
                                    params={"market": token, "startTs": left, "endTs": right, "fidelity": 60}, timeout=25)
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload.get("history"), list):
                raise ValueError("Polymarket history response missing history")
            for p in payload["history"]:
                stamp = int(p["t"])
                if start <= stamp < end:
                    points[stamp] = probability(p["p"])
        return [{"t": t, "p": p} for t, p in sorted(points.items())]

    meetings = []
    for date, previous, baseline, actual, slug in MEETINGS:
        decision = decision_ts(date)
        after = decision_ts(previous)
        # A small pre-T30 margin supports weekend checkpoints. Upcoming
        # meetings retain recent history even when T30 has not begun yet.
        end = min(decision, now_ts)
        start = min(decision - 35*DAY, end - 35*DAY)
        event_path = raw / (slug + ".json")
        issues = []
        statement_url = "https://www.federalreserve.gov/newsevents/pressreleases/monetary" + date.replace("-", "") + "a.htm"
        if actual is not None and not offline:
            try:
                response = requests.get(statement_url, timeout=25)
                response.raise_for_status()
                if "target range" not in response.text or "federal funds" not in response.text:
                    raise ValueError("Federal Reserve statement unavailable")
                archive(raw / f"fed_{date}.html", response.content, statement_url)
            except (requests.RequestException, ValueError):
                issues.append("The Fed statement could not be archived again during this run.")
        if not offline:
            try:
                url = "https://gamma-api.polymarket.com/events/slug/" + slug
                response = requests.get(url, timeout=25)
                response.raise_for_status()
                event = response.json()
                if event.get("slug") != slug or not event.get("markets"):
                    raise ValueError("Unexpected Polymarket event")
                archive(event_path, response.content, url)
            except (requests.RequestException, ValueError):
                issues.append("Polymarket metadata could not be refreshed. The stored snapshot has been retained.")
        if not event_path.exists():
            raise ValueError(f"Missing event metadata: {slug}")
        event = json.loads(event_path.read_text(encoding="utf-8"))
        buckets = []
        for market in event["markets"]:
            b = bucket_definition(market["groupItemTitle"])
            outcomes = json.loads(market["outcomes"])
            yes = outcomes.index("Yes")
            b.update(token_id=json.loads(market["clobTokenIds"])[yes], condition_id=market["conditionId"],
                     market_url="https://polymarket.com/event/" + slug + "/" + market["slug"])
            buckets.append(b)
        histories = {}

        def load_bucket(b):
            path = raw / f"pm_{date}_{b['key']}.json"
            issue = None
            fetched = None
            if not offline:
                try:
                    fetched = history(b["token_id"], start, end)
                    # Merge so a refresh never truncates previously archived history.
                    old = json.loads(path.read_text()) if path.exists() else []
                    merged = {p["t"]: p["p"] for p in old}
                    merged.update({p["t"]: p["p"] for p in fetched})
                    fetched = [{"t": t, "p": p} for t, p in sorted(merged.items())]
                    if fetched:
                        save_json(path, fetched)
                    else:
                        issue = "No historical Polymarket prices available: " + b["label"]
                except (requests.RequestException, ValueError):
                    issue = "Polymarket history could not be refreshed: " + b["label"]
            points = json.loads(path.read_text()) if path.exists() else []
            return b["key"], points, issue, path, fetched is not None

        with ThreadPoolExecutor(max_workers=4) as pool:
            for key, points, issue, path, fetched in pool.map(load_bucket, buckets):
                histories[key] = [p for p in points if p["t"] < decision]
                if issue:
                    issues.append(issue)
                if fetched and path.exists():
                    manifest[path.name] = {"source": "https://clob.polymarket.com/prices-history", "fidelity_minutes": 60,
                                           "retrieved_at": now.isoformat(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        cme_path = raw / f"cme_{date}.csv"
        try:
            if cme_dir is not None:
                content = (cme_dir / cme_path.name).read_bytes()
                parse_cme_csv(content.decode("utf-8-sig"), baseline or 400, buckets)
                archive(cme_path, content, CME_PAGE)
            elif cme_client is not None:
                session, params = cme_client
                response = session.get(CME_EXPORT, params={**params, "MeetingDate": date.replace("-", "")}, timeout=25)
                response.raise_for_status()
                content = response.content.decode("utf-8-sig")
                parse_cme_csv(content, baseline or 400, buckets)
                archive(cme_path, response.content, CME_EXPORT + "?MeetingDate=" + date.replace("-", ""))
        except (requests.RequestException, ValueError, OSError):
            # Requests errors can contain ephemeral public-session query params.
            if cme_path.exists():
                issues.append("CME history could not be refreshed. The latest stored snapshot is shown.")
        cme = []
        if cme_path.exists():
            cme = parse_cme_csv(cme_path.read_text(encoding="utf-8-sig"), baseline, buckets)
            cme = [r for r in cme if after <= r["t"] < min(decision, now_ts)]
        if not cme_path.exists():
            issues.append("CME history is missing. Public downloads start in April 2026. March requires an older original export or an authorised FedWatch API source.")
        archive_source = manifest.get(cme_path.name, {})
        archived = bool(archive_source.get("derived_from"))
        if archived:
            issues.append("March: FedWatch tables from the SinoPac broker archive, rounded to 0.1 percentage point. Gaps remain visible. Timestamps represent the end of the report date in Chicago, not a CME closing price; the intraday observation time is not used for a trading comparison.")
        if baseline is None:
            issues.append("The previous meeting has not yet taken place. CME rate levels therefore cannot yet be mapped unambiguously to rate changes at this meeting.")
        meeting = {"date": date, "decision_ts": decision, "previous_meeting": previous,
                   "baseline_upper_bps": baseline, "comparable_after": after if baseline is not None else None,
                   "actual": bucket_for(actual, buckets) if actual is not None else None,
                   "actual_change_bps": actual, "buckets": buckets, "polymarket": histories, "cme": cme,
                   "event_url": "https://polymarket.com/event/" + slug,
                   "statement_url": statement_url if actual is not None else None,
                   "cme_archive_url": archive_source.get("source") if archived else None,
                   "issues": issues}
        meetings.append(meeting)
        save_json(manifest_path, manifest)
        print(date, "PM", sum(map(len, histories.values())), "CME", len(cme), "issues", len(issues), flush=True)
    return {"schema": "fed_comparison/1", "generated_at": now.isoformat(), "meetings": meetings,
            "evaluation": evaluate(meetings), "errors": errors, "sources": manifest,
            "cme_url": CME_PAGE, "cme_resolution": "Daily CSV; conservative timestamp 23:59:59 America/Chicago; decision-day EOD excluded",
            "polymarket_resolution": "60-minute CLOB price history; price observations, not executable bid/ask",
            "calendar_verified_at": "2026-09-24", "calendar_through": "2026-12-09"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--cme-dir", type=Path)
    parser.add_argument("--raw-dir", type=Path, default=ROOT / "data/fed_comparison/raw")
    parser.add_argument("--out", type=Path, default=ROOT / "public/data/fed_comparison.json")
    args = parser.parse_args()
    payload = collect(args.raw_dir, args.offline, args.cme_dir)
    save_json(args.out, payload)
    print("Saved", args.out)


if __name__ == "__main__":
    main()
