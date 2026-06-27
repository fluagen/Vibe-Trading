#!/usr/bin/env python3
"""
northbound_flow.py — 同花顺北向资金实时流向 + 本地 CSV 自缓存

从 data.hexin.cn 获取沪深股通当日分钟级资金流向（含集合竞价时段），
并将每日收盘快照写入本地 CSV 缓存以积累历史数据。

已知行业性问题: eastmoney 全系北向数据自 2024-08 后净买额字段返回 NaN/0，
属上游断供。本脚本走同花顺 hsgtApi，数据完整可用。

用法:
    python northbound_flow.py [chart|history]

示例:
    python northbound_flow.py           # 实时分钟流向 + 缓存今日快照
    python northbound_flow.py chart     # 同上 + 最近20天历史摘要
    python northbound_flow.py history   # 仅显示缓存历史
"""

import sys
from datetime import date as _date
from pathlib import Path

import pandas as pd
import requests

HSGT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "Chrome/117.0.0.0 Safari/537.36"
    ),
    "Host": "data.hexin.cn",
    "Referer": "https://data.hexin.cn/",
}

CACHE_DIR = Path.home() / ".vibe-trading"
CACHE_FILE = CACHE_DIR / "hsgt_cache.csv"


# ---------------------------------------------------------------------------
# 数据获取
# ---------------------------------------------------------------------------

def hsgt_realtime() -> pd.DataFrame:
    """
    沪深股通当日实时分钟流向（含集合竞价 09:10–15:00，262 个时间点）。
    返回字段: time, hgt(沪股通累计净买入), sgt(深股通累计净买入)
    单位: 亿元
    """
    url = "https://data.hexin.cn/market/hsgtApi/method/dayChart/"
    r = requests.get(url, headers=HSGT_HEADERS, timeout=10)
    d = r.json()
    times = d.get("time", [])
    hgt = d.get("hgt", [])
    sgt = d.get("sgt", [])

    n = len(times)
    return pd.DataFrame({
        "time": times,
        "hgt_yi": hgt[:n] + [None] * (n - len(hgt)),
        "sgt_yi": sgt[:n] + [None] * (n - len(sgt)),
    })


# ---------------------------------------------------------------------------
# 本地 CSV 缓存
# ---------------------------------------------------------------------------

def _cache_path() -> Path:
    """北向资金本地 CSV 缓存路径"""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_FILE


def save_snapshot(date_str: str, hgt: float, sgt: float):
    """写入/更新当天北向收盘数据到 CSV"""
    path = _cache_path()
    rows: dict[str, str] = {}
    if path.exists():
        for line in path.read_text().strip().split("\n")[1:]:
            parts = line.split(",")
            if len(parts) == 3:
                rows[parts[0]] = line
    rows[date_str] = f"{date_str},{hgt},{sgt}"
    with open(path, "w") as f:
        f.write("date,hgt,sgt\n")
        for d in sorted(rows.keys()):
            f.write(rows[d] + "\n")


def load_history(n: int = 20) -> pd.DataFrame:
    """读取最近 N 天北向历史"""
    path = _cache_path()
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path)
    return df.tail(n)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "live"

    if mode == "history":
        # 仅显示缓存历史
        hist = load_history(20)
        if hist.empty:
            print("暂无历史缓存数据。请先运行一次实时查询以积累数据。")
        else:
            print("=== 北向资金历史（最近20天）===")
            print(f"{'日期':>12} {'沪股通(亿)':>12} {'深股通(亿)':>12} {'合计(亿)':>12}")
            print("-" * 50)
            for _, row in hist.iterrows():
                total = float(row["hgt"]) + float(row["sgt"])
                print(
                    f"{str(row['date']):>12} "
                    f"{float(row['hgt']):>+12.2f} "
                    f"{float(row['sgt']):>+12.2f} "
                    f"{total:>+12.2f}"
                )
        sys.exit(0)

    # live 模式: 获取实时分钟流向
    print("=== 北向资金实时分钟流向 ===")
    try:
        df = hsgt_realtime()
        print(f"分钟点数: {len(df)}")
        print()
        print("最近 10 个时间点:")
        print(f"{'时间':<10} {'沪股通(亿)':>12} {'深股通(亿)':>12} {'合计(亿)':>12}")
        print("-" * 50)
        for _, row in df.dropna().tail(10).iterrows():
            total = (row["hgt_yi"] or 0) + (row["sgt_yi"] or 0)
            print(
                f"{str(row['time']):<10} "
                f"{float(row['hgt_yi']):>+12.2f} "
                f"{float(row['sgt_yi']):>+12.2f} "
                f"{total:>+12.2f}"
            )

        # 自动缓存今日收盘数据
        if not df.empty:
            last = df.dropna().iloc[-1]
            today = _date.today().strftime("%Y-%m-%d")
            save_snapshot(today, last["hgt_yi"], last["sgt_yi"])
            print(f"\n已缓存今日 ({today}) 收盘快照: "
                  f"沪股通={last['hgt_yi']:.2f}亿 深股通={last['sgt_yi']:.2f}亿")

    except Exception as e:
        print(f"获取实时数据失败: {e}")
        print("提示: 非交易时段可能无数据，请查看历史缓存。")
        sys.exit(1)

    # chart 模式: 额外打印历史摘要
    if mode == "chart":
        hist = load_history(20)
        if not hist.empty:
            print()
            print("=== 历史缓存（最近 10 天）===")
            for _, row in hist.tail(10).iterrows():
                total = float(row["hgt"]) + float(row["sgt"])
                bar = "↑" if total > 0 else "↓"
                print(
                    f"  {row['date']}  "
                    f"沪={float(row['hgt']):>+8.2f}  "
                    f"深={float(row['sgt']):>+8.2f}  "
                    f"合计={total:>+8.2f} {bar}"
                )
