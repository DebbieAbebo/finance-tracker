"""Persistence for ``RecurringTransaction``."""

from __future__ import annotations

import sqlite3
from datetime import date
from typing import Optional

from ..exceptions import NotFoundError
from ..models import Cadence, RecurringTransaction
from ._helpers import parse_timestamp


def _row_to_recurring(row: sqlite3.Row) -> RecurringTransaction:
    return RecurringTransaction(
        id=row["id"],
        name=row["name"],
        amount_cents=row["amount_cents"],
        account_id=row["account_id"],
        category_id=row["category_id"],
        cadence=Cadence(row["cadence"]),
        interval=row["interval"],
        starts_on=date.fromisoformat(row["starts_on"]),
        ends_on=date.fromisoformat(row["ends_on"]) if row["ends_on"] else None,
        description=row["description"],
        notes=row["notes"],
        last_materialized_on=(
            date.fromisoformat(row["last_materialized_on"])
            if row["last_materialized_on"]
            else None
        ),
        active=bool(row["active"]),
        created_at=parse_timestamp(row["created_at"]),
        updated_at=parse_timestamp(row["updated_at"]),
    )


class RecurringTransactionRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def get(self, recurring_id: int) -> RecurringTransaction:
        row = self._conn.execute(
            "SELECT * FROM recurring_transactions WHERE id = ?", (recurring_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"recurring id={recurring_id} not found")
        return _row_to_recurring(row)

    def list(self, *, only_active: bool = False) -> list[RecurringTransaction]:
        sql = "SELECT * FROM recurring_transactions"
        if only_active:
            sql += " WHERE active = 1"
        sql += " ORDER BY name COLLATE NOCASE"
        return [_row_to_recurring(r) for r in self._conn.execute(sql).fetchall()]

    def create(self, r: RecurringTransaction) -> RecurringTransaction:
        cur = self._conn.execute(
            """
            INSERT INTO recurring_transactions
                (name, amount_cents, account_id, category_id, cadence, interval,
                 starts_on, ends_on, description, notes, last_materialized_on, active)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                r.name,
                r.amount_cents,
                r.account_id,
                r.category_id,
                r.cadence.value,
                r.interval,
                r.starts_on.isoformat(),
                r.ends_on.isoformat() if r.ends_on else None,
                r.description,
                r.notes,
                r.last_materialized_on.isoformat() if r.last_materialized_on else None,
                1 if r.active else 0,
            ),
        )
        return self.get(int(cur.lastrowid))

    def update(self, r: RecurringTransaction) -> RecurringTransaction:
        if r.id is None:
            raise ValueError("cannot update recurring without id")
        cur = self._conn.execute(
            """
            UPDATE recurring_transactions
               SET name = ?, amount_cents = ?, account_id = ?, category_id = ?,
                   cadence = ?, interval = ?, starts_on = ?, ends_on = ?,
                   description = ?, notes = ?, last_materialized_on = ?, active = ?,
                   updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
             WHERE id = ?
            """,
            (
                r.name,
                r.amount_cents,
                r.account_id,
                r.category_id,
                r.cadence.value,
                r.interval,
                r.starts_on.isoformat(),
                r.ends_on.isoformat() if r.ends_on else None,
                r.description,
                r.notes,
                r.last_materialized_on.isoformat() if r.last_materialized_on else None,
                1 if r.active else 0,
                r.id,
            ),
        )
        if cur.rowcount == 0:
            raise NotFoundError(f"recurring id={r.id} not found")
        return self.get(r.id)

    def delete(self, recurring_id: int) -> None:
        cur = self._conn.execute(
            "DELETE FROM recurring_transactions WHERE id = ?", (recurring_id,)
        )
        if cur.rowcount == 0:
            raise NotFoundError(f"recurring id={recurring_id} not found")
