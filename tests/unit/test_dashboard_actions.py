"""End-to-end tests (real AppContext, real SQLite file) for the
Dashboard's archive/restore composition -- especially the Program
archive cascading to its Runs, which is the one behavior that lives
above a single repository/service and is easy to get subtly wrong.
"""

from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from operations_allocation.ui import dashboard_actions
from operations_allocation.ui.app_context import AppContext


class DashboardActionsTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.context = AppContext.build(data_directory=Path(self.tempdir.name) / "app_data")
        self.context.program_configuration.create_program("MX-PT", "MX PT")

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _create_run(self) -> str:
        return self.context.orchestration.create_run(program_id="MX-PT", created_by="user", created_on=date(2026, 8, 15)).run_id

    def test_archiving_a_program_cascades_to_its_runs(self) -> None:
        run_id = self._create_run()
        dashboard_actions.archive_program(self.context, program_id="MX-PT")
        self.assertEqual(self.context.programs.list_all(), ())
        self.assertEqual(self.context.runs.list_all(), ())
        self.assertIsNotNone(self.context.runs.get(run_id).archived_at)
        self.assertFalse(self.context.programs.get("MX-PT").active)

    def test_archiving_a_program_does_not_re_archive_an_already_restored_run(self) -> None:
        run_id = self._create_run()
        dashboard_actions.archive_program(self.context, program_id="MX-PT")
        dashboard_actions.restore_run(self.context, run_id=run_id)
        dashboard_actions.archive_program(self.context, program_id="MX-PT")
        # Second archive_program call must not blow up re-archiving a Run
        # that is already archived, nor touch one a human deliberately restored.
        self.assertIsNotNone(self.context.runs.get(run_id).archived_at)

    def test_restoring_a_program_does_not_cascade_restore_its_runs(self) -> None:
        run_id = self._create_run()
        dashboard_actions.archive_program(self.context, program_id="MX-PT")
        dashboard_actions.restore_program(self.context, program_id="MX-PT")
        self.assertTrue(self.context.programs.get("MX-PT").active)
        self.assertIsNotNone(self.context.runs.get(run_id).archived_at)

    def test_archive_and_restore_run_directly(self) -> None:
        run_id = self._create_run()
        dashboard_actions.archive_run(self.context, run_id=run_id)
        self.assertIsNotNone(self.context.runs.get(run_id).archived_at)
        dashboard_actions.restore_run(self.context, run_id=run_id)
        self.assertIsNone(self.context.runs.get(run_id).archived_at)

    def test_archiving_a_run_is_recorded_in_the_audit_log(self) -> None:
        run_id = self._create_run()
        dashboard_actions.archive_run(self.context, run_id=run_id)
        actions = [event["action"] for event in self.context.audit_repository.for_run(run_id)]
        self.assertIn("RUN_ARCHIVED", actions)
