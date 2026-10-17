import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Field, Textarea } from "@/components/ui/form";
import { PageHeader, Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { Alert, Tag } from "@/components/ui/status";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import { api } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import type { Assignment, DifficultyAdjustment } from "@/lib/types";
import { errorMessage, useAsync } from "@/lib/useAsync";

const MIN_REASON = 3;
const MAX_REASON = 280;

/** Instructor view of one adaptive assignment: every recorded adjustment with its reason, and a
 *  one-step override within the assignment's bounds (recorded and audited like any adjustment). */
export function AssignmentDifficultyPage() {
  const { assignmentId = "" } = useParams();
  const assignment = useAsync(
    (sig) => api.get<Assignment>(`/assignments/${assignmentId}`, sig),
    [assignmentId],
  );
  const traineeId = assignment.data?.trainee.id;
  const history = useAsync(
    (sig) =>
      traineeId
        ? api.get<{ items: DifficultyAdjustment[] }>(`/analytics/difficulty?trainee_id=${traineeId}`, sig)
        : Promise.resolve({ items: [] }),
    [traineeId],
  );
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (assignment.loading) return <LoadingState rows={4} />;
  if (assignment.error) return <ErrorState error={assignment.error} onRetry={assignment.reload} />;
  const a = assignment.data!;
  const current = a.progress?.next_difficulty_level ?? a.difficulty_level;
  const items = (history.data?.items ?? []).filter((d) => d.assignment_id === a.id);

  async function override(level: number) {
    setError(null);
    setDone(null);
    if (reason.trim().length < MIN_REASON) {
      setError(`Give a reason of at least ${MIN_REASON} characters; it is recorded with the change.`);
      return;
    }
    setBusy(true);
    try {
      await api.post(`/assignments/${a.id}/difficulty`, { level, reason: reason.trim() });
      setDone(`The next session will run at level ${level}.`);
      setReason("");
      assignment.reload();
      history.reload();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader
        title={`Difficulty: ${a.title}`}
        description={`${a.trainee.display_name} · ${a.scenario.name} v${a.scenario.version}`}
        actions={
          <Button asChild variant="ghost" size="sm">
            <Link to="/instructor/assignments">Back to assignments</Link>
          </Button>
        }
      />
      <div className="space-y-4">
        {a.difficulty_mode !== "adaptive" ? (
          <Alert tone="info" title="Fixed difficulty">
            This assignment always runs at level {a.difficulty_level}. Only adaptive assignments can be
            adjusted.
          </Alert>
        ) : (
          <Panel>
            <PanelHeader
              title={`Next session: level ${current}`}
              description={`Adaptive between level ${a.min_level} and ${a.max_level}. An override moves one level and is recorded with your name and reason; later sessions keep adjusting from the new level.`}
            />
            <PanelBody className="space-y-3">
              <Field
                label="Reason for the change"
                hint={`${reason.trim().length} of ${MAX_REASON} characters`}
              >
                <Textarea value={reason} maxLength={MAX_REASON} onChange={(e) => setReason(e.target.value)} />
              </Field>
              <div className="flex flex-wrap gap-2">
                <Button
                  disabled={busy || current <= a.min_level}
                  onClick={() => override(current - 1)}
                  variant="secondary"
                >
                  Lower to level {current - 1}
                </Button>
                <Button
                  disabled={busy || current >= a.max_level}
                  onClick={() => override(current + 1)}
                  variant="secondary"
                >
                  Raise to level {current + 1}
                </Button>
              </div>
              {error ? <Alert tone="danger">{error}</Alert> : null}
              {done ? <Alert tone="success">{done}</Alert> : null}
            </PanelBody>
          </Panel>
        )}
        <Panel>
          <PanelHeader
            title="Adjustment history"
            description="Every recommendation recorded for this assignment, including holds, with the rule that produced it."
          />
          {history.loading ? (
            <LoadingState />
          ) : history.error ? (
            <ErrorState error={history.error} onRetry={history.reload} />
          ) : !items.length ? (
            <EmptyState title="No adjustments yet">
              A recommendation is recorded after each completed adaptive session.
            </EmptyState>
          ) : (
            <Table>
              <THead>
                <TR>
                  <TH>When</TH>
                  <TH>Change</TH>
                  <TH>Confidence</TH>
                  <TH>Reason</TH>
                  <TH>
                    <span className="sr-only">Session</span>
                  </TH>
                </TR>
              </THead>
              <TBody>
                {items.map((d) => (
                  <TR key={d.id}>
                    <TD className="whitespace-nowrap text-xs">{formatDateTime(d.created_at)}</TD>
                    <TD>
                      <Tag
                        tone={
                          d.change === "increase"
                            ? "success"
                            : d.change === "decrease"
                              ? "warning"
                              : "neutral"
                        }
                      >
                        {d.from_level} to {d.to_level} ({d.change})
                      </Tag>
                    </TD>
                    <TD className="text-xs">{d.confidence}</TD>
                    <TD className="text-xs">{d.reason}</TD>
                    <TD className="whitespace-nowrap text-right">
                      {d.session_id ? (
                        <Link
                          className="text-sm text-brand hover:underline"
                          to={`/sessions/${d.session_id}/result`}
                        >
                          Session
                        </Link>
                      ) : null}
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          )}
        </Panel>
      </div>
    </>
  );
}
