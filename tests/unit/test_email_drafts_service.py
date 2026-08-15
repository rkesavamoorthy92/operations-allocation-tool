from __future__ import annotations

import csv
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from operations_allocation.domain.exceptions import AssociateFileNotDistributedError, EmailTemplateError
from operations_allocation.domain.models import ArtifactType
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
from operations_allocation.services.distribution import DistributionService
from operations_allocation.services.eligible_population import EligiblePopulationService
from operations_allocation.services.email_drafts import EmailDraftService
from operations_allocation.services.program_configuration import ProgramConfigurationService
from operations_allocation.services.run_orchestration import RunOrchestrationService
from operations_allocation.services.sampling import SamplingService
from operations_allocation.services.source_import import SourceImportService
from tests.unit.test_distribution_service import distribution_config


def email_config() -> dict:
    config = distribution_config()
    config["email"] = {
        "templates": {
            "individual_subject": "{{program_name}} allocation for {{associate_name}}",
            "individual_body": "You have {{item_count}} items due {{due_date}} (Run {{run_id}}).",
            "consolidated_subject": "{{program_name}} team allocation - Run {{run_id}}",
            "consolidated_body": "{{item_count}} items total across the team, due {{due_date}}.",
        }
    }
    return config


class FakeOutlookAdapter:
    def __init__(self, *, should_fail: bool = False) -> None:
        self.should_fail = should_fail
        self.created_drafts: list = []

    def create_draft(self, draft) -> None:
        if self.should_fail:
            from operations_allocation.domain.exceptions import OutlookUnavailableError

            raise OutlookUnavailableError("simulated Outlook unavailability")
        self.created_drafts.append(draft)


class EmailDraftServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        database = Database(Path(self.tempdir.name) / "email.db")
        database.initialize_schema()
        programs = ProgramRepository(database)
        self.runs = RunRepository(database)
        self.snapshots = SnapshotRepository(database)
        self.audit_repository = AuditRepository(database)
        audit = AuditService(self.audit_repository, "Test Application")
        ProgramConfigurationService(programs).create_program("MX-PT", "MX PT")
        ProgramConfigurationService(programs).save_version(email_config())

        self.orchestration = RunOrchestrationService(runs=self.runs, snapshots=self.snapshots, manifests=ManifestRepository(database), audit=audit)
        self.file_artifacts = FileArtifactManager(base_directory=Path(self.tempdir.name) / "artifacts", artifacts=ArtifactRepository(database))
        self.source_import = SourceImportService(snapshots=self.snapshots, file_artifacts=self.file_artifacts, audit=audit)
        populations = EligiblePopulationRepository(database)
        self.eligible_population_service = EligiblePopulationService(runs=self.runs, snapshots=self.snapshots, populations=populations, audit=audit)
        self.sampling_results = SamplingResultRepository(database)
        self.sampling_service = SamplingService(runs=self.runs, snapshots=self.snapshots, populations=populations, sampling_results=self.sampling_results, audit=audit)
        self.allocation_results = AllocationResultRepository(database)
        self.allocation_service = AllocationService(runs=self.runs, snapshots=self.snapshots, sampling_results=self.sampling_results, allocation_results=self.allocation_results, audit=audit)
        self.distribution_service = DistributionService(runs=self.runs, snapshots=self.snapshots, allocation_results=self.allocation_results, source_import=self.source_import, file_artifacts=self.file_artifacts, audit=audit)
        self.email_service = EmailDraftService(snapshots=self.snapshots, allocation_results=self.allocation_results, file_artifacts=self.file_artifacts, audit=audit)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _write_source_csv(self, row_count: int) -> Path:
        path = Path(self.tempdir.name) / "source.csv"
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["Product ID", "PT"])
            for i in range(1, row_count + 1):
                writer.writerow([f"P{i:03d}", "Shoes"])
        return path

    def _run_to_distributed(self, *, associates: list[dict], sample_count: int, row_count: int = 20, due_date: str | None = "2026-08-25", configuration: dict | None = None) -> str:
        config = configuration if configuration is not None else email_config()
        run = self.orchestration.create_run(program_id="MX-PT", created_by="user", created_on=date(2026, 8, 15))
        self.orchestration.freeze_setup(run_id=run.run_id, program_configuration=config, sampling={"method": "count", "value": sample_count}, random_seed="seed", associates=associates, due_date=due_date)
        source_path = self._write_source_csv(row_count)
        canonical_rows, _ = self.source_import.import_source(run_id=run.run_id, file_path=source_path)
        self.eligible_population_service.validate(run_id=run.run_id, rows=canonical_rows)
        self.eligible_population_service.freeze(run_id=run.run_id, rows=canonical_rows)
        self.sampling_service.sample(run_id=run.run_id)
        self.allocation_service.finalize(run_id=run.run_id)
        self.distribution_service.distribute(run_id=run.run_id)
        return run.run_id

    def test_individual_drafts_created_with_fallback_artifact(self) -> None:
        associates = [
            {"associate_id": "A001", "name": "Jane Doe", "email": "jane.doe@example.test", "active": True, "target": 10, "maximum_capacity": 10},
            {"associate_id": "A002", "name": "John Smith", "email": "john.smith@example.test", "active": True, "target": 10, "maximum_capacity": 10},
        ]
        run_id = self._run_to_distributed(associates=associates, sample_count=20)
        artifacts = self.email_service.create_individual_drafts(run_id=run_id)
        self.assertEqual(len(artifacts), 2)
        for artifact in artifacts:
            self.assertEqual(artifact.artifact_type, ArtifactType.EMAIL_DRAFTS)
        text = self.file_artifacts.read_bytes(artifacts[0]).decode("utf-8")
        self.assertIn("To: ", text)
        self.assertIn("items due 2026-08-25", text)

    def test_individual_draft_uses_outlook_adapter_when_available(self) -> None:
        associates = [{"associate_id": "A001", "name": "Jane Doe", "email": "jane.doe@example.test", "active": True, "target": 5, "maximum_capacity": 5}]
        run_id = self._run_to_distributed(associates=associates, sample_count=5)
        adapter = FakeOutlookAdapter()
        self.email_service.create_individual_drafts(run_id=run_id, outlook_adapter=adapter)
        self.assertEqual(len(adapter.created_drafts), 1)
        actions = [event for event in self.audit_repository.for_run(run_id) if event["action"] == "EMAIL_DRAFT_CREATED"]
        self.assertTrue(json.loads(actions[0]["metadata_json"])["outlook_created"])

    def test_outlook_failure_falls_back_without_raising(self) -> None:
        associates = [{"associate_id": "A001", "name": "Jane Doe", "email": "jane.doe@example.test", "active": True, "target": 5, "maximum_capacity": 5}]
        run_id = self._run_to_distributed(associates=associates, sample_count=5)
        adapter = FakeOutlookAdapter(should_fail=True)
        artifacts = self.email_service.create_individual_drafts(run_id=run_id, outlook_adapter=adapter)
        self.assertEqual(len(artifacts), 1)
        actions = [event for event in self.audit_repository.for_run(run_id) if event["action"] == "EMAIL_DRAFT_CREATED"]
        metadata = json.loads(actions[0]["metadata_json"])
        self.assertFalse(metadata["outlook_created"])
        self.assertIn("simulated", metadata["outlook_error"])

    def test_consolidated_draft_recipients_are_unique_and_sorted(self) -> None:
        associates = [
            {"associate_id": "A001", "name": "Jane Doe", "email": "jane.doe@example.test", "active": True, "target": 10, "maximum_capacity": 10},
            {"associate_id": "A002", "name": "John Smith", "email": "john.smith@example.test", "active": True, "target": 10, "maximum_capacity": 10},
        ]
        run_id = self._run_to_distributed(associates=associates, sample_count=20)
        artifact = self.email_service.create_consolidated_draft(run_id=run_id)
        text = self.file_artifacts.read_bytes(artifact).decode("utf-8")
        self.assertIn("jane.doe@example.test; john.smith@example.test", text)
        self.assertIn("20 items total", text)

    def test_missing_templates_raise_clear_error(self) -> None:
        associates = [{"associate_id": "A001", "name": "Jane Doe", "email": "jane.doe@example.test", "active": True, "target": 5, "maximum_capacity": 5}]
        run_id = self._run_to_distributed(associates=associates, sample_count=5, configuration=distribution_config())
        with self.assertRaises(EmailTemplateError):
            self.email_service.create_individual_drafts(run_id=run_id)

    def test_missing_due_date_raises_clear_error(self) -> None:
        associates = [{"associate_id": "A001", "name": "Jane Doe", "email": "jane.doe@example.test", "active": True, "target": 5, "maximum_capacity": 5}]
        run_id = self._run_to_distributed(associates=associates, sample_count=5, due_date=None)
        with self.assertRaises(EmailTemplateError):
            self.email_service.create_individual_drafts(run_id=run_id)

    def test_drafts_before_distribution_raise_clear_error(self) -> None:
        run = self.orchestration.create_run(program_id="MX-PT", created_by="user", created_on=date(2026, 8, 15))
        associates = [{"associate_id": "A001", "name": "Jane Doe", "email": "jane.doe@example.test", "active": True, "target": 5, "maximum_capacity": 5}]
        self.orchestration.freeze_setup(run_id=run.run_id, program_configuration=email_config(), sampling={"method": "count", "value": 5}, random_seed="seed", associates=associates, due_date="2026-08-25")
        source_path = self._write_source_csv(20)
        canonical_rows, _ = self.source_import.import_source(run_id=run.run_id, file_path=source_path)
        self.eligible_population_service.validate(run_id=run.run_id, rows=canonical_rows)
        self.eligible_population_service.freeze(run_id=run.run_id, rows=canonical_rows)
        self.sampling_service.sample(run_id=run.run_id)
        self.allocation_service.finalize(run_id=run.run_id)
        with self.assertRaises(AssociateFileNotDistributedError):
            self.email_service.create_individual_drafts(run_id=run.run_id)
