"""动态仓位计算模块。根据节点类型 + 阶段返回目标仓位成数。"""

from __future__ import annotations


def calc_position(
    stage: str, node_type: str, r: float = 0.0,
    *, reversal_low_r_size: float = 0.2,
    reversal_high_r_size: float = 0.1,
    reversal_r_boundary: float = 6.0,
    support_s3_size: float = 0.5,
    support_s4_size: float = 0.3,
    sticky_breakout_size: float = 0.1,
) -> float:
    """计算目标开仓仓位成数。

    - 反转节点: R<=6% -> 2成, R>6% -> 1成
    - 支撑节点: S3 -> 5成, S4 -> 3成
    - S1粘合爆发: 1成
    """
    if node_type == "reversal":
        if r > reversal_r_boundary:
            return reversal_high_r_size
        return reversal_low_r_size

    if node_type == "support":
        if stage == "S4":
            return support_s4_size
        return support_s3_size

    if node_type == "sticky_breakout":
        return sticky_breakout_size

    return 0.0


def get_stage_max_position(stage: str, alignment: str = "") -> float:
    """获取当前阶段允许的总仓位上限。

    - S4(bull): 上限 3 成
    - S4(bear/crossed): 上限 2 成
    """
    caps = {"S1": 0.1, "S2": 0.2, "S3": 0.7, "S5": 0.0}
    if stage in caps:
        return caps[stage]
    if stage == "S4":
        if alignment == "bull":
            return 0.3
        return 0.2
    return 0.0
