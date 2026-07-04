"""Read-only sector-level aggregate flow tool — backed by SQLite cache.

Uses the SentimentStore (THS iwencai → SQLite) instead of calling Eastmoney
directly. Data must be collected via POST /sentiment/collect before use.

Use this tool together with ``get_market_data`` (for total-market turnover via
``000001.SH`` + ``399001.SZ``) to compute the sector crowding ratio.

Markets: A-share industry boards (行业板块) and concept boards (概念板块).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from src.agent.tools import BaseTool
from src.api.sentiment_store import SentimentStore

logger = logging.getLogger(__name__)

# Defensive caps so a payload can never blow up the LLM context.
_MAX_LIMIT = 100
_DEFAULT_LIMIT = 30
_VALID_BOARD_TYPES = ("industry", "concept")
_VALID_SORT_BY = ("change_pct", "amount", "net_inflow")


def _error(message: str) -> str:
    return json.dumps({"ok": False, "error": message}, ensure_ascii=False)


def _fetch_from_store(board_type: str, sort_by: str, limit: int) -> str:
    """Read board-level aggregate flow data from the SQLite cache."""
    store = SentimentStore()
    store.ensure_tables()

    latest_date = store.get_latest_trading_day()
    if not latest_date:
        return _error("暂无缓存数据。请先通过 POST /sentiment/collect 采集数据。")

    rows = store.get_sectors(latest_date, board_type, order_by=sort_by, limit=limit)

    if not rows:
        return _error(
            f"{latest_date} 无 {board_type} 板块缓存数据。请先采集该日数据。"
        )

    boards = [
        {
            "board_code": r["bk_code"],
            "board_name": r["bk_name"],
            "change_pct": r.get("change_pct"),
            "turnover": r.get("amount"),
            "main_net_inflow": r.get("net_inflow"),
        }
        for r in rows
    ]

    envelope = {
        "ok": True,
        "market": "stock",
        "source": "sentiment_store",
        "data_date": latest_date,
        "data": {
            "board_type": board_type,
            "sort_by": sort_by,
            "boards": boards,
        },
    }
    return json.dumps(envelope, ensure_ascii=False)


class SectorFlowTool(BaseTool):
    """Fetch sector-level aggregate turnover and capital flow for A-share boards.

    Data source: THS iwencai → SQLite cache. Uses cached data collected via
    the market sentiment Web UI or API. Use together with
    ``get_market_data(codes=["000001.SH","399001.SZ"], ...)`` to get
    total-market turnover for the crowding ratio denominator.

    This tool operates at the **board (sector) level** — never at the
    individual-stock level. For per-stock fund flow, use ``get_fund_flow``.
    For sector membership lookups, use ``get_sector_info``.
    """

    name = "get_sector_flow"
    is_readonly = True
    repeatable = True
    description = (
        "Fetch A-share sector-level aggregate turnover and capital flow from "
        "cached market data (THS iwencai → SQLite). Returns board-level "
        "monetary data: turnover (成交额), main capital net inflow (主力净流入), "
        "plus percent change. Data must be collected first via the sentiment "
        "UI or API. Operates at the BOARD / SECTOR level — NOT per-stock. "
        "Use this for sector crowding analysis. "
        "Market: A-share industry boards (行业板块) and concept boards (概念板块). "
        'Example: {"board_type": "industry", "sort_by": "amount", "limit": 20}.'
    )
    parameters = {
        "type": "object",
        "properties": {
            "board_type": {
                "type": "string",
                "enum": list(_VALID_BOARD_TYPES),
                "description": (
                    "Board universe: 'industry' for 行业板块 (default, "
                    "e.g. 半导体, 白酒, 银行) or 'concept' for 概念板块 "
                    "(e.g. AI算力, 光伏, 新能源车)."
                ),
                "default": "industry",
            },
            "limit": {
                "type": "integer",
                "description": (
                    f"Number of top boards to return "
                    f"(1-{_MAX_LIMIT}). Default {_DEFAULT_LIMIT}."
                ),
                "default": _DEFAULT_LIMIT,
            },
            "sort_by": {
                "type": "string",
                "enum": list(_VALID_SORT_BY),
                "description": (
                    "Sort boards by: 'change_pct' (涨跌幅, default), "
                    "'amount' (成交额, best for crowding analysis), "
                    "or 'net_inflow' (主力净流入). All descending."
                ),
                "default": "change_pct",
            },
        },
        "required": [],
    }

    def execute(self, **kwargs: Any) -> str:
        """Fetch board-level flow data from cache and return a JSON envelope."""
        board_type = kwargs.get("board_type", "industry")
        if board_type not in _VALID_BOARD_TYPES:
            return _error(
                f"board_type must be one of {list(_VALID_BOARD_TYPES)}, got {board_type!r}"
            )

        sort_by = kwargs.get("sort_by", "change_pct")
        if sort_by not in _VALID_SORT_BY:
            return _error(
                f"sort_by must be one of {list(_VALID_SORT_BY)}, got {sort_by!r}"
            )

        limit = kwargs.get("limit", _DEFAULT_LIMIT)
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
            return _error("limit must be a positive integer")

        return _fetch_from_store(board_type, sort_by, min(limit, _MAX_LIMIT))
