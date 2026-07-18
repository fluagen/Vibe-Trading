"""Tests for up-trend structure detector.

Tests verify behavior through the public `compute()` interface only.
No internal function testing — tests describe observable state outputs.
"""

import numpy as np
import pandas as pd
import pytest

from src.skills.up_trend_structure.up_trend_structure import UpTrendStructure


def _make_ohlcv(
    opens: list[float],
    highs: list[float],
    lows: list[float],
    closes: list[float],
    volumes: list[float],
) -> pd.DataFrame:
    """Build a minimal OHLCV DataFrame with daily DatetimeIndex."""
    n = len(opens)
    dates = pd.date_range("2026-01-05", periods=n, freq="B")
    return pd.DataFrame(
        {
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": volumes,
        },
        index=dates,
    )


# ---------------------------------------------------------------------------
# Behavior #1: 倒锤线 detected as 止跌K
# ---------------------------------------------------------------------------

class TestBottomSignalKInvertedHammer:
    """止跌K 倒垂: inverted hammer + high > prev_mid + volume surge (v3)."""

    def test_detects_inverted_hammer_as_bottom_signal_k(self):
        """A valid inverted hammer with volume surge and close condition
        should set bottom_signal_k = True."""
        # Day 1: bearish candle, body = 100-90 = 10, midpoint = 95
        # Day 2: inverted hammer — body=2, upper shadow=11 (>=3), lower shadow=1 (<2)
        #         vol=16000 (>1.5x 10000), close=99 > 95 (midpoint)
        df = _make_ohlcv(
            opens=[100.0, 97.0],
            highs=[102.0, 110.0],
            lows=[90.0, 96.0],
            closes=[90.0, 99.0],
            volumes=[10000, 16000],
        )
        detector = UpTrendStructure()
        result = detector.compute(df)

        assert bool(result.iloc[1]["bottom_signal_k"]) is True

    def test_rejects_when_volume_too_low(self):
        """Volume < 1.5x previous day → not 止跌K."""
        df = _make_ohlcv(
            opens=[100.0, 97.0],
            highs=[102.0, 110.0],
            lows=[90.0, 96.0],
            closes=[90.0, 99.0],
            volumes=[10000, 11500],
        )
        detector = UpTrendStructure()
        result = detector.compute(df)

        assert bool(result.iloc[1]["bottom_signal_k"]) is False

    def test_rejects_when_high_below_prev_mid(self):
        """High below prev mid → not 倒垂 止跌K (v3: high > prev_mid required)."""
        # Day 1: bearish, prev_mid = 95
        # Day 2: inverted hammer but high=94 < 95 (prev_mid)
        df = _make_ohlcv(
            opens=[100.0, 97.0],
            highs=[102.0, 94.0],
            lows=[90.0, 91.0],
            closes=[90.0, 93.0],
            volumes=[10000, 16000],
        )
        detector = UpTrendStructure()
        result = detector.compute(df)

        assert bool(result.iloc[1]["bottom_signal_k"]) is False

    def test_rejects_when_not_inverted_hammer(self):
        """Not an inverted hammer AND not a 反包线 → not 止跌K."""
        # Day 2: bullish but close below threshold (93 < prev_mid=95)
        # and no long upper shadow → fails both 倒垂 and 反包线
        df = _make_ohlcv(
            opens=[100.0, 97.0],
            highs=[102.0, 100.0],
            lows=[90.0, 96.0],
            closes=[90.0, 93.0],
            volumes=[10000, 16000],
        )
        detector = UpTrendStructure()
        result = detector.compute(df)

        assert bool(result.iloc[1]["bottom_signal_k"]) is False


# ---------------------------------------------------------------------------
# Behavior #2: 反包线 detected as 止跌K
# ---------------------------------------------------------------------------

