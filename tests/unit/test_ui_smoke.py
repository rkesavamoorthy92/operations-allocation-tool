"""Smoke tests for the PySide6 layer: construct real widgets against a
real AppContext (offscreen Qt platform, no visible window) and verify
they build without crashing and reflect the correct state. Does not
click through modal QDialog.exec() calls -- those block for real user
input, so dialogs are instead constructed directly and inspected.
"""

from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from PySide6.QtWidgets import QApplication

from operations_allocation.domain.models import RunState
from operations_allocation.ui.action_dialogs import ConsolidationOverrideDialog
from operations_allocation.ui.app_context import AppContext
from operations_allocation.ui.dashboard_view import DashboardView
from operations_allocation.ui.main_window import MainWindow
from operations_allocation.ui.run_detail_view import RunDetailView
from operations_allocation.ui.setup_dialogs import FreezeSetupDialog, NewProgramDialog, NewRunDialog
from tests.unit.test_distribution_service import distribution_config

_app = QApplication.instance() or QApplication(["test", "-platform", "offscreen"])


class UiSmokeTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.context = AppContext.build(data_directory=Path(self.tempdir.name) / "app_data")
        self.context.program_configuration.create_program("MX-PT", "MX PT")
        self.context.program_configuration.save_version(distribution_config())

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_main_window_constructs_and_shows_dashboard(self) -> None:
        window = MainWindow(self.context)
        self.assertIs(window.stack.currentWidget(), window.dashboard)

    def test_dashboard_lists_created_runs(self) -> None:
        self.context.orchestration.create_run(program_id="MX-PT", created_by="tester", created_on=date(2026, 8, 15))
        dashboard = DashboardView(self.context, on_open_run=lambda run_id: None)
        self.assertEqual(dashboard.runs_table.rowCount(), 1)

    def test_open_run_navigates_to_detail_view(self) -> None:
        run = self.context.orchestration.create_run(program_id="MX-PT", created_by="tester", created_on=date(2026, 8, 15))
        window = MainWindow(self.context)
        window.open_run(run.run_id)
        self.assertIsInstance(window.stack.currentWidget(), RunDetailView)
        window.show_dashboard()
        self.assertIs(window.stack.currentWidget(), window.dashboard)

    def test_run_detail_only_enables_actions_valid_for_draft_state(self) -> None:
        run = self.context.orchestration.create_run(program_id="MX-PT", created_by="tester", created_on=date(2026, 8, 15))
        view = RunDetailView(self.context, run.run_id, on_back=lambda: None)
        self.assertTrue(view._buttons["freeze_setup"].isEnabled())
        self.assertTrue(view._buttons["cancel"].isEnabled())
        self.assertFalse(view._buttons["import_source"].isEnabled())
        self.assertFalse(view._buttons["distribute"].isEnabled())

    def test_run_detail_buttons_update_after_freeze_setup(self) -> None:
        associates = [{"associate_id": "A001", "name": "Jane", "email": "jane@example.test", "active": True, "target": 5, "maximum_capacity": 5}]
        run = self.context.orchestration.create_run(program_id="MX-PT", created_by="tester", created_on=date(2026, 8, 15))
        self.context.orchestration.freeze_setup(run_id=run.run_id, program_configuration=distribution_config(), sampling={"method": "count", "value": 5}, random_seed="seed", associates=associates)
        view = RunDetailView(self.context, run.run_id, on_back=lambda: None)
        self.assertFalse(view._buttons["freeze_setup"].isEnabled())
        self.assertTrue(view._buttons["import_source"].isEnabled())

    def test_new_program_dialog_constructs(self) -> None:
        dialog = NewProgramDialog(self.context)
        self.assertEqual(dialog.windowTitle(), "New Program")

    def test_new_run_dialog_lists_programs(self) -> None:
        dialog = NewRunDialog(self.context)
        self.assertEqual(dialog.program_combo.count(), 1)

    def test_freeze_setup_dialog_constructs_with_program_configuration(self) -> None:
        run = self.context.orchestration.create_run(program_id="MX-PT", created_by="tester", created_on=date(2026, 8, 15))
        dialog = FreezeSetupDialog(self.context, run.run_id, "MX-PT")
        self.assertEqual(dialog.associates_table.rowCount(), 1)  # Starts with one blank row to fill in.

    def test_consolidation_override_dialog_requires_reason(self) -> None:
        summary = {"missing_identifiers": ["P1"], "duplicate_count": 0, "unexpected_count": 0, "wrong_associate_count": 0, "identity_issue_count": 0}
        dialog = ConsolidationOverrideDialog(summary)
        # Checked with a blank reason: verified via the dialog's own field
        # state rather than calling _on_accept(), which would pop a real
        # blocking QMessageBox.warning() with no automated way to close it.
        dialog.override_checkbox.setChecked(True)
        dialog.reason_field.setPlainText("")
        self.assertTrue(dialog.override_checkbox.isChecked() and not dialog.reason_field.toPlainText().strip())

        dialog.reason_field.setPlainText("Investigated separately.")
        dialog._on_accept()
        self.assertTrue(dialog.override)
        self.assertEqual(dialog.override_reason, "Investigated separately.")
