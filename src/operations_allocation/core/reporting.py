"""Pure row-building for the Run Summary Report (ARCHITECTURE.md section
4.11, "Reporting Service" -- "Produce Run-level and program-level
reports" / "export operational summaries").

Deliberately does no new computation of its own: every number here was
already derived by core.insights (via services.insights.InsightsReport).
This module's only job is arranging that already-computed data into
exportable (headers, rows) tables, the same shape core.errors and
core.consolidation use for their own exports -- one shareable .xlsx a
manager can ask for, instead of requiring someone to separately open the
Insights dialog, the Error Report export, and the Consolidated export.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

_TableRows = tuple[tuple[object, ...], ...]
_Table = tuple[tuple[str, ...], _TableRows]


@dataclass(frozen=True, slots=True)
class RunSummaryContext:
    """Identity/metadata fields the report needs that InsightsReport does
    not carry (it is scoped to computed metrics only, per core.insights'
    own docstring)."""

    run_id: str
    program_id: str
    program_name: str
    run_state: str
    created_by: str
    created_at: str


def build_run_summary_sheets(context: RunSummaryContext, report: Any) -> dict[str, _Table]:
    """Returns an ordered mapping of sheet name -> (headers, rows), ready
    for infrastructure.xlsx_writer.write_multi_sheet_workbook. ``report``
    is a services.insights.InsightsReport."""
    return {
        "Summary": _summary_sheet(context, report),
        "Allocation Utilization": _utilization_sheet(report),
        "Associate QC Performance": _performance_sheet(report),
        "Top Error Categories": _top_errors_sheet(report),
    }


def _fmt(value: Decimal | int | None) -> object:
    return value if value is not None else "N/A"


def _summary_sheet(context: RunSummaryContext, report: Any) -> _Table:
    headers = ("Field", "Value")
    historical = report.historical
    rows: list[tuple[object, ...]] = [
        ("Run ID", context.run_id),
        ("Program", f"{context.program_name} ({context.program_id})"),
        ("Run State", context.run_state),
        ("Created By", context.created_by),
        ("Created At", context.created_at),
        ("Completion Rate (%)", _fmt(report.completion_rate)),
        ("Error Frequency (%)", _fmt(report.error_frequency)),
        ("Outlier Associates", ", ".join(report.outliers) if report.outliers else "None"),
        ("Has Prior Completed Run for Comparison", historical.is_applicable),
        ("Current QC Score (%)", _fmt(historical.current_qc_score)),
        ("Previous QC Score (%)", _fmt(historical.previous_qc_score)),
        ("QC Score Change (points)", _fmt(historical.qc_score_change_points)),
        ("Current Error Rate (%)", _fmt(historical.current_error_rate)),
        ("Previous Error Rate (%)", _fmt(historical.previous_error_rate)),
        ("Error Rate Change (points)", _fmt(historical.error_rate_change_points)),
        ("Missing Identifiers (current)", _fmt(historical.missing_count_current)),
        ("Missing Identifiers (previous)", _fmt(historical.missing_count_previous)),
        ("Duplicate Count (current)", _fmt(historical.duplicate_count_current)),
        ("Duplicate Count (previous)", _fmt(historical.duplicate_count_previous)),
    ]
    return headers, tuple(rows)


def _utilization_sheet(report: Any) -> _Table:
    headers = ("Associate ID", "Utilization (%)")
    rows = tuple((associate_id, _fmt(value)) for associate_id, value in sorted(report.allocation_utilization.items()))
    return headers, rows


def _performance_sheet(report: Any) -> _Table:
    headers = ("Associate ID", "QC Score (%)", "Outlier")
    outliers = set(report.outliers)
    rows = tuple(
        (associate_id, _fmt(score), associate_id in outliers)
        for associate_id, score in sorted(report.associate_performance.items())
    )
    return headers, rows


def _top_errors_sheet(report: Any) -> _Table:
    headers = ("Category", "Count")
    return headers, tuple(report.top_error_categories)
