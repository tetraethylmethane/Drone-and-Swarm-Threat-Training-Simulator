/**
 * Builds the trainee's track picture from trainee-visible events only.
 *
 * This is the browser simulation adapter's state model. It never sees ground
 * truth: it is a pure projection of the event feed the backend delivered, so the
 * displayed state always agrees with the recorded event log.
 */
import type { SimEvent } from "@/lib/types";

export interface TrackPoint {
  t_ms: number;
  x: number;
  y: number;
  alt: number | null;
}

export interface Track {
  id: string;
  firstSeenMs: number;
  lastSeenMs: number;
  lastPositionalMs: number | null;
  sensors: Set<string>;
  observations: number;
  position: TrackPoint | null;
  trail: TrackPoint[];
  speed: number | null;
  bearing: number | null;
  quality: number;
  classHint: { value: string; quality: number; source: "optical" | "confirmation"; t_ms: number } | null;
  beacon: boolean;
  lost: boolean;
  classification: { value: string; confidence: string; t_ms: number } | null;
  response: { value: string; t_ms: number } | null;
  pendingConfirmation: boolean;
}

export interface SensorStatus {
  sensor: string;
  status: "nominal" | "degraded";
  detection_factor: number;
  noise_factor: number;
  extra_delay_s: number;
  since_ms: number;
}

export interface Picture {
  tracks: Map<string, Track>;
  sensors: Map<string, SensorStatus>;
  visibilityKm: number | null;
  messages: { t_ms: number; text: string; id: string }[];
  decisions: SimEvent[];
  lifecycle: SimEvent[];
}

const TRAIL_LENGTH = 12;

function newTrack(id: string, t: number): Track {
  return {
    id,
    firstSeenMs: t,
    lastSeenMs: t,
    lastPositionalMs: null,
    sensors: new Set(),
    observations: 0,
    position: null,
    trail: [],
    speed: null,
    bearing: null,
    quality: 0,
    classHint: null,
    beacon: false,
    lost: false,
    classification: null,
    response: null,
    pendingConfirmation: false,
  };
}

export function emptyPicture(): Picture {
  return {
    tracks: new Map(),
    sensors: new Map(),
    visibilityKm: null,
    messages: [],
    decisions: [],
    lifecycle: [],
  };
}

/** Apply events (in any order) to a picture. Events must be de-duplicated by event_id by the caller. */
export function applyEvents(picture: Picture, events: SimEvent[]): Picture {
  const sorted = [...events].sort((a, b) => a.t_ms - b.t_ms || a.seq - b.seq);
  for (const ev of sorted) {
    const p = ev.payload as Record<string, unknown>;
    switch (ev.type) {
      case "track_observation": {
        const id = p.track_id as string;
        const tr = picture.tracks.get(id) ?? newTrack(id, ev.t_ms);
        picture.tracks.set(id, tr);
        tr.observations += 1;
        tr.sensors.add(p.sensor as string);
        tr.firstSeenMs = Math.min(tr.firstSeenMs, ev.t_ms);
        if (ev.t_ms >= tr.lastSeenMs) {
          tr.lastSeenMs = ev.t_ms;
          tr.lost = false;
        }
        tr.quality = Math.max(tr.quality * 0.9, Number(p.quality ?? 0));
        if (typeof p.x_m === "number" && typeof p.y_m === "number") {
          const pt: TrackPoint = {
            t_ms: ev.t_ms,
            x: p.x_m,
            y: p.y_m,
            alt: typeof p.alt_m === "number" ? p.alt_m : (tr.position?.alt ?? null),
          };
          if (!tr.position || ev.t_ms >= tr.position.t_ms) tr.position = pt;
          tr.trail = [...tr.trail, pt].sort((a, b) => a.t_ms - b.t_ms).slice(-TRAIL_LENGTH);
          tr.lastPositionalMs = Math.max(tr.lastPositionalMs ?? 0, ev.t_ms);
        }
        if (typeof p.speed_mps === "number") tr.speed = p.speed_mps;
        if (typeof p.bearing_deg === "number") tr.bearing = p.bearing_deg;
        if (p.beacon === true) tr.beacon = true;
        if (typeof p.class_hint === "string" && (!tr.classHint || ev.t_ms >= tr.classHint.t_ms)) {
          tr.classHint = {
            value: p.class_hint,
            quality: Number(p.quality ?? 0),
            source: "optical",
            t_ms: ev.t_ms,
          };
        }
        break;
      }
      case "sensor_confirmation": {
        const id = p.track_id as string;
        const tr = picture.tracks.get(id);
        if (!tr) break;
        tr.pendingConfirmation = false;
        if (p.outcome === "hint_available" && typeof p.class_hint === "string") {
          tr.classHint = {
            value: p.class_hint,
            quality: Number(p.quality ?? 0),
            source: "confirmation",
            t_ms: ev.t_ms,
          };
        }
        break;
      }
      case "track_lost": {
        const tr = picture.tracks.get(p.track_id as string);
        if (tr && ev.t_ms >= tr.lastSeenMs) tr.lost = true;
        break;
      }
      case "sensor_status":
        picture.sensors.set(p.sensor as string, { ...(p as unknown as SensorStatus), since_ms: ev.t_ms });
        break;
      case "environment_update":
        picture.visibilityKm = Number(p.visibility_km);
        break;
      case "exercise_message":
        picture.messages = [...picture.messages, { t_ms: ev.t_ms, text: String(p.message), id: ev.event_id }];
        break;
      case "classification_submitted":
        for (const id of p.track_ids as string[]) {
          const tr = picture.tracks.get(id);
          if (tr)
            tr.classification = {
              value: p.classification as string,
              confidence: p.confidence as string,
              t_ms: ev.t_ms,
            };
        }
        picture.decisions = [...picture.decisions, ev];
        break;
      case "response_submitted":
        for (const id of p.track_ids as string[]) {
          const tr = picture.tracks.get(id);
          if (!tr) continue;
          tr.response = { value: p.response as string, t_ms: ev.t_ms };
          if (p.response === "request_sensor_confirmation") tr.pendingConfirmation = true;
        }
        picture.decisions = [...picture.decisions, ev];
        break;
      case "session_started":
      case "session_paused":
      case "session_resumed":
      case "session_completed":
        picture.lifecycle = [...picture.lifecycle, ev];
        break;
      default:
        break;
    }
  }
  return picture;
}

export function sortedTracks(picture: Picture): Track[] {
  return [...picture.tracks.values()].sort((a, b) => a.id.localeCompare(b.id));
}
