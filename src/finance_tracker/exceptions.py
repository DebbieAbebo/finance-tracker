"""Domain-specific exceptions.

Using our own exception types lets callers catch specific failure modes
without depending on sqlite3 internals.
"""

from __future__ import annotations


class FinanceTrackerError(Exception):
    """Base for all errors raised by the application."""


class NotFoundError(FinanceTrackerError):
    """Raised when an entity lookup by id (or other key) finds nothing."""


class DuplicateError(FinanceTrackerError):
    """Raised when a uniqueness constraint would be violated."""


class ValidationError(FinanceTrackerError):
    """Raised when input fails domain validation rules."""

    def __init__(self, field: str, message: str) -> None:
        super().__init__(f"{field}: {message}")
        self.field = field
        self.message = message
