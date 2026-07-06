import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Plus, Play, Trash2, RefreshCw, Upload } from "lucide-react";
import { cn } from "@/lib/utils";
import { api, type CandidateItem, type ScanResultItem, type WatchlistItem } from "@/lib/api";
import { toast } from "sonner";

export function OpportunityPool() {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState<"scan" | "watchlist">("scan");

  // Candidate pool state
  const [candidates, setCandidates] = useState<CandidateItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadingDefault, setLoadingDefault] = useState(false);
  const [newCode, setNewCode] = useState("");
  const [candidateSelection, setCandidateSelection] = useState<Set<string>>(new Set());

  // Scan state
  const [targetDate, setTargetDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [scanning, setScanning] = useState(false);
  const [scanProgress, setScanProgress] = useState<{ done: number; total: number; currentCode?: string } | null>(null);
  const [scanResults, setScanResults] = useState<ScanResultItem[]>([]);
  const scanAbortRef = useRef<AbortController | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      const result = await api.importCandidates(file);
      toast.success(t("opportunityPool.importResult", { added: result.added, invalid: result.invalid }));
      await loadCandidates();
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : String(err));
    }
    if (fileInputRef.current) fileInputRef.current.value = "";
  };
  const [selectedCodes, setSelectedCodes] = useState<Set<string>>(new Set());

  // Watchlist state
  const [watchlist, setWatchlist] = useState<WatchlistItem[]>([]);

  const loadWatchlist = useCallback(async () => {
    try {
      const data = await api.getWatchlist();
      setWatchlist(data);
    } catch { /* empty */ }
  }, []);

  useEffect(() => { loadWatchlist(); }, [loadWatchlist]);

  const handleAddToWatchlist = async () => {
    if (selectedCodes.size === 0) return;
    let added = 0;
    for (const code of selectedCodes) {
      const r = scanResults.find((s) => s.code === code);
      if (!r) continue;
      try {
        await api.addToWatchlist({
          code: r.code,
          name: r.name,
          state_at_add: r.state,
          position_at_add: r.position_signal,
          scan_job_id: "",
        });
        added++;
      } catch { /* skip */ }
    }
    setSelectedCodes(new Set());
    toast.success(t("opportunityPool.addedToWatchlist", { count: added }));
    await loadWatchlist();
  };

  // Refresh state
  const [refreshing, setRefreshing] = useState(false);
  const [refreshProgress, setRefreshProgress] = useState<{ done: number; total: number } | null>(null);

  const handleRefreshAll = async () => {
    setRefreshing(true);
    setRefreshProgress(null);
    try {
      const { job_id, error } = await api.refreshAllSignals();
      if (error || !job_id) { toast.error(error || "Failed"); setRefreshing(false); return; }

      const url = api.refreshStreamUrl(job_id);
      const es = new EventSource(url);
      es.addEventListener("progress", (e: MessageEvent) => {
        const d = JSON.parse(e.data);
        setRefreshProgress({ done: d.done, total: d.total });
      });
      es.addEventListener("done", () => { es.close(); setRefreshing(false); loadWatchlist(); });
      es.addEventListener("error", () => { es.close(); setRefreshing(false); });
      es.onerror = () => { es.close(); setRefreshing(false); };
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : String(err));
      setRefreshing(false);
    }
  };

  const handleBatchDelete = async () => {
    if (candidateSelection.size === 0) return;
    const codes = Array.from(candidateSelection);
    try {
      const result = await api.batchRemoveCandidates(codes);
      toast.success(t("opportunityPool.batchDeleteResult", { count: result.removed }));
      setCandidateSelection(new Set());
      await loadCandidates();
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : String(err));
    }
  };

  const handleRemoveWatchlist = async (code: string) => {
    try {
      await api.removeFromWatchlist(code);
      setWatchlist((prev) => prev.filter((w) => w.code !== code));
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : String(err));
    }
  };

  const loadCandidates = useCallback(async () => {
    try {
      const data = await api.listCandidates();
      setCandidates(data);
    } catch {
      // pool not yet loaded
    }
  }, []);

  useEffect(() => {
    loadCandidates();
  }, [loadCandidates]);

  const handleLoadDefault = async () => {
    setLoadingDefault(true);
    try {
      const result = await api.loadDefaultPool();
      toast.success(t("opportunityPool.defaultLoaded", { count: result.added }));
      if (result.errors.length > 0) {
        toast.error(result.errors.join("; "));
      }
      await loadCandidates();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      toast.error(msg);
    } finally {
      setLoadingDefault(false);
    }
  };

  const handleAdd = async () => {
    const code = newCode.trim();
    if (!code) return;
    setLoading(true);
    try {
      // Resolve name if available
      let resolvedName = code;
      let market = code.toUpperCase().endsWith(".SH") ? "SH"
        : code.toUpperCase().endsWith(".SZ") ? "SZ"
        : code.toUpperCase().endsWith(".BJ") ? "BJ"
        : code.startsWith("6") ? "SH"
        : "SZ";

      // If bare 6-digit code, try to resolve
      if (/^\d{6}$/.test(code) || !code.includes(".")) {
        try {
          const resolved = await api.resolveCode(code.replace(/\..*$/, ""));
          if (!("error" in resolved)) {
            resolvedName = resolved.name;
            market = resolved.market;
            setNewCode(resolved.code); // update input with full code
          }
        } catch { /* use bare code */ }
      }

      await api.addCandidates(
        [code.includes(".") ? code : `${code}.${market}`],
        [resolvedName],
        [market],
      );
      setNewCode("");
      await loadCandidates();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  };

  const handleRemove = async (code: string) => {
    try {
      await api.removeCandidate(code);
      setCandidates((prev) => prev.filter((c) => c.code !== code));
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      toast.error(msg);
    }
  };

  const handleStartScan = async () => {
    setScanning(true);
    setScanProgress({ done: 0, total: 0, currentCode: undefined });
    setScanResults([]);

    try {
      const selected = Array.from(candidateSelection);
      const body: Record<string, unknown> = { strategy: "up_trend_structure", target_date: targetDate };
      if (selected.length > 0) {
        body.codes = selected;
      }
      const { job_id, error } = await fetch("/opportunity-pool/scan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }).then(r => r.json());
      if (error || !job_id) {
        toast.error(error || "Failed to start scan");
        setScanning(false);
        return;
      }

      const url = api.scanStreamUrl(job_id);
      const eventSource = new EventSource(url);
      scanAbortRef.current = { abort: () => eventSource.close() } as AbortController;

      eventSource.addEventListener("progress", (e: MessageEvent) => {
        const data = JSON.parse(e.data);
        setScanProgress({ done: data.done, total: data.total, currentCode: data.current_code });
      });

      eventSource.addEventListener("result", (e: MessageEvent) => {
        const data = JSON.parse(e.data);
        const items: ScanResultItem[] = Object.values(data);
        setScanResults(items);
      });

      eventSource.addEventListener("done", () => {
        eventSource.close();
        setScanning(false);
        toast.success(t("opportunityPool.scanComplete", { count: scanResults.length || 0 }));
      });

      eventSource.addEventListener("error", (e: MessageEvent) => {
        try {
          const data = JSON.parse(e.data);
          toast.error(data.error || "Scan failed");
        } catch {
          // connection closed
        }
        eventSource.close();
        setScanning(false);
      });

      eventSource.onerror = () => {
        eventSource.close();
        setScanning(false);
      };
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      toast.error(msg);
      setScanning(false);
    }
  };

  const signalLabel = (signal: number): string => {
    if (signal >= 1.0) return "满仓";
    if (signal >= 0.67) return "加仓";
    if (signal >= 0.33) return "试探";
    if (signal < 0) return "离场";
    return "观望";
  };

  const signalColor = (signal: number): string => {
    if (signal >= 1.0) return "text-emerald-400";
    if (signal >= 0.67) return "text-green-400";
    if (signal >= 0.33) return "text-yellow-400";
    if (signal < 0) return "text-red-400";
    return "text-muted-foreground";
  };

  const stateColor = (state: string): string => {
    switch (state) {
      case "up_phase": return "bg-emerald-500/10 text-emerald-400";
      case "forming": return "bg-yellow-500/10 text-yellow-400";
      case "pullback": return "bg-orange-500/10 text-orange-400";
      case "breakdown": return "bg-red-500/10 text-red-400";
      default: return "bg-muted text-muted-foreground";
    }
  };

  const tabs = [
    { key: "scan" as const, label: t("opportunityPool.scanCenter") },
    { key: "watchlist" as const, label: t("opportunityPool.myWatchlist") },
  ];

  return (
    <div className="flex h-full flex-col gap-4 p-6">
      <h1 className="text-2xl font-bold">{t("layout.opportunityPool")}</h1>

      <div className="flex gap-2 border-b" role="tablist">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            role="tab"
            aria-selected={activeTab === tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={cn(
              "px-4 py-2 text-sm font-medium border-b-2 transition-colors",
              activeTab === tab.key
                ? "border-primary text-primary"
                : "border-transparent text-muted-foreground hover:text-foreground"
            )}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {activeTab === "scan" && (
        <div className="flex-1 space-y-4">
          {/* Toolbar */}
          <div className="flex items-center gap-3 flex-wrap">
            <button
              onClick={handleLoadDefault}
              disabled={loadingDefault}
              className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
            >
              <RefreshCw className={cn("h-4 w-4", loadingDefault && "animate-spin")} />
              {t("opportunityPool.loadDefault")}
            </button>
            <div className="h-6 w-px bg-border" />
            <form
              onSubmit={(e) => { e.preventDefault(); handleAdd(); }}
              className="flex items-center gap-2"
            >
              <input
                type="text"
                value={newCode}
                onChange={(e) => setNewCode(e.target.value)}
                placeholder={t("opportunityPool.addCodePlaceholder")}
                className="rounded-md border px-3 py-2 text-sm w-48"
              />
              <button
                type="submit"
                disabled={loading || !newCode.trim()}
                className="inline-flex items-center gap-1 rounded-md border px-3 py-2 text-sm hover:bg-accent disabled:opacity-50"
              >
                <Plus className="h-4 w-4" />
                {t("opportunityPool.add")}
              </button>
            </form>
            <input
              ref={fileInputRef}
              type="file"
              accept=".csv,.txt"
              onChange={handleImport}
              className="hidden"
            />
            <button
              onClick={() => fileInputRef.current?.click()}
              className="inline-flex items-center gap-1 rounded-md border px-3 py-2 text-sm text-muted-foreground hover:bg-accent"
            >
              <Upload className="h-4 w-4" />
              {t("opportunityPool.import")}
            </button>
            <div className="h-6 w-px bg-border" />
            <input
              type="date"
              value={targetDate}
              onChange={(e) => setTargetDate(e.target.value)}
              className="rounded-md border px-3 py-2 text-sm w-40"
            />
            <button
              onClick={handleStartScan}
              disabled={scanning || candidates.length === 0}
              className="inline-flex items-center gap-2 rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
            >
              <Play className="h-4 w-4" />
              {t("opportunityPool.startScan")}
              {candidateSelection.size > 0 && ` (${candidateSelection.size})`}
            </button>
            {candidateSelection.size > 0 && (
              <>
                <button
                  onClick={handleBatchDelete}
                  className="inline-flex items-center gap-1 rounded-md border border-red-200 px-3 py-2 text-sm text-red-500 hover:bg-red-50"
                >
                  <Trash2 className="h-4 w-4" />
                  {t("opportunityPool.deleteSelected")} ({candidateSelection.size})
                </button>
                <button
                  onClick={() => setCandidateSelection(new Set())}
                  className="text-xs text-muted-foreground hover:text-foreground"
                >
                  {t("opportunityPool.clearSelection")}
                </button>
              </>
            )}
            <span className="ml-auto text-xs text-muted-foreground">
              {t("opportunityPool.candidateCount", { count: candidates.length })}
            </span>
          </div>

          {/* Scan progress */}
          {scanProgress && (
            <div className="rounded-lg border p-4 space-y-2">
              <div className="flex items-center justify-between text-sm">
                <span>{t("opportunityPool.scanning")}</span>
                <span className="text-muted-foreground">
                  {scanProgress.done} / {scanProgress.total}
                </span>
              </div>
              <div className="h-2 rounded-full bg-muted overflow-hidden">
                <div
                  className="h-full rounded-full bg-emerald-500 transition-all duration-300"
                  style={{ width: `${scanProgress.total > 0 ? (scanProgress.done / scanProgress.total) * 100 : 0}%` }}
                />
              </div>
              {scanProgress.currentCode && (
                <p className="text-xs text-muted-foreground">
                  {t("opportunityPool.processing")}: {scanProgress.currentCode}
                </p>
              )}
            </div>
          )}

          {/* Scan results */}
          {scanResults.length > 0 && (
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-semibold">
                  {t("opportunityPool.scanResults")} ({scanResults.length})
                </h2>
                <button
                  onClick={handleAddToWatchlist}
                  disabled={selectedCodes.size === 0}
                  className="inline-flex items-center gap-1 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
                >
                  {t("opportunityPool.addToWatchlist")} {selectedCodes.size > 0 && `(${selectedCodes.size})`}
                </button>
              </div>
              <div className="overflow-auto rounded-lg border">
                <table className="w-full text-sm">
                  <thead className="bg-muted text-left">
                    <tr>
                      <th className="px-3 py-3 w-8">
                        <input
                          type="checkbox"
                          onChange={(e) => {
                            if (e.target.checked) setSelectedCodes(new Set(scanResults.map((s) => s.code)));
                            else setSelectedCodes(new Set());
                          }}
                          checked={selectedCodes.size === scanResults.length && scanResults.length > 0}
                        />
                      </th>
                      <th className="px-4 py-3 font-medium">{t("opportunityPool.code")}</th>
                      <th className="px-4 py-3 font-medium">{t("opportunityPool.state")}</th>
                      <th className="px-4 py-3 font-medium">{t("opportunityPool.signal")}</th>
                      <th className="px-4 py-3 font-medium">{t("opportunityPool.date")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {scanResults
                      .sort((a, b) => b.position_signal - a.position_signal)
                      .map((r) => (
                        <tr key={r.code} className="border-t hover:bg-muted/50">
                          <td className="px-3 py-2">
                            <input
                              type="checkbox"
                              checked={selectedCodes.has(r.code)}
                              onChange={() => {
                                const next = new Set(selectedCodes);
                                if (next.has(r.code)) next.delete(r.code);
                                else next.add(r.code);
                                setSelectedCodes(next);
                              }}
                            />
                          </td>
                          <td className="px-4 py-2 font-mono">{r.code}</td>
                          <td className="px-4 py-2">
                            <span className={cn("rounded px-2 py-0.5 text-xs font-medium", stateColor(r.state))}>
                              {r.state}
                            </span>
                          </td>
                          <td className={cn("px-4 py-2 font-medium", signalColor(r.position_signal))}>
                            {r.position_signal} ({signalLabel(r.position_signal)})
                          </td>
                          <td className="px-4 py-2 text-muted-foreground">{r.date}</td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Candidate table */}
          {!scanning && scanResults.length === 0 && candidates.length === 0 && (
            <div className="flex h-64 items-center justify-center rounded-lg border border-dashed text-muted-foreground">
              {t("opportunityPool.scanPlaceholder")}
            </div>
          )}
          {candidates.length > 0 && (
            <div className="overflow-auto rounded-lg border">
              <table className="w-full text-sm">
                <thead className="bg-muted text-left">
                  <tr>
                    <th className="px-3 py-3 w-8">
                      <input
                        type="checkbox"
                        onChange={(e) => {
                          if (e.target.checked) setCandidateSelection(new Set(candidates.map(c => c.code)));
                          else setCandidateSelection(new Set());
                        }}
                        checked={candidateSelection.size === candidates.length && candidates.length > 0}
                      />
                    </th>
                    <th className="px-4 py-3 font-medium">{t("opportunityPool.code")}</th>
                    <th className="px-4 py-3 font-medium">{t("opportunityPool.name")}</th>
                    <th className="px-4 py-3 font-medium">{t("opportunityPool.market")}</th>
                    <th className="px-4 py-3 font-medium">{t("opportunityPool.source")}</th>
                    <th className="px-4 py-3 font-medium w-16" />
                  </tr>
                </thead>
                <tbody>
                  {candidates.map((c) => (
                    <tr key={c.code} className="border-t hover:bg-muted/50">
                      <td className="px-3 py-2">
                        <input
                          type="checkbox"
                          checked={candidateSelection.has(c.code)}
                          onChange={() => {
                            const next = new Set(candidateSelection);
                            if (next.has(c.code)) next.delete(c.code);
                            else next.add(c.code);
                            setCandidateSelection(next);
                          }}
                        />
                      </td>
                      <td className="px-4 py-2 font-mono">{c.code}</td>
                      <td className="px-4 py-2">{c.name}</td>
                      <td className="px-4 py-2">{c.market}</td>
                      <td className="px-4 py-2 text-xs text-muted-foreground">{c.source}</td>
                      <td className="px-4 py-2">
                        <button
                          onClick={() => handleRemove(c.code)}
                          className="rounded p-1 text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {activeTab === "watchlist" && (
        <div className="flex-1 space-y-4">
          {watchlist.length > 0 && (
            <div className="flex items-center gap-3">
              <button
                onClick={handleRefreshAll}
                disabled={refreshing}
                className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
              >
                <RefreshCw className={cn("h-4 w-4", refreshing && "animate-spin")} />
                {t("opportunityPool.refreshSignals")}
              </button>
              {refreshProgress && (
                <span className="text-xs text-muted-foreground">
                  {t("opportunityPool.scanning")} {refreshProgress.done}/{refreshProgress.total}
                </span>
              )}
            </div>
          )}
          {watchlist.length === 0 ? (
            <div className="flex h-64 items-center justify-center rounded-lg border border-dashed text-muted-foreground">
              {t("opportunityPool.watchlistEmpty")}
            </div>
          ) : (
            <div className="overflow-auto rounded-lg border">
              <table className="w-full text-sm">
                <thead className="bg-muted text-left">
                  <tr>
                    <th className="px-4 py-3 font-medium">{t("opportunityPool.code")}</th>
                    <th className="px-4 py-3 font-medium">{t("opportunityPool.stateAtAdd")}</th>
                    <th className="px-4 py-3 font-medium">{t("opportunityPool.signalAtAdd")}</th>
                    <th className="px-4 py-3 font-medium">{t("opportunityPool.currentState")}</th>
                    <th className="px-4 py-3 font-medium">{t("opportunityPool.currentSignal")}</th>
                    <th className="px-4 py-3 font-medium">{t("opportunityPool.addedAt")}</th>
                    <th className="px-4 py-3 font-medium w-16" />
                  </tr>
                </thead>
                <tbody>
                  {watchlist.map((w) => (
                    <tr key={w.code} className={cn(
                      "border-t hover:bg-muted/50",
                      w.current_state && w.current_state !== w.state_at_add && "border-l-2 border-l-amber-400"
                    )}>
                      <td className="px-4 py-2 font-mono text-xs">{w.code}</td>
                      <td className="px-4 py-2">
                        <span className={cn("rounded px-2 py-0.5 text-xs font-medium", stateColor(w.state_at_add))}>
                          {w.state_at_add}
                        </span>
                      </td>
                      <td className={cn("px-4 py-2 font-medium text-xs", signalColor(w.position_at_add))}>
                        {w.position_at_add}
                      </td>
                      <td className="px-4 py-2">
                        {w.current_state ? (
                          <span className={cn("rounded px-2 py-0.5 text-xs font-medium", stateColor(w.current_state))}>
                            {w.current_state}
                          </span>
                        ) : (
                          <span className="text-muted-foreground text-xs">—</span>
                        )}
                      </td>
                      <td className={cn("px-4 py-2 font-medium text-xs", w.current_position !== undefined && w.current_position !== null ? signalColor(w.current_position) : "text-muted-foreground")}>
                        {w.current_position !== undefined && w.current_position !== null ? w.current_position : "—"}
                      </td>
                      <td className="px-4 py-2 text-muted-foreground text-xs">
                        {new Date(w.added_at).toLocaleDateString()}
                      </td>
                      <td className="px-4 py-2">
                        <button
                          onClick={() => handleRemoveWatchlist(w.code)}
                          className="rounded p-1 text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
