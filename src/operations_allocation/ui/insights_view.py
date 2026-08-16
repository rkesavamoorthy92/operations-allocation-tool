"""Read-only dialog rendering an InsightsReport (PROJECT_SPEC.md section
25-26): allocation utilization, completion rate, error categories/
frequency, associate performance/outliers, and the historical comparison
against the previous COMPLETED Run for the same program. No calculation
happens here -- this only formats what services.insights already computed.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QDialog, QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from operations_allocation.ui.formatting import format_percentage, format_percentage_point_change


class InsightsDialog(QDialog):
    def __init__(self, report: Any, run_id: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Insights — {run_id}")
        self.resize(560, 640)

        layout = QVBoxLayout(self)
        layout.addWidget(_heading("Historical Comparison"))
        layout.addWidget(QLabel(_historical_text(report.historical)))

        layout.addWidget(_heading("Run Summary"))
        layout.addWidget(QLabel(
            f"Completion Rate: {format_percentage(report.completion_rate)}\n"
            f"Error Frequency: {format_percentage(report.error_frequency)}\n"
            f"Outliers: {', '.join(report.outliers) if report.outliers else 'None'}"
        ))

        layout.addWidget(_heading("Allocation Utilization"))
        layout.addWidget(_table(("Associate", "Utilization"), [(associate_id, format_percentage(value)) for associate_id, value in report.allocation_utilization.items()]))

        layout.addWidget(_heading("Associate Performance (QC Score)"))
        layout.addWidget(_table(("Associate", "QC Score"), [(associate_id, format_percentage(value)) for associate_id, value in report.associate_performance.items()]))

        layout.addWidget(_heading("Top Error Categories"))
        layout.addWidget(_table(("Category", "Count"), [(category, str(count)) for category, count in report.top_error_categories]))


def _heading(text: str) -> QLabel:
    label = QLabel(text)
    label.setStyleSheet("font-weight: bold; margin-top: 8px;")
    return label


def _table(headers: tuple[str, str], rows: list[tuple[str, str]]) -> QTableWidget:
    table = QTableWidget(len(rows), 2)
    table.setHorizontalHeaderLabels(list(headers))
    for row_index, (left, right) in enumerate(rows):
        table.setItem(row_index, 0, QTableWidgetItem(left))
        table.setItem(row_index, 1, QTableWidgetItem(right))
    return table


def _historical_text(historical: Any) -> str:
    if not historical.is_applicable:
        return "N/A — no previous COMPLETED Run exists for this program yet."
    return (
        f"QC Score: {format_percentage(historical.previous_qc_score)} → {format_percentage(historical.current_qc_score)} "
        f"({format_percentage_point_change(historical.current_qc_score, historical.previous_qc_score)})\n"
        f"Error Rate: {format_percentage(historical.previous_error_rate)} → {format_percentage(historical.current_error_rate)} "
        f"({format_percentage_point_change(historical.current_error_rate, historical.previous_error_rate)})\n"
        f"Missing Items: {historical.missing_count_previous} → {historical.missing_count_current}\n"
        f"Duplicates: {historical.duplicate_count_previous} → {historical.duplicate_count_current}"
    )
