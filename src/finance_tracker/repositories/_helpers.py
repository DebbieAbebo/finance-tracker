"""Internal helpers shared by the repositories.

Keeping these small, private utilities here avoids circular imports and
keeps the per-repository modules focused on SQL and domain mapping.
"""

from __future__ import annotations

from datetime import datetime


def parse_timestamp(value: str) -> datetime:
    """Parse one of our ``%Y-%m-%dT%H:%M:%fZ`` timestamps from sqlite.

    SQLite stores them as TEXT; Python's ``fromisoformat`` accepts the
    format minus the trailing ``Z`` (UTC marker).
    """
    if value.endswith("Z"):
        value = value[:-1]
    return datetime.fromisoformat(value)
