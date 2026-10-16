import { Panel, PanelHeader } from "@/components/ui/panel";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import { api } from "@/lib/api";
import { formatPercent } from "@/lib/format";
import { DIMENSION_LABELS } from "@/lib/labels";
import { useAsync } from "@/lib/useAsync";

interface UnitRow {
  unit: string | null;
  trainees: number;
  trainees_with_sessions: number;
  sessions: number;
  mean_overall: number | null;
  pass_rate: number | null;
  dimensions: Record<string, number | null>;
}

/** Unit-level summary. `query` carries the page's scenario and date filters. */
export function UnitsPanel({ query }: { query: string }) {
  const st = useAsync(
    (sig) => api.get<{ units: UnitRow[]; note: string }>(`/analytics/units${query}`, sig),
    [query],
  );
  return (
    <Panel>
      <PanelHeader
        title="Units"
        description={
          st.data?.note ??
          "Assign trainees to units under Administration, Users. Means over completed, scored sessions."
        }
      />
      {st.loading ? (
        <LoadingState rows={3} />
      ) : st.error ? (
        <ErrorState error={st.error} onRetry={st.reload} />
      ) : !st.data?.units.length ? (
        <EmptyState title="No trainees yet" />
      ) : (
        <Table>
          <THead>
            <TR>
              <TH>Unit</TH>
              <TH>Trainees</TH>
              <TH>Sessions</TH>
              <TH>Mean overall</TH>
              <TH>Passed</TH>
              <TH>{DIMENSION_LABELS.recognition}</TH>
              <TH>{DIMENSION_LABELS.timing}</TH>
              <TH>{DIMENSION_LABELS.consistency}</TH>
            </TR>
          </THead>
          <TBody>
            {st.data.units.map((u) => (
              <TR key={u.unit ?? "(none)"}>
                <TD className="font-medium">{u.unit ?? "No unit"}</TD>
                <TD className="tabular">
                  {u.trainees_with_sessions} of {u.trainees} active
                </TD>
                <TD className="tabular">{u.sessions}</TD>
                <TD className="tabular">{formatPercent(u.mean_overall)}</TD>
                <TD className="tabular">{formatPercent(u.pass_rate)}</TD>
                <TD className="tabular text-xs">{formatPercent(u.dimensions.recognition)}</TD>
                <TD className="tabular text-xs">{formatPercent(u.dimensions.timing)}</TD>
                <TD className="tabular text-xs">{formatPercent(u.dimensions.consistency)}</TD>
              </TR>
            ))}
          </TBody>
        </Table>
      )}
    </Panel>
  );
}
