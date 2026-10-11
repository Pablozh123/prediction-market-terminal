"""Kausaler Paper-Test für BTC: CEX-Vorlauf und Polymarket-Reaktion.

Öffentliche Daten, ohne Wallet oder Order-API. Sichtbare Liquidität ist eine
optimistische Fill-Annahme. Methodik: docs/research/cex_leadlag.md.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import heapq
import json
import math
import sqlite3
import statistics
from collections import Counter, deque
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from itertools import groupby
from pathlib import Path

from src.book_stream import BookState

DEFAULT_ROOT = Path(__file__).resolve().parents[1] / "data" / "cex_leadlag"


@dataclass(frozen=True)
class Config:
    lookback_ms: float = 1000
    threshold_bps: float = 2
    cooldown_ms: float = 5000
    hold_ms: float = 5000
    stale_ms: float = 2000
    shares: float = 10
    cash: float = 100
    max_ask: float = .85
    max_price_jump: float = .02
    signal_source: str = "binance"

    def __post_init__(self):
        for name, value in asdict(self).items():
            if name == "signal_source":
                continue
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and positive")
        if self.max_ask >= 1 or self.max_price_jump >= 1:
            raise ValueError("Probability price limits must be below 1")
        if self.signal_source not in {"binance", "coinbase"}:
            raise ValueError("Unknown signal source")


def walk(levels: dict, shares: float, *, buy: bool, fee_rate: float) -> dict | None:
    """Full quantity or no simulated fill; fees charged per consumed level."""
    remaining, gross, fee = shares, 0., 0.
    worst = None
    for price in sorted(levels, reverse=not buy):
        quantity = min(remaining, levels[price])
        gross += quantity * price
        fee += quantity * fee_rate * price * (1 - price)
        worst = price
        remaining -= quantity
        if remaining < 1e-9:
            return {"gross": gross, "fee": round(fee, 5), "vwap": gross / shares, "worst": worst}
    return None


def replay(events: Iterable[dict], config: Config, latency_ms: float = 100,
           decisions: dict | None = None, *, presorted: bool = False) -> dict:
    """Execute deadlines against the book observed as of that deadline.

    Events at exactly the deadline are applied first, in recorded order. Each
    arm has independent cash and one position per market, including pending exits.
    """
    if not math.isfinite(latency_ms) or latency_ms < 0:
        raise ValueError("latency_ms must be finite and nonnegative")
    books, updated, markets, history, returns = {}, {}, {}, {}, {}
    positions, cooldown, tasks, trades, signals = {}, {}, [], [], []
    quote_responses, watching = [], {}
    diagnostics = {"cex_max_abs_return_bps": {}, "price_ticks": {}}
    skips = Counter()
    cash = config.cash
    task_seq = 0

    def schedule(due, action, data):
        nonlocal task_seq
        task_seq += 1
        heapq.heappush(tasks, (int(due), task_seq, action, data))

    def usable(token, at):
        book = books.get(token)
        if book is None:
            return None
        if at - updated[token] > config.stale_ms * 1e6:
            return None
        if book.best_bid() is None or book.best_ask() is None or book.best_bid() >= book.best_ask():
            return None
        return book

    def execute(due, action, data):
        nonlocal cash
        if action == "observation_end":
            if data in watching.get(data["token"], []):
                data["censored"] = False
                watching[data["token"]].remove(data)
            return
        token, mid = data["token"], data["market_id"]
        book = usable(token, due)
        fee_rate = markets[mid]["fee_rate"]
        if fee_rate is None:
            skips[action + "_unknown_fee"] += 1
            if action == "exit":
                positions[mid]["status"] = "open_unknown_exit_fee"
            return
        if action == "enter":
            if mid in positions:
                skips["position_limit"] += 1
                return
            # Compute wall time from the signal's local clock pair, not server time.
            due_wall = data["wall_ns"] / 1e9 + (due - data["t_ns"]) / 1e9
            if due_wall + config.hold_ms / 1000 >= markets[mid]["end_s"]:
                skips["market_ending"] += 1
                return
            if book is None:
                skips["entry_no_book"] += 1
                return
            fill = walk(book.asks, config.shares, buy=True, fee_rate=fee_rate)
            if fill is None:
                skips["entry_depth"] += 1
                return
            if fill["worst"] > min(config.max_ask, data["ask"] + config.max_price_jump) + 1e-9:
                skips["price_moved"] += 1
                return
            cost = fill["gross"] + fill["fee"]
            if cost > cash + 1e-9:
                skips["budget"] += 1
                return
            cash -= cost
            trade = {"signal_id": data["signal_id"], "market_id": mid, "token": token,
                     "outcome": data["outcome"], "signal_t_ns": data["t_ns"],
                     "entry_t_ns": due, "entry_vwap": fill["vwap"], "shares": config.shares,
                     "entry_gross": fill["gross"], "entry_fee": fill["fee"],
                     "exit_t_ns": None, "exit_vwap": None, "exit_fee": None,
                     "net_pnl": None, "status": "open"}
            positions[mid] = trade
            trades.append(trade)
            schedule(due + config.hold_ms * 1e6, "exit", data)
        else:
            trade = positions[mid]
            if book is None:
                skips["exit_no_book"] += 1
                trade["status"] = "open_missing_exit_book"
                return
            fill = walk(book.bids, config.shares, buy=False, fee_rate=fee_rate)
            if fill is None:
                skips["exit_depth"] += 1
                trade["status"] = "open_insufficient_exit_depth"
                return
            proceeds = fill["gross"] - fill["fee"]
            cash += proceeds
            trade.update(exit_t_ns=due, exit_vwap=fill["vwap"], exit_fee=fill["fee"],
                         net_pnl=proceeds - trade["entry_gross"] - trade["entry_fee"], status="closed")
            del positions[mid]

    ordered = events if presorted else sorted(events, key=lambda row: row["t_ns"])
    # Group equal timestamps so deadlines cannot sneak between simultaneous frames.
    for current_t, same in groupby(ordered, key=lambda row: row["t_ns"]):
        while tasks and tasks[0][0] < current_t:
            due, _, action, data = heapq.heappop(tasks)
            execute(due, action, data)
        for row in same:
            current_wall = row["wall_ns"]
            kind = row["kind"]
            if kind == "market":
                markets[row["market"]["id"]] = row["market"]
            elif kind == "status" and row["state"] in {"disconnected", "connected"}:
                if row["source"] == "polymarket":
                    books.clear()
                    updated.clear()
                    watching.clear()  # Unanswered observations remain censored.
                else:
                    history.pop(row["source"], None)
                    returns.pop(row["source"], None)
            elif kind == "book":
                token = row["token"]
                if row["snapshot"]:
                    book = BookState()
                    book.apply_snapshot(row["bids"], row["asks"])
                    books[token] = book
                elif token in books:
                    for price, size, side in row["changes"]:
                        books[token].apply_change(price, size, side)
                else:
                    continue
                updated[token] = current_t
                for observation in list(watching.get(token, [])):
                    ask = books[token].best_ask()
                    if ask is not None and ask >= observation["initial_ask"] + .01 - 1e-9:
                        observation["response_lag_ms"] = (current_t - observation["t_ns"]) / 1e6
                        observation["censored"] = False
                        watching[token].remove(observation)
            elif kind == "price":
                source = row["source"]
                diagnostics["price_ticks"][source] = diagnostics["price_ticks"].get(source, 0) + 1
                ticks = history.setdefault(source, deque())
                ticks.append((current_t, row["price"]))
                target = current_t - config.lookback_ms * 1e6
                while len(ticks) > 1 and ticks[1][0] <= target:
                    ticks.popleft()
                if ticks[0][0] > target or target - ticks[0][0] > config.stale_ms * 1e6:
                    continue
                move = (row["price"] / ticks[0][1] - 1) * 10000
                diagnostics["cex_max_abs_return_bps"][source] = max(
                    abs(move), diagnostics["cex_max_abs_return_bps"].get(source, 0))
                returns[source] = (current_t, move)
                if source != config.signal_source or abs(move) < config.threshold_bps:
                    continue
                outcome = "Up" if move > 0 else "Down"
                for mid, market in markets.items():
                    if market["fee_rate"] is None or not market["start_s"] <= current_wall / 1e9:
                        continue
                    if current_wall / 1e9 + (latency_ms + config.hold_ms) / 1000 >= market["end_s"]:
                        continue
                    if current_t - cooldown.get(mid, -10**30) < config.cooldown_ms * 1e6:
                        continue
                    token = market["tokens"][outcome]
                    book = usable(token, current_t)
                    if book is None or book.best_ask() > config.max_ask:
                        continue
                    other = "coinbase" if source == "binance" else "binance"
                    confirmation = returns.get(other)
                    features = {"cex_return_bps": move, "lookback_ms": config.lookback_ms,
                                "other_cex_return_bps": confirmation[1] if confirmation and
                                current_t - confirmation[0] <= config.stale_ms * 1e6 else None,
                                "ask": book.best_ask(), "bid": book.best_bid(),
                                "book_age_ms": (current_t - updated[token]) / 1e6,
                                "seconds_to_close": market["end_s"] - current_wall / 1e9,
                                "shares": config.shares, "fee_rate": market["fee_rate"],
                                "holding_ms": config.hold_ms, "max_price_jump": config.max_price_jump,
                                "max_ask": config.max_ask}
                    signal = {"signal_id": f"{current_t}:{mid}:{outcome}", "market_id": mid,
                              "outcome": outcome, "token": token, "t_ns": current_t,
                              "wall_ns": current_wall, "ask": book.best_ask(),
                              "fee_rate": market["fee_rate"], "features": features}
                    signals.append(signal)
                    observation = {"signal_id": signal["signal_id"], "token": token, "t_ns": current_t,
                                   "initial_ask": book.best_ask(), "response_lag_ms": None,
                                   "horizon_ms": config.hold_ms, "censored": True}
                    quote_responses.append(observation)
                    watching.setdefault(token, []).append(observation)
                    schedule(current_t + config.hold_ms * 1e6, "observation_end", observation)
                    cooldown[mid] = current_t
                    extra_delay = 0
                    if decisions is not None:
                        decision = decisions.get(signal["signal_id"], {})
                        if decision.get("input_sha256"):
                            from src.cex_decision import features_hash
                            if decision["input_sha256"] != features_hash(features):
                                skips["ai_input_changed"] += 1
                                continue
                        extra_delay = decision.get("latency_ms", 0)
                        if decision.get("choice") != "enter" or not isinstance(extra_delay, (float, int)) \
                                or not math.isfinite(extra_delay) or extra_delay < 0:
                            skips["ai_abstain"] += 1
                            continue
                    schedule(current_t + (latency_ms + extra_delay) * 1e6, "enter", signal)
        while tasks and tasks[0][0] <= current_t:
            due, _, action, data = heapq.heappop(tasks)
            execute(due, action, data)

    closed = [trade for trade in trades if trade["net_pnl"] is not None]
    pnl = sum(trade["net_pnl"] for trade in closed)
    response_lags = [r["response_lag_ms"] for r in quote_responses if r["response_lag_ms"] is not None]
    return {"config": asdict(config), "latency_ms": latency_ms,
            "mode": "jev_gate" if decisions is not None else "baseline",
            "summary": {"signals": len(signals), "closed_trades": len(closed),
                        "open_positions": len(positions), "pending_entries": sum(t[2] == "enter" for t in tasks),
                        "realized_pnl": pnl, "cash": cash,
                        "entry_cost_open": sum(t["entry_gross"] + t["entry_fee"] for t in positions.values()),
                        "wins": sum(t["net_pnl"] > 0 for t in closed),
                        "fees_closed": sum(t["entry_fee"] + t["exit_fee"] for t in closed),
                        "quote_responses": len(response_lags),
                        "censored_responses": sum(r["censored"] for r in quote_responses),
                        "median_response_ms": statistics.median(response_lags) if response_lags else None},
            "skips": dict(skips), "trades": trades, "signals": signals,
            "quote_responses": quote_responses, "diagnostics": diagnostics}


def write_report(run: Path, config: Config, latencies: list[float], decisions: dict | None = None) -> dict:
    manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("data_loss") or manifest.get("status") not in {"complete", "interrupted"}:
        raise ValueError("Recording is incomplete or lost events; replay refused")
    with (run / "events.jsonl").open("rb") as file:
        if hashlib.file_digest(file, "sha256").hexdigest() != manifest.get("events_sha256"):
            raise ValueError("Capture checksum mismatch")
    # A two-minute capture already contains ~200k events. Let SQLite sort on
    # disk rather than retaining every depth frame and four sort copies in RAM.
    database = sqlite3.connect("")  # Temporary disk database, removed on close.
    try:
        database.execute("CREATE TABLE events (ts INTEGER, payload TEXT)")
        with (run / "events.jsonl").open(encoding="utf-8") as file:
            database.executemany("INSERT INTO events VALUES (?, ?)",
                                 ((json.loads(line)["t_ns"], line) for line in file))
        database.execute("CREATE INDEX event_time ON events(ts)")
        event_count = database.execute("SELECT COUNT(*) FROM events").fetchone()[0]

        def rows():
            return (json.loads(row[0]) for row in database.execute("SELECT payload FROM events ORDER BY ts, rowid"))

        arms = [replay(rows(), config, latency, presorted=True) for latency in latencies]
        if decisions is not None:
            control = {sid: {**decision, "choice": "enter", "latency_ms": 0} for sid, decision in decisions.items()}
            for latency in latencies:
                matched = replay(rows(), config, latency, control, presorted=True)
                matched["mode"] = "scored_control"
                arms.append(matched)
            arms += [replay(rows(), config, latency, decisions, presorted=True) for latency in latencies]
    finally:
        database.close()
    report = {"schema": 1, "manifest": manifest, "arms": arms,
              "code_sha256": {name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                              for name in ("cex_leadlag.py", "cex_leadlag_feed.py", "cex_decision.py", "book_stream.py")},
              "limitations": ["Sichtbare Liquidität ist eine optimistische Fill-Annahme; echte Fills und "
                              "die eigene Position in der Orderwarteschlange sind nicht beobachtet.",
                              "Es zählt die lokale Empfangsreihenfolge. Synchronisierte Börsenuhren "
                              "werden nicht vorausgesetzt.",
                              "Der Test prüft Impuls und Wiederverkauf. Er schätzt keine kalibrierte "
                              "Gewinnwahrscheinlichkeit bis zur Auflösung.",
                              "Offene Positionen bleiben unbewertet und zählen nicht zum realisierten Ergebnis.",
                              "Jev ist mit scored_control zu vergleichen: Beide verwenden dieselbe "
                              "Auswahl bewerteter Kandidaten.",
                              "Jev-API-Kosten sind nicht abgezogen. Der Tokenverbrauch wird separat erfasst.",
                              "Kleine Stichproben und die Suche nach günstigen Parametern belegen "
                              "keinen belastbaren Handelsvorteil."]}
    counts = manifest.get("counts", {})
    report["data_quality"] = {"missing_feeds": [source for source, kind in
        (("binance", "price"), ("coinbase", "price"), ("polymarket", "book")) if not counts.get(source + ":" + kind)],
        "source_errors": manifest.get("errors", {}), "data_loss": manifest.get("data_loss", False)}
    name = "report_jev" if decisions is not None else "report"
    (run / f"{name}.json").write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    # The scoring file contains only information available at signal time.
    with (run / "decision_inputs.jsonl").open("w", encoding="utf-8") as file:
        for signal in arms[0]["signals"]:
            file.write(json.dumps(signal, allow_nan=False) + "\n")
    with (run / f"{name}_trades.csv").open("w", newline="", encoding="utf-8") as file:
        fields = ["mode", "latency_ms", "signal_id", "market_id", "outcome", "entry_t_ns", "entry_vwap",
                  "shares", "entry_fee", "exit_t_ns", "exit_vwap", "exit_fee", "net_pnl", "status"]
        writer = csv.DictWriter(file, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for arm in arms:
            writer.writerows({**trade, "mode": arm["mode"], "latency_ms": arm["latency_ms"]}
                             for trade in arm["trades"])
    modes = {"baseline": "Basisregel", "scored_control": "Vergleichsauswahl", "jev_gate": "Jev-Filter"}
    lines = ["# BTC: CEX-Vorlauf und Polymarket-Reaktion", "", "Es wurden keine echten Orders übermittelt.", "",
             f"Aufzeichnung: {manifest.get('capture_duration_s', manifest.get('duration_s', 0)):.1f} Sekunden; "
             f"{event_count:,} Ereignisse.", "",
             "| Variante | Verzögerung ms | Signale | Geschlossen | Offen | Einsatz offen USD | "
             "Netto realisiert USD | Gebühren USD |",
             "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for arm in arms:
        s = arm["summary"]
        lines.append(f"| {modes[arm['mode']]} | {arm['latency_ms']:g} | {s['signals']} | {s['closed_trades']} | "
                     f"{s['open_positions']} | {s['entry_cost_open']:.5f} | "
                     f"{s['realized_pnl']:.5f} | {s['fees_closed']:.5f} |")
    diagnostics = arms[0]["diagnostics"]
    lines += ["", "Jede Verzögerung ist ein eigener Simulationslauf. Die Gewinne dürfen nicht addiert werden.", "",
              "## Datenqualität", "", "| Quelle | Preismeldungen | Grösster absoluter Impuls in Basispunkten |",
              "|---|---:|---:|"]
    for source in ("binance", "coinbase"):
        move = diagnostics["cex_max_abs_return_bps"].get(source)
        lines.append(f"| {source.title()} | {diagnostics['price_ticks'].get(source, 0)} | "
                     f"{f'{move:.4f}' if move is not None else 'nicht messbar'} |")
    quality, summary = report["data_quality"], arms[0]["summary"]
    median = summary["median_response_ms"]
    lines += ["", "Fehlende Datenquellen: " + (", ".join(quality["missing_feeds"]) or "keine") + ".",
              "Verbindungsfehler: " + (json.dumps(quality["source_errors"], sort_keys=True) if
                                       quality["source_errors"] else "keine") + ".", "",
              "## Gemessene Kursreaktion", "",
              f"Ask-Anstiege um mindestens einen Cent: {summary['quote_responses']}; "
              f"Median der beobachteten Reaktionen: {f'{median:.2f} ms' if median is not None else 'nicht messbar'}; "
              f"wegen Datenlücken unvollständig beobachtet: {summary['censored_responses']}.", "",
              "Dies beschreibt die Reaktion nach dem Signal. Es belegt nicht, dass die CEX die Bewegung verursacht hat.",
              "", "## Einordnung", "", *[f"- {text}" for text in report["limitations"]], "",
              "Eine Gewinnwahrscheinlichkeit von 85 % wird weder angenommen noch aus einem CEX-Impuls abgeleitet.", "",
              "## Verwendete Parameter", "", "```json", json.dumps(asdict(config), indent=2), "```", "",
              "## Ausgelassene Ausführungen", ""]
    skip_labels = {"price_moved": "Kaufpreis über Limit", "position_limit": "Position bereits offen",
                   "budget": "Budget unzureichend", "market_ending": "Marktschluss zu nahe",
                   "entry_no_book": "Einstiegsbuch fehlt oder ist veraltet",
                   "exit_no_book": "Ausstiegsbuch fehlt oder ist veraltet", "entry_depth": "Kauftiefe unzureichend",
                   "exit_depth": "Verkaufstiefe unzureichend", "ai_abstain": "AI enthält sich oder lehnt ab",
                   "ai_input_changed": "AI-Eingabedaten verändert", "enter_unknown_fee": "Einstiegsgebühr unbekannt",
                   "exit_unknown_fee": "Ausstiegsgebühr unbekannt"}
    for arm in arms:
        reasons = "; ".join(f"{skip_labels.get(key, key)}: {count}" for key, count in sorted(arm["skips"].items()))
        lines.append(f"- {modes[arm['mode']]} {arm['latency_ms']:g} ms: {reasons or 'keine'}.")
    (run / f"{name}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    record = commands.add_parser("record", help="Öffentliche Daten aufzeichnen und anschliessend simulieren")
    record.add_argument("--duration", type=float, default=300)
    record.add_argument("--out", type=Path, default=DEFAULT_ROOT)
    repeat = commands.add_parser("replay", help="Bestehende Aufzeichnung erneut simulieren")
    repeat.add_argument("--run", type=Path, required=True)
    repeat.add_argument("--decisions", type=Path)
    score = commands.add_parser("score", help="Optionaler Jev-Vergleich, benötigt TYPESAFE_API_KEY")
    score.add_argument("--run", type=Path, required=True)
    score.add_argument("--max-calls", type=int, default=20)
    score.add_argument("--model", default="jev-latest")
    for sub in (record, repeat):
        sub.add_argument("--latencies", default="100,250,500,1000")
        for name, field in Config.__dataclass_fields__.items():
            sub.add_argument("--" + name.replace("_", "-"), type=str if name == "signal_source" else float,
                             default=field.default)
    args = parser.parse_args()
    if args.command == "score":
        from src.cex_decision import score_run
        print(json.dumps(score_run(args.run, args.max_calls, args.model)))
        return
    config = Config(**{name: getattr(args, name) for name in Config.__dataclass_fields__})
    latencies = [float(value) for value in args.latencies.split(",")]
    if not latencies or len(latencies) > 20 or any(not math.isfinite(x) or x < 0 for x in latencies):
        parser.error("Use 1 to 20 finite, nonnegative execution delays")
    if args.command == "record":
        from src.cex_leadlag_feed import record_run
        run = record_run(args.out, args.duration)
        decisions = None
    else:
        run = args.run
        decisions = None
        if args.decisions:
            from src.cex_decision import load_decisions
            decisions = load_decisions(args.decisions, run)
    result = write_report(run, config, latencies, decisions)
    print(json.dumps({"run": str(run), "results": [{"mode": a["mode"], "latency_ms": a["latency_ms"],
                                                  **a["summary"]} for a in result["arms"]]}, indent=2))


if __name__ == "__main__":
    main()
