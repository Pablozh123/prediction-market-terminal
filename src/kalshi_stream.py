"""Event-driven Kalshi recorder: seconds instead of two minutes.

``src/kalshi_recorder.py`` polls REST every two minutes, which is enough to
compare price levels across venues but useless for the question that matters
in cross-venue work: not how large a gap is, but how long it stays open. That
needs the socket.

Three things differ from the Polymarket stream recorder and each one is a way
to corrupt a book silently if it is got wrong.

Deltas are changes, not sizes. Polymarket sends the new size at a price level;
Kalshi sends the amount by which that level changed, positive or negative. The
same code applied to both feeds would drift within seconds.

Price scale is pinned. The subscription sends ``use_yes_price: true``, so both
sides arrive in YES pricing and the no side needs no reflection. Kalshi has
announced this default will flip; a client that relies on the default has its
whole book silently re-scaled on that date, with no error and no gap.

Sequence numbers must be checked, and acted on. The counter runs per
subscription, so a gap invalidates every book at once. Kalshi sends snapshots
only at subscribe time, so the recorder explicitly asks for fresh ones instead
of waiting out the connection cycle.

Authentication is read-only by construction: the handshake is signed through
``app/kalshi_auth.py``, which refuses anything but GET and blocks every
portfolio and order path. Even a key with trading rights cannot send an order
through this module.

Outputs under ``data/microstructure/``, day-partitioned, append-only, in the
same column layout as every other recorder here.

Run:  python -m src.kalshi_stream --duration 300 --top-n 20
Loop: python scripts/run_kalshi_stream.py
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from app import kalshi_auth as auth
from app import proc_lock
from app import watchlist
from app.proc_lock import AlreadyRunning
from src import book_recorder as rec
from src import kalshi_stream_state as state_mod
from src import kalshi_recorder as kx

WS_URL = "wss://api.elections.kalshi.com/trade-api/ws/v2"
WS_PATH = "/trade-api/ws/v2"

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT_DIR = REPO_ROOT / "data" / "microstructure"

TOP_N_MARKETS = 20
RECV_TIMEOUT_S = 5.0
STALE_AFTER_S = 90.0
MAX_BACKOFF_S = 60.0

STREAM_BOOK_FIELDS = [
    "recv_ts", "seq", "market_id", "event_type", "best_bid", "best_ask",
    "spread", "mid", "bid_usd_top", "ask_usd_top", "imbalance_top",
    "bid_size_touch", "ask_size_touch", "bid_levels", "ask_levels",
]
STREAM_TRADE_FIELDS = [
    "recv_ts", "exchange_ts", "market_id", "side", "price", "size", "trade_id",
]

BookState = state_mod.BookState
StreamState = state_mod.StreamState


def utc_now_iso(now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def subscribe_message(tickers: list[str], msg_id: int = 1) -> dict:
    """Subscribe to book deltas and trades for the given markets.

    ``use_yes_price`` is sent explicitly and must stay that way. By default the
    two sides of a Kalshi book arrive on different price scales, and Kalshi has
    announced the default will flip to true. A client that relies on the
    default gets its whole book silently re-scaled on the flip date: every ask,
    spread and mid inverts, with no error and no sequence gap to notice it by.
    Pinning the flag makes this code independent of when that happens.
    """
    return {
        "id": msg_id,
        "cmd": "subscribe",
        "params": {
            "channels": ["orderbook_delta", "trade"],
            "market_tickers": [str(t) for t in tickers],
            "use_yes_price": True,
        },
    }


def resnapshot_message(sid, tickers: list[str], msg_id: int = 2) -> dict:
    """Ask for fresh snapshots after a sequence gap.

    Kalshi only sends a snapshot at subscribe time, so without this a single
    dropped message costs every book until the connection cycles - up to ten
    minutes of recorded silence from one lost frame.
    """
    return {
        "id": msg_id,
        "cmd": "update_subscription",
        "params": {
            "sids": [sid],
            "action": "get_snapshot",
            "market_tickers": [str(t) for t in tickers],
        },
    }


def backoff_delay(attempt: int, base: float = 2.0,
                  cap: float = MAX_BACKOFF_S) -> float:
    if attempt <= 0:
        return 1.0
    return float(min(cap, base ** min(attempt, 10)))


def parse_payload(raw: str) -> list[dict]:
    text = (raw or "").strip()
    if not text:
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


def _default_ws_factory(url: str, headers: dict[str, str]):
    import websocket  # lokal, damit Tests ohne die Abhaengigkeit laufen

    return websocket.create_connection(
        url, timeout=RECV_TIMEOUT_S,
        header=[f"{key}: {value}" for key, value in headers.items()])


def handshake_headers(credentials, now_ms: int | None = None) -> dict[str, str]:
    """Signed headers for the socket handshake. GET only, no order path."""
    timestamp = now_ms if now_ms is not None else int(time.time() * 1000)
    return auth.auth_headers(credentials, "GET", WS_PATH, timestamp)


def stream_once(tickers: list[str], out_dir: Path, duration_s: float,
                credentials, ws_factory=_default_ws_factory, url: str = WS_URL,
                now_fn=time.monotonic, flush_every_s: float = 15.0) -> dict:
    """Connect, subscribe, and record until ``duration_s`` elapses."""
    out_dir = Path(out_dir)
    state = StreamState()
    started = now_fn()
    deadline = started + float(duration_s)
    last_flush = started
    last_message = started
    errors: list[str] = []
    written = {"book_rows": 0, "trade_rows": 0, "messages": 0}
    resyncs = {"n": 0}

    try:
        socket = ws_factory(url, handshake_headers(credentials))
    except Exception as exc:  # noqa: BLE001 - Verbindungsfehler ist ein Ergebnis
        return {"connected": False, "error": f"{type(exc).__name__}: {exc}",
                "book_rows": 0, "trade_rows": 0, "messages": 0,
                "markets": len(tickers), "event_counts": {}, "seq_gaps": 0,
                "resnapshots_requested": 0, "crossed_books": 0}

    def flush() -> None:
        nonlocal last_flush
        books, trades = state.drain()
        if books or trades:
            day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            rec.append_csv(out_dir / f"kalshi_stream_books_{day}.csv",
                           STREAM_BOOK_FIELDS, books)
            rec.append_csv(out_dir / f"kalshi_stream_trades_{day}.csv",
                           STREAM_TRADE_FIELDS, trades)
            written["book_rows"] += len(books)
            written["trade_rows"] += len(trades)
        last_flush = now_fn()

    try:
        socket.send(json.dumps(subscribe_message(tickers)))
        while now_fn() < deadline:
            try:
                raw = socket.recv()
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
                for event in parse_payload(raw):
                    state.handle(event, recv_ts)
                if state.needs_resync:
                    # Nach einer Sequenzluecke sind alle Buecher ungueltig.
                    # Kalshi schickt Snapshots nur beim Subscribe, also muss
                    # man sie ausdruecklich anfordern.
                    state.needs_resync = False
                    if state.sid is not None:
                        try:
                            socket.send(json.dumps(
                                resnapshot_message(state.sid, tickers)))
                            resyncs["n"] += 1
                        except Exception as exc:  # noqa: BLE001
                            errors.append(f"resync failed: {type(exc).__name__}: {exc}")
                            break
            if tick - last_message > STALE_AFTER_S:
                errors.append("stale: no message within STALE_AFTER_S")
                break
            if tick - last_flush >= flush_every_s:
                flush()
    finally:
        flush()
        try:
            socket.close()
        except Exception:  # noqa: BLE001
            pass

    return {
        "connected": True,
        "markets": len(tickers),
        "seconds": round(now_fn() - started, 1),
        "messages": written["messages"],
        "book_rows": written["book_rows"],
        "trade_rows": written["trade_rows"],
        "event_counts": dict(state.counts),
        "seq_gaps": state.seq_gaps,
        "resnapshots_requested": resyncs["n"],
        "crossed_books": state.crossed_books,
        "errors": errors,
    }


def write_status(out_dir: Path, summary: dict) -> None:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = dict(summary)
    payload["ts_utc"] = utc_now_iso()
    with open(out_dir / "kalshi_stream_status.json", "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)


def run(out_dir: Path | None = None, duration_s: float = 600.0,
        top_n: int = TOP_N_MARKETS, loop: bool = False,
        ws_factory=_default_ws_factory, get_json=kx._get_json,
        credentials=None) -> dict:
    """Record for ``duration_s``; with ``loop`` keep reconnecting."""
    out_dir = Path(out_dir or DEFAULT_OUT_DIR)
    if credentials is None:
        auth.load_from_env_files()
        credentials = auth.load_credentials()
    lock = proc_lock.acquire(out_dir, "kalshi_stream.lock")
    attempt = 0
    tickers: list[str] = []
    summary: dict = {}
    try:
        while True:
            if not tickers:
                markets = kx.discover_markets(get_json=get_json, top_n=top_n)
                # Cross-Venue-Paare ranken nie nach Volumen; ohne das Pinning
                # werden sie nie aufgezeichnet.
                tickers = watchlist.merge_pinned(
                    watchlist.kalshi_tickers(),
                    [m["ticker"] for m in markets], top_n)
            summary = stream_once(tickers, out_dir, duration_s, credentials,
                                  ws_factory=ws_factory)
            write_status(out_dir, summary)
            print(f"[kalshi-stream] {summary}", flush=True)
            if not loop:
                return summary
            attempt = 0 if summary.get("messages") else attempt + 1
            if attempt:
                tickers = []
            time.sleep(backoff_delay(attempt) if attempt else 1.0)
    finally:
        proc_lock.release(lock)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--duration", type=float, default=600.0)
    parser.add_argument("--top-n", type=int, default=TOP_N_MARKETS)
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    args = parser.parse_args(argv)

    try:
        summary = run(out_dir=Path(args.out_dir), duration_s=args.duration,
                      top_n=args.top_n, loop=args.loop)
    except auth.CredentialError as exc:
        print(f"[kalshi-stream] {exc}", flush=True)
        return 2
    except AlreadyRunning as exc:
        print(f"[kalshi-stream] {exc}", flush=True)
        return 1
    if not args.loop:
        print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
