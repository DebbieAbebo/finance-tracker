"""Materialize ``RecurringTransaction`` templates into concrete rows.

The service is idempotent: running ``run`` twice on the same date won't
double up rows because we track ``last_materialized_on`` on each
template.
"""

from __future__ import annotations

import calendar
import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable

from ..models import Cadence, RecurringTransaction, Transaction
from ..repositories.recurring import RecurringTransactionRepository
from ..repositories.transactions import TransactionRepository


@dataclass(frozen=True)
class MaterializeResult:
    template_id: int
    template_name: str
    created: int


class RecurringMaterializer:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._templates = RecurringTransactionRepository(conn)
        self._txns = TransactionRepository(conn)

    def run(self, *, through: date) -> list[MaterializeResult]:
        """Materialize every active template up to and including ``through``.

        Returns a per-template report so a caller (CLI, scheduler) can
        log what happened.
        """
        results: list[MaterializeResult] = []
        for template in self._templates.list(only_active=True):
            occurrences = list(_occurrences(template, through))
            if not occurrences:
                continue
            new_rows = [
                Transaction(
                    occurred_on=d,
                    amount_cents=template.amount_cents,
                    description=template.description or template.name,
                    notes=template.notes,
                    account_id=template.account_id,
                    category_id=template.category_id,
                )
                for d in occurrences
            ]
            self._txns.bulk_create(new_rows)
            template.last_materialized_on = occurrences[-1]
            self._templates.update(template)
            results.append(
                MaterializeResult(
                    template_id=template.id,
                    template_name=template.name,
                    created=len(new_rows),
                )
            )
        return results


def _occurrences(
    template: RecurringTransaction, through: date
) -> Iterable[date]:
    """Yield each due date for ``template`` up to and including ``through``."""
    if template.interval < 1:
        raise ValueError("interval must be >= 1")
    starts_on = template.starts_on
    cursor = (
        _next_after(template.last_materialized_on, template.cadence, template.interval)
        if template.last_materialized_on is not None
        else starts_on
    )
    while cursor <= through:
        if template.ends_on is not None and cursor > template.ends_on:
            return
        if cursor >= starts_on:
            yield cursor
        cursor = _next_after(cursor, template.cadence, template.interval)


def _next_after(d: date, cadence: Cadence, interval: int) -> date:
    if cadence is Cadence.DAILY:
        return d + timedelta(days=interval)
    if cadence is Cadence.WEEKLY:
        return d + timedelta(weeks=interval)
    if cadence is Cadence.MONTHLY:
        return _add_months(d, interval)
    if cadence is Cadence.YEARLY:
        return _add_months(d, interval * 12)
    raise ValueError(f"unsupported cadence: {cadence!r}")


def _add_months(d: date, months: int) -> date:
    """Add ``months`` to ``d``, clamping to the last day if needed.

    Adding 1 month to Jan 31 lands on Feb 28/29, not March 3.
    """
    total = d.month - 1 + months
    year = d.year + total // 12
    month = total % 12 + 1
    last = calendar.monthrange(year, month)[1]
    return date(year, month, min(d.day, last))
