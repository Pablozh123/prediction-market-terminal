import json
import tempfile
import unittest
from pathlib import Path

from app import kalshi_auth as ka
from src import kalshi_stream as ks
from src import kalshi_stream_state as st


def snapshot(market="KXTEST", yes=None, no=None, seq=1, sid=1):
    return {"type": "orderbook_snapshot", "seq": seq, "sid": sid, "msg": {
        "market_ticker": market,
        "yes_dollars_fp": yes if yes is not None
        else [["0.40", "100"], ["0.39", "200"]],
        "no_dollars_fp": no if no is not None
        else [["0.45", "50"], ["0.46", "80"]],
    }}


def delta(market="KXTEST", price="0.41", amount="25", side="yes", seq=2, sid=1):
    return {"type": "orderbook_delta", "seq": seq, "sid": sid, "msg": {
        "market_ticker": market, "price_dollars": price, "delta_fp": amount,
        "side": side}}


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
        self.book.apply_snapshot([["0.40", "100"]], [["0.45", "50"]])

    def test_a_delta_adds_to_the_existing_size(self):
        self.book.apply_delta("0.40", 25, "yes")
        self.assertEqual(self.book.yes_bids[0.40], 125.0)

    def test_a_negative_delta_subtracts(self):
        self.book.apply_delta("0.40", -30, "yes")
        self.assertEqual(self.book.yes_bids[0.40], 70.0)

    def test_a_level_disappears_when_it_reaches_zero(self):
        self.book.apply_delta("0.40", -100, "yes")
        self.assertNotIn(0.40, self.book.yes_bids)

    def test_a_level_cannot_go_negative(self):
        self.book.apply_delta("0.40", -500, "yes")
        self.assertNotIn(0.40, self.book.yes_bids)

    def test_a_delta_can_create_a_new_level(self):
        self.book.apply_delta("0.41", 10, "yes")
        self.assertEqual(self.book.best_bid(), 0.41)

    def test_a_malformed_delta_is_ignored(self):
        before = dict(self.book.yes_bids)
        self.book.apply_delta("nein", 10, "yes")
        self.book.apply_delta("0.40", "nein", "yes")
        self.assertEqual(self.book.yes_bids, before)


class YesPricingTests(unittest.TestCase):
    """With use_yes_price pinned, the no side already arrives as YES asks."""
    def setUp(self):
        self.book = st.BookState()
        self.book.apply_snapshot([["0.40", "100"], ["0.39", "200"]],
                                 [["0.45", "50"], ["0.46", "80"]])

    def test_the_ask_is_taken_as_sent(self):
        # Nochmal spiegeln wuerde 0.55 ergeben und jeden Spread invertieren.
        self.assertAlmostEqual(self.book.best_ask(), 0.45, places=6)

    def test_the_bid_is_taken_directly(self):
        self.assertAlmostEqual(self.book.best_bid(), 0.40, places=6)

    def test_the_book_does_not_cross(self):
        self.assertLess(self.book.best_bid(), self.book.best_ask())

    def test_ask_levels_are_ordered_outward(self):
        levels = self.book.ask_levels()
        self.assertAlmostEqual(levels[0][0], 0.45, places=6)
        self.assertAlmostEqual(levels[1][0], 0.46, places=6)

    def test_depth_is_priced_in_dollars(self):
        bid_usd, ask_usd = self.book.depth_usd()
        self.assertAlmostEqual(bid_usd, 0.40 * 100 + 0.39 * 200, places=3)
        self.assertAlmostEqual(ask_usd, 0.45 * 50 + 0.46 * 80, places=3)

    def test_a_one_sided_book_has_no_mid(self):
        book = st.BookState()
        book.apply_snapshot([["0.40", "100"]], [])
        row = book.top_row("t", "snapshot")
        self.assertIsNone(row["mid"])
        self.assertIsNone(row["spread"])


