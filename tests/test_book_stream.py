import json
import tempfile
import unittest
from pathlib import Path

from src import book_stream as bs


def book_event(token="t1", bids=None, asks=None, ts="1000"):
    return {
        "event_type": "book",
        "asset_id": token,
        "timestamp": ts,
        "bids": bids if bids is not None else [{"price": "0.40", "size": "100"}],
        "asks": asks if asks is not None else [{"price": "0.42", "size": "100"}],
    }


def change_event(token="t1", price="0.41", size="50", side="BUY", ts="1001"):
    return {
        "event_type": "price_change",
        "timestamp": ts,
        "price_changes": [
            {"asset_id": token, "price": price, "size": size, "side": side}
        ],
    }


class FakeSocket:
    """Minimal stand-in for a websocket-client connection."""

    def __init__(self, frames):
        self.frames = list(frames)
        self.sent = []
        self.closed = False

    def send(self, payload):
        self.sent.append(payload)

    def recv(self):
        if not self.frames:
            raise TimeoutError("no more frames")
        frame = self.frames.pop(0)
        if isinstance(frame, Exception):
            raise frame
        return frame

    def close(self):
        self.closed = True


class SubscribeTests(unittest.TestCase):
    def test_subscription_frame_shape(self):
        msg = bs.subscribe_message(["a", "b"])
        self.assertEqual(msg, {"assets_ids": ["a", "b"], "type": "market"})

    def test_token_ids_are_stringified(self):
        self.assertEqual(bs.subscribe_message([123])["assets_ids"], ["123"])


class BackoffTests(unittest.TestCase):
    def test_backoff_grows_then_caps(self):
        delays = [bs.backoff_delay(i) for i in range(0, 12)]
        self.assertEqual(delays[0], 1.0)
        self.assertLessEqual(max(delays), bs.MAX_BACKOFF_S)
        self.assertGreaterEqual(delays[4], delays[2])

    def test_backoff_never_exceeds_the_cap(self):
        self.assertEqual(bs.backoff_delay(99), bs.MAX_BACKOFF_S)


class BookStateTests(unittest.TestCase):
    def setUp(self):
        self.book = bs.BookState()
        self.book.apply_snapshot(
            [{"price": "0.40", "size": "100"}, {"price": "0.39", "size": "200"}],
            [{"price": "0.42", "size": "50"}, {"price": "0.43", "size": "80"}],
        )

    def test_snapshot_sets_best_prices(self):
        self.assertEqual(self.book.best_bid(), 0.40)
        self.assertEqual(self.book.best_ask(), 0.42)

    def test_snapshot_accepts_pair_lists_too(self):
        book = bs.BookState()
        book.apply_snapshot([[0.30, 10]], [[0.35, 10]])
        self.assertEqual(book.best_bid(), 0.30)

    def test_zero_size_levels_are_dropped_from_a_snapshot(self):
        book = bs.BookState()
        book.apply_snapshot([{"price": "0.40", "size": "0"}], [])
        self.assertIsNone(book.best_bid())

    def test_delta_adds_a_new_best_bid(self):
        self.book.apply_change("0.41", "25", "BUY")
        self.assertEqual(self.book.best_bid(), 0.41)

    def test_delta_with_zero_size_removes_the_level(self):
        self.book.apply_change("0.40", "0", "BUY")
        self.assertEqual(self.book.best_bid(), 0.39)

    def test_delta_overwrites_the_size_at_a_price(self):
        self.book.apply_change("0.40", "7", "BUY")
        self.assertEqual(self.book.bids[0.40], 7.0)

    def test_sell_side_delta_hits_the_asks(self):
        self.book.apply_change("0.415", "5", "SELL")
        self.assertEqual(self.book.best_ask(), 0.415)

    def test_malformed_delta_is_ignored(self):
        before = dict(self.book.bids)
        self.book.apply_change("nicht-zahl", "5", "BUY")
        self.assertEqual(self.book.bids, before)

    def test_depth_usd_counts_price_times_size(self):
        bid_usd, ask_usd = self.book.depth_usd(levels=5)
        self.assertAlmostEqual(bid_usd, 0.40 * 100 + 0.39 * 200, places=4)
        self.assertAlmostEqual(ask_usd, 0.42 * 50 + 0.43 * 80, places=4)

    def test_depth_usd_respects_the_level_limit(self):
        bid_usd, _ = self.book.depth_usd(levels=1)
        self.assertAlmostEqual(bid_usd, 0.40 * 100, places=4)

    def test_empty_side_yields_no_top_of_book(self):
        book = bs.BookState()
        book.apply_snapshot([{"price": "0.4", "size": "1"}], [])
        row = book.top_row("ts", "book")
        self.assertIsNone(row["best_ask"])
        self.assertIsNone(row["mid"])
        self.assertIsNone(row["spread"])

    def test_top_row_reports_mid_spread_and_imbalance(self):
        row = self.book.top_row("ts", "book")
        self.assertAlmostEqual(row["mid"], 0.41, places=6)
        self.assertAlmostEqual(row["spread"], 0.02, places=6)
        self.assertTrue(0.0 < row["imbalance_top"] < 1.0)
        self.assertEqual(row["bid_levels"], 2)

    def test_touch_signature_tracks_size_at_the_touch(self):
        before = self.book.touch_signature()
        self.book.apply_change("0.40", "999", "BUY")
        self.assertNotEqual(before, self.book.touch_signature())

    def test_touch_signature_ignores_moves_deep_in_the_book(self):
        before = self.book.touch_signature()
        self.book.apply_change("0.20", "500", "BUY")
        self.assertEqual(before, self.book.touch_signature())


