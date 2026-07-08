# ============================================================
# 中文名称: FactorMiner #1 - 止跌K
# 简要说明: 检测上涨结构中的止跌信号K线：前日阴线后出现倒锤线或大阳线，配合放量和收盘突破前阴线中点。
# 典型用途: 识别回调结束的潜在转折点，作为上涨结构的分步建仓入场信号。
# 来源: up_trend_structure 策略 UpTrendStructure._detect_bottom_signal_k()
# ============================================================
"""FactorMiner Alpha #1 — Bottom Signal K-line (止跌K).

Conditions:
  1. Previous day is bearish (close < open)
  2. Pattern: inverted hammer (upper shadow >= 1.5x body, lower shadow < body)
     OR big bullish (body > 60% range, close > open)
  3. Close > midpoint of previous bearish body
  4. Volume > 1.5x previous volume

Returns 0/1 binary signal per bar per stock.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

__alpha_meta__ = {
    "id": "fminer_001",
    "nickname": "止跌K",
    "theme": ["reversal", "volume"],
    "formula_latex": r"\text{止跌K} = \text{prev\_bearish} \land (\text{inv\_hammer} \lor \text{big\_bull}) \land (C > \text{prev\_mid}) \land (V > 1.5 V_{t-1})",
    "columns_required": ["open", "high", "low", "close", "volume"],
    "extras_required": [],
    "requires_sector": False,
    "universe": ["equity_cn"],
    "frequency": ["1D"],
    "decay_horizon": 2,
    "min_warmup_bars": 3,
    "notes": "提取自 up_trend_structure 策略。默认参数: volume_surge_ratio=1.5, big_bull_body_ratio=0.6, inv_hammer_shadow_ratio=1.5, close_above_prev_mid=0.5.",
}


def compute(panel: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Compute bottom signal K-line (止跌K) on a wide panel.

    Args:
        panel: dict with keys "open","high","low","close","volume"
               (index=date, columns=stock_codes).

    Returns:
        DataFrame of 0/1, same shape as input. 1 = 止跌K detected.
    """
    o = panel["open"]
    h = panel["high"]
    l = panel["low"]
    c = panel["close"]
    v = panel["volume"]

    # Condition 1: previous day is bearish
    prev_bearish = c.shift(1) < o.shift(1)

    # Helper: body = |close - open|
    body = (c - o).abs()

    # Inverted hammer: upper shadow >= 1.5x body, lower shadow < body, body > 0
    upper_shadow = h - np.maximum(o, c)
    lower_shadow = np.minimum(o, c) - l
    inv_hammer = (upper_shadow >= 1.5 * body) & (lower_shadow < body) & (body > 0)

    # Big bullish: body / range > 0.6, close > open, body > 0
    rng = h - l
    safe_rng = rng.replace(0, float("nan"))
    big_bullish = (body / safe_rng > 0.6) & (c > o) & (body > 0)

    # Condition 2: pattern = inv_hammer OR big_bullish
    pattern = inv_hammer | big_bullish

    # Condition 3: close > midpoint of previous bearish body
    prev_body_mid = (o.shift(1) + c.shift(1)) / 2
    close_ok = c > prev_body_mid

    # Condition 4: volume > 1.5x previous volume
    vol_ok = v > v.shift(1) * 1.5

    cond = prev_bearish & pattern & close_ok & vol_ok
    return cond.fillna(0).astype(np.int64)
