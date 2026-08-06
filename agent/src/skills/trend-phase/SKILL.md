---
name: trend-phase
description: Quantitative trend-phase trading strategy for A-share stocks — three-tier priority risk control, six-phase BIAS classification, dual-layer trend-position engine, divergence detection, trap identification, and dynamic position sizing (0%/10%/20%/50%/100%).
category: strategy
tags: [trend, bias, momentum, position-management, a-share, technical]
---

# Trend-Phase Trading Strategy (趋势阶段量化策略)

## Overview

基于 BIAS（乖离率 = (MA5−MA20)/MA20×100%）及其统计特征（μ 均值、σ 标准差）和平滑斜率 K，对 A 股走势进行六阶段量化分类，配合三层优先级风控体系、趋势-仓位双层引擎、背离信号处理和陷阱识别，实现从"什么时候买、买多少、什么时候卖"的全量化仓位管理。

## Core Indicators

| Indicator | Formula | Description |
|-----------|---------|-------------|
| BIAS | (MA5 − MA20) / MA20 × 100% | 短期与中期均线的乖离率 |
| μ (mu) | 60-day rolling mean of BIAS | 常态中枢，每 20 日更新 |
| σ (sigma) | 60-day rolling std of BIAS | 波动标尺，每 20 日更新 |
| K (slope) | MA3(BIAS)[t] − MA3(BIAS)[t−5] | 平滑短期斜率，过滤涨跌停跳变 |
| MA60 direction | MA60[t] − MA60[t−5] > 0 | 趋势总指挥 |
| MA20 direction | MA20[t] − MA20[t−3] > 0 | 灵敏度辅助 |

## Three-Tier Priority System

```
Tier 1 (Ultimate Risk Control)
  ├─ Trigger: MA60↓ AND BIAS ≥ μ − 2.5σ
  └─ Action:  FORBID all buys. Clear existing positions (0%).

Tier 2 (Extreme Bounce Channel)
  ├─ Trigger: MA60↓ AND BIAS < μ − 2.5σ
  └─ Action:  Max 10% position, 3-day hold limit, ±5% TP/SL.

Tier 3 (Standard Strategy)
  ├─ Trigger: MA60↑
  └─ Action:  Full six-phase + dual-layer engine.
```

## Tier 3: Trend-Position Dual-Layer Engine

| MA60 | MA20 | Position Cap | Allowed Actions |
|------|------|-------------|-----------------|
| ↑ | ↑ | 100% | Full buy/hold (trend resonance) |
| ↑ | ↓ | 50% | Hold or sell only, NO new buys |

**Sticky filter**: When |MA20−MA60|/MA60 < 1.5%, maintain current position (MA convergence).

## Six-Phase Classification

| Phase | BIAS Range | K Condition | Position | Notes |
|-------|-----------|-------------|----------|-------|
| ① Main Uptrend | > μ+2σ | K > 0 | 100% | Hold until K turns negative |
| ② High Consolidation | μ+σ ~ μ+2σ | K turns pos→neg | 50% | No new buys |
| ③ High Topping | < μ+σ | K persistently neg | 20% | Clear if BIAS < μ |
| ④ Main Downtrend | MA60↓ | — | 0% | Blocked by Tier 1 |
| ⑤ Low Consolidation | MA60↓ | — | 0% | Blocked by Tier 1 |
| ⑥ Low Bottoming | > μ−σ | K turns neg→pos | 0→50% | Wait for MA20 to turn up |

## Trap Identification

| Trap | Phenomenon | Filter | Action |
|------|-----------|--------|--------|
| ⑥→① False Rebound | BIAS rebounds, K positive, MA60 still down | Tier 1 intercepts | Clear Tier 2 at μ−0.5σ + K turns neg |
| ②→③ False Breakdown | BIAS drops fast, K negative, MA60 still up | DON'T panic sell | Add back to 100% at μ+σ + K turns pos |

## Divergence Signals

| Market | Divergence Type | Action |
|--------|----------------|--------|
| MA60↑ | Top divergence (price↑ BIAS→) | Early reduce 100%→50% |
| MA60↑ | Bottom divergence (price↓ BIAS→) | Early add 20%→50% |
| MA60↓ | Bottom divergence | Confirms Tier 2 bounce only |

## Execution Rules

- **Dynamic threshold**: σ > 2× median → tighten to μ±1.5σ; σ < 0.5× median → widen to μ±2.5σ
- **Hard stop**: −5% unrealized loss → unconditional exit
- **Time stop**: 10 days without hitting target → force close day 11
- **Gap protection**: Skip first bar after >3-day trading halt
- **Warmup**: First 60 bars output 0 (insufficient rolling data)

## Signal Convention

| Value | Meaning |
|-------|---------|
| 1.0 | Full position (100%) |
| 0.5 | Half position (50%) |
| 0.2 | Light position (20%) |
| 0.1 | Extreme bounce (10%, Tier 2) |
| 0.0 | Flat / no position |
| −1.0 | Force close all |

## Parameters

All parameters have defaults. See `signal_engine.py` `__init__` for the complete list.

Key groups:
- **MA periods**: `ma_short=5`, `ma_mid=20`, `ma_long=60`
- **μ/σ**: `mu_window=60`, `mu_recalc_freq=20`, `sigma_window=60`
- **K slope**: `k_ma_period=3`, `k_lag=5`
- **Phase thresholds**: `upper_extreme_sigma=2.0`, `upper_consolidate_sigma=1.0`, `lower_bottoming_sigma=1.0`, `lower_extreme_sigma=2.5`
- **Dynamic threshold**: `enable_dynamic_threshold=True`, `tighten_sigma_ratio=2.0`, `widen_sigma_ratio=0.5`
- **Tier 2**: `tier2_max_hold_days=3`, `tier2_take_profit_pct=0.05`, `tier2_stop_loss_pct=0.05`
- **Stops**: `hard_stop_loss_pct=0.05`, `enable_time_stop=True`, `time_stop_days=10`
- **Divergence**: `enable_divergence=True`, `divergence_lookback=20`
- **Market resonance**: `market_resonance_enabled=False` (off by default)

## Dependencies

- pandas, numpy only (no external signal libraries)

## Usage

1. Copy `signal_engine.py` to your run directory's `code/` subdirectory
2. Create `config.json` with codes, dates, source (see `config.example.json`)
3. Run: `python -m backtest.runner <run_dir>`

## Notes

- A-share only (沪深). No short selling — negative signals mean close positions.
- Single-stock independent signals. Multi-stock L1 normalization handled by engine.
- CSI 300 market resonance filter is optional and disabled by default.
- ChinaAEngine handles T+1, price limits, and 100-share lots automatically.
