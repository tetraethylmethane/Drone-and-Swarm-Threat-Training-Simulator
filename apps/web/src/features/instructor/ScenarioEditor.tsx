/**
 * Structured scenario editor. Every save creates a new immutable version.
 * Client-side Zod checks give immediate feedback; the server's two-layer
 * validation (structure + generation checks) is authoritative and runs before saving.
 */
import { useMemo, useState, type ReactNode } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Field, Input, Select, Textarea } from "@/components/ui/form";
import { Checkbox, Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/overlay";
import { PageHeader, Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { Alert } from "@/components/ui/status";
import { ErrorState, LoadingState } from "@/components/ui/states";
import {
  BEHAVIORS,
  clientValidate,
  ENTITY_CLASSES,
  EVENT_KINDS,
  FORMATIONS,
  OBJECTIVE_KINDS,
  SENSOR_KINDS,
  TERRAINS,
  TIMES_OF_DAY,
  TRAINING_RESPONSES,
  WEATHER,
} from "@/contracts/scenario";
import { api, ApiError } from "@/lib/api";
import { CLASSIFICATION_LABELS, ENV_LABELS, label, RESPONSE_LABELS, SENSOR_LABELS } from "@/lib/labels";
import type { RubricSummary, ScenarioDetail, ValidationIssue, ValidationReport } from "@/lib/types";
import { errorMessage, useAsync } from "@/lib/useAsync";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Def = Record<string, any>;

const BLANK: Def = {
  schema_version: "1.0",
  key: "",
  version: 1,
  name: "",
  description: "",
  briefing: "",
  learning_objectives: [
    {
      id: "no-false-clear",
      description: "Do not log a non-cooperative virtual drone as cleared.",
      criterion: { kind: "no_false_clearance" },
    },
  ],
  environment: { terrain: "rural", time_of_day: "day", weather: "clear", visibility_km: 15, wind_mps: 3 },
  sensors: {
    radar: {
      enabled: true,
      range_m: 4000,
      update_interval_s: 2,
      detection_probability: 0.9,
      position_noise_m: 25,
      latency_s: 0.5,
      clutter_tracks_per_min: 0,
    },
    electro_optical: {
      enabled: true,
      range_m: 2000,
      update_interval_s: 3,
      detection_probability: 0.8,
      classification_accuracy: 0.75,
      latency_s: 1,
    },
    rf: { enabled: true, range_m: 3000, update_interval_s: 4, detection_probability: 0.7, latency_s: 1.5 },
  },
  entities: [newGroup(1)],
  event_schedule: [],
  randomization: { seed: 1, allow_seed_override: true },
  difficulty: { level: 3, adaptive_allowed: true, min_level: 1, max_level: 5 },
  scoring: { rubric_key: "standard-assessment", rubric_version: 1 },
  time_limits: { duration_s: 300, allow_pause: true },
  self_guided: false,
};

function newGroup(n: number): Def {
  return {
    id: `group-${n}`,
    label: "Non-cooperative multirotor",
    entity_class: "small_multirotor",
    behavior: "loiter",
    cooperative: false,
    count: { min: 1, max: 1 },
    spawn_time_s: { min: 10, max: 40 },
    speed_mps: { min: 8, max: 12 },
    altitude_m: { min: 40, max: 100 },
    closest_approach_m: { min: 500, max: 900 },
    dwell_s: { min: 60, max: 120 },
    swarm: null,
  };
}

function setPath(obj: Def, path: (string | number)[], value: unknown): Def {
  const copy: Def = Array.isArray(obj) ? ([...obj] as unknown as Def) : { ...obj };
  const [head, ...rest] = path;
  if (head === undefined) return obj;
  copy[head as string] = rest.length ? setPath((obj[head as string] ?? {}) as Def, rest, value) : value;
  return copy;
}

function num(v: string): number {
  return v === "" ? Number.NaN : Number(v);
}

function NumberField({
  label: l,
  value,
  onChange,
  step = "any",
  hint,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  step?: string;
  hint?: string;
}) {
  return (
    <Field label={l} hint={hint}>
      <Input
        type="number"
        step={step}
        value={Number.isFinite(value) ? value : ""}
        onChange={(e) => onChange(num(e.target.value))}
      />
    </Field>
  );
}

function RangeField({
  label: l,
  value,
  onChange,
  unit,
}: {
  label: string;
  value: { min: number; max: number } | null | undefined;
  onChange: (v: { min: number; max: number }) => void;
  unit: string;
}) {
  const v = value ?? { min: 0, max: 0 };
  return (
    <fieldset>
      <legend className="mb-1.5 text-xs font-medium">
        {l} <span className="font-normal text-ink-subtle">({unit})</span>
      </legend>
      <div className="grid grid-cols-2 gap-2">
        <Input
          aria-label={`${l} minimum`}
          type="number"
          step="any"
          value={Number.isFinite(v.min) ? v.min : ""}
          onChange={(e) => onChange({ ...v, min: num(e.target.value) })}
        />
        <Input
          aria-label={`${l} maximum`}
          type="number"
          step="any"
          value={Number.isFinite(v.max) ? v.max : ""}
          onChange={(e) => onChange({ ...v, max: num(e.target.value) })}
        />
      </div>
    </fieldset>
  );
}

function Section({
  title,
  description,
  children,
  actions,
}: {
  title: string;
  description?: string;
  children: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <Panel>
      <PanelHeader title={title} description={description} actions={actions} />
      <PanelBody className="space-y-4">{children}</PanelBody>
    </Panel>
  );
}

export function ScenarioEditorPage({ mode }: { mode: "new" | "version" }) {
  const { scenarioId } = useParams();
  const location = useLocation();
  const initial = (location.state as { definition?: Def } | null)?.definition;
  const existing = useAsync(
    (sig) =>
      mode === "version" && scenarioId
        ? api.get<ScenarioDetail>(`/scenarios/${scenarioId}`, sig)
        : Promise.resolve(null),
    [mode, scenarioId],
  );
  if (existing.loading) return <LoadingState rows={8} />;
  if (existing.error) return <ErrorState error={existing.error} onRetry={existing.reload} />;
  const start = mode === "version" && existing.data ? (existing.data.definition as Def) : (initial ?? BLANK);
  return <Editor mode={mode} initial={start} sourceVersion={existing.data?.version} />;
}

function Editor({
  mode,
  initial,
  sourceVersion,
}: {
  mode: "new" | "version";
  initial: Def;
  sourceVersion?: number;
}) {
  const navigate = useNavigate();
  const [def, setDef] = useState<Def>(initial);
  const [json, setJson] = useState(() => JSON.stringify(initial, null, 2));
  const [jsonError, setJsonError] = useState<string | null>(null);
  const [report, setReport] = useState<ValidationReport | null>(null);
  const [saveError, setSaveError] = useState<{ message: string; issues?: ValidationIssue[] } | null>(null);
  const [busy, setBusy] = useState<"validate" | "save" | null>(null);
  const rubrics = useAsync(
    (sig) => api.get<{ items: RubricSummary[] }>("/rubrics?all_versions=true", sig),
    [],
  );
  const presets = useAsync(
    (sig) =>
      api.get<{
        environment_presets: { id: string; label: string; environment: Def; sensor_overrides: Def }[];
      }>("/scenarios/presets", sig),
    [],
  );
  const clientIssues = useMemo(() => clientValidate(def), [def]);

  const update = (path: (string | number)[], value: unknown) => {
    setDef((d) => setPath(d, path, value));
    setReport(null);
  };
  const list = (key: string) => (def[key] as Def[]) ?? [];

  async function validate() {
    setBusy("validate");
    setSaveError(null);
    try {
      setReport(await api.post<ValidationReport>("/scenarios/validate", { definition: def }));
    } catch (err) {
      setSaveError({ message: errorMessage(err) });
    } finally {
      setBusy(null);
    }
  }

  async function save() {
    setBusy("save");
    setSaveError(null);
    try {
      const path = mode === "new" ? "/scenarios" : `/scenarios/key/${def.key}/versions`;
      const saved = await api.post<{ id: string }>(path, { definition: def });
      navigate(`/instructor/scenarios/${saved.id}`);
    } catch (err) {
      const issues =
        err instanceof ApiError && Array.isArray(err.details)
          ? (err.details as ValidationIssue[])
          : undefined;
      setSaveError({ message: errorMessage(err), issues });
    } finally {
      setBusy(null);
    }
  }

  return (
    <>
      <PageHeader
        eyebrow={
          <Link to="/instructor/scenarios" className="hover:underline">
            Scenarios
          </Link>
        }
        title={mode === "new" ? "New scenario" : `New version of ${def.name}`}
        description={
          mode === "new"
            ? "Define the virtual exercise. Validation runs the scenario with its seed before it can be saved."
            : `Editing creates version ${(sourceVersion ?? 0) + 1}; version ${sourceVersion} and its sessions are unchanged.`
        }
      />
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_340px]">
        <Tabs
          defaultValue="form"
          onValueChange={(v) => {
            if (v === "json") setJson(JSON.stringify(def, null, 2));
          }}
        >
          <TabsList className="mb-4">
            <TabsTrigger value="form">Form</TabsTrigger>
            <TabsTrigger value="json">Definition (JSON)</TabsTrigger>
          </TabsList>
          <TabsContent value="form" className="space-y-4">
            <Section title="1. Basics">
              <div className="grid gap-3 sm:grid-cols-2">
                <Field
                  label="Key"
                  hint={
                    mode === "new"
                      ? "Permanent identifier, e.g. night-loiter-urban"
                      : "Fixed for all versions"
                  }
                >
                  <Input
                    value={def.key}
                    disabled={mode === "version"}
                    onChange={(e) => update(["key"], e.target.value.toLowerCase())}
                  />
                </Field>
                <Field label="Name">
                  <Input value={def.name} onChange={(e) => update(["name"], e.target.value)} />
                </Field>
              </div>
              <Field label="Description" hint="Shown to instructors and in the practice library.">
                <Textarea value={def.description} onChange={(e) => update(["description"], e.target.value)} />
              </Field>
              <Field label="Trainee briefing">
                <Textarea
                  className="min-h-[110px]"
                  value={def.briefing}
                  onChange={(e) => update(["briefing"], e.target.value)}
                />
              </Field>
              <Checkbox
                id="self-guided"
                checked={Boolean(def.self_guided)}
                onCheckedChange={(v) => update(["self_guided"], v)}
                label="Available in the self-guided practice library"
              />
            </Section>

            <Section
              title="2. Learning objectives"
              actions={
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() =>
                    update(
                      ["learning_objectives"],
                      [
                        ...list("learning_objectives"),
                        {
                          id: `objective-${list("learning_objectives").length + 1}`,
                          description: "",
                          criterion: { kind: "classify_all", min_fraction: 0.8 },
                        },
                      ],
                    )
                  }
                >
                  Add objective
                </Button>
              }
            >
              {list("learning_objectives").map((o, i) => (
                <div key={i} className="rounded border border-border p-3">
                  <div className="grid gap-3 sm:grid-cols-[160px_1fr_auto]">
                    <Field label="Id">
                      <Input
                        value={o.id}
                        onChange={(e) => update(["learning_objectives", i, "id"], e.target.value)}
                      />
                    </Field>
                    <Field label="Description">
                      <Input
                        value={o.description}
                        onChange={(e) => update(["learning_objectives", i, "description"], e.target.value)}
                      />
                    </Field>
                    <div className="flex items-end">
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() =>
                          update(
                            ["learning_objectives"],
                            list("learning_objectives").filter((_, j) => j !== i),
                          )
                        }
                      >
                        Remove
                      </Button>
                    </div>
                  </div>
                  <div className="mt-3 grid gap-3 sm:grid-cols-4">
                    <Field label="Criterion">
                      <Select
                        value={o.criterion.kind}
                        onChange={(e) => {
                          const kind = e.target.value;
                          const c =
                            kind === "classify_correctly"
                              ? { kind, entity_class: "small_multirotor", min_fraction: 1 }
                              : kind === "respond_within"
                                ? {
                                    kind,
                                    entity_class: "small_multirotor",
                                    response: "report_to_exercise_control",
                                    within_s: 90,
                                  }
                                : kind === "classify_all"
                                  ? { kind, min_fraction: 0.8 }
                                  : { kind };
                          update(["learning_objectives", i, "criterion"], c);
                        }}
                      >
                        {OBJECTIVE_KINDS.map((k) => (
                          <option key={k} value={k}>
                            {k.replace(/_/g, " ")}
                          </option>
                        ))}
                      </Select>
                    </Field>
                    {"entity_class" in o.criterion ? (
                      <Field label="Entity class">
                        <Select
                          value={o.criterion.entity_class}
                          onChange={(e) =>
                            update(["learning_objectives", i, "criterion", "entity_class"], e.target.value)
                          }
                        >
                          {ENTITY_CLASSES.map((c) => (
                            <option key={c} value={c}>
                              {label(CLASSIFICATION_LABELS, c)}
                            </option>
                          ))}
                        </Select>
                      </Field>
                    ) : null}
                    {"min_fraction" in o.criterion ? (
                      <NumberField
                        label="Minimum fraction (0–1)"
                        value={o.criterion.min_fraction}
                        onChange={(v) => update(["learning_objectives", i, "criterion", "min_fraction"], v)}
                      />
                    ) : null}
                    {o.criterion.kind === "respond_within" ? (
                      <>
                        <Field label="Response">
                          <Select
                            value={o.criterion.response}
                            onChange={(e) =>
                              update(["learning_objectives", i, "criterion", "response"], e.target.value)
                            }
                          >
                            {TRAINING_RESPONSES.map((r) => (
                              <option key={r} value={r}>
                                {label(RESPONSE_LABELS, r)}
                              </option>
                            ))}
                          </Select>
                        </Field>
                        <NumberField
                          label="Within (s)"
                          value={o.criterion.within_s}
                          onChange={(v) => update(["learning_objectives", i, "criterion", "within_s"], v)}
                        />
                      </>
                    ) : null}
                  </div>
                </div>
              ))}
            </Section>

            <Section title="3. Environment">
              <Field label="Apply preset" hint="Sets environment and suggested simulated sensor quality.">
                <Select
                  value=""
                  onChange={(e) => {
                    const p = presets.data?.environment_presets.find((x) => x.id === e.target.value);
                    if (!p) return;
                    let next = setPath(def, ["environment"], { ...p.environment });
                    for (const [sensor, vals] of Object.entries(p.sensor_overrides))
                      next = setPath(next, ["sensors", sensor], {
                        ...next.sensors[sensor],
                        ...(vals as Def),
                      });
                    setDef(next);
                    setReport(null);
                  }}
                >
                  <option value="">Choose a preset</option>
                  {presets.data?.environment_presets.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.label}
                    </option>
                  ))}
                </Select>
              </Field>
              <div className="grid gap-3 sm:grid-cols-5">
                {(
                  [
                    ["terrain", "Terrain", TERRAINS],
                    ["time_of_day", "Time of day", TIMES_OF_DAY],
                    ["weather", "Weather", WEATHER],
                  ] as const
                ).map(([k, l, opts]) => (
                  <Field key={k} label={l}>
                    <Select
                      value={def.environment[k]}
                      onChange={(e) => update(["environment", k], e.target.value)}
                    >
                      {opts.map((o) => (
                        <option key={o} value={o}>
                          {label(ENV_LABELS, o)}
                        </option>
                      ))}
                    </Select>
                  </Field>
                ))}
                <NumberField
                  label="Visibility (km)"
                  value={def.environment.visibility_km}
                  onChange={(v) => update(["environment", "visibility_km"], v)}
                />
                <NumberField
                  label="Wind (m/s)"
                  value={def.environment.wind_mps}
                  onChange={(v) => update(["environment", "wind_mps"], v)}
                />
              </div>
            </Section>

            <Section
              title="4. Simulated sensor quality"
              description="Synthetic sensor models. Lower detection, more noise and latency make the picture harder to interpret."
            >
              {SENSOR_KINDS.map((k) => {
                const s = def.sensors[k];
                const fields: [string, string][] = [
                  ["range_m", "Range (m)"],
                  ["update_interval_s", "Update interval (s)"],
                  ["detection_probability", "Detection probability (0–1)"],
                  ["latency_s", "Latency (s)"],
                  ...(k === "radar"
                    ? ([
                        ["position_noise_m", "Position noise (m)"],
                        ["clutter_tracks_per_min", "Clutter tracks per minute"],
                      ] as [string, string][])
                    : []),
                  ...(k === "electro_optical"
                    ? ([["classification_accuracy", "Classification accuracy (0–1)"]] as [string, string][])
                    : []),
                ];
                return (
                  <div key={k} className="rounded border border-border p-3">
                    <Checkbox
                      id={`sensor-${k}`}
                      checked={Boolean(s.enabled)}
                      onCheckedChange={(v) => update(["sensors", k, "enabled"], v)}
                      label={label(SENSOR_LABELS, k)}
                    />
                    {s.enabled ? (
                      <div className="mt-3 grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
                        {fields.map(([f, l]) => (
                          <NumberField
                            key={f}
                            label={l}
                            value={s[f]}
                            onChange={(v) => update(["sensors", k, f], v)}
                          />
                        ))}
                      </div>
                    ) : null}
                  </div>
                );
              })}
            </Section>

            <Section
              title="5. Virtual entities"
              description="Each group expands into one or more virtual entities. Ranges are randomisation constraints; the seed picks values within them."
              actions={
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() =>
                    update(["entities"], [...list("entities"), newGroup(list("entities").length + 1)])
                  }
                >
                  Add group
                </Button>
              }
            >
              {list("entities").map((g, i) => (
                <div key={i} className="rounded border border-border p-3">
                  <div className="grid gap-3 sm:grid-cols-[140px_1fr_170px_140px_auto]">
                    <Field label="Id">
                      <Input value={g.id} onChange={(e) => update(["entities", i, "id"], e.target.value)} />
                    </Field>
                    <Field label="Label">
                      <Input
                        value={g.label}
                        onChange={(e) => update(["entities", i, "label"], e.target.value)}
                      />
                    </Field>
                    <Field label="Class">
                      <Select
                        value={g.entity_class}
                        onChange={(e) => {
                          const v = e.target.value;
                          let next = setPath(def, ["entities", i, "entity_class"], v);
                          next = setPath(
                            next,
                            ["entities", i, "swarm"],
                            v === "coordinated_swarm"
                              ? { size: { min: 5, max: 8 }, formation: "cluster", spacing_m: 30 }
                              : null,
                          );
                          if (v === "bird_or_clutter")
                            next = setPath(next, ["entities", i, "cooperative"], false);
                          setDef(next);
                          setReport(null);
                        }}
                      >
                        {ENTITY_CLASSES.map((c) => (
                          <option key={c} value={c}>
                            {label(CLASSIFICATION_LABELS, c)}
                          </option>
                        ))}
                      </Select>
                    </Field>
                    <Field label="Behaviour">
                      <Select
                        value={g.behavior}
                        onChange={(e) => update(["entities", i, "behavior"], e.target.value)}
                      >
                        {BEHAVIORS.map((b) => (
                          <option key={b} value={b}>
                            {b}
                          </option>
                        ))}
                      </Select>
                    </Field>
                    <div className="flex items-end">
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() =>
                          update(
                            ["entities"],
                            list("entities").filter((_, j) => j !== i),
                          )
                        }
                      >
                        Remove
                      </Button>
                    </div>
                  </div>
                  <div className="mt-3 grid gap-3 sm:grid-cols-3">
                    <RangeField
                      label="Count"
                      unit="entities"
                      value={g.count}
                      onChange={(v) => update(["entities", i, "count"], v)}
                    />
                    <RangeField
                      label="Spawn time"
                      unit="s"
                      value={g.spawn_time_s}
                      onChange={(v) => update(["entities", i, "spawn_time_s"], v)}
                    />
                    <RangeField
                      label="Speed"
                      unit="m/s"
                      value={g.speed_mps}
                      onChange={(v) => update(["entities", i, "speed_mps"], v)}
                    />
                    <RangeField
                      label="Altitude"
                      unit="m"
                      value={g.altitude_m}
                      onChange={(v) => update(["entities", i, "altitude_m"], v)}
                    />
                    <RangeField
                      label="Closest approach to site"
                      unit="m"
                      value={g.closest_approach_m}
                      onChange={(v) => update(["entities", i, "closest_approach_m"], v)}
                    />
                    <div>
                      <Checkbox
                        id={`dwell-${i}`}
                        checked={Boolean(g.dwell_s)}
                        onCheckedChange={(v) =>
                          update(["entities", i, "dwell_s"], v ? { min: 60, max: 120 } : null)
                        }
                        label="Limited dwell, then depart"
                      />
                      {g.dwell_s ? (
                        <div className="mt-2">
                          <RangeField
                            label="Dwell"
                            unit="s"
                            value={g.dwell_s}
                            onChange={(v) => update(["entities", i, "dwell_s"], v)}
                          />
                        </div>
                      ) : null}
                    </div>
                  </div>
                  <div className="mt-3 flex flex-wrap items-end gap-4">
                    <Checkbox
                      id={`coop-${i}`}
                      checked={Boolean(g.cooperative)}
                      disabled={g.entity_class === "bird_or_clutter"}
                      onCheckedChange={(v) => update(["entities", i, "cooperative"], v)}
                      label="Cooperative (broadcasts simulated beacon)"
                    />
                    {g.swarm ? (
                      <div className="grid grid-cols-[1fr_140px_120px] gap-3">
                        <RangeField
                          label="Swarm size"
                          unit="members"
                          value={g.swarm.size}
                          onChange={(v) => update(["entities", i, "swarm", "size"], v)}
                        />
                        <Field label="Formation">
                          <Select
                            value={g.swarm.formation}
                            onChange={(e) => update(["entities", i, "swarm", "formation"], e.target.value)}
                          >
                            {FORMATIONS.map((f) => (
                              <option key={f} value={f}>
                                {f}
                              </option>
                            ))}
                          </Select>
                        </Field>
                        <NumberField
                          label="Spacing (m)"
                          value={g.swarm.spacing_m}
                          onChange={(v) => update(["entities", i, "swarm", "spacing_m"], v)}
                        />
                      </div>
                    ) : null}
                  </div>
                </div>
              ))}
            </Section>

            <Section
              title="6. Scripted events"
              actions={
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() =>
                    update(
                      ["event_schedule"],
                      [
                        ...list("event_schedule"),
                        {
                          type: "exercise_message",
                          id: `event-${list("event_schedule").length + 1}`,
                          at_s: 0,
                          message: "",
                        },
                      ],
                    )
                  }
                >
                  Add event
                </Button>
              }
            >
              {!list("event_schedule").length ? (
                <p className="text-sm text-ink-muted">No scripted events.</p>
              ) : null}
              {list("event_schedule").map((e, i) => (
                <div
                  key={i}
                  className="grid gap-3 rounded border border-border p-3 sm:grid-cols-[150px_120px_100px_1fr_auto]"
                >
                  <Field label="Type">
                    <Select
                      value={e.type}
                      onChange={(ev) => {
                        const t = ev.target.value;
                        const base = { type: t, id: e.id, at_s: e.at_s };
                        const v =
                          t === "sensor_degraded"
                            ? {
                                ...base,
                                sensor: "electro_optical",
                                detection_factor: 0.5,
                                noise_factor: 1.5,
                                extra_delay_s: 0,
                              }
                            : t === "sensor_restored"
                              ? { ...base, sensor: "electro_optical" }
                              : t === "visibility_change"
                                ? { ...base, visibility_km: 5 }
                                : { ...base, message: "" };
                        update(["event_schedule", i], v);
                      }}
                    >
                      {EVENT_KINDS.map((k) => (
                        <option key={k} value={k}>
                          {k.replace(/_/g, " ")}
                        </option>
                      ))}
                    </Select>
                  </Field>
                  <Field label="Id">
                    <Input
                      value={e.id}
                      onChange={(ev) => update(["event_schedule", i, "id"], ev.target.value)}
                    />
                  </Field>
                  <NumberField
                    label="At (s)"
                    value={e.at_s}
                    onChange={(v) => update(["event_schedule", i, "at_s"], v)}
                  />
                  <div className="grid gap-3 sm:grid-cols-4">
                    {"sensor" in e ? (
                      <Field label="Sensor">
                        <Select
                          value={e.sensor}
                          onChange={(ev) => update(["event_schedule", i, "sensor"], ev.target.value)}
                        >
                          {SENSOR_KINDS.map((k) => (
                            <option key={k} value={k}>
                              {label(SENSOR_LABELS, k)}
                            </option>
                          ))}
                        </Select>
                      </Field>
                    ) : null}
                    {e.type === "sensor_degraded" ? (
                      <>
                        <NumberField
                          label="Detection ×"
                          value={e.detection_factor}
                          onChange={(v) => update(["event_schedule", i, "detection_factor"], v)}
                        />
                        <NumberField
                          label="Noise ×"
                          value={e.noise_factor}
                          onChange={(v) => update(["event_schedule", i, "noise_factor"], v)}
                        />
                        <NumberField
                          label="Extra delay (s)"
                          value={e.extra_delay_s}
                          onChange={(v) => update(["event_schedule", i, "extra_delay_s"], v)}
                        />
                      </>
                    ) : null}
                    {e.type === "visibility_change" ? (
                      <NumberField
                        label="Visibility (km)"
                        value={e.visibility_km}
                        onChange={(v) => update(["event_schedule", i, "visibility_km"], v)}
                      />
                    ) : null}
                    {e.type === "exercise_message" ? (
                      <Field label="Message" className="sm:col-span-4">
                        <Input
                          value={e.message}
                          onChange={(ev) => update(["event_schedule", i, "message"], ev.target.value)}
                        />
                      </Field>
                    ) : null}
                  </div>
                  <div className="flex items-end">
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() =>
                        update(
                          ["event_schedule"],
                          list("event_schedule").filter((_, j) => j !== i),
                        )
                      }
                    >
                      Remove
                    </Button>
                  </div>
                </div>
              ))}
            </Section>

            <Section title="7. Randomisation, difficulty, time and scoring">
              <div className="grid gap-3 sm:grid-cols-4">
                <NumberField
                  label="Seed"
                  step="1"
                  value={def.randomization.seed}
                  onChange={(v) => update(["randomization", "seed"], v)}
                />
                <NumberField
                  label="Duration (s)"
                  step="1"
                  value={def.time_limits.duration_s}
                  onChange={(v) => update(["time_limits", "duration_s"], v)}
                />
                {(["level", "min_level", "max_level"] as const).map((k) => (
                  <Field
                    key={k}
                    label={
                      k === "level"
                        ? "Difficulty level"
                        : k === "min_level"
                          ? "Minimum level"
                          : "Maximum level"
                    }
                  >
                    <Select
                      value={def.difficulty[k]}
                      onChange={(e) => update(["difficulty", k], Number(e.target.value))}
                    >
                      {[1, 2, 3, 4, 5].map((l) => (
                        <option key={l} value={l}>
                          {l}
                        </option>
                      ))}
                    </Select>
                  </Field>
                ))}
                <Field label="Scoring rubric">
                  <Select
                    value={`${def.scoring.rubric_key}@${def.scoring.rubric_version}`}
                    onChange={(e) => {
                      const [key, v] = e.target.value.split("@");
                      update(["scoring"], { rubric_key: key, rubric_version: Number(v) });
                    }}
                  >
                    {rubrics.data?.items.map((r) => (
                      <option key={r.id} value={`${r.key}@${r.version}`}>
                        {r.name} v{r.version}
                      </option>
                    ))}
                  </Select>
                </Field>
              </div>
              <div className="flex flex-wrap gap-6">
                <Checkbox
                  id="seed-override"
                  checked={Boolean(def.randomization.allow_seed_override)}
                  onCheckedChange={(v) => update(["randomization", "allow_seed_override"], v)}
                  label="Allow seed override"
                />
                <Checkbox
                  id="adaptive"
                  checked={Boolean(def.difficulty.adaptive_allowed)}
                  onCheckedChange={(v) => update(["difficulty", "adaptive_allowed"], v)}
                  label="Allow adaptive difficulty"
                />
                <Checkbox
                  id="pause"
                  checked={Boolean(def.time_limits.allow_pause)}
                  onCheckedChange={(v) => update(["time_limits", "allow_pause"], v)}
                  label="Allow trainees to pause"
                />
              </div>
            </Section>
          </TabsContent>
          <TabsContent value="json">
            <Panel>
              <PanelHeader
                title="Definition (JSON)"
                description="Advanced editing. Apply to load it into the form; validation still runs before saving."
              />
              <PanelBody className="space-y-3">
                <Textarea
                  aria-label="Scenario definition JSON"
                  spellCheck={false}
                  className="min-h-[520px] text-xs leading-relaxed"
                  value={json}
                  onChange={(e) => setJson(e.target.value)}
                />
                {jsonError ? <Alert tone="danger">{jsonError}</Alert> : null}
                <Button
                  variant="secondary"
                  onClick={() => {
                    try {
                      const parsed = JSON.parse(json);
                      if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed))
                        throw new Error("The definition must be a JSON object.");
                      setDef(parsed);
                      setJsonError(null);
                      setReport(null);
                    } catch (err) {
                      setJsonError(errorMessage(err));
                    }
                  }}
                >
                  Apply JSON
                </Button>
              </PanelBody>
            </Panel>
          </TabsContent>
        </Tabs>

        <div className="space-y-4 xl:sticky xl:top-4 xl:self-start">
          <Panel>
            <PanelHeader
              title="Validation"
              description="Checks structure, cross-field rules and a seeded test run."
            />
            <PanelBody className="space-y-3">
              {clientIssues.length ? (
                <Alert tone="warning" title={`${clientIssues.length} issue(s) found in the form`}>
                  <ul className="list-disc space-y-0.5 pl-4 text-xs">
                    {clientIssues.slice(0, 8).map((i) => (
                      <li key={i.path + i.message}>
                        <span className="text-ink-muted">{i.path || "scenario"}:</span> {i.message}
                      </li>
                    ))}
                  </ul>
                </Alert>
              ) : (
                <p className="text-xs text-ink-muted">
                  No problems found in the form. Run server validation to test-generate the scenario.
                </p>
              )}
              <Button variant="secondary" className="w-full" disabled={busy !== null} onClick={validate}>
                {busy === "validate" ? "Validating" : "Validate on server"}
              </Button>
              {report ? <ReportView report={report} /> : null}
              {saveError ? (
                <Alert tone="danger" title={saveError.message}>
                  {saveError.issues?.length ? (
                    <ul className="list-disc space-y-0.5 pl-4 text-xs">
                      {saveError.issues.map((i) => (
                        <li key={i.path + i.message}>
                          {i.path}: {i.message}
                        </li>
                      ))}
                    </ul>
                  ) : null}
                </Alert>
              ) : null}
              <Button className="w-full" disabled={busy !== null || clientIssues.length > 0} onClick={save}>
                {busy === "save"
                  ? "Saving"
                  : mode === "new"
                    ? "Save scenario (version 1)"
                    : `Save as version ${(sourceVersion ?? 0) + 1}`}
              </Button>
            </PanelBody>
          </Panel>
        </div>
      </div>
    </>
  );
}

