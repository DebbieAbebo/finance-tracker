"""Tests for ``CsvImporter``."""

from __future__ import annotations

import io
import unittest
from datetime import date

from finance_tracker.exceptions import NotFoundError, ValidationError
from finance_tracker.models import (
    Account,
    AccountType,
    Category,
    CategoryKind,
)
from finance_tracker.repositories.accounts import AccountRepository
from finance_tracker.repositories.categories import CategoryRepository
from finance_tracker.repositories.transactions import TransactionRepository
from finance_tracker.services.importer import CsvImporter

from tests.support import TempDatabase


def _seed(conn):
    AccountRepository(conn).create(Account(name="Checking", type=AccountType.CHECKING))
    cats = CategoryRepository(conn)
    food = cats.create(Category(name="Food", kind=CategoryKind.EXPENSE))
    cats.create(Category(name="Groceries", kind=CategoryKind.EXPENSE, parent_id=food.id))


class CsvImporterTests(unittest.TestCase):
    def test_imports_simple_csv(self):
        with TempDatabase() as conn:
            _seed(conn)
            csv_data = io.StringIO(
                "date,amount,description,category\n"
                "2026-03-01,12.34,Coffee,Food\n"
                "2026-03-02,55.00,Trader Joe's,Food.Groceries\n"
            )
            result = CsvImporter(conn).import_file(csv_data, account_name="Checking")
            self.assertEqual(result.imported, 2)
            self.assertEqual(result.skipped, 0)
            txns = TransactionRepository(conn).list()
            self.assertEqual(len(txns), 2)
            self.assertEqual({t.amount_cents for t in txns}, {1234, 5500})

    def test_unknown_category_skips_row(self):
        with TempDatabase() as conn:
            _seed(conn)
            csv_data = io.StringIO(
                "date,amount,description,category\n"
                "2026-03-01,12.34,Coffee,DoesNotExist\n"
                "2026-03-02,5.00,Lunch,Food\n"
            )
            result = CsvImporter(conn).import_file(csv_data, account_name="Checking")
            self.assertEqual(result.imported, 1)
            self.assertEqual(result.skipped, 1)
            self.assertIn("DoesNotExist", result.errors[0])

    def test_signed_amounts_absolutized(self):
        with TempDatabase() as conn:
            _seed(conn)
            csv_data = io.StringIO(
                "date,amount,description,category\n"
                "2026-03-01,-12.34,Coffee,Food\n"
                "2026-03-02,5.00,Lunch,Food\n"
            )
            CsvImporter(conn).import_file(csv_data, account_name="Checking")
            amounts = sorted(t.amount_cents for t in TransactionRepository(conn).list())
            self.assertEqual(amounts, [500, 1234])

    def test_missing_required_columns_raises(self):
        with TempDatabase() as conn:
            _seed(conn)
            csv_data = io.StringIO("date,amount\n2026-03-01,5\n")
            with self.assertRaises(ValidationError):
                CsvImporter(conn).import_file(csv_data, account_name="Checking")

    def test_missing_account_raises(self):
        with TempDatabase() as conn:
            _seed(conn)
            csv_data = io.StringIO("date,amount,description\n2026-03-01,5,Test\n")
            with self.assertRaises(NotFoundError):
                CsvImporter(conn).import_file(csv_data, account_name="Nonexistent")

    def test_blank_lines_skipped(self):
        with TempDatabase() as conn:
            _seed(conn)
            csv_data = io.StringIO(
                "date,amount,description,category\n"
                "2026-03-01,1.00,A,Food\n"
                ",,,\n"
                "2026-03-02,2.00,B,Food\n"
            )
            result = CsvImporter(conn).import_file(csv_data, account_name="Checking")
            self.assertEqual(result.imported, 2)

    def test_optional_notes_column(self):
        with TempDatabase() as conn:
            _seed(conn)
            csv_data = io.StringIO(
                "date,amount,description,category,notes\n"
                "2026-03-01,12.34,Coffee,Food,Birthday treat\n"
            )
            CsvImporter(conn).import_file(csv_data, account_name="Checking")
            t = TransactionRepository(conn).list()[0]
            self.assertEqual(t.notes, "Birthday treat")

    def test_dates_in_alternative_formats(self):
        with TempDatabase() as conn:
            _seed(conn)
            csv_data = io.StringIO(
                'date,amount,description,category\n'
                '2026-03-01,1.00,ISO,Food\n'
                '"March 5, 2026",2.00,Long form,Food\n'
            )
            CsvImporter(conn).import_file(csv_data, account_name="Checking")
            dates = sorted(t.occurred_on for t in TransactionRepository(conn).list())
            self.assertEqual(dates, [date(2026, 3, 1), date(2026, 3, 5)])

    def test_malformed_row_skipped_with_error(self):
        # Unquoted comma inside a field produces extra columns. Should
        # be reported as a row error, not crash the whole import.
        with TempDatabase() as conn:
            _seed(conn)
            csv_data = io.StringIO(
                "date,amount,description,category\n"
                "March 5, 2026,2.00,Long form,Food\n"
                "2026-03-01,1.00,Good row,Food\n"
            )
            result = CsvImporter(conn).import_file(csv_data, account_name="Checking")
            self.assertEqual(result.imported, 1)
            self.assertEqual(result.skipped, 1)


if __name__ == "__main__":
    unittest.main()
