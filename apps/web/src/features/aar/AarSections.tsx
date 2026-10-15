import { useMemo, useState } from "react";

import { axisStyle, EChart } from "@/components/charts/EChart";
import { Button } from "@/components/ui/button";
import { Field, Select } from "@/components/ui/form";
import { KeyValues, Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { ScoreBar, Tag, toneForStatus } from "@/components/ui/status";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import { api, qs } from "@/lib/api";
import { formatClock, formatDateTime, formatDistance, formatPercent, formatSeconds } from "@/lib/format";
import {
  CLASSIFICATION_LABELS,
  CONFIDENCE_LABELS,
  DIMENSION_HELP,
  DIMENSION_LABELS,
  DIMENSION_ORDER,
  label,
  RESPONSE_LABELS,
  SENSOR_LABELS,
  STATUS_LABELS,
} from "@/lib/labels";
import type { Page, ResultItem, ScoreResult, SessionState, SimEvent } from "@/lib/types";
import { useAsync } from "@/lib/useAsync";

export function OverviewSection({ session, result }: { session: SessionState; result: ScoreResult }) {
  const scored = result.status === "scored";
  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_1fr]">
      <Panel>
        <PanelHeader title="Session overview" />
        <PanelBody>
          <KeyValues
            items={[
              ["Scenario", `${session.scenario.name} (version ${session.scenario.version})`],
              ["Trainee", session.trainee.display_name],
              [
                "Status",
                `${label(STATUS_LABELS, session.status)}${session.completion_reason ? ` (${session.completion_reason.replace(/_/g, " ")})` : ""}`,
              ],
              ["Exercise time", `${formatClock(session.sim_time_ms)} of ${formatClock(session.duration_ms)}`],
              ["Difficulty level", String(session.difficulty_level)],
              ["Completed", formatDateTime(session.completed_at)],
              [
                "Scoring",
                `${result.scoring_engine_version}, rubric ${result.rubric.key} v${result.rubric.version}`,
              ],
            ]}
          />
        </PanelBody>
      </Panel>
      <Panel>
        <PanelHeader title="Overall result" description={result.explanation} />
        <PanelBody>
          {scored ? (
            <div className="flex items-end gap-6">
              <div>
                <p className="tabular text-4xl font-semibold tracking-tight">
                  {formatPercent(result.overall)}
                </p>
                <p className="text-xs text-ink-muted">Pass mark {result.pass_mark}%</p>
              </div>
              <Tag tone={result.passed ? "success" : "danger"} className="mb-2">
                {result.passed ? "Passed" : "Not passed"}
              </Tag>
            </div>
          ) : (
            <p className="text-sm text-ink-muted">
              Insufficient data: no track was observable before the session ended, so no score was produced.
            </p>
          )}
          <p className="mt-3 text-xs text-ink-subtle">
            {result.counts.classified_tracks} of {result.counts.observable_tracks} observed tracks classified.
          </p>
        </PanelBody>
      </Panel>
      {scored ? (
        <Panel className="lg:col-span-2">
          <PanelHeader
            title="Performance breakdown"
            description="Each dimension is the mean credit over its applicable items. Weights come from the rubric version shown above."
          />
          <Table>
            <THead>
              <TR>
                <TH>Dimension</TH>
                <TH className="w-40">Score</TH>
                <TH>Weight</TH>
                <TH>Contribution</TH>
                <TH>How it was calculated</TH>
              </TR>
            </THead>
            <TBody>
              {DIMENSION_ORDER.map((d) => {
                const dim = result.dimensions[d];
                if (!dim) return null;
                return (
                  <TR key={d}>
                    <TD>
                      <p className="font-medium">{DIMENSION_LABELS[d]}</p>
                      <p className="max-w-xs text-xs text-ink-subtle">{DIMENSION_HELP[d]}</p>
                    </TD>
                    <TD>
                      <p className="tabular">
                        {dim.applicable ? formatPercent(dim.score) : "Not applicable"}
                      </p>
                      {dim.applicable ? (
                        <ScoreBar value={dim.score} label={`${DIMENSION_LABELS[d]} score`} />
                      ) : null}
                    </TD>
                    <TD className="tabular text-xs">
                      {dim.weight.toFixed(2)}
                      {dim.applicable && Math.abs(dim.effective_weight - dim.weight) > 0.001 ? (
                        <span className="text-ink-subtle">
                          {" "}
                          (effective {dim.effective_weight.toFixed(3)})
                        </span>
                      ) : null}
                    </TD>
                    <TD className="tabular text-xs">{dim.applicable ? dim.contribution.toFixed(2) : "—"}</TD>
                    <TD className="text-xs text-ink-muted">{dim.summary}</TD>
                  </TR>
                );
              })}
            </TBody>
          </Table>
        </Panel>
      ) : null}
      <Panel>
        <PanelHeader title="Learning objectives" />
        {result.objectives.length ? (
          <ul className="divide-y divide-border">
            {result.objectives.map((o) => (
              <li key={o.id} className="flex items-start justify-between gap-3 px-4 py-2.5">
                <div>
                  <p className="text-sm">{o.description}</p>
                  <p className="text-xs text-ink-subtle">{o.detail}</p>
                </div>
                <Tag tone={toneForStatus(o.status)}>{label(STATUS_LABELS, o.status)}</Tag>
              </li>
            ))}
          </ul>
        ) : (
          <EmptyState title="No objectives" />
        )}
      </Panel>
      <Panel>
        <PanelHeader title="Feedback" description="Generated from the computed result." />
        <PanelBody className="space-y-3 text-sm">
          <div>
            <h3>Strengths</h3>
            {result.feedback.strengths.length ? (
              <ul className="mt-1 list-disc space-y-0.5 pl-5">
                {result.feedback.strengths.map((s) => (
                  <li key={s}>{s}</li>
                ))}
              </ul>
            ) : (
              <p className="mt-1 text-ink-muted">None identified in this session.</p>
            )}
          </div>
          <div>
            <h3>Areas to practise</h3>
            {result.feedback.improvements.length ? (
              <ul className="mt-1 list-disc space-y-0.5 pl-5">
                {result.feedback.improvements.map((s) => (
                  <li key={s}>{s}</li>
                ))}
              </ul>
            ) : (
              <p className="mt-1 text-ink-muted">None identified in this session.</p>
            )}
          </div>
        </PanelBody>
      </Panel>
    </div>
  );
}

