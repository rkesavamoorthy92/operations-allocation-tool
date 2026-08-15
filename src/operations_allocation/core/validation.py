"""Validation Engine — pure, program-agnostic dataset validation.

Implements PROJECT_SPEC.md section 8 and ARCHITECTURE.md section 5:
severity classification, required-column checks, missing/duplicate primary
identifier detection. This module has no dependency on SQLite, PySide6, or
file formats -- it operates on already-parsed rows keyed by canonical field
name (post column-mapping), as produced by the File Processing pipeline.

Duplicate identifiers are never auto-resolved here: every duplicate group is
reported and left out of ``eligible_identifiers`` until a caller supplies an
explicit resolution (see ``services.eligible_population``).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping, Sequence

from operations_allocation.utils.identifiers import IdentifierNormalizationError, NormalizationPolicy, normalize_identifier


class Severity(StrEnum):
    CRITICAL = "CRITICAL"
    WARNING = "WARNING"
    INFORMATION = "INFORMATION"


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    severity: Severity
    code: str
    message: str
    row_indexes: tuple[int, ...] = ()


@dataclass(frozen=True, slots=True)
class DuplicateGroup:
    normalized_identifier: str
    original_values: tuple[str, ...]
    row_indexes: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class ValidationSummary:
    """``eligible_identifiers`` holds normalized identifiers with no
    missing-identifier or duplicate issue, in first-encountered row order.
    Every row in a duplicate group is excluded pending manual resolution."""

    total_rows: int
    issues: tuple[ValidationIssue, ...]
    duplicate_groups: tuple[DuplicateGroup, ...]
    eligible_identifiers: tuple[str, ...]

    @property
    def critical_issues(self) -> tuple[ValidationIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity is Severity.CRITICAL)

    @property
    def has_blocking_issues(self) -> bool:
        return len(self.critical_issues) > 0

    @property
    def valid_row_count(self) -> int:
        excluded_rows: set[int] = set()
        for issue in self.issues:
            if issue.code == "MISSING_IDENTIFIER":
                excluded_rows.update(issue.row_indexes)
        for group in self.duplicate_groups:
            excluded_rows.update(group.row_indexes)
        return self.total_rows - len(excluded_rows)


def validate_dataset(
    rows: Sequence[Mapping[str, Any]],
    *,
    identifier_field: str,
    required_fields: Sequence[str],
    normalization_policy: NormalizationPolicy,
) -> ValidationSummary:
    """Validate a dataset already mapped to canonical field names.

    ``rows`` must be non-empty and every entry in ``required_fields`` (plus
    ``identifier_field``) must appear as a key on at least one row, or a
    structural Critical issue is raised for the whole dataset.
    """
    issues: list[ValidationIssue] = []

    if not rows:
        return ValidationSummary(
            total_rows=0,
            issues=(ValidationIssue(Severity.CRITICAL, "EMPTY_DATASET", "The uploaded dataset contains no rows."),),
            duplicate_groups=(),
            eligible_identifiers=(),
        )

    required_columns = {identifier_field, *required_fields}
    present_columns: set[str] = set()
    for row in rows:
        present_columns.update(row.keys())
    missing_columns = sorted(required_columns - present_columns)
    if missing_columns:
        issues.append(
            ValidationIssue(
                Severity.CRITICAL,
                "MISSING_REQUIRED_COLUMN",
                f"Required column(s) could not be found in the uploaded file: {', '.join(missing_columns)}.",
            )
        )
        return ValidationSummary(total_rows=len(rows), issues=tuple(issues), duplicate_groups=(), eligible_identifiers=())

    identifier_by_row: dict[int, str] = {}
    missing_identifier_rows: list[int] = []
    for index, row in enumerate(rows):
        raw_value = row.get(identifier_field)
        if not isinstance(raw_value, str) or not raw_value.strip():
            missing_identifier_rows.append(index)
            continue
        try:
            identifier_by_row[index] = normalize_identifier(raw_value, normalization_policy)
        except IdentifierNormalizationError:
            missing_identifier_rows.append(index)

    if missing_identifier_rows:
        issues.append(
            ValidationIssue(
                Severity.CRITICAL,
                "MISSING_IDENTIFIER",
                f"{len(missing_identifier_rows)} row(s) are missing a value for '{identifier_field}'.",
                tuple(missing_identifier_rows),
            )
        )

    rows_by_normalized: dict[str, list[int]] = {}
    for index, normalized in identifier_by_row.items():
        rows_by_normalized.setdefault(normalized, []).append(index)

    duplicate_groups: list[DuplicateGroup] = []
    for normalized, row_indexes in rows_by_normalized.items():
        if len(row_indexes) <= 1:
            continue
        original_values = tuple(dict.fromkeys(rows[index][identifier_field] for index in row_indexes))
        duplicate_groups.append(DuplicateGroup(normalized, original_values, tuple(row_indexes)))

    if duplicate_groups:
        total_duplicate_rows = sum(len(group.row_indexes) for group in duplicate_groups)
        issues.append(
            ValidationIssue(
                Severity.CRITICAL,
                "DUPLICATE_IDENTIFIER",
                f"{len(duplicate_groups)} duplicate '{identifier_field}' value(s) affecting {total_duplicate_rows} row(s) require manual resolution.",
                tuple(index for group in duplicate_groups for index in group.row_indexes),
            )
        )

    duplicated_normalized = {group.normalized_identifier for group in duplicate_groups}
    eligible_identifiers = tuple(
        dict.fromkeys(
            normalized
            for index, normalized in identifier_by_row.items()
            if normalized not in duplicated_normalized
        )
    )

    return ValidationSummary(
        total_rows=len(rows),
        issues=tuple(issues),
        duplicate_groups=tuple(duplicate_groups),
        eligible_identifiers=eligible_identifiers,
    )
