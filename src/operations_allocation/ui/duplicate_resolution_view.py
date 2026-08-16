"""Duplicate-identifier resolution dialog (PROJECT_SPEC.md section 8,
"Duplicate Product IDs"): the system never infers whether to exclude a
whole duplicate group or keep exactly one row -- a human must choose,
with a reason, for every group before Eligible Population can be frozen.

v1 scope note: uses one shared reason for every resolution made in a
single dialog session rather than a separate reason field per group.
This keeps the dialog usable when there are many duplicate groups; if
that turns out to be too coarse in practice, per-group reasons are a
straightforward follow-up (domain.models.DuplicateResolution already
supports a distinct reason per group).
"""

from __future__ import annotations

from datetime import datetime, timezone

from PySide6.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QGroupBox, QLabel, QMessageBox, QPlainTextEdit, QVBoxLayout, QWidget

from operations_allocation.core.validation import DuplicateGroup
from operations_allocation.domain.models import DuplicateResolution

_EXCLUDE_ALL = "Exclude all rows in this group"


class DuplicateResolutionDialog(QDialog):
    def __init__(self, duplicate_groups: tuple[DuplicateGroup, ...], resolved_by: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.duplicate_groups, self.resolved_by = duplicate_groups, resolved_by
        self.resolutions: list[DuplicateResolution] = []
        self.setWindowTitle("Resolve Duplicate Identifiers")
        self.resize(560, 480)

        self._combos: list[tuple[DuplicateGroup, QComboBox]] = []
        layout = QVBoxLayout(self)
        for group in duplicate_groups:
            box = QGroupBox(f"Duplicate identifier: {group.normalized_identifier}  ({len(group.row_indexes)} rows)")
            box_layout = QVBoxLayout()
            combo = QComboBox()
            combo.addItem(_EXCLUDE_ALL, None)
            for row_index, original_value in zip(group.row_indexes, group.original_values):
                combo.addItem(f"Keep row {row_index} (as entered: '{original_value}')", row_index)
            box_layout.addWidget(combo)
            box.setLayout(box_layout)
            layout.addWidget(box)
            self._combos.append((group, combo))

        layout.addWidget(QLabel("Reason (applies to every resolution made below):"))
        self.reason_field = QPlainTextEdit()
        self.reason_field.setPlaceholderText("Required: why are these duplicates being resolved this way?")
        layout.addWidget(self.reason_field)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_accept(self) -> None:
        reason = self.reason_field.toPlainText().strip()
        if not reason:
            QMessageBox.warning(self, "Reason required", "Enter a reason before resolving duplicates.")
            return
        resolved_at = datetime.now(timezone.utc)
        resolutions = []
        for group, combo in self._combos:
            kept_row_index = combo.currentData()
            action = "EXCLUDE_ALL" if kept_row_index is None else "KEEP_ROW"
            resolutions.append(DuplicateResolution(
                normalized_identifier=group.normalized_identifier, original_values=group.original_values,
                row_indexes=group.row_indexes, action=action, resolved_by=self.resolved_by,
                resolved_at=resolved_at, reason=reason, kept_row_index=kept_row_index,
            ))
        self.resolutions = resolutions
        self.accept()
