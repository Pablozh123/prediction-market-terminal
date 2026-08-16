"""Per-IP token-bucket rate limiter for the control-room API. Stdlib only.

The limiter itself knows nothing about FastAPI: it maps a key (normally a
client IP) to a bucket and answers "allowed?" plus "how long until the next
token?". The HTTP glue -- reading the client address, raising 429 -- lives in
api/server.py, so this module can be tested without a web framework.

Semantics: a bucket holds at most ``burst`` tokens and refills continuously at
``per_minute`` tokens per minute. Every request takes one token; a request
that finds the bucket empty is refused and told how many seconds until one
token is back. ``per_minute <= 0`` disables the limiter (everything passes),
which is the escape hatch for local development and tests.

Buckets live in memory per process. That is the right size for a single
uvicorn worker behind Caddy; anything larger belongs in Cloudflare's rate
rules, not here.
"""

from __future__ import annotations

import math
import threading
import time
from collections import OrderedDict
from typing import Callable


class RateLimited(Exception):
    """Raised (by the HTTP glue) when a bucket refuses a request."""

    def __init__(self, retry_after_s: int) -> None:
        super().__init__(f"rate limited, retry after {retry_after_s}s")
        self.retry_after_s = int(retry_after_s)


class TokenBucketLimiter:
    """Thread-safe token bucket keyed by an arbitrary string (the client IP).

    ``clock`` is injectable so tests can move time by hand; it must return
    seconds as a float and never go backwards (``time.monotonic`` does).
    ``max_keys`` bounds memory: the least recently seen key is evicted once
    the table is full, so a scan from many addresses cannot grow the process
    without limit.
    """

    def __init__(
        self,
        per_minute: float,
        burst: int,
        *,
        clock: Callable[[], float] = time.monotonic,
        max_keys: int = 10_000,
    ) -> None:
        self.per_minute = float(per_minute)
        self.burst = max(1, int(burst))
        self.rate_per_s = self.per_minute / 60.0
        self.enabled = self.per_minute > 0
        self._clock = clock
        self._max_keys = max(1, int(max_keys))
        self._lock = threading.Lock()
        # key -> [tokens, last_refill_ts]; OrderedDict gives LRU eviction.
        self._buckets: OrderedDict[str, list[float]] = OrderedDict()

    # -- core -------------------------------------------------------------

    def check(self, key: str) -> tuple[bool, float]:
        """Take one token for ``key``.

        Returns ``(allowed, retry_after_s)``. ``retry_after_s`` is 0.0 when
        allowed, otherwise the seconds until one full token has refilled.
        """

        if not self.enabled:
            return True, 0.0
        now = self._clock()
        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                bucket = [float(self.burst), now]
                self._buckets[key] = bucket
                while len(self._buckets) > self._max_keys:
                    self._buckets.popitem(last=False)
            else:
                elapsed = max(0.0, now - bucket[1])
                bucket[0] = min(float(self.burst), bucket[0] + elapsed * self.rate_per_s)
                bucket[1] = now
                self._buckets.move_to_end(key)
            if bucket[0] >= 1.0:
                bucket[0] -= 1.0
                return True, 0.0
            missing = 1.0 - bucket[0]
            return False, missing / self.rate_per_s

    def allow(self, key: str) -> bool:
        """``check`` reduced to the boolean; convenient in tests and glue."""

        return self.check(key)[0]

    def hit(self, key: str) -> None:
        """Take a token or raise :class:`RateLimited` with a whole-second wait."""

        allowed, wait = self.check(key)
        if not allowed:
            raise RateLimited(max(1, math.ceil(wait)))

    # -- introspection ------------------------------------------------------

    def tokens(self, key: str) -> float:
        """Current token count for ``key`` without consuming (tests, debugging)."""

        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                return float(self.burst)
            elapsed = max(0.0, self._clock() - bucket[1])
            return min(float(self.burst), bucket[0] + elapsed * self.rate_per_s)

    def __len__(self) -> int:
        with self._lock:
            return len(self._buckets)


def client_ip(forwarded_for: str | None, remote_host: str | None) -> str:
    """Pick the address a bucket is keyed on.

    Behind Caddy the connecting host is always the proxy and the visitor sits
    in the first hop of ``X-Forwarded-For`` (``forwarded_for`` is that header's
    value, or the value of whichever header the server was told to read).
    With no such header -- local development, direct access -- the socket peer
    is the client. Empty values fall through to ``"unknown"`` so a missing
    address still shares one bucket rather than bypassing the limit.

    Trust model, stated once: Caddy discards ``X-Forwarded-For`` from clients
    it does not list under ``trusted_proxies`` and writes the real peer, so
    with Caddy on the edge the first hop is the visitor. With Cloudflare in
    front of Caddy the peer Caddy sees is a Cloudflare edge and every visitor
    would share a handful of buckets; there the server must read
    ``CF-Connecting-IP`` instead (``RATE_LIMIT_IP_HEADER`` in api/server.py).
    A client that can reach port 8787 without passing the proxy can forge any
    of these headers -- which is why the compose file never publishes it.
    """

    if forwarded_for:
        first = forwarded_for.split(",", 1)[0].strip()
        if first:
            return first
    if remote_host:
        return str(remote_host).strip() or "unknown"
    return "unknown"
