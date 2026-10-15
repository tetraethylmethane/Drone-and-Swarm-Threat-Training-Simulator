import { useEffect, useState, type ReactNode } from "react";
import { Link, useParams } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Field, Select, Textarea } from "@/components/ui/form";
import { Checkbox, Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/overlay";
import { KeyValues, PageHeader, Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { Alert, Tag, toneForStatus } from "@/components/ui/status";
import { ErrorState, LoadingState } from "@/components/ui/states";
import { api, ApiError, download } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatDateTime } from "@/lib/format";
import { label, STATUS_LABELS } from "@/lib/labels";
import type { Review, ScoreResult, SessionState } from "@/lib/types";
import { errorMessage, useAsync } from "@/lib/useAsync";

import { ErrorAnalysisSection, OverviewSection, TimelineSection, TrackDecisionsSection } from "./AarSections";

export function AarPage() {
  const { sessionId = "" } = useParams();
  const { user } = useAuth();
  const session = useAsync((sig) => api.get<SessionState>(`/sessions/${sessionId}`, sig), [sessionId]);
  const result = useAsync(
    (sig) =>
      api.get<ScoreResult>(`/sessions/${sessionId}/result`, sig).catch((e) => {
        if (e instanceof ApiError && e.code === "result_not_available") return null;
        throw e;
      }),
    [sessionId],
  );
  const isTrainee = user?.role === "trainee";

  if (session.loading || result.loading) return <LoadingState rows={8} label="Loading after-action review" />;
  if (session.error || !session.data) return <ErrorState error={session.error} onRetry={session.reload} />;
  if (result.error) return <ErrorState error={result.error} onRetry={result.reload} />;
  const s = session.data;
  const r = result.data;
  const back = isTrainee
    ? { to: "/trainee/history", label: "My progress" }
    : { to: "/instructor/sessions", label: "Sessions and reviews" };

  if (!r) {
    return (
      <>
        <PageHeader
          eyebrow={
            <Link to={back.to} className="hover:underline">
              {back.label}
            </Link>
          }
          title={s.scenario.name}
        />
        <Panel>
          <PanelBody>
            <p className="text-sm">
              This session is {label(STATUS_LABELS, s.status).toLowerCase()} and has no score result.
              {s.status === "aborted" ? " Aborted sessions are not scored." : ""}
            </p>
            {["created", "running", "paused"].includes(s.status) && isTrainee ? (
              <Button asChild className="mt-3">
                <Link to={`/exercise/${s.id}`}>Return to exercise</Link>
              </Button>
            ) : null}
          </PanelBody>
        </Panel>
      </>
    );
  }

  const detailed = r.feedback_level === "detailed";
  const trackIds = (r.items ?? []).map((i) => i.track_id);
  return (
    <>
      <PageHeader
        eyebrow={
          <Link to={back.to} className="hover:underline">
            {back.label}
          </Link>
        }
        title={`After-action review: ${s.scenario.name}`}
        description={`${s.trainee.display_name} · attempt ${s.attempt_number} · completed ${formatDateTime(s.completed_at)}`}
      />
      <Tabs defaultValue="summary">
        <TabsList aria-label="After-action review sections" className="mb-4">
          <TabsTrigger value="summary">Summary</TabsTrigger>
          {detailed ? <TabsTrigger value="tracks">Track decisions</TabsTrigger> : null}
          <TabsTrigger value="timeline">Event timeline</TabsTrigger>
          {detailed ? <TabsTrigger value="errors">Error analysis</TabsTrigger> : null}
          <TabsTrigger value="review">Instructor review</TabsTrigger>
          <TabsTrigger value="export">Export and verification</TabsTrigger>
        </TabsList>
        <TabsContent value="summary">
          {!detailed ? (
            <Alert tone="info" className="mb-4">
              Your instructor has enabled summary feedback for this exercise. Track-level ground truth is not
              shown.
            </Alert>
          ) : null}
          <OverviewSection session={s} result={r} />
        </TabsContent>
        {detailed ? (
          <TabsContent value="tracks">
            <TrackDecisionsSection result={r} />
          </TabsContent>
        ) : null}
        <TabsContent value="timeline">
          <TimelineSection sessionId={s.id} trackIds={trackIds} allowGroundTruth={detailed || !isTrainee} />
        </TabsContent>
        {detailed ? (
          <TabsContent value="errors">
            <ErrorAnalysisSection result={r} />
          </TabsContent>
        ) : null}
        <TabsContent value="review">
          <ReviewSection
            session={s}
            result={r}
            editable={user?.permissions.includes("reviews:write") ?? false}
          />
        </TabsContent>
        <TabsContent value="export">
          <ExportSection
            session={s}
            result={r}
            canVerify={user?.permissions.includes("sessions:verify") ?? false}
            detailed={detailed}
          />
        </TabsContent>
      </Tabs>
    </>
  );
}

function ReviewSection({
  session,
  result,
  editable,
}: {
  session: SessionState;
  result: ScoreResult;
  editable: boolean;
}) {
  const st = useAsync((sig) => api.get<Review | null>(`/sessions/${session.id}/review`, sig), [session.id]);
  const [form, setForm] = useState({
    status: "pending",
    notes: "",
    strengths: "",
    improvements: "",
    focus_objectives: [] as string[],
    shared_with_trainee: false,
  });
  const [msg, setMsg] = useState<{ tone: "success" | "danger"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (st.data) {
      setForm({
        status: st.data.status,
        notes: st.data.notes ?? "",
        strengths: st.data.strengths,
        improvements: st.data.improvements,
        focus_objectives: st.data.focus_objectives,
        shared_with_trainee: st.data.shared_with_trainee,
      });
    }
  }, [st.data]);

  if (st.loading) return <LoadingState />;
  if (st.error) return <ErrorState error={st.error} onRetry={st.reload} />;

  if (!editable) {
    const rv = st.data;
    return (
      <Panel>
        <PanelHeader title="Instructor review" />
        <PanelBody>
          {rv ? (
            <KeyValues
              items={[
                ["Reviewer", rv.reviewer.display_name],
                [
                  "Status",
                  <Tag key="s" tone={toneForStatus(rv.status)}>
                    {label(STATUS_LABELS, rv.status)}
                  </Tag>,
                ],
                ["Strengths", rv.strengths || "—"],
                ["Areas to improve", rv.improvements || "—"],
                ["Focus objectives", rv.focus_objectives.length ? rv.focus_objectives.join(", ") : "—"],
                ["Updated", formatDateTime(rv.updated_at)],
              ]}
            />
          ) : (
            <p className="text-sm text-ink-muted">
              No instructor review has been shared for this session yet.
            </p>
          )}
        </PanelBody>
      </Panel>
    );
  }

  async function save() {
    setBusy(true);
    setMsg(null);
    try {
      await api.put(`/sessions/${session.id}/review`, form);
      setMsg({ tone: "success", text: "Review saved." });
      st.reload();
    } catch (err) {
      setMsg({ tone: "danger", text: errorMessage(err) });
    } finally {
      setBusy(false);
    }
  }

  return (
    <Panel>
      <PanelHeader
        title="Instructor review"
        description="Notes stay private to instructors. Strengths, improvements and focus objectives are visible to the trainee when shared."
      />
      <PanelBody className="grid gap-4 lg:grid-cols-2">
        <div className="space-y-3">
          <Field label="Review status">
            <Select value={form.status} onChange={(e) => setForm((f) => ({ ...f, status: e.target.value }))}>
              {["pending", "in_review", "reviewed", "follow_up"].map((v) => (
                <option key={v} value={v}>
                  {label(STATUS_LABELS, v)}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Strengths">
            <Textarea
              maxLength={4000}
              value={form.strengths}
              onChange={(e) => setForm((f) => ({ ...f, strengths: e.target.value }))}
            />
          </Field>
          <Field label="Areas to improve">
            <Textarea
              maxLength={4000}
              value={form.improvements}
              onChange={(e) => setForm((f) => ({ ...f, improvements: e.target.value }))}
            />
          </Field>
        </div>
        <div className="space-y-3">
          <fieldset>
            <legend className="mb-1.5 text-xs font-medium">Focus objectives for next attempt</legend>
            <div className="space-y-1.5">
              {result.objectives.map((o) => (
                <Checkbox
                  key={o.id}
                  id={`focus-${o.id}`}
                  checked={form.focus_objectives.includes(o.id)}
                  onCheckedChange={(v) =>
                    setForm((f) => ({
                      ...f,
                      focus_objectives: v
                        ? [...f.focus_objectives, o.id]
                        : f.focus_objectives.filter((x) => x !== o.id),
                    }))
                  }
                  label={o.description}
                />
              ))}
            </div>
          </fieldset>
          <Field label="Private notes">
            <Textarea
              maxLength={8000}
              value={form.notes}
              onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))}
            />
          </Field>
          <Checkbox
            id="share-review"
            checked={form.shared_with_trainee}
            onCheckedChange={(v) => setForm((f) => ({ ...f, shared_with_trainee: v }))}
            label="Share strengths, improvements and focus objectives with the trainee"
          />
          {msg ? <Alert tone={msg.tone}>{msg.text}</Alert> : null}
          <Button onClick={save} disabled={busy}>
            {busy ? "Saving" : "Save review"}
          </Button>
        </div>
      </PanelBody>
    </Panel>
  );
}

