"""五月市场情绪数据回填脚本。

从 THS iwencai OpenAPI 逐日拉取 2026 年 5 月交易日数据，
写入 agent/data/market_data.db。全部 SKILL ID 配额耗尽时自动停止。

Usage:
    cd agent && python scripts/backfill_sentiment.py          # 执行回填
    cd agent && python scripts/backfill_sentiment.py --dry-run # 预览交易日
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
AGENT_DIR = HERE.parent
sys.path.insert(0, str(AGENT_DIR))

from src.api.sentiment_service import SentimentService


# ---------------------------------------------------------------------------
# May 2026 trading days (Mon-Fri, excluding Labor Day holiday May 1-5)
# ---------------------------------------------------------------------------
# May 1 (Fri) = Labor Day
# May 4 (Mon) = holiday
# May 5 (Tue) = holiday
# Trading resumes May 6 (Wed)
MAY_2026_TRADING_DAYS = [
    "2026-05-06", "2026-05-07", "2026-05-08",
    "2026-05-11", "2026-05-12", "2026-05-13", "2026-05-14", "2026-05-15",
    "2026-05-18", "2026-05-19", "2026-05-20", "2026-05-21", "2026-05-22",
    "2026-05-25", "2026-05-26", "2026-05-27", "2026-05-28", "2026-05-29",
]

EXCLUDE_DAYS = {"2026-05-01", "2026-05-04", "2026-05-05"}  # Labor Day


def run(dry_run: bool = False) -> None:
    service = SentimentService()
    success: list[str] = []
    failed: list[tuple[str, str]] = []
    skipped: list[str] = []

    print(f"=== 五月情绪数据回填 ===")
    print(f"交易日总数: {len(MAY_2026_TRADING_DAYS)}")
    print(f"排除非交易日 (五一假期): {sorted(EXCLUDE_DAYS)}")
    print()

    if dry_run:
        print("[DRY RUN] 仅预览，不实际调用 API:")
        for d in MAY_2026_TRADING_DAYS:
            dt = datetime.strptime(d, "%Y-%m-%d")
            weekday = ["一", "二", "三", "四", "五", "六", "日"][dt.weekday()]
            print(f"  {d} (周{weekday})")
        print()
        print("运行 python scripts/backfill_sentiment.py 开始回填。")
        return

    for i, trade_date in enumerate(MAY_2026_TRADING_DAYS, 1):
        dt = datetime.strptime(trade_date, "%Y-%m-%d")
        weekday = ["一", "二", "三", "四", "五", "六", "日"][dt.weekday()]
        print(f"[{i:2d}/{len(MAY_2026_TRADING_DAYS)}] {trade_date} (周{weekday}) ... ", end="", flush=True)

        try:
            result = service.collect(trade_date=trade_date)
        except RuntimeError as e:
            msg = str(e)
            if "所有问财 skill ID" in msg:
                print(f"🛑 配额耗尽，停止")
                skipped.extend(MAY_2026_TRADING_DAYS[i:])
                break
            print(f"❌ RuntimeError: {msg[:80]}")
            failed.append((trade_date, msg[:120]))
            continue
        except Exception as e:
            print(f"❌ {type(e).__name__}: {str(e)[:80]}")
            failed.append((trade_date, str(e)[:120]))
            continue

        if result.get("ok"):
            sectors = result.get("sectors_collected", {})
            elapsed = result.get("elapsed_seconds", 0)
            parts = [f"{k}:{v}" for k, v in sectors.items()]
            print(f"✅ {' | '.join(parts)} ({elapsed:.0f}s)")
            success.append(trade_date)
        else:
            error = result.get("error", "unknown")
            print(f"⚠️  {error[:60]}")
            failed.append((trade_date, error[:120]))

    # Summary
    print()
    print("=" * 50)
    print(f"回填完成: 成功 {len(success)}/{len(MAY_2026_TRADING_DAYS)}")
    if failed:
        print(f"失败 {len(failed)}:")
        for d, err in failed:
            print(f"  {d}: {err[:80]}")
    if skipped:
        print(f"跳过 {len(skipped)} (配额耗尽): {skipped[0]} ... {skipped[-1]}")
    print("=" * 50)


def main() -> None:
    dry_run = "--dry-run" in sys.argv or "--dry" in sys.argv
    run(dry_run=dry_run)


if __name__ == "__main__":
    main()
