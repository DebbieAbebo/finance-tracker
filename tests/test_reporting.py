"""Tests for ``ReportingService``."""

from __future__ import annotations

import unittest
from datetime import date

from finance_tracker.models import (
    Account,
    AccountType,
    Category,
    CategoryKind,
    Transaction,
)
from finance_tracker.repositories.accounts import AccountRepository
from finance_tracker.repositories.categories import CategoryRepository
from finance_tracker.repositories.transactions import TransactionRepository
from finance_tracker.services.reporting import ReportingService

from tests.support import TempDatabase


def _setup(conn):
    accounts = AccountRepository(conn)
    cats = CategoryRepository(conn)
    txns = TransactionRepository(conn)

    checking = accounts.create(Account(name="Checking", type=AccountType.CHECKING))

    food = cats.create(Category(name="Food", kind=CategoryKind.EXPENSE))
    groc = cats.create(
        Category(name="Groceries", kind=CategoryKind.EXPENSE, parent_id=food.id)
    )
    restaurants = cats.create(
        Category(name="Restaurants", kind=CategoryKind.EXPENSE, parent_id=food.id)
    )
    salary = cats.create(Category(name="Salary", kind=CategoryKind.INCOME))

    rows = [
        (date(2026, 1, 5), 200_000, salary.id, "Jan paycheck"),
        (date(2026, 1, 10), 12_000, groc.id, "Whole Foods"),
        (date(2026, 1, 15), 8_000, restaurants.id, "Tacos"),
        (date(2026, 2, 5), 200_000, salary.id, "Feb paycheck"),
        (date(2026, 2, 8), 15_000, groc.id, "Trader Joe's"),
        (date(2026, 2, 20), 4_000, food.id, "Ambiguous food spend"),
    ]
    for d, amt, cat, desc in rows:
        txns.create(
            Transaction(
                occurred_on=d,
                amount_cents=amt,
                description=desc,
                account_id=checking.id,
                category_id=cat,
            )
        )
    return {"food": food, "groc": groc, "restaurants": restaurants, "salary": salary}


class MonthlySummaryTests(unittest.TestCase):
    def test_january_summary(self):
        with TempDatabase() as conn:
            _setup(conn)
            summary = ReportingService(conn).monthly_summary(2026, 1)
            self.assertEqual(summary.income_cents, 200_000)
            self.assertEqual(summary.expense_cents, 20_000)
            self.assertEqual(summary.net_cents, 180_000)
            self.assertEqual(summary.label, "2026-01")

    def test_summaries_over_range(self):
        with TempDatabase() as conn:
            _setup(conn)
            results = ReportingService(conn).monthly_summaries(
                start=date(2026, 1, 1), end=date(2026, 2, 28)
            )
            self.assertEqual([s.label for s in results], ["2026-01", "2026-02"])
            self.assertEqual(results[1].expense_cents, 19_000)

    def test_summaries_inverted_range(self):
        with TempDatabase() as conn:
            _setup(conn)
            with self.assertRaises(ValueError):
                ReportingService(conn).monthly_summaries(
                    start=date(2026, 5, 1), end=date(2026, 1, 1)
                )

    def test_summaries_year_boundary(self):
        with TempDatabase() as conn:
            _setup(conn)
            results = ReportingService(conn).monthly_summaries(
                start=date(2025, 12, 1), end=date(2026, 2, 1)
            )
            self.assertEqual([s.label for s in results], ["2025-12", "2026-01", "2026-02"])


class CategoryBreakdownTests(unittest.TestCase):
    def test_breakdown_rolls_up_descendants(self):
        with TempDatabase() as conn:
            seed = _setup(conn)
            br = ReportingService(conn).category_breakdown(seed["food"].id)
            self.assertEqual(br.parent_name, "Food")
            # Direct: 4000. Rolled up: 4000 + 27000 (groc) + 8000 (rest) = 39000
            self.assertEqual(br.own_total_cents, 4_000)
            self.assertEqual(br.rolled_up_total_cents, 39_000)
            child_names = [c.category_name for c in br.children]
            self.assertEqual(set(child_names), {"Groceries", "Restaurants"})
            # Children sorted by total descending (Groceries 27k > Restaurants 8k)
            self.assertEqual(br.children[0].category_name, "Groceries")

    def test_breakdown_with_date_filter(self):
        with TempDatabase() as conn:
            seed = _setup(conn)
            br = ReportingService(conn).category_breakdown(
                seed["food"].id,
                date_from=date(2026, 1, 1),
                date_to=date(2026, 1, 31),
            )
            self.assertEqual(br.rolled_up_total_cents, 20_000)


if __name__ == "__main__":
    unittest.main()
