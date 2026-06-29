"""Read-only sector-level aggregate flow tool backed by the Eastmoney client.

Eastmoney publishes board-level turnover and capital-flow data through the same
``clist/get`` endpoint used by the sector ranking tool. This tool enriches the
field selector to include monetary aggregates — turnover (成交额), main capital
net inflow (主力净流入), and turnover rate (换手率) — that the crowding
analysis framework requires.

Use this tool together with ``get_market_data`` (for total-market turnover via
``000001.SH`` + ``399001.SZ``) to compute the sector crowding ratio.

Markets: A-share industry boards (行业板块) and concept boards (概念板块).
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from backtest.loaders.eastmoney_client import get_json
from src.agent.tools import BaseTool

logger = logging.getLogger(__name__)

# Eastmoney push2 board listing endpoint.  Same ``clist/get`` URL as the sector
# ranking tool, but with enriched field selectors for monetary aggregates.
_CLIST_URL = "https://push2.eastmoney.com/api/qt/clist/get"

# Field selectors.
#   f12 = board/security code
#   f14 = board name
#   f3  = percent change (涨跌幅)
#   f2  = board index value
#   f6  = turnover / 成交额 (CNY)
#   f62 = main capital net inflow / 主力净流入 (CNY)
#   f8  = turnover rate / 换手率 (%)
#   f104 = up constituent count
#   f105 = down constituent count
#   f140 = leading stock name
_FIELDS = "f12,f14,f3,f2,f6,f62,f8,f104,f105,f140"

# Board universe selectors (``fs`` parameter).  m:90 = board market.
_BOARD_FS = {
    "industry": "m:90+t:2",  # t:2 = industry board sub-type
    "concept": "m:90+t:3",   # t:3 = concept board sub-type
}

# Sort fid mapping.  f3 = percent change, f6 = turnover, f62 = main net inflow.
_SORT_FID = {
    "change_pct": "f3",
    "amount": "f6",
    "net_inflow": "f62",
}

# Defensive caps so a payload can never blow up the LLM context.
_MAX_LIMIT = 100
_DEFAULT_LIMIT = 30
_VALID_BOARD_TYPES = tuple(_BOARD_FS)
_VALID_SORT_BY = tuple(_SORT_FID)

# Retry settings for transient Eastmoney failures (rate limits, DNS, timeouts).
_MAX_ATTEMPTS = 3
_BACKOFF_BASE_SECONDS = 0.8


def _error(message: str) -> str:
    """Build the failure envelope as a JSON string.

    Args:
        message: Human-readable error description.

    Returns:
        A ``{"ok": false, "error": ...}`` JSON string.
    """
    return json.dumps({"ok": False, "error": message}, ensure_ascii=False)


def _as_float(value: Any) -> float | None:
    """Coerce an Eastmoney numeric cell to ``float``, or ``None`` if unusable.

    Eastmoney emits ``"-"`` for missing numerics; those map to ``None``.

    Args:
        value: Raw cell value from a push2 row.

    Returns:
        The float value, or ``None`` when the cell is missing / non-numeric.
    """
    if value is None or value == "-" or value == "":
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _parse_flow_row(row: Any) -> dict[str, Any] | None:
    """Parse one ``clist`` diff row into a board-flow dict with monetary fields.

    Args:
        row: One element of ``data.diff`` (a dict keyed by ``f12``/``f14``/...).

    Returns:
        A dict with ``board_code``, ``board_name``, ``change_pct``, ``index``,
        ``turnover``, ``main_net_inflow``, ``turnover_rate``, ``up_count``,
        ``down_count``, ``leader``; or ``None`` when the row lacks a board
        code/name.
    """
    if not isinstance(row, dict):
        return None
    board_code = row.get("f12")
    board_name = row.get("f14")
    if not board_code or not board_name:
        return None
    leader = row.get("f140")
    return {
        "board_code": str(board_code),
        "board_name": str(board_name),
        "change_pct": _as_float(row.get("f3")),
        "index": _as_float(row.get("f2")),
        "turnover": _as_float(row.get("f6")),
        "main_net_inflow": _as_float(row.get("f62")),
        "turnover_rate": _as_float(row.get("f8")),
        "up_count": _as_float(row.get("f104")),
        "down_count": _as_float(row.get("f105")),
        "leader": str(leader) if leader and leader != "-" else None,
    }


def _diff_rows(payload: Any) -> list:
    """Extract the ``data.diff`` row list from a push2 payload, defensively.

    Args:
        payload: Decoded JSON from a push2 board endpoint.

    Returns:
        The list of diff rows, or ``[]`` when the payload carries none.
    """
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        return []
    diff = data.get("diff")
    if isinstance(diff, dict):
        # Some push2 responses key diff rows by string index instead of a list.
        return list(diff.values())
    if isinstance(diff, list):
        return diff
    return []


def _fetch_board_flow(board_type: str, sort_by: str, limit: int) -> str:
    """Fetch board-level aggregate flow data from Eastmoney with retries.

    Args:
        board_type: ``"industry"`` or ``"concept"``.
        sort_by: ``"change_pct"``, ``"amount"``, or ``"net_inflow"``.
        limit: Number of top boards to return (already validated and capped).

    Returns:
        A JSON envelope string with the ranked boards and their monetary
        aggregates, or an error envelope after all retries are exhausted.
    """
    last_error: Exception | None = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            payload = get_json(
                _CLIST_URL,
                params={
                    "fs": _BOARD_FS[board_type],
                    "fields": _FIELDS,
                    "pn": "1",
                    "pz": str(limit),
                    "po": "1",
                    "fid": _SORT_FID[sort_by],
                    "fltt": "2",
                },
            )
        except Exception as exc:  # noqa: BLE001 - retry; surface after exhaustion
            last_error = exc
            logger.warning(
                "sector flow fetch attempt %d/%d failed (board=%s, sort=%s): %s",
                attempt, _MAX_ATTEMPTS, board_type, sort_by, exc,
            )
            if attempt < _MAX_ATTEMPTS:
                time.sleep(_BACKOFF_BASE_SECONDS * attempt)
            continue

        # Success path — payload received, parse boards.
        boards = [
            parsed
            for parsed in (_parse_flow_row(r) for r in _diff_rows(payload))
            if parsed is not None
        ]
        if len(boards) > limit:
            boards = boards[:limit]
        envelope = {
            "ok": True,
            "market": "stock",
            "source": "eastmoney",
            "data": {
                "board_type": board_type,
                "sort_by": sort_by,
                "boards": boards,
            },
        }
        return json.dumps(envelope, ensure_ascii=False)

    # All retries exhausted.
    return _error(
        f"board flow request failed after {_MAX_ATTEMPTS} attempts: {last_error}"
    )


class SectorFlowTool(BaseTool):
    """Fetch sector-level aggregate turnover and capital flow for A-share boards.

    Returns board-level monetary data (turnover, main capital net inflow,
    turnover rate) that feeds the sector crowding analysis framework.  Use
    together with ``get_market_data(codes=["000001.SH","399001.SZ"], ...)``
    to get total-market turnover for the crowding ratio denominator.

    This tool operates at the **board (sector) level** — never at the
    individual-stock level.  For per-stock fund flow, use ``get_fund_flow``.
    For sector membership lookups, use ``get_sector_info``.
    """

    name = "get_sector_flow"
    is_readonly = True
    repeatable = True  # safe to call multiple times: different board_types, sorts, or retries
    description = (
        "Fetch A-share sector-level aggregate turnover and capital flow from "
        "Eastmoney (free, no auth). Returns board-level monetary data: turnover "
        "(成交额), main capital net inflow (主力净流入), turnover rate (换手率), "
        "plus percent change, up/down counts, and leader stock. Operates at the "
        "BOARD / SECTOR level — NOT per-stock. Use this for sector crowding "
        "analysis. Market: A-share industry boards (行业板块) and concept "
        "boards (概念板块). "
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
                    "Number of top boards to return "
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
        """Fetch board-level flow data and return a JSON envelope.

        Args:
            **kwargs: ``board_type`` ("industry"|"concept", default "industry"),
                ``sort_by`` ("change_pct"|"amount"|"net_inflow", default
                "change_pct"), ``limit`` (int, default 30, capped at 100).

        Returns:
            A JSON string ``{"ok": true, "market": "stock", "source":
            "eastmoney", "data": {"board_type": ..., "sort_by": ..., "boards":
            [...]}}`` on success, or ``{"ok": false, "error": ...}`` on a
            validation / request failure.
        """
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

        return _fetch_board_flow(board_type, sort_by, min(limit, _MAX_LIMIT))
