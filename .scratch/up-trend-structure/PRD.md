# 上涨结构交易策略 v2 — 量价关系驱动的状态机重构

**Status:** ready-for-agent
**Created:** 2026-07-05
**Updated:** 2026-07-12
**Author:** fluagen

## Problem Statement

当前 v1 策略存在以下问题：

1. 上涨阶段（up_phase）进入依赖 止跌K → 证伪K 单次形态确认，而非对持续量价关系的验证。一根证伪K不足以确认上涨趋势的成立。
2. `up_phase_min_bars` 参数存在于代码中但从未被状态机使用（dead code）。
3. 上涨阶段内部只处理量价背离，未处理"价跌量缩"（价格和成交量同步萎缩）的情况。
4. 仓位管理只有全进全出（0.33 → 0.67 → 1.0），缺少分批止盈机制，无法在趋势运行中逐步锁定利润。

## Solution

**核心思路：上涨阶段由量价关系定义，而非单一K线形态。**

1. 上涨阶段 = 连续2天以上价涨量增（`close↑ + volume↑`）
2. 止跌K/证伪K 降级为上涨结构内部信号——在回调末尾触发新一轮结构
3. 上涨阶段结束条件扩展为两种：背离未修复 OR 价跌量缩未修复
4. 修复（补量）条件统一：`close > 触发日close AND volume > 触发日volume`
5. 仓位信号简化：移除 1.0 全仓，最大仓位 0.67
6. 新增三档分批止盈：盈利30% → 5日均线 → 10日均线

## User Stories

1. As a trader, I want the up-phase to be defined by 2+ consecutive days of 价涨量增 (close↑ + volume↑), so that I only enter trends backed by sustained volume-price coordination
2. As a trader, I want a single day of 价涨量增 to put the structure into "forming" state, so that I can observe whether a trend is forming before committing
3. As a trader, I want the structure to return to no_structure if the second day fails to confirm 价涨量增, so that false signals are quickly discarded
4. As a trader, I want 止跌K to restart the forming process from a pullback, so that I can capture the start of a new up-trend structure
5. As a trader, I want 证伪K to confirm entry from forming into up_phase during a pullback restart, so that I have a reliable entry trigger
6. As a trader, I want the structure to fall back to pullback if 止跌K appears but no 证伪K follows, so that unconfirmed signals don't trap me
7. As a trader, I want volume-price divergence in up_phase to NOT immediately end the phase—instead, the next day should attempt repair（补量）, so that brief anomalies don't prematurely end trends
8. As a trader, I want divergence repair to require close > divergence-day close AND volume > divergence-day volume, so that repair is a meaningful confirmation of trend health
9. As a trader, I want unrepaired divergence to end the up phase and enter pullback, so that deteriorating trends are exited
10. As a trader, I want 价跌量缩 (both price and volume falling) to also attempt next-day repair, with unrepaired cases ending the up phase, so that weakening trends are caught
11. As a trader, I want the 起涨点 (pivot low) to always be the lowest price of the forming bar, consistently applied across both entry paths, so that stop-loss placement is predictable
12. As a trader, I want price breaking below the pivot low to mark the structure as "breakdown", destroying it, so that I can cut losses decisively
13. As a trader, I want my maximum position to be 0.67 (证伪K confirmed) and never 1.0, so that I always maintain capital reserve
14. As a trader, I want to take profit 1/2 of my position when unrealized profit reaches 30%, so that I can lock in gains early
15. As a trader, I want to take profit another 1/2 of my remaining position when price breaks below the 5-day moving average, so that I exit on short-term weakness
16. As a trader, I want to fully exit when price breaks below the 10-day moving average (5日线止盈已触发过半仓), so that I'm fully out when the intermediate trend turns
17. As a trader, I want automatic stop-loss when price breaks below pivot_low or unrealized loss exceeds stop_loss_pct, so that downside is capped

## Implementation Decisions

### 概念定义

| 概念 | 定义 |
|------|------|
| 价涨量增 | `close > prev_close` AND `volume > prev_volume` |
| 量价背离 | `(close > prev_close AND volume < prev_volume)` OR `(volume > prev_volume AND close < prev_close)` |
| 价跌量缩 | `close < prev_close` AND `volume < prev_volume` |
| 补量（修复） | `close > 触发日close` AND `volume > 触发日volume` |
| 起涨点 | forming 状态对应K线的最低价（第一根价涨量增K线的最低价） |
| 上涨结构 | forming → up_phase → pullback 的完整生命周期 |

### 状态机

```
no_structure ──价涨量增──▶ forming ──第2天价涨量增──▶ up_phase
     ▲            │                    │
     │            │ 第2天未价涨量增      │ 背离/价跌量缩 未补量修复
     │            ▼                    ▼
     │       no_structure          pullback
     │                                 │
     │              止跌K（也是价涨量增）  │
     │                                 ▼
     │              ┌───────────── forming ──证伪K──▶ up_phase (新结构)
     │              │                  │
     │              │    无证伪K → 回到pullback
     │              │
     ├──────────────┴───────────────────── low < 起涨点 (breakdown)
     └────────────────────────────────────┘
```

完整转移表：

