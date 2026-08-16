"""Shows one Run's current state and every lifecycle action available
from it, as a simple stepper: buttons are enabled only when applicable
to the Run's current state, mirroring the state machine in
domain.state_machine. All actual work is delegated to ui.run_actions /
AppContext services -- this widget only wires user interaction to them
and renders the result (ARCHITECTURE.md section 9: no business logic
in PySide6 components).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from PySide6.QtWidgets import (
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from operations_allocation.domain.exceptions import ConsolidationBlockedByExceptionsError, OperationsAllocationError
from operations_allocation.domain.models import RunState
from operations_allocation.ui import run_actions
from operations_allocation.ui.action_dialogs import ConsolidationOverrideDialog, ReturnedFilesDialog
from operations_allocation.ui.audit_view import AuditLogDialog
from operations_allocation.ui.duplicate_resolution_view import DuplicateResolutionDialog
from operations_allocation.ui.formatting import format_percentage, state_label
from operations_allocation.ui.insights_view import InsightsDialog
from operations_allocation.ui.setup_dialogs import FreezeSetupDialog

_ANY_TIME_AFTER_CONSOLIDATED = {RunState.CONSOLIDATED, RunState.QC_COMPLETED, RunState.COMPLETED}
_ANY_STATE = set(RunState)


class RunDetailView(QWidget):
    def __init__(self, context: Any, run_id: str, on_back: Callable[[], None], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.context, self.run_id, self.on_back = context, run_id, on_back
        self._canonical_rows: list[dict] | None = None
        self._duplicate_groups: tuple = ()
        self._last_reconciliation: dict | None = None

        self.header_label = QLabel()
        self.header_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        back_button = QPushButton("← Back to Dashboard")
        back_button.clicked.connect(self.on_back)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)

        self._buttons: dict[str, QPushButton] = {}
        actions_box = QGroupBox("Actions")
        actions_layout = QVBoxLayout()
        for key, label, _states, _handler in self._action_specs():
            button = QPushButton(label)
            button.clicked.connect(self._make_handler(key))
            self._buttons[key] = button
            actions_layout.addWidget(button)
        actions_box.setLayout(actions_layout)

        top = QHBoxLayout()
        top.addWidget(back_button)
        top.addWidget(self.header_label)
        top.addStretch()

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(actions_box)
        layout.addWidget(QLabel("Activity Log"))
        layout.addWidget(self.log)

        self.refresh()

    def _action_specs(self) -> list[tuple[str, str, set[RunState], Callable[[], None]]]:
        return [
            ("freeze_setup", "Freeze Setup…", {RunState.DRAFT}, self._on_freeze_setup),
            ("import_source", "Import Source File & Validate…", {RunState.SNAPSHOT_FROZEN}, self._on_import_source),
            ("freeze_population", "Freeze Eligible Population", {RunState.VALIDATED}, self._on_freeze_population),
            ("sample", "Draw Sample", {RunState.ELIGIBLE_POPULATION_FROZEN}, self._on_sample),
            ("preview_allocation", "Preview Allocation", {RunState.SAMPLED}, self._on_preview_allocation),
            ("finalize_allocation", "Finalize Allocation", {RunState.SAMPLED}, self._on_finalize_allocation),
            ("distribute", "Distribute Associate Files", {RunState.ALLOCATED}, self._on_distribute),
            ("send_individual", "Send Individual Emails (Outlook)", {RunState.DISTRIBUTED}, self._on_send_individual),
            ("send_consolidated", "Send Consolidated Email (Outlook)", {RunState.DISTRIBUTED}, self._on_send_consolidated),
            ("import_returned", "Import Returned Files…", {RunState.DISTRIBUTED}, self._on_import_returned),
            ("finalize_consolidation", "Finalize Consolidation", {RunState.RETURNED}, self._on_finalize_consolidation),
            ("import_qc", "Import QC Report…", {RunState.CONSOLIDATED}, self._on_import_qc),
            ("generate_errors", "Generate Errors From Consolidation", _ANY_TIME_AFTER_CONSOLIDATED, self._on_generate_errors),
            ("import_errors", "Import Error Report…", _ANY_TIME_AFTER_CONSOLIDATED, self._on_import_errors),
            ("view_insights", "View Insights", _ANY_TIME_AFTER_CONSOLIDATED, self._on_view_insights),
            ("complete", "Mark Run Completed", {RunState.QC_COMPLETED}, self._on_complete),
            ("cancel", "Cancel Run", {RunState.DRAFT}, self._on_cancel),
            ("view_audit_log", "View Audit Log", _ANY_STATE, self._on_view_audit_log),
        ]

    def _make_handler(self, key: str) -> Callable[[], None]:
        return lambda: self._run_guarded(key)

    def _run_guarded(self, key: str) -> None:
        for spec_key, _label, _states, handler in self._action_specs():
            if spec_key == key:
                try:
                    handler()
                except OperationsAllocationError as error:
                    QMessageBox.warning(self, "Action could not be completed", str(error))
                except Exception as error:  # noqa: BLE001 -- surfaced to the user, never swallowed
                    QMessageBox.critical(self, "Unexpected error", str(error))
                self.refresh()
                return

    def refresh(self) -> None:
        run = self.context.runs.get(self.run_id)
        self.header_label.setText(f"{run.run_id}  ·  {run.program_id}  ·  {state_label(run.state)}")
        for key, _label, states, _handler in self._action_specs():
            self._buttons[key].setEnabled(run.state in states)

    def _append_log(self, message: str) -> None:
        self.log.appendPlainText(message)

    # -- Action handlers -----------------------------------------------

    def _on_freeze_setup(self) -> None:
        run = self.context.runs.get(self.run_id)
        dialog = FreezeSetupDialog(self.context, self.run_id, run.program_id, self)
        if dialog.exec():
            self._append_log("Setup frozen. Snapshot is now immutable for this Run.")

    def _on_import_source(self) -> None:
        file_path, _filter = QFileDialog.getOpenFileName(self, "Select source file", "", "Data Files (*.xlsx *.csv)")
        if not file_path:
            return
        canonical_rows, summary = run_actions.import_source_and_validate(self.context, run_id=self.run_id, file_path=file_path)
        self._canonical_rows = canonical_rows
        self._duplicate_groups = summary.duplicate_groups
        self._append_log(
            f"Imported {summary.total_rows} rows. Valid: {summary.valid_row_count}. "
            f"Critical issues: {len(summary.critical_issues)}. Duplicate groups: {len(summary.duplicate_groups)}."
        )

    def _on_freeze_population(self) -> None:
        if self._canonical_rows is None:
            QMessageBox.warning(self, "Import source first", "Re-run 'Import Source File & Validate' in this session before freezing.")
            return
        resolutions: tuple = ()
        if self._duplicate_groups:
            dialog = DuplicateResolutionDialog(self._duplicate_groups, self.context.current_os_username(), self)
            if not dialog.exec():
                self._append_log("Freeze cancelled; duplicate identifiers remain unresolved.")
                return
            resolutions = tuple(dialog.resolutions)
        population = run_actions.freeze_eligible_population(self.context, run_id=self.run_id, canonical_rows=self._canonical_rows, resolutions=resolutions)
        self._append_log(f"Eligible Population frozen with {len(population.member_identifiers)} items.")

    def _on_sample(self) -> None:
        result = run_actions.sample(self.context, run_id=self.run_id)
        self._append_log(f"Sampled {len(result.selected_identifiers)} items using seed '{result.random_seed}'.")

    def _on_preview_allocation(self) -> None:
        plan = run_actions.preview_allocation(self.context, run_id=self.run_id)
        lines = [f"  {a.associate_id}: {a.planned_count} planned" for a in plan.assignments]
        self._append_log("Allocation preview:\n" + "\n".join(lines))

    def _on_finalize_allocation(self) -> None:
        result = run_actions.finalize_allocation(self.context, run_id=self.run_id)
        self._append_log(f"Allocation finalized across {len(result.assignments)} associate(s).")

    def _on_distribute(self) -> None:
        artifacts = run_actions.distribute(self.context, run_id=self.run_id)
        self._append_log(f"Distributed {len(artifacts)} associate work file(s) to {self.context.file_artifacts.run_directory(self.run_id)}.")

    def _on_send_individual(self) -> None:
        drafts = run_actions.send_individual_drafts(self.context, run_id=self.run_id)
        self._append_log(f"Prepared {len(drafts)} individual email draft(s) (Outlook draft if available, plain-text fallback always saved).")

    def _on_send_consolidated(self) -> None:
        run_actions.send_consolidated_draft(self.context, run_id=self.run_id)
        self._append_log("Prepared the consolidated team email draft.")

    def _on_import_returned(self) -> None:
        dialog = ReturnedFilesDialog(self.context, self.run_id, self)
        if not dialog.exec():
            return
        payload = run_actions.import_returned_files(self.context, run_id=self.run_id, files=dialog.selection)
        self._last_reconciliation = payload
        summary = payload["summary"]
        self._append_log(
            f"Reconciled. Allocated: {summary['allocated_count']}, Returned: {summary['unique_returned_count']}, "
            f"Missing: {len(summary['missing_identifiers'])}, Duplicates: {summary['duplicate_count']}, "
            f"Unexpected: {summary['unexpected_count']}, Wrong Associate: {summary['wrong_associate_count']}."
        )

    def _on_finalize_consolidation(self) -> None:
        try:
            run_actions.finalize_consolidation(self.context, run_id=self.run_id)
            self._append_log("Consolidation finalized with no open critical exceptions.")
        except ConsolidationBlockedByExceptionsError:
            summary = (self._last_reconciliation or {}).get("summary", {})
            dialog = ConsolidationOverrideDialog(summary, self)
            if dialog.exec() and dialog.override:
                run_actions.finalize_consolidation(self.context, run_id=self.run_id, override=True, override_reason=dialog.override_reason)
                self._append_log(f"Consolidation finalized WITH OVERRIDE by {self.context.current_os_username()}: {dialog.override_reason}")
            else:
                self._append_log("Consolidation finalize cancelled; exceptions remain open.")

    def _on_import_qc(self) -> None:
        file_path, _filter = QFileDialog.getOpenFileName(self, "Select QC report file", "", "Data Files (*.xlsx *.csv)")
        if not file_path:
            return
        report = run_actions.import_qc_report(self.context, run_id=self.run_id, file_path=Path(file_path))
        qc_score = report.run_metrics.get("qc_score")
        score_text = format_percentage(qc_score.value, is_not_applicable=qc_score.is_not_applicable) if qc_score else "N/A"
        self._append_log(f"QC evaluated. Audited: {report.run_counts['audited_count']}. QC Score: {score_text}.")

    def _on_generate_errors(self) -> None:
        records = run_actions.generate_errors(self.context, run_id=self.run_id)
        self._append_log(f"Generated {len(records)} error record(s) from Consolidation exceptions.")

    def _on_import_errors(self) -> None:
        file_path, _filter = QFileDialog.getOpenFileName(self, "Select error report file", "", "Data Files (*.xlsx *.csv)")
        if not file_path:
            return
        records = run_actions.import_errors(self.context, run_id=self.run_id, file_path=Path(file_path))
        self._append_log(f"Imported {len(records)} error record(s).")

    def _on_view_insights(self) -> None:
        report = run_actions.generate_insights(self.context, run_id=self.run_id)
        InsightsDialog(report, self.run_id, self).exec()

    def _on_complete(self) -> None:
        run_actions.complete_run(self.context, run_id=self.run_id)
        self._append_log("Run marked COMPLETED.")

    def _on_cancel(self) -> None:
        run_actions.cancel_run(self.context, run_id=self.run_id)
        self._append_log("Run cancelled.")

    def _on_view_audit_log(self) -> None:
        AuditLogDialog(self.context, self.run_id, self).exec()