class TestBottomSignalKFanbao:
    """止跌K 反包线: prev bearish + bullish + close > threshold + volume surge."""

    def test_detects_fanbao_as_bottom_signal_k(self):
        """Bullish close above threshold with volume surge → 反包线 止跌K."""
        # Day 1: bearish, open=100 close=90, prev_mid=95
        # Day 2: bullish, open=92 close=98, close > threshold(=95 at default 0.5)
        #         vol=16000 > 1.2x 10000
        df = _make_ohlcv(
            opens=[100.0, 92.0],
            highs=[102.0, 100.0],
            lows=[90.0, 91.0],
            closes=[90.0, 98.0],
            volumes=[10000, 16000],
        )
        detector = UpTrendStructure()
        result = detector.compute(df)

        assert bool(result.iloc[1]["bottom_signal_k"]) is True

    def test_rejects_when_not_bullish(self):
        """Bearish candle → not 反包线."""
        # Day 2: bearish (close=94 < open=96)
        df = _make_ohlcv(
            opens=[100.0, 96.0],
            highs=[102.0, 98.0],
            lows=[90.0, 92.0],
            closes=[90.0, 94.0],
            volumes=[10000, 16000],
        )
        detector = UpTrendStructure()
        result = detector.compute(df)

        assert bool(result.iloc[1]["bottom_signal_k"]) is False

    def test_rejects_when_close_below_threshold(self):
        """Close below threshold → not 反包线."""
        # Day 1: bearish, prev_mid=95 (threshold at default 0.5)
        # Day 2: close=93 < 95
        df = _make_ohlcv(
            opens=[100.0, 96.0],
            highs=[102.0, 98.0],
            lows=[90.0, 91.0],
            closes=[90.0, 93.0],
            volumes=[10000, 16000],
        )
        detector = UpTrendStructure()
        result = detector.compute(df)

        assert bool(result.iloc[1]["bottom_signal_k"]) is False

    def test_rejects_when_volume_too_low(self):
        """Volume below threshold → not 反包线."""
        df = _make_ohlcv(
            opens=[100.0, 97.0],
            highs=[102.0, 100.0],
            lows=[90.0, 91.0],
            closes=[90.0, 98.0],
            volumes=[10000, 11500],
        )
        detector = UpTrendStructure()
        result = detector.compute(df)

        assert bool(result.iloc[1]["bottom_signal_k"]) is False

    def test_rejects_when_body_too_small(self):
        """Body/range < big_bull_body_ratio → not 反包线 (doji filter)."""
        # Day 2: bullish, close > threshold, vol surge, BUT body/range too small
        # body = 1, range = 10, ratio = 0.1 < 0.4
        df = _make_ohlcv(
            opens=[100.0, 97.0],
            highs=[102.0, 105.0],
            lows=[90.0, 95.0],
            closes=[90.0, 98.0],
            volumes=[10000, 16000],
        )
        detector = UpTrendStructure()
        result = detector.compute(df)

        assert bool(result.iloc[1]["bottom_signal_k"]) is False


# ---------------------------------------------------------------------------
# Behavior #3: 证伪K detection
# ---------------------------------------------------------------------------

class TestConfirmK:
    """证伪K = next day after 止跌K, bullish or close > 止跌K close."""

    def test_detects_confirm_k_bullish(self):
        """Next day after 止跌K is bullish → confirm_k = True."""
        # Day 1: bearish, Day 2: 止跌K (inverted hammer), Day 3: bullish
        df = _make_ohlcv(
            opens=[100.0, 97.0, 100.0],
            highs=[102.0, 110.0, 105.0],
            lows=[90.0, 96.0, 99.0],
            closes=[90.0, 99.0, 103.0],
            volumes=[10000, 16000, 12000],
        )
        detector = UpTrendStructure()
        result = detector.compute(df)

        # Day 2 (idx 1): 止跌K, Day 3 (idx 2): 证伪K (bullish)
        assert bool(result.iloc[1]["bottom_signal_k"]) is True
        assert bool(result.iloc[2]["confirm_k"]) is True

    def test_detects_confirm_k_close_above(self):
        """Next day after 止跌K closes above 止跌K close → confirm_k = True
        even if bearish candle."""
        # Day 2: 止跌K close=99
        # Day 3: bearish but close=100 > 99
        df = _make_ohlcv(
            opens=[100.0, 97.0, 102.0],
            highs=[102.0, 110.0, 104.0],
            lows=[90.0, 96.0, 99.0],
            closes=[90.0, 99.0, 100.0],
            volumes=[10000, 16000, 8000],
        )
        detector = UpTrendStructure()
        result = detector.compute(df)

        assert bool(result.iloc[1]["bottom_signal_k"]) is True
        assert bool(result.iloc[2]["confirm_k"]) is True

    def test_rejects_when_neither_condition(self):
        """Next day after 止跌K: bearish AND close <= 止跌K close → not 证伪K."""
        df = _make_ohlcv(
            opens=[100.0, 97.0, 102.0],
            highs=[102.0, 110.0, 103.0],
            lows=[90.0, 96.0, 96.0],
            closes=[90.0, 99.0, 97.0],  # bearish, close below 止跌K close
            volumes=[10000, 16000, 8000],
        )
        detector = UpTrendStructure()
        result = detector.compute(df)

        assert bool(result.iloc[1]["bottom_signal_k"]) is True
        assert bool(result.iloc[2]["confirm_k"]) is False


