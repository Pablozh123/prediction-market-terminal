"""Public BTC feed capture. Normalized full depth, monotonic receipt timestamps.

Binance BTC/USDT and Coinbase BTC/USD returns are kept separate. Gamma provides
market rules and fee schedules; neither CEX is treated as the resolution oracle.
"""
from __future__ import annotations

import hashlib
import json
import math
import queue
import threading
import time
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import requests
import websocket

from app import proc_lock
from src.book_stream import WS_URL, subscribe_message

GAMMA = "https://gamma-api.polymarket.com/markets"
URLS = {"binance": "wss://stream.binance.com:9443/ws/btcusdt@aggTrade",
        "coinbase": "wss://ws-feed.exchange.coinbase.com", "polymarket": WS_URL}


def number(value, low=0, high=math.inf):
    if isinstance(value, bool):
        raise ValueError("Boolean feed number")
    value = float(value)
    if not math.isfinite(value) or not low <= value <= high:
        raise ValueError("Out-of-range feed number")
    return value


def parse_cex(source: str, payload: dict) -> dict | None:
    try:
        if source == "binance" and payload.get("e") == "aggTrade" and payload.get("s") == "BTCUSDT":
            price, pair, stamp = payload["p"], "BTCUSDT", payload.get("T")
        elif source == "coinbase" and payload.get("type") == "ticker" and payload.get("product_id") == "BTC-USD":
            price, pair, stamp = payload["price"], "BTC-USD", payload.get("time")
        else:
            return None
        return {"kind": "price", "source": source, "pair": pair,
                "price": number(price, .01, 100_000_000), "exchange_ts": stamp}
    except (ValueError, TypeError, KeyError):
        return None


def parse_market(payload: dict, interval_s: int) -> dict | None:
    """Map labels explicitly. Unsupported fees stay unknown and cannot trade."""
    try:
        if not payload.get("active") or payload.get("closed") or not payload.get("acceptingOrders"):
            return None
        labels = payload["outcomes"]
        labels = json.loads(labels) if isinstance(labels, str) else labels
        version = payload.get("version", "v1")
        if version not in {"v1", "v2"}:
            return None
        tokens = payload["positionIds"] if version == "v2" else payload["clobTokenIds"]
        tokens = json.loads(tokens) if isinstance(tokens, str) else tokens
        if len(labels) != 2 or set(labels) != {"Up", "Down"} or len(tokens) != 2:
            return None
        if any(not isinstance(token, str) or not 0 < len(token) <= 120 for token in tokens):
            return None
        end = datetime.fromisoformat(payload["endDate"].replace("Z", "+00:00")).timestamp()
        rate = None
        schedule = payload.get("feeSchedule") or {}
        if payload.get("feesEnabled") is False:
            rate = 0.
        elif payload.get("feesEnabled") is True and schedule.get("exponent") == 1:
            rate = number(schedule["rate"], 0, 1)
        return {"id": str(payload["id"]), "slug": payload["slug"], "version": version,
                "start_s": end - interval_s, "end_s": end, "tokens": dict(zip(labels, tokens)),
                "fee_rate": rate, "fee_schedule": schedule,
                "resolution_source": payload.get("resolutionSource"), "rules": payload.get("description", "")}
    except (ValueError, TypeError, KeyError, AttributeError):
        return None


def parse_polymarket(payload: dict) -> list[dict]:
    """Reject an entire corrupt depth event rather than retaining partial levels."""
    try:
        kind = payload.get("event_type")
        stamp = payload.get("timestamp")
        if kind == "book":
            def levels(side):
                return [[number(item["price"], 0, 1), number(item["size"], 0)] for item in payload[side]]
            return [{"kind": "book", "source": "polymarket", "token": str(payload["asset_id"]),
                     "snapshot": True, "bids": levels("bids"), "asks": levels("asks"), "exchange_ts": stamp}]
        if kind == "price_change":
            changes = {}
            for change in payload["price_changes"]:
                if change["side"] not in {"BUY", "SELL"}:
                    return []
                level = [number(change["price"], 0, 1), number(change["size"], 0), change["side"]]
                changes.setdefault(str(change["asset_id"]), []).append(level)
            return [{"kind": "book", "source": "polymarket", "token": token, "snapshot": False,
                     "changes": values, "exchange_ts": stamp} for token, values in changes.items()]
    except (ValueError, TypeError, KeyError, AttributeError):
        return []
    return []


