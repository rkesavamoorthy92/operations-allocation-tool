"""Program Configuration authoring UI (PROJECT_SPEC.md's Program
Configuration Service, ARCHITECTURE.md section 3).

Design choice: this is a validated JSON editor, not a bespoke set of
widgets mirroring every nested section of the schema (fields, input/
response columns, sampling, allocation, tie-breaking, QC rules, error
taxonomy, filename pattern, email templates). The schema is rich and
config.program_config.validate_program_configuration() is already the
single source of truth for what's legal -- reusing it directly here
means this editor can never drift out of sync with what the rest of the
system actually accepts, and it avoids building a dozen specialized
table-editing widgets that would mostly duplicate each other. If
hand-holding non-technical authors turns out to be necessary later,
dedicated section widgets are a natural follow-up -- but that's
speculative right now (YAGNI).
"""

from __future__ import annotations

import json
from typing import Any

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QPlainTextEdit, QVBoxLayout, QWidget

from operations_allocation.config.program_config import validate_program_configuration
from operations_allocation.domain.exceptions import InvalidConfigurationError


def starter_template(program_id: str, program_name: str) -> dict[str, Any]:
    """A minimal, already-valid configuration skeleton so authors edit a
    working document rather than starting from a blank page.

    The email templates and filename pattern here are deliberately
    complete, working defaults (not empty placeholders) -- an empty
    ``templates`` dict or a filename pattern missing {ASSOCIATE_ID} both
    look "valid" to validate_program_configuration() but fail loudly
    later (a missing-template error the moment emails are sent, or a
    filename collision the moment a second associate is distributed to).
    Authors can still edit or replace these tokens/templates freely.
    """
    return {
        "program_id": program_id, "program_name": program_name, "version": 1,
        "primary_identifier": {"field": "product_id", "case_sensitive": True, "normalization": {"trim_whitespace": True}},
        "input_columns": [{"name": "product_id", "column": "Product ID", "ownership": "source", "data_type": "string", "required": True}],
        "response_columns": [{"name": "partner_feedback", "column": "Partner Feedback", "ownership": "response", "data_type": "string", "required": False}],
        "fields": [
            {"name": "product_id", "source_column": "Product ID", "ownership": "source", "data_type": "string", "required": True, "output_order": 0},
            {"name": "allocated_to", "ownership": "system", "data_type": "string", "required": False, "output_order": 1},
        ],
        "validation": {}, "sampling": {"allowed_methods": ["percentage", "count"]},
        "allocation": {"strategy": "target_capacity"}, "tie_breaking": {"field": "associate_id"},
        "qc": {}, "errors": {},
        "filename": {"pattern": "{PROGRAM}_{ASSOCIATE_ID}_{ASSOCIATE_NAME}_{RUN_ID}.xlsx"},
        "email": {"templates": {
            "individual_subject": "{{program_name}} {{run_id}} -- Your Allocated Items ({{item_count}})",
            "individual_body": "Hi {{associate_name}},\n\nYou have been allocated {{item_count}} item(s) for {{program_name}} Run {{run_id}}.\nPlease complete and return the attached file by {{due_date}}.\n\nThanks!",
            "consolidated_subject": "{{program_name}} {{run_id}} -- Allocation Summary",
            "consolidated_body": "Team,\n\n{{item_count}} item(s) have been allocated across the team for {{program_name}} Run {{run_id}}.\nPlease return completed files by {{due_date}}.\n\nThanks!",
        }},
    }


class ProgramConfigurationDialog(QDialog):
    def __init__(self, context: Any, program_id: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.context, self.program_id = context, program_id
        self.saved = False
        self.setWindowTitle(f"Program Configuration — {program_id}")
        self.resize(700, 640)

        program = context.programs.get(program_id)
        if program.active_configuration_version is not None:
            document = context.programs.configuration(program_id, program.active_configuration_version)
            document["version"] = program.active_configuration_version + 1
            hint = f"Editing a new version (current active version is {program.active_configuration_version})."
        else:
            document = starter_template(program_id, program.name)
            hint = "No configuration exists yet -- editing a starter template."

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(hint))

        self.editor = QPlainTextEdit(json.dumps(document, indent=2, sort_keys=True))
        self.editor.setFont(QFont("Consolas", 10))
        layout.addWidget(self.editor)

        self.status_label = QLabel("")
        layout.addWidget(self.status_label)

        buttons = QDialogButtonBox()
        validate_button = buttons.addButton("Validate", QDialogButtonBox.ButtonRole.ActionRole)
        validate_button.clicked.connect(self._on_validate)
        save_button = buttons.addButton("Save New Version", QDialogButtonBox.ButtonRole.AcceptRole)
        save_button.clicked.connect(self._on_save)
        cancel_button = buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
        cancel_button.clicked.connect(self.reject)
        layout.addWidget(buttons)

    def _parse_and_validate(self) -> dict[str, Any] | None:
        try:
            config = json.loads(self.editor.toPlainText())
        except json.JSONDecodeError as error:
            self._set_status(f"Invalid JSON: {error}", ok=False)
            return None
        try:
            validate_program_configuration(config)
        except InvalidConfigurationError as error:
            self._set_status(f"Invalid configuration: {error}", ok=False)
            return None
        return config

    def _on_validate(self) -> None:
        if self._parse_and_validate() is not None:
            self._set_status("Valid.", ok=True)

    def _on_save(self) -> None:
        config = self._parse_and_validate()
        if config is None:
            return
        self.context.program_configuration.save_version(config)
        self.saved = True
        self.accept()

    def _set_status(self, message: str, *, ok: bool) -> None:
        self.status_label.setText(message)
        self.status_label.setStyleSheet(f"color: {'green' if ok else 'red'};")
