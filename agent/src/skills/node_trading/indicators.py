"""矢量化指标预计算模块。

纯函数，输入 OHLCV DataFrame，返回带所有指标列的 DataFrame。
不维护任何状态，方便单元测试。
"""

from __future__ import annotations

import pandas as pd


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """对 OHLCV 数据计算全部节点策略指标。

    Args:
        df: 必须包含列 open, high, low, close, volume。
            索引为 pd.DatetimeIndex，按时间升序排列。

    Returns:
        在原始 df 上追加以下列：
        - ma5, ma10, ma20: 均线
        - r: 极差比 R（百分比）
        - cv: 变异系数
        - rs: 极差比斜率
        - alignment: 均线排列方向 (bull / bear / crossed)
        - cross_ma20: MA20 上穿标记 (0/1)
        - vol_ma5: 5 日均量
    """
    result = df.copy()

    close = result["close"]
    high = result["high"]
    low = result["low"]
    volume = result["volume"]

    # ---- 均线 ----
    result["ma5"] = close.rolling(window=5).mean()
    result["ma10"] = close.rolling(window=10).mean()
    result["ma20"] = close.rolling(window=20).mean()

    ma5 = result["ma5"]
    ma10 = result["ma10"]
    ma20 = result["ma20"]

    # ---- 极差比 R ----
    ma_all = pd.concat([ma5, ma10, ma20], axis=1)
    ma_max = ma_all.max(axis=1)
    ma_min = ma_all.min(axis=1)
    ma_mean = (ma5 + ma10 + ma20) / 3.0
    result["r"] = (ma_max - ma_min) / ma_mean * 100.0

    # ---- 变异系数 CV ----
    result["cv"] = ma_all.std(axis=1) / ma_mean

    # ---- 极差比斜率 RS（R / 5 日前的 R） ----
    r_5d = result["r"].shift(5)
    result["rs"] = result["r"] / r_5d.replace(0, float("nan"))

    # ---- 均线排列方向 ----
    def _alignment(row: pd.Series) -> str:
        if pd.isna(row["ma5"]) or pd.isna(row["ma10"]) or pd.isna(row["ma20"]):
            return "crossed"
        if row["ma5"] > row["ma10"] > row["ma20"]:
            return "bull"
        if row["ma5"] < row["ma10"] < row["ma20"]:
            return "bear"
        return "crossed"

    result["alignment"] = result.apply(_alignment, axis=1)

    # ---- MA20 上穿标记 ----
    prev_close = close.shift(1)
    prev_ma20 = ma20.shift(1)
    cross_today = (low < ma20) & (ma20 < high)
    cross_from_below = (prev_close < prev_ma20) & (high > ma20)
    result["cross_ma20"] = (cross_today | cross_from_below).astype(int)

    # ---- 5 日均量 ----
    result["vol_ma5"] = volume.rolling(window=5).mean()

    return result
