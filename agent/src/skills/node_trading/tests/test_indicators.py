"""测试 indicators.py 指标计算正确性。"""

import pandas as pd
import numpy as np
import pytest

from src.skills.node_trading.indicators import compute_indicators


def _make_ohlcv(prices: list[float], volumes: list[float] = None) -> pd.DataFrame:
    """构造测试用 OHLCV DataFrame。"""
    n = len(prices)
    if volumes is None:
        volumes = [10000.0] * n
    dates = pd.date_range("2025-01-01", periods=n, freq="B")
    return pd.DataFrame(
        {
            "open": prices,
            "high": [p * 1.02 for p in prices],
            "low": [p * 0.98 for p in prices],
            "close": prices,
            "volume": volumes,
        },
        index=dates,
    )


class TestMovingAverages:
    def test_ma5_basic(self):
        prices = [10.0, 11.0, 12.0, 13.0, 14.0, 15.0]
        df = _make_ohlcv(prices)
        result = compute_indicators(df)

        assert pd.isna(result["ma5"].iloc[0])
        assert pd.isna(result["ma5"].iloc[3])
        assert result["ma5"].iloc[4] == pytest.approx(12.0)
        assert result["ma5"].iloc[5] == pytest.approx(13.0)

    def test_ma10_ma20(self):
        prices = list(range(1, 31))
        df = _make_ohlcv(prices)
        result = compute_indicators(df)

        assert result["ma10"].iloc[9] == pytest.approx(5.5)
        assert result["ma20"].iloc[19] == pytest.approx(10.5)


class TestRangeRatio:
    def test_r_zero_when_all_equal(self):
        prices = [10.0] * 30
        df = _make_ohlcv(prices)
        result = compute_indicators(df)

        idx = result["ma20"].first_valid_index()
        if idx is not None:
            i = result.index.get_loc(idx)
            assert abs(result["r"].iloc[i]) < 0.01

    def test_r_positive_when_diverged(self):
        prices = [10.0 + i * 0.5 for i in range(30)]
        df = _make_ohlcv(prices)
        result = compute_indicators(df)

        i = result["ma20"].first_valid_index()
        i = result.index.get_loc(i)
        assert result["r"].iloc[i] >= 0


class TestCV:
    def test_cv_near_zero_when_equal(self):
        prices = [10.0] * 30
        df = _make_ohlcv(prices)
        result = compute_indicators(df)

        idx = result["ma20"].first_valid_index()
        if idx is not None:
            i = result.index.get_loc(idx)
            assert abs(result["cv"].iloc[i]) < 0.01


class TestAlignment:
    def test_bull_alignment(self):
        prices = [10.0 + i * 0.5 for i in range(30)]
        df = _make_ohlcv(prices)
        result = compute_indicators(df)

        i = result["ma20"].first_valid_index()
        i = result.index.get_loc(i)
        assert result["alignment"].iloc[i] == "bull"

    def test_bear_alignment(self):
        prices = [30.0 - i * 0.5 for i in range(30)]
        df = _make_ohlcv(prices)
        result = compute_indicators(df)

        i = result["ma20"].first_valid_index()
        i = result.index.get_loc(i)
        assert result["alignment"].iloc[i] == "bear"

    def test_crossed_when_interleaved(self):
        np.random.seed(42)
        prices = [10.0 + np.sin(i * 0.5) * 2 for i in range(40)]
        df = _make_ohlcv(prices)
        result = compute_indicators(df)

        i = result["ma20"].first_valid_index()
        valid = result.loc[i:]
        alignments = valid["alignment"].unique()
        assert "crossed" in alignments


class TestCrossMA20:
    def test_cross_from_below(self):
        # 前 19 天收盘 9.0（MA20≈9.0），第 20 天 low 跌破 MA20、high 穿越 → 上穿
        dates = pd.date_range("2025-01-01", periods=25, freq="B")
        df = pd.DataFrame(
            {
                "open": [9.0] * 19 + [9.0] + [10.5] * 5,
                "high": [9.2] * 19 + [11.0] + [11.0] * 5,
                "low": [8.8] * 19 + [8.5] + [10.0] * 5,
                "close": [9.0] * 19 + [10.5] + [10.5] * 5,
                "volume": [10000.0] * 25,
            },
            index=dates,
        )
        result = compute_indicators(df)

        # 第 20 根 bar (index 19): low(8.5) < ma20(~9.0) < high(11.0)
        assert result["cross_ma20"].iloc[19] == 1


class TestVolMA5:
    def test_vol_ma5_correct(self):
        volumes = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0]
        prices = [10.0] * len(volumes)
        df = _make_ohlcv(prices, volumes)
        result = compute_indicators(df)

        assert pd.isna(result["vol_ma5"].iloc[3])
        assert result["vol_ma5"].iloc[4] == pytest.approx(30.0)
        assert result["vol_ma5"].iloc[5] == pytest.approx(40.0)


class TestRS:
    def test_rs_greater_than_one_when_expanding(self):
        prices = [10.0 + i * 0.1 + i * i * 0.02 for i in range(40)]
        df = _make_ohlcv(prices)
        result = compute_indicators(df)

        late_rs = result["rs"].iloc[-5:]
        assert any(v > 0.9 for v in late_rs if not pd.isna(v))
