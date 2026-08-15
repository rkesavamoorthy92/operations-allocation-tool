"""Pure display-formatting helpers with zero PySide6 dependency, so they
are unit-testable without a display (ARCHITECTURE.md section 9: UI
components must not contain business logic -- and that cuts both ways,
this formatting logic doesn't belong scattered across widget code).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from operations_allocation.domain.models import RunState

NOT_APPLICABLE = "N/A"


def state_label(state: RunState) -> str:
    return state.value.replace("_", " ").title()


def format_percentage(value: Decimal | None, *, is_not_applicable: bool = False) -> str:
    if is_not_applicable or value is None:
        return NOT_APPLICABLE
    return f"{value:.2f}%"


def format_percentage_point_change(current: Decimal | None, previous: Decimal | None) -> str:
    """PROJECT_SPEC.md section 26: changes must be percentage-POINT
    changes, explicitly labeled, never confused with a percent change."""
    if current is None or previous is None:
        return NOT_APPLICABLE
    delta = current - previous
    sign = "+" if delta >= 0 else ""
    return f"{sign}{delta:.1f} percentage points"


def format_timestamp(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M")


def format_count(count: int, *, noun: str) -> str:
    suffix = "" if count == 1 else "s"
    return f"{count} {noun}{suffix}"
