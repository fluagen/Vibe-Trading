"""同花顺 iwencai OpenAPI 会话层 — skill ID 轮转 + 限流。

每个 IWENCAI_SKILL_ID 每天限流 100 次调用。本模块维护多个 skill ID，
在单个 ID 耗尽时自动切换到下一个，突破每日 100 次限制。

使用方式:
  export IWENCAI_API_KEY="your-key"
  export IWENCAI_SKILL_IDS="id1,id2,id3"   # 逗号分隔，可选
  # 或设置单个 skill ID:
  export IWENCAI_SKILL_ID="hithink-sector-selector"

限流:
  通过 VIBE_TRADING_IWENCAI_OPENAPI_MIN_INTERVAL 控制请求间隔（默认 1.0s），
  复用 backtest.loaders._http.HostThrottle 进程级限流基础设施。
"""

from __future__ import annotations

import json
import logging
import os
import secrets
import time
import urllib.error
import urllib.request
from pathlib import Path

from backtest.loaders._http import HostThrottle, resolve_min_interval

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

IWENCAI_API_URL = "https://openapi.iwencai.com/v1/query2data"
IWENCAI_SKILL_VERSION = "1.0.0"
IWENCAI_DEFAULT_SKILL_ID = "hithink-sector-selector"

# HostThrottle bucket name for the openapi.iwencai.com endpoint.
_THROTTLE_BUCKET = "iwencai-openapi"
_DEFAULT_MIN_INTERVAL = 1.0

# Shared process-wide throttle gate (dedicated instance for this endpoint).
_THROTTLE = HostThrottle()

# ---------------------------------------------------------------------------
# Custom exception for retry-aware pagination
# ---------------------------------------------------------------------------


class SkillExhaustedError(RuntimeError):
    """当前 skill ID 配额已耗尽，已自动切换到下一个 ID，调用方可重试。"""


# ---------------------------------------------------------------------------
# Skill ID rotation state (process memory, resets on restart = next day)
# ---------------------------------------------------------------------------

_skill_ids: list[str] = []
_current_skill_index: int = 0
_exhausted: set[int] = set()


def _read_env(key: str) -> str:
    """读取环境变量，优先 os.environ，其次 agent/.env 文件。"""
    # 1. os.environ
    val = os.environ.get(key, "")
    if val:
        return val

    # 2. agent/.env 文件回退
    env_path = Path(__file__).resolve().parent.parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith(f"{key}="):
                val = line.split("=", 1)[1].strip().strip('"').strip("'")
                if val:
                    os.environ[key] = val  # 缓存供后续调用
                    return val
    return ""


def _init_skill_ids() -> None:
    """从环境变量解析 skill ID 列表。

    优先级:
      1. IWENCAI_SKILL_IDS (逗号分隔多个 ID)   — 支持 .env 文件
      2. IWENCAI_SKILL_ID    (单个 ID)          — 支持 .env 文件
      3. 默认值 hithink-sector-selector
    """
    global _skill_ids, _current_skill_index, _exhausted

    # 1. 逗号分隔列表
    raw = _read_env("IWENCAI_SKILL_IDS")
    if raw:
        _skill_ids = [s.strip() for s in raw.split(",") if s.strip()]

    # 2. 单值 fallback
    if not _skill_ids:
        single = _read_env("IWENCAI_SKILL_ID")
        if single.strip():
            _skill_ids = [single.strip()]

    # 3. 默认值
    if not _skill_ids:
        _skill_ids = [IWENCAI_DEFAULT_SKILL_ID]

    _current_skill_index = 0
    _exhausted = set()


def _get_skill_id() -> str:
    """返回当前活跃的 skill ID，首次调用时自动初始化。"""
    if not _skill_ids:
        _init_skill_ids()
    return _skill_ids[_current_skill_index]


def _handle_rate_limit() -> None:
    """标记当前 skill ID 耗尽，切换到下一个。全部耗尽则抛 RuntimeError。"""
    global _current_skill_index
    if not _skill_ids:
        _init_skill_ids()

    _exhausted.add(_current_skill_index)
    logger.warning(
        "问财 skill ID '%s' 今日配额已用完（%d/%d 个已耗尽）",
        _skill_ids[_current_skill_index],
        len(_exhausted),
        len(_skill_ids),
    )

    # 寻找下一个未耗尽的 skill ID（循环遍历）
    for i in range(len(_skill_ids)):
        idx = (_current_skill_index + 1 + i) % len(_skill_ids)
        if idx not in _exhausted:
            _current_skill_index = idx
            logger.info("切换到 skill ID: '%s'", _skill_ids[_current_skill_index])
            time.sleep(5)  # 防反爬：切换间隔不低于 5s
            return

    raise RuntimeError(
        f"所有问财 skill ID 今日配额已用完（共 {len(_skill_ids)} 个）。"
        "请明天再试或添加更多 skill ID: export IWENCAI_SKILL_IDS=\"id1,id2,id3\""
    )


# ---------------------------------------------------------------------------
# API key resolution
# ---------------------------------------------------------------------------


def _get_api_key() -> str:
    """获取 iwencai API key（支持 os.environ + agent/.env 文件）。"""
    key = _read_env("IWENCAI_API_KEY")
    if key:
        return key

    raise RuntimeError(
        "IWENCAI_API_KEY 未设置。\n"
        "获取指引: https://www.iwencai.com/skillhub → 登录 → Skill → 复制 API Key。\n"
        "设置方式:\n"
        "  1. agent/.env 中添加: IWENCAI_API_KEY=your-key\n"
        "  2. 或 shell export: export IWENCAI_API_KEY=\"your-key\""
    )


