"""Up-trend structure detector.

State machine that processes OHLCV bars and outputs the current structure state
for each bar: no_structure → forming → up_phase → pullback → breakdown.

v2: Up-phase defined by 2+ consecutive days of 价涨量增 (price↑ + volume↑).
    止跌K/证伪K restart structures from pullback.
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
    """Detect up-trend structure states from daily OHLCV data.

    v2: Entering up_phase requires 2+ consecutive days of 价涨量增
    (close > prev_close AND volume > prev_volume). 止跌K/证伪K now
    restart structures from pullback rather than defining initial entry.
    """

    def __init__(
        self,
        up_phase_min_bars: int = 2,
        volume_surge_ratio: float = 1.2,
        big_bull_body_ratio: float = 0.6,
        inv_hammer_shadow_ratio: float = 1.2,
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

    def _detect_price_up_volume_up(self, df: pd.DataFrame) -> pd.Series:
        """Detect 价涨量增: close > prev_close AND volume > prev_volume."""
        c, v = df["close"], df["volume"]
        price_up = c > c.shift(1)
        volume_up = v > v.shift(1)
        result = price_up & volume_up
        return result.fillna(False)

    def _detect_price_volume_down(self, df: pd.DataFrame) -> pd.Series:
        """Detect 价跌量缩: close < prev_close AND volume < prev_volume."""
        c, v = df["close"], df["volume"]
        price_down = c < c.shift(1)
        volume_down = v < v.shift(1)
        result = price_down & volume_down
        return result.fillna(False)

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
    # State machine (v2)
    # -------------------------------------------------------------------

    def _compute_states(
        self,
        df: pd.DataFrame,
        puvu: pd.Series,
        pvd: pd.Series,
        bsk: pd.Series,
        ck: pd.Series,
        div: pd.Series,
    ) -> Tuple[pd.Series, pd.Series]:
        """Compute state and pivot_low for each bar.

        v2 state transitions:

        no_structure + 价涨量增 → forming (pivot = current low)
          forming + 价涨量增 → up_phase
          forming + !价涨量增 → no_structure

        up_phase + 价涨量增 → up_phase (continue)
        up_phase + divergence/价跌量缩 → pending repair
          repair next day → up_phase (continue)
          no repair next day → pullback

        pullback + 止跌K → pullback_end (new pivot)
          pullback_end + 证伪K → up_phase
          pullback_end + !证伪K → pullback

        any(!no_structure) + low < pivot → breakdown → no_structure
        """
        n = len(df)
        states = ["no_structure"] * n
        pivots = [float("nan")] * n

        current_state = "no_structure"
        current_pivot = float("nan")

        # Pending exit condition awaiting next-day repair (补量)
        pending_exit = None  # "divergence" or "price_volume_down"
        pending_close = float("nan")
        pending_volume = float("nan")

        for i in range(n):
            low_i = df["low"].iloc[i]
            close_i = df["close"].iloc[i]
            volume_i = df["volume"].iloc[i]
            is_puvu = bool(puvu.iloc[i])
            is_pvd = bool(pvd.iloc[i])
            is_bsk = bool(bsk.iloc[i])
            is_ck = bool(ck.iloc[i])
            is_div = bool(div.iloc[i])

            # --- Breakdown check (all states except no_structure) ---
            if current_state != "no_structure":
                if low_i < current_pivot:
                    current_state = "breakdown"
                    current_pivot = float("nan")
                    pending_exit = None

            # --- breakdown → no_structure (immediate) ---
            if current_state == "breakdown":
                current_state = "no_structure"

            # --- no_structure ---
            elif current_state == "no_structure":
                if is_puvu:
                    current_state = "forming"
                    current_pivot = low_i

            # --- forming ---
            elif current_state == "forming":
                if is_puvu:
                    current_state = "up_phase"
                else:
                    current_state = "no_structure"
                    current_pivot = float("nan")

            # --- up_phase ---
            elif current_state == "up_phase":
                if pending_exit is not None:
                    repaired = (close_i > pending_close and volume_i > pending_volume)
                    if repaired:
                        pending_exit = None
                        pending_close = float("nan")
                        pending_volume = float("nan")
                    else:
                        current_state = "pullback"
                        pending_exit = None
                        pending_close = float("nan")
                        pending_volume = float("nan")
                elif is_div:
                    pending_exit = "divergence"
                    pending_close = close_i
                    pending_volume = volume_i
                elif is_pvd:
                    pending_exit = "price_volume_down"
                    pending_close = close_i
                    pending_volume = volume_i

            # --- pullback ---
            elif current_state == "pullback":
                if is_bsk:
                    current_state = "pullback_end"
                    current_pivot = low_i

            # --- pullback_end ---
            elif current_state == "pullback_end":
                if is_ck:
                    current_state = "up_phase"
                else:
                    current_state = "pullback"

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
            DataFrame with columns: state, bottom_signal_k, confirm_k,
            divergence, price_up_volume_up, price_volume_down,
            pivot_low, pullback_depth_pct.
        """
        result = pd.DataFrame(index=df.index)
        result["price_up_volume_up"] = self._detect_price_up_volume_up(df)
        result["price_volume_down"] = self._detect_price_volume_down(df)
        result["bottom_signal_k"] = self._detect_bottom_signal_k(df)
        result["confirm_k"] = self._detect_confirm_k(df)
        result["divergence"] = self._detect_divergence(df)
        result["pullback_depth_pct"] = float("nan")

        states, pivots = self._compute_states(
            df,
            result["price_up_volume_up"],
            result["price_volume_down"],
            result["bottom_signal_k"],
            result["confirm_k"],
            result["divergence"],
        )
        result["state"] = states
        result["pivot_low"] = pivots

        return result
