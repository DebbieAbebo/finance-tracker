"""Import transactions from CSV files.

The CSV format is intentionally close to what banks export:

    date,amount,description,category,notes

- ``date`` accepts anything ``dateutil`` will parse (ISO recommended).
- ``amount`` may be signed; sign is ignored — the category's kind
  (income / expense) is what determines the direction in reports.
- ``category`` is a dotted path; missing categories are *not* created
  automatically — that's an explicit choice so a typo doesn't pollute
  the category tree.
- ``notes`` is optional.
"""

from __future__ import annotations

import csv
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, Iterable, Optional, Union

from ..exceptions import NotFoundError, ValidationError
from ..models import Transaction
from ..repositories.accounts import AccountRepository
from ..repositories.categories import CategoryRepository
from ..repositories.transactions import TransactionRepository
from ..validation import (
    validate_amount,
    validate_date,
    validate_description,
    validate_notes,
)

REQUIRED_HEADERS = {"date", "amount", "description"}
OPTIONAL_HEADERS = {"category", "notes"}


@dataclass
class ImportResult:
    imported: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.imported + self.skipped


class CsvImporter:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._accounts = AccountRepository(conn)
        self._categories = CategoryRepository(conn)
        self._txns = TransactionRepository(conn)

    def import_file(
        self,
        source: Union[str, Path, IO[str]],
        *,
        account_name: str,
    ) -> ImportResult:
        account = self._accounts.find_by_name(account_name)
        if account is None:
            raise NotFoundError(f"account {account_name!r} not found")

        if isinstance(source, (str, Path)):
            with open(source, newline="", encoding="utf-8") as fh:
                return self._import_from(fh, account_id=account.id)
        return self._import_from(source, account_id=account.id)

    def _import_from(self, fh: IO[str], *, account_id: int) -> ImportResult:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            raise ValidationError("csv", "no header row found")

        headers = {h.strip().lower() for h in reader.fieldnames}
        missing = REQUIRED_HEADERS - headers
        if missing:
            raise ValidationError("csv", f"missing required columns: {sorted(missing)}")

        rows: list[Transaction] = []
        result = ImportResult()
        for line_no, raw in enumerate(reader, start=2):  # +1 for header, +1 for 1-based
            try:
                # csv.DictReader stuffs surplus fields under a list keyed by
                # ``None``. That's a sign the row had unquoted commas; flag
                # it as a row error instead of crashing.
                if None in raw:
                    raise ValidationError("csv", "row has more columns than the header")
                row = {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items()}
                if not any(row.values()):
                    continue  # skip blank lines
                txn = self._row_to_transaction(row, account_id=account_id)
            except ValidationError as exc:
                result.skipped += 1
                result.errors.append(f"line {line_no}: {exc}")
                continue
            rows.append(txn)

        if rows:
            self._txns.bulk_create(rows)
            result.imported = len(rows)
        return result

    def _row_to_transaction(self, row: dict, *, account_id: int) -> Transaction:
        occurred_on = validate_date(row.get("date"))
        # Importer always stores positive cents; sign is implied by category kind.
        amount_cents = abs(validate_amount(row.get("amount")))
        description = validate_description(row.get("description"))
        notes = validate_notes(row.get("notes")) if row.get("notes") else None

        category_id: Optional[int] = None
        cat_path = row.get("category")
        if cat_path:
            cat = self._categories.find_by_path(cat_path)
            if cat is None:
                raise ValidationError("category", f"unknown category {cat_path!r}")
            category_id = cat.id

        return Transaction(
            occurred_on=occurred_on,
            amount_cents=amount_cents,
            description=description,
            notes=notes,
            account_id=account_id,
            category_id=category_id,
        )


def import_iter(
    conn: sqlite3.Connection,
    rows: Iterable[dict],
    *,
    account_name: str,
) -> ImportResult:
    """Convenience for tests / programmatic callers: import already-parsed rows."""
    importer = CsvImporter(conn)
    account = AccountRepository(conn).find_by_name(account_name)
    if account is None:
        raise NotFoundError(f"account {account_name!r} not found")

    out = ImportResult()
    txns: list[Transaction] = []
    for line_no, row in enumerate(rows, start=1):
        try:
            txns.append(importer._row_to_transaction(row, account_id=account.id))  # noqa: SLF001
        except ValidationError as exc:
            out.skipped += 1
            out.errors.append(f"row {line_no}: {exc}")
    if txns:
        TransactionRepository(conn).bulk_create(txns)
        out.imported = len(txns)
    return out
