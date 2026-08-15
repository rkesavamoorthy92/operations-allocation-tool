"""Consolidation reconciliation engine (PROJECT_SPEC.md sections 19-20).

Pure logic: identity cross-checking across filename/metadata/data-column
levels (section 19, items 1-3, 10) and reconciling returned rows against
the original allocation into matched/duplicate/unexpected/wrong-associate/
incomplete dispositions. Wrong-associate rows and duplicates are never
silently merged into the consolidated output -- they are quarantined for
manual review (section 20, "Wrong-Associate Rows").

V1 scope note: this reconciles *which* identifiers came back and from
whom, and flags duplicates as an open exception requiring manual
resolution. It does not attempt to diff response-field *values* across
duplicate returns of the same item ("conflicting response data" in
section 20) -- that is exactly the kind of conflict the spec says must
never be silently resolved, so duplicates are surfaced for a human to
look at rather than auto-compared.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Mapping, Sequence

from operations_allocation.utils.identifiers import NormalizationPolicy, normalize_identifier


class RowDisposition(StrEnum):
    MATCHED = "matched"
    DUPLICATE = "duplicate"
    UNEXPECTED = "unexpected"
    WRONG_ASSOCIATE = "wrong_associate"
    INCOMPLETE = "incomplete"


@dataclass(frozen=True, slots=True)
class IdentityIssue:
    level: str
    """'filename', 'metadata', or 'data'."""
    field_name: str
    """'run_id', 'associate_id', or 'associate_name'."""
    expected: str
    found: str


@dataclass(frozen=True, slots=True)
class FileIdentity:
    """Identity claimed for one returned file at each of the three levels
    (PROJECT_SPEC.md section 19, items 1-3). Any level's value may be
    ``None`` if that level did not surface the field at all."""

    filename_run_id: str | None
    filename_associate_id: str | None
    metadata_run_id: str | None
    metadata_associate_id: str | None
    metadata_associate_name: str | None
    data_run_ids: frozenset[str]
    data_allocated_to: frozenset[str]


def check_identity(identity: FileIdentity, *, expected_run_id: str, expected_associate_id: str, expected_associate_name: str) -> tuple[IdentityIssue, ...]:
    issues: list[IdentityIssue] = []

    if identity.filename_run_id is not None and identity.filename_run_id != expected_run_id:
        issues.append(IdentityIssue("filename", "run_id", expected_run_id, identity.filename_run_id))
    if identity.filename_associate_id is not None and identity.filename_associate_id != expected_associate_id:
        issues.append(IdentityIssue("filename", "associate_id", expected_associate_id, identity.filename_associate_id))

    if identity.metadata_run_id is not None and identity.metadata_run_id != expected_run_id:
        issues.append(IdentityIssue("metadata", "run_id", expected_run_id, identity.metadata_run_id))
    if identity.metadata_associate_id is not None and identity.metadata_associate_id != expected_associate_id:
        issues.append(IdentityIssue("metadata", "associate_id", expected_associate_id, identity.metadata_associate_id))
    if identity.metadata_associate_name is not None and identity.metadata_associate_name != expected_associate_name:
        issues.append(IdentityIssue("metadata", "associate_name", expected_associate_name, identity.metadata_associate_name))

    unexpected_run_ids = identity.data_run_ids - {expected_run_id}
    if unexpected_run_ids:
        issues.append(IdentityIssue("data", "run_id", expected_run_id, ", ".join(sorted(unexpected_run_ids))))
    unexpected_allocated_to = identity.data_allocated_to - {expected_associate_id}
    if unexpected_allocated_to:
        issues.append(IdentityIssue("data", "associate_id", expected_associate_id, ", ".join(sorted(unexpected_allocated_to))))

    return tuple(issues)


@dataclass(frozen=True, slots=True)
class ReconciledRow:
    associate_id: str
    identifier: str
    disposition: RowDisposition
    row: Mapping[str, str | None]


@dataclass(frozen=True, slots=True)
class ReconciliationSummary:
    allocated_count: int
    returned_count: int
    unique_returned_count: int
    """Distinct allocated identifiers actually touched by a returned file
    (matched or wrong-associate). This is the 'Returned' figure in the
    PROJECT_SPEC.md section 20 worked example: Allocated - Missing."""
    missing_identifiers: tuple[str, ...]
    duplicate_count: int
    unexpected_count: int
    wrong_associate_count: int
    incomplete_count: int
    identity_issues: tuple[IdentityIssue, ...]

    @property
    def has_open_critical_exceptions(self) -> bool:
        return bool(
            self.missing_identifiers
            or self.duplicate_count
            or self.unexpected_count
            or self.wrong_associate_count
            or self.identity_issues
        )


def reconcile(
    *,
    identifier_field: str,
    policy: NormalizationPolicy,
    assignments_by_associate: Mapping[str, Sequence[str]],
    returned_rows_by_associate: Mapping[str, Sequence[Mapping[str, str | None]]],
    identity_issues: Sequence[IdentityIssue],
) -> tuple[tuple[ReconciledRow, ...], ReconciliationSummary]:
    """Reconcile returned rows against the original allocation.

    ``assignments_by_associate`` maps associate_id to that associate's
    already-normalized assigned identifiers. ``returned_rows_by_associate``
    maps associate_id to that associate's raw returned Data-sheet rows.
    """
    ownership: dict[str, str] = {}
    for associate_id, identifiers in assignments_by_associate.items():
        for identifier in identifiers:
            ownership[identifier] = associate_id

    seen: set[str] = set()
    touched: set[str] = set()
    reconciled: list[ReconciledRow] = []
    incomplete_count = 0

    for associate_id, rows in returned_rows_by_associate.items():
        for row in rows:
            raw_value = row.get(identifier_field)
            if not isinstance(raw_value, str) or not raw_value.strip():
                reconciled.append(ReconciledRow(associate_id=associate_id, identifier="", disposition=RowDisposition.INCOMPLETE, row=row))
                incomplete_count += 1
                continue

            identifier = normalize_identifier(raw_value, policy)
            touched.add(identifier)

            if identifier in seen:
                disposition = RowDisposition.DUPLICATE
            else:
                owner = ownership.get(identifier)
                if owner is None:
                    disposition = RowDisposition.UNEXPECTED
                elif owner != associate_id:
                    disposition = RowDisposition.WRONG_ASSOCIATE
                else:
                    disposition = RowDisposition.MATCHED
                seen.add(identifier)
            reconciled.append(ReconciledRow(associate_id=associate_id, identifier=identifier, disposition=disposition, row=row))

    missing = tuple(sorted(set(ownership) - touched))
    summary = ReconciliationSummary(
        allocated_count=len(ownership),
        returned_count=len(reconciled),
        unique_returned_count=len(set(ownership) & touched),
        missing_identifiers=missing,
        duplicate_count=sum(1 for r in reconciled if r.disposition is RowDisposition.DUPLICATE),
        unexpected_count=sum(1 for r in reconciled if r.disposition is RowDisposition.UNEXPECTED),
        wrong_associate_count=sum(1 for r in reconciled if r.disposition is RowDisposition.WRONG_ASSOCIATE),
        incomplete_count=incomplete_count,
        identity_issues=tuple(identity_issues),
    )
    return tuple(reconciled), summary


def build_consolidated_export(reconciled_rows: Sequence[ReconciledRow]) -> tuple[tuple[str, ...], tuple[tuple[object, ...], ...], tuple[tuple[object, ...], ...]]:
    """Split reconciled rows into the Consolidation output's two layers
    (PROJECT_SPEC.md section 20/21): matched rows go to Consolidated;
    everything else (duplicate/unexpected/wrong_associate/incomplete) is
    quarantined for manual resolution, never silently merged.

    Returns (headers, consolidated_rows, quarantined_rows). Headers are
    'Associate ID', 'Disposition', plus the union of all row field names
    in order of first appearance.
    """
    field_names: list[str] = []
    for reconciled in reconciled_rows:
        for key in reconciled.row.keys():
            if key not in field_names:
                field_names.append(key)
    headers = ("Associate ID", "Disposition", *field_names)

    consolidated: list[tuple[object, ...]] = []
    quarantined: list[tuple[object, ...]] = []
    for reconciled in reconciled_rows:
        row_values = (reconciled.associate_id, reconciled.disposition.value, *(reconciled.row.get(name) for name in field_names))
        if reconciled.disposition is RowDisposition.MATCHED:
            consolidated.append(row_values)
        else:
            quarantined.append(row_values)
    return headers, tuple(consolidated), tuple(quarantined)
