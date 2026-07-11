"""Per-stock backtest engine for strategy research.

Runs the up-trend structure strategy (detector + signal engine) on each
stock independently, evaluates per-stock performance metrics, and
produces compact summaries (OHLCV snapshot + signal points) suitable for
streaming to the frontend.

Follows the ``watch_pool_runner.py`` pattern — same STRATEGY_MAP,
same loader resolution, same per-code iteration — but extends the output
to full backtest metrics instead of a single target-date signal.
"""

from __future__ import annotations

import importlib
import logging
from typing import Any, Callable

import numpy as np
import pandas as pd

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Strategy registry — same shape as watch_pool_runner.STRATEGY_MAP.
# Adding a new strategy means adding an entry here + adding it to the
# GET /strategy-research/strategies response in routes.
# ---------------------------------------------------------------------------

STRATEGY_MAP: dict[str, dict[str, str]] = {
    "up_trend_structure": {
        "detector_module": "src.skills.up_trend_structure.up_trend_structure",
        "detector_class": "UpTrendStructure",
        "signal_module": "src.skills.up_trend_structure.signal_engine",
        "signal_class": "SignalEngine",
    },
}


# Parameter keys used by the detector (UpTrendStructure.__init__).
_DETECTOR_PARAM_KEYS = {
    "up_phase_min_bars",
    "volume_surge_ratio",
    "big_bull_body_ratio",
    "inv_hammer_shadow_ratio",
    "close_above_prev_mid",
    "divergence_repair_bars",
}

# Parameter keys used by the signal engine (SignalEngine.__init__).
_SIGNAL_PARAM_KEYS = _DETECTOR_PARAM_KEYS | {"stop_loss_pct"}


def _load_strategy(strategy_name: str):
    entry = STRATEGY_MAP.get(strategy_name)
    if not entry:
        raise ValueError(f"Unknown strategy: {strategy_name}")
    detector_mod = importlib.import_module(entry["detector_module"])
    detector_cls = getattr(detector_mod, entry["detector_class"])
    signal_mod = importlib.import_module(entry["signal_module"])
    signal_cls = getattr(signal_mod, entry["signal_class"])
    return detector_cls, signal_cls