def discover(now: float | None = None, stop=None) -> list[dict]:
    now = time.time() if now is None else now
    markets = []
    for interval in (300, 900):
        start = int(now // interval) * interval
        for offset in (0, interval):
            if stop is not None and stop.is_set():
                raise InterruptedError("Discovery stopped")
            slug = f"btc-updown-{interval // 60}m-{start + offset}"
            response = requests.get(GAMMA, params={"slug": slug}, timeout=8)
            response.raise_for_status()
            if len(response.content) > 2_000_000:
                raise ValueError("Oversized Gamma response")
            data = response.json()
            if not isinstance(data, list):
                raise ValueError("Unexpected Gamma response")
            for payload in data:
                market = parse_market(payload, interval)
                if market and market["slug"] == slug:
                    markets.append(market)
    if not markets:
        raise ValueError("No active BTC 5m/15m contracts discovered")
    return markets


class FeedClosed(ConnectionError):
    """Preserve the public server close reason without logging request details."""
    def __init__(self, payload: bytes):
        self.code = int.from_bytes(payload[:2], "big") if len(payload) >= 2 else None
        self.reason = payload[2:].decode("utf-8")[:123]
        super().__init__("Feed closed")


def decode_frame(opcode: int, payload: bytes) -> str | None:
    if opcode == websocket.ABNF.OPCODE_CLOSE:
        raise FeedClosed(payload)
    if opcode in {websocket.ABNF.OPCODE_PING, websocket.ABNF.OPCODE_PONG}:
        return None  # websocket-client already answers protocol PING frames.
    if opcode != websocket.ABNF.OPCODE_TEXT or not payload or len(payload) > 8_000_000:
        raise ValueError("Invalid or oversized text frame")
    # Strict native decoding replaces the library's redundant Python byte scan.
    return payload.decode("utf-8")


def stream_connection(source, socket, stop, emit, get_markets=None):
    """Receive continuously; discovery runs separately and never blocks recv."""
    markets, tokens = None, set()
    last_message = last_ping = last_check = time.monotonic()
    ping_ns = None

    def refresh():
        nonlocal markets, tokens
        latest = get_markets()
        if latest is markets:
            return
        new = {token for market in latest for token in market["tokens"].values()}
        added, removed = sorted(new - tokens), sorted(tokens - new)
        if markets is None:
            socket.send(json.dumps(subscribe_message(sorted(new))))
        else:
            for ids, operation in ((added, "subscribe"), (removed, "unsubscribe")):
                if ids:
                    socket.send(json.dumps({"assets_ids": ids, "operation": operation}))
        emit([{"kind": "market", "market": market} for market in latest])
        if added or removed:
            emit([{"kind": "subscription", "source": source,
                   "added": added, "removed": removed, "initial": markets is None}])
        markets, tokens = latest, new

    if source == "polymarket":
        refresh()
    elif source == "coinbase":
        socket.send(json.dumps({"type": "subscribe", "product_ids": ["BTC-USD"],
                                "channels": ["ticker", "heartbeat"]}))
    while not stop.is_set():
        now = time.monotonic()
        if source == "polymarket":
            if now - last_check >= 1:
                refresh()
                last_check = now
            if now - last_ping >= 10:
                ping_ns = time.monotonic_ns()
                socket.send("PING")
                last_ping = now
        if now - last_message > 15:
            raise TimeoutError("Feed silent for 15 seconds")
        try:
            opcode, data = socket.recv_data(control_frame=True)
            received = (time.monotonic_ns(), time.time_ns())
        except websocket.WebSocketTimeoutException:
            continue
        raw = decode_frame(opcode, data)
        last_message = time.monotonic()
        if raw is None or raw == "PING":
            continue
        if raw == "PONG":
            if source == "polymarket" and ping_ns is not None:
                emit([{"kind": "heartbeat", "source": source,
                       "rtt_ms": (received[0] - ping_ns) / 1e6}], received)
                ping_ns = None
            continue
        payload = json.loads(raw)
        for item in payload if isinstance(payload, list) else [payload]:
            if not isinstance(item, dict):
                raise ValueError("Non-object feed event")
            if source == "polymarket":
                rows = parse_polymarket(item)
                if not rows and item.get("event_type") in {"book", "price_change"}:
                    raise ValueError("Invalid book event; require fresh snapshot")
            else:
                price = parse_cex(source, item)
                if item.get("type") == "error":
                    raise ValueError("CEX subscription rejected")
                rows = [price] if price else []
            if rows:
                emit(rows, received)


def record_run(root: Path, duration_s: float) -> Path:
    """Bounded capture with reconnects and a single, loss-detecting writer."""
    if not math.isfinite(duration_s) or not 1 <= duration_s <= 3600:
        raise ValueError("duration must be between 1 and 3600 seconds")
    root = Path(root)
    lock = proc_lock.acquire(root)
    run = root / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6])
    run.mkdir()
    stop = threading.Event()
    pending = queue.Queue(maxsize=100_000)
    receipt_lock = threading.Lock()
    market_lock = threading.Lock()
    market_cache = None
    queue_high_water = 0
    counts, errors = Counter(), Counter()
    data_loss = threading.Event()
    start = time.monotonic()
    manifest = {"schema": 1, "status": "recording", "started_utc": datetime.now(timezone.utc).isoformat(),
                "requested_duration_s": duration_s, "data_loss": False,
                "clock": "time.monotonic_ns at local receipt; wall_ns recorded alongside",
                "markets": [], "sources": URLS}
    manifest_path = run / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    def emit(rows, received=None):
        nonlocal queue_high_water
        # Keep the timestamp taken immediately after recv, before JSON parsing.
        # Replay sorts by this clock pair, independent of producer scheduling.
        with receipt_lock:
            tick, wall = received or (time.monotonic_ns(), time.time_ns())
            for row in rows:
                try:
                    pending.put_nowait({"t_ns": tick, "wall_ns": wall, **row})
                except queue.Full:
                    data_loss.set()
                    stop.set()
                    return
            queue_high_water = max(queue_high_water, pending.qsize())

    def current_markets():
        with market_lock:
            return market_cache

    def discovery_worker():
        nonlocal market_cache
        while not stop.is_set():
            try:
                found = discover(stop=stop)
                with market_lock:
                    market_cache = found
            except (OSError, ValueError, requests.RequestException) as exc:
                if not stop.is_set():
                    emit([{"kind": "error", "source": "gamma", "error": type(exc).__name__}])
            stop.wait(60)

    def worker(source):
        attempt = 0
        while not stop.is_set():
            if source == "polymarket" and current_markets() is None:
                stop.wait(.1)
                continue
            socket = None
            try:
                socket = websocket.create_connection(URLS[source], timeout=2, skip_utf8_validation=True)
                emit([{"kind": "status", "source": source, "state": "connected"}])
                attempt = 0
                stream_connection(source, socket, stop, emit, current_markets)
            except (OSError, ValueError, requests.RequestException, websocket.WebSocketException) as exc:
                # Keep only type/category, never headers, request bodies or keys.
                details = {"close_code": exc.code, "close_reason": exc.reason} if isinstance(exc, FeedClosed) else {}
                emit([{"kind": "error", "source": source,
                       "error": "ConnectionError" if isinstance(exc, FeedClosed) else type(exc).__name__, **details}])
                attempt += 1
            finally:
                emit([{"kind": "status", "source": source, "state": "disconnected"}])
                if socket is not None:
                    socket.close(timeout=1)
            stop.wait(min(2 ** min(attempt, 4), 15))

    threads = [threading.Thread(target=worker, args=(source,), name=f"leadlag-{source}", daemon=True)
               for source in URLS]
    threads.append(threading.Thread(target=discovery_worker, name="leadlag-discovery", daemon=True))
    interrupted, status = False, "failed"
    end_wall, end_tick = time.time_ns(), time.monotonic_ns()
    print(f"Öffentliche BTC-Daten für {duration_s:g} Sekunden aufzeichnen: {run}", flush=True)
    try:
        with (run / "events.jsonl").open("w", encoding="utf-8") as file:
            for thread in threads:
                thread.start()
            try:
                while time.monotonic() - start < duration_s and not stop.is_set():
                    try:
                        row = pending.get(timeout=.2)
                    except queue.Empty:
                        continue
                    file.write(json.dumps(row, allow_nan=False, separators=(",", ":")) + "\n")
                    counts[row.get("source", row["kind"]) + ":" + row["kind"]] += 1
                    if row["kind"] == "error":
                        errors[row["source"] + ":" + row["error"]] += 1
                    if row["kind"] == "market":
                        manifest["markets"].append(row["market"]["slug"])
            except KeyboardInterrupt:
                interrupted = True
            finally:
                end_wall, end_tick = time.time_ns(), time.monotonic_ns()
                stop.set()
                for thread in threads:
                    thread.join(timeout=12)
                if any(thread.is_alive() for thread in threads):
                    data_loss.set()
                # Drain pre-stop observations; shutdown must not extend trading time.
                while not pending.empty():
                    row = pending.get_nowait()
                    if row["t_ns"] > end_tick:
                        continue
                    file.write(json.dumps(row, allow_nan=False, separators=(",", ":")) + "\n")
                    counts[row.get("source", row["kind"]) + ":" + row["kind"]] += 1
                    if row["kind"] == "error":
                        errors[row["source"] + ":" + row["error"]] += 1
                file.write(json.dumps({"kind": "clock", "t_ns": end_tick, "wall_ns": end_wall}) + "\n")
        status = "interrupted" if interrupted else "complete"
    finally:
        manifest.update(status=status, data_loss=data_loss.is_set(),
                        duration_s=round(time.monotonic() - start, 3), counts=dict(counts), errors=dict(errors),
                        queue_high_water=queue_high_water)
        manifest["markets"] = sorted(set(manifest["markets"]))
        if (run / "events.jsonl").exists():
            with (run / "events.jsonl").open("rb") as file:
                manifest["events_sha256"] = hashlib.file_digest(file, "sha256").hexdigest()
        manifest["capture_duration_s"] = round((end_tick - int(start * 1e9)) / 1e9, 3)
        try:
            manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        finally:
            proc_lock.release(lock)
    return run
