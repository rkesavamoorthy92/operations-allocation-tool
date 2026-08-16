"""Reporting Service (ARCHITECTURE.md section 4.11): composes
InsightsService's already-computed metrics with the Run's own identity
metadata into one shareable operational summary export.

Deliberately thin -- all the actual number-crunching lives in
core.insights (via services.insights.InsightsService), and all the row
layout lives in core.reporting. This module's only job is fetching Run
identity fields (program name, created-by, state) that InsightsReport
does not carry, then handing everything to core.reporting for
arrangement and infrastructure.xlsx_writer for serialization -- the
same "services compose core + I/O, never invent their own business
logic" pattern as every other service in this codebase.
"""

from __future__ import annotations

from typing import Any

from operations_allocation.core.reporting import RunSummaryContext, build_run_summary_sheets
from operations_allocation.infrastructure.xlsx_writer import write_multi_sheet_workbook


class ReportingService:
    def __init__(self, *, runs: Any, programs: Any, insights: Any) -> None:
        self.runs, self.programs, self.insights = runs, programs, insights

    def export_run_summary(self, *, run_id: str) -> bytes:
        run = self.runs.get(run_id)
        program = self.programs.get(run.program_id)
        report = self.insights.generate(run_id=run_id)

        context = RunSummaryContext(
            run_id=run.run_id,
            program_id=run.program_id,
            program_name=program.name,
            run_state=run.state.value,
            created_by=run.created_by,
            created_at=run.created_at.isoformat(),
        )
        sheets = build_run_summary_sheets(context, report)
        return write_multi_sheet_workbook(sheets)
