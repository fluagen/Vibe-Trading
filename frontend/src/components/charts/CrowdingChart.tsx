import { useEffect, useRef } from "react";
import * as echarts from "echarts";
import { getChartTheme } from "@/lib/chart-theme";
import type { SectorDetailPoint } from "@/lib/api";

interface Props {
  data: SectorDetailPoint[];
  boardName: string;
  height?: number;
}

export function CrowdingChart({ data, boardName, height = 400 }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    const chart = echarts.init(containerRef.current);
    chartRef.current = chart;
    const onResize = () => chart.resize();
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("resize", onResize);
      chart.dispose();
    };
  }, []);

  useEffect(() => {
    if (!chartRef.current || !data.length) return;
    const t = getChartTheme();

    chartRef.current.setOption(
      {
        tooltip: {
          trigger: "axis",
          backgroundColor: t.tooltipBg,
          borderColor: t.tooltipBorder,
          textStyle: { color: t.tooltipText, fontSize: 12 },
        },
        legend: {
          data: ["拥挤度比率", "主力净流入"],
          textStyle: { color: t.textColor },
          top: 0,
        },
        grid: { top: 40, right: 60, bottom: 30, left: 60 },
        xAxis: {
          type: "category",
          data: data.map((d) => d.date.slice(5)),
          axisLabel: { color: t.textColor, fontSize: 11 },
          axisLine: { lineStyle: { color: t.axisColor } },
        },
        yAxis: [
          {
            type: "value",
            name: "拥挤度比率 (%)",
            nameTextStyle: { color: t.textColor, fontSize: 11 },
            axisLabel: { color: t.textColor, formatter: "{value}%" },
            splitLine: { lineStyle: { color: t.gridColor } },
          },
          {
            type: "value",
            name: "净流入 (亿)",
            nameTextStyle: { color: t.textColor, fontSize: 11 },
            axisLabel: { color: t.textColor },
            splitLine: { show: false },
          },
        ],
        series: [
          {
            name: "拥挤度比率",
            type: "line",
            data: data.map((d) => d.crowding_ratio),
            smooth: true,
            lineStyle: { color: t.warningColor, width: 2 },
            itemStyle: { color: t.warningColor },
            symbol: "circle",
            symbolSize: 4,
            markLine: {
              silent: true,
              symbol: "none",
              lineStyle: { type: "dashed", width: 1 },
              label: { fontSize: 10, color: t.textColor },
              data: [
                { yAxis: 10, name: "10%", lineStyle: { color: "#f59e0b" } },
                { yAxis: 16, name: "16%", lineStyle: { color: "#ef4444" } },
              ],
            },
          },
          {
            name: "主力净流入",
            type: "bar",
            yAxisIndex: 1,
            data: data.map((d) => d.main_net_inflow_billion),
            itemStyle: {
              color: (params: { value: number }) =>
                (params.value ?? 0) >= 0 ? "#ef4444" : "#22c55e",
            },
            barMaxWidth: 20,
          },
        ],
      },
      { notMerge: true }
    );
  }, [data]);

  return (
    <div className="w-full">
      <h3 className="text-sm font-medium mb-2 text-center">
        {boardName} — 拥挤度 & 资金流趋势
      </h3>
      <div ref={containerRef} style={{ width: "100%", height }} />
    </div>
  );
}
