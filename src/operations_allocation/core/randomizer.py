"""Randomizer — deterministic, reproducible sampling from a frozen Eligible
Population (PROJECT_SPEC.md section 9-10 / ARCHITECTURE.md section 8.1).

Pure logic only: no SQLite, no PySide6. Callers supply the eligible
population's canonical membership and a sampling configuration; this module
never mutates or re-derives that membership.

Percentage sampling uses explicit HALF-UP rounding (never Python's banker's
rounding `round()`), matching the worked examples in the spec:

    56,432 x 3%   = 1,692.96 -> 1,693
    1,692.5       -> 1,693
    1,692.4       -> 1,692
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Sequence

from operations_allocation.domain.exceptions import SamplingConfigurationError

RNG_ALGORITHM = "python-random-mt19937"
RNG_ALGORITHM_VERSION = "1"
SAMPLING_ALGORITHM = "sample-without-replacement"
SAMPLING_ALGORITHM_VERSION = "1"


@dataclass(frozen=True, slots=True)
class SampleSize:
    calculated_before_rounding: Decimal | None
    actual: int


@dataclass(frozen=True, slots=True)
class SamplingOutcome:
    selected_identifiers: tuple[str, ...]
    sample_size: SampleSize


def half_up_round(value: Decimal) -> int:
    """Round to the nearest integer, ties rounding away from zero."""
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def calculate_sample_size(*, method: str, value: object, eligible_count: int) -> SampleSize:
    if eligible_count < 0:
        raise SamplingConfigurationError("Eligible population count cannot be negative.")

    if method == "percentage":
        try:
            percentage = Decimal(str(value))
        except Exception as error:
            raise SamplingConfigurationError(f"Sampling percentage '{value}' is not a valid number.") from error
        if percentage <= 0 or percentage > 100:
            raise SamplingConfigurationError("Sampling percentage must be greater than 0 and at most 100.")
        calculated = (Decimal(eligible_count) * percentage) / Decimal(100)
        actual = half_up_round(calculated)
        return SampleSize(calculated_before_rounding=calculated, actual=min(actual, eligible_count))

    if method == "count":
        if isinstance(value, bool) or not isinstance(value, (int, str)):
            raise SamplingConfigurationError(f"Sampling count '{value}' is not a valid whole number.")
        try:
            count = int(value)
        except (TypeError, ValueError) as error:
            raise SamplingConfigurationError(f"Sampling count '{value}' is not a valid whole number.") from error
        if count <= 0:
            raise SamplingConfigurationError("Sampling count must be a positive integer.")
        if count > eligible_count:
            raise SamplingConfigurationError(
                f"Requested sample count {count} exceeds the eligible population of {eligible_count}."
            )
        return SampleSize(calculated_before_rounding=None, actual=count)

    raise SamplingConfigurationError(f"Unsupported sampling method '{method}'.")


def draw_sample(
    eligible_identifiers: Sequence[str],
    *,
    method: str,
    value: object,
    seed: str,
) -> SamplingOutcome:
    """Select a unique, reproducible sample from the eligible population.

    Given the same ``eligible_identifiers`` (in the same canonical order),
    ``method``, ``value``, and ``seed``, this always returns the same
    selection -- required for auditability and reproducibility.
    """
    if not seed:
        raise SamplingConfigurationError("A random seed is required to draw a reproducible sample.")
    canonical_population = sorted(eligible_identifiers)
    size = calculate_sample_size(method=method, value=value, eligible_count=len(canonical_population))
    rng = random.Random(seed)
    selected = rng.sample(canonical_population, size.actual)
    return SamplingOutcome(selected_identifiers=tuple(sorted(selected)), sample_size=size)
