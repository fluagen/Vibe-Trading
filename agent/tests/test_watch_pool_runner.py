"""Test WatchPoolRunner — strategy execution with mocked loader."""

from __future__ import annotations

from unittest.mock import MagicMock

import pandas as pd
import pytest

from src.api.watch_pool_runner import run_scan_blocking


def _make_ohlcv(dates: list[str], prices: list[float], volumes: list[float]) -> pd.DataFrame:
    df = pd.DataFrame(
        {
            "open": [p - 0.1 for p in prices],
            "high": [p + 0.2 for p in prices],
            "low": [p - 0.3 for p in prices],
            "close": prices,
            "volume": volumes,
        },
        index=pd.DatetimeIndex(pd.to_datetime(dates)),
    )
    return df


def _make_bullish_df(n_bars: int = 10) -> pd.DataFrame:
    dates = pd.date_range("2026-06-01", periods=n_bars, freq="B")
    prices = [10.0 + i * 0.5 for i in range(n_bars)]
    volumes = [1000 + i * 100 for i in range(n_bars)]
    return _make_ohlcv([str(d.date()) for d in dates], prices, volumes)


def _mock_loader(df_map: dict[str, pd.DataFrame]):
    """Create a mock loader whose fetch() returns the given DataFrames."""
    loader = MagicMock()
    loader.is_available.return_value = True
    loader.fetch.return_value = df_map
    return loader


class TestRunScanBlocking:
    def test_returns_result_per_code(self, monkeypatch):
        df = _make_bullish_df(10)
        loader = _mock_loader({"600519.SH": df})
        monkeypatch.setattr("src.api.watch_pool_runner._get_loader", lambda: loader)

        progress = []
        result = run_scan_blocking(
            job_id="test-job",
            strategy_name="up_trend_structure",
            codes=["600519.SH"],
            on_progress=lambda done, total, code: progress.append((done, total, code)),
        )

        assert "600519.SH" in result
        r = result["600519.SH"]
        assert "state" in r
        assert "position_signal" in r
        assert "date" in r
        assert progress

    def test_multiple_codes(self, monkeypatch):
        df1 = _make_bullish_df(10)
        df2 = _make_bullish_df(10)
        loader = _mock_loader({"600519.SH": df1, "000001.SZ": df2})
        monkeypatch.setattr("src.api.watch_pool_runner._get_loader", lambda: loader)

        progress = []
        result = run_scan_blocking(
            job_id="test-job-2",
            strategy_name="up_trend_structure",
            codes=["600519.SH", "000001.SZ"],
            on_progress=lambda done, total, code: progress.append((done, total, code)),
        )

        assert len(result) == 2
        assert progress[-1][0] == 2

    def test_handles_fetch_failure(self, monkeypatch):
        df = _make_bullish_df(10)
        loader = _mock_loader({"600519.SH": df})  # 000001.SZ not in map
        monkeypatch.setattr("src.api.watch_pool_runner._get_loader", lambda: loader)

        result = run_scan_blocking(
            job_id="test-job-3",
            strategy_name="up_trend_structure",
            codes=["600519.SH", "000001.SZ"],
            on_progress=lambda done, total, code: None,
        )

        assert "600519.SH" in result
        assert "000001.SZ" not in result

    def test_unknown_strategy_raises(self):
        with pytest.raises(ValueError, match="Unknown strategy"):
            run_scan_blocking(
                job_id="test-job-4",
                strategy_name="nonexistent_strategy",
                codes=["600519.SH"],
                on_progress=lambda done, total, code: None,
            )

    def test_progress_tracks_all_codes(self, monkeypatch):
        df = _make_bullish_df(10)
        codes = [f"00000{i}.SZ" for i in range(1, 6)]
        loader = _mock_loader({c: df for c in codes})
        monkeypatch.setattr("src.api.watch_pool_runner._get_loader", lambda: loader)

        progress_events = []
        run_scan_blocking(
            job_id="test-job-5",
            strategy_name="up_trend_structure",
            codes=codes,
            on_progress=lambda done, total, code: progress_events.append((done, total, code)),
        )

        assert len(progress_events) == 5
        for i, (done, total, code) in enumerate(progress_events):
            assert done == i + 1
            assert total == 5
