import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/overlay";
import { KeyValues, Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { Alert } from "@/components/ui/status";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import { api, download, qs } from "@/lib/api";
import { formatDate, formatPercent } from "@/lib/format";
import { errorMessage, useAsync } from "@/lib/useAsync";

interface Attempt {
  session_id: string;
  overall: number | null;
  difficulty_level: number;
  completed_at: string | null;
}

interface GainPair {
  trainee: { id: string; display_name: string };
  scenario_key: string;
  sessions: number;
  first: Attempt;
  latest: Attempt;
  gain: number;
  difficulty_changed: boolean;
}

interface Gains {
  pairs: GainPair[];
  summary: {
    pairs: number;
    mean_gain?: number;
    sd_gain?: number;
    ci95?: [number, number];
    effect_size_dz?: number;
    improved?: number;
    declined?: number;
    sign_test_p?: number;
    difficulty_changed?: number;
  };
  interpretation: string;
}

function signed(v: number): string {
  return `${v > 0 ? "+" : ""}${v.toFixed(1)}`;
}

export function LearningGainsPanel({
  traineeId,
  scenarioKey,
  canExport,
}: {
  traineeId: string;
  scenarioKey: string;
  canExport: boolean;
}) {
  const [sameDifficulty, setSameDifficulty] = useState(false);
  const query = qs({
    trainee_id: traineeId,
    scenario_key: scenarioKey,
    same_difficulty_only: sameDifficulty,
  });
  const st = useAsync((sig) => api.get<Gains>(`/analytics/learning-gains${query}`, sig), [query]);
  const [exportError, setExportError] = useState<string | null>(null);
  const s = st.data?.summary;

  return (
    <Panel>
      <PanelHeader
        title="Change between first and latest attempt"
        description="Per trainee and scenario, from scored sessions only."
        actions={
          canExport ? (
            <Button
              variant="secondary"
              size="sm"
              onClick={async () => {
                setExportError(null);
                try {
                  await download(
                    `/reports/study.csv${qs({ scenario_key: scenarioKey })}`,
                    "drikr-study-dataset.csv",
                  );
                } catch (err) {
                  setExportError(errorMessage(err));
                }
              }}
            >
              Export pseudonymised dataset
            </Button>
          ) : null
        }
      />
      <PanelBody className="space-y-4">
        <Checkbox
          id="same-difficulty"
          checked={sameDifficulty}
          onCheckedChange={setSameDifficulty}
          label="Only compare attempts at the same difficulty level"
        />
        {exportError ? <Alert tone="danger">{exportError}</Alert> : null}
        {st.loading ? (
          <LoadingState rows={3} />
        ) : st.error || !st.data ? (
          <ErrorState error={st.error} onRetry={st.reload} />
        ) : !st.data.pairs.length ? (
          <EmptyState title="No repeated attempts yet">
            A trainee needs at least two scored sessions of the same scenario.
          </EmptyState>
        ) : (
          <>
            <Alert tone="info" title="How to read this">
              {st.data.interpretation}
            </Alert>
            {s && s.mean_gain !== undefined ? (
              <KeyValues
                items={[
                  ["Pairs compared", String(s.pairs)],
                  [
                    "Mean change",
                    `${signed(s.mean_gain)} points (95% bootstrap interval ${signed(s.ci95?.[0] ?? 0)} to ${signed(s.ci95?.[1] ?? 0)})`,
                  ],
                  ["Improved / declined", `${s.improved ?? 0} / ${s.declined ?? 0}`],
                  ["Paired effect size (dz)", s.effect_size_dz?.toFixed(2) ?? "—"],
                  ["Sign test p", s.sign_test_p?.toFixed(3) ?? "—"],
                  ["Pairs with a difficulty change", String(s.difficulty_changed ?? 0)],
                ]}
              />
            ) : (
              <p className="text-sm text-ink-muted">At least two pairs are needed for cohort statistics.</p>
            )}
            <Table>
              <THead>
                <TR>
                  <TH>Trainee</TH>
                  <TH>Scenario</TH>
                  <TH>Sessions</TH>
                  <TH>First</TH>
                  <TH>Latest</TH>
                  <TH>Change</TH>
                </TR>
              </THead>
              <TBody>
                {st.data.pairs.map((p) => (
                  <TR key={`${p.trainee.id}-${p.scenario_key}`}>
                    <TD>{p.trainee.display_name}</TD>
                    <TD className="text-xs">{p.scenario_key}</TD>
                    <TD className="tabular">{p.sessions}</TD>
                    <TD className="tabular text-xs">
                      {formatPercent(p.first.overall)} · level {p.first.difficulty_level} ·{" "}
                      {formatDate(p.first.completed_at)}
                    </TD>
                    <TD className="tabular text-xs">
                      {formatPercent(p.latest.overall)} · level {p.latest.difficulty_level} ·{" "}
                      {formatDate(p.latest.completed_at)}
                    </TD>
                    <TD className="tabular font-medium">{signed(p.gain)}</TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          </>
        )}
      </PanelBody>
    </Panel>
  );
}
