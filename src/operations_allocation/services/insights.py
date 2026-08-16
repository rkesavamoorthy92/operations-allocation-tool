"""Composes the pure core.insights functions with real Run data: the
AllocationResult, Consolidation's reconciliation artifact, the QC report
artifact, error artifacts, and the previous COMPLETED Run for the same
program (PROJECT_SPEC.md section 25-26).

Every artifact read here is optional -- a Run may not have reached
Consolidation/QC/Errors yet, or may have skipped optional steps like
error generation. Missing data means the corresponding insight is simply
None/empty, never a crash and never a silently fabricated number.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from operations_allocation.core.insights import (
    HistoricalComparison,
    allocation_utilization,
    build_historical_comparison,
    completion_rate,
    detect_outliers,
    error_frequency,
    top_error_categories,
)
from operations_allocation.domain.models import RunState

_RECONCILIATION_FILENAME = "reconciliation.json"
_QC_REPORT_FILENAME = "qc_report.json"
_GENERATED_ERRORS_FILENAME = "generated_errors.json"
_IMPORTED_ERRORS_FILENAME = "imported_errors.json"


@dataclass(frozen=True, slots=True)
class InsightsReport:
    allocation_utilization: dict[str, Decimal | None]
    completion_rate: Decimal | None
    top_error_categories: tuple[tuple[str, int], ...]
    error_frequency: Decimal | None
    associate_performance: dict[str, Decimal | None]
    outliers: tuple[str, ...]
    historical: HistoricalComparison


class InsightsService:
    def __init__(self, *, runs: Any, allocation_results: Any, file_artifacts: Any) -> None:
        self.runs, self.allocation_results, self.file_artifacts = runs, allocation_results, file_artifacts

    def generate(self, *, run_id: str) -> InsightsReport:
        run = self.runs.get(run_id)
        allocation_result = self._safe_allocation_result(run_id)
        reconciliation = self._read_json_artifact(run_id, _RECONCILIATION_FILENAME)
        qc_report = self._read_json_artifact(run_id, _QC_REPORT_FILENAME)
        errors = self._read_error_records(run_id)

        utilization = allocation_utilization(_assignment_dicts(allocation_result)) if allocation_result else {}
        completion = None
        if reconciliation is not None:
            summary = reconciliation["summary"]
            completion = completion_rate(allocated_count=summary["allocated_count"], unique_returned_count=summary["unique_returned_count"])

        performance = _associate_qc_scores(qc_report)
        frequency = None
        if qc_report is not None:
            frequency = error_frequency(error_count=len(errors), audited_count=qc_report["run_counts"]["audited_count"])

        previous_payload = self._previous_completed_run_payload(run.program_id, run_id)
        current_qc = _qc_score(qc_report)
        current_error_rate = _error_rate(qc_report)
        current_missing = len(reconciliation["summary"]["missing_identifiers"]) if reconciliation is not None else None
        current_duplicate = reconciliation["summary"]["duplicate_count"] if reconciliation is not None else None
        historical = build_historical_comparison(
            current_qc_score=current_qc, current_error_rate=current_error_rate,
            current_missing_count=current_missing, current_duplicate_count=current_duplicate,
            previous=previous_payload,
        )

        return InsightsReport(
            allocation_utilization=utilization,
            completion_rate=completion,
            top_error_categories=top_error_categories([e["category"] for e in errors]),
            error_frequency=frequency,
            associate_performance=performance,
            outliers=detect_outliers(performance),
            historical=historical,
        )

    def _safe_allocation_result(self, run_id: str) -> Any | None:
        try:
            return self.allocation_results.get(run_id)
        except Exception:
            return None

    def _read_json_artifact(self, run_id: str, filename: str) -> dict | None:
        matching = [a for a in self.file_artifacts.list_for_run(run_id) if a.original_filename == filename]
        if not matching:
            return None
        return json.loads(self.file_artifacts.read_bytes(matching[0]))

    def _read_error_records(self, run_id: str) -> list[dict]:
        records = []
        for filename in (_GENERATED_ERRORS_FILENAME, _IMPORTED_ERRORS_FILENAME):
            payload = self._read_json_artifact(run_id, filename)
            if payload:
                records.extend(payload)
        return records

    def _previous_completed_run_payload(self, program_id: str, current_run_id: str) -> dict | None:
        candidates = [
            run for run in self.runs.list_all()
            if run.program_id == program_id and run.state is RunState.COMPLETED and run.run_id != current_run_id
        ]
        if not candidates:
            return None
        previous_run = max(candidates, key=lambda run: run.created_at)
        qc_report = self._read_json_artifact(previous_run.run_id, _QC_REPORT_FILENAME)
        reconciliation = self._read_json_artifact(previous_run.run_id, _RECONCILIATION_FILENAME)
        return {
            "qc_score": _qc_score(qc_report),
            "error_rate": _error_rate(qc_report),
            "missing_count": len(reconciliation["summary"]["missing_identifiers"]) if reconciliation else None,
            "duplicate_count": reconciliation["summary"]["duplicate_count"] if reconciliation else None,
        }


def _assignment_dicts(allocation_result: Any) -> list[dict]:
    return [{"associate_id": a.associate_id, "planned_count": a.planned_count, "maximum_capacity": a.maximum_capacity} for a in allocation_result.assignments]


def _associate_qc_scores(qc_report: dict | None) -> dict[str, Decimal | None]:
    if qc_report is None:
        return {}
    scores = {}
    for associate_id, metrics in qc_report["associate_metrics"].items():
        metric = metrics.get("qc_score")
        scores[associate_id] = Decimal(metric["value"]) if metric and metric["value"] is not None else None
    return scores


def _qc_score(qc_report: dict | None) -> Decimal | None:
    if qc_report is None:
        return None
    metric = qc_report["run_metrics"].get("qc_score")
    return Decimal(metric["value"]) if metric and metric["value"] is not None else None


def _error_rate(qc_report: dict | None) -> Decimal | None:
    if qc_report is None:
        return None
    metric = qc_report["run_metrics"].get("error_rate")
    return Decimal(metric["value"]) if metric and metric["value"] is not None else None
