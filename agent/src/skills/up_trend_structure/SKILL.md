---
name: up-trend-structure
description: Detect up-trend structure (上涨结构) from daily OHLCV data and generate position-scaling trading signals based on volume-price analysis.
category: strategy
---

## Overview

上涨结构策略 v2：上涨阶段由"连续2天以上价涨量增"定义，止跌K/证伪K在回调中触发新结构。三档分批止盈。

Core concept: 上涨结构 = forming → up_phase → pullback。

## Signal Flow

```
OHLCV → UpTrendStructure.compute() → structure states
       → SignalEngine.generate()     → position signals [0, 0.33, 0.67, -1.0]
```

## Entry Rules (v2)

| Trigger | Signal | Description |
|---------|--------|-------------|
| 止跌K → pullback_end | 0.33 | Trial entry — 1/3 position |
| 证伪K → up_phase (from pullback_end) | 0.67 | Confirm + add — 2/3 position (max) |

## Exit Rules (v2)

| Trigger | Signal | Description |
|---------|--------|-------------|
| Low < pivot_low | -1.0 | Stop loss — pivot broken |
| Loss > stop_loss_pct | -1.0 | Stop loss — percent |
| Divergence / 价跌量缩 unrepaired → pullback | -1.0 | Take profit |
| Profit >= 30% | x0.5 | Take profit half |
| Close < MA(5) | x0.5 | Take profit half of remaining |
| Close < MA(10) | -1.0 | Full exit |

## Key Concepts (v2)

### 价涨量增
- `close > prev_close` AND `volume > prev_volume`

### 价跌量缩
- `close < prev_close` AND `volume < prev_volume`

### 补量 (Repair)
- `close > trigger_close` AND `volume > trigger_volume`

### 止跌K (v3, three patterns, priority: 倒垂 > 反包线 > 两日筑底)
1. **倒垂**: 前日阴线 + 倒锤子(上影≥ratio×实体, 下影<实体) + 最高价>前日中点 + 放量
2. **反包线**: 前日阴线 + 当日收阳 + 收盘>threshold(默认前日中点) + 放量
3. **两日筑底**: D0阴 → D1阳(非倒垂且非反包线) → D2阳+放量+C>D0中点, D2为止跌K

## States (v2)

| State | Meaning |
|-------|---------|
| `no_structure` | No up-trend structure |
| `forming` | 1st day 价涨量增, awaiting confirmation |
| `up_phase` | 2+ consecutive 价涨量增 confirmed |
| `pullback` | Up phase ended (divergence/pvd unrepaired) |
| `pullback_end` | Pullback ended (止跌K detected, awaiting 证伪K) |
| `breakdown` | Price < pivot_low (transient → no_structure) |

## Tunable Parameters (v2)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `up_phase_min_bars` | 2 | Consecutive 价涨量增 days |
| `volume_surge_ratio` | 1.2 | 止跌K volume surge ratio |
| `big_bull_body_ratio` | 0.6 | Reserved, not used in current 止跌K |
| `inv_hammer_shadow_ratio` | 1.1 | 倒垂 upper shadow / body ratio |
| `close_above_prev_mid` | 0.5 | 反包线 close threshold: `threshold = prev_close + (prev_open-prev_close) * ratio` |
| `stop_loss_pct` | 0.03 | Unconditional stop loss |
| `take_profit_pct` | 0.30 | 1st-tier profit threshold |
| `ma_short` | 5 | Short MA period |
| `ma_mid` | 10 | Mid MA period |
| `divergence_repair_bars` | 1 | Repair window |
