"""Recurring transaction model.

A recurring transaction is a template that materializes into one or
more concrete ``Transaction`` rows on a schedule. Examples: rent on
the 1st of every month, paycheck every two weeks, annual subscription.

Cadence is intentionally narrow — we support DAILY, WEEKLY, MONTHLY,
YEARLY with an integer interval. That covers ~99% of real-life
household scheduling without dragging in a cron-style parser.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional


class Cadence(str, enum.Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    YEARLY = "yearly"


@dataclass
class RecurringTransaction:
    name: str
    amount_cents: int
    account_id: int
    cadence: Cadence
    interval: int = 1  # every N (days/weeks/months/years)
    starts_on: date = None  # type: ignore[assignment]
    ends_on: Optional[date] = None
    category_id: Optional[int] = None
    description: str = ""
    notes: Optional[str] = None
    last_materialized_on: Optional[date] = None
    active: bool = True
    id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
