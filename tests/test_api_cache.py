"""Regression checks for retaining expired/large API payloads on a 1 GB host."""
import gc
import threading
import unittest
import weakref
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from api import server
from api.cache import MemoryCache, retained_size
from app import backtester as bt


class CacheRetentionTests(unittest.TestCase):
    def setUp(self):
        server._CACHE.clear()
        self.addCleanup(server._CACHE.clear)

    def test_unrelated_request_releases_expired_dataframe(self):
        frame = pd.DataFrame({"price": range(1000)})
        reference = weakref.ref(frame)
        server.cached("expired", lambda value: value, frame, ttl=-1)
        del frame
        server.cached("unrelated", lambda: "fresh")
        gc.collect()
        self.assertIsNone(reference(), "expired data must not wait for the same key to return")

    def test_large_payload_is_returned_but_not_retained(self):
        # A payload larger than the entire configured cache budget must remain
        # usable by its caller, without pinning it for the next ten minutes.
        payload = bytearray(65 * 1024 * 1024)
        result = server.cached("oversized", lambda: payload, ttl=600)
        self.assertIs(result, payload)
        self.assertEqual(server.cached("oversized", lambda: "recomputed"), "recomputed")

    def test_same_key_reuses_fresh_result(self):
        self.assertEqual(server.cached("fresh", lambda: 42), 42)
        self.assertEqual(server.cached("fresh", lambda: 99), 42)


