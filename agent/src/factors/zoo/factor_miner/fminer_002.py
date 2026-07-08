# ============================================================
# 中文名称: FactorMiner #2 - 证伪K
# 简要说明: 止跌K的次日确认信号：阳线或收盘高于止跌K收盘价，确认回调结束进入上涨阶段。
# 典型用途: 作为止跌K的验证信号，确认入场后加仓至2/3仓位。
# 来源: up_trend_structure 策略 UpTrendStructure._detect_confirm_k()
# ============================================================
"""FactorMiner Alpha #2 — Confirmation K-line (证伪K).

Conditions:
  1. Previous bar was a 止跌K (bottom signal K)
  2. Current day is bullish (close > open) OR close > previous 止跌K close

Returns 0/1 binary signal per bar per stock.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

__alpha_meta__ = {
    "id": "fminer_002",
    "nickname": "证伪K",
    "theme": ["momentum"],
    "formula_latex": r"\text{prev\_bsk} \land (C_t > O_t \lor C_t > C_{t-1})",
    "columns_required": ["open", "high", "low", "close", "volume"],
    "extras_required": [],
    "requires_sector": False,
    "universe": ["equity_cn"],
    "frequency": ["1D"],
    "decay_horizon": 2,
    "min_warmup_bars": 4,
    "notes": "提取自 up_trend_structure 策略。依赖 fminer_001 (止跌K) 计算前一日信号。",
}


def compute(panel: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Compute confirmation K-line (证伪K) on a wide panel.

    Args:
        panel: dict with keys "open","high","low","close","volume"
               (index=date, columns=stock_codes).

    Returns:
        DataFrame of 0/1. 1 = 证伪K detected (止跌K confirmed).
    """
    o = panel["open"]
    h = panel["high"]
    l = panel["low"]
    c = panel["close"]
    v = panel["volume"]

    # Inline 止跌K detection (purity gate forbids cross-factor imports)
    prev_bearish = c.shift(1) < o.shift(1)
    body = (c - o).abs()
    upper_shadow = h - np.maximum(o, c)
    lower_shadow = np.minimum(o, c) - l
    inv_hammer = (upper_shadow >= 1.5 * body) & (lower_shadow < body) & (body > 0)
    rng = h - l
    safe_rng = rng.replace(0, float("nan"))
    big_bullish = (body / safe_rng > 0.6) & (c > o) & (body > 0)
    pattern = inv_hammer | big_bullish
    prev_body_mid = (o.shift(1) + c.shift(1)) / 2
    close_ok = c > prev_body_mid
    vol_ok = v > v.shift(1) * 1.5
    bsk = prev_bearish & pattern & close_ok & vol_ok

    # Previous bar was a 止跌K
    prev_bsk = bsk.shift(1).fillna(0).astype(bool)

    # Current day is bullish OR close > previous close
    is_bullish = c > o
    close_above = c > c.shift(1)

    cond = prev_bsk & (is_bullish | close_above)
    return cond.fillna(0).astype(np.int64)
