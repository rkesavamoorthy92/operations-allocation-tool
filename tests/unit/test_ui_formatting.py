from __future__ import annotations

import unittest
from datetime import datetime
from decimal import Decimal

from operations_allocation.domain.models import RunState
from operations_allocation.ui.formatting import (
    format_count,
    format_percentage,
    format_percentage_point_change,
    format_timestamp,
    state_label,
)


class StateLabelTestCase(unittest.TestCase):
    def test_formats_snake_case_state(self) -> None:
        self.assertEqual(state_label(RunState.SNAPSHOT_FROZEN), "Snapshot Frozen")
        self.assertEqual(state_label(RunState.QC_COMPLETED), "Qc Completed")
        self.assertEqual(state_label(RunState.DRAFT), "Draft")


class FormatPercentageTestCase(unittest.TestCase):
    def test_formats_decimal(self) -> None:
        self.assertEqual(format_percentage(Decimal("80")), "80.00%")

    def test_not_applicable_flag_wins(self) -> None:
        self.assertEqual(format_percentage(Decimal("80"), is_not_applicable=True), "N/A")

    def test_none_value_is_not_applicable(self) -> None:
        self.assertEqual(format_percentage(None), "N/A")


class FormatPercentagePointChangeTestCase(unittest.TestCase):
    def test_spec_worked_example(self) -> None:
        self.assertEqual(format_percentage_point_change(Decimal("91.7"), Decimal("94.2")), "-2.5 percentage points")

    def test_positive_change_has_explicit_sign(self) -> None:
        self.assertEqual(format_percentage_point_change(Decimal("95.0"), Decimal("90.0")), "+5.0 percentage points")

    def test_no_previous_value_is_not_applicable(self) -> None:
        self.assertEqual(format_percentage_point_change(Decimal("95.0"), None), "N/A")


class FormatTimestampTestCase(unittest.TestCase):
    def test_formats_iso_datetime(self) -> None:
        self.assertEqual(format_timestamp(datetime(2026, 8, 15, 14, 30)), "2026-08-15 14:30")


class FormatCountTestCase(unittest.TestCase):
    def test_singular(self) -> None:
        self.assertEqual(format_count(1, noun="item"), "1 item")

    def test_plural(self) -> None:
        self.assertEqual(format_count(2, noun="item"), "2 items")

    def test_zero_is_plural(self) -> None:
        self.assertEqual(format_count(0, noun="error"), "0 errors")
