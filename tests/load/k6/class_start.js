// Synchronised class start (backlog B-17): an instructor assigns one exercise to every trainee,
// the trainees sign in and open their assignment, and all of them start at the same moment, as
// when an instructor says "begin". Each trainee then runs one exercise, as in exercise.js.
//
// The burst measured is session creation (drikr_create_session_ms) plus the first exercise.
// Sign-ins happen before the start, so their Argon2 cost is not part of the burst.
import http from "k6/http";
import { check, sleep } from "k6";
import { Counter, Rate, Trend } from "k6/metrics";

const BASE = __ENV.BASE_URL || "http://host.docker.internal:9080/api/v1";
const PASSWORD = __ENV.LT_USER_PASSWORD;
const N = Number(__ENV.VUS || 30);
const FIRST = Number(__ENV.FIRST_TRAINEE || 41); // lt-041 onwards: earlier accounts may hold open sessions
const EXERCISE_S = Number(__ENV.EXERCISE_S || 90);
const PREP_S = Number(__ENV.PREP_S || 30); // between assigning and the start
const SCENARIO_KEY = __ENV.SCENARIO_KEY || "demo-perimeter-basics";

export const options = {
  setupTimeout: "300s",
  scenarios: {
    class: { executor: "per-vu-iterations", vus: N, iterations: 1, maxDuration: "10m" },
  },
  summaryTrendStats: ["min", "med", "avg", "p(90)", "p(95)", "p(99)", "max", "count"],
};

const createMs = new Trend("drikr_create_session_ms", true);
const feedMs = new Trend("drikr_feed_ms", true);
const actionMs = new Trend("drikr_action_ms", true);
const completeMs = new Trend("drikr_complete_ms", true);
const failed = new Rate("drikr_failed_requests");
const scored = new Counter("drikr_sessions_scored");
const paused = new Counter("drikr_sessions_paused");

function login(user) {
  const r = http.post(`${BASE}/auth/login`, JSON.stringify({ username: user, password: PASSWORD, mode: "token" }), {
    headers: { "Content-Type": "application/json" },
    timeout: "60s",
  });
  if (r.status !== 200) throw new Error(`sign-in failed for ${user}: ${r.status}`);
  return { token: r.json("access_token"), id: r.json("user.id") };
}

function call(token, method, path, body, trend) {
  const r = http.request(method, `${BASE}${path}`, body === undefined ? null : JSON.stringify(body), {
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    timeout: "60s",
  });
  failed.add(r.status === 0 || r.status >= 500);
  if (trend) trend.add(r.timings.duration);
  return r;
}

function uuid() {
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    return (c === "x" ? r : (r & 0x3) | 0x8).toString(16);
  });
}

export function setup() {
  const trainees = [];
  for (let i = FIRST; i < FIRST + N; i++) trainees.push(login(`lt-${String(i).padStart(3, "0")}`));
  const instructor = login("lt-instructor");
  const scenario = (call(instructor.token, "GET", "/scenarios").json("items") || []).find((s) => s.key === SCENARIO_KEY);
  const r = call(instructor.token, "POST", "/assignments", {
    scenario_id: scenario.id,
    trainee_ids: trainees.map((t) => t.id),
    title: `Class start ${new Date().toISOString()}`,
    difficulty_level: 2,
    min_level: 1,
    max_level: 4,
    max_attempts: 1,
  });
  if (r.status !== 201) throw new Error(`assignment failed: ${r.status} ${r.body}`);
  const byTrainee = {};
  for (const a of r.json("items")) byTrainee[a.trainee.id] = a.id;
  if (trainees.some((t) => !byTrainee[t.id])) throw new Error("an assignment is missing for a trainee");
  return {
    tokens: trainees.map((t) => t.token),
    assignments: trainees.map((t) => byTrainee[t.id]),
    startAt: Date.now() + PREP_S * 1000,
  };
}

export default function (data) {
  const token = data.tokens[__VU - 1];
  const wait = (data.startAt - Date.now()) / 1000;
  if (wait > 0) sleep(wait);
  const created = call(token, "POST", "/sessions", { assignment_id: data.assignments[__VU - 1] }, createMs);
  if (!check(created, { "session created": (r) => r.status === 201 })) return;
  const sid = created.json("id");
  call(token, "POST", `/sessions/${sid}/start`);
  const seen = new Set();
  let since = 0;
  let wasPaused = false;
  const end = Date.now() + EXERCISE_S * 1000;
  while (Date.now() < end) {
    sleep(1);
    const r = call(token, "GET", `/sessions/${sid}/feed?since_ms=${since}`, undefined, feedMs);
    if (r.status !== 200) continue;
    const body = r.json();
    since = body.state.sim_time_ms;
    if (body.state.status === "paused") {
      wasPaused = true;
      call(token, "POST", `/sessions/${sid}/resume`);
      continue;
    }
    for (const e of body.events) {
      if (e.type === "track_observation" && !seen.has(e.payload.track_id)) {
        seen.add(e.payload.track_id);
        call(token, "POST", `/sessions/${sid}/actions`, {
          client_action_id: uuid(),
          kind: "classify",
          track_ids: [e.payload.track_id],
          classification: "small_multirotor",
          confidence: "medium",
        }, actionMs);
      }
    }
  }
  if (wasPaused) paused.add(1);
  call(token, "POST", `/sessions/${sid}/complete`, undefined, completeMs);
  const res = call(token, "GET", `/sessions/${sid}/result`);
  if (res.status === 200 && res.json("status") === "scored") scored.add(1);
}
