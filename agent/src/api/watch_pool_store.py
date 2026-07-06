"""SQLite store for opportunity pool — candidate_pool, watchlist, scan_jobs.

Follows the same patterns as sentiment_store.py:
  - Lazy sqlite3 connection with WAL mode
  - Row factory for dict-like access
  - ensure_tables() for idempotent schema creation
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

_DEFAULT_DB_PATH = str(Path(__file__).resolve().parent.parent.parent / "data" / "watch_pool.db")

# ---------------------------------------------------------------------------
# DDL
# ---------------------------------------------------------------------------

CREATE_CANDIDATE_POOL = """
CREATE TABLE IF NOT EXISTS candidate_pool (
    code     TEXT PRIMARY KEY,
    name     TEXT NOT NULL,
    market   TEXT NOT NULL,
    source   TEXT NOT NULL,
    added_at TEXT NOT NULL
);
"""

CREATE_WATCHLIST = """
CREATE TABLE IF NOT EXISTS watchlist (
    code             TEXT NOT NULL,
    name             TEXT NOT NULL,
    strategy_name    TEXT NOT NULL,
    state_at_add     TEXT NOT NULL,
    position_at_add  REAL NOT NULL,
    score_at_add     REAL,
    score_details    TEXT,
    added_at         TEXT NOT NULL,
    scan_job_id      TEXT,
    current_state    TEXT,
    current_position REAL,
    current_score    REAL,
    current_updated  TEXT,
    notes            TEXT DEFAULT '',
    tags             TEXT DEFAULT '[]',
    ai_analysis      TEXT,
    PRIMARY KEY (code, strategy_name)
);
"""

CREATE_SCAN_JOBS = """
CREATE TABLE IF NOT EXISTS scan_jobs (
    job_id       TEXT PRIMARY KEY,
    status       TEXT NOT NULL,
    strategy     TEXT NOT NULL,
    total_codes  INTEGER NOT NULL,
    done_codes   INTEGER DEFAULT 0,
    current_code TEXT,
    created_at   TEXT NOT NULL,
    finished_at  TEXT,
    error        TEXT,
    result       TEXT
);
"""


class WatchPoolStore:
    """SQLite persistence for candidate pool, watchlist, and scan jobs."""

    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = db_path or _DEFAULT_DB_PATH
        os.makedirs(Path(self.db_path).parent, exist_ok=True)
        self._conn: sqlite3.Connection | None = None

    # -- connection management -------------------------------------------------

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=OFF")
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # -- schema ----------------------------------------------------------------

    def ensure_tables(self) -> None:
        self.conn.execute(CREATE_CANDIDATE_POOL)
        self.conn.execute(CREATE_WATCHLIST)
        self.conn.execute(CREATE_SCAN_JOBS)
        self.conn.commit()

    # -- candidate pool CRUD ---------------------------------------------------

    @staticmethod
    def _now() -> str:
        return datetime.now().isoformat(timespec="seconds")

    def list_candidates(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT code, name, market, source, added_at FROM candidate_pool ORDER BY code"
        ).fetchall()
        return [dict(r) for r in rows]

    def add_candidates(self, items: list[dict[str, Any]]) -> int:
        """Insert or replace candidate rows. Returns count of items added."""
        now = self._now()
        records = [
            {
                "code": item["code"],
                "name": item["name"],
                "market": item["market"],
                "source": item.get("source", "manual"),
                "added_at": now,
            }
            for item in items
        ]
        self.conn.executemany(
            "INSERT OR REPLACE INTO candidate_pool (code, name, market, source, added_at) "
            "VALUES (:code, :name, :market, :source, :added_at)",
            records,
        )
        self.conn.commit()
        return len(records)

    def remove_candidate(self, code: str) -> bool:
        cursor = self.conn.execute("DELETE FROM candidate_pool WHERE code = ?", (code,))
        self.conn.commit()
        return cursor.rowcount > 0

    # -- watchlist CRUD -------------------------------------------------------

    def list_watchlist(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT code, name, strategy_name, state_at_add, position_at_add, "
            "score_at_add, score_details, added_at, scan_job_id, "
            "current_state, current_position, current_score, current_updated, "
            "notes, tags, ai_analysis "
            "FROM watchlist ORDER BY added_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def add_to_watchlist(
        self,
        code: str,
        name: str,
        strategy_name: str,
        state_at_add: str,
        position_at_add: float,
        scan_job_id: str = "",
    ) -> None:
        now = self._now()
        self.conn.execute(
            "INSERT OR REPLACE INTO watchlist "
            "(code, name, strategy_name, state_at_add, position_at_add, added_at, scan_job_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (code, name, strategy_name, state_at_add, position_at_add, now, scan_job_id),
        )
        self.conn.commit()

    def remove_from_watchlist(self, code: str) -> bool:
        cursor = self.conn.execute("DELETE FROM watchlist WHERE code = ?", (code,))
        self.conn.commit()
        return cursor.rowcount > 0

    def update_current_signal(
        self, code: str, state: str, position: float
    ) -> None:
        now = self._now()
        self.conn.execute(
            "UPDATE watchlist SET current_state = ?, current_position = ?, current_updated = ? "
            "WHERE code = ?",
            (state, position, now, code),
        )
        self.conn.commit()
