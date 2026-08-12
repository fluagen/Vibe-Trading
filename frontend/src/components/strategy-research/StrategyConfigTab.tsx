import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { api, type StrategyConfigParams } from "@/lib/api";

interface ParamDef {
  key: string;
  min: number;
  max: number;
  step: number;
  isInt: boolean;
}

interface ParamGroup {
  title: string;
  params: ParamDef[];
}

const UP_TREND_DEFAULTS: StrategyConfigParams = {
  up_phase_min_bars: 3,
  volume_surge_ratio: 1.5,
  big_bull_body_ratio: 0.6,
  inv_hammer_shadow_ratio: 1.1,
  close_above_prev_mid: 0.5,
  stop_loss_pct: 0.03,
  divergence_repair_bars: 1,
};

const UP_TREND_GROUPS: ParamGroup[] = [
  {
    title: "entryParams",
    params: [
      { key: "up_phase_min_bars", min: 2, max: 10, step: 1, isInt: true },
      { key: "volume_surge_ratio", min: 1.0, max: 5.0, step: 0.1, isInt: false },
      { key: "big_bull_body_ratio", min: 0.3, max: 0.9, step: 0.05, isInt: false },
      { key: "inv_hammer_shadow_ratio", min: 1.0, max: 5.0, step: 0.1, isInt: false },
      { key: "close_above_prev_mid", min: 0.3, max: 0.9, step: 0.05, isInt: false },
      { key: "divergence_repair_bars", min: 1, max: 5, step: 1, isInt: true },
    ],
  },
  {
    title: "riskParams",
    params: [
      { key: "stop_loss_pct", min: 0.01, max: 0.10, step: 0.005, isInt: false },
    ],
  },
];

const NODE_TRADING_DEFAULTS: StrategyConfigParams = {
  r_s5: 9.0, cv_s5: 0.4, r_s4: 6.0, rs_s4: 1.1,
  r_s3_lower: 4.0, r_s3_upper: 6.0, cv_s3: 0.3,
  reversal_vol_ratio: 1.0, s2_reversal_r_min: 2.5,
  support_ma_tolerance: 0.005, s1_breakout_vol_ratio: 1.5,
  support_s3_size: 0.5, support_s4_size: 0.3,
  hard_stop_pct: 0.05, reversal_node_fail_days: 3,
};

const NODE_TRADING_GROUPS: ParamGroup[] = [
  {
    title: "stageThresholds",
    params: [
      { key: "r_s3_lower", min: 1.0, max: 10.0, step: 0.5, isInt: false },
      { key: "r_s3_upper", min: 3.0, max: 15.0, step: 0.5, isInt: false },
      { key: "r_s4", min: 3.0, max: 15.0, step: 0.5, isInt: false },
      { key: "r_s5", min: 5.0, max: 20.0, step: 0.5, isInt: false },
      { key: "cv_s3", min: 0.1, max: 0.8, step: 0.05, isInt: false },
      { key: "cv_s5", min: 0.2, max: 1.0, step: 0.05, isInt: false },
      { key: "rs_s4", min: 1.0, max: 3.0, step: 0.1, isInt: false },
    ],
  },
  {
    title: "nodeDetection",
    params: [
      { key: "reversal_vol_ratio", min: 0.5, max: 3.0, step: 0.1, isInt: false },
      { key: "s2_reversal_r_min", min: 1.0, max: 5.0, step: 0.5, isInt: false },
      { key: "support_ma_tolerance", min: 0.001, max: 0.02, step: 0.001, isInt: false },
      { key: "s1_breakout_vol_ratio", min: 1.0, max: 3.0, step: 0.1, isInt: false },
    ],
  },
  {
    title: "positionRisk",
    params: [
      { key: "support_s3_size", min: 0.1, max: 0.7, step: 0.05, isInt: false },
      { key: "support_s4_size", min: 0.1, max: 0.5, step: 0.05, isInt: false },
      { key: "hard_stop_pct", min: 0.01, max: 0.10, step: 0.005, isInt: false },
      { key: "reversal_node_fail_days", min: 1, max: 10, step: 1, isInt: true },
    ],
  },
];

function getDefaults(strategy: string): StrategyConfigParams {
  if (strategy === "node_trading") return { ...NODE_TRADING_DEFAULTS };
  return { ...UP_TREND_DEFAULTS };
}

function getGroups(strategy: string): ParamGroup[] {
  if (strategy === "node_trading") return NODE_TRADING_GROUPS;
  return UP_TREND_GROUPS;
}

function fmtVal(v: number, isInt: boolean): string {
  if (isInt) return String(v);
  return v.toFixed(3).replace(/0+$/, "").replace(/\.$/, "");
}

export function StrategyConfigTab({ selectedStrategy }: { selectedStrategy: string }) {
  const { t } = useTranslation();

  const defaults = getDefaults(selectedStrategy);
  const groups = getGroups(selectedStrategy);

  const [params, setParams] = useState<StrategyConfigParams>({ ...defaults });
  const [isDefault, setIsDefault] = useState(true);
  const [loading, setLoading] = useState(false);

  const loadConfig = useCallback(
    (strategy: string) => {
      setLoading(true);
      const curDefaults = getDefaults(strategy);
      api
        .getStrategyConfig(strategy)
        .then((res) => {
          setParams({ ...curDefaults, ...res.params });
          setIsDefault(res.is_default);
        })
        .catch(() => {
          setParams({ ...curDefaults });
          setIsDefault(true);
        })
        .finally(() => setLoading(false));
    },
    [],
  );

  useEffect(() => {
    loadConfig(selectedStrategy);
  }, [selectedStrategy, loadConfig]);

  const updateParam = (key: string, value: number) => {
    setParams((prev) => ({ ...prev, [key]: value }));
    setIsDefault(false);
  };

  const resetParam = (key: string) => {
    setParams((prev) => ({ ...prev, [key]: defaults[key] }));
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
      setParams({ ...defaults, ...res.params });
      setIsDefault(true);
      toast.success(t("strategyResearch.configSaved"));
    } catch {
      setParams({ ...defaults });
      setIsDefault(true);
    }
  };

  const renderParamGroup = (group: ParamGroup) => (
    <div className="mb-4">
      <h3 className="mb-3 text-sm font-medium text-foreground">{t(`strategyResearch.${group.title}`)}</h3>
      <div className="grid grid-cols-2 gap-x-8 gap-y-4">
        {group.params.map((d) => {
          const value = params[d.key] ?? defaults[d.key];
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
                  {value !== defaults[d.key] && (
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
      {loading ? (
        <div className="text-xs text-muted-foreground">Loading...</div>
      ) : (
        <>
          {groups.map((g) => renderParamGroup(g))}

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
