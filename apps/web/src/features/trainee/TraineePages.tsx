import { Link, useParams } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { PageHeader, Panel, PanelHeader } from "@/components/ui/panel";
import { Tag, toneForStatus } from "@/components/ui/status";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import { FirstVisitGuide, GUIDE_PATH } from "@/features/guide/HowToPlay";
import { api, qs } from "@/lib/api";
import { formatClock, formatDate, formatDateTime, formatPercent } from "@/lib/format";
import { ENV_LABELS, label, STATUS_LABELS } from "@/lib/labels";
import type { Assignment, Page, ScenarioSummary, SessionState } from "@/lib/types";
import { useAsync } from "@/lib/useAsync";

import { BriefingPanel, LaunchPanel } from "./LaunchPanel";

export function TraineeHome() {
  const assignments = useAsync((sig) => api.get<Page<Assignment>>("/assignments?limit=100", sig), []);
  const sessions = useAsync((sig) => api.get<Page<SessionState>>("/sessions?limit=10", sig), []);
  return (
    <>
      <FirstVisitGuide />
      <PageHeader
        title="My exercises"
        description="Exercises assigned to you by an instructor. Open one to read the briefing and launch it."
        actions={
          <Button asChild variant="secondary">
            <Link to={GUIDE_PATH}>How to play</Link>
          </Button>
        }
      />
      <Panel className="mb-4">
        <PanelHeader title="Assigned exercises" />
        {assignments.loading ? (
          <LoadingState />
        ) : assignments.error ? (
          <ErrorState error={assignments.error} onRetry={assignments.reload} />
        ) : !assignments.data?.items.length ? (
          <EmptyState title="No exercises assigned">
            Your instructor has not assigned any exercises yet. You can practise with the{" "}
            <Link className="text-brand underline" to="/trainee/practice">
              practice library
            </Link>
            .
          </EmptyState>
        ) : (
          <Table>
            <THead>
              <TR>
                <TH>Exercise</TH>
                <TH>Status</TH>
                <TH>Attempts</TH>
                <TH>Best score</TH>
                <TH>Due</TH>
                <TH>
                  <span className="sr-only">Actions</span>
                </TH>
              </TR>
            </THead>
            <TBody>
              {assignments.data.items.map((a) => (
                <TR key={a.id}>
                  <TD>
                    <p className="font-medium">{a.title}</p>
                    <p className="text-xs text-ink-muted">{a.scenario.name}</p>
                  </TD>
                  <TD>
                    <Tag tone={toneForStatus(a.progress?.state)}>
                      {label(STATUS_LABELS, a.progress?.state)}
                    </Tag>
                  </TD>
                  <TD className="tabular">
                    {a.progress?.attempts_used ?? 0} of {a.max_attempts}
                  </TD>
                  <TD className="tabular">{formatPercent(a.progress?.best_overall)}</TD>
                  <TD>{formatDate(a.due_at)}</TD>
                  <TD className="text-right">
                    <Button
                      asChild
                      size="sm"
                      variant={a.progress?.active_session_id ? "primary" : "secondary"}
                    >
                      <Link to={`/trainee/assignments/${a.id}`}>
                        {a.progress?.active_session_id ? "Resume" : "Open"}
                      </Link>
                    </Button>
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
        )}
      </Panel>
      <RecentSessions state={sessions} />
    </>
  );
}

function RecentSessions({ state }: { state: ReturnType<typeof useAsync<Page<SessionState>>> }) {
  return (
    <Panel>
      <PanelHeader
        title="Recent attempts"
        actions={
          <Link className="text-sm text-brand hover:underline" to="/trainee/history">
            View progress
          </Link>
        }
      />
      {state.loading ? (
        <LoadingState />
      ) : state.error ? (
        <ErrorState error={state.error} onRetry={state.reload} />
      ) : !state.data?.items.length ? (
        <EmptyState title="No attempts yet">Completed exercises and their results appear here.</EmptyState>
      ) : (
        <SessionTable sessions={state.data.items} />
      )}
    </Panel>
  );
}

export function SessionTable({ sessions }: { sessions: SessionState[] }) {
  return (
    <Table>
      <THead>
        <TR>
          <TH>Scenario</TH>
          <TH>Mode</TH>
          <TH>Started</TH>
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
            <TD>
              {s.scenario.name} <span className="text-xs text-ink-subtle">v{s.scenario.version}</span>
            </TD>
            <TD className="text-xs">
              {s.mode === "self_guided" ? "Practice" : `Assigned, attempt ${s.attempt_number}`}
            </TD>
            <TD className="text-xs">{formatDateTime(s.started_at ?? s.created_at)}</TD>
            <TD>
              <Tag tone={toneForStatus(s.status)}>{label(STATUS_LABELS, s.status)}</Tag>
            </TD>
            <TD className="tabular">{s.result ? formatPercent(s.result.overall) : "—"}</TD>
            <TD className="text-right">
              {s.status === "completed" ? (
                <Link className="text-sm text-brand hover:underline" to={`/sessions/${s.id}/result`}>
                  Result
                </Link>
              ) : s.status !== "aborted" ? (
                <Link className="text-sm text-brand hover:underline" to={`/exercise/${s.id}`}>
                  Continue
                </Link>
              ) : null}
            </TD>
          </TR>
        ))}
      </TBody>
    </Table>
  );
}

