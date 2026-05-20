"""Input validation rules.

These run at the boundary (CLI, importer) before data hits a
repository. They raise :class:`finance_tracker.exceptions.ValidationError`
with a field name so callers can surface friendly messages.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Optional

from dateutil import parser as date_parser  # type: ignore[import-untyped]

from .exceptions import ValidationError
from .money import to_cents

_NAME_RE = re.compile(r"^[\w][\w \-./&'()]{0,99}$")
_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")


def validate_account_name(value: str) -> str:
    if value is None:
        raise ValidationError("name", "is required")
    cleaned = value.strip()
    if not cleaned:
        raise ValidationError("name", "is required")
    if len(cleaned) > 100:
        raise ValidationError("name", "must be 100 characters or fewer")
    if not _NAME_RE.match(cleaned):
        raise ValidationError("name", "contains unsupported characters")
    return cleaned


def validate_category_name(value: str) -> str:
    if value is None:
        raise ValidationError("name", "is required")
    cleaned = value.strip()
    if not cleaned:
        raise ValidationError("name", "is required")
    if len(cleaned) > 80:
        raise ValidationError("name", "must be 80 characters or fewer")
    if "." in cleaned:
        raise ValidationError("name", "must not contain '.' (used as path separator)")
    return cleaned


def validate_currency(value: str) -> str:
    if value is None:
        raise ValidationError("currency", "is required")
    cleaned = value.strip().upper()
    if not _CURRENCY_RE.match(cleaned):
        raise ValidationError("currency", "must be a 3-letter ISO code")
    return cleaned


def validate_amount(value, *, allow_zero: bool = False) -> int:
    """Convert to integer cents, raising ``ValidationError`` on bad input."""
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ValidationError("amount", "is required")
    try:
        cents = to_cents(value)
    except (ValueError, InvalidOperation) as exc:
        raise ValidationError("amount", "must be a number") from exc
    if cents == 0 and not allow_zero:
        raise ValidationError("amount", "must be non-zero")
    return cents


def validate_date(value, *, field: str = "date") -> date:
    if value is None:
        raise ValidationError(field, "is required")
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            raise ValidationError(field, "is required")
        try:
            parsed = date_parser.parse(cleaned, dayfirst=False, yearfirst=True)
        except (ValueError, OverflowError) as exc:
            raise ValidationError(field, "could not be parsed as a date") from exc
        return parsed.date()
    raise ValidationError(field, f"unsupported type: {type(value).__name__}")


def validate_description(value: Optional[str]) -> str:
    if value is None:
        return ""
    cleaned = value.strip()
    if len(cleaned) > 255:
        raise ValidationError("description", "must be 255 characters or fewer")
    return cleaned


def validate_notes(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    if len(cleaned) > 1000:
        raise ValidationError("notes", "must be 1000 characters or fewer")
    return cleaned


def validate_date_range(
    date_from: Optional[date], date_to: Optional[date]
) -> tuple[Optional[date], Optional[date]]:
    if date_from is not None and date_to is not None and date_from > date_to:
        raise ValidationError("date_range", "from-date must not be after to-date")
    return date_from, date_to
