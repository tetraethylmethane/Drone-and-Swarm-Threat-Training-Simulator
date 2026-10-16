import { PageHeader, Panel, PanelHeader } from "@/components/ui/panel";
import { Tag } from "@/components/ui/status";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import { CompetencyPanel } from "@/features/analytics/Competency";
import { ProgressSection } from "@/features/analytics/ProgressCharts";
import { api } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import type { DifficultyAdjustment, Page, ProgressPoint, SessionState } from "@/lib/types";
import { useAsync } from "@/lib/useAsync";

import { SessionTable } from "./TraineePages";

export function HistoryPage() {
  const progress = useAsync((sig) => api.get<{ points: ProgressPoint[] }>("/analytics/progress", sig), []);
  const sessions = useAsync((sig) => api.get<Page<SessionState>>("/sessions?limit=100", sig), []);
  const difficulty = useAsync(
    (sig) => api.get<{ items: DifficultyAdjustment[] }>("/analytics/difficulty", sig),
    [],
  );
  return (
    <>
      <PageHeader
        title="My progress"
        description="Your scored sessions over time, from your recorded results only."
      />
      <div className="space-y-4">
        {progress.loading ? (
          <LoadingState rows={5} />
        ) : progress.error ? (
          <ErrorState error={progress.error} onRetry={progress.reload} />
        ) : (
          <ProgressSection points={progress.data!.points} showTrainee={false} />
        )}
        <CompetencyPanel />
        <Panel>
          <PanelHeader
            title="Difficulty adjustments"
            description="Rules-based recommendations recorded after each adaptive session, with the reason."
          />
          {difficulty.loading ? (
            <LoadingState />
          ) : difficulty.error ? (
            <ErrorState error={difficulty.error} onRetry={difficulty.reload} />
          ) : !difficulty.data?.items.length ? (
            <EmptyState title="No adjustments yet">
              Adjustments are recorded when you complete adaptive exercises.
            </EmptyState>
          ) : (
            <Table>
              <THead>
                <TR>
                  <TH>When</TH>
                  <TH>Scenario</TH>
                  <TH>Change</TH>
                  <TH>Reason</TH>
                </TR>
              </THead>
              <TBody>
                {difficulty.data.items.map((d) => (
                  <TR key={d.id}>
                    <TD className="whitespace-nowrap text-xs">{formatDateTime(d.created_at)}</TD>
                    <TD className="text-xs">{d.scenario_key}</TD>
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
                    <TD className="text-xs">{d.reason}</TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          )}
        </Panel>
        <Panel>
          <PanelHeader title="All attempts" />
          {sessions.loading ? (
            <LoadingState />
          ) : sessions.error ? (
            <ErrorState error={sessions.error} onRetry={sessions.reload} />
          ) : !sessions.data?.items.length ? (
            <EmptyState title="No attempts yet" />
          ) : (
            <SessionTable sessions={sessions.data.items} />
          )}
        </Panel>
      </div>
    </>
  );
}
