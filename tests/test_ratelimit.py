"""Tests fuer api/ratelimit.py — der Token-Bucket hinter /api/backtest und /api/risk."""

from __future__ import annotations

import threading
import unittest

from api.ratelimit import RateLimited, TokenBucketLimiter, client_ip


class FakeClock:
    """Uhr von Hand: die Tests bewegen die Zeit, nicht der Rechner."""

    def __init__(self, start: float = 1_000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class BurstAndBlockTests(unittest.TestCase):
    def test_allows_burst_then_blocks(self) -> None:
        clock = FakeClock()
        limiter = TokenBucketLimiter(per_minute=6, burst=3, clock=clock)
        for i in range(3):
            allowed, wait = limiter.check("1.2.3.4")
            self.assertTrue(allowed, f"request {i + 1} of the burst must pass")
            self.assertEqual(wait, 0.0)
        allowed, wait = limiter.check("1.2.3.4")
        self.assertFalse(allowed, "fourth request within the same instant must be refused")
        # 6/min = one token per 10 s; the bucket is empty, so a full token is 10 s away.
        self.assertAlmostEqual(wait, 10.0, places=6)

    def test_hit_raises_with_whole_second_retry(self) -> None:
        clock = FakeClock()
        limiter = TokenBucketLimiter(per_minute=6, burst=1, clock=clock)
        limiter.hit("k")
        with self.assertRaises(RateLimited) as ctx:
            limiter.hit("k")
        self.assertEqual(ctx.exception.retry_after_s, 10)
        clock.advance(0.5)
        with self.assertRaises(RateLimited) as ctx:
            limiter.hit("k")
        # 9.5 s remaining is reported as 10, never rounded down to a wait that is too short.
        self.assertEqual(ctx.exception.retry_after_s, 10)

    def test_disabled_when_rate_is_zero(self) -> None:
        limiter = TokenBucketLimiter(per_minute=0, burst=1, clock=FakeClock())
        self.assertFalse(limiter.enabled)
        for _ in range(50):
            self.assertTrue(limiter.allow("anyone"))


class RefillTests(unittest.TestCase):
    def test_refills_over_time(self) -> None:
        clock = FakeClock()
        limiter = TokenBucketLimiter(per_minute=6, burst=3, clock=clock)
        for _ in range(3):
            self.assertTrue(limiter.allow("ip"))
        self.assertFalse(limiter.allow("ip"))
        clock.advance(9.0)
        self.assertFalse(limiter.allow("ip"), "9 s is short of one token at 10 s per token")
        clock.advance(1.0)
        self.assertTrue(limiter.allow("ip"), "after 10 s exactly one token is back")
        self.assertFalse(limiter.allow("ip"), "and only one")

    def test_refill_is_capped_at_burst(self) -> None:
        clock = FakeClock()
        limiter = TokenBucketLimiter(per_minute=6, burst=3, clock=clock)
        self.assertTrue(limiter.allow("ip"))
        clock.advance(3_600.0)
        self.assertAlmostEqual(limiter.tokens("ip"), 3.0)
        for _ in range(3):
            self.assertTrue(limiter.allow("ip"))
        self.assertFalse(limiter.allow("ip"), "an hour idle does not bank more than the burst")

    def test_partial_refill_accumulates(self) -> None:
        clock = FakeClock()
        limiter = TokenBucketLimiter(per_minute=60, burst=1, clock=clock)  # 1 token/s
        self.assertTrue(limiter.allow("ip"))
        clock.advance(0.4)
        self.assertFalse(limiter.allow("ip"))
        clock.advance(0.4)
        self.assertFalse(limiter.allow("ip"))
        clock.advance(0.2)
        self.assertTrue(limiter.allow("ip"), "0.4 + 0.4 + 0.2 s add up to the one token")


class PerKeyTests(unittest.TestCase):
    def test_separate_buckets_per_ip(self) -> None:
        limiter = TokenBucketLimiter(per_minute=6, burst=2, clock=FakeClock())
        self.assertTrue(limiter.allow("10.0.0.1"))
        self.assertTrue(limiter.allow("10.0.0.1"))
        self.assertFalse(limiter.allow("10.0.0.1"))
        self.assertTrue(limiter.allow("10.0.0.2"), "a second address starts with a full bucket")
        self.assertTrue(limiter.allow("10.0.0.2"))
        self.assertFalse(limiter.allow("10.0.0.2"))
        self.assertFalse(limiter.allow("10.0.0.1"), "the first address is still empty")

    def test_evicts_least_recently_seen_key(self) -> None:
        limiter = TokenBucketLimiter(per_minute=6, burst=1, clock=FakeClock(), max_keys=2)
        self.assertTrue(limiter.allow("a"))
        self.assertTrue(limiter.allow("b"))
        self.assertTrue(limiter.allow("c"))  # evicts "a"
        self.assertEqual(len(limiter), 2)
        self.assertTrue(limiter.allow("a"), "an evicted key comes back with a fresh bucket")
        self.assertFalse(limiter.allow("c"), "the surviving key keeps its (empty) bucket")

    def test_thread_safety_never_over_admits(self) -> None:
        limiter = TokenBucketLimiter(per_minute=6, burst=25, clock=FakeClock())
        admitted: list[bool] = []
        lock = threading.Lock()

        def worker() -> None:
            for _ in range(20):
                ok = limiter.allow("shared")
                with lock:
                    admitted.append(ok)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(len(admitted), 160)
        self.assertEqual(sum(admitted), 25, "exactly the burst is admitted, however the threads interleave")


class ClientIpTests(unittest.TestCase):
    def test_prefers_first_hop_of_forwarded_for(self) -> None:
        self.assertEqual(client_ip("203.0.113.9, 172.18.0.5", "172.18.0.5"), "203.0.113.9")
        self.assertEqual(client_ip("  203.0.113.9  ", "172.18.0.5"), "203.0.113.9")

    def test_falls_back_to_remote_host(self) -> None:
        self.assertEqual(client_ip(None, "127.0.0.1"), "127.0.0.1")
        self.assertEqual(client_ip("", "127.0.0.1"), "127.0.0.1")
        self.assertEqual(client_ip(" , ", "127.0.0.1"), "127.0.0.1")

    def test_unknown_when_nothing_is_known(self) -> None:
        self.assertEqual(client_ip(None, None), "unknown")
        self.assertEqual(client_ip("", ""), "unknown")


if __name__ == "__main__":
    unittest.main()
