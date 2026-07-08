"""Test sentiment_fetcher — index_type parsing and filtering."""

from __future__ import annotations

from unittest import mock

from src.api.sentiment_fetcher import _parse_sector_rows, get_sectors


def test_parse_sector_rows_includes_index_type():
    """_parse_sector_rows should extract index_type from API response."""
    rows = [
        {
            "指数代码": "BK0001",
            "指数简称": "测试概念板块",
            "指数类型": "同花顺概念指数",
            "涨跌幅[20260701]": "1.50",
            "成交额[20260701]": "10000000000",
            "主力净买入额[20260701]": "500000000",
        },
    ]

    trade_date, parsed = _parse_sector_rows(rows)

    assert len(parsed) == 1
    assert parsed[0]["bk_code"] == "BK0001"
    assert parsed[0]["bk_name"] == "测试概念板块"
    assert parsed[0]["index_type"] == "同花顺概念指数"


def test_get_sectors_filters_out_tonghuashun_industry_index():
    """get_sectors should filter out rows where index_type == '同花顺行业指数'."""
    mock_rows = [
        {
            "指数代码": "BK0001",
            "指数简称": "概念板块A",
            "指数类型": "同花顺概念指数",
            "涨跌幅[20260701]": "1.50",
            "成交额[20260701]": "10000000000",
            "主力净买入额[20260701]": "500000000",
        },
        {
            "指数代码": "BK0002",
            "指数简称": "行业板块B",
            "指数类型": "同花顺行业指数",
            "涨跌幅[20260701]": "2.00",
            "成交额[20260701]": "20000000000",
            "主力净买入额[20260701]": "1000000000",
        },
        {
            "指数代码": "BK0003",
            "指数简称": "二级行业C",
            "指数类型": "同花顺二级行业指数",
            "涨跌幅[20260701]": "-1.00",
            "成交额[20260701]": "5000000000",
            "主力净买入额[20260701]": "-200000000",
        },
    ]

    with mock.patch("src.api.sentiment_fetcher.iwencai_paginate", return_value=mock_rows):
        result = get_sectors("industry", "2026-07-01")

    codes = [r["bk_code"] for r in result]
    assert "BK0001" in codes, "概念指数 should be kept"
    assert "BK0003" in codes, "二级行业指数 should be kept"
    assert "BK0002" not in codes, "同花顺行业指数 should be filtered out"
    assert len(result) == 2


def test_parse_sector_rows_handles_sparse_columns():
    """主力净买入额仅出现在第二行（稀疏列），第一行没有该列。"""
    rows = [
        {
            "指数代码": "BK0001",
            "指数简称": "板块A",
            "指数类型": "同花顺概念指数",
            "涨跌幅[20260701]": "1.50",
            "成交额[20260701]": "10000000000",
            # 注意：第一行没有 主力净买入额
        },
        {
            "指数代码": "BK0002",
            "指数简称": "板块B",
            "指数类型": "同花顺概念指数",
            "涨跌幅[20260701]": "2.00",
            "成交额[20260701]": "20000000000",
            "主力净买入额[20260701]": "1000000000",  # 仅第二行有
        },
    ]

    trade_date, parsed = _parse_sector_rows(rows)

    assert len(parsed) == 2
    # 第一行：无主力净买入额 → 0
    assert parsed[0]["bk_code"] == "BK0001"
    assert parsed[0]["change_pct"] == 1.5
    assert parsed[0]["amount"] == 100.0
    assert parsed[0]["net_inflow"] == 0.0
    # 第二行：有主力净买入额 → 正确解析
    assert parsed[1]["bk_code"] == "BK0002"
    assert parsed[1]["change_pct"] == 2.0
    assert parsed[1]["amount"] == 200.0
    assert parsed[1]["net_inflow"] == 10.0  # 10亿/1e8
