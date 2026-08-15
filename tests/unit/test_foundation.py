from __future__ import annotations

import copy
import tempfile
import threading
import unittest
from datetime import date
from pathlib import Path

from operations_allocation.config.program_config import validate_program_configuration
from operations_allocation.domain.exceptions import InvalidAssociateConfigurationError, InvalidConfigurationError, InvalidStateTransitionError, ManifestIntegrityError, PersistenceError
from operations_allocation.domain.models import Associate, RunState
from operations_allocation.domain.state_machine import ensure_transition
from operations_allocation.persistence.database import Database
from operations_allocation.persistence.repositories import AssociateRepository, AuditRepository, ManifestRepository, ProgramRepository, RunRepository, SnapshotRepository
from operations_allocation.services.audit import AuditService
from operations_allocation.services.program_configuration import ProgramConfigurationService
from operations_allocation.services.run_orchestration import RunOrchestrationService
from operations_allocation.utils.canonical import canonical_json, sha256_for


def valid_config(version: int = 1) -> dict:
    return {
        "program_id": "MX-PT", "program_name": "MX PT", "version": version,
        "primary_identifier": {"field": "product_id", "case_sensitive": True, "normalization": {"trim_whitespace": True}},
        "input_columns": [{"name": "product_id", "column": "Product ID", "ownership": "source", "data_type": "string", "required": True}],
        "response_columns": [{"name": "partner_feedback", "column": "Partner Feedback", "ownership": "response", "data_type": "string", "required": False}],
        "fields": [
            {"name": "product_id", "source_column": "Product ID", "ownership": "source", "data_type": "string", "required": True, "output_order": 0},
            {"name": "allocated_to", "ownership": "system", "data_type": "string", "required": False, "output_order": 1},
        ],
        "validation": {}, "sampling": {"allowed_methods": ["percentage", "count"]},
        "allocation": {"strategy": "target_capacity"}, "tie_breaking": {"field": "associate_id"},
        "qc": {}, "errors": {}, "filename": {"pattern": "{PROGRAM}_{RUN_ID}.xlsx"}, "email": {"templates": {}},
    }


class FailingManifestRepository(ManifestRepository):
    def add(self, manifest, connection=None):
        raise RuntimeError("deliberate manifest failure")


class FailingAuditRepository(AuditRepository):
    def add(self, **kwargs):
        raise RuntimeError("deliberate audit failure")


class FoundationTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        database = Database(Path(self.tempdir.name) / "foundation.db")
        database.initialize_schema()
        self.programs = ProgramRepository(database)
        self.runs = RunRepository(database)
        self.snapshots = SnapshotRepository(database)
        self.audit_repository = AuditRepository(database)
        self.manifests = ManifestRepository(database)
        self.config_service = ProgramConfigurationService(self.programs)
        self.audit = AuditService(self.audit_repository, "Test Application")
        self.service = RunOrchestrationService(runs=self.runs, snapshots=self.snapshots, manifests=self.manifests, audit=self.audit)
        self.config_service.create_program("MX-PT", "MX PT")
        self.config_service.save_version(valid_config())

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_valid_configuration(self) -> None:
        validate_program_configuration(valid_config())

    def test_invalid_configuration_variants(self) -> None:
        missing = valid_config(); del missing["filename"]
        with self.assertRaises(InvalidConfigurationError): validate_program_configuration(missing)
        bad_ownership = valid_config(); bad_ownership["fields"][0]["ownership"] = "external"
        with self.assertRaises(InvalidConfigurationError): validate_program_configuration(bad_ownership)
        bad_type = valid_config(); bad_type["fields"][0]["data_type"] = "spreadsheet"
        with self.assertRaises(InvalidConfigurationError): validate_program_configuration(bad_type)
        bad_version = valid_config(0)
        with self.assertRaises(InvalidConfigurationError): validate_program_configuration(bad_version)
        for key in ("input_columns", "response_columns", "sampling"):
            invalid = valid_config(); invalid[key] = {}
            with self.assertRaises(InvalidConfigurationError): validate_program_configuration(invalid)
        duplicate_order = valid_config(); duplicate_order["fields"][1]["output_order"] = 0
        with self.assertRaises(InvalidConfigurationError): validate_program_configuration(duplicate_order)
        bad_sampling = valid_config(); bad_sampling["sampling"]["method"] = "random"
        with self.assertRaises(InvalidConfigurationError): validate_program_configuration(bad_sampling)
        bad_allocation = valid_config(); bad_allocation["allocation"] = {}
        with self.assertRaises(InvalidConfigurationError): validate_program_configuration(bad_allocation)
        bad_tie_breaking = valid_config(); bad_tie_breaking["tie_breaking"] = {"field": ""}
        with self.assertRaises(InvalidConfigurationError): validate_program_configuration(bad_tie_breaking)
        bad_filename = valid_config(); bad_filename["filename"] = {"pattern": ""}
        with self.assertRaises(InvalidConfigurationError): validate_program_configuration(bad_filename)
        bad_email = valid_config(); bad_email["email"] = {"templates": {"subject": 3}}
        with self.assertRaises(InvalidConfigurationError): validate_program_configuration(bad_email)

    def test_configuration_program_must_exist(self) -> None:
        unknown = valid_config(); unknown["program_id"] = "OTHER"
        with self.assertRaises(PersistenceError): self.config_service.save_version(unknown)

    def test_deterministic_serialization_and_hashing(self) -> None:
        self.assertEqual(canonical_json({"b": 1, "a": {"y": 2, "x": 3}}), canonical_json({"a": {"x": 3, "y": 2}, "b": 1}))
        self.assertEqual(sha256_for({"b": 1, "a": 2}), sha256_for({"a": 2, "b": 1}))

    def test_run_id_sequence_and_daily_reset(self) -> None:
        first = self.service.create_run(program_id="MX-PT", created_by="user", created_on=date(2026, 8, 15))
        second = self.service.create_run(program_id="MX-PT", created_by="user", created_on=date(2026, 8, 15))
        next_day = self.service.create_run(program_id="MX-PT", created_by="user", created_on=date(2026, 8, 16))
        self.assertEqual(first.run_id, "MX-PT-20260815-001")
        self.assertEqual(second.run_id, "MX-PT-20260815-002")
        self.assertEqual(next_day.run_id, "MX-PT-20260816-001")

    def test_concurrent_run_creation_produces_unique_ids(self) -> None:
        run_ids: list[str] = []
        failures: list[Exception] = []

        def create() -> None:
            try:
                run_ids.append(self.service.create_run(program_id="MX-PT", created_by="user", created_on=date(2026, 8, 15)).run_id)
            except Exception as error:  # Test records an unexpected concurrent failure.
                failures.append(error)

        threads = [threading.Thread(target=create) for _ in range(5)]
        for thread in threads: thread.start()
        for thread in threads: thread.join()
        self.assertEqual(failures, [])
        self.assertEqual(sorted(run_ids), [f"MX-PT-20260815-{value:03d}" for value in range(1, 6)])

    def test_state_machine_and_audit(self) -> None:
        run = self.service.create_run(program_id="MX-PT", created_by="user", created_on=date(2026, 8, 15))
        with self.assertRaises(InvalidStateTransitionError):
            self.service.transition(run.run_id, RunState.VALIDATED)
        updated = self.service.transition(run.run_id, RunState.SNAPSHOT_FROZEN)
        self.assertEqual(updated.state, RunState.SNAPSHOT_FROZEN)
        events = self.audit_repository.for_run(run.run_id)
        self.assertEqual([event["action"] for event in events], ["RUN_CREATED", "RUN_STATE_CHANGED"])
        self.assertEqual(events[1]["previous_state"], "DRAFT")

    def test_snapshot_is_immutable_and_retains_original_configuration(self) -> None:
        run = self.service.create_run(program_id="MX-PT", created_by="user", created_on=date(2026, 8, 15))
        configuration = valid_config()
        snapshot = self.service.freeze_setup(run_id=run.run_id, program_configuration=configuration, sampling={"method": "percentage", "value": "3"}, random_seed="42", associates=[{"associate_id": "A001", "active": True, "target": 5, "maximum_capacity": 10, "experience": "new"}])
        configuration["fields"][0]["source_column"] = "Changed"
        frozen = self.snapshots.get(run.run_id)
        self.assertEqual(snapshot.sha256, frozen.sha256)
        self.assertEqual(frozen.configuration["program_configuration"]["fields"][0]["source_column"], "Product ID")
        with self.assertRaises(InvalidStateTransitionError):
            self.service.freeze_setup(run_id=run.run_id, program_configuration=valid_config(), sampling={}, random_seed=None, associates=[])

    def test_database_rejects_snapshot_update_and_delete(self) -> None:
        run = self.service.create_run(program_id="MX-PT", created_by="user", created_on=date(2026, 8, 15))
        snapshot = self.service.freeze_setup(run_id=run.run_id, program_configuration=valid_config(), sampling={}, random_seed=None, associates=[])
        with self.assertRaises(PersistenceError):
            with self.snapshots.database.transaction() as connection:
                connection.execute("UPDATE run_configuration_snapshots SET canonical_json = '{}' WHERE snapshot_id = ?", (snapshot.snapshot_id,))
        with self.assertRaises(PersistenceError):
            with self.snapshots.database.transaction() as connection:
                connection.execute("DELETE FROM run_configuration_snapshots WHERE snapshot_id = ?", (snapshot.snapshot_id,))
        self.assertEqual(self.snapshots.get(run.run_id).sha256, snapshot.sha256)

    def test_database_rejects_audit_update_and_delete(self) -> None:
        run = self.service.create_run(program_id="MX-PT", created_by="user", created_on=date(2026, 8, 15))
        event_id = self.audit_repository.for_run(run.run_id)[0]["audit_id"]
        with self.assertRaises(PersistenceError):
            with self.audit_repository.database.transaction() as connection:
                connection.execute("UPDATE audit_logs SET action = 'CHANGED' WHERE audit_id = ?", (event_id,))
        with self.assertRaises(PersistenceError):
            with self.audit_repository.database.transaction() as connection:
                connection.execute("DELETE FROM audit_logs WHERE audit_id = ?", (event_id,))

    def test_snapshot_freeze_rolls_back_when_manifest_fails(self) -> None:
        run = self.service.create_run(program_id="MX-PT", created_by="user", created_on=date(2026, 8, 15))
        failing = RunOrchestrationService(runs=self.runs, snapshots=self.snapshots, manifests=FailingManifestRepository(self.manifests.database), audit=self.audit)
        with self.assertRaises(RuntimeError):
            failing.freeze_setup(run_id=run.run_id, program_configuration=valid_config(), sampling={}, random_seed=None, associates=[])
        self.assertEqual(self.runs.get(run.run_id).state, RunState.DRAFT)
        with self.assertRaises(PersistenceError): self.snapshots.get(run.run_id)
        with self.assertRaises(PersistenceError): self.manifests.get(run.run_id)
        self.assertEqual(len(self.audit_repository.for_run(run.run_id)), 1)

    def test_snapshot_freeze_rolls_back_when_audit_fails(self) -> None:
        run = self.service.create_run(program_id="MX-PT", created_by="user", created_on=date(2026, 8, 15))
        failing = RunOrchestrationService(runs=self.runs, snapshots=self.snapshots, manifests=self.manifests, audit=AuditService(FailingAuditRepository(self.audit_repository.database)))
        with self.assertRaises(RuntimeError):
            failing.freeze_setup(run_id=run.run_id, program_configuration=valid_config(), sampling={}, random_seed=None, associates=[])
        self.assertEqual(self.runs.get(run.run_id).state, RunState.DRAFT)
        with self.assertRaises(PersistenceError): self.snapshots.get(run.run_id)
        with self.assertRaises(PersistenceError): self.manifests.get(run.run_id)
        self.assertEqual(len(self.audit_repository.for_run(run.run_id)), 1)

    def test_database_rejects_invalid_run_state_and_invalid_snapshot_reference(self) -> None:
        run = self.service.create_run(program_id="MX-PT", created_by="user", created_on=date(2026, 8, 15))
        with self.assertRaises(PersistenceError):
            with self.runs.database.transaction() as connection:
                connection.execute("UPDATE runs SET state = 'INVALID' WHERE run_id = ?", (run.run_id,))
        with self.assertRaises(PersistenceError):
            with self.runs.database.transaction() as connection:
                connection.execute("UPDATE runs SET snapshot_id = 999999 WHERE run_id = ?", (run.run_id,))
        with self.assertRaises(InvalidStateTransitionError): self.service.transition(run.run_id, RunState.VALIDATED)

    def test_run_snapshot_foreign_key_and_lifecycle_integrity(self) -> None:
        run = self.service.create_run(program_id="MX-PT", created_by="user", created_on=date(2026, 8, 15))
        snapshot = self.service.freeze_setup(run_id=run.run_id, program_configuration=valid_config(), sampling={}, random_seed=None, associates=[])
        self.assertEqual(self.runs.get(run.run_id).snapshot_id, snapshot.snapshot_id)
        with self.assertRaises(PersistenceError):
            with self.snapshots.database.transaction() as connection:
                connection.execute("DELETE FROM run_configuration_snapshots WHERE snapshot_id = ?", (snapshot.snapshot_id,))
        other_run = self.service.create_run(program_id="MX-PT", created_by="user", created_on=date(2026, 8, 15))
        with self.assertRaises(PersistenceError):
            with self.runs.database.transaction() as connection:
                connection.execute("UPDATE runs SET snapshot_id = ? WHERE run_id = ?", (snapshot.snapshot_id, other_run.run_id))

    def test_manifest_round_trip_and_hash_verification(self) -> None:
        run = self.service.create_run(program_id="MX-PT", created_by="user", created_on=date(2026, 8, 15))
        snapshot = self.service.freeze_setup(run_id=run.run_id, program_configuration=valid_config(), sampling={}, random_seed=None, associates=[])
        manifest = self.manifests.get(run.run_id)
        self.assertEqual(manifest.configuration_snapshot_hash, snapshot.sha256)
        self.assertTrue(self.manifests.verify_snapshot_hash(run.run_id))
        self.assertEqual(self.manifests.associated_snapshot(run.run_id).sha256, snapshot.sha256)
        with self.assertRaises(ManifestIntegrityError):
            self.manifests.add(type(manifest)(run_id="MX-PT-20260815-999", configuration_snapshot_hash="wrong"))
        with self.manifests.database.transaction() as connection:
            connection.execute("UPDATE execution_manifests SET configuration_snapshot_hash = 'wrong' WHERE run_id = ?", (run.run_id,))
        with self.assertRaises(ManifestIntegrityError): self.manifests.verify_snapshot_hash(run.run_id)

    def test_run_id_ledger_prevents_reuse_after_run_deletion(self) -> None:
        first = self.runs.create_next("MX-PT", "user", None, date(2026, 8, 15))
        self.runs.delete_for_test(first.run_id)
        second = self.runs.create_next("MX-PT", "user", None, date(2026, 8, 15))
        self.assertEqual(first.run_id, "MX-PT-20260815-001")
        self.assertEqual(second.run_id, "MX-PT-20260815-002")

    def test_schema_version_is_deterministic(self) -> None:
        self.assertEqual(self.runs.database.schema_version(), 2)

    def test_associate_master_and_invalid_snapshot_capacity(self) -> None:
        AssociateRepository(self.programs.database).add(Associate("A001", "Associate", "a@example.test", False, default_target=5, default_maximum_capacity=8))
        run = self.service.create_run(program_id="MX-PT", created_by="user", created_on=date(2026, 8, 15))
        with self.assertRaises(InvalidAssociateConfigurationError):
                self.service.freeze_setup(run_id=run.run_id, program_configuration=valid_config(), sampling={}, random_seed=None, associates=[{"associate_id": "A001", "active": False, "target": 8, "maximum_capacity": 4}])

    def test_associate_master_validation_and_immutable_objects(self) -> None:
        with self.assertRaises(InvalidAssociateConfigurationError): Associate("", "Name", "", True)
        with self.assertRaises(InvalidAssociateConfigurationError): Associate("A", "", "", True)
        with self.assertRaises(InvalidAssociateConfigurationError): Associate("A", "Name", "invalid", True)
        with self.assertRaises(InvalidAssociateConfigurationError): Associate("A", "Name", "", True, default_target=5, default_maximum_capacity=4)
        run = self.service.create_run(program_id="MX-PT", created_by="user", created_on=date(2026, 8, 15))
        snapshot = self.service.freeze_setup(run_id=run.run_id, program_configuration=valid_config(), sampling={}, random_seed=None, associates=[])
        with self.assertRaises(TypeError): snapshot.configuration["new"] = "value"
        manifest = self.manifests.get(run.run_id)
        with self.assertRaises(TypeError): manifest.output_artifact_hashes["artifact"] = "hash"

    def test_database_foreign_key_and_transaction_rollback(self) -> None:
        with self.assertRaises(Exception):
            self.service.create_run(program_id="UNKNOWN", created_by="user", created_on=date(2026, 8, 15))
        with self.assertRaises(Exception):
            self.programs.add(self.config_service.create_program("MX-PT", "Duplicate"))
        # The failed duplicate insert did not alter the original Program row/configuration.
        self.assertEqual(self.programs.configuration("MX-PT", 1)["program_name"], "MX PT")


class StateMachineTestCase(unittest.TestCase):
    def test_failure_allowed_from_nonterminal_and_terminal_is_final(self) -> None:
        ensure_transition(RunState.VALIDATED, RunState.FAILED)
        with self.assertRaises(InvalidStateTransitionError): ensure_transition(RunState.COMPLETED, RunState.FAILED)
