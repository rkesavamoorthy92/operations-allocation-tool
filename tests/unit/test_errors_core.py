from __future__ import annotations

import unittest

from operations_allocation.core.errors import UNCLASSIFIED, classify, parse_classification_rule
from operations_allocation.domain.exceptions import InvalidErrorRuleError


def _rule(match: dict, category="Missing", error_type="Item Not Returned", severity="Critical") -> dict:
    return {"match": match, "category": category, "type": error_type, "severity": severity}


class ParseClassificationRuleTestCase(unittest.TestCase):
    def test_parses_valid_rule(self) -> None:
        rule = parse_classification_rule(_rule({"disposition": "missing"}))
        self.assertEqual(rule.category, "Missing")
        self.assertEqual(rule.match, {"disposition": "missing"})

    def test_rejects_empty_match(self) -> None:
        with self.assertRaises(InvalidErrorRuleError):
            parse_classification_rule(_rule({}))

    def test_rejects_non_string_match_value(self) -> None:
        with self.assertRaises(InvalidErrorRuleError):
            parse_classification_rule(_rule({"count": 1}))

    def test_rejects_missing_category(self) -> None:
        raw = _rule({"disposition": "missing"}); del raw["category"]
        with self.assertRaises(InvalidErrorRuleError):
            parse_classification_rule(raw)

    def test_rejects_blank_severity(self) -> None:
        raw = _rule({"disposition": "missing"}, severity="  ")
        with self.assertRaises(InvalidErrorRuleError):
            parse_classification_rule(raw)


class ClassifyTestCase(unittest.TestCase):
    def test_matching_rule_returns_its_classification(self) -> None:
        rules = [parse_classification_rule(_rule({"disposition": "missing"}, category="Missing", error_type="Not Returned", severity="Critical"))]
        result = classify({"disposition": "missing"}, rules)
        self.assertEqual(result, ("Missing", "Not Returned", "Critical"))

    def test_first_matching_rule_wins(self) -> None:
        rules = [
            parse_classification_rule(_rule({"disposition": "duplicate"}, category="First", error_type="A", severity="Low")),
            parse_classification_rule(_rule({"disposition": "duplicate"}, category="Second", error_type="B", severity="High")),
        ]
        self.assertEqual(classify({"disposition": "duplicate"}, rules)[0], "First")

    def test_no_match_returns_unclassified(self) -> None:
        rules = [parse_classification_rule(_rule({"disposition": "missing"}))]
        self.assertEqual(classify({"disposition": "unexpected"}, rules), (UNCLASSIFIED, UNCLASSIFIED, UNCLASSIFIED))

    def test_rule_requires_all_match_fields(self) -> None:
        rules = [parse_classification_rule(_rule({"disposition": "duplicate", "associate_id": "A001"}))]
        self.assertEqual(classify({"disposition": "duplicate", "associate_id": "A002"}, rules)[0], UNCLASSIFIED)

    def test_empty_rules_always_unclassified(self) -> None:
        self.assertEqual(classify({"disposition": "missing"}, []), (UNCLASSIFIED, UNCLASSIFIED, UNCLASSIFIED))
