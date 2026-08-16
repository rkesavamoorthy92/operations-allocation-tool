from __future__ import annotations

import unittest
from decimal import Decimal

from operations_allocation.core.insights import HistoricalComparison
from operations_allocation.core.reporting import RunSummaryContext, build_run_summary_sheets
from operations_allocation.services.insights import InsightsReport


def _context() -> RunSummaryContext:
    return RunSummaryContext(
        run_id="MX-PT-2026-08-0001", program_id="MX-PT", program_name="MX PT",
        run_state="qc_completed", created_by="tester", created_at="2026-08-15T00:00:00",
    )


def _report(**overrides) -> InsightsReport:
    defaults = dict(
        allocation_utilization={"A002": Decimal("80.00"), "A001": Decimal("100.00")},
        completion_rate=Decimal("95.00"),
        top_error_categories=(("Clothing", 3), ("Electronics", 1)),
        error_frequency=Decimal("5.00"),
        associate_performance={"A001": Decimal("98.44"), "A002": Decimal("70.00")},
        outliers=("A002",),
        historical=HistoricalComparison(
            is_applicable=True, current_qc_score=Decimal("98.44"), previous_qc_score=Decimal("98.67"),
            qc_score_change_points=Decimal("-0.23"), current_error_rate=Decimal("5.00"), previous_error_rate=Decimal("3.00"),
            error_rate_change_points=Decimal("2.00"), missing_count_current=1, missing_count_previous=0,
            duplicate_count_current=0, duplicate_count_previous=0,
        ),
    )
    defaults.update(overrides)
    return InsightsReport(**defaults)


class BuildRunSummarySheetsTestCase(unittest.TestCase):
    def test_returns_four_named_sheets(self) -> None:
        sheets = build_run_summary_sheets(_context(), _report())
        self.assertEqual(list(sheets.keys()), ["Summary", "Allocation Utilization", "Associate QC Performance", "Top Error Categories"])

    def test_summary_sheet_includes_identity_and_historical_fields(self) -> None:
        headers, rows = build_run_summary_sheets(_context(), _report())["Summary"]
        self.assertEqual(headers, ("Field", "Value"))
        rows_by_field = dict(rows)
        self.assertEqual(rows_by_field["Run ID"], "MX-PT-2026-08-0001")
        self.assertEqual(rows_by_field["Program"], "MX PT (MX-PT)")
        self.assertEqual(rows_by_field["Outlier Associates"], "A002")
        self.assertEqual(rows_by_field["QC Score Change (points)"], Decimal("-0.23"))

    def test_summary_sheet_handles_no_prior_run(self) -> None:
        no_history = HistoricalComparison(
            is_applicable=False, current_qc_score=Decimal("98.44"), previous_qc_score=None,
            qc_score_change_points=None, current_error_rate=Decimal("5.00"), previous_error_rate=None,
            error_rate_change_points=None, missing_count_current=1, missing_count_previous=None,
            duplicate_count_current=0, duplicate_count_previous=None,
        )
        headers, rows = build_run_summary_sheets(_context(), _report(historical=no_history))["Summary"]
        rows_by_field = dict(rows)
        self.assertEqual(rows_by_field["Has Prior Completed Run for Comparison"], False)
        self.assertEqual(rows_by_field["Previous QC Score (%)"], "N/A")

    def test_utilization_sheet_sorted_by_associate_id(self) -> None:
        headers, rows = build_run_summary_sheets(_context(), _report())["Allocation Utilization"]
        self.assertEqual(headers, ("Associate ID", "Utilization (%)"))
        self.assertEqual(rows, (("A001", Decimal("100.00")), ("A002", Decimal("80.00"))))

    def test_performance_sheet_flags_outliers(self) -> None:
        headers, rows = build_run_summary_sheets(_context(), _report())["Associate QC Performance"]
        self.assertEqual(headers, ("Associate ID", "QC Score (%)", "Outlier"))
        rows_by_associate = {row[0]: row for row in rows}
        self.assertEqual(rows_by_associate["A001"], ("A001", Decimal("98.44"), False))
        self.assertEqual(rows_by_associate["A002"], ("A002", Decimal("70.00"), True))

    def test_top_errors_sheet_passes_through_tuples(self) -> None:
        headers, rows = build_run_summary_sheets(_context(), _report())["Top Error Categories"]
        self.assertEqual(headers, ("Category", "Count"))
        self.assertEqual(rows, (("Clothing", 3), ("Electronics", 1)))

    def test_no_error_categories_gives_empty_rows(self) -> None:
        headers, rows = build_run_summary_sheets(_context(), _report(top_error_categories=()))["Top Error Categories"]
        self.assertEqual(rows, ())
