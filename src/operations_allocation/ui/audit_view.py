"""Read-only Audit Log viewer (PROJECT_SPEC.md section 27): "the audit
history must allow the user to understand how a run was processed."
Purely a renderer over AuditRepository.for_run() -- no computation.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QDialog, QHeaderView, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget


_COLUMNS = ("Timestamp", "Action", "Previous State", "New State", "OS User", "Details")


class AuditLogDialog(QDialog):
    def __init__(self, context: Any, run_id: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Audit Log — {run_id}")
        self.resize(900, 500)

        events = context.audit_repository.for_run(run_id)
        table = QTableWidget(len(events), len(_COLUMNS))
        table.setHorizontalHeaderLabels(_COLUMNS)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        for row_index, event in enumerate(events):
            table.setItem(row_index, 0, QTableWidgetItem(event["occurred_at"]))
            table.setItem(row_index, 1, QTableWidgetItem(event["action"]))
            table.setItem(row_index, 2, QTableWidgetItem(event["previous_state"] or ""))
            table.setItem(row_index, 3, QTableWidgetItem(event["new_state"] or ""))
            table.setItem(row_index, 4, QTableWidgetItem(event["os_username"]))
            table.setItem(row_index, 5, QTableWidgetItem(event["metadata_json"] or ""))

        layout = QVBoxLayout(self)
        layout.addWidget(table)
