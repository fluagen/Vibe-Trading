"""Business logic for opportunity pool — default pool loading, scan orchestration."""

from __future__ import annotations

from typing import Any

import pandas as pd

from src.api.watch_pool_store import WatchPoolStore


def _code_to_suffixed(code: str, market: int) -> str | None:
    code = str(code).strip().zfill(6)
    if market == 1:
        return f"{code}.SH"
    if market == 0:
        return f"{code}.SZ"
    return None


def load_default_pool(store: WatchPoolStore | None = None) -> dict[str, Any]:
    """Load CSI 300 + CSI 500 constituents via mootdx block data.

    Returns {'added': int, 'errors': [str]}.
    """
    if store is None:
        store = WatchPoolStore()
    store.ensure_tables()

    errors: list[str] = []
    items: list[dict[str, Any]] = []

    try:
        from mootdx.quotes import Quotes

        client = Quotes.factory(market="std")
        blocks = client.block()

        if blocks is None or blocks.empty:
            errors.append("mootdx block() returned no data")
            return {"added": 0, "errors": errors}

        # Build name map from full stock list
        name_map: dict[str, str] = {}
        stock_list = _get_a_share_list(client)
        if stock_list is not None and not stock_list.empty:
            for _, row in stock_list.iterrows():
                suffixed = _code_to_suffixed(str(row["code"]), int(row["market"]))
                if suffixed:
                    name_map[suffixed] = str(row.get("name", ""))

        target_blocks = ["沪深300", "中证500"]
        seen: set[str] = set()

        for _, row in blocks.iterrows():
            block_name = str(row.get("blockname", ""))
            if block_name not in target_blocks:
                continue

            raw_code = str(row.get("code", ""))
            if not raw_code or raw_code in seen:
                continue

            code_stripped = raw_code.strip()
            if code_stripped.startswith(("6", "5")):
                market = 1
            elif code_stripped.startswith(("0", "3", "2")):
                market = 0
            else:
                continue

            suffixed = _code_to_suffixed(code_stripped, market)
            if not suffixed:
                continue

            seen.add(raw_code)
            source = "csi300" if "300" in block_name else "csi500"
            name = name_map.get(suffixed, raw_code)

            items.append({
                "code": suffixed,
                "name": name,
                "market": "SH" if market == 1 else "SZ",
                "source": source,
            })

        if items:
            store.add_candidates(items)

    except ImportError:
        errors.append("mootdx not installed; run: pip install mootdx")
    except Exception as exc:
        errors.append(str(exc))

    return {"added": len(items), "errors": errors}


def _get_a_share_list(client) -> pd.DataFrame | None:
    frames = []
    for m in [0, 1]:
        df = client.stocks(market=m)
        if df is not None and len(df) > 0:
            df = df.copy()
            df["market"] = m
            frames.append(df)
    if not frames:
        return None
    return pd.concat(frames, ignore_index=True)
