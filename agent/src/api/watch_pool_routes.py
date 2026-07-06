"""HTTP endpoints for opportunity pool — candidate pool, scan, watchlist CRUD.

SSE streaming follows alpha_routes.py pattern.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

from fastapi import FastAPI, Query, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from src.api.watch_pool_runner import run_scan_blocking
from src.api.watch_pool_service import load_default_pool
from src.api.watch_pool_store import WatchPoolStore


class AddCandidatesRequest(BaseModel):
    codes: list[str]
    names: list[str]
    markets: list[str]


class ScanRequest(BaseModel):
    strategy: str = "up_trend_structure"
    target_date: str | None = None
    codes: list[str] | None = None


class BatchDeleteRequest(BaseModel):
    codes: list[str]


class AddToWatchlistRequest(BaseModel):
    code: str
    name: str = ""
    state_at_add: str
    position_at_add: float
    scan_job_id: str = ""


# In-memory job store (matches alpha_routes pattern)
_scan_jobs: dict[str, dict[str, Any]] = {}
_scan_lock = asyncio.Lock()


def _get_store() -> WatchPoolStore:
    return WatchPoolStore()


def register_watch_pool_routes(app: FastAPI) -> None:
    """Mount all opportunity-pool routes onto the FastAPI app."""

    _get_store().ensure_tables()

    # -- strategies -----------------------------------------------------------

    @app.get("/opportunity-pool/strategies")
    async def list_strategies():
        return ["up_trend_structure"]

    # -- candidates -----------------------------------------------------------

    @app.get("/opportunity-pool/candidates")
    async def list_candidates():
        return _get_store().list_candidates()

    @app.post("/opportunity-pool/candidates")
    async def add_candidates(body: AddCandidatesRequest):
        store = _get_store()
        items: list[dict[str, Any]] = []
        for i, code in enumerate(body.codes):
            items.append({
                "code": code,
                "name": body.names[i] if i < len(body.names) else code,
                "market": body.markets[i] if i < len(body.markets) else _guess_market(code),
                "source": "manual",
            })
        return {"added": store.add_candidates(items)}

    @app.post("/opportunity-pool/candidates/batch-delete")
    async def batch_remove_candidates(req: BatchDeleteRequest):
        store = _get_store()
        removed = 0
        for code in req.codes:
            if store.remove_candidate(code):
                removed += 1
        return {"removed": removed}

    @app.delete("/opportunity-pool/candidates/{code:path}")
    async def remove_candidate(code: str):
        return {"removed": _get_store().remove_candidate(code)}

    @app.get("/opportunity-pool/candidates/default")
    async def load_default_candidates():
        return load_default_pool(_get_store())

    @app.get("/opportunity-pool/resolve")
    async def resolve_code(code: str = Query(..., description="6-digit code e.g. 600519")):
        """Resolve a 6-digit code to full suffixed code + name via mootdx."""
        code = code.strip()
        try:
            from mootdx.quotes import Quotes
            client = Quotes.factory(market="std")
            for m in [0, 1]:
                df = client.stocks(market=m)
                if df is not None and not df.empty:
                    match = df[df["code"].astype(str).str.zfill(6) == code.zfill(6)]
                    if not match.empty:
                        row = match.iloc[0]
                        raw_code = str(row["code"]).zfill(6)
                        market = int(row.get("market", m))
                        suffix = "SH" if market == 1 or raw_code.startswith(("6", "5")) else "SZ"
                        return {
                            "code": f"{raw_code}.{suffix}",
                            "name": str(row.get("name", raw_code)),
                            "market": suffix,
                        }
            return {"error": f"Code {code} not found"}
        except ImportError:
            return {"error": "mootdx not installed"}
        except Exception as exc:
            return {"error": str(exc)}

    @app.post("/opportunity-pool/candidates/import")
    async def import_candidates(file: UploadFile = File(...)):
        store = _get_store()
        content = (await file.read()).decode("utf-8", errors="ignore")
        lines = [l.strip() for l in content.splitlines() if l.strip()]

        valid: list[dict[str, Any]] = []
        invalid: list[str] = []
        seen = {c["code"] for c in store.list_candidates()}

        for line in lines:
            code = line.split(",")[0].strip().strip('"')
            if not code:
                continue
            # Normalize: add suffix if bare code
            if "." not in code:
                code = code.strip()
                if code.startswith(("6", "5")):
                    code = f"{code}.SH"
                elif code.startswith(("0", "3", "2")):
                    code = f"{code}.SZ"
                else:
                    invalid.append(line)
                    continue

            if code in seen:
                continue

            valid.append({
                "code": code,
                "name": code,
                "market": _guess_market(code),
                "source": "import",
            })
            seen.add(code)

        if valid:
            store.add_candidates(valid)

        return {"added": len(valid), "invalid": len(invalid), "skipped_duplicates": len(lines) - len(valid) - len(invalid)}

    # -- watchlist ------------------------------------------------------------

    @app.get("/opportunity-pool/watchlist")
    async def list_watchlist():
        return _get_store().list_watchlist()

    @app.post("/opportunity-pool/watchlist")
    async def add_to_watchlist(body: AddToWatchlistRequest):
        _get_store().add_to_watchlist(
            code=body.code,
            name=body.name or body.code,
            strategy_name="up_trend_structure",
            state_at_add=body.state_at_add,
            position_at_add=body.position_at_add,
            scan_job_id=body.scan_job_id,
        )
        return {"added": True}

    @app.delete("/opportunity-pool/watchlist/{code:path}")
    async def remove_from_watchlist(code: str):
        return {"removed": _get_store().remove_from_watchlist(code)}

    @app.post("/opportunity-pool/watchlist/refresh-all")
    async def refresh_all_signals():
        store = _get_store()
        items = store.list_watchlist()
        if not items:
            return {"job_id": None, "error": "Watchlist is empty"}

        codes = [item["code"] for item in items]
        job_id = str(uuid.uuid4())[:8]
        async with _scan_lock:
            _scan_jobs[job_id] = {
                "status": "queued",
                "strategy": "up_trend_structure",
                "total_codes": len(codes),
                "done_codes": 0,
                "current_code": None,
                "result": None,
            }

        async def _refresh_job():
            async with _scan_lock:
                _scan_jobs[job_id]["status"] = "running"

            def on_progress(done: int, total: int, code: str):
                job = _scan_jobs.get(job_id)
                if job:
                    job["done_codes"] = done
                    job["current_code"] = code

            try:
                result = await asyncio.to_thread(
                    run_scan_blocking, job_id, "up_trend_structure", codes, on_progress
                )
                # Update watchlist with refreshed signals
                s = _get_store()
                for code, data in result.items():
                    s.update_current_signal(code, data["state"], data["position_signal"])

                async with _scan_lock:
                    job = _scan_jobs.get(job_id)
                    if job:
                        job["status"] = "done"
                        job["result"] = result
            except Exception as exc:
                async with _scan_lock:
                    job = _scan_jobs.get(job_id)
                    if job:
                        job["status"] = "error"
                        job["error"] = str(exc)

        asyncio.create_task(_refresh_job())
        return {"job_id": job_id}

    # -- scan ----------------------------------------------------------------

    @app.post("/opportunity-pool/scan")
    async def start_scan(body: ScanRequest):
        store = _get_store()
        if body.codes:
            codes = body.codes
        else:
            candidates = store.list_candidates()
            codes = [c["code"] for c in candidates]

        if not codes:
            return {"job_id": None, "error": "Candidate pool is empty"}

        job_id = str(uuid.uuid4())[:8]
        async with _scan_lock:
            _scan_jobs[job_id] = {
                "status": "queued",
                "strategy": body.strategy,
                "total_codes": len(codes),
                "done_codes": 0,
                "current_code": None,
                "result": None,
            }

        asyncio.create_task(_run_scan_job(job_id, body.strategy, codes, body.target_date))
        return {"job_id": job_id}

    @app.get("/opportunity-pool/scan/{job_id}/stream")
    async def scan_stream(job_id: str):
        async def event_generator():
            last_done = -1
            while True:
                async with _scan_lock:
                    job = _scan_jobs.get(job_id)
                if job is None:
                    yield f"event: error\ndata: {json.dumps({'error': 'job not found'})}\n\n"
                    return

                if job["done_codes"] > last_done:
                    last_done = job["done_codes"]
                    yield f"event: progress\ndata: {json.dumps({'done': last_done, 'total': job['total_codes'], 'current_code': job.get('current_code')})}\n\n"

                if job["status"] == "done":
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

    @app.get("/opportunity-pool/scan/{job_id}")
    async def scan_status(job_id: str):
        async with _scan_lock:
            job = _scan_jobs.get(job_id)
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


async def _run_scan_job(job_id: str, strategy: str, codes: list[str], target_date: str | None = None):
    async with _scan_lock:
        _scan_jobs[job_id]["status"] = "running"

    def on_progress(done: int, total: int, code: str):
        job = _scan_jobs.get(job_id)
        if job:
            job["done_codes"] = done
            job["current_code"] = code

    try:
        result = await asyncio.to_thread(
            run_scan_blocking, job_id, strategy, codes, on_progress,
            "2026-01-01", target_date
        )
        async with _scan_lock:
            job = _scan_jobs.get(job_id)
            if job:
                job["status"] = "done"
                job["result"] = result
    except Exception as exc:
        async with _scan_lock:
            job = _scan_jobs.get(job_id)
            if job:
                job["status"] = "error"
                job["error"] = str(exc)


def _guess_market(code: str) -> str:
    if code.upper().endswith(".SH"):
        return "SH"
    if code.upper().endswith(".SZ"):
        return "SZ"
    if code.upper().endswith(".BJ"):
        return "BJ"
    return "UNKNOWN"
