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

    def test_archived_program_excluded_by_default_and_included_on_request(self) -> None:
        self.programs.add(Program("MX-PT", "MX PT", 0, True))
        self.programs.set_active("MX-PT", False)
        self.assertEqual(self.programs.list_all(), ())
        self.assertEqual(len(self.programs.list_all(include_archived=True)), 1)
        self.assertFalse(self.programs.list_all(include_archived=True)[0].active)

    def test_restoring_a_program_makes_it_visible_again(self) -> None:
        self.programs.add(Program("MX-PT", "MX PT", 0, True))
        self.programs.set_active("MX-PT", False)
        self.programs.set_active("MX-PT", True)
        self.assertEqual(len(self.programs.list_all()), 1)

    def test_archived_run_excluded_by_default_and_included_on_request(self) -> None:
        self.programs.add(Program("MX-PT", "MX PT", 0, True))
        run = self.runs.create_next("MX-PT", "user", None, date(2026, 8, 1))
        self.assertIsNone(self.runs.get(run.run_id).archived_at)
        self.runs.archive(run.run_id)
        self.assertEqual(self.runs.list_all(), ())
        restored_listing = self.runs.list_all(include_archived=True)
        self.assertEqual(len(restored_listing), 1)
        self.assertIsNotNone(restored_listing[0].archived_at)

    def test_restoring_a_run_makes_it_visible_again(self) -> None:
        self.programs.add(Program("MX-PT", "MX PT", 0, True))
        run = self.runs.create_next("MX-PT", "user", None, date(2026, 8, 1))
        self.runs.archive(run.run_id)
        self.runs.restore(run.run_id)
        self.assertEqual(len(self.runs.list_all()), 1)
        self.assertIsNone(self.runs.get(run.run_id).archived_at)
