"""SQLite store for strategy parameter configurations.

Each strategy has at most one saved config row (upsert semantics).
The DB file lives at ``agent/data/strategy_config.db``.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_log = logging.getLogger(__name__)

_DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "strategy_config.db"

_DEFAULT_PARAMS: dict[str, dict[str, Any]] = {
    "up_trend_structure": {
        "up_phase_min_bars": 2,
        "volume_surge_ratio": 1.2,
        "big_bull_body_ratio": 0.6,
        "inv_hammer_shadow_ratio": 1.1,
        "close_above_prev_mid": 0.5,
        "stop_loss_pct": 0.03,
        "divergence_repair_bars": 1,
        "take_profit_pct": 0.30,
        "ma_short": 5,
        "ma_mid": 10,
    },
}


class StrategyConfigStore:
    """Persist per-strategy parameter configs in SQLite."""

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
                CREATE TABLE IF NOT EXISTS strategy_config (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    strategy    TEXT NOT NULL UNIQUE,
                    config_json TEXT NOT NULL,
                    updated_at  TEXT NOT NULL
                )
                """
            )
            conn.commit()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_config(self, strategy: str) -> dict[str, Any]:
        """Return saved config for *strategy*, or default params if none saved.

        Returns:
            dict with keys: ``strategy``, ``params`` (dict), ``is_default`` (bool).
        """
        with self._connect() as conn:
            row = conn.execute(
                "SELECT config_json FROM strategy_config WHERE strategy = ?",
                (strategy,),
            ).fetchone()

        if row is None:
            defaults = _DEFAULT_PARAMS.get(strategy, {})
            return {
                "strategy": strategy,
                "params": defaults,
                "is_default": True,
            }

        return {
            "strategy": strategy,
            "params": json.loads(row["config_json"]),
            "is_default": False,
        }

    def save_config(self, strategy: str, params: dict[str, Any]) -> dict[str, Any]:
        """Upsert config for *strategy*.  Returns the saved config dict."""
        now = datetime.now(timezone.utc).isoformat()
        config_json = json.dumps(params, ensure_ascii=False)

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO strategy_config (strategy, config_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(strategy) DO UPDATE SET
                    config_json = excluded.config_json,
                    updated_at = excluded.updated_at
                """,
                (strategy, config_json, now),
            )
            conn.commit()

        _log.info("Saved config for strategy=%s", strategy)
        return {
            "strategy": strategy,
            "params": params,
            "is_default": False,
        }

    def delete_config(self, strategy: str) -> dict[str, Any]:
        """Delete saved config, reverting to defaults.  Returns the default config."""
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM strategy_config WHERE strategy = ?",
                (strategy,),
            )
            conn.commit()

        defaults = _DEFAULT_PARAMS.get(strategy, {})
        _log.info("Deleted config for strategy=%s, reverted to defaults", strategy)
        return {
            "strategy": strategy,
            "params": defaults,
            "is_default": True,
        }
