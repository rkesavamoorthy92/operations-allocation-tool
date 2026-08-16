"""Entry point for the desktop application: `python -m operations_allocation.ui.app`.

Creates the QApplication, builds the AppContext (real SQLite database in
the user's local application data directory), and shows the MainWindow.
Nothing else lives here -- this file exists so `python -m` has something
to run, not to hold logic.
"""

from __future__ import annotations

import sys


def main() -> int:
    from PySide6.QtWidgets import QApplication

    from operations_allocation.ui.app_context import AppContext
    from operations_allocation.ui.main_window import MainWindow
    from operations_allocation.ui.theme import apply_theme

    app = QApplication(sys.argv)
    apply_theme(app)
    context = AppContext.build()
    window = MainWindow(context)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
