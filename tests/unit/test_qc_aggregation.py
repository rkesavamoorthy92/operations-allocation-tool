from __future__ import annotations

import unittest
from decimal import Decimal

from operations_allocation.core.qc import parse_qc_rule
from operations_allocation.core.qc_aggregation import QcAuditRecord, QcOutcome, build_qc_report, counts_for, parse_outcome
from operations_allocation.domain.exceptions import InvalidQcResultError


def _rules() -> list:
    return [
        parse_qc_rule({"name": "qc_score", "rule_type": "ratio_percentage", "numerator": "pass_count", "denominator": "audited_count"}),
        parse_qc_rule({"name": "error_rate", "rule_type": "ratio_percentage", "numerator": "fail_count", "denominator": "audited_count"}),
    ]


class ParseOutcomeTestCase(unittest.TestCase):
    def test_recognizes_pass_and_fail_case_insensitively(self) -> None:
        self.assertEqual(parse_outcome("Pass", pass_label="Pass", fail_label="Fail"), QcOutcome.PASS)
        self.assertEqual(parse_outcome("FAIL", pass_label="Pass", fail_label="Fail"), QcOutcome.FAIL)

    def test_unrecognized_value_raises(self) -> None:
        with self.assertRaises(InvalidQcResultError):
            parse_outcome("Maybe", pass_label="Pass", fail_label="Fail")

    def test_non_string_raises(self) -> None:
        with self.assertRaises(InvalidQcResultError):
            parse_outcome(None, pass_label="Pass", fail_label="Fail")


class CountsForTestCase(unittest.TestCase):
    def test_counts_pass_fail_and_audited(self) -> None:
        records = [QcAuditRecord("P1", "A", QcOutcome.PASS), QcAuditRecord("P2", "A", QcOutcome.FAIL), QcAuditRecord("P3", "A", QcOutcome.PASS)]
        self.assertEqual(counts_for(records), {"pass_count": 2, "fail_count": 1, "audited_count": 3})

    def test_empty_records_all_zero(self) -> None:
        self.assertEqual(counts_for([]), {"pass_count": 0, "fail_count": 0, "audited_count": 0})


class BuildQcReportTestCase(unittest.TestCase):
    def test_spec_worked_example(self) -> None:
        records = [QcAuditRecord(f"P{i}", "A", QcOutcome.PASS) for i in range(8)] + [QcAuditRecord(f"F{i}", "A", QcOutcome.FAIL) for i in range(2)]
        report = build_qc_report(records, _rules())
        self.assertEqual(report.run_metrics["qc_score"].value, Decimal(80))
        self.assertEqual(report.run_metrics["error_rate"].value, Decimal(20))

    def test_per_associate_breakdown(self) -> None:
        records = [QcAuditRecord("P1", "A", QcOutcome.PASS), QcAuditRecord("P2", "B", QcOutcome.FAIL)]
        report = build_qc_report(records, _rules())
        self.assertEqual(report.associate_metrics["A"]["qc_score"].value, Decimal(100))
        self.assertEqual(report.associate_metrics["B"]["qc_score"].value, Decimal(0))
        self.assertEqual(report.run_metrics["qc_score"].value, Decimal(50))

    def test_no_records_run_metrics_are_not_applicable(self) -> None:
        report = build_qc_report([], _rules())
        self.assertTrue(report.run_metrics["qc_score"].is_not_applicable)
        self.assertEqual(report.associate_metrics, {})
