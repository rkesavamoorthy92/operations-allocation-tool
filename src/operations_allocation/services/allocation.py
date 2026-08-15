"""Coordinates the Allocation Strategy engine against a Run's frozen
snapshot associates and sampling result (PROJECT_SPEC.md section 11,
section 13 Allocation Preview / ARCHITECTURE.md section 8.2).

``preview()`` never persists anything or changes Run state -- it exists so
a caller (UI or another service) can inspect shortages, unused capacity,
and above-target confirmation requirements before finalizing. ``finalize()``
performs the same computation and, only once every required confirmation
has been supplied, persists the immutable AllocationResult and advances the
Run to ALLOCATED.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from operations_allocation.core.allocation import AllocationPlan, AssociateSnapshot, build_allocation_plan
from operations_allocation.domain.exceptions import AboveTargetConfirmationRequiredError, InsufficientCapacityError
from operations_allocation.domain.models import AllocationResult, RunState
from operations_allocation.domain.state_machine import ensure_transition


class AllocationService:
    def __init__(self, *, runs: Any, snapshots: Any, sampling_results: Any, allocation_results: Any, audit: Any) -> None:
        self.runs, self.snapshots, self.sampling_results = runs, snapshots, sampling_results
        self.allocation_results, self.audit = allocation_results, audit

    def preview(self, *, run_id: str) -> AllocationPlan:
        return self._build_plan(run_id)

    def finalize(self, *, run_id: str, confirm_above_target: bool = False, confirmed_by: str | None = None) -> AllocationResult:
        run = self.runs.get(run_id)
        ensure_transition(run.state, RunState.ALLOCATED)
        plan = self._build_plan(run_id)

        if plan.blocked:
            raise InsufficientCapacityError(
                f"Total active associate capacity ({plan.total_maximum_capacity}) is short by "
                f"{plan.capacity_shortage} item(s) for a sample of {plan.sample_count}. "
                "Add associates, raise capacity/targets, or reduce sampling before finalizing."
            )
        if plan.requires_above_target_confirmation and not confirm_above_target:
            raise AboveTargetConfirmationRequiredError(
                "One or more associates would be allocated above their target. "
                "Explicit confirmation is required before finalizing."
            )

        result = AllocationResult(
            run_id=run_id,
            sample_count=plan.sample_count,
            total_target=plan.total_target,
            total_maximum_capacity=plan.total_maximum_capacity,
            capacity_shortage=plan.capacity_shortage,
            unused_capacity=plan.unused_capacity,
            required_above_target_confirmation=plan.requires_above_target_confirmation,
            confirmed_above_target=plan.requires_above_target_confirmation and confirm_above_target,
            confirmed_by=confirmed_by if plan.requires_above_target_confirmation else None,
            assignments=plan.assignments,
            allocated_at=datetime.now(timezone.utc),
        )

        with self.runs.database.transaction() as connection:
            self.allocation_results.add(result, connection=connection)
            self.runs.update_state(run_id, RunState.ALLOCATED, connection=connection)
            self.audit.record(
                run_id=run_id,
                program_id=run.program_id,
                action="RUN_ALLOCATED",
                previous_state=run.state,
                new_state=RunState.ALLOCATED,
                metadata={
                    "sample_count": plan.sample_count,
                    "total_target": plan.total_target,
                    "total_maximum_capacity": plan.total_maximum_capacity,
                    "unused_capacity": plan.unused_capacity,
                    "required_above_target_confirmation": plan.requires_above_target_confirmation,
                    "confirmed_above_target": result.confirmed_above_target,
                    "confirmed_by": confirmed_by,
                    "associate_count": len(plan.assignments),
                },
                connection=connection,
            )
        return result

    def _build_plan(self, run_id: str) -> AllocationPlan:
        snapshot = self.snapshots.get(run_id)
        associates_config = snapshot.configuration["associates"]
        associates = tuple(
            AssociateSnapshot(
                associate_id=associate["associate_id"],
                active=associate["active"],
                target=associate["target"],
                maximum_capacity=associate["maximum_capacity"],
            )
            for associate in associates_config
        )
        sampling_result = self.sampling_results.get(run_id)
        return build_allocation_plan(sampling_result.selected_identifiers, associates)
