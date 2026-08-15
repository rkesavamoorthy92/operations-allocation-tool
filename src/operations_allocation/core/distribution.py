"""Associate File Splitting — pure logic (PROJECT_SPEC.md section 15).

Builds, for one AllocationAssignment, the exact filename and header/row
content of that associate's Excel work file: source-owned fields are
pre-filled from the canonical source row, response-owned fields are left
blank for the associate to complete, and system-owned fields (Run ID,
Allocated To) are filled in by this stage. No file I/O here -- writing
actual .xlsx bytes lives in ``infrastructure.xlsx_writer``.

Column order always follows each field's configured ``output_order``
(AGENTS.md section 26, never assume column order/structure).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping, Sequence

from operations_allocation.domain.exceptions import AssignedItemNotFoundError, InvalidConfigurationError
from operations_allocation.domain.models import AllocationAssignment

_HEADER_OVERRIDES = {"allocated_to": "Allocated To", "run_id": "Run ID"}
_SYSTEM_FIELD_NAMES = frozenset(_HEADER_OVERRIDES)
_UNSAFE_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9 _-]+")


@dataclass(frozen=True, slots=True)
class AssociateFileContent:
    associate_id: str
    associate_name: str
    filename: str
    headers: tuple[str, ...]
    rows: tuple[tuple[str | None, ...], ...]


def sanitize_for_filename(text: str) -> str:
    """Replace filesystem-unsafe characters with underscores and collapse
    repeated whitespace, so associate names can never break a path."""
    cleaned = _UNSAFE_FILENAME_CHARS.sub("_", text).strip()
    return re.sub(r"\s+", "_", cleaned) or "unnamed"


def build_filename(pattern: str, *, program_id: str, run_id: str, associate_id: str, associate_name: str) -> str:
    tokens = {
        "PROGRAM": program_id,
        "RUN_ID": run_id,
        "ASSOCIATE_ID": associate_id,
        "ASSOCIATE_NAME": sanitize_for_filename(associate_name),
    }
    return pattern.format(**tokens)


def _field_header(field: Mapping[str, object]) -> str:
    name = str(field["name"])
    if name in _HEADER_OVERRIDES:
        return _HEADER_OVERRIDES[name]
    source_column = field.get("source_column")
    if isinstance(source_column, str) and source_column.strip():
        return source_column
    return name.replace("_", " ").title()


def _field_value(field: Mapping[str, object], *, canonical_row: Mapping[str, str | None], associate_id: str, run_id: str) -> str | None:
    ownership = field["ownership"]
    name = str(field["name"])
    if ownership == "source":
        return canonical_row.get(name)
    if ownership == "response":
        return None
    if ownership == "system":
        if name == "allocated_to":
            return associate_id
        if name == "run_id":
            return run_id
        raise InvalidConfigurationError(
            f"Unsupported system field '{name}'. Supported system fields in v1: {sorted(_SYSTEM_FIELD_NAMES)}."
        )
    raise InvalidConfigurationError(f"Field '{name}' has an unrecognized ownership '{ownership}'.")


def build_associate_file_content(
    *,
    assignment: AllocationAssignment,
    associate_name: str,
    fields: Sequence[Mapping[str, object]],
    canonical_rows_by_identifier: Mapping[str, Mapping[str, str | None]],
    run_id: str,
    program_id: str,
    filename_pattern: str,
) -> AssociateFileContent:
    ordered_fields = sorted(fields, key=lambda field: field["output_order"])
    headers = tuple(_field_header(field) for field in ordered_fields)

    rows: list[tuple[str | None, ...]] = []
    for identifier in assignment.assigned_identifiers:
        canonical_row = canonical_rows_by_identifier.get(identifier)
        if canonical_row is None:
            raise AssignedItemNotFoundError(
                f"Allocated identifier '{identifier}' for associate '{assignment.associate_id}' has no matching canonical source row."
            )
        rows.append(tuple(_field_value(field, canonical_row=canonical_row, associate_id=assignment.associate_id, run_id=run_id) for field in ordered_fields))

    filename = build_filename(filename_pattern, program_id=program_id, run_id=run_id, associate_id=assignment.associate_id, associate_name=associate_name)
    return AssociateFileContent(associate_id=assignment.associate_id, associate_name=associate_name, filename=filename, headers=headers, rows=tuple(rows))
