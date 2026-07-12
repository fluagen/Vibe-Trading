"""Tests for up-trend-structure SignalEngine v2.

v2 changes:
- Remove 1.0 full position (max 0.67)
- Three-tier cascade take-profit: 30% profit → 5MA → 10MA
- Entry via 价涨量增 (止跌K=forming, 证伪K or 2nd puvu=up_phase)
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
    n = len(opens)
    dates = pd.date_range("2026-01-05", periods=n, freq="B")
    return pd.DataFrame(
        {"open": opens, "high": highs, "low": lows, "close": closes, "volume": volumes},
        index=dates,
    )


# ---------------------------------------------------------------------------
# Behavior #1: 止跌K → enter 0.33
# ---------------------------------------------------------------------------

class TestEntryOnBottomSignalK:
    """止跌K appears (价涨量增) → signal = 0.33."""

    def test_bottom_signal_k_triggers_entry(self):
        df = _make_ohlcv(
            opens=[100.0, 97.0], highs=[102.0, 110.0],
            lows=[90.0, 96.0], closes=[90.0, 99.0],
            volumes=[10000, 16000],
        )
        engine = SignalEngine()
        signals = engine.generate({"000001.SZ": df})
        sig = signals["000001.SZ"]
        assert sig.iloc[0] == 0.0
        assert sig.iloc[1] == pytest.approx(0.33, abs=0.01)


# ---------------------------------------------------------------------------
# Behavior #2: 证伪K → add to 0.67 (from pullback restart)
# ---------------------------------------------------------------------------

class TestAddOnConfirmK:
    """v2: Pullback restart: 止跌K → 证伪K → signal 0.67."""

    def test_confirm_k_adds_position(self):
        """Pullback restart: 止跌K→0.33, 证伪K→0.67."""
        # Build: up_phase → pullback → 止跌K → 证伪K → new up_phase
        df = _make_ohlcv(
            opens=[100.0, 101.0, 105.0, 107.0, 105.0, 99.0, 102.0],
            highs=[102.0, 108.0, 108.0, 109.0, 106.0, 112.0, 108.0],
            lows=[98.0, 100.0, 104.0, 106.0, 103.0, 101.0, 102.0],
            closes=[101.0, 106.0, 107.0, 108.0, 104.0, 107.0, 108.0],
            volumes=[10000, 12000, 13000, 9000, 8000, 16000, 12000],
        )
        engine = SignalEngine()
        signals = engine.generate({"000001.SZ": df})
        sig = signals["000001.SZ"]
        # Day 6 (idx 5): 止跌K → 0.33
        assert sig.iloc[5] == pytest.approx(0.33, abs=0.01)
        # Day 7 (idx 6): 证伪K → 0.67
        assert sig.iloc[6] == pytest.approx(0.67, abs=0.01)


# ---------------------------------------------------------------------------
# Behavior #3: No 1.0 full position (max = 0.67)
# ---------------------------------------------------------------------------

class TestMaxPosition:
    """v2: Max position is 0.67, never 1.0."""

    def test_max_position_is_0_67(self):
        """After 证伪K, position stays at 0.67, never goes to 1.0."""
        df = _make_ohlcv(
            opens=[100.0, 101.0, 105.0, 107.0, 105.0, 99.0, 102.0],
            highs=[102.0, 108.0, 108.0, 109.0, 106.0, 112.0, 108.0],
            lows=[98.0, 100.0, 104.0, 106.0, 103.0, 101.0, 102.0],
            closes=[101.0, 106.0, 107.0, 108.0, 104.0, 107.0, 108.0],
            volumes=[10000, 12000, 13000, 9000, 8000, 16000, 12000],
        )
        engine = SignalEngine()
        signals = engine.generate({"000001.SZ": df})
        sig = signals["000001.SZ"]
        assert sig.iloc[6] == pytest.approx(0.67, abs=0.01)
        # No signal should be 1.0
        assert (sig >= 1.0).sum() == 0


# ---------------------------------------------------------------------------
# Behavior #4: Take profit — 30% profit → sell half
# ---------------------------------------------------------------------------

class TestTakeProfit30Pct:
    """Profit ≥ 30% → sell half position."""

    def test_profit_30_sells_half(self):
        """Entry at 0.67, price rises 40% → takes profit half."""
        # Entry at ~100, price rises to ~140
        df = _make_ohlcv(
            opens=[100.0, 101.0, 105.0, 107.0, 105.0, 99.0, 102.0, 103.0, 106.0,
                    108.0, 112.0, 120.0, 135.0, 140.0, 141.0],
            highs=[102.0, 108.0, 108.0, 109.0, 106.0, 112.0, 108.0, 108.0, 110.0,
                    114.0, 120.0, 130.0, 140.0, 142.0, 143.0],
            lows=[98.0, 100.0, 104.0, 106.0, 103.0, 101.0, 102.0, 102.0, 104.0,
                    106.0, 110.0, 118.0, 133.0, 138.0, 140.0],
            closes=[101.0, 106.0, 107.0, 108.0, 104.0, 107.0, 108.0, 107.0, 109.0,
                    111.0, 118.0, 128.0, 138.0, 141.0, 142.0],
            volumes=[10000, 12000, 13000, 9000, 8000, 16000, 12000, 11000, 12000,
                     13000, 14000, 15000, 16000, 15000, 14000],
        )
        engine = SignalEngine(take_profit_pct=0.30)
        signals = engine.generate({"000001.SZ": df})
        sig = signals["000001.SZ"]

        # Day 6 (idx 5): 止跌K → 0.33
        assert sig.iloc[5] == pytest.approx(0.33, abs=0.01)
        # Day 7 (idx 6): 证伪K → 0.67
        assert sig.iloc[6] == pytest.approx(0.67, abs=0.01)
        # Around idx 13 (close=141, entry ~107): profit > 30% → sell half → 0.335
        # Find the first bar after entry where profit >= 30%
        found_take_profit = False
        for i in range(7, len(sig)):
            if sig.iloc[i] < 0.67 and sig.iloc[i] > 0:
                found_take_profit = True
                break
        assert found_take_profit, "Should find a partial take-profit signal"


# ---------------------------------------------------------------------------
# Behavior #5: Stop loss still works
# ---------------------------------------------------------------------------

class TestStopLoss:
    """Stop loss unchanged in v2."""

    def test_stop_loss_on_pivot_break(self):
        df = _make_ohlcv(
            opens=[100.0, 97.0, 90.0], highs=[102.0, 110.0, 92.0],
            lows=[90.0, 96.0, 88.0], closes=[90.0, 99.0, 89.0],
            volumes=[10000, 16000, 5000],
        )
        engine = SignalEngine()
        signals = engine.generate({"000001.SZ": df})
        sig = signals["000001.SZ"]
        assert sig.iloc[1] == pytest.approx(0.33, abs=0.01)
        assert sig.iloc[2] == -1.0


# ---------------------------------------------------------------------------
# Behavior #6: Take profit — divergence unrepaired
# ---------------------------------------------------------------------------

class TestTakeProfitDivergence:
    """v2: Divergence unrepaired → pullback → exit."""

    def test_divergence_unrepaired_exits(self):
        df = _make_ohlcv(
            opens=[100.0, 97.0, 105.0, 107.0, 105.0, 104.0],
            highs=[102.0, 110.0, 108.0, 109.0, 106.0, 106.0],
            lows=[90.0, 96.0, 104.0, 106.0, 103.0, 102.0],
            closes=[90.0, 106.0, 107.0, 108.0, 104.0, 103.0],
            volumes=[10000, 16000, 17000, 9000, 8000, 7000],
        )
        engine = SignalEngine()
        signals = engine.generate({"000001.SZ": df})
        sig = signals["000001.SZ"]
        # forming → up_phase via 价涨量增
        assert sig.iloc[1] == pytest.approx(0.33, abs=0.01)  # forming (止跌K)
        assert sig.iloc[2] == pytest.approx(0.67, abs=0.01)  # up_phase (2nd puvu)
        # divergence unrepaired → pullback → exit
        assert sig.iloc[4] == -1.0
