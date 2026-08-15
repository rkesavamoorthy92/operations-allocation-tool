from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from operations_allocation.domain.exceptions import AboveTargetConfirmationRequiredError, InsufficientCapacityError, InvalidStateTransitionError, PersistenceError
from operations_allocation.domain.models import RunState
from operations_allocation.persistence.database import Database
from operations_allocation.persistence.repositories import (
    AllocationResultRepository,
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
from operations_allocation.services.eligible_population import EligiblePopulationService
from operations_allocation.services.program_configuration import ProgramConfigurationService
from operations_allocation.services.run_orchestration import RunOrchestrationService
from operations_allocation.services.sampling import SamplingService
from tests.unit.test_foundation import valid_config


class AllocationServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        database = Database(Path(self.tempdir.name) / "allocation.db")
        database.initialize_schema()
        programs = ProgramRepository(database)
        self.runs = RunRepository(database)
        self.snapshots = SnapshotRepository(database)
        self.populations = EligiblePopulationRepository(database)
        self.sampling_results = SamplingResultRepository(database)
        self.allocation_results = AllocationResultRepository(database)
        self.audit_repository = AuditRepository(database)
        audit = AuditService(self.audit_repository, "Test Application")
        ProgramConfigurationService(programs).create_program("MX-PT", "MX PT")
        ProgramConfigurationService(programs).save_version(valid_config())
        self.orchestration = RunOrchestrationService(runs=self.runs, snapshots=self.snapshots, manifests=ManifestRepository(database), audit=audit)
        self.eligible_population_service = EligiblePopulationService(runs=self.runs, snapshots=self.snapshots, populations=self.populations, audit=audit)
        self.sampling_service = SamplingService(runs=self.runs, snapshots=self.snapshots, populations=self.populations, sampling_results=self.sampling_results, audit=audit)
        self.allocation_service = AllocationService(runs=self.runs, snapshots=self.snapshots, sampling_results=self.sampling_results, allocation_results=self.allocation_results, audit=audit)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _run_through_sampled(self, *, associates: list, sample_count: int, row_count: int = 20) -> str:
        run = self.orchestration.create_run(program_id="MX-PT", created_by="user", created_on=date(2026, 8, 15))
        self.orchestration.freeze_setup(run_id=run.run_id, program_configuration=valid_config(), sampling={"method": "count", "value": sample_count}, random_seed="seed", associates=associates)
        rows = [{"product_id": f"A{i}"} for i in range(1, row_count + 1)]
        self.eligible_population_service.validate(run_id=run.run_id, rows=rows)
        self.eligible_population_service.freeze(run_id=run.run_id, rows=rows)
        self.sampling_service.sample(run_id=run.run_id)
        return run.run_id

    def test_finalize_advances_state_and_persists_result(self) -> None:
        associates = [
            {"associate_id": "A", "active": True, "target": 10, "maximum_capacity": 10},
            {"associate_id": "B", "active": True, "target": 10, "maximum_capacity": 10},
        ]
        run_id = self._run_through_sampled(associates=associates, sample_count=15)
        result = self.allocation_service.finalize(run_id=run_id)
        self.assertEqual(self.runs.get(run_id).state, RunState.ALLOCATED)
        self.assertEqual(sum(a.planned_count for a in result.assignments), 15)
        stored = self.allocation_results.get(run_id)
        self.assertEqual(stored.assignments, result.assignments)
        actions = [event["action"] for event in self.audit_repository.for_run(run_id)]
        self.assertIn("RUN_ALLOCATED", actions)

    def test_finalize_blocked_by_insufficient_capacity(self) -> None:
        associates = [{"associate_id": "A", "active": True, "target": 5, "maximum_capacity": 5}]
        run_id = self._run_through_sampled(associates=associates, sample_count=10)
        with self.assertRaises(InsufficientCapacityError):
            self.allocation_service.finalize(run_id=run_id)
        self.assertEqual(self.runs.get(run_id).state, RunState.SAMPLED)

    def test_finalize_requires_confirmation_above_target(self) -> None:
        associates = [{"associate_id": "A", "active": True, "target": 5, "maximum_capacity": 20}]
        run_id = self._run_through_sampled(associates=associates, sample_count=10)
        with self.assertRaises(AboveTargetConfirmationRequiredError):
            self.allocation_service.finalize(run_id=run_id)
        result = self.allocation_service.finalize(run_id=run_id, confirm_above_target=True, confirmed_by="qa_lead")
        self.assertTrue(result.confirmed_above_target)
        self.assertEqual(result.confirmed_by, "qa_lead")

    def test_finalize_requires_sampled_state(self) -> None:
        run = self.orchestration.create_run(program_id="MX-PT", created_by="user", created_on=date(2026, 8, 15))
        self.orchestration.freeze_setup(run_id=run.run_id, program_configuration=valid_config(), sampling={"method": "count", "value": 1}, random_seed="seed", associates=[])
        with self.assertRaises(InvalidStateTransitionError):
            self.allocation_service.finalize(run_id=run.run_id)

    def test_preview_does_not_change_state_or_persist(self) -> None:
        associates = [{"associate_id": "A", "active": True, "target": 10, "maximum_capacity": 10}]
        run_id = self._run_through_sampled(associates=associates, sample_count=8)
        plan = self.allocation_service.preview(run_id=run_id)
        self.assertFalse(plan.blocked)
        self.assertEqual(self.runs.get(run_id).state, RunState.SAMPLED)
        with self.assertRaises(PersistenceError):
            self.allocation_results.get(run_id)

    def test_allocation_result_table_is_append_only(self) -> None:
        associates = [{"associate_id": "A", "active": True, "target": 10, "maximum_capacity": 10}]
        run_id = self._run_through_sampled(associates=associates, sample_count=8)
        self.allocation_service.finalize(run_id=run_id)
        with self.assertRaises(PersistenceError):
            with self.allocation_results.database.transaction() as connection:
                connection.execute("UPDATE allocation_results SET confirmed_by = 'x' WHERE run_id = ?", (run_id,))
        with self.assertRaises(PersistenceError):
            with self.allocation_results.database.transaction() as connection:
                connection.execute("DELETE FROM allocation_results WHERE run_id = ?", (run_id,))

    def test_inactive_associates_excluded_end_to_end(self) -> None:
        associates = [
            {"associate_id": "A", "active": True, "target": 10, "maximum_capacity": 10},
            {"associate_id": "B", "active": False, "target": 100, "maximum_capacity": 100},
        ]
        run_id = self._run_through_sampled(associates=associates, sample_count=8)
        result = self.allocation_service.finalize(run_id=run_id)
        self.assertEqual(len(result.assignments), 1)
        self.assertEqual(result.assignments[0].associate_id, "A")