class StreamStateTests(unittest.TestCase):
    def setUp(self):
        self.state = bs.StreamState()

    def test_book_event_creates_a_row(self):
        self.state.handle(book_event(), "r1")
        self.assertEqual(len(self.state.book_rows), 1)
        self.assertEqual(self.state.book_rows[0]["token_id"], "t1")
        self.assertEqual(self.state.book_rows[0]["event_type"], "book")

    def test_exchange_timestamp_is_carried_through(self):
        self.state.handle(book_event(ts="1785000000000"), "r1")
        self.assertEqual(self.state.book_rows[0]["exchange_ts"], "1785000000000")

    def test_price_change_at_the_touch_emits_a_row(self):
        self.state.handle(book_event(), "r1")
        self.state.handle(change_event(price="0.41", size="10"), "r2")
        self.assertEqual(len(self.state.book_rows), 2)
        self.assertEqual(self.state.book_rows[-1]["best_bid"], 0.41)

    def test_price_change_deep_in_the_book_emits_nothing(self):
        self.state.handle(book_event(), "r1")
        self.state.handle(change_event(price="0.10", size="10"), "r2")
        self.assertEqual(len(self.state.book_rows), 1)

    def test_a_repeated_identical_book_emits_only_once(self):
        self.state.handle(book_event(), "r1")
        self.state.handle(book_event(), "r2")
        self.assertEqual(len(self.state.book_rows), 1)

    def test_multi_token_change_emits_one_row_per_token(self):
        self.state.handle(book_event(token="a"), "r1")
        self.state.handle(book_event(token="b"), "r1")
        self.state.handle({
            "event_type": "price_change", "timestamp": "9",
            "price_changes": [
                {"asset_id": "a", "price": "0.99", "size": "5", "side": "BUY"},
                {"asset_id": "b", "price": "0.98", "size": "5", "side": "BUY"},
            ],
        }, "r2")
        emitted = [r["token_id"] for r in self.state.book_rows[-2:]]
        self.assertEqual(sorted(emitted), ["a", "b"])

    def test_trade_event_records_the_aggressor_side(self):
        self.state.handle({
            "event_type": "last_trade_price", "asset_id": "t1", "side": "SELL",
            "price": "0.33", "size": "12", "timestamp": "5",
            "transaction_hash": "0xabc",
        }, "r1")
        self.assertEqual(len(self.state.trade_rows), 1)
        self.assertEqual(self.state.trade_rows[0]["side"], "SELL")
        self.assertEqual(self.state.trade_rows[0]["tx_hash"], "0xabc")

    def test_event_types_are_counted(self):
        self.state.handle(book_event(), "r1")
        self.state.handle(change_event(), "r2")
        self.assertEqual(self.state.counts["book"], 1)
        self.assertEqual(self.state.counts["price_change"], 1)

    def test_unknown_event_type_is_counted_but_harmless(self):
        self.state.handle({"event_type": "tick_size_change", "asset_id": "t1"}, "r1")
        self.assertEqual(self.state.counts["tick_size_change"], 1)
        self.assertEqual(self.state.book_rows, [])

    def test_non_dict_event_is_ignored(self):
        self.state.handle(["not", "a", "dict"], "r1")
        self.assertEqual(self.state.book_rows, [])

    def test_event_without_asset_id_is_ignored(self):
        self.state.handle({"event_type": "book", "bids": [], "asks": []}, "r1")
        self.assertEqual(self.state.book_rows, [])

    def test_drain_hands_over_and_resets(self):
        self.state.handle(book_event(), "r1")
        books, trades = self.state.drain()
        self.assertEqual(len(books), 1)
        self.assertEqual(trades, [])
        self.assertEqual(self.state.book_rows, [])


