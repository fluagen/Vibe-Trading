import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import {
  api,
  type SectorMemberItem,
  type BacktestSummaryItem,
  type TradingDaysResponse,
  type StrategyConfigParams,
} from "@/lib/api";
import { DetailPanel } from "@/components/strategy-research/DetailPanel";
import { StrategyConfigTab } from "@/components/strategy-research/StrategyConfigTab";

type SectorType = "industry" | "concept";
type DatePreset = "30" | "60" | "120" | "250" | "custom";

const STATE_COLORS: Record<string, string> = {
  no_structure: "bg-slate-500", forming: "bg-amber-500", up_phase: "bg-emerald-500",
  pullback: "bg-sky-500", breakdown: "bg-red-500",
};

const STATE_LABELS: Record<string, string> = {
  no_structure: "无结构", forming: "形成中", up_phase: "上涨", pullback: "回调", breakdown: "崩坏",
};

export function StrategyResearch() {
  const { t } = useTranslation();

  const [tradingDay, setTradingDay] = useState("");
  const [availableDays, setAvailableDays] = useState<string[]>([]);
  const [sectorType, setSectorType] = useState<SectorType>("industry");
  const [sectors, setSectors] = useState<{ bk_code: string; bk_name: string }[]>([]);
  const [selectedSector, setSelectedSector] = useState("");
  const [members, setMembers] = useState<SectorMemberItem[]>([]);
  const [selectedCodes, setSelectedCodes] = useState<Set<string>>(new Set());
  const [datePreset, setDatePreset] = useState<DatePreset>("30");
  const [customStart, setCustomStart] = useState("");
  const [customEnd, setCustomEnd] = useState("");
  const [loadingMembers, setLoadingMembers] = useState(false);

  const [backtesting, setBacktesting] = useState(false);
  const [progress, setProgress] = useState<{ done: number; total: number; current: string } | null>(null);
  const [results, setResults] = useState<BacktestSummaryItem[]>([]);
  const [selectedResultCode, setSelectedResultCode] = useState<string | null>(null);
  const eventSourceRef = useRef<EventSource | null>(null);

  // Tab & params state
  const [activeTab, setActiveTab] = useState<"config" | "backtest">("backtest");
  const [backtestParams, setBacktestParams] = useState<StrategyConfigParams | null>(null);
  const [showParamsOverride, setShowParamsOverride] = useState(false);

  // Load saved config for backtest params
  useEffect(() => {
    api.getStrategyConfig("up_trend_structure")
      .then((res) => setBacktestParams(res.params))
      .catch(() => {});
  }, []);

  useEffect(() => {
    api.getTradingDays(60).then((d: TradingDaysResponse) => {
      setAvailableDays(d.dates);
      if (d.latest) setTradingDay(d.latest);
      else if (d.dates.length) setTradingDay(d.dates[0]);
    }).catch(() => toast.error(t("strategyResearch.loadFailed")));
  }, [t]);

  useEffect(() => {
    api.getStrategyResearchSectors(sectorType)
      .then((d) => setSectors(d.sectors || []))
      .catch(() => toast.error(t("strategyResearch.loadFailed")));
  }, [sectorType, t]);

  const handleSectorSelect = useCallback(async (bkCode: string) => {
    setSelectedSector(bkCode);
    if (!bkCode) { setMembers([]); setSelectedCodes(new Set()); return; }
    setLoadingMembers(true);
    try {
      const data = await api.getSectorMembers(bkCode, sectorType);
      const m = data.members || [];
      setMembers(m);
      setSelectedCodes(new Set(m.map((x) => x.code)));
    } catch {
      toast.error(t("strategyResearch.loadFailed"));
    } finally {
      setLoadingMembers(false);
    }
  }, [sectorType, t]);

  const toggleStock = (code: string) => {
    setSelectedCodes((prev) => {
      const next = new Set(prev);
      if (next.has(code)) next.delete(code); else next.add(code);
      return next;
    });
  };

  const toggleAll = () => {
    if (selectedCodes.size === members.length) {
      setSelectedCodes(new Set());
    } else {
      setSelectedCodes(new Set(members.map((m) => m.code)));
    }
  };

  const computeDateRange = (): { start: string; end: string } | null => {
    if (datePreset !== "custom") {
      const idx = availableDays.indexOf(tradingDay);
      if (idx < 0) return null;
      const count = parseInt(datePreset);
      const startIdx = Math.min(idx + count - 1, availableDays.length - 1);
      return { start: availableDays[startIdx], end: tradingDay };
    }
    if (!customStart || !customEnd) return null;
    return { start: customStart, end: customEnd };
  };

  const handleStartBacktest = async () => {
    const codes = [...selectedCodes];
    if (!codes.length) { toast.error("请选择至少一只股票"); return; }
    const range = computeDateRange();
    if (!range) { toast.error("请选择回测区间"); return; }

    setBacktesting(true);
    setProgress(null);
    setResults([]);
    setSelectedResultCode(null);
    if (eventSourceRef.current) eventSourceRef.current.close();

    try {
      const { job_id } = await api.startBacktest({
        codes, start_date: range.start, end_date: range.end,
        strategy: "up_trend_structure",
        params: backtestParams ?? undefined,
      });
      if (!job_id) { toast.error(t("strategyResearch.backtestFailed")); setBacktesting(false); return; }

      const es = new EventSource(api.backtestStreamUrl(job_id));
      eventSourceRef.current = es;
      es.addEventListener("progress", (e) => setProgress(JSON.parse(e.data)));
      es.addEventListener("stock_result", (e) => setResults((prev) => [...prev, JSON.parse(e.data).summary]));
      es.addEventListener("result", (e) => setResults(Object.values(JSON.parse(e.data)) as BacktestSummaryItem[]));
      es.addEventListener("done", () => { es.close(); setBacktesting(false); toast.success("回测完成"); });
      es.addEventListener("error", () => { es.close(); setBacktesting(false); toast.error(t("strategyResearch.backtestFailed")); });
    } catch {
      setBacktesting(false);
      toast.error(t("strategyResearch.backtestFailed"));
    }
  };

  useEffect(() => () => eventSourceRef.current?.close(), []);

  const detailData = results.find((r) => r.code === selectedResultCode) || null;

  return (
    <div className="flex h-full flex-col gap-4 overflow-auto p-6">
      <h1 className="text-lg font-bold text-slate-100">{t("strategyResearch.title")}</h1>

      {/* Tab Bar */}
      <div className="flex rounded border border-slate-700 bg-slate-800 w-fit">
        {(["backtest", "config"] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-4 py-1.5 text-sm rounded ${activeTab === tab ? "bg-slate-700 text-slate-100" : "text-slate-400"}`}
          >
            {t(`strategyResearch.${tab}Tab`)}
          </button>
        ))}
      </div>

      {/* Config Tab */}
      {activeTab === "config" && <StrategyConfigTab />}

      {/* Backtest Tab */}
      {activeTab === "backtest" && (
      <>
      {/* Filter Controls */}
      <div className="flex flex-wrap items-end gap-3">
        <div>
          <label className="mb-1 block text-xs text-slate-500">{t("strategyResearch.tradingDay")}</label>
          <select value={tradingDay} onChange={(e) => setTradingDay(e.target.value)}
            className="rounded border border-slate-700 bg-slate-800 px-2 py-1 text-sm text-slate-200">
            {availableDays.map((d) => <option key={d} value={d}>{d}</option>)}
          </select>
        </div>
        <div>
          <label className="mb-1 block text-xs text-slate-500">{t("strategyResearch.sectorType")}</label>
          <div className="flex rounded border border-slate-700 bg-slate-800">
            {(["industry", "concept"] as SectorType[]).map((st) => (
              <button key={st} onClick={() => { setSectorType(st); setSelectedSector(""); setMembers([]); }}
                className={`px-3 py-1 text-sm ${sectorType === st ? "bg-slate-700 text-slate-100" : "text-slate-400"} rounded`}>
                {t(`strategyResearch.${st}`)}
              </button>
            ))}
          </div>
        </div>
        <div>
          <label className="mb-1 block text-xs text-slate-500">{t("strategyResearch.selectSectors")}</label>
          <select value={selectedSector} onChange={(e) => handleSectorSelect(e.target.value)}
            className="max-w-[200px] rounded border border-slate-700 bg-slate-800 px-2 py-1 text-sm text-slate-200">
            <option value="">--</option>
            {sectors.map((s) => <option key={s.bk_code} value={s.bk_code}>{s.bk_name}</option>)}
          </select>
        </div>
        <div>
          <label className="mb-1 block text-xs text-slate-500">{t("strategyResearch.dateRange")}</label>
          <div className="flex rounded border border-slate-700 bg-slate-800">
            {(["30", "60", "120", "250", "custom"] as DatePreset[]).map((p) => (
              <button key={p} onClick={() => setDatePreset(p)}
                className={`px-2 py-1 text-xs ${datePreset === p ? "bg-slate-700 text-slate-100" : "text-slate-400"} rounded`}>
                {p === "custom" ? t("strategyResearch.customRange") : t(`strategyResearch.last${p}Days`)}
              </button>
            ))}
          </div>
        </div>
        {datePreset === "custom" && (
          <>
            <div><label className="mb-1 block text-xs text-slate-500">{t("strategyResearch.startDate")}</label>
              <input type="date" value={customStart} onChange={(e) => setCustomStart(e.target.value)}
                className="rounded border border-slate-700 bg-slate-800 px-2 py-1 text-sm text-slate-200" /></div>
            <div><label className="mb-1 block text-xs text-slate-500">{t("strategyResearch.endDate")}</label>
              <input type="date" value={customEnd} onChange={(e) => setCustomEnd(e.target.value)}
                className="rounded border border-slate-700 bg-slate-800 px-2 py-1 text-sm text-slate-200" /></div>
          </>
        )}
        <button onClick={handleStartBacktest} disabled={backtesting || selectedCodes.size === 0}
          className="rounded bg-emerald-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-50">
          {backtesting ? t("strategyResearch.backtesting") : t("strategyResearch.startBacktest")}
        </button>
      </div>

      {/* Backtest Params Override (collapsible) */}
      <div>
        <button
          onClick={() => setShowParamsOverride(!showParamsOverride)}
          className="text-xs text-slate-500 hover:text-slate-300"
        >
          {showParamsOverride ? "▾" : "▸"} 回测参数{backtestParams && "（已加载配置）"}
        </button>
        {showParamsOverride && backtestParams && (
          <div className="mt-2 grid grid-cols-4 gap-x-4 gap-y-2 rounded border border-slate-700 bg-slate-800/50 p-3">
            {Object.entries(backtestParams).map(([key, value]) => (
              <div key={key} className="flex items-center gap-2">
                <label className="text-xs text-slate-400 w-36">{t(`strategyResearch.param_${key}`)}</label>
                <input
                  type="number"
                  value={value}
                  onChange={(e) => {
                    const v = parseFloat(e.target.value);
                    if (!isNaN(v)) setBacktestParams((prev) => prev ? { ...prev, [key]: v } : null);
                  }}
                  className="w-20 rounded border border-slate-600 bg-slate-800 px-1.5 py-0.5 text-xs text-slate-200"
                />
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Sector Members Table */}
      {members.length > 0 && (
        <div>
          <div className="mb-2 flex items-center justify-between text-xs text-slate-500">
            <span>
              {t("strategyResearch.constituentStocks")} ({members.length}) — 已选 {selectedCodes.size} 只
            </span>
            <button onClick={toggleAll} className="text-slate-400 hover:text-slate-200">
              {selectedCodes.size === members.length ? "取消全选" : "全选"}
            </button>
          </div>
          <div className="max-h-[400px] overflow-auto rounded-lg border border-slate-700">
            <table className="w-full text-xs text-slate-300">
              <thead className="sticky top-0 bg-slate-900">
                <tr className="border-b border-slate-700 text-slate-500">
                  <th className="w-8 px-2 py-2">
                    <input type="checkbox" checked={selectedCodes.size === members.length && members.length > 0} onChange={toggleAll} />
                  </th>
                  <th className="px-2 py-2 text-left">代码</th>
                  <th className="px-2 py-2 text-left">名称</th>
                  <th className="px-2 py-2 text-right">最新价</th>
                  <th className="px-2 py-2 text-right">涨跌幅</th>
                  <th className="px-2 py-2 text-left">所属概念</th>
                  <th className="px-2 py-2 text-left">所属行业</th>
                </tr>
              </thead>
              <tbody>
                {members.map((m) => {
                  const sel = selectedCodes.has(m.code);
                  return (
                    <tr key={m.code} onClick={() => toggleStock(m.code)}
                      className={`cursor-pointer border-b border-slate-800 hover:bg-slate-800/50 ${sel ? "bg-slate-800/70" : ""}`}>
                      <td className="px-2 py-1.5">
                        <input type="checkbox" checked={sel} onChange={() => toggleStock(m.code)} />
                      </td>
                      <td className="px-2 py-1.5 font-mono">{m.code}</td>
                      <td className="px-2 py-1.5">{m.name}</td>
                      <td className="px-2 py-1.5 text-right">{m.price?.toFixed(2) || "—"}</td>
                      <td className={`px-2 py-1.5 text-right ${m.change_pct >= 0 ? "text-red-400" : "text-emerald-400"}`}>
                        {m.change_pct != null ? `${m.change_pct > 0 ? "+" : ""}${m.change_pct.toFixed(2)}%` : "—"}
                      </td>
                      <td className="max-w-[200px] truncate px-2 py-1.5" title={m.concepts?.join(", ")}>
                        {m.concepts?.slice(0, 3).join(", ") || "—"}{m.concepts && m.concepts.length > 3 ? ` +${m.concepts.length - 3}` : ""}
                      </td>
                      <td className="max-w-[150px] truncate px-2 py-1.5" title={m.industries?.join(" → ")}>
                        {m.industries?.join(" → ") || "—"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {loadingMembers && <div className="text-xs text-slate-500">加载中...</div>}

      {/* Backtest Progress */}
      {backtesting && progress && (
        <div>
          <div className="mb-1 flex justify-between text-xs text-slate-500">
            <span>{progress.current}</span><span>{progress.done}/{progress.total}</span>
          </div>
          <div className="h-1.5 rounded-full bg-slate-800">
            <div className="h-full rounded-full bg-emerald-500 transition-all" style={{ width: `${(progress.done / progress.total) * 100}%` }} />
          </div>
        </div>
      )}

      {/* Backtest Results */}
      {results.length > 0 && (
        <div className="overflow-auto rounded-lg border border-slate-700">
          <table className="w-full text-sm text-slate-300">
            <thead>
              <tr className="border-b border-slate-700 text-xs text-slate-500">
                <th className="px-2 py-2 text-left">{t("strategyResearch.code")}</th>
                <th className="px-2 py-2 text-left">{t("strategyResearch.currentState")}</th>
                <th className="px-2 py-2 text-right">{t("strategyResearch.tradeCount")}</th>
                <th className="px-2 py-2 text-right">{t("strategyResearch.winRate")}</th>
                <th className="px-2 py-2 text-right">止跌K</th>
                <th className="px-2 py-2 text-right">证伪K</th>
                <th className="px-2 py-2 text-right">{t("strategyResearch.cumulativeReturn")}</th>
                <th className="px-2 py-2">操作</th>
              </tr>
            </thead>
            <tbody>
              {results.map((r) => (
                <tr key={r.code} className={`border-b border-slate-800 hover:bg-slate-800/50 ${selectedResultCode === r.code ? "bg-slate-800/70" : ""}`}>
                  <td className="px-2 py-2 font-mono text-xs">{r.code}</td>
                  <td className="px-2 py-2"><span className={`rounded-full px-1.5 py-0.5 text-xs text-white ${STATE_COLORS[r.final_state] || "bg-slate-500"}`}>{STATE_LABELS[r.final_state] || r.final_state}</span></td>
                  <td className="px-2 py-2 text-right">{r.trade_count}</td>
                  <td className="px-2 py-2 text-right">{(r.win_rate * 100).toFixed(0)}%</td>
                  <td className="px-2 py-2 text-right">{r.bsk_count ?? "—"}</td>
                  <td className="px-2 py-2 text-right">{r.ck_count ?? "—"}</td>
                  <td className={`px-2 py-2 text-right font-mono ${r.cumulative_return >= 0 ? "text-emerald-400" : "text-red-400"}`}>{(r.cumulative_return * 100).toFixed(2)}%</td>
                  <td className="px-2 py-2">
                    <button onClick={() => setSelectedResultCode(selectedResultCode === r.code ? null : r.code)}
                      className="rounded px-2 py-0.5 text-xs text-slate-400 hover:bg-slate-700 hover:text-slate-200">
                      {selectedResultCode === r.code ? t("strategyResearch.closeDetail") : t("strategyResearch.viewDetail")}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {detailData && <DetailPanel data={detailData} onClose={() => setSelectedResultCode(null)} />}
      </>
      )}
    </div>
  );
}
