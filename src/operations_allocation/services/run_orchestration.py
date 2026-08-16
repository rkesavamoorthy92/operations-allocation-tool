"""Run creation, immutable setup freezing, state changes, and manifest creation."""

from __future__ import annotations

from datetime import date
import re
from typing import Any

from operations_allocation.config.program_config import validate_program_configuration
from operations_allocation.domain.exceptions import InvalidAssociateConfigurationError, InvalidConfigurationError, PersistenceError, SnapshotCreationError
from operations_allocation.domain.models import ExecutionManifest, Run, RunState
from operations_allocation.domain.state_machine import ensure_transition
from operations_allocation.utils.canonical import CANONICAL_JSON_VERSION, canonical_json, sha256_for


class RunOrchestrationService:
    def __init__(self, *, runs: Any, snapshots: Any, manifests: Any, audit: Any) -> None:
        self.runs, self.snapshots, self.manifests, self.audit = runs, snapshots, manifests, audit

    def create_run(self, *, program_id: str, created_by: str, due_date: date | None = None, created_on: date | None = None) -> Run:
        if not re.fullmatch(r"[A-Z0-9]+(?:-[A-Z0-9]+)*", program_id):
            raise InvalidConfigurationError("Program ID must use uppercase letters, digits, and internal hyphens only.")
        run = self.runs.create_next(program_id, created_by, due_date, created_on or date.today())
        self.audit.record(run_id=run.run_id, program_id=run.program_id, action="RUN_CREATED", new_state=RunState.DRAFT)
        return run

    def freeze_setup(self, *, run_id: str, program_configuration: dict[str, Any], sampling: dict[str, Any], random_seed: str | None, associates: list[dict[str, Any]], due_date: str | None = None) -> Any:
        run = self.runs.get(run_id)
        ensure_transition(run.state, RunState.SNAPSHOT_FROZEN)
        validate_program_configuration(program_configuration)
        if run.program_id != program_configuration["program_id"]:
            raise InvalidConfigurationError("Run program does not match the supplied program configuration.")
        _validate_snapshot_associates(associates)
        snapshot_data = {"run_id": run_id, "program_configuration_version": program_configuration["version"], "program_configuration": program_configuration, "column_mappings": {field["name"]: field.get("source_column") for field in program_configuration["fields"]}, "sampling": sampling, "random_seed": random_seed, "associates": associates, "qc_rules": program_configuration["qc"], "error_rules": program_configuration["errors"], "email_configuration": program_configuration["email"], "due_date": due_date if due_date is not None else (run.due_date.isoformat() if run.due_date else None), "allocation_strategy": program_configuration["allocation"], "tie_breaking": program_configuration["tie_breaking"]}
        with self.runs.database.transaction() as connection:
            try:
                snapshot = self.snapshots.add(run_id, program_configuration["version"], CANONICAL_JSON_VERSION, canonical_json(snapshot_data), sha256_for(snapshot_data), connection=connection)
            except PersistenceError as error:
                raise SnapshotCreationError("Run configuration snapshot could not be created.") from error
            self.runs.update_state(run_id, RunState.SNAPSHOT_FROZEN, connection=connection)
            self.manifests.add(ExecutionManifest(run_id=run_id, configuration_snapshot_hash=snapshot.sha256), connection=connection)
            self.audit.record(run_id=run_id, program_id=run.program_id, action="RUN_SETUP_FROZEN", previous_state=RunState.DRAFT, new_state=RunState.SNAPSHOT_FROZEN, metadata={"snapshot_hash": snapshot.sha256}, connection=connection)
        return snapshot

    def transition(self, run_id: str, target: RunState) -> Run:
        run = self.runs.get(run_id)
        ensure_transition(run.state, target)
        self.runs.update_state(run_id, target)
        self.audit.record(run_id=run_id, program_id=run.program_id, action="RUN_STATE_CHANGED", previous_state=run.state, new_state=target)
        return self.runs.get(run_id)

    def archive(self, run_id: str) -> None:
        """Soft-delete: hides the Run from the Dashboard's default view.
        The Run row, its snapshot, and every artifact/audit record stay on
        disk untouched -- restore() reverses this instantly. Allowed from
        any RunState; archiving is a visibility choice, not a lifecycle
        transition, so it deliberately does not go through ensure_transition.
        """
        run = self.runs.get(run_id)
        self.runs.archive(run_id)
        self.audit.record(run_id=run_id, program_id=run.program_id, action="RUN_ARCHIVED", previous_state=run.state, new_state=run.state)

    def restore(self, run_id: str) -> None:
        run = self.runs.get(run_id)
        self.runs.restore(run_id)
        self.audit.record(run_id=run_id, program_id=run.program_id, action="RUN_RESTORED", previous_state=run.state, new_state=run.state)


def _validate_snapshot_associates(associates: list[dict[str, Any]]) -> None:
    ids: set[str] = set()
    for associate in associates:
        identifier = associate.get("associate_id")
        if not isinstance(identifier, str) or not identifier.strip() or identifier in ids:
            raise InvalidAssociateConfigurationError("Snapshot associates require unique non-empty associate IDs.")
        ids.add(identifier)
        name = associate.get("name")
        if not isinstance(name, str) or not name.strip():
            raise InvalidAssociateConfigurationError(f"Associate '{identifier}' requires a non-empty name.")
        email = associate.get("email")
        if not isinstance(email, str) or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            raise InvalidAssociateConfigurationError(f"Associate '{identifier}' requires a valid email address.")
        for field in ("target", "maximum_capacity"):
            value = associate.get(field)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise InvalidAssociateConfigurationError(f"Associate '{identifier}' {field} must be a non-negative integer.")
        if associate["target"] > associate["maximum_capacity"]:
            raise InvalidAssociateConfigurationError(f"Associate '{identifier}' target cannot exceed maximum capacity.")
        if not isinstance(associate.get("active"), bool):
            raise InvalidAssociateConfigurationError(f"Associate '{identifier}' active must be a boolean.")
