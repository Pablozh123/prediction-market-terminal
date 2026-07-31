import json
import tempfile
import unittest
from pathlib import Path

from app import kalshi_auth as ka
from src import kalshi_stream as ks
from src import kalshi_stream_state as st


def snapshot(market="KXTEST", yes=None, no=None, seq=1):
    return {"type": "orderbook_snapshot", "seq": seq, "msg": {
        "market_ticker": market,
        "yes": yes if yes is not None else [[40, 100], [39, 200]],
        "no": no if no is not None else [[55, 50], [54, 80]],
    }}


def delta(market="KXTEST", price=41, amount=25, side="yes", seq=2):
    return {"type": "orderbook_delta", "seq": seq, "msg": {
        "market_ticker": market, "price": price, "delta": amount, "side": side}}


def throwaway_credentials(directory: Path):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    path = directory / "test_key.pem"
    path.write_bytes(key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()))
    return ka.load_credentials("kid", path, allow_in_repo=True)


class FakeSocket:
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


class PriceTests(unittest.TestCase):
    def test_cents_become_dollars(self):
        self.assertAlmostEqual(st.to_dollars(40), 0.40, places=6)

    def test_values_already_in_dollars_pass_through(self):
        self.assertAlmostEqual(st.to_dollars(0.4), 0.40, places=6)

    def test_out_of_range_prices_are_rejected(self):
        self.assertIsNone(st.to_dollars(0))
        self.assertIsNone(st.to_dollars(-5))
        self.assertIsNone(st.to_dollars(100))

    def test_nonsense_is_rejected(self):
        self.assertIsNone(st.to_dollars("viel"))
        self.assertIsNone(st.to_dollars(None))


class DeltaSemanticsTests(unittest.TestCase):
    """Kalshi sends a change, Polymarket sends a size. Mixing them up drifts."""

    def setUp(self):
        self.book = st.BookState()
        self.book.apply_snapshot([[40, 100]], [[55, 50]])

    def test_a_delta_adds_to_the_existing_size(self):
        self.book.apply_delta(40, 25, "yes")
        self.assertEqual(self.book.yes_bids[0.40], 125.0)

    def test_a_negative_delta_subtracts(self):
        self.book.apply_delta(40, -30, "yes")
        self.assertEqual(self.book.yes_bids[0.40], 70.0)

    def test_a_level_disappears_when_it_reaches_zero(self):
        self.book.apply_delta(40, -100, "yes")
        self.assertNotIn(0.40, self.book.yes_bids)

    def test_a_level_cannot_go_negative(self):
        self.book.apply_delta(40, -500, "yes")
        self.assertNotIn(0.40, self.book.yes_bids)

    def test_a_delta_can_create_a_new_level(self):
        self.book.apply_delta(41, 10, "yes")
        self.assertEqual(self.book.best_bid(), 0.41)

    def test_a_malformed_delta_is_ignored(self):
        before = dict(self.book.yes_bids)
        self.book.apply_delta("nein", 10, "yes")
        self.book.apply_delta(40, "nein", "yes")
        self.assertEqual(self.book.yes_bids, before)


class ReflectionTests(unittest.TestCase):
    def setUp(self):
        self.book = st.BookState()
        self.book.apply_snapshot([[40, 100], [39, 200]], [[55, 50], [54, 80]])

    def test_the_ask_is_the_reflected_best_no_bid(self):
        self.assertAlmostEqual(self.book.best_ask(), 0.45, places=6)

    def test_the_bid_is_taken_directly(self):
        self.assertAlmostEqual(self.book.best_bid(), 0.40, places=6)

    def test_the_book_does_not_cross(self):
        self.assertLess(self.book.best_bid(), self.book.best_ask())

    def test_ask_levels_are_reflected_and_ordered_outward(self):
        levels = self.book.ask_levels()
        self.assertAlmostEqual(levels[0][0], 0.45, places=6)
        self.assertAlmostEqual(levels[1][0], 0.46, places=6)

    def test_depth_is_priced_in_dollars(self):
        bid_usd, ask_usd = self.book.depth_usd()
        self.assertAlmostEqual(bid_usd, 0.40 * 100 + 0.39 * 200, places=3)
        self.assertAlmostEqual(ask_usd, 0.45 * 50 + 0.46 * 80, places=3)

    def test_a_one_sided_book_has_no_mid(self):
        book = st.BookState()
        book.apply_snapshot([[40, 100]], [])
        row = book.top_row("t", "snapshot")
        self.assertIsNone(row["mid"])
        self.assertIsNone(row["spread"])


