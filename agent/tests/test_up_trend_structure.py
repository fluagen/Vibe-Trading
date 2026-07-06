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
    """止跌K = 倒锤线 + close > prev bearish body 1/2 + volume > 1.5x prev."""

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
            volumes=[10000, 14000],
        )
        detector = UpTrendStructure()
        result = detector.compute(df)

        assert bool(result.iloc[1]["bottom_signal_k"]) is False

    def test_rejects_when_close_below_prev_midpoint(self):
        """Close below prev bearish body midpoint → not 止跌K."""
        df = _make_ohlcv(
            opens=[100.0, 97.0],
            highs=[102.0, 110.0],
            lows=[90.0, 96.0],
            closes=[90.0, 94.0],
            volumes=[10000, 16000],
        )
        detector = UpTrendStructure()
        result = detector.compute(df)

        assert bool(result.iloc[1]["bottom_signal_k"]) is False

    def test_rejects_when_not_inverted_hammer(self):
        """Regular bullish candle without long upper shadow → not 止跌K."""
        df = _make_ohlcv(
            opens=[100.0, 97.0],
            highs=[102.0, 100.0],
            lows=[90.0, 96.0],
            closes=[90.0, 99.0],
            volumes=[10000, 16000],
        )
        detector = UpTrendStructure()
        result = detector.compute(df)

        assert bool(result.iloc[1]["bottom_signal_k"]) is False


# ---------------------------------------------------------------------------
# Behavior #2: 大阳线 detected as 止跌K
# ---------------------------------------------------------------------------

