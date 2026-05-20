"""Tests for ``RecurringTransactionRepository``."""

from __future__ import annotations

import unittest
from datetime import date

from finance_tracker.exceptions import NotFoundError
from finance_tracker.models import (
    Account,
    AccountType,
    Cadence,
    Category,
    CategoryKind,
    RecurringTransaction,
)
from finance_tracker.repositories.accounts import AccountRepository
from finance_tracker.repositories.categories import CategoryRepository
from finance_tracker.repositories.recurring import RecurringTransactionRepository

from tests.support import TempDatabase


def _seed(conn):
    accounts = AccountRepository(conn)
    cats = CategoryRepository(conn)
    checking = accounts.create(Account(name="Checking", type=AccountType.CHECKING))
    rent_cat = cats.create(Category(name="Rent", kind=CategoryKind.EXPENSE))
    return checking, rent_cat


def _rent(checking_id, cat_id, **overrides):
    defaults = dict(
        name="Rent",
        amount_cents=180_000,
        account_id=checking_id,
        category_id=cat_id,
        cadence=Cadence.MONTHLY,
        interval=1,
        starts_on=date(2026, 1, 1),
        description="Monthly rent",
    )
    defaults.update(overrides)
    return RecurringTransaction(**defaults)


class RecurringRepositoryTests(unittest.TestCase):
    def test_create_and_get(self):
        with TempDatabase() as conn:
            checking, rent_cat = _seed(conn)
            repo = RecurringTransactionRepository(conn)
            saved = repo.create(_rent(checking.id, rent_cat.id))
            self.assertIsNotNone(saved.id)
            fetched = repo.get(saved.id)
            self.assertEqual(fetched.name, "Rent")
            self.assertEqual(fetched.cadence, Cadence.MONTHLY)
            self.assertTrue(fetched.active)

    def test_list_only_active(self):
        with TempDatabase() as conn:
            checking, rent_cat = _seed(conn)
            repo = RecurringTransactionRepository(conn)
            repo.create(_rent(checking.id, rent_cat.id, name="Active"))
            repo.create(_rent(checking.id, rent_cat.id, name="Inactive", active=False))

            self.assertEqual(len(repo.list()), 2)
            self.assertEqual(len(repo.list(only_active=True)), 1)

    def test_update(self):
        with TempDatabase() as conn:
            checking, rent_cat = _seed(conn)
            repo = RecurringTransactionRepository(conn)
            saved = repo.create(_rent(checking.id, rent_cat.id))
            saved.amount_cents = 195_000
            saved.last_materialized_on = date(2026, 3, 1)
            updated = repo.update(saved)
            self.assertEqual(updated.amount_cents, 195_000)
            self.assertEqual(updated.last_materialized_on, date(2026, 3, 1))

    def test_delete(self):
        with TempDatabase() as conn:
            checking, rent_cat = _seed(conn)
            repo = RecurringTransactionRepository(conn)
            saved = repo.create(_rent(checking.id, rent_cat.id))
            repo.delete(saved.id)
            with self.assertRaises(NotFoundError):
                repo.get(saved.id)

    def test_delete_missing_raises(self):
        with TempDatabase() as conn:
            with self.assertRaises(NotFoundError):
                RecurringTransactionRepository(conn).delete(123)


if __name__ == "__main__":
    unittest.main()
