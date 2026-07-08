# FactorMiner: Extract Quant Factors from up_trend_structure

**Status:** ready-for-agent

## Problem Statement

The `up_trend_structure` strategy contains three valuable K-line pattern detectors (止跌K, 证伪K, 量价背离) and a five-state structure machine — but these are buried inside a strategy-specific class (`UpTrendStructure`) and can't be reused as standalone quant factors. An analyst who wants to combine 止跌K with factors from the alpha zoo (e.g. GTJA #1 volume-price correlation) has no way to do so without copy-pasting detection logic. The patterns are locked to a single strategy's signal pipeline.

## Solution

Create a new factor zoo — `factor_miner` — that houses quant factors extracted from `up_trend_structure`. Each factor is a standalone `.py` file with `__alpha_meta__` and `compute(panel)`, following the same contract as existing alpha101/gtja191 factors. This makes the patterns available through the standard `Registry.compute()` interface for factor analysis, combination, backtesting, and use by any other strategy.

## User Stories

1. As a quant analyst, I want to use 止跌K as a standalone factor, so that I can combine it with other alpha zoo factors in a multi-factor model.
2. As a quant analyst, I want to use 证伪K as a standalone factor, so that I can confirm 止跌K signals independently or use it as a standalone momentum signal.
3. As a quant analyst, I want to use 量价背离 as a standalone factor, so that I can measure volume-price divergence separately from the up-trend structure state machine.
4. As a quant analyst, I want to use 上涨结构状态 as a factor encoding (0-4), so that I can use the structure phase as a regime filter for other strategies.
5. As a strategy developer, I want the new factors to be discoverable via `Registry.list()` and computable via `Registry.compute()`, so that they integrate with the existing factor analysis toolchain.
6. As a developer, I want the factor outputs to match the original `UpTrendStructure.compute()` outputs for single-stock data, so that I can trust the extraction didn't introduce bugs.
7. As a developer, I want the new factors to pass purity and lookahead gates automatically, so that they meet the same quality bar as existing zoo factors.
8. As a developer, I want the original `up_trend_structure` strategy to remain unchanged, so that the existing opportunity pool and scan pipeline are unaffected.

## Implementation Decisions

**Zoo naming**: New zoo called `factor_miner`. Four factors: `fminer_001` through `fminer_004`.

**Parameter strategy**: All thresholds hardcoded at defaults (`volume_surge_ratio=1.5`, `big_bull_body_ratio=0.6`, `inv_hammer_shadow_ratio=1.5`, `close_above_prev_mid=0.5`, `stop_loss_pct=0.03`, `divergence_repair_bars=1`). `compute(panel)` takes no parameters, matching existing zoo convention. Parameter tuning stays at the strategy layer.

**Batch 1 — Pure vectorized factors**:
- `fminer_001`: 止跌K signal. Binary (0/1). Conditions: prior day bearish + (inverted hammer or big bullish) + close above prior body midpoint + volume > 1.5x prior.
- `fminer_002`: 证伪K signal. Binary (0/1). Conditions: prior day was 止跌K + (current bullish or close > prior 止跌K close).
- `fminer_003`: Volume-price divergence signal. Binary (0/1). Conditions: (price up ∧ volume down) ∨ (volume up ∧ price down).

**Batch 2 — State machine factor**:
- `fminer_004`: Up-trend structure state encoding. Integer 0-4 (0=no_structure, 1=forming, 2=up_phase, 3=pullback, 4=breakdown). Requires per-column iteration because each bar's state depends on prior state and pivot_low.

**Wide-panel adaptation**: The detector logic from `UpTrendStructure` is already column-vectorized using `shift(1)`. On wide DataFrames (columns = stock codes), `shift(1)` operates independently per column — no code change needed for fminer_001-003. fminer_004 wraps `UpTrendStructure.compute()` per column.

**Registry integration**: No changes to `registry.py`. The Registry AST-scans all `zoo/*/*.py` files and auto-registers modules with valid `__alpha_meta__`.

**Factor metadata shape** (all four factors share this structure):
| Field | fminer_001-002 | fminer_003 | fminer_004 |
|-------|---------------|-----------|------------|
| theme | `["reversal", "volume"]` (001), `["momentum"]` (002) | `["volume", "reversal"]` | `["momentum", "volume"]` |
| columns_required | `["open","high","low","close","volume"]` | `["close","volume"]` | `["open","high","low","close","volume"]` |
| universe | `["equity_cn"]` | `["equity_cn"]` | `["equity_cn"]` |
| frequency | `["1D"]` | `["1D"]` | `["1D"]` |
| decay_horizon | 2 | 1 | 5 |
| min_warmup_bars | 3 | 2 | 5 |

**Existing strategy untouched**: `watch_pool_runner.py` and `watch_pool_routes.py` continue using `UpTrendStructure` + `SignalEngine` directly. The factors are an additive layer.

## Testing Decisions

**Test seam**: `Registry.compute(alpha_id, panel)` — same seam used by all existing zoo factor tests (`test_gtja191_part1_samples.py` pattern).

**Test design**:
- Seeded panel (`np.random.RandomState(42)`, 30 rows × 3 codes) for reproducible numerical regression.
- For fminer_001-003: compare factor `compute(panel)` column output against `UpTrendStructure.compute()` single-stock output on the same synthetic data.
- For fminer_004: verify state encodings are consistent and all five states appear in realistic sequences.
- Single test file.

**Existing gates reused**:
- `test_alpha_purity.py` — AST-scans all zoo modules, auto-covers new factors.
- `test_lookahead.py` — lookahead detection, auto-covers new factors.

**Prior art**: `agent/tests/factors/test_gtja191_part1_samples.py` — same seeded panel pattern, same `Registry.compute()` seam.

## Out of Scope

- Automated factor mining from arbitrary strategies (manual extraction only for this PRD)
- CLI tool for factor mining (`screen_bottom_k.py` exists but is unchanged)
- Modifying `up_trend_structure` strategy logic or parameters
- Frontend changes (factor results are consumed via existing factor analysis tools)
- New API endpoints for factor miner
- Parameterized factor variants (e.g. `fminer_001_vol2.0`)

## Further Notes

- The `factor_miner` zoo establishes the pattern for future strategy-to-factor extraction. Other strategies with reusable signal components can follow the same workflow.
- fminer_004 (state machine) is expected to be slower than the vectorized factors — it calls `UpTrendStructure.compute()` once per stock code. For large panels this cost is documented and expected.
