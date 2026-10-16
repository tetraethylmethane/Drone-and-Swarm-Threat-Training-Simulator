"""In-process request timing for the System health page.

Measured, not estimated: every API request's duration is recorded against its route template
(for example ``GET /sessions/{session_id}/feed``) in a bounded window. Nothing leaves the
process; values reset when the API restarts.
"""

from __future__ import annotations

import math
import threading
import time
from collections import deque
from typing import Any

WINDOW = 20_000


def _percentile(sorted_ms: list[float], p: float) -> float:
    if not sorted_ms:
        return 0.0
    k = max(0, math.ceil(p / 100 * len(sorted_ms)) - 1)
    return sorted_ms[k]


class RequestMetrics:
    def __init__(self, window: int = WINDOW) -> None:
        self.started = time.time()
        self._lock = threading.Lock()
        self._samples: deque[tuple[str, float, int]] = deque(maxlen=window)
        self.total = 0

    def record(self, route: str, duration_ms: float, status: int) -> None:
        with self._lock:
            self._samples.append((route, duration_ms, status))
            self.total += 1

    def summary(self, top: int = 15) -> dict[str, Any]:
        with self._lock:
            samples = list(self._samples)
            total = self.total
        by_route: dict[str, list[tuple[float, int]]] = {}
        for route, ms, status in samples:
            by_route.setdefault(route, []).append((ms, status))
        rows: list[dict[str, Any]] = []
        for route, values in by_route.items():
            ms_sorted = sorted(v[0] for v in values)
            rows.append(
                {
                    "route": route,
                    "requests": len(values),
                    "p50_ms": round(_percentile(ms_sorted, 50), 1),
                    "p95_ms": round(_percentile(ms_sorted, 95), 1),
                    "max_ms": round(ms_sorted[-1], 1),
                    "server_errors": sum(1 for v in values if v[1] >= 500),
                }
            )
        rows.sort(key=lambda r: -int(r["requests"]))
        all_ms = sorted(ms for _, ms, _ in samples)
        return {
            "since": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.started)),
            "uptime_s": round(time.time() - self.started),
            "requests_total": total,
            "window": len(samples),
            "overall": {
                "p50_ms": round(_percentile(all_ms, 50), 1),
                "p95_ms": round(_percentile(all_ms, 95), 1),
                "server_errors": sum(1 for _, _, s in samples if s >= 500),
            },
            "routes": rows[:top],
            "note": "Measured by this API process since it started (most recent requests only). "
            "Server time only: network and browser rendering are not included.",
        }