# ---------------------------------------------------------------------------
# Behavior #4: 量价背离 detection
# ---------------------------------------------------------------------------

class TestDivergence:
    """量价背离: price rises but volume shrinks, OR volume rises but price falls."""

    def test_detects_price_up_volume_down(self):
        """Price up vs prev day but volume down → divergence."""
        df = _make_ohlcv(
            opens=[100.0, 100.0],
            highs=[105.0, 106.0],
            lows=[95.0, 99.0],
            closes=[101.0, 104.0],  # close ↑
            volumes=[10000, 8000],  # volume ↓
        )
        detector = UpTrendStructure()
        result = detector.compute(df)

        assert bool(result.iloc[1]["divergence"]) is True

    def test_detects_volume_up_price_down(self):
        """Volume up vs prev day but price down → divergence."""
        df = _make_ohlcv(
            opens=[100.0, 100.0],
            highs=[105.0, 102.0],
            lows=[95.0, 96.0],
            closes=[101.0, 98.0],  # close ↓
            volumes=[10000, 15000],  # volume ↑
        )
        detector = UpTrendStructure()
        result = detector.compute(df)

        assert bool(result.iloc[1]["divergence"]) is True

    def test_no_divergence_when_price_and_volume_sync(self):
        """Price and volume both up → no divergence."""
        df = _make_ohlcv(
            opens=[100.0, 100.0],
            highs=[105.0, 108.0],
            lows=[95.0, 99.0],
            closes=[101.0, 106.0],  # close ↑
            volumes=[10000, 12000],  # volume ↑
        )
        detector = UpTrendStructure()
        result = detector.compute(df)

        assert bool(result.iloc[1]["divergence"]) is False


# ---------------------------------------------------------------------------
# Behavior #5-8: State machine transitions
# ---------------------------------------------------------------------------

class TestStateMachine:
    """v2: 止跌K (价涨量增) still triggers forming, but up_phase needs 2+ days 价涨量增.
    Breakdown is transient → immediately resolves to no_structure."""

    def test_no_structure_to_forming_on_bottom_signal_k(self):
        """止跌K IS 价涨量增, so it triggers no_structure → forming."""
        df = _make_ohlcv(
            opens=[100.0, 97.0],
            highs=[102.0, 110.0],
            lows=[90.0, 96.0],
            closes=[90.0, 99.0],
            volumes=[10000, 16000],
        )
        detector = UpTrendStructure()
        result = detector.compute(df)

        assert result.iloc[0]["state"] == "no_structure"
        assert result.iloc[1]["state"] == "forming"

    def test_forming_to_no_structure_when_volume_drops(self):
        """v2: 止跌K→证伪K from no_structure: 证伪K without volume confirmation (not 价涨量增)
        → forming goes back to no_structure."""
        df = _make_ohlcv(
            opens=[100.0, 97.0, 100.0],
            highs=[102.0, 110.0, 105.0],
            lows=[90.0, 96.0, 99.0],
            closes=[90.0, 99.0, 103.0],
            volumes=[10000, 16000, 12000],  # day 3 vol↓ vs day 2 → not 价涨量增
        )
        detector = UpTrendStructure()
        result = detector.compute(df)

        assert result.iloc[1]["state"] == "forming"
        # 证伪K has close↑ but vol↓ → not 价涨量增 → back to no_structure
        assert result.iloc[2]["state"] == "no_structure"

    def test_breakdown_transient_to_no_structure(self):
        """v2: breakdown is transient → immediately resolves to no_structure."""
        # forming at idx 1 (pivot=96), idx 2 low=88 breaks pivot
        df = _make_ohlcv(
            opens=[100.0, 97.0, 90.0],
            highs=[102.0, 110.0, 92.0],
            lows=[90.0, 96.0, 88.0],
            closes=[90.0, 99.0, 89.0],
            volumes=[10000, 16000, 5000],
        )
        detector = UpTrendStructure()
        result = detector.compute(df)

        assert result.iloc[1]["state"] == "forming"
        # breakdown → immediately no_structure
        assert result.iloc[2]["state"] == "no_structure"

    def test_stays_in_no_structure_without_signal(self):
        """No 价涨量增 → state remains 'no_structure'."""
        df = _make_ohlcv(
            opens=[100.0, 100.0],
            highs=[102.0, 102.0],
            lows=[98.0, 98.0],
            closes=[101.0, 101.0],
            volumes=[10000, 10000],
        )
        detector = UpTrendStructure()
        result = detector.compute(df)

        assert result.iloc[0]["state"] == "no_structure"
        assert result.iloc[1]["state"] == "no_structure"


