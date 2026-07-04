"""Test SentimentStore — schema, upsert, and query behavior."""

from __future__ import annotations

from src.api.sentiment_store import SentimentStore


def test_table_schema_has_index_type():
    """market_sector table should have index_type column and (trade_date, bk_code) PK."""
    store = SentimentStore(db_path=":memory:")
    store.ensure_tables()

    # Verify columns
    info = store.conn.execute("PRAGMA table_info('market_sector')").fetchall()
    cols = {row["name"]: row for row in info}

    assert "index_type" in cols, "index_type column must exist"
    assert cols["index_type"]["notnull"] == 1, "index_type must be NOT NULL"
    assert cols["index_type"]["dflt_value"] == "''", "index_type default must be ''"

    assert "sector_type" in cols, "sector_type column must still exist"

    # Verify PK: should be (trade_date, bk_code), not containing sector_type
    pk_cols = [row["name"] for row in info if row["pk"] > 0]
    assert "trade_date" in pk_cols, "trade_date must be in PK"
    assert "bk_code" in pk_cols, "bk_code must be in PK"
    assert "sector_type" not in pk_cols, "sector_type must NOT be in PK"

    store.close()


def test_upsert_sectors_stores_index_type():
    """upsert_sectors should store index_type for each row."""
    store = SentimentStore(db_path=":memory:")
    store.ensure_tables()

    rows = [
        {
            "bk_code": "BK0001",
            "bk_name": "测试概念板块",
            "index_type": "同花顺概念指数",
            "change_pct": 1.5,
            "amount": 100.0,
            "net_inflow": 5.0,
        },
        {
            "bk_code": "BK0002",
            "bk_name": "测试行业板块",
            "index_type": "同花顺二级行业指数",
            "change_pct": -0.5,
            "amount": 200.0,
            "net_inflow": -3.0,
        },
    ]

    store.upsert_sectors("2026-07-01", "industry", rows)

    # Read back directly to verify index_type was stored
    result = store.conn.execute(
        "SELECT bk_code, index_type FROM market_sector WHERE trade_date = ? ORDER BY bk_code",
        ("2026-07-01",),
    ).fetchall()

    assert len(result) == 2
    assert dict(result[0]) == {"bk_code": "BK0001", "index_type": "同花顺概念指数"}
    assert dict(result[1]) == {"bk_code": "BK0002", "index_type": "同花顺二级行业指数"}

    store.close()


def test_get_sectors_returns_index_type():
    """get_sectors() should include index_type in returned rows."""
    store = SentimentStore(db_path=":memory:")
    store.ensure_tables()

    rows = [
        {
            "bk_code": "BK0001",
            "bk_name": "测试板块",
            "index_type": "同花顺概念指数",
            "change_pct": 1.5,
            "amount": 100.0,
            "net_inflow": 5.0,
        },
    ]
    store.upsert_sectors("2026-07-01", "industry", rows)

    result = store.get_sectors("2026-07-01", sector_type="industry")
    assert len(result) == 1
    assert "index_type" in result[0], "get_sectors must return index_type"
    assert result[0]["index_type"] == "同花顺概念指数"

    store.close()


def test_get_sector_history_returns_index_type():
    """get_sector_history() should include index_type in returned rows."""
    store = SentimentStore(db_path=":memory:")
    store.ensure_tables()

    rows = [
        {
            "bk_code": "BK0001",
            "bk_name": "测试板块",
            "index_type": "同花顺概念指数",
            "change_pct": 1.5,
            "amount": 100.0,
            "net_inflow": 5.0,
        },
    ]
    store.upsert_sectors("2026-07-01", "industry", rows)

    result = store.get_sector_history("BK0001", "industry")
    assert len(result) == 1
    assert "index_type" in result[0], "get_sector_history must return index_type"
    assert result[0]["index_type"] == "同花顺概念指数"

    store.close()
