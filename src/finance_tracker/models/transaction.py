"""Transaction model.

A transaction is a movement of money in or out of an account on a given
date, optionally tagged with a category. Amounts are stored as positive
integers (cents); the sign is inferred from the category kind when
reporting.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional


@dataclass
class Transaction:
    occurred_on: date
    amount_cents: int
    account_id: int
    description: str = ""
    notes: Optional[str] = None
    category_id: Optional[int] = None
    id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
