---
name: up-trend-structure
description: 上涨结构交易策略 — 基于量价关系的状态机策略，通过止跌K/证伪K入场，三档阶梯止盈。适用于 A 股日线级别中短线交易。
category: strategy
---

# 上涨结构交易策略

## 一、策略概述

上涨结构策略是一个**纯量价+均线**的状态机交易策略，不依赖任何宏观、基本面或资金流指标。核心思想是将价格行为归纳为"无结构 → 形成 → 上涨 → 回调 → 回调结束"的完整生命周期，通过 **止跌K** 和 **证伪K** 触发分批入场，通过 **起涨点(pivot)止损** 和 **三档阶梯止盈** 管理出场。

**三层架构：**

```
日线 OHLCV  →  UpTrendStructure.compute()  →  结构状态（6种）
            →  SignalEngine.generate()      →  仓位信号 [0, 0.33, 0.67, -1.0]
```

- **指标层**：从 OHLCV 衍生 K线形态、量价关系、均线指标
- **状态机层**：6 个状态 + 转移规则，追踪上涨结构的生命周期
- **信号引擎层**：逐 bar 追踪持仓状态，输出标准化仓位信号

**策略定位**：A 股日线级别，中短线趋势跟踪。最大仓位 0.67（2/3），不做空。

## 二、核心概念定义

### 2.1 量价关系

| 概念 | 定义 | 方向含义 |
|------|------|----------|
| **价涨量增** | `close > prev_close` AND `volume > prev_volume` | 多头确认信号 |
| **价跌量缩** | `close < prev_close` AND `volume < prev_volume` | 回调/弱势信号 |
| **量价背离** | (价涨量缩) OR (量涨价跌) | 预警信号，动能衰竭 |
| **补量修复** | `close > 触发日close` AND `volume > 触发日volume` | 背离被修复，上涨延续 |

### 2.2 K线形态指标

| 指标 | 计算方式 | 用途 |
|------|----------|------|
| 实体 (body) | `abs(close - open)` | 判断K线阴阳及实体大小 |
| 振幅 (range) | `high - low` | 当日波动区间 |
| 上影线 | `high - max(open, close)` | 倒锤子线检测 |
| 下影线 | `min(open, close) - low` | 锤子线检测 |
| 前日实体中点 | `(prev_open + prev_close) / 2` | 止跌K收盘位判断基准 |

### 2.3 止跌K（三种形态，优先级：倒垂 > 反包线 > 两日筑底）

止跌K是回调结束的标志性K线，三种形态按优先级判定：

**形态一：倒垂（优先级最高）**

| 条件 | 说明 |
|------|------|
| 前日为阴线 | `prev_close < prev_open` |
| 当日为倒锤子线 | 上影线 ≥ `inv_hammer_shadow_ratio` × 实体，且下影线 < 实体 |
| 最高价突破前日中点 | `high > (prev_open + prev_close) / 2` |
| 放量 | `volume > prev_volume × volume_surge_ratio` |

**形态二：反包线**

| 条件 | 说明 |
|------|------|
| 前日为阴线 | `prev_close < prev_open` |
| 当日收阳 | `close > open` |
| 实体足够大（排除十字星） | 实体/振幅 > `big_bull_body_ratio` |
| 收盘价超过阈值 | `close > prev_close + (prev_open - prev_close) × close_above_prev_mid`（默认阈值 = 前日实体中点） |
| 放量 | `volume > prev_volume × volume_surge_ratio` |

**形态三：两日筑底（优先级最低）**

| 时间 | 条件 |
|------|------|
| D0 | 阴线 |
| D1 | 阳线，且非倒垂、非反包线 |
| D2 | 阳线 + 放量 + `close > D0中点`，**D2 为止跌K** |

### 2.4 证伪K

止跌K出现后的确认信号，满足以下任一条件即为证伪K：

- 当日收阳（`close > open`），或
- 当日收盘价 > 止跌K收盘价

证伪K不需要放量确认。

### 2.5 起涨点 (pivot_low)

pivot_low 是当前上涨结构的**止损基准**，在以下时机设置：

- `forming → up_phase` 时：取 forming bar 的 `low`
- `pullback_end → up_phase` 时：取止跌K的 `low`

一旦价格跌破 pivot_low，结构破位，立即清仓。

## 三、状态机

### 3.1 六种状态