class ParsePayloadTests(unittest.TestCase):
    def test_single_object(self):
        self.assertEqual(len(bs.parse_payload(json.dumps(book_event()))), 1)

    def test_list_of_events(self):
        payload = json.dumps([book_event(), change_event()])
        self.assertEqual(len(bs.parse_payload(payload)), 2)

    def test_pong_is_not_an_event(self):
        self.assertEqual(bs.parse_payload("PONG"), [])
        self.assertEqual(bs.parse_payload(""), [])

    def test_garbage_does_not_raise(self):
        self.assertEqual(bs.parse_payload("{nope"), [])

    def test_scalar_json_is_dropped(self):
        self.assertEqual(bs.parse_payload("42"), [])

    def test_non_dict_items_in_a_list_are_dropped(self):
        self.assertEqual(bs.parse_payload(json.dumps([1, "a"])), [])


class StreamOnceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def _clock(self, step=1.0):
        state = {"t": 0.0}

        def now():
            state["t"] += step
            return state["t"]
        return now

    def test_subscribes_then_records_rows_to_csv(self):
        frames = [json.dumps(book_event()), json.dumps(change_event(price="0.41", size="9"))]
        socket = FakeSocket(frames)
        summary = bs.stream_once(["t1"], self.out, duration_s=5,
                                 ws_factory=lambda url: socket,
                                 now_fn=self._clock(0.5))
        self.assertTrue(summary["connected"])
        self.assertGreaterEqual(summary["book_rows"], 1)
        sent = json.loads(socket.sent[0])
        self.assertEqual(sent["type"], "market")
        self.assertEqual(sent["assets_ids"], ["t1"])
        written = list(self.out.glob("stream_books_*.csv"))
        self.assertEqual(len(written), 1)
        self.assertIn("token_id", written[0].read_text(encoding="utf-8"))

    def test_trades_land_in_their_own_file(self):
        trade = {"event_type": "last_trade_price", "asset_id": "t1",
                 "side": "BUY", "price": "0.5", "size": "3", "timestamp": "1"}
        socket = FakeSocket([json.dumps(trade)])
        summary = bs.stream_once(["t1"], self.out, duration_s=5,
                                 ws_factory=lambda url: socket,
                                 now_fn=self._clock(0.5))
        self.assertEqual(summary["trade_rows"], 1)
        self.assertTrue(list(self.out.glob("stream_trades_*.csv")))

    def test_connection_failure_is_reported_not_raised(self):
        def boom(url):
            raise ConnectionError("refused")

        summary = bs.stream_once(["t1"], self.out, duration_s=5, ws_factory=boom)
        self.assertFalse(summary["connected"])
        self.assertIn("ConnectionError", summary["error"])
        self.assertEqual(summary["book_rows"], 0)

    def test_ping_is_sent_on_the_heartbeat_interval(self):
        socket = FakeSocket([])
        bs.stream_once(["t1"], self.out, duration_s=30,
                       ws_factory=lambda url: socket,
                       now_fn=self._clock(bs.PING_INTERVAL_S + 1))
        self.assertIn("PING", socket.sent)

    def test_socket_is_closed_even_when_the_loop_breaks(self):
        socket = FakeSocket([ValueError("hard failure")])
        summary = bs.stream_once(["t1"], self.out, duration_s=5,
                                 ws_factory=lambda url: socket,
                                 now_fn=self._clock(0.5))
        self.assertTrue(socket.closed)
        self.assertTrue(summary["errors"])

    def test_timeouts_are_tolerated_and_not_logged_as_errors(self):
        socket = FakeSocket([TimeoutError("read timeout"), json.dumps(book_event())])
        summary = bs.stream_once(["t1"], self.out, duration_s=5,
                                 ws_factory=lambda url: socket,
                                 now_fn=self._clock(0.5))
        self.assertEqual(summary["errors"], [])
        self.assertEqual(summary["book_rows"], 1)

    def test_raw_archive_is_opt_in(self):
        socket = FakeSocket([json.dumps(book_event())])
        bs.stream_once(["t1"], self.out, duration_s=5,
                       ws_factory=lambda url: socket,
                       now_fn=self._clock(0.5), keep_raw=False)
        self.assertEqual(list(self.out.glob("*.jsonl")), [])

    def test_raw_archive_is_written_when_requested(self):
        socket = FakeSocket([json.dumps(book_event())])
        bs.stream_once(["t1"], self.out, duration_s=5,
                       ws_factory=lambda url: socket,
                       now_fn=self._clock(0.5), keep_raw=True)
        raw = list(self.out.glob("stream_raw_*.jsonl"))
        self.assertEqual(len(raw), 1)
        self.assertIn("payload", raw[0].read_text(encoding="utf-8"))


