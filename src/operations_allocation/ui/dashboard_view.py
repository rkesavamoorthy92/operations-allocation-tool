"""Landing screen: lists Programs and Runs, and lets the user create new
ones. Double-clicking a Run opens its detail view via the provided
callback (MainWindow owns navigation, not this widget).
"""

from __future__ import annotations

from typing import Any, Callable

from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from operations_allocation.ui.formatting import format_timestamp, state_color, state_label
from operations_allocation.ui.program_configuration_view import ProgramConfigurationDialog
from operations_allocation.ui.setup_dialogs import NewProgramDialog, NewRunDialog

_RUN_COLUMNS = ("Run ID", "Program", "State", "Created")
_PROGRAM_COLUMNS = ("Program ID", "Name", "Active Config Version")


class DashboardView(QWidget):
    def __init__(self, context: Any, on_open_run: Callable[[str], None], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.context, self.on_open_run = context, on_open_run

        title = QLabel("Operations Allocation Tool")
        title.setProperty("heading", True)

        new_program_button = QPushButton("+ New Program")
        new_program_button.setProperty("accent", True)
        new_program_button.clicked.connect(self._new_program)
        edit_configuration_button = QPushButton("Edit Configuration")
        edit_configuration_button.clicked.connect(self._edit_selected_program_configuration)
        new_run_button = QPushButton("+ New Run")
        new_run_button.setProperty("accent", True)
        new_run_button.clicked.connect(self._new_run)
        refresh_button = QPushButton("Refresh")
        refresh_button.clicked.connect(self.refresh)

        self.programs_table = QTableWidget(0, len(_PROGRAM_COLUMNS))
        self.programs_table.setHorizontalHeaderLabels(_PROGRAM_COLUMNS)
        self.programs_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.programs_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.programs_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.programs_table.cellDoubleClicked.connect(self._open_program_configuration)

        self.runs_table = QTableWidget(0, len(_RUN_COLUMNS))
        self.runs_table.setHorizontalHeaderLabels(_RUN_COLUMNS)
        self.runs_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.runs_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.runs_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.runs_table.cellDoubleClicked.connect(self._open_selected_run)

        buttons_row = QHBoxLayout()
        buttons_row.addWidget(new_program_button)
        buttons_row.addWidget(edit_configuration_button)
        buttons_row.addWidget(new_run_button)
        buttons_row.addWidget(refresh_button)
        buttons_row.addStretch()

        layout = QVBoxLayout(self)
        layout.addWidget(title)
        layout.addLayout(buttons_row)
        layout.addWidget(_subheading("Programs (double-click to edit configuration)"))
        layout.addWidget(self.programs_table)
        layout.addWidget(_subheading("Runs (double-click to open)"))
        layout.addWidget(self.runs_table)

        self.refresh()

    def refresh(self) -> None:
        programs = self.context.programs.list_all()
        self.programs_table.setRowCount(len(programs))
        for row, program in enumerate(programs):
            self.programs_table.setItem(row, 0, QTableWidgetItem(program.program_id))
            self.programs_table.setItem(row, 1, QTableWidgetItem(program.name))
            version_text = str(program.active_configuration_version) if program.active_configuration_version is not None else "None yet"
            self.programs_table.setItem(row, 2, QTableWidgetItem(version_text))

        runs = self.context.runs.list_all()
        self.runs_table.setRowCount(len(runs))
        for row, run in enumerate(runs):
            self.runs_table.setItem(row, 0, QTableWidgetItem(run.run_id))
            self.runs_table.setItem(row, 1, QTableWidgetItem(run.program_id))
            state_item = QTableWidgetItem(state_label(run.state))
            state_item.setForeground(QBrush(QColor(state_color(run.state))))
            font = state_item.font()
            font.setBold(True)
            state_item.setFont(font)
            self.runs_table.setItem(row, 2, state_item)
            self.runs_table.setItem(row, 3, QTableWidgetItem(format_timestamp(run.created_at)))

    def _new_program(self) -> None:
        dialog = NewProgramDialog(self.context, self)
        if dialog.exec():
            self.refresh()

    def _edit_selected_program_configuration(self) -> None:
        row = self.programs_table.currentRow()
        if row < 0:
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.information(self, "No program selected", "Select a Program in the table first.")
            return
        self._open_program_configuration(row, 0)

    def _open_program_configuration(self, row: int, _column: int) -> None:
        program_id = self.programs_table.item(row, 0).text()
        dialog = ProgramConfigurationDialog(self.context, program_id, self)
        if dialog.exec():
            self.refresh()

    def _new_run(self) -> None:
        if not self.context.programs.list_all():
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.information(self, "No programs yet", "Create a Program before creating a Run.")
            return
        dialog = NewRunDialog(self.context, self)
        if dialog.exec():
            self.refresh()
            if dialog.created_run is not None:
                self.on_open_run(dialog.created_run.run_id)

    def _open_selected_run(self, row: int, _column: int) -> None:
        run_id = self.runs_table.item(row, 0).text()
        self.on_open_run(run_id)


def _subheading(text: str) -> QLabel:
    label = QLabel(text)
    label.setProperty("subheading", True)
    return label
