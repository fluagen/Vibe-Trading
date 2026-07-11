import { useTranslation } from "react-i18next";
import { X } from "lucide-react";
import type { BacktestDetailItem } from "@/lib/api";

interface DetailPanelProps { data: BacktestDetailItem; onClose: () => void; }

const STATE_COLORS: Record<string, string> = {
  no_structure: "bg-slate-500", forming: "bg-amber-500", up_phase: "bg-emerald-500",
  pullback: "bg-sky-500", breakdown: "bg-red-500",
};

const STATE_LABELS: Record<string, string> = {
  no_structure: "无结构", forming: "形成中", up_phase: "上涨阶段", pullback: "回调", breakdown: "崩坏",
};

export function DetailPanel({ data, onClose }: DetailPanelProps) {
  const { t } = useTranslation();
  const stateLabel = STATE_LABELS[data.final_state] || data.final_state;
  const stateColor = STATE_COLORS[data.final_state] || "bg-slate-500";

  return (
    <div className="rounded-lg border border-slate-700 bg-slate-900/80 p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-200">{data.code} {data.name} — {t("strategyResearch.viewDetail")}</h3>
        <button onClick={onClose} className="rounded p-1 text-slate-400 hover:text-slate-200"><X size={16} /></button>
      </div>
      <div className="mb-4 grid grid-cols-4 gap-3">
        <Metric label={t("strategyResearch.currentState")} value={stateLabel} badge={stateColor} />
        <Metric label={t("strategyResearch.tradeCount")} value={String(data.trade_count)} />
        <Metric label={t("strategyResearch.winRate")} value={`${(data.win_rate * 100).toFixed(1)}%`} />
        <Metric label={t("strategyResearch.cumulativeReturn")} value={`${(data.cumulative_return * 100).toFixed(2)}%`} colorClass={data.cumulative_return >= 0 ? "text-emerald-400" : "text-red-400"} />
        <Metric label={t("strategyResearch.annualReturn")} value={`${(data.annual_return * 100).toFixed(2)}%`} />
        <Metric label={t("strategyResearch.maxDrawdown")} value={`${(data.max_drawdown * 100).toFixed(2)}%`} />
        <Metric label={t("strategyResearch.sharpeRatio")} value={data.sharpe.toFixed(2)} />
        <Metric label="W/L" value={`${data.win_count}W/${data.loss_count}L`} />
      </div>
      {data.states_summary && Object.keys(data.states_summary).length > 0 && (
        <div className="mb-4">
          <h4 className="mb-2 text-xs font-medium text-slate-400">{t("strategyResearch.stateDistribution")}</h4>
          <div className="flex flex-wrap gap-2">
            {Object.entries(data.states_summary).map(([state, count]) => (
              <span key={state} className={`rounded-full px-2 py-0.5 text-xs text-white ${STATE_COLORS[state] || "bg-slate-500"}`}>
                {STATE_LABELS[state] || state}: {count}
              </span>
            ))}
          </div>
        </div>
      )}
      {data.latest_signal && (
        <div className="mb-4">
          <h4 className="mb-1 text-xs font-medium text-slate-400">{t("strategyResearch.latestSignal")}</h4>
          <span className="text-sm text-slate-300">{data.latest_signal.date} — {data.latest_signal.type} @ {data.latest_signal.price}</span>
        </div>
      )}
      {data.signal_points.length > 0 && (
        <div>
          <h4 className="mb-2 text-xs font-medium text-slate-400">{t("strategyResearch.tradeLog")}</h4>
          <div className="max-h-48 overflow-y-auto">
            <table className="w-full text-xs text-slate-300">
              <thead><tr className="text-slate-500"><th className="pb-1 text-left">日期</th><th className="pb-1 text-left">类型</th><th className="pb-1 text-right">价格</th></tr></thead>
              <tbody>
                {data.signal_points.map((s, i) => (
                  <tr key={i} className="border-t border-slate-800">
                    <td className="py-1">{s.date}</td>
                    <td className={s.type.startsWith("entry") ? "text-emerald-400" : "text-red-400"}>{s.type}</td>
                    <td className="text-right">{s.price}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

function Metric({ label, value, badge, colorClass }: { label: string; value: string; badge?: string; colorClass?: string }) {
  return (
    <div className="rounded bg-slate-800/50 p-2">
      <div className="text-[10px] text-slate-500">{label}</div>
      <div className={`text-sm font-medium ${colorClass || "text-slate-200"}`}>
        {badge ? <span className={`inline-block rounded-full px-1.5 py-0.5 text-xs text-white ${badge}`}>{value}</span> : value}
      </div>
    </div>
  );
}