class SequenceTests(unittest.TestCase):
    """The counter belongs to the subscription, not to a market."""

    def setUp(self):
        self.state = st.StreamState()

    def test_consecutive_sequences_across_markets_are_fine(self):
        # Genau der Livefall: vier Maerkte teilen sich einen Zaehler.
        self.state.handle(snapshot(market="A", seq=1), "r")
        self.state.handle(snapshot(market="B", seq=2), "r")
        self.state.handle(delta(market="A", seq=3), "r")
        self.state.handle(delta(market="B", seq=4), "r")
        self.assertEqual(self.state.seq_gaps, 0)

    def test_per_market_counting_would_have_flagged_that_as_gaps(self):
        # Regression: pro Markt gezaehlt saehe 1 -> 3 wie eine Luecke aus.
        self.state.handle(snapshot(market="A", seq=1), "r")
        self.state.handle(snapshot(market="B", seq=2), "r")
        self.state.handle(delta(market="A", seq=3), "r")
        self.assertFalse(self.state.needs_resync)

    def test_a_real_gap_is_detected(self):
        self.state.handle(snapshot(seq=1), "r")
        self.state.handle(delta(seq=9), "r")
        self.assertEqual(self.state.seq_gaps, 1)
        self.assertTrue(self.state.needs_resync)

    def test_a_gap_invalidates_every_book_not_just_one(self):
        self.state.handle(snapshot(market="A", seq=1), "r")
        self.state.handle(snapshot(market="B", seq=2), "r")
        self.state.handle(delta(market="A", seq=99), "r")
        self.assertTrue(all(b.broken for b in self.state.books.values()))

    def test_a_repeated_sequence_is_tolerated(self):
        self.state.handle(snapshot(seq=1), "r")
        self.state.handle(delta(seq=1), "r")
        self.assertEqual(self.state.seq_gaps, 0)

    def test_separate_subscriptions_keep_separate_counters(self):
        self.state.handle(snapshot(market="A", seq=1, sid=1), "r")
        self.state.handle(snapshot(market="B", seq=1, sid=2), "r")
        self.assertEqual(self.state.seq_gaps, 0)

    def test_a_missing_sequence_number_cannot_be_checked(self):
        self.state.handle(snapshot(seq=None), "r")
        self.assertEqual(self.state.seq_gaps, 0)


class StreamStateTests(unittest.TestCase):
    def setUp(self):
        self.state = st.StreamState()

    def test_a_snapshot_produces_a_row(self):
        self.state.handle(snapshot(), "r1")
        self.assertEqual(len(self.state.book_rows), 1)
        self.assertEqual(self.state.book_rows[0]["market_id"], "KXTEST")

    def test_a_delta_at_the_touch_produces_a_row(self):
        self.state.handle(snapshot(), "r1")
        self.state.handle(delta(price="0.41", amount="10"), "r2")
        self.assertEqual(len(self.state.book_rows), 2)
        self.assertAlmostEqual(self.state.book_rows[-1]["best_bid"], 0.41, places=6)

    def test_a_delta_deep_in_the_book_produces_nothing(self):
        self.state.handle(snapshot(), "r1")
        self.state.handle(delta(price="0.20", amount="10"), "r2")
        self.assertEqual(len(self.state.book_rows), 1)

    def test_a_sequence_gap_stops_rows_until_a_new_snapshot(self):
        # Zeilen aus einem Buch zu schreiben, von dem man weiss, dass es
        # falsch ist, ist schlimmer als gar keine zu schreiben.
        self.state.handle(snapshot(seq=1), "r1")
        self.state.handle(delta(seq=99), "r2")
        self.assertEqual(self.state.seq_gaps, 1)
        before = len(self.state.book_rows)
        self.state.handle(delta(seq=100, price="0.42"), "r3")
        self.assertEqual(len(self.state.book_rows), before)

    def test_a_fresh_snapshot_resumes_recording(self):
        self.state.handle(snapshot(seq=1), "r1")
        self.state.handle(delta(seq=99), "r2")
        self.state.handle(snapshot(seq=200, yes=[["0.42", "10"]]), "r3")
        self.assertAlmostEqual(self.state.book_rows[-1]["best_bid"], 0.42,
                               places=6)

    def test_a_trade_records_the_aggressor_side(self):
        self.state.handle({"type": "trade", "msg": {
            "market_ticker": "KXTEST", "taker_side": "yes", "yes_price_dollars": "0.33",
            "count_fp": "12", "ts": 1735689600, "trade_id": "abc"}}, "r1")
        row = self.state.trade_rows[0]
        self.assertEqual(row["side"], "BUY")
        self.assertAlmostEqual(row["price"], 0.33, places=6)

    def test_a_no_side_taker_is_a_sell_of_yes(self):
        self.state.handle({"type": "trade", "msg": {
            "market_ticker": "KXTEST", "taker_side": "no", "yes_price_dollars": "0.33",
            "count_fp": "5"}}, "r1")
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


class CrossedBookAlarmTests(unittest.TestCase):
    """A healthy book never crosses. Any count above zero is a convention bug."""

    def test_a_normal_book_never_counts_as_crossed(self):
        state = st.StreamState()
        state.handle(snapshot(), "r")
        self.assertEqual(state.crossed_books, 0)

    def test_an_inverted_book_is_counted(self):
        # Genau das Bild, das eine doppelte Spiegelung erzeugen wuerde.
        state = st.StreamState()
        state.handle(snapshot(yes=[["0.60", "10"]], no=[["0.40", "10"]]), "r")
        self.assertEqual(state.crossed_books, 1)

    def test_the_subscription_id_is_remembered_for_resync(self):
        state = st.StreamState()
        state.handle({"type": "subscribed", "msg": {"sid": 42,
                                                    "market_ticker": "A"}}, "r")
        self.assertEqual(state.sid, 42)


