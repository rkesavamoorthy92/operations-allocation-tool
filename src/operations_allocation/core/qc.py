"""QC Rule Evaluator — restricted declarative QC rule execution.

Implements PROJECT_SPEC.md section 22-23 / ARCHITECTURE.md section 4.8 /
9.1: QC calculations are configurable per program but must NEVER use
`eval()`, `exec()`, arbitrary Python expressions, or unrestricted
user-entered formulas. This module has no code-execution path at all --
only a closed dispatch table of named, hand-implemented rule types, so
there is nothing an untrusted configuration document could inject.

The only rule type supported in v1 is ``ratio_percentage``
(numerator / denominator * 100), with the MX PT-configured intent:

    QC Score  = Pass Count  / Audited Count * 100
    Error Rate = Fail Count / Audited Count * 100

If the denominator is 0, the result is N/A -- never silently treated as a
Pass (PROJECT_SPEC.md section 22 / AGENTS.md section 12).

This evaluator is level-agnostic: the same rule can be evaluated against
item-level, associate-level, or run-level ``counts`` mappings supplied by
the caller (ARCHITECTURE.md section 4.8, "QC must support item-level,
associate-level, and run-level metrics").
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping

from operations_allocation.domain.exceptions import InvalidQcRuleError

SUPPORTED_RULE_TYPES = frozenset({"ratio_percentage"})
SUPPORTED_ZERO_DENOMINATOR_BEHAVIORS = frozenset({"N/A"})


@dataclass(frozen=True, slots=True)
class QcRule:
    name: str
    rule_type: str
    numerator_field: str
    denominator_field: str
    zero_denominator_behavior: str = "N/A"


@dataclass(frozen=True, slots=True)
class QcMetricResult:
    rule_name: str
    numerator: int
    denominator: int
    is_not_applicable: bool
    value: Decimal | None
    """Percentage value (e.g. 80 for 80%), or None when ``is_not_applicable``."""


def parse_qc_rule(rule: Mapping[str, object]) -> QcRule:
    """Parse and validate a QC rule from a Run Configuration Snapshot."""
    name = rule.get("name")
    rule_type = rule.get("rule_type")
    numerator_field = rule.get("numerator")
    denominator_field = rule.get("denominator")
    zero_denominator_behavior = rule.get("zero_denominator_behavior", "N/A")

    if not isinstance(name, str) or not name.strip():
        raise InvalidQcRuleError("QC rule requires a non-empty name.")
    if rule_type not in SUPPORTED_RULE_TYPES:
        raise InvalidQcRuleError(f"Unsupported QC rule_type '{rule_type}'. Supported types: {sorted(SUPPORTED_RULE_TYPES)}.")
    if not isinstance(numerator_field, str) or not numerator_field.strip():
        raise InvalidQcRuleError(f"QC rule '{name}' requires a non-empty numerator field name.")
    if not isinstance(denominator_field, str) or not denominator_field.strip():
        raise InvalidQcRuleError(f"QC rule '{name}' requires a non-empty denominator field name.")
    if zero_denominator_behavior not in SUPPORTED_ZERO_DENOMINATOR_BEHAVIORS:
        raise InvalidQcRuleError(
            f"QC rule '{name}' has an unsupported zero_denominator_behavior '{zero_denominator_behavior}'. "
            f"Supported values: {sorted(SUPPORTED_ZERO_DENOMINATOR_BEHAVIORS)}."
        )
    return QcRule(name=name, rule_type=rule_type, numerator_field=numerator_field, denominator_field=denominator_field, zero_denominator_behavior=zero_denominator_behavior)


def evaluate_qc_rule(rule: QcRule, counts: Mapping[str, int]) -> QcMetricResult:
    """Evaluate one parsed QC rule against a counts mapping.

    ``counts`` may represent item-level, associate-level, or run-level
    aggregates -- this function does not care which, so long as it
    contains ``rule.numerator_field`` and ``rule.denominator_field`` as
    non-negative integers.
    """
    if rule.rule_type != "ratio_percentage":
        raise InvalidQcRuleError(f"Unsupported QC rule_type '{rule.rule_type}'.")

    for field_name in (rule.numerator_field, rule.denominator_field):
        if field_name not in counts:
            raise InvalidQcRuleError(f"QC rule '{rule.name}' requires count field '{field_name}', which was not provided.")
        value = counts[field_name]
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise InvalidQcRuleError(f"QC rule '{rule.name}' count field '{field_name}' must be a non-negative integer.")

    numerator = counts[rule.numerator_field]
    denominator = counts[rule.denominator_field]

    if denominator == 0:
        return QcMetricResult(rule_name=rule.name, numerator=numerator, denominator=denominator, is_not_applicable=True, value=None)

    percentage = (Decimal(numerator) * Decimal(100)) / Decimal(denominator)
    return QcMetricResult(rule_name=rule.name, numerator=numerator, denominator=denominator, is_not_applicable=False, value=percentage)


def evaluate_qc_rules(rules: list[QcRule], counts: Mapping[str, int]) -> dict[str, QcMetricResult]:
    return {rule.name: evaluate_qc_rule(rule, counts) for rule in rules}
