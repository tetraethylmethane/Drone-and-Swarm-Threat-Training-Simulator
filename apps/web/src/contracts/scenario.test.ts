/**
 * Contract drift test: the client-side Zod mirror must use exactly the enum values
 * exported from the authoritative Python contract (packages/contracts/schemas).
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import {
  BEHAVIORS,
  clientValidate,
  CONFIDENCES,
  ENTITY_CLASSES,
  FORMATIONS,
  SENSOR_KINDS,
  TERRAINS,
  TIMES_OF_DAY,
  TRACK_CLASSIFICATIONS,
  TRAINING_RESPONSES,
  WEATHER,
} from "./scenario";

const schemaDir = resolve(__dirname, "../../../../packages/contracts/schemas");
const scenarioSchema = JSON.parse(readFileSync(resolve(schemaDir, "scenario.schema.json"), "utf-8"));
const actionSchema = JSON.parse(readFileSync(resolve(schemaDir, "trainee-action.schema.json"), "utf-8"));
const demo = JSON.parse(
  readFileSync(
    resolve(
      __dirname,
      "../../../../packages/simcore/drikr_simcore/demo_scenarios/demo-perimeter-basics.json",
    ),
    "utf-8",
  ),
);

function enumOf(schema: { $defs: Record<string, { enum?: string[] }> }, name: string): string[] {
  const def = schema.$defs[name];
  if (!def?.enum) throw new Error(`enum ${name} not found in exported schema`);
  return [...def.enum].sort();
}

describe("scenario contract mirror", () => {
  it.each([
    ["Terrain", TERRAINS],
    ["TimeOfDay", TIMES_OF_DAY],
    ["Weather", WEATHER],
    ["EntityClass", ENTITY_CLASSES],
    ["Behavior", BEHAVIORS],
    ["Formation", FORMATIONS],
    ["SensorKind", SENSOR_KINDS],
    ["TrainingResponse", TRAINING_RESPONSES],
  ])("%s matches the exported JSON Schema", (name, values) => {
    expect([...values].sort()).toEqual(enumOf(scenarioSchema, name));
  });

  it("action enums match", () => {
    expect([...TRACK_CLASSIFICATIONS].sort()).toEqual(enumOf(actionSchema, "TrackClassification"));
    expect([...CONFIDENCES].sort()).toEqual(enumOf(actionSchema, "Confidence"));
  });

  it("accepts a bundled demo scenario", () => {
    expect(clientValidate(demo)).toEqual([]);
  });

  it("reports cross-field problems with paths", () => {
    const bad = structuredClone(demo);
    bad.environment.weather = "fog";
    bad.entities[0].speed_mps = { min: 20, max: 5 };
    bad.entities[1].entity_class = "coordinated_swarm";
    const paths = clientValidate(bad).map((i) => i.path);
    expect(paths).toContain("environment.visibility_km");
    expect(paths).toContain("entities.0.speed_mps.max");
    expect(paths).toContain("entities.1.swarm");
  });
});

describe("defaults", () => {
  it("accepts definitions that omit fields the backend defaults", () => {
    const minimal = structuredClone(demo);
    delete minimal.sensors;
    delete minimal.difficulty;
    delete minimal.event_schedule;
    delete minimal.self_guided;
    delete minimal.environment.wind_mps;
    for (const g of minimal.entities) delete g.cooperative;
    expect(clientValidate(minimal)).toEqual([]);
  });
});