class SubscribeTests(unittest.TestCase):
    def test_the_frame_asks_for_books_and_trades(self):
        msg = ks.subscribe_message(["A", "B"])
        self.assertEqual(msg["cmd"], "subscribe")
        self.assertEqual(msg["params"]["market_tickers"], ["A", "B"])
        self.assertIn("orderbook_delta", msg["params"]["channels"])
        self.assertIn("trade", msg["params"]["channels"])

    def test_the_price_scale_flag_is_pinned_not_defaulted(self):
        # Kalshi kippt den Default; ohne explizites Setzen invertiert an dem
        # Tag jeder Spread lautlos.
        self.assertIs(ks.subscribe_message(["A"])["params"]["use_yes_price"],
                      True)

    def test_the_resnapshot_frame_targets_the_subscription(self):
        msg = ks.resnapshot_message(7, ["A", "B"])
        self.assertEqual(msg["cmd"], "update_subscription")
        self.assertEqual(msg["params"]["action"], "get_snapshot")
        self.assertEqual(msg["params"]["sids"], [7])

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
                             json.dumps(delta(price="0.41", amount="5"))])
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
                                          "taker_side": "yes", "yes_price_dollars": "0.40",
                                          "count_fp": "3"}}
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

    def test_a_quiet_market_is_not_treated_as_a_dead_socket(self):
        # Vorher brach der Lauf nach 90 Sekunden ohne Daten ab und baute die
        # Verbindung samt Marktauswahl neu auf. Bei langlaufenden Maerkten ist
        # Stille aber der Normalfall, nicht der Fehlerfall.
        socket = FakeSocket([])
        summary = ks.stream_once(["KXTEST"], self.out, 300, self.creds,
                                 ws_factory=lambda url, headers: socket,
                                 now_fn=self._clock(100.0))
        self.assertEqual(summary["stop_reason"], "Laufzeit erreicht")
        self.assertEqual(summary["errors"], [])

    def test_a_long_silence_does_end_the_cycle(self):
        socket = FakeSocket([])
        summary = ks.stream_once(["KXTEST"], self.out, 100000, self.creds,
                                 ws_factory=lambda url, headers: socket,
                                 now_fn=self._clock(400.0))
        self.assertIn("still", summary["stop_reason"])

    def test_a_connection_error_names_itself_as_the_stop_reason(self):
        socket = FakeSocket([ValueError("hart")])
        summary = ks.stream_once(["KXTEST"], self.out, 50, self.creds,
                                 ws_factory=lambda url, headers: socket,
                                 now_fn=self._clock())
        self.assertIn("Verbindungsfehler", summary["stop_reason"])

    def test_the_quiet_time_is_reported(self):
        socket = FakeSocket([json.dumps(snapshot())])
        summary = ks.stream_once(["KXTEST"], self.out, 20, self.creds,
                                 ws_factory=lambda url, headers: socket,
                                 now_fn=self._clock())
        self.assertGreaterEqual(summary["quiet_seconds"], 0.0)

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

    def test_the_pointer_may_live_in_the_project_env_file(self):
        # Der Normalfall fuer eine Scheduled Task: sie erbt die
        # Logon-Umgebung und weiss nichts von diesem Projekt.
        import os

        saved = os.environ.pop(ka.ENV_FILE_OVERRIDE, None)
        project_env = ka.REPO_ROOT / ".env"
        try:
            if project_env.exists():
                pointed = ka.read_selected_env(project_env,
                                               (ka.ENV_FILE_OVERRIDE,))
                if pointed.get(ka.ENV_FILE_OVERRIDE):
                    self.assertEqual(str(ka.env_file_candidates()[0]),
                                     str(Path(pointed[ka.ENV_FILE_OVERRIDE])))
        finally:
            if saved is not None:
                os.environ[ka.ENV_FILE_OVERRIDE] = saved

    def test_the_project_env_is_always_a_candidate(self):
        import os

        saved = os.environ.pop(ka.ENV_FILE_OVERRIDE, None)
        try:
            self.assertIn(ka.REPO_ROOT / ".env", ka.env_file_candidates())
        finally:
            if saved is not None:
                os.environ[ka.ENV_FILE_OVERRIDE] = saved

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
