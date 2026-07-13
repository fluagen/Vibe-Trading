# ============================================================
# 中文名称: FactorMiner #4 - 上涨结构状态
# 简要说明: 编码上涨结构的五个状态阶段，可用于市场状态筛选和多策略组合。
# 典型用途: 作为regime filter，只在up_phase(2)中允许其他策略入场。
# 来源: up_trend_structure 策略 UpTrendStructure._compute_states()
# ============================================================
"""FactorMiner Alpha #4 — Up-Trend Structure State.

Encodes the six structure states as integers:
  0 = no_structure
  1 = forming (价涨量增 seen, awaiting confirmation)
  2 = up_phase (uptrend active)
  3 = pullback (divergence unrepaired, pullback in progress)
  4 = breakdown (price broke below pivot_low)
  5 = pullback_end (止跌K in pullback, awaiting 证伪K)

State machine is per-column sequential (state depends on prior state + pivot_low).
All logic inlined to pass purity gate.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

__alpha_meta__ = {
    "id": "fminer_004",
    "nickname": "上涨结构状态",
    "theme": ["momentum", "volume"],
    "formula_latex": r"S_t \in \{0,1,2,3,4,5\}",
    "columns_required": ["open", "high", "low", "close", "volume"],
    "extras_required": [],
    "requires_sector": False,
    "universe": ["equity_cn"],
    "frequency": ["1D"],
    "decay_horizon": 5,
    "min_warmup_bars": 5,
    "notes": "提取自 up_trend_structure 策略的状态机。默认参数硬编码。逐列计算。",
}


def compute(panel: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Compute up-trend structure state on a wide panel.

    Args:
        panel: dict with keys "open","high","low","close","volume"
               (index=date, columns=stock_codes).

    Returns:
        DataFrame of integers 0-4, same shape as input.
    """
    o = panel["open"]
    h = panel["high"]
    l = panel["low"]
    c = panel["close"]
    v = panel["volume"]

    codes = list(c.columns)
    n = len(c)
    result = pd.DataFrame(0, index=c.index, columns=c.columns, dtype=np.int64)

    for code in codes:
        result[code] = _compute_one(
            o[code].values, h[code].values, l[code].values,
            c[code].values, v[code].values, n,
        )

    return result


# ---------------------------------------------------------------------------
# Inlined detector + state machine (purity gate: no external imports beyond
# numpy/pandas).
# ---------------------------------------------------------------------------


def _detect_bottom_signal_k(
    o: np.ndarray, h: np.ndarray, l: np.ndarray, c_arr: np.ndarray, v_arr: np.ndarray,
) -> np.ndarray:
    """Vectorized 止跌K detection. Returns bool array."""
    prev_bearish = np.roll(c_arr, 1) < np.roll(o, 1)
    prev_bearish[0] = False

    body = np.abs(c_arr - o)
    us = h - np.maximum(o, c_arr)
    ls = np.minimum(o, c_arr) - l
    inv_hammer = (us >= 1.5 * body) & (ls < body) & (body > 0)

    rng = h - l
    safe_rng = np.where(rng == 0, np.nan, rng)
    big_bullish = (body / safe_rng > 0.6) & (c_arr > o) & (body > 0)
    pattern = inv_hammer | big_bullish

    prev_body_mid = (np.roll(o, 1) + np.roll(c_arr, 1)) / 2
    prev_body_mid[0] = np.nan
    close_ok = c_arr > prev_body_mid

    vol_ok = v_arr > np.roll(v_arr, 1) * 1.5
    vol_ok[0] = False

    return prev_bearish & pattern & close_ok & vol_ok


def _detect_confirm_k(bsk: np.ndarray, o: np.ndarray, c_arr: np.ndarray) -> np.ndarray:
    """Vectorized 证伪K detection. bsk must already be computed."""
    prev_bsk = np.roll(bsk, 1)
    prev_bsk[0] = False
    is_bullish = c_arr > o
    close_above = c_arr > np.roll(c_arr, 1)
    close_above[0] = False
    return prev_bsk & (is_bullish | close_above)


def _detect_divergence(c_arr: np.ndarray, v_arr: np.ndarray) -> np.ndarray:
    """Vectorized volume-price divergence detection."""
    prev_c = np.roll(c_arr, 1)
    prev_v = np.roll(v_arr, 1)
    price_up = c_arr > prev_c
    volume_down = v_arr < prev_v
    volume_up = v_arr > prev_v
    price_down = c_arr < prev_c
    price_up[0] = False
    volume_down[0] = False
    volume_up[0] = False
    price_down[0] = False
    return (price_up & volume_down) | (volume_up & price_down)


def _compute_one(
    o: np.ndarray, h: np.ndarray, l_arr: np.ndarray,
    c_arr: np.ndarray, v_arr: np.ndarray, n: int,
) -> np.ndarray:
    """Compute state encoding for a single stock column. Returns int array 0-5."""
    bsk = _detect_bottom_signal_k(o, h, l_arr, c_arr, v_arr)
    ck = _detect_confirm_k(bsk, o, c_arr)
    div = _detect_divergence(c_arr, v_arr)

    states = np.zeros(n, dtype=np.int64)
    current_state = 0  # no_structure
    current_pivot = np.nan
    prev_divergence = False

    for i in range(n):
        low_i = l_arr[i]
        o_i = o[i]
        c_i = c_arr[i]
        v_i = v_arr[i]
        is_bsk = bool(bsk[i])
        is_ck = bool(ck[i])
        is_div = bool(div[i])
        is_puvu = (i > 0) and (c_i > c_arr[i - 1]) and (v_i > v_arr[i - 1])

        # Check breakdown first
        if current_state in (1, 2, 3, 5):  # forming, up_phase, pullback, pullback_end
            if low_i < current_pivot:
                current_state = 4  # breakdown
                current_pivot = np.nan
                prev_divergence = False

        if current_state == 0:  # no_structure
            if is_puvu:
                current_state = 1  # forming
                current_pivot = low_i

        elif current_state == 1:  # forming
            if is_puvu:
                current_state = 2  # up_phase
            else:
                current_state = 0  # no_structure
                current_pivot = np.nan

        elif current_state == 2:  # up_phase
            if prev_divergence:
                prev_v = v_arr[i - 1]
                repaired = (c_i > o_i) and (v_i > prev_v)
                if not repaired:
                    current_state = 3  # pullback
                prev_divergence = False
            elif is_div:
                prev_divergence = True

        elif current_state == 3:  # pullback
            if is_bsk:
                current_state = 5  # pullback_end
                current_pivot = low_i

        elif current_state == 5:  # pullback_end
            if is_ck:
                current_state = 2  # up_phase
            else:
                current_state = 3  # pullback

        elif current_state == 4:  # breakdown
            current_state = 0  # no_structure
            current_pivot = np.nan
            prev_divergence = False

        states[i] = current_state

    return states
