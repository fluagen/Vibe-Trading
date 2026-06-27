# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Runtime Environment Constraint
### Python Constraint


### Activate existing environment
```bash
conda activate vibe-trading
```

### If the environment does not exist, run this creation command first
```bash
conda create -n vibe-trading python=3.12
conda activate vibe-trading
# After creating env, install dependencies inside this environment
pip install -e ".[dev]"
```

### Rules must follow
1. Before running any Python, pytest, py_compile, vibe-trading series commands: verify `vibe-trading` conda env is active.
2. If env missing or inactive: halt all Python execution, output full environment setup instructions to user instead of running code.
3. All pip install, lint, test, server startup operations must be executed under `vibe-trading`.
4. Frontend npm commands and docker compose are exempt from this conda env restriction.


## Commands

### Python (backend)

```bash
# Install in editable mode with dev deps
pip install -e ".[dev]"

# Run all safe tests (skip live E2E)
pytest --ignore=agent/tests/e2e_backtest --ignore=agent/tests/test_e2e_harness_v2.py --tb=short -q

# Run a specific test file or subset
pytest agent/tests/test_backtest_runner_security.py -q
pytest -m unit                       # unit tests only (fast, no network)
pytest -m integration                # integration tests (may need network)

# Factor-zoo purity/lookahead gates
pytest agent/tests/factors/test_alpha_purity.py agent/tests/factors/test_lookahead.py -q

# Live/order safety tests
pytest agent/tests/test_sdk_order_gate.py agent/tests/test_mandate_enforcement.py agent/tests/test_killswitch_blocks_orders.py -q

# Compile-check critical entry points
python -m py_compile agent/api_server.py agent/mcp_server.py
python -m compileall -q agent/cli

# Lint (ruff config in pyproject.toml)
ruff check agent/

# Live E2E tests (requires VIBE_TRADING_RUN_LIVE_E2E=1 env var and real LLM key)
VIBE_TRADING_RUN_LIVE_E2E=1 pytest agent/tests/test_e2e_harness_v2.py
```

### Frontend (React + Vite)

```bash
cd frontend
npm ci && npm run build        # install + type-check + production build
npm run dev                    # dev server on localhost:5899
npm run test:run               # vitest (197 tests)
npm run test:coverage          # with coverage
```

### Running the app

```bash
vibe-trading                   # interactive CLI/TUI
vibe-trading run -p "..."      # single research run
vibe-trading serve --port 8899 # FastAPI server (serves built frontend from frontend/dist)
vibe-trading-mcp               # MCP server (stdio; --transport sse for web)

# Docker
docker compose up --build      # backend on 127.0.0.1:8899
```

## Architecture

### Package layout

All backend code lives under `agent/`. Entry points are defined in `pyproject.toml`:

| Command | Source |
|---------|--------|
| `vibe-trading` | `agent/cli/main.py` (package at `agent/cli/`) |
| `vibe-trading-mcp` | `agent/mcp_server.py` |
| `vibe-trading serve` | `agent/api_server.py` (FastAPI) |

`pyproject.toml` `[tool.setuptools.package-dir]` maps `"" = "agent"`, so imports like `from src.agent.loop import AgentLoop` work from anywhere inside `agent/`.

### Core agent loop (`agent/src/agent/`)

The ReAct agent loop (`loop.py`) drives the main research workflow: it manages the LLM conversation, dispatches tool calls, and applies five-layer context compression (microcompact → context_collapse → auto_compact → explicit compact tool → iterative update). Tools are registered in `ToolRegistry` (`tools.py`), which builds OpenAI-format function schemas. `context.py` builds the system prompt from skills, memory, goals, and tool definitions. `trace.py` writes per-run JSONL traces.

### Tools (`agent/src/tools/`)

~54 tools exposed to the agent. `BaseTool` (in `agent/src/agent/tools.py`) defines the interface: `name`, `description`, `parameters` (JSON Schema), `is_readonly`, and `execute(**kwargs) -> str`. Tools are auto-discovered by `ToolRegistry.discover()`. Read-only tools can be batched; write tools run sequentially. Key categories:

- **Market data**: `market_data_tool.py` (unified OHLCV via loader registry), plus 18 read-only tools for fund flow, dragon-tiger, northbound, margin, block trades, SEC filings, financials, options chains, screening, etc.
- **Backtest**: `backtest_tool.py` (strategy generation + execution)
- **Swarm**: `swarm_tool.py` (multi-agent orchestration)
- **Trading**: `trading_connector_tool.py` (connector-scoped read-only access; order tools require an explicit mandate)
- **Shadow Account**: `shadow_account_tool.py` (journal → behavior → shadow strategy → report)
- **File/Doc**: `doc_reader_tool.py`, `web_reader_tool.py`, `web_search_tool.py`, `read_file_tool.py`, `write_file_tool.py`, `edit_file_tool.py`
- **Alpha Zoo**: `alpha_zoo_tool.py`, `alpha_bench_tool.py`, `alpha_compare_tool.py`
- **Research**: `factor_analysis_tool.py`, `pattern_tool.py`, `goal_tool.py`, `hypothesis_tool.py`

Shell-capable tools (`bash_tool.py`) are gated behind `VIBE_TRADING_ENABLE_SHELL_TOOLS=1` and never exposed remotely by default.

### Backtest system (`agent/backtest/`)

Multi-market backtesting with per-market simulation engines:

