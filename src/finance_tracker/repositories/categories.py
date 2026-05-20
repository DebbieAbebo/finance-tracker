"""Persistence for ``Category``."""

from __future__ import annotations

import sqlite3
from datetime import datetime

from ._helpers import parse_timestamp
from typing import Optional

from ..exceptions import DuplicateError, NotFoundError
from ..models import Category, CategoryKind


def _row_to_category(row: sqlite3.Row) -> Category:
    return Category(
        id=row["id"],
        name=row["name"],
        kind=CategoryKind(row["kind"]),
        parent_id=row["parent_id"],
        created_at=parse_timestamp(row["created_at"]),
        updated_at=parse_timestamp(row["updated_at"]),
    )


class CategoryRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def get(self, category_id: int) -> Category:
        row = self._conn.execute(
            "SELECT * FROM categories WHERE id = ?", (category_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"category id={category_id} not found")
        return _row_to_category(row)

    def find_by_path(self, path: str) -> Optional[Category]:
        """Look up a category by its dotted path, e.g. ``Food.Groceries``.

        If the input has no dot and there is a unique category with that
        name anywhere in the tree, fall back to that. Keeps the CLI
        usable when the user knows the leaf but not the full path.
        """
        parts = [p.strip() for p in path.split(".") if p.strip()]
        if not parts:
            return None

        # Pure leaf-name lookup (no dots) — accept iff unambiguous.
        if len(parts) == 1:
            rows = self._conn.execute(
                "SELECT * FROM categories WHERE name = ?", (parts[0],)
            ).fetchall()
            if len(rows) == 1:
                return _row_to_category(rows[0])
            # Two or more matches: fall through to strict path resolution
            # below, which will require an exact match against parent_id.

        parent_id: Optional[int] = None
        node: Optional[Category] = None
        for part in parts:
            if parent_id is None:
                row = self._conn.execute(
                    "SELECT * FROM categories WHERE name = ? AND parent_id IS NULL",
                    (part,),
                ).fetchone()
            else:
                row = self._conn.execute(
                    "SELECT * FROM categories WHERE name = ? AND parent_id = ?",
                    (part, parent_id),
                ).fetchone()
            if row is None:
                return None
            node = _row_to_category(row)
            parent_id = node.id
        return node

    def list(self, *, kind: Optional[CategoryKind] = None) -> list[Category]:
        sql = "SELECT * FROM categories"
        params: tuple = ()
        if kind is not None:
            sql += " WHERE kind = ?"
            params = (kind.value,)
        sql += " ORDER BY name COLLATE NOCASE"
        return [_row_to_category(r) for r in self._conn.execute(sql, params).fetchall()]

    def children_of(self, parent_id: Optional[int]) -> list[Category]:
        if parent_id is None:
            sql = "SELECT * FROM categories WHERE parent_id IS NULL ORDER BY name"
            params: tuple = ()
        else:
            sql = "SELECT * FROM categories WHERE parent_id = ? ORDER BY name"
            params = (parent_id,)
        return [_row_to_category(r) for r in self._conn.execute(sql, params).fetchall()]

    def descendants_of(self, category_id: int) -> list[int]:
        """Return ids of ``category_id`` and all of its descendants.

        Used by reports that want to roll up child categories under a
        parent. Implemented as an iterative BFS in Python so we don't
        need WITH RECURSIVE — the trees are tiny in practice.
        """
        all_ids: list[int] = [category_id]
        frontier: list[int] = [category_id]
        while frontier:
            placeholders = ",".join("?" for _ in frontier)
            rows = self._conn.execute(
                f"SELECT id FROM categories WHERE parent_id IN ({placeholders})",
                frontier,
            ).fetchall()
            next_frontier = [r["id"] for r in rows]
            all_ids.extend(next_frontier)
            frontier = next_frontier
        return all_ids

    def full_path(self, category: Category) -> str:
        parts = [category.name]
        node = category
        while node.parent_id is not None:
            parent_row = self._conn.execute(
                "SELECT * FROM categories WHERE id = ?", (node.parent_id,)
            ).fetchone()
            if parent_row is None:  # pragma: no cover - shouldn't happen with FKs on
                break
            node = _row_to_category(parent_row)
            parts.append(node.name)
        return ".".join(reversed(parts))

    def create(self, category: Category) -> Category:
        try:
            cur = self._conn.execute(
                """
                INSERT INTO categories (name, kind, parent_id) VALUES (?, ?, ?)
                """,
                (category.name, category.kind.value, category.parent_id),
            )
        except sqlite3.IntegrityError as exc:
            raise DuplicateError(
                f"category {category.name!r} already exists at this level"
            ) from exc
        return self.get(int(cur.lastrowid))

    def update(self, category: Category) -> Category:
        if category.id is None:
            raise ValueError("cannot update category without id")
        try:
            cur = self._conn.execute(
                """
                UPDATE categories
                   SET name = ?, kind = ?, parent_id = ?,
                       updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                 WHERE id = ?
                """,
                (category.name, category.kind.value, category.parent_id, category.id),
            )
        except sqlite3.IntegrityError as exc:
            raise DuplicateError(
                f"category {category.name!r} already exists at this level"
            ) from exc
        if cur.rowcount == 0:
            raise NotFoundError(f"category id={category.id} not found")
        return self.get(category.id)

    def delete(self, category_id: int) -> None:
        cur = self._conn.execute("DELETE FROM categories WHERE id = ?", (category_id,))
        if cur.rowcount == 0:
            raise NotFoundError(f"category id={category_id} not found")
