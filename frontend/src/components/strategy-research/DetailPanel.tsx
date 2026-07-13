import { useState } from "react";
import { X, Maximize2, Minimize2 } from "lucide-react";
import type { BacktestDetailItem } from "@/lib/api";
import { MiniKLineChart } from "@/components/charts/MiniKLineChart";

interface DetailPanelProps { data: BacktestDetailItem; onClose: () => void; }

const STATE_LABELS: Record<string, string> = {
  no_structure: "无结构", forming: "形成中", up_phase: "上涨",
  pullback: "回调", pullback_end: "回调结束", breakdown: "崩坏",
};
const STATE_COLORS: Record<string, string> = {
  no_structure: "bg-slate-500", forming: "bg-amber-500", up_phase: "bg-emerald-500",
  pullback: "bg-sky-500", pullback_end: "bg-teal-500", breakdown: "bg-red-500",
};

function MetricCard({ label, value, sub, hl }: {
  label: string; value: string; sub?: string; hl?: "green" | "red" | "amber";
}) {
  const c = hl === "green" ? "text-emerald-500" : hl === "red" ? "text-red-500" : hl === "amber" ? "text-amber-500" : "text-foreground";
  return (
    <div className="rounded-lg border border-border/60 bg-card/60 p-2.5 text-center">
      <div className="text-[10px] text-muted-foreground uppercase tracking-wider mb-1">{label}</div>
      <div className={`text-sm font-bold font-mono tabular-nums ${c}`}>{value}</div>
      {sub && <div className="text-[10px] mt-0.5 text-muted-foreground">{sub}</div>}
    </div>
  );
}

function signalReason(sig: { type: string; description?: string }): string {
  if (sig.description) {
    const i = sig.description.indexOf(",");
    return i > 0 ? sig.description.slice(0, i) : sig.description;
  }
  if (sig.type === "entry_trial") return "止跌K";
  if (sig.type === "entry_confirm") return "证伪K";
  if (sig.type === "take_profit") return "止盈";
  if (sig.type === "exit") return "离场";
  return "";
}

function signalAction(sig: { type: string; signal_value: number }): string {
  if (sig.type === "entry_trial") return `入场(${sig.signal_value.toFixed(2)})`;
  if (sig.type === "entry_confirm") return `加仓(${sig.signal_value.toFixed(2)})`;
  if (sig.type === "take_profit") return `止盈(x${sig.signal_value.toFixed(2)})`;
  if (sig.type === "exit") return "退出(-1.0)";
  return sig.type;
}