export function AssignmentBriefingPage() {
  const { assignmentId = "" } = useParams();
  const st = useAsync((sig) => api.get<Assignment>(`/assignments/${assignmentId}`, sig), [assignmentId]);
  if (st.loading) return <LoadingState rows={6} />;
  if (st.error || !st.data) return <ErrorState error={st.error} onRetry={st.reload} />;
  const a = st.data;
  const p = a.progress!;
  const b = a.briefing!;
  const exhausted = p.attempts_remaining <= 0 ? "All permitted attempts have been used." : null;
  return (
    <>
      <PageHeader
        eyebrow={
          <Link to="/trainee" className="hover:underline">
            My exercises
          </Link>
        }
        title={a.title}
        description={`${a.scenario.name} · assigned by ${a.assigned_by.display_name}${a.due_at ? ` · due ${formatDate(a.due_at)}` : ""}`}
      />
      {a.instructions ? (
        <Panel className="mb-4">
          <PanelHeader title="Instructor instructions" />
          <p className="whitespace-pre-line px-4 py-3 text-sm">{a.instructions}</p>
        </Panel>
      ) : null}
      <div className="space-y-4">
        <BriefingPanel briefing={b} />
        <LaunchPanel
          options={a.trainee_options}
          defaults={{ time_of_day: b.environment.time_of_day, weather: b.environment.weather }}
          body={{ assignment_id: a.id }}
          activeSessionId={p.active_session_id}
          disabledReason={exhausted}
          difficultyLevel={p.next_difficulty_level}
        />
        {p.sessions.length ? (
          <Panel>
            <PanelHeader title="Previous attempts" />
            <Table>
              <THead>
                <TR>
                  <TH>Attempt</TH>
                  <TH>Status</TH>
                  <TH>Difficulty</TH>
                  <TH>Score</TH>
                  <TH>Completed</TH>
                  <TH>
                    <span className="sr-only">Actions</span>
                  </TH>
                </TR>
              </THead>
              <TBody>
                {p.sessions.map((s) => (
                  <TR key={s.id}>
                    <TD>{s.attempt_number}</TD>
                    <TD>
                      <Tag tone={toneForStatus(s.status)}>{label(STATUS_LABELS, s.status)}</Tag>
                    </TD>
                    <TD>{s.difficulty_level}</TD>
                    <TD className="tabular">{formatPercent(s.overall)}</TD>
                    <TD className="text-xs">{formatDateTime(s.completed_at)}</TD>
                    <TD className="text-right">
                      {s.status === "completed" ? (
                        <Link className="text-sm text-brand hover:underline" to={`/sessions/${s.id}/result`}>
                          Result
                        </Link>
                      ) : null}
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          </Panel>
        ) : null}
      </div>
    </>
  );
}

export function PracticeLibraryPage() {
  const st = useAsync((sig) => api.get<{ items: ScenarioSummary[] }>("/scenarios", sig), []);
  return (
    <>
      <PageHeader
        title="Practice library"
        description="Self-guided practice. Results are recorded in your progress but are not part of an assignment."
      />
      <Panel>
        {st.loading ? (
          <LoadingState />
        ) : st.error ? (
          <ErrorState error={st.error} onRetry={st.reload} />
        ) : !st.data?.items.length ? (
          <EmptyState title="No practice scenarios available">
            An instructor has not enabled any scenarios for self-guided practice.
          </EmptyState>
        ) : (
          <Table>
            <THead>
              <TR>
                <TH>Scenario</TH>
                <TH>Environment</TH>
                <TH>Duration</TH>
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
                    <p className="max-w-2xl text-xs text-ink-muted">{s.description}</p>
                  </TD>
                  <TD className="whitespace-nowrap text-xs">
                    {label(ENV_LABELS, s.environment.terrain)}, {label(ENV_LABELS, s.environment.time_of_day)}
                    , {label(ENV_LABELS, s.environment.weather)}
                  </TD>
                  <TD className="tabular">{formatClock(s.duration_s * 1000)}</TD>
                  <TD className="text-right">
                    <Button asChild size="sm" variant="secondary">
                      <Link to={`/trainee/practice/${s.id}`}>Open</Link>
                    </Button>
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

export function PracticeBriefingPage() {
  const { scenarioId = "" } = useParams();
  const st = useAsync((sig) => api.get<ScenarioSummary>(`/scenarios/${scenarioId}`, sig), [scenarioId]);
  const active = useAsync((sig) => api.get<Page<SessionState>>(`/sessions${qs({ limit: 50 })}`, sig), []);
  if (st.loading) return <LoadingState rows={6} />;
  if (st.error || !st.data?.briefing) return <ErrorState error={st.error} onRetry={st.reload} />;
  const s = st.data;
  const b = s.briefing!;
  const inProgress = active.data?.items.find(
    (x) =>
      x.mode === "self_guided" &&
      x.scenario.id === s.id &&
      ["created", "running", "paused"].includes(x.status),
  );
  return (
    <>
      <PageHeader
        eyebrow={
          <Link to="/trainee/practice" className="hover:underline">
            Practice library
          </Link>
        }
        title={s.name}
        description="Self-guided practice"
      />
      <div className="space-y-4">
        <BriefingPanel briefing={b} />
        <LaunchPanel
          options={{
            time_of_day: ["day", "dusk", "night"],
            weather: ["clear", "haze", "rain", "fog"],
            allow_custom_seed: true,
          }}
          defaults={{ time_of_day: b.environment.time_of_day, weather: b.environment.weather }}
          body={{ scenario_id: s.id }}
          activeSessionId={inProgress?.id}
        />
      </div>
    </>
  );
}
