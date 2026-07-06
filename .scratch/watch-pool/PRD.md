# PRD: 机会池 (Opportunity Pool)

Status: ready-for-agent

## Problem Statement

用户希望在交易前有一个系统化的"选股观察"环节：用交易策略（目前是 up_trend_structure 形态策略）对候选股票池进行批量扫描，从扫描结果中挑选符合自己判断的标的，加入一个可跟踪的观察列表。加入时需要保留当时的信号快照（形态状态、仓位信号、日期），后续可以手动刷新查看信号变化。当前系统没有这个能力——策略只能通过 Agent 对话做单只回测，无法批量扫描，也没有持久化的观察列表。

## Solution

在前端新增"机会池"栏目。用户先维护一个候选股票池（内置沪深300+中证500成分股，可增删、可导入），选择交易策略触发批量扫描（后端直接执行 Python 策略引擎，不经过 LLM），扫描进度通过 SSE 实时推送。用户在扫描结果中挑选标的加入观察列表，系统冻结加入时的信号快照。后续支持手动刷新，更新当前信号但保留历史快照。LLM 分析能力预留接口，初版不做。

## User Stories

1. As a trader, I want to load a default candidate pool (CSI 300 + CSI 500) from the system, so that I have a reasonable starting universe without manually entering hundreds of stock codes.
2. As a trader, I want to add individual stock codes to my candidate pool, so that I can include stocks I'm personally interested in beyond the default indices.
3. As a trader, I want to remove stocks from my candidate pool, so that I can exclude stocks I'm not interested in.
4. As a trader, I want to import a list of stock codes from a CSV or text file, so that I can quickly set up a custom candidate pool from external research.
5. As a trader, I want to select a trading strategy (starting with up_trend_structure) and trigger a batch scan against my candidate pool, so that I can discover which stocks currently match the strategy's entry criteria.
6. As a trader, I want to see real-time scan progress (how many stocks processed, which stock is currently being analyzed), so that I know how long the scan will take and that it's still working.
7. As a trader, I want to see scan results in a sortable table (code, name, structure state, position signal), so that I can quickly identify the most promising candidates.
8. As a trader, I want to select specific stocks from scan results and add them to my watchlist, so that I can build a curated list for ongoing monitoring.
9. As a trader, I want the system to freeze the signal snapshot (state, position signal, date) at the moment I add a stock to the watchlist, so that I have a permanent record of why I added it.
10. As a trader, I want to view my watchlist with both the frozen "added-at" snapshot and the current signal side by side, so that I can see how the signal has evolved since I added the stock.
11. As a trader, I want to manually trigger a "refresh all signals" action on my watchlist, so that I can update all current signals to the latest market data without re-adding stocks.
12. As a trader, I want to remove stocks from my watchlist, so that my list stays clean and focused.
13. As a trader, I want the watchlist data to persist across browser sessions and server restarts, so that I don't lose my curated list.
14. As a developer, I want new trading strategies to be registrable via a strategy map without changing routes or store code, so that adding a second strategy later requires minimal effort.

## Implementation Decisions

### Architecture

- Three-layer backend pattern following existing `sentiment_routes/service/store`: `watch_pool_routes.py` → `watch_pool_service.py` → `watch_pool_store.py`
- SSE job streaming pattern following existing `alpha_routes.py`: in-memory job store, `_job_event_stream` helper, heartbeat + progress events
- Scan runner (`watch_pool_runner.py`) calls `UpTrendStructure.compute()` and `SignalEngine.generate()` directly — no LLM in the scan pipeline
- `ThreadPoolExecutor(max_workers=10)` for parallel stock data fetching via existing `fetch_market_data()`

### Strategy Registration

A `STRATEGY_MAP` dict maps strategy names to detector/signal-engine module+class paths. Initially contains only `up_trend_structure`. Designed as a dict so new strategies are a single-entry addition.

### Candidate Pool

Default pool loaded via mootdx (通达信), fetching CSI 300 + CSI 500 constituent lists. Stored in SQLite. Supports manual add/remove and file import (CSV).

### SQLite Schema

