import { useState } from "react";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Field, Input, Select } from "@/components/ui/form";
import { PageHeader, Panel, PanelHeader } from "@/components/ui/panel";
import { Alert, Tag, toneForStatus } from "@/components/ui/status";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import { CompetencyPanel } from "@/features/analytics/Competency";
import { LearningGainsPanel } from "@/features/analytics/LearningGains";
import { ProgressSection } from "@/features/analytics/ProgressCharts";
import { UnitsPanel } from "@/features/analytics/Units";
import { api, download, qs } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatDateTime, formatPercent } from "@/lib/format";
import { label, STATUS_LABELS } from "@/lib/labels";
import type { Page, ProgressPoint, SessionState } from "@/lib/types";
import { errorMessage, useAsync } from "@/lib/useAsync";

interface Overview {
  trainees: number;
  active_assignments: number;
  sessions_completed: number;
  sessions_in_progress: number;
  sessions_awaiting_review: number;
  average_overall: number | null;
}

interface Filters {
  scenarios: { key: string; name: string }[];
  objectives: { id: string; description: string }[];
  trainees: { id: string; display_name: string; unit?: string | null }[];
  units?: string[];
}

function Metric({ label: l, value, hint }: { label: string; value: string | number; hint?: string }) {
  return (
    <div className="rounded-md border border-border bg-surface px-4 py-3">
      <p className="text-xs text-ink-muted">{l}</p>
      <p className="tabular mt-1 text-2xl font-semibold tracking-tight">{value}</p>
      {hint ? <p className="mt-0.5 text-2xs text-ink-subtle">{hint}</p> : null}
    </div>
  );
}

export function InstructorHome() {
  const ov = useAsync((sig) => api.get<Overview>("/analytics/overview", sig), []);
  const review = useAsync(
    (sig) => api.get<Page<SessionState>>("/sessions?needs_review=true&limit=10", sig),
    [],
  );
  return (
    <>
      <PageHeader
        title="Instructor overview"
        actions={
          <>
            <Button asChild variant="secondary">
              <Link to="/instructor/scenarios">Scenarios</Link>
            </Button>
            <Button asChild>
              <Link to="/instructor/assignments/new">New assignment</Link>
            </Button>
          </>
        }
      />
      {ov.loading ? (
        <LoadingState />
      ) : ov.error ? (
        <ErrorState error={ov.error} onRetry={ov.reload} />
      ) : (
        <div className="mb-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
          <Metric label="Active trainees" value={ov.data!.trainees} />
          <Metric label="Active assignments" value={ov.data!.active_assignments} />
          <Metric label="Sessions in progress" value={ov.data!.sessions_in_progress} />
          <Metric label="Completed sessions" value={ov.data!.sessions_completed} />
          <Metric
            label="Average score"
            value={formatPercent(ov.data!.average_overall)}
            hint={
              ov.data!.average_overall === null
                ? "No scored sessions yet"
                : "Mean overall, all scored sessions"
            }
          />
        </div>
      )}
      <Panel>
        <PanelHeader
          title="Awaiting review"
          description="Completed sessions without a review marked as reviewed."
          actions={
            <Link className="text-sm text-brand hover:underline" to="/instructor/sessions">
              All sessions
            </Link>
          }
        />
        {review.loading ? (
          <LoadingState />
        ) : review.error ? (
          <ErrorState error={review.error} onRetry={review.reload} />
        ) : !review.data?.items.length ? (
          <EmptyState title="Nothing awaiting review" />
        ) : (
          <SessionsTable sessions={review.data.items} />
        )}
      </Panel>
    </>
  );
}

export function SessionsTable({ sessions }: { sessions: SessionState[] }) {
  return (
    <Table>
      <THead>
        <TR>
          <TH>Trainee</TH>
          <TH>Scenario</TH>
          <TH>Mode</TH>
          <TH>Created</TH>
          <TH>Status</TH>
          <TH>Score</TH>
          <TH>
            <span className="sr-only">Actions</span>
          </TH>
        </TR>
      </THead>
      <TBody>
        {sessions.map((s) => (
          <TR key={s.id}>
            <TD>{s.trainee.display_name}</TD>
            <TD>
              {s.scenario.name} <span className="text-xs text-ink-subtle">v{s.scenario.version}</span>
            </TD>
            <TD className="text-xs">
              {s.mode === "self_guided" ? "Practice" : `Attempt ${s.attempt_number}`}
            </TD>
            <TD className="whitespace-nowrap text-xs">{formatDateTime(s.created_at)}</TD>
            <TD>
              <Tag tone={toneForStatus(s.status)}>{label(STATUS_LABELS, s.status)}</Tag>
            </TD>
            <TD className="tabular">{s.result ? formatPercent(s.result.overall) : "—"}</TD>
            <TD className="text-right">
              {s.status === "completed" || s.status === "aborted" ? (
                <Link className="text-sm text-brand hover:underline" to={`/sessions/${s.id}/result`}>
                  Review
                </Link>
              ) : null}
            </TD>
          </TR>
        ))}
      </TBody>
    </Table>
  );
}

