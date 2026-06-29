"""Market Sentiment HTTP routes for the Web UI.

Mounted by ``agent/api_server.py`` via ``register_sentiment_routes(app)``.

Routes:
- ``GET /sentiment/overview``       — daily total-market turnover + sector crowding ranking
- ``GET /sentiment/sector-detail``   — single sector crowding trend + net inflow history
- ``GET /sentiment/history``         — date-range sector crowding + net inflow history

All endpoints are read-only. Data comes from Eastmoney free public APIs
routed through ``backtest.loaders.eastmoney_client.get_json()``.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from fastapi import Depends, FastAPI, Query, Request

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Eastmoney endpoint constants
# ---------------------------------------------------------------------------

_CLIST_URL = "https://push2.eastmoney.com/api/qt/clist/get"
_KLINE_URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
_FFLOW_URL = "https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get"

_BOARD_FS = {"industry": "m:90+t:2", "concept": "m:90+t:3"}

_CLIST_FIELDS = "f12,f14,f3,f2,f6,f62,f8,f104,f105,f140"
_KLINE_FIELDS1 = "f1,f2,f3,f4,f5,f6"
_KLINE_FIELDS2 = "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
_FFLOW_FIELDS1 = "f1,f2,f3,f7"
_FFLOW_FIELDS2 = "f51,f52,f53,f54,f55,f56"

_SH_SECID = "1.000001"
_SZ_SECID = "0.399001"

_VALID_BOARD_TYPES = ("industry", "concept")
_MAX_DAYS = 60
_DEFAULT_DAYS = 20

_FLOW_BUCKETS = ("main", "small", "medium", "large", "super_large")


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _error(message: str) -> dict[str, Any]:
    return {"ok": False, "error": message}


def _as_float(value: Any) -> float | None:
    if value is None or value == "-" or value == "":
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _parse_clist_row(row: Any) -> dict[str, Any] | None:
    if not isinstance(row, dict):
        return None
    code = row.get("f12")
    name = row.get("f14")
    if not code or not name:
        return None
    leader = row.get("f140")
    return {
        "board_code": str(code),
        "board_name": str(name),
        "change_pct": _as_float(row.get("f3")),
        "index": _as_float(row.get("f2")),
        "turnover": _as_float(row.get("f6")),
        "main_net_inflow": _as_float(row.get("f62")),
        "turnover_rate": _as_float(row.get("f8")),
        "up_count": _as_float(row.get("f104")),
        "down_count": _as_float(row.get("f105")),
        "leader": str(leader) if leader and leader != "-" else None,
    }


def _diff_rows(payload: Any) -> list[Any]:
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        return []
    diff = data.get("diff")
    if isinstance(diff, dict):
        return list(diff.values())
    if isinstance(diff, list):
        return diff
    return []


def _parse_kline_row(raw: str) -> dict[str, Any] | None:
    parts = raw.split(",")
    if len(parts) < 7:
        return None
    try:
        return {
            "date": parts[0],
            "open": float(parts[1]),
            "close": float(parts[2]),
            "high": float(parts[3]),
            "low": float(parts[4]),
            "volume": float(parts[5]),
            "amount": float(parts[6]),
            "amplitude": float(parts[7]) if len(parts) > 7 and parts[7] != "-" else None,
            "change_pct": float(parts[8]) if len(parts) > 8 and parts[8] != "-" else None,
            "change_amt": float(parts[9]) if len(parts) > 9 and parts[9] != "-" else None,
            "turnover_pct": float(parts[10]) if len(parts) > 10 and parts[10] != "-" else None,
        }
    except (ValueError, TypeError):
        return None


def _parse_fflow_row(raw: str) -> dict[str, Any] | None:
    parts = raw.split(",")
    if len(parts) < 1 + len(_FLOW_BUCKETS):
        return None
    ts = parts[0]
    try:
        vals = [float(parts[i + 1]) for i in range(len(_FLOW_BUCKETS))]
    except (ValueError, TypeError):
        return None
    return {
        "date": ts[:10] if len(ts) >= 10 else ts,
        "main_net_inflow": vals[0],
        "small_net_inflow": vals[1],
        "medium_net_inflow": vals[2],
        "large_net_inflow": vals[3],
        "super_large_net_inflow": vals[4],
    }


# ---------------------------------------------------------------------------
# Eastmoney data fetchers
# ---------------------------------------------------------------------------

def _em_get(url: str, params: dict[str, Any]) -> Any:
    """Throttled Eastmoney GET via the shared eastmoney_client."""
    from backtest.loaders.eastmoney_client import get_json

    return get_json(url, params=params)


def _fetch_boards(board_type: str, limit: int = 60) -> list[dict[str, Any]]:
    """Fetch board-level aggregate flow snapshot sorted by turnover desc."""
    fs = _BOARD_FS.get(board_type, _BOARD_FS["industry"])
    try:
        payload = _em_get(
            _CLIST_URL,
            params={
                "fs": fs,
                "fields": _CLIST_FIELDS,
                "pn": "1",
                "pz": str(min(limit, 100)),
                "po": "1",
                "fid": "f6",
                "fltt": "2",
            },
        )
    except Exception as exc:
        logger.warning("Board flow snapshot failed: %s", exc)
        return []
    boards = [
        p for p in (_parse_clist_row(r) for r in _diff_rows(payload)) if p is not None
    ]
    return boards[:limit]


def _fetch_kline(secid: str, days: int = 30) -> list[dict[str, Any]]:
    """Fetch index/board daily kline history."""
    end = datetime.now().strftime("%Y%m%d")
    beg = (datetime.now() - timedelta(days=days + 10)).strftime("%Y%m%d")
    try:
        payload = _em_get(
            _KLINE_URL,
            params={
                "secid": secid,
                "klt": "101",
                "fqt": "0",
                "beg": beg,
                "end": end,
                "lmt": str(max(days + 5, 30)),
                "fields1": _KLINE_FIELDS1,
                "fields2": _KLINE_FIELDS2,
            },
        )
    except Exception as exc:
        logger.warning("Kline fetch failed for %s: %s", secid, exc)
        return []
    klines = payload.get("data", {}).get("klines", []) or []
    return [p for p in (_parse_kline_row(line) for line in klines) if p is not None]


def _fetch_fflow(board_code: str, days: int = 30) -> list[dict[str, Any]]:
    """Fetch board-level daily fund flow history."""
    secid = f"90.{board_code}" if not board_code.startswith("90.") else board_code
    try:
        payload = _em_get(
            _FFLOW_URL,
            params={
                "secid": secid,
                "klt": "101",
                "lmt": str(days + 10),
                "fields1": _FFLOW_FIELDS1,
                "fields2": _FFLOW_FIELDS2,
            },
        )
    except Exception as exc:
        logger.warning("Fund flow fetch failed for %s: %s", board_code, exc)
        return []
    klines = payload.get("data", {}).get("klines", []) or []
    return [p for p in (_parse_fflow_row(line) for line in klines) if p is not None]


def _total_market_turnover(target_date: str | None = None) -> tuple[float, str, float, float]:
    """Get total market turnover (SH + SZ) for a date. Returns (total_cny, actual_date, sh, sz)."""
    sh = _fetch_kline(_SH_SECID, days=15)
    sz = _fetch_kline(_SZ_SECID, days=15)
    if not sh or not sz:
        return 0, target_date or datetime.now().strftime("%Y-%m-%d"), 0, 0

    sz_map = {r["date"]: r["amount"] for r in sz}
    sh_map = {r["date"]: r["amount"] for r in sh}
    target = target_date or datetime.now().strftime("%Y-%m-%d")

    for r in reversed(sh):
        if r["date"] <= target:
            dt = r["date"]
            return sh_map.get(dt, 0) + sz_map.get(dt, 0), dt, sh_map.get(dt, 0), sz_map.get(dt, 0)

    last = sh[-1]
    dt = last["date"]
    return last["amount"] + sz_map.get(dt, 0), dt, last["amount"], sz_map.get(dt, 0)


def _crowding_ratio(sector_turnover: float, total: float) -> float | None:
    return round(sector_turnover / total * 100, 2) if total > 0 else None


def _crowding_label(ratio: float) -> str:
    if ratio < 10:
        return "normal"
    if ratio < 14:
        return "elevated"
    if ratio < 16:
        return "high"
    return "extreme"


def _fund_preference(board_code: str, days: int = 10) -> tuple[int, bool]:
    """Count consecutive days of positive main_net_inflow. (consecutive, favored)."""
    rows = _fetch_fflow(board_code, days=days)
    if not rows:
        return 0, False
    cons = 0
    for r in reversed(rows):
        if (r.get("main_net_inflow") or 0) > 0:
            cons += 1
        else:
            break
    return cons, cons >= 3


def _build_market_map(days: int) -> dict[str, float]:
    """Build date → total market turnover lookup map for the last N days."""
    sh = _fetch_kline(_SH_SECID, days=days)
    sz = _fetch_kline(_SZ_SECID, days=days)
    sz_by_date = {r["date"]: r["amount"] for r in sz}
    result: dict[str, float] = {}
    for r in sh:
        dt = r["date"]
        result[dt] = r["amount"] + sz_by_date.get(dt, 0)
    return result


def _board_name(board_code: str, board_type: str) -> str:
    """Look up board name from a snapshot. Falls back to board_code."""
    try:
        boards = _fetch_boards(board_type, limit=100)
        for b in boards:
            if b.get("board_code") == board_code:
                return b.get("board_name", board_code)
    except Exception:
        pass
    return board_code


def _merge_points(
    klines: list,
    fflows: list,
    market_map: dict[str, float],
    start: str | None = None,
    end: str | None = None,
) -> list[dict[str, Any]]:
    """Merge klines + fflows into unified data points with crowding ratio."""
    ff_by_date = {r["date"]: r for r in fflows}
    points: list[dict[str, Any]] = []
    for k in klines:
        dt = k["date"]
        if start and dt < start:
            continue
        if end and dt > end:
            continue
        ff = ff_by_date.get(dt, {})
        total = market_map.get(dt, 0)
        turnover = k.get("amount", 0) or 0
        cr = _crowding_ratio(turnover, total)
        inflow = ff.get("main_net_inflow")
        points.append({
            "date": dt,
            "crowding_ratio": cr,
            "main_net_inflow": inflow,
            "main_net_inflow_billion": round(inflow / 1e8, 2) if inflow is not None else None,
            "turnover": turnover,
            "turnover_billion": round(turnover / 1e8, 2) if turnover else None,
            "total_market_turnover": total,
            "total_market_turnover_billion": round(total / 1e8, 2) if total > 0 else None,
            "turnover_rate": k.get("turnover_pct"),
            "change_pct": k.get("change_pct"),
            "close": k.get("close"),
        })
    return points


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
    # GET /sentiment/boards — 板块列表同步
    # ---------------------------------------------------------------

    @app.get("/sentiment/boards", dependencies=deps)
    async def list_boards(
        request: Request,
        board_type: str = Query("industry", description="'industry' or 'concept'"),
    ) -> dict[str, Any]:
        """Return the full board list for local caching / autocomplete."""
        if board_type not in _VALID_BOARD_TYPES:
            return _error(f"board_type must be one of {list(_VALID_BOARD_TYPES)}")
        boards = _fetch_boards(board_type, limit=100)
        return {"ok": True, "board_type": board_type, "boards": boards}

    # ---------------------------------------------------------------
    # GET /sentiment/overview
    # ---------------------------------------------------------------

    @app.get("/sentiment/overview", dependencies=deps)
    async def sentiment_overview(
        request: Request,
        board_type: str = Query("industry", description="'industry' or 'concept'"),
        top_n: int = Query(20, ge=1, le=60),
    ) -> dict[str, Any]:
        if board_type not in _VALID_BOARD_TYPES:
            return _error(f"board_type must be one of {list(_VALID_BOARD_TYPES)}")

        total_cny, actual_date, sh_amt, sz_amt = _total_market_turnover()
        boards = _fetch_boards(board_type, limit=max(top_n * 2, 60))

        # Enrich with crowding ratio
        enriched: list[dict[str, Any]] = []
        for b in boards:
            t = b.get("turnover") or 0
            cr = _crowding_ratio(t, total_cny) if total_cny > 0 else None
            b["crowding_ratio"] = cr
            b["crowding_level"] = _crowding_label(cr) if cr is not None else None
            enriched.append(b)

        enriched.sort(key=lambda x: x.get("crowding_ratio") or 0, reverse=True)

        # Fund preference for top sectors
        top_crowding = enriched[:top_n]
        for b in top_crowding[:8]:
            code = b.get("board_code", "")
            if code:
                cons, fav = _fund_preference(code)
                b["consecutive_inflow_days"] = cons
                b["is_favored"] = fav

        # Inflow ranking
        inflow_sorted = sorted(
            enriched, key=lambda x: x.get("main_net_inflow") or -(10**18), reverse=True
        )[:top_n]
        for b in inflow_sorted[:8]:
            code = b.get("board_code", "")
            if code and "is_favored" not in b:
                cons, fav = _fund_preference(code)
                b["consecutive_inflow_days"] = cons
                b["is_favored"] = fav

        return {
            "ok": True,
            "total_market_turnover": total_cny,
            "total_market_turnover_billion": round(total_cny / 1e8, 2) if total_cny > 0 else 0,
            "sh_turnover": sh_amt,
            "sh_turnover_billion": round(sh_amt / 1e8, 2) if sh_amt > 0 else 0,
            "sz_turnover": sz_amt,
            "sz_turnover_billion": round(sz_amt / 1e8, 2) if sz_amt > 0 else 0,
            "board_type": board_type,
            "data_date": actual_date,
            "top_by_crowding": top_crowding,
            "top_by_inflow": inflow_sorted,
            "timestamp": datetime.now().isoformat(),
        }

    # ---------------------------------------------------------------
    # GET /sentiment/sector-detail
    # ---------------------------------------------------------------

    @app.get("/sentiment/sector-detail", dependencies=deps)
    async def sentiment_sector_detail(
        request: Request,
        board_code: str = Query(..., min_length=3),
        days: int = Query(_DEFAULT_DAYS, ge=1, le=_MAX_DAYS),
        board_type: str = Query("industry"),
    ) -> dict[str, Any]:
        klines = _fetch_kline(f"90.{board_code}", days=days)
        if not klines:
            return _error(f"No kline data for board {board_code}")

        fflows = _fetch_fflow(board_code, days=days)
        market_map = _build_market_map(days=days)
        points = _merge_points(klines, fflows, market_map)
        name = _board_name(board_code, board_type if board_type in _VALID_BOARD_TYPES else "industry")
        total_mkt = market_map.get(points[-1]["date"], 0) if points else 0

        return {
            "ok": True,
            "board_code": board_code,
            "board_name": name,
            "total_market_turnover": total_mkt,
            "total_market_turnover_billion": round(total_mkt / 1e8, 2) if total_mkt > 0 else 0,
            "days_requested": days,
            "data": points,
        }

    # ---------------------------------------------------------------
    # GET /sentiment/history
    # ---------------------------------------------------------------

    @app.get("/sentiment/history", dependencies=deps)
    async def sentiment_history(
        request: Request,
        board_code: str = Query(..., min_length=3),
        start_date: str = Query(...),
        end_date: str = Query(...),
        board_type: str = Query("industry"),
    ) -> dict[str, Any]:
        try:
            start = datetime.strptime(start_date, "%Y-%m-%d")
            end = datetime.strptime(end_date, "%Y-%m-%d")
        except ValueError:
            return _error("Dates must be in YYYY-MM-DD format")

        if start > end:
            return _error("start_date must be before or equal to end_date")
        if (end - start).days > _MAX_DAYS:
            return _error(f"Date range must be at most {_MAX_DAYS} days")
        if start > datetime.now():
            return _error("start_date cannot be in the future")

        days_needed = (end - start).days + 20
        klines = _fetch_kline(f"90.{board_code}", days=days_needed)
        fflows = _fetch_fflow(board_code, days=days_needed)
        market_map = _build_market_map(days=days_needed)
        points = _merge_points(
            klines, fflows, market_map,
            start=start.strftime("%Y-%m-%d"),
            end=end.strftime("%Y-%m-%d"),
        )
        name = _board_name(board_code, board_type if board_type in _VALID_BOARD_TYPES else "industry")

        return {
            "ok": True,
            "board_code": board_code,
            "board_name": name,
            "start_date": start.strftime("%Y-%m-%d"),
            "end_date": end.strftime("%Y-%m-%d"),
            "data": points,
            "timestamp": datetime.now().isoformat(),
        }
