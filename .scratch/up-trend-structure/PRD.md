# 上涨结构交易策略 — PRD

**Status:** ready-for-agent
**Created:** 2026-07-05
**Author:** fluagen

## Problem Statement

交易者从课程学习中掌握了 "上涨结构" 交易方法论（基于量价关系的趋势跟踪战法），但目前只能在飞书文档中手动查阅课件，无法系统性地将这套方法论应用于实际选股和交易决策。需要将这套主观交易方法论量化为可执行的信号引擎，接入现有的回测系统进行验证和优化。

## Solution

实现 "上涨结构" 策略作为一个独立栏目（`up-trend-structure`），包含三层架构：

1. **结构识别器**：实时识别每根 K 线所处的上涨结构状态（上涨阶段/回调阶段/结构破坏）
2. **信号引擎**：基于结构状态 + 止跌K/证伪K 检测，生成仓位信号（1/3 分步建仓）
3. **回测配置**：通过标准 config.json + SignalEngine 协议接入 backtest runner

数据源使用现有 loader registry（tushare/akshare/eastmoney）实时获取 A 股日线数据。

## User Stories

1. As a trader, I want the system to automatically identify when a stock is in an "up trend structure" (上涨结构), so that I can focus on stocks with favorable trend conditions.
2. As a trader, I want the system to detect "bottom signal K-lines" (止跌K) during pullback phases, so that I can identify potential entry points.
3. As a trader, I want the system to detect "confirmation K-lines" (证伪K) that validate the bottom signal, so that I can confirm the pullback is ending.
4. As a trader, I want the system to detect volume-price divergence (量价背离) within the up phase, so that I can be alerted to weakening trend quality.
5. As a trader, I want the system to generate position-sizing signals (1/3 → 2/3 → full position), so that I can scale into positions with controlled risk.
6. As a trader, I want automatic stop-loss signals when price breaks below the bottom signal K-line low or loss exceeds 3%, so that I can protect capital.
7. As a trader, I want automatic take-profit signals when volume-price divergence appears and is not repaired the next day, so that I can exit before the pullback phase begins.
8. As a trader, I want the strategy to be backtestable on A-share stocks using existing data loaders, so that I can evaluate its historical performance.
9. As a developer, I want the strategy implemented as an independent skill directory, so that it does not interfere with existing strategies.
10. As a developer, I want re-usable candlestick detection utilities (from the existing candlestick skill) to be leveraged, so that code duplication is minimized.

## Implementation Decisions

### Architecture: Three-layer with independent skill directory

All code lives in a new `up-trend-structure` skill directory, following the pattern of existing skills (e.g., `candlestick/`). No existing files are modified.

**Layer 1** — Structure Detector: State machine that processes OHLCV bars sequentially and outputs the current structure state for each bar.

**Layer 2** — Signal Engine: Implements the `SignalEngine` contract (`generate(data_map) -> dict[code, Series]`). Consumes Layer 1 output. Manages position scaling and stop-loss/take-profit logic.

**Layer 3** — Backtest Config: Standard `config.json` using `source: "auto"` for A-share data routing.

### Up Trend Structure Rules

**Up phase:**
- Requires ≥ 3 consecutive trading days of predominantly bullish candles with volume-price coordination

**Volume-price divergence:**
- Price rises but volume shrinks vs previous day, OR volume rises but price falls
- Requires next-day repair (bullish candle with higher volume than divergence day)
- Unrepaired divergence → up phase ends → pullback begins

**Pullback phase:**
- Consolidation or decline with shrinking volume
- Must not break below pivot low (止跌K lowest price)

**Bottom Signal K-line (止跌K):**
- Pattern: inverted hammer (upper shadow ≥ 1.5× body, lower shadow < body) OR big bullish candle (bullish, body > 60% of range)
- Close > 50% of previous bearish candle's body
- Volume > 1.5× previous day's volume

**Confirmation K-line (证伪K):**
- Next day after 止跌K
- Any bullish candle OR close > 止跌K close
- Volume not required

