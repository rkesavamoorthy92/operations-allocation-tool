"""Landing screen: lists Programs and Runs, lets the user create new
ones, and archive/restore ones they no longer want cluttering the view.
Double-clicking a Run opens its detail view via the provided callback
(MainWindow owns navigation, not this widget). Archiving/restoring
composition lives in ui.dashboard_actions -- this widget only wires
user interaction to it and renders the result (ARCHITECTURE.md section
9: no business logic in PySide6 components).
"""

from __future__ import annotations

from typing import Any, Callable

from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from operations_allocation.ui import dashboard_actions
from operations_allocation.ui.confirm_dialog import TypeToConfirmDialog
from operations_allocation.ui.formatting import format_timestamp, state_color, state_label
from operations_allocation.ui.program_configuration_view import ProgramConfigurationDialog
from operations_allocation.ui.setup_dialogs import NewProgramDialog, NewRunDialog

_RUN_COLUMNS = ("Run ID", "Program", "State", "Created", "Visibility")
_PROGRAM_COLUMNS = ("Program ID", "Name", "Active Config Version", "Status")
_MUTED_TEXT_COLOR = QColor("#9CA3AF")  # matches ui.theme's disabled_text


class DashboardView(QWidget):
    def __init__(self, context: Any, on_open_run: Callable[[str], None], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.context, self.on_open_run = context, on_open_run

        title = QLabel("Operations Allocation Tool")
        title.setProperty("heading", True)

        self.show_archived_checkbox = QCheckBox("Show archived Programs && Runs")
        self.show_archived_checkbox.stateChanged.connect(self.refresh)
        refresh_button = QPushButton("Refresh")
        refresh_button.clicked.connect(self.refresh)

        top_row = QHBoxLayout()
        top_row.addWidget(self.show_archived_checkbox)
        top_row.addStretch()
        top_row.addWidget(refresh_button)

        new_program_button = QPushButton("+ New Program")
        new_program_button.setProperty("accent", True)
        new_program_button.clicked.connect(self._new_program)
        edit_configuration_button = QPushButton("Edit Configuration")
        edit_configuration_button.clicked.connect(self._edit_selected_program_configuration)
        archive_program_button = QPushButton("Archive Selected Program")
        archive_program_button.setProperty("danger", True)
        archive_program_button.clicked.connect(self._archive_selected_program)
        restore_program_button = QPushButton("Restore Selected Program")
        restore_program_button.clicked.connect(self._restore_selected_program)

        program_buttons_row = QHBoxLayout()
        for button in (new_program_button, edit_configuration_button, archive_program_button, restore_program_button):
            program_buttons_row.addWidget(button)
        program_buttons_row.addStretch()

        self.programs_table = QTableWidget(0, len(_PROGRAM_COLUMNS))
        self.programs_table.setHorizontalHeaderLabels(_PROGRAM_COLUMNS)
        self.programs_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.programs_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.programs_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.programs_table.cellDoubleClicked.connect(self._open_program_configuration)

        new_run_button = QPushButton("+ New Run")
        new_run_button.setProperty("accent", True)
        new_run_button.clicked.connect(self._new_run)
        archive_run_button = QPushButton("Archive Selected Run")
        archive_run_button.setProperty("danger", True)
        archive_run_button.clicked.connect(self._archive_selected_run)
        restore_run_button = QPushButton("Restore Selected Run")
        restore_run_button.clicked.connect(self._restore_selected_run)

        run_buttons_row = QHBoxLayout()
        for button in (new_run_button, archive_run_button, restore_run_button):
            run_buttons_row.addWidget(button)
        run_buttons_row.addStretch()

        self.runs_table = QTableWidget(0, len(_RUN_COLUMNS))
        self.runs_table.setHorizontalHeaderLabels(_RUN_COLUMNS)
        self.runs_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.runs_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.runs_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.runs_table.cellDoubleClicked.connect(self._open_selected_run)

        layout = QVBoxLayout(self)
        layout.addWidget(title)
        layout.addLayout(top_row)
        layout.addWidget(_subheading("Programs (double-click to edit configuration)"))
        layout.addLayout(program_buttons_row)
        layout.addWidget(self.programs_table)
        layout.addWidget(_subheading("Runs (double-click to open)"))
        layout.addLayout(run_buttons_row)
        layout.addWidget(self.runs_table)

        self.refresh()

    def refresh(self) -> None:
        include_archived = self.show_archived_checkbox.isChecked()

        programs = self.context.programs.list_all(include_archived=include_archived)
        self.programs_table.setRowCount(len(programs))
        for row, program in enumerate(programs):
            version_text = str(program.active_configuration_version) if program.active_configuration_version is not None else "None yet"
            status_text = "Active" if program.active else "Archived"
            values = (program.program_id, program.name, version_text, status_text)
            for column, value in enumerate(values):
                self.programs_table.setItem(row, column, _muted_item(value, muted=not program.active))

        runs = self.context.runs.list_all(include_archived=include_archived)
        self.runs_table.setRowCount(len(runs))
        for row, run in enumerate(runs):
            is_archived = run.archived_at is not None
            self.runs_table.setItem(row, 0, _muted_item(run.run_id, muted=is_archived))
            self.runs_table.setItem(row, 1, _muted_item(run.program_id, muted=is_archived))
            state_item = _muted_item(state_label(run.state), muted=is_archived)
            if not is_archived:
                state_item.setForeground(QBrush(QColor(state_color(run.state))))
                font = state_item.font()
                font.setBold(True)
                state_item.setFont(font)
            self.runs_table.setItem(row, 2, state_item)
            self.runs_table.setItem(row, 3, _muted_item(format_timestamp(run.created_at), muted=is_archived))
            self.runs_table.setItem(row, 4, _muted_item("Archived" if is_archived else "Visible", muted=is_archived))

    def _new_program(self) -> None:
        dialog = NewProgramDialog(self.context, self)
        if dialog.exec():
            self.refresh()

    def _edit_selected_program_configuration(self) -> None:
        row = self.programs_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "No program selected", "Select a Program in the table first.")
            return
        self._open_program_configuration(row, 0)

    def _open_program_configuration(self, row: int, _column: int) -> None:
        program_id = self.programs_table.item(row, 0).text()
        dialog = ProgramConfigurationDialog(self.context, program_id, self)
        if dialog.exec():
            self.refresh()

    def _archive_selected_program(self) -> None:
        program_id = _selected_id(self.programs_table, self, "program")
        if program_id is None:
            return
        dialog = TypeToConfirmDialog(
            title="Archive Program",
            message=(
                f"Archive Program '{program_id}'? It will disappear from this Dashboard, along with all "
                "of its Runs. Nothing is deleted -- check \"Show archived\" above to find and restore it anytime."
            ),
            expected_text=program_id, parent=self,
        )
        if dialog.exec():
            dashboard_actions.archive_program(self.context, program_id=program_id)
            self.refresh()

    def _restore_selected_program(self) -> None:
        program_id = _selected_id(self.programs_table, self, "program")
        if program_id is None:
            return
        dashboard_actions.restore_program(self.context, program_id=program_id)
        self.refresh()

    def _new_run(self) -> None:
        if not self.context.programs.list_all():
            QMessageBox.information(self, "No programs yet", "Create a Program before creating a Run.")
            return
        dialog = NewRunDialog(self.context, self)
        if dialog.exec():
            self.refresh()
            if dialog.created_run is not None:
                self.on_open_run(dialog.created_run.run_id)

    def _archive_selected_run(self) -> None:
        run_id = _selected_id(self.runs_table, self, "run")
        if run_id is None:
            return
        dialog = TypeToConfirmDialog(
            title="Archive Run",
            message=(
                f"Archive Run '{run_id}'? It will disappear from this Dashboard. Nothing is deleted -- "
                "check \"Show archived\" above to find and restore it anytime."
            ),
            expected_text=run_id, parent=self,
        )
        if dialog.exec():
            dashboard_actions.archive_run(self.context, run_id=run_id)
            self.refresh()

    def _restore_selected_run(self) -> None:
        run_id = _selected_id(self.runs_table, self, "run")
        if run_id is None:
            return
        dashboard_actions.restore_run(self.context, run_id=run_id)
        self.refresh()

    def _open_selected_run(self, row: int, _column: int) -> None:
        run_id = self.runs_table.item(row, 0).text()
        self.on_open_run(run_id)


def _subheading(text: str) -> QLabel:
    label = QLabel(text)
    label.setProperty("subheading", True)
    return label


def _muted_item(text: str, *, muted: bool) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    if muted:
        item.setForeground(QBrush(_MUTED_TEXT_COLOR))
    return item


def _selected_id(table: QTableWidget, parent: QWidget, noun: str) -> str | None:
    row = table.currentRow()
    if row < 0:
        QMessageBox.information(parent, f"No {noun} selected", f"Select a {noun.title()} in the table first.")
        return None
    return table.item(row, 0).text()
