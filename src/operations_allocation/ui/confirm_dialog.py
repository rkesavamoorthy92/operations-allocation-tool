"""A generic "type the ID to confirm" dialog for destructive-looking
actions (here: archiving a Program/Run). Nothing is actually erased by
what this dialog guards -- see ui.dashboard_actions -- but the
type-to-confirm friction is deliberate so it is never triggered by a
stray double-click.
"""

from __future__ import annotations

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QLineEdit, QVBoxLayout, QWidget


class TypeToConfirmDialog(QDialog):
    def __init__(self, *, title: str, message: str, expected_text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self._expected_text = expected_text

        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText(expected_text)
        self.input_field.textChanged.connect(self._sync_ok_enabled)

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        self._sync_ok_enabled()

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(message))
        layout.addWidget(QLabel(f"Type \"{expected_text}\" below to confirm:"))
        layout.addWidget(self.input_field)
        layout.addWidget(self.buttons)

    def _sync_ok_enabled(self) -> None:
        ok_button = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        ok_button.setEnabled(self.input_field.text() == self._expected_text)
