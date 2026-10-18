"""Pre-generated timelines, so a class can start at once (backlog B-17).

When a whole class starts together, every session creation used to generate its timeline then
(about 0.3 to 0.5 s of CPU each, two at a time in the worker pool), and creation slowed to over 10 s at
p95 (docs/testing/load-resilience-report.md 5.8). The inputs of an assignment's first attempt are
known when the instructor creates it, so its timeline is generated in the background then.

The cache is **content-addressed**: the key is the session's ``config_digest`` (scenario definition,
seed, difficulty level and engine version). Generation is deterministic, so a cached timeline is
exactly the one that would be generated now. Different inputs (another seed, an adversary plan) are
simply a miss. Entries are compressed (``drikr_simcore.packed``) and the total is bounded
(``DRIKR_TIMELINE_CACHE_MB``); the least recently used entries are dropped first. The cache lives in
the API process (the supported deployment is one process), so a restart empties it, which only
costs speed.
"""

from __future__ import annotations

import logging
import threading
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from drikr_api import cpu
from drikr_simcore.packed import PackedTimeline, generate_packed

log = logging.getLogger("drikr.api")


class TimelineCache:
    def __init__(self, max_bytes: int) -> None:
        self.max_bytes = max_bytes
        self._items: OrderedDict[str, PackedTimeline] = OrderedDict()
        self._bytes = 0
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> PackedTimeline | None:
        with self._lock:
            item = self._items.get(key)
            if item is None:
                self.misses += 1
                return None
            self._items.move_to_end(key)
            self.hits += 1
            return item

    def __contains__(self, key: str) -> bool:
        with self._lock:
            return key in self._items

    def put(self, key: str, item: PackedTimeline) -> None:
        size = len(item.blob)
        if self.max_bytes <= 0 or size > self.max_bytes:
            return
        with self._lock:
            old = self._items.pop(key, None)
            if old is not None:
                self._bytes -= len(old.blob)
            self._items[key] = item
            self._bytes += size
            while self._bytes > self.max_bytes:
                _, dropped = self._items.popitem(last=False)
                self._bytes -= len(dropped.blob)

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "entries": len(self._items),
                "bytes": self._bytes,
                "max_bytes": self.max_bytes,
                "hits": self.hits,
                "misses": self.misses,
            }


_cache = TimelineCache(0)
_prewarm: ThreadPoolExecutor | None = None
_prewarm_lock = threading.Lock()


def configure(max_mb: int) -> None:
    global _cache
    shutdown()
    _cache = TimelineCache(max_mb * 1024 * 1024)


def shutdown() -> None:
    global _prewarm
    with _prewarm_lock:
        ex, _prewarm = _prewarm, None
    if ex is not None:
        ex.shutdown(wait=False, cancel_futures=True)


def stats() -> dict[str, Any]:
    return _cache.stats()


def timeline(key: str, definition: dict[str, Any], seed: int, level: int) -> PackedTimeline:
    """The packed timeline for these inputs: from the cache, or generated now (and not cached)."""
    hit = _cache.get(key)
    if hit is not None:
        return hit
    return cpu.run(generate_packed, definition, seed, level)


def prewarm(key: str, definition: dict[str, Any], seed: int, level: int) -> bool:
    """Generate in the background and keep the result; returns False when nothing was queued."""
    global _prewarm
    if _cache.max_bytes <= 0 or key in _cache:
        return False
    with _prewarm_lock:
        if _prewarm is None:
            # One at a time: pre-generation should not compete with exercises already running.
            _prewarm = ThreadPoolExecutor(max_workers=1, thread_name_prefix="timeline-prewarm")
        ex = _prewarm

    def work() -> None:
        try:
            _cache.put(key, cpu.run(generate_packed, definition, seed, level))
        except Exception:  # pre-generation only saves time; a failure must never fail a request
            log.exception("timeline_prewarm_failed")

    ex.submit(work)
    return True


def wait_idle(timeout: float = 30.0) -> None:
    """Block until queued pre-generation has finished (tests and the CLI)."""
    with _prewarm_lock:
        ex = _prewarm
    if ex is not None:
        ex.submit(lambda: None).result(timeout=timeout)
