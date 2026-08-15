"""Wires the application data directory, SQLite database, repositories,
and every application service into one object the UI layer can use.

ARCHITECTURE.md section 3/9: PySide6 UI components must not contain
business logic. This module has no PySide6 dependency at all -- it is
plain composition, fully unit-testable without a display, and is the
*only* place the UI is allowed to reach into repositories/services.
"""

from __future__ import annotations

import getpass
import os
from dataclasses import dataclass
from pathlib import Path

from operations_allocation.infrastructure.file_artifacts import FileArtifactManager
from operations_allocation.persistence.database import Database
from operations_allocation.persistence.repositories import (
    AllocationResultRepository,
    ArtifactRepository,
    AuditRepository,
    EligiblePopulationRepository,
    ManifestRepository,
    ProgramRepository,
    RunRepository,
    SamplingResultRepository,
    SnapshotRepository,
)
from operations_allocation.services.allocation import AllocationService
from operations_allocation.services.audit import AuditService
from operations_allocation.services.consolidation import ConsolidationService
from operations_allocation.services.distribution import DistributionService
from operations_allocation.services.eligible_population import EligiblePopulationService
from operations_allocation.services.email_drafts import EmailDraftService
from operations_allocation.services.errors import ErrorService
from operations_allocation.services.program_configuration import ProgramConfigurationService
from operations_allocation.services.qc import QcService
from operations_allocation.services.run_orchestration import RunOrchestrationService
from operations_allocation.services.sampling import SamplingService
from operations_allocation.services.source_import import SourceImportService


def default_data_directory() -> Path:
    """PROJECT_SPEC.md section 29 / ARCHITECTURE.md section 11: mutable
    application data lives in a user-writable local application data
    directory, never the installation directory. Falls back to a local
    folder outside Windows (e.g. for development on macOS)."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    base = Path(local_app_data) if local_app_data else Path.home() / ".operations-allocation-tool"
    return base / "OperationsAllocationTool"


@dataclass(frozen=True, slots=True)
class AppContext:
    data_directory: Path
    database: Database
    programs: ProgramRepository
    runs: RunRepository
    snapshots: SnapshotRepository
    audit_repository: AuditRepository
    file_artifacts: FileArtifactManager
    program_configuration: ProgramConfigurationService
    orchestration: RunOrchestrationService
    source_import: SourceImportService
    eligible_population: EligiblePopulationService
    sampling: SamplingService
    allocation: AllocationService
    distribution: DistributionService
    email_drafts: EmailDraftService
    consolidation: ConsolidationService
    qc: QcService
    errors: ErrorService
    audit: AuditService

    @classmethod
    def build(cls, *, data_directory: Path | None = None, application_name: str = "Operations Allocation Tool") -> "AppContext":
        directory = data_directory or default_data_directory()
        directory.mkdir(parents=True, exist_ok=True)

        database = Database(directory / "operations_allocation.db")
        database.initialize_schema()

        programs = ProgramRepository(database)
        runs = RunRepository(database)
        snapshots = SnapshotRepository(database)
        audit_repository = AuditRepository(database)
        manifests = ManifestRepository(database)
        populations = EligiblePopulationRepository(database)
        sampling_results = SamplingResultRepository(database)
        allocation_results = AllocationResultRepository(database)
        artifacts = ArtifactRepository(database)

        file_artifacts = FileArtifactManager(base_directory=directory / "artifacts", artifacts=artifacts)
        audit = AuditService(audit_repository, application_name)

        program_configuration = ProgramConfigurationService(programs)
        orchestration = RunOrchestrationService(runs=runs, snapshots=snapshots, manifests=manifests, audit=audit)
        source_import = SourceImportService(snapshots=snapshots, file_artifacts=file_artifacts, audit=audit)
        eligible_population = EligiblePopulationService(runs=runs, snapshots=snapshots, populations=populations, audit=audit)
        sampling = SamplingService(runs=runs, snapshots=snapshots, populations=populations, sampling_results=sampling_results, audit=audit)
        allocation = AllocationService(runs=runs, snapshots=snapshots, sampling_results=sampling_results, allocation_results=allocation_results, audit=audit)
        distribution = DistributionService(runs=runs, snapshots=snapshots, allocation_results=allocation_results, source_import=source_import, file_artifacts=file_artifacts, audit=audit)
        email_drafts = EmailDraftService(snapshots=snapshots, allocation_results=allocation_results, file_artifacts=file_artifacts, audit=audit)
        consolidation = ConsolidationService(runs=runs, snapshots=snapshots, allocation_results=allocation_results, file_artifacts=file_artifacts, audit=audit)
        qc = QcService(runs=runs, snapshots=snapshots, file_artifacts=file_artifacts, audit=audit)
        errors = ErrorService(snapshots=snapshots, file_artifacts=file_artifacts, audit=audit)

        return cls(
            data_directory=directory, database=database, programs=programs, runs=runs, snapshots=snapshots,
            audit_repository=audit_repository, file_artifacts=file_artifacts, program_configuration=program_configuration,
            orchestration=orchestration, source_import=source_import, eligible_population=eligible_population,
            sampling=sampling, allocation=allocation, distribution=distribution, email_drafts=email_drafts,
            consolidation=consolidation, qc=qc, errors=errors, audit=audit,
        )

    @staticmethod
    def current_os_username() -> str:
        try:
            return getpass.getuser()
        except Exception:
            return "unknown"