function ReportView({ report }: { report: ValidationReport }) {
  const errors = report.issues.filter((i) => i.severity === "error");
  const warnings = report.issues.filter((i) => i.severity === "warning");
  return (
    <div className="space-y-2">
      <Alert
        tone={report.valid ? "success" : "danger"}
        title={report.valid ? "Valid" : `${errors.length} error(s)`}
      >
        {errors.length ? (
          <ul className="list-disc space-y-0.5 pl-4 text-xs">
            {errors.map((i) => (
              <li key={i.path + i.message}>
                <span className="text-ink-muted">{i.path}:</span> {i.message}
              </li>
            ))}
          </ul>
        ) : null}
      </Alert>
      {warnings.length ? (
        <Alert tone="warning" title="Warnings">
          <ul className="list-disc space-y-0.5 pl-4 text-xs">
            {warnings.map((i) => (
              <li key={i.path + i.message}>{i.message}</li>
            ))}
          </ul>
        </Alert>
      ) : null}
      {report.preview ? (
        <p className="text-xs text-ink-muted">
          Test run (seed {report.preview.seed}, level {report.preview.difficulty_level}):{" "}
          {report.preview.stats.entities} entities, {report.preview.stats.tracks} tracks,{" "}
          {report.preview.stats.observations} synthetic observations.
        </p>
      ) : null}
    </div>
  );
}