# ---------------------------------------------------------------------------
# Behavior #6: Divergence → pullback (unrepaired divergence ends up phase)
# ---------------------------------------------------------------------------

class TestDivergenceToPullback:
    """v2: 量价背离/价跌量缩 + 次日不补量 → up_phase ends → pullback."""

    def test_up_phase_to_pullback_on_unrepaired_divergence(self):
        """Divergence then next day NOT repaired → pullback."""
        # Day 1: 价涨量增 (forming), Day 2: 价涨量增 → up_phase
        # Day 3: divergence (price up, volume down)
        # Day 4: NOT repaired (close↓ or vol↓) → pullback
        df = _make_ohlcv(
            opens=[100.0, 101.0, 105.0, 106.0, 104.0],
            highs=[102.0, 108.0, 107.0, 108.0, 106.0],
            lows=[98.0, 100.0, 104.0, 105.0, 102.0],
            closes=[101.0, 106.0, 107.0, 108.0, 103.0],
            volumes=[10000, 12000, 13000, 9000, 8000],
        )
        detector = UpTrendStructure()
        result = detector.compute(df)

        # Day 2 (idx 1): forming, Day 3 (idx 2): up_phase (2nd puvu)
        assert result.iloc[1]["state"] == "forming"
        assert result.iloc[2]["state"] == "up_phase"
        # Day 4 (idx 3): divergence (close↑ vol↓)
        assert bool(result.iloc[3]["divergence"]) is True
        # Day 5 (idx 4): not repaired (close↓, vol↓) → pullback
        assert result.iloc[4]["state"] == "pullback"

    def test_divergence_repaired_stays_in_up_phase(self):
        """Divergence then next day repaired (补量) → stays in up_phase."""
        df = _make_ohlcv(
            opens=[100.0, 101.0, 105.0, 106.0, 103.0],
            highs=[102.0, 108.0, 107.0, 108.0, 109.0],
            lows=[98.0, 100.0, 104.0, 105.0, 102.0],
            closes=[101.0, 106.0, 107.0, 108.0, 110.0],
            volumes=[10000, 12000, 13000, 9000, 10000],
        )
        detector = UpTrendStructure()
        result = detector.compute(df)

        assert result.iloc[1]["state"] == "forming"
        assert result.iloc[2]["state"] == "up_phase"
        # Day 4 (idx 3): divergence (close↑ but vol↓ vs day 3)
        assert bool(result.iloc[3]["divergence"]) is True
        # Day 5 (idx 4): repaired: close=110 > 108(trigger), vol=10000 > 9000(trigger)
        assert result.iloc[4]["state"] == "up_phase"


# ---------------------------------------------------------------------------
# Behavior #7: Pullback → next up phase (止跌K + 证伪K from pullback)
# ---------------------------------------------------------------------------

