"""Tests for ``AccountRepository``."""

from __future__ import annotations

import unittest

from finance_tracker.exceptions import DuplicateError, NotFoundError
from finance_tracker.models import Account, AccountType
from finance_tracker.repositories.accounts import AccountRepository

from tests.support import TempDatabase


def _make(name="Main Checking", type=AccountType.CHECKING, opening=0, archived=False):
    return Account(
        name=name,
        type=type,
        opening_balance_cents=opening,
        archived=archived,
    )


class AccountRepositoryTests(unittest.TestCase):
    def test_create_and_get(self):
        with TempDatabase() as conn:
            repo = AccountRepository(conn)
            saved = repo.create(_make(opening=10000))
            self.assertIsNotNone(saved.id)
            self.assertEqual(saved.opening_balance_cents, 10000)
            self.assertIsNotNone(saved.created_at)

            fetched = repo.get(saved.id)
            self.assertEqual(fetched.name, saved.name)
            self.assertEqual(fetched.type, AccountType.CHECKING)

    def test_get_missing_raises(self):
        with TempDatabase() as conn:
            with self.assertRaises(NotFoundError):
                AccountRepository(conn).get(999)

    def test_find_by_name_returns_none_when_missing(self):
        with TempDatabase() as conn:
            self.assertIsNone(AccountRepository(conn).find_by_name("nope"))

    def test_duplicate_name_raises(self):
        with TempDatabase() as conn:
            repo = AccountRepository(conn)
            repo.create(_make())
            with self.assertRaises(DuplicateError):
                repo.create(_make())

    def test_list_excludes_archived_by_default(self):
        with TempDatabase() as conn:
            repo = AccountRepository(conn)
            repo.create(_make("A"))
            repo.create(_make("B", archived=True))
            names = [a.name for a in repo.list()]
            self.assertEqual(names, ["A"])
            all_names = [a.name for a in repo.list(include_archived=True)]
            self.assertEqual(sorted(all_names), ["A", "B"])

    def test_list_orders_case_insensitively(self):
        with TempDatabase() as conn:
            repo = AccountRepository(conn)
            for n in ["zebra", "Apple", "banana"]:
                repo.create(_make(name=n))
            self.assertEqual([a.name for a in repo.list()], ["Apple", "banana", "zebra"])

    def test_update(self):
        with TempDatabase() as conn:
            repo = AccountRepository(conn)
            saved = repo.create(_make(opening=100))
            saved.opening_balance_cents = 999
            saved.name = "Renamed"
            updated = repo.update(saved)
            self.assertEqual(updated.opening_balance_cents, 999)
            self.assertEqual(updated.name, "Renamed")

    def test_update_missing_raises(self):
        with TempDatabase() as conn:
            ghost = _make()
            ghost.id = 1234
            with self.assertRaises(NotFoundError):
                AccountRepository(conn).update(ghost)

    def test_update_to_existing_name_raises(self):
        with TempDatabase() as conn:
            repo = AccountRepository(conn)
            a = repo.create(_make("A"))
            repo.create(_make("B"))
            a.name = "B"
            with self.assertRaises(DuplicateError):
                repo.update(a)

    def test_archive(self):
        with TempDatabase() as conn:
            repo = AccountRepository(conn)
            saved = repo.create(_make())
            archived = repo.archive(saved.id)
            self.assertTrue(archived.archived)

    def test_delete(self):
        with TempDatabase() as conn:
            repo = AccountRepository(conn)
            saved = repo.create(_make())
            repo.delete(saved.id)
            with self.assertRaises(NotFoundError):
                repo.get(saved.id)

    def test_delete_missing_raises(self):
        with TempDatabase() as conn:
            with self.assertRaises(NotFoundError):
                AccountRepository(conn).delete(42)


if __name__ == "__main__":
    unittest.main()