**Pivot low (起涨点):**
- Set to the low of the most recent 止跌K
- If 证伪K confirms, the 止跌K becomes the first bar of the new up phase
- Breaking below pivot low = structure breakdown

### Entry Rules (position scaling)

| Trigger | Action | Signal Value |
|---------|--------|-------------|
| 止跌K appears | Enter 1/3 position (trial) | 0.33 |
| 证伪K confirms | Add 1/3 position | 0.67 |
| Pullback holds above 止跌K low + bullish volume candle | Add final 1/3 | 1.0 |

### Exit Rules

| Trigger | Action | Signal Value |
|---------|--------|-------------|
| Price breaks below 止跌K low | Stop loss — full exit | -1.0 |
| Unrealized loss > 3% | Stop loss — full exit | -1.0 |
| Volume-price divergence + next-day unrepaired | Take profit — full exit | -1.0 |

### Reuse of existing code

The candlestick skill's example signal engine provides helper functions (`_body`, `_range`, `_upper_shadow`, `_lower_shadow`) and the `_detect_inverted_hammer` detector that are directly reusable. These functions are copied into the new module (not imported) to keep the module self-contained.

### Data source

Use existing loader registry via `source: "auto"` in config.json. A-share daily OHLCV data routed through tushare/akshare/eastmoney loaders automatically.

### Tunable parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `up_phase_min_bars` | 3 | Minimum bars for up phase |
| `volume_surge_ratio` | 1.5 | 止跌K volume threshold vs prior day |
| `big_bull_body_ratio` | 0.6 | Big bullish candle body/range ratio |
| `inv_hammer_shadow_ratio` | 1.5 | Inverted hammer upper shadow/body ratio |
| `close_above_prev_mid` | 0.5 | Close must be above this fraction of prior bearish body |
| `stop_loss_pct` | 0.03 | Unconditional stop loss threshold |
| `divergence_repair_bars` | 1 | Days allowed for divergence repair |

## Testing Decisions

### Testing seams

All tests use existing seams — no new frameworks or mock layers needed.

| Level | Seam | What it tests |
|-------|------|---------------|
| Unit | Synthetic OHLCV DataFrames → detector functions | 止跌K, 证伪K, divergence, big bullish candle detection correctness |
| State machine | Hand-crafted K-line sequences covering full structure lifecycle | State transitions: no_structure → forming → up_phase → pullback → breakdown |
| Signal engine | `SignalEngine.generate()` with synthetic data_map | Position scaling logic (0 → 0.33 → 0.67 → 1.0), stop-loss/take-profit signals |
| Integration | Backtest runner with real historical data (A-share, e.g. 000001.SZ) | End-to-end verification: config.json → runner → artifacts (metrics.csv, equity.csv) |

### Good test characteristics
- Test external behavior (signal values, state labels), not internal implementation
- Independent tests per detector function
- State machine tests verify transitions at exact boundary bars
- Integration test verifies: metrics.csv exists, equity.csv has no NaN, trade_count > 0, exit_code == 0

### Prior art
- `agent/tests/` — existing test patterns for backtest runner
- `agent/src/skills/candlestick/example_signal_engine.py` — same `SignalEngine` contract, same testing approach

## Out of Scope

- Real-time/live trading execution
- Multi-timeframe analysis (daily only for initial implementation)
- 堆量 (volume accumulation) detection — deferred
- 涨停后 7-14 天窗口检测 — deferred
- 周线均线多头判断 — deferred
- Multi-stock portfolio optimization (single-stock strategy initially)
- Short-side trading (long-only for initial implementation)
- Database/本地数据存储 — data sourced via existing remote API loaders only

## Further Notes

- The strategy is derived from 飞书知识库 "大a知识库/大a梦想" course materials (公开课 + 会员课件)
- Core philosophy: never participate in pullback phases — exit when divergence appears unrepaired, re-enter only after 止跌K + 证伪K confirm new up phase
- The up trend structure state machine is the foundation layer; future strategies can consume its output
