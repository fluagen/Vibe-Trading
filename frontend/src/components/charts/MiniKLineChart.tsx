import { useMemo } from "react";
import type { OHLCSnapshotBar, SignalPoint } from "@/lib/api";

interface MiniKLineChartProps {
  bars: OHLCSnapshotBar[];
  signals: SignalPoint[];
  width?: number;
  height?: number;
}

export function MiniKLineChart({
  bars,
  signals,
  width = 200,
  height = 60,
}: MiniKLineChartProps) {
  const { candleShapes, signalDots } = useMemo(() => {
    if (!bars.length) return { candleShapes: [], signalDots: [] };

    const padding = { top: 4, bottom: 4, left: 2, right: 2 };
    const chartW = width - padding.left - padding.right;
    const chartH = height - padding.top - padding.bottom;
    const allPrices = bars.flatMap((b) => [b.high, b.low]);
    const maxP = Math.max(...allPrices);
    const minP = Math.min(...allPrices);
    const priceRange = maxP - minP || 1;
    const scaleY = (v: number) => padding.top + chartH - ((v - minP) / priceRange) * chartH;
    const shapes: { x: number; y1: number; y2: number; yHigh: number; yLow: number; isGreen: boolean }[] = [];
    bars.forEach((b, i) => {
      const x = padding.left + i * (chartW / bars.length);
      shapes.push({
        x, y1: Math.min(scaleY(b.open), scaleY(b.close)), y2: Math.max(scaleY(b.open), scaleY(b.close)),
        yHigh: scaleY(b.high), yLow: scaleY(b.low), isGreen: b.close >= b.open,
      });
    });

    const signalDates = new Map(signals.map((s) => [s.date, s.type]));
    const dots: { x: number; y: number; color: string }[] = [];
    bars.forEach((b, i) => {
      const stype = signalDates.get(b.date);
      if (!stype) return;
      dots.push({
        x: padding.left + i * (chartW / bars.length),
        y: scaleY(b.close),
        color: stype.startsWith("entry") ? "#22c55e" : "#ef4444",
      });
    });
    return { candleShapes: shapes, signalDots: dots };
  }, [bars, signals, width, height]);

  if (!bars.length) return <svg width={width} height={height}><text x={width / 2} y={height / 2} textAnchor="middle" fontSize={10} fill="#888">—</text></svg>;

  return (
    <svg width={width} height={height}>
      {candleShapes.map((c, i) => (
        <g key={i}>
          <line x1={c.x + 1} x2={c.x + 1} y1={c.yHigh} y2={c.yLow} stroke={c.isGreen ? "#22c55e" : "#ef4444"} strokeWidth={0.5} />
          <rect x={c.x} y={c.y1} width={2} height={Math.max(0.5, c.y2 - c.y1)} fill={c.isGreen ? "#22c55e" : "#ef4444"} />
        </g>
      ))}
      {signalDots.map((d, i) => (
        <circle key={`s${i}`} cx={d.x + 1} cy={d.y} r={2} fill={d.color} />
      ))}
    </svg>
  );
}
