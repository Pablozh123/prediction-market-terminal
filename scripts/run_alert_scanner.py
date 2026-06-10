"""Background alert scanner: builds monitor signals and delivers rule hits via Telegram.

Reuses the exact signal/rule logic from the website (app/signals.py), the saved
alert rules from data/monitor_rules.json (managed on the Monitor page), and the
delivery configuration from data/app_settings.json (managed on the Settings page).

Run:
    python scripts/run_alert_scanner.py            # loop per settings interval
    python scripts/run_alert_scanner.py --once     # single scan (for testing)

Already-notified signals are remembered in data/alert_scanner_state.json so each
hit is delivered only once.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import app_settings as cfg
from app import notify
from app import signals as sig
from src import prediction_markets as md

STATE_PATH = Path("data/alert_scanner_state.json")
RULES_PATH = Path("data/monitor_rules.json")
STOP_PATH = Path("data/alert_scanner.stop")
MAX_SEEN = 4000
MAX_MESSAGES_PER_SCAN = 10


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def signal_key(row: pd.Series) -> str:
    time_part = str(row.get("time", ""))[:16]
    return f"{row.get('signal_type', '')}|{row.get('market_key', '')}|{row.get('wallet', '')}|{time_part}"


def format_hit(row: pd.Series) -> str:
    parts = [
        f"[{row.get('rule_name', 'Alert')}] {row.get('signal_type', '')}",
        str(row.get("title", ""))[:120],
        str(row.get("reason", "")),
    ]
    url = str(row.get("url", "") or "")
    if url:
        parts.append(url)
    return "\n".join(part for part in parts if part)


def scan_once(settings: dict) -> tuple[int, int]:
    """Run one scan. Returns (hits found, messages sent)."""

    rules = load_json(RULES_PATH, [])
    if not isinstance(rules, list) or not rules:
        return 0, 0
    try:
        markets = md.get_polymarket_markets(limit=int(settings["market_sample"]))
    except md.MarketDataError:
        markets = pd.DataFrame()
    try:
        trades = md.get_polymarket_trades(limit=int(settings["trade_sample"]))
    except md.MarketDataError:
        trades = pd.DataFrame()
    if markets.empty and trades.empty:
        return 0, 0

    signals = sig.build_monitor_signals(
        markets,
        trades,
        min_volume=0.0,
        min_liquidity=0.0,
        min_move=float(settings["alert_min_move_cents"]) / 100.0,
        max_spread=0.07,
        min_whale_notional=float(settings["whale_threshold"]),
        ending_days=3,
        holder_threshold=0.4,
        holder_checks=int(settings["alert_holder_checks"]),
        tracked_keys=set(),
        fetch_holders=(lambda key: md.get_polymarket_holders(key)) if int(settings["alert_holder_checks"]) > 0 else None,
    )
    hits = sig.build_monitor_alert_hits(signals, rules)
    if hits.empty:
        return 0, 0

    state = load_json(STATE_PATH, {})
    seen = list(state.get("seen", []))
    seen_set = set(seen)
    sent = 0
    for _, row in hits.iterrows():
        key = signal_key(row)
        if key in seen_set:
            continue
        seen.append(key)
        seen_set.add(key)
        if sent >= MAX_MESSAGES_PER_SCAN:
            continue
        ok, detail = notify.send_telegram(settings["telegram_bot_token"], settings["telegram_chat_id"], format_hit(row))
        if ok:
            sent += 1
        else:
            print(f"telegram delivery failed: {detail}", file=sys.stderr)
    state["seen"] = seen[-MAX_SEEN:]
    state["last_scan_at"] = pd.Timestamp.now(tz="UTC").isoformat()
    state["last_hits"] = int(len(hits))
    state["last_sent"] = sent
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")
    return int(len(hits)), sent


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan monitor rules and deliver alert hits via Telegram.")
    parser.add_argument("--once", action="store_true", help="Run a single scan and exit.")
    args = parser.parse_args()

    while True:
        settings = cfg.load_settings()
        if STOP_PATH.exists():
            print("stop file found, exiting")
            STOP_PATH.unlink(missing_ok=True)
            return 0
        if not settings["alerts_enabled"] or not settings["telegram_bot_token"]:
            if args.once:
                print("alerts disabled or Telegram not configured; nothing to do")
                return 0
        else:
            try:
                hits, sent = scan_once(settings)
                print(f"scan complete: {hits} hits, {sent} sent")
            except Exception as exc:
                print(f"scan failed: {exc}", file=sys.stderr)
        if args.once:
            return 0
        interval = max(1, int(settings["alert_interval_minutes"])) * 60
        deadline = time.monotonic() + interval
        while time.monotonic() < deadline:
            if STOP_PATH.exists():
                STOP_PATH.unlink(missing_ok=True)
                print("stop file found, exiting")
                return 0
            time.sleep(5)


if __name__ == "__main__":
    raise SystemExit(main())