# ---------------------------------------------------------------------------
# Core iwencai query (with throttling + skill rotation)
# ---------------------------------------------------------------------------


def iwencai_query(query: str, page: int = 1, limit: int = 200) -> dict:
    """调用问财 OpenAPI 单次查询，返回 {datas, code_count, chunks_info}。

    自动处理:
      - 限流: 通过 HostThrottle 确保请求间隔不低于配置值
      - 轮转: 401 配额耗尽时自动切换 skill ID 并抛出 SkillExhaustedError

    Raises:
        SkillExhaustedError: 当前 skill ID 已耗尽，已自动切换，调用方可重试。
        RuntimeError: 其他 HTTP/网络错误，或全部 skill ID 均已耗尽。
    """
    api_key = _get_api_key()
    skill_id = _get_skill_id()
    trace_id = secrets.token_hex(32)

    # 限流等待
    min_interval = resolve_min_interval(
        "VIBE_TRADING_IWENCAI_OPENAPI_MIN_INTERVAL", _DEFAULT_MIN_INTERVAL
    )
    _THROTTLE.wait(_THROTTLE_BUCKET, min_interval)

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
        "X-Claw-Skill-Id": skill_id,
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
        if e.code == 401 and "次数已用完" in body:
            _handle_rate_limit()
            raise SkillExhaustedError(
                f"skill ID '{skill_id}' 今日配额已用完，已自动切换到下一个"
            )
        raise RuntimeError(f"问财 API HTTP {e.code}: {body[:200]}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"问财 API 网络错误: {e.reason}")


# ---------------------------------------------------------------------------
# Pagination (with retry on skill exhaustion)
# ---------------------------------------------------------------------------


def query_sector_members(bk_code_or_name: str) -> list[dict[str, object]]:
    """Query sector constituent stocks via THS iwencai — rich fields.

    Returns:
        List of ``{"code": "600519", "name": "贵州茅台", "price": 33.0,
        "change_pct": 2.01, "concepts": ["黄金概念",...],
        "industries": ["有色金属","贵金属",...]}``.
        ``code`` is normalized to bare 6-digit.

    Raises:
        RuntimeError: If no members are found for the given code/name.
    """
    name = bk_code_or_name
    if "." in bk_code_or_name:
        rows = iwencai_paginate(bk_code_or_name, max_pages=1, label="板块查找")
        if rows:
            name = rows[0].get("指数简称", bk_code_or_name)

    query = f"{name} 成分股 股票代码 股票简称 最新价 最新涨跌幅 所属概念 所属同花顺行业"
    rows = iwencai_paginate(query, max_pages=5, label="成份股")

    # Resolve dynamic field keys (iwencai may suffix with date like "最新价[20260710]")
    _keys: list[str] = []
    if rows:
        _keys = list(set().union(*(r.keys() for r in rows)))

    def _f(prefix: str) -> str | None:
        for k in _keys:
            if k.startswith(prefix):
                return k
        return None

    price_key = _f("最新价") or "最新价"
    chg_key = _f("最新涨跌幅") or "最新涨跌幅"
    concepts_key = _f("所属概念") or "所属概念"
    industry_key = _f("所属同花顺行业") or "所属同花顺行业"

    members: list[dict[str, object]] = []
    for r in rows:
        stock_code = r.get("股票代码", "") or r.get("代码", "")
        stock_name = r.get("股票简称", "") or r.get("名称", "")
        if not stock_code:
            continue
        # Normalize to bare 6-digit code.
        code = str(stock_code).strip()
        if "." in code:
            code = code.split(".")[0]
        code = code.zfill(6)

        try:
            price = float(r.get(price_key, 0) or 0)
        except (ValueError, TypeError):
            price = 0.0
        try:
            change_pct = float(r.get(chg_key, 0) or 0)
        except (ValueError, TypeError):
            change_pct = 0.0

        concepts = r.get(concepts_key, []) or []
        if isinstance(concepts, str):
            concepts = [c.strip() for c in concepts.split(",") if c.strip()]
        industries = r.get(industry_key, []) or []
        if isinstance(industries, str):
            industries = [c.strip() for c in industries.split(",") if c.strip()]

        members.append({
            "code": code,
            "name": str(stock_name),
            "price": round(price, 2),
            "change_pct": round(change_pct, 4),
            "concepts": [str(c) for c in concepts],
            "industries": [str(c) for c in industries],
        })

    if not members:
        raise RuntimeError(
            f"未找到板块 {bk_code_or_name!r} 的成份股，请确认板块名称/代码是否正确"
        )

    return members


def iwencai_paginate(query: str, max_pages: int = 20, label: str = "") -> list[dict]:
    """分页获取全部结果。

    页面间等待 1s 防限流。当 skill ID 耗尽时自动切换并重试当前页，
    确保数据不丢失。全部 skill ID 耗尽时停止分页并记录错误。

    Args:
        query: 问财查询语句。
        max_pages: 最大分页数。
        label: 日志标签（如 "行业板块"、"概念板块"）。
    """
    all_rows: list[dict] = []
    page = 1
    while page <= max_pages:
        try:
            result = iwencai_query(query, page=page, limit=200)
        except SkillExhaustedError:
            # skill ID 已自动切换，重试当前页（不递增 page）
            logger.info("%s 第%d页: skill ID 已切换，重试当前页", label, page)
            continue
        except Exception as e:
            logger.warning("%s 第%d页失败: %s", label, page, e)
            page += 1
            continue

        datas = result.get("datas") or []
        code_count = int(result.get("code_count", 0))

        if not datas:
            break

        all_rows.extend(datas)

        if page * 200 >= code_count:
            break

        page += 1
        if page <= max_pages:
            time.sleep(1.0)

    return all_rows
