"""Market Sentiment HTTP routes for the Web UI.

Mounted by ``agent/api_server.py`` via ``register_sentiment_routes(app)``.

数据源: THS iwencai OpenAPI → SQLite 缓存
所有查询从缓存库读取，采集通过 POST /sentiment/collect 手动触发。
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from fastapi import Depends, FastAPI, Query, Request

from .sentiment_service import SentimentService

logger = logging.getLogger(__name__)

_service = SentimentService()

_VALID_BOARD_TYPES = ("industry", "concept")
_MAX_DAYS = 60
_DEFAULT_DAYS = 20


def _error(message: str) -> dict[str, Any]:
    return {"ok": False, "error": message}


# ---------------------------------------------------------------------------
# Route registration
# ---------------------------------------------------------------------------


def register_sentiment_routes(
    app: FastAPI,
    require_local: Any = None,
) -> None:
    """Mount the market sentiment routes onto ``app``.

    Args:
        app: The host FastAPI app.
        require_local: FastAPI dependency for local-or-auth gating.
            Resolved from api_server module if not provided.
    """
    if require_local is None:
        import sys as _sys

        host = _sys.modules.get("api_server") or _sys.modules.get("agent.api_server")
        if host is not None:
            require_local = getattr(host, "require_local_or_auth", None)

    deps = [Depends(require_local)] if require_local else []

    # ---------------------------------------------------------------
    # POST /sentiment/collect — 手动触发采集
    # ---------------------------------------------------------------

    @app.post("/sentiment/collect", dependencies=deps)
    async def collect_data(
        request: Request,
        date: str | None = Query(None, description="交易日 YYYY-MM-DD，默认最新"),
    ) -> dict[str, Any]:
        """从 THS iwencai 拉取全市场 + 板块数据，写入 SQLite 缓存。

        同步阻塞，超时取决于板块数量（行业 ~90 + 概念 ~400）。
        """
        if date:
            try:
                datetime.strptime(date, "%Y-%m-%d")
            except ValueError:
                return _error("date must be YYYY-MM-DD format")

        return _service.collect(trade_date=date)

    # ---------------------------------------------------------------
    # DELETE /sentiment/collect — 删除指定日期缓存
    # ---------------------------------------------------------------

    @app.delete("/sentiment/collect", dependencies=deps)
    async def delete_collect_data(
        request: Request,
        date: str = Query(..., description="交易日 YYYY-MM-DD"),
    ) -> dict[str, Any]:
        """删除指定日期的全市场 + 板块缓存数据。"""
        try:
            datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            return _error("date must be YYYY-MM-DD format")
        return _service.delete_collect(trade_date=date)

    # ---------------------------------------------------------------
    # GET /sentiment/collect/status — 采集状态
    # ---------------------------------------------------------------

    @app.get("/sentiment/collect/status", dependencies=deps)
    async def collect_status(request: Request) -> dict[str, Any]:
        """最近一次采集状态。"""
        return _service.get_collect_status()

    # ---------------------------------------------------------------
    # GET /sentiment/boards — 板块列表 (autocomplete)
    # ---------------------------------------------------------------

    @app.get("/sentiment/boards", dependencies=deps)
    async def list_boards(
        request: Request,
        board_type: str = Query("industry", description="'industry' or 'concept'"),
    ) -> dict[str, Any]:
        """板块名称+代码列表（SQLite 去重）。"""
        if board_type not in _VALID_BOARD_TYPES:
            return _error(f"board_type must be one of {list(_VALID_BOARD_TYPES)}")
        return _service.get_boards(board_type)

    # ---------------------------------------------------------------
    # GET /sentiment/overview
    # ---------------------------------------------------------------

    @app.get("/sentiment/overview", dependencies=deps)
    async def sentiment_overview(
        request: Request,
        board_type: str = Query("industry", description="'industry' or 'concept'"),
        top_n: int = Query(20, ge=1, le=1000),
        date: str | None = Query(None, description="交易日 YYYY-MM-DD，默认最新"),
    ) -> dict[str, Any]:
        """全市场成交额 + 板块拥挤度排名 + 资金偏好。

        拥挤度比率和资金偏好均从 SQLite 原始数据动态计算。
        """
        if board_type not in _VALID_BOARD_TYPES:
            return _error(f"board_type must be one of {list(_VALID_BOARD_TYPES)}")

        if date:
            try:
                datetime.strptime(date, "%Y-%m-%d")
            except ValueError:
                return _error("date must be YYYY-MM-DD format")

        return _service.get_overview(board_type=board_type, top_n=top_n, trade_date=date)

    # ---------------------------------------------------------------
    # GET /sentiment/sector-detail
    # ---------------------------------------------------------------

    @app.get("/sentiment/sector-detail", dependencies=deps)
    async def sentiment_sector_detail(
        request: Request,
        board_code: str = Query(..., min_length=1),
        days: int = Query(_DEFAULT_DAYS, ge=1, le=_MAX_DAYS),
        board_type: str = Query("industry"),
    ) -> dict[str, Any]:
        """单板块拥挤度趋势 + 资金流向历史。"""
        return _service.get_sector_detail(board_code=board_code, board_type=board_type, days=days)

    # ---------------------------------------------------------------
    # GET /sentiment/history
    # ---------------------------------------------------------------

    @app.get("/sentiment/history", dependencies=deps)
    async def sentiment_history(
        request: Request,
        board_code: str = Query(..., min_length=1),
        start_date: str = Query(...),
        end_date: str = Query(...),
        board_type: str = Query("industry"),
    ) -> dict[str, Any]:
        """日期范围板块历史（拥挤度 + 资金流向）。"""
        try:
            s = datetime.strptime(start_date, "%Y-%m-%d")
            e = datetime.strptime(end_date, "%Y-%m-%d")
        except ValueError:
            return _error("Dates must be in YYYY-MM-DD format")

        if s > e:
            return _error("start_date must be before or equal to end_date")
        if (e - s).days > _MAX_DAYS:
            return _error(f"Date range must be at most {_MAX_DAYS} days")

        return _service.get_history(
            board_code=board_code,
            board_type=board_type,
            start_date=start_date,
            end_date=end_date,
        )
