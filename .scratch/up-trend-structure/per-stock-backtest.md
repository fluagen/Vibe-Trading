---
name: per-stock-backtest
description: "How to run single-stock backtests using strategy_research_runner.py — loader, strategy, execution, and output fields."
metadata: 
  node_type: memory
  type: reference
  originSessionId: 37761cbc-c19d-40b3-a925-152334ba616f
---

# Per-Stock Backtest Usage

## Core Entry Points

All in [agent/src/api/strategy_research_runner.py](agent/src/api/strategy_research_runner.py):

| Function | Purpose |
|----------|---------|
| `run_single_stock_backtest(code, df, detector, signal_engine)` | Run backtest for ONE stock |
| `run_backtest_blocking(job_id, codes, start_date, end_date, strategy_name, on_progress, on_stock_result, params)` | Batch backtest with SSE streaming |
| `_get_loader()` | Get available A-share data loader (mootdx > baostock > eastmoney > akshare > tushare) |
| `_load_strategy(strategy_name)` | Import detector + signal engine classes from STRATEGY_MAP |
| `_split_params(params)` | Split combined params into detector_kwargs and signal_kwargs |

## Quick-Start Template

```python
import sys
sys.path.insert(0, "/path/to/Vibe-Trading/agent")

from src.api.strategy_research_runner import (
    _load_strategy, _get_loader, run_single_stock_backtest
)

CODE = "688072.SH"          # SH for Shanghai, SZ for Shenzhen
STRATEGY = "up_trend_structure"
START = "2026-05-01"
END = "2026-07-14"

detector_cls, signal_cls = _load_strategy(STRATEGY)
detector = detector_cls()
signal_engine = signal_cls()

loader = _get_loader()
data_map = loader.fetch([CODE], start_date=START, end_date=END, interval="1D")
df = data_map.get(CODE)

result = run_single_stock_backtest(CODE, df, detector, signal_engine)
```

## Custom Parameters

```python
params = {
    "up_phase_min_bars": 2,
    "volume_surge_ratio": 1.2,
    "big_bull_body_ratio": 0.6,
    "inv_hammer_shadow_ratio": 1.1,
    "stop_loss_pct": 0.03,
    "take_profit_pct": 0.15,
}
detector_kwargs, signal_kwargs = _split_params(params)
detector = detector_cls(**detector_kwargs)
signal_engine = signal_cls(**signal_kwargs)
```

## Output Fields

| Field | Type | Description |
|-------|------|-------------|
| `code` | str | Stock code |
| `final_state` | str | Current state: no_structure/forming/up_phase/pullback/pullback_end/breakdown |
| `previous_state` | str | Previous bar's state |
| `trade_count` | int | Number of completed trades |
| `win_rate` | float | Win rate (0-1) |
| `win_count` / `loss_count` | int | Win/loss counts |
| `cumulative_return` | float | Total return (e.g. 0.0774 = 7.74%) |
| `annual_return` | float | Annualized return |
| `max_drawdown` | float | Max drawdown (negative, e.g. -0.0027) |
| `sharpe` | float | Sharpe ratio |
| `bsk_count` | int | Total bottom_signal_k count |
| `ck_count` | int | Total confirm_k count |
| `trading_days` | int | Number of bars in data |
| `date_start` / `date_end` | str | Date range (YYYY-MM-DD) |
| `signal_points` | list | Entry/exit markers with date, type, price, signal_value |
| `trades` | list | Grouped trades with entry/exit reasons and return_pct |
| `equity_curve` | list | Daily equity values [{date, equity}] |
| `states_summary` | dict | Count of days in each state |
| `ohlcv_snapshot` | list | Last ~100 bars for mini chart |

## 回测脚本模板

完整脚本文件：`/tmp/backtest_<code>.py`

```python
import sys
sys.path.insert(0, '/home/majie/ai/vibe-trading/Vibe-Trading/agent')
from src.api.strategy_research_runner import _get_loader, run_single_stock_backtest, _load_strategy

CODE = "<code>.SH"   # or .SZ
STRATEGY = "up_trend_structure"

detector_cls, signal_cls = _load_strategy(STRATEGY)
detector = detector_cls()
signal_engine = signal_cls()
loader = _get_loader()

df = loader.fetch([CODE], start_date="<YYYY-MM-DD>", end_date="<YYYY-MM-DD>", interval="1D").get(CODE)
result = run_single_stock_backtest(CODE, df, detector, signal_engine)
```

需要状态阶段明细时，额外运行 `detector.compute(df)` 获取 per-bar states。

## 输出展示模板

每次回测结果必须按以下三部分展示：

### 第一部分：核心指标表

```
## <CODE> <策略名>策略回测

| 指标 | 数值 |
|------|------|
| 日期范围 | YYYY-MM-DD → YYYY-MM-DD（N个交易日） |
| 当前状态 | **状态中文名**（已持续X天） |
| 止跌K/证伪K | N次 / N次 |
| 交易 | N笔，胜率 XX% |
| 累计收益 | **+XX.XX%** |
| 年化收益 | +XX.XX% |
| 最大回撤 | -X.XX% |
| 夏普 | X.XX |
```

状态中文映射：no_structure=无结构, forming=形成中, up_phase=上涨阶段, pullback=回调, pullback_end=回调结束, breakdown=破位

### 第二部分：状态阶段列表

```
### 状态阶段（N段）

MM/DD → MM/DD  状态     N天   简要说明
```

每行附带简要说明（如"价涨量增"、"止跌K但未确认"、"跌破pivot破位"等）。

### 第三部分：交易明细表

```
### 交易明细

| # | 日期 | 动作 | 价格 | 说明 |
|---|------|------|------|------|
| 1 | MM-DD | 止跌K入场 | ¥XXX | 回调后止跌信号 |
|   | MM-DD | 证伪K加仓 | ¥XXX | 确认上涨 |
|   | MM-DD | 离场 | ¥XXX | 回调离场，+XX% |
```

### 第四部分（可选）：关键观察

列出值得关注的要点，如多次试探失败、当前状态判断等。

## Environment

Must run under `vibe-trading` conda env from the `agent/` directory.
