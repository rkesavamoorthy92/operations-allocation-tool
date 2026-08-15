from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from operations_allocation.domain.models import RunState
from operations_allocation.persistence.database import Database
from operations_allocation.persistence.repositories import AuditRepository, ManifestRepository, ProgramRepository, RunRepository, SnapshotRepository
from operations_allocation.services.audit import AuditService
from operations_allocation.services.program_configuration import ProgramConfigurationService
from operations_allocation.services.run_orchestration import RunOrchestrationService
from tests.unit.test_foundation import valid_config


class RunLifecycleIntegrationTest(unittest.TestCase):
    def test_persisted_run_lifecycle_uses_immutable_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Database(Path(directory) / "run.db")
            database.initialize_schema()
            programs = ProgramRepository(database)
            configuration = ProgramConfigurationService(programs)
            configuration.create_program("MX-PT", "MX PT")
            configuration.save_version(valid_config())
            audit_repository = AuditRepository(database)
            service = RunOrchestrationService(runs=RunRepository(database), snapshots=SnapshotRepository(database), manifests=ManifestRepository(database), audit=AuditService(audit_repository))
            run = service.create_run(program_id="MX-PT", created_by="tester", created_on=date(2026, 8, 15))
            snapshot = service.freeze_setup(run_id=run.run_id, program_configuration=valid_config(), sampling={"method": "count", "value": 1}, random_seed="7", associates=[])
            run = service.transition(run.run_id, RunState.VALIDATED)

            self.assertEqual(snapshot.configuration["program_configuration_version"], 1)
            self.assertEqual(run.state, RunState.VALIDATED)
            self.assertEqual([event["action"] for event in audit_repository.for_run(run.run_id)], ["RUN_CREATED", "RUN_SETUP_FROZEN", "RUN_STATE_CHANGED"])
