"""Account model.

An account is a place where money lives: a checking account, a credit
card, a brokerage, cash on hand, etc. Every transaction belongs to
exactly one account.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


class AccountType(str, enum.Enum):
    CHECKING = "checking"
    SAVINGS = "savings"
    CREDIT_CARD = "credit_card"
    CASH = "cash"
    INVESTMENT = "investment"
    LOAN = "loan"
    OTHER = "other"


@dataclass
class Account:
    name: str
    type: AccountType
    currency: str = "USD"
    opening_balance_cents: int = 0
    archived: bool = False
    id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
