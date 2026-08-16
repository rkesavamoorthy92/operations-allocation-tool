"""Dialogs used to create a Program, create a Run, and freeze a Run's
setup (sampling configuration + associate roster). Thin: every dialog's
job is collecting input and handing it to ui.run_actions / AppContext
services -- no business rules live here (ARCHITECTURE.md section 9).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHeaderView,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from operations_allocation.core.randomizer import generate_random_seed
from operations_allocation.ui import run_actions


class NewProgramDialog(QDialog):
    def __init__(self, context: Any, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.context = context
        self.setWindowTitle("New Program")

        self.program_id_field = QLineEdit()
        self.program_id_field.setPlaceholderText("MX-PT")
        self.name_field = QLineEdit()
        self.name_field.setPlaceholderText("MX PT")

        form = QFormLayout()
        form.addRow("Program ID", self.program_id_field)
        form.addRow("Program Name", self.name_field)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _on_accept(self) -> None:
        try:
            self.context.program_configuration.create_program(self.program_id_field.text().strip(), self.name_field.text().strip())
        except Exception as error:
            QMessageBox.critical(self, "Could not create program", str(error))
            return
        self.accept()


class NewRunDialog(QDialog):
    def __init__(self, context: Any, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.context = context
        self.setWindowTitle("New Run")
        self.created_run: Any = None

        self.program_combo = QComboBox()
        for program in context.programs.list_all():
            self.program_combo.addItem(f"{program.program_id} — {program.name}", program.program_id)

        form = QFormLayout()
        form.addRow("Program", self.program_combo)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _on_accept(self) -> None:
        program_id = self.program_combo.currentData()
        if not program_id:
            QMessageBox.warning(self, "No program selected", "Create a Program first.")
            return
        try:
            self.created_run = self.context.orchestration.create_run(program_id=program_id, created_by=self.context.current_os_username())
        except Exception as error:
            QMessageBox.critical(self, "Could not create Run", str(error))
            return
        self.accept()


_ASSOCIATE_COLUMNS = ("Associate ID", "Name", "Email", "Target", "Max Capacity")


class FreezeSetupDialog(QDialog):
    """Collects the sampling configuration and associate roster needed to
    freeze a Run's immutable setup (PROJECT_SPEC.md section 6-7). The
    program's active configuration version is used as-is; editing program
    configuration itself is out of this dialog's scope."""

    def __init__(self, context: Any, run_id: str, program_id: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.context, self.run_id, self.program_id = context, run_id, program_id
        self.setWindowTitle(f"Freeze Setup — {run_id}")
        self.resize(640, 420)

        program = context.programs.get(program_id)
        self.program_configuration = context.programs.configuration(program_id, program.active_configuration_version)

        self.sampling_method_combo = QComboBox()
        self.sampling_method_combo.addItems(["count", "percentage"])
        self.sampling_value_field = QLineEdit()
        self.sampling_value_field.setPlaceholderText("e.g. 200 or 5")
        self.random_seed_field = QLineEdit()
        self.random_seed_field.setPlaceholderText("Optional; blank uses a generated seed")
        self.due_date_field = QDateEdit()
        self.due_date_field.setCalendarPopup(True)
        self.due_date_field.setDate(QDate.currentDate().addDays(7))
        self.due_date_field.setDisplayFormat("yyyy-MM-dd")

        self.associates_table = QTableWidget(0, len(_ASSOCIATE_COLUMNS))
        self.associates_table.setHorizontalHeaderLabels(_ASSOCIATE_COLUMNS)
        self.associates_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        add_row_button = QPushButton("+ Add Associate")
        add_row_button.clicked.connect(self._add_associate_row)
        remove_row_button = QPushButton("- Remove Selected")
        remove_row_button.clicked.connect(self._remove_selected_row)
        load_previous_button = QPushButton("Load from Previous Run")
        load_previous_button.clicked.connect(self._load_from_previous_run)
        import_file_button = QPushButton("Import from File...")
        import_file_button.clicked.connect(self._import_from_file)

        row_buttons = QHBoxLayout()
        row_buttons.addWidget(add_row_button)
        row_buttons.addWidget(remove_row_button)
        row_buttons.addWidget(load_previous_button)
        row_buttons.addWidget(import_file_button)

        form = QFormLayout()
        form.addRow("Sampling Method", self.sampling_method_combo)
        form.addRow("Sampling Value", self.sampling_value_field)
        form.addRow("Random Seed", self.random_seed_field)
        form.addRow("Due Date (shown to associates in email drafts)", self.due_date_field)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.associates_table)
        layout.addLayout(row_buttons)
        layout.addWidget(buttons)
        self._add_associate_row()

    def _add_associate_row(self) -> None:
        row = self.associates_table.rowCount()
        self.associates_table.insertRow(row)
        for column in range(len(_ASSOCIATE_COLUMNS)):
            self.associates_table.setItem(row, column, QTableWidgetItem(""))

    def _remove_selected_row(self) -> None:
        row = self.associates_table.currentRow()
        if row >= 0:
            self.associates_table.removeRow(row)

    def _load_from_previous_run(self) -> None:
        associates = run_actions.previous_run_associates(self.context, program_id=self.program_id, exclude_run_id=self.run_id)
        if not associates:
            QMessageBox.information(self, "No previous roster found", "No prior Run for this Program has a frozen associate roster yet.")
            return
        if not self._confirm_replace_roster():
            return
        self._populate_associates(associates)

    def _import_from_file(self) -> None:
        path, _filter = QFileDialog.getOpenFileName(self, "Select Associate Roster file", "", "Excel/CSV Files (*.xlsx *.csv)")
        if not path:
            return
        try:
            associates = run_actions.import_associate_roster(file_path=Path(path))
        except Exception as error:
            QMessageBox.critical(self, "Could not import Associate Roster", str(error))
            return
        if not associates:
            QMessageBox.information(self, "No associates found", "That file did not contain any associate rows.")
            return
        if not self._confirm_replace_roster():
            return
        self._populate_associates(associates)

    def _confirm_replace_roster(self) -> bool:
        """Only prompt if the table already has associate rows worth
        losing -- a brand-new dialog's single blank starter row shouldn't
        require a confirmation click."""
        if not any(self._collect_associates()):
            return True
        choice = QMessageBox.question(
            self, "Replace current roster?",
            "This will replace the associates currently in the table. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        return choice == QMessageBox.StandardButton.Yes

    def _populate_associates(self, associates: list[dict]) -> None:
        self.associates_table.setRowCount(0)
        for associate in associates:
            row = self.associates_table.rowCount()
            self.associates_table.insertRow(row)
            values = (
                associate.get("associate_id", ""),
                associate.get("name", ""),
                associate.get("email", ""),
                str(associate.get("target", 0)),
                str(associate.get("maximum_capacity", 0)),
            )
            for column, value in enumerate(values):
                self.associates_table.setItem(row, column, QTableWidgetItem(value))
        if self.associates_table.rowCount() == 0:
            self._add_associate_row()

    def _collect_associates(self) -> list[dict]:
        associates = []
        for row in range(self.associates_table.rowCount()):
            associate_id = self._cell(row, 0)
            if not associate_id:
                continue
            associates.append({
                "associate_id": associate_id,
                "name": self._cell(row, 1),
                "email": self._cell(row, 2),
                "active": True,
                "target": int(self._cell(row, 3) or 0),
                "maximum_capacity": int(self._cell(row, 4) or 0),
            })
        return associates

    def _cell(self, row: int, column: int) -> str:
        item = self.associates_table.item(row, column)
        return item.text().strip() if item else ""

    def _on_accept(self) -> None:
        try:
            sampling = {"method": self.sampling_method_combo.currentText(), "value": self.sampling_value_field.text().strip()}
            random_seed = self.random_seed_field.text().strip() or generate_random_seed()
            self.context.orchestration.freeze_setup(
                run_id=self.run_id,
                program_configuration=self.program_configuration,
                sampling=sampling,
                random_seed=random_seed,
                associates=self._collect_associates(),
                due_date=self.due_date_field.date().toString("yyyy-MM-dd"),
            )
        except Exception as error:
            QMessageBox.critical(self, "Could not freeze setup", str(error))
            return
        self.accept()
