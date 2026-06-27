#!/usr/bin/env python3
"""
hot_stocks_research.py — 同花顺当日热点强势股 + 题材归因分析

从同花顺 zx.10jqka.com.cn 获取当日强势股列表，包含每只股票的
人工运营题材标签 (reason)，解答"哪些走强"和"为什么走强"两个核心问题。

用法:
    python hot_stocks_research.py [日期]

示例:
    python hot_stocks_research.py                  # 今天
    python hot_stocks_research.py 2026-06-20       # 指定日期
"""

import sys
from datetime import date as _date

import pandas as pd
import requests

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/117.0.0.0 Safari/537.36"

# 同花顺热点字段重命名映射
_FIELD_RENAME = {
    "name": "名称",
    "code": "代码",
    "reason": "题材归因",
    "close": "收盘价",
    "zhangdie": "涨跌额",
    "zhangfu": "涨幅%",
    "huanshou": "换手率%",
    "chengjiaoe": "成交额",
    "chengjiaoliang": "成交量",
    "ddejingliang": "大单净量",
    "market": "市场",
}


# ---------------------------------------------------------------------------
# 数据获取
# ---------------------------------------------------------------------------

def ths_hot_stocks(date: str | None = None) -> pd.DataFrame:
    """
    同花顺当日强势股归因。
    date: 'YYYY-MM-DD' 格式，None=今天
    返回 DataFrame，含每只股票的题材标签 (reason)。

    实测: 73ms 拿到 ~125 只 + 完整字段
    """
    if date is None:
        date = _date.today().strftime("%Y-%m-%d")

    url = (
        f"http://zx.10jqka.com.cn/event/api/getharden/"
        f"date/{date}/orderby/date/orderway/desc/charset/GBK/"
    )
    headers = {"User-Agent": UA}
    r = requests.get(url, headers=headers, timeout=10)
    data = r.json()
    if data.get("errocode", 0) != 0:
        raise RuntimeError(f"同花顺热点错误: {data.get('errormsg', '')}")

    rows = data.get("data") or []
    df = pd.DataFrame(rows)
    if df.empty:
        return df

    # 字段重命名（中文友好）
    df = df.rename(columns=_FIELD_RENAME)
    return df


# ---------------------------------------------------------------------------
# 分析输出
# ---------------------------------------------------------------------------

def print_hot_analysis(df: pd.DataFrame, top_n: int = 20):
    """打印热点分析报告"""
    if df.empty:
        print("当日无强势股数据（可能非交易日）")
        return

    print(f"当日强势股总数: {len(df)} 只")
    print()

    # 按涨幅降序排列
    top = df.sort_values("涨幅%", ascending=False).head(top_n)

    print(f"=== 涨幅 TOP {top_n} ===")
    print(f"{'排名':<4} {'代码':<8} {'名称':<8} {'涨幅%':>7} {'换手%':>7} {'题材归因'}")
    print("-" * 90)
    for rank, (_, row) in enumerate(top.iterrows(), 1):
        reason = row.get("题材归因", "") or ""
        # 截断过长的题材标签
        if len(reason) > 50:
            reason = reason[:48] + ".."
        print(
            f"{rank:<4} "
            f"{row.get('代码', ''):<8} "
            f"{row.get('名称', ''):<8} "
            f"{row.get('涨幅%', 0):>7.2f} "
            f"{row.get('换手率%', 0):>7.2f} "
            f"{reason}"
        )

    # 题材热度统计
    print()
    print("=== 题材热度统计（按出现频次） ===")
    theme_counts: dict[str, int] = {}
    for _, row in df.iterrows():
        reason = row.get("题材归因", "")
        if not reason or pd.isna(reason):
            continue
        # 同花顺 reason 以 "+" 分隔多个题材标签
        for tag in str(reason).split("+"):
            tag = tag.strip()
            if tag:
                theme_counts[tag] = theme_counts.get(tag, 0) + 1

    for tag, count in sorted(theme_counts.items(), key=lambda x: -x[1])[:15]:
        bar = "#" * min(count, 30)
        print(f"  {tag:<20} {count:>3}只 {bar}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    target_date = sys.argv[1] if len(sys.argv) > 1 else None

    print(f"查询日期: {target_date or _date.today().strftime('%Y-%m-%d')}")
    print()

    try:
        df = ths_hot_stocks(target_date)
        print_hot_analysis(df)
    except Exception as e:
        print(f"获取热点数据失败: {e}")
        sys.exit(1)
