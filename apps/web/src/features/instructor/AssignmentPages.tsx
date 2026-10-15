import { useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Field, Input, Select, Textarea } from "@/components/ui/form";
import { Checkbox } from "@/components/ui/overlay";
import { PageHeader, Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { Alert, Tag, toneForStatus } from "@/components/ui/status";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import { TIMES_OF_DAY, WEATHER } from "@/contracts/scenario";
import { api, qs } from "@/lib/api";
import { formatDate, formatPercent } from "@/lib/format";
import { ENV_LABELS, label, STATUS_LABELS } from "@/lib/labels";
import type { Assignment, Page, ScenarioSummary, UserOut } from "@/lib/types";
import { errorMessage, useAsync } from "@/lib/useAsync";

export function AssignmentsPage() {
  const [status, setStatus] = useState("active");
  const st = useAsync(
    (sig) => api.get<Page<Assignment>>(`/assignments${qs({ status, limit: 200 })}`, sig),
    [status],
  );
  const [msg, setMsg] = useState<string | null>(null);
  return (
    <>
      <PageHeader
        title="Assignments"
        actions={
          <Button asChild>
            <Link to="/instructor/assignments/new">New assignment</Link>
          </Button>
        }
      />
      {msg ? (
        <Alert tone="danger" className="mb-3">
          {msg}
        </Alert>
      ) : null}
      <Panel>
        <div className="flex items-end gap-3 border-b border-border px-4 py-3">
          <Field label="Status" className="w-48">
            <Select value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="active">Active</option>
              <option value="cancelled">Cancelled</option>
              <option value="">All</option>
            </Select>
          </Field>
        </div>
        {st.loading ? (
          <LoadingState rows={5} />
        ) : st.error ? (
          <ErrorState error={st.error} onRetry={st.reload} />
        ) : !st.data?.items.length ? (
          <EmptyState
            title="No assignments"
            action={
              <Button asChild size="sm">
                <Link to="/instructor/assignments/new">Create an assignment</Link>
              </Button>
            }
          />
        ) : (
          <Table>
            <THead>
              <TR>
                <TH>Title</TH>
                <TH>Trainee</TH>
                <TH>Scenario</TH>
                <TH>Difficulty</TH>
                <TH>Progress</TH>
                <TH>Attempts</TH>
                <TH>Best</TH>
                <TH>Due</TH>
                <TH>
                  <span className="sr-only">Actions</span>
                </TH>
              </TR>
            </THead>
            <TBody>
              {st.data.items.map((a) => (
                <TR key={a.id}>
                  <TD className="font-medium">{a.title}</TD>
                  <TD>{a.trainee.display_name}</TD>
                  <TD className="text-xs">
                    {a.scenario.name} v{a.scenario.version}
                  </TD>
                  <TD className="text-xs">
                    {a.difficulty_mode === "adaptive"
                      ? `Adaptive ${a.min_level}–${a.max_level}, next ${a.progress?.next_difficulty_level}`
                      : `Fixed ${a.difficulty_level}`}
                  </TD>
                  <TD>
                    <Tag tone={toneForStatus(a.progress?.state)}>
                      {label(STATUS_LABELS, a.progress?.state)}
                    </Tag>
                  </TD>
                  <TD className="tabular">
                    {a.progress?.attempts_used} of {a.max_attempts}
                  </TD>
                  <TD className="tabular">{formatPercent(a.progress?.best_overall)}</TD>
                  <TD className="text-xs">{formatDate(a.due_at)}</TD>
                  <TD className="whitespace-nowrap text-right">
                    {a.progress?.sessions.length ? (
                      <Link
                        className="mr-3 text-sm text-brand hover:underline"
                        to={`/sessions/${a.progress.sessions[a.progress.sessions.length - 1]!.id}/result`}
                      >
                        Latest attempt
                      </Link>
                    ) : null}
                    {a.status === "active" ? (
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={async () => {
                          setMsg(null);
                          try {
                            await api.post(`/assignments/${a.id}/cancel`);
                            st.reload();
                          } catch (err) {
                            setMsg(errorMessage(err));
                          }
                        }}
                      >
                        Cancel
                      </Button>
                    ) : null}
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
        )}
      </Panel>
    </>
  );
}

const AssignmentSchema = z
  .object({
    scenario_id: z.string().uuid("Choose a scenario"),
    trainee_ids: z.array(z.string().uuid()).min(1, "Choose at least one trainee"),
    title: z.string().trim().min(3, "Use at least 3 characters").max(160),
    instructions: z.string().max(4000),
    difficulty_mode: z.enum(["fixed", "adaptive"]),
    difficulty_level: z.number().int().min(1).max(5),
    min_level: z.number().int().min(1).max(5),
    max_level: z.number().int().min(1).max(5),
    max_attempts: z.number().int().min(1, "At least 1").max(50, "At most 50"),
    feedback_level: z.enum(["summary", "detailed"]),
    due_at: z.string().nullable(),
    trainee_options: z.object({
      time_of_day: z.array(z.string()),
      weather: z.array(z.string()),
      allow_custom_seed: z.boolean(),
    }),
  })
  .refine((d) => d.min_level <= d.difficulty_level && d.difficulty_level <= d.max_level, {
    path: ["difficulty_level"],
    message: "Starting level must lie within the minimum and maximum",
  });

export function AssignmentCreatePage() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const scenarios = useAsync((sig) => api.get<{ items: ScenarioSummary[] }>("/scenarios", sig), []);
  const trainees = useAsync((sig) => api.get<Page<UserOut>>("/users?role=trainee&limit=200", sig), []);
  const [form, setForm] = useState({
    scenario_id: params.get("scenario") ?? "",
    trainee_ids: [] as string[],
    title: "",
    instructions: "",
    difficulty_mode: "fixed" as "fixed" | "adaptive",
    difficulty_level: 3,
    min_level: 1,
    max_level: 5,
    max_attempts: 3,
    feedback_level: "detailed" as "summary" | "detailed",
    due: "",
    tod: [] as string[],
    weather: [] as string[],
    seed: false,
  });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [serverError, setServerError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const scenario = useMemo(
    () => scenarios.data?.items.find((s) => s.id === form.scenario_id),
    [scenarios.data, form.scenario_id],
  );
  const set = <K extends keyof typeof form>(k: K, v: (typeof form)[K]) => setForm((f) => ({ ...f, [k]: v }));

  function pickScenario(id: string) {
    const s = scenarios.data?.items.find((x) => x.id === id);
    setForm((f) => ({
      ...f,
      scenario_id: id,
      title: f.title || (s ? s.name : ""),
      difficulty_level: s?.difficulty.level ?? 3,
      min_level: s?.difficulty.min_level ?? 1,
      max_level: s?.difficulty.max_level ?? 5,
      difficulty_mode: s?.difficulty.adaptive_allowed ? f.difficulty_mode : "fixed",
    }));
  }

  async function submit() {
    setServerError(null);
    const body = {
      scenario_id: form.scenario_id,
      trainee_ids: form.trainee_ids,
      title: form.title,
      instructions: form.instructions,
      difficulty_mode: form.difficulty_mode,
      difficulty_level: form.difficulty_level,
      min_level: form.min_level,
      max_level: form.max_level,
      max_attempts: form.max_attempts,
      feedback_level: form.feedback_level,
      due_at: form.due ? new Date(`${form.due}T23:59:00`).toISOString() : null,
      trainee_options: { time_of_day: form.tod, weather: form.weather, allow_custom_seed: form.seed },
    };
    const parsed = AssignmentSchema.safeParse(body);
    if (!parsed.success) {
      const fe: Record<string, string> = {};
      for (const i of parsed.error.issues) fe[String(i.path[0])] ??= i.message;
      setErrors(fe);
      return;
    }
    setErrors({});
    setBusy(true);
    try {
      await api.post("/assignments", parsed.data);
      navigate("/instructor/assignments");
    } catch (err) {
      setServerError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  if (scenarios.loading || trainees.loading) return <LoadingState rows={6} />;
  if (scenarios.error) return <ErrorState error={scenarios.error} onRetry={scenarios.reload} />;
  if (trainees.error) return <ErrorState error={trainees.error} onRetry={trainees.reload} />;
  const bounds = scenario?.difficulty;
  const levels = [1, 2, 3, 4, 5].filter((l) => !bounds || (l >= bounds.min_level && l <= bounds.max_level));

  return (
    <>
      <PageHeader
        eyebrow={
          <Link to="/instructor/assignments" className="hover:underline">
            Assignments
          </Link>
        }
        title="New assignment"
      />
      <div className="grid gap-4 lg:grid-cols-2">
        <Panel>
          <PanelHeader title="1. Exercise" />
          <PanelBody className="space-y-3">
            <Field label="Scenario" error={errors.scenario_id}>
              <Select value={form.scenario_id} onChange={(e) => pickScenario(e.target.value)}>
                <option value="">Choose a scenario</option>
                {scenarios.data?.items.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name} (v{s.version})
                  </option>
                ))}
              </Select>
            </Field>
            {scenario ? <p className="text-xs text-ink-muted">{scenario.description}</p> : null}
            <Field label="Title" error={errors.title}>
              <Input value={form.title} onChange={(e) => set("title", e.target.value)} />
            </Field>
            <Field label="Instructions for the trainee" hint="Shown above the briefing.">
              <Textarea value={form.instructions} onChange={(e) => set("instructions", e.target.value)} />
            </Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Maximum attempts" error={errors.max_attempts}>
                <Input
                  type="number"
                  min={1}
                  max={50}
                  value={form.max_attempts}
                  onChange={(e) => set("max_attempts", Number(e.target.value))}
                />
              </Field>
              <Field label="Due date (optional)">
                <Input type="date" value={form.due} onChange={(e) => set("due", e.target.value)} />
              </Field>
            </div>
            <Field
              label="Feedback shown to the trainee"
              hint="Summary hides track-level ground truth and PDF export from the trainee."
            >
              <Select
                value={form.feedback_level}
                onChange={(e) => set("feedback_level", e.target.value as "summary" | "detailed")}
              >
                <option value="detailed">Detailed</option>
                <option value="summary">Summary only</option>
              </Select>
            </Field>
          </PanelBody>
        </Panel>
        <Panel>
          <PanelHeader title="2. Trainees" description="One assignment is created per trainee." />
          <PanelBody>
            {!trainees.data?.items.length ? (
              <p className="text-sm text-ink-muted">
                No active trainees. An administrator can add trainee accounts.
              </p>
            ) : (
              <div className="max-h-72 space-y-1.5 overflow-y-auto">
                {trainees.data.items.map((t) => (
                  <Checkbox
                    key={t.id}
                    id={`t-${t.id}`}
                    checked={form.trainee_ids.includes(t.id)}
                    onCheckedChange={(v) =>
                      set(
                        "trainee_ids",
                        v ? [...form.trainee_ids, t.id] : form.trainee_ids.filter((x) => x !== t.id),
                      )
                    }
                    label={`${t.display_name} (${t.username})`}
                  />
                ))}
              </div>
            )}
            {errors.trainee_ids ? <p className="mt-2 text-xs text-danger">{errors.trainee_ids}</p> : null}
          </PanelBody>
        </Panel>
        <Panel>
          <PanelHeader
            title="3. Difficulty"
            description={
              bounds ? `This scenario allows levels ${bounds.min_level}–${bounds.max_level}.` : undefined
            }
          />
          <PanelBody className="space-y-3">
            <Field
              label="Mode"
              hint={
                form.difficulty_mode === "adaptive"
                  ? "Level changes between attempts by documented rules, within the bounds below."
                  : undefined
              }
            >
              <Select
                value={form.difficulty_mode}
                onChange={(e) => set("difficulty_mode", e.target.value as "fixed" | "adaptive")}
                disabled={!scenario?.difficulty.adaptive_allowed}
              >
                <option value="fixed">Fixed</option>
                <option value="adaptive">Adaptive</option>
              </Select>
            </Field>
            <div className="grid grid-cols-3 gap-3">
              {(
                [
                  ["difficulty_level", "Starting level"],
                  ["min_level", "Minimum"],
                  ["max_level", "Maximum"],
                ] as const
              ).map(([k, l]) => (
                <Field key={k} label={l} error={errors[k]}>
                  <Select
                    value={form[k]}
                    onChange={(e) => set(k, Number(e.target.value))}
                    disabled={k !== "difficulty_level" && form.difficulty_mode === "fixed"}
                  >
                    {levels.map((v) => (
                      <option key={v} value={v}>
                        {v}
                      </option>
                    ))}
                  </Select>
                </Field>
              ))}
            </div>
          </PanelBody>
        </Panel>
        <Panel>
          <PanelHeader
            title="4. Options the trainee may choose"
            description="Leave everything unticked to fix the exercise exactly as authored."
          />
          <PanelBody className="space-y-3">
            <fieldset>
              <legend className="mb-1 text-xs font-medium">Time of day</legend>
              <div className="flex flex-wrap gap-4">
                {TIMES_OF_DAY.map((v) => (
                  <Checkbox
                    key={v}
                    id={`tod-${v}`}
                    checked={form.tod.includes(v)}
                    onCheckedChange={(c) =>
                      set("tod", c ? [...form.tod, v] : form.tod.filter((x) => x !== v))
                    }
                    label={label(ENV_LABELS, v)}
                  />
                ))}
              </div>
            </fieldset>
            <fieldset>
              <legend className="mb-1 text-xs font-medium">Weather</legend>
              <div className="flex flex-wrap gap-4">
                {WEATHER.map((v) => (
                  <Checkbox
                    key={v}
                    id={`w-${v}`}
                    checked={form.weather.includes(v)}
                    onCheckedChange={(c) =>
                      set("weather", c ? [...form.weather, v] : form.weather.filter((x) => x !== v))
                    }
                    label={label(ENV_LABELS, v)}
                  />
                ))}
              </div>
            </fieldset>
            <Checkbox
              id="seed-opt"
              checked={form.seed}
              onCheckedChange={(c) => set("seed", c)}
              label="Allow a custom scenario seed"
            />
          </PanelBody>
        </Panel>
      </div>
      {serverError ? (
        <Alert tone="danger" className="mt-4">
          {serverError}
        </Alert>
      ) : null}
      <div className="mt-4 flex gap-2">
        <Button onClick={submit} disabled={busy}>
          {busy
            ? "Assigning"
            : form.trainee_ids.length > 1
              ? `Assign to ${form.trainee_ids.length} trainees`
              : "Assign exercise"}
        </Button>
        <Button variant="secondary" onClick={() => navigate("/instructor/assignments")}>
          Cancel
        </Button>
      </div>
    </>
  );
}