function pathText(item: ResultItem): string {
  return item.decision_path
    .filter((p) => !p.leaf)
    .map((p) => `${p.fact} ${p.op} ${JSON.stringify(p.value)}: ${p.result ? "yes" : "no"}`)
    .join(" → ");
}

export function TrackDecisionsSection({ result }: { result: ScoreResult }) {
  const items = result.items ?? [];
  const credits = useMemo(() => {
    const m = new Map<string, Record<string, { credit: number; reason: string }>>();
    for (const d of DIMENSION_ORDER) {
      for (const it of result.dimensions[d]?.items ?? []) {
        if (!it.track_id) continue;
        const row = m.get(it.track_id) ?? {};
        row[d] = { credit: it.credit, reason: it.reason };
        m.set(it.track_id, row);
      }
    }
    return m;
  }, [result]);
  if (!items.length) return <EmptyState title="No track-level detail available" />;
  return (
    <Panel>
      <PanelHeader
        title="Track decisions and scoring outcomes"
        description="Ground truth is shown after the exercise. Rubric path shows how the expected response was derived."
      />
      <Table>
        <THead>
          <TR>
            <TH>Track</TH>
            <TH>Ground truth</TH>
            <TH>Your classification</TH>
            <TH>Time to classify</TH>
            <TH>Your response</TH>
            <TH>Rubric expected</TH>
            <TH>Credit</TH>
          </TR>
        </THead>
        <TBody>
          {items.map((it) => {
            const c = credits.get(it.track_id) ?? {};
            const correct = it.final_classification === it.true_class;
            const delay =
              it.first_classification_s !== null && it.first_available_s !== null
                ? it.first_classification_s - it.first_available_s
                : null;
            return (
              <TR key={it.track_id}>
                <TD className="font-medium">{it.track_id}</TD>
                <TD className="text-xs">
                  <p>{label(CLASSIFICATION_LABELS, it.true_class)}</p>
                  <p className="text-ink-subtle">
                    {it.behavior}
                    {it.cooperative ? ", cooperative" : ""}
                    {it.beacon_observed ? ", beacon seen" : ""} · closest {formatDistance(it.closest_range_m)}
                  </p>
                </TD>
                <TD className="text-xs">
                  {it.final_classification ? (
                    <>
                      <span className={correct ? "text-success" : "text-danger"}>
                        {label(CLASSIFICATION_LABELS, it.final_classification)}
                      </span>{" "}
                      <span className="text-ink-subtle">
                        ({label(CONFIDENCE_LABELS, it.final_confidence)})
                      </span>
                    </>
                  ) : (
                    <span className="text-danger">Not classified</span>
                  )}
                  {it.evidence_at_decision !== null ? (
                    <p className="text-ink-subtle">Evidence {it.evidence_at_decision.toFixed(2)}</p>
                  ) : null}
                </TD>
                <TD className="tabular text-xs">{formatSeconds(delay)}</TD>
                <TD className="text-xs">{label(RESPONSE_LABELS, it.final_response, "None")}</TD>
                <TD className="text-xs">
                  <p>{it.expected_responses.map((r) => label(RESPONSE_LABELS, r)).join(" or ")}</p>
                  {it.acceptable_responses.length ? (
                    <p className="text-ink-subtle">
                      Acceptable: {it.acceptable_responses.map((r) => label(RESPONSE_LABELS, r)).join(", ")}
                    </p>
                  ) : null}
                  <p className="mt-0.5 text-2xs text-ink-subtle" title={pathText(it)}>
                    Rubric leaf: {it.decision_leaf}
                  </p>
                </TD>
                <TD className="text-xs">
                  {(["recognition", "timing", "consistency"] as const).map((d) =>
                    c[d] ? (
                      <p key={d} title={c[d]!.reason}>
                        {DIMENSION_LABELS[d]!.split(" ")[0]} {Math.round(c[d]!.credit * 100)}%
                      </p>
                    ) : null,
                  )}
                </TD>
              </TR>
            );
          })}
        </TBody>
      </Table>
    </Panel>
  );
}

