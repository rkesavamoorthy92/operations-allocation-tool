"""Imports a raw Excel/CSV file for a Run, maps it to canonical field names,
and persists the result as the Run's authoritative source artifact.

PROJECT_SPEC.md section 5: "The original source file must never be
modified. The authoritative processed source must be an imported local
artifact associated with the Run, rather than a mutable external file
path." This service is what makes that concrete: everything downstream
(Validation, Sampling, Allocation, Distribution) reads canonical rows back
from this artifact rather than re-reading a caller-supplied file path,
and the artifact is written once -- FileArtifactManager's
never-silently-overwrite guarantee means a second import attempt for the
same Run fails loudly rather than quietly replacing immutable evidence.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from operations_allocation.core.column_mapping import map_rows
from operations_allocation.domain.exceptions import PersistenceError
from operations_allocation.domain.models import Artifact, ArtifactType
from operations_allocation.infrastructure.tabular_import import read_raw_table

_CANONICAL_SOURCE_FILENAME = "canonical_source.json"


class SourceImportService:
    def __init__(self, *, snapshots: Any, file_artifacts: Any, audit: Any) -> None:
        self.snapshots, self.file_artifacts, self.audit = snapshots, file_artifacts, audit

    def import_source(self, *, run_id: str, file_path: Path | str) -> tuple[list[dict[str, str | None]], Artifact]:
        snapshot = self.snapshots.get(run_id)
        column_mappings = snapshot.configuration["column_mappings"]
        raw_table = read_raw_table(file_path)
        canonical_rows = map_rows(raw_table, column_mappings)

        content = json.dumps(canonical_rows, ensure_ascii=False).encode("utf-8")
        artifact = self.file_artifacts.write_bytes(
            run_id=run_id,
            artifact_type=ArtifactType.SOURCE,
            filename=_CANONICAL_SOURCE_FILENAME,
            content=content,
        )
        self.audit.record(
            run_id=run_id,
            program_id=run_id.rsplit("-", 2)[0],
            action="SOURCE_IMPORTED",
            metadata={
                "original_filename": Path(file_path).name,
                "row_count": len(canonical_rows),
                "artifact_sha256": artifact.sha256,
            },
        )
        return canonical_rows, artifact

    def read_canonical_source(self, *, run_id: str) -> list[dict[str, str | None]]:
        """Read back the canonical rows persisted by :meth:`import_source`."""
        matching = [
            artifact
            for artifact in self.file_artifacts.list_for_run(run_id)
            if artifact.artifact_type is ArtifactType.SOURCE and artifact.original_filename == _CANONICAL_SOURCE_FILENAME
        ]
        if not matching:
            raise PersistenceError(f"Run '{run_id}' does not have an imported canonical source artifact.")
        return json.loads(self.file_artifacts.read_bytes(matching[0]))
