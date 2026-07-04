"""THS iwencai OpenAPI 数据抓取 — 全市场成交额 + 板块数据。

从 a-stock-data/scripts/market_data.py 提取 THS 部分，
适配 Vibe-Trading 代码风格。所有金额字段统一为亿元。

前置条件:
  export IWENCAI_API_KEY="..."
"""

from __future__ import annotations

import re
from datetime import datetime

from .iwencai_session import iwencai_paginate


# ---------------------------------------------------------------------------
# Dynamic field name helpers
# ---------------------------------------------------------------------------

def _find_key(keys: list[str], prefix: str) -> str | None:
    """问财返回字段形如 '涨跌幅[20260703]'，按前缀匹配。"""
    for k in keys:
        if k.startswith(prefix):
            return k
    return None


def _extract_date(keys: list[str], prefix: str) -> str:
    """从问财字段名提取日期，如 '成交额[20260703]' → '2026-07-03'。"""
    key = _find_key(keys, prefix)
    if key:
        m = re.search(r'\[(\d{8})\]', key)
        if m:
            dt = m.group(1)
            return f"{dt[:4]}-{dt[4:6]}-{dt[6:8]}"
    return datetime.now().strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# Market total + sectors
# ---------------------------------------------------------------------------

def get_market_total(trade_date: str | None = None) -> dict | None:
    """全市场成交额（上证+深证），返回 {trade_date, sh_amount, sz_amount, total} 亿元。

    trade_date: 交易日，None 则返回最新交易日数据。
    """
    query = "上证指数成交额 深证成指成交额"
    if trade_date:
        query = f"{trade_date} {query}"
    rows = iwencai_paginate(query, max_pages=1, label="大盘")

    if not rows or len(rows) < 2:
        return None

    keys = list(rows[0].keys())
    amt_key = _find_key(keys, "成交额[")
    trade_date = _extract_date(keys, "成交额[")

    sh_amt = sz_amt = 0.0
    for r in rows:
        code = r.get("指数代码", "")
        amt = float(r.get(amt_key, 0) or 0)
        if "000001" in str(code):
            sh_amt = amt / 1e8
        elif "399001" in str(code):
            sz_amt = amt / 1e8

    return {
        "trade_date": trade_date,
        "sh_amount": round(sh_amt, 2),
        "sz_amount": round(sz_amt, 2),
        "total": round(sh_amt + sz_amt, 2),
    }


def _parse_sector_rows(rows: list[dict]) -> tuple[str, list[dict]]:
    """解析板块数据，返回 (trade_date, [{bk_code, bk_name, change_pct, amount, net_inflow}])。

    金额单位统一为亿元。
    """
    if not rows:
        return datetime.now().strftime("%Y-%m-%d"), []

    keys = list(rows[0].keys())
    chg_key = _find_key(keys, "涨跌幅[")
    amt_key = _find_key(keys, "成交额[")
    inf_key = _find_key(keys, "主力净买入额[")

    trade_date = _extract_date(keys, "涨跌幅[") if chg_key else datetime.now().strftime("%Y-%m-%d")

    parsed: list[dict] = []
    for r in rows:
        try:
            chg_val = float(r.get(chg_key) or 0) if chg_key else 0.0
        except (ValueError, TypeError):
            chg_val = 0.0
        try:
            amt_val = float(r.get(amt_key) or 0) if amt_key else 0.0
        except (ValueError, TypeError):
            amt_val = 0.0
        try:
            inf_val = float(r.get(inf_key) or 0) if inf_key else 0.0
        except (ValueError, TypeError):
            inf_val = 0.0

        parsed.append({
            "bk_code": r.get("指数代码", ""),
            "bk_name": r.get("指数简称", ""),
            "index_type": r.get("指数类型", ""),
            "change_pct": round(chg_val, 4),
            "amount": round(amt_val / 1e8, 2),
            "net_inflow": round(inf_val / 1e8, 2),
        })

    return trade_date, parsed


def get_sectors(sector_type: str = "industry", trade_date: str | None = None) -> list[dict]:
    """获取板块数据（同花顺问财，自动分页）。

    Args:
        sector_type: 'industry' (行业板块) | 'concept' (概念板块)
        trade_date: 交易日，None 则返回最新交易日数据。

    Returns:
        [{bk_code, bk_name, change_pct, amount, net_inflow}]
        所有金额字段统一为亿元。
    """
    label_map = {
        "industry": ("行业板块", "行业板块 涨跌幅 成交额 主力净流入额 排名"),
        "concept": ("概念板块", "概念板块 涨跌幅 成交额 主力净流入额 排名"),
    }
    if sector_type not in label_map:
        raise ValueError(f"不支持的板块类型: {sector_type}，可选: {list(label_map.keys())}")

    label, query = label_map[sector_type]
    if trade_date:
        query = f"{trade_date} {query}"
    rows = iwencai_paginate(query, label=label)
    _trade_date, parsed = _parse_sector_rows(rows)
    # 过滤掉 "同花顺行业指数" 类型的数据
    parsed = [s for s in parsed if s.get("index_type") != "同花顺行业指数"]
    return parsed
