from __future__ import annotations

import unittest
from decimal import Decimal

from operations_allocation.core.qc import evaluate_qc_rule, evaluate_qc_rules, parse_qc_rule
from operations_allocation.domain.exceptions import InvalidQcRuleError


def qc_score_rule_config() -> dict:
    return {"name": "qc_score", "rule_type": "ratio_percentage", "numerator": "pass_count", "denominator": "audited_count"}


def error_rate_rule_config() -> dict:
    return {"name": "error_rate", "rule_type": "ratio_percentage", "numerator": "fail_count", "denominator": "audited_count"}


class ParseQcRuleTestCase(unittest.TestCase):
    def test_parses_valid_rule(self) -> None:
        rule = parse_qc_rule(qc_score_rule_config())
        self.assertEqual(rule.name, "qc_score")
        self.assertEqual(rule.zero_denominator_behavior, "N/A")

    def test_rejects_missing_name(self) -> None:
        config = qc_score_rule_config(); del config["name"]
        with self.assertRaises(InvalidQcRuleError):
            parse_qc_rule(config)

    def test_rejects_unsupported_rule_type(self) -> None:
        config = qc_score_rule_config(); config["rule_type"] = "weighted_average"
        with self.assertRaises(InvalidQcRuleError):
            parse_qc_rule(config)

    def test_rejects_missing_numerator(self) -> None:
        config = qc_score_rule_config(); del config["numerator"]
        with self.assertRaises(InvalidQcRuleError):
            parse_qc_rule(config)

    def test_rejects_missing_denominator(self) -> None:
        config = qc_score_rule_config(); del config["denominator"]
        with self.assertRaises(InvalidQcRuleError):
            parse_qc_rule(config)

    def test_rejects_unsupported_zero_denominator_behavior(self) -> None:
        config = qc_score_rule_config(); config["zero_denominator_behavior"] = "TREAT_AS_ZERO"
        with self.assertRaises(InvalidQcRuleError):
            parse_qc_rule(config)

    def test_rejects_eval_style_rule_type_as_unsupported(self) -> None:
        # Defense in depth: even a maliciously crafted rule_type is just an
        # unrecognized string to this parser, never something executed.
        config = qc_score_rule_config(); config["rule_type"] = "eval(counts)"
        with self.assertRaises(InvalidQcRuleError):
            parse_qc_rule(config)


class EvaluateQcRuleTestCase(unittest.TestCase):
    def test_spec_worked_example_qc_score_and_error_rate(self) -> None:
        counts = {"pass_count": 8, "fail_count": 2, "audited_count": 10}
        qc_score = evaluate_qc_rule(parse_qc_rule(qc_score_rule_config()), counts)
        error_rate = evaluate_qc_rule(parse_qc_rule(error_rate_rule_config()), counts)
        self.assertFalse(qc_score.is_not_applicable)
        self.assertEqual(qc_score.value, Decimal(80))
        self.assertFalse(error_rate.is_not_applicable)
        self.assertEqual(error_rate.value, Decimal(20))

    def test_zero_denominator_is_not_applicable_never_pass(self) -> None:
        counts = {"pass_count": 0, "audited_count": 0}
        result = evaluate_qc_rule(parse_qc_rule(qc_score_rule_config()), counts)
        self.assertTrue(result.is_not_applicable)
        self.assertIsNone(result.value)

    def test_missing_count_field_raises(self) -> None:
        with self.assertRaises(InvalidQcRuleError):
            evaluate_qc_rule(parse_qc_rule(qc_score_rule_config()), {"audited_count": 10})

    def test_negative_count_rejected(self) -> None:
        with self.assertRaises(InvalidQcRuleError):
            evaluate_qc_rule(parse_qc_rule(qc_score_rule_config()), {"pass_count": -1, "audited_count": 10})

    def test_boolean_count_rejected(self) -> None:
        with self.assertRaises(InvalidQcRuleError):
            evaluate_qc_rule(parse_qc_rule(qc_score_rule_config()), {"pass_count": True, "audited_count": 10})

    def test_full_pass_is_100_percent(self) -> None:
        result = evaluate_qc_rule(parse_qc_rule(qc_score_rule_config()), {"pass_count": 5, "audited_count": 5})
        self.assertEqual(result.value, Decimal(100))

    def test_evaluate_multiple_rules_keyed_by_name(self) -> None:
        rules = [parse_qc_rule(qc_score_rule_config()), parse_qc_rule(error_rate_rule_config())]
        counts = {"pass_count": 8, "fail_count": 2, "audited_count": 10}
        results = evaluate_qc_rules(rules, counts)
        self.assertEqual(set(results), {"qc_score", "error_rate"})
        self.assertEqual(results["qc_score"].value, Decimal(80))
        self.assertEqual(results["error_rate"].value, Decimal(20))
