"""Data access layer.

Each module exposes one repository class scoped to a sqlite connection.
Repositories take care of mapping rows back to dataclass models and
raising our own exception types instead of leaking sqlite3 errors.
"""

from .accounts import AccountRepository
from .categories import CategoryRepository
from .recurring import RecurringTransactionRepository
from .transactions import TransactionFilter, TransactionRepository

__all__ = [
    "AccountRepository",
    "CategoryRepository",
    "RecurringTransactionRepository",
    "TransactionFilter",
    "TransactionRepository",
]
