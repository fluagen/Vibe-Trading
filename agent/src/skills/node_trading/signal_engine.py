"""节点交易策略 SignalEngine。

组合 indicators → stage_classifier → node_detector → position_manager → risk_manager，
按固定顺序逐 bar 推进，输出 [-1.0, 1.0] 信号序列。
"""

from __future__ import annotations
from typing import Dict
import pandas as pd

from src.skills.node_trading.indicators import compute_indicators
from src.skills.node_trading.stage_classifier import classify_stage
from src.skills.node_trading.node_detector import detect_node
from src.skills.node_trading.position_manager import calc_position, get_stage_max_position
from src.skills.node_trading.risk_manager import (
    PositionState, check_stop_loss, check_take_profit,
)


def _tp_reason_name(
    stage: str, r_val: float, close: float,
    ma5: float, ma10: float, ma20: float,
    tp_r_s5: float = 9.0, tp_r_s4: float = 6.0,
    is_halve: bool = False,
) -> str:
    """Build human-readable take-profit reason string."""
    suffix = "减半" if is_halve else "全清"
    if stage in ("S4", "S5"):
        if r_val > tp_r_s5:
            ma_label = "MA5" if (is_halve and close < ma5) else "MA10"
            return f"R>9% {ma_label}{suffix}"
        if r_val > tp_r_s4:
            ma_label = "MA10" if is_halve else "MA20"
            return f"6%<R≤9% {ma_label}{suffix}"
        return f"R≤6% MA20全清"
    if stage == "S3":
        ma_label = "MA10" if is_halve else "MA20"
        return f"S3 {ma_label}{suffix}"
    return f"止盈{suffix}"