class MemoryCacheTests(unittest.TestCase):
    def test_window_data_fields_cannot_bypass_budget(self):
        now = pd.Timestamp("2026-06-01", tz="UTC")
        data = bt.WindowData("0x" + "a" * 40, 30, now, now,
                             pd.DataFrame({"price": range(10000)}), False, {}, now)
        cache = MemoryCache(max_bytes=1024)
        cache.get_or_compute("window", lambda: data)
        self.assertEqual(cache.stats()["entries"], 0)

    def test_api_backtest_accounts_for_history_growth_and_preserves_variants(self):
        from unittest.mock import patch
        now = pd.Timestamp("2026-06-01", tz="UTC")
        wallet = "0x" + "a" * 40
        trades = pd.DataFrame([{"time": pd.Timestamp("2026-05-02", tz="UTC"),
                               "type": "TRADE", "side": "BUY", "outcome": "Yes",
                               "title": "Test", "price": .5, "size": 100., "notional": 50.,
                               "market_key": "cond-1", "asset": "tok-yes", "transactionHash": "0x1"}])
        data = bt.WindowData(wallet, 30, now - pd.Timedelta(days=30), now, trades,
                             False, {"tok-yes": {"price": .7, "closed": False, "end_time": None}}, now)
        history = pd.DataFrame({"time": pd.to_datetime(["2026-05-03", "2026-05-10", "2026-05-20"], utc=True),
                                "price": [.5, .1, .7]})
        server._CACHE.clear()
        self.addCleanup(server._CACHE.clear)
        with patch.object(server.btr, "load_window_data", return_value=data), \
             patch.object(server.md, "get_polymarket_price_history_lifetime", return_value=history) as upstream:
            first = server.backtest({"wallet": wallet, "window_days": 30, "stake_fixed": 25, "variants": True})
            second = server.backtest({"wallet": wallet, "window_days": 30, "stake_fixed": 10})
        self.assertEqual(first["data_rows"], 1)
        self.assertEqual(second["data_rows"], 1)
        self.assertIn("tok-yes", data.price_history)
        self.assertEqual(upstream.call_count, 1, "replays still reuse bounded history")
        self.assertTrue(any(row["max_drawdown"] < 0 for row in first["variants"]),
                        "variants must keep the actual marked-to-market drawdown")
        actual = sum(retained_size(entry.value, 2**30) for entry in server._CACHE._entries.values())
        self.assertEqual(server._CACHE.stats()["bytes"], actual)

    def test_refresh_evicts_payload_that_grows_after_insertion(self):
        cache = MemoryCache(max_bytes=1024)
        payload = {}
        cache.get_or_compute("growing", lambda: payload)
        payload["history"] = pd.DataFrame({"price": range(1000)})
        cache.refresh("growing", payload)
        self.assertEqual(cache.stats()["entries"], 0)
        self.assertEqual(cache.stats()["bytes"], 0)

    def test_refresh_of_evicted_value_does_not_overwrite_newer_entry(self):
        cache = MemoryCache()
        old = {}
        cache.get_or_compute("key", lambda: old)
        cache.pop("key")
        cache.get_or_compute("key", lambda: 42)
        old["history"] = bytearray(10000)
        cache.refresh("key", old)
        self.assertEqual(cache.get_or_compute("key", lambda: 0), 42)

    def test_expiry_releases_values_without_a_request_for_the_key(self):
        now = [0]
        cache = MemoryCache(clock=lambda: now[0])
        frame = pd.DataFrame({"price": range(1000)})
        reference = weakref.ref(frame)
        cache.get_or_compute("old", lambda value: value, frame, ttl=5)
        del frame
        self.assertIsNotNone(reference())
        now[0] = 5
        cache.expire()
        self.assertIsNone(reference())
        self.assertEqual(cache.stats()["bytes"], 0)

    def test_byte_budget_evicts_lru_even_below_entry_limit(self):
        cache = MemoryCache(max_entries=20, max_bytes=2500)
        for key in ("a", "b", "a", "c"):
            cache.get_or_compute(key, lambda: bytearray(1000))
        self.assertLessEqual(cache.stats()["bytes"], 2500)
        self.assertIsInstance(cache.get_or_compute("a", lambda: None), bytearray)
        self.assertEqual(cache.get_or_compute("b", lambda: "evicted"), "evicted")

    def test_entry_limit_and_invalidation_release_accounting(self):
        cache = MemoryCache(max_entries=2)
        for key in ("a", "b", "c"):
            cache.get_or_compute(key, lambda: bytearray(1000))
        self.assertEqual(cache.stats()["entries"], 2)
        cache.pop("b")
        cache.pop("c")
        self.assertEqual(cache.stats()["bytes"], 0)

    def test_nested_dataframe_and_cycles_are_accounted(self):
        data = pd.DataFrame({"text": ["x" * 1000] * 100})
        payload = {"data": data}
        payload["self"] = payload
        self.assertGreater(retained_size(payload, 200000), 100000)
        cache = MemoryCache(max_bytes=50000)
        cache.get_or_compute("big", lambda: payload)
        self.assertEqual(cache.stats()["entries"], 0)

    def test_concurrent_requests_share_oversized_result(self):
        cache = MemoryCache(max_bytes=1)
        started, release = threading.Event(), threading.Event()
        calls = []
        payload = bytearray(100)

        def compute():
            calls.append(1)
            started.set()
            self.assertTrue(release.wait(5))
            return payload

        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(cache.get_or_compute, "same", compute)
            self.assertTrue(started.wait(5))
            # Observe the waiter entering Future.result, without timing sleeps.
            from unittest.mock import patch
            from concurrent.futures import Future
            waiting = threading.Event()
            original = Future.result

            def wait(future, *args, **kwargs):
                waiting.set()
                return original(future, *args, **kwargs)

            with patch.object(Future, "result", wait):
                second = pool.submit(cache.get_or_compute, "same", compute)
                self.assertTrue(waiting.wait(5))
                release.set()
                self.assertIs(first.result(5), payload)
                self.assertIs(second.result(5), payload)
        self.assertEqual(len(calls), 1)
        self.assertEqual(cache.stats()["inflight"], 0)

    def test_failed_computation_can_be_retried_and_nested_keys_work(self):
        cache = MemoryCache()
        with self.assertRaises(ValueError):
            cache.get_or_compute("key", lambda: int("invalid"))
        self.assertEqual(cache.get_or_compute("key", lambda: cache.get_or_compute("child", lambda: 42)), 42)
