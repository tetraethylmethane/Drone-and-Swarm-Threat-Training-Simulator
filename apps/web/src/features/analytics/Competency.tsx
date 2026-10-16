import { Link } from "react-router-dom";

import { Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { Tag } from "@/components/ui/status";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import { api, qs } from "@/lib/api";
import { formatDate, formatPercent } from "@/lib/format";
import { DIMENSION_LABELS, DIMENSION_ORDER } from "@/lib/labels";
import { useAsync } from "@/lib/useAsync";

export interface AttemptMeta {
  session_id: string;
  completed_at: string | null;
  scenario_key: string;
  scenario_version: number;
  difficulty_level: number;
  seed: number;
  overall: number | null;
  rubric_version: string;
  scoring_engine_version: string;
}

interface Competency {
  trainee: { id: string; display_name: string };
  sessions: AttemptMeta[];
  dimensions: Record<
    string,
    {
      assessed_sessions: number;
      early_mean: number | null;
      recent_mean: number | null;
      change: number | null;
      trend: "improving" | "declining" | "steady" | "insufficient_data";
    }
  >;
  recurring_errors: {
    type: string;
    label: string;
    sessions_with_error: number;
    sessions_considered: number;
    in_recent_sessions: number;
    recent_window: number;
    recurring: boolean;
    latest: { session_id: string } | null;
  }[];
  equivalent_attempts: {
    timeline_digest: string;
    scenario_key: string;
    seed: number;
    difficulty_level: number;
    attempts: AttemptMeta[];
  }[];
  method: { description: string };
}

const TREND: Record<string, { text: string; tone: "success" | "danger" | "neutral" | "info" }> = {
  improving: { text: "Improving", tone: "success" },
  declining: { text: "Declining", tone: "danger" },
  steady: { text: "Steady", tone: "neutral" },
  insufficient_data: { text: "Not enough data", tone: "info" },
};

function signed(v: number | null): string {
  return v === null ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(1)}`;
}

export function compareHref(a: string, b: string): string {
  return `/sessions/compare${qs({ a, b })}`;
}

/** Competency trends, recurring errors and identical-exercise attempts for one trainee. */
export function CompetencyPanel({ traineeId, scenarioKey }: { traineeId?: string; scenarioKey?: string }) {
  const query = qs({ trainee_id: traineeId, scenario_key: scenarioKey });
  const st = useAsync((sig) => api.get<Competency>(`/analytics/competency${query}`, sig), [query]);
  if (st.loading) return <LoadingState rows={4} />;
  if (st.error || !st.data) return <ErrorState error={st.error} onRetry={st.reload} />;
  const c = st.data;
  if (!c.sessions.length)
    return (
      <Panel>
        <PanelHeader title="Competency tracking" />
        <EmptyState title="No scored sessions yet">
          Competency trends appear after completed, scored exercises.
        </EmptyState>
      </Panel>
    );
  const recurring = c.recurring_errors.filter((e) => e.sessions_with_error > 0);
  return (
    <div className="space-y-4">
      <Panel>
        <PanelHeader
          title="Competency tracking"
          description={`${c.trainee.display_name}: ${c.sessions.length} scored session(s). ${c.method.description}`}
        />
        <Table>
          <THead>
            <TR>
              <TH>Competency</TH>
              <TH>Early sessions</TH>
              <TH>Recent sessions</TH>
              <TH>Change</TH>
              <TH>Trend</TH>
              <TH>Assessed in</TH>
            </TR>
          </THead>
          <TBody>
            {DIMENSION_ORDER.map((d) => {
              const row = c.dimensions[d];
              if (!row) return null;
              return (
                <TR key={d}>
                  <TD className="font-medium">{DIMENSION_LABELS[d]}</TD>
                  <TD className="tabular">{formatPercent(row.early_mean)}</TD>
                  <TD className="tabular">{formatPercent(row.recent_mean)}</TD>
                  <TD className="tabular">{signed(row.change)}</TD>
                  <TD>
                    <Tag tone={TREND[row.trend]!.tone}>{TREND[row.trend]!.text}</Tag>
                  </TD>
                  <TD className="text-xs">{row.assessed_sessions} session(s)</TD>
                </TR>
              );
            })}
          </TBody>
        </Table>
      </Panel>
      <Panel>
        <PanelHeader
          title="Errors across sessions"
          description="How often each kind of error appeared, with the most recent session as evidence."
        />
        {!recurring.length ? (
          <EmptyState title="No errors recorded in these sessions" />
        ) : (
          <Table>
            <THead>
              <TR>
                <TH>Error</TH>
                <TH>Status</TH>
                <TH>Sessions with it</TH>
                <TH>Recent sessions</TH>
                <TH>
                  <span className="sr-only">Evidence</span>
                </TH>
              </TR>
            </THead>
            <TBody>
              {recurring.map((e) => (
                <TR key={e.type}>
                  <TD className="font-medium">{e.label}</TD>
                  <TD>
                    <Tag tone={e.recurring ? "warning" : "neutral"}>
                      {e.recurring ? "Recurring" : "Occasional"}
                    </Tag>
                  </TD>
                  <TD className="tabular">
                    {e.sessions_with_error} of {e.sessions_considered}
                  </TD>
                  <TD className="tabular">
                    {e.in_recent_sessions} of last {e.recent_window}
                  </TD>
                  <TD className="text-right">
                    {e.latest ? (
                      <Link
                        className="text-sm text-brand hover:underline"
                        to={`/sessions/${e.latest.session_id}/result`}
                      >
                        Latest occurrence
                      </Link>
                    ) : null}
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
        )}
      </Panel>
      {c.equivalent_attempts.length ? (
        <Panel>
          <PanelHeader
            title="Repeated identical exercises"
            description="Attempts with the same scenario version, seed and difficulty face exactly the same tracks, so their scores are directly comparable."
          />
          <PanelBody className="space-y-3">
            {c.equivalent_attempts.map((g) => {
              const first = g.attempts[0]!;
              const last = g.attempts[g.attempts.length - 1]!;
              return (
                <div
                  key={g.timeline_digest}
                  className="flex flex-wrap items-center justify-between gap-2 text-sm"
                >
                  <span>
                    <span className="font-medium">{g.scenario_key}</span> · seed {g.seed} · level{" "}
                    {g.difficulty_level}: {g.attempts.length} attempts, from {formatPercent(first.overall)} (
                    {formatDate(first.completed_at)}) to {formatPercent(last.overall)} (
                    {formatDate(last.completed_at)})
                  </span>
                  <Link
                    className="text-brand hover:underline"
                    to={compareHref(first.session_id, last.session_id)}
                  >
                    Compare first and latest
                  </Link>
                </div>
              );
            })}
          </PanelBody>
        </Panel>
      ) : null}
    </div>
  );
}
