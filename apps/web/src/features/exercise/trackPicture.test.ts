import { describe, expect, it } from "vitest";

import type { SimEvent } from "@/lib/types";

import { applyEvents, emptyPicture, sortedTracks } from "./trackPicture";

let seq = 0;
function ev(type: string, t_ms: number, payload: Record<string, unknown>): SimEvent {
  seq += 1;
  return {
    event_id: `G-${String(seq).padStart(6, "0")}`,
    seq,
    t_ms,
    available_at_ms: t_ms,
    type,
    visibility: "trainee",
    origin: "generated",
    payload,
  };
}

describe("track picture", () => {
  it("builds tracks from observations regardless of arrival order", () => {
    const events = [
      ev("track_observation", 4000, {
        track_id: "TRK-001",
        sensor: "radar",
        synthetic: true,
        quality: 0.8,
        x_m: 20,
        y_m: 10,
        alt_m: 50,
      }),
      ev("track_observation", 2000, {
        track_id: "TRK-001",
        sensor: "radar",
        synthetic: true,
        quality: 0.7,
        x_m: 10,
        y_m: 5,
        alt_m: 50,
      }),
      ev("track_observation", 3000, {
        track_id: "TRK-001",
        sensor: "electro_optical",
        synthetic: true,
        quality: 0.6,
        x_m: 12,
        y_m: 6,
        class_hint: "bird_or_clutter",
      }),
    ];
    const a = applyEvents(emptyPicture(), events);
    const b = applyEvents(emptyPicture(), [...events].reverse());
    for (const pic of [a, b]) {
      const tr = pic.tracks.get("TRK-001")!;
      expect(tr.position).toMatchObject({ x: 20, y: 10 });
      expect(tr.firstSeenMs).toBe(2000);
      expect(tr.observations).toBe(3);
      expect([...tr.sensors].sort()).toEqual(["electro_optical", "radar"]);
      expect(tr.classHint?.value).toBe("bird_or_clutter");
      expect(tr.trail.map((p) => p.t_ms)).toEqual([2000, 3000, 4000]);
    }
  });

  it("marks tracks lost and recovers on new observations", () => {
    let pic = applyEvents(emptyPicture(), [
      ev("track_observation", 1000, {
        track_id: "TRK-002",
        sensor: "radar",
        synthetic: true,
        quality: 0.5,
        x_m: 0,
        y_m: 0,
      }),
      ev("track_lost", 9000, { track_id: "TRK-002" }),
    ]);
    expect(pic.tracks.get("TRK-002")!.lost).toBe(true);
    pic = applyEvents(pic, [
      ev("track_observation", 12000, {
        track_id: "TRK-002",
        sensor: "radar",
        synthetic: true,
        quality: 0.5,
        x_m: 1,
        y_m: 1,
      }),
    ]);
    expect(pic.tracks.get("TRK-002")!.lost).toBe(false);
  });

  it("records trainee decisions and pending confirmations", () => {
    let pic = applyEvents(emptyPicture(), [
      ev("track_observation", 1000, {
        track_id: "TRK-003",
        sensor: "rf",
        synthetic: true,
        quality: 0.5,
        bearing_deg: 45,
        beacon: true,
      }),
      ev("classification_submitted", 2000, {
        track_ids: ["TRK-003"],
        classification: "small_multirotor",
        confidence: "low",
        client_action_id: "a",
      }),
      ev("response_submitted", 2500, {
        track_ids: ["TRK-003"],
        response: "request_sensor_confirmation",
        client_action_id: "b",
      }),
    ]);
    const tr = pic.tracks.get("TRK-003")!;
    expect(tr.beacon).toBe(true);
    expect(tr.position).toBeNull();
    expect(tr.classification).toMatchObject({ value: "small_multirotor", confidence: "low" });
    expect(tr.pendingConfirmation).toBe(true);
    pic = applyEvents(pic, [
      ev("sensor_confirmation", 6500, {
        track_id: "TRK-003",
        outcome: "hint_available",
        class_hint: "small_multirotor",
        quality: 0.9,
        synthetic: true,
      }),
    ]);
    expect(pic.tracks.get("TRK-003")!.pendingConfirmation).toBe(false);
    expect(pic.tracks.get("TRK-003")!.classHint).toMatchObject({ source: "confirmation", quality: 0.9 });
    expect(pic.decisions).toHaveLength(2);
  });

  it("tracks sensor status, visibility and messages", () => {
    const pic = applyEvents(emptyPicture(), [
      ev("sensor_status", 0, {
        sensor: "radar",
        status: "nominal",
        detection_factor: 1,
        noise_factor: 1,
        extra_delay_s: 0,
      }),
      ev("sensor_status", 5000, {
        sensor: "radar",
        status: "degraded",
        detection_factor: 0.5,
        noise_factor: 2,
        extra_delay_s: 1,
      }),
      ev("environment_update", 0, { visibility_km: 3 }),
      ev("exercise_message", 100, { message: "Exercise control: begin." }),
    ]);
    expect(pic.sensors.get("radar")).toMatchObject({ status: "degraded", since_ms: 5000 });
    expect(pic.visibilityKm).toBe(3);
    expect(pic.messages[0]!.text).toContain("begin");
    expect(sortedTracks(pic)).toEqual([]);
  });
});
