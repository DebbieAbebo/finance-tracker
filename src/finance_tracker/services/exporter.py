"""Export transactions to CSV or JSON.

Output is shaped to match the importer's expectations so a round-trip
through export -> import is lossless for the fields we care about.
"""

from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path
from typing import IO, Optional, Union

from ..money import from_cents
from ..repositories.accounts import AccountRepository
from ..repositories.categories import CategoryRepository
from ..repositories.transactions import TransactionFilter, TransactionRepository

CSV_HEADERS = ["date", "amount", "description", "category", "notes", "account"]


class TransactionExporter:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._txns = TransactionRepository(conn)
        self._accounts = AccountRepository(conn)
        self._categories = CategoryRepository(conn)
        # Cache lookups so an export of N transactions doesn't issue
        # N * 3 SELECTs.
        self._account_cache: dict[int, str] = {}
        self._category_cache: dict[int, str] = {}

    def to_csv(
        self,
        target: Union[str, Path, IO[str]],
        *,
        criteria: Optional[TransactionFilter] = None,
    ) -> int:
        rows = self._collect_rows(criteria)
        if isinstance(target, (str, Path)):
            with open(target, "w", newline="", encoding="utf-8") as fh:
                return self._write_csv(fh, rows)
        return self._write_csv(target, rows)

    def to_json(
        self,
        target: Union[str, Path, IO[str]],
        *,
        criteria: Optional[TransactionFilter] = None,
        indent: int = 2,
    ) -> int:
        rows = self._collect_rows(criteria)
        payload = json.dumps(rows, indent=indent, default=str)
        if isinstance(target, (str, Path)):
            Path(target).write_text(payload, encoding="utf-8")
        else:
            target.write(payload)
        return len(rows)

    def _collect_rows(self, criteria: Optional[TransactionFilter]) -> list[dict]:
        out: list[dict] = []
        for t in self._txns.list(criteria):
            out.append(
                {
                    "date": t.occurred_on.isoformat(),
                    "amount": str(from_cents(t.amount_cents)),
                    "description": t.description,
                    "category": self._category_path(t.category_id),
                    "notes": t.notes or "",
                    "account": self._account_name(t.account_id),
                }
            )
        return out

    def _write_csv(self, fh: IO[str], rows: list[dict]) -> int:
        writer = csv.DictWriter(fh, fieldnames=CSV_HEADERS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
        return len(rows)

    def _account_name(self, account_id: int) -> str:
        cached = self._account_cache.get(account_id)
        if cached is None:
            cached = self._accounts.get(account_id).name
            self._account_cache[account_id] = cached
        return cached

    def _category_path(self, category_id: Optional[int]) -> str:
        if category_id is None:
            return ""
        cached = self._category_cache.get(category_id)
        if cached is None:
            cached = self._categories.full_path(self._categories.get(category_id))
            self._category_cache[category_id] = cached
        return cached
