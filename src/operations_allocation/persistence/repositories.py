"""Repository boundary for all Phase 1 SQLite access."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timezone
from collections.abc import Iterator
from typing import Any

from operations_allocation.domain.exceptions import DuplicateRunIdError, InvalidRunStateError, ManifestIntegrityError, PersistenceError
from operations_allocation.domain.models import Associate, AllocationAssignment, AllocationResult, Artifact, ArtifactType, DuplicateResolution, EligiblePopulation, ExecutionManifest, Program, Run, RunConfigurationSnapshot, RunState, SamplingResult
from operations_allocation.domain.state_machine import ensure_transition
from operations_allocation.utils.canonical import deep_thaw


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run_from_row(row: sqlite3.Row) -> Run:
    return Run(
        row["run_id"], row["program_id"], row["created_by"], datetime.fromisoformat(row["created_at"]),
        RunState(row["state"]), date.fromisoformat(row["due_date"]) if row["due_date"] else None,
        row["snapshot_id"], datetime.fromisoformat(row["archived_at"]) if row["archived_at"] else None,
    )


@contextmanager
def _write_scope(database: Any, connection: sqlite3.Connection | None) -> Iterator[sqlite3.Connection]:
    if connection is not None:
        yield connection
    else:
        with database.transaction() as managed_connection:
            yield managed_connection


@contextmanager
def _read_scope(database: Any) -> Iterator[sqlite3.Connection]:
    with database.read_transaction() as connection:
        yield connection


class ProgramRepository:
    def __init__(self, database: Any) -> None:
        self.database = database

    def add(self, program: Program) -> None:
        try:
            with _write_scope(self.database, None) as conn:
                conn.execute("INSERT INTO programs VALUES (?, ?, ?, ?, ?)", (program.program_id, program.name, program.active_configuration_version, int(program.active), _now()))
        except PersistenceError:
            raise

    def save_configuration(self, program_id: str, version: int, configuration_json: str, configuration_hash: str) -> None:
        try:
            with self.database.transaction() as conn:
                conn.execute("INSERT INTO program_configurations VALUES (?, ?, ?, ?, ?)", (program_id, version, configuration_json, configuration_hash, _now()))
                conn.execute("UPDATE programs SET active_configuration_version = ? WHERE program_id = ?", (version, program_id))
        except PersistenceError:
            raise

    def configuration(self, program_id: str, version: int) -> dict[str, Any]:
        try:
            with _read_scope(self.database) as conn:
                row = conn.execute("SELECT configuration_json FROM program_configurations WHERE program_id = ? AND version = ?", (program_id, version)).fetchone()
                if row is None:
                    raise PersistenceError("Program configuration could not be found.")
                return json.loads(row["configuration_json"])
        except PersistenceError:
            raise

    def get(self, program_id: str) -> Program:
        with _read_scope(self.database) as conn:
            row = conn.execute("SELECT * FROM programs WHERE program_id = ?", (program_id,)).fetchone()
            if row is None:
                raise PersistenceError(f"Program '{program_id}' could not be found.")
            return Program(row["program_id"], row["name"], row["active_configuration_version"], bool(row["active"]))

    def list_all(self, *, include_archived: bool = False) -> tuple[Program, ...]:
        query = "SELECT * FROM programs" if include_archived else "SELECT * FROM programs WHERE active = 1"
        with _read_scope(self.database) as conn:
            rows = conn.execute(f"{query} ORDER BY program_id").fetchall()
            return tuple(Program(row["program_id"], row["name"], row["active_configuration_version"], bool(row["active"])) for row in rows)

    def set_active(self, program_id: str, active: bool) -> None:
        with _write_scope(self.database, None) as conn:
            cursor = conn.execute("UPDATE programs SET active = ? WHERE program_id = ?", (int(active), program_id))
            if cursor.rowcount == 0:
                raise PersistenceError(f"Program '{program_id}' could not be found.")


class AssociateRepository:
    def __init__(self, database: Any) -> None:
        self.database = database

    def add(self, associate: Associate) -> None:
        timestamp = _now()
        try:
            with _write_scope(self.database, None) as conn:
                conn.execute("INSERT INTO associates VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (associate.associate_id, associate.name, associate.email, int(associate.active), associate.team_or_program, associate.experience, associate.default_target, associate.default_maximum_capacity, timestamp, timestamp))
        except PersistenceError:
            raise


class RunRepository:
    def __init__(self, database: Any) -> None:
        self.database = database

    def create_next(self, program_id: str, created_by: str, due_date: date | None, on_date: date) -> Run:
        """Allocate, ledger, and persist an ID in one IMMEDIATE transaction."""
        prefix = f"{program_id}-{on_date:%Y%m%d}-"
        created_at = datetime.now(timezone.utc)
        try:
            with self.database.transaction() as conn:
                row = conn.execute("SELECT next_sequence FROM run_id_sequences WHERE program_id = ? AND run_date = ?", (program_id, on_date.isoformat())).fetchone()
                sequence = int(row["next_sequence"]) if row else 1
                if row is None:
                    conn.execute("INSERT INTO run_id_sequences (program_id, run_date, next_sequence) VALUES (?, ?, ?)", (program_id, on_date.isoformat(), 2))
                else:
                    conn.execute("UPDATE run_id_sequences SET next_sequence = ? WHERE program_id = ? AND run_date = ?", (sequence + 1, program_id, on_date.isoformat()))
                run_id = f"{prefix}{sequence:03d}"
                conn.execute("INSERT INTO run_id_ledger (run_id, program_id, run_date, sequence, issued_at) VALUES (?, ?, ?, ?, ?)", (run_id, program_id, on_date.isoformat(), sequence, created_at.isoformat()))
                conn.execute("INSERT INTO runs (run_id, program_id, created_by, created_at, state, due_date) VALUES (?, ?, ?, ?, ?, ?)", (run_id, program_id, created_by, created_at.isoformat(), RunState.DRAFT.value, due_date.isoformat() if due_date else None))
        except PersistenceError as error:
            if "FOREIGN KEY constraint failed" in str(error.__cause__):
                raise PersistenceError(f"Program '{program_id}' could not be found.") from error
            raise
        return Run(run_id, program_id, created_by, created_at, RunState.DRAFT, due_date)

    def add(self, run: Run) -> None:
        try:
            with self.database.transaction() as conn:
                run_date, sequence = _run_date_and_sequence(run.run_id)
                program_id = run.run_id.rsplit("-", 2)[0]
                conn.execute("INSERT INTO run_id_ledger (run_id, program_id, run_date, sequence, issued_at) VALUES (?, ?, ?, ?, ?)", (run.run_id, program_id, run_date, sequence, run.created_at.isoformat()))
                conn.execute("INSERT INTO run_id_sequences (program_id, run_date, next_sequence) VALUES (?, ?, ?) ON CONFLICT(program_id, run_date) DO UPDATE SET next_sequence = MAX(next_sequence, excluded.next_sequence)", (program_id, run_date, sequence + 1))
                conn.execute("INSERT INTO runs (run_id, program_id, created_by, created_at, state, due_date) VALUES (?, ?, ?, ?, ?, ?)", (run.run_id, run.program_id, run.created_by, run.created_at.isoformat(), run.state.value, run.due_date.isoformat() if run.due_date else None))
        except PersistenceError as error:
            if any(marker in str(error.__cause__) for marker in ("UNIQUE constraint failed: runs.run_id", "UNIQUE constraint failed: run_id_ledger.run_id")):
                raise DuplicateRunIdError(f"Run ID '{run.run_id}' already exists.") from error
            raise

    def get(self, run_id: str) -> Run:
        with _read_scope(self.database) as conn:
            row = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
            if row is None:
                raise PersistenceError(f"Run '{run_id}' could not be found.")
            return _run_from_row(row)

    def list_all(self, *, include_archived: bool = False) -> tuple[Run, ...]:
        query = "SELECT * FROM runs" if include_archived else "SELECT * FROM runs WHERE archived_at IS NULL"
        with _read_scope(self.database) as conn:
            rows = conn.execute(f"{query} ORDER BY created_at DESC").fetchall()
            return tuple(_run_from_row(row) for row in rows)

    def archive(self, run_id: str) -> None:
        with _write_scope(self.database, None) as conn:
            cursor = conn.execute("UPDATE runs SET archived_at = ? WHERE run_id = ?", (_now(), run_id))
            if cursor.rowcount == 0:
                raise PersistenceError(f"Run '{run_id}' could not be found.")

    def restore(self, run_id: str) -> None:
        with _write_scope(self.database, None) as conn:
            cursor = conn.execute("UPDATE runs SET archived_at = NULL WHERE run_id = ?", (run_id,))
            if cursor.rowcount == 0:
                raise PersistenceError(f"Run '{run_id}' could not be found.")

    def update_state(self, run_id: str, state: RunState, connection: sqlite3.Connection | None = None) -> None:
        with _write_scope(self.database, connection) as conn:
            row = conn.execute("SELECT state FROM runs WHERE run_id = ?", (run_id,)).fetchone()
            if row is None:
                raise PersistenceError(f"Run '{run_id}' could not be found.")
            try:
                current = RunState(row["state"])
            except ValueError as error:
                raise InvalidRunStateError(f"Run '{run_id}' has an invalid persisted state.") from error
            ensure_transition(current, state)
            conn.execute("UPDATE runs SET state = ? WHERE run_id = ?", (state.value, run_id))

    def attach_snapshot(self, run_id: str, snapshot_id: int, connection: sqlite3.Connection | None = None) -> None:
        with _write_scope(self.database, connection) as conn:
            conn.execute("UPDATE runs SET snapshot_id = ? WHERE run_id = ?", (snapshot_id, run_id))

    def delete_for_test(self, run_id: str) -> None:
        """Delete an unreferenced Run row; the issued-ID ledger remains."""
        with _write_scope(self.database, None) as conn:
            conn.execute("DELETE FROM runs WHERE run_id = ?", (run_id,))


class SnapshotRepository:
    def __init__(self, database: Any) -> None:
        self.database = database

    def add(self, run_id: str, program_version: int, canonical_version: str, canonical: str, digest: str, connection: sqlite3.Connection | None = None) -> RunConfigurationSnapshot:
        try:
            with _write_scope(self.database, connection) as conn:
                cursor = conn.execute("INSERT INTO run_configuration_snapshots (run_id, program_configuration_version, canonical_version, canonical_json, sha256, created_at) VALUES (?, ?, ?, ?, ?, ?)", (run_id, program_version, canonical_version, canonical, digest, _now()))
                snapshot_id = cursor.lastrowid
                conn.execute("UPDATE runs SET snapshot_id = ? WHERE run_id = ?", (snapshot_id, run_id))
                row = conn.execute("SELECT * FROM run_configuration_snapshots WHERE snapshot_id = ?", (snapshot_id,)).fetchone()
                return _snapshot(row)
        except PersistenceError:
            raise

    def get(self, run_id: str) -> RunConfigurationSnapshot:
        with _read_scope(self.database) as conn:
            row = conn.execute("SELECT * FROM run_configuration_snapshots WHERE run_id = ?", (run_id,)).fetchone()
            if row is None:
                raise PersistenceError(f"Run '{run_id}' does not have a configuration snapshot.")
            return _snapshot(row)


class AuditRepository:
    def __init__(self, database: Any) -> None:
        self.database = database

    def add(self, *, run_id: str | None, program_id: str, os_username: str, application_name: str, action: str, previous_state: RunState | None, new_state: RunState | None, metadata: dict[str, Any], connection: sqlite3.Connection | None = None) -> None:
        with _write_scope(self.database, connection) as conn:
            conn.execute("INSERT INTO audit_logs (run_id, program_id, os_username, application_name, occurred_at, action, previous_state, new_state, metadata_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (run_id, program_id, os_username, application_name, _now(), action, previous_state.value if previous_state else None, new_state.value if new_state else None, json.dumps(metadata, sort_keys=True, separators=(",", ":"))))

    def for_run(self, run_id: str) -> list[sqlite3.Row]:
        with _read_scope(self.database) as conn:
            return list(conn.execute("SELECT * FROM audit_logs WHERE run_id = ? ORDER BY audit_id", (run_id,)))


class ManifestRepository:
    def __init__(self, database: Any) -> None:
        self.database = database

    def add(self, manifest: ExecutionManifest, connection: sqlite3.Connection | None = None) -> None:
        with _write_scope(self.database, connection) as conn:
            snapshot = conn.execute("SELECT sha256 FROM run_configuration_snapshots WHERE run_id = ?", (manifest.run_id,)).fetchone()
            if snapshot is None or snapshot["sha256"] != manifest.configuration_snapshot_hash:
                raise ManifestIntegrityError("Execution manifest hash does not match the Run configuration snapshot.")
            conn.execute("INSERT INTO execution_manifests VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (manifest.run_id, manifest.configuration_snapshot_hash, manifest.source_artifact_hash, manifest.eligible_population_hash, manifest.sampling_algorithm, manifest.sampling_algorithm_version, manifest.rng_algorithm, manifest.rng_algorithm_version, manifest.random_seed, manifest.allocation_strategy, manifest.allocation_strategy_version, json.dumps(deep_thaw(manifest.output_artifact_hashes), sort_keys=True, separators=(",", ":")), _now()))

    def get(self, run_id: str) -> ExecutionManifest:
        with _read_scope(self.database) as conn:
            row = conn.execute("SELECT * FROM execution_manifests WHERE run_id = ?", (run_id,)).fetchone()
            if row is None:
                raise PersistenceError(f"Execution manifest for Run '{run_id}' could not be found.")
            return ExecutionManifest(run_id=row["run_id"], configuration_snapshot_hash=row["configuration_snapshot_hash"], source_artifact_hash=row["source_artifact_hash"], eligible_population_hash=row["eligible_population_hash"], sampling_algorithm=row["sampling_algorithm"], sampling_algorithm_version=row["sampling_algorithm_version"], rng_algorithm=row["rng_algorithm"], rng_algorithm_version=row["rng_algorithm_version"], random_seed=row["random_seed"], allocation_strategy=row["allocation_strategy"], allocation_strategy_version=row["allocation_strategy_version"], output_artifact_hashes=json.loads(row["output_artifact_hashes_json"]), created_at=datetime.fromisoformat(row["created_at"]))

    def associated_snapshot(self, run_id: str) -> RunConfigurationSnapshot:
        with _read_scope(self.database) as conn:
            row = conn.execute("SELECT s.* FROM runs r JOIN run_configuration_snapshots s ON s.snapshot_id = r.snapshot_id WHERE r.run_id = ?", (run_id,)).fetchone()
            if row is None:
                raise PersistenceError(f"Run '{run_id}' does not have an associated snapshot.")
            return _snapshot(row)

    def verify_snapshot_hash(self, run_id: str) -> bool:
        manifest = self.get(run_id)
        snapshot = self.associated_snapshot(run_id)
        if manifest.configuration_snapshot_hash != snapshot.sha256:
            raise ManifestIntegrityError("Execution manifest hash does not match the persisted snapshot hash.")
        return True


def _snapshot(row: sqlite3.Row) -> RunConfigurationSnapshot:
    return RunConfigurationSnapshot(row["snapshot_id"], row["run_id"], row["program_configuration_version"], row["canonical_version"], row["canonical_json"], row["sha256"], datetime.fromisoformat(row["created_at"]))


class EligiblePopulationRepository:
    def __init__(self, database: Any) -> None:
        self.database = database

    def add(self, population: EligiblePopulation, connection: sqlite3.Connection | None = None) -> None:
        resolutions_payload = [
            {
                "normalized_identifier": resolution.normalized_identifier,
                "original_values": list(resolution.original_values),
                "row_indexes": list(resolution.row_indexes),
                "action": resolution.action,
                "resolved_by": resolution.resolved_by,
                "resolved_at": resolution.resolved_at.isoformat(),
                "reason": resolution.reason,
                "kept_row_index": resolution.kept_row_index,
            }
            for resolution in population.resolutions
        ]
        with _write_scope(self.database, connection) as conn:
            conn.execute(
                "INSERT INTO eligible_populations (run_id, member_identifiers_json, fingerprint, frozen_at, total_rows, excluded_row_count, resolutions_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    population.run_id,
                    json.dumps(list(population.member_identifiers), sort_keys=False, separators=(",", ":")),
                    population.fingerprint,
                    population.frozen_at.isoformat(),
                    population.total_rows,
                    population.excluded_row_count,
                    json.dumps(resolutions_payload, sort_keys=True, separators=(",", ":")),
                ),
            )

    def get(self, run_id: str) -> EligiblePopulation:
        with _read_scope(self.database) as conn:
            row = conn.execute("SELECT * FROM eligible_populations WHERE run_id = ?", (run_id,)).fetchone()
            if row is None:
                raise PersistenceError(f"Run '{run_id}' does not have a frozen eligible population.")
            resolutions = tuple(
                DuplicateResolution(
                    normalized_identifier=item["normalized_identifier"],
                    original_values=tuple(item["original_values"]),
                    row_indexes=tuple(item["row_indexes"]),
                    action=item["action"],
                    resolved_by=item["resolved_by"],
                    resolved_at=datetime.fromisoformat(item["resolved_at"]),
                    reason=item["reason"],
                    kept_row_index=item["kept_row_index"],
                )
                for item in json.loads(row["resolutions_json"])
            )
            return EligiblePopulation(
                run_id=row["run_id"],
                member_identifiers=tuple(json.loads(row["member_identifiers_json"])),
                fingerprint=row["fingerprint"],
                frozen_at=datetime.fromisoformat(row["frozen_at"]),
                total_rows=row["total_rows"],
                excluded_row_count=row["excluded_row_count"],
                resolutions=resolutions,
            )


class SamplingResultRepository:
    def __init__(self, database: Any) -> None:
        self.database = database

    def add(self, result: SamplingResult, connection: sqlite3.Connection | None = None) -> None:
        with _write_scope(self.database, connection) as conn:
            conn.execute(
                "INSERT INTO sampling_results (run_id, sampling_method, requested_value, eligible_population_count, calculated_sample_count, actual_sample_count, random_seed, rng_algorithm, rng_algorithm_version, sampling_algorithm, sampling_algorithm_version, selected_identifiers_json, sampled_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    result.run_id,
                    result.sampling_method,
                    result.requested_value,
                    result.eligible_population_count,
                    result.calculated_sample_count,
                    result.actual_sample_count,
                    result.random_seed,
                    result.rng_algorithm,
                    result.rng_algorithm_version,
                    result.sampling_algorithm,
                    result.sampling_algorithm_version,
                    json.dumps(list(result.selected_identifiers), separators=(",", ":")),
                    result.sampled_at.isoformat(),
                ),
            )

    def get(self, run_id: str) -> SamplingResult:
        with _read_scope(self.database) as conn:
            row = conn.execute("SELECT * FROM sampling_results WHERE run_id = ?", (run_id,)).fetchone()
            if row is None:
                raise PersistenceError(f"Run '{run_id}' does not have a sampling result.")
            return SamplingResult(
                run_id=row["run_id"],
                sampling_method=row["sampling_method"],
                requested_value=row["requested_value"],
                eligible_population_count=row["eligible_population_count"],
                calculated_sample_count=row["calculated_sample_count"],
                actual_sample_count=row["actual_sample_count"],
                random_seed=row["random_seed"],
                rng_algorithm=row["rng_algorithm"],
                rng_algorithm_version=row["rng_algorithm_version"],
                sampling_algorithm=row["sampling_algorithm"],
                sampling_algorithm_version=row["sampling_algorithm_version"],
                selected_identifiers=tuple(json.loads(row["selected_identifiers_json"])),
                sampled_at=datetime.fromisoformat(row["sampled_at"]),
            )


class AllocationResultRepository:
    def __init__(self, database: Any) -> None:
        self.database = database

    def add(self, result: AllocationResult, connection: sqlite3.Connection | None = None) -> None:
        assignments_payload = [
            {
                "associate_id": a.associate_id,
                "target": a.target,
                "maximum_capacity": a.maximum_capacity,
                "planned_count": a.planned_count,
                "assigned_identifiers": list(a.assigned_identifiers),
                "above_target": a.above_target,
            }
            for a in result.assignments
        ]
        with _write_scope(self.database, connection) as conn:
            conn.execute(
                "INSERT INTO allocation_results (run_id, sample_count, total_target, total_maximum_capacity, capacity_shortage, unused_capacity, required_above_target_confirmation, confirmed_above_target, confirmed_by, assignments_json, allocated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    result.run_id,
                    result.sample_count,
                    result.total_target,
                    result.total_maximum_capacity,
                    result.capacity_shortage,
                    result.unused_capacity,
                    int(result.required_above_target_confirmation),
                    int(result.confirmed_above_target),
                    result.confirmed_by,
                    json.dumps(assignments_payload, separators=(",", ":")),
                    result.allocated_at.isoformat(),
                ),
            )

    def get(self, run_id: str) -> AllocationResult:
        with _read_scope(self.database) as conn:
            row = conn.execute("SELECT * FROM allocation_results WHERE run_id = ?", (run_id,)).fetchone()
            if row is None:
                raise PersistenceError(f"Run '{run_id}' does not have an allocation result.")
            assignments = tuple(
                AllocationAssignment(
                    associate_id=item["associate_id"],
                    target=item["target"],
                    maximum_capacity=item["maximum_capacity"],
                    planned_count=item["planned_count"],
                    assigned_identifiers=tuple(item["assigned_identifiers"]),
                    above_target=item["above_target"],
                )
                for item in json.loads(row["assignments_json"])
            )
            return AllocationResult(
                run_id=row["run_id"],
                sample_count=row["sample_count"],
                total_target=row["total_target"],
                total_maximum_capacity=row["total_maximum_capacity"],
                capacity_shortage=row["capacity_shortage"],
                unused_capacity=row["unused_capacity"],
                required_above_target_confirmation=bool(row["required_above_target_confirmation"]),
                confirmed_above_target=bool(row["confirmed_above_target"]),
                confirmed_by=row["confirmed_by"],
                assignments=assignments,
                allocated_at=datetime.fromisoformat(row["allocated_at"]),
            )


class ArtifactRepository:
    def __init__(self, database: Any) -> None:
        self.database = database

    def add(self, artifact: Artifact, connection: sqlite3.Connection | None = None) -> None:
        with _write_scope(self.database, connection) as conn:
            conn.execute(
                "INSERT INTO artifacts (run_id, artifact_type, relative_path, original_filename, sha256, byte_size, created_at, associate_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    artifact.run_id,
                    artifact.artifact_type.value,
                    artifact.relative_path,
                    artifact.original_filename,
                    artifact.sha256,
                    artifact.byte_size,
                    artifact.created_at.isoformat(),
                    artifact.associate_id,
                ),
            )

    def list_for_run(self, run_id: str) -> tuple[Artifact, ...]:
        with _read_scope(self.database) as conn:
            rows = conn.execute("SELECT * FROM artifacts WHERE run_id = ? ORDER BY artifact_id", (run_id,)).fetchall()
            return tuple(_artifact(row) for row in rows)


def _artifact(row: sqlite3.Row) -> Artifact:
    return Artifact(
        run_id=row["run_id"],
        artifact_type=ArtifactType(row["artifact_type"]),
        relative_path=row["relative_path"],
        original_filename=row["original_filename"],
        sha256=row["sha256"],
        byte_size=row["byte_size"],
        created_at=datetime.fromisoformat(row["created_at"]),
        associate_id=row["associate_id"],
    )


def _run_date_and_sequence(run_id: str) -> tuple[str, int]:
    parts = run_id.rsplit("-", 2)
    if len(parts) != 3 or len(parts[1]) != 8 or not parts[2].isdigit():
        raise PersistenceError("Run ID does not match the approved format.")
    try:
        parsed_date = date.fromisoformat(f"{parts[1][:4]}-{parts[1][4:6]}-{parts[1][6:]}")
    except ValueError as error:
        raise PersistenceError("Run ID contains an invalid date.") from error
    return parsed_date.isoformat(), int(parts[2])
