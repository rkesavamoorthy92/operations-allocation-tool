from __future__ import annotations

import unittest

from operations_allocation.core.allocation import AssociateSnapshot, apportion, build_allocation_plan


class ApportionTestCase(unittest.TestCase):
    def test_exact_proportional_split(self) -> None:
        self.assertEqual(apportion(300, {"A": 50, "B": 50, "C": 100, "D": 100}), {"A": 50, "B": 50, "C": 100, "D": 100})

    def test_remainder_goes_to_largest_fraction_first(self) -> None:
        # 10 split 3-ways with equal weight -> 4/3/3, tie broken by key.
        result = apportion(10, {"A": 1, "B": 1, "C": 1})
        self.assertEqual(sum(result.values()), 10)
        self.assertEqual(result["A"], 4)

    def test_zero_total_weight_requires_zero_total(self) -> None:
        self.assertEqual(apportion(0, {"A": 0, "B": 0}), {"A": 0, "B": 0})

    def test_zero_weight_key_gets_nothing(self) -> None:
        result = apportion(5, {"A": 0, "B": 5})
        self.assertEqual(result, {"A": 0, "B": 5})

    def test_deterministic_across_repeated_calls(self) -> None:
        first = apportion(7, {"A": 3, "B": 3, "C": 3})
        second = apportion(7, {"A": 3, "B": 3, "C": 3})
        self.assertEqual(first, second)


def _associate(associate_id: str, target: int, maximum_capacity: int, active: bool = True) -> AssociateSnapshot:
    return AssociateSnapshot(associate_id=associate_id, active=active, target=target, maximum_capacity=maximum_capacity)


class BuildAllocationPlanTestCase(unittest.TestCase):
    def test_spec_example_exact_target_match(self) -> None:
        sample = tuple(f"I{i:03d}" for i in range(1, 301))
        associates = [_associate("A", 50, 50), _associate("B", 50, 50), _associate("C", 100, 100), _associate("D", 100, 100)]
        plan = build_allocation_plan(sample, associates)
        self.assertFalse(plan.blocked)
        self.assertFalse(plan.requires_above_target_confirmation)
        self.assertEqual(plan.unused_capacity, 0)
        counts = {a.associate_id: a.planned_count for a in plan.assignments}
        self.assertEqual(counts, {"A": 50, "B": 50, "C": 100, "D": 100})

    def test_insufficient_capacity_blocks_and_reports_shortage(self) -> None:
        sample = tuple(f"I{i}" for i in range(1, 21))
        associates = [_associate("A", 5, 5), _associate("B", 5, 5)]
        plan = build_allocation_plan(sample, associates)
        self.assertTrue(plan.blocked)
        self.assertEqual(plan.capacity_shortage, 10)
        self.assertEqual(plan.assignments, ())

    def test_excess_capacity_allocates_only_sample_and_reports_unused(self) -> None:
        sample = tuple(f"I{i}" for i in range(1, 11))
        associates = [_associate("A", 10, 10), _associate("B", 10, 10)]
        plan = build_allocation_plan(sample, associates)
        self.assertFalse(plan.blocked)
        self.assertEqual(plan.unused_capacity, 10)
        self.assertEqual(sum(a.planned_count for a in plan.assignments), 10)

    def test_inactive_associates_are_excluded(self) -> None:
        sample = tuple(f"I{i}" for i in range(1, 6))
        associates = [_associate("A", 5, 5), _associate("B", 100, 100, active=False)]
        plan = build_allocation_plan(sample, associates)
        self.assertEqual(plan.total_target, 5)
        self.assertEqual(plan.total_maximum_capacity, 5)
        self.assertEqual(len(plan.assignments), 1)
        self.assertEqual(plan.assignments[0].associate_id, "A")

    def test_overflow_above_target_requires_confirmation_and_uses_remaining_capacity(self) -> None:
        sample = tuple(f"I{i}" for i in range(1, 21))
        associates = [_associate("A", 5, 15), _associate("B", 5, 15)]
        plan = build_allocation_plan(sample, associates)
        self.assertFalse(plan.blocked)
        self.assertTrue(plan.requires_above_target_confirmation)
        counts = {a.associate_id: a.planned_count for a in plan.assignments}
        self.assertEqual(sum(counts.values()), 20)
        self.assertEqual(counts, {"A": 10, "B": 10})
        for assignment in plan.assignments:
            self.assertTrue(assignment.above_target)

    def test_no_active_associates_with_zero_sample_is_not_blocked(self) -> None:
        plan = build_allocation_plan((), [_associate("A", 5, 5, active=False)])
        self.assertFalse(plan.blocked)
        self.assertEqual(plan.assignments, ())

    def test_no_active_associates_with_positive_sample_is_blocked(self) -> None:
        plan = build_allocation_plan(("I1",), [_associate("A", 5, 5, active=False)])
        self.assertTrue(plan.blocked)
        self.assertEqual(plan.capacity_shortage, 1)

    def test_assigned_identifiers_partition_the_sample_without_overlap(self) -> None:
        sample = tuple(f"I{i:03d}" for i in range(1, 21))
        associates = [_associate("A", 5, 5), _associate("B", 15, 15)]
        plan = build_allocation_plan(sample, associates)
        all_assigned = [identifier for assignment in plan.assignments for identifier in assignment.assigned_identifiers]
        self.assertEqual(sorted(all_assigned), sorted(sample))
        self.assertEqual(len(all_assigned), len(set(all_assigned)))

    def test_tie_breaking_is_deterministic_by_associate_id(self) -> None:
        sample = tuple(f"I{i}" for i in range(1, 11))
        associates = [_associate("Z", 1, 10), _associate("A", 1, 10), _associate("M", 1, 10)]
        plan_one = build_allocation_plan(sample, associates)
        plan_two = build_allocation_plan(sample, list(reversed(associates)))
        counts_one = {a.associate_id: a.planned_count for a in plan_one.assignments}
        counts_two = {a.associate_id: a.planned_count for a in plan_two.assignments}
        self.assertEqual(counts_one, counts_two)
        self.assertEqual(sum(counts_one.values()), 10)