class TestPullbackToNextUpPhase:
    """v2: 止跌K from pullback → forming, 证伪K → up_phase (new structure)."""

    def test_pullback_to_next_up_phase(self):
        """止跌K + 证伪K in pullback → next up_phase, new pivot."""
        # Day 1-3: 价涨量增 → up_phase (pivot=100 from forming bar)
        # Day 4: divergence, Day 5: unrepaired → pullback
        # Day 6: 止跌K in pullback (low=101 > pivot=100 → no breakdown)
        # Day 7: 证伪K → up_phase (new structure, new pivot=101)
        df = _make_ohlcv(
            opens=[100.0, 101.0, 105.0, 107.0, 105.0, 99.0, 102.0],
            highs=[102.0, 108.0, 108.0, 109.0, 106.0, 112.0, 108.0],
            lows=[98.0, 100.0, 104.0, 106.0, 103.0, 101.0, 102.0],
            closes=[101.0, 106.0, 107.0, 108.0, 104.0, 107.0, 108.0],
            volumes=[10000, 12000, 13000, 9000, 8000, 16000, 12000],
        )
        detector = UpTrendStructure()
        result = detector.compute(df)

        # Day 1-3: forming → up_phase
        assert result.iloc[1]["state"] == "forming"
        assert result.iloc[2]["state"] == "up_phase"
        # Day 5 (idx 4): divergence unrepaired → pullback
        assert result.iloc[4]["state"] == "pullback"
        # Day 6 (idx 5): 止跌K in pullback → forming (new pivot=101, above old pivot)
        assert result.iloc[5]["state"] == "pullback_end"
        assert bool(result.iloc[5]["bottom_signal_k"]) is True
        # Day 7 (idx 6): 证伪K → up_phase (new structure)
        assert result.iloc[6]["state"] == "up_phase"
        # New pivot = 止跌K low = 101
        assert result.iloc[6]["pivot_low"] == 101.0


# ---------------------------------------------------------------------------
# Behavior #8: 价涨量增 detection (v2 new)
# ---------------------------------------------------------------------------


class TestPriceUpVolumeUp:
    """价涨量增 = close > prev_close AND volume > prev_volume."""

    def test_detects_price_up_volume_up(self):
        df = _make_ohlcv(
            opens=[100.0, 101.0], highs=[105.0, 107.0],
            lows=[95.0, 100.0], closes=[101.0, 105.0],
            volumes=[10000, 12000],
        )
        detector = UpTrendStructure()
        result = detector.compute(df)
        assert bool(result.iloc[1]["price_up_volume_up"]) is True

    def test_rejects_when_price_down(self):
        df = _make_ohlcv(
            opens=[100.0, 101.0], highs=[105.0, 103.0],
            lows=[95.0, 98.0], closes=[101.0, 99.0],
            volumes=[10000, 12000],
        )
        detector = UpTrendStructure()
        result = detector.compute(df)
        assert bool(result.iloc[1]["price_up_volume_up"]) is False

    def test_rejects_when_volume_down(self):
        df = _make_ohlcv(
            opens=[100.0, 101.0], highs=[105.0, 107.0],
            lows=[95.0, 100.0], closes=[101.0, 105.0],
            volumes=[10000, 8000],
        )
        detector = UpTrendStructure()
        result = detector.compute(df)
        assert bool(result.iloc[1]["price_up_volume_up"]) is False


# ---------------------------------------------------------------------------
# Behavior #9: 价跌量缩 detection (v2 new)
# ---------------------------------------------------------------------------


class TestPriceVolumeDown:
    """价跌量缩 = close < prev_close AND volume < prev_volume."""

    def test_detects_price_down_volume_down(self):
        df = _make_ohlcv(
            opens=[100.0, 99.0], highs=[105.0, 101.0],
            lows=[95.0, 96.0], closes=[101.0, 97.0],
            volumes=[10000, 7000],
        )
        detector = UpTrendStructure()
        result = detector.compute(df)
        assert bool(result.iloc[1]["price_volume_down"]) is True

    def test_rejects_when_only_price_down(self):
        df = _make_ohlcv(
            opens=[100.0, 99.0], highs=[105.0, 101.0],
            lows=[95.0, 96.0], closes=[101.0, 97.0],
            volumes=[10000, 12000],
        )
        detector = UpTrendStructure()
        result = detector.compute(df)
        assert bool(result.iloc[1]["price_volume_down"]) is False


