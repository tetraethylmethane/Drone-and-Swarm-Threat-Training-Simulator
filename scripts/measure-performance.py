"""Measure one complete exercise against a running deployment and print the timings as JSON.

    DRIKR_BENCH_PASSWORD=<password> python scripts/measure-performance.py \
        --api https://localhost:8443/api/v1 --ca deploy/tls/ca.crt --user trainee2 --polls 30

Client-side wall-clock timings (network included) for: sign-in, session creation and start, feed
polling at one request per second, decision submission, completion with scoring, result retrieval
and PDF export. Uses a practice scenario, so it creates one real session in the target database.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import time
import uuid
from typing import Any

import httpx


def pct(values: list[float], p: float) -> float:
    s = sorted(values)
    return round(s[max(0, int(round(p / 100 * len(s))) - 1)], 1) if s else 0.0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", required=True)
    ap.add_argument("--ca", default=None)
    ap.add_argument("--user", default="trainee2")
    ap.add_argument("--polls", type=int, default=30)
    ap.add_argument("--scenario", default="demo-perimeter-basics")
    args = ap.parse_args()
    password = os.environ["DRIKR_BENCH_PASSWORD"]
    trusted_roots = args.ca if args.ca else True  # CA certificate file, or the system trust store
    client = httpx.Client(base_url=args.api, verify=trusted_roots, timeout=60)
    t: dict[str, Any] = {}

    def timed(name: str, method: str, path: str, **kw: Any) -> httpx.Response:
        start = time.perf_counter()
        r = client.request(method, path, **kw)
        t.setdefault(name, []).append((time.perf_counter() - start) * 1000)
        r.raise_for_status()
        return r

    creds = {"username": args.user, "password": password, "mode": "token"}
    timed("login_first_ms", "POST", "/auth/login", json=creds)  # includes connection setup
    token = timed("login_ms", "POST", "/auth/login", json=creds)
    client.headers["Authorization"] = f"Bearer {token.json()['access_token']}"
    items = timed("list_scenarios_ms", "GET", "/scenarios").json()["items"]
    scenario = next(i for i in items if i["key"] == args.scenario)
    session = timed("create_session_ms", "POST", "/sessions", json={"scenario_id": scenario["id"]}).json()
    sid = session["id"]
    timed("start_ms", "POST", f"/sessions/{sid}/start")
    since, tracks, events = 0, set(), 0
    for _ in range(args.polls):
        time.sleep(1)
        body = timed("feed_ms", "GET", f"/sessions/{sid}/feed", params={"since_ms": since}).json()
        since = body["state"]["sim_time_ms"]
        events += len(body["events"])
        tracks |= {e["payload"]["track_id"] for e in body["events"] if e["type"] == "track_observation"}
    for tid in sorted(tracks):
        timed(
            "action_ms",
            "POST",
            f"/sessions/{sid}/actions",
            json={
                "client_action_id": str(uuid.uuid4()),
                "kind": "classify",
                "track_ids": [tid],
                "classification": "small_multirotor",
                "confidence": "medium",
            },
        )
    timed("complete_and_score_ms", "POST", f"/sessions/{sid}/complete")
    result = timed("result_ms", "GET", f"/sessions/{sid}/result").json()
    timed("pdf_export_ms", "GET", f"/reports/sessions/{sid}.pdf")
    summary: dict[str, Any] = {
        "api": args.api,
        "scenario": scenario["key"],
        "feed_polls": args.polls,
        "events_received": events,
        "tracks": len(tracks),
        "overall": result.get("overall"),
    }
    for name, values in t.items():
        summary[name] = (
            {
                "n": len(values),
                "median": round(statistics.median(values), 1),
                "p95": pct(values, 95),
                "max": round(max(values), 1),
            }
            if len(values) > 1
            else round(values[0], 1)
        )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
