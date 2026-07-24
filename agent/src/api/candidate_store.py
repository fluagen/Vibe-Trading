"""SQLite store for candidate stock watchlist.

Stores user-curated stocks with metadata for later backtesting.
The DB file lives at ``agent/data/candidates.db``.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import date
from pathlib import Path

from src.config import get_app_data_dir

_log = logging.getLogger(__name__)

_DB_PATH = get_app_data_dir() / "candidates.db"


class CandidateStore:
    """Persist candidate stocks in SQLite."""

    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = Path(db_path) if db_path else _DB_PATH
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_table()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _ensure_table(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS candidates (
                    code        TEXT PRIMARY KEY,
                    name        TEXT NOT NULL,
                    added_at    TEXT NOT NULL,
                    concepts    TEXT NOT NULL,
                    industries  TEXT NOT NULL
                )
                """
            )
            conn.commit()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def list_all(self) -> list[dict]:
        """Return all candidate stocks ordered by added_at descending."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT code, name, added_at, concepts, industries FROM candidates ORDER BY added_at DESC"
            ).fetchall()

        result: list[dict] = []
        for row in rows:
            result.append({
                "code": row["code"],
                "name": row["name"],
                "added_at": row["added_at"],
                "concepts": json.loads(row["concepts"]),
                "industries": json.loads(row["industries"]),
            })
        return result

    def upsert(
        self,
        code: str,
        name: str,
        concepts: list[str] | None = None,
        industries: list[str] | None = None,
    ) -> dict:
        """Insert or update a candidate stock. Returns the saved record."""
        added_at = date.today().isoformat()
        concepts_json = json.dumps(concepts or [], ensure_ascii=False)
        industries_json = json.dumps(industries or [], ensure_ascii=False)

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO candidates (code, name, added_at, concepts, industries)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(code) DO UPDATE SET
                    name = excluded.name,
                    added_at = excluded.added_at,
                    concepts = excluded.concepts,
                    industries = excluded.industries
                """,
                (code, name, added_at, concepts_json, industries_json),
            )
            conn.commit()

        _log.info("Upserted candidate: code=%s name=%s", code, name)
        return {
            "code": code,
            "name": name,
            "added_at": added_at,
            "concepts": concepts or [],
            "industries": industries or [],
        }

    def delete(self, code: str) -> bool:
        """Remove a candidate stock. Returns True if a row was deleted."""
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM candidates WHERE code = ?", (code,)
            )
            conn.commit()
            deleted = cursor.rowcount > 0

        if deleted:
            _log.info("Deleted candidate: code=%s", code)
        return deleted
