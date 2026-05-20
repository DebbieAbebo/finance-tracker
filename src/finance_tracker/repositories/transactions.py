"""Persistence for ``Transaction``."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime

from ._helpers import parse_timestamp
from typing import Optional

from ..exceptions import NotFoundError
from ..models import Transaction


def _row_to_transaction(row: sqlite3.Row) -> Transaction:
    return Transaction(
        id=row["id"],
        occurred_on=date.fromisoformat(row["occurred_on"]),
        amount_cents=row["amount_cents"],
        description=row["description"],
        notes=row["notes"],
        account_id=row["account_id"],
        category_id=row["category_id"],
        created_at=parse_timestamp(row["created_at"]),
        updated_at=parse_timestamp(row["updated_at"]),
    )


@dataclass
class TransactionFilter:
    """Filter criteria for ``TransactionRepository.list``."""

    account_ids: Optional[list[int]] = None
    category_ids: Optional[list[int]] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    min_amount_cents: Optional[int] = None
    max_amount_cents: Optional[int] = None
    search: Optional[str] = None  # substring match against description / notes
    limit: Optional[int] = None
    offset: int = 0
    order: str = "occurred_on DESC, id DESC"

    _allowed_orders: tuple[str, ...] = field(
        default=(
            "occurred_on ASC, id ASC",
            "occurred_on DESC, id DESC",
            "amount_cents ASC",
            "amount_cents DESC",
        ),
        repr=False,
    )

    def validate(self) -> None:
        if self.order not in self._allowed_orders:
            raise ValueError(
                f"order must be one of {self._allowed_orders}, got {self.order!r}"
            )


class TransactionRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def get(self, transaction_id: int) -> Transaction:
        row = self._conn.execute(
            "SELECT * FROM transactions WHERE id = ?", (transaction_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"transaction id={transaction_id} not found")
        return _row_to_transaction(row)

    def list(self, criteria: Optional[TransactionFilter] = None) -> list[Transaction]:
        criteria = criteria or TransactionFilter()
        criteria.validate()

        clauses: list[str] = []
        params: list = []

        if criteria.account_ids:
            placeholders = ",".join("?" for _ in criteria.account_ids)
            clauses.append(f"account_id IN ({placeholders})")
            params.extend(criteria.account_ids)

        if criteria.category_ids:
            placeholders = ",".join("?" for _ in criteria.category_ids)
            clauses.append(f"category_id IN ({placeholders})")
            params.extend(criteria.category_ids)

        if criteria.date_from is not None:
            clauses.append("occurred_on >= ?")
            params.append(criteria.date_from.isoformat())

        if criteria.date_to is not None:
            clauses.append("occurred_on <= ?")
            params.append(criteria.date_to.isoformat())

        if criteria.min_amount_cents is not None:
            clauses.append("amount_cents >= ?")
            params.append(criteria.min_amount_cents)

        if criteria.max_amount_cents is not None:
            clauses.append("amount_cents <= ?")
            params.append(criteria.max_amount_cents)

        if criteria.search:
            clauses.append("(description LIKE ? OR COALESCE(notes,'') LIKE ?)")
            needle = f"%{criteria.search}%"
            params.extend([needle, needle])

        sql = "SELECT * FROM transactions"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += f" ORDER BY {criteria.order}"
        if criteria.limit is not None:
            sql += " LIMIT ? OFFSET ?"
            params.extend([criteria.limit, criteria.offset])

        return [_row_to_transaction(r) for r in self._conn.execute(sql, params).fetchall()]

    def count(self, criteria: Optional[TransactionFilter] = None) -> int:
        criteria = criteria or TransactionFilter()
        # Reuse list's predicate building by re-running it without the LIMIT/OFFSET.
        clone = TransactionFilter(
            account_ids=criteria.account_ids,
            category_ids=criteria.category_ids,
            date_from=criteria.date_from,
            date_to=criteria.date_to,
            min_amount_cents=criteria.min_amount_cents,
            max_amount_cents=criteria.max_amount_cents,
            search=criteria.search,
        )
        return len(self.list(clone))

    def create(self, transaction: Transaction) -> Transaction:
        cur = self._conn.execute(
            """
            INSERT INTO transactions
                (occurred_on, amount_cents, description, notes, account_id, category_id)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                transaction.occurred_on.isoformat(),
                transaction.amount_cents,
                transaction.description,
                transaction.notes,
                transaction.account_id,
                transaction.category_id,
            ),
        )
        return self.get(int(cur.lastrowid))

    def update(self, transaction: Transaction) -> Transaction:
        if transaction.id is None:
            raise ValueError("cannot update transaction without id")
        cur = self._conn.execute(
            """
            UPDATE transactions
               SET occurred_on = ?, amount_cents = ?, description = ?, notes = ?,
                   account_id = ?, category_id = ?,
                   updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
             WHERE id = ?
            """,
            (
                transaction.occurred_on.isoformat(),
                transaction.amount_cents,
                transaction.description,
                transaction.notes,
                transaction.account_id,
                transaction.category_id,
                transaction.id,
            ),
        )
        if cur.rowcount == 0:
            raise NotFoundError(f"transaction id={transaction.id} not found")
        return self.get(transaction.id)

    def delete(self, transaction_id: int) -> None:
        cur = self._conn.execute(
            "DELETE FROM transactions WHERE id = ?", (transaction_id,)
        )
        if cur.rowcount == 0:
            raise NotFoundError(f"transaction id={transaction_id} not found")

    def bulk_create(self, transactions: list[Transaction]) -> int:
        """Insert many transactions in a single transaction. Returns count."""
        if not transactions:
            return 0
        rows = [
            (
                t.occurred_on.isoformat(),
                t.amount_cents,
                t.description,
                t.notes,
                t.account_id,
                t.category_id,
            )
            for t in transactions
        ]
        self._conn.executemany(
            """
            INSERT INTO transactions
                (occurred_on, amount_cents, description, notes, account_id, category_id)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        return len(rows)
