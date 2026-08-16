"""Error classification engine — restricted declarative model, no eval().

Implements PROJECT_SPEC.md section 24: error categories, types, fields,
severity, and classification rules are entirely program-defined, never
hard-coded from any other Operations program. Like core.qc, the only way
a classification rule can affect behavior is through a closed set of
literal field-equality checks -- there is no expression execution path,
so a maliciously or carelessly crafted rule document cannot do anything
beyond matching plain string fields.

Supports both of section 24's required sources:

* GENERATED errors -- built from Consolidation's own detected exceptions
  (missing/duplicate/unexpected/wrong_associate/incomplete rows), run
  through the program's own classification rules so two programs can
  describe the same underlying problem with entirely different
  taxonomies (PROJECT_SPEC.md section 24, "MX PT may have one error
  structure while another program may use a completely different
  structure").
* IMPORTED errors -- rows from an external error report, trusted as
  already-classified when category/type/severity are present, and
  classified via the same rules only for whatever is missing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from operations_allocation.domain.exceptions import InvalidErrorRuleError
from operations_allocation.domain.models import ErrorRecord

UNCLASSIFIED = "unclassified"


@dataclass(frozen=True, slots=True)
class ErrorClassificationRule:
    match: Mapping[str, str]
    """Field name -> required exact value. A row matches only if every
    entry here matches exactly (case-sensitive, no partial/regex match)."""
    category: str
    error_type: str
    severity: str


def parse_classification_rule(raw: Mapping[str, object]) -> ErrorClassificationRule:
    match = raw.get("match")
    category = raw.get("category")
    error_type = raw.get("type")
    severity = raw.get("severity")
    if not isinstance(match, Mapping) or not match or any(not isinstance(k, str) or not isinstance(v, str) for k, v in match.items()):
        raise InvalidErrorRuleError("Error classification rule 'match' must be a non-empty mapping of string field names to string values.")
    for label, value in (("category", category), ("type", error_type), ("severity", severity)):
        if not isinstance(value, str) or not value.strip():
            raise InvalidErrorRuleError(f"Error classification rule requires a non-empty '{label}'.")
    return ErrorClassificationRule(match=dict(match), category=category, error_type=error_type, severity=severity)


def classify(fields: Mapping[str, str | None], rules: Sequence[ErrorClassificationRule]) -> tuple[str, str, str]:
    """Return (category, type, severity) for the first rule whose every
    match condition is satisfied by ``fields``, in configured order. If no
    rule matches, returns the explicit UNCLASSIFIED marker for all three
    -- never a silently guessed category."""
    for rule in rules:
        if all(fields.get(field_name) == expected for field_name, expected in rule.match.items()):
            return rule.category, rule.error_type, rule.severity
    return UNCLASSIFIED, UNCLASSIFIED, UNCLASSIFIED


def build_error_report_rows(records: Sequence[ErrorRecord]) -> tuple[tuple[str, ...], tuple[tuple[object, ...], ...]]:
    """Flatten classified error records into a single exportable table
    (same 'fixed columns + union of dynamic fields, in first-appearance
    order' pattern as core.consolidation.build_consolidated_export, so
    Error Reporting's export has the same shape/rationale as
    Consolidation's rather than a bespoke one-off layout).

    Returns (headers, rows). Fixed columns come first (Identifier,
    Associate ID, Category, Type, Severity, Source), followed by every
    key seen across any record's ``fields`` mapping -- this covers both
    GENERATED records (whose fields carry e.g. 'disposition') and
    IMPORTED records (whose fields are that report's own raw columns).
    """
    field_names: list[str] = []
    for record in records:
        for key in record.fields.keys():
            if key not in field_names:
                field_names.append(key)
    headers = ("Identifier", "Associate ID", "Category", "Type", "Severity", "Source", *field_names)
    rows = tuple(
        (
            record.identifier, record.associate_id, record.category, record.error_type,
            record.severity, record.source.value, *(record.fields.get(name) for name in field_names),
        )
        for record in records
    )
    return headers, rows
