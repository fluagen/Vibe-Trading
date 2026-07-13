"""Up-trend-structure SignalEngine v2 with position management.

v2 changes:
- Remove 1.0 full position (max 0.67)
- Three-tier cascade take-profit: 30% profit → 5MA → 10MA
- MA-based stops computed internally
"""

from __future__ import annotations

from typing import Dict
import pandas as pd

from src.skills.up_trend_structure.up_trend_structure import UpTrendStructure


class SignalEngine:
    """Signal engine for up-trend-structure strategy v2."""

    def __init__(
        self,
        up_phase_min_bars: int = 2,
        volume_surge_ratio: float = 1.2,
        big_bull_body_ratio: float = 0.6,
        inv_hammer_shadow_ratio: float = 1.2,
        close_above_prev_mid: float = 0.5,
        stop_loss_pct: float = 0.03,
        take_profit_pct: float = 0.30,
        ma_short: int = 5,
        ma_mid: int = 10,
    ):
        self.structure = UpTrendStructure(
            up_phase_min_bars=up_phase_min_bars,
            volume_surge_ratio=volume_surge_ratio,
            big_bull_body_ratio=big_bull_body_ratio,
            inv_hammer_shadow_ratio=inv_hammer_shadow_ratio,
            close_above_prev_mid=close_above_prev_mid,
        )
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        self.ma_short = ma_short
        self.ma_mid = ma_mid

    def generate(self, data_map: Dict[str, pd.DataFrame]) -> Dict[str, pd.Series]:
        """Generate trading signals from OHLCV data.

        Entry (v2):
          - 止跌K in forming → 0.33 (trial entry)
          - 证伪K in forming (from pullback) → 0.67 (confirm and add)
          - Max position = 0.67 (no more 1.0)

        Exit (v2):
          - low < pivot_low → -1.0 (stop loss)
          - unrealized loss > stop_loss_pct → -1.0 (stop loss)
          - divergence/pvd unrepaired → pullback → -1.0
          - profit ≥ take_profit_pct → partial exit (×0.5)
          - close < MA(short) → partial exit (×0.5)
          - close < MA(mid) → full exit (-1.0)
        """
        result = {}
        for code, df in data_map.items():
            states = self.structure.compute(df)
            n = len(df)
            signals = pd.Series(0.0, index=df.index, name="signal")

            # Compute MAs
            ma_s = df["close"].rolling(window=self.ma_short).mean()
            ma_m = df["close"].rolling(window=self.ma_mid).mean()

            # Track position state
            position_size = 0.0
            entry_prices = []
            pivot_low = float("nan")
            in_pullback = False
            profit_taken_30 = False    # 30% take-profit triggered
            ma_short_taken = False     # 5MA take-profit triggered

            for i in range(n):
                state = states["state"].iloc[i]
                bsk = bool(states["bottom_signal_k"].iloc[i])
                ck = bool(states["confirm_k"].iloc[i])
                pivot = float(states["pivot_low"].iloc[i])
                close = df["close"].iloc[i]
                low = df["low"].iloc[i]

                # --- Stop loss: price breaks pivot ---
                if position_size > 0 and not pd.isna(pivot):
                    if low < pivot:
                        signals.iloc[i] = -1.0
                        position_size = 0.0
                        entry_prices = []
                        pivot_low = float("nan")
                        profit_taken_30 = False
                        ma_short_taken = False
                        continue

                # --- Stop loss: unrealized loss ---
                if position_size > 0 and entry_prices:
                    avg_entry = sum(entry_prices) / len(entry_prices)
                    if (close - avg_entry) / avg_entry < -self.stop_loss_pct:
                        signals.iloc[i] = -1.0
                        position_size = 0.0
                        entry_prices = []
                        pivot_low = float("nan")
                        profit_taken_30 = False
                        ma_short_taken = False
                        continue

                # --- Take profit: divergence/pvd unrepaired → pullback ---
                if position_size > 0 and state == "pullback" and not in_pullback:
                    in_pullback = True
                    signals.iloc[i] = -1.0
                    position_size = 0.0
                    entry_prices = []
                    pivot_low = float("nan")
                    profit_taken_30 = False
                    ma_short_taken = False
                    continue
                in_pullback = (state == "pullback")

                # --- Take profit: 30% profit → sell half ---
                if position_size > 0 and not profit_taken_30 and entry_prices:
                    avg_entry = sum(entry_prices) / len(entry_prices)
                    if (close - avg_entry) / avg_entry >= self.take_profit_pct:
                        new_size = position_size / 2
                        signals.iloc[i] = new_size
                        position_size = new_size
                        profit_taken_30 = True
                        continue

                # --- Take profit: close < MA(short) → sell half ---
                if position_size > 0 and not ma_short_taken and not pd.isna(ma_s.iloc[i]):
                    if close < ma_s.iloc[i]:
                        new_size = position_size / 2
                        signals.iloc[i] = new_size
                        position_size = new_size
                        ma_short_taken = True
                        continue

                # --- Take profit: close < MA(mid) → full exit ---
                if position_size > 0 and not pd.isna(ma_m.iloc[i]):
                    if close < ma_m.iloc[i]:
                        signals.iloc[i] = -1.0
                        position_size = 0.0
                        entry_prices = []
                        pivot_low = float("nan")
                        profit_taken_30 = False
                        ma_short_taken = False
                        continue

                # --- Entry: 止跌K when pullback → pullback_end ---
                prev_state = states["state"].iloc[i - 1] if i > 0 else ""
                if state == "pullback_end" and bsk and position_size == 0.0 and prev_state == "pullback":
                    signals.iloc[i] = 0.33
                    position_size = 0.33
                    entry_prices = [close]
                    pivot_low = pivot if not pd.isna(pivot) else low
                    profit_taken_30 = False
                    ma_short_taken = False
                # --- Entry: 证伪K when pullback_end → up_phase, add to 0.67 ---
                elif state == "up_phase" and ck and position_size == 0.33 and prev_state == "pullback_end":
                    signals.iloc[i] = 0.67
                    position_size = 0.67
                    entry_prices.append(close)

                pivot_low = pivot if not pd.isna(pivot) else pivot_low

            result[code] = signals
        return result
