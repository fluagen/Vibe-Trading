"""Per-stock backtest engine for strategy research.

Runs the up-trend structure strategy (detector + signal engine) on each
stock independently, evaluates per-stock performance metrics, and
produces compact summaries (OHLCV snapshot + signal points) suitable for
streaming to the frontend.

Per-code iteration with STRATEGY_MAP and loader resolution, extending output
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
# Strategy registry.
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
    "node_trading": {
        "signal_module": "src.skills.node_trading.signal_engine",
        "signal_class": "SignalEngine",
        "has_detector": "false",
    },
}


def _strategy_has_detector(strategy_name: str) -> bool:
    entry = STRATEGY_MAP.get(strategy_name, {})
    return entry.get("has_detector", "true") != "false"


# Parameter keys shared by both detector and signal engine.
_COMMON_PARAM_KEYS = {
    "up_phase_min_bars",
    "volume_surge_ratio",
    "big_bull_body_ratio",
    "inv_hammer_shadow_ratio",
    "close_above_prev_mid",
}

# Parameter keys used by the detector (UpTrendStructure.__init__).
_DETECTOR_PARAM_KEYS = _COMMON_PARAM_KEYS | {"divergence_repair_bars"}

# Parameter keys used by the signal engine (SignalEngine.__init__).
_SIGNAL_PARAM_KEYS = _COMMON_PARAM_KEYS | {"stop_loss_pct", "take_profit_pct", "ma_short", "ma_mid"}

# All parameter keys for node_trading SignalEngine (22 params, no separate detector).
_NODE_TRADING_PARAM_KEYS = {
    "r_s5", "cv_s5", "r_s4", "rs_s4",
    "r_s3_lower", "r_s3_upper", "cv_s3", "r_s2_lower", "r_s2_upper",
    "reversal_vol_ratio", "s2_reversal_r_min", "support_ma_tolerance", "s1_breakout_vol_ratio",
    "reversal_low_r_size", "reversal_high_r_size", "reversal_r_boundary",
    "support_s3_size", "support_s4_size", "sticky_breakout_size",
    "hard_stop_pct", "reversal_node_fail_days", "tp_r_s5", "tp_r_s4",
}


def _load_strategy(strategy_name: str):
    entry = STRATEGY_MAP.get(strategy_name)
    if not entry:
        raise ValueError(f"Unknown strategy: {strategy_name}")
    signal_mod = importlib.import_module(entry["signal_module"])
    signal_cls = getattr(signal_mod, entry["signal_class"])
    if _strategy_has_detector(strategy_name):
        detector_mod = importlib.import_module(entry["detector_module"])
        detector_cls = getattr(detector_mod, entry["detector_class"])
        return detector_cls, signal_cls
    return None, signal_cls


def _split_params(params: dict[str, Any], strategy_name: str = "up_trend_structure") -> tuple[dict[str, Any], dict[str, Any]]:
    """Split combined params dict into detector_kwargs and signal_kwargs."""
    if strategy_name == "node_trading":
        # All params go to signal engine; no separate detector.
        signal_kwargs = {k: v for k, v in params.items() if k in _NODE_TRADING_PARAM_KEYS}
        return {}, signal_kwargs
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


def _state_label(val: float | int | str) -> str:
    try:
        return _STATE_LABELS.get(int(val), str(val))
    except (ValueError, TypeError):
        # State machine now returns string labels directly (e.g. "up_phase")
        return str(val) if val else "no_structure"


# ---------------------------------------------------------------------------
# Per-stock backtest
# ---------------------------------------------------------------------------


def run_single_stock_backtest(
    code: str,
    df: pd.DataFrame,
    detector: Any,
    signal_engine: Any,
    strategy_name: str = "up_trend_structure",
) -> dict[str, Any]:
    """Run backtest for ONE stock.

    Args:
        code: Suffixed stock code (e.g. ``"600519.SH"``).
        df: OHLCV DataFrame (columns: open, high, low, close, volume;
            DatetimeIndex).
        detector: ``UpTrendStructure`` instance (or None for strategies
            without separate detector, e.g. node_trading).
        signal_engine: ``SignalEngine`` instance.
        strategy_name: Key into ``STRATEGY_MAP``.

    Returns a dict with summary, signals, equity_curve, and ohlcv_snapshot
    suitable for JSON serialization.
    """
    if df is None or df.empty:
        return _empty_result(code)

    if strategy_name == "node_trading":
        return _run_node_trading_backtest(code, df, signal_engine)

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
    signal_points = _build_signal_points(df, sig_series, states)

    # 5. Build OHLCV snapshot (last ~100 bars for mini chart).
    ohlcv_snapshot = _build_ohlcv_snapshot(df, states, signal_points)

    # 6. Current state (latest bar) + previous state for transition display.
    final_state = "no_structure"
    previous_state = "no_structure"
    if not states.empty and "state" in states.columns:
        final_state = _state_label(states["state"].iloc[-1])
        if len(states) >= 2:
            previous_state = _state_label(states["state"].iloc[-2])

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

    # 9. Build grouped trade records with reason descriptions.
    stop_loss_pct = getattr(signal_engine, "stop_loss_pct", 0.03)
    ma_short = getattr(signal_engine, "ma_short", 5)
    ma_mid = getattr(signal_engine, "ma_mid", 10)
    trades = _build_trade_records(df, states, sig_series, stop_loss_pct, ma_short, ma_mid)

    # 10. Trading days and date range.
    trading_days = len(df)
    date_start = str(df.index[0])[:10] if len(df) > 0 else ""
    date_end = str(df.index[-1])[:10] if len(df) > 0 else ""

    return {
        "code": code,
        "name": code,
        "final_state": final_state,
        "previous_state": previous_state,
        "trade_count": metrics["trade_count"],
        "win_rate": metrics["win_rate"],
        "win_count": metrics["win_count"],
        "loss_count": metrics["loss_count"],
        "cumulative_return": metrics["cumulative_return"],
        "annual_return": metrics["annual_return"],
        "max_drawdown": metrics["max_drawdown"],
        "sharpe": metrics["sharpe"],
        "annual_volatility": metrics["annual_volatility"],
        "profit_factor": metrics["profit_factor"],
        "final_equity": metrics["final_equity"],
        "bsk_count": bsk_count,
        "ck_count": ck_count,
        "latest_signal": signal_points[-1] if signal_points else None,
        "signal_points": signal_points,
        "trades": trades,
        "trading_days": trading_days,
        "date_start": date_start,
        "date_end": date_end,
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
        detector_kwargs, signal_kwargs = _split_params(params, strategy_name)
    else:
        detector_kwargs, signal_kwargs = {}, {}

    detector = detector_cls(**detector_kwargs) if detector_cls is not None else None
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
            result = run_single_stock_backtest(code, df, detector, signal_engine, strategy_name)
            results[code] = result

            if on_stock_result:
                on_stock_result(i + 1, result)
        except Exception as exc:
            _log.warning("Backtest %s: failed for %s: %s", job_id, code, exc)
            results[code] = _empty_result(code)

        on_progress(i + 1, total, code)

    return results


# ---------------------------------------------------------------------------
# Node trading backtest pipeline
# ---------------------------------------------------------------------------

_NODE_TYPE_LABELS: dict[str, str] = {
    "reversal": "反转",
    "support": "支撑",
    "sticky_breakout": "粘合突破",
}

_NODE_STAGE_LABELS: dict[str, str] = {
    "S1": "蓄势", "S2": "萌芽", "S3": "健康趋势", "S4": "加速", "S5": "极端",
}


def _run_node_trading_backtest(
    code: str, df: pd.DataFrame, signal_engine: Any,
) -> dict[str, Any]:
    """Run node_trading backtest for ONE stock."""
    # 1. Generate signals.
    try:
        signals = signal_engine.generate({code: df})
        sig_series = signals.get(code, pd.Series(dtype=float))
        bar_meta = getattr(signal_engine, "bar_metadata_", [])
    except Exception:
        _log.warning("signal_engine.generate failed for %s", code, exc_info=True)
        return _empty_result(code)

    # 2. Evaluate performance (reuse common metrics).
    metrics = _evaluate_performance(df, sig_series)

    # 3. Build node-trading signal points.
    signal_points = _build_node_trading_signal_points(df, sig_series, bar_meta)

    # 4. Build trade records from bar metadata.
    trades = _build_node_trading_trades(df, sig_series, bar_meta)

    # 5. Stage summary and node counts.
    if bar_meta:
        stage_counts: dict[str, int] = {}
        node_counts: dict[str, int] = {"reversal": 0, "support": 0, "sticky_breakout": 0}
        for m in bar_meta:
            s = m.get("stage", "S1")
            stage_counts[s] = stage_counts.get(s, 0) + 1
            nt = m.get("node_type")
            if nt and nt in node_counts:
                node_counts[nt] += 1
        last_meta = bar_meta[-1]
        latest_stage = last_meta.get("stage", "S1")
        latest_alignment = last_meta.get("alignment", "crossed")
        final_state = f"{latest_stage}({latest_alignment})"
        latest_r = last_meta.get("r", 0)
        latest_cv = last_meta.get("cv", 0)
        latest_rs = last_meta.get("rs", 0)
    else:
        stage_counts = {}
        node_counts = {"reversal": 0, "support": 0, "sticky_breakout": 0}
        final_state = "S1(crossed)"
        latest_stage = "S1"
        latest_alignment = "crossed"
        latest_r = latest_cv = latest_rs = 0.0

    node_count_str = f"反{node_counts['reversal']} 支{node_counts['support']} 突{node_counts['sticky_breakout']}"

    # 6. Build states-like DataFrame for OHLCV snapshot colouring.
    states_df = _node_trading_states_df(df, bar_meta)

    # 7. OHLCV snapshot.
    ohlcv_snapshot = _build_ohlcv_snapshot(df, states_df, signal_points)

    # 8. Current state line data.
    ma5 = float(df["close"].rolling(5).mean().iloc[-1]) if len(df) >= 5 else 0.0
    ma10 = float(df["close"].rolling(10).mean().iloc[-1]) if len(df) >= 10 else 0.0
    ma20 = float(df["close"].rolling(20).mean().iloc[-1]) if len(df) >= 20 else 0.0
    current_close = float(df["close"].iloc[-1])
    current_state_line = (
        f"{final_state} R={latest_r:.1f} CV={latest_cv:.3f} RS={latest_rs:.2f}  |  "
        f"MA5={ma5:.2f} MA10={ma10:.2f} MA20={ma20:.2f} Close={current_close:.2f}"
    )

    trading_days = len(df)
    date_start = str(df.index[0])[:10] if len(df) > 0 else ""
    date_end = str(df.index[-1])[:10] if len(df) > 0 else ""

    return {
        "code": code,
        "name": code,
        "final_state": final_state,
        "previous_state": "",
        "trade_count": metrics["trade_count"],
        "win_rate": metrics["win_rate"],
        "win_count": metrics["win_count"],
        "loss_count": metrics["loss_count"],
        "cumulative_return": metrics["cumulative_return"],
        "annual_return": metrics["annual_return"],
        "max_drawdown": metrics["max_drawdown"],
        "sharpe": metrics["sharpe"],
        "annual_volatility": metrics["annual_volatility"],
        "profit_factor": metrics["profit_factor"],
        "final_equity": metrics["final_equity"],
        "bsk_count": node_counts["reversal"],
        "ck_count": node_counts["support"] + node_counts["sticky_breakout"],
        "node_count_str": node_count_str,
        "latest_stage": latest_stage,
        "latest_alignment": latest_alignment,
        "latest_r": latest_r,
        "latest_cv": latest_cv,
        "latest_rs": latest_rs,
        "current_state_line": current_state_line,
        "latest_signal": signal_points[-1] if signal_points else None,
        "signal_points": signal_points,
        "trades": [],
        "trade_rows": trades,
        "trading_days": trading_days,
        "date_start": date_start,
        "date_end": date_end,
        "equity_curve": metrics["equity_curve"],
        "states_summary": stage_counts,
        "ohlcv_snapshot": ohlcv_snapshot,
    }


def _node_trading_states_df(df: pd.DataFrame, bar_meta: list[dict]) -> pd.DataFrame:
    """Build a states-like DataFrame from bar metadata for OHLCV colouring."""
    states = pd.DataFrame(
        {"state": [m.get("stage", "S1") for m in bar_meta]},
        index=df.index[:len(bar_meta)],
    )
    return states


def _build_node_trading_signal_points(
    df: pd.DataFrame,
    signals: pd.Series,
    bar_meta: list[dict],
) -> list[dict[str, Any]]:
    """Build signal points with node type labels for node_trading."""
    points: list[dict[str, Any]] = []
    position = 0.0
    for i, idx in enumerate(signals.index):
        sig = float(signals.loc[idx])
        if sig == 0.0:
            continue
        try:
            price = float(df["close"].loc[idx])
        except (KeyError, TypeError):
            price = 0.0

        meta = bar_meta[i] if i < len(bar_meta) else {}
        node_type = meta.get("node_type")
        exit_reason = meta.get("exit_reason")

        if sig > 0:
            if position > 0 and sig < position:
                stype = "take_profit"
            elif position > 0 and sig > position:
                stype = "entry_add"
            else:
                stype = "entry"
            position = sig
        else:
            stype = "exit"
            position = 0.0

        pt: dict[str, Any] = {
            "date": str(idx)[:10],
            "type": stype,
            "price": round(price, 2),
            "signal_value": round(sig, 2),
        }
        if node_type:
            label = _NODE_TYPE_LABELS.get(node_type, node_type)
            pt["entry_label"] = f"入({label})"
            pt["entry_pattern"] = node_type
        if exit_reason:
            pt["exit_reason"] = exit_reason
        points.append(pt)
    return points


def _build_node_trading_trades(
    df: pd.DataFrame,
    signals: pd.Series,
    bar_meta: list[dict],
) -> list[dict[str, Any]]:
    """Build flat trade rows for node_trading matching output-template format.

    Each row is one entry→exit pair.  Halving/partial-TP produces multiple rows
    from the same entry.
    """
    if df is None or df.empty or signals.empty:
        return []

    close = df["close"]

    # State: pending entries (FIFO — entries consumed by exits).
    pending: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    position = 0.0

    for i, idx in enumerate(signals.index):
        sig = float(signals.loc[idx])
        if sig == 0.0:
            continue
        try:
            price = float(close.loc[idx])
        except (KeyError, TypeError):
            price = 0.0

        meta = bar_meta[i] if i < len(bar_meta) else {}
        stage = meta.get("stage", "")
        alignment = meta.get("alignment", "")
        r_val = meta.get("r", 0)
        cv_val = meta.get("cv", 0)
        rs_val = meta.get("rs", 0)

        def _stage_desc() -> str:
            return f"{stage}({alignment}) R={r_val:.1f} CV={cv_val:.3f} RS={rs_val:.2f}"

        if sig > 0:
            node_type = meta.get("node_type", "")
            node_label = _NODE_TYPE_LABELS.get(node_type, "") if node_type else ""
            entry_size = abs(sig - position) if position > 0 else sig

            if position > 0 and sig < position:
                # Partial take-profit (halve): record exit row against FIRST pending entry.
                exit_size = position - sig
                if pending:
                    ent = pending[0]
                    ent_size = ent["size"]
                    # Take from the first pending entry proportionally.
                    consumed = min(exit_size, ent_size)
                    ret = (price - ent["price"]) / ent["price"] * consumed if ent["price"] else 0.0
                    rows.append({
                        "entry_date": ent["date"],
                        "entry_stage": ent["stage_desc"],
                        "exit_date": str(idx)[:10],
                        "exit_stage": _stage_desc(),
                        "node_label": ent["node_label"],
                        "position": round(consumed, 2),
                        "entry_price": ent["price"],
                        "exit_price": round(price, 2),
                        "return_pct": round(ret, 4),
                        "exit_reason": meta.get("exit_reason") or "止盈",
                        "is_open": False,
                    })
                    ent["size"] -= consumed
                    if ent["size"] <= 0.001:
                        pending.pop(0)
            elif position > 0 and sig > position:
                # Add position: record as a new pending entry.
                add_size = sig - position
                pending.append({
                    "date": str(idx)[:10],
                    "stage_desc": _stage_desc(),
                    "price": round(price, 2),
                    "size": add_size,
                    "node_label": node_label,
                })
            else:
                # Fresh entry.
                pending.append({
                    "date": str(idx)[:10],
                    "stage_desc": _stage_desc(),
                    "price": round(price, 2),
                    "size": sig,
                    "node_label": node_label,
                })
            position = sig

        else:
            # Exit: consume pending entries FIFO.
            remaining = position  # total to exit
            position = 0.0
            exit_reason = meta.get("exit_reason") or "离场"
            while remaining > 0.001 and pending:
                ent = pending.pop(0)
                consumed = min(remaining, ent["size"])
                ret = (price - ent["price"]) / ent["price"] * consumed if ent["price"] else 0.0
                rows.append({
                    "entry_date": ent["date"],
                    "entry_stage": ent["stage_desc"],
                    "exit_date": str(idx)[:10],
                    "exit_stage": _stage_desc(),
                    "node_label": ent["node_label"],
                    "position": round(consumed, 2),
                    "entry_price": ent["price"],
                    "exit_price": round(price, 2),
                    "return_pct": round(ret, 4),
                    "exit_reason": exit_reason,
                    "is_open": False,
                })
                remaining -= consumed
                if ent["size"] - consumed > 0.001:
                    ent["size"] -= consumed

    # Any remaining pending entries are still open.
    if pending:
        last_idx = df.index[-1]
        last_price = float(close.iloc[-1])
        for ent in pending:
            ret = (last_price - ent["price"]) / ent["price"] * ent["size"] if ent["price"] else 0.0
            rows.append({
                "entry_date": ent["date"],
                "entry_stage": ent["stage_desc"],
                "exit_date": str(last_idx)[:10],
                "exit_stage": "",
                "node_label": ent["node_label"],
                "position": round(ent["size"], 2),
                "entry_price": ent["price"],
                "exit_price": round(last_price, 2),
                "return_pct": round(ret, 4),
                "exit_reason": "持仓中",
                "is_open": True,
            })

    return rows


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _empty_result(code: str) -> dict[str, Any]:
    return {
        "code": code,
        "name": code,
        "final_state": "no_structure",
        "previous_state": "no_structure",
        "trade_count": 0,
        "win_rate": 0.0,
        "win_count": 0,
        "loss_count": 0,
        "cumulative_return": 0.0,
        "annual_return": 0.0,
        "max_drawdown": 0.0,
        "sharpe": 0.0,
        "annual_volatility": 0.0,
        "profit_factor": 0.0,
        "final_equity": 1.0,
        "bsk_count": 0,
        "ck_count": 0,
        "latest_signal": None,
        "signal_points": [],
        "trades": [],
        "trading_days": 0,
        "date_start": "",
        "date_end": "",
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

    # ---- profit factor & annual volatility ----
    if trades > 0:
        matched_trades = min(len(entries), len(exits))
        win_returns: list[float] = []
        loss_returns: list[float] = []
        for i in range(matched_trades):
            r = (exits[i]["price"] - entries[i]["price"]) / entries[i]["price"]
            if r > 0:
                win_returns.append(r)
            elif r < 0:
                loss_returns.append(abs(r))
        avg_win = float(np.mean(win_returns)) if win_returns else 0.0
        avg_loss = float(np.mean(loss_returns)) if loss_returns else 0.0
        profit_factor = round(avg_win / avg_loss, 2) if avg_loss > 0 else 0.0
    else:
        profit_factor = 0.0

    annual_volatility = round(float(std_ret * np.sqrt(252)) if len(daily_returns) > 1 else 0.0, 4)
    final_equity = round(float(equity.iloc[-1]), 6) if len(equity) > 0 else 1.0

    return {
        "trade_count": trades,
        "win_rate": round(win_rate, 4),
        "win_count": win_count,
        "loss_count": loss_count,
        "cumulative_return": round(cumulative_return, 6),
        "annual_return": round(annual_return, 6),
        "max_drawdown": round(max_drawdown, 6),
        "sharpe": round(sharpe, 4),
        "annual_volatility": annual_volatility,
        "profit_factor": profit_factor,
        "final_equity": final_equity,
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
    states: pd.DataFrame | None = None,
) -> list[dict[str, Any]]:
    """Extract signal change points for frontend chart markers."""
    points: list[dict[str, Any]] = []
    position = 0.0
    for idx in signals.index:
        sig = float(signals.loc[idx])
        if sig == 0.0:
            continue
        entry_types = {0.33: "entry_trial", 0.67: "entry_confirm", 1.0: "entry_full"}
        if sig > 0:
            if position > 0 and sig < position:
                stype = "take_profit"
            else:
                stype = entry_types.get(round(sig, 2), "entry")
            position = sig
        else:  # sig < 0
            stype = "exit"
            position = 0.0

        try:
            price = float(df["close"].loc[idx])
        except (KeyError, TypeError):
            price = 0.0

        pt = {
            "date": str(idx)[:10],
            "type": stype,
            "price": round(price, 2),
            "signal_value": round(sig, 2),
        }

        # Attach entry_label / entry_pattern for 止跌K signals with known pattern
        if stype == "entry_trial" and states is not None and not states.empty:
            pattern = ""
            try:
                if "bsk_pattern" in states.columns:
                    pattern = str(states.loc[idx, "bsk_pattern"])
            except (KeyError, TypeError):
                pass
            if pattern:
                pt["entry_label"] = f"入({pattern})"
                pt["entry_pattern"] = pattern

        points.append(pt)
    return points


def _build_trade_records(
    df: pd.DataFrame,
    states: pd.DataFrame,
    signals: pd.Series,
    stop_loss_pct: float,
    ma_short: int,
    ma_mid: int,
) -> list[dict[str, Any]]:
    """Group signal points into trades with human-readable result descriptions.

    Each trade contains a list of signals (entry_trial → entry_confirm →
    exit) and a per-trade return percentage.  Exit reasons are inferred
    from the OHLCV bar conditions at the exit date in the same priority
    order used by ``SignalEngine``.
    """
    if df is None or df.empty or signals.empty:
        return []

    close = df["close"]
    low = df["low"]

    # Compute MAs (same as signal engine).
    ma_s = close.rolling(window=ma_short).mean()
    ma_m = close.rolling(window=ma_mid).mean()

    # Extract signal change points preserving order and value.
    events: list[dict[str, Any]] = []
    position = 0.0
    for idx in signals.index:
        sig = float(signals.loc[idx])
        if sig == 0.0:
            continue
        entry_types = {0.33: "entry_trial", 0.67: "entry_confirm", 1.0: "entry_full"}
        if sig > 0:
            if position > 0 and sig < position:
                stype = "take_profit"
            else:
                stype = entry_types.get(round(sig, 2), "entry")
            position = sig
        else:  # sig < 0
            stype = "exit"
            position = 0.0
        try:
            price = float(close.loc[idx])
        except (KeyError, TypeError):
            price = 0.0
        events.append({
            "date": str(idx)[:10],
            "type": stype,
            "price": round(price, 2),
            "signal_value": round(sig, 2),
        })

        # Attach entry_pattern for 止跌K entry_trial signals
        if stype == "entry_trial" and states is not None and not states.empty:
            pattern = ""
            try:
                if "bsk_pattern" in states.columns:
                    pattern = str(states.loc[idx, "bsk_pattern"])
            except (KeyError, TypeError):
                pass
            if pattern:
                events[-1]["entry_pattern"] = pattern

    # Group events into trades: entry events → exit event.
    trades: list[dict[str, Any]] = []
    current_signals: list[dict[str, Any]] = []
    entry_prices: list[float] = []

    ENTRY_LABELS: dict[str, str] = {
        "entry_trial": "止跌K入场",
        "entry_confirm": "证伪K加仓",
        "entry_full": "加仓至满仓",
    }

    for ev in events:
        if ev["type"].startswith("entry"):
            label = ENTRY_LABELS.get(ev["type"], ev["type"])
            current_signals.append({**ev, "description": label})
            entry_prices.append(ev["price"])
        elif ev["type"] == "exit" and current_signals:
            # Determine exit reason.
            exit_date = ev["date"]
            exit_price = ev["price"]
            avg_entry = sum(entry_prices) / len(entry_prices) if entry_prices else exit_price
            return_pct = (exit_price - avg_entry) / avg_entry if avg_entry else 0.0

            reason = _infer_exit_reason(
                df, states, exit_date, exit_price, avg_entry,
                stop_loss_pct, ma_s, ma_m, low,
            )
            desc = f"{reason}，{return_pct * 100:.1f}%"
            current_signals.append({**ev, "description": desc})
            trades.append({
                "trade_index": len(trades) + 1,
                "signals": current_signals,
                "return_pct": round(return_pct, 4),
                "is_win": return_pct > 0,
            })
            current_signals = []
            entry_prices = []

    return trades


def _infer_exit_reason(
    df: pd.DataFrame,
    states: pd.DataFrame,
    exit_date: str,
    exit_price: float,
    avg_entry: float,
    stop_loss_pct: float,
    ma_s: pd.Series,
    ma_m: pd.Series,
    low: pd.Series,
) -> str:
    """Infer the most likely exit reason by checking conditions at *exit_date*.

    Priority mirrors ``SignalEngine``: pivot break → stop-loss % →
    pullback/divergence → MA break.
    """
    try:
        idx = df.index[df.index.astype(str).str.startswith(exit_date)][0]
    except IndexError:
        return "离场"

    try:
        bar_low = float(low.loc[idx])
        bar_close = float(df["close"].loc[idx])
        pivot_val: float | None = None
        if not states.empty and "pivot_low" in states.columns:
            pv = states["pivot_low"].loc[idx]
            pivot_val = float(pv) if not pd.isna(pv) else None
        state_val = ""
        if not states.empty and "state" in states.columns:
            state_val = str(states["state"].loc[idx])
        ma_s_val = float(ma_s.loc[idx]) if not pd.isna(ma_s.loc[idx]) else None
        ma_m_val = float(ma_m.loc[idx]) if not pd.isna(ma_m.loc[idx]) else None
    except (KeyError, TypeError, ValueError):
        return "离场"

    loss_pct = (bar_close - avg_entry) / avg_entry if avg_entry else 0.0

    # 1. Pivot stop-loss.
    if pivot_val is not None and bar_low < pivot_val:
        return "跌破 pivot 止损"

    # 2. Percentage stop-loss.
    if loss_pct < -stop_loss_pct:
        return f"{stop_loss_pct * 100:.0f}%止损"

    # 3. Divergence / pullback.
    if state_val == "pullback":
        return "回调离场"

    # 4. MA-based exit.
    if ma_m_val is not None and bar_close < ma_m_val:
        return "跌破均线止盈"
    if ma_s_val is not None and bar_close < ma_s_val:
        return "跌破短期均线止盈"

    return "离场"


def _build_ohlcv_snapshot(
    df: pd.DataFrame,
    states: pd.DataFrame,
    signal_points: list[dict[str, Any]],
    max_bars: int = 100,
) -> list[dict[str, Any]]:
    """Build a compact OHLCV snapshot (last *max_bars*) for mini chart.

    Returns a list of dicts with date, open, high, low, close, volume,
    ``has_signal`` boolean, and ``state`` string for state-coloring.
    """
    if df is None or df.empty:
        return []

    df_slice = df.tail(max_bars)
    signal_dates = {s["date"] for s in signal_points}

    bars: list[dict[str, Any]] = []
    for idx in df_slice.index:
        date_str = str(idx)[:10]
        try:
            state_val = ""
            if states is not None and not states.empty and "state" in states.columns:
                try:
                    state_val = str(states.loc[idx, "state"])
                except (KeyError, TypeError):
                    pass
            bar = {
                "date": date_str,
                "open": round(float(df_slice.loc[idx, "open"]), 2),
                "high": round(float(df_slice.loc[idx, "high"]), 2),
                "low": round(float(df_slice.loc[idx, "low"]), 2),
                "close": round(float(df_slice.loc[idx, "close"]), 2),
                "volume": int(df_slice.loc[idx, "volume"]),
                "has_signal": date_str in signal_dates,
                "state": state_val,
            }
        except (KeyError, TypeError, ValueError):
            continue
        bars.append(bar)

    return bars
