"""Landing screen: lists Programs and Runs, and lets the user create new
ones. Double-clicking a Run opens its detail view via the provided
callback (MainWindow owns navigation, not this widget).
"""

from __future__ import annotations

from typing import Any, Callable

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

from operations_allocation.ui.formatting import format_timestamp, state_label
from operations_allocation.ui.setup_dialogs import NewProgramDialog, NewRunDialog

_RUN_COLUMNS = ("Run ID", "Program", "State", "Created")


class DashboardView(QWidget):
    def __init__(self, context: Any, on_open_run: Callable[[str], None], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.context, self.on_open_run = context, on_open_run

        title = QLabel("Operations Allocation Tool")
        title.setStyleSheet("font-size: 20px; font-weight: bold;")

        new_program_button = QPushButton("+ New Program")
        new_program_button.clicked.connect(self._new_program)
        new_run_button = QPushButton("+ New Run")
        new_run_button.clicked.connect(self._new_run)
        refresh_button = QPushButton("Refresh")
        refresh_button.clicked.connect(self.refresh)

        self.runs_table = QTableWidget(0, len(_RUN_COLUMNS))
        self.runs_table.setHorizontalHeaderLabels(_RUN_COLUMNS)
        self.runs_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.runs_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.runs_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.runs_table.cellDoubleClicked.connect(self._open_selected_run)

        buttons_row = QHBoxLayout()
        buttons_row.addWidget(new_program_button)
        buttons_row.addWidget(new_run_button)
        buttons_row.addWidget(refresh_button)
        buttons_row.addStretch()

        layout = QVBoxLayout(self)
        layout.addWidget(title)
        layout.addLayout(buttons_row)
        layout.addWidget(QLabel("Runs (double-click to open)"))
        layout.addWidget(self.runs_table)

        self.refresh()

    def refresh(self) -> None:
        runs = self.context.runs.list_all()
        self.runs_table.setRowCount(len(runs))
        for row, run in enumerate(runs):
            self.runs_table.setItem(row, 0, QTableWidgetItem(run.run_id))
            self.runs_table.setItem(row, 1, QTableWidgetItem(run.program_id))
            self.runs_table.setItem(row, 2, QTableWidgetItem(state_label(run.state)))
            self.runs_table.setItem(row, 3, QTableWidgetItem(format_timestamp(run.created_at)))

    def _new_program(self) -> None:
        dialog = NewProgramDialog(self.context, self)
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
