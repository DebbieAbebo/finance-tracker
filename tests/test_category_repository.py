"""Tests for ``CategoryRepository``."""

from __future__ import annotations

import unittest

from finance_tracker.exceptions import DuplicateError, NotFoundError
from finance_tracker.models import Category, CategoryKind
from finance_tracker.repositories.categories import CategoryRepository

from tests.support import TempDatabase


class CategoryRepositoryTests(unittest.TestCase):
    def test_create_top_level(self):
        with TempDatabase() as conn:
            repo = CategoryRepository(conn)
            cat = repo.create(Category(name="Food", kind=CategoryKind.EXPENSE))
            self.assertIsNotNone(cat.id)
            self.assertIsNone(cat.parent_id)

    def test_hierarchy_and_full_path(self):
        with TempDatabase() as conn:
            repo = CategoryRepository(conn)
            food = repo.create(Category(name="Food", kind=CategoryKind.EXPENSE))
            groc = repo.create(
                Category(name="Groceries", kind=CategoryKind.EXPENSE, parent_id=food.id)
            )
            org = repo.create(
                Category(name="Organic", kind=CategoryKind.EXPENSE, parent_id=groc.id)
            )
            self.assertEqual(repo.full_path(org), "Food.Groceries.Organic")
            self.assertEqual(repo.full_path(food), "Food")

    def test_find_by_path(self):
        with TempDatabase() as conn:
            repo = CategoryRepository(conn)
            food = repo.create(Category(name="Food", kind=CategoryKind.EXPENSE))
            groc = repo.create(
                Category(name="Groceries", kind=CategoryKind.EXPENSE, parent_id=food.id)
            )
            self.assertEqual(repo.find_by_path("Food.Groceries").id, groc.id)
            self.assertEqual(repo.find_by_path("Food").id, food.id)
            self.assertIsNone(repo.find_by_path("Food.Nope"))
            self.assertIsNone(repo.find_by_path(""))

    def test_find_by_path_falls_back_to_unambiguous_leaf(self):
        with TempDatabase() as conn:
            repo = CategoryRepository(conn)
            food = repo.create(Category(name="Food", kind=CategoryKind.EXPENSE))
            groc = repo.create(
                Category(name="Groceries", kind=CategoryKind.EXPENSE, parent_id=food.id)
            )
            # "Groceries" is unique anywhere in the tree, so the leaf-name
            # shortcut should resolve it without the dotted path.
            self.assertEqual(repo.find_by_path("Groceries").id, groc.id)

    def test_find_by_path_does_not_guess_when_ambiguous(self):
        with TempDatabase() as conn:
            repo = CategoryRepository(conn)
            food = repo.create(Category(name="Food", kind=CategoryKind.EXPENSE))
            travel = repo.create(Category(name="Travel", kind=CategoryKind.EXPENSE))
            repo.create(Category(name="Misc", kind=CategoryKind.EXPENSE, parent_id=food.id))
            repo.create(Category(name="Misc", kind=CategoryKind.EXPENSE, parent_id=travel.id))
            # Two "Misc" categories exist — leaf-name shortcut must not
            # silently pick one. Caller has to use the full dotted path.
            self.assertIsNone(repo.find_by_path("Misc"))

    def test_duplicate_at_same_level(self):
        with TempDatabase() as conn:
            repo = CategoryRepository(conn)
            food = repo.create(Category(name="Food", kind=CategoryKind.EXPENSE))
            # Same name under the same non-null parent should fail.
            repo.create(Category(name="Sub", kind=CategoryKind.EXPENSE, parent_id=food.id))
            with self.assertRaises(DuplicateError):
                repo.create(
                    Category(name="Sub", kind=CategoryKind.EXPENSE, parent_id=food.id)
                )

    def test_duplicate_top_level_name_rejected(self):
        # Regression: SQLite's UNIQUE constraint treats NULL != NULL, so
        # a plain UNIQUE(name, parent_id) didn't catch two top-level
        # categories with the same name. We use a partial unique index now.
        with TempDatabase() as conn:
            repo = CategoryRepository(conn)
            repo.create(Category(name="Food", kind=CategoryKind.EXPENSE))
            with self.assertRaises(DuplicateError):
                repo.create(Category(name="Food", kind=CategoryKind.EXPENSE))

    def test_same_name_under_different_parents_is_allowed(self):
        with TempDatabase() as conn:
            repo = CategoryRepository(conn)
            food = repo.create(Category(name="Food", kind=CategoryKind.EXPENSE))
            travel = repo.create(Category(name="Travel", kind=CategoryKind.EXPENSE))
            # "Misc" can exist under both parents.
            repo.create(Category(name="Misc", kind=CategoryKind.EXPENSE, parent_id=food.id))
            repo.create(Category(name="Misc", kind=CategoryKind.EXPENSE, parent_id=travel.id))

    def test_descendants_of_collects_subtree(self):
        with TempDatabase() as conn:
            repo = CategoryRepository(conn)
            food = repo.create(Category(name="Food", kind=CategoryKind.EXPENSE))
            groc = repo.create(
                Category(name="Groceries", kind=CategoryKind.EXPENSE, parent_id=food.id)
            )
            rest = repo.create(
                Category(name="Restaurants", kind=CategoryKind.EXPENSE, parent_id=food.id)
            )
            org = repo.create(
                Category(name="Organic", kind=CategoryKind.EXPENSE, parent_id=groc.id)
            )
            ids = repo.descendants_of(food.id)
            self.assertEqual(set(ids), {food.id, groc.id, rest.id, org.id})

    def test_list_filters_by_kind(self):
        with TempDatabase() as conn:
            repo = CategoryRepository(conn)
            repo.create(Category(name="Salary", kind=CategoryKind.INCOME))
            repo.create(Category(name="Food", kind=CategoryKind.EXPENSE))
            repo.create(Category(name="Transfer", kind=CategoryKind.TRANSFER))
            expense_names = [c.name for c in repo.list(kind=CategoryKind.EXPENSE)]
            self.assertEqual(expense_names, ["Food"])

    def test_delete_cascades_to_children(self):
        with TempDatabase() as conn:
            repo = CategoryRepository(conn)
            food = repo.create(Category(name="Food", kind=CategoryKind.EXPENSE))
            groc = repo.create(
                Category(name="Groceries", kind=CategoryKind.EXPENSE, parent_id=food.id)
            )
            repo.delete(food.id)
            with self.assertRaises(NotFoundError):
                repo.get(groc.id)


if __name__ == "__main__":
    unittest.main()
