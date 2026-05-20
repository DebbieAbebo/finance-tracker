"""Application configuration.

Reads settings from environment variables with sensible defaults.
Anything that varies between dev/prod/CI lives here so we don't have to
sprinkle ``os.environ.get`` calls through the rest of the codebase.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _default_data_dir() -> Path:
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg) / "finance-tracker"
    return Path.home() / ".local" / "share" / "finance-tracker"


@dataclass(frozen=True)
class Settings:
    database_path: Path
    debug: bool

    @classmethod
    def from_env(cls) -> "Settings":
        db_env = os.environ.get("FINANCE_DATABASE_PATH")
        if db_env:
            db_path = Path(db_env).expanduser()
        else:
            data_dir = _default_data_dir()
            db_path = data_dir / "finance.db"

        debug = os.environ.get("FINANCE_DEBUG", "").lower() in {"1", "true", "yes"}
        return cls(database_path=db_path, debug=debug)


def load_settings() -> Settings:
    """Build a fresh ``Settings`` from the current environment.

    Returning a fresh object (rather than a module-level singleton) makes
    it easier to override during tests by patching ``os.environ``.
    """
    return Settings.from_env()
