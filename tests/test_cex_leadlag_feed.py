"""Empfang bleibt strikt; Marktwechsel dürfen die Verbindung nicht erneuern."""
import json
import struct
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import websocket

from src import cex_leadlag_feed as feed


class ReceiveTests(unittest.TestCase):
    def test_native_decode_accepts_umlauts_and_rejects_invalid_utf8(self):
        text = '{"value":"Zürich"}'
        self.assertEqual(feed.decode_frame(websocket.ABNF.OPCODE_TEXT, text.encode()), text)
        with self.assertRaises(UnicodeDecodeError):
            feed.decode_frame(websocket.ABNF.OPCODE_TEXT, b'{"value":"\xff"}')
        with self.assertRaises(ValueError):
            feed.decode_frame(websocket.ABNF.OPCODE_BINARY, b'{}')

    def test_close_code_and_reason_survive_receipt(self):
        payload = struct.pack('!H', 1013) + b'slow consumer: send buffer full'
        with self.assertRaises(feed.FeedClosed) as caught:
            feed.decode_frame(websocket.ABNF.OPCODE_CLOSE, payload)
        self.assertEqual(caught.exception.code, 1013)
        self.assertEqual(caught.exception.reason, 'slow consumer: send buffer full')

    def test_control_frames_and_oversized_messages(self):
        self.assertIsNone(feed.decode_frame(websocket.ABNF.OPCODE_PING, b'ping'))
        self.assertIsNone(feed.decode_frame(websocket.ABNF.OPCODE_PONG, b'pong'))
        with self.assertRaises(ValueError):
            feed.decode_frame(websocket.ABNF.OPCODE_TEXT, b'x' * 8_000_001)

    def test_market_roll_and_minute_boundary_keep_same_connection(self):
        clock = [0.]
        stop = threading.Event()
        frames, rows = [], []
        retained = {'id': 'keep', 'tokens': {'Up': 'ku', 'Down': 'kd'}}
        before = [{'id': 'old', 'tokens': {'Up': 'ou', 'Down': 'od'}}, retained]
        after = [retained, {'id': 'new', 'tokens': {'Up': 'nu', 'Down': 'nd'}}]

        class Socket:
            def send(self, value):
                frames.append(json.loads(value) if value != 'PING' else value)

            def recv_data(self, control_frame=False):
                clock[0] += 1
                if clock[0] >= 75:
                    stop.set()
                return websocket.ABNF.OPCODE_TEXT, b'{"event_type":"last_trade_price"}'

        def current_markets():
            return before if clock[0] < 30 else after

        def emit(batch, received=None):
            rows.extend(batch)

        with patch.object(feed.time, 'monotonic', side_effect=lambda: clock[0]):
            feed.stream_connection('polymarket', Socket(), stop, emit, current_markets)
        self.assertGreaterEqual(clock[0], 75)
        self.assertEqual(sum(isinstance(f, dict) and f.get('type') == 'market' for f in frames), 1)
        changes = [f for f in frames if isinstance(f, dict) and 'operation' in f]
        self.assertEqual(changes, [{'assets_ids': ['nd', 'nu'], 'operation': 'subscribe'},
                                  {'assets_ids': ['od', 'ou'], 'operation': 'unsubscribe'}])
        self.assertFalse(any(r['kind'] == 'status' for r in rows))
        self.assertEqual(sum(r['kind'] == 'subscription' for r in rows), 2)

    def test_silent_connection_still_raises_timeout(self):
        clock = [0.]

        class Socket:
            def send(self, value):
                pass

            def recv_data(self, control_frame=False):
                clock[0] += 16
                raise websocket.WebSocketTimeoutException()

        with patch.object(feed.time, 'monotonic', side_effect=lambda: clock[0]):
            with self.assertRaises(TimeoutError):
                feed.stream_connection('binance', Socket(), threading.Event(), lambda *a: None)

    def test_receipt_timestamp_precedes_decode_and_parse(self):
        stop = threading.Event()
        clock, emitted = [0], []
        real_decode = feed.decode_frame

        class Socket:
            def recv_data(self, control_frame=False):
                clock[0] = 10
                stop.set()
                return websocket.ABNF.OPCODE_TEXT, b'{"e":"aggTrade","s":"BTCUSDT","p":"100"}'

        def slow_decode(*args):
            clock[0] = 20
            return real_decode(*args)

        with patch.object(feed.time, 'monotonic_ns', side_effect=lambda: clock[0]), \
             patch.object(feed, 'decode_frame', side_effect=slow_decode):
            feed.stream_connection('binance', Socket(), stop,
                                   lambda batch, received: emitted.append((batch, received)))
        self.assertEqual(emitted[0][1][0], 10)
        self.assertEqual(emitted[0][0][0]['price'], 100)

    def test_recorder_logs_remote_close_and_uses_native_validation(self):
        class Socket:
            def __init__(self, polymarket):
                self.polymarket = polymarket

            def send(self, value):
                pass

            def recv_data(self, control_frame=False):
                if self.polymarket:
                    return websocket.ABNF.OPCODE_CLOSE, struct.pack('!H', 1013) + b'slow consumer'
                time.sleep(.01)
                raise websocket.WebSocketTimeoutException()

            def close(self, timeout=1):
                pass

        def connect(url, **options):
            self.assertTrue(options['skip_utf8_validation'])
            return Socket(url == feed.URLS['polymarket'])

        markets = [{'id': 'm', 'slug': 'test', 'tokens': {'Up': 'u', 'Down': 'd'}}]
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(feed, 'discover', return_value=markets), \
             patch.object(feed.websocket, 'create_connection', side_effect=connect):
            run = feed.record_run(Path(directory), 1)
            manifest = json.loads((run / 'manifest.json').read_text(encoding='utf-8'))
            rows = [json.loads(line) for line in (run / 'events.jsonl').read_text().splitlines()]
        error = next(r for r in rows if r['kind'] == 'error')
        self.assertEqual(error['close_code'], 1013)
        self.assertEqual(error['close_reason'], 'slow consumer')
        self.assertEqual(manifest['errors'], {'polymarket:ConnectionError': 1})
        self.assertTrue(any(r.get('state') == 'disconnected' and r.get('source') == 'polymarket' for r in rows))
        self.assertFalse(manifest['data_loss'])


if __name__ == '__main__':
    unittest.main()