| 状态 | 含义 | 持仓建议 |
|------|------|----------|
| `no_structure` | 无上涨结构 | 空仓等待 |
| `forming` | 结构形成中（首日价涨量增） | 空仓观察 |
| `up_phase` | 上涨阶段确认 | 可持有/加仓 |
| `pullback` | 回调中（背离/价跌量缩未修复） | 离场或空仓 |
| `pullback_end` | 回调结束（止跌K出现，等待证伪K） | 试仓持有 |
| `breakdown` | 破位（价格跌破起涨点） | 立即清仓（瞬态→no_structure） |

### 3.2 完整转移规则

| 当前状态 | 触发条件 | 新状态 | 说明 |
|----------|----------|--------|------|
| `no_structure` | 价涨量增 | `forming` | 记录 forming_low = 当日 low |
| `forming` | 价涨量增（连续第2天） | `up_phase` | pivot = forming_low |
| `forming` | 非价涨量增 | `no_structure` | 结构失败，回归空仓 |
| `up_phase` | 价涨量增 | `up_phase` | 延续上涨 |
| `up_phase` | 背离 或 价跌量缩 | 挂起（pending） | 记录触发日 close/volume，等次日补量 |
| 挂起 | 补量成功（次日） | `up_phase` | 背离被修复，延续上涨 |
| 挂起 | 补量失败（次日） | `pullback` | 上涨阶段结束 |
| `pullback` | 止跌K | `pullback_end` | 记录 pullback_end_low/close |
| `pullback_end` | 证伪K | `up_phase` | pivot = pullback_end_low |
| `pullback_end` | 收阳 且 close > pullback_end_close | `up_phase` | 扩展确认条件 |
| `pullback_end` | `low < pullback_end_low` | `pullback` | 止跌K 低点被跌破，回调继续 |
| `*`（除 no_structure） | `low < pivot` | `breakdown` | 结构破位 |
| `breakdown` | 立即 | `no_structure` | 瞬态转移 |

### 3.3 状态流转图

```
no_structure ──价涨量增──→ forming ──价涨量增──→ up_phase
     ↑                        │                      │
     │                        │非价涨量增              │背离/价跌量缩
     │                        ↓                      ↓
     │                    no_structure           挂起(pending)
     │                                             │      │
     │                                       补量成功   补量失败
     │                                             │      │
     │                                             ↓      ↓
     │                                        up_phase  pullback
     │                                          ↑         │
     │                                          │      止跌K
     │                                          │         ↓
     │                                    证伪K/扩展  pullback_end
     │                                          │         │
     │                                          └─────────┘
     │                                              │ low < pullback_end_low
     │                                              ↓
     │                                           pullback
     │
     └─────────── breakdown ←── low < pivot ── (all states except no_structure)
```

## 四、信号规则

信号值为**仓位目标比例**，正数表示建仓/持仓目标，`-1.0` 表示清仓。每 bar 按以下优先级依次检查，**命中即执行，不再检查后续条件**。

### 4.1 止损（强制全平，优先级最高）

| 优先级 | 条件 | 信号 | 说明 |
|--------|------|------|------|
| **1** | 跌破起涨点：`low < pivot_low` | `-1.0` | 结构破位，立即清仓 |
| **2** | 浮动亏损超限：`(close - avg_entry) / avg_entry < -stop_loss_pct` | `-1.0` | 无条件百分比止损，默认 -3% |
| **3** | 进入回调（仅 up_phase → pullback） | `-1.0` | 背离/价跌量缩补量失败，上涨阶段结束 |

> **注意**：止损条件 3 仅在 `up_phase → pullback`（补量失败）时触发。`pullback_end → pullback`（止跌K未被确认）不触发此退出。

### 4.2 止盈（阶梯减仓，止损之后检查）

止盈采用**三档级联**模式：每档独立触发一次，按顺序递进减仓。

| 优先级 | 条件 | 信号 | 说明 |
|--------|------|------|------|
| **4** | 盈利 ≥ 30%：`(close - avg_entry) / avg_entry >= take_profit_pct` | 当前仓位 × 0.5 | 卖一半，仅触发一次 |
| **5** | 收盘 < MA(short)：`close < ma_s` | 当前仓位 × 0.5 | 短线走弱再减半，仅触发一次 |
| **6** | 收盘 < MA(mid)：`close < ma_m` | `-1.0` | 中线破位全部清仓 |

> **级联示例**：0.67 仓位 → 盈利 30% 减至 0.335 → 跌破 MA5 减至 0.1675 → 跌破 MA10 清仓。

