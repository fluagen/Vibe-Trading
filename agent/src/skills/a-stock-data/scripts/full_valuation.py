#!/usr/bin/env python3
"""
full_valuation.py — 单票完整估值分析

组合腾讯实时行情 + 同花顺一致预期EPS，输出前向PE、PEG、PE消化时间等
估值指标。适用于 A 股成长股的快速估值判断。

用法:
    python full_valuation.py <股票代码> [股票代码...]

示例:
    python full_valuation.py 688017
    python full_valuation.py 688017 300308 300476 002463
"""

import math
import sys
import urllib.request
from io import StringIO

import pandas as pd
import requests

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


# ---------------------------------------------------------------------------
# 核心估值辅助函数
# ---------------------------------------------------------------------------

def forward_pe(price: float, eps_forecast: float) -> float:
    """前向PE = 当前股价 / 未来年度一致预期EPS"""
    if eps_forecast <= 0:
        return float("inf")
    return price / eps_forecast


def pe_digestion(current_pe: float, cagr: float, target_pe: float = 30) -> float:
    """
    当前PE消化到目标PE需要多少年。
    target_pe 固定30x（A股成长股合理估值锚点）。
    cagr: 用 下一年EPS / 当年EPS - 1
    """
    if current_pe <= target_pe:
        return 0.0
    if cagr <= 0:
        return float("inf")
    return math.log(current_pe / target_pe) / math.log(1 + cagr)


def calc_peg(pe: float, cagr: float) -> float:
    """
    PEG = 前向PE / (CAGR * 100)
    PEG < 1   → 便宜
    PEG 1-1.5 → 合理
    PEG > 1.5 → 贵
    """
    if cagr <= 0:
        return float("inf")
    return pe / (cagr * 100)


# ---------------------------------------------------------------------------
# 数据获取函数
# ---------------------------------------------------------------------------

def tencent_quote(code: str) -> dict:
    """获取单只股票腾讯实时行情"""
    if code.startswith(("6", "9")):
        prefix = "sh"
    elif code.startswith("8"):
        prefix = "bj"
    else:
        prefix = "sz"

    url = f"https://qt.gtimg.cn/q={prefix}{code}"
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "Mozilla/5.0")
    resp = urllib.request.urlopen(req, timeout=10)
    data = resp.read().decode("gbk")
    vals = data.split('"')[1].split("~")

    return {
        "name": vals[1],
        "price": float(vals[3]) if vals[3] else 0,
        "mcap_yi": float(vals[44]) if vals[44] else 0,
        "pe_ttm": float(vals[39]) if vals[39] else 0,
        "pb": float(vals[46]) if vals[46] else 0,
    }


def ths_eps_forecast(code: str) -> pd.DataFrame:
    """
    同花顺机构一致预期EPS。
    直连 basic.10jqka.com.cn，解析HTML表格。
    返回 DataFrame: 年度, 预测机构数, 最小值, 均值, 最大值
    "均值" = 机构一致预期EPS
    """
    url = f"https://basic.10jqka.com.cn/new/{code}/worth.html"
    headers = {
        "User-Agent": UA,
        "Referer": "https://basic.10jqka.com.cn/",
    }
    r = requests.get(url, headers=headers, timeout=15)
    r.encoding = "gbk"
    dfs = pd.read_html(StringIO(r.text))
    for df in dfs:
        cols = [str(c) for c in df.columns]
        if any("每股收益" in c or "均值" in c for c in cols):
            return df
    return dfs[0] if dfs else pd.DataFrame()


# ---------------------------------------------------------------------------
# 综合估值函数
# ---------------------------------------------------------------------------

def full_valuation(code: str) -> dict:
    """单票完整估值分析"""
    # 1. 腾讯实时行情
    q = tencent_quote(code)
    price = q["price"]
    mcap = q["mcap_yi"]
    pe_ttm = q["pe_ttm"]
    pb = q["pb"]

    # 2. 机构一致预期（直连同花顺）
    df = ths_eps_forecast(code)
    eps_cur = eps_next = None
    analyst_count = 0
    if not df.empty and len(df.columns) >= 3:
        try:
            for i, row in df.iterrows():
                if i == 0:
                    eps_cur = float(row.iloc[2]) if pd.notna(row.iloc[2]) else None
                    analyst_count = int(row.iloc[1]) if pd.notna(row.iloc[1]) else 0
                elif i == 1:
                    eps_next = float(row.iloc[2]) if pd.notna(row.iloc[2]) else None
        except (ValueError, IndexError):
            pass

    # 3. 估值指标
    pe_fwd = price / eps_cur if eps_cur else float("inf")
    cagr = (eps_next / eps_cur - 1) if (eps_cur and eps_next) else 0
    peg = calc_peg(pe_fwd, cagr)
    digest = pe_digestion(pe_fwd, cagr)

    return {
        "name": q["name"],
        "price": price,
        "mcap_yi": mcap,
        "pe_ttm": pe_ttm,
        "pb": pb,
        "eps_cur": eps_cur,
        "eps_next": eps_next,
        "pe_fwd": round(pe_fwd, 1) if eps_cur else None,
        "cagr_pct": round(cagr * 100, 0) if cagr else None,
        "peg": round(peg, 2) if peg != float("inf") else None,
        "digest_years": round(digest, 1),
        "analyst_count": analyst_count,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _peg_label(peg: float | None) -> str:
    """PEG 中文标签"""
    if peg is None:
        return "N/A"
    if peg < 1:
        return "便宜"
    if peg <= 1.5:
        return "合理"
    return "贵"


def _digest_label(years: float) -> str:
    """消化时间中文标签"""
    if years == 0:
        return "已合理"
    if years <= 2:
        return "快(<2年)"
    if years <= 4:
        return "中(2-4年)"
    return "慢(>4年)"


if __name__ == "__main__":
    codes = sys.argv[1:] if len(sys.argv) > 1 else ["688017"]

    print(f"{'名称':<8} {'代码':<8} {'股价':>8} {'PE_TTM':>8} {'PE_FWD':>8} {'PEG':>7} {'消化':>8} {'覆盖':>4}")
    print("-" * 70)

    for code in codes:
        try:
            r = full_valuation(code)
            print(
                f"{r['name']:<8} {code:<8} {r['price']:>8.2f} {r['pe_ttm']:>8.1f} "
                f"{r['pe_fwd'] or 'N/A':>8} {r['peg'] or 'N/A':>7} "
                f"{r['digest_years']:>6.1f}年 {r['analyst_count']:>4}家"
            )
        except Exception as e:
            print(f"{'ERROR':<8} {code:<8} {'—':>8} 失败: {e}")
