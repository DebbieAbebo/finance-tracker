"""Tests for ``TransactionRepository`` including filtering."""

from __future__ import annotations

import unittest
from datetime import date

from finance_tracker.exceptions import NotFoundError
from finance_tracker.models import (
    Account,
    AccountType,
    Category,
    CategoryKind,
    Transaction,
)
from finance_tracker.repositories.accounts import AccountRepository
from finance_tracker.repositories.categories import CategoryRepository
from finance_tracker.repositories.transactions import (
    TransactionFilter,
    TransactionRepository,
)

from tests.support import TempDatabase


def _seed(conn):
    """Set up a small but useful fixture: 2 accounts, 3 categories, 5 txns."""
    accounts = AccountRepository(conn)
    cats = CategoryRepository(conn)
    txns = TransactionRepository(conn)

    checking = accounts.create(Account(name="Checking", type=AccountType.CHECKING))
    savings = accounts.create(Account(name="Savings", type=AccountType.SAVINGS))

    food = cats.create(Category(name="Food", kind=CategoryKind.EXPENSE))
    salary = cats.create(Category(name="Salary", kind=CategoryKind.INCOME))
    transfer = cats.create(Category(name="Transfer", kind=CategoryKind.TRANSFER))

    txns.create(
        Transaction(
            occurred_on=date(2026, 2, 1),
            amount_cents=300_000,
            description="February paycheck",
            account_id=checking.id,
            category_id=salary.id,
        )
    )
    txns.create(
        Transaction(
            occurred_on=date(2026, 2, 3),
            amount_cents=4500,
            description="Coffee shop",
            account_id=checking.id,
            category_id=food.id,
        )
    )
    txns.create(
        Transaction(
            occurred_on=date(2026, 2, 8),
            amount_cents=12000,
            description="Grocery run",
            notes="Whole Foods",
            account_id=checking.id,
            category_id=food.id,
        )
    )
    txns.create(
        Transaction(
            occurred_on=date(2026, 2, 15),
            amount_cents=50000,
            description="Move to savings",
            account_id=savings.id,
            category_id=transfer.id,
        )
    )
    txns.create(
        Transaction(
            occurred_on=date(2026, 3, 2),
            amount_cents=8000,
            description="Lunch",
            account_id=checking.id,
            category_id=food.id,
        )
    )
    return {
        "checking": checking,
        "savings": savings,
        "food": food,
        "salary": salary,
        "transfer": transfer,
    }