class TestBottomSignalKBigBullish:
    """止跌K = 大阳线 + close > prev bearish body 1/2 + volume > 1.5x prev."""

    def test_detects_big_bullish_as_bottom_signal_k(self):
        """Big bullish candle (body > 60% range) with volume and close
        conditions should set bottom_signal_k = True."""
        # Day 1: bearish, open=100 close=90, body=10, midpoint=95
        # Day 2: big bullish, open=95 close=105, body=10, range=12
        #         body/range=0.83 > 0.6, close=105 > 95
        #         vol=16000 > 1.5x 10000
        df = _make_ohlcv(
            opens=[100.0, 95.0],
            highs=[102.0, 108.0],
            lows=[90.0, 93.0],
            closes=[90.0, 105.0],
            volumes=[10000, 16000],
        )
        detector = UpTrendStructure()
        result = detector.compute(df)

        assert bool(result.iloc[1]["bottom_signal_k"]) is True

    def test_rejects_when_body_too_small(self):
        """Bullish candle with body < 60% range → not 止跌K."""
        df = _make_ohlcv(
            opens=[100.0, 100.0],
            highs=[102.0, 110.0],
            lows=[90.0, 95.0],
            closes=[90.0, 103.0],
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
    """State transitions: no_structure → forming → up_phase → pullback → breakdown."""

    def test_no_structure_to_forming_on_bottom_signal_k(self):
        """When 止跌K appears in no_structure, state should become 'forming'."""
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

    def test_forming_to_up_phase_on_confirm_k(self):
        """止跌K then 证伪K → state becomes 'up_phase'."""
        df = _make_ohlcv(
            opens=[100.0, 97.0, 100.0],
            highs=[102.0, 110.0, 105.0],
            lows=[90.0, 96.0, 99.0],
            closes=[90.0, 99.0, 103.0],
            volumes=[10000, 16000, 12000],
        )
        detector = UpTrendStructure()
        result = detector.compute(df)

        assert result.iloc[1]["state"] == "forming"
        assert result.iloc[2]["state"] == "up_phase"

    def test_breakdown_when_price_breaks_pivot_low(self):
        """Price below pivot_low during forming → breakdown."""
        # 止跌K at idx 1 with low=96 (pivot), then idx 2 breaks below 96
        df = _make_ohlcv(
            opens=[100.0, 97.0, 90.0],
            highs=[102.0, 110.0, 92.0],
            lows=[90.0, 96.0, 88.0],  # idx 2 low=88 < pivot=96
            closes=[90.0, 99.0, 89.0],
            volumes=[10000, 16000, 5000],
        )
        detector = UpTrendStructure()
        result = detector.compute(df)

        assert result.iloc[1]["state"] == "forming"
        assert result.iloc[2]["state"] == "breakdown"

    def test_stays_in_no_structure_without_signal(self):
        """No 止跌K → state remains 'no_structure'."""
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
    """量价背离且次日不修复 → up_phase ends → pullback begins."""

    def test_up_phase_to_pullback_on_unrepaired_divergence(self):
        """Divergence then next day NOT repaired → pullback.
        Repair = next day bullish with higher volume than divergence day."""
        # Day 1-3: up phase starts (止跌K+证伪K)
        # Day 4: divergence (price up, volume down)
        # Day 5: not repaired (volume down again) → pullback
        df = _make_ohlcv(
            opens=[100.0, 97.0, 100.0, 102.0, 104.0],
            highs=[102.0, 110.0, 105.0, 104.0, 106.0],
            lows=[90.0, 96.0, 99.0, 101.0, 102.0],
            closes=[90.0, 99.0, 103.0, 104.0, 103.0],  # Day 4 close↑, Day 5 close↓
            volumes=[10000, 16000, 12000, 8000, 7000],  # Day 4 vol↓ vs Day 3
        )
        detector = UpTrendStructure()
        result = detector.compute(df)

        assert result.iloc[2]["state"] == "up_phase"   # 证伪K → up_phase
        assert bool(result.iloc[3]["divergence"]) is True    # Day 4: 量价背离
        assert result.iloc[4]["state"] == "pullback"   # Day 5: unrepaired → pullback

    def test_divergence_repaired_stays_in_up_phase(self):
        """Divergence then next day repaired → stays in up_phase.
        Repair = bullish (close > open) with volume > divergence day volume."""
        df = _make_ohlcv(
            opens=[100.0, 97.0, 100.0, 102.0, 100.0],
            highs=[102.0, 110.0, 105.0, 104.0, 106.0],
            lows=[90.0, 96.0, 99.0, 101.0, 99.0],
            closes=[90.0, 99.0, 103.0, 104.0, 105.0],  # Day 5: bullish close↑
            volumes=[10000, 16000, 12000, 8000, 9000],  # Day 5 vol > Day 4 → repaired
        )
        detector = UpTrendStructure()
        result = detector.compute(df)

        assert bool(result.iloc[3]["divergence"]) is True
        assert result.iloc[4]["state"] == "up_phase"   # repaired → stays up_phase


# ---------------------------------------------------------------------------
# Behavior #7: Pullback → next up phase (止跌K + 证伪K in pullback)
# ---------------------------------------------------------------------------

class TestPullbackToNextUpPhase:
    """Pullback ends when new 止跌K + 证伪K appear without breaking pivot."""

    def test_pullback_to_next_up_phase(self):
        """New 止跌K + 证伪K in pullback → next up_phase, new pivot."""
        # Build: up_phase → pullback → new 止跌K + 证伪K
        # Day 1: bearish, Day 2: 止跌K (low=96, pivot), Day 3: 证伪K → up_phase
        # Day 4: divergence (unrepaired)
        # Day 5: pullback starts, stays above pivot=96
        # Day 6: new 止跌K (low=100 > 96, new pivot=100)
        # Day 7: new 证伪K → next up_phase
        df = _make_ohlcv(
            opens=[100.0, 97.0, 100.0, 102.0, 104.0, 99.0, 101.0],
            highs=[102.0, 110.0, 105.0, 104.0, 106.0, 112.0, 108.0],
            lows=[90.0, 96.0, 99.0, 101.0, 102.0, 98.0, 100.0],
            closes=[90.0, 99.0, 103.0, 104.0, 103.0, 104.0, 105.0],
            volumes=[10000, 16000, 12000, 8000, 7000, 16000, 10000],
        )
        detector = UpTrendStructure()
        result = detector.compute(df)

        # Verify transitions
        assert result.iloc[2]["state"] == "up_phase"
        assert result.iloc[4]["state"] == "pullback"
        # Day 5 (idx 5): new 止跌K in pullback → forming
        assert result.iloc[5]["state"] == "forming"
        assert bool(result.iloc[5]["bottom_signal_k"]) is True
        # Day 6 (idx 6): new 证伪K → next up_phase
        assert result.iloc[6]["state"] == "up_phase"
        # New pivot should be Day 5 low = 98 (not the original 96)
        assert result.iloc[6]["pivot_low"] == 98.0
