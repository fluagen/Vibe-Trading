#!/usr/bin/env python3
"""Screen all A-shares for 止跌K (bottom signal K-line) on a given date.

Usage:
    conda activate vibe-trading
    python agent/src/skills/up_trend_structure/screen_bottom_k.py [--date 2026-07-03] [--workers 20]

Dependencies: mootdx (for stock list), urllib (stdlib, for tencent API).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional, Tuple

import pandas as pd

# ---------------------------------------------------------------------------
# Stock list via mootdx
# ---------------------------------------------------------------------------


def get_a_share_list() -> pd.DataFrame:
    """Return DataFrame of all A-shares with columns: code, name, market (0=SZ, 1=SH)."""
    from mootdx.quotes import Quotes

    client = Quotes.factory(market="std")
    frames = []
    for m in [0, 1]:
        df = client.stocks(market=m)
        if df is not None and len(df) > 0:
            df = df.copy()
            df["market"] = m
            frames.append(df)
    if not frames:
        return pd.DataFrame(columns=["code", "name", "market"])
    return pd.concat(frames, ignore_index=True)


def _code_to_suffixed(code: str, market: int) -> Optional[str]:
    """Convert bare 6-digit code + market to suffixed form (e.g. 600519,1 → 600519.SH)."""
    code = str(code).strip().zfill(6)
    if market == 1:
        return f"{code}.SH"
    elif market == 0:
        return f"{code}.SZ"
    return None


# ---------------------------------------------------------------------------
# Tencent Finance API (free, no auth)
# ---------------------------------------------------------------------------

_TENCENT_URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
_TENCENT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://web.ifzq.gtimg.cn/",
}

# Columns in tencent response: date, open, close, high, low, volume
_KT_COLS = ["open", "close", "high", "low", "volume"]


def _tencent_code(suffixed: str) -> Optional[str]:
    """Convert 600519.SH → sh600519, 000001.SZ → sz000001, BJ → None."""
    parts = suffixed.upper().split(".")
    symbol, suffix = parts[0], parts[1] if len(parts) > 1 else ""
    if suffix == "SH":
        return f"sh{symbol}"
    if suffix == "SZ":
        return f"sz{symbol}"
    return None


def fetch_single_tencent(
    code: str, start_date: str, end_date: str
) -> Optional[pd.DataFrame]:
    """Fetch daily OHLCV for one A-stock via Tencent API.  Returns DataFrame or None."""
    tc = _tencent_code(code)
    if tc is None:
        return None

    url = f"{_TENCENT_URL}?param={tc},day,{start_date},{end_date},10,qfq"
    try:
        req = urllib.request.Request(url, headers=_TENCENT_HEADERS)
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8")
    except Exception:
        return None

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None

    stock_data = data.get("data", {})
    if not stock_data:
        return None
    stock_key = next(iter(stock_data), None)
    if not stock_key:
        return None

    klines = stock_data[stock_key].get("qfqday") or stock_data[stock_key].get("day")
    if not klines:
        return None

    rows = []
    for k in klines:
        if len(k) >= 6:
            try:
                rows.append({
                    "trade_date": k[0],
                    "open": float(k[1]),
                    "close": float(k[2]),
                    "high": float(k[3]),
                    "low": float(k[4]),
                    "volume": float(k[5]),
                })
            except (ValueError, TypeError):
                continue

    if not rows:
        return None

    df = pd.DataFrame(rows)
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    df = df.set_index("trade_date").sort_index()
    df = df[_KT_COLS]
    return df


# ---------------------------------------------------------------------------
# Main screener
# ---------------------------------------------------------------------------


def screen_date(
    target_date: str,
    workers: int = 20,
    min_volume_ratio: float = 1.5,
    max_stocks: int = 0,
) -> pd.DataFrame:
    """Screen all A-shares for 止跌K on target_date.

    Args:
        target_date: YYYY-MM-DD, e.g. "2026-07-03".
        workers: concurrent HTTP workers.
        min_volume_ratio: volume surge threshold (止跌K vol / prev vol).
        max_stocks: 0 = scan all; >0 = limit for quick test.

    Returns:
        DataFrame of matched stocks with columns:
        code, name, date, close, prev_close, volume, prev_volume, bottom_signal_k, state.
    """
    from src.skills.up_trend_structure.up_trend_structure import UpTrendStructure

    import datetime as _dt

    target_dt = _dt.datetime.strptime(target_date, "%Y-%m-%d")
    start_dt = target_dt - _dt.timedelta(days=10)
    start_date = start_dt.strftime("%Y-%m-%d")

    print(f"Fetching A-share stock list via mootdx...", file=sys.stderr)
    stock_list = get_a_share_list()
    print(f"Got {len(stock_list)} stocks", file=sys.stderr)

    if max_stocks > 0:
        stock_list = stock_list.head(max_stocks)

    # Build suffixed code list
    codes_info: List[Tuple[str, str]] = []  # (suffixed_code, name)
    for _, row in stock_list.iterrows():
        suffixed = _code_to_suffixed(str(row["code"]), int(row["market"]))
        if suffixed:
            codes_info.append((suffixed, str(row.get("name", ""))))

    print(
        f"Fetching OHLCV data for {len(codes_info)} stocks (workers={workers})...",
        file=sys.stderr,
    )

    detector = UpTrendStructure(volume_surge_ratio=min_volume_ratio)
    matched_rows: List[dict] = []
    fetched = 0
    failed = 0
    t0 = time.time()

    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_map = {
            executor.submit(
                fetch_single_tencent, code, start_date, target_date
            ): (code, name)
            for code, name in codes_info
        }

        for future in as_completed(future_map):
            code, name = future_map[future]
            try:
                df = future.result()
            except Exception:
                failed += 1
                continue

            if df is None or df.empty:
                failed += 1
                continue

            fetched += 1
            if fetched % 500 == 0:
                print(f"  {fetched}/{len(codes_info)} fetched...", file=sys.stderr)

            # Run detector
            try:
                states = detector.compute(df)
            except Exception:
                failed += 1
                continue

            # Check if bottom_signal_k on target_date
            target_ts = pd.Timestamp(target_date)
            if target_ts not in states.index:
                continue

            bsk = bool(states.loc[target_ts, "bottom_signal_k"])
            if not bsk:
                continue

            row = df.loc[target_ts]
            prev_idx = df.index.get_loc(target_ts) - 1
            prev_row = df.iloc[prev_idx] if prev_idx >= 0 else None

            matched_rows.append({
                "code": code,
                "name": name,
                "date": target_date,
                "close": float(row["close"]),
                "prev_close": float(prev_row["close"]) if prev_row is not None else None,
                "volume": float(row["volume"]),
                "prev_volume": float(prev_row["volume"]) if prev_row is not None else None,
                "bottom_signal_k": True,
                "state": str(states.loc[target_ts, "state"]),
            })

    elapsed = time.time() - t0
    print(
        f"Done in {elapsed:.1f}s: {fetched} fetched, {failed} failed, "
        f"{len(matched_rows)} matched",
        file=sys.stderr,
    )

    return pd.DataFrame(matched_rows)


def print_results(df: pd.DataFrame, output_format: str = "table"):
    """Print results in table or CSV format."""
    if df.empty:
        print("No stocks with 止跌K found.")
        return

    if output_format == "csv":
        df.to_csv(sys.stdout, index=False)
        return

    # Table format
    print(
        f"\n{'代码':<12} {'名称':<10} {'收盘':>8} {'前收':>8} "
        f"{'成交量':>12} {'前量':>12} {'状态':<14}"
    )
    print("-" * 80)
    for _, r in df.sort_values("volume", ascending=False).iterrows():
        print(
            f"{r['code']:<12} {r['name']:<10} {r['close']:>8.2f} "
            f"{r['prev_close']:>8.2f} "
            f"{r['volume']:>12.0f} {r['prev_volume']:>12.0f} "
            f"{r['state']:<14}"
        )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Screen A-shares for 止跌K (bottom signal K-line)"
    )
    parser.add_argument(
        "--date",
        default="2026-07-03",
        help="Target date YYYY-MM-DD (default: 2026-07-03)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=20,
        help="Concurrent HTTP workers (default: 20)",
    )
    parser.add_argument(
        "--format",
        choices=["table", "csv"],
        default="table",
        help="Output format (default: table)",
    )
    parser.add_argument(
        "--max-stocks",
        type=int,
        default=0,
        help="Limit to N stocks for quick test (0=all)",
    )
    parser.add_argument(
        "--volume-ratio",
        type=float,
        default=1.5,
        help="Volume surge ratio threshold (default: 1.5)",
    )
    args = parser.parse_args()

    df = screen_date(
        target_date=args.date,
        workers=args.workers,
        min_volume_ratio=args.volume_ratio,
        max_stocks=args.max_stocks,
    )
    print_results(df, output_format=args.format)


if __name__ == "__main__":
    main()
