#!/usr/bin/env python3
"""
announcement_search.py — 巨潮公告全文检索 + 批量查询

直连 cninfo.com.cn（深交所官方披露平台），支持动态 orgId 映射、
任意股票代码公告检索、批量多股票查询。

用法:
    python announcement_search.py <股票代码> [股票代码...]

示例:
    python announcement_search.py 688017                 # 单票查询
    python announcement_search.py 688017 601318 601398  # 多票批量查询
"""

import sys
from datetime import datetime

import requests

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

# 模块级缓存：股票代码 → orgId 映射
_ORGID_MAP: dict[str, str] = {}


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def _ts_to_date(ts) -> str:
    """巨潮 announcementTime: Unix 毫秒 → 日期字符串"""
    if isinstance(ts, (int, float)):
        return datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d")
    return str(ts)[:10] if ts else ""


def _lookup_orgid(code: str) -> str:
    """查股票真实 orgId，优先动态查官方映射表，失败回退硬编码。"""
    global _ORGID_MAP
    if not _ORGID_MAP:
        try:
            r = requests.get(
                "http://www.cninfo.com.cn/new/data/szse_stock.json",
                headers={"User-Agent": UA},
                timeout=15,
            )
            _ORGID_MAP = {
                s["code"]: s["orgId"]
                for s in r.json().get("stockList", [])
            }
        except Exception as e:
            print(f"[WARN] 巨潮 orgId 映射表拉取失败，回退硬编码规则: {e}")

    org = _ORGID_MAP.get(code)
    if org:
        return org

    # fallback 硬编码规则
    if code.startswith("6"):
        return f"gssh0{code}"
    elif code.startswith("8") or code.startswith("4"):
        return f"gsbj0{code}"
    return f"gssz0{code}"


# ---------------------------------------------------------------------------
# 公告检索
# ---------------------------------------------------------------------------

def cninfo_announcements(code: str, page_size: int = 30) -> list[dict]:
    """
    巨潮公告全文检索。
    返回: [{title, type, date, url}]
    """
    url = "https://www.cninfo.com.cn/new/hisAnnouncement/query"
    org_id = _lookup_orgid(code)

    payload = {
        "stock": f"{code},{org_id}",
        "tabName": "fulltext",
        "pageSize": str(page_size),
        "pageNum": "1",
        "column": "",
        "category": "",
        "plate": "",
        "seDate": "",
        "searchkey": "",
        "secid": "",
        "sortName": "",
        "sortType": "",
        "isHLtitle": "true",
    }
    headers = {
        "User-Agent": UA,
        "Content-Type": "application/x-www-form-urlencoded",
        "Referer": "https://www.cninfo.com.cn/new/disclosure",
        "Origin": "https://www.cninfo.com.cn",
    }
    r = requests.post(url, data=payload, headers=headers, timeout=15)
    d = r.json()

    rows = []
    for item in d.get("announcements", []) or []:
        rows.append({
            "title": item.get("announcementTitle", ""),
            "type": item.get("announcementTypeName", ""),
            "date": _ts_to_date(item.get("announcementTime")),
            "url": (
                "https://www.cninfo.com.cn/new/disclosure/detail?"
                f"annoId={item.get('announcementId', '')}"
            ),
        })
    return rows


def search_and_download(code: str, keyword: str | None = None,
                        page_size: int = 30) -> list[dict]:
    """
    公告检索 + 可选关键词过滤。
    keyword: 若提供，仅返回标题包含该关键词的公告。
    """
    anns = cninfo_announcements(code, page_size=page_size)
    if keyword:
        kw = keyword.lower()
        anns = [a for a in anns if kw in a["title"].lower()]
    return anns


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    codes = sys.argv[1:] if len(sys.argv) > 1 else ["688017"]

    for code in codes:
        print(f"\n{'=' * 70}")
        print(f"  股票: {code}  |  orgId: {_lookup_orgid(code)}")
        print(f"{'=' * 70}")

        try:
            anns = cninfo_announcements(code)
            if not anns:
                print("  (无公告记录)")
                continue

            # 按日期降序
            anns.sort(key=lambda x: x["date"], reverse=True)

            for a in anns[:15]:
                print(f"  {a['date']}  [{a['type']}]  {a['title'][:60]}")
            if len(anns) > 15:
                print(f"  ... 共 {len(anns)} 条，仅显示最近 15 条")

            # 公告类型统计
            type_counts: dict[str, int] = {}
            for a in anns:
                t = a["type"] or "其他"
                type_counts[t] = type_counts.get(t, 0) + 1
            print(f"\n  公告类型分布: ", end="")
            for t, c in sorted(type_counts.items(), key=lambda x: -x[1])[:5]:
                print(f"[{t} x{c}]  ", end="")
            print()

        except Exception as e:
            print(f"  [ERROR] 查询失败: {e}")
