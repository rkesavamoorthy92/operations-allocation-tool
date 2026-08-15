"""Immutable domain records used by services and repositories."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
import re
from typing import Any, Mapping

from operations_allocation.domain.exceptions import InvalidAssociateConfigurationError, InvalidResolutionError
from operations_allocation.utils.canonical import deep_freeze


class RunState(StrEnum):
    DRAFT = "DRAFT"
    SNAPSHOT_FROZEN = "SNAPSHOT_FROZEN"
    VALIDATED = "VALIDATED"
    ELIGIBLE_POPULATION_FROZEN = "ELIGIBLE_POPULATION_FROZEN"
    SAMPLED = "SAMPLED"
    ALLOCATED = "ALLOCATED"
    DISTRIBUTED = "DISTRIBUTED"
    RETURNED = "RETURNED"
    CONSOLIDATED = "CONSOLIDATED"
    QC_COMPLETED = "QC_COMPLETED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"
    ABANDONED = "ABANDONED"


@dataclass(frozen=True, slots=True)
class Program:
    program_id: str
    name: str
    active_configuration_version: int | None = None
    active: bool = True


@dataclass(frozen=True, slots=True)
class Associate:
    associate_id: str
    name: str
    email: str
    active: bool
    team_or_program: str | None = None
    experience: str | None = None
    default_target: int | None = None
    default_maximum_capacity: int | None = None

    def __post_init__(self) -> None:
        if not self.associate_id.strip():
            raise InvalidAssociateConfigurationError("Associate ID must not be empty.")
        if not self.name.strip():
            raise InvalidAssociateConfigurationError("Associate name must not be empty.")
        if self.email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", self.email):
            raise InvalidAssociateConfigurationError("Associate email must be a valid email address.")
        for label, value in (("default target", self.default_target), ("default maximum capacity", self.default_maximum_capacity)):
            if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 0):
                raise InvalidAssociateConfigurationError(f"Associate {label} must be a non-negative integer.")
        if self.default_target is not None and self.default_maximum_capacity is not None and self.default_target > self.default_maximum_capacity:
            raise InvalidAssociateConfigurationError("Associate default target cannot exceed default maximum capacity.")


@dataclass(frozen=True, slots=True)
class Run:
    run_id: str
    program_id: str
    created_by: str
    created_at: datetime
    state: RunState
    due_date: date | None = None
    snapshot_id: int | None = None


@dataclass(frozen=True, slots=True)
class RunConfigurationSnapshot:
    snapshot_id: int
    run_id: str
    program_configuration_version: int
    canonical_version: str
    canonical_json: str
    sha256: str
    created_at: datetime

    @property
    def configuration(self) -> Mapping[str, Any]:
        import json
        return deep_freeze(json.loads(self.canonical_json))


@dataclass(frozen=True, slots=True)
class ExecutionManifest:
    run_id: str
    configuration_snapshot_hash: str
    source_artifact_hash: str | None = None
    eligible_population_hash: str | None = None
    sampling_algorithm: str | None = None
    sampling_algorithm_version: str | None = None
    rng_algorithm: str | None = None
    rng_algorithm_version: str | None = None
    random_seed: str | None = None
    allocation_strategy: str | None = None
    allocation_strategy_version: str | None = None
    output_artifact_hashes: Mapping[str, str] | None = None
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "output_artifact_hashes", deep_freeze(self.output_artifact_hashes or {}))


_RESOLUTION_ACTIONS = {"EXCLUDE_ALL", "KEEP_ROW"}


@dataclass(frozen=True, slots=True)
class DuplicateResolution:
    """A manual resolution for one duplicate-identifier group (PROJECT_SPEC.md
    section 8, Duplicate Product IDs).

    ``action`` is either ``EXCLUDE_ALL`` (every row sharing the normalized
    identifier is excluded from the eligible population) or ``KEEP_ROW``
    (exactly one row, identified by ``kept_row_index``, is retained and the
    rest are excluded). The system never infers this choice automatically.
    """

    normalized_identifier: str
    original_values: tuple[str, ...]
    row_indexes: tuple[int, ...]
    action: str
    resolved_by: str
    resolved_at: datetime
    reason: str
    kept_row_index: int | None = None

    def __post_init__(self) -> None:
        if not self.normalized_identifier.strip():
            raise InvalidResolutionError("Duplicate resolution requires a normalized identifier.")
        if self.action not in _RESOLUTION_ACTIONS:
            raise InvalidResolutionError(f"Duplicate resolution action must be one of {sorted(_RESOLUTION_ACTIONS)}.")
        if self.action == "KEEP_ROW" and self.kept_row_index not in self.row_indexes:
            raise InvalidResolutionError("KEEP_ROW resolutions must name a row index within the duplicate group.")
        if not self.reason.strip():
            raise InvalidResolutionError("Duplicate resolution requires a reason.")
        if not self.resolved_by.strip():
            raise InvalidResolutionError("Duplicate resolution requires the resolving user.")


@dataclass(frozen=True, slots=True)
class EligiblePopulation:
    """The frozen, immutable set of items eligible for sampling for a Run
    (PROJECT_SPEC.md section 8 / ARCHITECTURE.md section 7.1)."""

    run_id: str
    member_identifiers: tuple[str, ...]
    fingerprint: str
    frozen_at: datetime
    total_rows: int
    excluded_row_count: int
    resolutions: tuple[DuplicateResolution, ...] = ()


@dataclass(frozen=True, slots=True)
class SamplingResult:
    """The immutable outcome of random sampling for a Run (PROJECT_SPEC.md
    section 9-10 / ARCHITECTURE.md section 7.1, SamplingResult)."""

    run_id: str
    sampling_method: str
    requested_value: str
    eligible_population_count: int
    calculated_sample_count: str | None
    actual_sample_count: int
    random_seed: str
    rng_algorithm: str
    rng_algorithm_version: str
    sampling_algorithm: str
    sampling_algorithm_version: str
    selected_identifiers: tuple[str, ...]
    sampled_at: datetime
