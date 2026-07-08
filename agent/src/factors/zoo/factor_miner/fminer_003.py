# ============================================================
# 中文名称: FactorMiner #3 - 量价背离
# 简要说明: 价涨量缩或量涨价跌，检测价格与成交量的短期背离。
# 典型用途: 识别上涨动能衰竭或下跌中的放量抵抗，作为反转信号的前置指标。
# 来源: up_trend_structure 策略 UpTrendStructure._detect_divergence()
# ============================================================
"""FactorMiner Alpha #3 — Volume-Price Divergence.

Formula: (close > close.shift(1) AND volume < volume.shift(1))
      OR (volume > volume.shift(1) AND close < close.shift(1))

Returns 0/1 binary signal per bar per stock.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

__alpha_meta__ = {
    "id": "fminer_003",
    "nickname": "量价背离",
    "theme": ["volume", "reversal"],
    "formula_latex": r"(C_t > C_{t-1} \land V_t < V_{t-1}) \lor (V_t > V_{t-1} \land C_t < C_{t-1})",
    "columns_required": ["close", "volume"],
    "extras_required": [],
    "requires_sector": False,
    "universe": ["equity_cn"],
    "frequency": ["1D"],
    "decay_horizon": 1,
    "min_warmup_bars": 2,
    "notes": "提取自 up_trend_structure 策略的量价背离检测器。Binary signal: 1=divergence, 0=normal.",
}


def compute(panel: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Compute volume-price divergence signal on a wide panel.

    Args:
        panel: dict with keys "close", "volume" — wide DataFrames
               (index=date, columns=stock_codes).

    Returns:
        DataFrame of 0/1, same shape as input. 1 = divergence detected.
    """
    c = panel["close"]
    v = panel["volume"]

    price_up = c > c.shift(1)
    volume_down = v < v.shift(1)
    volume_up = v > v.shift(1)
    price_down = c < c.shift(1)

    divergence = (price_up & volume_down) | (volume_up & price_down)
    return divergence.fillna(0).astype(np.int64)
