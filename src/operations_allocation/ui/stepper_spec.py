"""Plain metadata describing the Run lifecycle stepper: which action keys
apply to which RunStates, and their display labels. Framework-agnostic
(no PySide6, no FastAPI/Jinja2) so both the desktop UI and the web UI
gate their buttons/forms from the exact same table -- ARCHITECTURE.md
section 9's "no business logic in UI components" cuts both ways: the
*rendering* differs per frontend, but which actions are even legal in a
given Run state is a single fact that must not fork into two
independently-maintained copies.

Each entry is (action_key, label, states). ``action_key`` is the stable
identifier both frontends use to look up their own handler for it --
this module never holds handlers itself, only the gating metadata.
"""

from __future__ import annotations

from operations_allocation.domain.models import RunState

ANY_TIME_AFTER_CONSOLIDATED = frozenset({RunState.CONSOLIDATED, RunState.QC_COMPLETED, RunState.COMPLETED})
ANY_STATE = frozenset(RunState)

STEPPER_ACTIONS: tuple[tuple[str, str, frozenset[RunState]], ...] = (
    ("freeze_setup", "Freeze Setup…", frozenset({RunState.DRAFT})),
    ("import_source", "Import Source File & Validate…", frozenset({RunState.SNAPSHOT_FROZEN})),
    ("freeze_population", "Freeze Eligible Population", frozenset({RunState.VALIDATED})),
    ("sample", "Draw Sample", frozenset({RunState.ELIGIBLE_POPULATION_FROZEN})),
    ("preview_allocation", "Preview Allocation", frozenset({RunState.SAMPLED})),
    ("finalize_allocation", "Finalize Allocation", frozenset({RunState.SAMPLED})),
    ("distribute", "Distribute Associate Files", frozenset({RunState.ALLOCATED})),
    ("send_individual", "Send Individual Emails (Outlook)", frozenset({RunState.DISTRIBUTED})),
    ("send_consolidated", "Send Consolidated Email (Outlook)", frozenset({RunState.DISTRIBUTED})),
    ("import_returned", "Import Returned Files…", frozenset({RunState.DISTRIBUTED})),
    ("finalize_consolidation", "Finalize Consolidation", frozenset({RunState.RETURNED})),
    ("import_qc", "Import QC Report…", frozenset({RunState.CONSOLIDATED})),
    ("generate_errors", "Generate Errors From Consolidation", ANY_TIME_AFTER_CONSOLIDATED),
    ("import_errors", "Import Error Report…", ANY_TIME_AFTER_CONSOLIDATED),
    ("export_errors", "Export Error Report…", ANY_TIME_AFTER_CONSOLIDATED),
    ("view_insights", "View Insights", ANY_TIME_AFTER_CONSOLIDATED),
    ("export_summary", "Export Run Summary Report…", ANY_TIME_AFTER_CONSOLIDATED),
    ("complete", "Mark Run Completed", frozenset({RunState.QC_COMPLETED})),
    ("cancel", "Cancel Run", frozenset({RunState.DRAFT})),
    ("view_audit_log", "View Audit Log", ANY_STATE),
)


def actions_enabled_for(state: RunState) -> dict[str, bool]:
    """Convenience for templates: {action_key: is_enabled_in_this_state}."""
    return {key: state in states for key, _label, states in STEPPER_ACTIONS}
