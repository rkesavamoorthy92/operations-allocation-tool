from __future__ import annotations

import unittest
from decimal import Decimal

from operations_allocation.core.insights import (
    allocation_utilization,
    build_historical_comparison,
    completion_rate,
    detect_outliers,
    error_frequency,
    top_error_categories,
)


class AllocationUtilizationTestCase(unittest.TestCase):
    def test_computes_percentage_of_capacity(self) -> None:
        assignments = [{"associate_id": "A001", "planned_count": 8, "maximum_capacity": 10}]
        self.assertEqual(allocation_utilization(assignments), {"A001": Decimal("80.00")})

    def test_zero_capacity_is_not_applicable(self) -> None:
        assignments = [{"associate_id": "A001", "planned_count": 0, "maximum_capacity": 0}]
        self.assertIsNone(allocation_utilization(assignments)["A001"])


class CompletionRateTestCase(unittest.TestCase):
    def test_spec_style_example(self) -> None:
        self.assertEqual(completion_rate(allocated_count=1693, unique_returned_count=1512), Decimal("89.31"))

    def test_zero_allocated_is_not_applicable(self) -> None:
        self.assertIsNone(completion_rate(allocated_count=0, unique_returned_count=0))


class TopErrorCategoriesTestCase(unittest.TestCase):
    def test_orders_by_frequency_descending(self) -> None:
        categories = ["Missing", "Missing", "Duplicate", "Unexpected", "Missing"]
        self.assertEqual(top_error_categories(categories), (("Missing", 3), ("Duplicate", 1), ("Unexpected", 1)))

    def test_ties_broken_alphabetically_for_determinism(self) -> None:
        self.assertEqual(top_error_categories(["Zebra", "Alpha"]), (("Alpha", 1), ("Zebra", 1)))

    def test_respects_top_n(self) -> None:
        self.assertEqual(len(top_error_categories(["A", "B", "C"], top_n=2)), 2)


class ErrorFrequencyTestCase(unittest.TestCase):
    def test_computes_percentage(self) -> None:
        self.assertEqual(error_frequency(error_count=2, audited_count=10), Decimal("20.00"))

    def test_zero_audited_is_not_applicable(self) -> None:
        self.assertIsNone(error_frequency(error_count=0, audited_count=0))


class DetectOutliersTestCase(unittest.TestCase):
    def test_flags_associate_far_below_mean(self) -> None:
        scores = {"A": Decimal("95"), "B": Decimal("96"), "C": Decimal("60")}
        self.assertEqual(detect_outliers(scores, threshold_points=Decimal(10)), ("C",))

    def test_no_outliers_when_scores_are_close(self) -> None:
        scores = {"A": Decimal("95"), "B": Decimal("94")}
        self.assertEqual(detect_outliers(scores), ())

    def test_na_scores_excluded_from_mean_and_outlier_check(self) -> None:
        scores = {"A": Decimal("95"), "B": None, "C": Decimal("94")}
        self.assertEqual(detect_outliers(scores), ())

    def test_single_associate_never_an_outlier(self) -> None:
        self.assertEqual(detect_outliers({"A": Decimal("50")}), ())


class BuildHistoricalComparisonTestCase(unittest.TestCase):
    def test_no_previous_run_is_not_applicable(self) -> None:
        comparison = build_historical_comparison(current_qc_score=Decimal("91.7"), current_error_rate=Decimal("8.3"), current_missing_count=1, current_duplicate_count=0, previous=None)
        self.assertFalse(comparison.is_applicable)
        self.assertIsNone(comparison.qc_score_change_points)

    def test_spec_worked_example(self) -> None:
        previous = {"qc_score": Decimal("94.2"), "error_rate": Decimal("5.8"), "missing_count": 2, "duplicate_count": 1}
        comparison = build_historical_comparison(current_qc_score=Decimal("91.7"), current_error_rate=Decimal("8.3"), current_missing_count=1, current_duplicate_count=0, previous=previous)
        self.assertTrue(comparison.is_applicable)
        self.assertEqual(comparison.qc_score_change_points, Decimal("-2.5"))
        self.assertEqual(comparison.missing_count_previous, 2)
