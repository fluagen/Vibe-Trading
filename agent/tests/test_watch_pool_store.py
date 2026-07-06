"""Test WatchPoolStore — schema creation, idempotency, and CRUD."""

from __future__ import annotations

from src.api.watch_pool_store import WatchPoolStore


class TestEnsureTables:
    """Schema creation and idempotency."""

    def test_creates_three_tables(self):
        """ensure_tables should create candidate_pool, watchlist, and scan_jobs."""
        store = WatchPoolStore(db_path=":memory:")
        store.ensure_tables()

        tables = store.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        names = [r["name"] for r in tables]

        assert "candidate_pool" in names
        assert "watchlist" in names
        assert "scan_jobs" in names
        store.close()

    def test_ensure_tables_is_idempotent(self):
        """Calling ensure_tables multiple times should not raise."""
        store = WatchPoolStore(db_path=":memory:")
        store.ensure_tables()
        store.ensure_tables()
        store.ensure_tables()

        tables = store.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        names = [r["name"] for r in tables]
        assert "candidate_pool" in names
        store.close()


class TestCandidatePoolSchema:
    """candidate_pool table structure."""

    def test_candidate_pool_columns(self):
        """candidate_pool should have code PK, name, market, source, added_at."""
        store = WatchPoolStore(db_path=":memory:")
        store.ensure_tables()

        info = store.conn.execute("PRAGMA table_info('candidate_pool')").fetchall()
        cols = {row["name"]: row for row in info}

        assert "code" in cols
        assert cols["code"]["pk"] == 1
        assert "name" in cols
        assert cols["name"]["notnull"] == 1
        assert "market" in cols
        assert cols["market"]["notnull"] == 1
        assert "source" in cols
        assert cols["source"]["notnull"] == 1
        assert "added_at" in cols
        assert cols["added_at"]["notnull"] == 1
        store.close()


class TestWatchlistSchema:
    """watchlist table structure."""

    def test_watchlist_composite_pk(self):
        """watchlist PK should be (code, strategy_name)."""
        store = WatchPoolStore(db_path=":memory:")
        store.ensure_tables()

        info = store.conn.execute("PRAGMA table_info('watchlist')").fetchall()
        pk_cols = [row["name"] for row in info if row["pk"] > 0]

        assert "code" in pk_cols
        assert "strategy_name" in pk_cols
        store.close()

    def test_watchlist_has_snapshot_columns(self):
        """watchlist must have state_at_add and position_at_add for frozen snapshots."""
        store = WatchPoolStore(db_path=":memory:")
        store.ensure_tables()

        info = store.conn.execute("PRAGMA table_info('watchlist')").fetchall()
        cols = {row["name"]: row for row in info}

        assert "state_at_add" in cols
        assert "position_at_add" in cols
        assert "added_at" in cols
        assert "current_state" in cols
        assert "current_position" in cols
        store.close()

    def test_watchlist_reserved_columns(self):
        """Reserved columns for future features should exist."""
        store = WatchPoolStore(db_path=":memory:")
        store.ensure_tables()

        info = store.conn.execute("PRAGMA table_info('watchlist')").fetchall()
        cols = {row["name"]: row for row in info}

        assert "score_at_add" in cols
        assert "score_details" in cols
        assert "current_score" in cols
        assert "tags" in cols
        assert "notes" in cols
        assert "ai_analysis" in cols
        store.close()


class TestScanJobsSchema:
    """scan_jobs table structure."""

    def test_scan_jobs_columns(self):
        """scan_jobs should have job_id PK and status/strategy tracking columns."""
        store = WatchPoolStore(db_path=":memory:")
        store.ensure_tables()

        info = store.conn.execute("PRAGMA table_info('scan_jobs')").fetchall()
        cols = {row["name"]: row for row in info}

        assert "job_id" in cols
        assert cols["job_id"]["pk"] == 1
        assert "status" in cols
        assert "strategy" in cols
        assert "total_codes" in cols
        assert "done_codes" in cols
        assert "result" in cols
        store.close()


