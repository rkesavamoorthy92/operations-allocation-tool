"""Coordinates Error Reporting (PROJECT_SPEC.md section 24): generating
errors from Consolidation's own detected exceptions, and importing an
external error report. Informational -- does not gate any Run state
transition (section 26 only requires Consolidation finalized and QC
completed for COMPLETED).

Error rules are read from the Run Configuration Snapshot, same as every
other engine in this pipeline, so error processing for a Run always uses
the rules frozen at that Run's setup time even if the program's
configuration changes later.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from operations_allocation.core.distribution import field_header
from operations_allocation.core.errors import ErrorClassificationRule, build_error_report_rows, classify, parse_classification_rule
from operations_allocation.domain.exceptions import InvalidErrorRecordError, PersistenceError
from operations_allocation.domain.models import ArtifactType, ErrorRecord, ErrorSource
from operations_allocation.infrastructure.tabular_import import read_raw_table
from operations_allocation.infrastructure.xlsx_writer import write_multi_sheet_workbook
from operations_allocation.utils.identifiers import NormalizationPolicy, normalize_identifier

_GENERATED_ERRORS_FILENAME = "generated_errors.json"
_IMPORTED_ERRORS_FILENAME = "imported_errors.json"
_RECONCILIATION_FILENAME = "reconciliation.json"


class ErrorService:
    def __init__(self, *, snapshots: Any, file_artifacts: Any, audit: Any) -> None:
        self.snapshots, self.file_artifacts, self.audit = snapshots, file_artifacts, audit

    def generate_from_consolidation(self, *, run_id: str) -> tuple[ErrorRecord, ...]:
        snapshot = self.snapshots.get(run_id)
        program_id = snapshot.configuration["program_configuration"]["program_id"]
        rules = _load_rules(snapshot)

        reconciliation_artifact = _find_artifact(self.file_artifacts, run_id, _RECONCILIATION_FILENAME)
        payload = json.loads(self.file_artifacts.read_bytes(reconciliation_artifact))

        records = []
        for item in payload["reconciled_rows"]:
            if item["disposition"] == "matched":
                continue
            fields = {"disposition": item["disposition"], **{k: v for k, v in item["row"].items()}}
            category, error_type, severity = classify(fields, rules)
            records.append(ErrorRecord(
                run_id=run_id, identifier=item["identifier"], associate_id=item["associate_id"],
                category=category, error_type=error_type, severity=severity, source=ErrorSource.GENERATED, fields=fields,
            ))
        for identifier in payload["summary"]["missing_identifiers"]:
            fields = {"disposition": "missing"}
            category, error_type, severity = classify(fields, rules)
            records.append(ErrorRecord(
                run_id=run_id, identifier=identifier, associate_id=None,
                category=category, error_type=error_type, severity=severity, source=ErrorSource.GENERATED, fields=fields,
            ))

        artifact = self.file_artifacts.write_bytes(
            run_id=run_id, artifact_type=ArtifactType.ERRORS, filename=_GENERATED_ERRORS_FILENAME,
            content=json.dumps([_serialize(r) for r in records], ensure_ascii=False).encode("utf-8"),
        )
        self.audit.record(run_id=run_id, program_id=program_id, action="ERRORS_GENERATED", metadata={"error_count": len(records), "artifact_sha256": artifact.sha256})
        return tuple(records)

    def import_errors(self, *, run_id: str, file_path: Path | str) -> tuple[ErrorRecord, ...]:
        snapshot = self.snapshots.get(run_id)
        configuration = snapshot.configuration["program_configuration"]
        program_id = configuration["program_id"]
        rules = _load_rules(snapshot)

        identifier_field_name = configuration["primary_identifier"]["field"]
        fields_by_name = {field["name"]: field for field in configuration["fields"]}
        identifier_header = field_header(fields_by_name[identifier_field_name])
        associate_header = field_header(fields_by_name["allocated_to"])
        policy = NormalizationPolicy.from_configuration(configuration["primary_identifier"])

        raw_table = read_raw_table(file_path)
        records = []
        for row in raw_table.rows:
            raw_identifier = row.get(identifier_header)
            if not isinstance(raw_identifier, str) or not raw_identifier.strip():
                raise InvalidErrorRecordError(f"Imported error report row is missing a value for '{identifier_header}'.")
            identifier = normalize_identifier(raw_identifier, policy)
            associate_id = row.get(associate_header)

            category = row.get("Category") or None
            error_type = row.get("Type") or None
            severity = row.get("Severity") or None
            if category is None or error_type is None or severity is None:
                classified_category, classified_type, classified_severity = classify(row, rules)
                category = category or classified_category
                error_type = error_type or classified_type
                severity = severity or classified_severity

            records.append(ErrorRecord(
                run_id=run_id, identifier=identifier, associate_id=associate_id,
                category=category, error_type=error_type, severity=severity, source=ErrorSource.IMPORTED, fields=dict(row),
            ))

        artifact = self.file_artifacts.write_bytes(
            run_id=run_id, artifact_type=ArtifactType.ERRORS, filename=_IMPORTED_ERRORS_FILENAME,
            content=json.dumps([_serialize(r) for r in records], ensure_ascii=False).encode("utf-8"),
        )
        self.audit.record(run_id=run_id, program_id=program_id, action="ERRORS_IMPORTED", metadata={"error_count": len(records), "artifact_sha256": artifact.sha256})
        return tuple(records)

    def list_records(self, *, run_id: str) -> tuple[ErrorRecord, ...]:
        """Read back every error record persisted for this Run so far
        (both GENERATED and IMPORTED, if both were ever run), for display
        or export. Returns an empty tuple if no errors have been
        generated/imported yet -- that's a legitimate state, not an error."""
        records: list[ErrorRecord] = []
        for filename in (_GENERATED_ERRORS_FILENAME, _IMPORTED_ERRORS_FILENAME):
            matching = [a for a in self.file_artifacts.list_for_run(run_id) if a.original_filename == filename]
            if not matching:
                continue
            payload = json.loads(self.file_artifacts.read_bytes(matching[0]))
            records.extend(_deserialize(item) for item in payload)
        return tuple(records)

    def export_report(self, *, run_id: str) -> bytes:
        """Build a downloadable .xlsx of every error recorded for this Run
        so far. Reuses the same multi-sheet writer Consolidation uses
        (infrastructure.xlsx_writer) rather than a bespoke export path."""
        records = self.list_records(run_id=run_id)
        headers, rows = build_error_report_rows(records)
        return write_multi_sheet_workbook({"Errors": (headers, rows)})


def _load_rules(snapshot: Any) -> list[ErrorClassificationRule]:
    raw_rules = snapshot.configuration["program_configuration"]["errors"].get("classification_rules", [])
    return [parse_classification_rule(rule) for rule in raw_rules]


def _find_artifact(file_artifacts: Any, run_id: str, filename: str) -> Any:
    matching = [artifact for artifact in file_artifacts.list_for_run(run_id) if artifact.original_filename == filename]
    if not matching:
        raise PersistenceError(f"Run '{run_id}' does not have a '{filename}' artifact yet.")
    return matching[0]


def _serialize(record: ErrorRecord) -> dict:
    return {
        "run_id": record.run_id, "identifier": record.identifier, "associate_id": record.associate_id,
        "category": record.category, "type": record.error_type, "severity": record.severity,
        "source": record.source.value, "fields": dict(record.fields),
    }


def _deserialize(payload: Mapping[str, Any]) -> ErrorRecord:
    return ErrorRecord(
        run_id=payload["run_id"], identifier=payload["identifier"], associate_id=payload["associate_id"],
        category=payload["category"], error_type=payload["type"], severity=payload["severity"],
        source=ErrorSource(payload["source"]), fields=dict(payload["fields"]),
    )