# ---------------------------------------------------------------------------
# Behavior #10: State machine v2 — entry via 价涨量增
# ---------------------------------------------------------------------------


class TestStateMachineV2Entry:
    """v2: no_structure → forming → up_phase driven by 价涨量增."""

    def test_no_structure_to_forming_on_puvu(self):
        df = _make_ohlcv(
            opens=[100.0, 101.0], highs=[102.0, 107.0],
            lows=[98.0, 100.0], closes=[101.0, 105.0],
            volumes=[10000, 12000],
        )
        detector = UpTrendStructure()
        result = detector.compute(df)
        assert result.iloc[0]["state"] == "no_structure"
        assert result.iloc[1]["state"] == "forming"
        assert result.iloc[1]["pivot_low"] == 100.0

    def test_forming_to_up_phase_on_second_puvu(self):
        df = _make_ohlcv(
            opens=[100.0, 101.0, 102.0], highs=[102.0, 107.0, 109.0],
            lows=[98.0, 100.0, 101.0], closes=[101.0, 105.0, 108.0],
            volumes=[10000, 12000, 13000],
        )
        detector = UpTrendStructure()
        result = detector.compute(df)
        assert result.iloc[1]["state"] == "forming"
        assert result.iloc[2]["state"] == "up_phase"
        assert result.iloc[2]["pivot_low"] == 100.0

    def test_forming_to_no_structure_when_second_fails(self):
        df = _make_ohlcv(
            opens=[100.0, 101.0, 102.0], highs=[102.0, 107.0, 104.0],
            lows=[98.0, 100.0, 100.0], closes=[101.0, 105.0, 101.0],
            volumes=[10000, 12000, 8000],
        )
        detector = UpTrendStructure()
        result = detector.compute(df)
        assert result.iloc[1]["state"] == "forming"
        assert result.iloc[2]["state"] == "no_structure"

    def test_stays_no_structure_without_signal(self):
        df = _make_ohlcv(
            opens=[100.0, 100.0], highs=[102.0, 102.0],
            lows=[98.0, 98.0], closes=[101.0, 101.0],
            volumes=[10000, 9000],
        )
        detector = UpTrendStructure()
        result = detector.compute(df)
        assert result.iloc[0]["state"] == "no_structure"
        assert result.iloc[1]["state"] == "no_structure"

    def test_up_phase_continues_with_puvu(self):
        df = _make_ohlcv(
            opens=[100.0, 101.0, 102.0, 103.0],
            highs=[102.0, 107.0, 109.0, 110.0],
            lows=[98.0, 100.0, 101.0, 102.0],
            closes=[101.0, 105.0, 108.0, 109.0],
            volumes=[10000, 12000, 13000, 14000],
        )
        detector = UpTrendStructure()
        result = detector.compute(df)
        assert result.iloc[1]["state"] == "forming"
        assert result.iloc[2]["state"] == "up_phase"
        assert result.iloc[3]["state"] == "up_phase"

    def test_up_phase_min_bars_default_2(self):
        detector = UpTrendStructure()
        assert detector.up_phase_min_bars == 2


# ---------------------------------------------------------------------------
# Behavior #11: Extended pullback_end confirmation (condition 2)
# ---------------------------------------------------------------------------


