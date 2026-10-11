"""Causal execution, protocol validation and decision gating for the CEX study."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from src.cex_leadlag import Config, replay, walk, write_report
from src.cex_leadlag_feed import parse_cex, parse_market, parse_polymarket


def event(ms, kind, **data):
    return {"t_ns": int(ms * 1_000_000), "wall_ns": int((1000 + ms / 1000) * 1e9),
            "kind": kind, **data}


def market():
    return event(0, "market", market={"id": "m", "slug": "test", "start_s": 900,
                 "end_s": 2000, "tokens": {"Up": "u", "Down": "d"}, "fee_rate": .07})


def book(ms, bid=.49, ask=.50, size=100):
    return event(ms, "book", token="u", snapshot=True,
                 bids=[[bid, size]], asks=[[ask, size]])


def price(ms, value):
    return event(ms, "price", source="binance", price=value, pair="BTCUSDT")


def stream():
    return [market(), book(0), price(0, 100), book(1000), price(1000, 100.1),
            book(1101, .69, .70), book(2000, .79, .80), event(2300, "clock")]


class ReplayTests(unittest.TestCase):
    def config(self, **kwargs):
        return Config(hold_ms=1000, cooldown_ms=5000, **kwargs)

    def test_entry_and_exit_use_only_book_known_at_deadline(self):
        result = replay(stream(), self.config(), latency_ms=100)
        trade = result["trades"][0]
        self.assertEqual(trade["entry_vwap"], .50)  # .70 arrives one ms too late
        self.assertEqual(trade["exit_vwap"], .79)
        self.assertAlmostEqual(trade["net_pnl"], 2.60887, places=5)
        self.assertEqual(result["summary"]["closed_trades"], 1)

    def test_quote_response_lag_is_measured_without_becoming_ai_input(self):
        result = replay(stream(), self.config(), latency_ms=100)
        observation = result["quote_responses"][0]
        self.assertEqual(observation["response_lag_ms"], 101)
        self.assertFalse(observation["censored"])
        self.assertNotIn("response_lag_ms", result["signals"][0]["features"])

    def test_disconnect_censors_quote_response_measurement(self):
        events = stream()[:5] + [event(1050, "status", source="polymarket", state="disconnected"),
                                book(1101, .69, .70), event(2300, "clock")]
        result = replay(events, self.config())
        self.assertTrue(result["quote_responses"][0]["censored"])
        self.assertIsNone(result["quote_responses"][0]["response_lag_ms"])

    def test_later_execution_observes_price_jump_and_skips(self):
        result = replay(stream(), self.config(), latency_ms=250)
        self.assertEqual(result["summary"]["closed_trades"], 0)
        self.assertEqual(result["skips"]["price_moved"], 1)

    def test_depth_and_fee_walk(self):
        fill = walk({.5: 2, .6: 3}, 4, buy=True, fee_rate=.07)
        self.assertAlmostEqual(fill["gross"], 2.2)
        self.assertAlmostEqual(fill["fee"], .0686)
        self.assertIsNone(walk({.5: 2}, 3, buy=True, fee_rate=.07))

    def test_missing_exit_is_open_not_a_fabricated_zero_pnl(self):
        result = replay(stream()[:6], self.config(), latency_ms=100)
        self.assertEqual(result["summary"]["open_positions"], 1)
        self.assertEqual(result["summary"]["closed_trades"], 0)
        self.assertIsNone(result["trades"][0]["net_pnl"])

    def test_budget_includes_entry_fee(self):
        result = replay(stream(), self.config(cash=5), latency_ms=100)
        self.assertEqual(result["skips"]["budget"], 1)

    def test_fees_use_metadata_available_at_execution_not_signal(self):
        changed = market()
        changed.update(t_ns=1_050_000_000, wall_ns=1_001_050_000_000)
        changed["market"]["fee_rate"] = .10
        events = stream() + [changed]
        trade = replay(events, self.config())["trades"][0]
        self.assertEqual(trade["entry_fee"], .25)
        self.assertEqual(trade["exit_fee"], .16590)

    def test_stale_exit_and_disconnect_do_not_fill(self):
        events = stream()[:5] + [event(1200, "status", source="polymarket", state="disconnected"),
                                event(2300, "clock")]
        result = replay(events, self.config(), latency_ms=100)
        self.assertEqual(result["summary"]["open_positions"], 1)
        self.assertEqual(result["skips"]["exit_no_book"], 1)

    def test_delta_before_snapshot_does_not_create_tradable_book(self):
        events = [market(), event(0, "book", token="u", snapshot=False,
                  changes=[[.5, 100, "SELL"], [.49, 100, "BUY"]]), price(0, 100),
                  price(1000, 100.1), event(2500, "clock")]
        self.assertEqual(replay(events, self.config())["signals"], [])

    def test_unknown_fees_cannot_trade(self):
        events = stream()
        events[0]["market"]["fee_rate"] = None
        self.assertEqual(replay(events, self.config())["signals"], [])

    def test_expiring_market_cannot_trade(self):
        events = stream()
        events[0]["market"]["end_s"] = 1002
        self.assertEqual(replay(events, self.config())["signals"], [])

    def test_jev_delay_is_added_and_missing_scores_abstain(self):
        baseline = replay(stream(), self.config(), latency_ms=100)
        sid = baseline["signals"][0]["signal_id"]
        scored = replay(stream(), self.config(), latency_ms=100,
                        decisions={sid: {"choice": "enter", "latency_ms": 150}})
        self.assertEqual(scored["skips"]["price_moved"], 1)
        self.assertEqual(replay(stream(), self.config(), decisions={})["skips"]["ai_abstain"], 1)

    def test_configuration_rejects_nonfinite_and_unbounded_inputs(self):
        for kwargs in ({"cash": float("nan")}, {"shares": 0}, {"hold_ms": -1}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                Config(**kwargs)

    def test_report_checks_capture_hash_and_has_matched_ai_control(self):
        with tempfile.TemporaryDirectory() as folder:
            run = Path(folder)
            capture = "".join(json.dumps(row) + "\n" for row in stream()).encode()
            (run / "events.jsonl").write_bytes(capture)
            (run / "manifest.json").write_text(json.dumps({"status": "complete", "data_loss": False,
                "events_sha256": hashlib.sha256(capture).hexdigest()}))
            report = write_report(run, self.config(), [100], decisions={})
            self.assertEqual([a["mode"] for a in report["arms"]], ["baseline", "scored_control", "jev_gate"])
            (run / "events.jsonl").write_bytes(capture + b"\n")
            with self.assertRaises(ValueError):
                write_report(run, self.config(), [100])


class FeedTests(unittest.TestCase):
    def test_cex_pairs_remain_distinct_and_bad_prices_are_rejected(self):
        msg = {"e": "aggTrade", "s": "BTCUSDT", "p": "100", "T": 123}
        self.assertEqual(parse_cex("binance", msg)["pair"], "BTCUSDT")
        for value in ("nan", "inf", "-1", True, "1e308"):
            self.assertIsNone(parse_cex("binance", {**msg, "p": value}))
        self.assertIsNone(parse_cex("binance", {**msg, "s": "ETHUSDT"}))

    def test_market_maps_labels_not_token_order(self):
        msg = {"id": "m", "slug": "btc-updown-5m-900", "active": True, "closed": False,
               "acceptingOrders": True, "endDate": "1970-01-01T00:20:00Z", "version": "v1",
               "outcomes": '["Down", "Up"]', "clobTokenIds": '["d", "u"]',
               "feesEnabled": True, "feeSchedule": {"exponent": 1, "rate": .07}}
        result = parse_market(msg, 300)
        self.assertEqual(result["tokens"], {"Down": "d", "Up": "u"})
        self.assertEqual(result["start_s"], 900)
        self.assertIsNone(parse_market({**msg, "closed": True}, 300))
        self.assertIsNone(parse_market({**msg, "version": "v3"}, 300))
        self.assertIsNone(parse_market({**msg, "feeSchedule": {"exponent": 2, "rate": .07}}, 300)
                          ["fee_rate"])

    def test_polymarket_rejects_unknown_sides_and_nonfinite_depth(self):
        self.assertEqual(parse_polymarket({"event_type": "price_change", "price_changes": [
            {"asset_id": "u", "price": ".5", "size": "2", "side": "UNKNOWN"}]}), [])
        self.assertEqual(parse_polymarket({"event_type": "book", "asset_id": "u",
            "bids": [{"price": "nan", "size": "2"}], "asks": []}), [])


if __name__ == "__main__":
    unittest.main()
