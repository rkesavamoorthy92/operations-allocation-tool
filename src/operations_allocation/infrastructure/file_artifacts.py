"""File Artifact Manager (ARCHITECTURE.md section 4.6).

Manages Run-specific output directories and artifact metadata: every
imported or generated file gets a SHA-256 hash, byte size, original
filename, timestamp, Run ID, and artifact type recorded so nothing relies
on ad hoc filesystem scanning. Generated files are written via
temporary-file-plus-atomic-rename. Source artifacts (and any artifact,
by default) are never silently overwritten -- AGENTS.md section 30, "No
Silent Data Loss."

This module only touches the filesystem and the ArtifactRepository; it has
no business logic about *what* to generate.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from operations_allocation.domain.exceptions import ArtifactAlreadyExistsError, ArtifactSourceNotFoundError, InvalidArtifactFilenameError
from operations_allocation.domain.models import Artifact, ArtifactType


def validate_artifact_filename(filename: str) -> str:
    """Reject path separators, empty names, and traversal attempts."""
    if not filename or not filename.strip():
        raise InvalidArtifactFilenameError("Artifact filename must not be empty.")
    candidate = Path(filename)
    if candidate.name != filename or candidate.is_absolute() or ".." in candidate.parts:
        raise InvalidArtifactFilenameError(f"Artifact filename '{filename}' must be a plain filename with no path components.")
    return filename


class FileArtifactManager:
    def __init__(self, *, base_directory: Path | str, artifacts: Any) -> None:
        self.base_directory = Path(base_directory)
        self.artifacts = artifacts

    def run_directory(self, run_id: str) -> Path:
        return self.base_directory / run_id

    def ensure_run_directories(self, run_id: str) -> None:
        for artifact_type in ArtifactType:
            (self.run_directory(run_id) / artifact_type.value).mkdir(parents=True, exist_ok=True)

    def write_bytes(
        self,
        *,
        run_id: str,
        artifact_type: ArtifactType,
        filename: str,
        content: bytes,
        associate_id: str | None = None,
    ) -> Artifact:
        """Atomically write ``content`` and register it as an Artifact.

        Never overwrites an existing artifact of the same name for the same
        Run -- AGENTS.md section 30, "No Silent Data Loss." Callers needing
        a new version must use a distinct filename (e.g. including a
        regeneration timestamp or Run ID, which the v1 filename convention
        already does).
        """
        validate_artifact_filename(filename)
        target_directory = self.run_directory(run_id) / artifact_type.value
        target_directory.mkdir(parents=True, exist_ok=True)
        target_path = target_directory / filename
        if target_path.exists():
            raise ArtifactAlreadyExistsError(f"Artifact '{filename}' already exists for Run '{run_id}' and would be silently overwritten.")

        descriptor, temp_path_str = tempfile.mkstemp(dir=target_directory, prefix=".tmp-")
        temp_path = Path(temp_path_str)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(content)
            os.replace(temp_path, target_path)
        finally:
            temp_path.unlink(missing_ok=True)

        artifact = Artifact(
            run_id=run_id,
            artifact_type=artifact_type,
            relative_path=str(Path(artifact_type.value) / filename),
            original_filename=filename,
            sha256=hashlib.sha256(content).hexdigest(),
            byte_size=len(content),
            created_at=datetime.now(timezone.utc),
            associate_id=associate_id,
        )
        self.artifacts.add(artifact)
        return artifact

    def import_file(
        self,
        *,
        run_id: str,
        artifact_type: ArtifactType,
        source_path: Path | str,
        filename: str | None = None,
        associate_id: str | None = None,
    ) -> Artifact:
        """Copy an externally-supplied file into the Run's artifact tree.

        The original ``source_path`` is only read, never modified or
        deleted -- PROJECT_SPEC.md section 5, "The original source file
        must never be modified."
        """
        source = Path(source_path)
        if not source.is_file():
            raise ArtifactSourceNotFoundError(f"Source file '{source}' could not be found.")
        content = source.read_bytes()
        return self.write_bytes(
            run_id=run_id,
            artifact_type=artifact_type,
            filename=filename or source.name,
            content=content,
            associate_id=associate_id,
        )

    def read_bytes(self, artifact: Artifact) -> bytes:
        return (self.run_directory(artifact.run_id) / artifact.relative_path).read_bytes()

    def list_for_run(self, run_id: str) -> tuple[Artifact, ...]:
        return self.artifacts.list_for_run(run_id)
