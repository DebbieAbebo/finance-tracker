"""Higher-level reports: monthly summaries and category breakdowns.

Reports are read-only views built on top of the analytics service and
the repositories.
"""

from __future__ import annotations

import calendar
import sqlite3
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from ..models import CategoryKind
from ..repositories.categories import CategoryRepository
from .analytics import AnalyticsService, CategoryTotal


@dataclass(frozen=True)
class MonthlySummary:
    year: int
    month: int
    income_cents: int
    expense_cents: int

    @property
    def net_cents(self) -> int:
        return self.income_cents - self.expense_cents

    @property
    def label(self) -> str:
        return f"{self.year:04d}-{self.month:02d}"


@dataclass(frozen=True)
class CategoryBreakdown:
    parent_id: Optional[int]
    parent_name: str
    own_total_cents: int
    rolled_up_total_cents: int
    children: list[CategoryTotal] = field(default_factory=list)


class ReportingService:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._analytics = AnalyticsService(conn)
        self._categories = CategoryRepository(conn)

    # --- monthly summary --------------------------------------------------

    def monthly_summary(self, year: int, month: int) -> MonthlySummary:
        first, last = _month_bounds(year, month)
        income = self._analytics.total_for_kind(
            CategoryKind.INCOME, date_from=first, date_to=last
        )
        expense = self._analytics.total_for_kind(
            CategoryKind.EXPENSE, date_from=first, date_to=last
        )
        return MonthlySummary(year=year, month=month, income_cents=income, expense_cents=expense)

    def monthly_summaries(
        self, *, start: date, end: date
    ) -> list[MonthlySummary]:
        if start > end:
            raise ValueError("start must be <= end")
        results: list[MonthlySummary] = []
        cursor = date(start.year, start.month, 1)
        while cursor <= end:
            results.append(self.monthly_summary(cursor.year, cursor.month))
            cursor = _add_month(cursor)
        return results

    # --- category breakdown ----------------------------------------------

    def category_breakdown(
        self,
        parent_id: Optional[int],
        *,
        kind: CategoryKind = CategoryKind.EXPENSE,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
    ) -> CategoryBreakdown:
        """Spend (or income) under a parent, rolled up across descendants."""
        if parent_id is None:
            parent_name = "(uncategorized)"
        else:
            parent_name = self._categories.full_path(self._categories.get(parent_id))

        descendant_ids = (
            self._categories.descendants_of(parent_id)
            if parent_id is not None
            else None
        )

        # Own total: transactions directly tagged to parent_id.
        own_total = self._sum_amount_for_categories(
            [parent_id] if parent_id is not None else [None],
            kind=kind,
            date_from=date_from,
            date_to=date_to,
        )

        # Rolled-up total: parent + descendants
        rolled_total = self._sum_amount_for_categories(
            descendant_ids if descendant_ids is not None else [None],
            kind=kind,
            date_from=date_from,
            date_to=date_to,
        )

        # Per-child breakdown (one level deep)
        children = self._categories.children_of(parent_id)
        child_totals: list[CategoryTotal] = []
        for child in children:
            child_descendants = self._categories.descendants_of(child.id)
            total = self._sum_amount_for_categories(
                child_descendants, kind=kind, date_from=date_from, date_to=date_to
            )
            count = self._count_transactions_for_categories(
                child_descendants, kind=kind, date_from=date_from, date_to=date_to
            )
            if total or count:
                child_totals.append(
                    CategoryTotal(
                        category_id=child.id,
                        category_name=child.name,
                        kind=child.kind,
                        total_cents=total,
                        transaction_count=count,
                    )
                )

        child_totals.sort(key=lambda c: c.total_cents, reverse=True)

        return CategoryBreakdown(
            parent_id=parent_id,
            parent_name=parent_name,
            own_total_cents=own_total,
            rolled_up_total_cents=rolled_total,
            children=child_totals,
        )

    # --- internals --------------------------------------------------------

    def _sum_amount_for_categories(
        self,
        category_ids,
        *,
        kind: CategoryKind,
        date_from: Optional[date],
        date_to: Optional[date],
    ) -> int:
        if category_ids == [None]:
            sql = (
                "SELECT COALESCE(SUM(amount_cents), 0) AS total "
                "FROM transactions WHERE category_id IS NULL"
            )
            params: list = []
        else:
            placeholders = ",".join("?" for _ in category_ids)
            sql = f"""
                SELECT COALESCE(SUM(t.amount_cents), 0) AS total
                  FROM transactions t
                  JOIN categories c ON c.id = t.category_id
                 WHERE c.id IN ({placeholders}) AND c.kind = ?
            """
            params = list(category_ids) + [kind.value]

        if date_from is not None:
            sql += " AND occurred_on >= ?" if "WHERE" in sql.upper() else " WHERE occurred_on >= ?"
            params.append(date_from.isoformat())
        if date_to is not None:
            sql += " AND occurred_on <= ?"
            params.append(date_to.isoformat())

        return int(self._conn.execute(sql, params).fetchone()["total"])

    def _count_transactions_for_categories(
        self,
        category_ids,
        *,
        kind: CategoryKind,
        date_from: Optional[date],
        date_to: Optional[date],
    ) -> int:
        if not category_ids or category_ids == [None]:
            return 0
        placeholders = ",".join("?" for _ in category_ids)
        sql = f"""
            SELECT COUNT(*) AS n
              FROM transactions t
              JOIN categories c ON c.id = t.category_id
             WHERE c.id IN ({placeholders}) AND c.kind = ?
        """
        params = list(category_ids) + [kind.value]
        if date_from is not None:
            sql += " AND occurred_on >= ?"
            params.append(date_from.isoformat())
        if date_to is not None:
            sql += " AND occurred_on <= ?"
            params.append(date_to.isoformat())
        return int(self._conn.execute(sql, params).fetchone()["n"])


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last_day)


def _add_month(d: date) -> date:
    if d.month == 12:
        return date(d.year + 1, 1, 1)
    return date(d.year, d.month + 1, 1)
