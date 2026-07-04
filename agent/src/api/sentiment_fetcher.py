"""THS iwencai OpenAPI 数据抓取 — 全市场成交额 + 板块数据。

从 a-stock-data/scripts/market_data.py 提取 THS 部分，
适配 Vibe-Trading 代码风格。所有金额字段统一为亿元。

前置条件:
  export IWENCAI_API_KEY="..."
"""

from __future__ import annotations

import json
import logging
import os
import re
import secrets
import time
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# iwencai OpenAPI constants
# ---------------------------------------------------------------------------

IWENCAI_API_URL = "https://openapi.iwencai.com/v1/query2data"
IWENCAI_SKILL_ID = "hithink-sector-selector"
IWENCAI_SKILL_VERSION = "1.0.0"


def _get_api_key() -> str:
    # 1. os.environ (shell export / settings UI push)
    key = os.environ.get("IWENCAI_API_KEY", "")
    if key:
        return key

    # 2. agent/.env (project-local dotenv, not auto-loaded by the server)
    env_path = Path(__file__).resolve().parent.parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("IWENCAI_API_KEY="):
                key = line.split("=", 1)[1].strip().strip('"').strip("'")
                if key:
                    os.environ["IWENCAI_API_KEY"] = key  # cache for next call
                    return key

    raise RuntimeError(
        "IWENCAI_API_KEY 未设置。\n"
        "获取指引: https://www.iwencai.com/skillhub → 登录 → Skill → 复制 API Key。\n"
        "设置方式:\n"
        "  1. agent/.env 中添加: IWENCAI_API_KEY=your-key\n"
        "  2. 或 shell export: export IWENCAI_API_KEY=\"your-key\""
    )


# ---------------------------------------------------------------------------
# Core iwencai query
# ---------------------------------------------------------------------------

def iwencai_query(query: str, page: int = 1, limit: int = 200) -> dict:
    """调用问财 OpenAPI 单次查询，返回 {datas, code_count, chunks_info}。"""
    api_key = _get_api_key()
    trace_id = secrets.token_hex(32)

    payload = json.dumps({
        "query": query,
        "page": str(page),
        "limit": str(limit),
        "is_cache": "1",
        "expand_index": "true",
    }).encode("utf-8")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "X-Claw-Call-Type": "normal",
        "X-Claw-Skill-Id": IWENCAI_SKILL_ID,
        "X-Claw-Skill-Version": IWENCAI_SKILL_VERSION,
        "X-Claw-Plugin-Id": "none",
        "X-Claw-Plugin-Version": "none",
        "X-Claw-Trace-Id": trace_id,
    }

    req = urllib.request.Request(IWENCAI_API_URL, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace") if e.fp else ""
        raise RuntimeError(f"问财 API HTTP {e.code}: {body[:200]}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"问财 API 网络错误: {e.reason}")


def iwencai_paginate(query: str, max_pages: int = 20, label: str = "") -> list[dict]:
    """分页获取全部结果（页面间等 1s 防限流）。"""
    all_rows: list[dict] = []
    for page in range(1, max_pages + 1):
        try:
            result = iwencai_query(query, page=page, limit=200)
        except Exception as e:
            logger.warning("%s 第%d页失败: %s", label, page, e)
            continue

        datas = result.get("datas") or []
        code_count = int(result.get("code_count", 0))

        if not datas:
            break

        all_rows.extend(datas)

        if page * 200 >= code_count:
            break

        if page < max_pages:
            time.sleep(1.0)

    return all_rows


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
