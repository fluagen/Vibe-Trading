import { useState } from "react";
import { X, Maximize2, Minimize2 } from "lucide-react";
import type { BacktestDetailItem, TradeRow } from "@/lib/api";
import { MiniKLineChart } from "@/components/charts/MiniKLineChart";

interface DetailPanelProps {
  data: BacktestDetailItem;
  strategy: string;
  stockName?: string;
  onClose: () => void;
  onAddCandidate?: (code: string) => void;
}

const STATE_LABELS: Record<string, string> = {
  no_structure: "无结构", forming: "形成中", up_phase: "上涨",
  pullback: "回调", pullback_end: "回调结束", breakdown: "崩坏",
};
const STATE_COLORS: Record<string, string> = {
  no_structure: "bg-slate-500", forming: "bg-amber-500", up_phase: "bg-emerald-500",
  pullback: "bg-sky-500", pullback_end: "bg-teal-500", breakdown: "bg-red-500",
};

const NODE_STAGE_COLORS: Record<string, string> = {
  S1: "bg-slate-400", S2: "bg-amber-500", S3: "bg-emerald-500", S4: "bg-sky-500", S5: "bg-red-500",
};
const NODE_STAGE_LABELS: Record<string, string> = {
  S1: "蓄势", S2: "萌芽", S3: "健康趋势", S4: "加速", S5: "极端",
};

function stageDisplay(finalState: string): { label: string; color: string } {
  const m = finalState.match(/^(S\d)/);
  const stage = m ? m[1] : "S1";
  const dir = finalState.includes("bull") ? "多" : finalState.includes("bear") ? "空" : "";
  return {
    label: (NODE_STAGE_LABELS[stage] || stage) + (dir ? `(${dir})` : ""),
    color: NODE_STAGE_COLORS[stage] || "bg-slate-400",
  };
}

// ---- up_trend inline helpers ----

function signalReason(sig: { type: string; description?: string; entry_pattern?: string }): string {
  if (sig.description) {
    let text = sig.description;
    const i = text.indexOf(",");
    if (i > 0) text = text.slice(0, i);
    if (sig.entry_pattern && sig.type === "entry_trial")
      text = text.replace("止跌K", `止跌K(${sig.entry_pattern})`);
    return text;
  }
  if (sig.type === "entry_trial") return sig.entry_pattern ? `止跌K(${sig.entry_pattern})` : "止跌K";
  if (sig.type === "entry_confirm") return "证伪K";
  if (sig.type === "take_profit") return "止盈";
  if (sig.type === "exit") return "离场";
  return "";
}

function signalActionUpTrend(sig: { type: string; signal_value: number }): string {
  if (sig.type === "entry_trial") return `入场(${sig.signal_value.toFixed(2)})`;
  if (sig.type === "entry_confirm") return `加仓(${sig.signal_value.toFixed(2)})`;
  if (sig.type === "take_profit") return `止盈(x${sig.signal_value.toFixed(2)})`;
  if (sig.type === "exit") return "退出(-1.0)";
  return sig.type;
}

// ---- node_trading modal ----

function fmtPct(v: number): string {
  return `${v >= 0 ? "+" : ""}${(v * 100).toFixed(2)}%`;
}

function fmtMoney(v: number): string {
  return `¥${(v * 100000).toLocaleString("zh-CN", { maximumFractionDigits: 0 })}`;
}

function dateShort(d: string): string {
  return d.length >= 10 ? d.slice(5) : d;
}

/** Build Xueqiu URL: "600519.SH" or "603538" → "https://xueqiu.com/S/SH603538" */
function xueqiuUrl(code: string): string {
  const normalized = code.replace(/\.(SH|SZ|BJ)$/i, "");
  const prefix = normalized.startsWith("6") ? "SH" : "SZ";
  return `https://xueqiu.com/S/${prefix}${normalized}`;
}

export function DetailPanel({ data, strategy, stockName, onClose, onAddCandidate }: DetailPanelProps) {
  // ---- node_trading: full modal ----
  if (strategy === "node_trading") {
    return <NodeTradingModal data={data} stockName={stockName} onClose={onClose} onAddCandidate={onAddCandidate} />;
  }

  // ---- up_trend_structure: inline (unchanged) ----
  return <UpTrendInline data={data} onClose={onClose} onAddCandidate={onAddCandidate} />;
}

// =============================================================================
// Node Trading Modal
// =============================================================================

