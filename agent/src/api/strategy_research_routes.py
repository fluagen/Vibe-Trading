"""HTTP endpoints for strategy research — sector members + per-stock backtest.

SSE streaming implementation.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

from fastapi import FastAPI, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from src.api.sentiment_store import SentimentStore
from src.api.strategy_config_store import StrategyConfigStore
from src.api.strategy_research_runner import STRATEGY_MAP, run_backtest_blocking
from src.api.strategy_research_service import StrategyResearchService


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class SaveConfigRequest(BaseModel):
    strategy: str
    params: dict[str, Any]


class BacktestRequest(BaseModel):
    codes: list[str]
    start_date: str
    end_date: str
    strategy: str = "up_trend_structure"
    params: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# In-memory job store
# ---------------------------------------------------------------------------

_backtest_jobs: dict[str, dict[str, Any]] = {}
_backtest_lock = asyncio.Lock()


def _get_service() -> StrategyResearchService:
    return StrategyResearchService()


def _get_sentiment_store() -> SentimentStore:
    return SentimentStore()


def _get_config_store() -> StrategyConfigStore:
    return StrategyConfigStore()


# ---------------------------------------------------------------------------
# Route registration
# ---------------------------------------------------------------------------


def register_strategy_research_routes(app: FastAPI) -> None:
    """Mount all strategy-research routes onto the FastAPI app."""

    # -- strategies -----------------------------------------------------------

    @app.get("/strategy-research/strategies")
    async def list_strategies():
        return list(STRATEGY_MAP.keys())

    # -- strategy configs -----------------------------------------------------

    @app.get("/strategy-research/configs")
    async def get_config(strategy: str = Query(...)):
        """Return saved or default config for *strategy*."""
        store = _get_config_store()
        return store.get_config(strategy)

    @app.put("/strategy-research/configs")
    async def save_config(body: SaveConfigRequest):
        """Save parameter config for a strategy (upsert)."""
        store = _get_config_store()
        return store.save_config(body.strategy, body.params)

    @app.delete("/strategy-research/configs")
    async def delete_config(strategy: str = Query(...)):
        """Delete saved config, reverting to built-in defaults."""
        store = _get_config_store()
        return store.delete_config(strategy)

    # -- trading days ---------------------------------------------------------

    @app.get("/strategy-research/trading-days")
    async def trading_days(limit: int = Query(30, ge=1, le=250)):
        """Return available trading dates from sentiment market_total table."""
        svc = _get_service()
        return svc.get_available_trading_days(limit=limit)

    # -- sectors --------------------------------------------------------------

    @app.get("/strategy-research/sectors")
    async def list_sectors(
        type: str = Query("industry", regex="^(industry|concept)$"),
    ):
        """Return cached sector name/code list for autocomplete."""
        store = _get_sentiment_store()
        boards = store.get_board_list(type)
        return {"sectors": boards}

    # -- sector members -------------------------------------------------------

    @app.get("/strategy-research/sector-members/{bk_code:path}")
    async def sector_members(
        bk_code: str,
        sector_type: str = Query("industry", regex="^(industry|concept)$"),
    ):
        """Fetch sector constituent stocks — cache-first, iwencai fallback."""
        svc = _get_service()
        return svc.get_sector_members(
            bk_code=bk_code, bk_name=bk_code, sector_type=sector_type
        )

    # -- backtest -------------------------------------------------------------

    @app.post("/strategy-research/backtest")
    async def start_backtest(body: BacktestRequest):
        """Start a per-stock backtest job.  Returns a job_id for SSE streaming."""
        if not body.codes:
            return {"job_id": None, "error": "No stock codes provided"}

        job_id = str(uuid.uuid4())[:8]
        async with _backtest_lock:
            _backtest_jobs[job_id] = {
                "status": "queued",
                "strategy": body.strategy,
                "total_codes": len(body.codes),
                "done_codes": 0,
                "current_code": None,
                "result": None,
            }

        asyncio.create_task(
            _run_backtest_job(
                job_id,
                body.strategy,
                body.codes,
                body.start_date,
                body.end_date,
                body.params,
            )
        )
        return {"job_id": job_id}

    @app.get("/strategy-research/backtest/{job_id}")
    async def backtest_status(job_id: str):
        """Poll job status."""
        async with _backtest_lock:
            job = _backtest_jobs.get(job_id)
        if job is None:
            return {"error": "job not found"}
        return {
            "job_id": job_id,
            "status": job["status"],
            "strategy": job["strategy"],
            "total_codes": job["total_codes"],
            "done_codes": job["done_codes"],
            "current_code": job.get("current_code"),
        }

    @app.get("/strategy-research/backtest/{job_id}/stream")
    async def backtest_stream(job_id: str):
        """SSE stream emitting progress, stock_result, and done events."""

        async def event_generator():
            last_done = -1
            while True:
                async with _backtest_lock:
                    job = _backtest_jobs.get(job_id)
                if job is None:
                    yield f"event: error\ndata: {json.dumps({'error': 'job not found'})}\n\n"
                    return

                # Emit progress when done_codes advances.
                if job["done_codes"] > last_done:
                    last_done = job["done_codes"]
                    yield (
                        f"event: progress\ndata: {json.dumps({'done': last_done, 'total': job['total_codes'], 'current_code': job.get('current_code')})}\n\n"
                    )

                # Emit individual stock results as they arrive.
                pending = job.get("_pending_results", [])
                while pending:
                    item = pending.pop(0)
                    yield f"event: stock_result\ndata: {json.dumps(item)}\n\n"

                if job["status"] == "done":
                    if job.get("result"):
                        yield f"event: result\ndata: {json.dumps(job['result'])}\n\n"
                    yield f"event: done\ndata: {json.dumps({'status': 'done'})}\n\n"
                    return

                if job["status"] == "error":
                    yield f"event: error\ndata: {json.dumps({'error': job.get('error', 'unknown')})}\n\n"
                    return

                await asyncio.sleep(0.5)

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )


# ---------------------------------------------------------------------------
# Background job runner
# ---------------------------------------------------------------------------


async def _run_backtest_job(
    job_id: str,
    strategy: str,
    codes: list[str],
    start_date: str,
    end_date: str,
    params: dict[str, Any] | None = None,
) -> None:
    """Run the backtest in a background thread, streaming results via SSE."""
    async with _backtest_lock:
        job = _backtest_jobs.get(job_id)
        if job:
            job["status"] = "running"
            job["_pending_results"] = []

    def on_progress(done: int, total: int, code: str) -> None:
        job = _backtest_jobs.get(job_id)
        if job:
            job["done_codes"] = done
            job["current_code"] = code

    def on_stock_result(done: int, summary: dict[str, Any]) -> None:
        job = _backtest_jobs.get(job_id)
        if job:
            pending = job.setdefault("_pending_results", [])
            pending.append({"done": done, "summary": summary})

    try:
        result = await asyncio.to_thread(
            run_backtest_blocking,
            job_id,
            codes,
            start_date,
            end_date,
            strategy,
            on_progress,
            on_stock_result,
            params,
        )
        async with _backtest_lock:
            job = _backtest_jobs.get(job_id)
            if job:
                job["status"] = "done"
                job["result"] = result
    except Exception as exc:
        async with _backtest_lock:
            job = _backtest_jobs.get(job_id)
            if job:
                job["status"] = "error"
                job["error"] = str(exc)
