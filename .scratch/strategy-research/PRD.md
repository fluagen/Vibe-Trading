# Strategy Research: Per-Stock Backtest from Sentiment Sector Constituents

**Status:** ready-for-agent

## Problem Statement

A quant analyst using the market sentiment dashboard can see which sectors are crowded or favored by capital flow, but there is no way to drill down from a hot sector into its constituent stocks and test whether a strategy — like the up-trend structure strategy — would have produced profitable signals on those stocks historically. The analyst must manually look up sector constituents, fetch OHLCV data, and run the strategy detector script outside the app. The sentiment-to-backtest pipeline is entirely manual.

## Solution

Add a "策略研究" (Strategy Research) page that closes the gap between the sentiment dashboard and strategy backtesting. The user selects one or more sectors from the sentiment-collected board list, the system auto-resolves their constituent stocks (cached from THS iwencai), fetches OHLCV data via the existing mootdx loader, runs the up-trend structure strategy per stock, and streams backtest results via SSE — with incremental progress, a summary table with mini K-line charts, and a drill-down detail panel per stock showing full metrics, equity curve, and trade log.

## User Stories

1. As a quant analyst, I want to select a sector from the sentiment-collected board list, so that I can focus my backtest on stocks that belong to a capital-favored sector.
2. As a quant analyst, I want the system to automatically load all constituent stocks of my chosen sector(s), so that I don't have to manually collect stock codes.
3. As a quant analyst, I want to add or remove individual stocks from the auto-selected list, so that I can fine-tune the backtest universe.
4. As a quant analyst, I want to choose a backtest date range via preset buttons (30/60/120/250 trading days) or custom start/end dates, so that I can test the strategy over different lookback windows.
5. As a quant analyst, I want to run the up-trend structure strategy as a per-stock backtest on all selected stocks, so that I can see how the strategy would have performed on each individual stock.
6. As a quant analyst, I want to see real-time progress (done N / total M) as the backtest runs, so that I know how long the operation will take.
7. As a quant analyst, I want to see a summary table showing each stock's current structure state, trade count, win rate, latest signal, and cumulative return, so that I can quickly compare stocks at a glance.
8. As a quant analyst, I want to see a miniature K-line chart with signal markers embedded in each summary table row, so that I can visually assess signal quality without expanding a detail view.
9. As a quant analyst, I want to click a stock row and see a full detail panel with equity curve, trade log (entry/exit with dates and prices), and state distribution, so that I can deeply analyze a single stock's backtest results.
10. As a developer, I want the sector constituent data to be cached in SQLite with a 24-hour TTL, so that repeated queries don't burn the THS iwencai API quota.
11. As a developer, I want the backtest runner to reuse the existing mootdx loader and its parquet cache, so that OHLCV data is not refetched on every backtest run with the same date range.
12. As a developer, I want new strategies to be addable via the same STRATEGY_MAP pattern used by the watch pool, so that the system is extensible without rewriting the backtest engine.

## Implementation Decisions

- **Strategy**: Only "up_trend_structure" is supported initially. The runner uses the same `STRATEGY_MAP` pattern as `watch_pool_runner`, so adding strategies is a map entry + detector class + signal engine class.

- **Backtest mode**: Per-stock independent backtest only for phase 1. Each stock runs `UpTrendStructure.compute()` + `SignalEngine.generate()` in isolation. Portfolio-level composite backtest is deferred to a future phase.

- **Two-tier results**: The SSE stream emits per-stock summary data (including a downsampled OHLCV snapshot of ~100 bars plus signal points for the mini chart) as each stock completes. The full detail (equity curve, trade log, full OHLCV) is embedded in the final result event. The frontend renders summary rows incrementally; clicking a row expands the detail panel from already-received data with no additional API call.

- **Sector constituent caching**: Sector membership is stored in a new `sector_members` table inside the existing `market_data.db` SQLite database (same DB as the sentiment `market_sector` table). Cache TTL is 24 hours, since index constituent changes are infrequent (quarterly rebalancing). On cache miss, the system calls THS iwencai's "成分股" query via the existing `iwencai_paginate` session module.

- **OHLCV caching**: No new caching layer. The existing mootdx loader's `cached_loader_fetch` with parquet files is used as-is. The runner calls `loader.fetch([code], start_date, end_date)` and the cache layer transparently handles hits and misses.

- **Date range presets**: Four preset buttons (30, 60, 120, 250 trading days) computed relative to the selected trading day using the available trading dates list. A custom mode allows free start/end date selection.

- **Progress model**: Async background job with in-memory job store (matching the watch pool scan pattern). SSE events: `progress` (done/total/current_code), `stock_result` (per-stock summary), `result` (full payload), `done`, `error`.

- **No backtest result caching**: Backtest results are recomputed on every request. The OHLCV data is already cached in parquet, and the strategy computation is CPU-bound but fast per stock, so result caching would add complexity without meaningful latency improvement.

## Testing Decisions

- **Store tests**: Direct SQLite CRUD — insert via `upsert_sector_members`, read via `get_sector_members`, verify round-trip correctness. No mocking.

- **Service tests**: Mock store to verify cache-hit returns cached data without calling iwencai. Mock `iwencai_paginate` to verify cache-miss calls the API, parses the response, and upserts to store.

- **Runner tests**: `run_single_stock_backtest` is a pure function (takes DataFrame + detector + signal engine, returns dict). Test with crafted OHLCV fixtures: verify output dict shape, metric calculation correctness (win_rate, cumulative_return), edge cases (zero trades in flat market).

- **Routes tests**: FastAPI `TestClient` against the registered routes. Verify JSON response shapes, status codes, and SSE event stream format. Follows existing pattern from sentiment and watch pool route tests.

- **iwencai extension test**: Mock the HTTP layer, verify `query_sector_members` correctly parses iwencai's sparse-column response into `[{code, name}]`.

- **Frontend tests**: Mock `api.*` return values via vitest. Verify page renders trading day selector, sector type toggle, auto-selection of stocks, SSE event parsing, and detail panel expansion.

- **Existing gates**: No changes to purity/lookahead gates. No changes to order safety gates. The standard `ruff check` and `npm run build` must pass.

## Out of Scope

- Portfolio-level composite backtest (deferred to future phase)
- Strategies other than up-trend structure (extensible but not implemented now)
- Automated factor mining from strategy outputs (covered by the separate FactorMiner PRD)
- Modifying the up-trend structure strategy logic or parameters
- Real-time/live trading signals from strategy backtest results
- Export of backtest results to CSV/JSON
- Comparison view across multiple strategies for the same stock universe

## Further Notes

- The `sector_members` table shares the `market_data.db` database with the sentiment `market_sector` table because they are naturally related — sector aggregate data and sector membership both describe the same board entities. Queries that join them (e.g., "show me stocks from the top-N crowded sectors") are efficient within a single SQLite file.
- The mini K-line chart is intentionally simple: downsampled OHLCV bars with colored dots for entry/exit signals. Advanced annotations (support/resistance lines, pivot markers) are deferred.
- The runner's `run_single_stock_backtest` function is designed to be composable — a future portfolio backtest can call it for each stock, collect the per-stock signals, and feed them into a portfolio optimizer.