class SequenceTests(unittest.TestCase):
    def test_consecutive_sequences_are_accepted(self):
        book = st.BookState()
        book.apply_snapshot([[40, 1]], [[55, 1]], seq=5)
        self.assertTrue(book.check_seq(6))
        self.assertFalse(book.broken)

    def test_a_repeat_of_the_same_sequence_is_tolerated(self):
        book = st.BookState()
        book.apply_snapshot([[40, 1]], [[55, 1]], seq=5)
        self.assertTrue(book.check_seq(5))

    def test_a_gap_marks_the_book_broken(self):
        book = st.BookState()
        book.apply_snapshot([[40, 1]], [[55, 1]], seq=5)
        self.assertFalse(book.check_seq(9))
        self.assertTrue(book.broken)

    def test_a_missing_sequence_number_cannot_be_checked(self):
        book = st.BookState()
        book.apply_snapshot([[40, 1]], [[55, 1]], seq=5)
        self.assertTrue(book.check_seq(None))

    def test_a_snapshot_repairs_a_broken_book(self):
        book = st.BookState()
        book.apply_snapshot([[40, 1]], [[55, 1]], seq=5)
        book.check_seq(99)
        self.assertTrue(book.broken)
        book.apply_snapshot([[40, 1]], [[55, 1]], seq=100)
        self.assertFalse(book.broken)


class StreamStateTests(unittest.TestCase):
    def setUp(self):
        self.state = st.StreamState()

    def test_a_snapshot_produces_a_row(self):
        self.state.handle(snapshot(), "r1")
        self.assertEqual(len(self.state.book_rows), 1)
        self.assertEqual(self.state.book_rows[0]["market_id"], "KXTEST")

    def test_a_delta_at_the_touch_produces_a_row(self):
        self.state.handle(snapshot(), "r1")
        self.state.handle(delta(price=41, amount=10), "r2")
        self.assertEqual(len(self.state.book_rows), 2)
        self.assertAlmostEqual(self.state.book_rows[-1]["best_bid"], 0.41, places=6)

    def test_a_delta_deep_in_the_book_produces_nothing(self):
        self.state.handle(snapshot(), "r1")
        self.state.handle(delta(price=20, amount=10), "r2")
        self.assertEqual(len(self.state.book_rows), 1)

    def test_a_sequence_gap_stops_rows_until_a_new_snapshot(self):
        # Zeilen aus einem Buch zu schreiben, von dem man weiss, dass es
        # falsch ist, ist schlimmer als gar keine zu schreiben.
        self.state.handle(snapshot(seq=1), "r1")
        self.state.handle(delta(seq=99), "r2")
        self.assertEqual(self.state.seq_gaps, 1)
        before = len(self.state.book_rows)
        self.state.handle(delta(seq=100, price=42), "r3")
        self.assertEqual(len(self.state.book_rows), before)

    def test_a_fresh_snapshot_resumes_recording(self):
        self.state.handle(snapshot(seq=1), "r1")
        self.state.handle(delta(seq=99), "r2")
        self.state.handle(snapshot(seq=200, yes=[[42, 10]]), "r3")
        self.assertAlmostEqual(self.state.book_rows[-1]["best_bid"], 0.42,
                               places=6)

    def test_a_trade_records_the_aggressor_side(self):
        self.state.handle({"type": "trade", "msg": {
            "market_ticker": "KXTEST", "taker_side": "yes", "yes_price": 33,
            "count": 12, "ts": 1735689600, "trade_id": "abc"}}, "r1")
        row = self.state.trade_rows[0]
        self.assertEqual(row["side"], "BUY")
        self.assertAlmostEqual(row["price"], 0.33, places=6)

    def test_a_no_side_taker_is_a_sell_of_yes(self):
        self.state.handle({"type": "trade", "msg": {
            "market_ticker": "KXTEST", "taker_side": "no", "yes_price": 33,
            "count": 5}}, "r1")
        self.assertEqual(self.state.trade_rows[0]["side"], "SELL")

    def test_messages_without_a_market_are_ignored(self):
        self.state.handle({"type": "orderbook_snapshot", "msg": {}}, "r1")
        self.assertEqual(self.state.book_rows, [])

    def test_unknown_message_types_are_counted_only(self):
        self.state.handle({"type": "subscribed", "msg": {"market_ticker": "X"}}, "r1")
        self.assertEqual(self.state.counts["subscribed"], 1)
        self.assertEqual(self.state.book_rows, [])

    def test_drain_hands_over_and_resets(self):
        self.state.handle(snapshot(), "r1")
        books, trades = self.state.drain()
        self.assertEqual(len(books), 1)
        self.assertEqual(self.state.book_rows, [])