### 4.3 入场（仅空仓/试仓时触发）

| 触发条件 | 信号值 | 说明 |
|----------|--------|------|
| 止跌K + `pullback → pullback_end` + 当前空仓 | **0.33** | 试仓 1/3 |
| 证伪K + `pullback_end → up_phase` + 当前仓位为 0.33 | **0.67** | 确认加至 2/3（最大仓位） |

**入场规则要点**：
- 必须从 `pullback` 状态进入，不直接在 `no_structure` 或 `forming` 状态入场
- 先 0.33 试仓，确认后再加至 0.67，不一次性满仓
- 最大仓位 0.67，不做全仓（1.0）

## 五、仓位管理

### 5.1 仓位状态流转

```
空仓 (0.0)
  │  止跌K出现（pullback → pullback_end）
  ↓
试仓 (0.33)  ←── 回调后首次入场
  │  证伪K出现（pullback_end → up_phase）
  ↓
确认仓位 (0.67)  ←── 最大仓位，不再增加
  │
  │  触发条件（按优先级）：
  ├── 跌破 pivot ────────────→ 清仓 (-1.0)
  ├── 亏损 > 3% ──────────────→ 清仓 (-1.0)
  ├── up_phase → pullback ────→ 清仓 (-1.0)
  ├── 盈利 ≥ 30% ─────────────→ 减半 (0.67→0.335)
  ├── 收盘 < MA5 ─────────────→ 再减半 (0.335→0.1675)
  └── 收盘 < MA10 ────────────→ 清仓 (-1.0)
```

### 5.2 仓位管理核心原则

| 原则 | 说明 |
|------|------|
| **分批建仓** | 先 0.33 试仓，确认后再加至 0.67，不一次性满仓 |
| **止损优先** | 止损条件优先级最高，先于止盈检查。跌破 pivot、亏损超限、进入回调任一触发即全平 |
| **阶梯止盈** | 三档止盈递进执行：30%利润减半 → MA5破位再减半 → MA10破位清仓，逐步锁定利润 |
| **每档仅一次** | 30%止盈和MA5止盈各只触发一次，避免重复减仓 |
| **状态重置** | 清仓后所有跟踪状态（profit_taken、ma_short_taken、entry_prices）全部重置 |

### 5.3 不支持的仓位场景

- **不做全仓（1.0）**：最大仓位 0.67，始终保留部分资金应对风险
- **不做空**：A 股不允许融券做空，所有 `-1.0` 信号仅表示平仓
- **不加杠杆**：仓位信号 0.67 表示 67% 资金使用率

## 六、可调参数

### 6.1 参数一览

| 参数 | 默认值 | 类型 | 说明 |
|------|--------|------|------|
| `up_phase_min_bars` | 2 | int | 价涨量增连续天数要求，定义进入 up_phase 的确认天数 |
| `volume_surge_ratio` | 1.2 | float | 止跌K 成交量放大倍数，当日量需 > 前日量 × 此值 |
| `big_bull_body_ratio` | 0.4 | float | 反包线实体/振幅最小比例，用于过滤 doji（十字星）假阳线 |
| `inv_hammer_shadow_ratio` | 1.2 | float | 倒垂线上影/实体倍数（形态一），值越大要求上影越长 |
| `close_above_prev_mid` | 0.5 | float | 反包线收盘阈值系数：`threshold = prev_close + (prev_open - prev_close) × 此值`。默认 0.5 等价于前日实体中点 |
| `stop_loss_pct` | 0.03 | float | 无条件止损比例（3%），基于入场均价计算浮动亏损 |
| `take_profit_pct` | 0.30 | float | 第一档止盈盈利比例（30%），触发后减半仓 |
| `ma_short` | 5 | int | 第二档止盈均线周期，收盘跌破此均线减半仓 |
| `ma_mid` | 10 | int | 第三档清仓均线周期，收盘跌破此均线全部清仓 |

### 6.2 参数调优建议

| 调优方向 | 建议调整 |
|----------|----------|
| 更保守（减少交易频率） | 增大 `up_phase_min_bars`（如 3）、增大 `volume_surge_ratio`（如 1.5） |
| 更激进（捕捉更多信号） | 减小 `volume_surge_ratio`（如 1.1）、减小 `big_bull_body_ratio`（如 0.3） |
| 放宽止损（容忍更大回撤） | 增大 `stop_loss_pct`（如 0.05） |
| 更快止盈（短线操作） | 减小 `take_profit_pct`（如 0.15）、减小 `ma_short`（如 3） |
| 更慢止盈（趋势跟踪） | 增大 `take_profit_pct`（如 0.50）、增大 `ma_short`/`ma_mid`（如 10/20） |

