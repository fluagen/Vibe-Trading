#!/usr/bin/env python3
"""
consensus_research.py — 同花顺机构一致预期EPS 多股票对比

从同花顺 basic.10jqka.com.cn 获取机构一致预期EPS数据，
支持多只股票横向对比，输出覆盖机构数、EPS均值、隐含增速等。

用法:
    python consensus_research.py <股票代码> [股票代码...]

示例:
    python consensus_research.py 688017                          # 单票
    python consensus_research.py 688017 300308 300476 002463    # 多票对比
"""

import sys
from io import StringIO

import pandas as pd
import requests

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


# ---------------------------------------------------------------------------
# 数据获取
# ---------------------------------------------------------------------------

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
    # 找含"每股收益"的表格
    for df in dfs:
        cols = [str(c) for c in df.columns]
        if any("每股收益" in c or "均值" in c for c in cols):
            return df
    # fallback: 返回第一个表
    return dfs[0] if dfs else pd.DataFrame()


def parse_eps_forecast(df: pd.DataFrame) -> dict:
    """
    从同花顺 EPS 预测 DataFrame 中提取关键数据。
    返回:
        {
            "years": [年份列表],
            "analyst_counts": [机构数列表],
            "eps_means": [一致预期EPS列表],
            "has_data": bool,
        }
    """
    result = {
        "years": [],
        "analyst_counts": [],
        "eps_means": [],
        "has_data": False,
    }
    if df.empty or len(df.columns) < 3:
        return result

    try:
        for _, row in df.iterrows():
            year_val = row.iloc[0]
            if pd.isna(year_val):
                continue
            try:
                year = int(float(str(year_val)))
            except (ValueError, TypeError):
                continue
            count = int(row.iloc[1]) if pd.notna(row.iloc[1]) else 0
            eps = float(row.iloc[2]) if pd.notna(row.iloc[2]) else None

            result["years"].append(year)
            result["analyst_counts"].append(count)
            result["eps_means"].append(eps)
            result["has_data"] = True
    except (ValueError, IndexError):
        pass

    return result


def multi_stock_consensus(codes: list[str]) -> pd.DataFrame:
    """
    多只股票机构一致预期对比。
    返回 DataFrame: 代码, 是否有覆盖, 当前年度, 当前EPS, 次年EPS, 隐含增速%, 覆盖机构数
    """
    rows = []
    for code in codes:
        try:
            df = ths_eps_forecast(code)
            parsed = parse_eps_forecast(df)

            if not parsed["has_data"] or len(parsed["years"]) < 1:
                rows.append({
                    "代码": code, "有覆盖": False,
                    "当前年度": None, "EPS_当前": None,
                    "EPS_次年": None, "隐含增速%": None,
                    "覆盖机构数": 0,
                })
                continue

            eps_cur = parsed["eps_means"][0]
            eps_next = parsed["eps_means"][1] if len(parsed["eps_means"]) > 1 else None
            cagr = None
            if eps_cur and eps_next and eps_cur > 0:
                cagr = round((eps_next / eps_cur - 1) * 100, 1)

            rows.append({
                "代码": code,
                "有覆盖": True,
                "当前年度": parsed["years"][0],
                "EPS_当前": eps_cur,
                "EPS_次年": eps_next,
                "隐含增速%": cagr,
                "覆盖机构数": parsed["analyst_counts"][0] if parsed["analyst_counts"] else 0,
            })
        except Exception as e:
            rows.append({
                "代码": code, "有覆盖": False,
                "当前年度": None, "EPS_当前": None,
                "EPS_次年": None, "隐含增速%": None,
                "覆盖机构数": 0,
                "error": str(e),
            })

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    codes = sys.argv[1:] if len(sys.argv) > 1 else ["688017"]

    print("=== 同花顺机构一致预期EPS 多股票对比 ===\n")

    df = multi_stock_consensus(codes)

    # 按覆盖机构数降序排列
    df = df.sort_values("覆盖机构数", ascending=False)

    print(f"{'代码':<8} {'覆盖':<6} {'当前年度':>8} {'当前EPS':>10} {'次年EPS':>10} {'隐含增速%':>10} {'机构数':>6}")
    print("-" * 70)

    for _, row in df.iterrows():
        if not row["有覆盖"]:
            err = row.get("error", "无机构覆盖")
            print(f"{row['代码']:<8} {'否':<6} {'N/A':>8} {'N/A':>10} {'N/A':>10} {'N/A':>10} {'0':>6}  ({err})")
        else:
            eps_c = f"{row['EPS_当前']:.2f}" if row["EPS_当前"] else "N/A"
            eps_n = f"{row['EPS_次年']:.2f}" if row["EPS_次年"] else "N/A"
            cagr_s = f"{row['隐含增速%']:.1f}%" if row["隐含增速%"] is not None else "N/A"
            print(
                f"{row['代码']:<8} {'是':<6} "
                f"{str(row['当前年度']):>8} "
                f"{eps_c:>10} {eps_n:>10} "
                f"{cagr_s:>10} "
                f"{row['覆盖机构数']:>6}"
            )

    # 汇总
    covered = df["有覆盖"].sum()
    print(f"\n共 {len(codes)} 只股票，{covered} 只有机构覆盖，"
          f"{len(codes) - covered} 只无覆盖。")
    if covered < 3 and covered > 0:
        print("⚠ 覆盖机构数 < 3 的标的需谨慎对待预测数据。")
