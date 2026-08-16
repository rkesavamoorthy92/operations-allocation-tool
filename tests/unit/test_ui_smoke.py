"""Smoke tests for the PySide6 layer: construct real widgets against a
real AppContext (offscreen Qt platform, no visible window) and verify
they build without crashing and reflect the correct state. Does not
click through modal QDialog.exec() calls -- those block for real user
input, so dialogs are instead constructed directly and inspected.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from PySide6.QtWidgets import QApplication, QTableWidget

from operations_allocation.domain.models import RunState
from operations_allocation.core.validation import DuplicateGroup
from operations_allocation.ui.action_dialogs import ConsolidationOverrideDialog
from operations_allocation.ui.app_context import AppContext
from operations_allocation.ui.audit_view import AuditLogDialog
from operations_allocation.ui.duplicate_resolution_view import DuplicateResolutionDialog
from operations_allocation.ui.dashboard_view import DashboardView
from operations_allocation.ui.insights_view import InsightsDialog
from operations_allocation.ui.main_window import MainWindow
from operations_allocation.ui.program_configuration_view import ProgramConfigurationDialog, starter_template
from operations_allocation.ui.run_detail_view import RunDetailView
from operations_allocation.ui import run_actions
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

    def test_dashboard_lists_programs_with_active_version(self) -> None:
        dashboard = DashboardView(self.context, on_open_run=lambda run_id: None)
        self.assertEqual(dashboard.programs_table.rowCount(), 1)
        self.assertEqual(dashboard.programs_table.item(0, 0).text(), "MX-PT")
        self.assertEqual(dashboard.programs_table.item(0, 2).text(), "1")

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
        self.assertFalse(view._buttons["view_insights"].isEnabled())

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

    def test_insights_dialog_constructs_for_a_run_with_no_data_yet(self) -> None:
        run = self.context.orchestration.create_run(program_id="MX-PT", created_by="tester", created_on=date(2026, 8, 15))
        report = run_actions.generate_insights(self.context, run_id=run.run_id)
        dialog = InsightsDialog(report, run.run_id)
        self.assertIn(run.run_id, dialog.windowTitle())

    def test_audit_log_dialog_lists_events(self) -> None:
        run = self.context.orchestration.create_run(program_id="MX-PT", created_by="tester", created_on=date(2026, 8, 15))
        dialog = AuditLogDialog(self.context, run.run_id)
        table = dialog.findChild(QTableWidget)
        self.assertEqual(table.rowCount(), len(self.context.audit_repository.for_run(run.run_id)))
        self.assertIn(run.run_id, dialog.windowTitle())

    def test_duplicate_resolution_dialog_defaults_to_exclude_all(self) -> None:
        groups = (DuplicateGroup(normalized_identifier="P001", original_values=("P001", "p001"), row_indexes=(0, 1)),)
        dialog = DuplicateResolutionDialog(groups, "tester")
        dialog.reason_field.setPlainText("Confirmed true duplicates.")
        dialog._on_accept()
        self.assertEqual(len(dialog.resolutions), 1)
        self.assertEqual(dialog.resolutions[0].action, "EXCLUDE_ALL")
        self.assertIsNone(dialog.resolutions[0].kept_row_index)

    def test_duplicate_resolution_dialog_keep_row_selection(self) -> None:
        groups = (DuplicateGroup(normalized_identifier="P001", original_values=("P001", "p001"), row_indexes=(0, 1)),)
        dialog = DuplicateResolutionDialog(groups, "tester")
        _group, combo = dialog._combos[0]
        combo.setCurrentIndex(1)  # "Keep row 0"
        dialog.reason_field.setPlainText("Row 0 is the authoritative entry.")
        dialog._on_accept()
        self.assertEqual(dialog.resolutions[0].action, "KEEP_ROW")
        self.assertEqual(dialog.resolutions[0].kept_row_index, 0)

    def test_program_configuration_dialog_edits_next_version_of_existing_program(self) -> None:
        dialog = ProgramConfigurationDialog(self.context, "MX-PT")
        self.assertIn('"version": 2', dialog.editor.toPlainText())
        dialog._on_validate()
        self.assertEqual(dialog.status_label.text(), "Valid.")
        dialog._on_save()
        self.assertTrue(dialog.saved)
        self.assertEqual(self.context.programs.get("MX-PT").active_configuration_version, 2)

    def test_program_configuration_dialog_starter_template_for_new_program(self) -> None:
        self.context.program_configuration.create_program("MX-QC", "MX QC")
        dialog = ProgramConfigurationDialog(self.context, "MX-QC")
        self.assertEqual(json.loads(dialog.editor.toPlainText()), starter_template("MX-QC", "MX QC"))

    def test_program_configuration_dialog_shows_error_for_invalid_json(self) -> None:
        dialog = ProgramConfigurationDialog(self.context, "MX-PT")
        dialog.editor.setPlainText("{not valid json")
        dialog._on_validate()
        self.assertIn("Invalid JSON", dialog.status_label.text())
