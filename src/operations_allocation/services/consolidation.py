"""Coordinates Consolidation: DISTRIBUTED -> RETURNED -> CONSOLIDATED
(PROJECT_SPEC.md sections 19-21).

v1 scope: one bulk import of all returned files per Run (matching the
spec's "select multiple returned files at once"), not incremental
imports across multiple sessions -- a repeated import attempt fails
loudly via FileArtifactManager's never-overwrite guarantee rather than
silently replacing evidence, which is an intentional limitation rather
than a hidden one.

Filename identity (PROJECT_SPEC.md section 19, item 1) is checked by
reconstructing the expected filename for the associate the caller claims
a file belongs to and comparing it byte-for-byte; this avoids parsing an
ambiguous, program-configurable filename pattern back into components.
The caller (UI) is expected to have already resolved file-to-associate
by matching filenames against candidates, same as a human would.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from operations_allocation.core.consolidation import (
    FileIdentity,
    IdentityIssue,
    ReconciledRow,
    RowDisposition,
    build_consolidated_export,
    check_identity,
    reconcile,
)
from operations_allocation.core.distribution import build_filename, field_header
from operations_allocation.domain.exceptions import ConsolidationBlockedByExceptionsError, InvalidAssociateConfigurationError, InvalidOverrideError, PersistenceError
from operations_allocation.domain.models import ArtifactType, RunState
from operations_allocation.domain.state_machine import ensure_transition
from operations_allocation.infrastructure.returned_file_reader import read_returned_workbook
from operations_allocation.infrastructure.xlsx_writer import write_multi_sheet_workbook
from operations_allocation.utils.identifiers import NormalizationPolicy

_RECONCILIATION_FILENAME = "reconciliation.json"
_RAW_RETURNED_FILENAME = "raw_returned_rows.json"


class ConsolidationService:
    def __init__(self, *, runs: Any, snapshots: Any, allocation_results: Any, file_artifacts: Any, audit: Any) -> None:
        self.runs, self.snapshots, self.allocation_results = runs, snapshots, allocation_results
        self.file_artifacts, self.audit = file_artifacts, audit

    def import_returned_files(self, *, run_id: str, files: list[tuple[Path, str]]) -> dict:
        run = self.runs.get(run_id)
        ensure_transition(run.state, RunState.RETURNED)
        snapshot = self.snapshots.get(run_id)
        configuration = snapshot.configuration
        program_configuration = configuration["program_configuration"]
        allocation_result = self.allocation_results.get(run_id)

        associates_by_id = {associate["associate_id"]: associate for associate in configuration["associates"]}
        assignments_by_associate = {a.associate_id: a.assigned_identifiers for a in allocation_result.assignments}
        policy = NormalizationPolicy.from_configuration(program_configuration["primary_identifier"])
        identifier_field = program_configuration["primary_identifier"]["field"]
        header_to_field = {field_header(field): field["name"] for field in program_configuration["fields"]}
        filename_pattern = program_configuration["filename"].get("pattern", "{PROGRAM}_{ASSOCIATE_ID}_{ASSOCIATE_NAME}_{RUN_ID}.xlsx")

        all_identity_issues: list[IdentityIssue] = []
        returned_rows_by_associate: dict[str, list[dict]] = {}

        for file_path, claimed_associate_id in files:
            associate = associates_by_id.get(claimed_associate_id)
            if associate is None:
                raise InvalidAssociateConfigurationError(f"Returned file claims associate '{claimed_associate_id}', which is not in this Run's snapshot.")

            workbook = read_returned_workbook(file_path)
            canonical_rows = [{header_to_field.get(header, header): value for header, value in row.items()} for row in workbook.rows]

            expected_filename = build_filename(filename_pattern, program_id=run.program_id, run_id=run_id, associate_id=claimed_associate_id, associate_name=associate["name"])
            filename_matches = Path(file_path).name == expected_filename
            issues: list[IdentityIssue] = []
            if not filename_matches:
                issues.append(IdentityIssue("filename", "filename", expected_filename, Path(file_path).name))

            identity = FileIdentity(
                filename_run_id=run_id if filename_matches else None,
                filename_associate_id=claimed_associate_id if filename_matches else None,
                metadata_run_id=workbook.metadata.get("Run ID"),
                metadata_associate_id=workbook.metadata.get("Associate ID"),
                metadata_associate_name=workbook.metadata.get("Associate Name"),
                data_run_ids=frozenset(row["run_id"] for row in canonical_rows if row.get("run_id")),
                data_allocated_to=frozenset(row["allocated_to"] for row in canonical_rows if row.get("allocated_to")),
            )
            issues.extend(check_identity(identity, expected_run_id=run_id, expected_associate_id=claimed_associate_id, expected_associate_name=associate["name"]))
            all_identity_issues.extend(issues)
            returned_rows_by_associate.setdefault(claimed_associate_id, []).extend(canonical_rows)

        reconciled_rows, summary = reconcile(
            identifier_field=identifier_field,
            policy=policy,
            assignments_by_associate=assignments_by_associate,
            returned_rows_by_associate=returned_rows_by_associate,
            identity_issues=tuple(all_identity_issues),
        )

        self.file_artifacts.write_bytes(
            run_id=run_id,
            artifact_type=ArtifactType.RETURNED_FILES,
            filename=_RAW_RETURNED_FILENAME,
            content=json.dumps(returned_rows_by_associate, ensure_ascii=False).encode("utf-8"),
        )
        reconciliation_payload = _serialize_reconciliation(reconciled_rows, summary)
        reconciliation_artifact = self.file_artifacts.write_bytes(
            run_id=run_id,
            artifact_type=ArtifactType.RETURNED_FILES,
            filename=_RECONCILIATION_FILENAME,
            content=json.dumps(reconciliation_payload, ensure_ascii=False).encode("utf-8"),
        )

        self.runs.update_state(run_id, RunState.RETURNED)
        self.audit.record(
            run_id=run_id,
            program_id=run.program_id,
            action="RUN_RETURNED",
            previous_state=run.state,
            new_state=RunState.RETURNED,
            metadata={
                "allocated_count": summary.allocated_count,
                "unique_returned_count": summary.unique_returned_count,
                "missing_count": len(summary.missing_identifiers),
                "duplicate_count": summary.duplicate_count,
                "unexpected_count": summary.unexpected_count,
                "wrong_associate_count": summary.wrong_associate_count,
                "identity_issue_count": len(summary.identity_issues),
                "reconciliation_artifact_sha256": reconciliation_artifact.sha256,
            },
        )
        return reconciliation_payload

    def finalize(self, *, run_id: str, override: bool = False, overridden_by: str | None = None, override_reason: str | None = None) -> Any:
        run = self.runs.get(run_id)
        ensure_transition(run.state, RunState.CONSOLIDATED)
        reconciliation_artifact = _find_artifact(self.file_artifacts, run_id, _RECONCILIATION_FILENAME)
        payload = json.loads(self.file_artifacts.read_bytes(reconciliation_artifact))
        has_open_critical_exceptions = payload["summary"]["has_open_critical_exceptions"]

        if has_open_critical_exceptions and not override:
            raise ConsolidationBlockedByExceptionsError(
                f"Run '{run_id}' has open critical reconciliation exceptions and cannot be consolidated without an explicit override. "
                f"Summary: {payload['summary']}."
            )
        if override:
            if not overridden_by or not overridden_by.strip() or not override_reason or not override_reason.strip():
                raise InvalidOverrideError("An override requires both an accountable user and a non-empty reason.")

        reconciled_rows = tuple(
            ReconciledRow(associate_id=item["associate_id"], identifier=item["identifier"], disposition=RowDisposition(item["disposition"]), row=item["row"])
            for item in payload["reconciled_rows"]
        )
        headers, consolidated_rows, quarantined_rows = build_consolidated_export(reconciled_rows)
        workbook_bytes = write_multi_sheet_workbook({"Consolidated": (headers, consolidated_rows), "Quarantined": (headers, quarantined_rows)})
        export_artifact = self.file_artifacts.write_bytes(
            run_id=run_id,
            artifact_type=ArtifactType.CONSOLIDATED,
            filename=f"{run_id}_consolidated.xlsx",
            content=workbook_bytes,
        )

        self.runs.update_state(run_id, RunState.CONSOLIDATED)
        self.audit.record(
            run_id=run_id,
            program_id=run.program_id,
            action="RUN_CONSOLIDATED",
            previous_state=run.state,
            new_state=RunState.CONSOLIDATED,
            metadata={
                "override": override,
                "overridden_by": overridden_by,
                "override_reason": override_reason,
                "reconciliation_version": reconciliation_artifact.sha256,
                "consolidated_row_count": len(consolidated_rows),
                "quarantined_row_count": len(quarantined_rows),
            },
        )
        return export_artifact


def _find_artifact(file_artifacts: Any, run_id: str, filename: str) -> Any:
    matching = [artifact for artifact in file_artifacts.list_for_run(run_id) if artifact.original_filename == filename]
    if not matching:
        raise PersistenceError(f"Run '{run_id}' does not have a '{filename}' artifact yet.")
    return matching[0]


def _serialize_reconciliation(reconciled_rows: tuple, summary: Any) -> dict:
    return {
        "summary": {
            "allocated_count": summary.allocated_count,
            "returned_count": summary.returned_count,
            "unique_returned_count": summary.unique_returned_count,
            "missing_identifiers": list(summary.missing_identifiers),
            "duplicate_count": summary.duplicate_count,
            "unexpected_count": summary.unexpected_count,
            "wrong_associate_count": summary.wrong_associate_count,
            "incomplete_count": summary.incomplete_count,
            "identity_issue_count": len(summary.identity_issues),
            "has_open_critical_exceptions": summary.has_open_critical_exceptions,
        },
        "reconciled_rows": [
            {"associate_id": r.associate_id, "identifier": r.identifier, "disposition": r.disposition.value, "row": dict(r.row)}
            for r in reconciled_rows
        ],
    }
