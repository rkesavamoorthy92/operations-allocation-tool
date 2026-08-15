"""Immutable domain records used by services and repositories."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
import re
from typing import Any, Mapping

from operations_allocation.domain.exceptions import InvalidAssociateConfigurationError
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
