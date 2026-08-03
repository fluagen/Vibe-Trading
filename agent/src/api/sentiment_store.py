"""SQLite 存储层 — market_total + market_sector 两张表的 CRUD。

数据仅存原始值，所有衍生指标（拥挤度、资金偏好）由 sentiment_service 动态计算。
数据库路径默认 agent/data/market_data.db。
"""

from __future__ import annotations

import logging
import os
import shutil
import sqlite3
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from src.config import get_app_data_dir

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_DB_PATH = str(get_app_data_dir() / "market_data.db")

_VALID_SECTOR_TYPES = ("industry", "concept")

CREATE_MARKET_TOTAL = """
CREATE TABLE IF NOT EXISTS market_total (
    trade_date     TEXT PRIMARY KEY,
    total_amount   REAL NOT NULL,
    sh_amount      REAL NOT NULL,
    sz_amount      REAL NOT NULL,
    collected_at   TEXT NOT NULL
);
"""

CREATE_MARKET_SECTOR = """
CREATE TABLE IF NOT EXISTS market_sector (
    trade_date     TEXT NOT NULL,
    sector_type    TEXT NOT NULL,
    bk_code        TEXT NOT NULL,
    bk_name        TEXT NOT NULL,
    index_type     TEXT NOT NULL DEFAULT '',
    change_pct     REAL,
    amount         REAL,
    net_inflow     REAL,
    collected_at   TEXT NOT NULL,
    PRIMARY KEY (trade_date, bk_code)
);
"""

CREATE_SECTOR_MEMBERS = """
CREATE TABLE IF NOT EXISTS sector_members (
    bk_code       TEXT NOT NULL,
    bk_name       TEXT NOT NULL,
    sector_type   TEXT NOT NULL,
    stock_code    TEXT NOT NULL,
    stock_name    TEXT NOT NULL,
    collected_at  TEXT NOT NULL,
    PRIMARY KEY (bk_code, stock_code)
);
"""

UPSERT_MARKET_TOTAL = """
INSERT OR REPLACE INTO market_total
    (trade_date, total_amount, sh_amount, sz_amount, collected_at)
VALUES
    (:trade_date, :total_amount, :sh_amount, :sz_amount, :collected_at);
"""

UPSERT_MARKET_SECTOR = """
INSERT OR REPLACE INTO market_sector
    (trade_date, sector_type, bk_code, bk_name, index_type, change_pct, amount, net_inflow, collected_at)
VALUES
    (:trade_date, :sector_type, :bk_code, :bk_name, :index_type, :change_pct, :amount, :net_inflow, :collected_at);
"""

# ---------------------------------------------------------------------------
# Store class
# ---------------------------------------------------------------------------


