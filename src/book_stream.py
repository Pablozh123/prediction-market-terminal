"""Event-driven Polymarket book recorder (seconds instead of minutes).

``src/book_recorder.py`` polls REST every 120 seconds. That resolution answers
the five-minute drift question but says nothing about the seconds-scale
questions microstructure actually lives on: how long a stale quote survives
after a large print, how fast a book reacts to a trade, whether an imbalance
persists or flickers.

This module subscribes to the public CLOB market channel instead, keeps a full
book per token from the snapshot plus the price-change deltas, and appends a
row whenever the top of book actually moves. It also records the trade stream,
which - unlike the REST tape - carries the aggressor side per print, so signed
order flow becomes computable.

Outputs under ``data/microstructure/`` (gitignored), day-partitioned,
append-only:

  stream_books_<day>.csv   top of book on every change, with local receive time
  stream_depth_<day>.csv   the top levels with sizes on every such change, so a
                           queue-position fill model knows what rests at a price
  stream_trades_<day>.csv  last_trade_price events incl. aggressor side
  stream_raw_<day>.jsonl   optional verbatim archive (--raw)
  stream_status.json       last run summary

Public endpoints only: no order path, no credentials, no wallet columns.

Run:  python -m src.book_stream --duration 300 --top-n 40
Loop: python scripts/run_book_stream.py
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from app import proc_lock
from app import watchlist
from app.proc_lock import AlreadyRunning
from src import book_recorder as rec

_pid_alive = proc_lock.pid_alive

WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT_DIR = REPO_ROOT / "data" / "microstructure"

TOP_N_MARKETS = 40
DEPTH_LEVELS = 5
PING_INTERVAL_S = 10.0
RECV_TIMEOUT_S = 5.0
#: Der Server beendet stille Verbindungen; nach so langer Stille neu verbinden.
STALE_AFTER_S = 90.0
MAX_BACKOFF_S = 60.0

STREAM_BOOK_FIELDS = [
    "recv_ts", "exchange_ts", "token_id", "event_type", "best_bid", "best_ask",
    "spread", "mid", "bid_usd_top", "ask_usd_top", "imbalance_top",
    "bid_size_touch", "ask_size_touch", "bid_levels", "ask_levels",
]
STREAM_TRADE_FIELDS = [
    "recv_ts", "exchange_ts", "token_id", "side", "price", "size", "tx_hash",
]
#: Sidecar mit den obersten Stufen je Seite. Eigene Datei statt neuer Spalten
#: in stream_books, damit ein laufender Tag sein Schema behaelt und jeder
#: bisherige Leser unveraendert weiterlaeuft. Join-Schluessel: recv_ts + token_id.
STREAM_DEPTH_LEVELS = 5
STREAM_DEPTH_FIELDS = ["recv_ts", "token_id", "event_type"] + [
    f"{side}_{kind}_{level}"
    for side in ("bid", "ask")
    for level in range(1, STREAM_DEPTH_LEVELS + 1)
    for kind in ("px", "sz")
]


def utc_now_iso(now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def subscribe_message(token_ids: list[str]) -> dict:
    """Subscription frame for the public market channel."""
    return {"assets_ids": [str(t) for t in token_ids], "type": "market"}


def backoff_delay(attempt: int, base: float = 2.0,
                  cap: float = MAX_BACKOFF_S) -> float:
    """Exponential backoff, capped. Attempt 0 retries immediately-ish."""
    if attempt <= 0:
        return 1.0
    return float(min(cap, base ** min(attempt, 10)))


class BookState:
    """Full book for one token, kept from a snapshot plus price-change deltas.

    Prices are dict keys so a delta is an assignment and a zero size is a
    deletion, which is exactly the semantics the venue sends.
    """

    __slots__ = ("bids", "asks", "last_exchange_ts")

    def __init__(self) -> None:
        self.bids: dict[float, float] = {}
        self.asks: dict[float, float] = {}
        self.last_exchange_ts: str | None = None

    def apply_snapshot(self, bids: list, asks: list) -> None:
        self.bids = self._parse_levels(bids)
        self.asks = self._parse_levels(asks)

    @staticmethod
    def _parse_levels(levels: list) -> dict[float, float]:
        out: dict[float, float] = {}
        for level in levels or []:
            try:
                if isinstance(level, dict):
                    price = float(level["price"])
                    size = float(level["size"])
                else:
                    price, size = float(level[0]), float(level[1])
            except (KeyError, TypeError, ValueError, IndexError):
                continue
            if size > 0:
                out[round(price, 6)] = size
        return out

    def apply_change(self, price: float, size: float, side: str) -> None:
        """One level update. ``size == 0`` removes the level."""
        try:
            price = round(float(price), 6)
            size = float(size)
        except (TypeError, ValueError):
            return
        book = self.bids if str(side).upper().startswith("B") else self.asks
        if size <= 0:
            book.pop(price, None)
        else:
            book[price] = size

    def best_bid(self) -> float | None:
        return max(self.bids) if self.bids else None

    def best_ask(self) -> float | None:
        return min(self.asks) if self.asks else None

    def depth_usd(self, levels: int = DEPTH_LEVELS) -> tuple[float, float]:
        """USD sitting in the top ``levels`` of each side."""
        bid_prices = sorted(self.bids, reverse=True)[:levels]
        ask_prices = sorted(self.asks)[:levels]
        bid_usd = sum(p * self.bids[p] for p in bid_prices)
        ask_usd = sum(p * self.asks[p] for p in ask_prices)
        return round(bid_usd, 4), round(ask_usd, 4)

    def touch_signature(self) -> tuple:
        """What counts as a top-of-book change worth writing a row for."""
        bid, ask = self.best_bid(), self.best_ask()
        return (bid, ask,
                self.bids.get(bid) if bid is not None else None,
                self.asks.get(ask) if ask is not None else None)

    def depth_row(self, recv_ts: str, event_type: str,
                  levels: int = STREAM_DEPTH_LEVELS) -> dict:
        """The top ``levels`` of each side with sizes, best first.

        The books row carries only the size at the touch. A resting order one
        tick behind the touch has no observable queue in that row, and that
        is the case a paper market maker at mid minus a half spread is in
        most of the time. Levels beyond what the book holds stay empty.
        """
        bid_prices = sorted(self.bids, reverse=True)[:levels]
        ask_prices = sorted(self.asks)[:levels]
        row: dict = {"recv_ts": recv_ts, "token_id": "", "event_type": event_type}
        for index in range(1, levels + 1):
            bid = bid_prices[index - 1] if index <= len(bid_prices) else None
            ask = ask_prices[index - 1] if index <= len(ask_prices) else None
            row[f"bid_px_{index}"] = bid
            row[f"bid_sz_{index}"] = self.bids[bid] if bid is not None else None
            row[f"ask_px_{index}"] = ask
            row[f"ask_sz_{index}"] = self.asks[ask] if ask is not None else None
        return row

    def top_row(self, recv_ts: str, event_type: str,
                levels: int = DEPTH_LEVELS) -> dict:
        bid, ask = self.best_bid(), self.best_ask()
        bid_usd, ask_usd = self.depth_usd(levels)
        total = bid_usd + ask_usd
        spread = round(ask - bid, 6) if bid is not None and ask is not None else None
        mid = round((ask + bid) / 2.0, 6) if bid is not None and ask is not None else None
        return {
            "recv_ts": recv_ts,
            "exchange_ts": self.last_exchange_ts,
            "token_id": "",
            "event_type": event_type,
            "best_bid": bid,
            "best_ask": ask,
            "spread": spread,
            "mid": mid,
            "bid_usd_top": bid_usd,
            "ask_usd_top": ask_usd,
            "imbalance_top": round(bid_usd / total, 6) if total > 0 else None,
            "bid_size_touch": self.bids.get(bid) if bid is not None else None,
            "ask_size_touch": self.asks.get(ask) if ask is not None else None,
            "bid_levels": len(self.bids),
            "ask_levels": len(self.asks),
        }


class StreamState:
    """All books plus the rows produced so far. Pure: no socket, no files."""

    def __init__(self, depth_levels: int = DEPTH_LEVELS) -> None:
        self.books: dict[str, BookState] = {}
        self.depth_levels = depth_levels
        self.book_rows: list[dict] = []
        self.depth_rows: list[dict] = []
        self.trade_rows: list[dict] = []
        self.counts: dict[str, int] = {}
        self._last_touch: dict[str, tuple] = {}

    def _book(self, token_id: str) -> BookState:
        return self.books.setdefault(token_id, BookState())

    def _emit_if_touch_moved(self, token_id: str, recv_ts: str,
                             event_type: str) -> None:
        book = self._book(token_id)
        signature = book.touch_signature()
        if self._last_touch.get(token_id) == signature:
            return
        self._last_touch[token_id] = signature
        row = book.top_row(recv_ts, event_type, self.depth_levels)
        row["token_id"] = token_id
        self.book_rows.append(row)
        depth = book.depth_row(recv_ts, event_type)
        depth["token_id"] = token_id
        self.depth_rows.append(depth)

    def handle(self, event: dict, recv_ts: str) -> None:
        """Fold one venue event into the state. Unknown types are counted only."""
        if not isinstance(event, dict):
            return
        event_type = str(event.get("event_type") or "")
        self.counts[event_type or "unknown"] = self.counts.get(event_type or "unknown", 0) + 1

        if event_type == "book":
            token_id = str(event.get("asset_id") or "")
            if not token_id:
                return
            book = self._book(token_id)
            book.apply_snapshot(event.get("bids"), event.get("asks"))
            book.last_exchange_ts = event.get("timestamp")
            self._emit_if_touch_moved(token_id, recv_ts, "book")

        elif event_type == "price_change":
            timestamp = event.get("timestamp")
            touched: list[str] = []
            for change in event.get("price_changes") or []:
                if not isinstance(change, dict):
                    continue
                token_id = str(change.get("asset_id") or "")
                if not token_id:
                    continue
                book = self._book(token_id)
                book.apply_change(change.get("price"), change.get("size"),
                                  change.get("side"))
                book.last_exchange_ts = timestamp
                if token_id not in touched:
                    touched.append(token_id)
            for token_id in touched:
                self._emit_if_touch_moved(token_id, recv_ts, "price_change")

        elif event_type == "last_trade_price":
            token_id = str(event.get("asset_id") or "")
            if not token_id:
                return
            self.trade_rows.append({
                "recv_ts": recv_ts,
                "exchange_ts": event.get("timestamp"),
                "token_id": token_id,
                "side": event.get("side"),
                "price": event.get("price"),
                "size": event.get("size"),
                "tx_hash": event.get("transaction_hash"),
            })

    def drain(self) -> tuple[list[dict], list[dict]]:
        """Hand over accumulated rows and start collecting fresh ones."""
        books, trades = self.book_rows, self.trade_rows
        self.book_rows, self.trade_rows = [], []
        return books, trades

    def drain_depth(self) -> list[dict]:
        """Hand over the depth sidecar rows collected since the last drain."""
        depth = self.depth_rows
        self.depth_rows = []
        return depth


def parse_payload(raw: str) -> list[dict]:
    """Venue frames arrive as a single object, a list, or a bare PONG."""
    text = (raw or "").strip()
    if not text or text.upper() in {"PONG", "PING"}:
        return []
    try:
        parsed = json.loads(text)
    except (TypeError, ValueError):
        return []
    if isinstance(parsed, list):
        return [item for item in parsed if isinstance(item, dict)]
    if isinstance(parsed, dict):
        return [parsed]
    return []


def select_stream_tokens(get_json=rec._get_json, top_n: int = TOP_N_MARKETS) -> list[dict]:
    """Reuse the REST recorder's market selection so both feeds cover the same set."""
    tracked = rec.select_markets(rec.fetch_active_markets(get_json=get_json),
                                 top_n=top_n, priority_slots=0)
    tokens: list[dict] = []
    for entry in tracked:
        for outcome, token_id in entry["tokens"]:
            tokens.append({
                "token_id": token_id,
                "market_id": entry["market_id"],
                "slug": entry["slug"],
                "outcome": outcome,
            })
    return tokens


