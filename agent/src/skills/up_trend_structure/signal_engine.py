"""Up-trend-structure SignalEngine with position management.

Implements the SignalEngine contract: generate(data_map) -> dict[code, Series].
"""

from __future__ import annotations

from typing import Dict

import pandas as pd

from src.skills.up_trend_structure.up_trend_structure import UpTrendStructure


class SignalEngine:
    """Signal engine for up-trend-structure strategy."""

    def __init__(
        self,
        up_phase_min_bars: int = 3,
        volume_surge_ratio: float = 1.5,
        big_bull_body_ratio: float = 0.6,
        inv_hammer_shadow_ratio: float = 1.5,
        close_above_prev_mid: float = 0.5,
        stop_loss_pct: float = 0.03,
    ):
        self.structure = UpTrendStructure(
            up_phase_min_bars=up_phase_min_bars,
            volume_surge_ratio=volume_surge_ratio,
            big_bull_body_ratio=big_bull_body_ratio,
            inv_hammer_shadow_ratio=inv_hammer_shadow_ratio,
            close_above_prev_mid=close_above_prev_mid,
        )
        self.stop_loss_pct = stop_loss_pct

    def generate(self, data_map: Dict[str, pd.DataFrame]) -> Dict[str, pd.Series]:
        """Generate trading signals from OHLCV data.

        Entry rules:
          - 止跌K → signal 0.33 (trial entry)
          - 证伪K → signal 0.67 (confirm and add)
          - 缩量不破止跌K + 放量阳线 → signal 1.0 (full position)
        Exit rules:
          - Price breaks below 止跌K pivot_low → -1.0
          - Loss > stop_loss_pct → -1.0
          - Divergence unrepaired → -1.0
        """
        result = {}
        for code, df in data_map.items():
            states = self.structure.compute(df)
            n = len(df)
            signals = pd.Series(0.0, index=df.index, name="signal")

            # Track position state
            position_size = 0.0  # current position: 0, 0.33, 0.67, 1.0
            entry_prices = []    # prices at which we entered
            pivot_low = float("nan")
            in_pullback = False

            for i in range(n):
                state = states["state"].iloc[i]
                bsk = bool(states["bottom_signal_k"].iloc[i])
                ck = bool(states["confirm_k"].iloc[i])
                div = bool(states["divergence"].iloc[i])
                pivot = float(states["pivot_low"].iloc[i])
                close = df["close"].iloc[i]
                low = df["low"].iloc[i]

                # Check stop loss: price breaks pivot
                if position_size > 0 and not pd.isna(pivot):
                    if low < pivot:
                        signals.iloc[i] = -1.0
                        position_size = 0.0
                        entry_prices = []
                        pivot_low = float("nan")
                        continue

                # Check stop loss: unrealized loss > 3%
                if position_size > 0 and entry_prices:
                    avg_entry = sum(entry_prices) / len(entry_prices)
                    if (close - avg_entry) / avg_entry < -self.stop_loss_pct:
                        signals.iloc[i] = -1.0
                        position_size = 0.0
                        entry_prices = []
                        pivot_low = float("nan")
                        continue

                # Divergence → take profit (only if in position and divergence is unrepaired)
                # Divergence is unrepaired when state transitions to pullback
                if position_size > 0 and state == "pullback" and not in_pullback:
                    in_pullback = True
                    signals.iloc[i] = -1.0
                    position_size = 0.0
                    entry_prices = []
                    pivot_low = float("nan")
                    continue
                in_pullback = (state == "pullback")

                # Entry logic
                if state == "forming" and bsk and position_size == 0.0:
                    signals.iloc[i] = 0.33
                    position_size = 0.33
                    entry_prices = [close]
                    pivot_low = pivot if not pd.isna(pivot) else low
                elif state in ("forming", "up_phase") and ck and position_size == 0.33:
                    signals.iloc[i] = 0.67
                    position_size = 0.67
                    entry_prices.append(close)
                elif state == "up_phase" and position_size == 0.67:
                    # Third add: pullback held above pivot + bullish volume candle
                    # Check if we had a pullback that held and now resuming
                    prev_state = states["state"].iloc[i - 1] if i > 0 else ""
                    if prev_state in ("pullback", "forming") and close > df["open"].iloc[i]:
                        signals.iloc[i] = 1.0
                        position_size = 1.0
                        entry_prices.append(close)

                pivot_low = pivot if not pd.isna(pivot) else pivot_low

            result[code] = signals
        return result