| 当前状态 | 条件 | 新状态 | 动作 |
|----------|------|--------|------|
| `no_structure` | 价涨量增 | `forming` | 起涨点 = 当前low |
| `forming` | 第2天价涨量增（从 no_structure 来） | `up_phase` | — |
| `forming` | 第2天未价涨量增（从 no_structure 来） | `no_structure` | — |
| `forming` | 证伪K（从 pullback 来，由止跌K触发） | `up_phase` | — |
| `forming` | 止跌K后无证伪K（从 pullback 来） | `pullback` | — |
| `up_phase` | 价涨量增持续 | `up_phase` | — |
| `up_phase` | 背离 + 第二天补量成功 | `up_phase` | 延续 |
| `up_phase` | 背离 + 第二天补量失败 | `pullback` | 上涨阶段结束 |
| `up_phase` | 价跌量缩 + 第二天补量成功 | `up_phase` | 延续 |
| `up_phase` | 价跌量缩 + 第二天补量失败 | `pullback` | 上涨阶段结束 |
| `pullback` | 止跌K | `forming` | 新起涨点 = 止跌K low |
| 任何(除no_structure) | `low < 起涨点` | `breakdown` | — |
| `breakdown` | (立即) | `no_structure` | — |

### 仓位信号规则

| 触发条件 | 信号值 | 说明 |
|----------|--------|------|
| 止跌K（在 forming 中） | 0.33 | 试探性建仓 1/3 |
| 证伪K（确认 forming → up_phase） | 0.67 | 加仓至 2/3（最大仓位） |
| 盈利 ≥ 30% | ×0.5 | 止盈一半 |
| 跌破 5日均线 | ×0.5 | 止盈剩余一半 |
| 跌破 10日均线 | 0 | 清仓（5日线止盈已触发过） |
| low < 起涨点 | 0 | 止损，结构破坏 |
| 未实现亏损 > stop_loss_pct | 0 | 无条件止损 |
| 背离未修复 → pullback | 0 | 止盈退出 |
| 价跌量缩未修复 → pullback | 0 | 止盈退出 |

### 模块变更

- **UpTrendStructure 检测器**: 新增 `_detect_price_up_volume_up()` 和 `_detect_price_volume_down()`；完全重写 `_compute_states()`；`up_phase_min_bars` 默认值改为 2 并实际生效
- **SignalEngine**: 移除 1.0 全仓逻辑；新增三档止盈（需计算 MA 和累计盈亏）；`stop_loss_pct` 保持
- **策略配置（strategy_config_store）**: `up_phase_min_bars` 默认 3→2；新增 `take_profit_pct`、`ma_short`、`ma_mid`
- **SKILL.md**: 更新状态机文档

### 参数变更

| 参数 | 旧默认值 | 新默认值 | 说明 |
|------|---------|---------|------|
| `up_phase_min_bars` | 3 (dead) | 2 | 价涨量增连续天数要求，现在生效 |
| `stop_loss_pct` | 0.03 | 0.03 | 不变 |
| `take_profit_pct` | — | 0.30 | 新增：第一档止盈盈利比例 |
| `ma_short` | — | 5 | 新增：短期均线周期 |
| `ma_mid` | — | 10 | 新增：中期均线周期 |
| `volume_surge_ratio` | 1.5 | 1.5 | 不变 |
| `big_bull_body_ratio` | 0.6 | 0.6 | 不变 |
| `inv_hammer_shadow_ratio` | 1.5 | 1.5 | 不变 |
| `close_above_prev_mid` | 0.5 | 0.5 | 不变 |
| `divergence_repair_bars` | 1 | 1 | 不变（修复窗口固定1天） |

## Testing Decisions

### 测试策略

测试 external behavior（给定K线序列 → 输出状态/信号），不测试 implementation details（内部循环变量）。

### 测试层级

| Level | Seam | 覆盖 |
|-------|------|------|
| Unit — 状态机 | 合成 OHLCV DataFrame → `UpTrendStructure.compute()` | 所有状态转移场景 |
| Unit — 信号引擎 | OHLCV + 状态序列 → `SignalEngine.generate()` | 仓位信号 + 分批止盈 |
| Compile | `py_compile` | 语法检查 |

### 状态机测试场景

- 连续2天价涨量增 → up_phase
- 1天价涨量增后失败 → forming → no_structure
- 背离 + 补量成功 → up_phase 延续
- 背离 + 补量失败 → pullback
- 价跌量缩 + 补量成功 → up_phase 延续
- 价跌量缩 + 补量失败 → pullback
- pullback → 止跌K → forming → 证伪K → up_phase
- 止跌K 后无证伪K → forming → pullback
- 跌破起涨点 → breakdown → no_structure

### 信号引擎测试场景

- 止跌K → signal 0.33
- 证伪K → signal 0.67
- 最大仓位不超过 0.67
- 盈利30%触发止盈（仓位减半）
- 跌破5日线触发止盈（仓位再减半）
- 跌破10日线清仓
- 止损优先级高于止盈

### Prior Art

- `agent/tests/test_up_trend_structure.py` — 现有状态机测试
- `agent/tests/test_structure_signal_engine.py` — 现有信号引擎测试

## Out of Scope

- 多股票组合层面仓位管理
- 其他策略文件的适配
- 前端 UI 变更（参数面板自动适配新参数）
- `watch_pool_runner.py` 的适配（后续单独处理）
- `screen_bottom_k.py` CLI 工具的适配

## Further Notes

- 止跌K 天然满足"价涨量增"条件（volume surge + close above midpoint），因此无论从 no_structure 还是 pullback 进入 forming，起涨点 = forming bar 最低价——逻辑一致
- 三档止盈是级联关系：先触发盈利30%（减半仓），再跌破5日线（再减半），最后跌破10日线（清仓）。每档操作的是当前剩余仓位
- 修复窗口固定为1天。连续多天背离/价跌量缩时，每对（触发日+次日）独立判断
- 策略源自飞书知识库 "大a知识库/大a梦想" 课程材料（公开课 + 会员课件）
