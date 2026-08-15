"""Coordinates Associate File Splitting: ALLOCATED -> DISTRIBUTED.

Reads the frozen snapshot (associates, fields, filename pattern), the
finalized AllocationResult, and the persisted canonical source rows, then
builds and writes one .xlsx artifact per associate with a planned
allocation (PROJECT_SPEC.md section 15).

Each associate's file is registered as an ArtifactType.ASSOCIATE_FILES
artifact via FileArtifactManager, which never silently overwrites -- a
retry after a partial failure will surface loudly (ArtifactAlreadyExistsError)
for associates whose files already exist rather than quietly replacing
them. This is a known v1 limitation (no resume/idempotent-retry support
yet) rather than a hidden risk: operators should treat a failed
Distribution run as needing investigation, not a blind retry.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from operations_allocation.core.distribution import build_associate_file_content
from operations_allocation.domain.exceptions import InvalidAssociateConfigurationError
from operations_allocation.domain.models import ArtifactType, RunState
from operations_allocation.domain.state_machine import ensure_transition
from operations_allocation.infrastructure.xlsx_writer import write_associate_workbook
from operations_allocation.utils.identifiers import NormalizationPolicy, normalize_identifier


class DistributionService:
    def __init__(self, *, runs: Any, snapshots: Any, allocation_results: Any, source_import: Any, file_artifacts: Any, audit: Any) -> None:
        self.runs, self.snapshots, self.allocation_results = runs, snapshots, allocation_results
        self.source_import, self.file_artifacts, self.audit = source_import, file_artifacts, audit

    def distribute(self, *, run_id: str) -> tuple[Any, ...]:
        run = self.runs.get(run_id)
        ensure_transition(run.state, RunState.DISTRIBUTED)
        snapshot = self.snapshots.get(run_id)
        configuration = snapshot.configuration
        allocation_result = self.allocation_results.get(run_id)
        canonical_rows = self.source_import.read_canonical_source(run_id=run_id)

        policy = NormalizationPolicy.from_configuration(configuration["program_configuration"]["primary_identifier"])
        identifier_field = configuration["program_configuration"]["primary_identifier"]["field"]
        rows_by_identifier = {normalize_identifier(row[identifier_field], policy): row for row in canonical_rows}

        associates_by_id = {associate["associate_id"]: associate for associate in configuration["associates"]}
        filename_pattern = configuration["program_configuration"]["filename"].get("pattern", "{PROGRAM}_{ASSOCIATE_ID}_{ASSOCIATE_NAME}_{RUN_ID}.xlsx")
        fields = configuration["program_configuration"]["fields"]

        artifacts = []
        for assignment in allocation_result.assignments:
            if assignment.planned_count == 0:
                continue
            associate = associates_by_id.get(assignment.associate_id)
            if associate is None:
                raise InvalidAssociateConfigurationError(f"Allocated associate '{assignment.associate_id}' is not present in the Run Configuration Snapshot.")

            content = build_associate_file_content(
                assignment=assignment,
                associate_name=associate["name"],
                fields=fields,
                canonical_rows_by_identifier=rows_by_identifier,
                run_id=run_id,
                program_id=run.program_id,
                filename_pattern=filename_pattern,
            )
            workbook_bytes = write_associate_workbook(
                metadata={
                    "Run ID": run_id,
                    "Program": run.program_id,
                    "Associate ID": content.associate_id,
                    "Associate Name": content.associate_name,
                    "Item Count": str(len(content.rows)),
                    "Generated At": datetime.now(timezone.utc).isoformat(),
                },
                headers=content.headers,
                rows=content.rows,
            )
            artifact = self.file_artifacts.write_bytes(
                run_id=run_id,
                artifact_type=ArtifactType.ASSOCIATE_FILES,
                filename=content.filename,
                content=workbook_bytes,
                associate_id=content.associate_id,
            )
            artifacts.append(artifact)

        self.runs.update_state(run_id, RunState.DISTRIBUTED)
        self.audit.record(
            run_id=run_id,
            program_id=run.program_id,
            action="RUN_DISTRIBUTED",
            previous_state=run.state,
            new_state=RunState.DISTRIBUTED,
            metadata={"associate_file_count": len(artifacts), "total_items": sum(a.planned_count for a in allocation_result.assignments)},
        )
        return tuple(artifacts)
