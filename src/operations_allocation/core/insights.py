"""Deterministic Insights Engine (PROJECT_SPEC.md section 25).

Every function here is pure: given already-computed data (an
AllocationResult, a Consolidation reconciliation summary, a QC report,
error records), it derives one insight. No AI/narrative generation --
section 25 explicitly scopes that out as "a later enhancement." No I/O,
no repository access -- that composition lives in services.insights.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Mapping, Sequence

_TWO_PLACES = Decimal("0.01")


def _percentage(numerator: int, denominator: int) -> Decimal | None:
    if denominator == 0:
        return None
    return (Decimal(numerator) / Decimal(denominator) * Decimal(100)).quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)


def allocation_utilization(assignments: Sequence[Mapping[str, object]]) -> dict[str, Decimal | None]:
    """Planned count as a percentage of maximum capacity, per associate."""
    return {a["associate_id"]: _percentage(int(a["planned_count"]), int(a["maximum_capacity"])) for a in assignments}


def completion_rate(*, allocated_count: int, unique_returned_count: int) -> Decimal | None:
    return _percentage(unique_returned_count, allocated_count)


def top_error_categories(categories: Sequence[str], *, top_n: int = 5) -> tuple[tuple[str, int], ...]:
    """Most frequent error categories, highest first. Ties broken by
    category name for determinism (never insertion order, which would
    make this non-reproducible)."""
    counts = Counter(categories)
    return tuple(sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:top_n])


def error_frequency(*, error_count: int, audited_count: int) -> Decimal | None:
    return _percentage(error_count, audited_count)


def associate_performance(qc_scores_by_associate: Mapping[str, Decimal | None]) -> dict[str, Decimal | None]:
    return dict(qc_scores_by_associate)


def detect_outliers(scores_by_associate: Mapping[str, Decimal | None], *, threshold_points: Decimal = Decimal(10)) -> tuple[str, ...]:
    """Associates whose score falls more than ``threshold_points``
    percentage points below the mean of all applicable scores. Returns
    associate IDs sorted for determinism. Associates with an N/A score
    are excluded from both the mean and the outlier check."""
    applicable = {associate_id: score for associate_id, score in scores_by_associate.items() if score is not None}
    if len(applicable) < 2:
        return ()
    mean = sum(applicable.values()) / Decimal(len(applicable))
    return tuple(sorted(associate_id for associate_id, score in applicable.items() if (mean - score) > threshold_points))


@dataclass(frozen=True, slots=True)
class HistoricalComparison:
    """PROJECT_SPEC.md section 26: comparison against the previous
    COMPLETED Run for the same program. ``is_applicable`` is False (and
    every delta is None) when no previous completed Run exists."""

    is_applicable: bool
    current_qc_score: Decimal | None
    previous_qc_score: Decimal | None
    qc_score_change_points: Decimal | None
    current_error_rate: Decimal | None
    previous_error_rate: Decimal | None
    error_rate_change_points: Decimal | None
    missing_count_current: int | None
    missing_count_previous: int | None
    duplicate_count_current: int | None
    duplicate_count_previous: int | None


def _point_change(current: Decimal | None, previous: Decimal | None) -> Decimal | None:
    if current is None or previous is None:
        return None
    return current - previous


def build_historical_comparison(
    *,
    current_qc_score: Decimal | None,
    current_error_rate: Decimal | None,
    current_missing_count: int | None,
    current_duplicate_count: int | None,
    previous: Mapping[str, object] | None,
) -> HistoricalComparison:
    if previous is None:
        return HistoricalComparison(False, current_qc_score, None, None, current_error_rate, None, None, None, None, None, None)
    previous_qc_score = previous.get("qc_score")
    previous_error_rate = previous.get("error_rate")
    return HistoricalComparison(
        is_applicable=True,
        current_qc_score=current_qc_score,
        previous_qc_score=previous_qc_score,
        qc_score_change_points=_point_change(current_qc_score, previous_qc_score),
        current_error_rate=current_error_rate,
        previous_error_rate=previous_error_rate,
        error_rate_change_points=_point_change(current_error_rate, previous_error_rate),
        missing_count_current=current_missing_count,
        missing_count_previous=previous.get("missing_count"),
        duplicate_count_current=current_duplicate_count,
        duplicate_count_previous=previous.get("duplicate_count"),
    )
