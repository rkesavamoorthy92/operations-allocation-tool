from __future__ import annotations

import unittest

from operations_allocation.core.consolidation import FileIdentity, RowDisposition, build_consolidated_export, check_identity, reconcile
from operations_allocation.utils.identifiers import NormalizationPolicy


class CheckIdentityTestCase(unittest.TestCase):
    def _identity(self, **overrides) -> FileIdentity:
        base = dict(
            filename_run_id="R1", filename_associate_id="A001",
            metadata_run_id="R1", metadata_associate_id="A001", metadata_associate_name="Jane Doe",
            data_run_ids=frozenset({"R1"}), data_allocated_to=frozenset({"A001"}),
        )
        base.update(overrides)
        return FileIdentity(**base)

    def test_matching_identity_has_no_issues(self) -> None:
        issues = check_identity(self._identity(), expected_run_id="R1", expected_associate_id="A001", expected_associate_name="Jane Doe")
        self.assertEqual(issues, ())

    def test_filename_run_id_mismatch_detected(self) -> None:
        issues = check_identity(self._identity(filename_run_id="WRONG"), expected_run_id="R1", expected_associate_id="A001", expected_associate_name="Jane Doe")
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].level, "filename")
        self.assertEqual(issues[0].field_name, "run_id")

    def test_metadata_associate_name_mismatch_detected(self) -> None:
        issues = check_identity(self._identity(metadata_associate_name="Someone Else"), expected_run_id="R1", expected_associate_id="A001", expected_associate_name="Jane Doe")
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].field_name, "associate_name")

    def test_data_column_wrong_run_id_detected(self) -> None:
        issues = check_identity(self._identity(data_run_ids=frozenset({"R1", "OTHER"})), expected_run_id="R1", expected_associate_id="A001", expected_associate_name="Jane Doe")
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].level, "data")

    def test_none_at_a_level_is_not_a_mismatch(self) -> None:
        issues = check_identity(self._identity(filename_run_id=None, metadata_associate_name=None), expected_run_id="R1", expected_associate_id="A001", expected_associate_name="Jane Doe")
        self.assertEqual(issues, ())


def _policy() -> NormalizationPolicy:
    return NormalizationPolicy(trim_whitespace=True, case_sensitive=True)


class ReconcileTestCase(unittest.TestCase):
    def test_spec_worked_example_arithmetic(self) -> None:
        assignments = {"A": [f"P{i}" for i in range(1693)]}
        returned_ids = [f"P{i}" for i in range(1512)]  # 1512 unique matched items
        returned_ids += ["P0", "P1"]  # 2 duplicates
        returned_ids += ["X1", "X2", "X3", "X4"]  # 4 unexpected
        rows = [{"product_id": pid} for pid in returned_ids]
        _, summary = reconcile(
            identifier_field="product_id", policy=_policy(),
            assignments_by_associate=assignments, returned_rows_by_associate={"A": rows}, identity_issues=(),
        )
        self.assertEqual(summary.allocated_count, 1693)
        self.assertEqual(summary.unique_returned_count, 1512)
        self.assertEqual(len(summary.missing_identifiers), 181)
        self.assertEqual(summary.duplicate_count, 2)
        self.assertEqual(summary.unexpected_count, 4)

    def test_matched_row_disposition(self) -> None:
        rows = [{"product_id": "P1"}]
        reconciled, summary = reconcile(identifier_field="product_id", policy=_policy(), assignments_by_associate={"A": ["P1"]}, returned_rows_by_associate={"A": rows}, identity_issues=())
        self.assertEqual(reconciled[0].disposition, RowDisposition.MATCHED)
        self.assertFalse(summary.has_open_critical_exceptions)

    def test_wrong_associate_detected_and_quarantined(self) -> None:
        rows = [{"product_id": "P1"}]
        reconciled, summary = reconcile(
            identifier_field="product_id", policy=_policy(),
            assignments_by_associate={"A": ["P1"], "B": []}, returned_rows_by_associate={"B": rows}, identity_issues=(),
        )
        self.assertEqual(reconciled[0].disposition, RowDisposition.WRONG_ASSOCIATE)
        self.assertEqual(summary.wrong_associate_count, 1)
        self.assertTrue(summary.has_open_critical_exceptions)

    def test_blank_identifier_is_incomplete_not_unexpected(self) -> None:
        rows = [{"product_id": None}, {"product_id": "  "}]
        reconciled, summary = reconcile(identifier_field="product_id", policy=_policy(), assignments_by_associate={"A": []}, returned_rows_by_associate={"A": rows}, identity_issues=())
        self.assertTrue(all(r.disposition == RowDisposition.INCOMPLETE for r in reconciled))
        self.assertEqual(summary.incomplete_count, 2)
        self.assertEqual(summary.unexpected_count, 0)

    def test_missing_items_never_silently_dropped(self) -> None:
        _, summary = reconcile(identifier_field="product_id", policy=_policy(), assignments_by_associate={"A": ["P1", "P2"]}, returned_rows_by_associate={"A": [{"product_id": "P1"}]}, identity_issues=())
        self.assertEqual(summary.missing_identifiers, ("P2",))
        self.assertTrue(summary.has_open_critical_exceptions)

    def test_no_exceptions_when_everything_matches(self) -> None:
        _, summary = reconcile(identifier_field="product_id", policy=_policy(), assignments_by_associate={"A": ["P1"]}, returned_rows_by_associate={"A": [{"product_id": "P1"}]}, identity_issues=())
        self.assertFalse(summary.has_open_critical_exceptions)

    def test_identity_issues_count_as_open_critical_exceptions(self) -> None:
        from operations_allocation.core.consolidation import IdentityIssue

        _, summary = reconcile(
            identifier_field="product_id", policy=_policy(), assignments_by_associate={"A": ["P1"]},
            returned_rows_by_associate={"A": [{"product_id": "P1"}]},
            identity_issues=(IdentityIssue("filename", "run_id", "R1", "R2"),),
        )
        self.assertTrue(summary.has_open_critical_exceptions)


class BuildConsolidatedExportTestCase(unittest.TestCase):
    def test_matched_rows_go_to_consolidated_others_quarantined(self) -> None:
        reconciled, _ = reconcile(
            identifier_field="product_id", policy=_policy(),
            assignments_by_associate={"A": ["P1"], "B": []},
            returned_rows_by_associate={"A": [{"product_id": "P1"}], "B": [{"product_id": "P1"}, {"product_id": "X1"}]},
            identity_issues=(),
        )
        headers, consolidated, quarantined = build_consolidated_export(reconciled)
        self.assertEqual(headers, ("Associate ID", "Disposition", "product_id"))
        self.assertEqual(len(consolidated), 1)
        self.assertEqual(len(quarantined), 2)
        self.assertIn("duplicate", [row[1] for row in quarantined])
        self.assertIn("unexpected", [row[1] for row in quarantined])
