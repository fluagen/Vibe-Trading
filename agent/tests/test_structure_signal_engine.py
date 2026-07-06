"""Tests for up-trend-structure SignalEngine with position management.

Tests verify behavior through the public `generate()` interface only.
"""

import numpy as np
import pandas as pd
import pytest

from src.skills.up_trend_structure.signal_engine import SignalEngine


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
# Behavior #1: 止跌K → enter 1/3 position
# ---------------------------------------------------------------------------

class TestEntryOnBottomSignalK:
    """止跌K appears → signal = 0.33 (1/3 trial entry)."""

    def test_bottom_signal_k_triggers_entry(self):
        """A valid 止跌K should generate signal 0.33."""
        df = _make_ohlcv(
            opens=[100.0, 97.0],
            highs=[102.0, 110.0],
            lows=[90.0, 96.0],
            closes=[90.0, 99.0],
            volumes=[10000, 16000],
        )
        data_map = {"000001.SZ": df}
        engine = SignalEngine()
        signals = engine.generate(data_map)

        sig = signals["000001.SZ"]
        assert sig.iloc[0] == 0.0
        assert sig.iloc[1] == pytest.approx(0.33, abs=0.01)


# ---------------------------------------------------------------------------
# Behavior #2: 证伪K → add to 0.67 position
# ---------------------------------------------------------------------------

class TestAddOnConfirmK:
    """证伪K confirms 止跌K → signal = 0.67 (add to 2/3)."""

    def test_confirm_k_adds_position(self):
        """止跌K then 证伪K → signal goes 0.33 then 0.67."""
        df = _make_ohlcv(
            opens=[100.0, 97.0, 100.0],
            highs=[102.0, 110.0, 105.0],
            lows=[90.0, 96.0, 99.0],
            closes=[90.0, 99.0, 103.0],
            volumes=[10000, 16000, 12000],
        )
        data_map = {"000001.SZ": df}
        engine = SignalEngine()
        signals = engine.generate(data_map)

        sig = signals["000001.SZ"]
        assert sig.iloc[1] == pytest.approx(0.33, abs=0.01)  # 止跌K → 1/3
        assert sig.iloc[2] == pytest.approx(0.67, abs=0.01)  # 证伪K → 2/3


# ---------------------------------------------------------------------------
# Behavior #3: Stop loss — price breaks pivot
# ---------------------------------------------------------------------------

class TestStopLossBreakPivot:
    """Price breaking below 止跌K pivot_low → exit (-1.0)."""

    def test_stop_loss_on_pivot_break(self):
        """After entry, low < pivot → signal -1.0."""
        # Day 2: 止跌K with low=96 (pivot=96), Day 3: low=95 < 96 → stop
        df = _make_ohlcv(
            opens=[100.0, 97.0, 90.0],
            highs=[102.0, 110.0, 92.0],
            lows=[90.0, 96.0, 88.0],
            closes=[90.0, 99.0, 89.0],
            volumes=[10000, 16000, 5000],
        )
        data_map = {"000001.SZ": df}
        engine = SignalEngine()
        signals = engine.generate(data_map)

        sig = signals["000001.SZ"]
        assert sig.iloc[1] == pytest.approx(0.33, abs=0.01)
        assert sig.iloc[2] == -1.0  # Stop loss


# ---------------------------------------------------------------------------
# Behavior #4: Stop loss — unrealized loss > 3%
# ---------------------------------------------------------------------------

class TestStopLossPercent:
    """Unrealized loss > 3% → exit (-1.0)."""

    def test_percent_stop_loss(self):
        """Entry at close=99, then close drops to 95 → >3% loss → stop."""
        df = _make_ohlcv(
            opens=[100.0, 97.0, 95.0],
            highs=[102.0, 110.0, 97.0],
            lows=[90.0, 96.0, 94.0],
            closes=[90.0, 99.0, 95.0],  # 95/99 - 1 = -4.04%
            volumes=[10000, 16000, 12000],
        )
        data_map = {"000001.SZ": df}
        engine = SignalEngine(stop_loss_pct=0.03)
        signals = engine.generate(data_map)

        sig = signals["000001.SZ"]
        assert sig.iloc[1] == pytest.approx(0.33, abs=0.01)
        assert sig.iloc[2] == -1.0


# ---------------------------------------------------------------------------
# Behavior #5: Take profit — divergence unrepaired
# ---------------------------------------------------------------------------

class TestTakeProfitDivergence:
    """Divergence unrepaired in up_phase → take profit (-1.0)."""

    def test_divergence_unrepaired_exits(self):
        """In position, divergence → unrepaired → pullback → exit."""
        df = _make_ohlcv(
            opens=[100.0, 97.0, 100.0, 102.0, 104.0],
            highs=[102.0, 110.0, 105.0, 104.0, 106.0],
            lows=[90.0, 96.0, 99.0, 101.0, 100.0],
            closes=[90.0, 99.0, 103.0, 104.0, 103.0],
            volumes=[10000, 16000, 12000, 8000, 7000],  # Day 4 vol↓, Day 5 not repaired
        )
        data_map = {"000001.SZ": df}
        engine = SignalEngine()
        signals = engine.generate(data_map)

        sig = signals["000001.SZ"]
        assert sig.iloc[1] == pytest.approx(0.33, abs=0.01)  # 止跌K
        assert sig.iloc[2] == pytest.approx(0.67, abs=0.01)  # 证伪K
        # Day 5 (idx 4): unrepaired → pullback → take profit
        assert sig.iloc[4] == -1.0