class TokenSelectionTests(unittest.TestCase):
    def test_selection_flattens_markets_into_tokens(self):
        market = {
            "id": "1", "slug": "s", "question": "Q", "volume24hr": 10,
            "outcomes": json.dumps(["Yes", "No"]),
            "clobTokenIds": json.dumps(["tok-yes", "tok-no"]),
        }
        tokens = bs.select_stream_tokens(get_json=lambda *a, **k: [market], top_n=5)
        self.assertEqual([t["token_id"] for t in tokens], ["tok-yes", "tok-no"])
        self.assertEqual(tokens[0]["outcome"], "Yes")

    def test_selection_survives_an_empty_market_list(self):
        self.assertEqual(bs.select_stream_tokens(get_json=lambda *a, **k: [],
                                                 top_n=5), [])


class LockTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def test_a_fresh_directory_can_be_claimed(self):
        lock = bs.acquire_lock(self.out)
        self.assertTrue(lock.exists())

    def test_re_acquiring_our_own_lock_is_allowed(self):
        bs.acquire_lock(self.out)
        bs.acquire_lock(self.out)  # darf nicht werfen

    def test_a_live_foreign_owner_blocks_the_start(self):
        # PID 1 existiert praktisch immer und gehoert uns nicht.
        (self.out / "stream_recorder.lock").write_text("1", encoding="utf-8")
        original = bs._pid_alive
        bs._pid_alive = lambda pid: True
        self.addCleanup(setattr, bs, "_pid_alive", original)
        with self.assertRaises(bs.AlreadyRunning):
            bs.acquire_lock(self.out)

    def test_a_stale_lock_from_a_dead_process_is_taken_over(self):
        (self.out / "stream_recorder.lock").write_text("999999", encoding="utf-8")
        original = bs._pid_alive
        bs._pid_alive = lambda pid: False
        self.addCleanup(setattr, bs, "_pid_alive", original)
        bs.acquire_lock(self.out)  # darf nicht werfen

    def test_a_corrupt_lock_does_not_block_forever(self):
        (self.out / "stream_recorder.lock").write_text("nicht-zahl", encoding="utf-8")
        bs.acquire_lock(self.out)

    def test_releasing_removes_our_own_lock(self):
        lock = bs.acquire_lock(self.out)
        bs.release_lock(lock)
        self.assertFalse(lock.exists())

    def test_releasing_leaves_a_foreign_lock_alone(self):
        lock = self.out / "stream_recorder.lock"
        lock.write_text("424242", encoding="utf-8")
        bs.release_lock(lock)
        self.assertTrue(lock.exists())

    def test_pid_zero_is_never_alive(self):
        self.assertFalse(bs._pid_alive(0))
        self.assertFalse(bs._pid_alive(-5))

    def test_run_releases_the_lock_even_when_it_fails(self):
        def boom(url):
            raise ConnectionError("refused")

        bs.run(out_dir=self.out, duration_s=1, loop=False, ws_factory=boom,
               get_json=lambda *a, **k: [])
        self.assertFalse((self.out / "stream_recorder.lock").exists())

    def test_a_second_run_is_refused_while_the_first_holds_the_lock(self):
        bs.acquire_lock(self.out)
        (self.out / "stream_recorder.lock").write_text("1", encoding="utf-8")
        original = bs._pid_alive
        bs._pid_alive = lambda pid: True
        self.addCleanup(setattr, bs, "_pid_alive", original)
        with self.assertRaises(bs.AlreadyRunning):
            bs.run(out_dir=self.out, duration_s=1, loop=False,
                   ws_factory=lambda url: FakeSocket([]),
                   get_json=lambda *a, **k: [])

    def test_the_cli_reports_a_conflict_instead_of_crashing(self):
        (self.out / "stream_recorder.lock").write_text("1", encoding="utf-8")
        original = bs._pid_alive
        bs._pid_alive = lambda pid: True
        self.addCleanup(setattr, bs, "_pid_alive", original)
        code = bs.main(["--duration", "1", "--out-dir", str(self.out)])
        self.assertEqual(code, 1)


class StatusTests(unittest.TestCase):
    def test_status_file_is_written_with_a_timestamp(self):
        with tempfile.TemporaryDirectory() as tmp:
            bs.write_status(Path(tmp), {"connected": True, "messages": 3})
            payload = json.loads(
                (Path(tmp) / "stream_status.json").read_text(encoding="utf-8"))
            self.assertTrue(payload["ts_utc"].endswith("Z"))
            self.assertEqual(payload["messages"], 3)


if __name__ == "__main__":
    unittest.main()
