"""Batch scan runner — fetches OHLCV, runs strategy detector + signal engine."""

from __future__ import annotations

import importlib
import logging
from typing import Any, Callable

import pandas as pd

_log = logging.getLogger(__name__)

STRATEGY_MAP: dict[str, dict[str, str]] = {
    "up_trend_structure": {
        "detector_module": "src.skills.up_trend_structure.up_trend_structure",
        "detector_class": "UpTrendStructure",
        "signal_module": "src.skills.up_trend_structure.signal_engine",
        "signal_class": "SignalEngine",
    },
}


def _load_strategy(strategy_name: str):
    entry = STRATEGY_MAP.get(strategy_name)
    if not entry:
        raise ValueError(f"Unknown strategy: {strategy_name}")
    detector_mod = importlib.import_module(entry["detector_module"])
    detector_cls = getattr(detector_mod, entry["detector_class"])
    signal_mod = importlib.import_module(entry["signal_module"])
    signal_cls = getattr(signal_mod, entry["signal_class"])
    return detector_cls, signal_cls


def _get_loader():
    """Get an available A-share data loader."""
    from backtest.loaders.registry import LOADER_REGISTRY, _ensure_registered
    _ensure_registered()

    for name in ["mootdx", "baostock", "eastmoney", "akshare", "tushare"]:
        cls = LOADER_REGISTRY.get(name)
        if cls is None:
            continue
        try:
            loader = cls()
            if loader.is_available():
                return loader
        except Exception:
            continue
    raise RuntimeError("No available A-share data loader")


def run_scan_blocking(
    job_id: str,
    strategy_name: str,
    codes: list[str],
    on_progress: Callable[[int, int, str], None],
    start_date: str = "2026-01-01",
    target_date: str | None = None,
) -> dict[str, dict[str, Any]]:
    """Run a strategy scan against a list of stock codes.

    Args:
        target_date: YYYY-MM-DD to extract signal for. Defaults to today.

    Returns dict keyed by code: {code, name, state, position_signal, date}.
    """
    if target_date is None:
        target_date = pd.Timestamp.now().strftime("%Y-%m-%d")

    detector_cls, signal_cls = _load_strategy(strategy_name)
    detector = detector_cls()
    signal_engine = signal_cls()
    loader = _get_loader()

    results: dict[str, dict[str, Any]] = {}
    total = len(codes)

    for i, code in enumerate(codes):
        try:
            data_map = loader.fetch([code], start_date, end_date=target_date, interval="1D")
            df = data_map.get(code)
            if df is None or df.empty:
                on_progress(i + 1, total, code)
                continue

            states = detector.compute(df)
            signals = signal_engine.generate({code: df})

            target_ts = pd.Timestamp(target_date)
            if target_ts in states.index:
                state = str(states.loc[target_ts, "state"])
            else:
                state = str(states["state"].iloc[-1]) if not states.empty else "no_structure"

            sig_series = signals.get(code)
            if sig_series is not None and target_ts in sig_series.index:
                last_signal = float(sig_series.loc[target_ts])
            elif sig_series is not None and not sig_series.empty:
                last_signal = float(sig_series.iloc[-1])
            else:
                last_signal = 0.0

            results[code] = {
                "code": code,
                "name": str(code),
                "state": state,
                "position_signal": last_signal,
                "date": target_date,
            }
        except Exception as exc:
            _log.warning("Scan %s: failed for %s: %s", job_id, code, exc)

        on_progress(i + 1, total, code)

    return results