const PAGE = 25;

export function SessionsPage() {
  const filters = useAsync((sig) => api.get<Filters>("/analytics/filters", sig), []);
  const [f, setF] = useState({
    trainee_id: "",
    scenario_key: "",
    status: "",
    needs_review: "",
    sort: "newest",
  });
  const [offset, setOffset] = useState(0);
  const query = qs({ ...f, limit: PAGE, offset });
  const st = useAsync((sig) => api.get<Page<SessionState>>(`/sessions${query}`, sig), [query]);
  const [exportError, setExportError] = useState<string | null>(null);
  const set = (k: keyof typeof f, v: string) => {
    setF((x) => ({ ...x, [k]: v }));
    setOffset(0);
  };
  return (
    <>
      <PageHeader
        title="Sessions and reviews"
        actions={
          <Button
            variant="secondary"
            onClick={async () => {
              setExportError(null);
              try {
                await download(
                  `/reports/sessions.csv${qs({ trainee_id: f.trainee_id, scenario_key: f.scenario_key, status: f.status })}`,
                  "drikr-sessions.csv",
                );
              } catch (err) {
                setExportError(errorMessage(err));
              }
            }}
          >
            Export CSV (current filters)
          </Button>
        }
      />
      {exportError ? (
        <Alert tone="danger" className="mb-3">
          {exportError}
        </Alert>
      ) : null}
      <Panel>
        <div className="grid gap-3 border-b border-border px-4 py-3 sm:grid-cols-2 lg:grid-cols-5">
          <Field label="Trainee">
            <Select value={f.trainee_id} onChange={(e) => set("trainee_id", e.target.value)}>
              <option value="">All trainees</option>
              {filters.data?.trainees.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.display_name}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Scenario">
            <Select value={f.scenario_key} onChange={(e) => set("scenario_key", e.target.value)}>
              <option value="">All scenarios</option>
              {filters.data?.scenarios.map((s) => (
                <option key={s.key} value={s.key}>
                  {s.name}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Status">
            <Select value={f.status} onChange={(e) => set("status", e.target.value)}>
              <option value="">Any status</option>
              {["created", "running", "paused", "completed", "aborted"].map((s) => (
                <option key={s} value={s}>
                  {label(STATUS_LABELS, s)}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Review">
            <Select value={f.needs_review} onChange={(e) => set("needs_review", e.target.value)}>
              <option value="">Any</option>
              <option value="true">Awaiting review</option>
              <option value="false">Reviewed</option>
            </Select>
          </Field>
          <Field label="Sort">
            {/* Sorted by the server before paging, so the order holds across pages. */}
            <Select value={f.sort} onChange={(e) => set("sort", e.target.value)}>
              <option value="newest">Newest first</option>
              <option value="score_asc">Lowest score first</option>
              <option value="score_desc">Highest score first</option>
            </Select>
          </Field>
        </div>
        {st.loading ? (
          <LoadingState rows={6} />
        ) : st.error ? (
          <ErrorState error={st.error} onRetry={st.reload} />
        ) : !st.data?.items.length ? (
          <EmptyState title="No sessions match these filters" />
        ) : (
          <>
            <SessionsTable sessions={st.data.items} />
            <div className="flex items-center justify-between border-t border-border px-4 py-2 text-xs text-ink-muted">
              <span>
                {offset + 1}–{Math.min(offset + PAGE, st.data.total)} of {st.data.total}
              </span>
              <div className="flex gap-2">
                <Button
                  size="sm"
                  variant="secondary"
                  disabled={offset === 0}
                  onClick={() => setOffset((o) => Math.max(0, o - PAGE))}
                >
                  Previous
                </Button>
                <Button
                  size="sm"
                  variant="secondary"
                  disabled={offset + PAGE >= st.data.total}
                  onClick={() => setOffset((o) => o + PAGE)}
                >
                  Next
                </Button>
              </div>
            </div>
          </>
        )}
      </Panel>
    </>
  );
}

export function AnalyticsPage() {
  const { can } = useAuth();
  const filters = useAsync((sig) => api.get<Filters>("/analytics/filters", sig), []);
  const [f, setF] = useState({
    trainee_id: "",
    unit: "",
    scenario_key: "",
    objective_id: "",
    date_from: "",
    date_to: "",
  });
  const dates = {
    date_from: f.date_from ? new Date(f.date_from).toISOString() : "",
    date_to: f.date_to ? new Date(`${f.date_to}T23:59:59`).toISOString() : "",
  };
  const query = qs({
    trainee_id: f.trainee_id,
    unit: f.unit,
    scenario_key: f.scenario_key,
    objective_id: f.objective_id,
    ...dates,
  });
  const st = useAsync(
    (sig) => api.get<{ points: ProgressPoint[] }>(`/analytics/progress${query}`, sig),
    [query],
  );
  const set = (k: keyof typeof f, v: string) => setF((x) => ({ ...x, [k]: v }));
  const points = st.data?.points ?? [];
  return (
    <>
      <PageHeader
        title="Analytics"
        description="Progress across repeated sessions, computed only from persisted, scored results."
      />
      <Panel className="mb-4">
        <div className="grid gap-3 px-4 py-3 sm:grid-cols-2 lg:grid-cols-6">
          <Field label="Unit">
            <Select value={f.unit} onChange={(e) => set("unit", e.target.value)}>
              <option value="">All units</option>
              {(filters.data?.units ?? []).map((u) => (
                <option key={u} value={u}>
                  {u}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Trainee">
            <Select value={f.trainee_id} onChange={(e) => set("trainee_id", e.target.value)}>
              <option value="">All trainees</option>
              {filters.data?.trainees.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.display_name}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Scenario">
            <Select value={f.scenario_key} onChange={(e) => set("scenario_key", e.target.value)}>
              <option value="">All scenarios</option>
              {filters.data?.scenarios.map((s) => (
                <option key={s.key} value={s.key}>
                  {s.name}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Training objective">
            <Select value={f.objective_id} onChange={(e) => set("objective_id", e.target.value)}>
              <option value="">Any objective</option>
              {filters.data?.objectives.map((o) => (
                <option key={o.id} value={o.id}>
                  {o.description}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="From">
            <Input type="date" value={f.date_from} onChange={(e) => set("date_from", e.target.value)} />
          </Field>
          <Field label="To">
            <Input type="date" value={f.date_to} onChange={(e) => set("date_to", e.target.value)} />
          </Field>
        </div>
      </Panel>
      {st.loading ? (
        <LoadingState rows={6} />
      ) : st.error ? (
        <ErrorState error={st.error} onRetry={st.reload} />
      ) : (
        <div className="space-y-4">
          <ProgressSection points={points} showTrainee />
          {f.trainee_id ? (
            <CompetencyPanel traineeId={f.trainee_id} scenarioKey={f.scenario_key || undefined} />
          ) : (
            <UnitsPanel query={qs({ scenario_key: f.scenario_key, ...dates })} />
          )}
          <LearningGainsPanel
            traineeId={f.trainee_id}
            unit={f.unit}
            scenarioKey={f.scenario_key}
            canExport={can("reports:export")}
          />
          {points.length ? (
            <Panel>
              <PanelHeader
                title="Session comparison"
                description="All sessions in the current selection, newest first."
              />
              <Table>
                <THead>
                  <TR>
                    <TH>Completed</TH>
                    <TH>Trainee</TH>
                    <TH>Scenario</TH>
                    <TH>Difficulty</TH>
                    <TH>Overall</TH>
                    <TH>Recognition</TH>
                    <TH>Timing</TH>
                    <TH>Consistency</TH>
                    {f.objective_id ? <TH>Objective</TH> : null}
                    <TH>
                      <span className="sr-only">Actions</span>
                    </TH>
                  </TR>
                </THead>
                <TBody>
                  {[...points].reverse().map((p) => (
                    <TR key={p.session_id}>
                      <TD className="whitespace-nowrap text-xs">{formatDateTime(p.completed_at)}</TD>
                      <TD>{p.trainee.display_name}</TD>
                      <TD className="text-xs">
                        {p.scenario_name} v{p.scenario_version}
                      </TD>
                      <TD>{p.difficulty_level}</TD>
                      <TD className="tabular">{formatPercent(p.overall)}</TD>
                      <TD className="tabular text-xs">{formatPercent(p.dimensions.recognition)}</TD>
                      <TD className="tabular text-xs">{formatPercent(p.dimensions.timing)}</TD>
                      <TD className="tabular text-xs">{formatPercent(p.dimensions.consistency)}</TD>
                      {f.objective_id ? (
                        <TD>
                          <Tag tone={toneForStatus(p.objective_status)}>
                            {label(STATUS_LABELS, p.objective_status)}
                          </Tag>
                        </TD>
                      ) : null}
                      <TD className="text-right">
                        <Link
                          className="text-sm text-brand hover:underline"
                          to={`/sessions/${p.session_id}/result`}
                        >
                          Review
                        </Link>
                      </TD>
                    </TR>
                  ))}
                </TBody>
              </Table>
            </Panel>
          ) : null}
        </div>
      )}
    </>
  );
}
