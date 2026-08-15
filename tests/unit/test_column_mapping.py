from __future__ import annotations

import unittest

from operations_allocation.core.column_mapping import RawTable, map_rows
from operations_allocation.domain.exceptions import ColumnMappingError


class MapRowsTestCase(unittest.TestCase):
    def test_maps_by_configured_column_name_regardless_of_order(self) -> None:
        table = RawTable(headers=("PT", "Product ID"), rows=({"PT": "Shoes", "Product ID": "P1"},))
        mapped = map_rows(table, {"product_id": "Product ID", "pt": "PT", "allocated_to": None})
        self.assertEqual(mapped, [{"product_id": "P1", "pt": "Shoes"}])

    def test_system_fields_without_source_column_are_omitted(self) -> None:
        table = RawTable(headers=("Product ID",), rows=({"Product ID": "P1"},))
        mapped = map_rows(table, {"product_id": "Product ID", "allocated_to": None})
        self.assertEqual(mapped, [{"product_id": "P1"}])

    def test_missing_required_source_column_raises_clear_error(self) -> None:
        table = RawTable(headers=("Product ID",), rows=({"Product ID": "P1"},))
        with self.assertRaises(ColumnMappingError) as context:
            map_rows(table, {"product_id": "Product ID", "pt": "PT"})
        self.assertIn("PT", str(context.exception))

    def test_blank_cell_maps_to_none_not_missing_column(self) -> None:
        table = RawTable(headers=("Product ID", "PT"), rows=({"Product ID": "P1", "PT": None},))
        mapped = map_rows(table, {"product_id": "Product ID", "pt": "PT"})
        self.assertIsNone(mapped[0]["pt"])

    def test_empty_table_maps_to_empty_list(self) -> None:
        table = RawTable(headers=("Product ID",), rows=())
        self.assertEqual(map_rows(table, {"product_id": "Product ID"}), [])

    def test_does_not_assume_column_order(self) -> None:
        table_a = RawTable(headers=("A", "B"), rows=({"A": "1", "B": "2"},))
        table_b = RawTable(headers=("B", "A"), rows=({"B": "2", "A": "1"},))
        mappings = {"first": "A", "second": "B"}
        self.assertEqual(map_rows(table_a, mappings), map_rows(table_b, mappings))
