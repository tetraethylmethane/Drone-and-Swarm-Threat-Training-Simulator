// Load model: each virtual user is one trainee running practice exercises back to back, exactly as
// the web and Unity clients do (tests/load/README.md):
//   sign in once -> create session -> start -> poll the feed every 1 s -> classify each new track
//   -> finish after EXERCISE_S seconds -> read the result.
// A paused session (e.g. after an API restart longer than the 15 s grace) is resumed, like a
// trainee pressing Resume.
import http from "k6/http";
import { check, sleep } from "k6";
import { Counter, Rate, Trend } from "k6/metrics";

const BASE = __ENV.BASE_URL || "http://host.docker.internal:9080/api/v1";
const PASSWORD = __ENV.LT_USER_PASSWORD;
const EXERCISE_S = Number(__ENV.EXERCISE_S || 90);
const SCENARIO_KEY = __ENV.SCENARIO_KEY || "demo-perimeter-basics";

export const options = {
  scenarios: {
    trainees: {
      executor: "constant-vus",
      vus: Number(__ENV.VUS || 10),
      duration: __ENV.DURATION || "5m",
      gracefulStop: "120s",
    },
  },
  summaryTrendStats: ["min", "med", "avg", "p(90)", "p(95)", "p(99)", "max", "count"],
  // Raw thresholds are reported, not used to stop the run; acceptance is judged in the report.
};

const feedMs = new Trend("drikr_feed_ms", true);
const actionMs = new Trend("drikr_action_ms", true);
const completeMs = new Trend("drikr_complete_ms", true);
const createMs = new Trend("drikr_create_session_ms", true);
const failed = new Rate("drikr_failed_requests");
const completed = new Counter("drikr_sessions_completed");
const scored = new Counter("drikr_sessions_scored");
const resumed = new Counter("drikr_sessions_resumed");
const inconsistent = new Counter("drikr_inconsistent_results");

let token = null;
let scenarioId = null;

function headers() {
  return { headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` }, timeout: "30s" };
}

function req(method, path, body, trend) {
  const r = http.request(method, `${BASE}${path}`, body === undefined ? null : JSON.stringify(body), headers());
  failed.add(r.status === 0 || r.status >= 500);
  if (trend) trend.add(r.timings.duration);
  return r;
}

function signIn() {
  const user = `lt-${String(__VU).padStart(3, "0")}`;
  const r = http.post(`${BASE}/auth/login`, JSON.stringify({ username: user, password: PASSWORD, mode: "token" }), {
    headers: { "Content-Type": "application/json" },
    timeout: "30s",
  });
  failed.add(r.status !== 200);
  if (r.status !== 200) return false;
  token = r.json("access_token");
  const list = req("GET", "/scenarios");
  const item = (list.json("items") || []).find((s) => s.key === SCENARIO_KEY);
  scenarioId = item ? item.id : null;
  return scenarioId !== null;
}

function uuid() {
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    return (c === "x" ? r : (r & 0x3) | 0x8).toString(16);
  });
}

function finishOpenSessions() {
  const list = req("GET", "/sessions?limit=50");
  for (const s of list.json("items") || []) {
    if (s.status === "created") req("POST", `/sessions/${s.id}/start`);
    if (["created", "running", "paused"].includes(s.status)) req("POST", `/sessions/${s.id}/complete`);
  }
}

export default function () {
  if ((!token || !scenarioId) && !signIn()) {
    sleep(5);
    return;
  }
  const created = req("POST", "/sessions", { scenario_id: scenarioId, selection: {} }, createMs);
  if (created.status === 409) {
    // A session from an interrupted run is still open: finish it, as a returning trainee would.
    finishOpenSessions();
    return;
  }
  if (!check(created, { "session created": (r) => r.status === 201 })) {
    sleep(2);
    return;
  }
  const sid = created.json("id");
  req("POST", `/sessions/${sid}/start`);
  const seen = new Set();
  const accepted = new Set(); // classifications the server accepted (e.g. not refused while paused)
  let since = 0;
  const end = Date.now() + EXERCISE_S * 1000;
  while (Date.now() < end) {
    sleep(1);
    const r = req("GET", `/sessions/${sid}/feed?since_ms=${since}`, undefined, feedMs);
    if (r.status !== 200) continue;
    const body = r.json();
    since = body.state.sim_time_ms;
    if (body.state.status === "paused") {
      resumed.add(1);
      req("POST", `/sessions/${sid}/resume`);
      continue;
    }
    for (const e of body.events) {
      if (e.type === "track_observation" && !seen.has(e.payload.track_id)) {
        seen.add(e.payload.track_id);
        const r = req(
          "POST",
          `/sessions/${sid}/actions`,
          {
            client_action_id: uuid(),
            kind: "classify",
            track_ids: [e.payload.track_id],
            classification: "small_multirotor",
            confidence: "medium",
          },
          actionMs,
        );
        if (r.status === 200) accepted.add(e.payload.track_id);
      }
    }
  }
  const done = req("POST", `/sessions/${sid}/complete`, undefined, completeMs);
  if (done.status === 200) completed.add(1);
  const result = req("GET", `/sessions/${sid}/result`);
  if (result.status === 200) {
    const res = result.json();
    if (res.status === "scored") scored.add(1);
    // Consistency: every classification the server accepted must be reflected in the stored result.
    const classified = (res.counts && res.counts.classified_tracks) || 0;
    if (res.status === "scored" && classified < Math.min(accepted.size, res.counts.observable_tracks)) {
      inconsistent.add(1);
      // Enough to trace the session in the database afterwards (no credentials or tokens).
      console.warn(
        `inconsistent_result session=${sid} accepted=${JSON.stringify([...accepted])} counts=${JSON.stringify(res.counts)}`,
      );
    }
  }
}
