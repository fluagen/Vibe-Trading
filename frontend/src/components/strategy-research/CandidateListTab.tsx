import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { api, type CandidateItem } from "@/lib/api";

function getXueqiuUrl(code: string): string {
  const prefix = code.startsWith("6") ? "SH" : "SZ";
  return `https://xueqiu.com/S/${prefix}${code}`;
}

export function CandidateListTab() {
  const { t } = useTranslation();
  const [candidates, setCandidates] = useState<CandidateItem[]>([]);
  const [loading, setLoading] = useState(true);

  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);

  const fetchCandidates = async () => {
    setLoading(true);
    try {
      const data = await api.getCandidates();
      setCandidates(data.candidates || []);
    } catch {
      toast.error(t("strategyResearch.loadFailed"));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchCandidates();
  }, []);

  const totalPages = Math.max(1, Math.ceil(candidates.length / pageSize));
  const safePage = Math.min(page, totalPages);
  const paged = candidates.slice((safePage - 1) * pageSize, safePage * pageSize);

  const handleRemove = async (code: string) => {
    if (!window.confirm(t("strategyResearch.candidateRemoveConfirm"))) return;
    try {
      await api.removeCandidate(code);
      setCandidates((prev) => prev.filter((c) => c.code !== code));
      toast.success("已移除");
    } catch {
      toast.error(t("strategyResearch.loadFailed"));
    }
  };

  return (
    <div className="rounded-lg border border-border overflow-hidden">
      <div className="flex items-center justify-between px-4 py-2.5 bg-muted/30">
        <div className="flex items-center gap-3">
          <h2 className="text-xs font-semibold text-foreground tracking-wide uppercase">
            {t("strategyResearch.candidateTab")}
          </h2>
          <span className="text-[11px] tabular-nums text-muted-foreground">
            {candidates.length} 只
          </span>
        </div>
      </div>

      {loading ? (
        <div className="flex items-center justify-center gap-2 py-8 text-xs text-muted-foreground">
          <span className="h-3 w-3 animate-spin rounded-full border-2 border-muted-foreground/30 border-t-muted-foreground" />
          加载中...
        </div>
      ) : candidates.length === 0 ? (
        <div className="py-12 text-center text-xs text-muted-foreground">
          暂无候选股票，请在回测结果中点击"加候选"添加
        </div>
      ) : (
        <>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead className="bg-muted/30">
                <tr className="text-[10px] text-muted-foreground uppercase tracking-wider">
                  <th className="px-3 py-2 text-left font-medium">代码</th>
                  <th className="px-3 py-2 text-left font-medium">名称</th>
                  <th className="px-3 py-2 text-left font-medium">{t("strategyResearch.addedAt")}</th>
                  <th className="px-3 py-2 text-left font-medium">{t("strategyResearch.concept")}</th>
                  <th className="px-3 py-2 text-left font-medium">{t("strategyResearch.industry")}</th>
                  <th className="px-3 py-2 text-center font-medium w-16">操作</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/50">
                {paged.map((c) => (
                  <tr key={c.code} className="hover:bg-muted/40 transition-colors">
                    <td className="px-3 py-2.5 font-mono tabular-nums font-medium">
                      <a
                        href={getXueqiuUrl(c.code)}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-primary hover:underline"
                      >
                        {c.code}
                      </a>
                    </td>
                    <td className="px-3 py-2.5 text-xs">{c.name}</td>
                    <td className="px-3 py-2.5 text-muted-foreground">{c.added_at}</td>
                    <td
                      className="max-w-[180px] truncate px-3 py-2.5 text-muted-foreground"
                      title={c.concepts?.join(", ")}
                    >
                      {c.concepts?.slice(0, 3).join(", ") || "—"}
                      {c.concepts && c.concepts.length > 3 ? (
                        <span className="text-[10px] text-muted-foreground/60">
                          +{c.concepts.length - 3}
                        </span>
                      ) : (
                        ""
                      )}
                    </td>
                    <td
                      className="max-w-[140px] truncate px-3 py-2.5 text-muted-foreground"
                      title={c.industries?.join(" → ")}
                    >
                      {c.industries?.join(" → ") || "—"}
                    </td>
                    <td className="px-3 py-2.5 text-center">
                      <button
                        onClick={() => handleRemove(c.code)}
                        className="text-[10px] px-2 py-0.5 rounded border border-border text-muted-foreground hover:text-red-500 hover:border-red-500/30 transition-colors"
                      >
                        移除
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="px-4 py-2.5 border-t border-border flex items-center justify-between text-xs text-muted-foreground">
            <div className="flex items-center gap-2">
              <span>每页</span>
              <select
                value={pageSize}
                onChange={(e) => { setPageSize(Number(e.target.value)); setPage(1); }}
                className="border border-border rounded px-1.5 py-0.5 text-xs bg-card text-foreground"
              >
                {[20, 50, 100].map((n) => (<option key={n} value={n}>{n}</option>))}
              </select>
              <span>条</span>
            </div>
            <span>第 {safePage}/{totalPages} 页，共 {candidates.length} 条</span>
            <div className="flex items-center gap-1">
              <button onClick={() => setPage(1)} disabled={safePage <= 1}
                className="px-2 py-0.5 rounded border border-border text-xs hover:bg-muted transition disabled:opacity-30 disabled:cursor-not-allowed">首页</button>
              <button onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={safePage <= 1}
                className="px-2 py-0.5 rounded border border-border text-xs hover:bg-muted transition disabled:opacity-30 disabled:cursor-not-allowed">
                <ChevronLeft size={12} />
              </button>
              <button onClick={() => setPage((p) => Math.min(totalPages, p + 1))} disabled={safePage >= totalPages}
                className="px-2 py-0.5 rounded border border-border text-xs hover:bg-muted transition disabled:opacity-30 disabled:cursor-not-allowed">
                <ChevronRight size={12} />
              </button>
              <button onClick={() => setPage(totalPages)} disabled={safePage >= totalPages}
                className="px-2 py-0.5 rounded border border-border text-xs hover:bg-muted transition disabled:opacity-30 disabled:cursor-not-allowed">末页</button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
