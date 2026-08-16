from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook

from operations_allocation.domain.exceptions import InvalidReturnedFileError
from operations_allocation.infrastructure.returned_file_reader import read_returned_workbook
from operations_allocation.infrastructure.xlsx_writer import write_associate_workbook


class ReadReturnedWorkbookTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_reads_a_real_distributed_work_file(self) -> None:
        content = write_associate_workbook(
            metadata={"Run ID": "R1", "Associate ID": "A001", "Associate Name": "Jane"},
            headers=("product_id", "run_id", "allocated_to"),
            rows=[["P001", "R1", "A001"]],
        )
        path = Path(self.tempdir.name) / "work.xlsx"
        path.write_bytes(content)

        workbook = read_returned_workbook(path)
        self.assertEqual(workbook.metadata["Associate ID"], "A001")
        self.assertEqual(len(workbook.rows), 1)

    def test_raises_a_clear_error_for_a_file_missing_both_sheets(self) -> None:
        # Regression: a user selecting the wrong file (e.g. the original
        # source spreadsheet instead of a distributed work file) used to
        # get a bare, confusing openpyxl KeyError ("Worksheet Metadata
        # does not exist"). This should now be a clear, actionable error.
        plain_workbook = Workbook()
        plain_workbook.active.title = "Sheet1"
        path = Path(self.tempdir.name) / "wrong_file.xlsx"
        plain_workbook.save(path)

        with self.assertRaises(InvalidReturnedFileError) as context:
            read_returned_workbook(path)
        message = str(context.exception)
        self.assertIn("Metadata", message)
        self.assertIn("Data", message)
        self.assertIn("wrong_file.xlsx", message)

    def test_raises_a_clear_error_when_only_one_sheet_is_missing(self) -> None:
        workbook = Workbook()
        workbook.active.title = "Metadata"
        path = Path(self.tempdir.name) / "half_right.xlsx"
        workbook.save(path)

        with self.assertRaises(InvalidReturnedFileError) as context:
            read_returned_workbook(path)
        self.assertIn("Data", str(context.exception))
