"""Thin, PySide6-free facade over AppContext's services for one Run's
lifecycle actions. Each function here does the minimum composition a
view needs (e.g. "import this file, then validate it") and returns/raises
plain domain objects -- the view layer's only job is turning those into
widgets and dialogs. Fully unit-testable without a display.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from operations_allocation.domain.models import RunState


def import_source_and_validate(context: Any, *, run_id: str, file_path: Path | str) -> tuple[list[dict], Any]:
    canonical_rows, _artifact = context.source_import.import_source(run_id=run_id, file_path=file_path)
    summary = context.eligible_population.validate(run_id=run_id, rows=canonical_rows)
    return canonical_rows, summary


def freeze_eligible_population(context: Any, *, run_id: str, canonical_rows: list[dict]) -> Any:
    """v1 scope note: does not yet support duplicate-resolution input from
    the UI -- if any duplicate identifier groups were detected during
    validation, this raises UnresolvedDuplicatesError (surfaced to the
    user) rather than silently picking a resolution."""
    return context.eligible_population.freeze(run_id=run_id, rows=canonical_rows, resolved_by=context.current_os_username())


def sample(context: Any, *, run_id: str) -> Any:
    return context.sampling.sample(run_id=run_id)


def preview_allocation(context: Any, *, run_id: str) -> Any:
    return context.allocation.preview(run_id=run_id)


def finalize_allocation(context: Any, *, run_id: str, confirm_above_target: bool = False) -> Any:
    return context.allocation.finalize(run_id=run_id, confirm_above_target=confirm_above_target, confirmed_by=context.current_os_username())


def distribute(context: Any, *, run_id: str) -> tuple[Any, ...]:
    return context.distribution.distribute(run_id=run_id)


def send_individual_drafts(context: Any, *, run_id: str) -> tuple[Any, ...]:
    adapter = _try_build_outlook_adapter()
    return context.email_drafts.create_individual_drafts(run_id=run_id, outlook_adapter=adapter)


def send_consolidated_draft(context: Any, *, run_id: str) -> Any:
    adapter = _try_build_outlook_adapter()
    return context.email_drafts.create_consolidated_draft(run_id=run_id, outlook_adapter=adapter)


def import_returned_files(context: Any, *, run_id: str, files: list[tuple[Path, str]]) -> dict:
    return context.consolidation.import_returned_files(run_id=run_id, files=files)


def finalize_consolidation(context: Any, *, run_id: str, override: bool = False, override_reason: str | None = None) -> Any:
    return context.consolidation.finalize(
        run_id=run_id, override=override,
        overridden_by=context.current_os_username() if override else None,
        override_reason=override_reason,
    )


def import_qc_report(context: Any, *, run_id: str, file_path: Path | str) -> Any:
    return context.qc.import_and_evaluate(run_id=run_id, file_path=file_path)


def generate_errors(context: Any, *, run_id: str) -> tuple[Any, ...]:
    return context.errors.generate_from_consolidation(run_id=run_id)


def import_errors(context: Any, *, run_id: str, file_path: Path | str) -> tuple[Any, ...]:
    return context.errors.import_errors(run_id=run_id, file_path=file_path)


def complete_run(context: Any, *, run_id: str) -> Any:
    return context.orchestration.transition(run_id, RunState.COMPLETED)


def cancel_run(context: Any, *, run_id: str) -> Any:
    return context.orchestration.transition(run_id, RunState.CANCELLED)


def _try_build_outlook_adapter() -> Any | None:
    """Best-effort: Outlook COM is Windows-only and may not be installed.
    Returning None here makes EmailDraftService fall back to the
    plain-text draft it always persists first, per AGENTS.md section 16 --
    never blocks the workflow, never raises up to the UI."""
    try:
        from operations_allocation.infrastructure.outlook_adapter import OutlookComAdapter

        return OutlookComAdapter()
    except Exception:
        return None
