import { useState, useEffect, useCallback, useRef } from "react";
import { TrendingUp, RefreshCw, ChevronDown, ChevronUp, Hourglass, 
ChevronLeft, ChevronRight, ArrowUpDown, ArrowUp, ArrowDown } from "lucide-react";
import { api, type SentimentOverviewResponse, type SentimentBoardItem, type SectorDetailPoint, type SentimentBoardItemSimple } from "@/lib/api";
import { CrowdingChart } from "@/components/charts/CrowdingChart";

// ---- helpers ----

function fmtYi(value: number | null | undefined): string {
  if (value == null || value === 0) return "-";
  const yi = value;
  if (Math.abs(yi) >= 10000) return (yi / 10000).toFixed(2) + "万亿";
  return yi.toFixed(0) + "亿";
}

function fmtPct(value: number | null | undefined): string {
  if (value == null) return "-";
  return (value > 0 ? "+" : "") + value.toFixed(2) + "%";
}

function crowdingBadge(level: string | null | undefined) {
  const colors: Record<string, string> = {
    normal: "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400",
    elevated: "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400",
    high: "bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-400",
    extreme: "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400",
  };
  const labels: Record<string, string> = {
    normal: "正常",
    elevated: "偏高",
    high: "高位",
    extreme: "极端",
  };
  if (!level) return null;
  return (
    <span className={`px-1.5 py-0.5 rounded text-xs font-medium ${colors[level] || ""}`}>
      {labels[level] || level}
    </span>
  );
}

// ---- component ----

