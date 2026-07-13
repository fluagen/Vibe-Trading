# 上涨结构交易策略 v2

**Status:** ready-for-agent | **Updated:** 2026-07-13 | **Author:** fluagen

## 核心设计

策略基于三层架构：**指标**描述K线形态 → **状态机**判断结构阶段 → **信号引擎**输出仓位决策。

### 概念定义

| 概念 | 定义 |
|------|------|
| 价涨量增 | `close > prev_close` AND `volume > prev_volume` |
| 价跌量缩 | `close < prev_close` AND `volume < prev_volume` |
| 量价背离 | `(close↑ AND volume↓)` OR `(volume↑ AND close↓)` |
| 补量（修复） | `close > 触发日close` AND `volume > 触发日volume` |
| 起涨点 | forming bar 的最低价 |
| 止跌K | 倒锤线(上影≥1.2×body)/大阳线(body>60%振幅) + vol>前日×1.2 + close>前日中点 |
| 证伪K | 止跌K次日，阳线 OR close>止跌K close |
| 上涨结构 | forming → up_phase → pullback → pullback_end 的完整生命周期 |

### 状态机

6 个状态，13 条转移规则：

| 当前状态 | 条件 | 新状态 | 动作 |
|----------|------|--------|------|
| `no_structure` | 价涨量增 | `forming` | 起涨点=当前low |
| `forming` | 价涨量增 | `up_phase` | — |
| `forming` | 非价涨量增 | `no_structure` | — |
| `pullback_end` | 证伪K | `up_phase` | — |
| `pullback_end` | 非证伪K | `pullback` | — |
| `up_phase` | 背离 or 价跌量缩 | (挂起) | 记录触发日close/vol |
| `up_phase` | 挂起次日 + 补量成功 | `up_phase` | 延续 |
| `up_phase` | 挂起次日 + 补量失败 | `pullback` | 上涨阶段结束 |
| `up_phase` | 价涨量增 | `up_phase` | 延续 |
| `pullback` | 止跌K | `pullback_end` | 新起涨点=止跌K low |
| `*` (除no_structure) | `low < 起涨点` | `breakdown` | — |
| `breakdown` | 立即 | `no_structure` | — |

### 信号规则

入场仅限 pullback 重启路径，退出为三档级联：

| 信号值 | 触发条件 | 说明 |
|--------|------|------|
| 0.33 | 止跌K + `pullback→pullback_end` + 空仓 | 入场 1/3 |
| 0.67 | 证伪K + `pullback_end→up_phase` + 已有0.33 | 加至 2/3（上限） |
| ×0.5 | 浮动盈利 ≥ 30% | 止盈减半 |
| ×0.5 | close < MA(5) | 止盈再减半 |
| -1.0 | close < MA(10) | 清仓 |
| -1.0 | low < 起涨点 | 止损 |
| -1.0 | 浮动亏损 > 3% | 止损 |
| -1.0 | 背离/价跌量缩 补量失败 → pullback | 退出 |

信号值为**仓位目标**：正数 = 目标仓位，`×0.5` = 当前仓位减半，`-1.0` = 清仓。

### 指标 → 状态 → 信号 关系

```
指标                  状态转移               信号
─────────────────────────────────────────────────────
价涨量增 ────→ no_structure → forming
价涨量增(2nd) → forming → up_phase
背离/价跌量缩  → up_phase → pullback ────→ -1.0
  (补量失败)
止跌K ───────→ pullback → pullback_end ──→ 0.33
证伪K ───────→ pullback_end → up_phase ──→ 0.67
pivot_low ───→ breakdown ──────────────→ -1.0
盈利≥30% ─────────────────────────────→ ×0.5
close<MA(5) ───────────────────────────→ ×0.5
close<MA(10) ──────────────────────────→ -1.0
```

## 可调参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `up_phase_min_bars` | 2 | 价涨量增连续天数要求 |
| `volume_surge_ratio` | 1.2 | 止跌K 成交量放大倍数 |
| `inv_hammer_shadow_ratio` | 1.2 | 倒锤线上影/实体倍数 |
| `big_bull_body_ratio` | 0.6 | 大阳线实体/振幅比例 |
| `close_above_prev_mid` | 0.5 | 收盘站上前日实体中点 |
| `stop_loss_pct` | 0.03 | 无条件止损比例 |
| `take_profit_pct` | 0.30 | 第一档止盈盈利比例 |
| `ma_short` | 5 | 第二档止盈均线周期 |
| `ma_mid` | 10 | 第三档清仓均线周期 |
| `divergence_repair_bars` | 1 | 背离修复窗口（天） |

## Testing

测试策略：只测 external behavior（K线序列 → 状态/信号输出），不测内部实现。

| Level | Seam | 覆盖 |
|-------|------|------|
| 状态机 | 合成OHLCV → `UpTrendStructure.compute()` | 所有转移规则 |
| 信号引擎 | OHLCV + 状态 → `SignalEngine.generate()` | 入场/止盈/止损 |
| 编译 | `py_compile` | 语法 |

关键测试场景：
- 连续2天价涨量增 → forming → up_phase
- 背离 + 补量成功/失败
- pullback → 止跌K → 证伪K → 新up_phase
- 三档止盈级联触发
- 止损优先级

Prior art: `agent/tests/test_up_trend_structure.py`, `agent/tests/test_structure_signal_engine.py`

## Out of Scope

- 多股票组合仓位管理
- `watch_pool_runner.py` / `screen_bottom_k.py` 适配
- 前端 UI 变更