class TransactionRepositoryTests(unittest.TestCase):
    def test_create_and_get(self):
        with TempDatabase() as conn:
            seed = _seed(conn)
            txns = TransactionRepository(conn)
            t = txns.create(
                Transaction(
                    occurred_on=date(2026, 4, 1),
                    amount_cents=1000,
                    description="Test",
                    account_id=seed["checking"].id,
                )
            )
            self.assertIsNotNone(t.id)
            self.assertEqual(txns.get(t.id).description, "Test")

    def test_get_missing_raises(self):
        with TempDatabase() as conn:
            with self.assertRaises(NotFoundError):
                TransactionRepository(conn).get(1)

    def test_list_default_orders_newest_first(self):
        with TempDatabase() as conn:
            _seed(conn)
            results = TransactionRepository(conn).list()
            dates = [t.occurred_on for t in results]
            self.assertEqual(dates, sorted(dates, reverse=True))

    def test_filter_by_account(self):
        with TempDatabase() as conn:
            seed = _seed(conn)
            results = TransactionRepository(conn).list(
                TransactionFilter(account_ids=[seed["savings"].id])
            )
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].account_id, seed["savings"].id)

    def test_filter_by_date_range(self):
        with TempDatabase() as conn:
            _seed(conn)
            results = TransactionRepository(conn).list(
                TransactionFilter(
                    date_from=date(2026, 2, 1),
                    date_to=date(2026, 2, 10),
                )
            )
            self.assertEqual(len(results), 3)

    def test_filter_by_amount_range(self):
        with TempDatabase() as conn:
            _seed(conn)
            results = TransactionRepository(conn).list(
                TransactionFilter(min_amount_cents=10000, max_amount_cents=60000)
            )
            self.assertEqual(sorted(t.amount_cents for t in results), [12000, 50000])

    def test_filter_by_category(self):
        with TempDatabase() as conn:
            seed = _seed(conn)
            results = TransactionRepository(conn).list(
                TransactionFilter(category_ids=[seed["food"].id])
            )
            self.assertEqual(len(results), 3)

    def test_search_matches_description_and_notes(self):
        with TempDatabase() as conn:
            _seed(conn)
            repo = TransactionRepository(conn)
            self.assertEqual(
                len(repo.list(TransactionFilter(search="grocery"))), 1
            )
            self.assertEqual(
                len(repo.list(TransactionFilter(search="Whole Foods"))), 1
            )

    def test_combined_filters(self):
        with TempDatabase() as conn:
            seed = _seed(conn)
            results = TransactionRepository(conn).list(
                TransactionFilter(
                    account_ids=[seed["checking"].id],
                    category_ids=[seed["food"].id],
                    date_from=date(2026, 2, 1),
                    date_to=date(2026, 2, 28),
                )
            )
            self.assertEqual(len(results), 2)

    def test_pagination(self):
        with TempDatabase() as conn:
            _seed(conn)
            repo = TransactionRepository(conn)
            page1 = repo.list(TransactionFilter(limit=2, offset=0))
            page2 = repo.list(TransactionFilter(limit=2, offset=2))
            self.assertEqual(len(page1), 2)
            self.assertEqual(len(page2), 2)
            ids1 = {t.id for t in page1}
            ids2 = {t.id for t in page2}
            self.assertTrue(ids1.isdisjoint(ids2))

    def test_count(self):
        with TempDatabase() as conn:
            seed = _seed(conn)
            repo = TransactionRepository(conn)
            self.assertEqual(repo.count(), 5)
            self.assertEqual(
                repo.count(TransactionFilter(category_ids=[seed["food"].id])), 3
            )

    def test_invalid_order_rejected(self):
        with TempDatabase() as conn:
            _seed(conn)
            with self.assertRaises(ValueError):
                TransactionRepository(conn).list(
                    TransactionFilter(order="DROP TABLE transactions")
                )

    def test_update(self):
        with TempDatabase() as conn:
            seed = _seed(conn)
            repo = TransactionRepository(conn)
            t = repo.list(TransactionFilter(limit=1))[0]
            t.description = "Updated"
            t.amount_cents = 9999
            updated = repo.update(t)
            self.assertEqual(updated.description, "Updated")
            self.assertEqual(updated.amount_cents, 9999)

    def test_delete(self):
        with TempDatabase() as conn:
            _seed(conn)
            repo = TransactionRepository(conn)
            t = repo.list(TransactionFilter(limit=1))[0]
            repo.delete(t.id)
            with self.assertRaises(NotFoundError):
                repo.get(t.id)

    def test_bulk_create(self):
        with TempDatabase() as conn:
            seed = _seed(conn)
            repo = TransactionRepository(conn)
            new = [
                Transaction(
                    occurred_on=date(2026, 5, 1),
                    amount_cents=100 + i,
                    description=f"Bulk {i}",
                    account_id=seed["checking"].id,
                )
                for i in range(20)
            ]
            inserted = repo.bulk_create(new)
            self.assertEqual(inserted, 20)
            self.assertEqual(repo.count(), 25)

    def test_account_delete_cascades_to_transactions(self):
        with TempDatabase() as conn:
            seed = _seed(conn)
            AccountRepository(conn).delete(seed["savings"].id)
            results = TransactionRepository(conn).list(
                TransactionFilter(account_ids=[seed["savings"].id])
            )
            self.assertEqual(results, [])

    def test_category_delete_keeps_transactions_uncategorized(self):
        with TempDatabase() as conn:
            seed = _seed(conn)
            CategoryRepository(conn).delete(seed["food"].id)
            results = TransactionRepository(conn).list(
                TransactionFilter(account_ids=[seed["checking"].id])
            )
            food_txns = [t for t in results if "Coffee" in t.description or "Lunch" in t.description]
            self.assertTrue(food_txns)
            for t in food_txns:
                self.assertIsNone(t.category_id)


if __name__ == "__main__":
    unittest.main()
