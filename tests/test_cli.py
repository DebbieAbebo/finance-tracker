"""End-to-end CLI tests via ``click.testing.CliRunner``.

Each test redirects the database to a temp path via the FINANCE_DATABASE_PATH
env var so we don't touch the user's real database.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from finance_tracker.cli import main


class CliTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "test.db"
        self._env_patch = patch.dict(
            os.environ, {"FINANCE_DATABASE_PATH": str(self.db_path)}, clear=False
        )
        self._env_patch.start()
        self.runner = CliRunner()

    def tearDown(self) -> None:
        self._env_patch.stop()
        self.tmp.cleanup()

    def run_cli(self, *args, expect_exit: int = 0):
        result = self.runner.invoke(main, list(args), catch_exceptions=False)
        self.assertEqual(
            result.exit_code,
            expect_exit,
            msg=f"exit={result.exit_code}\nstdout:\n{result.output}\nstderr:\n{result.stderr if result.stderr_bytes is not None else ''}",
        )
        return result


class AccountCommandsTests(CliTestBase):
    def test_add_and_list(self):
        self.run_cli("account", "add", "Checking", "--type", "checking")
        result = self.run_cli("account", "list")
        self.assertIn("Checking", result.output)
        self.assertIn("checking", result.output)

    def test_duplicate_name_fails(self):
        self.run_cli("account", "add", "X", "--type", "cash")
        result = self.run_cli("account", "add", "X", "--type", "cash", expect_exit=1)
        self.assertIn("error", result.output.lower() + (result.stderr or ""))

    def test_archive(self):
        self.run_cli("account", "add", "Old", "--type", "savings")
        self.run_cli("account", "archive", "Old")
        without = self.run_cli("account", "list").output
        self.assertNotIn("Old", without)
        with_archived = self.run_cli("account", "list", "--all").output
        self.assertIn("Old", with_archived)


class CategoryCommandsTests(CliTestBase):
    def test_add_with_parent(self):
        self.run_cli("category", "add", "Food", "--kind", "expense")
        self.run_cli(
            "category", "add", "Groceries", "--kind", "expense", "--parent", "Food"
        )
        out = self.run_cli("category", "list").output
        self.assertIn("Food.Groceries", out)


class TransactionCommandsTests(CliTestBase):
    def _setup_world(self):
        self.run_cli("account", "add", "Checking", "--type", "checking")
        self.run_cli("category", "add", "Food", "--kind", "expense")

    def test_add_and_list(self):
        self._setup_world()
        self.run_cli(
            "transaction",
            "add",
            "12.34",
            "--account",
            "Checking",
            "--category",
            "Food",
            "--description",
            "Coffee",
            "--date",
            "2026-04-01",
        )
        out = self.run_cli("transaction", "list").output
        self.assertIn("Coffee", out)
        self.assertIn("12.34", out)

    def test_filter_by_account(self):
        self._setup_world()
        self.run_cli("account", "add", "Cash", "--type", "cash")
        self.run_cli(
            "transaction", "add", "1.00", "--account", "Checking", "--description", "A"
        )
        self.run_cli(
            "transaction", "add", "2.00", "--account", "Cash", "--description", "B"
        )
        out = self.run_cli(
            "transaction", "list", "--account", "Cash"
        ).output
        self.assertIn("B", out)
        self.assertNotIn(" A ", out)


class ReportCommandsTests(CliTestBase):
    def test_balances(self):
        self.run_cli("account", "add", "C", "--type", "checking", "--opening-balance", "500")
        out = self.run_cli("report", "balances").output
        self.assertIn("500.00", out)

    def test_monthly_summary(self):
        self.run_cli("account", "add", "C", "--type", "checking")
        self.run_cli("category", "add", "Food", "--kind", "expense")
        self.run_cli(
            "transaction",
            "add",
            "10",
            "--account",
            "C",
            "--category",
            "Food",
            "--date",
            "2026-04-15",
        )
        out = self.run_cli(
            "report", "monthly", "--from", "2026-04-01", "--to", "2026-04-30"
        ).output
        self.assertIn("2026-04", out)


class ImportExportCommandsTests(CliTestBase):
    def test_round_trip(self):
        self.run_cli("account", "add", "Checking", "--type", "checking")
        self.run_cli("category", "add", "Food", "--kind", "expense")
        # add a couple of transactions
        for desc, amt, d in [("A", "10", "2026-04-01"), ("B", "20", "2026-04-02")]:
            self.run_cli(
                "transaction",
                "add",
                amt,
                "--account",
                "Checking",
                "--category",
                "Food",
                "--description",
                desc,
                "--date",
                d,
            )
        export_path = Path(self.tmp.name) / "out.csv"
        self.run_cli("export", str(export_path), "--format", "csv")
        self.assertTrue(export_path.exists())
        content = export_path.read_text()
        self.assertIn("A", content)
        self.assertIn("B", content)


class RecurringCommandsTests(CliTestBase):
    def test_add_list_and_run(self):
        self.run_cli("account", "add", "Checking", "--type", "checking")
        self.run_cli("category", "add", "Rent", "--kind", "expense")
        self.run_cli(
            "recurring",
            "add",
            "--name",
            "Rent",
            "--amount",
            "1500",
            "--account",
            "Checking",
            "--category",
            "Rent",
            "--cadence",
            "monthly",
            "--starts-on",
            "2026-01-01",
        )
        listing = self.run_cli("recurring", "list").output
        self.assertIn("Rent", listing)

        self.run_cli("recurring", "run", "--through", "2026-03-31")
        txns_out = self.run_cli("transaction", "list").output
        # 3 monthly occurrences: Jan 1, Feb 1, Mar 1
        self.assertEqual(txns_out.count("2026-"), 3)


if __name__ == "__main__":
    unittest.main()
