"""单标的节点交易策略快速验证脚本。

用法:
    python -m src.skills.node_trading.run_backtest --code 600498 --start 2025-10-01
    python -m src.skills.node_trading.run_backtest --code 600498 --start 2025-10-01 --end 2026-08-01

输出: equity.csv, trades.csv, stdout metrics
"""

from __future__ import annotations
import argparse, os, sys
import pandas as pd
import numpy as np


def run_backtest(
    df: pd.DataFrame, signal_engine,
    initial_capital: float = 100_000.0,
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """执行单标回测。Returns (equity_df, trades_df, metrics_dict)."""
    signals = signal_engine.generate({"STOCK": df})["STOCK"]
    # 当日尾盘执行：信号与收盘价同 bar，不 shift

    equity = pd.DataFrame(index=df.index, dtype=float)
    equity["close"] = df["close"]
    equity["signal"] = signals
    equity["position"] = 0.0
    equity["equity"] = initial_capital
    equity["returns"] = 0.0

    trades: list[dict] = []
    pos_size = 0.0
    entry_price = 0.0

    for i in range(1, len(equity)):
        signal = equity["signal"].iloc[i]
        prev_close = equity["close"].iloc[i - 1]
        cur_close = equity["close"].iloc[i]
        prev_equity = equity["equity"].iloc[i - 1]

        if signal == -1.0 and pos_size > 0:
            pnl = pos_size * (cur_close - entry_price) / entry_price
            equity.loc[equity.index[i], "equity"] = prev_equity * (1 + pnl)
            trades.append({
                "exit_date": equity.index[i], "exit_price": cur_close,
                "pnl_pct": pnl * 100, "reason": "stop_or_tp",
            })
            pos_size = 0.0
            entry_price = 0.0
        elif signal > 0 and pos_size <= 0:
            pos_size = signal
            entry_price = cur_close
            equity.loc[equity.index[i], "equity"] = prev_equity
            trades.append({
                "entry_date": equity.index[i], "entry_price": cur_close,
                "position_size": pos_size,
            })
        elif signal > 0 and pos_size > 0:
            # 信号 = 目标仓位（非增量），减仓/加仓按差值处理
            if signal < pos_size:
                reduce_ratio = (pos_size - signal) / pos_size
                pnl = pos_size * reduce_ratio * (cur_close - entry_price) / entry_price
                equity.loc[equity.index[i], "equity"] = prev_equity * (1 + pnl)
                pos_size = signal
                trades.append({
                    "exit_date": equity.index[i], "exit_price": cur_close,
                    "pnl_pct": pnl * 100, "reason": "partial_tp",
                })
            elif signal > pos_size:
                add_size = signal - pos_size
                entry_price = (entry_price * pos_size + cur_close * add_size) / signal
                pos_size = signal
                equity.loc[equity.index[i], "equity"] = prev_equity
            else:
                equity.loc[equity.index[i], "equity"] = prev_equity
        else:
            if pos_size > 0:
                pnl = pos_size * (cur_close - prev_close) / prev_close
                equity.loc[equity.index[i], "equity"] = prev_equity * (1 + pnl)
            else:
                equity.loc[equity.index[i], "equity"] = prev_equity
        equity.loc[equity.index[i], "position"] = pos_size

    equity["returns"] = equity["equity"].pct_change().fillna(0.0)

    total_return = (equity["equity"].iloc[-1] / initial_capital - 1) * 100
    peak = equity["equity"].expanding().max()
    drawdown = (equity["equity"] - peak) / peak * 100
    max_dd = drawdown.min()
    ann_return = (1 + total_return / 100) ** (252 / max(len(equity), 1)) - 1
    ann_vol = equity["returns"].std() * np.sqrt(252)
    sharpe = (ann_return - 0.02) / ann_vol if ann_vol > 0 else 0
    exit_trades = [t for t in trades if "exit_date" in t]
    win_count = sum(1 for t in exit_trades if t.get("pnl_pct", 0) > 0)
    win_rate = win_count / len(exit_trades) * 100 if exit_trades else 0

    trades_df = pd.DataFrame(trades) if trades else pd.DataFrame()
    metrics = {
        "total_return_pct": round(total_return, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "sharpe_ratio": round(sharpe, 2),
        "annual_return_pct": round(ann_return * 100, 2),
        "annual_volatility_pct": round(ann_vol * 100, 2),
        "total_trades": len(exit_trades),
        "win_rate_pct": round(win_rate, 2),
    }
    return equity, trades_df, metrics


def main():
    parser = argparse.ArgumentParser(description="节点交易策略单标回测")
    parser.add_argument("--code", required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", default=None)
    parser.add_argument("--capital", type=float, default=100_000.0)
    parser.add_argument("--output", default=".")
    args = parser.parse_args()

    try:
        from backtest.loaders.local_loader import LocalLoader
        loader = LocalLoader()
        end_date = args.end or pd.Timestamp.today().strftime("%Y-%m-%d")
        data_map = loader.fetch([args.code], args.start, end_date)
        df = data_map.get(args.code)
        if df is None or df.empty:
            print(f"错误: 未找到 {args.code} 的数据")
            sys.exit(1)
    except Exception:
        try:
            import akshare as ak
            raw = ak.stock_zh_a_hist(
                symbol=args.code, period="daily",
                start_date=args.start.replace("-", ""),
                end_date=(args.end or pd.Timestamp.today().strftime("%Y-%m-%d")).replace("-", ""),
                adjust="qfq",
            )
            df = pd.DataFrame({
                "open": raw["开盘"].astype(float), "high": raw["最高"].astype(float),
                "low": raw["最低"].astype(float), "close": raw["收盘"].astype(float),
                "volume": raw["成交量"].astype(float),
            }, index=pd.to_datetime(raw["日期"]))
        except Exception as e:
            print(f"数据加载失败: {e}")
            sys.exit(1)

    from src.skills.node_trading.signal_engine import SignalEngine
    engine = SignalEngine()
    equity, trades, metrics = run_backtest(df, engine, args.capital)

    os.makedirs(args.output, exist_ok=True)
    equity.to_csv(os.path.join(args.output, "equity.csv"))
    if not trades.empty:
        trades.to_csv(os.path.join(args.output, "trades.csv"), index=False)

    print("\n========== 回测指标 ==========")
    for k, v in metrics.items():
        print(f"  {k}: {v}")
    print(f"==============================\n")
    print(f"输出: {args.output}/equity.csv, {args.output}/trades.csv")


if __name__ == "__main__":
    main()
