import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Field, Input, Select } from "@/components/ui/form";
import { Checkbox, Dialog } from "@/components/ui/overlay";
import { KeyValues, PageHeader, Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { Alert, Tag } from "@/components/ui/status";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import { api, qs } from "@/lib/api";
import { formatClock, formatDateTime, formatDistance } from "@/lib/format";
import { CLASSIFICATION_LABELS, ENV_LABELS, label, SENSOR_LABELS } from "@/lib/labels";
import type { ScenarioDetail, ScenarioSummary } from "@/lib/types";
import { errorMessage, useAsync } from "@/lib/useAsync";

export function ScenarioListPage() {
  const [archived, setArchived] = useState(false);
  const st = useAsync(
    (sig) => api.get<{ items: ScenarioSummary[] }>(`/scenarios${qs({ include_archived: archived })}`, sig),
    [archived],
  );
  const [genOpen, setGenOpen] = useState(false);
  return (
    <>
      <PageHeader
        title="Scenarios"
        description="Versioned scenario definitions. Saving changes always creates a new version; earlier versions and their sessions are never altered."
        actions={
          <>
            <Button variant="secondary" onClick={() => setGenOpen(true)}>
              Generate scenario
            </Button>
            <Button asChild>
              <Link to="/instructor/scenarios/new">New scenario</Link>
            </Button>
          </>
        }
      />
      <Panel>
        <div className="border-b border-border px-4 py-2.5">
          <Checkbox
            id="show-archived"
            checked={archived}
            onCheckedChange={setArchived}
            label="Include archived scenarios"
          />
        </div>
        {st.loading ? (
          <LoadingState rows={5} />
        ) : st.error ? (
          <ErrorState error={st.error} onRetry={st.reload} />
        ) : !st.data?.items.length ? (
          <EmptyState title="No scenarios" />
        ) : (
          <Table>
            <THead>
              <TR>
                <TH>Scenario</TH>
                <TH>Version</TH>
                <TH>Environment</TH>
                <TH>Duration</TH>
                <TH>Objectives</TH>
                <TH>Use</TH>
                <TH>
                  <span className="sr-only">Actions</span>
                </TH>
              </TR>
            </THead>
            <TBody>
              {st.data.items.map((s) => (
                <TR key={s.id}>
                  <TD>
                    <p className="font-medium">{s.name}</p>
                    <p className="text-xs text-ink-subtle">{s.key}</p>
                  </TD>
                  <TD className="tabular">
                    v{s.version}
                    {s.version_count && s.version_count > 1 ? (
                      <span className="text-xs text-ink-subtle"> ({s.version_count} versions)</span>
                    ) : null}
                  </TD>
                  <TD className="whitespace-nowrap text-xs">
                    {label(ENV_LABELS, s.environment.terrain)}, {label(ENV_LABELS, s.environment.time_of_day)}
                    , {label(ENV_LABELS, s.environment.weather)}
                  </TD>
                  <TD className="tabular">{formatClock(s.duration_s * 1000)}</TD>
                  <TD className="tabular">{s.objective_count}</TD>
                  <TD className="space-x-1">
                    {s.is_demo ? <Tag tone="info">Demonstration</Tag> : null}
                    {s.self_guided ? <Tag tone="brand">Practice</Tag> : null}
                    {s.status === "archived" ? <Tag tone="danger">Archived</Tag> : null}
                  </TD>
                  <TD className="text-right">
                    <Link className="text-sm text-brand hover:underline" to={`/instructor/scenarios/${s.id}`}>
                      Open
                    </Link>
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
        )}
      </Panel>
      <GenerateDialog open={genOpen} onOpenChange={setGenOpen} />
    </>
  );
}

function GenerateDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) {
  const navigate = useNavigate();
  const presets = useAsync(
    (sig) => api.get<{ environment_presets: { id: string; label: string }[] }>("/scenarios/presets", sig),
    [],
  );
  const [seed, setSeed] = useState(String(Math.floor(Math.random() * 1_000_000)));
  const [preset, setPreset] = useState("");
  const [swarm, setSwarm] = useState("");
  const [duration, setDuration] = useState(300);
  const [level, setLevel] = useState(3);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title="Generate a scenario"
      description="Builds a valid draft from a seed and constraints. The same inputs always produce the same draft. Review it before saving."
      footer={
        <>
          <Button variant="secondary" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            disabled={busy}
            onClick={async () => {
              setError(null);
              const n = Number(seed);
              if (!Number.isInteger(n) || n < 0) {
                setError("Seed must be a whole number of 0 or more.");
                return;
              }
              setBusy(true);
              try {
                const res = await api.post<{ definition: Record<string, unknown> }>("/scenarios/generate", {
                  seed: n,
                  preset: preset || null,
                  include_swarm: swarm === "" ? null : swarm === "yes",
                  duration_s: duration,
                  difficulty_level: level,
                });
                onOpenChange(false);
                navigate("/instructor/scenarios/new", { state: { definition: res.definition } });
              } catch (err) {
                setError(errorMessage(err));
              } finally {
                setBusy(false);
              }
            }}
          >
            {busy ? "Generating" : "Generate draft"}
          </Button>
        </>
      }
    >
      <div className="grid grid-cols-2 gap-3">
        <Field label="Seed">
          <Input inputMode="numeric" value={seed} onChange={(e) => setSeed(e.target.value)} />
        </Field>
        <Field label="Environment preset">
          <Select value={preset} onChange={(e) => setPreset(e.target.value)}>
            <option value="">Any (from seed)</option>
            {presets.data?.environment_presets.map((p) => (
              <option key={p.id} value={p.id}>
                {p.label}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Coordinated swarm">
          <Select value={swarm} onChange={(e) => setSwarm(e.target.value)}>
            <option value="">From seed</option>
            <option value="yes">Include</option>
            <option value="no">Exclude</option>
          </Select>
        </Field>
        <Field label="Duration (s)">
          <Input
            type="number"
            min={120}
            max={1800}
            value={duration}
            onChange={(e) => setDuration(Number(e.target.value))}
          />
        </Field>
        <Field label="Difficulty level">
          <Select value={level} onChange={(e) => setLevel(Number(e.target.value))}>
            {[1, 2, 3, 4, 5].map((l) => (
              <option key={l} value={l}>
                {l}
              </option>
            ))}
          </Select>
        </Field>
      </div>
      {error ? (
        <Alert tone="danger" className="mt-3">
          {error}
        </Alert>
      ) : null}
    </Dialog>
  );
}

interface PreviewResponse {
  summary: {
    seed: number;
    difficulty_level: number;
    digest: string;
    stats: { entities: number; tracks: number; observations: number; events: number };
  };
  entities: {
    entity_id: string;
    entity_class: string;
    behavior: string;
    cooperative: boolean;
    spawn_s: number;
    exit_s: number | null;
    closest_range_m: number | null;
    track_id: string | null;
  }[];
}

export function ScenarioDetailPage() {
  const { scenarioId = "" } = useParams();
  const navigate = useNavigate();
  const st = useAsync((sig) => api.get<ScenarioDetail>(`/scenarios/${scenarioId}`, sig), [scenarioId]);
  const [seed, setSeed] = useState("");
  const [level, setLevel] = useState("");
  const [preview, setPreview] = useState<PreviewResponse | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  if (st.loading) return <LoadingState rows={8} />;
  if (st.error || !st.data) return <ErrorState error={st.error} onRetry={st.reload} />;
  const s = st.data;
  const d = s.definition as Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any

  async function toggleArchive() {
    setMsg(null);
    try {
      await api.post(`/scenarios/${s.id}/${s.status === "archived" ? "restore" : "archive"}`);
      st.reload();
    } catch (err) {
      setMsg(errorMessage(err));
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
        title={s.name}
        description={`${s.key} · version ${s.version} · created ${formatDateTime(s.created_at)}`}
        actions={
          <>
            <Button variant="secondary" onClick={toggleArchive}>
              {s.status === "archived" ? "Restore" : "Archive"}
            </Button>
            <Button variant="secondary" onClick={() => navigate(`/instructor/scenarios/${s.id}/edit`)}>
              Edit as new version
            </Button>
            <Button
              onClick={() => navigate(`/instructor/assignments/new?scenario=${s.id}`)}
              disabled={s.status === "archived"}
            >
              Assign
            </Button>
          </>
        }
      />
      {msg ? (
        <Alert tone="danger" className="mb-3">
          {msg}
        </Alert>
      ) : null}
      {s.is_demo ? (
        <Alert tone="info" className="mb-4">
          Demonstration scenario shipped with the product. It is separate from instructor-authored content.
        </Alert>
      ) : null}
      <div className="grid gap-4 lg:grid-cols-2">
        <Panel>
          <PanelHeader title="Summary" />
          <PanelBody className="space-y-3">
            <p className="text-sm">{s.description}</p>
            <KeyValues
              items={[
                [
                  "Environment",
                  `${label(ENV_LABELS, d.environment.terrain)}, ${label(ENV_LABELS, d.environment.time_of_day)}, ${label(ENV_LABELS, d.environment.weather)}, ${d.environment.visibility_km} km visibility`,
                ],
                ["Duration", formatClock(d.time_limits.duration_s * 1000)],
                [
                  "Difficulty",
                  `Level ${d.difficulty.level} (bounds ${d.difficulty.min_level}–${d.difficulty.max_level}${d.difficulty.adaptive_allowed ? ", adaptive allowed" : ""})`,
                ],
                [
                  "Seed",
                  `${d.randomization.seed}${d.randomization.allow_seed_override ? " (override allowed)" : ""}`,
                ],
                ["Rubric", `${d.scoring.rubric_key} v${d.scoring.rubric_version}`],
                [
                  "Digest",
                  <span key="d" className="break-all text-xs">
                    {s.digest}
                  </span>,
                ],
              ]}
            />
          </PanelBody>
        </Panel>
        <Panel>
          <PanelHeader title="Learning objectives" />
          <ol className="list-decimal space-y-1 py-3 pl-9 pr-4 text-sm">
            {d.learning_objectives.map(
              (o: { id: string; description: string; criterion: { kind: string } }) => (
                <li key={o.id}>
                  {o.description}{" "}
                  <span className="text-xs text-ink-subtle">({o.criterion.kind.replace(/_/g, " ")})</span>
                </li>
              ),
            )}
          </ol>
        </Panel>
        <Panel className="lg:col-span-2">
          <PanelHeader title="Virtual entity groups" />
          <Table>
            <THead>
              <TR>
                <TH>Group</TH>
                <TH>Class</TH>
                <TH>Behaviour</TH>
                <TH>Count</TH>
                <TH>Spawn window</TH>
                <TH>Closest approach</TH>
                <TH>Cooperative</TH>
              </TR>
            </THead>
            <TBody>
              {d.entities.map(
                (
                  g: Record<string, any>, // eslint-disable-line @typescript-eslint/no-explicit-any
                ) => (
                  <TR key={g.id}>
                    <TD>{g.label}</TD>
                    <TD>
                      {label(CLASSIFICATION_LABELS, g.entity_class)}
                      {g.swarm ? ` (${g.swarm.size.min}–${g.swarm.size.max} members)` : ""}
                    </TD>
                    <TD>{g.behavior}</TD>
                    <TD className="tabular">
                      {g.count.min === g.count.max ? g.count.min : `${g.count.min}–${g.count.max}`}
                    </TD>
                    <TD className="tabular">
                      {g.spawn_time_s.min}–{g.spawn_time_s.max} s
                    </TD>
                    <TD className="tabular">
                      {formatDistance(g.closest_approach_m.min)}–{formatDistance(g.closest_approach_m.max)}
                    </TD>
                    <TD>{g.cooperative ? "Yes" : "No"}</TD>
                  </TR>
                ),
              )}
            </TBody>
          </Table>
        </Panel>
        <Panel>
          <PanelHeader title="Simulated sensors" />
          <Table>
            <THead>
              <TR>
                <TH>Sensor</TH>
                <TH>Range</TH>
                <TH>Update</TH>
                <TH>Detection</TH>
                <TH>Latency</TH>
              </TR>
            </THead>
            <TBody>
              {Object.entries(d.sensors as Record<string, Record<string, number | boolean>>).map(([k, v]) => (
                <TR key={k} className={v.enabled ? "" : "text-ink-subtle"}>
                  <TD>
                    {label(SENSOR_LABELS, k)}
                    {v.enabled ? "" : " (off)"}
                  </TD>
                  <TD className="tabular">{formatDistance(v.range_m as number)}</TD>
                  <TD className="tabular">{String(v.update_interval_s)} s</TD>
                  <TD className="tabular">{Math.round((v.detection_probability as number) * 100)}%</TD>
                  <TD className="tabular">{String(v.latency_s)} s</TD>
                </TR>
              ))}
            </TBody>
          </Table>
        </Panel>
        <Panel>
          <PanelHeader title="Scripted events" />
          {d.event_schedule.length ? (
            <ul className="divide-y divide-border">
              {d.event_schedule.map(
                (
                  e: Record<string, any>, // eslint-disable-line @typescript-eslint/no-explicit-any
                ) => (
                  <li key={e.id} className="grid grid-cols-[56px_1fr] gap-2 px-4 py-2 text-sm">
                    <span className="tabular text-ink-subtle">{formatClock(e.at_s * 1000)}</span>
                    <span>
                      {e.type.replace(/_/g, " ")}
                      {e.sensor ? `: ${label(SENSOR_LABELS, e.sensor)}` : ""}
                      {e.message ? `: ${e.message}` : ""}
                      {e.visibility_km ? `: ${e.visibility_km} km` : ""}
                    </span>
                  </li>
                ),
              )}
            </ul>
          ) : (
            <EmptyState title="No scripted events" />
          )}
        </Panel>
        <Panel className="lg:col-span-2">
          <PanelHeader
            title="Planning preview"
            description="Expands the scenario with a seed and difficulty to show the resulting virtual entities. Contains ground truth; never shown to trainees."
            actions={
              <div className="flex items-end gap-2">
                <Field label="Seed" className="w-32">
                  <Input
                    inputMode="numeric"
                    placeholder={String(d.randomization.seed)}
                    value={seed}
                    onChange={(e) => setSeed(e.target.value)}
                  />
                </Field>
                <Field label="Level" className="w-24">
                  <Select value={level} onChange={(e) => setLevel(e.target.value)}>
                    <option value="">{d.difficulty.level}</option>
                    {[1, 2, 3, 4, 5].map((l) => (
                      <option key={l} value={l}>
                        {l}
                      </option>
                    ))}
                  </Select>
                </Field>
                <Button
                  variant="secondary"
                  onClick={async () => {
                    setMsg(null);
                    try {
                      setPreview(
                        await api.get<PreviewResponse>(
                          `/scenarios/${s.id}/preview${qs({ seed, difficulty_level: level })}`,
                        ),
                      );
                    } catch (err) {
                      setMsg(errorMessage(err));
                    }
                  }}
                >
                  Run preview
                </Button>
              </div>
            }
          />
          {preview ? (
            <>
              <p className="px-4 py-2 text-xs text-ink-muted">
                Seed {preview.summary.seed}, level {preview.summary.difficulty_level}:{" "}
                {preview.summary.stats.entities} entities, {preview.summary.stats.tracks} tracks,{" "}
                {preview.summary.stats.observations} observations, {preview.summary.stats.events} events.
                Timeline digest {preview.summary.digest.slice(0, 16)}…
              </p>
              <Table>
                <THead>
                  <TR>
                    <TH>Entity</TH>
                    <TH>Class</TH>
                    <TH>Behaviour</TH>
                    <TH>Appears</TH>
                    <TH>Leaves</TH>
                    <TH>Closest</TH>
                    <TH>Track</TH>
                  </TR>
                </THead>
                <TBody>
                  {preview.entities.map((e) => (
                    <TR key={e.entity_id}>
                      <TD className="text-xs">{e.entity_id}</TD>
                      <TD className="text-xs">
                        {label(CLASSIFICATION_LABELS, e.entity_class)}
                        {e.cooperative ? " (cooperative)" : ""}
                      </TD>
                      <TD className="text-xs">{e.behavior}</TD>
                      <TD className="tabular text-xs">{e.spawn_s.toFixed(1)} s</TD>
                      <TD className="tabular text-xs">
                        {e.exit_s === null ? "—" : `${e.exit_s.toFixed(1)} s`}
                      </TD>
                      <TD className="tabular text-xs">{formatDistance(e.closest_range_m)}</TD>
                      <TD className="text-xs">{e.track_id ?? "Never detected"}</TD>
                    </TR>
                  ))}
                </TBody>
              </Table>
            </>
          ) : (
            <p className="px-4 py-3 text-sm text-ink-muted">Run a preview to see how this version expands.</p>
          )}
        </Panel>
        <Panel className="lg:col-span-2">
          <PanelHeader title="Version history" />
          <Table>
            <THead>
              <TR>
                <TH>Version</TH>
                <TH>Status</TH>
                <TH>Created</TH>
                <TH>
                  <span className="sr-only">Actions</span>
                </TH>
              </TR>
            </THead>
            <TBody>
              {s.versions.map((v) => (
                <TR key={v.id}>
                  <TD>v{v.version}</TD>
                  <TD>{v.status}</TD>
                  <TD className="text-xs">{formatDateTime(v.created_at)}</TD>
                  <TD className="text-right">
                    {v.id !== s.id ? (
                      <Link
                        className="text-sm text-brand hover:underline"
                        to={`/instructor/scenarios/${v.id}`}
                      >
                        Open
                      </Link>
                    ) : (
                      <span className="text-xs text-ink-subtle">Viewing</span>
                    )}
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
        </Panel>
      </div>
    </>
  );
}