### 6.3 内部参数（不开放配置）

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `divergence_repair_bars` | 1 | 背离修复窗口（天），当前固定为 1，不通过 SignalEngine 暴露 |

## 七、回测用法

### 7.1 快速启动

```python
import sys
sys.path.insert(0, "/home/majie/ai/vibe-trading/Vibe-Trading/agent")

from src.api.strategy_research_runner import (
    _load_strategy, _get_loader, run_single_stock_backtest
)

CODE = "688072.SH"          # SH 上海, SZ 深圳
STRATEGY = "up_trend_structure"
START = "2026-01-01"
END = "2026-08-01"

detector_cls, signal_cls = _load_strategy(STRATEGY)
detector = detector_cls()
signal_engine = signal_cls()

loader = _get_loader()
data_map = loader.fetch([CODE], start_date=START, end_date=END, interval="1D")
df = data_map.get(CODE)

result = run_single_stock_backtest(CODE, df, detector, signal_engine)
```

### 7.2 自定义参数回测

```python
params = {
    "up_phase_min_bars": 2,
    "volume_surge_ratio": 1.5,       # 更严格的放量要求
    "stop_loss_pct": 0.05,           # 放宽止损到 5%
    "take_profit_pct": 0.15,         # 更快的止盈
    "ma_short": 5,
    "ma_mid": 10,
}

from src.api.strategy_research_runner import _split_params
detector_kwargs, signal_kwargs = _split_params(params)
detector = detector_cls(**detector_kwargs)
signal_engine = signal_cls(**signal_kwargs)

result = run_single_stock_backtest(CODE, df, detector, signal_engine)
```

### 7.3 输出字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `code` | str | 股票代码 |
| `final_state` | str | 当前状态 |
| `trade_count` | int | 完成的交易笔数 |
| `win_rate` | float | 胜率 (0-1) |
| `cumulative_return` | float | 累计收益（如 0.0774 = 7.74%） |
| `annual_return` | float | 年化收益 |
| `max_drawdown` | float | 最大回撤（负值，如 -0.0027） |
| `sharpe` | float | 夏普比率 |
| `bsk_count` / `ck_count` | int | 止跌K/证伪K 出现次数 |
| `trades` | list | 交易明细（入场/离场日期、价格、原因、收益率） |
| `equity_curve` | list | 每日权益曲线 `[{date, equity}]` |
| `signal_points` | list | 信号点位标记 |
| `states_summary` | dict | 各状态天数统计 |

### 7.4 状态中文映射

| 状态 | 中文 |
|------|------|
| `no_structure` | 无结构 |
| `forming` | 形成中 |
| `up_phase` | 上涨阶段 |
| `pullback` | 回调 |
| `pullback_end` | 回调结束 |
| `breakdown` | 破位 |

### 7.5 运行环境

必须在 `vibe-trading` conda 环境下，从 `agent/` 目录运行：

```bash
conda activate vibe-trading
cd agent
```

## 八、策略限制与边界

### 适用场景
- A 股日线级别中短线交易
- 单股独立回测（不支持多股组合）
- 有明显量价关系的活跃个股

### 不适用场景
- 日内/分钟级别交易（日线以下周期）
- 缩量阴跌的冷门股（缺乏量价信号）
- 一字涨跌停期间（无有效量价信号）
- 刚上市新股（历史数据不足，无法形成有效结构）

### 已知局限
- 不含大盘共振过滤
- 不含基本面/资金流验证
- 回调期间的止跌K可能反复出现（假突破风险）
- 均线周期固定，不根据波动率自适应

## 九、相关文件

| 文件 | 说明 |
|------|------|
| `up_trend_structure.py` | 状态机探测器（UpTrendStructure 类） |
| `signal_engine.py` | 信号引擎（SignalEngine 类） |
| `agent/tests/test_up_trend_structure.py` | 状态机单元测试 |
| `agent/tests/test_structure_signal_engine.py` | 信号引擎单元测试 |
| `agent/src/api/strategy_research_runner.py` | 回测运行器（STRATEGY_MAP 注册） |
| `agent/src/api/strategy_config_store.py` | 策略配置存储（默认参数） |