class SubscribeTests(unittest.TestCase):
    def test_the_frame_asks_for_books_and_trades(self):
        msg = ks.subscribe_message(["A", "B"])
        self.assertEqual(msg["cmd"], "subscribe")
        self.assertEqual(msg["params"]["market_tickers"], ["A", "B"])
        self.assertIn("orderbook_delta", msg["params"]["channels"])
        self.assertIn("trade", msg["params"]["channels"])

    def test_backoff_grows_and_caps(self):
        self.assertEqual(ks.backoff_delay(0), 1.0)
        self.assertEqual(ks.backoff_delay(99), ks.MAX_BACKOFF_S)

    def test_payload_parsing_survives_garbage(self):
        self.assertEqual(ks.parse_payload("{kaputt"), [])
        self.assertEqual(ks.parse_payload(""), [])
        self.assertEqual(len(ks.parse_payload(json.dumps(snapshot()))), 1)


class HandshakeTests(unittest.TestCase):
    def test_the_handshake_is_signed_as_a_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            creds = throwaway_credentials(Path(tmp))
            headers = ks.handshake_headers(creds, now_ms=1735689600000)
            self.assertEqual(headers["KALSHI-ACCESS-KEY"], "kid")
            self.assertTrue(headers["KALSHI-ACCESS-SIGNATURE"])

    def test_the_websocket_path_is_not_a_blocked_path(self):
        ka.check_request("GET", ks.WS_PATH)


class StreamOnceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        self.creds = throwaway_credentials(self.out)

    def _clock(self, step=0.5):
        state = {"t": 0.0}

        def now():
            state["t"] += step
            return state["t"]
        return now

    def test_a_run_subscribes_and_writes_rows(self):
        socket = FakeSocket([json.dumps(snapshot()),
                             json.dumps(delta(price=41, amount=5))])
        summary = ks.stream_once(["KXTEST"], self.out, 5, self.creds,
                                 ws_factory=lambda url, headers: socket,
                                 now_fn=self._clock())
        self.assertTrue(summary["connected"])
        self.assertGreaterEqual(summary["book_rows"], 1)
        sent = json.loads(socket.sent[0])
        self.assertEqual(sent["params"]["market_tickers"], ["KXTEST"])
        self.assertTrue(list(self.out.glob("kalshi_stream_books_*.csv")))

    def test_trades_land_in_their_own_file(self):
        trade = {"type": "trade", "msg": {"market_ticker": "KXTEST",
                                          "taker_side": "yes", "yes_price": 40,
                                          "count": 3}}
        socket = FakeSocket([json.dumps(trade)])
        summary = ks.stream_once(["KXTEST"], self.out, 5, self.creds,
                                 ws_factory=lambda url, headers: socket,
                                 now_fn=self._clock())
        self.assertEqual(summary["trade_rows"], 1)

    def test_a_connection_failure_is_reported_not_raised(self):
        def boom(url, headers):
            raise ConnectionError("refused")

        summary = ks.stream_once(["KXTEST"], self.out, 5, self.creds,
                                 ws_factory=boom)
        self.assertFalse(summary["connected"])
        self.assertIn("ConnectionError", summary["error"])

    def test_sequence_gaps_are_reported_in_the_summary(self):
        socket = FakeSocket([json.dumps(snapshot(seq=1)),
                             json.dumps(delta(seq=77))])
        summary = ks.stream_once(["KXTEST"], self.out, 5, self.creds,
                                 ws_factory=lambda url, headers: socket,
                                 now_fn=self._clock())
        self.assertEqual(summary["seq_gaps"], 1)

    def test_the_socket_is_closed_even_on_failure(self):
        socket = FakeSocket([ValueError("hart")])
        ks.stream_once(["KXTEST"], self.out, 5, self.creds,
                       ws_factory=lambda url, headers: socket,
                       now_fn=self._clock())
        self.assertTrue(socket.closed)


class EnvLoadingTests(unittest.TestCase):
    """Only the two Kalshi variables may cross over from a shared secrets file."""

    def test_only_the_named_keys_are_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text(
                "POLY_PRIVATE_KEY=0xdeadbeef-darf-nicht-auftauchen\n"
                "ANTHROPIC_API_KEY=sk-darf-nicht-auftauchen\n"
                "KALSHI_KEY_ID=meine-kid\n"
                "KALSHI_PRIVATE_KEY_PATH=C:/irgendwo/key.pem\n",
                encoding="utf-8")
            found = ka.read_selected_env(path)
            self.assertEqual(set(found), {"KALSHI_KEY_ID",
                                          "KALSHI_PRIVATE_KEY_PATH"})
            self.assertNotIn("POLY_PRIVATE_KEY", found)

    def test_comments_and_blank_lines_are_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text("# Kommentar\n\nKALSHI_KEY_ID=x\n", encoding="utf-8")
            self.assertEqual(ka.read_selected_env(path)["KALSHI_KEY_ID"], "x")

    def test_quotes_are_stripped(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text('KALSHI_KEY_ID="x"\n', encoding="utf-8")
            self.assertEqual(ka.read_selected_env(path)["KALSHI_KEY_ID"], "x")

    def test_a_missing_file_yields_nothing(self):
        self.assertEqual(ka.read_selected_env("C:/gibt/es/nicht/.env"), {})

    def test_an_exported_variable_wins_over_the_file(self):
        import os

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text("KALSHI_KEY_ID=aus-datei\n", encoding="utf-8")
            saved = os.environ.get(ka.KEY_ID_ENV)
            os.environ[ka.KEY_ID_ENV] = "aus-umgebung"
            try:
                ka.load_from_env_files([path])
                self.assertEqual(os.environ[ka.KEY_ID_ENV], "aus-umgebung")
            finally:
                if saved is None:
                    os.environ.pop(ka.KEY_ID_ENV, None)
                else:
                    os.environ[ka.KEY_ID_ENV] = saved

    def test_an_override_path_is_searched_first(self):
        import os

        saved = os.environ.get(ka.ENV_FILE_OVERRIDE)
        os.environ[ka.ENV_FILE_OVERRIDE] = "C:/woanders/.env"
        try:
            self.assertEqual(str(ka.env_file_candidates()[0]),
                             str(Path("C:/woanders/.env")))
        finally:
            if saved is None:
                os.environ.pop(ka.ENV_FILE_OVERRIDE, None)
            else:
                os.environ[ka.ENV_FILE_OVERRIDE] = saved


if __name__ == "__main__":
    unittest.main()