class SentimentStore:
    """SQLite 持久化存储，管理 market_total 和 market_sector 两张表。"""

    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = db_path or _DEFAULT_DB_PATH
        os.makedirs(Path(self.db_path).parent, exist_ok=True)
        self._conn: sqlite3.Connection | None = None

    # -- connection management -------------------------------------------------

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = self._open_connection()
        return self._conn

    def _open_connection(self) -> sqlite3.Connection:
        """Open a SQLite connection with integrity check and auto-recovery."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=OFF")

        # Integrity check on first open — fast path for healthy DBs
        if not self._check_integrity(conn):
            logger.warning("Database corruption detected at %s, attempting recovery...", self.db_path)
            conn.close()
            self._recover_from_corruption()
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=OFF")
            # Re-verify after recovery
            if not self._check_integrity(conn):
                logger.error("Recovery failed — database remains corrupt. Recreating from scratch.")
                conn.close()
                self._recreate_database()
                conn = sqlite3.connect(self.db_path)
                conn.row_factory = sqlite3.Row
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA foreign_keys=OFF")

        return conn

    @staticmethod
    def _check_integrity(conn: sqlite3.Connection) -> bool:
        """Run PRAGMA quick_check — returns True if database is healthy."""
        try:
            result = conn.execute("PRAGMA quick_check").fetchone()
            return result is not None and result[0] == "ok"
        except sqlite3.DatabaseError:
            return False

    def _recover_from_corruption(self) -> None:
        """Attempt to salvage data from a corrupt database using sqlite3 .recover.

        Backs up the corrupt file, recovers what it can, and replaces the
        database with the recovered version.  Tables that could not be recovered
        are left empty but structurally valid.
        """
        backup_path = f"{self.db_path}.corrupted-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        shutil.copy2(self.db_path, backup_path)
        logger.info("Corrupt database backed up to %s", backup_path)

        # Run sqlite3 CLI .recover to salvage data
        try:
            result = subprocess.run(
                ["sqlite3", self.db_path, ".recover"],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode != 0 or not result.stdout.strip():
                raise RuntimeError(f"sqlite3 .recover failed: {result.stderr[:500]}")
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            logger.error("Cannot run sqlite3 CLI for recovery: %s", exc)
            self._recreate_database()
            return

        # Rebuild into a new database
        recovered_sql = result.stdout
        temp_db = self.db_path + ".recovering"
        try:
            rebuild_result = subprocess.run(
                ["sqlite3", temp_db],
                input=recovered_sql, capture_output=True, text=True, timeout=30,
            )
            if rebuild_result.returncode != 0:
                raise RuntimeError(f"Rebuild failed: {rebuild_result.stderr[:500]}")
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            logger.error("Cannot rebuild recovered database: %s", exc)
            if os.path.exists(temp_db):
                os.remove(temp_db)
            self._recreate_database()
            return

        # Verify the recovered database
        recovered_conn = sqlite3.connect(temp_db)
        recovered_conn.row_factory = sqlite3.Row
        if not self._check_integrity(recovered_conn):
            recovered_conn.close()
            os.remove(temp_db)
            logger.error("Recovered database still corrupt — recreating from scratch")
            self._recreate_database()
            return

        # Log recovery stats
        for table in ("market_total", "market_sector", "sector_members"):
            try:
                count = recovered_conn.execute(
                    f"SELECT COUNT(*) FROM {table}"
                ).fetchone()[0]
                logger.info("Recovered %s: %d rows", table, count)
            except sqlite3.DatabaseError:
                logger.warning("Recovered table %s is still unreadable", table)

        recovered_conn.close()

        # Atomically replace the corrupt database
        os.replace(temp_db, self.db_path)
        logger.info("Database recovered successfully from %s", backup_path)

    def _recreate_database(self) -> None:
        """Drop and recreate the database from scratch when recovery is impossible."""
        if os.path.exists(self.db_path):
            backup_path = f"{self.db_path}.corrupted-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
            shutil.copy2(self.db_path, backup_path)
            logger.warning("Corrupt database backed up to %s, recreating empty", backup_path)
            os.remove(self.db_path)
        # Initialise an empty database
        conn = sqlite3.connect(self.db_path)
        conn.execute(CREATE_MARKET_TOTAL)
        conn.execute(CREATE_MARKET_SECTOR)
        conn.execute(CREATE_SECTOR_MEMBERS)
        conn.commit()
        conn.close()
        logger.info("Empty database created at %s — data must be re-collected", self.db_path)

    def close(self) -> None:
        if self._conn is not None:
            try:
                # Checkpoint WAL so the main DB file is consistent on disk
                self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            except sqlite3.DatabaseError:
                pass
            self._conn.close()
            self._conn = None

    # -- schema ----------------------------------------------------------------

    def ensure_tables(self) -> None:
        self.conn.execute(CREATE_MARKET_TOTAL)
        self.conn.execute(CREATE_MARKET_SECTOR)
        self.conn.execute(CREATE_SECTOR_MEMBERS)
        self.conn.commit()

    # -- write ----------------------------------------------------------------

    def upsert_market_total(
        self,
        trade_date: str,
        total: float,
        sh: float,
        sz: float,
        collected_at: str | None = None,
    ) -> None:
        collected_at = collected_at or datetime.now().isoformat(timespec="seconds")
        self.conn.execute(
            UPSERT_MARKET_TOTAL,
            {
                "trade_date": trade_date,
                "total_amount": total,
                "sh_amount": sh,
                "sz_amount": sz,
                "collected_at": collected_at,
            },
        )
        self.conn.commit()

    def upsert_sectors(
        self,
        trade_date: str,
        sector_type: str,
        rows: list[dict[str, Any]],
        collected_at: str | None = None,
    ) -> None:
        collected_at = collected_at or datetime.now().isoformat(timespec="seconds")
        records = [
            {
                "trade_date": trade_date,
                "sector_type": sector_type,
                "bk_code": r["bk_code"],
                "bk_name": r["bk_name"],
                "index_type": r.get("index_type", ""),
                "change_pct": r.get("change_pct"),
                "amount": r.get("amount"),
                "net_inflow": r.get("net_inflow"),
                "collected_at": collected_at,
            }
            for r in rows
        ]
        self.conn.executemany(UPSERT_MARKET_SECTOR, records)
        self.conn.commit()

    # -- read: market_total ----------------------------------------------------

    def get_market_total(self, trade_date: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT trade_date, total_amount, sh_amount, sz_amount, collected_at "
            "FROM market_total WHERE trade_date = ?",
            (trade_date,),
        ).fetchone()
        if row is None:
            return None
        return dict(row)

    def get_latest_trading_day(self) -> str | None:
        row = self.conn.execute(
            "SELECT MAX(trade_date) FROM market_total"
        ).fetchone()
        return row[0] if row else None

    def get_adjacent_trading_days(self, trade_date: str) -> tuple[str | None, str | None]:
        """返回指定日期前后相邻的交易日。

        Args:
            trade_date: 当前交易日，YYYY-MM-DD。

        Returns:
            (prev_trade_date, next_trade_date) — 无前/后数据时对应位置为 None。
            next_trade_date 若超过今天则返回 None。
        """
        from datetime import date

        prev_row = self.conn.execute(
            "SELECT MAX(trade_date) FROM market_total WHERE trade_date < ?",
            (trade_date,),
        ).fetchone()
        next_row = self.conn.execute(
            "SELECT MIN(trade_date) FROM market_total WHERE trade_date > ?",
            (trade_date,),
        ).fetchone()
        prev_date: str | None = prev_row[0] if prev_row else None
        next_date: str | None = next_row[0] if next_row else None
        # 不返回未来日期
        today = date.today().isoformat()
        if next_date and next_date > today:
            next_date = None
        return prev_date, next_date

    # -- read: market_sector ---------------------------------------------------

    def get_sectors(
        self,
        trade_date: str,
        sector_type: str | None = None,
        order_by: str = "amount",
        order_dir: str = "desc",
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        valid_sort = {"amount", "net_inflow", "change_pct"}
        sort_col = order_by if order_by in valid_sort else "amount"
        direction = "DESC" if order_dir == "desc" else "ASC"

        where = "WHERE trade_date = ?"
        params: list[Any] = [trade_date]
        if sector_type:
            where += " AND sector_type = ?"
            params.append(sector_type)

        sql = (
            f"SELECT trade_date, sector_type, bk_code, bk_name, "
            f"index_type, change_pct, amount, net_inflow, collected_at "
            f"FROM market_sector {where} "
            f"ORDER BY {sort_col} {direction} "
            f"LIMIT ?"
        )
        params.append(limit)
        return [dict(r) for r in self.conn.execute(sql, params).fetchall()]

    def get_sector_history(
        self,
        bk_code: str,
        sector_type: str,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 60,
    ) -> list[dict[str, Any]]:
        where = "WHERE bk_code = ? AND sector_type = ?"
        params: list[Any] = [bk_code, sector_type]
        if start_date:
            where += " AND trade_date >= ?"
            params.append(start_date)
        if end_date:
            where += " AND trade_date <= ?"
            params.append(end_date)

        sql = (
            f"SELECT * FROM ("
            f"SELECT trade_date, sector_type, bk_code, bk_name, "
            f"index_type, change_pct, amount, net_inflow, collected_at "
            f"FROM market_sector {where} "
            f"ORDER BY trade_date DESC LIMIT ?"
            f") ORDER BY trade_date ASC"
        )
        params.append(limit)
        return [dict(r) for r in self.conn.execute(sql, params).fetchall()]

    def get_board_list(self, sector_type: str) -> list[dict[str, str]]:
        """取最新交易日的板块名称+代码去重列表，供前端 autocomplete。"""
        latest = self.get_latest_trading_day()
        if not latest:
            return []
        rows = self.conn.execute(
            "SELECT DISTINCT bk_code, bk_name FROM market_sector "
            "WHERE sector_type = ? AND trade_date = ? "
            "ORDER BY bk_code",
            (sector_type, latest),
        ).fetchall()
        return [{"bk_code": r["bk_code"], "bk_name": r["bk_name"]} for r in rows]

    def get_available_dates(self, limit: int = 30) -> list[str]:
        rows = self.conn.execute(
            "SELECT DISTINCT trade_date FROM market_total "
            "ORDER BY trade_date DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [r[0] for r in rows]

    # -- delete ----------------------------------------------------------------

    def delete_by_date(self, trade_date: str) -> dict[str, int]:
        """删除指定日期的全市场 + 板块数据，返回删除行数。"""
        cursor = self.conn.execute(
            "DELETE FROM market_total WHERE trade_date = ?", (trade_date,)
        )
        total_deleted = cursor.rowcount
        cursor = self.conn.execute(
            "DELETE FROM market_sector WHERE trade_date = ?", (trade_date,)
        )
        sector_deleted = cursor.rowcount
        self.conn.commit()
        return {"market_total_deleted": total_deleted, "market_sector_deleted": sector_deleted}

    # -- collect status -------------------------------------------------------

    def get_collect_status(self) -> dict[str, Any]:
        """返回最近采集状态。"""
        latest = self.get_latest_trading_day()
        if not latest:
            return {"has_data": False, "latest_date": None, "latest_collected_at": None}

        total_row = self.conn.execute(
            "SELECT collected_at FROM market_total WHERE trade_date = ?",
            (latest,),
        ).fetchone()

        industry_count = self.conn.execute(
            "SELECT COUNT(*) FROM market_sector WHERE trade_date = ? AND sector_type = 'industry'",
            (latest,),
        ).fetchone()[0]

        concept_count = self.conn.execute(
            "SELECT COUNT(*) FROM market_sector WHERE trade_date = ? AND sector_type = 'concept'",
            (latest,),
        ).fetchone()[0]

        return {
            "has_data": True,
            "latest_date": latest,
            "latest_collected_at": total_row["collected_at"] if total_row else None,
            "sector_counts": {"industry": industry_count, "concept": concept_count},
        }
