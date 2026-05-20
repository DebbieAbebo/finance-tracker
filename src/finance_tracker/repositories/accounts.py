"""Persistence for ``Account``."""

from __future__ import annotations

import sqlite3
from datetime import datetime

from ._helpers import parse_timestamp
from typing import Optional

from ..exceptions import DuplicateError, NotFoundError
from ..models import Account, AccountType


def _row_to_account(row: sqlite3.Row) -> Account:
    return Account(
        id=row["id"],
        name=row["name"],
        type=AccountType(row["type"]),
        currency=row["currency"],
        opening_balance_cents=row["opening_balance_cents"],
        archived=bool(row["archived"]),
        created_at=parse_timestamp(row["created_at"]),
        updated_at=parse_timestamp(row["updated_at"]),
    )


class AccountRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    # --- queries ---------------------------------------------------------

    def get(self, account_id: int) -> Account:
        row = self._conn.execute(
            "SELECT * FROM accounts WHERE id = ?", (account_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"account id={account_id} not found")
        return _row_to_account(row)

    def find_by_name(self, name: str) -> Optional[Account]:
        row = self._conn.execute(
            "SELECT * FROM accounts WHERE name = ?", (name,)
        ).fetchone()
        return _row_to_account(row) if row else None

    def list(self, *, include_archived: bool = False) -> list[Account]:
        sql = "SELECT * FROM accounts"
        if not include_archived:
            sql += " WHERE archived = 0"
        sql += " ORDER BY name COLLATE NOCASE"
        return [_row_to_account(r) for r in self._conn.execute(sql).fetchall()]

    # --- writes ----------------------------------------------------------

    def create(self, account: Account) -> Account:
        try:
            cur = self._conn.execute(
                """
                INSERT INTO accounts (name, type, currency, opening_balance_cents, archived)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    account.name,
                    account.type.value,
                    account.currency,
                    account.opening_balance_cents,
                    1 if account.archived else 0,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise DuplicateError(f"account name {account.name!r} already exists") from exc
        return self.get(int(cur.lastrowid))

    def update(self, account: Account) -> Account:
        if account.id is None:
            raise ValueError("cannot update account without id")
        try:
            cur = self._conn.execute(
                """
                UPDATE accounts
                   SET name = ?, type = ?, currency = ?,
                       opening_balance_cents = ?, archived = ?,
                       updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                 WHERE id = ?
                """,
                (
                    account.name,
                    account.type.value,
                    account.currency,
                    account.opening_balance_cents,
                    1 if account.archived else 0,
                    account.id,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise DuplicateError(f"account name {account.name!r} already exists") from exc
        if cur.rowcount == 0:
            raise NotFoundError(f"account id={account.id} not found")
        return self.get(account.id)

    def delete(self, account_id: int) -> None:
        cur = self._conn.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
        if cur.rowcount == 0:
            raise NotFoundError(f"account id={account_id} not found")

    def archive(self, account_id: int) -> Account:
        account = self.get(account_id)
        account.archived = True
        return self.update(account)
