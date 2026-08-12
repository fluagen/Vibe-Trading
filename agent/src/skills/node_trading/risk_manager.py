"""止损止盈规则模块。"""

from __future__ import annotations
from typing import Optional
import pandas as pd


class PositionState:
    """单只股票持仓状态。"""

    def __init__(self):
        self.size: float = 0.0
        self.entry_price: float = 0.0
        self.node_type: str = ""
        self.node_low: float = 0.0
        self.entry_bar_index: int = 0
        self.profit_taken_ma5: bool = False
        self.profit_taken_ma10: bool = False

    def add(self, size: float, price: float, node_type: str,
            node_low: float, bar_index: int) -> None:
        """累加入场（加权均价）。"""
        total = self.size + size
        self.entry_price = (
            (self.entry_price * self.size + price * size) / total
            if total > 0 else price
        )
        self.size = total
        self.node_type = node_type
        self.node_low = node_low
        self.entry_bar_index = bar_index
        self.profit_taken_ma5 = False
        self.profit_taken_ma10 = False

    def clear(self) -> None:
        """清仓。"""
        self.size = 0.0
        self.entry_price = 0.0
        self.node_type = ""
        self.node_low = 0.0
        self.entry_bar_index = 0


def check_stop_loss(
    position: PositionState, close: float,
    bar_index: int,
    *, hard_stop_pct: float = 0.05,
    reversal_node_fail_days: int = 3,
) -> Optional[str]:
    """检查止损。Returns 'hard_stop' / 'node_fail' / None.

    规则（按节点类型）：
    - 反转: 硬性止损 -5%；3 日内节点失败止损
    - 支撑 / S1粘合爆发: 硬性止损 -5% + 节点失败止损（无限期）
    """
    if position.size <= 0:
        return None

    # (1) 硬性止损（所有节点统一 -5%）
    if position.entry_price > 0:
        if (close - position.entry_price) / position.entry_price < -hard_stop_pct:
            return "hard_stop"

    # (2) 节点失败止损
    if position.node_low > 0 and close < position.node_low:
        if position.node_type in ("support", "sticky_breakout"):
            return "node_fail"
        # 反转节点：仅 3 日内触发节点失败止损
        if position.node_type == "reversal":
            if bar_index - position.entry_bar_index <= reversal_node_fail_days:
                return "node_fail"

    return None


def check_take_profit(
    position: PositionState, close: float,
    ma5: float, ma10: float, ma20: float,
    stage: str, alignment: str,
    r: float = 0.0,
    *, r_s5: float = 9.0, r_s4: float = 6.0,
) -> float | None:
    """检查止盈。R 值分层控制灵敏度。

    加速期 S4/S5 — R 分层:
      R > 9%（极端发散）:  Close < MA5 → 减半, Close < MA10 → 全清
      6% < R ≤ 9%（一般发散）: Close < MA10 → 减半, Close < MA20 → 全清
      R ≤ 6%（趋近粘合）: Close < MA20 → 全清（不触发减半）

    正常期 S3: Close < MA10 → 减半, Close < MA20 → 全清
    S1/S2 不触发止盈。

    Returns 新仓位或 -1.0 或 None。
    """
    if position.size <= 0:
        return None
    if pd.isna(ma5) or pd.isna(ma10) or pd.isna(ma20):
        return None

    # 加速期止盈：S4 / S5（R 分层）
    if stage in ("S4", "S5"):
        if r > r_s5:
            # 极端发散：MA5 减半，MA10 全清
            if close < ma10:
                return -1.0
            if close < ma5 and not position.profit_taken_ma5:
                position.profit_taken_ma5 = True
                return position.size / 2
        elif r > r_s4:
            # 一般发散：MA10 减半，MA20 全清
            if close < ma20:
                return -1.0
            if close < ma10 and not position.profit_taken_ma10:
                position.profit_taken_ma10 = True
                return position.size / 2
        else:
            # 趋近粘合：仅 MA20 全清，不触发减半
            if close < ma20:
                return -1.0
        return None

    # 正常止盈：S3
    if stage == "S3":
        if close < ma20:
            return -1.0
        if close < ma10 and not position.profit_taken_ma10:
            position.profit_taken_ma10 = True
            return position.size / 2
        return None

    # S1/S2 不触发止盈
    return None
