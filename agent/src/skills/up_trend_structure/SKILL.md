---
name: up-trend-structure
description: Detect up-trend structure (上涨结构) from daily OHLCV data and generate position-scaling trading signals based on volume-price analysis.
category: strategy
---

## Overview

上涨结构策略：基于量价关系识别上涨趋势中的 "上涨阶段 + 回调阶段" 结构，在回调结束（止跌K + 证伪K）时分步建仓，在量价背离不修复时止盈，在破起涨点或亏损超 3% 时止损。

Core concept: 上涨趋势 = 多个连续上涨结构。每个上涨结构 = 上涨阶段 (≥3天) + 回调阶段 (不破起涨点)。

## Signal Flow

```
OHLCV → UpTrendStructure.compute() → structure states
       → SignalEngine.generate()     → position signals [0, 0.33, 0.67, 1.0, -1.0]
```

## Entry Rules

| Trigger | Signal | Description |
|---------|--------|-------------|
| 止跌K | 0.33 | Trial entry — 1/3 position |
| 证伪K | 0.67 | Confirm + add — 2/3 position |
| Pullback held + bullish volume candle | 1.0 | Full position |

## Exit Rules

| Trigger | Signal | Description |
|---------|--------|-------------|
| Low < pivot_low | -1.0 | Stop loss — pivot broken |
| Loss > 3% | -1.0 | Stop loss — percent |
| Divergence unrepaired → pullback | -1.0 | Take profit |

## Key Signals

### 止跌K (Bottom Signal K-line)
- Pattern: inverted hammer (upper shadow ≥ 1.5× body) or big bullish (body > 60% range)
- Close > 50% of previous bearish body
- Volume > 1.5× previous day

### 证伪K (Confirmation K-line)
- Next day after 止跌K
- Bullish candle OR close > 止跌K close

### 量价背离 (Volume-Price Divergence)
- Price up + volume down vs previous day, OR
- Volume up + price down vs previous day
- Needs next-day repair (bullish + higher volume)

## States

| State | Meaning |
|-------|---------|
| `no_structure` | No up-trend structure detected |
| `forming` | 止跌K seen, awaiting 证伪K |
| `up_phase` | Confirmed up phase (证伪K passed) |
| `pullback` | Divergence unrepaired, pullback in progress |
| `breakdown` | Price broke below pivot_low |

## Backtest Usage

Config snippet:
```json
{
  "source": "auto",
  "codes": ["000001.SZ"],
  "start_date": "2020-01-01",
  "end_date": "2026-07-05",
  "interval": "1D",
  "initial_cash": 1000000,
  "commission": 0.001,
  "engine": "daily"
}
```

Signal engine wrapper at `code/signal_engine.py`:
```python
from src.skills.up_trend_structure.signal_engine import SignalEngine
```

## Tunable Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `up_phase_min_bars` | 3 | Minimum bars for up phase |
| `volume_surge_ratio` | 1.5 | 止跌K volume threshold |
| `big_bull_body_ratio` | 0.6 | Big bullish body/range ratio |
| `inv_hammer_shadow_ratio` | 1.5 | Inverted hammer shadow/body ratio |
| `close_above_prev_mid` | 0.5 | Close above prev body midpoint |
| `stop_loss_pct` | 0.03 | Unconditional stop loss |
| `divergence_repair_bars` | 1 | Divergence repair window |
