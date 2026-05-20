"""Tests for ``AnalyticsService``."""

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
from finance_tracker.services.analytics import AnalyticsService

from tests.support import TempDatabase


def _setup(conn):
    accounts = AccountRepository(conn)
    cats = CategoryRepository(conn)
    txns = TransactionRepository(conn)

    checking = accounts.create(
        Account(name="Checking", type=AccountType.CHECKING, opening_balance_cents=100_000)
    )
    food = cats.create(Category(name="Food", kind=CategoryKind.EXPENSE))
    rent = cats.create(Category(name="Rent", kind=CategoryKind.EXPENSE))
    salary = cats.create(Category(name="Salary", kind=CategoryKind.INCOME))

    txns.create(
        Transaction(
            occurred_on=date(2026, 3, 1),
            amount_cents=300_000,
            description="Paycheck",
            account_id=checking.id,
            category_id=salary.id,
        )
    )
    txns.create(
        Transaction(
            occurred_on=date(2026, 3, 2),
            amount_cents=180_000,
            description="Rent",
            account_id=checking.id,
            category_id=rent.id,
        )
    )
    txns.create(
        Transaction(
            occurred_on=date(2026, 3, 5),
            amount_cents=8_000,
            description="Lunch",
            account_id=checking.id,
            category_id=food.id,
        )
    )
    txns.create(
        Transaction(
            occurred_on=date(2026, 3, 12),
            amount_cents=12_000,
            description="Dinner",
            account_id=checking.id,
            category_id=food.id,
        )
    )
    return checking, food, rent, salary


class AccountBalanceTests(unittest.TestCase):
    def test_balance_combines_opening_and_activity(self):
        with TempDatabase() as conn:
            checking, *_ = _setup(conn)
            svc = AnalyticsService(conn)
            bal = svc.account_balance(checking.id)
            # opening 1000 + income 3000 - expenses (1800 + 80 + 120) = 2000
            self.assertEqual(bal.opening_balance_cents, 100_000)
            self.assertEqual(bal.activity_cents, 300_000 - 180_000 - 8_000 - 12_000)
            self.assertEqual(bal.balance_cents, 200_000)

    def test_balance_as_of_excludes_later_transactions(self):
        with TempDatabase() as conn:
            checking, *_ = _setup(conn)
            svc = AnalyticsService(conn)
            bal = svc.account_balance(checking.id, as_of=date(2026, 3, 4))
            # only paycheck + rent are <= 3/4
            self.assertEqual(bal.activity_cents, 300_000 - 180_000)
            self.assertEqual(bal.balance_cents, 100_000 + 120_000)

    def test_all_balances_excludes_archived(self):
        with TempDatabase() as conn:
            checking, *_ = _setup(conn)
            accounts = AccountRepository(conn)
            accounts.create(
                Account(
                    name="Old Account", type=AccountType.SAVINGS, archived=True
                )
            )
            svc = AnalyticsService(conn)
            balances = svc.all_balances()
            self.assertEqual([b.account_id for b in balances], [checking.id])


class TotalsTests(unittest.TestCase):
    def test_total_for_expense(self):
        with TempDatabase() as conn:
            _setup(conn)
            svc = AnalyticsService(conn)
            self.assertEqual(svc.total_for_kind(CategoryKind.EXPENSE), 200_000)

    def test_total_with_date_filter(self):
        with TempDatabase() as conn:
            _setup(conn)
            svc = AnalyticsService(conn)
            total = svc.total_for_kind(
                CategoryKind.EXPENSE,
                date_from=date(2026, 3, 1),
                date_to=date(2026, 3, 5),
            )
            self.assertEqual(total, 180_000 + 8_000)


class TopCategoriesTests(unittest.TestCase):
    def test_top_categories_orders_by_total_desc(self):
        with TempDatabase() as conn:
            _, food, rent, _ = _setup(conn)
            svc = AnalyticsService(conn)
            top = svc.top_categories(kind=CategoryKind.EXPENSE, limit=10)
            self.assertEqual(top[0].category_id, rent.id)
            self.assertEqual(top[0].total_cents, 180_000)
            self.assertEqual(top[1].category_id, food.id)
            self.assertEqual(top[1].total_cents, 20_000)
            self.assertEqual(top[1].transaction_count, 2)


class AverageDailySpendTests(unittest.TestCase):
    def test_average_over_inclusive_range(self):
        with TempDatabase() as conn:
            _setup(conn)
            svc = AnalyticsService(conn)
            avg = svc.average_daily_spend(
                date_from=date(2026, 3, 1), date_to=date(2026, 3, 31)
            )
            self.assertAlmostEqual(avg, 200_000 / 31, places=4)

    def test_inverted_range_raises(self):
        with TempDatabase() as conn:
            _setup(conn)
            svc = AnalyticsService(conn)
            with self.assertRaises(ValueError):
                svc.average_daily_spend(
                    date_from=date(2026, 3, 31), date_to=date(2026, 3, 1)
                )


if __name__ == "__main__":
    unittest.main()
