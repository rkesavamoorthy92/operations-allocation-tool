"""Coordinates QC report import and evaluation: CONSOLIDATED -> QC_COMPLETED
(PROJECT_SPEC.md sections 22-23).

Reuses the same file-reading and identifier-normalization building blocks
as the rest of the pipeline (infrastructure.tabular_import,
utils.identifiers) and the restricted, no-eval rule evaluator from
core.qc/core.qc_aggregation -- this module only wires them together and
persists the result.

QC report files are expected to use the same column headers as the rest
of the Run's file convention: the primary identifier's configured header,
the 'Allocated To' system column, and a configurable pass/fail result
column (default 'QC Result', values 'Pass'/'Fail', both overridable via
the program's qc configuration). This avoids inventing a second,
inconsistent column-mapping surface just for QC imports.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from operations_allocation.core.distribution import field_header
from operations_allocation.core.qc import QcMetricResult, parse_qc_rule
from operations_allocation.core.qc_aggregation import QcAuditRecord, QcReport, build_qc_report, parse_outcome
from operations_allocation.domain.exceptions import InvalidQcRuleError
from operations_allocation.domain.models import ArtifactType, RunState
from operations_allocation.domain.state_machine import ensure_transition
from operations_allocation.infrastructure.tabular_import import read_raw_table
from operations_allocation.utils.identifiers import NormalizationPolicy, normalize_identifier

_QC_REPORT_FILENAME = "qc_report.json"


class QcService:
    def __init__(self, *, runs: Any, snapshots: Any, file_artifacts: Any, audit: Any) -> None:
        self.runs, self.snapshots = runs, snapshots
        self.file_artifacts, self.audit = file_artifacts, audit

    def import_and_evaluate(self, *, run_id: str, file_path: Path | str) -> QcReport:
        run = self.runs.get(run_id)
        ensure_transition(run.state, RunState.QC_COMPLETED)
        snapshot = self.snapshots.get(run_id)
        configuration = snapshot.configuration["program_configuration"]

        rule_configs = configuration["qc"].get("rules", [])
        if not rule_configs:
            raise InvalidQcRuleError(f"Program '{run.program_id}' has no QC rules configured; cannot evaluate QC.")
        rules = [parse_qc_rule(rule) for rule in rule_configs]

        identifier_field_name = configuration["primary_identifier"]["field"]
        fields_by_name = {field["name"]: field for field in configuration["fields"]}
        identifier_header = field_header(fields_by_name[identifier_field_name])
        associate_header = field_header(fields_by_name["allocated_to"])
        result_header = configuration["qc"].get("result_column", "QC Result")
        pass_label = configuration["qc"].get("pass_label", "Pass")
        fail_label = configuration["qc"].get("fail_label", "Fail")
        policy = NormalizationPolicy.from_configuration(configuration["primary_identifier"])

        raw_table = read_raw_table(file_path)
        records = []
        for row in raw_table.rows:
            identifier = normalize_identifier(row[identifier_header], policy)
            associate_id = row[associate_header]
            outcome = parse_outcome(row[result_header], pass_label=pass_label, fail_label=fail_label)
            records.append(QcAuditRecord(identifier=identifier, associate_id=associate_id, outcome=outcome))

        report = build_qc_report(records, rules)
        payload = _serialize_report(report)
        artifact = self.file_artifacts.write_bytes(
            run_id=run_id,
            artifact_type=ArtifactType.QC,
            filename=_QC_REPORT_FILENAME,
            content=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        )

        self.runs.update_state(run_id, RunState.QC_COMPLETED)
        self.audit.record(
            run_id=run_id,
            program_id=run.program_id,
            action="RUN_QC_COMPLETED",
            previous_state=run.state,
            new_state=RunState.QC_COMPLETED,
            metadata={
                "audited_count": report.run_counts["audited_count"],
                "pass_count": report.run_counts["pass_count"],
                "fail_count": report.run_counts["fail_count"],
                "associate_count": len(report.associate_counts),
                "qc_report_artifact_sha256": artifact.sha256,
            },
        )
        return report


def _serialize_metric(metric: QcMetricResult) -> dict:
    return {
        "numerator": metric.numerator,
        "denominator": metric.denominator,
        "is_not_applicable": metric.is_not_applicable,
        "value": str(metric.value) if isinstance(metric.value, Decimal) else None,
    }


def _serialize_report(report: QcReport) -> dict:
    return {
        "run_counts": report.run_counts,
        "run_metrics": {name: _serialize_metric(metric) for name, metric in report.run_metrics.items()},
        "associate_counts": report.associate_counts,
        "associate_metrics": {
            associate_id: {name: _serialize_metric(metric) for name, metric in metrics.items()}
            for associate_id, metrics in report.associate_metrics.items()
        },
    }
