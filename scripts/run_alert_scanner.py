"""Background alert scanner: builds monitor signals and delivers rule hits via Telegram.

Reuses the exact signal/rule logic from the website (app/signals.py), the saved
alert rules from data/monitor_rules.json (managed on the Monitor page), and the
delivery configuration from data/app_settings.json (managed on the Settings page).

Run:
    python scripts/run_alert_scanner.py            # loop per settings interval
    python scripts/run_alert_scanner.py --once     # single scan (for testing)

Every delivery attempt is written to the chained delivery log in
data/signal_ledger.sqlite (app/ledger.py): time, channel, target fingerprint,
signal key and whether the send succeeded. That log is what answers "did this
alert actually go out"; the JSON state file next to it is only a fallback for
the case where the database cannot be opened, plus the last scan's counters.

How often the same signal may go out is decided by app/signals.py
(due_for_delivery over the last SUCCESSFUL delivery), not by a timestamp some
API happened to set.
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
from app import ledger
from app import notify
from app import signals as sig
from src import prediction_markets as md

STATE_PATH = Path("data/alert_scanner_state.json")
RULES_PATH = Path("data/monitor_rules.json")
STOP_PATH = Path("data/alert_scanner.stop")
LEDGER_DB_PATH = ledger.DEFAULT_LEDGER_PATH
MAX_SEEN = 4000
MAX_MESSAGES_PER_SCAN = 10


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


#: Identitaet eines Signals im Zustell-Zustand. Liegt in app/signals.py,
#: damit sie pruefbar ist und die Seite dieselbe Regel benutzt.
signal_key = sig.signal_dedupe_key


DELIVERY_CHANNEL = "telegram"


def delivery_state(settings: dict) -> tuple[dict[str, str], str]:
    """Letzte gelungene Zustellung je Schluessel, aus dem Protokoll.

    Zweiter Rueckgabewert ist ein Fehlertext; ist er gesetzt, faellt der
    Aufrufer auf die Schluesselliste im JSON-Zustand zurueck. Ein nicht
    lesbares Protokoll darf den Scan nicht kippen, aber es darf auch nicht
    stillschweigend wie ein leeres aussehen: leer hiesse "noch nie zugestellt"
    und wuerde alles erneut verschicken.
    """

    try:
        conn = ledger.init_ledger(LEDGER_DB_PATH)
    except Exception as exc:  # noqa: BLE001
        return {}, f"delivery log unavailable: {exc}"
    try:
        return ledger.last_delivery_times(conn), ""
    except Exception as exc:  # noqa: BLE001
        return {}, f"delivery log unreadable: {exc}"
    finally:
        try:
            conn.close()
        except Exception:
            pass


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
    zuletzt, log_error = delivery_state(settings)
    if log_error:
        print(log_error, file=sys.stderr)
    now = pd.Timestamp.now(tz="UTC")
    new_rows: list[pd.Series] = []
    versuche: list[dict[str, str]] = []
    sent = 0
    deferred = 0
    for _, row in hits.iterrows():
        key = signal_key(row)
        if log_error:
            # Ohne lesbares Protokoll gilt die alte, groebere Regel: einmal
            # gesehen, nicht noch einmal. Lieber eine Zustellung zu wenig als
            # ein Schwall Wiederholungen.
            if key in seen_set:
                continue
        elif not sig.due_for_delivery(row, zuletzt.get(key), now):
            continue
        seen.append(key)
        seen_set.add(key)
        new_rows.append(row)
        if sent >= MAX_MESSAGES_PER_SCAN:
            # Nicht versucht heisst nicht zugestellt: keine Protokollzeile,
            # damit die Zustellquote nicht mit Nichtversuchen verduennt wird.
            # Ohne Erfolgszeile bleibt der Treffer beim naechsten Scan faellig.
            deferred += 1
            continue
        ok, detail = notify.send_telegram(settings["telegram_bot_token"], settings["telegram_chat_id"], format_hit(row))
        versuche.append({
            "dedupe_key": key,
            "channel": DELIVERY_CHANNEL,
            "target": str(settings.get("telegram_chat_id", "")),
            "status": ledger.DELIVERY_STATUS_SENT if ok else "failed",
            "detail": "" if ok else str(detail),
            "signal_type": str(row.get("signal_type", "")),
            "market_key": str(row.get("market_key", "")),
        })
        if ok:
            sent += 1
        else:
            zuletzt.pop(key, None)
            print(f"telegram delivery failed: {detail}", file=sys.stderr)
    # Every new hit goes to the append-only ledger, not just the ones that fit
    # under the Telegram message cap. A broken ledger must never kill the scan.
    ledger_written = 0
    if new_rows:
        ledger_written, ledger_error = ledger.safe_emit_signals(pd.DataFrame(new_rows), LEDGER_DB_PATH)
        if ledger_error:
            print(ledger_error, file=sys.stderr)
    # Jeder Versuch wird protokolliert, der gelungene wie der fehlgeschlagene.
    # Nur der gelungene setzt die Ruhezeit (ledger.last_delivery_times).
    delivery_logged = 0
    if versuche:
        delivery_logged, delivery_error = ledger.safe_record_deliveries(versuche, LEDGER_DB_PATH)
        if delivery_error:
            print(delivery_error, file=sys.stderr)
    state["last_ledger_written"] = ledger_written
    state["seen"] = seen[-MAX_SEEN:]
    state["last_scan_at"] = now.isoformat()
    state["last_hits"] = int(len(hits))
    state["last_attempted"] = len(versuche)
    state["last_sent"] = sent
    state["last_failed"] = len(versuche) - sent
    state["last_deferred"] = deferred
    state["last_delivery_logged"] = delivery_logged
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