def _flush(out_dir: Path, day: str, books: list[dict], trades: list[dict],
           raw_lines: list[str] | None = None,
           depth: list[dict] | None = None) -> None:
    rec.append_csv(out_dir / f"stream_books_{day}.csv", STREAM_BOOK_FIELDS, books)
    rec.append_csv(out_dir / f"stream_trades_{day}.csv", STREAM_TRADE_FIELDS, trades)
    if depth:
        rec.append_csv(out_dir / f"stream_depth_{day}.csv", STREAM_DEPTH_FIELDS, depth)
    if raw_lines:
        path = out_dir / f"stream_raw_{day}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write("\n".join(raw_lines) + "\n")


def _default_ws_factory(url: str):
    import websocket  # lokal, damit Tests ohne die Abhaengigkeit laufen

    return websocket.create_connection(url, timeout=RECV_TIMEOUT_S)


def stream_once(token_ids: list[str], out_dir: Path, duration_s: float,
                ws_factory=_default_ws_factory, url: str = WS_URL,
                keep_raw: bool = False, now_fn=time.monotonic,
                flush_every_s: float = 15.0) -> dict:
    """Connect, subscribe, and record until ``duration_s`` elapses.

    One connection attempt only; the retry loop lives in :func:`run`. Returns a
    summary dict. Never raises for socket trouble - it reports it instead, so a
    daemon can decide whether to reconnect.
    """
    out_dir = Path(out_dir)
    state = StreamState()
    started = now_fn()
    deadline = started + float(duration_s)
    last_ping = started
    last_flush = started
    last_message = started
    raw_buffer: list[str] = []
    errors: list[str] = []
    written = {"book_rows": 0, "trade_rows": 0, "depth_rows": 0, "messages": 0}

    try:
        ws = ws_factory(url)
    except Exception as exc:  # noqa: BLE001 - Verbindungsfehler ist ein Ergebnis
        return {"connected": False, "error": f"{type(exc).__name__}: {exc}",
                "book_rows": 0, "trade_rows": 0, "messages": 0,
                "tokens": len(token_ids), "event_counts": {}}

    def flush(force: bool = False) -> None:
        nonlocal last_flush, raw_buffer
        books, trades = state.drain()
        depth = state.drain_depth()
        if books or trades or (force and raw_buffer):
            day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            _flush(out_dir, day, books, trades, raw_buffer if keep_raw else None,
                   depth=depth)
            written["book_rows"] += len(books)
            written["trade_rows"] += len(trades)
            written["depth_rows"] += len(depth)
            raw_buffer = []
        last_flush = now_fn()

    try:
        ws.send(json.dumps(subscribe_message(token_ids)))
        while now_fn() < deadline:
            try:
                raw = ws.recv()
            except Exception as exc:  # noqa: BLE001 - Timeout ist der Normalfall
                name = type(exc).__name__
                if "Timeout" not in name:
                    errors.append(f"{name}: {exc}")
                    break
                raw = ""
            tick = now_fn()
            if raw:
                last_message = tick
                written["messages"] += 1
                recv_ts = utc_now_iso()
                if keep_raw:
                    raw_buffer.append(json.dumps(
                        {"recv_ts": recv_ts, "payload": raw}, ensure_ascii=False))
                for event in parse_payload(raw):
                    state.handle(event, recv_ts)
            if tick - last_ping >= PING_INTERVAL_S:
                try:
                    ws.send("PING")
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"ping failed: {type(exc).__name__}: {exc}")
                    break
                last_ping = tick
            if tick - last_message > STALE_AFTER_S:
                errors.append("stale: no message within STALE_AFTER_S")
                break
            if tick - last_flush >= flush_every_s:
                flush()
    finally:
        flush(force=True)
        try:
            ws.close()
        except Exception:  # noqa: BLE001 - close darf den Lauf nicht kippen
            pass

    return {
        "connected": True,
        "tokens": len(token_ids),
        "seconds": round(now_fn() - started, 1),
        "messages": written["messages"],
        "book_rows": written["book_rows"],
        "trade_rows": written["trade_rows"],
        "depth_rows": written["depth_rows"],
        "event_counts": dict(state.counts),
        "errors": errors,
    }


