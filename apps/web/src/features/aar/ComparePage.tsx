import { Link, useSearchParams } from "react-router-dom";

import { KeyValues, PageHeader, Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { Alert } from "@/components/ui/status";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import type { AttemptMeta } from "@/features/analytics/Competency";
import { api, qs } from "@/lib/api";
import { formatDateTime, formatPercent } from "@/lib/format";
import {
  CLASSIFICATION_LABELS,
  DIMENSION_LABELS,
  DIMENSION_ORDER,
  label,
  RESPONSE_LABELS,
  STATUS_LABELS,
} from "@/lib/labels";
import { useAsync } from "@/lib/useAsync";

interface Comparison {
  a: AttemptMeta;
  b: AttemptMeta;
  same: Record<string, boolean>;
  comparability: "identical" | "same_scenario" | "different_scenarios";
  note: string;
  overall: { a: number | null; b: number | null; delta: number | null };
  dimensions: Record<string, { a: number | null; b: number | null; delta: number | null }>;
  objectives: { id: string; description: string | null; a: string | null; b: string | null }[];
  errors: Record<string, { label: string; a: number; b: number }>;
  tracks: {
    track_id: string;
    true_class: string | null;
    a: {
      final_classification: string | null;
      final_confidence: string | null;
      final_response: string | null;
    };
    b: {
      final_classification: string | null;
      final_confidence: string | null;
      final_response: string | null;
    };
  }[];
}

const COMPARABILITY = {
  identical: { text: "Identical exercise", tone: "success" as const },
  same_scenario: { text: "Same scenario, different tracks", tone: "info" as const },
  different_scenarios: { text: "Different scenarios", tone: "warning" as const },
};

function signed(v: number | null): string {
  return v === null ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(1)}`;
}

function decision(d: Comparison["tracks"][number]["a"]): string {
  if (!d.final_classification && !d.final_response) return "No decision";
  return [
    d.final_classification ? label(CLASSIFICATION_LABELS, d.final_classification) : "Not classified",
    d.final_response ? label(RESPONSE_LABELS, d.final_response) : null,
  ]
    .filter(Boolean)
    .join(" · ");
}

export function ComparePage() {
  const [params] = useSearchParams();
  const a = params.get("a") ?? "";
  const b = params.get("b") ?? "";
  const st = useAsync((sig) => api.get<Comparison>(`/analytics/compare${qs({ a, b })}`, sig), [a, b]);
  if (!a || !b) return <EmptyState title="Choose two scored sessions to compare" />;
  if (st.loading) return <LoadingState rows={6} />;
  if (st.error || !st.data) return <ErrorState error={st.error} onRetry={st.reload} />;
  const c = st.data;
  const tag = COMPARABILITY[c.comparability];
  const attempt = (m: AttemptMeta, name: string) => (
    <Panel>
      <PanelHeader title={name} />
      <PanelBody>
        <KeyValues
          items={[
            ["Completed", formatDateTime(m.completed_at)],
            ["Scenario", `${m.scenario_key} v${m.scenario_version}`],
            ["Seed and level", `seed ${m.seed}, level ${m.difficulty_level}`],
            ["Overall", formatPercent(m.overall)],
            ["Scored with", `${m.rubric_version}, ${m.scoring_engine_version}`],
          ]}
        />
        <Link
          className="mt-2 inline-block text-sm text-brand hover:underline"
          to={`/sessions/${m.session_id}/result`}
        >
          Open after-action review
        </Link>
      </PanelBody>
    </Panel>
  );
  return (
    <>
      <PageHeader
        title="Compare attempts"
        description="Two scored sessions side by side, computed from their stored results."
      />
      <div className="space-y-4">
        <Alert tone={tag.tone === "warning" ? "warning" : "info"} title={tag.text}>
          {c.note}
        </Alert>
        <div className="grid gap-4 lg:grid-cols-2">
          {attempt(c.a, "Attempt A")}
          {attempt(c.b, "Attempt B")}
        </div>
        <Panel>
          <PanelHeader title="Scores" description="Change is B minus A, in percentage points." />
          <Table>
            <THead>
              <TR>
                <TH>Measure</TH>
                <TH>A</TH>
                <TH>B</TH>
                <TH>Change</TH>
              </TR>
            </THead>
            <TBody>
              <TR>
                <TD className="font-medium">Overall</TD>
                <TD className="tabular">{formatPercent(c.overall.a)}</TD>
                <TD className="tabular">{formatPercent(c.overall.b)}</TD>
                <TD className="tabular font-medium">{signed(c.overall.delta)}</TD>
              </TR>
              {DIMENSION_ORDER.map((d) => (
                <TR key={d}>
                  <TD>{DIMENSION_LABELS[d]}</TD>
                  <TD className="tabular">{formatPercent(c.dimensions[d]?.a)}</TD>
                  <TD className="tabular">{formatPercent(c.dimensions[d]?.b)}</TD>
                  <TD className="tabular">{signed(c.dimensions[d]?.delta ?? null)}</TD>
                </TR>
              ))}
            </TBody>
          </Table>
        </Panel>
        <div className="grid gap-4 lg:grid-cols-2">
          <Panel>
            <PanelHeader title="Learning objectives" />
            <Table>
              <THead>
                <TR>
                  <TH>Objective</TH>
                  <TH>A</TH>
                  <TH>B</TH>
                </TR>
              </THead>
              <TBody>
                {c.objectives.map((o) => (
                  <TR key={o.id}>
                    <TD className="text-sm">{o.description ?? o.id}</TD>
                    <TD className="text-xs">{label(STATUS_LABELS, o.a)}</TD>
                    <TD className="text-xs">{label(STATUS_LABELS, o.b)}</TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          </Panel>
          <Panel>
            <PanelHeader title="Errors" />
            <Table>
              <THead>
                <TR>
                  <TH>Type</TH>
                  <TH>A</TH>
                  <TH>B</TH>
                </TR>
              </THead>
              <TBody>
                {Object.entries(c.errors).map(([k, e]) => (
                  <TR key={k}>
                    <TD className="text-sm">{e.label}</TD>
                    <TD className="tabular">{e.a}</TD>
                    <TD className="tabular">{e.b}</TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          </Panel>
        </div>
        {c.tracks.length ? (
          <Panel>
            <PanelHeader
              title="Track by track"
              description="Shown only for identical exercises, where both attempts faced the same tracks."
            />
            <Table>
              <THead>
                <TR>
                  <TH>Track</TH>
                  <TH>Ground truth</TH>
                  <TH>A</TH>
                  <TH>B</TH>
                </TR>
              </THead>
              <TBody>
                {c.tracks.map((t) => (
                  <TR key={t.track_id}>
                    <TD className="font-medium">{t.track_id}</TD>
                    <TD className="text-xs">{label(CLASSIFICATION_LABELS, t.true_class)}</TD>
                    <TD className="text-xs">{decision(t.a)}</TD>
                    <TD className="text-xs">{decision(t.b)}</TD>
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