function NodeTradingModal({ data, stockName, onClose, onAddCandidate }: {
  data: BacktestDetailItem;
  stockName?: string;
  onClose: () => void;
  onAddCandidate?: (code: string) => void;
}) {
  const [chartExpanded, setChartExpanded] = useState(false);
  const hasChart = data.ohlcv_snapshot && data.ohlcv_snapshot.length > 0;
  const rows: TradeRow[] = data.trade_rows || [];

  // State pill
  const disp = data.final_state ? stageDisplay(data.final_state) : { label: "S1", color: "bg-slate-400" };

  // Compute trade count excluding open positions
  const closedTrades = rows.filter((r) => !r.is_open).length;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/50 p-4 pt-8 pb-8">
      <div className="relative w-full max-w-4xl rounded-xl border border-border bg-background shadow-2xl">
        {/* Header */}
        <div className="sticky top-0 z-10 flex items-center justify-between border-b border-border bg-card/95 px-5 py-3 rounded-t-xl">
          <div className="flex items-center gap-3">
            <a
              href={xueqiuUrl(data.code)}
              target="_blank"
              rel="noopener noreferrer"
              className="font-mono text-base font-bold text-foreground hover:text-primary transition-colors underline decoration-dotted underline-offset-4"
              title={`在雪球查看 ${data.code}`}
            >
              {data.code}
            </a>
            {(stockName || (data.name && data.name !== data.code)) && (
              <a
                href={xueqiuUrl(data.code)}
                target="_blank"
                rel="noopener noreferrer"
                className="text-sm text-muted-foreground hover:text-primary transition-colors"
                title="在雪球查看"
              >
                {stockName || data.name}
              </a>
            )}
            <span className={`inline-flex items-center rounded px-2 py-0.5 text-[11px] font-medium text-white ${disp.color}`}>
              {disp.label}
            </span>
            {onAddCandidate && (
              <button
                onClick={() => onAddCandidate(data.code)}
                className="text-[11px] px-2 py-0.5 rounded border border-border text-muted-foreground hover:text-primary hover:border-primary/30 transition-colors"
              >
                加候选
              </button>
            )}
          </div>
          <button onClick={onClose} className="rounded-lg p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground">
            <X size={18} />
          </button>
        </div>

        {/* Body */}
        <div className="px-5 py-4 space-y-5">
          {/* Date range */}
          <p className="text-sm text-muted-foreground">
            <span className="font-medium">区间</span>: {data.date_start} ~ {data.date_end}{" "}
            ({data.trading_days} 个交易日)
          </p>

          {/* Current state line */}
          {data.current_state_line && (
            <p className="rounded bg-muted/30 px-3 py-2 text-sm font-mono text-muted-foreground">
              <span className="font-medium text-foreground">当前</span>: {data.current_state_line}
            </p>
          )}

          {/* Metrics grid */}
          <div>
            <h3 className="mb-2 text-xs font-semibold text-muted-foreground uppercase tracking-wider">指标</h3>
            <div className="grid grid-cols-3 gap-x-6 gap-y-2 text-sm">
              <MetricRow label="总收益率" value={fmtPct(data.cumulative_return)} hl={data.cumulative_return >= 0 ? "green" : "red"} />
              <MetricRow label="年化收益" value={fmtPct(data.annual_return)} hl={data.annual_return >= 0 ? "green" : "red"} />
              <MetricRow label="年化波动" value={`${((data.annual_volatility || 0) * 100).toFixed(2)}%`} />
              <MetricRow label="夏普比率" value={data.sharpe >= 0 ? `+${data.sharpe.toFixed(2)}` : data.sharpe.toFixed(2)} />
              <MetricRow label="最大回撤" value={fmtPct(data.max_drawdown)} hl="red" />
              <MetricRow label="已平仓交易" value={`${closedTrades} 笔`} />
              <MetricRow label="胜率" value={`${(data.win_rate * 100).toFixed(1)}%`} />
              <MetricRow label="盈亏比" value={(data.profit_factor || 0).toFixed(2)} />
              <MetricRow label="最终权益" value={fmtMoney(data.final_equity || 1)} />
            </div>
          </div>

          {/* Trade detail table */}
          {rows.length > 0 && (
            <div>
              <h3 className="mb-2 text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                交易明细（{rows.length} 笔）
              </h3>
              <div className="overflow-x-auto rounded-lg border border-border">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-border bg-muted/20 text-left text-muted-foreground">
                      <th className="px-2 py-1.5 font-medium">入场</th>
                      <th className="px-2 py-1.5 font-medium">入场阶段</th>
                      <th className="px-2 py-1.5 font-medium">出场</th>
                      <th className="px-2 py-1.5 font-medium">出场阶段</th>
                      <th className="px-2 py-1.5 font-medium">节点</th>
                      <th className="px-2 py-1.5 font-medium text-right">仓位</th>
                      <th className="px-2 py-1.5 font-medium text-right">入场价</th>
                      <th className="px-2 py-1.5 font-medium text-right">出场价</th>
                      <th className="px-2 py-1.5 font-medium text-right">盈亏</th>
                      <th className="px-2 py-1.5 font-medium">原因</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/50">
                    {rows.map((r, i) => (
                      <tr key={i} className="hover:bg-muted/10 font-mono">
                        <td className="px-2 py-1.5 whitespace-nowrap">{dateShort(r.entry_date)}</td>
                        <td className="px-2 py-1.5 text-muted-foreground max-w-[180px] truncate" title={r.entry_stage}>{r.entry_stage}</td>
                        <td className="px-2 py-1.5 whitespace-nowrap">{dateShort(r.exit_date)}</td>
                        <td className="px-2 py-1.5 text-muted-foreground max-w-[180px] truncate" title={r.exit_stage}>{r.exit_stage}</td>
                        <td className="px-2 py-1.5 font-medium">{r.node_label}</td>
                        <td className="px-2 py-1.5 text-right">{r.position.toFixed(2)}</td>
                        <td className="px-2 py-1.5 text-right">{r.entry_price.toFixed(2)}</td>
                        <td className="px-2 py-1.5 text-right">{r.exit_price.toFixed(2)}</td>
                        <td className={`px-2 py-1.5 text-right font-semibold ${r.return_pct >= 0 ? "text-red-500" : "text-emerald-500"}`}>
                          {fmtPct(r.return_pct)}
                        </td>
                        <td className="px-2 py-1.5 whitespace-nowrap">{r.is_open ? <span className="text-amber-500">持仓中</span> : r.exit_reason}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Mini K-line chart */}
          {hasChart && (
            <div>
              <div className="flex items-center justify-between mb-1">
                <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">K线 + 信号标记</h3>
                <button onClick={() => setChartExpanded(!chartExpanded)} className="text-muted-foreground hover:text-foreground">
                  {chartExpanded ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
                </button>
              </div>
              <div className="flex justify-center rounded-lg border border-border/60 bg-card/40 p-2">
                <MiniKLineChart
                  bars={data.ohlcv_snapshot!}
                  signals={data.signal_points || []}
                  width={chartExpanded ? 700 : 520}
                  height={chartExpanded ? 200 : 100}
                  markerStyle="bs"
                />
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function MetricRow({ label, value, hl }: { label: string; value: string; hl?: "green" | "red" }) {
  const c = hl === "green" ? "text-emerald-500" : hl === "red" ? "text-red-500" : "text-foreground";
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="text-muted-foreground">{label}</span>
      <span className={`font-mono font-semibold tabular-nums ${c}`}>{value}</span>
    </div>
  );
}

// =============================================================================
// Up-trend inline (kept from before)
// =============================================================================

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

function UpTrendInline({ data, onClose, onAddCandidate }: {
  data: BacktestDetailItem;
  onClose: () => void;
  onAddCandidate?: (code: string) => void;
}) {
  const [chartExpanded, setChartExpanded] = useState(false);
  const stateColor = STATE_COLORS[data.final_state] || "bg-slate-500";
  const winHl = data.win_rate >= 0.5 ? "green" as const : data.win_rate > 0 ? "amber" as const : "red" as const;
  const retHl = data.cumulative_return >= 0 ? "red" as const : "green" as const;
  const hasTrades = data.trades && data.trades.length > 0;
  const hasChart = data.ohlcv_snapshot && data.ohlcv_snapshot.length > 0;

  const chartEl = hasChart ? (
    <div className="flex justify-center">
      <MiniKLineChart
        bars={data.ohlcv_snapshot!}
        signals={data.signal_points || []}
        width={chartExpanded ? 600 : 280}
        height={chartExpanded ? 140 : 70}
        markerStyle="shape"
        onClick={chartExpanded ? undefined : () => setChartExpanded(true)}
      />
    </div>
  ) : null;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-baseline gap-2">
          <a href={xueqiuUrl(data.code)} target="_blank" rel="noopener noreferrer" className="font-mono text-sm font-semibold hover:text-primary transition-colors underline decoration-dotted underline-offset-4">{data.code}</a>
          {data.name && <span className="text-xs text-muted-foreground">{data.name}</span>}
          <span className={`inline-flex items-center rounded px-2 py-0.5 text-[10px] font-medium text-white ${stateColor}`}>
            {STATE_LABELS[data.final_state] || data.final_state}
          </span>
          {onAddCandidate && (
            <button
              onClick={() => onAddCandidate(data.code)}
              className="text-[10px] px-2 py-0.5 rounded border border-border text-muted-foreground hover:text-primary hover:border-primary/30 transition-colors"
            >
              加候选
            </button>
          )}
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
            <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">交易明细（{data.trades!.length} 笔）</span>
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
                          <span className={color}>{signalActionUpTrend(sig)}</span>
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
              {chartEl}
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
          {chartEl}
        </div>
      )}
    </div>
  );
}
