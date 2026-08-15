from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook

from operations_allocation.domain.exceptions import UnsupportedFileFormatError
from operations_allocation.infrastructure.tabular_import import read_raw_table


class ReadRawTableCsvTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _write_csv(self, rows: list[list[str]]) -> Path:
        path = Path(self.tempdir.name) / "input.csv"
        with path.open("w", newline="", encoding="utf-8") as handle:
            csv.writer(handle).writerows(rows)
        return path

    def test_reads_headers_and_rows(self) -> None:
        path = self._write_csv([["Product ID", "PT"], ["P1", "Shoes"], ["P2", "Bags"]])
        table = read_raw_table(path)
        self.assertEqual(table.headers, ("Product ID", "PT"))
        self.assertEqual(table.rows, ({"Product ID": "P1", "PT": "Shoes"}, {"Product ID": "P2", "PT": "Bags"}))

    def test_preserves_leading_zeros(self) -> None:
        path = self._write_csv([["Product ID"], ["00042"]])
        table = read_raw_table(path)
        self.assertEqual(table.rows[0]["Product ID"], "00042")

    def test_blank_cell_becomes_none(self) -> None:
        path = self._write_csv([["Product ID", "PT"], ["P1", ""]])
        table = read_raw_table(path)
        self.assertIsNone(table.rows[0]["PT"])

    def test_fully_blank_rows_are_skipped(self) -> None:
        path = self._write_csv([["Product ID"], ["P1"], ["", ""], ["P2"]])
        table = read_raw_table(path)
        self.assertEqual(len(table.rows), 2)

    def test_empty_file_returns_empty_table(self) -> None:
        path = Path(self.tempdir.name) / "empty.csv"
        path.write_text("", encoding="utf-8")
        table = read_raw_table(path)
        self.assertEqual(table.headers, ())
        self.assertEqual(table.rows, ())


class ReadRawTableXlsxTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _write_xlsx(self, rows: list[list[object]]) -> Path:
        path = Path(self.tempdir.name) / "input.xlsx"
        workbook = Workbook()
        sheet = workbook.active
        for row in rows:
            sheet.append(row)
        workbook.save(path)
        return path

    def test_reads_headers_and_rows(self) -> None:
        path = self._write_xlsx([["Product ID", "PT"], ["P1", "Shoes"]])
        table = read_raw_table(path)
        self.assertEqual(table.headers, ("Product ID", "PT"))
        self.assertEqual(table.rows, ({"Product ID": "P1", "PT": "Shoes"},))

    def test_string_identifier_with_leading_zeros_preserved(self) -> None:
        # Written as an explicit string value (as a Text-formatted Excel
        # column would contain) -- openpyxl round-trips it unchanged.
        path = self._write_xlsx([["Product ID"], ["00042"]])
        table = read_raw_table(path)
        self.assertEqual(table.rows[0]["Product ID"], "00042")

    def test_integer_cell_rendered_without_decimal_or_scientific_notation(self) -> None:
        path = self._write_xlsx([["Count"], [42]])
        table = read_raw_table(path)
        self.assertEqual(table.rows[0]["Count"], "42")

    def test_integral_float_cell_rendered_without_trailing_zero(self) -> None:
        path = self._write_xlsx([["Count"], [42.0]])
        table = read_raw_table(path)
        self.assertEqual(table.rows[0]["Count"], "42")

    def test_blank_cell_becomes_none(self) -> None:
        path = self._write_xlsx([["Product ID", "PT"], ["P1", None]])
        table = read_raw_table(path)
        self.assertIsNone(table.rows[0]["PT"])

    def test_fully_blank_rows_are_skipped(self) -> None:
        path = self._write_xlsx([["Product ID"], ["P1"], [None], ["P2"]])
        table = read_raw_table(path)
        self.assertEqual(len(table.rows), 2)


class ReadRawTableFormatTestCase(unittest.TestCase):
    def test_xls_is_rejected_as_deferred(self) -> None:
        with self.assertRaises(UnsupportedFileFormatError):
            read_raw_table("legacy.xls")

    def test_unknown_extension_is_rejected(self) -> None:
        with self.assertRaises(UnsupportedFileFormatError):
            read_raw_table("data.txt")
