import { useMemo } from "react";

import { axisStyle, EChart } from "@/components/charts/EChart";
import { Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { EmptyState } from "@/components/ui/states";
import { formatDateTime } from "@/lib/format";
import { DIMENSION_LABELS, DIMENSION_ORDER } from "@/lib/labels";
import type { ProgressPoint } from "@/lib/types";

/** Pad a time axis so the first and last sessions are not drawn on the plot edge. */
const timeAxis = {
  type: "time",
  min: (v: { min: number; max: number }) => v.min - Math.max((v.max - v.min) * 0.05, 5 * 60_000),
  max: (v: { min: number; max: number }) => v.max + Math.max((v.max - v.min) * 0.05, 5 * 60_000),
  ...axisStyle,
};
const yName = { nameLocation: "middle", nameGap: 38, nameRotate: 90 } as const;

/** Line chart of overall score per completed session, one series per trainee. Built only from persisted results. */
export function OverallTrendChart({ points }: { points: ProgressPoint[] }) {
  const option = useMemo(() => {
    const byTrainee = new Map<string, ProgressPoint[]>();
    for (const p of points)
      byTrainee.set(p.trainee.display_name, [...(byTrainee.get(p.trainee.display_name) ?? []), p]);
    return {
      tooltip: {
        trigger: "item",
        formatter: (params: { data: [string, number, ProgressPoint] }) => {
          const p = params.data[2];
          return `${p.trainee.display_name}<br/>${p.scenario_name} v${p.scenario_version}<br/>${formatDateTime(p.completed_at)}<br/>Overall ${p.overall.toFixed(1)}% · difficulty ${p.difficulty_level}`;
        },
      },
      grid: { left: 56, right: 24, top: 36, bottom: 28, containLabel: true },
      xAxis: timeAxis,
      yAxis: { type: "value", name: "Overall score (%)", min: 0, max: 100, ...yName, ...axisStyle },
      series: [...byTrainee.entries()].map(([name, pts]) => ({
        name,
        type: "line",
        showSymbol: true,
        symbolSize: 7,
        data: pts.map((p) => [p.completed_at, p.overall, p]),
        markLine:
          byTrainee.size === 1
            ? {
                silent: true,
                symbol: "none",
                lineStyle: { type: "dashed", color: "#C6C2B8" },
                label: { formatter: "Pass mark 70%", fontSize: 10 },
                data: [{ yAxis: 70 }],
              }
            : undefined,
      })),
    };
  }, [points]);
  return <EChart option={option} height={300} ariaLabel="Overall score by completed session over time" />;
}

/** Mean score per dimension across the selected sessions (non-applicable dimensions excluded from each mean). */
export function DimensionMeansChart({ points }: { points: ProgressPoint[] }) {
  const option = useMemo(() => {
    const means = DIMENSION_ORDER.map((d) => {
      const vals = points.map((p) => p.dimensions[d]).filter((v): v is number => typeof v === "number");
      return { d, mean: vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null, n: vals.length };
    });
    return {
      grid: { left: 150, right: 40, top: 10, bottom: 44, containLabel: false },
      tooltip: {
        trigger: "item",
        formatter: (p: { name: string; value: number; dataIndex: number }) =>
          `${p.name}<br/>Mean ${p.value.toFixed(1)}% over ${means[p.dataIndex]!.n} session(s)`,
      },
      xAxis: {
        type: "value",
        min: 0,
        max: 100,
        name: "Mean score (%)",
        nameLocation: "middle",
        nameGap: 26,
        ...axisStyle,
      },
      yAxis: { type: "category", data: means.map((m) => DIMENSION_LABELS[m.d]), inverse: true, ...axisStyle },
      series: [
        {
          type: "bar",
          barWidth: 12,
          data: means.map((m) => m.mean ?? 0),
          itemStyle: { color: "#1F4D3A" },
          label: {
            show: true,
            position: "right",
            formatter: (p: { dataIndex: number }) =>
              means[p.dataIndex]!.mean === null ? "n/a" : `${means[p.dataIndex]!.mean!.toFixed(0)}%`,
            fontSize: 10,
          },
        },
      ],
    };
  }, [points]);
  return <EChart option={option} height={230} ariaLabel="Mean score per assessment dimension" />;
}

export function DifficultyChart({ points }: { points: ProgressPoint[] }) {
  const option = useMemo(
    () => ({
      grid: { left: 56, right: 24, top: 12, bottom: 28, containLabel: true },
      legend: { show: false },
      xAxis: timeAxis,
      yAxis: { type: "value", name: "Difficulty level", min: 1, max: 5, interval: 1, ...yName, ...axisStyle },
      tooltip: { trigger: "axis" },
      series: [
        {
          type: "line",
          step: "end",
          name: "Difficulty",
          data: points.map((p) => [p.completed_at, p.difficulty_level]),
        },
      ],
    }),
    [points],
  );
  return <EChart option={option} height={200} ariaLabel="Difficulty level by session" />;
}

export function ProgressSection({ points, showTrainee }: { points: ProgressPoint[]; showTrainee: boolean }) {
  if (!points.length) {
    return (
      <Panel>
        <EmptyState title="No completed sessions match these filters">
          Charts appear once exercises have been completed and scored. No sample or estimated data is shown.
        </EmptyState>
      </Panel>
    );
  }
  return (
    <div className="grid gap-4 xl:grid-cols-2">
      <Panel className="xl:col-span-2">
        <PanelHeader
          title="Overall score over time"
          description={`${points.length} scored session(s). Overall is the rubric-weighted mean of applicable dimensions (0–100%).`}
        />
        <PanelBody>
          <OverallTrendChart points={points} />
        </PanelBody>
      </Panel>
      <Panel>
        <PanelHeader
          title="Dimension averages"
          description="Not-applicable dimensions are excluded from each average."
        />
        <PanelBody>
          <DimensionMeansChart points={points} />
        </PanelBody>
      </Panel>
      <Panel>
        <PanelHeader
          title={showTrainee ? "Difficulty levels (all selected)" : "Difficulty level"}
          description="Levels 1–5; 3 runs the scenario as authored."
        />
        <PanelBody>
          <DifficultyChart points={points} />
        </PanelBody>
      </Panel>
    </div>
  );
}
