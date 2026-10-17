"""CPU-bound engine work in worker processes, so it does not hold the API process's interpreter lock.

The API is one Python process (rate limits, metrics and the session sweeper live in it, ADR-001).
Generating a timeline takes about 0.45 s of pure Python. With many trainees starting at once,
that held the interpreter lock long enough to delay other trainees' feed polls past the 15 s
connection grace, which paused their exercises (docs/testing/load-resilience-report.md, L-02).

Only pure, deterministic functions are sent to the pool (timeline generation). They give the same
result in any process (`test_fresh_interpreters_with_different_hash_seeds_agree`), so where they run
cannot change a record. Database access stays in the API process. With ``workers = 0``, the default
for the command line and tests, work runs inline.
"""

from __future__ import annotations

import multiprocessing
import threading
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor
from typing import Any, TypeVar

T = TypeVar("T")

_lock = threading.Lock()
_workers = 0
_executor: ProcessPoolExecutor | None = None


def configure(workers: int) -> None:
    """Set the number of worker processes (0 = inline). Started lazily on first use."""
    global _workers
    shutdown()
    _workers = max(0, workers)


def run(fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    global _executor
    if _workers <= 0:
        return fn(*args, **kwargs)
    with _lock:
        if _executor is None:
            _executor = ProcessPoolExecutor(_workers, mp_context=multiprocessing.get_context("spawn"))
        ex = _executor
    return ex.submit(fn, *args, **kwargs).result()


def shutdown() -> None:
    global _executor
    with _lock:
        ex, _executor = _executor, None
    if ex is not None:
        ex.shutdown(wait=True, cancel_futures=True)
