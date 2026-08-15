from __future__ import annotations

import csv
import tempfile
import unittest
from datetime import date
from pathlib import Path

from operations_allocation.domain.exceptions import ArtifactAlreadyExistsError, PersistenceError
from operations_allocation.infrastructure.file_artifacts import FileArtifactManager
from operations_allocation.persistence.database import Database
from operations_allocation.persistence.repositories import ArtifactRepository, AuditRepository, ManifestRepository, ProgramRepository, RunRepository, SnapshotRepository
from operations_allocation.services.audit import AuditService
from operations_allocation.services.program_configuration import ProgramConfigurationService
from operations_allocation.services.run_orchestration import RunOrchestrationService
from operations_allocation.services.source_import import SourceImportService
from tests.unit.test_foundation import valid_config


class SourceImportServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        database = Database(Path(self.tempdir.name) / "source.db")
        database.initialize_schema()
        programs = ProgramRepository(database)
        self.runs = RunRepository(database)
        self.snapshots = SnapshotRepository(database)
        self.audit_repository = AuditRepository(database)
        audit = AuditService(self.audit_repository, "Test Application")
        ProgramConfigurationService(programs).create_program("MX-PT", "MX PT")
        ProgramConfigurationService(programs).save_version(valid_config())
        self.orchestration = RunOrchestrationService(runs=self.runs, snapshots=self.snapshots, manifests=ManifestRepository(database), audit=audit)
        self.file_artifacts = FileArtifactManager(base_directory=Path(self.tempdir.name) / "artifacts", artifacts=ArtifactRepository(database))
        self.service = SourceImportService(snapshots=self.snapshots, file_artifacts=self.file_artifacts, audit=audit)
        run = self.orchestration.create_run(program_id="MX-PT", created_by="user", created_on=date(2026, 8, 15))
        self.orchestration.freeze_setup(run_id=run.run_id, program_configuration=valid_config(), sampling={}, random_seed=None, associates=[])
        self.run_id = run.run_id

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _write_source_csv(self, rows: list[list[str]]) -> Path:
        path = Path(self.tempdir.name) / "source.csv"
        with path.open("w", newline="", encoding="utf-8") as handle:
            csv.writer(handle).writerows(rows)
        return path

    def test_import_maps_and_persists_canonical_rows(self) -> None:
        path = self._write_source_csv([["Product ID"], ["P1"], ["P2"]])
        canonical_rows, artifact = self.service.import_source(run_id=self.run_id, file_path=path)
        self.assertEqual(canonical_rows, [{"product_id": "P1"}, {"product_id": "P2"}])
        self.assertEqual(artifact.original_filename, "canonical_source.json")

    def test_read_canonical_source_round_trips(self) -> None:
        path = self._write_source_csv([["Product ID"], ["P1"], ["P2"]])
        self.service.import_source(run_id=self.run_id, file_path=path)
        read_back = self.service.read_canonical_source(run_id=self.run_id)
        self.assertEqual(read_back, [{"product_id": "P1"}, {"product_id": "P2"}])

    def test_read_canonical_source_without_import_raises(self) -> None:
        with self.assertRaises(PersistenceError):
            self.service.read_canonical_source(run_id=self.run_id)

    def test_second_import_for_same_run_is_rejected_not_silently_overwritten(self) -> None:
        path = self._write_source_csv([["Product ID"], ["P1"]])
        self.service.import_source(run_id=self.run_id, file_path=path)
        with self.assertRaises(ArtifactAlreadyExistsError):
            self.service.import_source(run_id=self.run_id, file_path=path)

    def test_preserves_leading_zeros_end_to_end(self) -> None:
        path = self._write_source_csv([["Product ID"], ["00042"]])
        canonical_rows, _ = self.service.import_source(run_id=self.run_id, file_path=path)
        self.assertEqual(canonical_rows[0]["product_id"], "00042")

    def test_import_records_audit_event(self) -> None:
        path = self._write_source_csv([["Product ID"], ["P1"]])
        self.service.import_source(run_id=self.run_id, file_path=path)
        actions = [event["action"] for event in self.audit_repository.for_run(self.run_id)]
        self.assertIn("SOURCE_IMPORTED", actions)
