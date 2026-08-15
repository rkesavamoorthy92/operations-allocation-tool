from __future__ import annotations

import unittest

from operations_allocation.core.validation import Severity, validate_dataset
from operations_allocation.utils.identifiers import NormalizationPolicy

POLICY = NormalizationPolicy()


class ValidateDatasetTestCase(unittest.TestCase):
    def test_empty_dataset_is_critical(self) -> None:
        summary = validate_dataset([], identifier_field="product_id", required_fields=[], normalization_policy=POLICY)
        self.assertEqual(summary.total_rows, 0)
        self.assertEqual(summary.valid_row_count, 0)
        self.assertTrue(summary.has_blocking_issues)
        self.assertEqual(summary.critical_issues[0].code, "EMPTY_DATASET")
        self.assertEqual(summary.eligible_identifiers, ())

    def test_missing_required_column_is_critical_and_stops_row_checks(self) -> None:
        rows = [{"product_id": "A1"}]
        summary = validate_dataset(rows, identifier_field="product_id", required_fields=["pt"], normalization_policy=POLICY)
        self.assertEqual(summary.critical_issues[0].code, "MISSING_REQUIRED_COLUMN")
        self.assertIn("pt", summary.critical_issues[0].message)

    def test_valid_dataset_has_no_issues(self) -> None:
        rows = [{"product_id": "A1"}, {"product_id": "A2"}]
        summary = validate_dataset(rows, identifier_field="product_id", required_fields=[], normalization_policy=POLICY)
        self.assertEqual(summary.issues, ())
        self.assertEqual(summary.eligible_identifiers, ("A1", "A2"))
        self.assertEqual(summary.valid_row_count, 2)

    def test_missing_identifier_rows_are_excluded_and_flagged(self) -> None:
        rows = [{"product_id": "A1"}, {"product_id": ""}, {"product_id": None}, {"product_id": "A2"}]
        summary = validate_dataset(rows, identifier_field="product_id", required_fields=[], normalization_policy=POLICY)
        self.assertEqual(summary.total_rows, 4)
        self.assertEqual(summary.eligible_identifiers, ("A1", "A2"))
        self.assertEqual(summary.valid_row_count, 2)
        issue = next(issue for issue in summary.issues if issue.code == "MISSING_IDENTIFIER")
        self.assertEqual(issue.severity, Severity.CRITICAL)
        self.assertEqual(issue.row_indexes, (1, 2))

    def test_duplicate_identifiers_are_grouped_and_excluded_pending_resolution(self) -> None:
        rows = [{"product_id": "A1"}, {"product_id": "A2"}, {"product_id": "A1"}]
        summary = validate_dataset(rows, identifier_field="product_id", required_fields=[], normalization_policy=POLICY)
        self.assertEqual(len(summary.duplicate_groups), 1)
        group = summary.duplicate_groups[0]
        self.assertEqual(group.normalized_identifier, "A1")
        self.assertEqual(group.row_indexes, (0, 2))
        self.assertEqual(summary.eligible_identifiers, ("A2",))
        self.assertEqual(summary.valid_row_count, 1)
        self.assertTrue(summary.has_blocking_issues)

    def test_normalization_collision_across_case_creates_duplicate_group(self) -> None:
        policy = NormalizationPolicy(case_sensitive=False)
        rows = [{"product_id": "abc"}, {"product_id": "ABC"}]
        summary = validate_dataset(rows, identifier_field="product_id", required_fields=[], normalization_policy=policy)
        self.assertEqual(len(summary.duplicate_groups), 1)
        self.assertEqual(set(summary.duplicate_groups[0].original_values), {"abc", "ABC"})

    def test_whitespace_only_identifier_treated_as_missing(self) -> None:
        rows = [{"product_id": "   "}]
        summary = validate_dataset(rows, identifier_field="product_id", required_fields=[], normalization_policy=POLICY)
        self.assertEqual(summary.critical_issues[0].code, "MISSING_IDENTIFIER")
