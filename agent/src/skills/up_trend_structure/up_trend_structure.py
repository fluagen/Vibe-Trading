"""Up-trend structure detector.

State machine that processes OHLCV bars and outputs the current structure state
for each bar: no_structure → forming → up_phase → pullback → breakdown.
"""

from __future__ import annotations

from typing import Tuple
import pandas as pd


# ---------------------------------------------------------------------------
# Vectorized helper functions
# ---------------------------------------------------------------------------


def _body(o: pd.Series, c: pd.Series) -> pd.Series:
    return (c - o).abs()


def _range(h: pd.Series, l: pd.Series) -> pd.Series:
    return h - l


def _upper_shadow(o: pd.Series, c: pd.Series, h: pd.Series) -> pd.Series:
    return h - pd.concat([o, c], axis=1).max(axis=1)


def _lower_shadow(o: pd.Series, c: pd.Series, l: pd.Series) -> pd.Series:
    return pd.concat([o, c], axis=1).min(axis=1) - l


# ---------------------------------------------------------------------------
# Detector
# ---------------------------------------------------------------------------


class UpTrendStructure:
    """Detect up-trend structure states from daily OHLCV data."""

    def __init__(
        self,
        up_phase_min_bars: int = 3,
        volume_surge_ratio: float = 1.5,
        big_bull_body_ratio: float = 0.6,
        inv_hammer_shadow_ratio: float = 1.5,
        close_above_prev_mid: float = 0.5,
        divergence_repair_bars: int = 1,
    ):
        self.up_phase_min_bars = up_phase_min_bars
        self.volume_surge_ratio = volume_surge_ratio
        self.big_bull_body_ratio = big_bull_body_ratio
        self.inv_hammer_shadow_ratio = inv_hammer_shadow_ratio
        self.close_above_prev_mid = close_above_prev_mid
        self.divergence_repair_bars = divergence_repair_bars

    # -------------------------------------------------------------------
    # Detectors
    # -------------------------------------------------------------------

    def _detect_bottom_signal_k(self, df: pd.DataFrame) -> pd.Series:
        """Detect 止跌K (bottom signal K-line).

        Conditions:
          - Previous day is bearish (close < open)
          - Pattern is inverted hammer: upper shadow >= ratio * body,
            lower shadow < body, body > 0
          - Close > midpoint of previous bearish body
          - Volume > prev_volume * volume_surge_ratio
        """
        o, h, l, c, v = df["open"], df["high"], df["low"], df["close"], df["volume"]

        prev_bearish = c.shift(1) < o.shift(1)

        bd = _body(o, c)
        us = _upper_shadow(o, c, h)
        ls = _lower_shadow(o, c, l)
        inv_hammer = (us >= self.inv_hammer_shadow_ratio * bd) & (ls < bd) & (bd > 0)

        # Big bullish: body / range > big_bull_body_ratio, bullish candle
        rng = _range(h, l)
        safe_rng = rng.replace(0, float("nan"))
        big_bullish = (bd / safe_rng > self.big_bull_body_ratio) & (c > o) & (bd > 0)

        pattern = inv_hammer | big_bullish

        prev_body_mid = (o.shift(1) + c.shift(1)) / 2
        close_ok = c > prev_body_mid

        vol_ok = v > v.shift(1) * self.volume_surge_ratio

        cond = prev_bearish & pattern & close_ok & vol_ok
        return cond.fillna(False)

    def _detect_confirm_k(self, df: pd.DataFrame) -> pd.Series:
        """Detect 证伪K (confirmation K-line).

        Conditions:
          - Previous bar is a 止跌K (bottom_signal_k)
          - Current day is bullish (close > open) OR close > prev 止跌K close
          - Volume not considered
        """
        o, c = df["open"], df["close"]
        prev_bsk = self._detect_bottom_signal_k(df).shift(1).fillna(False)

        is_bullish = c > o
        close_above = c > c.shift(1)

        cond = prev_bsk & (is_bullish | close_above)
        return cond.fillna(False)

    def _detect_divergence(self, df: pd.DataFrame) -> pd.Series:
        """Detect 量价背离 (volume-price divergence).

        Price up & volume down vs prev day, OR
        Volume up & price down vs prev day.
        """
        c, v = df["close"], df["volume"]

        price_up = c > c.shift(1)
        volume_down = v < v.shift(1)
        volume_up = v > v.shift(1)
        price_down = c < c.shift(1)

        divergence = (price_up & volume_down) | (volume_up & price_down)
        return divergence.fillna(False)

    # -------------------------------------------------------------------
    # State machine
    # -------------------------------------------------------------------

    def _compute_states(
        self,
        df: pd.DataFrame,
        bsk: pd.Series,
        ck: pd.Series,
        div: pd.Series,
    ) -> Tuple[pd.Series, pd.Series]:
        """Compute state and pivot_low for each bar.

        Sequential state machine because each bar's state depends on the
        previous bar's state and pivot_low.
        """
        n = len(df)
        states = ["no_structure"] * n
        pivots = [float("nan")] * n

        current_state = "no_structure"
        current_pivot = float("nan")
        prev_divergence = False  # True if previous bar had divergence awaiting repair

        for i in range(n):
            low_i = df["low"].iloc[i]
            o_i = df["open"].iloc[i]
            c_i = df["close"].iloc[i]
            v_i = df["volume"].iloc[i]
            is_bsk = bool(bsk.iloc[i])
            is_ck = bool(ck.iloc[i])
            is_div = bool(div.iloc[i])

            # Check breakdown first (applies to all states except no_structure/breakdown)
            if current_state in ("forming", "up_phase", "pullback"):
                if low_i < current_pivot:
                    current_state = "breakdown"
                    current_pivot = float("nan")
                    prev_divergence = False

            if current_state == "no_structure":
                if is_bsk:
                    current_state = "forming"
                    current_pivot = low_i

            elif current_state == "forming":
                if is_ck:
                    current_state = "up_phase"

            elif current_state == "up_phase":
                # Check divergence repair from previous bar
                if prev_divergence:
                    prev_v = df["volume"].iloc[i - 1]
                    repaired = (c_i > o_i) and (v_i > prev_v)
                    if not repaired:
                        current_state = "pullback"
                    prev_divergence = False
                # Track new divergence
                elif is_div:
                    prev_divergence = True

            elif current_state == "pullback":
                if is_bsk:
                    current_state = "forming"
                    current_pivot = low_i

            elif current_state == "breakdown":
                if is_bsk:
                    current_state = "forming"
                    current_pivot = low_i

            states[i] = current_state
            pivots[i] = current_pivot

        return pd.Series(states, index=df.index), pd.Series(pivots, index=df.index)

    # -------------------------------------------------------------------
    # Main entry point
    # -------------------------------------------------------------------

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        """Compute structure state for each bar.

        Args:
            df: OHLCV DataFrame (open, high, low, close, volume, DatetimeIndex).

        Returns:
            DataFrame with added columns: state, bottom_signal_k, confirm_k,
            divergence, pivot_low, pullback_depth_pct.
        """
        result = pd.DataFrame(index=df.index)
        result["bottom_signal_k"] = self._detect_bottom_signal_k(df)
        result["confirm_k"] = self._detect_confirm_k(df)
        result["divergence"] = self._detect_divergence(df)
        result["pullback_depth_pct"] = float("nan")

        states, pivots = self._compute_states(
            df, result["bottom_signal_k"], result["confirm_k"], result["divergence"]
        )
        result["state"] = states
        result["pivot_low"] = pivots

        return result
