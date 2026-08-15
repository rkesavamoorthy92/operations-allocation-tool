from __future__ import annotations

import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

from operations_allocation.domain.exceptions import InvalidResolutionError, UnresolvedDuplicatesError, ValidationBlockedError
from operations_allocation.domain.models import DuplicateResolution, RunState
from operations_allocation.persistence.database import Database
from operations_allocation.persistence.repositories import AuditRepository, EligiblePopulationRepository, ManifestRepository, ProgramRepository, RunRepository, SnapshotRepository
from operations_allocation.services.audit import AuditService
from operations_allocation.services.eligible_population import EligiblePopulationService
from operations_allocation.services.program_configuration import ProgramConfigurationService
from operations_allocation.services.run_orchestration import RunOrchestrationService
from tests.unit.test_foundation import valid_config


class EligiblePopulationServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        database = Database(Path(self.tempdir.name) / "eligible.db")
        database.initialize_schema()
        programs = ProgramRepository(database)
        self.runs = RunRepository(database)
        self.snapshots = SnapshotRepository(database)
        self.populations = EligiblePopulationRepository(database)
        self.audit_repository = AuditRepository(database)
        audit = AuditService(self.audit_repository, "Test Application")
        ProgramConfigurationService(programs).create_program("MX-PT", "MX PT")
        ProgramConfigurationService(programs).save_version(valid_config())
        self.orchestration = RunOrchestrationService(runs=self.runs, snapshots=self.snapshots, manifests=ManifestRepository(database), audit=audit)
        self.service = EligiblePopulationService(runs=self.runs, snapshots=self.snapshots, populations=self.populations, audit=audit)
        run = self.orchestration.create_run(program_id="MX-PT", created_by="user", created_on=date(2026, 8, 15))
        self.orchestration.freeze_setup(run_id=run.run_id, program_configuration=valid_config(), sampling={}, random_seed=None, associates=[])
        self.run_id = run.run_id

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _resolution(self, normalized: str, originals: tuple[str, ...], rows: tuple[int, ...], action: str = "EXCLUDE_ALL", kept_row_index: int | None = None) -> DuplicateResolution:
        return DuplicateResolution(
            normalized_identifier=normalized,
            original_values=originals,
            row_indexes=rows,
            action=action,
            resolved_by="qa_lead",
            resolved_at=datetime.now(timezone.utc),
            reason="Confirmed source duplicate.",
            kept_row_index=kept_row_index,
        )

    def test_validate_advances_state_and_records_audit(self) -> None:
        rows = [{"product_id": "A1"}, {"product_id": "A2"}]
        summary = self.service.validate(run_id=self.run_id, rows=rows)
        self.assertFalse(summary.has_blocking_issues)
        self.assertEqual(self.runs.get(self.run_id).state, RunState.VALIDATED)
        actions = [event["action"] for event in self.audit_repository.for_run(self.run_id)]
        self.assertIn("RUN_VALIDATED", actions)

    def test_validate_blocks_on_structural_failure(self) -> None:
        with self.assertRaises(ValidationBlockedError):
            self.service.validate(run_id=self.run_id, rows=[])
        self.assertEqual(self.runs.get(self.run_id).state, RunState.SNAPSHOT_FROZEN)

    def test_freeze_requires_validated_state(self) -> None:
        rows = [{"product_id": "A1"}]
        from operations_allocation.domain.exceptions import InvalidStateTransitionError
        with self.assertRaises(InvalidStateTransitionError):
            self.service.freeze(run_id=self.run_id, rows=rows)

    def test_freeze_without_duplicates(self) -> None:
        rows = [{"product_id": "A1"}, {"product_id": "A2"}]
        self.service.validate(run_id=self.run_id, rows=rows)
        population = self.service.freeze(run_id=self.run_id, rows=rows)
        self.assertEqual(population.member_identifiers, ("A1", "A2"))
        self.assertEqual(population.excluded_row_count, 0)
        self.assertEqual(self.runs.get(self.run_id).state, RunState.ELIGIBLE_POPULATION_FROZEN)
        stored = self.populations.get(self.run_id)
        self.assertEqual(stored.fingerprint, population.fingerprint)

    def test_freeze_blocks_on_unresolved_duplicates(self) -> None:
        rows = [{"product_id": "A1"}, {"product_id": "A1"}, {"product_id": "A2"}]
        self.service.validate(run_id=self.run_id, rows=rows)
        with self.assertRaises(UnresolvedDuplicatesError):
            self.service.freeze(run_id=self.run_id, rows=rows)
        self.assertEqual(self.runs.get(self.run_id).state, RunState.VALIDATED)

    def test_freeze_excludes_duplicate_group_when_resolved_exclude_all(self) -> None:
        rows = [{"product_id": "A1"}, {"product_id": "A1"}, {"product_id": "A2"}]
        self.service.validate(run_id=self.run_id, rows=rows)
        resolution = self._resolution("A1", ("A1", "A1"), (0, 1))
        population = self.service.freeze(run_id=self.run_id, rows=rows, resolutions=[resolution])
        self.assertEqual(population.member_identifiers, ("A2",))
        self.assertEqual(population.excluded_row_count, 2)
        self.assertEqual(population.resolutions[0].action, "EXCLUDE_ALL")

    def test_freeze_keeps_row_when_resolved_keep_row(self) -> None:
        rows = [{"product_id": "A1"}, {"product_id": "A1"}, {"product_id": "A2"}]
        self.service.validate(run_id=self.run_id, rows=rows)
        resolution = self._resolution("A1", ("A1", "A1"), (0, 1), action="KEEP_ROW", kept_row_index=0)
        population = self.service.freeze(run_id=self.run_id, rows=rows, resolutions=[resolution])
        self.assertEqual(population.member_identifiers, ("A1", "A2"))
        self.assertEqual(population.excluded_row_count, 1)

    def test_freeze_rejects_resolution_that_does_not_match_detected_rows(self) -> None:
        rows = [{"product_id": "A1"}, {"product_id": "A1"}, {"product_id": "A2"}]
        self.service.validate(run_id=self.run_id, rows=rows)
        bad_resolution = self._resolution("A1", ("A1",), (0,))
        with self.assertRaises(InvalidResolutionError):
            self.service.freeze(run_id=self.run_id, rows=rows, resolutions=[bad_resolution])

    def test_fingerprint_is_deterministic_for_same_membership(self) -> None:
        rows = [{"product_id": "A2"}, {"product_id": "A1"}]
        self.service.validate(run_id=self.run_id, rows=rows)
        population = self.service.freeze(run_id=self.run_id, rows=rows)
        self.assertEqual(population.member_identifiers, ("A1", "A2"))
        from operations_allocation.utils.canonical import sha256_for
        expected = sha256_for({"run_id": self.run_id, "members": ["A1", "A2"]})
        self.assertEqual(population.fingerprint, expected)

    def test_eligible_population_table_is_append_only(self) -> None:
        from operations_allocation.domain.exceptions import PersistenceError
        rows = [{"product_id": "A1"}]
        self.service.validate(run_id=self.run_id, rows=rows)
        self.service.freeze(run_id=self.run_id, rows=rows)
        with self.assertRaises(PersistenceError):
            with self.populations.database.transaction() as connection:
                connection.execute("UPDATE eligible_populations SET fingerprint = 'x' WHERE run_id = ?", (self.run_id,))
        with self.assertRaises(PersistenceError):
            with self.populations.database.transaction() as connection:
                connection.execute("DELETE FROM eligible_populations WHERE run_id = ?", (self.run_id,))

    def test_invalid_duplicate_resolution_construction(self) -> None:
        base = dict(original_values=("A1",), row_indexes=(0,), resolved_by="qa", resolved_at=datetime.now(timezone.utc), reason="dup")
        with self.assertRaises(InvalidResolutionError):
            DuplicateResolution(normalized_identifier="", action="EXCLUDE_ALL", **base)
        with self.assertRaises(InvalidResolutionError):
            DuplicateResolution(normalized_identifier="A1", action="MERGE", **base)
        with self.assertRaises(InvalidResolutionError):
            DuplicateResolution(normalized_identifier="A1", action="KEEP_ROW", kept_row_index=99, **base)
        with self.assertRaises(InvalidResolutionError):
            DuplicateResolution(normalized_identifier="A1", action="EXCLUDE_ALL", original_values=("A1",), row_indexes=(0,), resolved_by="", resolved_at=datetime.now(timezone.utc), reason="dup")
