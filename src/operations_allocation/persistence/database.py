"""SQLite connection lifecycle and Phase 1 schema.

Run configuration snapshots and audit records are append-only by design. SQLite
``BEFORE UPDATE`` and ``BEFORE DELETE`` triggers reject mutation at the database
boundary, independent of repository methods. ``schema_metadata`` records the
deterministic schema version used by the local database.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from operations_allocation.domain.exceptions import PersistenceError

SCHEMA_VERSION = 5


class Database:
    def __init__(self, path: Path | str) -> None:
        self.path = str(path)

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, isolation_level=None)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except sqlite3.Error as error:
            connection.rollback()
            raise PersistenceError("Local database operation could not be completed.") from error
        finally:
            connection.close()

    @contextmanager
    def read_transaction(self) -> Iterator[sqlite3.Connection]:
        """Open a deferred read transaction so readers do not take a write lock."""
        connection = sqlite3.connect(self.path, isolation_level=None)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("BEGIN")
            yield connection
            connection.commit()
        except sqlite3.Error as error:
            connection.rollback()
            raise PersistenceError("Local database read could not be completed.") from error
        finally:
            connection.close()

    def initialize_schema(self) -> None:
        schema = """
        CREATE TABLE IF NOT EXISTS programs (
            program_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            active_configuration_version INTEGER,
            active INTEGER NOT NULL CHECK (active IN (0, 1)),
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS program_configurations (
            program_id TEXT NOT NULL REFERENCES programs(program_id),
            version INTEGER NOT NULL CHECK (version >= 1),
            configuration_json TEXT NOT NULL,
            configuration_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (program_id, version),
            UNIQUE (program_id, configuration_hash)
        );
        CREATE TABLE IF NOT EXISTS associates (
            associate_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            active INTEGER NOT NULL CHECK (active IN (0, 1)),
            team_or_program TEXT,
            experience TEXT,
            default_target INTEGER CHECK (default_target IS NULL OR default_target >= 0),
            default_maximum_capacity INTEGER CHECK (default_maximum_capacity IS NULL OR default_maximum_capacity >= 0),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS runs (
            run_id TEXT PRIMARY KEY,
            program_id TEXT NOT NULL REFERENCES programs(program_id),
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            state TEXT NOT NULL CHECK (state IN (
                'DRAFT', 'SNAPSHOT_FROZEN', 'VALIDATED', 'ELIGIBLE_POPULATION_FROZEN',
                'SAMPLED', 'ALLOCATED', 'DISTRIBUTED', 'RETURNED', 'CONSOLIDATED',
                'QC_COMPLETED', 'COMPLETED', 'CANCELLED', 'FAILED', 'ABANDONED'
            )),
            due_date TEXT,
            snapshot_id INTEGER UNIQUE,
            FOREIGN KEY (snapshot_id, run_id) REFERENCES run_configuration_snapshots(snapshot_id, run_id)
        );
        CREATE TABLE IF NOT EXISTS run_configuration_snapshots (
            snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL UNIQUE REFERENCES runs(run_id),
            program_configuration_version INTEGER NOT NULL,
            canonical_version TEXT NOT NULL,
            canonical_json TEXT NOT NULL,
            sha256 TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL,
            UNIQUE (snapshot_id, run_id)
        );
        CREATE TABLE IF NOT EXISTS audit_logs (
            audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT REFERENCES runs(run_id),
            program_id TEXT NOT NULL,
            os_username TEXT NOT NULL,
            application_name TEXT NOT NULL,
            occurred_at TEXT NOT NULL,
            action TEXT NOT NULL,
            previous_state TEXT,
            new_state TEXT,
            metadata_json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS execution_manifests (
            run_id TEXT PRIMARY KEY REFERENCES runs(run_id),
            configuration_snapshot_hash TEXT NOT NULL,
            source_artifact_hash TEXT,
            eligible_population_hash TEXT,
            sampling_algorithm TEXT,
            sampling_algorithm_version TEXT,
            rng_algorithm TEXT,
            rng_algorithm_version TEXT,
            random_seed TEXT,
            allocation_strategy TEXT,
            allocation_strategy_version TEXT,
            output_artifact_hashes_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS run_id_ledger (
            run_id TEXT PRIMARY KEY,
            program_id TEXT NOT NULL REFERENCES programs(program_id),
            run_date TEXT NOT NULL,
            sequence INTEGER NOT NULL CHECK (sequence >= 1),
            issued_at TEXT NOT NULL,
            UNIQUE (program_id, run_date, sequence)
        );
        CREATE TABLE IF NOT EXISTS run_id_sequences (
            program_id TEXT NOT NULL REFERENCES programs(program_id),
            run_date TEXT NOT NULL,
            next_sequence INTEGER NOT NULL CHECK (next_sequence >= 1),
            PRIMARY KEY (program_id, run_date)
        );
        CREATE TABLE IF NOT EXISTS eligible_populations (
            run_id TEXT PRIMARY KEY REFERENCES runs(run_id),
            member_identifiers_json TEXT NOT NULL,
            fingerprint TEXT NOT NULL,
            frozen_at TEXT NOT NULL,
            total_rows INTEGER NOT NULL CHECK (total_rows >= 0),
            excluded_row_count INTEGER NOT NULL CHECK (excluded_row_count >= 0),
            resolutions_json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sampling_results (
            run_id TEXT PRIMARY KEY REFERENCES runs(run_id),
            sampling_method TEXT NOT NULL,
            requested_value TEXT NOT NULL,
            eligible_population_count INTEGER NOT NULL CHECK (eligible_population_count >= 0),
            calculated_sample_count TEXT,
            actual_sample_count INTEGER NOT NULL CHECK (actual_sample_count >= 0),
            random_seed TEXT NOT NULL,
            rng_algorithm TEXT NOT NULL,
            rng_algorithm_version TEXT NOT NULL,
            sampling_algorithm TEXT NOT NULL,
            sampling_algorithm_version TEXT NOT NULL,
            selected_identifiers_json TEXT NOT NULL,
            sampled_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS allocation_results (
            run_id TEXT PRIMARY KEY REFERENCES runs(run_id),
            sample_count INTEGER NOT NULL CHECK (sample_count >= 0),
            total_target INTEGER NOT NULL CHECK (total_target >= 0),
            total_maximum_capacity INTEGER NOT NULL CHECK (total_maximum_capacity >= 0),
            capacity_shortage INTEGER NOT NULL CHECK (capacity_shortage >= 0),
            unused_capacity INTEGER NOT NULL CHECK (unused_capacity >= 0),
            required_above_target_confirmation INTEGER NOT NULL CHECK (required_above_target_confirmation IN (0, 1)),
            confirmed_above_target INTEGER NOT NULL CHECK (confirmed_above_target IN (0, 1)),
            confirmed_by TEXT,
            assignments_json TEXT NOT NULL,
            allocated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS schema_metadata (
            schema_name TEXT PRIMARY KEY,
            schema_version INTEGER NOT NULL CHECK (schema_version >= 1)
        );
        CREATE TRIGGER IF NOT EXISTS prevent_snapshot_update
        BEFORE UPDATE ON run_configuration_snapshots
        BEGIN SELECT RAISE(ABORT, 'Run configuration snapshots are append-only'); END;
        CREATE TRIGGER IF NOT EXISTS prevent_snapshot_delete
        BEFORE DELETE ON run_configuration_snapshots
        BEGIN SELECT RAISE(ABORT, 'Run configuration snapshots are append-only'); END;
        CREATE TRIGGER IF NOT EXISTS prevent_audit_update
        BEFORE UPDATE ON audit_logs
        BEGIN SELECT RAISE(ABORT, 'Audit records are append-only'); END;
        CREATE TRIGGER IF NOT EXISTS prevent_audit_delete
        BEFORE DELETE ON audit_logs
        BEGIN SELECT RAISE(ABORT, 'Audit records are append-only'); END;
        CREATE TRIGGER IF NOT EXISTS prevent_eligible_population_update
        BEFORE UPDATE ON eligible_populations
        BEGIN SELECT RAISE(ABORT, 'Eligible populations are append-only'); END;
        CREATE TRIGGER IF NOT EXISTS prevent_eligible_population_delete
        BEFORE DELETE ON eligible_populations
        BEGIN SELECT RAISE(ABORT, 'Eligible populations are append-only'); END;
        CREATE TRIGGER IF NOT EXISTS prevent_sampling_result_update
        BEFORE UPDATE ON sampling_results
        BEGIN SELECT RAISE(ABORT, 'Sampling results are append-only'); END;
        CREATE TRIGGER IF NOT EXISTS prevent_sampling_result_delete
        BEFORE DELETE ON sampling_results
        BEGIN SELECT RAISE(ABORT, 'Sampling results are append-only'); END;
        CREATE TRIGGER IF NOT EXISTS prevent_allocation_result_update
        BEFORE UPDATE ON allocation_results
        BEGIN SELECT RAISE(ABORT, 'Allocation results are append-only'); END;
        CREATE TRIGGER IF NOT EXISTS prevent_allocation_result_delete
        BEFORE DELETE ON allocation_results
        BEGIN SELECT RAISE(ABORT, 'Allocation results are append-only'); END;
        """
        try:
            with self.transaction() as connection:
                connection.executescript(schema)
                connection.execute("INSERT OR IGNORE INTO schema_metadata (schema_name, schema_version) VALUES ('operations_allocation', ?)", (SCHEMA_VERSION,))
                row = connection.execute("SELECT schema_version FROM schema_metadata WHERE schema_name = 'operations_allocation'").fetchone()
                if row["schema_version"] != SCHEMA_VERSION:
                    raise PersistenceError("Unsupported local database schema version.")
        except PersistenceError:
            raise

    def schema_version(self) -> int:
        with self.read_transaction() as connection:
            row = connection.execute("SELECT schema_version FROM schema_metadata WHERE schema_name = 'operations_allocation'").fetchone()
            if row is None:
                raise PersistenceError("Local database schema version is unavailable.")
            return int(row["schema_version"])
