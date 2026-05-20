"""Database connection and migrations.

Migrations are kept inline as a list of ``(version, sql)`` tuples. We
track the applied version in a ``schema_version`` table. The migration
runner is intentionally tiny — for a personal-scale app this is enough,
and it avoids dragging in Alembic.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .config import Settings, load_settings


# Each entry is (version, sql). Versions must be contiguous starting at 1.
# To add a migration: append a new tuple, never edit an existing one.
MIGRATIONS: list[tuple[int, str]] = [
    (
        1,
        """
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL
        );
        """,
    ),
    (
        2,
        """
        CREATE TABLE accounts (
            id                    INTEGER PRIMARY KEY AUTOINCREMENT,
            name                  TEXT NOT NULL UNIQUE,
            type                  TEXT NOT NULL,
            currency              TEXT NOT NULL DEFAULT 'USD',
            opening_balance_cents INTEGER NOT NULL DEFAULT 0,
            archived              INTEGER NOT NULL DEFAULT 0,
            created_at            TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
            updated_at            TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        );
        CREATE INDEX ix_accounts_archived ON accounts (archived);
        """,
    ),
    (
        3,
        """
        CREATE TABLE categories (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL,
            kind        TEXT NOT NULL,
            parent_id   INTEGER REFERENCES categories(id) ON DELETE CASCADE,
            created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
            updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
            UNIQUE (name, parent_id)
        );
        CREATE INDEX ix_categories_parent_id ON categories (parent_id);
        CREATE INDEX ix_categories_kind ON categories (kind);
        """,
    ),
    (
        4,
        """
        CREATE TABLE transactions (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            occurred_on   TEXT NOT NULL,
            amount_cents  INTEGER NOT NULL,
            description   TEXT NOT NULL DEFAULT '',
            notes         TEXT,
            account_id    INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
            category_id   INTEGER REFERENCES categories(id) ON DELETE SET NULL,
            created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
            updated_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        );
        CREATE INDEX ix_transactions_occurred_on ON transactions (occurred_on);
        CREATE INDEX ix_transactions_account_id ON transactions (account_id);
        CREATE INDEX ix_transactions_category_id ON transactions (category_id);
        """,
    ),
    (
        5,
        # The natural UNIQUE(name, parent_id) constraint on `categories`
        # doesn't catch duplicates at the top level because SQLite treats
        # NULL != NULL. We need a separate partial index for the case
        # where parent_id IS NULL.
        """
        CREATE UNIQUE INDEX uq_categories_top_level_name
            ON categories (name)
            WHERE parent_id IS NULL;
        """,
    ),
    (
        6,
        """
        CREATE TABLE recurring_transactions (
            id                     INTEGER PRIMARY KEY AUTOINCREMENT,
            name                   TEXT NOT NULL,
            amount_cents           INTEGER NOT NULL,
            account_id             INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
            category_id            INTEGER REFERENCES categories(id) ON DELETE SET NULL,
            cadence                TEXT NOT NULL,
            interval               INTEGER NOT NULL DEFAULT 1,
            starts_on              TEXT NOT NULL,
            ends_on                TEXT,
            description            TEXT NOT NULL DEFAULT '',
            notes                  TEXT,
            last_materialized_on   TEXT,
            active                 INTEGER NOT NULL DEFAULT 1,
            created_at             TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
            updated_at             TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        );
        CREATE INDEX ix_recurring_active ON recurring_transactions (active);
        """,
    ),
    (
        7,
        # The hottest query is "all transactions for account X in date
        # range Y..Z". A composite index on (account_id, occurred_on)
        # lets sqlite cover both predicates without falling back to the
        # individual single-column indexes.
        """
        CREATE INDEX ix_transactions_account_date
            ON transactions (account_id, occurred_on);
        """,
    ),
]


def connect(database_path: Path) -> sqlite3.Connection:
    """Open a connection with the conventions we want everywhere."""
    database_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(
        database_path,
        detect_types=sqlite3.PARSE_DECLTYPES,
        isolation_level=None,  # we manage transactions explicitly
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _current_version(conn: sqlite3.Connection) -> int:
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
    )
    if cur.fetchone() is None:
        return 0
    row = conn.execute("SELECT MAX(version) AS v FROM schema_version").fetchone()
    return int(row["v"]) if row and row["v"] is not None else 0


def _split_statements(sql: str) -> list[str]:
    """Split a multi-statement SQL string. Naive but enough for our DDL."""
    return [s.strip() for s in sql.split(";") if s.strip()]


def migrate(conn: sqlite3.Connection) -> int:
    """Apply any pending migrations. Returns the new schema version."""
    current = _current_version(conn)
    for version, sql in MIGRATIONS:
        if version <= current:
            continue
        conn.execute("BEGIN")
        try:
            for statement in _split_statements(sql):
                conn.execute(statement)
            conn.execute(
                "INSERT INTO schema_version (version, applied_at) "
                "VALUES (?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))",
                (version,),
            )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        current = version
    return current


@contextmanager
def connection_scope(settings: Settings | None = None) -> Iterator[sqlite3.Connection]:
    """Open a connection, run migrations, and clean up on exit."""
    s = settings or load_settings()
    conn = connect(s.database_path)
    try:
        migrate(conn)
        yield conn
    finally:
        conn.close()
