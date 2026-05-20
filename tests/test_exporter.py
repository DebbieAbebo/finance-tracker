"""Tests for ``TransactionExporter``."""

from __future__ import annotations

import io
import json
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
from finance_tracker.repositories.transactions import (
    TransactionFilter,
    TransactionRepository,
)
from finance_tracker.services.exporter import CSV_HEADERS, TransactionExporter
from finance_tracker.services.importer import CsvImporter

from tests.support import TempDatabase


def _seed(conn):
    accounts = AccountRepository(conn)
    cats = CategoryRepository(conn)
    txns = TransactionRepository(conn)

    checking = accounts.create(Account(name="Checking", type=AccountType.CHECKING))
    food = cats.create(Category(name="Food", kind=CategoryKind.EXPENSE))
    groc = cats.create(Category(name="Groceries", kind=CategoryKind.EXPENSE, parent_id=food.id))

    txns.create(
        Transaction(
            occurred_on=date(2026, 4, 1),
            amount_cents=1234,
            description="Coffee",
            account_id=checking.id,
            category_id=food.id,
        )
    )
    txns.create(
        Transaction(
            occurred_on=date(2026, 4, 2),
            amount_cents=4500,
            description="Trader Joe's",
            notes="weekly run",
            account_id=checking.id,
            category_id=groc.id,
        )
    )


class CsvExportTests(unittest.TestCase):
    def test_csv_round_trip(self):
        with TempDatabase() as conn:
            _seed(conn)
            buf = io.StringIO()
            n = TransactionExporter(conn).to_csv(buf)
            self.assertEqual(n, 2)
            text = buf.getvalue()
            self.assertEqual(text.splitlines()[0].split(","), CSV_HEADERS)

        # Re-import into a fresh database and verify counts and amounts match.
        with TempDatabase() as conn2:
            AccountRepository(conn2).create(Account(name="Checking", type=AccountType.CHECKING))
            cats = CategoryRepository(conn2)
            food = cats.create(Category(name="Food", kind=CategoryKind.EXPENSE))
            cats.create(Category(name="Groceries", kind=CategoryKind.EXPENSE, parent_id=food.id))

            buf.seek(0)
            CsvImporter(conn2).import_file(buf, account_name="Checking")
            txns = TransactionRepository(conn2).list()
            self.assertEqual(len(txns), 2)
            self.assertEqual(sorted(t.amount_cents for t in txns), [1234, 4500])

    def test_csv_export_with_filter(self):
        with TempDatabase() as conn:
            _seed(conn)
            buf = io.StringIO()
            TransactionExporter(conn).to_csv(
                buf,
                criteria=TransactionFilter(min_amount_cents=2000),
            )
            lines = [l for l in buf.getvalue().splitlines() if l]
            self.assertEqual(len(lines), 2)  # header + 1 data row


class JsonExportTests(unittest.TestCase):
    def test_json_export(self):
        with TempDatabase() as conn:
            _seed(conn)
            buf = io.StringIO()
            n = TransactionExporter(conn).to_json(buf)
            self.assertEqual(n, 2)
            data = json.loads(buf.getvalue())
            self.assertEqual(len(data), 2)
            categories = {row["category"] for row in data}
            self.assertEqual(categories, {"Food", "Food.Groceries"})

    def test_json_includes_account_name(self):
        with TempDatabase() as conn:
            _seed(conn)
            buf = io.StringIO()
            TransactionExporter(conn).to_json(buf)
            data = json.loads(buf.getvalue())
            self.assertTrue(all(row["account"] == "Checking" for row in data))


if __name__ == "__main__":
    unittest.main()
