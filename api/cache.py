"""Thread-safe TTL/LRU cache with a retained-payload budget.

The budget estimates Python containers and deep pandas storage. It is not an
RSS limit: computations and native allocators also need container headroom.
"""
from __future__ import annotations

import sys
import threading
import time
from collections import OrderedDict
from concurrent.futures import Future
from dataclasses import dataclass, fields, is_dataclass

import pandas as pd


def retained_size(value, budget: int) -> int:
    """Bound the accounting walk too; count shared/cyclic objects only once."""
    seen = set()
    pending = [value]
    total = 0
    while pending and total <= budget:
        item = pending.pop()
        identity = id(item)
        if identity in seen:
            continue
        seen.add(identity)
        if isinstance(item, pd.DataFrame):
            total += int(item.memory_usage(index=True, deep=True).sum())
        elif isinstance(item, pd.Series):
            total += int(item.memory_usage(index=True, deep=True))
        else:
            total += sys.getsizeof(item)
            if isinstance(item, dict):
                pending.extend(item.keys())
                pending.extend(item.values())
            elif isinstance(item, (list, tuple, set, frozenset)):
                pending.extend(item)
            elif is_dataclass(item) and not isinstance(item, type):
                pending.extend(getattr(item, field.name) for field in fields(item))
    return total


@dataclass
class Entry:
    created: float
    expires: float
    value: object
    size: int


class MemoryCache:
    def __init__(self, max_entries=512, max_bytes=64 * 1024 * 1024, clock=time.monotonic):
        self.max_entries = max_entries
        self.max_bytes = max_bytes
        self.clock = clock
        self._entries = OrderedDict()
        self._inflight = {}
        self._lock = threading.RLock()
        self._bytes = 0

    def _drop(self, key):
        entry = self._entries.pop(key)
        self._bytes -= entry.size
        return entry.value

    def expire(self):
        with self._lock:
            now = self.clock()
            for key in [k for k, entry in self._entries.items() if entry.expires <= now]:
                self._drop(key)

    def clear(self):
        with self._lock:
            self._entries.clear()
            self._bytes = 0

    def pop(self, key, default=None):
        with self._lock:
            return self._drop(key) if key in self._entries else default

    def refresh(self, key, value):
        """Reaccount a caller-mutated value, without touching a replacement.

        Backtests add price histories while computing. They call this in a
        finally block so even a failed computation cannot pin uncounted data.
        """
        with self._lock:
            entry = self._entries.get(key)
            if entry is None or entry.value is not value:
                return
            size = retained_size(value, self.max_bytes)
            if size > self.max_bytes:
                self._drop(key)
                return
            self._bytes += size - entry.size
            entry.size = size
            self.expire()
            while self._bytes > self.max_bytes:
                self._drop(next(iter(self._entries)))

    def stats(self):
        with self._lock:
            self.expire()
            return {"entries": len(self._entries), "bytes": self._bytes,
                    "max_bytes": self.max_bytes, "inflight": len(self._inflight)}

    def get_or_compute(self, key, fn, *args, ttl=30.0, **kwargs):
        with self._lock:
            self.expire()
            hit = self._entries.get(key)
            if hit and self.clock() - hit.created < ttl:
                self._entries.move_to_end(key)
                return hit.value
            if hit:
                self._drop(key)
            future = self._inflight.get(key)
            owner = future is None
            if owner:
                future = self._inflight[key] = Future()
        if not owner:
            return future.result()
        try:
            value = fn(*args, **kwargs)
            size = retained_size(value, self.max_bytes)
            with self._lock:
                self.expire()
                if ttl > 0 and size <= self.max_bytes:
                    while self._entries and (self._bytes + size > self.max_bytes
                                             or len(self._entries) >= self.max_entries):
                        self._drop(next(iter(self._entries)))
                    now = self.clock()
                    self._entries[key] = Entry(now, now + ttl, value, size)
                    self._bytes += size
                future.set_result(value)
                del self._inflight[key]
            return value
        except BaseException as exc:
            with self._lock:
                future.set_exception(exc)
                del self._inflight[key]
            raise
