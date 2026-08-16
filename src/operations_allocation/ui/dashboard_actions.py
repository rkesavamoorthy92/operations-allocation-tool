"""Thin, PySide6-free facade over AppContext's services for Dashboard-level
actions that need composing more than one service call. Mirrors
ui.run_actions's role for Run Detail: the view layer only turns these
into widgets/dialogs, all sequencing lives here so it is unit-testable
without a display.
"""

from __future__ import annotations

from typing import Any


def archive_program(context: Any, *, program_id: str) -> None:
    """Archives the Program and cascades to every one of its Runs that
    is not already archived -- otherwise a Program's Runs would keep
    cluttering the Dashboard's Runs table after their own Program has
    disappeared from the Programs table, which would look like a bug.
    Restoring the Program deliberately does *not* cascade-restore Runs
    (see restore_program) -- appearing is opt-in, disappearing is not.
    """
    context.program_configuration.archive_program(program_id)
    for run in context.runs.list_all():
        if run.program_id == program_id and run.archived_at is None:
            context.orchestration.archive(run.run_id)


def restore_program(context: Any, *, program_id: str) -> None:
    context.program_configuration.restore_program(program_id)


def archive_run(context: Any, *, run_id: str) -> None:
    context.orchestration.archive(run_id)


def restore_run(context: Any, *, run_id: str) -> None:
    context.orchestration.restore(run_id)
