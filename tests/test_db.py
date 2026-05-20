"""Tests for the database module: connection setup and migrations."""

from __future__ import annotations

import unittest

from finance_tracker.db import MIGRATIONS, _current_version, migrate

from tests.support import TempDatabase


class MigrationTests(unittest.TestCase):
    def test_fresh_database_runs_all_migrations(self):
        with TempDatabase() as conn:
            self.assertEqual(_current_version(conn), MIGRATIONS[-1][0])

    def test_migrate_is_idempotent(self):
        with TempDatabase() as conn:
            before = _current_version(conn)
            migrate(conn)
            self.assertEqual(_current_version(conn), before)

    def test_accounts_table_exists(self):
        with TempDatabase() as conn:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='accounts'"
            ).fetchone()
            self.assertIsNotNone(row)

    def test_foreign_keys_enabled(self):
        with TempDatabase() as conn:
            row = conn.execute("PRAGMA foreign_keys").fetchone()
            self.assertEqual(row[0], 1)


if __name__ == "__main__":
    unittest.main()
