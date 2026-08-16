"""Coordinates the Validation Engine, duplicate-identifier resolution, and
Eligible Population freezing for a Run.

Implements the processing sequence from PROJECT_SPEC.md section 8:

    Input -> Validation -> User-approved exclusions/resolution
    -> Freeze eligible population -> Random sampling

Rows are supplied directly by the caller for this phase -- in practice
that's ui.run_actions.import_source_and_validate, which sources them
from services.source_import.SourceImportService's canonical artifact for
the Run rather than re-parsing the original file. Keeping ``rows`` as an
explicit parameter here (rather than this service reaching into the
artifact store itself) keeps this service testable with plain in-memory
data and keeps the artifact-reading concern in one place.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from operations_allocation.core.validation import Severity, ValidationSummary, validate_dataset
from operations_allocation.domain.exceptions import InvalidResolutionError, UnresolvedDuplicatesError, ValidationBlockedError
from operations_allocation.domain.models import DuplicateResolution, EligiblePopulation, RunState
from operations_allocation.domain.state_machine import ensure_transition
from operations_allocation.utils.canonical import sha256_for
from operations_allocation.utils.identifiers import NormalizationPolicy

_STRUCTURAL_CODES = {"EMPTY_DATASET", "MISSING_REQUIRED_COLUMN"}


class EligiblePopulationService:
    def __init__(self, *, runs: Any, snapshots: Any, populations: Any, audit: Any) -> None:
        self.runs, self.snapshots, self.populations, self.audit = runs, snapshots, populations, audit

    def validate(self, *, run_id: str, rows: Sequence[Mapping[str, Any]]) -> ValidationSummary:
        """Run the Validation Engine and, absent structural failures, advance
        the Run to VALIDATED. Duplicate/missing-identifier issues do not
        block this transition -- they must be resolved before freezing."""
        run = self.runs.get(run_id)
        ensure_transition(run.state, RunState.VALIDATED)
        summary = self._run_validation(run_id, rows)
        structural = [issue for issue in summary.critical_issues if issue.code in _STRUCTURAL_CODES]
        if structural:
            raise ValidationBlockedError("; ".join(issue.message for issue in structural))
        with self.runs.database.transaction() as connection:
            self.runs.update_state(run_id, RunState.VALIDATED, connection=connection)
            self.audit.record(
                run_id=run_id,
                program_id=run.program_id,
                action="RUN_VALIDATED",
                previous_state=run.state,
                new_state=RunState.VALIDATED,
                metadata={
                    "total_rows": summary.total_rows,
                    "valid_row_count": summary.valid_row_count,
                    "critical_count": len(summary.critical_issues),
                    "warning_count": len([i for i in summary.issues if i.severity is Severity.WARNING]),
                    "duplicate_group_count": len(summary.duplicate_groups),
                },
                connection=connection,
            )
        return summary

    def freeze(
        self,
        *,
        run_id: str,
        rows: Sequence[Mapping[str, Any]],
        resolutions: Sequence[DuplicateResolution] = (),
        resolved_by: str | None = None,
    ) -> EligiblePopulation:
        """Freeze the immutable Eligible Population, requiring an explicit
        resolution for every duplicate-identifier group detected during
        validation (PROJECT_SPEC.md section 8, Duplicate Product IDs)."""
        run = self.runs.get(run_id)
        ensure_transition(run.state, RunState.ELIGIBLE_POPULATION_FROZEN)
        summary = self._run_validation(run_id, rows)
        structural = [issue for issue in summary.critical_issues if issue.code in _STRUCTURAL_CODES]
        if structural:
            raise ValidationBlockedError("; ".join(issue.message for issue in structural))

        resolutions_by_identifier = {resolution.normalized_identifier: resolution for resolution in resolutions}
        unresolved = [group.normalized_identifier for group in summary.duplicate_groups if group.normalized_identifier not in resolutions_by_identifier]
        if unresolved:
            raise UnresolvedDuplicatesError(f"Duplicate identifier(s) require manual resolution before freezing: {', '.join(sorted(unresolved))}.")

        for group in summary.duplicate_groups:
            resolution = resolutions_by_identifier[group.normalized_identifier]
            if set(resolution.row_indexes) != set(group.row_indexes):
                raise InvalidResolutionError(f"Resolution for '{group.normalized_identifier}' does not match the detected duplicate rows.")

        members = set(summary.eligible_identifiers)
        for group in summary.duplicate_groups:
            resolution = resolutions_by_identifier[group.normalized_identifier]
            if resolution.action == "KEEP_ROW":
                members.add(group.normalized_identifier)
        member_identifiers = tuple(sorted(members))

        frozen_at = datetime.now(timezone.utc)
        population = EligiblePopulation(
            run_id=run_id,
            member_identifiers=member_identifiers,
            fingerprint=sha256_for({"run_id": run_id, "members": list(member_identifiers)}),
            frozen_at=frozen_at,
            total_rows=summary.total_rows,
            excluded_row_count=summary.total_rows - len(member_identifiers),
            resolutions=tuple(resolutions),
        )

        with self.runs.database.transaction() as connection:
            self.populations.add(population, connection=connection)
            self.runs.update_state(run_id, RunState.ELIGIBLE_POPULATION_FROZEN, connection=connection)
            self.audit.record(
                run_id=run_id,
                program_id=run.program_id,
                action="ELIGIBLE_POPULATION_FROZEN",
                previous_state=run.state,
                new_state=RunState.ELIGIBLE_POPULATION_FROZEN,
                metadata={
                    "member_count": len(member_identifiers),
                    "excluded_row_count": population.excluded_row_count,
                    "fingerprint": population.fingerprint,
                    "resolution_count": len(resolutions),
                    "resolved_by": resolved_by,
                },
                connection=connection,
            )
        return population

    def _run_validation(self, run_id: str, rows: Sequence[Mapping[str, Any]]) -> ValidationSummary:
        snapshot = self.snapshots.get(run_id)
        configuration = snapshot.configuration["program_configuration"]
        policy = NormalizationPolicy.from_configuration(configuration["primary_identifier"])
        required_fields = [field["name"] for field in configuration["fields"] if field.get("required")]
        return validate_dataset(
            rows,
            identifier_field=configuration["primary_identifier"]["field"],
            required_fields=required_fields,
            normalization_policy=policy,
        )