- **Engines** (`engines/`): `china_a.py` (A-shares), `global_equity.py` (US/HK), `crypto.py`, `china_futures.py`, `global_futures.py`, `forex.py`, `options_portfolio.py`, `composite.py` (cross-market with shared capital pool)
- **Loaders** (`loaders/`): 18 data sources with a `@register` decorator pattern. Each loader implements `name`, `markets`, `is_available()`, `fetch(codes, start_date, end_date)`. The `registry.py` manages fallback chains ordered by IP-ban risk (free/no-auth sources first, throttled/key-gated last).
- **Runner** (`runner.py`): executes generated strategy code in a subprocess, collects artifacts (equity curve, metrics, trade log), validates with `validation.py`
- **Benchmark** (`benchmark.py`): yfinance-backed benchmark comparison
- **Optimizers** (`optimizers/`): Monte Carlo, Bootstrap CI, Walk-Forward

### Skills (`agent/src/skills/`)

79 finance skills across 8 categories. Each skill is a directory with a `SKILL.md` (Markdown prompt loaded into the agent context). Skills are the primary mechanism for giving the agent domain knowledge — the system prompt loads relevant skills based on the user's request. Managed by `agent/src/agent/skills.py`.

### Memory & sessions (`agent/src/memory/`, `agent/src/session/`)

Persistent cross-session memory stored as JSONL files with CJK-aware slug generation. `session/search.py` provides FTS5 full-text search across all sessions. Sessions are stored as JSONL message logs in `agent/sessions/`.

### Swarm (`agent/src/swarm/`)

29 preset multi-agent teams. Presets are YAML files in `presets/` defining worker DAGs. The swarm runtime launches worker agents (each gets a subset of tools), manages DAG dependencies, and streams live status via SSE. Swarm workers now get a local `get_market_data` tool backed by the same loader registry.

### Trading & broker connectors (`agent/src/trading/`, `agent/src/live/`)

Connector-first architecture: each broker is a profile selectable via `vibe-trading connector use <name>`. Connectors live in `connectors/` (ibkr, robinhood, tiger, longbridge, alpaca, okx, binance, futu, dhan, shoonya). Each exposes read-only account/positions/orders/quote/history plus optional paper-trading order placement.

Live/order safety in `src/live/` follows a mandate-gated, kill-switch-aware model:
- **Mandate**: user-committed symbol universe, order size, exposure, leverage, daily cap
- **Order guard** (`order_guard.py`): pre-trade validation against mandate
- **Halt** (`halt.py`): filesystem-based instant kill switch
- **Audit** (`audit.py`): full ledger of all trading actions

### Alpha Zoo (`agent/src/factors/`)

456 pre-built quant alphas across 4 zoos (qlib158, alpha101, gtja191, academic). Each alpha is a single `.py` file with `__alpha_meta__` (pydantic-validated metadata) and a pure `compute(panel)` function. Purity enforced by AST scan (`test_alpha_purity.py`) — only `pandas`, `numpy`, `scipy`, `src.factors.base` allowed. Lookahead banned by `test_lookahead.py`.

### API server (`agent/api_server.py`)

FastAPI monolith serving REST + SSE. Key route modules in `src/api/alpha_routes.py`. Serves the built frontend from `frontend/dist` as static files in production. Security: CORS hardened, `API_AUTH_KEY` required for non-loopback clients, path-traversal protections on file reads.

### MCP server (`agent/mcp_server.py`)

Exposes 54 read-only/research-only tools via MCP (stdio or SSE transport). No order-placing tools are ever surfaced via MCP. Compatible with Claude Desktop, OpenClaw, Cursor, etc.

### Frontend (`frontend/src/`)

React 19 + Vite + Tailwind CSS + Zustand + ECharts + i18next. Lazy-loaded routes (`router.tsx`) reduce initial bundle. Key pages in `pages/`, shared components in `components/`, state in `stores/`, i18n translations in `i18n/`. The dev server proxies API calls to `VITE_API_URL` (defaults to `localhost:8899`).

### Environment & config

Copy `agent/.env.example` to `agent/.env`. Provider config uses `LANGCHAIN_PROVIDER`, `<PROVIDER>_API_KEY`, `<PROVIDER>_BASE_URL`, `LANGCHAIN_MODEL_NAME`. Optional: `TUSHARE_TOKEN`, `API_AUTH_KEY`, `VIBE_TRADING_ENABLE_SHELL_TOOLS`, `VIBE_TRADING_ENABLE_SCHEDULER`, `VIBE_TRADING_DATA_CACHE`.

External MCP servers for the agent to call are configured in `~/.vibe-trading/agent.json` (not `agent/.env`).

## Important conventions

- **DCO required**: all community PR commits must carry `Signed-off-by:` (`git commit -s`). No CLA.
- **Code style**: black formatting, ruff linting (E/F/W rules, line-length 120), Google-style docstrings, type annotations on public signatures.
- **File size**: keep files under 400 lines where practical, 800 hard cap.
- **Paths**: no hardcoded paths — use `agent/uploads`, `agent/runs`, `~/.vibe-trading/` or env-configurable roots.
- **Secrets**: never commit `.env` files, token caches, broker credentials. Treat secrets as access, not text.
- **Order safety changes**: require explicit maintainer approval. Must remain mandate-gated, kill-switch-aware, fail-closed, and audit-logged.
- **Factor zoo contributions**: must pass purity gate, lookahead gate, and include `__alpha_meta__`. See `CONTRIBUTING.md` for the full reviewer checklist.
- **No AI-attribution trailers**: do not add `Co-Authored-By:` or similar to commits.
- **Live trading** is experimental/opt-in only — never test broker-write flows during routine PR validation.
