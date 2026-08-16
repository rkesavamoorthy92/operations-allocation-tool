"""Verifies a database file created before the archived_at column existed
upgrades cleanly instead of getting stuck raising 'Unsupported local
database schema version' forever -- the exact failure mode a real user's
existing local database would hit if initialize_schema() only bumped
SCHEMA_VERSION without an accompanying ALTER TABLE migration.
"""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from operations_allocation.persistence.database import SCHEMA_VERSION, Database
from operations_allocation.persistence.repositories import ProgramRepository, RunRepository
from operations_allocation.domain.models import Program


_PRE_MIGRATION_RUNS_TABLE = """
CREATE TABLE runs (
    run_id TEXT PRIMARY KEY,
    program_id TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    state TEXT NOT NULL,
    due_date TEXT,
    snapshot_id INTEGER UNIQUE
);
"""


class SchemaMigrationTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "pre_existing.db"

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _create_pre_migration_database(self) -> None:
        connection = sqlite3.connect(str(self.db_path))
        try:
            connection.execute("CREATE TABLE programs (program_id TEXT PRIMARY KEY, name TEXT NOT NULL, active_configuration_version INTEGER, active INTEGER NOT NULL, created_at TEXT NOT NULL)")
            connection.execute(_PRE_MIGRATION_RUNS_TABLE)
            connection.execute("CREATE TABLE schema_metadata (schema_name TEXT PRIMARY KEY, schema_version INTEGER NOT NULL)")
            connection.execute("INSERT INTO schema_metadata VALUES ('operations_allocation', 6)")
            connection.commit()
        finally:
            connection.close()

    def test_pre_existing_database_upgrades_instead_of_rejecting(self) -> None:
        self._create_pre_migration_database()
        database = Database(self.db_path)
        database.initialize_schema()  # must not raise
        self.assertEqual(database.schema_version(), SCHEMA_VERSION)

    def test_run_repository_works_normally_after_upgrading_an_old_database(self) -> None:
        self._create_pre_migration_database()
        database = Database(self.db_path)
        database.initialize_schema()
        programs, runs = ProgramRepository(database), RunRepository(database)
        programs.add(Program("MX-PT", "MX PT"))
        from datetime import date

        run = runs.create_next("MX-PT", "user", None, date(2026, 8, 1))
        self.assertIsNone(runs.get(run.run_id).archived_at)
        runs.archive(run.run_id)
        self.assertIsNotNone(runs.get(run.run_id).archived_at)

    def test_migration_is_idempotent(self) -> None:
        self._create_pre_migration_database()
        database = Database(self.db_path)
        database.initialize_schema()
        database.initialize_schema()  # second call must not raise "duplicate column"
        self.assertEqual(database.schema_version(), SCHEMA_VERSION)
