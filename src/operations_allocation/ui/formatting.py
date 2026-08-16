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

_TERMINAL_SUCCESS = frozenset({RunState.COMPLETED})
_TERMINAL_FAILURE = frozenset({RunState.CANCELLED, RunState.FAILED, RunState.ABANDONED})
_NOT_STARTED = frozenset({RunState.DRAFT})


def state_color(state: RunState) -> str:
    """Semantic color (hex) for a RunState badge -- gray for not-yet-
    started, amber for actively in-progress, green for the one true
    success terminal state, red for every failure/exit terminal state.
    Colocated with state_label rather than in ui.theme because this is a
    *meaning* decision (which states count as success/failure), not a
    palette/styling one -- ui.theme owns the actual hex values it maps
    to plus everything else about how the app looks.
    """
    if state in _NOT_STARTED:
        return "#6B7280"  # gray-500: nothing has happened yet
    if state in _TERMINAL_SUCCESS:
        return "#16A34A"  # green-600
    if state in _TERMINAL_FAILURE:
        return "#DC2626"  # red-600
    return "#D97706"  # amber-600: anywhere mid-pipeline, actively in progress


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