export function DetailPanel({ data, onClose }: DetailPanelProps) {
  const [chartExpanded, setChartExpanded] = useState(false);
  const stateColor = STATE_COLORS[data.final_state] || "bg-slate-500";
  const winHl = data.win_rate >= 0.5 ? "green" as const : data.win_rate > 0 ? "amber" as const : "red" as const;
  const retHl = data.cumulative_return >= 0 ? "red" as const : "green" as const;
  const hasTrades = data.trades && data.trades.length > 0;
  const hasChart = data.ohlcv_snapshot && data.ohlcv_snapshot.length > 0;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-baseline gap-2">
          <span className="font-mono text-sm font-semibold">{data.code}</span>
          {data.name && <span className="text-xs text-muted-foreground">{data.name}</span>}
          <span className={`inline-flex items-center rounded px-2 py-0.5 text-[10px] font-medium text-white ${stateColor}`}>
            {STATE_LABELS[data.final_state] || data.final_state}
          </span>
        </div>
        <button onClick={onClose} className="rounded p-1 text-muted-foreground hover:text-foreground"><X size={14} /></button>
      </div>

      <div className="grid grid-cols-4 gap-2">
        <MetricCard label="交易" value={`${data.trade_count}`} sub={`${data.win_count}胜${data.loss_count}负`} />
        <MetricCard label="胜率" value={`${(data.win_rate * 100).toFixed(0)}%`} hl={winHl} />
        <MetricCard label="累计收益" value={`${data.cumulative_return >= 0 ? "+" : ""}${(data.cumulative_return * 100).toFixed(2)}%`} hl={retHl} />
        <MetricCard label="最大回撤" value={`${(data.max_drawdown * 100).toFixed(2)}%`} />
      </div>

      <div className="flex items-center gap-3 text-[11px] text-muted-foreground">
        <span>年化 {(data.annual_return * 100).toFixed(1)}%</span>
        <span>Sharpe {data.sharpe?.toFixed(2) || "—"}</span>
        <span className="text-red-500">止跌K {data.bsk_count}</span>
        <span className="text-red-500">证伪K {data.ck_count}</span>
      </div>

      {hasTrades && (
        <div className="rounded-lg border border-border overflow-hidden">
          <div className="px-3 py-2 bg-muted/20">
            <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">
              交易明细（{data.trades!.length} 笔）
            </span>
          </div>
          <div className="divide-y divide-border/50">
            {data.trades!.map((trade) => {
              const ds = trade.signals;
              const first = ds[0]?.date.slice(5) ?? "";
              const last = ds[ds.length - 1]?.date.slice(5) ?? "";
              return (
                <div key={trade.trade_index} className="px-3 py-2">
                  <div className="flex items-center gap-2 mb-1.5">
                    <span className="text-[11px] font-mono font-semibold">#{trade.trade_index}</span>
                    <span className="text-[11px] text-muted-foreground">{first} → {last}</span>
                    <span className={`text-xs font-bold font-mono ${trade.is_win ? "text-red-500" : "text-emerald-500"}`}>
                      {trade.is_win ? "+" : ""}{(trade.return_pct * 100).toFixed(1)}%
                    </span>
                    <span>{trade.is_win ? "✅" : "❌"}</span>
                  </div>
                  <div className="space-y-0.5 ml-1">
                    {trade.signals.map((sig, si) => {
                      const isExit = sig.type === "exit";
                      const isTP = sig.type === "take_profit";
                      const color = isExit ? "text-blue-500" : isTP ? "text-orange-500" : "text-red-500";
                      return (
                        <div key={si} className="flex items-center gap-2 text-[11px]">
                          <span className="text-muted-foreground font-mono w-12">{sig.date.slice(5)}</span>
                          <span className={color}>{signalAction(sig)}</span>
                          <span className="text-foreground font-mono w-14 text-right">{sig.price.toFixed(2)}</span>
                          <span className="text-muted-foreground">{signalReason(sig)}</span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>
          {hasChart && (
            <div className="border-t border-border/50 px-3 py-2">
              <div className="flex items-center justify-between mb-1">
                <span className="text-[10px] text-muted-foreground uppercase tracking-wider">K线 + 信号标记</span>
                <button onClick={() => setChartExpanded(!chartExpanded)} className="text-muted-foreground hover:text-foreground">
                  {chartExpanded ? <Minimize2 size={12} /> : <Maximize2 size={12} />}
                </button>
              </div>
              <div className="flex justify-center">
                <MiniKLineChart
                  bars={data.ohlcv_snapshot!}
                  signals={data.signal_points || []}
                  width={chartExpanded ? 600 : 280}
                  height={chartExpanded ? 140 : 70}
                  onClick={chartExpanded ? undefined : () => setChartExpanded(true)}
                />
              </div>
            </div>
          )}
        </div>
      )}

      {!hasTrades && hasChart && (
        <div className="rounded-lg border border-border/60 bg-card/60 p-2">
          <div className="flex items-center justify-between mb-1 px-1">
            <span className="text-[10px] text-muted-foreground uppercase tracking-wider">K线 + 信号标记</span>
            <button onClick={() => setChartExpanded(!chartExpanded)} className="text-muted-foreground hover:text-foreground">
              {chartExpanded ? <Minimize2 size={12} /> : <Maximize2 size={12} />}
            </button>
          </div>
          <div className="flex justify-center">
            <MiniKLineChart
              bars={data.ohlcv_snapshot!}
              signals={data.signal_points || []}
              width={chartExpanded ? 600 : 280}
              height={chartExpanded ? 140 : 70}
              onClick={chartExpanded ? undefined : () => setChartExpanded(true)}
            />
          </div>
        </div>
      )}
    </div>
  );
}
