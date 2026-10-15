/**
 * Browser simulation adapter: drives an exercise through the documented session API.
 *
 * - Polls GET /sessions/{id}/feed (which is also the heartbeat) about once per second
 *   while running, and less often otherwise.
 * - De-duplicates events by event_id, so overlapping windows and reconnects are safe.
 * - Submits actions with a client-generated client_action_id and retries on network
 *   failure with the same id; the server records each action exactly once.
 * - Interpolates the displayed clock between polls but always resynchronises to the
 *   server's authoritative simulation time.
 */
import { useCallback, useEffect, useRef, useState } from "react";

import { api, ApiError } from "@/lib/api";
import type { FeedResponse, SessionState, SimEvent } from "@/lib/types";

import { applyEvents, emptyPicture, type Picture } from "./trackPicture";

const RUNNING_POLL_MS = 1000;
const IDLE_POLL_MS = 4000;

export interface ActionBody {
  kind: "classify" | "respond";
  track_ids: string[];
  classification?: string;
  confidence?: string;
  response?: string;
  note?: string;
}

export function useExercise(sessionId: string) {
  const [state, setState] = useState<SessionState | null>(null);
  const [picture, setPicture] = useState<Picture>(emptyPicture);
  const [connection, setConnection] = useState<"ok" | "retrying">("ok");
  const [error, setError] = useState<ApiError | null>(null);
  const [displayMs, setDisplayMs] = useState(0);
  const seen = useRef(new Set<string>());
  const pictureRef = useRef<Picture>(emptyPicture());
  const sinceRef = useRef(0);
  const syncRef = useRef<{ simMs: number; wall: number; running: boolean }>({
    simMs: 0,
    wall: 0,
    running: false,
  });

  const ingest = useCallback((events: SimEvent[]) => {
    const fresh = events.filter((e) => !seen.current.has(e.event_id));
    if (!fresh.length) return;
    fresh.forEach((e) => seen.current.add(e.event_id));
    pictureRef.current = applyEvents(pictureRef.current, fresh);
    // New object identity so React re-renders; the Maps inside are reused for efficiency.
    setPicture({ ...pictureRef.current });
  }, []);

  // The feed carries live state only; the trainee-safe briefing is loaded once.
  const briefingRef = useRef<SessionState["briefing"]>(undefined);
  useEffect(() => {
    const ctrl = new AbortController();
    api
      .get<SessionState>(`/sessions/${sessionId}`, ctrl.signal)
      .then((s) => {
        briefingRef.current = s.briefing;
        setState((prev) => (prev ? { ...prev, briefing: s.briefing } : s));
      })
      .catch(() => undefined); // the polling loop reports errors
    return () => ctrl.abort();
  }, [sessionId]);

  const applyState = useCallback((s: SessionState) => {
    setState({ ...s, briefing: s.briefing ?? briefingRef.current });
    syncRef.current = { simMs: s.sim_time_ms, wall: performance.now(), running: s.status === "running" };
    setDisplayMs(s.sim_time_ms);
  }, []);

  const poll = useCallback(async () => {
    try {
      const res = await api.get<FeedResponse>(`/sessions/${sessionId}/feed?since_ms=${sinceRef.current}`);
      ingest(res.events);
      // Inclusive lower bound next time; duplicates are removed by event_id.
      sinceRef.current = res.state.sim_time_ms;
      applyState(res.state);
      setConnection("ok");
      setError(null);
    } catch (err) {
      if (err instanceof ApiError && err.status !== 0 && err.status < 500 && err.status !== 429) {
        setError(err);
      } else {
        setConnection("retrying");
      }
    }
  }, [sessionId, ingest, applyState]);

  // Initial load and polling loop.
  useEffect(() => {
    let stopped = false;
    let timer: number | undefined;
    const loop = async () => {
      await poll();
      if (stopped) return;
      const running = syncRef.current.running;
      timer = window.setTimeout(loop, running ? RUNNING_POLL_MS : IDLE_POLL_MS);
    };
    loop();
    return () => {
      stopped = true;
      if (timer) window.clearTimeout(timer);
    };
  }, [poll]);

  // Smooth clock between polls (display only).
  useEffect(() => {
    const id = window.setInterval(() => {
      const s = syncRef.current;
      if (!s.running || !state) return;
      const est = s.simMs + (performance.now() - s.wall);
      setDisplayMs(Math.min(est, s.simMs + 2000, state.duration_ms));
    }, 200);
    return () => window.clearInterval(id);
  }, [state]);

  const transition = useCallback(
    async (op: "start" | "pause" | "resume" | "complete") => {
      const s = await api.post<SessionState>(`/sessions/${sessionId}/${op}`);
      applyState(s);
      await poll();
      return s;
    },
    [sessionId, applyState, poll],
  );

  const submit = useCallback(
    async (body: ActionBody) => {
      const payload = { client_action_id: crypto.randomUUID(), ...body };
      let lastErr: unknown;
      for (let attempt = 0; attempt < 3; attempt++) {
        try {
          const res = await api.post<{
            event: SimEvent;
            duplicate: boolean;
            confirmations: SimEvent[];
            state: SessionState;
          }>(`/sessions/${sessionId}/actions`, payload);
          ingest([res.event]);
          applyState(res.state);
          return res;
        } catch (err) {
          lastErr = err;
          // Retry only when the outcome is unknown (network failure or server unavailable).
          if (!(err instanceof ApiError) || (err.status !== 0 && err.status < 500)) throw err;
          await new Promise((r) => setTimeout(r, 500 * (attempt + 1)));
        }
      }
      throw lastErr;
    },
    [sessionId, ingest, applyState],
  );

  return { state, picture, connection, error, displayMs, transition, submit, refresh: poll };
}