def _split_params(params: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Split combined params dict into detector_kwargs and signal_kwargs."""
    detector_kwargs = {k: v for k, v in params.items() if k in _DETECTOR_PARAM_KEYS}
    signal_kwargs = {k: v for k, v in params.items() if k in _SIGNAL_PARAM_KEYS}
    return detector_kwargs, signal_kwargs


def _get_loader():
    """Get an available A-share data loader (mootdx preferred)."""
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


# ---------------------------------------------------------------------------
# State label mapping
# ---------------------------------------------------------------------------

_STATE_LABELS: dict[int, str] = {
    0: "no_structure",
    1: "forming",
    2: "up_phase",
    3: "pullback",
    4: "breakdown",
}


def _state_label(val: float | int) -> str:
    try:
        return _STATE_LABELS.get(int(val), "unknown")
    except (ValueError, TypeError):
        return "unknown"


# ---------------------------------------------------------------------------
# Per-stock backtest
# ---------------------------------------------------------------------------


def run_single_stock_backtest(
    code: str,
    df: pd.DataFrame,
    detector: Any,
    signal_engine: Any,
) -> dict[str, Any]:
    """Run backtest for ONE stock.

    Args:
        code: Suffixed stock code (e.g. ``"600519.SH"``).
        df: OHLCV DataFrame (columns: open, high, low, close, volume;
            DatetimeIndex).
        detector: ``UpTrendStructure`` instance (or equivalent for future
            strategies).
        signal_engine: ``SignalEngine`` instance.

    Returns a dict with summary, signals, equity_curve, and ohlcv_snapshot
    suitable for JSON serialization.
    """
    if df is None or df.empty:
        return _empty_result(code)

    # 1. Compute structure states.
    try:
        states = detector.compute(df)
    except Exception:
        _log.warning("detector.compute failed for %s", code, exc_info=True)
        return _empty_result(code)

    # 2. Generate position signals.
    try:
        signals = signal_engine.generate({code: df})
        sig_series = signals.get(code, pd.Series(dtype=float))
    except Exception:
        _log.warning("signal_engine.generate failed for %s", code, exc_info=True)
        sig_series = pd.Series(dtype=float)

    # 3. Evaluate per-stock performance.
    metrics = _evaluate_performance(df, sig_series)

    # 4. Build signal point list (for frontend chart markers).
    signal_points = _build_signal_points(df, sig_series)

    # 5. Build OHLCV snapshot (last ~100 bars for mini chart).
    ohlcv_snapshot = _build_ohlcv_snapshot(df, signal_points)

    # 6. Current state (latest bar).
    final_state = "no_structure"
    if not states.empty and "state" in states.columns:
        final_state = _state_label(states["state"].iloc[-1])

    # 7. States summary (count of days in each state).
    states_summary: dict[str, int] = {}
    if not states.empty and "state" in states.columns:
        counts = states["state"].value_counts().to_dict()
        states_summary = {_state_label(k): int(v) for k, v in counts.items()}

    # 8. Signal statistics for text display.
    bsk_count = int(states["bottom_signal_k"].sum()) if (
        not states.empty and "bottom_signal_k" in states.columns
    ) else 0
    ck_count = int(states["confirm_k"].sum()) if (
        not states.empty and "confirm_k" in states.columns
    ) else 0

    return {
        "code": code,
        "name": code,
        "final_state": final_state,
        "trade_count": metrics["trade_count"],
        "win_rate": metrics["win_rate"],
        "win_count": metrics["win_count"],
        "loss_count": metrics["loss_count"],
        "cumulative_return": metrics["cumulative_return"],
        "annual_return": metrics["annual_return"],
        "max_drawdown": metrics["max_drawdown"],
        "sharpe": metrics["sharpe"],
        "bsk_count": bsk_count,
        "ck_count": ck_count,
        "latest_signal": signal_points[-1] if signal_points else None,
        "signal_points": signal_points,
        "equity_curve": metrics["equity_curve"],
        "states_summary": states_summary,
        "ohlcv_snapshot": ohlcv_snapshot,
    }


# ---------------------------------------------------------------------------
# Batch runner (called from routes with SSE)
# ---------------------------------------------------------------------------


def run_backtest_blocking(
    job_id: str,
    codes: list[str],
    start_date: str,
    end_date: str,
    strategy_name: str,
    on_progress: Callable[[int, int, str], None],
    on_stock_result: Callable[[int, dict[str, Any]], None] | None = None,
    params: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """Run per-stock backtest for all *codes*.

    Args:
        job_id: UUID for logging / job-tracking.
        codes: Suffixed stock codes (``"600519.SH"``, ...).
        start_date: Backtest window start (YYYY-MM-DD).
        end_date: Backtest window end (YYYY-MM-DD).
        strategy_name: Key into ``STRATEGY_MAP``.
        on_progress: Called after each stock: ``(done, total, code)``.
        on_stock_result: Called after each stock with the summary dict
            for SSE incremental streaming.  May be None.
        params: Optional parameter overrides for the strategy detector
            and signal engine.  When omitted, defaults are used.

    Returns dict keyed by code — each value is the full per-stock result.
    """
    detector_cls, signal_cls = _load_strategy(strategy_name)

    if params:
        detector_kwargs, signal_kwargs = _split_params(params)
    else:
        detector_kwargs, signal_kwargs = {}, {}

    detector = detector_cls(**detector_kwargs)
    signal_engine = signal_cls(**signal_kwargs)
    loader = _get_loader()

    results: dict[str, dict[str, Any]] = {}
    total = len(codes)

    for i, code in enumerate(codes):
        try:
            data_map = loader.fetch(
                [code], start_date=start_date, end_date=end_date, interval="1D"
            )
            df = data_map.get(code)
            result = run_single_stock_backtest(code, df, detector, signal_engine)
            results[code] = result

            if on_stock_result:
                on_stock_result(i + 1, result)
        except Exception as exc:
            _log.warning("Backtest %s: failed for %s: %s", job_id, code, exc)
            results[code] = _empty_result(code)

        on_progress(i + 1, total, code)

    return results


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _empty_result(code: str) -> dict[str, Any]:
    return {
        "code": code,
        "name": code,
        "final_state": "no_structure",
        "trade_count": 0,
        "win_rate": 0.0,
        "win_count": 0,
        "loss_count": 0,
        "cumulative_return": 0.0,
        "annual_return": 0.0,
        "max_drawdown": 0.0,
        "sharpe": 0.0,
        "bsk_count": 0,
        "ck_count": 0,
        "latest_signal": None,
        "signal_points": [],
        "equity_curve": [],
        "states_summary": {},
        "ohlcv_snapshot": [],
    }


def _evaluate_performance(
    df: pd.DataFrame,
    signals: pd.Series,
) -> dict[str, Any]:
    """Compute per-stock metrics from OHLCV + position signals.

    The signals series has the same DatetimeIndex as *df* and contains
    position values: 0.0 (flat), 0.33 (trial), 0.67 (confirm), 1.0 (full),
    -1.0 (exit).

    Trades are identified by scanning for position changes:
    - entry: 0 → >0 (new entry) or position increase (add)
    - exit:  >0 → ≤0
    """
    close = df["close"]
    n_bars = len(close)

    # ---- identify trades ----
    entries: list[dict[str, Any]] = []
    exits: list[dict[str, Any]] = []

    position = 0.0
    for idx in range(len(signals)):
        sig = float(signals.iloc[idx])
        date_str = str(signals.index[idx])[:10]
        price = float(close.iloc[idx])

        if sig > 0 and position == 0:
            entries.append({"date": date_str, "price": price, "signal": sig})
            position = sig
        elif sig > 0 and position > 0 and sig > position:
            entries.append({"date": date_str, "price": price, "signal": sig})
            position = sig
        elif sig < 0 and position > 0:
            exits.append({"date": date_str, "price": price})
            position = 0.0

    # Match entries and exits into trades.
    trades = min(len(entries), len(exits))
    win_count = sum(
        1 for i in range(trades) if exits[i]["price"] > entries[i]["price"]
    )
    loss_count = trades - win_count
    win_rate = (win_count / trades) if trades > 0 else 0.0

    # ---- equity curve (daily) ----
    daily_position = _compute_daily_position(signals)
    daily_return = close.pct_change().fillna(0.0) * daily_position.shift(1).fillna(0.0)
    equity = (1.0 + daily_return).cumprod()
    cumulative_return = float(equity.iloc[-1] - 1.0) if len(equity) > 0 else 0.0

    equity_curve = [
        {"date": str(equity.index[i])[:10], "equity": round(float(equity.iloc[i]), 6)}
        for i in range(len(equity))
    ]

    # ---- derived metrics ----
    annual_factor = 252 / max(n_bars, 1)
    annual_return = (1.0 + cumulative_return) ** annual_factor - 1.0 if n_bars > 0 else 0.0

    daily_returns = daily_return[daily_return != 0]
    if len(daily_returns) > 1:
        mean_ret = float(daily_returns.mean())
        std_ret = float(daily_returns.std())
        sharpe = (mean_ret / std_ret * np.sqrt(252)) if std_ret > 0 else 0.0
        rolling_max = equity.cummax()
        drawdown = (equity - rolling_max) / rolling_max
        max_drawdown = float(drawdown.min()) if len(drawdown) > 0 else 0.0
    else:
        sharpe = 0.0
        max_drawdown = 0.0

    return {
        "trade_count": trades,
        "win_rate": round(win_rate, 4),
        "win_count": win_count,
        "loss_count": loss_count,
        "cumulative_return": round(cumulative_return, 6),
        "annual_return": round(annual_return, 6),
        "max_drawdown": round(max_drawdown, 6),
        "sharpe": round(sharpe, 4),
        "equity_curve": equity_curve,
    }


def _compute_daily_position(signals: pd.Series) -> pd.Series:
    """Convert sparse signal events into a daily position series.

    Between signal events the position stays at the last signal value.
    When position becomes negative (exit), it resets to 0 until the next
    positive signal.
    """
    position = pd.Series(0.0, index=signals.index)
    current = 0.0
    for idx in signals.index:
        sig = float(signals.loc[idx])
        if sig < 0:
            current = 0.0
        elif sig > 0:
            current = sig
        position.loc[idx] = current
    return position


def _build_signal_points(
    df: pd.DataFrame,
    signals: pd.Series,
) -> list[dict[str, Any]]:
    """Extract signal change points for frontend chart markers."""
    points: list[dict[str, Any]] = []
    prev = 0.0
    for idx in signals.index:
        sig = float(signals.loc[idx])
        if sig != prev:
            entry_types = {0.33: "entry_trial", 0.67: "entry_confirm", 1.0: "entry_full"}
            exit_types = {-1.0: "exit"}
            if sig > 0:
                stype = entry_types.get(round(sig, 2), "entry")
            elif sig < 0:
                stype = exit_types.get(round(sig, 2), "exit")
            else:
                stype = "flat"

            try:
                price = float(df["close"].loc[idx])
            except (KeyError, TypeError):
                price = 0.0

            points.append({
                "date": str(idx)[:10],
                "type": stype,
                "price": round(price, 2),
                "signal_value": round(sig, 2),
            })
        prev = sig
    return points


def _build_ohlcv_snapshot(
    df: pd.DataFrame,
    signal_points: list[dict[str, Any]],
    max_bars: int = 100,
) -> list[dict[str, Any]]:
    """Build a compact OHLCV snapshot (last *max_bars*) for mini chart.

    Returns a list of dicts with date, open, high, low, close, volume + a
    ``has_signal`` boolean flag so the frontend can overlay markers.
    """
    if df is None or df.empty:
        return []

    df_slice = df.tail(max_bars)
    signal_dates = {s["date"] for s in signal_points}

    bars: list[dict[str, Any]] = []
    for idx in df_slice.index:
        date_str = str(idx)[:10]
        try:
            bar = {
                "date": date_str,
                "open": round(float(df_slice.loc[idx, "open"]), 2),
                "high": round(float(df_slice.loc[idx, "high"]), 2),
                "low": round(float(df_slice.loc[idx, "low"]), 2),
                "close": round(float(df_slice.loc[idx, "close"]), 2),
                "volume": int(df_slice.loc[idx, "volume"]),
                "has_signal": date_str in signal_dates,
            }
        except (KeyError, TypeError, ValueError):
            continue
        bars.append(bar)

    return bars
