from __future__ import annotations

import unittest

from operations_allocation.core.distribution import build_associate_file_content, build_filename, sanitize_for_filename
from operations_allocation.domain.exceptions import AssignedItemNotFoundError
from operations_allocation.domain.models import AllocationAssignment


def _fields() -> list[dict]:
    return [
        {"name": "product_id", "source_column": "Product ID", "ownership": "source", "output_order": 0},
        {"name": "pt", "source_column": "PT", "ownership": "source", "output_order": 1},
        {"name": "partner_feedback", "ownership": "response", "output_order": 2},
        {"name": "allocated_to", "ownership": "system", "output_order": 3},
        {"name": "run_id", "ownership": "system", "output_order": 4},
    ]


class SanitizeForFilenameTestCase(unittest.TestCase):
    def test_replaces_unsafe_characters(self) -> None:
        self.assertEqual(sanitize_for_filename("O'Brien/Smith"), "O_Brien_Smith")

    def test_collapses_whitespace(self) -> None:
        self.assertEqual(sanitize_for_filename("Jane   Doe"), "Jane_Doe")

    def test_blank_becomes_unnamed(self) -> None:
        self.assertEqual(sanitize_for_filename("   "), "unnamed")


class BuildFilenameTestCase(unittest.TestCase):
    def test_substitutes_all_tokens(self) -> None:
        filename = build_filename(
            "{PROGRAM}_{ASSOCIATE_ID}_{ASSOCIATE_NAME}_{RUN_ID}.xlsx",
            program_id="MX-PT", run_id="MX-PT-20260815-01", associate_id="A001", associate_name="Jane Doe",
        )
        self.assertEqual(filename, "MX-PT_A001_Jane_Doe_MX-PT-20260815-01.xlsx")


class BuildAssociateFileContentTestCase(unittest.TestCase):
    def test_headers_follow_output_order_and_use_source_column_or_title_case(self) -> None:
        assignment = AllocationAssignment(associate_id="A001", target=1, maximum_capacity=1, planned_count=1, assigned_identifiers=("P1",), above_target=False)
        content = build_associate_file_content(
            assignment=assignment, associate_name="Jane Doe", fields=_fields(),
            canonical_rows_by_identifier={"P1": {"product_id": "P1", "pt": "Shoes"}},
            run_id="MX-PT-20260815-01", program_id="MX-PT", filename_pattern="{PROGRAM}_{ASSOCIATE_ID}_{ASSOCIATE_NAME}_{RUN_ID}.xlsx",
        )
        self.assertEqual(content.headers, ("Product ID", "PT", "Partner Feedback", "Allocated To", "Run ID"))

    def test_source_fields_prefilled_response_blank_system_populated(self) -> None:
        assignment = AllocationAssignment(associate_id="A001", target=1, maximum_capacity=1, planned_count=1, assigned_identifiers=("P1",), above_target=False)
        content = build_associate_file_content(
            assignment=assignment, associate_name="Jane Doe", fields=_fields(),
            canonical_rows_by_identifier={"P1": {"product_id": "P1", "pt": "Shoes"}},
            run_id="MX-PT-20260815-01", program_id="MX-PT", filename_pattern="{PROGRAM}_{ASSOCIATE_ID}_{ASSOCIATE_NAME}_{RUN_ID}.xlsx",
        )
        self.assertEqual(content.rows, (("P1", "Shoes", None, "A001", "MX-PT-20260815-01"),))

    def test_filename_uses_associate_name_not_id(self) -> None:
        assignment = AllocationAssignment(associate_id="A001", target=1, maximum_capacity=1, planned_count=1, assigned_identifiers=("P1",), above_target=False)
        content = build_associate_file_content(
            assignment=assignment, associate_name="Jane Doe", fields=_fields(),
            canonical_rows_by_identifier={"P1": {"product_id": "P1", "pt": "Shoes"}},
            run_id="MX-PT-20260815-01", program_id="MX-PT", filename_pattern="{PROGRAM}_{ASSOCIATE_ID}_{ASSOCIATE_NAME}_{RUN_ID}.xlsx",
        )
        self.assertEqual(content.filename, "MX-PT_A001_Jane_Doe_MX-PT-20260815-01.xlsx")

    def test_missing_canonical_row_raises_clear_error(self) -> None:
        assignment = AllocationAssignment(associate_id="A001", target=1, maximum_capacity=1, planned_count=1, assigned_identifiers=("MISSING",), above_target=False)
        with self.assertRaises(AssignedItemNotFoundError):
            build_associate_file_content(
                assignment=assignment, associate_name="Jane Doe", fields=_fields(),
                canonical_rows_by_identifier={}, run_id="MX-PT-20260815-01", program_id="MX-PT",
                filename_pattern="{PROGRAM}_{ASSOCIATE_ID}_{ASSOCIATE_NAME}_{RUN_ID}.xlsx",
            )
