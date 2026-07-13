"""Tests for up-trend-structure SignalEngine v2.

v2 changes:
- Remove 1.0 full position (max 0.67)
- Three-tier cascade take-profit: 30% profit -> 5MA -> 10MA
- 止跌K only triggers entry from pullback -> forming (not no_structure -> forming)
"""

import numpy as np
import pandas as pd
import pytest

from src.skills.up_trend_structure.signal_engine import SignalEngine


def _make_ohlcv(opens, highs, lows, closes, volumes):
    n = len(opens)
    dates = pd.date_range("2026-01-05", periods=n, freq="B")
    return pd.DataFrame(
        {"open": opens, "high": highs, "low": lows, "close": closes, "volume": volumes},
        index=dates,
    )


# Shared setup: up_phase -> pullback before 止跌K entry
# bar0: bearish, bar1: 价涨量增(止跌K) -> forming, bar2: 价涨量增 -> up_phase
# bar3: divergence, bar4: unrepaired -> pullback, bar5: low stays above pivot
# bar6: 止跌K -> forming (entry!), bar7: 证伪K -> add
PULLBACK_SETUP_7 = dict(
    opens=[100, 101, 105, 108, 106, 99, 97],
    highs=[102, 108, 109, 110, 108, 102, 110],
    lows=[90, 100, 104, 106, 104, 100, 100],
    closes=[90, 106, 108, 109, 105, 93, 99],
    volumes=[10000, 15000, 16000, 8000, 7000, 10000, 16000],
)


class TestEntryOnBottomSignalK:
    """v2: 止跌K only triggers entry when pullback -> forming."""

    def test_bottom_signal_k_triggers_entry(self):
        df = _make_ohlcv(**PULLBACK_SETUP_7)
        engine = SignalEngine()
        signals = engine.generate({"000001.SZ": df})
        sig = signals["000001.SZ"]
        assert sig.iloc[6] == pytest.approx(0.33, abs=0.01)


class TestAddOnConfirmK:
    """v2: 止跌K -> 证伪K -> signal 0.67."""

    def test_confirm_k_adds_position(self):
        # Add 证伪K after 止跌K entry
        opens = PULLBACK_SETUP_7["opens"] + [102]
        highs = PULLBACK_SETUP_7["highs"] + [108]
        lows = PULLBACK_SETUP_7["lows"] + [102]
        closes = PULLBACK_SETUP_7["closes"] + [107]
        volumes = PULLBACK_SETUP_7["volumes"] + [12000]
        df = _make_ohlcv(opens, highs, lows, closes, volumes)
        engine = SignalEngine()
        signals = engine.generate({"000001.SZ": df})
        sig = signals["000001.SZ"]
        assert sig.iloc[6] == pytest.approx(0.33, abs=0.01)
        assert sig.iloc[7] == pytest.approx(0.67, abs=0.01)


class TestMaxPosition:
    """v2: Max position is 0.67, never 1.0."""

    def test_max_position_is_0_67(self):
        opens = PULLBACK_SETUP_7["opens"] + [102]
        highs = PULLBACK_SETUP_7["highs"] + [108]
        lows = PULLBACK_SETUP_7["lows"] + [102]
        closes = PULLBACK_SETUP_7["closes"] + [107]
        volumes = PULLBACK_SETUP_7["volumes"] + [12000]
        df = _make_ohlcv(opens, highs, lows, closes, volumes)
        engine = SignalEngine()
        signals = engine.generate({"000001.SZ": df})
        sig = signals["000001.SZ"]
        assert sig.iloc[7] == pytest.approx(0.67, abs=0.01)
        assert (sig >= 1.0).sum() == 0


class TestTakeProfit30Pct:
    """Profit >= 30% -> sell half position."""

    def test_profit_30_sells_half(self):
        # Build pullback setup then entry, then rally to >30%
        opens = PULLBACK_SETUP_7["opens"] + [102, 103, 106, 108, 112, 120, 135, 140, 141]
        highs = PULLBACK_SETUP_7["highs"] + [108, 108, 110, 114, 120, 130, 140, 142, 143]
        lows = PULLBACK_SETUP_7["lows"] + [102, 102, 104, 106, 110, 118, 133, 138, 140]
        closes = PULLBACK_SETUP_7["closes"] + [107, 107, 109, 111, 118, 128, 138, 141, 142]
        volumes = PULLBACK_SETUP_7["volumes"] + [12000, 11000, 12000, 13000, 14000, 15000, 16000, 15000, 14000]
        df = _make_ohlcv(opens, highs, lows, closes, volumes)
        engine = SignalEngine(take_profit_pct=0.30)
        signals = engine.generate({"000001.SZ": df})
        sig = signals["000001.SZ"]
        assert sig.iloc[6] == pytest.approx(0.33, abs=0.01)
        assert sig.iloc[7] == pytest.approx(0.67, abs=0.01)
        found = any(sig.iloc[i] < 0.67 and sig.iloc[i] > 0 for i in range(8, len(sig)))
        assert found, "Should find a partial take-profit signal"


class TestStopLoss:
    """v2: stop loss unchanged, entry requires pullback context."""

    def test_stop_loss_on_pivot_break(self):
        opens = PULLBACK_SETUP_7["opens"] + [90]
        highs = PULLBACK_SETUP_7["highs"] + [92]
        lows = PULLBACK_SETUP_7["lows"] + [88]   # breaks pivot
        closes = PULLBACK_SETUP_7["closes"] + [89]
        volumes = PULLBACK_SETUP_7["volumes"] + [5000]
        df = _make_ohlcv(opens, highs, lows, closes, volumes)
        engine = SignalEngine()
        signals = engine.generate({"000001.SZ": df})
        sig = signals["000001.SZ"]
        assert sig.iloc[6] == pytest.approx(0.33, abs=0.01)
        assert sig.iloc[7] == -1.0  # stop loss


class TestTakeProfitDivergence:
    """v2: Divergence unrepaired -> pullback -> exit."""

    def test_divergence_unrepaired_exits(self):
        # After entry and add, divergence -> unrepaired -> exit
        opens = PULLBACK_SETUP_7["opens"] + [105, 107, 105, 104]
        highs = PULLBACK_SETUP_7["highs"] + [108, 109, 106, 106]
        lows = PULLBACK_SETUP_7["lows"] + [104, 106, 103, 102]
        closes = PULLBACK_SETUP_7["closes"] + [107, 108, 104, 103]
        volumes = PULLBACK_SETUP_7["volumes"] + [17000, 9000, 8000, 7000]
        df = _make_ohlcv(opens, highs, lows, closes, volumes)
        engine = SignalEngine()
        signals = engine.generate({"000001.SZ": df})
        sig = signals["000001.SZ"]
        assert sig.iloc[6] == pytest.approx(0.33, abs=0.01)
        assert sig.iloc[7] == pytest.approx(0.67, abs=0.01)
        assert sig.iloc[9] == -1.0  # divergence unrepaired -> pullback -> exit
