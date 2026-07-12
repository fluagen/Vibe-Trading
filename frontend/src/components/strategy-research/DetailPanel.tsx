import { useState } from "react";
import { X, ChevronDown, ChevronUp } from "lucide-react";
import type { BacktestDetailItem } from "@/lib/api";

interface DetailPanelProps { data: BacktestDetailItem; onClose: () => void; }

const STATE_LABELS: Record<string, string> = {
  no_structure: "无结构", forming: "形成中", up_phase: "上涨阶段", pullback: "回调", breakdown: "崩坏",
};

const STATE_COLORS: Record<string, string> = {
  no_structure: "bg-slate-500", forming: "bg-amber-500", up_phase: "bg-emerald-500",
  pullback: "bg-sky-500", breakdown: "bg-red-500",
};

function fmtMonth(dateStr: string): string {
  if (!dateStr) return "";
  const [y, m] = dateStr.split("-");
  return `${y}年${parseInt(m)}月`;
}

function fmtDateRange(start: string, end: string): string {
  if (!start) return "";
  const sm = fmtMonth(start);
  const em = fmtMonth(end);
  if (!em || sm === em) return sm;
  return `${sm}至${em}`;
}

export function DetailPanel({ data, onClose }: DetailPanelProps) {
  const [showTimeline, setShowTimeline] = useState(true);
  const stateLabel = STATE_LABELS[data.final_state] || data.final_state;
  const stateColor = STATE_COLORS[data.final_state] || "bg-slate-500";
  const dateRangeLabel = fmtDateRange(data.date_start, data.date_end);

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-baseline gap-2.5">
          <span className="font-mono text-sm font-semibold text-foreground">{data.code}</span>
          {data.name && <span className="text-xs text-muted-foreground">{data.name}</span>}
          <span className="text-[10px] text-muted-foreground/60 font-mono">{dateRangeLabel}</span>
        </div>
        <button onClick={onClose} className="rounded p-1 text-muted-foreground hover:text-foreground transition-colors">
          <X size={14} />
        </button>
      </div>

      {/* Metrics — dashboard card grid */}
      <div className="grid grid-cols-5 gap-2">
        <MetricCard label="数据范围">
          <span className="text-[11px] font-mono text-foreground font-medium">{data.date_start || "—"} ~ {data.date_end || "—"}</span>
          <span className="text-[10px] text-muted-foreground">（{data.trading_days ?? "—"} 个交易日）</span>
        </MetricCard>

        <MetricCard label="当前状态">
          <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium text-white ${stateColor}`}>
            <span className="h-1.5 w-1.5 rounded-full bg-white/60" />
            {stateLabel}
          </span>
        </MetricCard>

        <MetricCard label="止跌K / 证伪K" value={`${data.bsk_count ?? "—"} / ${data.ck_count ?? "—"}`} />

        <MetricCard label="交易次数" value={`${data.trade_count}`}
          sub={`${data.win_count} 胜 ${data.loss_count} 负`}
          subClassName={data.win_count > data.loss_count ? "text-emerald-500" : data.loss_count > data.win_count ? "text-red-500" : ""} />

        <MetricCard label="胜率" value={`${(data.win_rate * 100).toFixed(0)}%`}
          valueClassName={data.win_rate >= 0.5 ? "text-emerald-500" : data.win_rate > 0 ? "text-amber-500" : "text-red-500"} />

        <MetricCard label="累计收益" value={`${data.cumulative_return >= 0 ? "+" : ""}${(data.cumulative_return * 100).toFixed(2)}%`}
          valueClassName={data.cumulative_return >= 0 ? "text-red-500" : "text-emerald-500"} />

        <MetricCard label="年化收益" value={`${data.annual_return >= 0 ? "+" : ""}${(data.annual_return * 100).toFixed(2)}%`}
          valueClassName={data.annual_return >= 0 ? "text-red-500" : "text-emerald-500"} />

        <MetricCard label="最大回撤" value={`${(data.max_drawdown * 100).toFixed(2)}%`} />

        <MetricCard label="夏普比率" value={data.sharpe?.toFixed(2) || "—"} />

        <MetricCard label="状态分布">
          <div className="flex flex-wrap justify-center gap-1">
            {Object.entries(data.states_summary || {}).length > 0
              ? Object.entries(data.states_summary).map(([k, v]) => (
                  <span key={k} className={`inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 text-[10px] font-medium text-white ${STATE_COLORS[k] || "bg-slate-500"}`}>
                    {STATE_LABELS[k] || k} {v}
                  </span>
                ))
              : <span className="text-[10px] text-muted-foreground">—</span>}
          </div>
        </MetricCard>
      </div>

      {/* Signal Timeline */}
      {data.trades && data.trades.length > 0 && (
        <div className="rounded-lg border border-border overflow-hidden">
          <button
            onClick={() => setShowTimeline(!showTimeline)}
            className="flex w-full items-center justify-between px-3 py-2 bg-muted/20 hover:bg-muted/30 transition-colors select-none"
          >
            <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">
              信号时间线（{data.trades.length} 笔交易）
            </span>
            {showTimeline ? <ChevronUp size={13} className="text-muted-foreground" /> : <ChevronDown size={13} className="text-muted-foreground" />}
          </button>
          {showTimeline && (
            <div className="max-h-64 overflow-y-auto">
              <table className="w-full text-[11px]">
                <thead className="bg-muted/15 sticky top-0">
                  <tr className="text-[10px] text-muted-foreground uppercase tracking-wider">
                    <th className="px-2 py-1.5 text-left w-6">#</th>
                    <th className="px-2 py-1.5 text-left w-16">日期</th>
                    <th className="px-2 py-1.5 text-left w-24">信号</th>
                    <th className="px-2 py-1.5 text-right w-16">价格</th>
                    <th className="px-2 py-1.5 text-left">结果</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/50">
                  {data.trades.map((trade) => (
                    trade.signals.map((sig, si) => {
                      const isEntry = sig.type.startsWith("entry");
                      const isFirst = si === 0;
                      return (
                        <tr key={`${trade.trade_index}-${si}`}
                          className={`transition-colors hover:bg-muted/20 ${isFirst ? "border-t-2 border-border/80" : ""}`}>
                          <td className="px-2 py-1 text-muted-foreground text-center">
                            {isFirst ? (
                              <span className="inline-flex items-center justify-center h-4 w-4 rounded-full bg-muted text-[10px] font-mono font-medium text-muted-foreground">
                                {trade.trade_index}
                              </span>
                            ) : ""}
                          </td>
                          <td className="px-2 py-1 font-mono tabular-nums text-foreground">{sig.date.slice(5)}</td>
                          <td className={`px-2 py-1 font-medium ${isEntry ? "text-emerald-500" : "text-red-500"}`}>{sig.type}</td>
                          <td className="px-2 py-1 text-right font-mono tabular-nums text-foreground">{sig.price.toFixed(2)}</td>
                          <td className="px-2 py-1 text-muted-foreground">{sig.description}</td>
                        </tr>
                      );
                    })
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Fallback: flat signal points */}
      {(!data.trades || data.trades.length === 0) && data.signal_points && data.signal_points.length > 0 && (
        <div className="max-h-36 overflow-y-auto rounded-lg border border-border">
          <table className="w-full text-[11px]">
            <thead className="bg-muted/15 sticky top-0">
              <tr className="text-[10px] text-muted-foreground uppercase tracking-wider">
                <th className="pb-1.5 px-2 text-left">日期</th>
                <th className="pb-1.5 px-2 text-left">类型</th>
                <th className="pb-1.5 px-2 text-right">价格</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/50">
              {data.signal_points.map((s, i) => (
                <tr key={i}>
                  <td className="py-1 px-2 font-mono text-foreground">{s.date}</td>
                  <td className={`py-1 px-2 font-medium ${s.type.startsWith("entry") ? "text-emerald-500" : "text-red-500"}`}>{s.type}</td>
                  <td className="py-1 px-2 text-right font-mono text-foreground">{s.price}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function MetricCard({ label, value, valueClassName, sub, subClassName, children }: {
  label: string;
  value?: string;
  valueClassName?: string;
  sub?: string;
  subClassName?: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="rounded-lg border border-border/60 bg-card/60 p-2.5 text-center hover:border-border transition-colors">
      <div className="text-[10px] text-muted-foreground uppercase tracking-wider mb-1">{label}</div>
      {children ? (
        <div className="flex flex-col items-center gap-0.5">{children}</div>
      ) : (
        <div className={`text-sm font-bold font-mono tabular-nums ${valueClassName || "text-foreground"}`}>
          {value ?? "—"}
        </div>
      )}
      {sub && <div className={`text-[10px] mt-0.5 font-mono ${subClassName || "text-muted-foreground"}`}>{sub}</div>}
    </div>
  );
}
