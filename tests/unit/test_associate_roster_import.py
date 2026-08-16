from __future__ import annotations

import unittest

from operations_allocation.core.associate_roster_import import parse_associate_roster
from operations_allocation.core.column_mapping import RawTable
from operations_allocation.domain.exceptions import InvalidAssociateConfigurationError


class ParseAssociateRosterTestCase(unittest.TestCase):
    def test_parses_rows_with_exact_headers(self) -> None:
        table = RawTable(
            headers=("Associate ID", "Name", "Email", "Target", "Max Capacity"),
            rows=(
                {"Associate ID": "A001", "Name": "Jane Doe", "Email": "jane@example.test", "Target": "10", "Max Capacity": "12"},
                {"Associate ID": "A002", "Name": "John Roe", "Email": "john@example.test", "Target": "8", "Max Capacity": "9"},
            ),
        )
        associates = parse_associate_roster(table)
        self.assertEqual(len(associates), 2)
        self.assertEqual(associates[0], {"associate_id": "A001", "name": "Jane Doe", "email": "jane@example.test", "active": True, "target": 10, "maximum_capacity": 12})

    def test_matches_common_header_synonyms_case_insensitively(self) -> None:
        table = RawTable(
            headers=("id", "Associate Name", "Email Address", "target", "MaxCapacity"),
            rows=({"id": "A001", "Associate Name": "Jane Doe", "Email Address": "jane@example.test", "target": "5", "MaxCapacity": "5"},),
        )
        associates = parse_associate_roster(table)
        self.assertEqual(associates[0]["associate_id"], "A001")
        self.assertEqual(associates[0]["maximum_capacity"], 5)

    def test_skips_rows_with_blank_associate_id(self) -> None:
        table = RawTable(
            headers=("Associate ID", "Name", "Email", "Target", "Max Capacity"),
            rows=({"Associate ID": "", "Name": "Ghost", "Email": "", "Target": "1", "Max Capacity": "1"},),
        )
        self.assertEqual(parse_associate_roster(table), [])

    def test_defaults_blank_target_and_capacity_to_zero(self) -> None:
        table = RawTable(
            headers=("Associate ID", "Name", "Email", "Target", "Max Capacity"),
            rows=({"Associate ID": "A001", "Name": "Jane Doe", "Email": "", "Target": "", "Max Capacity": None},),
        )
        associate = parse_associate_roster(table)[0]
        self.assertEqual(associate["target"], 0)
        self.assertEqual(associate["maximum_capacity"], 0)

    def test_raises_on_missing_required_column(self) -> None:
        table = RawTable(headers=("Name", "Email"), rows=())
        with self.assertRaises(InvalidAssociateConfigurationError):
            parse_associate_roster(table)

    def test_raises_on_non_numeric_target(self) -> None:
        table = RawTable(
            headers=("Associate ID", "Name", "Email", "Target", "Max Capacity"),
            rows=({"Associate ID": "A001", "Name": "Jane Doe", "Email": "", "Target": "ten", "Max Capacity": "5"},),
        )
        with self.assertRaises(InvalidAssociateConfigurationError):
            parse_associate_roster(table)

    def test_raises_on_negative_capacity(self) -> None:
        table = RawTable(
            headers=("Associate ID", "Name", "Email", "Target", "Max Capacity"),
            rows=({"Associate ID": "A001", "Name": "Jane Doe", "Email": "", "Target": "1", "Max Capacity": "-1"},),
        )
        with self.assertRaises(InvalidAssociateConfigurationError):
            parse_associate_roster(table)
