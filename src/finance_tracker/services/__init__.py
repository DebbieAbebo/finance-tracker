"""Application services.

Services orchestrate repositories and apply business rules. They take
a sqlite connection and instantiate the repositories they need, so a
caller only has to wire the connection once.
"""

from .analytics import AccountBalance, AnalyticsService, CategoryTotal
from .recurring import MaterializeResult, RecurringMaterializer
from .reporting import CategoryBreakdown, MonthlySummary, ReportingService

__all__ = [
    "AccountBalance",
    "AnalyticsService",
    "CategoryBreakdown",
    "CategoryTotal",
    "MaterializeResult",
    "MonthlySummary",
    "RecurringMaterializer",
    "ReportingService",
]
