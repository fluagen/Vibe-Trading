import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { ArrowUpDown, ArrowDown, ArrowUp, ChevronDown, ChevronUp, ChevronLeft, ChevronRight, FlaskConical, Play, Search, SlidersHorizontal } from "lucide-react";
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
  no_structure: "bg-slate-500", forming: "bg-amber-500",
  up_phase: "bg-emerald-500", pullback: "bg-sky-500",
  pullback_end: "bg-teal-500", breakdown: "bg-red-500",
};

const STATE_LABELS: Record<string, string> = {
  no_structure: "无结构", forming: "形成中",
  up_phase: "上涨", pullback: "回调",
  pullback_end: "回调结束", breakdown: "崩坏",
};

const DATE_PRESETS: DatePreset[] = ["30", "60", "120", "250", "custom"];

function getXueqiuUrl(code: string): string {
  const normalized = code.replace(/\.(SH|SZ|BJ)$/i, "");
  const prefix = normalized.startsWith("6") ? "SH" : "SZ";
  return `https://xueqiu.com/S/${prefix}${normalized}`;
}

export function StrategyResearch() {
  const { t } = useTranslation();

  const [tradingDay, setTradingDay] = useState("");
  const [availableDays, setAvailableDays] = useState<string[]>([]);
  const [sectorType, setSectorType] = useState<SectorType>("industry");
  const [sectors, setSectors] = useState<{ bk_code: string; bk_name: string }[]>([]);
  const [selectedSector, setSelectedSector] = useState("");
  const [sectorSearch, setSectorSearch] = useState("");
  const [showSectorDropdown, setShowSectorDropdown] = useState(false);
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

  const [activeTab, setActiveTab] = useState<"config" | "backtest">("backtest");
  const [backtestParams, setBacktestParams] = useState<StrategyConfigParams | null>(null);
  const [showParamsOverride, setShowParamsOverride] = useState(false);

  const [showMembers, setShowMembers] = useState(true);
  const [showResults, setShowResults] = useState(true);

  // Members pagination
  const [memberPage, setMemberPage] = useState(1);
  const [memberPageSize, setMemberPageSize] = useState(20);
  const totalMemberPages = Math.max(1, Math.ceil(members.length / memberPageSize));
  const safeMemberPage = Math.min(memberPage, totalMemberPages);
  const pagedMembers = members.slice((safeMemberPage - 1) * memberPageSize, safeMemberPage * memberPageSize);

  // Results pagination
  const [resultPage, setResultPage] = useState(1);
  const [resultPageSize, setResultPageSize] = useState(20);
  type ResultSortField = "trade_count" | "win_rate" | "cumulative_return" | "final_state";
  const [resultSortField, setResultSortField] = useState<ResultSortField>("cumulative_return");
  const [resultSortOrder, setResultSortOrder] = useState<"asc" | "desc">("desc");
  const [resultStateFilter, setResultStateFilter] = useState("");

  const toggleResultSort = (field: ResultSortField) => {
    if (resultSortField === field) {
      setResultSortOrder((prev) => (prev === "desc" ? "asc" : "desc"));
    } else {
      setResultSortField(field);
      setResultSortOrder("desc");
    }
    setResultPage(1);
  };

  const resultSortIcon = (field: ResultSortField) => {
    if (resultSortField !== field) return <ArrowUpDown className="h-3 w-3 text-muted-foreground/50" />;
    return resultSortOrder === "desc"
      ? <ArrowDown className="h-3 w-3 text-primary" />
      : <ArrowUp className="h-3 w-3 text-primary" />;
  };

  const sortedResults = useMemo(() => {
    const list = [...results];
    const dir = resultSortOrder === "desc" ? -1 : 1;
    list.sort((a, b) => {
      const va = a[resultSortField];
      const vb = b[resultSortField];
      if (va == null && vb == null) return 0;
      if (va == null) return 1;
      if (vb == null) return -1;
      if (resultSortField === "final_state") {
        return String(va).localeCompare(String(vb)) * dir;
      }
      return (Number(va) - Number(vb)) * dir;
    });
    return list;
  }, [results, resultSortField, resultSortOrder]);

  const filteredResults = useMemo(() => {
    if (!resultStateFilter) return sortedResults;
    return sortedResults.filter((r) => r.final_state === resultStateFilter);
  }, [sortedResults, resultStateFilter]);

  const totalResultPages = Math.max(1, Math.ceil(filteredResults.length / resultPageSize));
  const safeResultPage = Math.min(resultPage, totalResultPages);
  const pagedResults = filteredResults.slice((safeResultPage - 1) * resultPageSize, safeResultPage * resultPageSize);

  // Code → name lookup from members
  const codeToName = useMemo(() => {
    const map: Record<string, string> = {};
    members.forEach((m) => { map[m.code] = m.name; });
    return map;
  }, [members]);

  useEffect(() => {
    api.getStrategyConfig("up_trend_structure")
      .then((res) => setBacktestParams(res.params))
      .catch(() => {});
  }, []);

  useEffect(() => {
    api.getTradingDays(250).then((d: TradingDaysResponse) => {
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

  const filteredSectors = useMemo(() => {
    if (!sectorSearch) return sectors.slice(0, 20);
    const q = sectorSearch.toLowerCase();
    return sectors.filter((s) =>
      s.bk_name.toLowerCase().includes(q) || s.bk_code.toLowerCase().includes(q)
    ).slice(0, 15);
  }, [sectors, sectorSearch]);

  const handleSectorSelect = useCallback(async (bkCode: string, bkName: string) => {
    setSelectedSector(bkCode);
    setSectorSearch(bkName);
    setShowSectorDropdown(false);
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

  // Reset pagination when data changes
  useEffect(() => { setMemberPage(1); }, [members.length]);
  useEffect(() => { setResultPage(1); }, [results.length]);

  const detailData = results.find((r) => r.code === selectedResultCode) || null;
  const hasSelection = selectedCodes.size > 0;

  return (
    <div className="flex flex-col gap-5 p-6">
      {/* Header row: icon + title | tabs | params button */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10">
              <FlaskConical size={16} className="text-primary" />
            </div>
            <h1 className="text-lg font-semibold text-foreground tracking-tight">
              {t("strategyResearch.title")}
            </h1>
          </div>
          <div className="h-5 w-px bg-border" />
          <div className="flex rounded-md border border-border bg-card p-0.5">
            {(["backtest", "config"] as const).map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`px-3.5 py-1.5 text-xs font-medium rounded-sm transition-colors ${
                  activeTab === tab
                    ? "bg-primary text-primary-foreground shadow-sm"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                {t(`strategyResearch.${tab}Tab`)}
              </button>
            ))}
          </div>
        </div>
        {activeTab === "backtest" && backtestParams && (
          <button
            onClick={() => setShowParamsOverride(!showParamsOverride)}
            className={`inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs transition-colors ${
              showParamsOverride
                ? "bg-primary/10 text-primary border border-primary/20"
                : "text-muted-foreground hover:text-foreground border border-transparent hover:border-border"
            }`}
          >
            <SlidersHorizontal size={13} />
            参数
          </button>
        )}
      </div>

      {/* Config Tab */}
      {activeTab === "config" && <StrategyConfigTab />}

      {/* Backtest Tab */}
      {activeTab === "backtest" && (
      <>
      {/* Params panel — slides open */}
      {showParamsOverride && backtestParams && (
        <div className="grid grid-cols-4 gap-x-5 gap-y-2.5 rounded-lg border border-primary/20 bg-primary/5 p-4">
          {Object.entries(backtestParams).map(([key, value]) => (
            <div key={key} className="flex items-center gap-2.5">
              <label className="text-xs text-muted-foreground min-w-0 flex-1 truncate">
                {t(`strategyResearch.param_${key}`)}
              </label>
              <input type="number" step="any" value={value}
                onChange={(e) => { const v = parseFloat(e.target.value); if (!isNaN(v)) setBacktestParams((prev) => prev ? { ...prev, [key]: v } : null); }}
                className="w-20 rounded border border-border bg-card px-2 py-1 text-xs font-mono text-foreground focus:border-primary/50 focus:outline-none focus:ring-1 focus:ring-primary/20" />
            </div>
          ))}
        </div>
      )}

      {/* Command bar — unified controls */}
      <div className="flex flex-wrap items-center gap-2 rounded-lg border border-border bg-card px-3 py-2">
        <select value={tradingDay} onChange={(e) => setTradingDay(e.target.value)}
          className="rounded border-0 bg-muted/50 px-2.5 py-1.5 text-xs font-mono text-foreground focus:outline-none focus:ring-1 focus:ring-primary/30">
          {availableDays.map((d) => <option key={d} value={d}>{d}</option>)}
        </select>

        <div className="h-5 w-px bg-border" />

        <div className="flex rounded bg-muted/50 p-0.5">
          {(["industry", "concept"] as SectorType[]).map((st) => (
            <button key={st}
              onClick={() => { setSectorType(st); setSelectedSector(""); setSectorSearch(""); setMembers([]); }}
              className={`px-2.5 py-1 text-xs rounded-sm font-medium transition-colors ${
                sectorType === st ? "bg-card text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"
              }`}>
              {t(`strategyResearch.${st}`)}
            </button>
          ))}
        </div>

        <div className="relative">
          <div className="relative">
            <Search size={12} className="absolute left-2 top-1/2 -translate-y-1/2 text-muted-foreground pointer-events-none" />
            <input type="text" value={sectorSearch}
              onChange={(e) => { setSectorSearch(e.target.value); setShowSectorDropdown(true); }}
              onFocus={() => setShowSectorDropdown(true)}
              onBlur={() => setTimeout(() => setShowSectorDropdown(false), 150)}
              placeholder="搜索板块..."
              className="w-36 rounded border-0 bg-muted/50 pl-7 pr-2 py-1.5 text-xs text-foreground placeholder:text-muted-foreground/60 focus:outline-none focus:ring-1 focus:ring-primary/30" />
          </div>
          {showSectorDropdown && filteredSectors.length > 0 && (
            <div className="absolute z-10 mt-1 w-64 max-h-56 overflow-y-auto rounded-lg border border-border bg-card shadow-lg py-1">
              {filteredSectors.map((s) => (
                <button key={s.bk_code} type="button"
                  className={`w-full text-left px-3 py-1.5 text-xs hover:bg-muted transition-colors flex justify-between items-center ${
                    selectedSector === s.bk_code ? "bg-primary/5 text-primary" : "text-foreground"
                  }`}
                  onMouseDown={() => handleSectorSelect(s.bk_code, s.bk_name)}>
                  <span className="font-medium">{s.bk_name}</span>
                  <span className="text-[10px] text-muted-foreground font-mono">{s.bk_code}</span>
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="h-5 w-px bg-border" />

        <div className="flex rounded bg-muted/50 p-0.5">
          {DATE_PRESETS.map((p) => (
            <button key={p} onClick={() => setDatePreset(p)}
              className={`px-2 py-1 text-xs rounded-sm font-medium transition-colors ${
                datePreset === p ? "bg-card text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"
              }`}>
              {p === "custom" ? t("strategyResearch.customRange") : p}
            </button>
          ))}
        </div>

        {datePreset === "custom" && (
          <>
            <input type="date" value={customStart} onChange={(e) => setCustomStart(e.target.value)}
              className="rounded border-0 bg-muted/50 px-2 py-1.5 text-xs font-mono text-foreground focus:outline-none focus:ring-1 focus:ring-primary/30 w-32" />
            <span className="text-xs text-muted-foreground">—</span>
            <input type="date" value={customEnd} onChange={(e) => setCustomEnd(e.target.value)}
              className="rounded border-0 bg-muted/50 px-2 py-1.5 text-xs font-mono text-foreground focus:outline-none focus:ring-1 focus:ring-primary/30 w-32" />
          </>
        )}

        <div className="flex-1" />

        <button onClick={handleStartBacktest} disabled={backtesting || !hasSelection}
          className={`inline-flex items-center gap-1.5 rounded-md px-4 py-1.5 text-xs font-semibold transition-all ${
            backtesting
              ? "bg-muted text-muted-foreground cursor-wait"
              : hasSelection
                ? "bg-primary text-primary-foreground hover:brightness-110 shadow-sm shadow-primary/20"
                : "bg-muted text-muted-foreground cursor-not-allowed"
          }`}>
          {backtesting ? (
            <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-muted-foreground/30 border-t-muted-foreground" />
          ) : (
            <Play size={13} />
          )}
          {backtesting ? t("strategyResearch.backtesting") : t("strategyResearch.startBacktest")}
        </button>
      </div>

      {/* Progress indicator */}
      {backtesting && progress && (
        <div className="flex items-center gap-3 rounded-lg border border-border bg-card px-4 py-2.5">
          <div className="flex-1 h-1 rounded-full bg-muted overflow-hidden">
            <div className="h-full rounded-full bg-primary transition-all duration-300 ease-out"
              style={{ width: `${(progress.done / progress.total) * 100}%` }} />
          </div>
          <span className="text-[11px] font-mono text-muted-foreground tabular-nums whitespace-nowrap">
            {progress.done}/{progress.total}
          </span>
        </div>
      )}

      {/* Constituent stocks */}
      {members.length > 0 && (
        <div className="rounded-lg border border-border overflow-hidden">
          <button onClick={() => setShowMembers(!showMembers)}
            className="flex w-full items-center justify-between px-4 py-2.5 bg-muted/30 hover:bg-muted/50 transition-colors select-none">
            <div className="flex items-center gap-3">
              <h2 className="text-xs font-semibold text-foreground tracking-wide uppercase">成分股</h2>
              <span className="text-[11px] tabular-nums text-muted-foreground">{members.length} 只</span>
              {selectedCodes.size > 0 && (
                <span className="text-[10px] font-medium text-primary bg-primary/10 rounded-full px-2 py-0.5">
                  已选 {selectedCodes.size}
                </span>
              )}
            </div>
            <div className="flex items-center gap-2">
              <span onClick={(e) => { e.stopPropagation(); toggleAll(); }}
                className="text-[10px] text-muted-foreground hover:text-foreground transition-colors px-2 py-0.5 rounded hover:bg-muted">
                {selectedCodes.size === members.length ? "取消全选" : "全选"}
              </span>
              {showMembers ? <ChevronUp size={14} className="text-muted-foreground" /> : <ChevronDown size={14} className="text-muted-foreground" />}
            </div>
          </button>
          {showMembers && (
            <>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead className="bg-muted/30">
                    <tr className="text-[10px] text-muted-foreground uppercase tracking-wider">
                      <th className="w-8 px-2 py-2"><input type="checkbox" checked={selectedCodes.size === members.length && members.length > 0} onChange={toggleAll} className="rounded" /></th>
                      <th className="px-2 py-2 text-left font-medium">代码</th>
                      <th className="px-2 py-2 text-left font-medium">名称</th>
                      <th className="px-2 py-2 text-right font-medium">最新价</th>
                      <th className="px-2 py-2 text-right font-medium">涨跌幅</th>
                      <th className="px-2 py-2 text-left font-medium">概念</th>
                      <th className="px-2 py-2 text-left font-medium">行业</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/50">
                    {pagedMembers.map((m) => {
                    const sel = selectedCodes.has(m.code);
                    return (
                      <tr key={m.code} onClick={() => toggleStock(m.code)}
                        className={`cursor-pointer transition-colors hover:bg-muted/40 ${sel ? "bg-primary/5 hover:bg-primary/8" : ""}`}>
                        <td className="px-2 py-1.5"><input type="checkbox" checked={sel} onChange={() => toggleStock(m.code)} className="rounded" /></td>
                        <td className="px-2 py-1.5 font-mono tabular-nums text-foreground/90">{m.code}</td>
                        <td className="px-2 py-1.5 text-foreground/90">{m.name}</td>
                        <td className="px-2 py-1.5 text-right font-mono tabular-nums">{m.price?.toFixed(2) || "—"}</td>
                        <td className={`px-2 py-1.5 text-right font-mono tabular-nums ${(m.change_pct ?? 0) >= 0 ? "text-red-500" : "text-emerald-500"}`}>
                          {m.change_pct != null ? `${m.change_pct > 0 ? "+" : ""}${m.change_pct.toFixed(2)}%` : "—"}
                        </td>
                        <td className="max-w-[180px] truncate px-2 py-1.5 text-muted-foreground" title={m.concepts?.join(", ")}>
                          {m.concepts?.slice(0, 3).join(", ") || "—"}
                          {m.concepts && m.concepts.length > 3 ? <span className="text-[10px] text-muted-foreground/60"> +{m.concepts.length - 3}</span> : ""}
                        </td>
                        <td className="max-w-[140px] truncate px-2 py-1.5 text-muted-foreground" title={m.industries?.join(" → ")}>
                          {m.industries?.join(" → ") || "—"}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* Members pagination */}
              <div className="px-4 py-2.5 border-t border-border flex items-center justify-between text-xs text-muted-foreground">
                <div className="flex items-center gap-2">
                  <span>每页</span>
                  <select value={memberPageSize} onChange={(e) => { setMemberPageSize(Number(e.target.value)); setMemberPage(1); }}
                    className="border border-border rounded px-1.5 py-0.5 text-xs bg-card text-foreground">
                    {[20, 50, 100].map((n) => (<option key={n} value={n}>{n}</option>))}
                  </select>
                  <span>条</span>
                </div>
                <span>第 {safeMemberPage}/{totalMemberPages} 页，共 {members.length} 条</span>
                <div className="flex items-center gap-1">
                  <button onClick={() => setMemberPage(1)} disabled={safeMemberPage <= 1}
                    className="px-2 py-0.5 rounded border border-border text-xs hover:bg-muted transition disabled:opacity-30 disabled:cursor-not-allowed">首页</button>
                  <button onClick={() => setMemberPage((p) => Math.max(1, p - 1))} disabled={safeMemberPage <= 1}
                    className="px-2 py-0.5 rounded border border-border text-xs hover:bg-muted transition disabled:opacity-30 disabled:cursor-not-allowed">
                    <ChevronLeft size={12} />
                  </button>
                  <button onClick={() => setMemberPage((p) => Math.min(totalMemberPages, p + 1))} disabled={safeMemberPage >= totalMemberPages}
                    className="px-2 py-0.5 rounded border border-border text-xs hover:bg-muted transition disabled:opacity-30 disabled:cursor-not-allowed">
                    <ChevronRight size={12} />
                  </button>
                  <button onClick={() => setMemberPage(totalMemberPages)} disabled={safeMemberPage >= totalMemberPages}
                    className="px-2 py-0.5 rounded border border-border text-xs hover:bg-muted transition disabled:opacity-30 disabled:cursor-not-allowed">末页</button>
                </div>
              </div>
            </>
          )}
        </div>
      )}

      {loadingMembers && (
        <div className="flex items-center justify-center gap-2 py-8 text-xs text-muted-foreground">
          <span className="h-3 w-3 animate-spin rounded-full border-2 border-muted-foreground/30 border-t-muted-foreground" />
          加载成分股...
        </div>
      )}

      {/* Backtest results */}
      {results.length > 0 && (
        <div className="rounded-lg border border-border overflow-hidden">
          <button onClick={() => setShowResults(!showResults)}
            className="flex w-full items-center justify-between px-4 py-2.5 bg-muted/30 hover:bg-muted/50 transition-colors select-none">
            <div className="flex items-center gap-3">
              <h2 className="text-xs font-semibold text-foreground tracking-wide uppercase">回测结果</h2>
              <span className="text-[11px] tabular-nums text-muted-foreground">
                {resultStateFilter ? `${filteredResults.length}/` : ""}{results.length} 只
              </span>
              <span className="text-[10px] text-muted-foreground">
                平均胜率 {results.length > 0 ? `${(results.reduce((s, r) => s + r.win_rate, 0) / results.length * 100).toFixed(0)}%` : "—"}
              </span>
            </div>
            <div className="flex items-center gap-2" onClick={(e) => e.stopPropagation()}>
              {Object.keys(STATE_LABELS).map((st) => (
                <button key={st}
                  onClick={() => {
                    setResultStateFilter(resultStateFilter === st ? "" : st);
                    setResultPage(1);
                  }}
                  className={`text-[10px] px-2 py-0.5 rounded border transition-colors ${
                    resultStateFilter === st
                      ? "border-primary/30 bg-primary/10 text-primary"
                      : "border-border text-muted-foreground hover:border-muted-foreground/50"
                  }`}>
                  {STATE_LABELS[st]}
                </button>
              ))}
            </div>
            {showResults ? <ChevronUp size={14} className="text-muted-foreground" /> : <ChevronDown size={14} className="text-muted-foreground" />}
          </button>
          {showResults && (
            <>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead className="bg-muted/30">
                    <tr className="text-[10px] text-muted-foreground uppercase tracking-wider">
                      <th className="px-3 py-2 text-left font-medium">代码</th>
                      <th className="px-3 py-2 text-left font-medium">名称</th>
                      <th className="px-3 py-2 text-left font-medium cursor-pointer select-none hover:text-foreground transition-colors"
                        onClick={() => toggleResultSort("final_state")}>
                        <span className="inline-flex items-center gap-1">状态 {resultSortIcon("final_state")}</span>
                      </th>
                      <th className="px-3 py-2 text-right font-medium cursor-pointer select-none hover:text-foreground transition-colors"
                        onClick={() => toggleResultSort("trade_count")}>
                        <span className="inline-flex items-center gap-1">交易 {resultSortIcon("trade_count")}</span>
                      </th>
                      <th className="px-3 py-2 text-right font-medium cursor-pointer select-none hover:text-foreground transition-colors"
                        onClick={() => toggleResultSort("win_rate")}>
                        <span className="inline-flex items-center gap-1">胜率 {resultSortIcon("win_rate")}</span>
                      </th>
                      <th className="px-3 py-2 text-right font-medium">止跌K</th>
                      <th className="px-3 py-2 text-right font-medium">证伪K</th>
                      <th className="px-3 py-2 text-right font-medium cursor-pointer select-none hover:text-foreground transition-colors"
                        onClick={() => toggleResultSort("cumulative_return")}>
                        <span className="inline-flex items-center gap-1">累计收益 {resultSortIcon("cumulative_return")}</span>
                      </th>
                      <th className="px-3 py-2 text-center font-medium w-16">详情</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/50">
                    {pagedResults.map((r) => {
                      const isOpen = selectedResultCode === r.code;
                      return (
                        <>
                          <tr key={r.code}
                            onClick={() => setSelectedResultCode(isOpen ? null : r.code)}
                            className={`cursor-pointer transition-colors hover:bg-muted/40 ${isOpen ? "bg-primary/5 hover:bg-primary/8" : ""}`}>
                            <td className="px-3 py-2.5 font-mono tabular-nums font-medium">
                              <a href={getXueqiuUrl(r.code)} target="_blank" rel="noopener noreferrer"
                                onClick={(e) => e.stopPropagation()}
                                className="text-primary hover:underline">{r.code}</a>
                            </td>
                            <td className="px-3 py-2.5 text-xs truncate max-w-[80px]" title={codeToName[r.code] || r.name || ""}>
                              <a href={getXueqiuUrl(r.code)} target="_blank" rel="noopener noreferrer"
                                onClick={(e) => e.stopPropagation()}
                                className="text-primary/80 hover:text-primary hover:underline">
                                {codeToName[r.code] || r.name || r.code}
                              </a>
                            </td>
                            <td className="px-3 py-2.5">
                              {(() => {
                                const ds = r.final_state;
                                return (
                                  <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium text-white ${STATE_COLORS[ds] || "bg-slate-500"}`}>
                                    <span className={`h-1.5 w-1.5 rounded-full ${isOpen ? "bg-white" : "bg-white/60"}`} />
                                    {STATE_LABELS[ds] || ds}
                                  </span>
                                );
                              })()}
                            </td>
                            <td className="px-3 py-2.5 text-right tabular-nums font-mono">{r.trade_count}</td>
                            <td className={`px-3 py-2.5 text-right tabular-nums font-mono ${
                              r.win_rate >= 0.5 ? "text-emerald-500" : r.win_rate > 0 ? "text-amber-500" : "text-red-500"
                            }`}>{(r.win_rate * 100).toFixed(0)}%</td>
                            <td className="px-3 py-2.5 text-right tabular-nums font-mono text-muted-foreground">{r.bsk_count ?? "—"}</td>
                            <td className="px-3 py-2.5 text-right tabular-nums font-mono text-muted-foreground">{r.ck_count ?? "—"}</td>
                            <td className={`px-3 py-2.5 text-right tabular-nums font-mono font-medium ${
                              r.cumulative_return >= 0 ? "text-red-500" : "text-emerald-500"
                            }`}>{r.cumulative_return >= 0 ? "+" : ""}{(r.cumulative_return * 100).toFixed(2)}%</td>
                            <td className="px-3 py-2.5 text-center">
                              <span className={`inline-flex items-center justify-center rounded-md px-2 py-0.5 text-[10px] font-medium transition-colors ${
                                isOpen ? "bg-primary/10 text-primary" : "text-muted-foreground hover:bg-muted hover:text-foreground"
                              }`}>{isOpen ? "收起" : "展开"}</span>
                            </td>
                          </tr>
                          {isOpen && detailData && (
                            <tr key={`${r.code}-detail`}>
                              <td colSpan={9} className="px-4 py-3 bg-muted/15 border-t border-primary/10">
                                <DetailPanel data={detailData} onClose={() => setSelectedResultCode(null)} />
                              </td>
                            </tr>
                          )}
                        </>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              {/* Pagination */}
                <div className="px-4 py-2.5 border-t border-border flex items-center justify-between text-xs text-muted-foreground">
                  <div className="flex items-center gap-2">
                    <span>每页</span>
                    <select
                      value={resultPageSize}
                      onChange={(e) => { setResultPageSize(Number(e.target.value)); setResultPage(1); }}
                      className="border border-border rounded px-1.5 py-0.5 text-xs bg-card text-foreground"
                    >
                      {[20, 50, 100].map((n) => (<option key={n} value={n}>{n}</option>))}
                    </select>
                    <span>条</span>
                  </div>
                  <span>第 {safeResultPage}/{totalResultPages} 页，共 {results.length} 条</span>
                  <div className="flex items-center gap-1">
                    <button onClick={() => setResultPage(1)} disabled={safeResultPage <= 1}
                      className="px-2 py-0.5 rounded border border-border text-xs hover:bg-muted transition disabled:opacity-30 disabled:cursor-not-allowed">首页</button>
                    <button onClick={() => setResultPage((p) => Math.max(1, p - 1))} disabled={safeResultPage <= 1}
                      className="px-2 py-0.5 rounded border border-border text-xs hover:bg-muted transition disabled:opacity-30 disabled:cursor-not-allowed">
                      <ChevronLeft size={12} />
                    </button>
                    <button onClick={() => setResultPage((p) => Math.min(totalResultPages, p + 1))} disabled={safeResultPage >= totalResultPages}
                      className="px-2 py-0.5 rounded border border-border text-xs hover:bg-muted transition disabled:opacity-30 disabled:cursor-not-allowed">
                      <ChevronRight size={12} />
                    </button>
                    <button onClick={() => setResultPage(totalResultPages)} disabled={safeResultPage >= totalResultPages}
                      className="px-2 py-0.5 rounded border border-border text-xs hover:bg-muted transition disabled:opacity-30 disabled:cursor-not-allowed">末页</button>
                  </div>
                </div>
            </>
          )}
        </div>
      )}
      </>
      )}
    </div>
  );
}
