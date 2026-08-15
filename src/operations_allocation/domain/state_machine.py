"""The explicit, independently testable Run state machine."""

from operations_allocation.domain.exceptions import InvalidStateTransitionError
from operations_allocation.domain.models import RunState

_LINEAR_TRANSITIONS = {
    RunState.DRAFT: {RunState.SNAPSHOT_FROZEN, RunState.CANCELLED, RunState.ABANDONED},
    RunState.SNAPSHOT_FROZEN: {RunState.VALIDATED},
    RunState.VALIDATED: {RunState.ELIGIBLE_POPULATION_FROZEN},
    RunState.ELIGIBLE_POPULATION_FROZEN: {RunState.SAMPLED},
    RunState.SAMPLED: {RunState.ALLOCATED},
    RunState.ALLOCATED: {RunState.DISTRIBUTED},
    RunState.DISTRIBUTED: {RunState.RETURNED},
    RunState.RETURNED: {RunState.CONSOLIDATED},
    RunState.CONSOLIDATED: {RunState.QC_COMPLETED},
    RunState.QC_COMPLETED: {RunState.COMPLETED},
}
_TERMINAL = {RunState.COMPLETED, RunState.CANCELLED, RunState.FAILED, RunState.ABANDONED}


def allowed_transitions(state: RunState) -> frozenset[RunState]:
    if state in _TERMINAL:
        return frozenset()
    return frozenset(_LINEAR_TRANSITIONS.get(state, set()) | {RunState.FAILED})


def ensure_transition(current: RunState, target: RunState) -> None:
    if target not in allowed_transitions(current):
        raise InvalidStateTransitionError(
            f"Run cannot transition from {current.value} to {target.value}."
        )
