"""Column mapping — Excel/CSV raw rows -> canonical field names.

Implements the "Column mapping (from Run Configuration Snapshot)" stage of
the File Processing pipeline (ARCHITECTURE.md section 6.2):

    Excel/CSV -> Raw table -> Column mapping -> Canonical item records
    -> Core engines -> Output mappers -> Excel/CSV artifacts

Pure logic only -- no file I/O (that lives in
``infrastructure.tabular_import``). Column mapping never assumes column
order (AGENTS.md section 26): every canonical field is located strictly by
its configured source column *name*, taken from the Run Configuration
Snapshot's ``column_mappings`` (built by RunOrchestrationService from each
field's ``source_column``).

System/generated fields (e.g. ``allocated_to``) have no source column --
they do not exist yet at import time and are added by later stages
(Allocation, Consolidation) -- so they are intentionally omitted from the
mapped canonical rows here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from operations_allocation.domain.exceptions import ColumnMappingError


@dataclass(frozen=True, slots=True)
class RawTable:
    """A parsed, not-yet-mapped Excel/CSV table: exact header names, in
    file order, plus rows keyed by that same header text."""

    headers: tuple[str, ...]
    rows: tuple[Mapping[str, str | None], ...]


def map_rows(table: RawTable, column_mappings: Mapping[str, str | None]) -> list[dict[str, str | None]]:
    """Map a :class:`RawTable` to canonical field names.

    Raises :class:`ColumnMappingError` with an operator-friendly message
    (AGENTS.md section 29) if a configured source column is entirely
    absent from the file's header -- this is a file-structure problem,
    distinct from a per-row blank/missing value which the Validation
    Engine handles.
    """
    header_set = set(table.headers)
    source_columns = {name: column for name, column in column_mappings.items() if column is not None}
    missing = sorted(column for column in source_columns.values() if column not in header_set)
    if missing:
        raise ColumnMappingError(f"Required column(s) could not be found in the uploaded file: {', '.join(missing)}.")

    return [
        {canonical_name: row.get(source_column) for canonical_name, source_column in source_columns.items()}
        for row in table.rows
    ]
