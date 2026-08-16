"""Parses a bulk Associate Roster file (.xlsx/.csv) into the same
associate dict shape ``ui.setup_dialogs.FreezeSetupDialog`` collects from
manual table entry (associate_id / name / email / active / target /
maximum_capacity). Pure logic only -- file I/O lives in
``infrastructure.tabular_import`` (ARCHITECTURE.md section 6.2's
Excel/CSV -> Raw table -> mapping split applies here too).

Header matching is case/whitespace-insensitive and accepts a few common
synonyms so a roster exported from Excel/Workday/wherever doesn't need to
be reformatted by hand first -- but a column that cannot be matched to a
required field is a clear, named error rather than a silently empty
column (AGENTS.md section 29: operator-friendly error messages).
"""

from __future__ import annotations

from operations_allocation.core.column_mapping import RawTable
from operations_allocation.domain.exceptions import InvalidAssociateConfigurationError

_HEADER_ALIASES: dict[str, tuple[str, ...]] = {
    "associate_id": ("associate id", "associateid", "id"),
    "name": ("name", "associate name"),
    "email": ("email", "email address"),
    "target": ("target",),
    "maximum_capacity": ("max capacity", "maximum capacity", "maxcapacity"),
}
_REQUIRED_FIELDS = ("associate_id", "name")


def parse_associate_roster(table: RawTable) -> list[dict]:
    """Return associate dicts ready for ``FreezeSetupDialog``/``freeze_setup``.

    Raises :class:`InvalidAssociateConfigurationError` if a required
    column is missing from the header, or if Target/Max Capacity contain
    something other than a non-negative whole number. Rows with a blank
    Associate ID are skipped (the same tolerance manual entry has for a
    stray blank row).
    """
    column_by_field = _match_columns(table.headers)
    missing = [field for field in _REQUIRED_FIELDS if field not in column_by_field]
    if missing:
        raise InvalidAssociateConfigurationError(
            f"Associate roster file is missing required column(s): {', '.join(missing)}. "
            "Expected headers like 'Associate ID', 'Name', 'Email', 'Target', 'Max Capacity'."
        )

    associates = []
    for row_number, row in enumerate(table.rows, start=2):  # header occupies row 1
        associate_id = _cell(row, column_by_field.get("associate_id"))
        if not associate_id:
            continue
        associates.append({
            "associate_id": associate_id,
            "name": _cell(row, column_by_field.get("name")),
            "email": _cell(row, column_by_field.get("email")),
            "active": True,
            "target": _int_cell(row, column_by_field.get("target"), row_number, "Target"),
            "maximum_capacity": _int_cell(row, column_by_field.get("maximum_capacity"), row_number, "Max Capacity"),
        })
    return associates


def _match_columns(headers: tuple[str, ...]) -> dict[str, str]:
    normalized = {_normalize(header): header for header in headers}
    matched = {}
    for field, aliases in _HEADER_ALIASES.items():
        for alias in aliases:
            if alias in normalized:
                matched[field] = normalized[alias]
                break
    return matched


def _normalize(header: str) -> str:
    return " ".join(header.strip().lower().split())


def _cell(row: dict, column: str | None) -> str:
    if column is None:
        return ""
    value = row.get(column)
    return value.strip() if isinstance(value, str) else (value or "")


def _int_cell(row: dict, column: str | None, row_number: int, label: str) -> int:
    raw = _cell(row, column)
    if not raw:
        return 0
    try:
        value = int(raw)
    except ValueError as error:
        raise InvalidAssociateConfigurationError(f"Row {row_number}: '{label}' must be a whole number, got '{raw}'.") from error
    if value < 0:
        raise InvalidAssociateConfigurationError(f"Row {row_number}: '{label}' must not be negative, got '{raw}'.")
    return value
