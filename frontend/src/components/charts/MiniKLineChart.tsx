import { useMemo } from "react";
import type { OHLCSnapshotBar, SignalPoint } from "@/lib/api";

interface MiniKLineChartProps {
  bars: OHLCSnapshotBar[];
  signals: SignalPoint[];
  width?: number;
  height?: number;
  markerStyle?: "shape" | "bs";
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

// B/S marker colors
const BS_GRAY = "#6b7280";
const BS_BLUE = "#3b82f6";
const BS_ORANGE = "#f97316";
const BS_RED = "#ef4444";

interface BsStyle { letter: "B" | "S"; bg: string }

function bsStyle(sp: SignalPoint): BsStyle {
  if (sp.signal_value > 0) {
    if (sp.type === "entry_add") return { letter: "B", bg: BS_BLUE };
    if (sp.type === "take_profit") return { letter: "S", bg: BS_ORANGE };
    return { letter: "B", bg: BS_GRAY }; // entry (initial)
  }
  const reason = sp.exit_reason || "";
  if (reason.includes("止损")) return { letter: "S", bg: BS_RED };
  if (reason.includes("止盈") || reason.includes("MA") || reason.includes("R")) return { letter: "S", bg: BS_ORANGE };
  return { letter: "S", bg: BS_GRAY }; // 清仓 or generic exit
}

function Marker({ x, y, sz, t }: { x: number; y: number; sz: number; t: { c: string; s: string } }) {
  if (t.s === "tri-up") return <polygon points={`${x},${y - sz} ${x - sz},${y + 2} ${x + sz},${y + 2}`} fill={t.c} />;
  if (t.s === "tri-down") return <polygon points={`${x},${y + sz} ${x - sz},${y - 2} ${x + sz},${y - 2}`} fill={t.c} />;
  return <circle cx={x} cy={y} r={sz / 1.5} fill={t.c} />;
}

export function MiniKLineChart({ bars, signals, width = 200, height = 60, markerStyle = "shape", onClick }: MiniKLineChartProps) {
  const isBS = markerStyle === "bs";

  const { shapes, markers, bsMarkers } = useMemo(() => {
    if (!bars.length) return { shapes: [] as any[], markers: [] as any[], bsMarkers: [] as any[] };
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
    const markers: any[] = [];
    const bsMarkers: any[] = [];
    bars.forEach((b, i) => {
      const sp = sm.get(b.date);
      if (!sp) return;
      const cx = pad.l + i * (cw / bars.length);
      const cy = sy(b.close);
      const t = STYLE[sp.type] ?? { c: "#888", s: "circle" };
      const lbl = sp.entry_label || LAB[sp.type] || "";
      markers.push({ x: cx, y: cy, t, lbl });
      bsMarkers.push({ x: cx, y: cy, bs: bsStyle(sp) });
    });
    return { shapes, markers, bsMarkers };
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
      {isBS
        ? bsMarkers.map((m, i) => {
            const cx = m.x + Math.max(1, (width - 4) / bars.length / 2);
            const bx = cx - 5, by = m.y - 5, bw2 = 10, bh = 9;
            return (
              <g key={`bs${i}`}>
                <rect x={bx} y={by} width={bw2} height={bh} rx={1.5} fill={m.bs.bg} />
                <text x={cx} y={by + bh - 2} textAnchor="middle" fontSize={6.5} fill="#fff" fontWeight="bold">{m.bs.letter}</text>
              </g>
            );
          })
        : markers.map((m, i) => {
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
