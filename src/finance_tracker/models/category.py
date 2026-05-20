"""Category model.

Categories are hierarchical: a top-level category like ``Food`` can have
children like ``Groceries`` and ``Restaurants``. Transactions attach to
any node (typically a leaf), and reports can roll up to the parent.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


class CategoryKind(str, enum.Enum):
    INCOME = "income"
    EXPENSE = "expense"
    TRANSFER = "transfer"


@dataclass
class Category:
    name: str
    kind: CategoryKind
    parent_id: Optional[int] = None
    id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
