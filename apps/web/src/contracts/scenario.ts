/**
 * Client-side mirror of the scenario contract (packages/contracts/drikr_contracts/scenario.py).
 *
 * Used for immediate form feedback only. The backend re-validates every definition
 * (structure, cross-field rules and generation checks) and is authoritative.
 * src/contracts/scenario.test.ts fails if these enums drift from the exported JSON Schema.
 */
import { z } from "zod";

export const TERRAINS = ["urban", "rural", "coastal", "industrial"] as const;
export const TIMES_OF_DAY = ["day", "dusk", "night"] as const;
export const WEATHER = ["clear", "haze", "rain", "fog"] as const;
export const ENTITY_CLASSES = [
  "small_multirotor",
  "fixed_wing_uas",
  "coordinated_swarm",
  "bird_or_clutter",
] as const;
export const TRACK_CLASSIFICATIONS = [...ENTITY_CLASSES, "unknown"] as const;
export const BEHAVIORS = ["transit", "loiter", "orbit", "hover", "erratic"] as const;
export const FORMATIONS = ["line", "wedge", "cluster"] as const;
export const SENSOR_KINDS = ["radar", "electro_optical", "rf"] as const;
export const TRAINING_RESPONSES = [
  "continue_monitoring",
  "request_sensor_confirmation",
  "report_to_exercise_control",
  "log_as_cleared",
] as const;
export const CONFIDENCES = ["low", "medium", "high"] as const;
export const OBJECTIVE_KINDS = [
  "classify_correctly",
  "respond_within",
  "no_false_clearance",
  "classify_all",
] as const;
export const EVENT_KINDS = [
  "sensor_degraded",
  "sensor_restored",
  "visibility_change",
  "exercise_message",
] as const;

const slug = z.string().regex(/^[a-z0-9][a-z0-9-]{1,62}$/, "Use 2-63 lowercase letters, digits or hyphens");
const shortId = z
  .string()
  .regex(/^[a-z0-9][a-z0-9_-]{0,39}$/, "Use lowercase letters, digits, hyphens or underscores");

const range = (min: number, max: number) =>
  z
    .object({ min: z.number().min(min).max(max), max: z.number().min(min).max(max) })
    .refine((r) => r.min <= r.max, { message: "Minimum must not exceed maximum", path: ["max"] });

const objective = z.object({
  id: shortId,
  description: z.string().min(5).max(300),
  criterion: z.discriminatedUnion("kind", [
    z.object({
      kind: z.literal("classify_correctly"),
      entity_class: z.enum(ENTITY_CLASSES),
      min_fraction: z.number().min(0).max(1),
    }),
    z.object({
      kind: z.literal("respond_within"),
      entity_class: z.enum(ENTITY_CLASSES),
      response: z.enum(TRAINING_RESPONSES),
      within_s: z.number().gt(0).max(1800),
    }),
    z.object({ kind: z.literal("no_false_clearance") }),
    z.object({ kind: z.literal("classify_all"), min_fraction: z.number().min(0).max(1) }),
  ]),
});

const entityGroup = z
  .object({
    id: shortId,
    label: z.string().min(2).max(120),
    entity_class: z.enum(ENTITY_CLASSES),
    behavior: z.enum(BEHAVIORS),
    cooperative: z.boolean().default(false),
    count: range(1, 20),
    spawn_time_s: range(0, 1800),
    speed_mps: range(0, 60),
    altitude_m: range(5, 1500),
    closest_approach_m: range(0, 3600),
    dwell_s: range(0, 1800).nullable().optional(),
    swarm: z
      .object({
        size: range(3, 24),
        formation: z.enum(FORMATIONS).default("cluster"),
        spacing_m: z.number().min(5).max(200).default(30),
      })
      .nullable()
      .optional(),
  })
  .superRefine((g, ctx) => {
    const swarm = g.entity_class === "coordinated_swarm";
    if (swarm && !g.swarm)
      ctx.addIssue({ code: "custom", path: ["swarm"], message: "Swarm groups need a swarm configuration" });
    if (!swarm && g.swarm)
      ctx.addIssue({
        code: "custom",
        path: ["swarm"],
        message: "Only swarm groups may have a swarm configuration",
      });
    if (g.behavior === "hover" && g.entity_class === "fixed_wing_uas")
      ctx.addIssue({ code: "custom", path: ["behavior"], message: "Fixed-wing aircraft cannot hover" });
    if (g.entity_class === "bird_or_clutter" && g.cooperative)
      ctx.addIssue({
        code: "custom",
        path: ["cooperative"],
        message: "Birds and clutter cannot be cooperative",
      });
  });

const scheduled = z.discriminatedUnion("type", [
  z.object({
    type: z.literal("sensor_degraded"),
    id: shortId,
    at_s: z.number().min(0),
    sensor: z.enum(SENSOR_KINDS),
    detection_factor: z.number().min(0).max(1),
    noise_factor: z.number().min(1).max(5).default(1),
    extra_delay_s: z.number().min(0).max(10).default(0),
  }),
  z.object({
    type: z.literal("sensor_restored"),
    id: shortId,
    at_s: z.number().min(0),
    sensor: z.enum(SENSOR_KINDS),
  }),
  z.object({
    type: z.literal("visibility_change"),
    id: shortId,
    at_s: z.number().min(0),
    visibility_km: z.number().min(0.2).max(30),
  }),
  z.object({
    type: z.literal("exercise_message"),
    id: shortId,
    at_s: z.number().min(0),
    message: z.string().min(3).max(280),
  }),
]);

