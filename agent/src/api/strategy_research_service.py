"""Service layer for strategy research — thin iwencai passthrough.

Sector constituent data is fetched in real-time from THS iwencai
(no caching).  The service owns only orchestration: resolve sector
members, suffix stock codes, and bridge to the sentiment store for
trading-day queries.
"""

from __future__ import annotations

from typing import Any

from src.api.iwencai_session import query_sector_members
from src.api.sentiment_store import SentimentStore


class StrategyResearchService:
    """Thin orchestrator — real-time iwencai, no local caching."""

    def get_sector_members(
        self,
        bk_code: str,
        bk_name: str = "",
        sector_type: str = "industry",
    ) -> dict[str, Any]:
        """Fetch constituents for a single sector from iwencai.

        Returns:
            ``{bk_code, bk_name, sector_type, members: [{code, name, price,
            change_pct, concepts, industries}, ...]}``.
        """
        try:
            raw_members = query_sector_members(bk_name or bk_code)
        except RuntimeError:
            return {
                "bk_code": bk_code,
                "bk_name": bk_name or bk_code,
                "sector_type": sector_type,
                "members": [],
            }

        return {
            "bk_code": bk_code,
            "bk_name": bk_name or bk_code,
            "sector_type": sector_type,
            "members": raw_members,
        }

    def get_available_trading_days(self, limit: int = 30) -> dict[str, Any]:
        """Return available trading dates.

        Generates weekdays backwards from the latest known trading day in
        ``market_total``.  This avoids the 50-row ceiling when the sentiment
        DB only covers recent history — the data loaders have years of OHLCV,
        so the date picker should reflect that.
        """
        store = SentimentStore()
        latest = store.get_latest_trading_day()
        if not latest:
            return {"dates": [], "latest": None}

        from datetime import datetime as dt, timedelta

        anchor = dt.strptime(latest, "%Y-%m-%d")
        dates: list[str] = []
        cursor = anchor
        while len(dates) < limit:
            if cursor.weekday() < 5:  # Mon=0 … Fri=4
                dates.append(cursor.strftime("%Y-%m-%d"))
            cursor -= timedelta(days=1)

        return {"dates": dates, "latest": latest}


def add_suffix(code: str) -> str:
    """Add exchange suffix to a bare 6-digit A-share code."""
    code = code.strip()
    if "." in code:
        return code  # already suffixed
    code = code.zfill(6)
    if code.startswith(("6", "5", "9")):
        return f"{code}.SH"
    elif code.startswith("8"):
        return f"{code}.BJ"
    else:
        return f"{code}.SZ"
