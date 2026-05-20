"""Helpers for tests that need a real (but disposable) database."""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path
from typing import Optional

from finance_tracker.db import connect, migrate


class TempDatabase:
    """Create a fresh sqlite database in a temp dir, migrated to head."""

    def __init__(self) -> None:
        self._tmp: Optional[tempfile.TemporaryDirectory] = None
        self.path: Optional[Path] = None
        self.conn: Optional[sqlite3.Connection] = None

    def __enter__(self) -> sqlite3.Connection:
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "test.db"
        self.conn = connect(self.path)
        migrate(self.conn)
        return self.conn

    def __exit__(self, exc_type, exc, tb) -> None:
        if self.conn is not None:
            self.conn.close()
        if self._tmp is not None:
            self._tmp.cleanup()