export function Sentiment() {
  const today = new Date().toISOString().slice(0, 10);
  const past = new Date(Date.now() - 10 * 864e5).toISOString().slice(0, 10);

  // overview
  const [overview, setOverview] = useState<SentimentOverviewResponse | null>(null);
  const [boardType, setBoardType] = useState<"industry" | "concept">("industry");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [overviewDate, setOverviewDate] = useState(today);
  const [collecting, setCollecting] = useState(false);
  const initialLoad = useRef(true);

  // table sort & pagination
  type SortField = "turnover" | "crowding_ratio" | "main_net_inflow" | "change_pct" | "is_favored";
  const [sortField, setSortField] = useState<SortField>("crowding_ratio");
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("desc");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);

  // detail
  const [selectedBoard, setSelectedBoard] = useState<SentimentBoardItem | null>(null);
  const [detailData, setDetailData] = useState<SectorDetailPoint[]>([]);
  const [detailLoading, setDetailLoading] = useState(false);

  // history
  const [histStart, setHistStart] = useState(past);
  const [histEnd, setHistEnd] = useState(today);
  const [histCode, setHistCode] = useState("");
  const [histData, setHistData] = useState<SectorDetailPoint[]>([]);
  const [histName, setHistName] = useState("");
  const [histLoading, setHistLoading] = useState(false);

  // board autocomplete (from /sentiment/boards)
  const [allBoards, setAllBoards] = useState<SentimentBoardItemSimple[]>([]);
  const [boardSearch, setBoardSearch] = useState("");
  const [showDropdown, setShowDropdown] = useState(false);

  // load board list for autocomplete (on mount + boardType change)
  useEffect(() => {
    api.getSentimentBoards({ board_type: boardType }).then((data) => {
      if (data.ok) setAllBoards(data.boards);
    }).catch(() => {});
  }, [boardType]);

  const filteredBoards = boardSearch
    ? allBoards.filter((b) => b.bk_name.toLowerCase().includes(boardSearch.toLowerCase())).slice(0, 10)
    : allBoards.slice(0, 10);

  // ---- actions ----

  const loadOverview = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params: { board_type: string; top_n: number; date?: string } = { board_type: boardType, top_n: 20 };
      if (!initialLoad.current) {
        params.date = overviewDate;
      }
      const data = await api.getSentimentOverview(params);
      if (data.ok) {
        setOverview(data);
        if (initialLoad.current) {
          setOverviewDate(data.data_date);
          initialLoad.current = false;
        }
      } else {
        setError((data as unknown as { error?: string }).error || "加载失败");
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "网络错误");
    } finally {
      setLoading(false);
    }
  }, [boardType, overviewDate]);

  // load overview when date or boardType changes
  useEffect(() => { loadOverview(); }, [loadOverview]);

  const doCollect = useCallback(async () => {
    setCollecting(true);
    setError(null);
    try {
      const result = await api.collectSentiment({ date: overviewDate });
      if (result.ok) {
        await loadOverview();
      } else {
        setError(result.error || "采集失败");
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "采集失败");
    } finally {
      setCollecting(false);
    }
  }, [overviewDate, loadOverview]);

  const loadDetail = useCallback(async (board: SentimentBoardItem) => {
    setSelectedBoard(board);
    setDetailLoading(true);
    try {
      const data = await api.getSectorDetail({ board_code: board.board_code, days: 20, board_type: boardType, date: overviewDate });
      if (data.ok) setDetailData(data.data);
    } catch { /* ignore */ }
    finally { setDetailLoading(false); }
  }, [boardType, overviewDate]);

  const loadHistory = useCallback(async () => {
    if (!histCode) return;
    setHistLoading(true);
    try {
      const data = await api.getSentimentHistory({ board_code: histCode, start_date: histStart, end_date: histEnd, board_type: boardType });
      if (data.ok) { setHistData(data.data); setHistName(data.board_name); }
    } catch { /* ignore */ }
    finally { setHistLoading(false); }
  }, [histCode, histStart, histEnd, boardType]);

  const favoredCount = overview?.all_sectors?.filter((b) => b.is_favored).length ?? 0;
  const hasData = overview !== null && overview.all_sectors && overview.all_sectors.length > 0;

  // sort + paginate
  const toggleSort = (field: SortField) => {
    if (sortField === field) {
      setSortOrder((prev: "asc" | "desc") => (prev === "desc" ? "asc" : "desc"));
    } else {
      setSortField(field);
      setSortOrder(field === "is_favored" ? "desc" : "desc");
    }
    setPage(1);
  };

  const sortIcon = (field: SortField) => {
    if (sortField !== field) return <ArrowUpDown className="h-3 w-3 text-muted-foreground/50" />;
    return sortOrder === "desc"
      ? <ArrowDown className="h-3 w-3 text-primary" />
      : <ArrowUp className="h-3 w-3 text-primary" />;
  };

  const sortedSectors = (() => {
    if (!overview?.all_sectors) return [];
    const list = [...overview.all_sectors];
    const dir = sortOrder === "desc" ? -1 : 1;
    list.sort((a, b) => {
      if (sortField === "is_favored") {
        const va = a.is_favored === true ? 1 : a.is_favored === false ? 0 : -1;
        const vb = b.is_favored === true ? 1 : b.is_favored === false ? 0 : -1;
        return (va - vb) * dir;
      }
      const va = a[sortField];
      const vb = b[sortField];
      if (va == null && vb == null) return 0;
      if (va == null) return 1;
      if (vb == null) return -1;
      return (va - vb) * dir;
    });
    return list;
  })();

  const totalPages = Math.max(1, Math.ceil((overview?.total_count || 0) / pageSize));
  const safePage = Math.min(page, totalPages);
  const pagedSectors = sortedSectors.slice((safePage - 1) * pageSize, safePage * pageSize);

  // reset page when date or boardType changes
  useEffect(() => { setPage(1); }, [overviewDate, boardType]);

  // ---- render ----

  return (
    <div className="flex flex-col gap-6 p-6 max-w-6xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <TrendingUp className="h-6 w-6 text-primary" />
          <h1 className="text-2xl font-bold">市场情绪</h1>
          <div className="flex items-center gap-1 ml-4">
            {(["industry", "concept"] as const).map((t) => (
              <button key={t} onClick={() => setBoardType(t)}
                className={`px-3 py-1 rounded text-sm font-medium transition ${
                  boardType === t ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground hover:bg-muted/80"
                }`}
              >
                {t === "industry" ? "行业板块" : "概念板块"}
              </button>
            ))}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => overview?.prev_trade_date && setOverviewDate(overview.prev_trade_date)}
            disabled={!overview?.prev_trade_date}
            className="inline-flex items-center gap-1 px-2 py-1.5 rounded-lg border text-sm hover:bg-muted transition disabled:opacity-30 disabled:cursor-not-allowed"
            title="上个交易日"
          >
            <ChevronLeft className="h-4 w-4" />上个交易日
          </button>
          <input
            type="date"
            value={overviewDate}
            onChange={(e) => setOverviewDate(e.target.value)}
            className="border rounded px-2 py-1.5 text-sm bg-background"
          />
          <button
            onClick={() => overview?.next_trade_date && setOverviewDate(overview.next_trade_date)}
            disabled={!overview?.next_trade_date}
            className="inline-flex items-center gap-1 px-2 py-1.5 rounded-lg border text-sm hover:bg-muted transition disabled:opacity-30 disabled:cursor-not-allowed"
            title="下个交易日"
          >
            下个交易日<ChevronRight className="h-4 w-4" />
          </button>
          <button onClick={doCollect} disabled={collecting}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-sm bg-primary text-primary-foreground hover:opacity-90 transition disabled:opacity-50">
            <Hourglass className={`h-4 w-4 ${collecting ? "animate-spin" : ""}`} />
            {collecting ? "采集中..." : "采集数据"}
          </button>
          <button onClick={loadOverview} disabled={loading}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-sm hover:bg-muted transition">
            <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />刷新
          </button>
        </div>
      </div>

      {error && (
        <div className="border border-red-200 bg-red-50 dark:bg-red-950/20 rounded-lg p-4 text-sm text-red-700 dark:text-red-400">
          {error}
        </div>
      )}

      {/* Empty state */}
      {!hasData && !loading && !error && (
        <div className="border rounded-lg p-12 text-center text-muted-foreground space-y-2">
          <p className="text-lg font-medium">暂无缓存数据</p>
          <p className="text-sm">请选择日期后点击"采集数据"按钮，从同花顺 iwencai 拉取市场数据</p>
        </div>
      )}

      {/* Overview cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="border rounded-lg p-4 space-y-1">
          <div className="text-xs text-muted-foreground">全市场成交额</div>
          <div className="text-2xl font-bold">{overview ? fmtYi(overview.total_market_turnover_billion) : "-"}</div>
          <div className="text-xs text-muted-foreground">
            {overview ? `沪 ${fmtYi(overview.sh_turnover_billion)}  深 ${fmtYi(overview.sz_turnover_billion)}` : "-"}
          </div>
          <div className="text-xs text-muted-foreground">数据日期: {overview?.data_date || overviewDate}</div>
        </div>
        <div className="border rounded-lg p-4 space-y-1">
          <div className="text-xs text-muted-foreground">最高拥挤板块</div>
          {overview?.top_by_crowding?.[0] ? (
            <><div className="text-2xl font-bold truncate">{overview.top_by_crowding[0].board_name}</div>
              <div className="flex items-center gap-2">
                <span className="text-lg font-semibold">{overview.top_by_crowding[0].crowding_ratio?.toFixed(1)}%</span>
                {crowdingBadge(overview.top_by_crowding[0].crowding_level)}
              </div></>
          ) : <div className="text-2xl font-bold text-muted-foreground">-</div>}
        </div>
        <div className="border rounded-lg p-4 space-y-1">
          <div className="text-xs text-muted-foreground">主力资金方向</div>
          {overview?.top_by_inflow?.[0] ? (
            <><div className="text-2xl font-bold truncate">{overview.top_by_inflow[0].board_name}</div>
              <div className={`text-lg font-semibold flex items-center gap-1 ${(overview.top_by_inflow[0].main_net_inflow ?? 0) >= 0 ? "text-red-600 dark:text-red-400" : "text-green-600 dark:text-green-400"}`}>
                {(overview.top_by_inflow[0].main_net_inflow ?? 0) >= 0 ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                {fmtYi(overview.top_by_inflow[0].main_net_inflow)}
              </div></>
          ) : <div className="text-2xl font-bold text-muted-foreground">-</div>}
        </div>
        <div className="border rounded-lg p-4 space-y-1">
          <div className="text-xs text-muted-foreground">资金偏好信号</div>
          <div className="text-2xl font-bold">{favoredCount} 个</div>
          <div className="text-xs text-muted-foreground">板块获资金持续青睐</div>
        </div>
      </div>

      {/* Crowding table */}
      <div className="border rounded-lg overflow-hidden">
        <div className="px-4 py-3 border-b bg-muted/50 flex items-center justify-between">
          <h2 className="font-semibold text-sm">板块拥挤度明细</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-muted/30">
              <tr>
                <th className="px-4 py-2 text-left font-medium">板块名称</th>
                {([
                  ["turnover", "成交额"],
                  ["crowding_ratio", "拥挤度比率"],
                  ["main_net_inflow", "主力净流入"],
                  ["change_pct", "涨跌幅"],
                ] as [SortField, string][]).map(([field, label]) => (
                  <th key={field} className="px-4 py-2 text-right font-medium cursor-pointer select-none hover:bg-muted/50 transition" onClick={() => toggleSort(field)}>
                    <span className="inline-flex items-center justify-end gap-1">{label}{sortIcon(field)}</span>
                  </th>
                ))}
                <th className="px-4 py-2 text-center font-medium cursor-pointer select-none hover:bg-muted/50 transition" onClick={() => toggleSort("is_favored")}>
                  <span className="inline-flex items-center justify-center gap-1">资金偏好{sortIcon("is_favored")}</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {pagedSectors.map((b) => {
                const cr = b.crowding_ratio ?? 0;
                const barColor = cr >= 16 ? "#ef4444" : cr >= 14 ? "#f97316" : cr >= 10 ? "#eab308" : "#22c55e";
                return (
                  <tr key={b.board_code} onClick={() => loadDetail(b)}
                    className={`border-t cursor-pointer hover:bg-muted/50 transition ${selectedBoard?.board_code === b.board_code ? "bg-primary/5" : ""}`}>
                    <td className="px-4 py-2.5 font-medium">{b.board_name}</td>
                    <td className="px-4 py-2.5 text-right tabular-nums">{fmtYi(b.turnover)}</td>
                    <td className="px-4 py-2.5 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <div className="w-16 h-1.5 bg-muted rounded-full overflow-hidden">
                          <div className="h-full rounded-full" style={{ width: `${Math.min(cr / 20 * 100, 100)}%`, backgroundColor: barColor }} />
                        </div>
                        <span className="tabular-nums w-14 text-right">{b.crowding_ratio?.toFixed(1) ?? "-"}%</span>
                        {crowdingBadge(b.crowding_level)}
                      </div>
                    </td>
                    <td className={`px-4 py-2.5 text-right tabular-nums ${(b.main_net_inflow ?? 0) >= 0 ? "text-red-600 dark:text-red-400" : "text-green-600 dark:text-green-400"}`}>
                      {fmtYi(b.main_net_inflow)}
                    </td>
                    <td className={`px-4 py-2.5 text-right tabular-nums ${(b.change_pct ?? 0) >= 0 ? "text-red-600 dark:text-red-400" : "text-green-600 dark:text-green-400"}`}>
                      {fmtPct(b.change_pct)}
                    </td>
                    <td className="px-4 py-2.5 text-center">
                      {b.is_favored
                        ? <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-xs bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400">★ {b.consecutive_inflow_days}日</span>
                        : <span className="text-muted-foreground">-</span>}
                    </td>
                  </tr>
                );
              })}
              {pagedSectors.length === 0 && !loading && (
                <tr><td colSpan={6} className="px-4 py-8 text-center text-muted-foreground">暂无数据</td></tr>
              )}
              {loading && (
                <tr><td colSpan={6} className="px-4 py-8 text-center text-muted-foreground"><RefreshCw className="h-4 w-4 inline animate-spin mr-2" />加载中...</td></tr>
              )}
            </tbody>
          </table>
        </div>
        {/* Pagination */}
        {hasData && totalPages > 0 && (
          <div className="px-4 py-2.5 border-t flex items-center justify-between text-sm text-muted-foreground">
            <div className="flex items-center gap-2">
              <span>每页</span>
              <select
                value={pageSize}
                onChange={(e) => { setPageSize(Number((e.target as HTMLSelectElement).value)); setPage(1); }}
                className="border rounded px-1.5 py-0.5 text-sm bg-background"
              >
                {[20, 50, 100].map((n) => (<option key={n} value={n}>{n}</option>))}
              </select>
              <span>条</span>
            </div>
            <div className="flex items-center gap-1">
              <span>第 {safePage}/{totalPages} 页，共 {overview?.total_count ?? 0} 条</span>
            </div>
            <div className="flex items-center gap-1">
              <button onClick={() => setPage(1)} disabled={safePage <= 1}
                className="px-2 py-0.5 rounded border text-sm hover:bg-muted transition disabled:opacity-30 disabled:cursor-not-allowed">首页</button>
              <button onClick={() => setPage((p: number) => Math.max(1, p - 1))} disabled={safePage <= 1}
                className="px-2 py-0.5 rounded border text-sm hover:bg-muted transition disabled:opacity-30 disabled:cursor-not-allowed">
                <ChevronLeft className="h-3 w-3" />
              </button>
              <button onClick={() => setPage((p: number) => Math.min(totalPages, p + 1))} disabled={safePage >= totalPages}
                className="px-2 py-0.5 rounded border text-sm hover:bg-muted transition disabled:opacity-30 disabled:cursor-not-allowed">
                <ChevronRight className="h-3 w-3" />
              </button>
              <button onClick={() => setPage(totalPages)} disabled={safePage >= totalPages}
                className="px-2 py-0.5 rounded border text-sm hover:bg-muted transition disabled:opacity-30 disabled:cursor-not-allowed">末页</button>
            </div>
          </div>
        )}
      </div>

      {/* Detail panel */}
      {selectedBoard && (
        <div className="border rounded-lg p-4 space-y-4">
          <h2 className="font-semibold text-sm">板块详情: {selectedBoard.board_name} ({selectedBoard.board_code})</h2>
          {detailLoading ? (
            <div className="flex items-center justify-center py-12 text-muted-foreground"><RefreshCw className="h-4 w-4 animate-spin mr-2" />加载中...</div>
          ) : detailData.length > 0 ? (
            <>
              <div className="grid grid-cols-2 md:grid-cols-5 gap-3 text-sm">
                {[
                  ["当前拥挤度", detailData[detailData.length - 1]?.crowding_ratio?.toFixed(1) + "%"],
                  ["5日均拥挤度", (detailData.slice(-5).reduce((s, d) => s + (d.crowding_ratio ?? 0), 0) / 5).toFixed(1) + "%"],
                  ["今日净流入", fmtYi(detailData[detailData.length - 1]?.main_net_inflow_billion)],
                  ["全市场成交额", fmtYi(detailData[detailData.length - 1]?.total_market_turnover_billion)],
                  ["连续流入", (() => { let c = 0; for (let i = detailData.length - 1; i >= 0 && (detailData[i]?.main_net_inflow ?? 0) > 0; i--) c++; return c ? c + "日" : "-"; })()],
                ].map(([label, value]) => (
                  <div key={label} className="border rounded p-2 text-center">
                    <div className="text-xs text-muted-foreground">{label}</div>
                    <div className="font-bold text-lg">{value}</div>
                  </div>
                ))}
              </div>
              <CrowdingChart data={detailData} boardName={selectedBoard.board_name} />
            </>
          ) : <div className="py-8 text-center text-muted-foreground text-sm">暂无详情数据</div>}
        </div>
      )}

      {/* History query */}
      <div className="border rounded-lg p-4 space-y-4">
        <h2 className="font-semibold text-sm">历史查询</h2>
        <div className="flex flex-wrap items-end gap-3">
          <div className="space-y-1"><label className="text-xs text-muted-foreground">开始日期</label>
            <input type="date" value={histStart} onChange={(e) => setHistStart(e.target.value)} className="border rounded px-2 py-1.5 text-sm bg-background" /></div>
          <div className="space-y-1"><label className="text-xs text-muted-foreground">结束日期</label>
            <input type="date" value={histEnd} onChange={(e) => setHistEnd(e.target.value)} className="border rounded px-2 py-1.5 text-sm bg-background" /></div>
          <div className="space-y-1 relative">
            <label className="text-xs text-muted-foreground">板块名称</label>
            <input
              type="text"
              value={boardSearch}
              onChange={(e) => { setBoardSearch(e.target.value); setShowDropdown(true); }}
              onFocus={() => setShowDropdown(true)}
              onBlur={() => setTimeout(() => setShowDropdown(false), 150)}
              placeholder="搜索板块名称..."
              className="border rounded px-2 py-1.5 text-sm bg-background w-44"
            />
            {showDropdown && filteredBoards.length > 0 && (
              <div className="absolute z-10 mt-0.5 w-64 max-h-48 overflow-y-auto border rounded bg-popover shadow-lg">
                {filteredBoards.map((b) => (
                  <button
                    key={b.bk_code}
                    type="button"
                    className="w-full text-left px-3 py-1.5 text-sm hover:bg-muted transition flex justify-between items-center"
                    onMouseDown={() => {
                      setHistCode(b.bk_code);
                      setBoardSearch(b.bk_name);
                      setHistName(b.bk_name);
                      setShowDropdown(false);
                    }}
                  >
                    <span>{b.bk_name}</span>
                    <span className="text-xs text-muted-foreground font-mono">{b.bk_code}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
          <button onClick={loadHistory} disabled={histLoading || !histCode}
            className="px-4 py-1.5 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:opacity-90 transition disabled:opacity-50">
            {histLoading ? "查询中..." : "查询"}
          </button>
        </div>
        {histData.length > 0 && (
          <div className="space-y-3">
            <div className="grid grid-cols-3 gap-3 text-sm">
              {[
                ["区间交易日", histData.length + "天"],
                ["区间全市场日均成交", fmtYi(histData.reduce((s, d) => s + (d.total_market_turnover ?? 0), 0) / histData.length)],
                ["首日全市场成交", fmtYi(histData[0]?.total_market_turnover)],
              ].map(([label, value]) => (
                <div key={label} className="border rounded p-2 text-center">
                  <div className="text-xs text-muted-foreground">{label}</div>
                  <div className="font-bold">{value}</div>
                </div>
              ))}
            </div>
            <CrowdingChart data={histData} boardName={histName || histCode} />
          </div>
        )}
      </div>

      {/* Disclaimer */}
      <div className="text-xs text-muted-foreground text-center py-4 border-t">
        本分析仅基于公开交易数据的拥挤度指标，不构成投资建议。市场有风险，投资需谨慎。
      </div>
    </div>
  );
}
