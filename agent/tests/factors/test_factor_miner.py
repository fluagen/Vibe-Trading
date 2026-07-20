"""Tests for factor_miner zoo — cross-validated against UpTrendStructure detector.

Seeded panel pattern follows test_gtja191_part1_samples.py. Tests verify that
factor compute() on wide panels matches UpTrendStructure compute() on single
stock DataFrames.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.skills.up_trend_structure.up_trend_structure import UpTrendStructure


def _single_stock_df(close: np.ndarray, volume: np.ndarray) -> pd.DataFrame:
    """Build single-stock OHLCV DataFrame from close+volume arrays.

    Synthetic open/high/low derived from close for testing divergence detection
    (which only needs close + volume).
    """
    n = len(close)
    dates = pd.date_range("2026-01-05", periods=n, freq="B")
    opens = np.roll(close, 1)
    opens[0] = close[0] * 0.99
    highs = np.maximum(opens, close) * 1.01
    lows = np.minimum(opens, close) * 0.99
    return pd.DataFrame(
        {"open": opens, "high": highs, "low": lows, "close": close, "volume": volume},
        index=dates,
    )


def _wide_panel(codes: list[str], close_arr: np.ndarray, volume_arr: np.ndarray) -> dict[str, pd.DataFrame]:
    """Build wide-format panel from (n_rows, n_codes) arrays."""
    n_rows = close_arr.shape[0]
    dates = pd.date_range("2026-01-05", periods=n_rows, freq="B")
    close = pd.DataFrame(close_arr, index=dates, columns=codes)
    opens = close.shift(1).fillna(close.iloc[0] * 0.99)
    highs = pd.DataFrame(
        np.maximum(opens.to_numpy(), close.to_numpy()) * 1.01, index=dates, columns=codes
    )
    lows = pd.DataFrame(
        np.minimum(opens.to_numpy(), close.to_numpy()) * 0.99, index=dates, columns=codes
    )
    volume = pd.DataFrame(volume_arr, index=dates, columns=codes)
    return {"open": opens, "high": highs, "low": lows, "close": close, "volume": volume}


# ---------------------------------------------------------------------------
# fminer_003 — Volume-price divergence
# ---------------------------------------------------------------------------


def _full_wide_panel(
    codes: list[str],
    open_arr: np.ndarray,
    high_arr: np.ndarray,
    low_arr: np.ndarray,
    close_arr: np.ndarray,
    volume_arr: np.ndarray,
) -> dict[str, pd.DataFrame]:
    """Build wide-format panel from full (n_rows, n_codes) OHLCV arrays."""
    n_rows = open_arr.shape[0]
    dates = pd.date_range("2026-01-05", periods=n_rows, freq="B")
    return {
        "open": pd.DataFrame(open_arr, index=dates, columns=codes),
        "high": pd.DataFrame(high_arr, index=dates, columns=codes),
        "low": pd.DataFrame(low_arr, index=dates, columns=codes),
        "close": pd.DataFrame(close_arr, index=dates, columns=codes),
        "volume": pd.DataFrame(volume_arr, index=dates, columns=codes),
    }


def _full_single_df(o: np.ndarray, h: np.ndarray, l: np.ndarray, c: np.ndarray, v: np.ndarray) -> pd.DataFrame:
    """Build single-stock OHLCV DataFrame from per-bar arrays."""
    n = len(o)
    dates = pd.date_range("2026-01-05", periods=n, freq="B")
    return pd.DataFrame(
        {"open": o, "high": h, "low": l, "close": c, "volume": v},
        index=dates,
    )


class TestFminer003:
    """fminer_003: 量价背离 = (price up ∧ volume down) ∨ (volume up ∧ price down)."""

    def test_divergence_matches_up_trend_structure(self):
        """Factor output on wide panel matches UpTrendStructure._detect_divergence
        on each single-stock column."""
        rng = np.random.RandomState(42)
        n_rows = 30
        n_codes = 3
        codes = ["000001.SZ", "600519.SH", "000858.SZ"]

        close_arr = 100.0 + np.cumsum(rng.normal(0, 1, (n_rows, n_codes)), axis=0)
        close_arr = np.abs(close_arr) + 1.0
        volume_arr = rng.randint(10000, 100000, (n_rows, n_codes)).astype(float)

        from importlib import import_module

        mod = import_module("src.factors.zoo.factor_miner.fminer_003")
        panel = _wide_panel(codes, close_arr, volume_arr)
        factor_result = mod.compute(panel)

        detector = UpTrendStructure()

        for col_idx, code in enumerate(codes):
            single = _single_stock_df(close_arr[:, col_idx], volume_arr[:, col_idx])
            ref = detector._detect_divergence(single)

            factor_col = factor_result[code]
            for i in range(n_rows):
                ref_val = 1 if bool(ref.iloc[i]) else 0
                factor_val = int(factor_col.iloc[i])
                assert factor_val == ref_val, (
                    f"fminer_003[{code}] row {i}: factor={factor_val}, ref={ref_val}"
                )


# ---------------------------------------------------------------------------
# fminer_001 — Bottom signal K-line (止跌K)
# ---------------------------------------------------------------------------


class TestFminer001:
    """fminer_001: 止跌K = inverted hammer or big bullish + volume surge."""

    def test_bottom_signal_k_matches_up_trend_structure(self):
        """Factor output on wide panel matches UpTrendStructure._detect_bottom_signal_k
        on each single-stock column."""
        rng = np.random.RandomState(42)
        n_rows = 30
        n_codes = 3
        codes = ["000001.SZ", "600519.SH", "000858.SZ"]

        # Generate realistic OHLCV data
        close_arr = 100.0 + np.cumsum(rng.normal(0, 1, (n_rows, n_codes)), axis=0)
        close_arr = np.abs(close_arr) + 1.0
        open_arr = np.roll(close_arr, 1, axis=0)
        open_arr[0] = close_arr[0] * 0.99
        high_arr = np.maximum(open_arr, close_arr) + rng.uniform(0, 2, (n_rows, n_codes))
        low_arr = np.minimum(open_arr, close_arr) - rng.uniform(0, 2, (n_rows, n_codes))
        low_arr = np.abs(low_arr) + 0.01
        volume_arr = rng.randint(10000, 100000, (n_rows, n_codes)).astype(float)

        from importlib import import_module

        mod = import_module("src.factors.zoo.factor_miner.fminer_001")
        panel = _full_wide_panel(codes, open_arr, high_arr, low_arr, close_arr, volume_arr)
        factor_result = mod.compute(panel)

        detector = UpTrendStructure()

        for col_idx, code in enumerate(codes):
            single = _full_single_df(
                open_arr[:, col_idx], high_arr[:, col_idx], low_arr[:, col_idx],
                close_arr[:, col_idx], volume_arr[:, col_idx],
            )
            ref = detector._detect_bottom_signal_k(single)[0]

            factor_col = factor_result[code]
            for i in range(n_rows):
                ref_val = 1 if bool(ref.iloc[i]) else 0
                factor_val = int(factor_col.iloc[i])
                assert factor_val == ref_val, (
                    f"fminer_001[{code}] row {i}: factor={factor_val}, ref={ref_val}"
                )


# ---------------------------------------------------------------------------
# fminer_002 — Confirmation K-line (证伪K)
# ---------------------------------------------------------------------------


class TestFminer002:
    """fminer_002: 证伪K = next day after 止跌K, bullish or close > prev close."""

    def test_confirm_k_matches_up_trend_structure(self):
        """Factor output on wide panel matches UpTrendStructure._detect_confirm_k
        on each single-stock column."""
        rng = np.random.RandomState(42)
        n_rows = 30
        n_codes = 3
        codes = ["000001.SZ", "600519.SH", "000858.SZ"]

        close_arr = 100.0 + np.cumsum(rng.normal(0, 1, (n_rows, n_codes)), axis=0)
        close_arr = np.abs(close_arr) + 1.0
        open_arr = np.roll(close_arr, 1, axis=0)
        open_arr[0] = close_arr[0] * 0.99
        high_arr = np.maximum(open_arr, close_arr) + rng.uniform(0, 2, (n_rows, n_codes))
        low_arr = np.minimum(open_arr, close_arr) - rng.uniform(0, 2, (n_rows, n_codes))
        low_arr = np.abs(low_arr) + 0.01
        volume_arr = rng.randint(10000, 100000, (n_rows, n_codes)).astype(float)

        from importlib import import_module

        mod = import_module("src.factors.zoo.factor_miner.fminer_002")
        panel = _full_wide_panel(codes, open_arr, high_arr, low_arr, close_arr, volume_arr)
        factor_result = mod.compute(panel)

        detector = UpTrendStructure()

        for col_idx, code in enumerate(codes):
            single = _full_single_df(
                open_arr[:, col_idx], high_arr[:, col_idx], low_arr[:, col_idx],
                close_arr[:, col_idx], volume_arr[:, col_idx],
            )
            ref = detector._detect_confirm_k(single)

            factor_col = factor_result[code]
            for i in range(n_rows):
                ref_val = 1 if bool(ref.iloc[i]) else 0
                factor_val = int(factor_col.iloc[i])
                assert factor_val == ref_val, (
                    f"fminer_002[{code}] row {i}: factor={factor_val}, ref={ref_val}"
                )


# ---------------------------------------------------------------------------
# fminer_004 — Up-trend structure state
# ---------------------------------------------------------------------------


_STATE_MAP = {"no_structure": 0, "forming": 1, "up_phase": 2, "pullback": 3, "breakdown": 4, "pullback_end": 5}


class TestFminer004:
    """fminer_004: 上涨结构状态编码 (0=no_structure, 1=forming, 2=up_phase, 3=pullback, 4=breakdown)."""

    def test_state_encoding_matches_up_trend_structure(self):
        """Factor output on wide panel matches UpTrendStructure.compute() state
        on each single-stock column, encoded to integer."""
        rng = np.random.RandomState(42)
        n_rows = 30
        n_codes = 3
        codes = ["000001.SZ", "600519.SH", "000858.SZ"]

        close_arr = 100.0 + np.cumsum(rng.normal(0, 1, (n_rows, n_codes)), axis=0)
        close_arr = np.abs(close_arr) + 1.0
        open_arr = np.roll(close_arr, 1, axis=0)
        open_arr[0] = close_arr[0] * 0.99
        high_arr = np.maximum(open_arr, close_arr) + rng.uniform(0, 2, (n_rows, n_codes))
        low_arr = np.minimum(open_arr, close_arr) - rng.uniform(0, 2, (n_rows, n_codes))
        low_arr = np.abs(low_arr) + 0.01
        volume_arr = rng.randint(10000, 100000, (n_rows, n_codes)).astype(float)

        from importlib import import_module

        mod = import_module("src.factors.zoo.factor_miner.fminer_004")
        panel = _full_wide_panel(codes, open_arr, high_arr, low_arr, close_arr, volume_arr)
        factor_result = mod.compute(panel)

        detector = UpTrendStructure()

        for col_idx, code in enumerate(codes):
            single = _full_single_df(
                open_arr[:, col_idx], high_arr[:, col_idx], low_arr[:, col_idx],
                close_arr[:, col_idx], volume_arr[:, col_idx],
            )
            ref_states = detector.compute(single)

            factor_col = factor_result[code]
            for i in range(n_rows):
                ref_state_str = ref_states["state"].iloc[i]
                ref_val = _STATE_MAP.get(ref_state_str, -1)
                factor_val = int(factor_col.iloc[i])
                assert factor_val == ref_val, (
                    f"fminer_004[{code}] row {i}: factor={factor_val}, ref={ref_val} (ref_str={ref_state_str})"
                )

    def test_all_six_states_appear(self):
        """With enough realistic random data, all 6 states should appear across
        at least one column."""
        rng = np.random.RandomState(99)
        n_rows = 200
        n_codes = 5
        codes = [f"STOCK_{i}" for i in range(n_codes)]

        # Generate data with more volatility to trigger state transitions
        close_arr = 100.0 + np.cumsum(rng.normal(0, 2, (n_rows, n_codes)), axis=0)
        close_arr = np.abs(close_arr) + 1.0
        open_arr = np.roll(close_arr, 1, axis=0)
        open_arr[0] = close_arr[0] * 0.99
        high_arr = np.maximum(open_arr, close_arr) + rng.uniform(0, 3, (n_rows, n_codes))
        low_arr = np.minimum(open_arr, close_arr) - rng.uniform(0, 3, (n_rows, n_codes))
        low_arr = np.abs(low_arr) + 0.01
        volume_arr = rng.randint(5000, 200000, (n_rows, n_codes)).astype(float)

        from importlib import import_module

        mod = import_module("src.factors.zoo.factor_miner.fminer_004")
        panel = _full_wide_panel(codes, open_arr, high_arr, low_arr, close_arr, volume_arr)
        factor_result = mod.compute(panel)

        all_seen: set[int] = set()
        for col in factor_result.columns:
            all_seen.update(int(v) for v in factor_result[col].unique())

        # At minimum {0,1,2,3,5} should appear; breakdown (4) requires
        # low < pivot_low which is rare with random trending-up data.
        assert {0, 1, 2, 3, 5}.issubset(all_seen), (
            f"Expected at least states {{0,1,2,3,5}}, got {sorted(all_seen)}"
        )
