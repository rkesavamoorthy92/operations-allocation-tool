"""Allocation Strategy — target/capacity-based allocation.

Implements PROJECT_SPEC.md section 11 / ARCHITECTURE.md section 8.2:

* Associates may have different targets and maximum capacities; equal
  distribution must never be assumed.
* If total maximum capacity < sample count: allocation is BLOCKED. Nothing
  is discarded or redistributed silently -- the caller must change
  associates, targets, capacity, or sampling and try again.
* If total maximum capacity > sample count: only the sampled items are
  allocated; unused capacity is reported, never used to inflate sampling.
* Allocation above target (but at or below maximum capacity) requires
  explicit confirmation before it can be finalized.
* If the sample exceeds total target but not total maximum capacity, the v1
  overflow strategy is proportional distribution based on each associate's
  remaining capacity (maximum_capacity - target), with Associate ID as the
  deterministic tie-breaker.
* Inactive associates are excluded automatically.

Baseline distribution (sample within total target) is likewise proportional
to each associate's configured target share, using the same largest-
remainder apportionment as overflow, again tie-broken by Associate ID. The
spec constrains capacity/shortage/confirmation behavior precisely but does
not name a baseline distribution formula; proportional-to-target is the
smallest deterministic rule consistent with "must not assume equal
distribution" and reuses one apportionment algorithm for both phases. This
choice affects *which* active associate receives how many items and should
be confirmed as correct before relying on it operationally.

Which specific items (as opposed to how many) go to which associate is
similarly unconstrained by the spec; this module assigns canonically sorted
sample identifiers to canonically sorted (by Associate ID) associates in
contiguous blocks, which is deterministic and reproducible but arbitrary.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Mapping, Sequence

from operations_allocation.domain.models import AllocationAssignment


@dataclass(frozen=True, slots=True)
class AssociateSnapshot:
    associate_id: str
    active: bool
    target: int
    maximum_capacity: int


@dataclass(frozen=True, slots=True)
class AllocationPlan:
    sample_count: int
    total_target: int
    total_maximum_capacity: int
    capacity_shortage: int
    unused_capacity: int
    blocked: bool
    requires_above_target_confirmation: bool
    assignments: tuple[AllocationAssignment, ...]


def apportion(total: int, weights: Mapping[str, int]) -> dict[str, int]:
    """Largest-remainder apportionment of ``total`` across ``weights``.

    Every key gets ``floor(total * weight / sum(weights))``; the remaining
    units go one-at-a-time to the largest fractional remainders, ties broken
    by ascending key (Associate ID) for determinism. Keys with zero weight
    receive zero. If every weight is zero, ``total`` must be zero.
    """
    total_weight = sum(weights.values())
    if total_weight == 0:
        return {key: 0 for key in weights}

    shares = {key: Fraction(total * weight, total_weight) for key, weight in weights.items()}
    allocation = {key: share.numerator // share.denominator for key, share in shares.items()}
    remainder = total - sum(allocation.values())
    remainders = sorted(weights.keys(), key=lambda key: (-(shares[key] - allocation[key]), key))
    for key in remainders[:remainder]:
        allocation[key] += 1
    return allocation


def build_allocation_plan(sample_identifiers: Sequence[str], associates: Sequence[AssociateSnapshot]) -> AllocationPlan:
    sample_count = len(sample_identifiers)
    active = sorted((a for a in associates if a.active), key=lambda a: a.associate_id)
    total_target = sum(a.target for a in active)
    total_maximum_capacity = sum(a.maximum_capacity for a in active)

    if total_maximum_capacity < sample_count:
        return AllocationPlan(
            sample_count=sample_count,
            total_target=total_target,
            total_maximum_capacity=total_maximum_capacity,
            capacity_shortage=sample_count - total_maximum_capacity,
            unused_capacity=0,
            blocked=True,
            requires_above_target_confirmation=False,
            assignments=(),
        )

    baseline_total = min(sample_count, total_target)
    overflow_total = sample_count - baseline_total

    baseline_counts = apportion(baseline_total, {a.associate_id: a.target for a in active})
    remaining_capacity = {a.associate_id: a.maximum_capacity - a.target for a in active}
    overflow_counts = apportion(overflow_total, remaining_capacity)

    canonical_sample = sorted(sample_identifiers)
    assignments: list[AllocationAssignment] = []
    cursor = 0
    for associate in active:
        planned_count = baseline_counts[associate.associate_id] + overflow_counts[associate.associate_id]
        assigned = tuple(canonical_sample[cursor : cursor + planned_count])
        cursor += planned_count
        assignments.append(
            AllocationAssignment(
                associate_id=associate.associate_id,
                target=associate.target,
                maximum_capacity=associate.maximum_capacity,
                planned_count=planned_count,
                assigned_identifiers=assigned,
                above_target=planned_count > associate.target,
            )
        )

    return AllocationPlan(
        sample_count=sample_count,
        total_target=total_target,
        total_maximum_capacity=total_maximum_capacity,
        capacity_shortage=0,
        unused_capacity=total_maximum_capacity - sample_count,
        blocked=False,
        requires_above_target_confirmation=any(a.above_target for a in assignments),
        assignments=tuple(assignments),
    )