Three tables in `agent/data/watch_pool.db`:
- `candidate_pool`: code (PK), name, market, source, added_at
- `watchlist`: (code, strategy_name) composite PK, name, state_at_add, position_at_add, score_at_add (reserved), score_details (reserved, JSON), added_at, scan_job_id, current_state, current_position, current_score (reserved), current_updated, notes, tags (reserved, JSON array), ai_analysis (reserved, JSON)
- `scan_jobs`: job_id (PK), status, strategy, total_codes, done_codes, current_code, created_at, finished_at, error, result (JSON)

All date/timestamp fields use ISO 8601 format.

### Signal Snapshot

A signal snapshot captures at minimum: `state` (enum: no_structure/forming/up_phase/pullback/breakdown), `position_signal` (float: 0/0.33/0.67/1.0/-1.0), `date` (trade date YYYY-MM-DD), `strategy` (strategy name). Reserved fields `score_at_add` and `score_details` for future continuous scoring.

### API Endpoints

```
GET    /opportunity-pool/candidates           List candidate pool
POST   /opportunity-pool/candidates           Add codes to pool
DELETE /opportunity-pool/candidates/{code}    Remove from pool
POST   /opportunity-pool/candidates/import    Import from file
GET    /opportunity-pool/candidates/default   Load default pool (CSI 300+500)

POST   /opportunity-pool/scan                 Start scan, returns {job_id}
GET    /opportunity-pool/scan/{job_id}/stream SSE progress stream
GET    /opportunity-pool/scan/{job_id}        Poll job status

GET    /opportunity-pool/watchlist            List watched stocks
POST   /opportunity-pool/watchlist            Add to watchlist (freezes snapshot)
DELETE /opportunity-pool/watchlist/{code}     Remove from watchlist
POST   /opportunity-pool/watchlist/refresh-all Refresh all signals (SSE)

GET    /opportunity-pool/strategies           List available strategies
```

### Frontend

- Route: `/opportunity-pool`, lazy-loaded page component
- Navigation: sidebar entry with icon (lucide-react `Crosshair`), label via i18n key `layout.opportunityPool`
- Two tabs: "Scan Center" (候选扫描) and "My Watchlist" (我的观察)
- Zustand store (`stores/opportunityPool.ts`) for watchlist items, scan state, candidate pool
- SSE-connected ScanProgress component for real-time scan feedback
- SignalBadge component: color-coded badge rendering state + position signal
- LLM analysis column reserved in UI but hidden until backend support is added

### LLM Integration (Deferred)

Reserved `ai_analysis` field on watchlist items and API responses. Three identified use cases for future: scan result aggregation analysis, per-stock deep dive, signal change interpretation. Not implemented in v1.

## Testing Decisions

- **Strategy correctness**: Reuse existing `test_up_trend_structure.py` and `test_structure_signal_engine.py` — must continue passing
- **Store layer**: New `test_watch_pool_store.py` — test CRUD against in-memory SQLite, following `SentimentStore` test patterns
- **Runner**: New `test_watch_pool_runner.py` — test with synthetic OHLCV DataFrames, verify correct delegation to `UpTrendStructure` + `SignalEngine`
- **API integration**: FastAPI `TestClient` — test endpoint contracts (status codes, response shapes), mock `fetch_market_data` and `mootdx`
- **Frontend build**: `npm run build` must pass; `npm run test:run` (197 existing tests) must not regress
- **External data sources (mootdx, Tencent API)**: Not tested directly — mocked in all test seams
- **E2E user flow**: Manual verification for v1; automated browser test deferred

## Out of Scope

- LLM-powered scan result analysis or per-stock interpretation
- Strategy parameter configuration UI (parameters use hardcoded defaults)
- Automatic scheduled scans (e.g., daily at market close)
- Alert/notification when watchlist stock signal changes
- Multi-strategy simultaneous scanning
- Watchlist export to CSV/JSON
- Cross-device or team-shared watchlists

## Further Notes

- The `up_trend_structure` skill already has a CLI scanning tool (`screen_bottom_k.py`) that demonstrates the full-A-share scanning pattern. The runner adapts this to an API-callable form scoped to the candidate pool.
- The sentiment module (`sentiment_routes/service/store`) is the closest architectural analog and should be referenced during implementation.
- The `score_at_add` and `score_details` columns are nullable — they exist to avoid a schema migration when continuous scoring is added later.
- All i18n keys should be added to both `en.json` and `zh-CN.json` under an `opportunityPool` namespace.
