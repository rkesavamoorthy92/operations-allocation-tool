from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from operations_allocation.domain.models import Program
from operations_allocation.persistence.database import Database
from operations_allocation.persistence.repositories import ProgramRepository, RunRepository


class RepositoryListingTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.database = Database(Path(self.tempdir.name) / "listing.db")
        self.database.initialize_schema()
        self.programs = ProgramRepository(self.database)
        self.runs = RunRepository(self.database)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_list_all_programs_empty_then_populated(self) -> None:
        self.assertEqual(self.programs.list_all(), ())
        self.programs.add(Program("MX-PT", "MX PT", 0, True))
        self.programs.add(Program("US-PT", "US PT", 0, True))
        listed = self.programs.list_all()
        self.assertEqual([p.program_id for p in listed], ["MX-PT", "US-PT"])

    def test_list_all_runs_ordered_newest_first(self) -> None:
        self.programs.add(Program("MX-PT", "MX PT", 0, True))
        first = self.runs.create_next("MX-PT", "user", None, date(2026, 8, 1))
        second = self.runs.create_next("MX-PT", "user", None, date(2026, 8, 2))
        listed = self.runs.list_all()
        self.assertEqual(listed[0].run_id, second.run_id)
        self.assertEqual(listed[1].run_id, first.run_id)

    def test_list_all_runs_empty(self) -> None:
        self.assertEqual(self.runs.list_all(), ())
