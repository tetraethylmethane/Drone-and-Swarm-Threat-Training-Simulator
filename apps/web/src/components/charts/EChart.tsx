import { BarChart, LineChart, ScatterChart } from "echarts/charts";
import {
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  MarkLineComponent,
  TooltipComponent,
} from "echarts/components";
import * as echarts from "echarts/core";
import { SVGRenderer } from "echarts/renderers";
import { useEffect, useRef } from "react";

echarts.use([
  LineChart,
  BarChart,
  ScatterChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  DataZoomComponent,
  MarkLineComponent,
  SVGRenderer,
]);

/** Restrained chart palette derived from the design tokens. */
export const CHART_COLORS = ["#1F4D3A", "#2D4F73", "#8A5A12", "#7A2E5C", "#5D7A3A", "#5B605C", "#9B2C2C"];

export const baseOption = {
  color: CHART_COLORS,
  textStyle: { fontFamily: "Inter, system-ui, sans-serif", color: "#545A56", fontSize: 11 },
  grid: { left: 48, right: 16, top: 28, bottom: 36, containLabel: true },
  tooltip: {
    trigger: "axis",
    backgroundColor: "#FFFFFF",
    borderColor: "#DCD9D1",
    textStyle: { color: "#1B1F1D", fontSize: 12 },
  },
  legend: { top: 0, left: 0, itemWidth: 12, itemHeight: 8, textStyle: { fontSize: 11 } },
};

export const axisStyle = {
  axisLine: { lineStyle: { color: "#C6C2B8" } },
  axisTick: { show: false },
  splitLine: { lineStyle: { color: "#EFEEE9" } },
  axisLabel: { color: "#545A56", fontSize: 11 },
  nameTextStyle: { color: "#545A56", fontSize: 11 },
};

interface Props {
  option: echarts.EChartsCoreOption;
  height?: number;
  ariaLabel: string;
}

/** Thin ECharts wrapper (tree-shaken, SVG renderer for crisp text and print). */
export function EChart({ option, height = 280, ariaLabel }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const chart = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    if (!ref.current) return;
    chart.current = echarts.init(ref.current, undefined, { renderer: "svg" });
    const ro = new ResizeObserver(() => chart.current?.resize());
    ro.observe(ref.current);
    return () => {
      ro.disconnect();
      chart.current?.dispose();
      chart.current = null;
    };
  }, []);

  useEffect(() => {
    chart.current?.setOption({ ...baseOption, ...option, aria: { enabled: true } }, true);
  }, [option]);

  return <div ref={ref} role="img" aria-label={ariaLabel} style={{ height, width: "100%" }} />;
}