class TestCandidateCRUD:
    """candidate_pool CRUD operations."""

    def test_list_candidates_empty(self):
        store = WatchPoolStore(db_path=":memory:")
        store.ensure_tables()
        assert store.list_candidates() == []
        store.close()

    def test_add_and_list_candidates(self):
        store = WatchPoolStore(db_path=":memory:")
        store.ensure_tables()

        added = store.add_candidates([
            {"code": "600519.SH", "name": "贵州茅台", "market": "SH", "source": "manual"},
            {"code": "000001.SZ", "name": "平安银行", "market": "SZ", "source": "manual"},
        ])
        assert added == 2

        rows = store.list_candidates()
        assert len(rows) == 2
        assert rows[0]["code"] == "000001.SZ" or rows[0]["code"] == "600519.SH"
        store.close()

    def test_add_duplicate_upserts(self):
        store = WatchPoolStore(db_path=":memory:")
        store.ensure_tables()

        store.add_candidates([
            {"code": "600519.SH", "name": "贵州茅台", "market": "SH", "source": "manual"},
        ])
        store.add_candidates([
            {"code": "600519.SH", "name": "贵州茅台", "market": "SH", "source": "csi300"},
        ])
        rows = store.list_candidates()
        assert len(rows) == 1
        assert rows[0]["source"] == "csi300"  # upserted
        store.close()

    def test_remove_candidate(self):
        store = WatchPoolStore(db_path=":memory:")
        store.ensure_tables()
        store.add_candidates([
            {"code": "600519.SH", "name": "贵州茅台", "market": "SH", "source": "manual"},
        ])

        removed = store.remove_candidate("600519.SH")
        assert removed is True
        assert store.list_candidates() == []

        assert store.remove_candidate("999999.SZ") is False
        store.close()


class TestWatchlistCRUD:
    def test_list_watchlist_empty(self):
        store = WatchPoolStore(db_path=":memory:")
        store.ensure_tables()
        assert store.list_watchlist() == []
        store.close()

    def test_add_and_list_watchlist(self):
        store = WatchPoolStore(db_path=":memory:")
        store.ensure_tables()

        store.add_to_watchlist(
            code="600519.SH",
            name="贵州茅台",
            strategy_name="up_trend_structure",
            state_at_add="forming",
            position_at_add=0.33,
            scan_job_id="job-001",
        )

        rows = store.list_watchlist()
        assert len(rows) == 1
        assert rows[0]["code"] == "600519.SH"
        assert rows[0]["state_at_add"] == "forming"
        assert rows[0]["position_at_add"] == 0.33
        assert rows[0]["strategy_name"] == "up_trend_structure"
        assert "added_at" in rows[0]
        store.close()

    def test_add_duplicate_upserts_watchlist(self):
        store = WatchPoolStore(db_path=":memory:")
        store.ensure_tables()

        store.add_to_watchlist("600519.SH", "贵州茅台", "up_trend_structure", "forming", 0.33, "job-001")
        store.add_to_watchlist("600519.SH", "贵州茅台", "up_trend_structure", "up_phase", 0.67, "job-002")

        rows = store.list_watchlist()
        assert len(rows) == 1
        assert rows[0]["state_at_add"] == "up_phase"  # upserted
        assert rows[0]["position_at_add"] == 0.67
        store.close()

    def test_remove_from_watchlist(self):
        store = WatchPoolStore(db_path=":memory:")
        store.ensure_tables()

        store.add_to_watchlist("600519.SH", "test", "up_trend_structure", "forming", 0.33, "job-001")
        removed = store.remove_from_watchlist("600519.SH")
        assert removed is True
        assert store.list_watchlist() == []
        assert store.remove_from_watchlist("999999.SZ") is False
        store.close()

    def test_update_current_signal(self):
        store = WatchPoolStore(db_path=":memory:")
        store.ensure_tables()

        store.add_to_watchlist("600519.SH", "test", "up_trend_structure", "forming", 0.33, "job-001")
        store.update_current_signal("600519.SH", "up_phase", 0.67)
        rows = store.list_watchlist()

        # Snapshot unchanged
        assert rows[0]["state_at_add"] == "forming"
        assert rows[0]["position_at_add"] == 0.33
        # Current updated
        assert rows[0]["current_state"] == "up_phase"
        assert rows[0]["current_position"] == 0.67
        assert rows[0]["current_updated"] is not None
        store.close()