function eventSummary(e: SimEvent): string {
  const p = e.payload as Record<string, unknown>;
  switch (e.type) {
    case "track_observation":
      return `${p.track_id} · ${label(SENSOR_LABELS, p.sensor as string)} · quality ${Number(p.quality).toFixed(2)}${p.class_hint ? ` · hint ${label(CLASSIFICATION_LABELS, p.class_hint as string)}` : ""}${p.beacon ? " · beacon" : ""}`;
    case "classification_submitted":
      return `${(p.track_ids as string[]).join(", ")} classified ${label(CLASSIFICATION_LABELS, p.classification as string)} (${label(CONFIDENCE_LABELS, p.confidence as string)})`;
    case "response_submitted":
      return `${(p.track_ids as string[]).join(", ")}: ${label(RESPONSE_LABELS, p.response as string)}`;
    case "sensor_confirmation":
      return `${p.track_id}: ${p.outcome === "hint_available" ? `confirmation hint ${label(CLASSIFICATION_LABELS, p.class_hint as string)} (${Number(p.quality).toFixed(2)})` : "no contact"}`;
    case "sensor_status":
      return `${label(SENSOR_LABELS, p.sensor as string)} ${p.status}`;
    case "environment_update":
      return `Visibility ${p.visibility_km} km`;
    case "exercise_message":
      return String(p.message);
    case "track_lost":
      return `${p.track_id} lost`;
    case "entity_spawned":
      return `${p.entity_id} appeared (${label(CLASSIFICATION_LABELS, p.entity_class as string)}, ${p.behavior}${p.cooperative ? ", cooperative" : ""})`;
    case "entity_exited":
      return `${p.entity_id} ${p.reason === "faded" ? "faded" : "left the area"}`;
    case "track_assigned":
      return `${p.track_id} assigned to ${p.entity_id}`;
    case "observation_missed":
      return `${p.entity_id} not detected by ${label(SENSOR_LABELS, p.sensor as string)} (${String(p.reason).replace("_", " ")})`;
    case "entity_state":
      return `${p.entity_id} at ${formatDistance(Number(p.range_m))}, ${p.alt_m} m altitude`;
    default:
      return (
        e.type.replace(/_/g, " ") +
        ((p as { reason?: string }).reason ? ` (${(p as { reason?: string }).reason})` : "")
      );
  }
}