interface Verification {
  timeline_reproduced: boolean;
  /** null when the event log was removed by the data-retention policy. */
  stored_log_intact: boolean | null;
  score_checked: boolean;
  score_reproduced?: boolean;
  reproducible: boolean;
  timeline_digest_recorded: string;
  timeline_digest_regenerated: string;
  score_digest_recorded?: string;
  score_digest_recomputed?: string;
  engine_version_recorded: string;
  engine_version_current: string;
  score_note?: string;
}

function ExportSection({
  session,
  result,
  canVerify,
  detailed,
}: {
  session: SessionState;
  result: ScoreResult;
  canVerify: boolean;
  detailed: boolean;
}) {
  const [msg, setMsg] = useState<string | null>(null);
  const [verify, setVerify] = useState<Verification | null>(null);
  const [busy, setBusy] = useState(false);
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Panel>
        <PanelHeader
          title="Export report"
          description="PDF after-action review generated from the stored record. Exports are recorded in the audit log."
        />
        <PanelBody className="space-y-3">
          {detailed ? (
            <Button
              onClick={async () => {
                setMsg(null);
                try {
                  await download(`/reports/sessions/${session.id}.pdf`, `drikr-aar-${session.id}.pdf`);
                } catch (err) {
                  setMsg(errorMessage(err));
                }
              }}
            >
              Download PDF report
            </Button>
          ) : (
            <p className="text-sm text-ink-muted">
              PDF reports are available when detailed feedback is enabled for the exercise.
            </p>
          )}
          {msg ? <Alert tone="danger">{msg}</Alert> : null}
        </PanelBody>
      </Panel>
      <Panel>
        <PanelHeader
          title="Traceability"
          description="Digests identify the exact inputs this result was computed from."
        />
        <PanelBody className="space-y-3">
          <KeyValues
            items={[
              ["Simulation engine", session.engine_version],
              ["Seed", String(session.seed)],
              [
                "Configuration digest",
                <span key="c" className="break-all text-xs">
                  {session.config_digest}
                </span>,
              ],
              [
                "Timeline digest",
                <span key="t" className="break-all text-xs">
                  {session.timeline_digest}
                </span>,
              ],
              [
                "Scoring",
                `${result.scoring_engine_version}, rubric ${result.rubric.key} v${result.rubric.version}`,
              ],
              ...(result.input_digest
                ? ([
                    [
                      "Score input digest",
                      <span key="i" className="break-all text-xs">
                        {result.input_digest}
                      </span>,
                    ],
                  ] as [string, ReactNode][])
                : []),
            ]}
          />
          {canVerify ? (
            <>
              <Button
                variant="secondary"
                disabled={busy}
                onClick={async () => {
                  setBusy(true);
                  try {
                    setVerify(await api.post<Verification>(`/sessions/${session.id}/verify`));
                  } catch (err) {
                    setMsg(errorMessage(err));
                  } finally {
                    setBusy(false);
                  }
                }}
              >
                {busy ? "Verifying" : "Verify reproducibility"}
              </Button>
              {verify ? (
                <Alert
                  tone={verify.reproducible ? "success" : "danger"}
                  title={verify.reproducible ? "Reproduced" : "Not reproduced"}
                >
                  <ul className="list-disc pl-5 text-xs">
                    <li>
                      Timeline regenerated from configuration and seed:{" "}
                      {verify.timeline_reproduced ? "identical" : "different"}
                    </li>
                    <li>
                      Stored event log integrity:{" "}
                      {verify.stored_log_intact === null
                        ? "not checked (event log removed by the retention policy)"
                        : verify.stored_log_intact
                          ? "intact"
                          : "changed"}
                    </li>
                    <li>
                      Score recomputed from stored events and rubric version:{" "}
                      {verify.score_checked
                        ? verify.score_reproduced
                          ? "identical"
                          : "different"
                        : "not scored"}
                    </li>
                    {verify.score_note ? <li>{verify.score_note}</li> : null}
                    {verify.engine_version_current !== verify.engine_version_recorded ? (
                      <li>
                        Engine version changed from {verify.engine_version_recorded} to{" "}
                        {verify.engine_version_current}
                      </li>
                    ) : null}
                  </ul>
                </Alert>
              ) : null}
            </>
          ) : null}
        </PanelBody>
      </Panel>
    </div>
  );
}
