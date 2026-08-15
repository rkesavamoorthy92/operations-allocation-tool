"""Aggregates imported QC audit records into item/associate/run-level
counts and evaluates the Run's configured QC rules against them
(PROJECT_SPEC.md sections 22-23).

Pure logic -- reuses core.qc's restricted, no-eval rule evaluator for the
actual calculation; this module is only responsible for turning a flat
list of per-item pass/fail audit records into the counts that evaluator
needs at each of the three required levels.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Mapping, Sequence

from operations_allocation.core.qc import QcMetricResult, QcRule, evaluate_qc_rules
from operations_allocation.domain.exceptions import InvalidQcResultError


class QcOutcome(StrEnum):
    PASS = "pass"
    FAIL = "fail"


def parse_outcome(raw_value: object, *, pass_label: str, fail_label: str) -> QcOutcome:
    if isinstance(raw_value, str):
        if raw_value.strip().casefold() == pass_label.casefold():
            return QcOutcome.PASS
        if raw_value.strip().casefold() == fail_label.casefold():
            return QcOutcome.FAIL
    raise InvalidQcResultError(f"QC result value '{raw_value!r}' is not a recognized outcome. Expected '{pass_label}' or '{fail_label}'.")


@dataclass(frozen=True, slots=True)
class QcAuditRecord:
    identifier: str
    associate_id: str
    outcome: QcOutcome


def counts_for(records: Sequence[QcAuditRecord]) -> dict[str, int]:
    pass_count = sum(1 for r in records if r.outcome is QcOutcome.PASS)
    fail_count = sum(1 for r in records if r.outcome is QcOutcome.FAIL)
    return {"pass_count": pass_count, "fail_count": fail_count, "audited_count": pass_count + fail_count}


@dataclass(frozen=True, slots=True)
class QcReport:
    run_metrics: Mapping[str, QcMetricResult]
    run_counts: Mapping[str, int]
    associate_metrics: Mapping[str, Mapping[str, QcMetricResult]]
    associate_counts: Mapping[str, Mapping[str, int]]


def build_qc_report(records: Sequence[QcAuditRecord], rules: Sequence[QcRule]) -> QcReport:
    run_counts = counts_for(records)
    run_metrics = evaluate_qc_rules(list(rules), run_counts)

    by_associate: dict[str, list[QcAuditRecord]] = {}
    for record in records:
        by_associate.setdefault(record.associate_id, []).append(record)

    associate_counts = {associate_id: counts_for(recs) for associate_id, recs in by_associate.items()}
    associate_metrics = {associate_id: evaluate_qc_rules(list(rules), counts) for associate_id, counts in associate_counts.items()}

    return QcReport(run_metrics=run_metrics, run_counts=run_counts, associate_metrics=associate_metrics, associate_counts=associate_counts)
