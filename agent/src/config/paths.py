"""Path helpers for agent-level structured config."""

from __future__ import annotations

import os
from pathlib import Path

_DEFAULT_FILENAMES = ("agent.json", "agent.yaml", "agent.yml")


def get_runtime_root(config_path: Path | None = None) -> Path:
    """Return the runtime root directory for user-level agent state.

    Args:
        config_path: Optional explicit config file path. When provided, the
            runtime root is derived from that file's parent directory.

    Returns:
        The directory containing the explicit structured config file when one
        is provided, otherwise the default ``~/.vibe-trading`` runtime root.
    """
    if config_path is not None:
        return config_path.expanduser().parent
    return Path.home() / ".vibe-trading"


def get_config_candidates(config_path: Path | None = None) -> list[Path]:
    """Return supported config path candidates in lookup order.

    Returns:
        Candidate config paths ordered by lookup priority. When an explicit
        config path is provided, only that path is returned.
    """
    if config_path is not None:
        return [config_path.expanduser()]
    root = get_runtime_root()
    return [root / filename for filename in _DEFAULT_FILENAMES]


def get_config_path(config_path: Path | None = None) -> Path:
    """Return the active config file path.

    Prefers the first existing candidate. If an explicit path is provided,
    returns that path directly. If no candidate exists yet, returns the
    recommended default JSON path.

    Args:
        config_path: Optional explicit config file path.

    Returns:
        The selected config file path for the current runtime context.
    """
    candidates = get_config_candidates(config_path)
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def get_data_dir(config_path: Path | None = None) -> Path:
    """Return and create the runtime data directory derived from config path.

    Args:
        config_path: Optional explicit config file path.

    Returns:
        The directory containing the active config file. The directory is
        created when it does not already exist.
    """
    data_dir = get_config_path(config_path).parent
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def _read_env(key: str) -> str:
    """Read an env var with ``agent/.env`` fallback.

    Mirrors :func:`iwencai_session._read_env` so that ``agent/.env`` is
    honoured even before the dotenv loader runs (module-level imports).
    """
    # 1. os.environ (already exported or injected)
    val = os.environ.get(key, "")
    if val:
        return val
    # 2. agent/.env fallback
    env_path = Path(__file__).resolve().parent.parent.parent / ".env"
    if not env_path.exists():
        return ""
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith(f"{key}="):
            val = line.split("=", 1)[1].strip().strip('"').strip("'")
            if val:
                os.environ[key] = val  # cache for subsequent calls
                return val
    return ""


def get_app_data_dir() -> Path:
    """Return the application data directory for SQLite stores, and create it.

    Resolves in order:
    1. os.environ ``VIBE_TRADING_DATA_DIR``
    2. ``agent/.env`` entry ``VIBE_TRADING_DATA_DIR``
    3. project-relative ``agent/data/``

    Returns:
        The resolved data directory (guaranteed to exist).
    """
    env = _read_env("VIBE_TRADING_DATA_DIR")
    if env:
        data_dir = Path(env).expanduser()
    else:
        data_dir = Path(__file__).resolve().parent.parent.parent / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir