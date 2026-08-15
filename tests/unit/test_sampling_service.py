from __future__ import annotations

import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

from operations_allocation.domain.exceptions import InvalidStateTransitionError, SamplingConfigurationError
from operations_allocation.domain.models import RunState
from operations_allocation.persistence.database import Database
from operations_allocation.persistence.repositories import (
    AuditRepository,
    EligiblePopulationRepository,
    ManifestRepository,
    ProgramRepository,
    RunRepository,
    SamplingResultRepository,
    SnapshotRepository,
)
from operations_allocation.services.audit import AuditService
from operations_allocation.services.eligible_population import EligiblePopulationService
from operations_allocation.services.program_configuration import ProgramConfigurationService
from operations_allocation.services.run_orchestration import RunOrchestrationService
from operations_allocation.services.sampling import SamplingService
from tests.unit.test_foundation import valid_config


class SamplingServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        database = Database(Path(self.tempdir.name) / "sampling.db")
        database.initialize_schema()
        programs = ProgramRepository(database)
        self.runs = RunRepository(database)
        self.snapshots = SnapshotRepository(database)
        self.populations = EligiblePopulationRepository(database)
        self.sampling_results = SamplingResultRepository(database)
        self.audit_repository = AuditRepository(database)
        audit = AuditService(self.audit_repository, "Test Application")
        ProgramConfigurationService(programs).create_program("MX-PT", "MX PT")
        ProgramConfigurationService(programs).save_version(valid_config())
        self.orchestration = RunOrchestrationService(runs=self.runs, snapshots=self.snapshots, manifests=ManifestRepository(database), audit=audit)
        self.eligible_population_service = EligiblePopulationService(runs=self.runs, snapshots=self.snapshots, populations=self.populations, audit=audit)
        self.sampling_service = SamplingService(runs=self.runs, snapshots=self.snapshots, populations=self.populations, sampling_results=self.sampling_results, audit=audit)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _run_through_frozen_population(self, *, sampling: dict, random_seed: str | None, rows: list[dict], due_date: str | None = None) -> str:
        run = self.orchestration.create_run(program_id="MX-PT", created_by="user", created_on=date(2026, 8, 15))
        self.orchestration.freeze_setup(run_id=run.run_id, program_configuration=valid_config(), sampling=sampling, random_seed=random_seed, associates=[], due_date=due_date)
        self.eligible_population_service.validate(run_id=run.run_id, rows=rows)
        self.eligible_population_service.freeze(run_id=run.run_id, rows=rows)
        return run.run_id

    def test_sample_advances_state_and_persists_result(self) -> None:
        rows = [{"product_id": f"A{i}"} for i in range(1, 21)]
        run_id = self._run_through_frozen_population(sampling={"method": "count", "value": 5}, random_seed="seed-42", rows=rows)
        result = self.sampling_service.sample(run_id=run_id)
        self.assertEqual(result.actual_sample_count, 5)
        self.assertEqual(len(result.selected_identifiers), 5)
        self.assertEqual(self.runs.get(run_id).state, RunState.SAMPLED)
        stored = self.sampling_results.get(run_id)
        self.assertEqual(stored.selected_identifiers, result.selected_identifiers)
        actions = [event["action"] for event in self.audit_repository.for_run(run_id)]
        self.assertIn("RUN_SAMPLED", actions)

    def test_sample_requires_sampled_transition_from_frozen_population(self) -> None:
        run = self.orchestration.create_run(program_id="MX-PT", created_by="user", created_on=date(2026, 8, 15))
        self.orchestration.freeze_setup(run_id=run.run_id, program_configuration=valid_config(), sampling={"method": "count", "value": 1}, random_seed="seed", associates=[])
        with self.assertRaises(InvalidStateTransitionError):
            self.sampling_service.sample(run_id=run.run_id)

    def test_sample_requires_seed_present_in_snapshot(self) -> None:
        rows = [{"product_id": "A1"}, {"product_id": "A2"}]
        run_id = self._run_through_frozen_population(sampling={"method": "count", "value": 1}, random_seed=None, rows=rows)
        with self.assertRaises(SamplingConfigurationError):
            self.sampling_service.sample(run_id=run_id)

    def test_percentage_sampling_uses_half_up_rounding_end_to_end(self) -> None:
        rows = [{"product_id": f"A{i}"} for i in range(1, 101)]
        run_id = self._run_through_frozen_population(sampling={"method": "percentage", "value": "3"}, random_seed="seed-7", rows=rows)
        result = self.sampling_service.sample(run_id=run_id)
        self.assertEqual(Decimal(result.calculated_sample_count), Decimal("3"))
        self.assertEqual(result.actual_sample_count, 3)

    def test_sampling_result_table_is_append_only(self) -> None:
        from operations_allocation.domain.exceptions import PersistenceError
        rows = [{"product_id": "A1"}, {"product_id": "A2"}]
        run_id = self._run_through_frozen_population(sampling={"method": "count", "value": 1}, random_seed="seed", rows=rows)
        self.sampling_service.sample(run_id=run_id)
        with self.assertRaises(PersistenceError):
            with self.sampling_results.database.transaction() as connection:
                connection.execute("UPDATE sampling_results SET random_seed = 'x' WHERE run_id = ?", (run_id,))
        with self.assertRaises(PersistenceError):
            with self.sampling_results.database.transaction() as connection:
                connection.execute("DELETE FROM sampling_results WHERE run_id = ?", (run_id,))

    def test_reproducible_given_same_snapshot_and_population(self) -> None:
        # Distinguishing due_date avoids an unrelated pre-existing collision:
        # run_configuration_snapshots.sha256 is globally UNIQUE and the
        # canonical payload does not include run_id, so two runs with a
        # byte-identical setup cannot both freeze successfully today.
        rows = [{"product_id": f"A{i}"} for i in range(1, 21)]
        run_id_one = self._run_through_frozen_population(sampling={"method": "count", "value": 5}, random_seed="fixed-seed", rows=rows, due_date="2026-09-01")
        run_id_two = self._run_through_frozen_population(sampling={"method": "count", "value": 5}, random_seed="fixed-seed", rows=rows, due_date="2026-09-02")
        result_one = self.sampling_service.sample(run_id=run_id_one)
        result_two = self.sampling_service.sample(run_id=run_id_two)
        self.assertEqual(result_one.selected_identifiers, result_two.selected_identifiers)
