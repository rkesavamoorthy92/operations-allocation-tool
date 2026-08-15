"""Dialogs for the mid-lifecycle actions: mapping returned files to
associates for Consolidation, and confirming a Consolidation override
when critical exceptions are open (PROJECT_SPEC.md section 20 -- an
override always requires an accountable user and a written reason).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


def _guess_associate(file_path: str, associate_ids: list[str]) -> str | None:
    """A convenience suggestion only -- the confirmed value in the combo
    box is always what gets sent to Consolidation for reconciliation."""
    name = Path(file_path).stem
    for associate_id in associate_ids:
        if associate_id in name:
            return associate_id
    return None


class ReturnedFilesDialog(QDialog):
    """Lets the user pick one or more returned .xlsx files and confirm
    which associate each belongs to. The claimed associate is what
    Consolidation actually reconciles against -- filename matching here
    is only a convenience suggestion, never silently trusted on its own
    (see services.consolidation module docstring)."""

    def __init__(self, context: Any, run_id: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.context, self.run_id = context, run_id
        self.setWindowTitle(f"Import Returned Files — {run_id}")
        self.resize(560, 360)
        self.selection: list[tuple[Path, str]] = []

        snapshot = context.snapshots.get(run_id)
        self.associate_ids = [a["associate_id"] for a in snapshot.configuration["associates"]]

        pick_button = QPushButton("Choose Files…")
        pick_button.clicked.connect(self._choose_files)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["File", "Associate"])

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(pick_button)
        layout.addWidget(self.table)
        layout.addWidget(buttons)

    def _choose_files(self) -> None:
        paths, _filter = QFileDialog.getOpenFileNames(self, "Select returned associate files", "", "Excel Files (*.xlsx)")
        self.table.setRowCount(0)
        for path in paths:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(path))
            combo = QComboBox()
            combo.addItems(self.associate_ids)
            guess = _guess_associate(path, self.associate_ids)
            if guess is not None:
                combo.setCurrentIndex(self.associate_ids.index(guess))
            self.table.setCellWidget(row, 1, combo)

    def _on_accept(self) -> None:
        selection = []
        for row in range(self.table.rowCount()):
            file_path = self.table.item(row, 0).text()
            combo = self.table.cellWidget(row, 1)
            selection.append((Path(file_path), combo.currentText()))
        if not selection:
            QMessageBox.warning(self, "No files selected", "Choose at least one returned file.")
            return
        self.selection = selection
        self.accept()


class ConsolidationOverrideDialog(QDialog):
    """Shown only when Consolidation has open critical exceptions.
    Overriding always requires an explicit, non-empty reason -- there is
    no way to dismiss this dialog with the override checked and no
    reason typed (PROJECT_SPEC.md section 20)."""

    def __init__(self, summary: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Open Consolidation Exceptions")
        self.resize(480, 320)
        self.override = False
        self.override_reason = ""

        text = (
            f"Missing: {len(summary['missing_identifiers'])}   "
            f"Duplicates: {summary['duplicate_count']}   "
            f"Unexpected: {summary['unexpected_count']}   "
            f"Wrong Associate: {summary['wrong_associate_count']}   "
            f"Identity Issues: {summary['identity_issue_count']}\n\n"
            "This Run has open critical Consolidation exceptions. "
            "Consolidation will be blocked unless you explicitly override, "
            "with a reason, below."
        )
        self.override_checkbox = QCheckBox("Override and proceed anyway")
        self.reason_field = QPlainTextEdit()
        self.reason_field.setPlaceholderText("Required if overriding: why is it safe to proceed?")

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(text))
        layout.addWidget(self.override_checkbox)
        layout.addWidget(self.reason_field)
        layout.addWidget(buttons)

    def _on_accept(self) -> None:
        if self.override_checkbox.isChecked() and not self.reason_field.toPlainText().strip():
            QMessageBox.warning(self, "Reason required", "An override requires a non-empty reason.")
            return
        self.override = self.override_checkbox.isChecked()
        self.override_reason = self.reason_field.toPlainText().strip()
        self.accept()
