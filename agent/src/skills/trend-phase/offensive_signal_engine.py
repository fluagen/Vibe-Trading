"""进攻型趋势阶段量化交易策略 SignalEngine.

基于防守型策略框架，放宽阈值、简化减仓规则、维持持仓，
适合趋势行情中最大化收益。纯 pandas/numpy 实现。

与防守型的核心差异：
- σ 阈值从 2.0/1.0 放宽到 3.0/1.5
- MA20↓ 时不禁止新开仓，仓位上限 80% 而非 50%
- 过渡区维持当前仓位，不清仓
- MA60↑ 时仓位地板 50%（永不全清）
- 硬止损从 −5% 放宽到 −10%
- 移除时间止损
- K 持久性从 2 天增加到 3 天
- μ 重算使用平滑过渡（5 天线性插值）
"""

from __future__ import annotations

from typing import Dict

import numpy as np
import pandas as pd


class SignalEngine:
    """进攻型趋势阶段策略信号引擎."""

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
        upper_extreme_sigma: float = 3.0,
        upper_consolidate_sigma: float = 1.5,
        lower_bottoming_sigma: float = 1.5,
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
        hard_stop_loss_pct: float = 0.10,
        enable_time_stop: bool = False,
        time_stop_days: int = 10,
        enable_divergence: bool = True,
        divergence_lookback: int = 20,
        enable_early_reduce: bool = True,
        enable_early_add: bool = True,
        enable_trap_detection: bool = True,
        market_resonance_enabled: bool = False,
        index_ma60_up: bool = True,
        k_persistence_bars: int = 3,
        ma20_down_cap: float = 0.80,
        ma20_down_block_buys: bool = False,
        position_floor_ma60_up: float = 0.50,
        mu_smooth_days: int = 5,
    ):
        self.ma_short = ma_short
        self.ma_mid = ma_mid
        self.ma_long = ma_long
        self.mu_window = mu_window
        self.mu_recalc_freq = mu_recalc_freq
        self.sigma_window = sigma_window
        self.k_ma_period = k_ma_period
        self.k_lag = k_lag
        self.ma60_dir_lag = ma60_dir_lag
        self.ma20_dir_lag = ma20_dir_lag
        self.upper_extreme_sigma = upper_extreme_sigma
        self.upper_consolidate_sigma = upper_consolidate_sigma
        self.lower_bottoming_sigma = lower_bottoming_sigma
        self.lower_extreme_sigma = lower_extreme_sigma
        self.enable_dynamic_threshold = enable_dynamic_threshold
        self.tighten_sigma_ratio = tighten_sigma_ratio
        self.widen_sigma_ratio = widen_sigma_ratio
        self.tighten_multiplier = tighten_multiplier
        self.widen_multiplier = widen_multiplier
        self.dynamic_median_window = dynamic_median_window
        self.sticky_threshold = sticky_threshold
        self.tier2_max_hold_days = tier2_max_hold_days
        self.tier2_take_profit_pct = tier2_take_profit_pct
        self.tier2_stop_loss_pct = tier2_stop_loss_pct
        self.tier2_exit_bias_offset = -tier2_exit_bias_offset
        self.hard_stop_loss_pct = hard_stop_loss_pct
        self.enable_time_stop = enable_time_stop
        self.time_stop_days = time_stop_days
        self.enable_divergence = enable_divergence
        self.divergence_lookback = divergence_lookback
        self.enable_early_reduce = enable_early_reduce
        self.enable_early_add = enable_early_add
        self.enable_trap_detection = enable_trap_detection
        self.market_resonance_enabled = market_resonance_enabled
        self.index_ma60_up = index_ma60_up
        self.k_persistence_bars = k_persistence_bars
        self.ma20_down_cap = ma20_down_cap
        self.ma20_down_block_buys = ma20_down_block_buys
        self.position_floor_ma60_up = position_floor_ma60_up
        self.mu_smooth_days = mu_smooth_days

    def generate(self, data_map: Dict[str, pd.DataFrame]) -> Dict[str, pd.Series]:
        result: Dict[str, pd.Series] = {}
        for code, df in data_map.items():
            result[code] = self._generate_one(df)
        return result

    def _generate_one(self, df: pd.DataFrame) -> pd.Series:
        n = len(df)
        signals = pd.Series(0.0, index=df.index, name="signal")
        min_bars = max(self.mu_window, self.ma_long) + self.mu_recalc_freq
        if n < min_bars:
            return signals

        close = df["close"].values
        ma5 = self._rolling_mean(close, self.ma_short)
        ma20 = self._rolling_mean(close, self.ma_mid)
        ma60 = self._rolling_mean(close, self.ma_long)
        bias_pct = self._compute_bias(ma5, ma20)
        mu, sigma = self._compute_mu_sigma(bias_pct)
        k_slope = self._compute_k(bias_pct)
        ma60_up = self._compute_ma_direction(ma60, self.ma60_dir_lag)
        ma20_up = self._compute_ma_direction(ma20, self.ma20_dir_lag)
        eff_ue, eff_uc, eff_lb, eff_le = self._compute_dynamic_sigma_multipliers(sigma)
        top_div, bot_div = self._compute_divergence(close, bias_pct)
        ma_sticky = self._compute_sticky(ma20, ma60)
        date_gaps = self._detect_gaps(df)

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
            if i < warmup:
                continue
            if i > 0 and date_gaps[i]:
                signals.iloc[i] = signals.iloc[i - 1]
                continue

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

            if k > 0:
                k_streak_pos += 1
                k_streak_neg = 0
            elif k < 0:
                k_streak_neg += 1
                k_streak_pos = 0
            else:
                k_streak_pos = 0
                k_streak_neg = 0

            # 硬止损
            if in_position and entry_price > 0:
                if (c - entry_price) / entry_price <= -self.hard_stop_loss_pct:
                    signals.iloc[i] = -1.0
                    in_position, position_target = False, 0.0
                    entry_price = 0.0
                    bars_held, tier2_active = 0, False
                    tier2_entry_bar, tier2_entry_price = -1, 0.0
                    prev_phase = 0
                    continue

            # 时间止损（进攻型默认关闭）
            if self.enable_time_stop and in_position and bars_held >= self.time_stop_days:
                signals.iloc[i] = -1.0
                in_position, position_target = False, 0.0
                entry_price = 0.0
                bars_held, tier2_active = 0, False
                tier2_entry_bar, tier2_entry_price = -1, 0.0
                prev_phase = 0
                continue

            # Tier 2 退出
            if tier2_active:
                t2_bars = i - tier2_entry_bar
                t2_pnl = (c - tier2_entry_price) / tier2_entry_price if tier2_entry_price > 0 else 0.0
                exit_bias = m + self.tier2_exit_bias_offset * s
                was_k_pos = k_slope[i - 1] > 0 if i > 0 else False
                should_exit = (
                    t2_pnl >= self.tier2_take_profit_pct
                    or t2_pnl <= -self.tier2_stop_loss_pct
                    or t2_bars >= self.tier2_max_hold_days
                    or (b >= exit_bias and k < 0 and was_k_pos)
                )
                if should_exit:
                    signals.iloc[i] = -1.0
                    in_position, position_target = False, 0.0
                    entry_price = 0.0
                    bars_held, tier2_active = 0, False
                    tier2_entry_bar, tier2_entry_price = -1, 0.0
                    prev_phase = 0
                    continue

            # Tier 1
            if (not m60_up) and (b >= m - eff_le[i] * s):
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

            # Tier 2
            if (not m60_up) and (b < m - eff_le[i] * s):
                if not in_position:
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

            # Tier 3（进攻型）
            if m60_up:
                target = self._tier3_offensive(
                    bias=b, mu=m, sigma=s, k=k,
                    k_prev=k_slope[i - 1] if i > 0 else 0.0,
                    m20_up=m20_up, sticky=sticky,
                    top_div=bool(top_div[i]), bot_div=bool(bot_div[i]),
                    k_streak_neg=k_streak_neg, k_streak_pos=k_streak_pos,
                    in_position=in_position, position_target=position_target,
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
                if target >= 1.0:
                    prev_phase = 1
                elif target >= 0.8:
                    prev_phase = 2
                elif target >= 0.5:
                    prev_phase = 3
                else:
                    prev_phase = 0
            else:
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
    # 进攻型 Tier 3
    # ------------------------------------------------------------------

    def _tier3_offensive(
        self,
        bias: float,
        mu: float,
        sigma: float,
        k: float,
        k_prev: float,
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
        upper_ext = mu + self.upper_extreme_sigma * sigma
        upper_con = mu + self.upper_consolidate_sigma * sigma
        lower_bot = mu - self.lower_bottoming_sigma * sigma

        if m20_up:
            position_cap = 1.0
        else:
            position_cap = self.ma20_down_cap
        allow_new_buys = True if m20_up else (not self.ma20_down_block_buys)

        if self.market_resonance_enabled and not self.index_ma60_up:
            position_cap = min(position_cap, 0.5)
        if sticky and in_position:
            return position_target

        k_turns_pos = k > 0 and k_prev < 0

        # 默认：维持当前仓位（进攻型核心差异）
        target = position_target if in_position else 0.0

        # ① 主升浪
        if bias > upper_ext and k > 0:
            target = 1.0
        # ② 盘整：维持
        elif upper_con < bias <= upper_ext:
            if in_position:
                target = position_target
            elif k > 0 and k_streak_pos >= 2:
                target = 0.8
        # ③ 筑顶风险：降一档但不低于地板
        elif bias <= upper_con and k_streak_neg >= self.k_persistence_bars:
            reduced = position_target * 0.5 if position_target > 0.5 else self.position_floor_ma60_up
            target = max(self.position_floor_ma60_up, reduced)
            if bias < mu:
                target = self.position_floor_ma60_up
        # ⑥ 低位筑底
        elif bias > lower_bot and k_turns_pos:
            target = max(self.position_floor_ma60_up, 0.5)
            if m20_up and k_streak_pos >= 2:
                target = 0.8
        # 过渡区：维持
        elif in_position:
            target = position_target

        # 背离
        if self.enable_divergence:
            if self.enable_early_reduce and top_div and target >= 1.0:
                target = 0.8
            if self.enable_early_add and bot_div and target <= 0.5:
                target = max(target, 0.8)

        # 陷阱：诱空杀跌加回
        if self.enable_trap_detection:
            if prev_phase in (2, 3) and in_position and bias >= upper_con and k_turns_pos:
                target = 1.0

        if not allow_new_buys:
            if not in_position and target > 0:
                target = 0.0
            elif in_position and target > position_target:
                target = position_target

        target = min(target, position_cap)
        if in_position and target > 0:
            target = max(target, self.position_floor_ma60_up)
        return target

    # ------------------------------------------------------------------
    # 指标计算（同防守型，μ 平滑增强）
    # ------------------------------------------------------------------

    def _rolling_mean(self, arr: np.ndarray, window: int) -> np.ndarray:
        s = pd.Series(arr)
        return s.rolling(window=window, min_periods=window).mean().to_numpy()

    def _compute_bias(self, ma5: np.ndarray, ma20: np.ndarray) -> np.ndarray:
        denom = np.where(np.abs(ma20) > 1e-8, ma20, np.nan)
        return (ma5 - ma20) / denom * 100.0

    def _compute_mu_sigma(self, bias: np.ndarray):
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

        # μ 平滑过渡
        if self.mu_smooth_days > 0:
            recalc_bars = list(range(start, n, self.mu_recalc_freq))
            if len(recalc_bars) > 1:
                mu_smooth = mu.copy()
                for j in range(1, len(recalc_bars)):
                    prev_bar = recalc_bars[j - 1]
                    curr_bar = recalc_bars[j]
                    old_val = mu[prev_bar]
                    for offset in range(min(self.mu_smooth_days, n - curr_bar)):
                        idx = curr_bar + offset
                        if idx >= n:
                            break
                        alpha = min(1.0, (offset + 1) / self.mu_smooth_days)
                        mu_smooth[idx] = old_val * (1.0 - alpha) + mu_smooth[idx] * alpha
                mu = mu_smooth

        return mu, sigma

    def _compute_k(self, bias: np.ndarray) -> np.ndarray:
        bias_s = pd.Series(bias)
        bias_ma = bias_s.rolling(window=self.k_ma_period, min_periods=self.k_ma_period).mean()
        return (bias_ma - bias_ma.shift(self.k_lag)).to_numpy()

    def _compute_ma_direction(self, ma: np.ndarray, lag: int) -> np.ndarray:
        ma_s = pd.Series(ma)
        return (ma_s > ma_s.shift(lag)).to_numpy()

    def _compute_dynamic_sigma_multipliers(self, sigma: np.ndarray):
        n = len(sigma)
        ue = np.full(n, self.upper_extreme_sigma)
        uc = np.full(n, self.upper_consolidate_sigma)
        lb = np.full(n, self.lower_bottoming_sigma)
        le = np.full(n, self.lower_extreme_sigma)
        if not self.enable_dynamic_threshold:
            return ue, uc, lb, le

        sigma_s = pd.Series(sigma)
        med = sigma_s.rolling(window=self.dynamic_median_window, min_periods=self.dynamic_median_window).median().to_numpy()
        for i in range(self.dynamic_median_window, n):
            if np.isnan(med[i]) or np.isnan(sigma[i]) or med[i] < 1e-8:
                continue
            if sigma[i] > self.tighten_sigma_ratio * med[i]:
                ue[i] = self.tighten_multiplier
                uc[i] = self.tighten_multiplier * 0.5
                lb[i] = self.tighten_multiplier * 0.5
                le[i] = self.tighten_multiplier
            elif sigma[i] < self.widen_sigma_ratio * med[i]:
                ue[i] = self.widen_multiplier
                uc[i] = self.widen_multiplier * 0.4
                lb[i] = self.widen_multiplier * 0.4
                le[i] = self.widen_multiplier
        return ue, uc, lb, le

    def _compute_divergence(self, close: np.ndarray, bias: np.ndarray):
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
        denom = np.where(np.abs(ma60) > 1e-8, ma60, np.nan)
        return np.abs(ma20 - ma60) / denom < self.sticky_threshold

    def _detect_gaps(self, df: pd.DataFrame) -> np.ndarray:
        n = len(df)
        gaps = np.zeros(n, dtype=bool)
        if n < 2:
            return gaps
        date_diffs = df.index.to_series().diff().dt.days
        for i in range(1, n):
            if pd.notna(date_diffs.iloc[i]) and date_diffs.iloc[i] > 3:
                gaps[i] = True
        return gaps
