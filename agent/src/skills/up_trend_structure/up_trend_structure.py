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
        big_bull_body_ratio: float = 0.4,
        inv_hammer_shadow_ratio: float = 1.1,
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

    def _detect_bottom_signal_k(self, df: pd.DataFrame) -> tuple:
        """Detect 止跌K (bottom signal K-line).

        v3: three patterns with priority 倒垂 > 反包线 > 两日筑底.
        Pattern 1 — 倒垂: inverted hammer + high > prev_mid + vol surge.
        Pattern 2 — 反包线: prev bearish + bullish + close > threshold + vol surge.
        Pattern 3 — 两日筑底: D0 bearish → D1 bullish (not P1/P2) → D2 bullish+vol↑+close>D0_mid.

        Returns:
            (bottom_signal_k, p1_daochui, p2_fanbao, p3_two_day) — the union
            boolean Series plus the three individual pattern Series (unfilled).
        """
        o, h, l, c, v = df["open"], df["high"], df["low"], df["close"], df["volume"]

        prev_bearish = c.shift(1) < o.shift(1)
        prev_mid = (o.shift(1) + c.shift(1)) / 2

        # Pattern 1: 倒垂 — inverted hammer with high above prev_mid
        bd = _body(o, c)
        us = _upper_shadow(o, c, h)
        ls = _lower_shadow(o, c, l)
        inv_hammer = (us >= self.inv_hammer_shadow_ratio * bd) & (ls < bd) & (bd > 0)
        p1_daochui = prev_bearish & inv_hammer & (h > prev_mid) & (v > v.shift(1) * self.volume_surge_ratio)

        # Pattern 2: 反包线 — bullish close above threshold (default threshold = prev_mid)
        #   + body/range > big_bull_body_ratio (filters doji false-bullish candles)
        threshold = c.shift(1) + (o.shift(1) - c.shift(1)) * self.close_above_prev_mid
        is_bullish = c > o
        rng = _range(h, l)
        safe_rng = rng.replace(0, float("nan"))
        body_ratio_ok = (bd / safe_rng) > self.big_bull_body_ratio
        p2_fanbao = prev_bearish & is_bullish & body_ratio_ok & (c > threshold) & (v > v.shift(1) * self.volume_surge_ratio)

        # Pattern 3: 两日筑底
        # D0 bearish → D1 bullish (NOT P1 AND NOT P2) → D2 bullish+vol↑+close>D0_mid → D2 is 止跌K
        d0_bearish = c.shift(2) < o.shift(2)
        d0_mid = (o.shift(2) + c.shift(2)) / 2
        d1_bull = c.shift(1) > o.shift(1)
        d1_is_bsk = p1_daochui.shift(1).fillna(False) | p2_fanbao.shift(1).fillna(False)
        d2_bull = c > o
        d2_vol = v > v.shift(1)
        d2_close = c > d0_mid
        p3_two_day = d0_bearish & d1_bull & ~d1_is_bsk & d2_bull & d2_vol & d2_close

        # Union with priority: 倒垂 > 反包线 > 两日筑底
        result = p1_daochui | p2_fanbao | p3_two_day
        return result.fillna(False), p1_daochui.fillna(False), p2_fanbao.fillna(False), p3_two_day.fillna(False)

    def _detect_confirm_k(self, df: pd.DataFrame) -> pd.Series:
        """Detect 证伪K (confirmation K-line).

        Conditions:
          - Previous bar is a 止跌K (bottom_signal_k)
          - Current day is bullish (close > open) OR close > prev 止跌K close
          - Volume not considered
        """
        o, c = df["open"], df["close"]
        prev_bsk = self._detect_bottom_signal_k(df)[0].shift(1).fillna(False)

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
    # State machine (v3)
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

        v3 state transitions:

        no_structure + 价涨量增 → forming (pivot = forming low)
          forming + 价涨量增 → up_phase (pivot = forming low)
          forming + !价涨量增 → no_structure

        up_phase + 价涨量增 → up_phase (continue)
        up_phase + divergence/价跌量缩 → pending repair
          repair next day → up_phase (continue)
          no repair next day → pullback

        pullback + 止跌K → pullback_end (pullback_end_low = 止跌K low)
          pullback_end + 证伪K → up_phase (pivot = pullback_end_low)
          pullback_end + low < pullback_end_low → pullback
          pullback_end + otherwise → stay in pullback_end

        any(!no_structure) + low < pivot → breakdown → no_structure
        """
        n = len(df)
        states = ["no_structure"] * n
        pivots = [float("nan")] * n

        current_state = "no_structure"
        current_pivot = float("nan")

        # Low and close of the 止跌K that triggered pullback_end entry.
        # pullback_end_low: new pivot when → up_phase; floor for staying.
        # pullback_end_close: condition-2 confirm threshold (收阳 + close > this).
        pullback_end_low = float("nan")
        pullback_end_close = float("nan")

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
                    pullback_end_low = float("nan")
                    pullback_end_close = float("nan")
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
                    # pivot stays as forming bar's low (set on entry)
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
                    pullback_end_low = low_i
                    pullback_end_close = close_i
                    current_state = "pullback_end"
                    # pivot unchanged — only set when entering up_phase

            # --- pullback_end ---
            elif current_state == "pullback_end":
                # Condition 1: 证伪K on the bar right after 止跌K
                # Condition 2: extended — 收阳 + close > 止跌K close
                is_bullish = close_i > df["open"].iloc[i]
                if is_ck:
                    current_state = "up_phase"
                    current_pivot = pullback_end_low
                    pullback_end_low = float("nan")
                    pullback_end_close = float("nan")
                elif is_bullish and close_i > pullback_end_close:
                    current_state = "up_phase"
                    current_pivot = pullback_end_low
                    pullback_end_low = float("nan")
                    pullback_end_close = float("nan")
                elif low_i < pullback_end_low:
                    current_state = "pullback"
                    pullback_end_low = float("nan")
                    pullback_end_close = float("nan")
                # else: stay in pullback_end, wait for confirm or breakdown

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
        bsk_all, p1, p2, p3 = self._detect_bottom_signal_k(df)
        result["bottom_signal_k"] = bsk_all
        # Record which sub-pattern triggered (priority: 倒垂 > 反包 > 筑底)
        result["bsk_pattern"] = ""
        result.loc[p1, "bsk_pattern"] = "倒垂"
        result.loc[p2 & ~p1, "bsk_pattern"] = "反包"
        result.loc[p3 & ~p1 & ~p2, "bsk_pattern"] = "筑底"
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