class SignalEngine:
    """节点交易策略信号引擎。所有阈值参数可配置，带 PRD 默认值。"""

    def __init__(
        self,
        # --- stage_classifier ---
        r_s5: float = 9.0, cv_s5: float = 0.4,
        r_s4: float = 6.0, rs_s4: float = 1.1,
        r_s3_lower: float = 4.0, r_s3_upper: float = 6.0, cv_s3: float = 0.3,
        r_s2_lower: float = 2.0, r_s2_upper: float = 4.0,
        # --- node_detector ---
        reversal_vol_ratio: float = 1.0,
        s2_reversal_r_min: float = 2.5,
        support_ma_tolerance: float = 0.005,
        s1_breakout_vol_ratio: float = 1.5,
        # --- position_manager ---
        reversal_low_r_size: float = 0.2,
        reversal_high_r_size: float = 0.1,
        reversal_r_boundary: float = 6.0,
        support_s3_size: float = 0.5,
        support_s4_size: float = 0.3,
        sticky_breakout_size: float = 0.1,
        # --- risk_manager ---
        hard_stop_pct: float = 0.05,
        reversal_node_fail_days: int = 3,
        tp_r_s5: float = 9.0,
        tp_r_s4: float = 6.0,
    ):
        self._stage_kwargs = dict(
            r_s5=r_s5, cv_s5=cv_s5, r_s4=r_s4, rs_s4=rs_s4,
            r_s3_lower=r_s3_lower, r_s3_upper=r_s3_upper, cv_s3=cv_s3,
            r_s2_lower=r_s2_lower, r_s2_upper=r_s2_upper,
        )
        self._node_kwargs = dict(
            reversal_vol_ratio=reversal_vol_ratio,
            s2_reversal_r_min=s2_reversal_r_min,
            support_ma_tolerance=support_ma_tolerance,
            s1_breakout_vol_ratio=s1_breakout_vol_ratio,
        )
        self._position_kwargs = dict(
            reversal_low_r_size=reversal_low_r_size,
            reversal_high_r_size=reversal_high_r_size,
            reversal_r_boundary=reversal_r_boundary,
            support_s3_size=support_s3_size,
            support_s4_size=support_s4_size,
            sticky_breakout_size=sticky_breakout_size,
        )
        self._stop_kwargs = dict(
            hard_stop_pct=hard_stop_pct,
            reversal_node_fail_days=reversal_node_fail_days,
        )
        self._tp_kwargs = dict(
            r_s5=tp_r_s5,
            r_s4=tp_r_s4,
        )
        self.bar_metadata_: list[dict] = []

    def generate(self, data_map: Dict[str, pd.DataFrame]) -> Dict[str, pd.Series]:
        """为每只股票生成交易信号。"""
        result = {}
        for code, df in data_map.items():
            result[code] = self._generate_one(df)
        return result

    def _generate_one(self, df: pd.DataFrame) -> pd.Series:
        ind = compute_indicators(df)
        n = len(ind)
        signals = pd.Series(0.0, index=ind.index, name="signal")
        pos = PositionState()
        prev_stage, prev_alignment = "S1", "crossed"
        self.bar_metadata_ = []

        def _update_prev(s: str, a: str) -> None:
            """只在 alignment 有意义（非 crossed）时更新 prev_stage/prev_alignment。"""
            nonlocal prev_stage, prev_alignment
            if a != "crossed":
                prev_stage, prev_alignment = s, a

        for i in range(n):
            row = ind.iloc[i]
            open_ = float(row["open"])
            high = float(row["high"])
            low = float(row["low"])
            close = float(row["close"])
            ma5 = float(row["ma5"])
            ma10 = float(row["ma10"])
            ma20 = float(row["ma20"])
            r_val = float(row["r"])
            cv_val = float(row["cv"])
            rs_val = float(row["rs"])
            alignment = str(row["alignment"])
            volume = float(row["volume"])
            prev_volume = float(ind["volume"].iloc[i - 1]) if i > 0 else volume
            stage = classify_stage(
                r=r_val, cv=cv_val, rs=rs_val, alignment=alignment,
                **self._stage_kwargs,
            )

            reason: str | None = None
            node_type: str | None = None

            # --- 止损检查 ---
            stop_reason = check_stop_loss(
                pos, close, i, **self._stop_kwargs,
            )
            if stop_reason is not None:
                signals.iloc[i] = -1.0
                pos.clear()
                reason = stop_reason
                self.bar_metadata_.append(dict(
                    stage=stage, alignment=alignment, r=r_val, cv=cv_val, rs=rs_val,
                    node_type=None, exit_reason=reason, signal=-1.0,
                ))
                _update_prev(stage, alignment)
                continue

            # --- 止盈检查 ---
            tp_result = check_take_profit(pos, close, ma5, ma10, ma20, stage, alignment, r=r_val, **self._tp_kwargs)
            if tp_result is not None:
                is_halve = tp_result != -1.0
                if not is_halve:
                    signals.iloc[i] = -1.0
                    pos.clear()
                else:
                    signals.iloc[i] = tp_result
                    pos.size = tp_result
                reason = _tp_reason_name(
                    stage=stage, r_val=r_val, close=close,
                    ma5=ma5, ma10=ma10, ma20=ma20,
                    tp_r_s5=self._tp_kwargs["r_s5"],
                    tp_r_s4=self._tp_kwargs["r_s4"],
                    is_halve=is_halve,
                )
                self.bar_metadata_.append(dict(
                    stage=stage, alignment=alignment, r=r_val, cv=cv_val, rs=rs_val,
                    node_type=None, exit_reason=reason, signal=signals.iloc[i],
                ))
                _update_prev(stage, alignment)
                continue

            # --- 禁买区 ---
            stage_max = get_stage_max_position(stage, alignment)
            if pos.size <= 0 and stage_max <= 0:
                self.bar_metadata_.append(dict(
                    stage=stage, alignment=alignment, r=r_val, cv=cv_val, rs=rs_val,
                    node_type=None, exit_reason=None, signal=0.0,
                ))
                _update_prev(stage, alignment)
                continue

            # --- 已有仓位不开新仓 ---
            if pos.size > 0:
                self.bar_metadata_.append(dict(
                    stage=stage, alignment=alignment, r=r_val, cv=cv_val, rs=rs_val,
                    node_type=None, exit_reason=None, signal=0.0,
                ))
                _update_prev(stage, alignment)
                continue

            # --- 节点扫描 ---
            node_type = detect_node(
                stage=stage, alignment=alignment,
                prev_stage=prev_stage, prev_alignment=prev_alignment,
                open_=open_, close=close, low=low, high=high,
                volume=volume, prev_volume=prev_volume,
                ma20=ma20, r=r_val, **self._node_kwargs,
            )
            if node_type is None:
                self.bar_metadata_.append(dict(
                    stage=stage, alignment=alignment, r=r_val, cv=cv_val, rs=rs_val,
                    node_type=None, exit_reason=None, signal=0.0,
                ))
                _update_prev(stage, alignment)
                continue

            # --- 仓位计算（支撑节点按上个阶段授权仓位）---
            pos_stage = prev_stage if node_type == "support" else stage
            target_size = calc_position(
                stage=pos_stage, node_type=node_type, r=r_val,
                **self._position_kwargs,
            )
            if target_size <= 0:
                self.bar_metadata_.append(dict(
                    stage=stage, alignment=alignment, r=r_val, cv=cv_val, rs=rs_val,
                    node_type=node_type, exit_reason=None, signal=0.0,
                ))
                _update_prev(stage, alignment)
                continue
            if stage_max > 0:
                target_size = min(target_size, stage_max)

            # --- 输出信号 ---
            signals.iloc[i] = target_size
            pos.add(
                size=target_size, price=close, node_type=node_type,
                node_low=low, bar_index=i,
            )
            self.bar_metadata_.append(dict(
                stage=stage, alignment=alignment, r=r_val, cv=cv_val, rs=rs_val,
                node_type=node_type, exit_reason=None, signal=target_size,
            ))
            _update_prev(stage, alignment)

        return signals
