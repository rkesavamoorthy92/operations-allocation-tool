"""Top-level window: swaps between the Dashboard and a Run's detail view.
Owns navigation only -- no business logic (ARCHITECTURE.md section 9).
"""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QMainWindow, QStackedWidget

from operations_allocation.ui.dashboard_view import DashboardView
from operations_allocation.ui.run_detail_view import RunDetailView


class MainWindow(QMainWindow):
    def __init__(self, context: Any) -> None:
        super().__init__()
        self.context = context
        self.setWindowTitle("Operations Allocation Tool")
        self.resize(1000, 700)

        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        self.dashboard = DashboardView(context, on_open_run=self.open_run)
        self.stack.addWidget(self.dashboard)
        self.stack.setCurrentWidget(self.dashboard)

    def open_run(self, run_id: str) -> None:
        detail = RunDetailView(self.context, run_id, on_back=self.show_dashboard)
        self.stack.addWidget(detail)
        self.stack.setCurrentWidget(detail)

    def show_dashboard(self) -> None:
        self.dashboard.refresh()
        self.stack.setCurrentWidget(self.dashboard)
        # Drop every detail view except the dashboard so re-opening a Run
        # always builds a fresh one reflecting the latest state.
        for index in reversed(range(self.stack.count())):
            widget = self.stack.widget(index)
            if widget is not self.dashboard:
                self.stack.removeWidget(widget)
                widget.deleteLater()
