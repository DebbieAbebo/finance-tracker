"""High-level numeric queries: balances, totals, top categories."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date
from typing import Optional

from ..models import CategoryKind


@dataclass(frozen=True)
class CategoryTotal:
    category_id: Optional[int]
    category_name: str
    kind: Optional[CategoryKind]
    total_cents: int
    transaction_count: int


@dataclass(frozen=True)
class AccountBalance:
    account_id: int
    account_name: str
    opening_balance_cents: int
    activity_cents: int
    balance_cents: int


class AnalyticsService:
    """Numeric aggregations driven directly off SQL.

    These could be expressed by loading transactions through the
    repository and summing in Python, but for the dashboards we want
    fast, set-based queries — so we drop into SQL here and keep
    repositories focused on row-level access.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    # --- balances --------------------------------------------------------

    def account_balance(self, account_id: int, *, as_of: Optional[date] = None) -> AccountBalance:
        params: list = [account_id]
        sql = """
            SELECT a.id, a.name, a.opening_balance_cents,
                   COALESCE(SUM(
                       CASE
                           WHEN c.kind = 'expense' THEN -t.amount_cents
                           WHEN c.kind = 'income'  THEN  t.amount_cents
                           ELSE t.amount_cents
                       END
                   ), 0) AS activity
              FROM accounts a
              LEFT JOIN transactions t ON t.account_id = a.id
              LEFT JOIN categories c ON c.id = t.category_id
             WHERE a.id = ?
        """
        if as_of is not None:
            sql += " AND (t.occurred_on IS NULL OR t.occurred_on <= ?)"
            params.append(as_of.isoformat())
        sql += " GROUP BY a.id"

        row = self._conn.execute(sql, params).fetchone()
        if row is None:
            raise ValueError(f"account id={account_id} not found")
        return AccountBalance(
            account_id=row["id"],
            account_name=row["name"],
            opening_balance_cents=row["opening_balance_cents"],
            activity_cents=int(row["activity"]),
            balance_cents=row["opening_balance_cents"] + int(row["activity"]),
        )

    def all_balances(self, *, as_of: Optional[date] = None) -> list[AccountBalance]:
        rows = self._conn.execute(
            "SELECT id FROM accounts WHERE archived = 0 ORDER BY name COLLATE NOCASE"
        ).fetchall()
        return [self.account_balance(r["id"], as_of=as_of) for r in rows]

    # --- totals & top-N --------------------------------------------------

    def total_for_kind(
        self,
        kind: CategoryKind,
        *,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
    ) -> int:
        sql = """
            SELECT COALESCE(SUM(t.amount_cents), 0) AS total
              FROM transactions t
              JOIN categories c ON c.id = t.category_id
             WHERE c.kind = ?
        """
        params: list = [kind.value]
        if date_from is not None:
            sql += " AND t.occurred_on >= ?"
            params.append(date_from.isoformat())
        if date_to is not None:
            sql += " AND t.occurred_on <= ?"
            params.append(date_to.isoformat())
        return int(self._conn.execute(sql, params).fetchone()["total"])

    def top_categories(
        self,
        *,
        kind: CategoryKind = CategoryKind.EXPENSE,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        limit: int = 10,
    ) -> list[CategoryTotal]:
        sql = """
            SELECT c.id, c.name, c.kind,
                   SUM(t.amount_cents) AS total,
                   COUNT(*) AS n
              FROM transactions t
              JOIN categories c ON c.id = t.category_id
             WHERE c.kind = ?
        """
        params: list = [kind.value]
        if date_from is not None:
            sql += " AND t.occurred_on >= ?"
            params.append(date_from.isoformat())
        if date_to is not None:
            sql += " AND t.occurred_on <= ?"
            params.append(date_to.isoformat())
        sql += " GROUP BY c.id ORDER BY total DESC LIMIT ?"
        params.append(limit)

        return [
            CategoryTotal(
                category_id=r["id"],
                category_name=r["name"],
                kind=CategoryKind(r["kind"]),
                total_cents=int(r["total"]),
                transaction_count=int(r["n"]),
            )
            for r in self._conn.execute(sql, params).fetchall()
        ]

    def average_daily_spend(
        self, *, date_from: date, date_to: date
    ) -> float:
        """Average daily expense between the two dates (inclusive)."""
        if date_from > date_to:
            raise ValueError("date_from must be <= date_to")
        total = self.total_for_kind(CategoryKind.EXPENSE, date_from=date_from, date_to=date_to)
        days = (date_to - date_from).days + 1
        return total / days