export const ScenarioSchema = z
  .object({
    schema_version: z.literal("1.0").default("1.0"),
    key: slug,
    version: z.number().int().min(1).default(1),
    name: z.string().min(3).max(120),
    description: z.string().min(10).max(2000),
    briefing: z.string().min(10).max(4000),
    learning_objectives: z.array(objective).min(1).max(10),
    environment: z
      .object({
        terrain: z.enum(TERRAINS),
        time_of_day: z.enum(TIMES_OF_DAY),
        weather: z.enum(WEATHER),
        visibility_km: z.number().min(0.2).max(30),
        wind_mps: z.number().min(0).max(25).default(3),
      })
      .refine((e) => e.weather !== "fog" || e.visibility_km <= 2, {
        path: ["visibility_km"],
        message: "Fog requires visibility of 2 km or less",
      })
      .refine((e) => e.weather !== "haze" || e.visibility_km <= 8, {
        path: ["visibility_km"],
        message: "Haze requires visibility of 8 km or less",
      }),
    // Defaults mirror RadarConfig / ElectroOpticalConfig / RfConfig in the Python contract.
    sensors: z
      .object({
        radar: z
          .object({
            enabled: z.boolean().default(true),
            range_m: z.number().min(500).max(10000).default(4000),
            update_interval_s: z.number().min(0.5).max(10).default(2),
            detection_probability: z.number().min(0.05).max(1).default(0.9),
            position_noise_m: z.number().min(0).max(250).default(25),
            latency_s: z.number().min(0).max(10).default(0.5),
            clutter_tracks_per_min: z.number().min(0).max(6).default(0),
          })
          .default({}),
        electro_optical: z
          .object({
            enabled: z.boolean().default(true),
            range_m: z.number().min(200).max(6000).default(2000),
            update_interval_s: z.number().min(0.5).max(10).default(3),
            detection_probability: z.number().min(0.05).max(1).default(0.8),
            classification_accuracy: z.number().min(0).max(1).default(0.75),
            latency_s: z.number().min(0).max(10).default(1),
          })
          .default({}),
        rf: z
          .object({
            enabled: z.boolean().default(true),
            range_m: z.number().min(200).max(8000).default(3000),
            update_interval_s: z.number().min(0.5).max(10).default(4),
            detection_probability: z.number().min(0.05).max(1).default(0.7),
            latency_s: z.number().min(0).max(10).default(1.5),
          })
          .default({}),
      })
      .default({}),
    entities: z.array(entityGroup).min(1).max(20),
    event_schedule: z.array(scheduled).max(50).default([]),
    randomization: z.object({
      seed: z.number().int().min(0).max(Number.MAX_SAFE_INTEGER),
      allow_seed_override: z.boolean().default(true),
    }),
    difficulty: z
      .object({
        level: z.number().int().min(1).max(5).default(3),
        adaptive_allowed: z.boolean().default(true),
        min_level: z.number().int().min(1).max(5).default(1),
        max_level: z.number().int().min(1).max(5).default(5),
      })
      .default({})
      .refine((d) => d.min_level <= d.level && d.level <= d.max_level, {
        path: ["level"],
        message: "Level must lie within the minimum and maximum",
      }),
    scoring: z.object({ rubric_key: slug, rubric_version: z.number().int().min(1) }),
    time_limits: z.object({
      duration_s: z.number().int().min(60).max(1800),
      allow_pause: z.boolean().default(true),
    }),
    self_guided: z.boolean().default(false),
  })
  .superRefine((s, ctx) => {
    const ids = s.entities.map((g) => g.id);
    if (new Set(ids).size !== ids.length)
      ctx.addIssue({ code: "custom", path: ["entities"], message: "Entity group ids must be unique" });
    s.entities.forEach((g, i) => {
      if (g.spawn_time_s.max > s.time_limits.duration_s - 30)
        ctx.addIssue({
          code: "custom",
          path: ["entities", i, "spawn_time_s", "max"],
          message: "Must spawn at least 30 s before the time limit",
        });
    });
    const sensorsOn = s.sensors.radar.enabled || s.sensors.electro_optical.enabled;
    if (!sensorsOn)
      ctx.addIssue({
        code: "custom",
        path: ["sensors"],
        message: "Enable radar or optical to produce positional tracks",
      });
  });

export type ScenarioDefinition = z.infer<typeof ScenarioSchema>;

export interface ClientIssue {
  path: string;
  message: string;
}

export function clientValidate(def: unknown): ClientIssue[] {
  const r = ScenarioSchema.safeParse(def);
  if (r.success) return [];
  return r.error.issues.map((i) => ({ path: i.path.join("."), message: i.message }));
}
