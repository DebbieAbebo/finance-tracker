"""Money handling.

We store amounts in SQLite as ``INTEGER`` minor units (cents for USD,
fils for AED, etc.) to avoid the floating-point issues that plague
naive money handling. In Python we surface them as ``Decimal`` so
arithmetic is exact and predictable.

The number of minor units per major unit defaults to 100 (USD/EUR/GBP
style). Currencies with more or fewer fractional digits should pass
``minor_units`` explicitly when calling these helpers.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Union

Numeric = Union[int, str, Decimal, float]


def to_cents(amount: Numeric, *, minor_units: int = 100) -> int:
    """Convert a money amount to integer minor units.

    Floats are accepted for convenience but go through ``str`` first
    so that ``0.1 + 0.2`` style errors don't slip into the database.
    """
    if isinstance(amount, float):
        amount = str(amount)
    try:
        d = Decimal(amount)
    except (InvalidOperation, TypeError) as exc:
        raise ValueError(f"not a valid money amount: {amount!r}") from exc

    quantizer = Decimal(1) / Decimal(minor_units)
    rounded = d.quantize(quantizer, rounding=ROUND_HALF_UP)
    return int(rounded * minor_units)


def from_cents(cents: int, *, minor_units: int = 100) -> Decimal:
    """Convert integer minor units back to a ``Decimal`` major amount."""
    if not isinstance(cents, int):
        raise TypeError(f"cents must be int, got {type(cents).__name__}")
    return (Decimal(cents) / Decimal(minor_units)).quantize(
        Decimal(1) / Decimal(minor_units)
    )


def format_amount(cents: int, currency: str = "USD", *, minor_units: int = 100) -> str:
    """Render an amount for display, e.g. ``-$12.34``."""
    sign = "-" if cents < 0 else ""
    abs_value = from_cents(abs(cents), minor_units=minor_units)
    # Currency placement is naive; good enough for display.
    return f"{sign}{currency} {abs_value:,.2f}"
