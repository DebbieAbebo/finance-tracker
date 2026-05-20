"""Tests for ``RecurringMaterializer``."""

from __future__ import annotations

import unittest
from datetime import date

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
from finance_tracker.repositories.transactions import (
    TransactionFilter,
    TransactionRepository,
)
from finance_tracker.services.recurring import (
    RecurringMaterializer,
    _add_months,
    _occurrences,
)

from tests.support import TempDatabase


def _seed(conn):
    accounts = AccountRepository(conn)
    cats = CategoryRepository(conn)
    checking = accounts.create(Account(name="Checking", type=AccountType.CHECKING))
    rent_cat = cats.create(Category(name="Rent", kind=CategoryKind.EXPENSE))
    return checking, rent_cat


def _template(checking_id, cat_id, **overrides):
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


class AddMonthsTests(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(_add_months(date(2026, 1, 15), 1), date(2026, 2, 15))

    def test_clamps_to_last_day(self):
        # Jan 31 + 1 month -> Feb 28 (in 2026)
        self.assertEqual(_add_months(date(2026, 1, 31), 1), date(2026, 2, 28))

    def test_year_rollover(self):
        self.assertEqual(_add_months(date(2026, 11, 5), 3), date(2027, 2, 5))

    def test_leap_year(self):
        # Adding 1 month to Jan 30 in 2024 (leap year) lands on Feb 29
        self.assertEqual(_add_months(date(2024, 1, 30), 1), date(2024, 2, 29))


class OccurrencesTests(unittest.TestCase):
    def test_monthly(self):
        with TempDatabase() as conn:
            checking, cat = _seed(conn)
            t = _template(checking.id, cat.id)
            dates = list(_occurrences(t, through=date(2026, 4, 15)))
            self.assertEqual(
                dates,
                [date(2026, 1, 1), date(2026, 2, 1), date(2026, 3, 1), date(2026, 4, 1)],
            )

    def test_weekly_with_interval(self):
        with TempDatabase() as conn:
            checking, cat = _seed(conn)
            t = _template(
                checking.id,
                cat.id,
                cadence=Cadence.WEEKLY,
                interval=2,
                starts_on=date(2026, 1, 1),
            )
            dates = list(_occurrences(t, through=date(2026, 1, 31)))
            self.assertEqual(
                dates, [date(2026, 1, 1), date(2026, 1, 15), date(2026, 1, 29)]
            )

    def test_ends_on_truncates(self):
        with TempDatabase() as conn:
            checking, cat = _seed(conn)
            t = _template(checking.id, cat.id, ends_on=date(2026, 2, 15))
            dates = list(_occurrences(t, through=date(2026, 12, 31)))
            self.assertEqual(dates, [date(2026, 1, 1), date(2026, 2, 1)])

    def test_resumes_from_last_materialized(self):
        with TempDatabase() as conn:
            checking, cat = _seed(conn)
            t = _template(
                checking.id, cat.id, last_materialized_on=date(2026, 2, 1)
            )
            dates = list(_occurrences(t, through=date(2026, 5, 15)))
            self.assertEqual(
                dates, [date(2026, 3, 1), date(2026, 4, 1), date(2026, 5, 1)]
            )


class MaterializerTests(unittest.TestCase):
    def test_creates_expected_transactions(self):
        with TempDatabase() as conn:
            checking, cat = _seed(conn)
            templates = RecurringTransactionRepository(conn)
            templates.create(_template(checking.id, cat.id))

            mat = RecurringMaterializer(conn)
            results = mat.run(through=date(2026, 4, 15))
            self.assertEqual(results[0].created, 4)

            txns = TransactionRepository(conn).list()
            self.assertEqual(len(txns), 4)
            self.assertTrue(all(t.amount_cents == 180_000 for t in txns))

    def test_running_twice_is_idempotent(self):
        with TempDatabase() as conn:
            checking, cat = _seed(conn)
            templates = RecurringTransactionRepository(conn)
            templates.create(_template(checking.id, cat.id))

            mat = RecurringMaterializer(conn)
            mat.run(through=date(2026, 3, 15))
            results2 = mat.run(through=date(2026, 3, 15))
            self.assertEqual(results2, [])
            self.assertEqual(TransactionRepository(conn).count(), 3)

    def test_subsequent_runs_pick_up_from_last(self):
        with TempDatabase() as conn:
            checking, cat = _seed(conn)
            templates = RecurringTransactionRepository(conn)
            templates.create(_template(checking.id, cat.id))

            mat = RecurringMaterializer(conn)
            mat.run(through=date(2026, 2, 15))
            mat.run(through=date(2026, 4, 15))

            self.assertEqual(TransactionRepository(conn).count(), 4)

    def test_inactive_templates_are_skipped(self):
        with TempDatabase() as conn:
            checking, cat = _seed(conn)
            templates = RecurringTransactionRepository(conn)
            templates.create(_template(checking.id, cat.id, active=False))

            results = RecurringMaterializer(conn).run(through=date(2026, 12, 31))
            self.assertEqual(results, [])
            self.assertEqual(TransactionRepository(conn).count(), 0)

    def test_uses_template_description_when_set(self):
        with TempDatabase() as conn:
            checking, cat = _seed(conn)
            templates = RecurringTransactionRepository(conn)
            templates.create(
                _template(checking.id, cat.id, description="Apt 4B rent")
            )
            RecurringMaterializer(conn).run(through=date(2026, 1, 31))
            t = TransactionRepository(conn).list(TransactionFilter(limit=1))[0]
            self.assertEqual(t.description, "Apt 4B rent")


if __name__ == "__main__":
    unittest.main()
