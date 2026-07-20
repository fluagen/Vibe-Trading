import { useMemo } from "react";
import type { OHLCSnapshotBar, SignalPoint } from "@/lib/api";

interface MiniKLineChartProps {
  bars: OHLCSnapshotBar[];
  signals: SignalPoint[];
  width?: number;
  height?: number;
  onClick?: () => void;
}

const UP = "#ef4444";    // red = up (Chinese convention)
const DN = "#22c55e";    // green = down

const STYLE: Record<string, { c: string; s: string }> = {
  entry_trial: { c: UP, s: "tri-up" }, entry_confirm: { c: UP, s: "tri-up" },
  entry_full: { c: UP, s: "tri-up" }, entry: { c: UP, s: "tri-up" },
  take_profit: { c: "#f97316", s: "circle" }, exit: { c: "#3b82f6", s: "tri-down" },
};
const LAB: Record<string, string> = { entry_trial: "入", entry_confirm: "加", take_profit: "盈", exit: "出" };

function Marker({ x, y, sz, t }: { x: number; y: number; sz: number; t: { c: string; s: string } }) {
  if (t.s === "tri-up") return <polygon points={`${x},${y - sz} ${x - sz},${y + 2} ${x + sz},${y + 2}`} fill={t.c} />;
  if (t.s === "tri-down") return <polygon points={`${x},${y + sz} ${x - sz},${y - 2} ${x + sz},${y - 2}`} fill={t.c} />;
  return <circle cx={x} cy={y} r={sz / 1.5} fill={t.c} />;
}

export function MiniKLineChart({ bars, signals, width = 200, height = 60, onClick }: MiniKLineChartProps) {
  const { shapes, markers } = useMemo(() => {
    if (!bars.length) return { shapes: [] as any[], markers: [] as any[] };
    const pad = { t: 10, b: 4, l: 2, r: 2 };
    const cw = width - pad.l - pad.r, ch = height - pad.t - pad.b;
    const maxP = Math.max(...bars.flatMap(b => [b.high, b.low]));
    const minP = Math.min(...bars.flatMap(b => [b.high, b.low]));
    const range = maxP - minP || 1;
    const sy = (v: number) => pad.t + ch - ((v - minP) / range) * ch;
    const bw = Math.max(1, cw / bars.length - 0.5);
    const shapes = bars.map((b, i) => {
      const x = pad.l + i * (cw / bars.length);
      return { x, y1: Math.min(sy(b.open), sy(b.close)), y2: Math.max(sy(b.open), sy(b.close)),
        yH: sy(b.high), yL: sy(b.low), up: b.close >= b.open, bw };
    });
    const sm = new Map(signals.map(s => [s.date, s]));
    const markers = bars.flatMap((b, i) => {
      const sp = sm.get(b.date);
      if (!sp) return [];
      const t = STYLE[sp.type] ?? { c: "#888", s: "circle" };
      const lbl = sp.entry_label || LAB[sp.type] || "";
      return [{ x: pad.l + i * (cw / bars.length), y: sy(b.close), t, lbl }];
    });
    return { shapes, markers };
  }, [bars, signals, width, height]);

  if (!bars.length) return <svg width={width} height={height}><text x={width/2} y={height/2} textAnchor="middle" fontSize={10} fill="#888">—</text></svg>;

  const svg = (
    <svg width={width} height={height}>
      {shapes.map((c, i) => (
        <g key={i}>
          <line x1={c.x + c.bw / 2} x2={c.x + c.bw / 2} y1={c.yH} y2={c.yL} stroke={c.up ? UP : DN} strokeWidth={0.5} />
          <rect x={c.x} y={c.y1} width={c.bw} height={Math.max(0.5, c.y2 - c.y1)} fill={c.up ? UP : DN} />
        </g>
      ))}
      {markers.map((m, i) => {
        const cx = m.x + Math.max(1, (width - 4) / bars.length / 2);
        return (
          <g key={`s${i}`}>
            <Marker x={cx} y={m.y} sz={4} t={m.t} />
            {m.lbl && <text x={cx} y={m.y - 6} textAnchor="middle" fontSize={6} fill={m.t.c} fontWeight="bold">{m.lbl}</text>}
          </g>
        );
      })}
    </svg>
  );

  if (onClick) return <button onClick={onClick} className="inline-block rounded hover:opacity-80 transition-opacity" title="点击放大">{svg}</button>;
  return svg;
}
