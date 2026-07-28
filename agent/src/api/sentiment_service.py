"""业务逻辑层 — 采集编排、动态指标计算、查询。

依赖:
- sentiment_fetcher: 从 THS iwencai 抓取原始数据
- sentiment_store:  SQLite 读写

所有衍生指标（拥挤度比率、拥挤度等级、资金偏好）在查询时动态计算，
不存入数据库，确保数据一致性。
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any

from .sentiment_fetcher import get_market_total, get_sectors
from .sentiment_store import SentimentStore

logger = logging.getLogger(__name__)

_VALID_BOARD_TYPES = ("industry", "concept")

# ---------------------------------------------------------------------------
# Indicator helpers
# ---------------------------------------------------------------------------


def crowding_ratio(sector_amount: float, total_amount: float) -> float | None:
    """拥挤度比率 = 板块成交额 / 全市场成交额 * 100%"""
    if total_amount <= 0:
        return None
    return round(sector_amount / total_amount * 100, 2)


def crowding_level(ratio: float | None) -> str | None:
    """拥挤度等级：normal (<10%), elevated (10-14%), high (14-16%), extreme (>16%)"""
    if ratio is None:
        return None
    if ratio < 10:
        return "normal"
    if ratio < 14:
        return "elevated"
    if ratio < 16:
        return "high"
    return "extreme"


def consecutive_inflow_days(history: list[dict[str, Any]]) -> tuple[int, bool]:
    """计算最近连续净流入天数。

    Args:
        history: 按 trade_date ASC 排列的板块历史数据。

    Returns:
        (consecutive_days, is_favored) — is_favored 为 True 当 >= 3 天。
    """
    cons = 0
    for r in reversed(history):
        if (r.get("net_inflow") or 0) > 0:
            cons += 1
        else:
            break
    return cons, cons >= 3


# ---------------------------------------------------------------------------
# Service class
# ---------------------------------------------------------------------------


class SentimentService:
    """市场情绪业务编排 — 采集 + 查询 + 指标计算。"""

    def __init__(self, store: SentimentStore | None = None) -> None:
        self.store = store or SentimentStore()
        self.store.ensure_tables()

    # -- collect --------------------------------------------------------------

    def collect(self, trade_date: str | None = None) -> dict[str, Any]:
        """采集指定日期的全市场 + 板块数据并写入 SQLite。

        Args:
            trade_date: 可选，YYYY-MM-DD。None 时取最新交易日。

        Returns:
            {ok, date, total_market, sectors_collected, sectors_failed, elapsed_seconds}
        """
        started = time.monotonic()
        self.store.ensure_tables()

        # 1. 全市场数据（必需）
        market = get_market_total(trade_date)
        if not market:
            return {
                "ok": False,
                "error": "全市场数据获取失败，请检查 IWENCAI_API_KEY 和网络连接",
                "elapsed_seconds": round(time.monotonic() - started, 1),
            }

        trade_date = trade_date or market["trade_date"]
        collected_at = datetime.now().isoformat(timespec="seconds")

        self.store.upsert_market_total(
            trade_date=trade_date,
            total=market["total"],
            sh=market["sh_amount"],
            sz=market["sz_amount"],
            collected_at=collected_at,
        )

        # 2. 板块数据（容忍部分失败）
        sectors_collected: dict[str, int] = {}
        sectors_failed: list[str] = []

        for stype in _VALID_BOARD_TYPES:
            try:
                sectors = get_sectors(stype, trade_date)
                if sectors:
                    self.store.upsert_sectors(trade_date, stype, sectors, collected_at)
                    sectors_collected[stype] = len(sectors)
                else:
                    sectors_failed.append(stype)
            except Exception as exc:
                logger.warning("采集 %s 板块失败: %s", stype, exc)
                sectors_failed.append(stype)

        elapsed = round(time.monotonic() - started, 1)

        if not sectors_collected and sectors_failed:
            return {
                "ok": False,
                "error": f"所有板块数据采集失败: {sectors_failed}",
                "date": trade_date,
                "total_market": market,
                "elapsed_seconds": elapsed,
            }

        return {
            "ok": True,
            "date": trade_date,
            "total_market": market,
            "sectors_collected": sectors_collected,
            "sectors_failed": sectors_failed,
            "elapsed_seconds": elapsed,
        }

    # -- delete ----------------------------------------------------------------

    def delete_collect(self, trade_date: str) -> dict[str, Any]:
        """删除指定日期的采集数据。"""
        deleted = self.store.delete_by_date(trade_date)
        total = deleted["market_total_deleted"] + deleted["market_sector_deleted"]
        return {
            "ok": True,
            "date": trade_date,
            "deleted": deleted,
            "total_rows_deleted": total,
        }

    # -- overview -------------------------------------------------------------

    def get_overview(
        self, board_type: str = "industry", top_n: int = 20, trade_date: str | None = None, page_size: int = 20
    ) -> dict[str, Any]:
        """全市场成交额 + 板块拥挤度排名 + 资金偏好。

        Args:
            board_type: 'industry' | 'concept'
            top_n: summary card 返回的板块数量 (1-1000)
            trade_date: 可选，默认最新交易日
            page_size: 资金偏好计算条数（按拥挤度排序的前 N 条）
        """
        if board_type not in _VALID_BOARD_TYPES:
            return {"ok": False, "error": f"board_type must be one of {list(_VALID_BOARD_TYPES)}"}

        if not trade_date:
            trade_date = self.store.get_latest_trading_day()
        if not trade_date:
            return {"ok": False, "error": "暂无缓存数据，请先执行 POST /sentiment/collect"}

        market = self.store.get_market_total(trade_date)
        if not market:
            return {
                "ok": False,
                "error": f"{trade_date} 无全市场数据，请先采集该日期",
            }

        total = market["total_amount"]

        # 相邻交易日（翻页用）
        prev_date, next_date = self.store.get_adjacent_trading_days(trade_date)

        # 板块数据（全量，供前端分页排序）
        sectors = self.store.get_sectors(trade_date, board_type, order_by="amount", limit=1000)
        if not sectors:
            return {
                "ok": True,
                "total_market_turnover": total,
                "total_market_turnover_billion": total,
                "sh_turnover": market["sh_amount"],
                "sh_turnover_billion": market["sh_amount"],
                "sz_turnover": market["sz_amount"],
                "sz_turnover_billion": market["sz_amount"],
                "board_type": board_type,
                "data_date": trade_date,
                "prev_trade_date": prev_date,
                "next_trade_date": next_date,
                "all_sectors": [],
                "total_count": 0,
                "top_by_crowding": [],
                "top_by_inflow": [],
                "timestamp": datetime.now().isoformat(),
            }

        # 动态计算拥挤度 + 字段名映射（DB → 前端）
        enriched: list[dict[str, Any]] = []
        for s in sectors:
            cr = crowding_ratio(s.get("amount") or 0, total)
            enriched.append({
                "board_code": s["bk_code"],
                "board_name": s["bk_name"],
                "turnover": s.get("amount"),
                "main_net_inflow": s.get("net_inflow"),
                "change_pct": s.get("change_pct"),
                "crowding_ratio": cr,
                "crowding_level": crowding_level(cr),
            })

        # 拥挤度排名（summary card 用）
        by_crowding = sorted(enriched, key=lambda x: x.get("crowding_ratio") or 0, reverse=True)[:top_n]

        # 资金流入排名（summary card 用）
        by_inflow = sorted(enriched, key=lambda x: x.get("main_net_inflow") or -(10**18), reverse=True)[:top_n]

        # 资金偏好（连续流入天数）— 对所有主力净流入为正的板块计算
        for b in enriched:
            if (b.get("main_net_inflow") or 0) > 0:
                hist = self.store.get_sector_history(b["board_code"], board_type, end_date=trade_date, limit=10)
                cons, fav = consecutive_inflow_days(hist)
                b["consecutive_inflow_days"] = cons
                b["is_favored"] = fav
            else:
                b["consecutive_inflow_days"] = 0
                b["is_favored"] = False

        return {
            "ok": True,
            "total_market_turnover": total,
            "total_market_turnover_billion": total,
            "sh_turnover": market["sh_amount"],
            "sh_turnover_billion": market["sh_amount"],
            "sz_turnover": market["sz_amount"],
            "sz_turnover_billion": market["sz_amount"],
            "board_type": board_type,
            "data_date": trade_date,
            "prev_trade_date": prev_date,
            "next_trade_date": next_date,
            "all_sectors": enriched,
            "total_count": len(enriched),
            "top_by_crowding": by_crowding,
            "top_by_inflow": by_inflow,
            "timestamp": datetime.now().isoformat(),
        }

    # -- sector detail --------------------------------------------------------

    def get_sector_detail(
        self, board_code: str, board_type: str = "industry", days: int = 20, trade_date: str | None = None
    ) -> dict[str, Any]:
        """单板块拥挤度趋势 + 资金流向。"""
        if board_type not in _VALID_BOARD_TYPES:
            board_type = "industry"

        hist = self.store.get_sector_history(board_code, board_type, end_date=trade_date, limit=days)
        if not hist:
            return {"ok": False, "error": f"No data for {board_code}"}

        dates = [r["trade_date"] for r in hist]
        market_totals = self._get_market_totals(dates)

        points: list[dict[str, Any]] = []
        for r in hist:
            dt = r["trade_date"]
            total = market_totals.get(dt, 0)
            amt = r.get("amount") or 0
            cr = crowding_ratio(amt, total)
            points.append({
                "date": dt,
                "crowding_ratio": cr,
                "main_net_inflow": r.get("net_inflow"),
                "main_net_inflow_billion": r.get("net_inflow"),
                "turnover": amt,
                "turnover_billion": amt,
                "total_market_turnover": total,
                "total_market_turnover_billion": total,
                "change_pct": r.get("change_pct"),
            })

        board_name = hist[0].get("bk_name", board_code) if hist else board_code
        last_total = market_totals.get(points[-1]["date"], 0) if points else 0

        return {
            "ok": True,
            "board_code": board_code,
            "board_name": board_name,
            "total_market_turnover": last_total,
            "total_market_turnover_billion": last_total,
            "days_requested": days,
            "data": points,
        }

    # -- history --------------------------------------------------------------

    def get_history(
        self,
        board_code: str,
        board_type: str = "industry",
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict[str, Any]:
        """日期范围板块历史数据。"""
        if board_type not in _VALID_BOARD_TYPES:
            board_type = "industry"

        if start_date:
            try:
                datetime.strptime(start_date, "%Y-%m-%d")
            except ValueError:
                return {"ok": False, "error": "start_date must be YYYY-MM-DD"}
        if end_date:
            try:
                datetime.strptime(end_date, "%Y-%m-%d")
            except ValueError:
                return {"ok": False, "error": "end_date must be YYYY-MM-DD"}

        hist = self.store.get_sector_history(
            board_code, board_type, start_date=start_date, end_date=end_date, limit=60
        )
        if not hist:
            return {"ok": False, "error": f"No data for {board_code}"}

        dates = sorted({r["trade_date"] for r in hist})
        market_totals = self._get_market_totals(dates)

        points: list[dict[str, Any]] = []
        for r in hist:
            dt = r["trade_date"]
            total = market_totals.get(dt, 0)
            amt = r.get("amount") or 0
            cr = crowding_ratio(amt, total)
            points.append({
                "date": dt,
                "crowding_ratio": cr,
                "main_net_inflow": r.get("net_inflow"),
                "main_net_inflow_billion": r.get("net_inflow"),
                "turnover": amt,
                "turnover_billion": amt,
                "total_market_turnover": total,
                "total_market_turnover_billion": total,
                "change_pct": r.get("change_pct"),
            })

        board_name = hist[0].get("bk_name", board_code) if hist else board_code

        return {
            "ok": True,
            "board_code": board_code,
            "board_name": board_name,
            "start_date": start_date or "",
            "end_date": end_date or "",
            "data": points,
            "timestamp": datetime.now().isoformat(),
        }

    # -- boards ---------------------------------------------------------------

    def get_boards(self, board_type: str = "industry") -> dict[str, Any]:
        """板块名称列表（autocomplete 用）。"""
        if board_type not in _VALID_BOARD_TYPES:
            return {"ok": False, "error": f"board_type must be one of {list(_VALID_BOARD_TYPES)}"}
        boards = self.store.get_board_list(board_type)
        return {"ok": True, "board_type": board_type, "boards": boards}

    # -- collect status -------------------------------------------------------

    def get_collect_status(self) -> dict[str, Any]:
        return self.store.get_collect_status()

    # -- internal helpers -----------------------------------------------------

    def _get_market_totals(self, dates: list[str]) -> dict[str, float]:
        """批量获取多个日期的全市场成交额。"""
        result: dict[str, float] = {}
        for dt in dates:
            row = self.store.get_market_total(dt)
            if row:
                result[dt] = row["total_amount"]
        return result
