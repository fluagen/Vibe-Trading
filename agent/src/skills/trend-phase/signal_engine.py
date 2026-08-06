"""趋势阶段量化交易策略 SignalEngine.

基于乖离率与斜率对走势各阶段的量化 V2，实现三层优先级风控体系、
六阶段分类、趋势-仓位双层引擎、背离信号处理、陷阱识别和仓位管理。

纯 pandas/numpy 实现，适用于 A 股日线单股回测。
"""

from __future__ import annotations

from typing import Dict

import numpy as np
import pandas as pd


class SignalEngine:
    """趋势阶段量化交易策略信号引擎.

    基于 BIAS（乖离率）、均线方向和标准差阈值，对 A 股走势进行六阶段分类，
    通过三层优先级风控体系输出标准仓位信号（0.0 ~ 1.0）。

    所有构造参数均有默认值，可直接被 backtest runner 无参实例化。
    """

    def __init__(
        self,
        ma_short: int = 5,
        ma_mid: int = 20,
        ma_long: int = 60,
        mu_window: int = 60,
        mu_recalc_freq: int = 20,
        sigma_window: int = 60,
        k_ma_period: int = 3,
        k_lag: int = 5,
        ma60_dir_lag: int = 5,
        ma20_dir_lag: int = 3,
        upper_extreme_sigma: float = 2.0,
        upper_consolidate_sigma: float = 1.0,
        lower_bottoming_sigma: float = 1.0,
        lower_extreme_sigma: float = 2.5,
        enable_dynamic_threshold: bool = True,
        tighten_sigma_ratio: float = 2.0,
        widen_sigma_ratio: float = 0.5,
        tighten_multiplier: float = 1.5,
        widen_multiplier: float = 2.5,
        dynamic_median_window: int = 60,
        sticky_threshold: float = 0.015,
        tier2_max_hold_days: int = 3,
        tier2_take_profit_pct: float = 0.05,
        tier2_stop_loss_pct: float = 0.05,
        tier2_exit_bias_offset: float = 0.5,
        hard_stop_loss_pct: float = 0.05,
        enable_time_stop: bool = True,
        time_stop_days: int = 10,
        enable_divergence: bool = True,
        divergence_lookback: int = 20,
        enable_early_reduce: bool = True,
        enable_early_add: bool = True,
        enable_trap_detection: bool = True,
        market_resonance_enabled: bool = False,
        index_ma60_up: bool = True,
    ):
        """初始化趋势阶段策略信号引擎.

        Args:
            ma_short: 短期均线周期（BIAS 分子 MA5）。
            ma_mid: 中期均线周期（BIAS 分母 MA20）。
            ma_long: 长期均线周期（MA60，趋势总指挥）。
            mu_window: μ 计算窗口。
            mu_recalc_freq: μ 重算频率（交易日）。
            sigma_window: σ 计算窗口。
            k_ma_period: K 斜率平滑周期。
            k_lag: K 斜率滞后天数。
            ma60_dir_lag: MA60 方向比较滞后天数。
            ma20_dir_lag: MA20 方向比较滞后天数。
            upper_extreme_sigma: 上轨极度区域 σ 倍数（μ + Nσ）。
            upper_consolidate_sigma: 上轨盘整区域 σ 倍数（μ + Nσ）。
            lower_bottoming_sigma: 下轨筑底区域 σ 倍数（μ - Nσ）。
            lower_extreme_sigma: 下轨极端区域 σ 倍数（μ - Nσ）。
            enable_dynamic_threshold: 是否启用动态阈值调整。
            tighten_sigma_ratio: σ 超出中位数 N 倍时收紧阈值。
            widen_sigma_ratio: σ 低于中位数 N 倍时放宽阈值。
            tighten_multiplier: 收紧后的 σ 倍数。
            widen_multiplier: 放宽后的 σ 倍数。
            dynamic_median_window: 动态阈值中位数计算窗口。
            sticky_threshold: 均线粘合阈值（|MA20-MA60| / MA60）。
            tier2_max_hold_days: Tier 2 极端抢反弹最大持仓天数。
            tier2_take_profit_pct: Tier 2 止盈比例。
            tier2_stop_loss_pct: Tier 2 止损比例。
            tier2_exit_bias_offset: Tier 2 退出 BIAS 偏移（μ + Nσ 时退出）。
            hard_stop_loss_pct: 硬止损底线（亏损超过此比例无条件离场）。
            enable_time_stop: 是否启用时间止损。
            time_stop_days: 时间止损天数（超期未触及目标则强制平仓）。
            enable_divergence: 是否启用背离信号检测。
            divergence_lookback: 背离检测回溯窗口。
            enable_early_reduce: 顶背离是否允许提前减仓。
            enable_early_add: 底背离是否允许提前加仓。
            enable_trap_detection: 是否启用陷阱识别。
            market_resonance_enabled: 是否启用大盘共振过滤（默认关闭）。
            index_ma60_up: 大盘 MA60 方向（True=向上），仅 market_resonance_enabled 时生效。
        """
        # MA 周期
        self.ma_short = ma_short
        self.ma_mid = ma_mid
        self.ma_long = ma_long

        # μ / σ
        self.mu_window = mu_window
        self.mu_recalc_freq = mu_recalc_freq
        self.sigma_window = sigma_window

        # K 斜率
        self.k_ma_period = k_ma_period
        self.k_lag = k_lag

        # MA 方向
        self.ma60_dir_lag = ma60_dir_lag
        self.ma20_dir_lag = ma20_dir_lag

        # 阈值倍数
        self.upper_extreme_sigma = upper_extreme_sigma
        self.upper_consolidate_sigma = upper_consolidate_sigma
        self.lower_bottoming_sigma = lower_bottoming_sigma
        self.lower_extreme_sigma = lower_extreme_sigma

        # 动态阈值
        self.enable_dynamic_threshold = enable_dynamic_threshold
        self.tighten_sigma_ratio = tighten_sigma_ratio
        self.widen_sigma_ratio = widen_sigma_ratio
        self.tighten_multiplier = tighten_multiplier
        self.widen_multiplier = widen_multiplier
        self.dynamic_median_window = dynamic_median_window

        # 均线粘合
        self.sticky_threshold = sticky_threshold

        # Tier 2
        self.tier2_max_hold_days = tier2_max_hold_days
        self.tier2_take_profit_pct = tier2_take_profit_pct
        self.tier2_stop_loss_pct = tier2_stop_loss_pct
        self.tier2_exit_bias_offset = -tier2_exit_bias_offset

        # 止损
        self.hard_stop_loss_pct = hard_stop_loss_pct
        self.enable_time_stop = enable_time_stop
        self.time_stop_days = time_stop_days

        # 背离
        self.enable_divergence = enable_divergence
        self.divergence_lookback = divergence_lookback
        self.enable_early_reduce = enable_early_reduce
        self.enable_early_add = enable_early_add

        # 陷阱
        self.enable_trap_detection = enable_trap_detection

        # 大盘共振
        self.market_resonance_enabled = market_resonance_enabled
        self.index_ma60_up = index_ma60_up

    def generate(self, data_map: Dict[str, pd.DataFrame]) -> Dict[str, pd.Series]:
        """为每个标的生成趋势阶段仓位信号.

        Args:
            data_map: 标的代码到 OHLCV DataFrame 的映射.
                DataFrame 必须包含 open/high/low/close/volume 列，
                index 为 DatetimeIndex.

        Returns:
            标的代码到信号 Series 的映射。信号值:
                1.0  = 满仓（100%）
                0.5  = 半仓（50%）
                0.2  = 轻仓（20%）
                0.1  = 极限抢反弹（10%）
                0.0  = 空仓
                -1.0 = 强制平仓
        """
        result: Dict[str, pd.Series] = {}
        for code, df in data_map.items():
            result[code] = self._generate_one(df)
        return result

    # ------------------------------------------------------------------
    # Per-stock signal generation
    # ------------------------------------------------------------------

    def _generate_one(self, df: pd.DataFrame) -> pd.Series:
        """对单个标的生成信号序列."""
        n = len(df)
        signals = pd.Series(0.0, index=df.index, name="signal")

        min_bars = max(self.mu_window, self.ma_long) + self.mu_recalc_freq
        if n < min_bars:
            return signals

        close = df["close"].values

        # ---- 向量化指标计算 ----
        ma5 = self._rolling_mean(close, self.ma_short)
        ma20 = self._rolling_mean(close, self.ma_mid)
        ma60 = self._rolling_mean(close, self.ma_long)

        bias_pct = self._compute_bias(ma5, ma20)
        mu, sigma = self._compute_mu_sigma(bias_pct)
        k_slope = self._compute_k(bias_pct)
        ma60_up = self._compute_ma_direction(ma60, self.ma60_dir_lag)
        ma20_up = self._compute_ma_direction(ma20, self.ma20_dir_lag)

        # 动态阈值 σ 倍数
        eff_upper_ext, eff_upper_con, eff_lower_bot, eff_lower_ext = (
            self._compute_dynamic_sigma_multipliers(sigma)
        )

        # 背离检测
        top_div, bot_div = self._compute_divergence(close, bias_pct)

        # 均线粘合
        ma_sticky = self._compute_sticky(ma20, ma60)

        # Gap 检测
        date_gaps = self._detect_gaps(df)

        # ---- 逐 bar 状态机 ----
        warmup = self.ma_long
        in_position = False
        position_target: float = 0.0
        entry_price: float = 0.0
        bars_held: int = 0
        tier2_entry_bar: int = -1
        tier2_entry_price: float = 0.0
        tier2_active: bool = False
        k_streak_neg: int = 0
        k_streak_pos: int = 0
        prev_phase: int = 0

        for i in range(n):
            # Warmup
            if i < warmup:
                continue

            # Gap 保护：跳过停牌复牌后首日
            if i > 0 and date_gaps[i]:
                signals.iloc[i] = signals.iloc[i - 1]
                continue

            # 当前 bar 的指标快照
            b = bias_pct[i]
            m = mu[i]
            s = sigma[i]
            k = k_slope[i]
            c = close[i]
            m60_up = ma60_up[i]
            m20_up = ma20_up[i]
            sticky = ma_sticky[i]

            if np.isnan(b) or np.isnan(m) or np.isnan(s) or np.isnan(k):
                continue

            # K 方向持续计数
            if k > 0:
                k_streak_pos += 1
                k_streak_neg = 0
            elif k < 0:
                k_streak_neg += 1
                k_streak_pos = 0
            else:
                k_streak_pos = 0
                k_streak_neg = 0

            # ---- 硬止损检查 ----
            if in_position and entry_price > 0:
                loss_pct = (c - entry_price) / entry_price
                if loss_pct <= -self.hard_stop_loss_pct:
                    signals.iloc[i] = -1.0
                    in_position, position_target = False, 0.0
                    entry_price = 0.0
                    bars_held, tier2_active = 0, False
                    tier2_entry_bar, tier2_entry_price = -1, 0.0
                    prev_phase = 0
                    continue

            # ---- 时间止损 ----
            if self.enable_time_stop and in_position and bars_held >= self.time_stop_days:
                signals.iloc[i] = -1.0
                in_position, position_target = False, 0.0
                entry_price = 0.0
                bars_held, tier2_active = 0, False
                tier2_entry_bar, tier2_entry_price = -1, 0.0
                prev_phase = 0
                continue

            # ---- Tier 2 退出检查 ----
            if tier2_active:
                tier2_bars = i - tier2_entry_bar
                tier2_pnl = (c - tier2_entry_price) / tier2_entry_price if tier2_entry_price > 0 else 0.0

                if tier2_pnl >= self.tier2_take_profit_pct:
                    signals.iloc[i] = -1.0
                    in_position, position_target = False, 0.0
                    entry_price = 0.0
                    bars_held, tier2_active = 0, False
                    tier2_entry_bar, tier2_entry_price = -1, 0.0
                    prev_phase = 0
                    continue

                if tier2_pnl <= -self.tier2_stop_loss_pct:
                    signals.iloc[i] = -1.0
                    in_position, position_target = False, 0.0
                    entry_price = 0.0
                    bars_held, tier2_active = 0, False
                    tier2_entry_bar, tier2_entry_price = -1, 0.0
                    prev_phase = 0
                    continue

                if tier2_bars >= self.tier2_max_hold_days:
                    signals.iloc[i] = -1.0
                    in_position, position_target = False, 0.0
                    entry_price = 0.0
                    bars_held, tier2_active = 0, False
                    tier2_entry_bar, tier2_entry_price = -1, 0.0
                    prev_phase = 0
                    continue

                # BIAS 恢复到 mu-0.5σ 且 K 转负 → 诱多反弹退出
                exit_bias = m + self.tier2_exit_bias_offset * s
                was_k_pos = k_slope[i - 1] > 0 if i > 0 else False
                if b >= exit_bias and k < 0 and was_k_pos:
                    signals.iloc[i] = -1.0
                    in_position, position_target = False, 0.0
                    entry_price = 0.0
                    bars_held, tier2_active = 0, False
                    tier2_entry_bar, tier2_entry_price = -1, 0.0
                    prev_phase = 0
                    continue

            # ---- 三层优先级体系 ----

            # Tier 1: 终极风控（MA60↓ 且 BIAS ≥ μ − 2.5σ）
            tier1_trigger = (not m60_up) and (b >= m - eff_lower_ext[i] * s)
            if tier1_trigger:
                if in_position:
                    signals.iloc[i] = -1.0
                    in_position, position_target = False, 0.0
                    entry_price = 0.0
                    bars_held, tier2_active = 0, False
                    tier2_entry_bar, tier2_entry_price = -1, 0.0
                    prev_phase = 0
                else:
                    signals.iloc[i] = 0.0
                continue

            # Tier 2: 极端抢反弹（MA60↓ 且 BIAS < μ − 2.5σ）
            tier2_trigger = (not m60_up) and (b < m - eff_lower_ext[i] * s)
            if tier2_trigger:
                if not in_position:
                    # 开仓 10%
                    signals.iloc[i] = 0.1
                    in_position = True
                    position_target = 0.1
                    entry_price = c
                    bars_held = 0
                    tier2_active = True
                    tier2_entry_bar = i
                    tier2_entry_price = c
                    prev_phase = 0
                else:
                    signals.iloc[i] = position_target
                    bars_held += 1
                continue

            # Tier 3: 标准策略（MA60↑）
            if m60_up:
                target = self._tier3_evaluate(
                    bias=b,
                    mu=m,
                    sigma=s,
                    k=k,
                    k_prev=k_slope[i - 1] if i > 0 else 0.0,
                    close=c,
                    m20_up=m20_up,
                    sticky=sticky,
                    top_div=bool(top_div[i]),
                    bot_div=bool(bot_div[i]),
                    k_streak_neg=k_streak_neg,
                    k_streak_pos=k_streak_pos,
                    in_position=in_position,
                    position_target=position_target,
                    prev_phase=prev_phase,
                )

                signals.iloc[i] = target

                if target > 0 and not in_position:
                    in_position = True
                    entry_price = c
                    bars_held = 0
                elif target > 0 and in_position:
                    bars_held += 1
                elif target <= 0 and in_position:
                    in_position = False
                    entry_price = 0.0
                    bars_held = 0

                position_target = target
                if target == 1.0:
                    prev_phase = 1
                elif target == 0.5:
                    prev_phase = 2
                elif target == 0.2:
                    prev_phase = 3
                else:
                    prev_phase = 0
            else:
                # 安全兜底：MA60 向下但不触发 Tier 1/Tier 2
                if in_position:
                    signals.iloc[i] = -1.0
                    in_position, position_target = False, 0.0
                    entry_price = 0.0
                    bars_held, tier2_active = 0, False
                    tier2_entry_bar, tier2_entry_price = -1, 0.0
                    prev_phase = 0
                else:
                    signals.iloc[i] = 0.0

        signals = signals.fillna(0.0).clip(-1.0, 1.0)
        return signals

    # ------------------------------------------------------------------
    # Tier 3 标准策略评估
    # ------------------------------------------------------------------

    def _tier3_evaluate(
        self,
        bias: float,
        mu: float,
        sigma: float,
        k: float,
        k_prev: float,
        close: float,
        m20_up: bool,
        sticky: bool,
        top_div: bool,
        bot_div: bool,
        k_streak_neg: int,
        k_streak_pos: int,
        in_position: bool,
        position_target: float,
        prev_phase: int,
    ) -> float:
        """Tier 3 标准策略：六阶段分类 + 仓位管理."""
        upper_ext = mu + self.upper_extreme_sigma * sigma
        upper_con = mu + self.upper_consolidate_sigma * sigma
        lower_bot = mu - self.lower_bottoming_sigma * sigma

        # ---- 趋势-仓位双层引擎 ----
        if m20_up:
            position_cap = 1.0
            allow_new_buys = True
        else:
            position_cap = 0.5
            allow_new_buys = False

        # ---- 大盘共振过滤 ----
        if self.market_resonance_enabled and not self.index_ma60_up:
            position_cap = min(position_cap, 0.5)

        # ---- 均线粘合：维持当前仓位 ----
        if sticky and in_position:
            return position_target

        # ---- K 方向转换检测 ----
        k_turns_neg = k < 0 and k_prev > 0
        k_turns_pos = k > 0 and k_prev < 0

        # ---- 六阶段判定 ----
        target = position_target if in_position else 0.0

        # ① 主升浪：BIAS > μ + 2σ, K > 0
        if bias > upper_ext and k > 0:
            target = 1.0
        # ② 高位盘整：μ+σ < BIAS < μ+2σ, K 由正转负
        elif upper_con < bias <= upper_ext and k_turns_neg:
            target = 0.5
        # ③ 高位筑顶：BIAS < μ+σ, K 持续为负
        elif bias <= upper_con and k_streak_neg >= 2:
            target = 0.2
            if bias < mu:
                target = 0.0
        # ⑥ 低位筑底：BIAS > μ−σ, K 由负转正
        elif bias > lower_bot and k_turns_pos:
            target = 0.5 if m20_up else 0.0
        # 诱空杀跌回踩加仓：在 μ+σ ~ μ+2σ 区域，K 为正，从阶段②/③恢复
        elif upper_con <= bias <= upper_ext and k > 0 and k_streak_pos >= 1:
            if in_position and prev_phase in (2, 3):
                target = 1.0

        # ---- 背离信号覆写 ----
        if self.enable_divergence:
            if self.enable_early_reduce and top_div and target == 1.0:
                target = 0.5
            if self.enable_early_add and bot_div and target <= 0.2:
                target = 0.5

        # ---- 陷阱识别：诱空杀跌加回 ----
        if self.enable_trap_detection:
            in_trap2 = prev_phase in (2, 3) and in_position
            if in_trap2 and bias >= upper_con and k_turns_pos:
                target = 1.0

        # ---- 仓位限制 ----
        if not allow_new_buys:
            if not in_position and target > 0:
                target = 0.0
            elif in_position and target > position_target:
                target = position_target

        target = min(target, position_cap)
        return target

    # ------------------------------------------------------------------
    # 向量化指标计算
    # ------------------------------------------------------------------

    def _rolling_mean(self, arr: np.ndarray, window: int) -> np.ndarray:
        """计算滚动均值."""
        s = pd.Series(arr)
        return s.rolling(window=window, min_periods=window).mean().to_numpy()

    def _compute_bias(self, ma5: np.ndarray, ma20: np.ndarray) -> np.ndarray:
        """计算 BIAS = (MA5 - MA20) / MA20 * 100."""
        denom = np.where(np.abs(ma20) > 1e-8, ma20, np.nan)
        return (ma5 - ma20) / denom * 100.0

    def _compute_mu_sigma(self, bias: np.ndarray):
        """计算 μ（均值）和 σ（标准差），每 mu_recalc_freq 更新一次."""
        bias_s = pd.Series(bias)
        mu_raw = bias_s.rolling(window=self.mu_window, min_periods=self.mu_window).mean()
        sigma_raw = bias_s.rolling(window=self.sigma_window, min_periods=self.sigma_window).std()

        n = len(bias)
        recalc_mask = np.zeros(n, dtype=bool)
        start = max(self.mu_window, self.sigma_window) - 1
        recalc_mask[start :: self.mu_recalc_freq] = True

        mu = mu_raw.where(recalc_mask).ffill().to_numpy()
        sigma = sigma_raw.where(recalc_mask).ffill().to_numpy()
        sigma = np.where(sigma > 1e-8, sigma, 1e-6)
        return mu, sigma

    def _compute_k(self, bias: np.ndarray) -> np.ndarray:
        """计算 K 平滑斜率 = MA3(BIAS)[t] - MA3(BIAS)[t-k_lag]."""
        bias_s = pd.Series(bias)
        bias_ma = bias_s.rolling(window=self.k_ma_period, min_periods=self.k_ma_period).mean()
        k = bias_ma - bias_ma.shift(self.k_lag)
        return k.to_numpy()

    def _compute_ma_direction(self, ma: np.ndarray, lag: int) -> np.ndarray:
        """计算均线方向: ma[t] - ma[t-lag] > 0."""
        ma_s = pd.Series(ma)
        return (ma_s > ma_s.shift(lag)).to_numpy()

    def _compute_dynamic_sigma_multipliers(self, sigma: np.ndarray):
        """计算动态阈值调整后的 σ 倍数.

        Returns:
            (upper_extreme, upper_consolidate, lower_bottoming, lower_extreme) 四个数组。
        """
        n = len(sigma)
        upper_ext = np.full(n, self.upper_extreme_sigma)
        upper_con = np.full(n, self.upper_consolidate_sigma)
        lower_bot = np.full(n, self.lower_bottoming_sigma)
        lower_ext = np.full(n, self.lower_extreme_sigma)

        if not self.enable_dynamic_threshold:
            return upper_ext, upper_con, lower_bot, lower_ext

        sigma_s = pd.Series(sigma)
        median_sigma = (
            sigma_s.rolling(window=self.dynamic_median_window, min_periods=self.dynamic_median_window)
            .median()
            .to_numpy()
        )

        for i in range(self.dynamic_median_window, n):
            if np.isnan(median_sigma[i]) or np.isnan(sigma[i]) or median_sigma[i] < 1e-8:
                continue
            if sigma[i] > self.tighten_sigma_ratio * median_sigma[i]:
                upper_ext[i] = self.tighten_multiplier
                upper_con[i] = self.tighten_multiplier * 0.5
                lower_bot[i] = self.tighten_multiplier * 0.5
                lower_ext[i] = self.tighten_multiplier
            elif sigma[i] < self.widen_sigma_ratio * median_sigma[i]:
                upper_ext[i] = self.widen_multiplier
                upper_con[i] = self.widen_multiplier * 0.4
                lower_bot[i] = self.widen_multiplier * 0.4
                lower_ext[i] = self.widen_multiplier

        return upper_ext, upper_con, lower_bot, lower_ext

    def _compute_divergence(self, close: np.ndarray, bias: np.ndarray):
        """计算顶背离和底背离（向量化 + 逐 bar 校验）."""
        n = len(close)
        lookback = self.divergence_lookback
        top_div = np.zeros(n, dtype=bool)
        bot_div = np.zeros(n, dtype=bool)

        if not self.enable_divergence:
            return top_div, bot_div

        for i in range(lookback, n):
            win_c = close[i - lookback : i + 1]
            win_b = bias[i - lookback : i + 1]

            if close[i] >= np.nanmax(win_c) and not (bias[i] >= np.nanmax(win_b)):
                top_div[i] = True
            if close[i] <= np.nanmin(win_c) and not (bias[i] <= np.nanmin(win_b)):
                bot_div[i] = True

        return top_div, bot_div

    def _compute_sticky(self, ma20: np.ndarray, ma60: np.ndarray) -> np.ndarray:
        """检测均线粘合: |MA20 - MA60| / MA60 < sticky_threshold."""
        denom = np.where(np.abs(ma60) > 1e-8, ma60, np.nan)
        ratio = np.abs(ma20 - ma60) / denom
        return ratio < self.sticky_threshold

    def _detect_gaps(self, df: pd.DataFrame) -> np.ndarray:
        """检测日期间隙（停牌 > 3 天后复牌首日标记为 gap）."""
        n = len(df)
        gaps = np.zeros(n, dtype=bool)
        if n < 2:
            return gaps
        date_diffs = df.index.to_series().diff().dt.days
        for i in range(1, n):
            if pd.notna(date_diffs.iloc[i]) and date_diffs.iloc[i] > 3:
                gaps[i] = True
        return gaps
