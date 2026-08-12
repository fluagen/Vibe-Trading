"""节点检测模块。三节点体系：反转、支撑、粘合爆发。纯函数，无状态。"""

from __future__ import annotations
from typing import Optional
import pandas as pd


def detect_node(
    stage: str, alignment: str,
    prev_stage: str, prev_alignment: str,
    open_: float, close: float, low: float, high: float,
    volume: float, prev_volume: float, ma20: float, r: float,
    *, reversal_vol_ratio: float = 1.0,
    s2_reversal_r_min: float = 2.5,
    support_ma_tolerance: float = 0.005,
    s1_breakout_vol_ratio: float = 1.5,
) -> Optional[str]:
    """检测当前 bar 是否触发节点信号。

    Returns:
        节点类型: 'reversal' / 'support' / 'sticky_breakout' / None
    """
    if pd.isna(ma20) or pd.isna(close) or pd.isna(volume):
        return None

    # 1. 支撑节点（上涨中继）— 优先级最高
    #    上个阶段 S3/S4 + bull + 回踩MA20收阳
    if prev_stage in ("S3", "S4") and prev_alignment == "bull":
        near_ma20 = (low < ma20 * (1 + support_ma_tolerance)
                     and close > ma20 * (1 + support_ma_tolerance))
        is_bullish = close > open_
        if near_ma20 and is_bullish:
            return "support"

    # 2. 反转节点（V型反转）
    #    上个阶段 bear + 上穿MA20收阳 + 放量
    if prev_alignment == "bear" and volume > prev_volume * reversal_vol_ratio:
        cross_up = open_ < ma20 < high
        is_bullish = close > open_
        if cross_up and is_bullish:
            if stage == "S2" and r < s2_reversal_r_min:
                return None
            return "reversal"

    # 3. S1 粘合爆发（横盘突破）
    #    S1 + 上穿MA20收阳 + 显著放量
    if stage == "S1" and close > open_:
        cross_up = open_ < ma20 < close
        if cross_up and volume > prev_volume * s1_breakout_vol_ratio:
            return "sticky_breakout"

    return None