def acquire_lock(out_dir: Path) -> Path:
    """Claim the output directory so a second instance cannot corrupt the files."""
    return proc_lock.acquire(out_dir, "stream_recorder.lock")


def release_lock(lock: Path) -> None:
    return proc_lock.release(lock)


def write_status(out_dir: Path, summary: dict) -> None:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = dict(summary)
    payload["ts_utc"] = utc_now_iso()
    with open(out_dir / "stream_status.json", "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)


def run(out_dir: Path | None = None, duration_s: float = 300.0,
        top_n: int = TOP_N_MARKETS, loop: bool = False, keep_raw: bool = False,
        ws_factory=_default_ws_factory, get_json=rec._get_json,
        refresh_tokens_each_cycle: bool = True) -> dict:
    """Record for ``duration_s``; with ``loop`` keep reconnecting forever."""
    out_dir = Path(out_dir or DEFAULT_OUT_DIR)
    lock = acquire_lock(out_dir)
    try:
        return _run_locked(out_dir, duration_s, top_n, loop, keep_raw,
                           ws_factory, get_json, refresh_tokens_each_cycle)
    finally:
        release_lock(lock)


def _run_locked(out_dir: Path, duration_s: float, top_n: int, loop: bool,
                keep_raw: bool, ws_factory, get_json,
                refresh_tokens_each_cycle: bool) -> dict:
    attempt = 0
    tokens: list[dict] = []
    summary: dict = {}
    while True:
        if not tokens or refresh_tokens_each_cycle:
            try:
                tokens = select_stream_tokens(get_json=get_json, top_n=top_n)
            except Exception as exc:  # noqa: BLE001
                summary = {"connected": False,
                           "error": f"token selection failed: {exc}"}
                write_status(out_dir, summary)
                if not loop:
                    return summary
                time.sleep(backoff_delay(attempt))
                attempt += 1
                continue
        # Gepinnte Cross-Venue-Token zuerst, dann die Volumen-Auswahl.
        subscribed = watchlist.merge_pinned(
            watchlist.polymarket_token_ids(),
            [t["token_id"] for t in tokens], max(1, 2 * top_n))
        summary = stream_once(subscribed, out_dir, duration_s,
                              ws_factory=ws_factory, keep_raw=keep_raw)
        summary["tracked_tokens"] = len(tokens)
        write_status(out_dir, summary)
        print(f"[stream] {summary}", flush=True)
        if not loop:
            return summary
        attempt = 0 if summary.get("connected") and summary.get("messages") else attempt + 1
        delay = backoff_delay(attempt) if attempt else 1.0
        time.sleep(delay)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--duration", type=float, default=300.0,
                        help="seconds per connection cycle")
    parser.add_argument("--top-n", type=int, default=TOP_N_MARKETS)
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--raw", action="store_true",
                        help="also archive verbatim frames as JSONL")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    args = parser.parse_args(argv)

    try:
        summary = run(out_dir=Path(args.out_dir), duration_s=args.duration,
                      top_n=args.top_n, loop=args.loop, keep_raw=args.raw)
    except AlreadyRunning as exc:
        print(f"[stream] {exc}", flush=True)
        return 1
    if not args.loop:
        print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