const PAGE = 100;

export function TimelineSection({
  sessionId,
  trackIds,
  allowGroundTruth,
}: {
  sessionId: string;
  trackIds: string[];
  allowGroundTruth: boolean;
}) {
  const [category, setCategory] = useState("decisions");
  const [track, setTrack] = useState("");
  const [offset, setOffset] = useState(0);
  const st = useAsync(
    (sig) =>
      api.get<Page<SimEvent> & { events_purged_at?: string | null }>(
        `/sessions/${sessionId}/timeline${qs({ category, track_id: track, limit: PAGE, offset })}`,
        sig,
      ),
    [sessionId, category, track, offset],
  );
  return (
    <Panel>
      <PanelHeader
        title="Event timeline"
        description="Chronological record from the stored event log (simulation time). Replays do not depend on any live simulation state."
        actions={
          <div className="flex flex-wrap items-end gap-2">
            <Field label="Category" className="w-44">
              <Select
                value={category}
                onChange={(e) => {
                  setCategory(e.target.value);
                  setOffset(0);
                }}
              >
                <option value="decisions">Decisions and confirmations</option>
                <option value="exercise">Exercise and sensor status</option>
                <option value="observations">Synthetic observations</option>
                {allowGroundTruth ? <option value="ground_truth">Ground truth</option> : null}
                <option value="all">All events</option>
              </Select>
            </Field>
            <Field label="Track" className="w-32">
              <Select
                value={track}
                onChange={(e) => {
                  setTrack(e.target.value);
                  setOffset(0);
                }}
              >
                <option value="">All tracks</option>
                {trackIds.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </Select>
            </Field>
          </div>
        }
      />
      {st.loading ? (
        <LoadingState rows={6} />
      ) : st.error ? (
        <ErrorState error={st.error} onRetry={st.reload} />
      ) : st.data?.events_purged_at ? (
        <EmptyState title="Event log removed under the data-retention policy">
          The detailed event log was deleted on {formatDateTime(st.data.events_purged_at)}. The score, its
          explanation and the recorded digests are kept.
        </EmptyState>
      ) : !st.data?.items.length ? (
        <EmptyState title="No events in this category" />
      ) : (
        <>
          <Table>
            <THead>
              <TR>
                <TH>Time</TH>
                <TH>Visible at</TH>
                <TH>Event</TH>
                <TH>Detail</TH>
                <TH>Source</TH>
              </TR>
            </THead>
            <TBody>
              {st.data.items.map((e) => (
                <TR key={e.event_id}>
                  <TD className="tabular whitespace-nowrap text-xs">
                    {formatClock(e.t_ms)}.{String(Math.floor((e.t_ms % 1000) / 100))}
                  </TD>
                  <TD className="tabular whitespace-nowrap text-xs text-ink-subtle">
                    {e.available_at_ms !== e.t_ms ? formatClock(e.available_at_ms) : ""}
                  </TD>
                  <TD className="whitespace-nowrap text-xs">{e.type.replace(/_/g, " ")}</TD>
                  <TD className="text-xs">{eventSummary(e)}</TD>
                  <TD className="whitespace-nowrap text-xs text-ink-subtle">
                    {e.visibility === "ground_truth" ? "Ground truth" : e.origin} · {e.event_id}
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
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
  );
}

export function ErrorAnalysisSection({ result }: { result: ScoreResult }) {
  const errors = useMemo(() => result.errors ?? {}, [result.errors]);
  const chart = useMemo(() => {
    const cats = [
      ["incorrect_classifications", "Incorrect classifications"],
      ["missed_tracks", "Missed tracks"],
      ["inconsistent_decisions", "Inconsistent decisions"],
      ["overconfident", "Overconfident on weak evidence"],
      ["procedure_violations", "Procedural violations"],
    ] as const;
    return {
      grid: { left: 190, right: 30, top: 10, bottom: 24, containLabel: false },
      xAxis: {
        type: "value",
        minInterval: 1,
        name: "Count",
        nameLocation: "middle",
        nameGap: 22,
        ...axisStyle,
      },
      yAxis: { type: "category", inverse: true, data: cats.map((c) => c[1]), ...axisStyle },
      tooltip: { trigger: "item" },
      series: [
        {
          type: "bar",
          barWidth: 12,
          itemStyle: { color: "#9B2C2C" },
          data: cats.map((c) => (errors[c[0]] ?? []).length),
        },
      ],
    };
  }, [errors]);
  const practice = [
    ...DIMENSION_ORDER.filter(
      (d) => result.dimensions[d]?.applicable && (result.dimensions[d]?.score ?? 100) < 70,
    ).map((d) => DIMENSION_LABELS[d]!),
    ...result.objectives.filter((o) => o.status === "not_met").map((o) => o.description),
  ];
  const list = (key: string, render: (e: Record<string, unknown>) => string) => {
    const rows = errors[key] ?? [];
    return rows.length ? (
      <ul className="list-disc space-y-0.5 pl-5 text-sm">
        {rows.map((e, i) => (
          <li key={i}>{render(e)}</li>
        ))}
      </ul>
    ) : (
      <p className="text-sm text-ink-muted">None.</p>
    );
  };
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Panel className="lg:col-span-2">
        <PanelHeader title="Error summary" />
        <PanelBody>
          <EChart option={chart} height={200} ariaLabel="Count of errors by category" />
        </PanelBody>
      </Panel>
      <Panel>
        <PanelHeader title="Incorrect classifications" />
        <PanelBody>
          {list(
            "incorrect_classifications",
            (e) =>
              `${e.track_id}: classified ${label(CLASSIFICATION_LABELS, e.given as string)} (${label(CONFIDENCE_LABELS, e.confidence as string)}), was ${label(CLASSIFICATION_LABELS, e.true_class as string)}`,
          )}
        </PanelBody>
      </Panel>
      <Panel>
        <PanelHeader
          title="Missed observations"
          description="Tracks that were visible but never classified."
        />
        <PanelBody>
          {list(
            "missed_tracks",
            (e) =>
              `${e.track_id} (${label(CLASSIFICATION_LABELS, e.true_class as string)}), first visible at ${formatSeconds(e.first_available_s as number, 0)}`,
          )}
        </PanelBody>
      </Panel>
      <Panel>
        <PanelHeader
          title="Inconsistent decisions"
          description="Final response compared with the rubric decision tree."
        />
        <PanelBody>
          {list(
            "inconsistent_decisions",
            (e) =>
              `${e.track_id}: ${label(RESPONSE_LABELS, e.response as string, "no response")}; expected ${(e.expected as string[]).map((r) => label(RESPONSE_LABELS, r)).join(" or ")}`,
          )}
        </PanelBody>
      </Panel>
      <Panel>
        <PanelHeader title="Uncertainty and procedure" />
        <PanelBody className="space-y-3">
          {list(
            "overconfident",
            (e) =>
              `${e.track_id}: high confidence ${label(CLASSIFICATION_LABELS, e.given as string)} with evidence ${Number(e.evidence).toFixed(2)}`,
          )}
          {list(
            "procedure_violations",
            (e) => `${e.track_id} at ${formatSeconds(e.t_s as number)}: ${e.detail}`,
          )}
        </PanelBody>
      </Panel>
      <Panel className="lg:col-span-2">
        <PanelHeader title="Areas requiring further practice" />
        <PanelBody>
          {practice.length ? (
            <ul className="list-disc space-y-0.5 pl-5 text-sm">
              {practice.map((p) => (
                <li key={p}>{p}</li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-ink-muted">
              No dimension below 70% and every assessable objective was met.
            </p>
          )}
        </PanelBody>
      </Panel>
    </div>
  );
}