class TestPullbackEndExtendedConfirm:
    """v3: pullback_end persists; condition-2 triggers after condition-1 fails."""

    def test_condition2_triggers_after_condition1_fails(self):
        """止跌K 次日 not confirm K, 第三日 收阳+close>止跌K close → up_phase."""
        # Day 1-3: 价涨量增 → up_phase (pivot=100)
        # Day 4: divergence, Day 5: unrepaired → pullback
        # Day 6: 止跌K (反包线, close=107, low=101) → pullback_end
        # Day 7: bearish, close=104 < 107 → NOT confirm K (condition 1 fails)
        # Day 8: bullish + close=108 > 107 → condition 2 triggers → up_phase
        df = _make_ohlcv(
            opens=[100.0, 101.0, 105.0, 107.0, 105.0, 99.0, 105.0, 106.0],
            highs=[102.0, 108.0, 108.0, 109.0, 106.0, 112.0, 106.0, 110.0],
            lows=[98.0, 100.0, 104.0, 106.0, 103.0, 101.0, 102.0, 105.0],
            closes=[101.0, 106.0, 107.0, 108.0, 104.0, 107.0, 104.0, 108.0],
            volumes=[10000, 12000, 13000, 9000, 8000, 16000, 7000, 10000],
        )
        detector = UpTrendStructure()
        result = detector.compute(df)

        # Day 5: pullback
        assert result.iloc[4]["state"] == "pullback"
        # Day 6 (idx 5): 止跌K → pullback_end
        assert result.iloc[5]["state"] == "pullback_end"
        assert bool(result.iloc[5]["bottom_signal_k"]) is True
        # Day 7 (idx 6): bearish, close=104 < 止跌K close=107 → not ck, stays
        assert result.iloc[6]["state"] == "pullback_end"
        assert bool(result.iloc[6]["confirm_k"]) is False
        # Day 8 (idx 7): bullish + close=108 > 107 → condition 2 → up_phase
        assert result.iloc[7]["state"] == "up_phase"
        assert result.iloc[7]["pivot_low"] == 101.0  # 止跌K low

    def test_stays_in_pullback_end_when_condition2_not_met(self):
        """Neither bullish nor close > pullback_end_close → stay pullback_end."""
        # Day 6: 止跌K (close=107, low=101) → pullback_end
        # Day 7: bearish, close=105 < 107 → not ck
        # Day 8: bearish, close=106 < 107 → not condition 2 either
        df = _make_ohlcv(
            opens=[100.0, 101.0, 105.0, 107.0, 105.0, 99.0, 105.0, 107.0],
            highs=[102.0, 108.0, 108.0, 109.0, 106.0, 112.0, 106.0, 108.0],
            lows=[98.0, 100.0, 104.0, 106.0, 103.0, 101.0, 103.0, 104.0],
            closes=[101.0, 106.0, 107.0, 108.0, 104.0, 107.0, 105.0, 106.0],
            volumes=[10000, 12000, 13000, 9000, 8000, 16000, 7000, 8000],
        )
        detector = UpTrendStructure()
        result = detector.compute(df)

        assert result.iloc[5]["state"] == "pullback_end"
        # Day 7: bearish → not ck
        assert result.iloc[6]["state"] == "pullback_end"
        # Day 8: bearish, close=106 < 107 → not condition 2 → stays
        assert result.iloc[7]["state"] == "pullback_end"

    def test_condition2_requires_bullish(self):
        """close > pullback_end_close but bearish → NOT condition 2."""
        # Day 6: 止跌K (close=107) → pullback_end
        # Day 7: bearish, close=106 <= 107 → condition 1 fails
        # Day 8: bearish (open=110 > close=108), close=108 > 107, but not bullish
        df = _make_ohlcv(
            opens=[100.0, 101.0, 105.0, 107.0, 105.0, 99.0, 109.0, 110.0],
            highs=[102.0, 108.0, 108.0, 109.0, 106.0, 112.0, 110.0, 111.0],
            lows=[98.0, 100.0, 104.0, 106.0, 103.0, 101.0, 105.0, 107.0],
            closes=[101.0, 106.0, 107.0, 108.0, 104.0, 107.0, 106.0, 108.0],
            volumes=[10000, 12000, 13000, 9000, 8000, 16000, 7000, 8000],
        )
        detector = UpTrendStructure()
        result = detector.compute(df)

        assert result.iloc[5]["state"] == "pullback_end"
        # Day 7 (idx 6): bearish, close=106 < 107 → condition 1 fails
        assert result.iloc[6]["state"] == "pullback_end"
        # Day 8 (idx 7): bearish (open=110 > close=108), close=108 > 107
        #   condition 2 requires bullish → fails → stays
        assert result.iloc[7]["state"] == "pullback_end"
