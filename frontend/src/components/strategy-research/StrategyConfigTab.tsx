import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { api, type StrategyConfigParams } from "@/lib/api";

interface ParamDef {
  key: keyof StrategyConfigParams;
  min: number;
  max: number;
  step: number;
  isInt: boolean;
}

const DEFAULTS: StrategyConfigParams = {
  up_phase_min_bars: 3,
  volume_surge_ratio: 1.5,
  big_bull_body_ratio: 0.6,
  inv_hammer_shadow_ratio: 1.5,
  close_above_prev_mid: 0.5,
  stop_loss_pct: 0.03,
  divergence_repair_bars: 1,
};

const ENTRY_PARAMS: ParamDef[] = [
  { key: "up_phase_min_bars", min: 2, max: 10, step: 1, isInt: true },
  { key: "volume_surge_ratio", min: 1.0, max: 5.0, step: 0.1, isInt: false },
  { key: "big_bull_body_ratio", min: 0.3, max: 0.9, step: 0.05, isInt: false },
  { key: "inv_hammer_shadow_ratio", min: 1.0, max: 5.0, step: 0.1, isInt: false },
  { key: "close_above_prev_mid", min: 0.3, max: 0.9, step: 0.05, isInt: false },
  { key: "divergence_repair_bars", min: 1, max: 5, step: 1, isInt: true },
];

const RISK_PARAMS: ParamDef[] = [
  { key: "stop_loss_pct", min: 0.01, max: 0.10, step: 0.005, isInt: false },
];

function fmtVal(v: number, isInt: boolean): string {
  if (isInt) return String(v);
  return v.toFixed(3).replace(/0+$/, "").replace(/\.$/, "");
}

export function StrategyConfigTab() {
  const { t } = useTranslation();

  const [strategies, setStrategies] = useState<string[]>([]);
  const [selectedStrategy, setSelectedStrategy] = useState("up_trend_structure");
  const [params, setParams] = useState<StrategyConfigParams>({ ...DEFAULTS });
  const [isDefault, setIsDefault] = useState(true);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api.getStrategyResearchStrategies()
      .then((list) => {
        setStrategies(list);
        if (list.length > 0 && !list.includes(selectedStrategy)) {
          setSelectedStrategy(list[0]);
        }
      })
      .catch(() => toast.error(t("strategyResearch.loadFailed")));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const loadConfig = useCallback(
    (strategy: string) => {
      setLoading(true);
      api
        .getStrategyConfig(strategy)
        .then((res) => {
          setParams({ ...DEFAULTS, ...res.params });
          setIsDefault(res.is_default);
        })
        .catch(() => {
          setParams({ ...DEFAULTS });
          setIsDefault(true);
        })
        .finally(() => setLoading(false));
    },
    [],
  );

  useEffect(() => {
    loadConfig(selectedStrategy);
  }, [selectedStrategy, loadConfig]);

  const updateParam = (key: keyof StrategyConfigParams, value: number) => {
    setParams((prev) => ({ ...prev, [key]: value }));
    setIsDefault(false);
  };

  const resetParam = (key: keyof StrategyConfigParams) => {
    setParams((prev) => ({ ...prev, [key]: DEFAULTS[key] }));
  };

  const handleSave = async () => {
    try {
      await api.saveStrategyConfig(selectedStrategy, params);
      setIsDefault(false);
      toast.success(t("strategyResearch.configSaved"));
    } catch {
      toast.error(t("strategyResearch.loadFailed"));
    }
  };

  const handleResetAll = async () => {
    if (!confirm(t("strategyResearch.resetConfirm"))) return;
    try {
      const res = await api.deleteStrategyConfig(selectedStrategy);
      setParams({ ...DEFAULTS, ...res.params });
      setIsDefault(true);
      toast.success(t("strategyResearch.configSaved"));
    } catch {
      setParams({ ...DEFAULTS });
      setIsDefault(true);
    }
  };

  const renderParamGroup = (title: string, defs: ParamDef[]) => (
    <div className="mb-4">
      <h3 className="mb-3 text-sm font-medium text-foreground">{title}</h3>
      <div className="grid grid-cols-2 gap-x-8 gap-y-4">
        {defs.map((d) => {
          const value = params[d.key];
          return (
            <div key={d.key} className="flex flex-col gap-1.5">
              <div className="flex items-center justify-between">
                <label className="text-xs text-muted-foreground">
                  {t(`strategyResearch.param_${d.key}`)}
                </label>
                <div className="flex items-center gap-1">
                  <input
                    type="number"
                    min={d.min}
                    max={d.max}
                    step={d.step}
                    value={value}
                    onChange={(e) => {
                      const v = parseFloat(e.target.value);
                      if (!isNaN(v)) updateParam(d.key, d.isInt ? Math.round(v) : v);
                    }}
                    className="w-16 rounded border border-border bg-card px-1.5 py-0.5 text-right text-xs text-foreground"
                  />
                  {value !== DEFAULTS[d.key] && (
                    <button
                      onClick={() => resetParam(d.key)}
                      className="text-xs text-muted-foreground hover:text-foreground"
                      title={t("strategyResearch.resetDefault")}
                    >
                      ↺
                    </button>
                  )}
                </div>
              </div>
              <input
                type="range"
                min={d.min}
                max={d.max}
                step={d.step}
                value={value}
                onChange={(e) => updateParam(d.key, parseFloat(e.target.value))}
                className="h-1.5 w-full cursor-pointer appearance-none rounded bg-muted accent-emerald-500"
              />
              <div className="flex justify-between text-[10px] text-slate-600">
                <span>{fmtVal(d.min, d.isInt)}</span>
                <span>{fmtVal(d.max, d.isInt)}</span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );

  return (
    <div className="flex flex-col gap-4">
      {/* Strategy selector */}
      <div className="flex items-center gap-3">
        <label className="text-xs text-muted-foreground">{t("strategyResearch.strategy")}</label>
        <select
          value={selectedStrategy}
          onChange={(e) => setSelectedStrategy(e.target.value)}
          className="rounded border border-border bg-card px-2 py-1 text-sm text-foreground"
        >
          {strategies.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </div>

      {loading ? (
        <div className="text-xs text-muted-foreground">Loading...</div>
      ) : (
        <>
          {renderParamGroup(t("strategyResearch.entryParams"), ENTRY_PARAMS)}
          {renderParamGroup(t("strategyResearch.riskParams"), RISK_PARAMS)}

          {/* Action buttons */}
          <div className="flex gap-3">
            <button
              onClick={handleSave}
              className="rounded bg-emerald-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-emerald-500"
            >
              {t("strategyResearch.saveConfig")}
            </button>
            <button
              onClick={handleResetAll}
              className="rounded border border-border px-4 py-1.5 text-sm text-muted-foreground hover:bg-card hover:text-foreground"
            >
              {t("strategyResearch.resetDefault")}
            </button>
            {!isDefault && (
              <span className="self-center text-xs text-amber-500">未保存的修改</span>
            )}
          </div>
        </>
      )}
    </div>
  );
}
