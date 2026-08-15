"""Structural validation for versioned, program-agnostic configuration documents."""

from __future__ import annotations

import re
from typing import Any

from operations_allocation.domain.exceptions import InvalidConfigurationError

VALID_DATA_TYPES = {"string", "integer", "decimal", "boolean", "date", "datetime"}
VALID_OWNERSHIPS = {"source", "response", "system"}


def validate_program_configuration(config: dict[str, Any]) -> None:
    """Validate the Phase 1 configuration contract without interpreting workflows."""
    _require_mapping(config, "configuration")
    _require_non_empty_string(config, "program_id")
    _require_non_empty_string(config, "program_name")
    if not re.fullmatch(r"[A-Z0-9]+(?:-[A-Z0-9]+)*", config["program_id"]):
        raise InvalidConfigurationError("program_id must use uppercase letters, digits, and internal hyphens only.")
    version = config.get("version")
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise InvalidConfigurationError("Configuration version must be a positive integer.")
    identifier = config.get("primary_identifier")
    _require_mapping(identifier, "primary_identifier")
    _require_non_empty_string(identifier, "field")
    if not isinstance(identifier.get("case_sensitive"), bool):
        raise InvalidConfigurationError("primary_identifier.case_sensitive must be a boolean.")
    normalization = identifier.get("normalization")
    _require_mapping(normalization, "primary_identifier.normalization")
    if not isinstance(normalization.get("trim_whitespace"), bool):
        raise InvalidConfigurationError("primary_identifier.normalization.trim_whitespace must be a boolean.")
    for option in ("preserve_leading_zeros", "preserve_scientific_notation"):
        if option in normalization and not isinstance(normalization[option], bool):
            raise InvalidConfigurationError(f"primary_identifier.normalization.{option} must be a boolean.")

    _validate_column_definitions(config.get("input_columns"), "input_columns", "source")
    _validate_column_definitions(config.get("response_columns"), "response_columns", "response")

    fields = config.get("fields")
    if not isinstance(fields, list) or not fields:
        raise InvalidConfigurationError("Configuration requires a non-empty fields list.")
    names: set[str] = set()
    for field in fields:
        _require_mapping(field, "field")
        name = field.get("name")
        if not isinstance(name, str) or not name.strip():
            raise InvalidConfigurationError("Every field requires a non-empty name.")
        if name in names:
            raise InvalidConfigurationError(f"Duplicate configured field '{name}'.")
        names.add(name)
        if field.get("ownership") not in VALID_OWNERSHIPS:
            raise InvalidConfigurationError("Field ownership must be source, response, or system.")
        if field.get("data_type") not in VALID_DATA_TYPES:
            raise InvalidConfigurationError(f"Unsupported data type for field '{name}'.")
        if not isinstance(field.get("required"), bool):
            raise InvalidConfigurationError(f"Field '{name}' required must be a boolean.")
        if isinstance(field.get("output_order"), bool) or not isinstance(field.get("output_order"), int) or field["output_order"] < 0:
            raise InvalidConfigurationError(f"Field '{name}' output_order must be a non-negative integer.")
    if len({field["output_order"] for field in fields}) != len(fields):
        raise InvalidConfigurationError("Field output_order values must be unique.")
    if identifier["field"] not in names:
        raise InvalidConfigurationError("The primary identifier must name a configured field.")

    _validate_section_structures(config)


def _require_mapping(value: object, label: str) -> None:
    if not isinstance(value, dict):
        raise InvalidConfigurationError(f"{label} must be an object.")


def _require_non_empty_string(mapping: dict[str, Any], key: str) -> None:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        raise InvalidConfigurationError(f"{key} must be a non-empty string.")


def _validate_column_definitions(value: object, label: str, ownership: str) -> None:
    if not isinstance(value, list) or not value:
        raise InvalidConfigurationError(f"{label} must be a non-empty list.")
    for column in value:
        _require_mapping(column, label)
        _require_non_empty_string(column, "name")
        source_name = column.get("column", column.get("source_column"))
        if not isinstance(source_name, str) or not source_name.strip():
            raise InvalidConfigurationError(f"{label} entries require a non-empty column name.")
        if column.get("ownership", ownership) != ownership:
            raise InvalidConfigurationError(f"{label} entries must have {ownership} ownership.")
        if column.get("data_type") not in VALID_DATA_TYPES:
            raise InvalidConfigurationError(f"{label} entries require a supported data_type.")
        if not isinstance(column.get("required"), bool):
            raise InvalidConfigurationError(f"{label} entries require a boolean required value.")


def _validate_section_structures(config: dict[str, Any]) -> None:
    validation = config.get("validation")
    allocation = config.get("allocation")
    tie_breaking = config.get("tie_breaking")
    qc = config.get("qc")
    errors = config.get("errors")
    filename = config.get("filename")
    email = config.get("email")
    for section, value in (("validation", validation), ("allocation", allocation), ("tie_breaking", tie_breaking), ("qc", qc), ("errors", errors), ("filename", filename), ("email", email)):
        _require_mapping(value, section)
    sampling = config.get("sampling")
    _require_mapping(sampling, "sampling")
    if not sampling:
        raise InvalidConfigurationError("sampling must define an allowed method or method.")
    if "method" in sampling and sampling["method"] not in {"percentage", "count"}:
        raise InvalidConfigurationError("sampling.method must be percentage or count.")
    if "allowed_methods" in sampling:
        if not isinstance(sampling["allowed_methods"], list) or not sampling["allowed_methods"] or any(item not in {"percentage", "count"} for item in sampling["allowed_methods"]):
            raise InvalidConfigurationError("sampling.allowed_methods must contain percentage and/or count.")
    strategy = allocation.get("strategy")
    if not isinstance(strategy, str) or not strategy.strip():
        raise InvalidConfigurationError("allocation.strategy must be a non-empty string.")
    if "overflow_strategy" in allocation and not isinstance(allocation["overflow_strategy"], str):
        raise InvalidConfigurationError("allocation.overflow_strategy must be a string.")
    if not isinstance(tie_breaking.get("field"), str) or not tie_breaking["field"].strip():
        raise InvalidConfigurationError("tie_breaking.field must be a non-empty string.")
    if "rules" in qc:
        _validate_rule_list(qc["rules"], "qc.rules")
    if "categories" in errors and not isinstance(errors["categories"], list):
        raise InvalidConfigurationError("errors.categories must be a list.")
    if "types" in errors and not isinstance(errors["types"], list):
        raise InvalidConfigurationError("errors.types must be a list.")
    if "pattern" in filename and (not isinstance(filename["pattern"], str) or not filename["pattern"].strip()):
        raise InvalidConfigurationError("filename.pattern must be a non-empty string.")
    if "templates" in email:
        if not isinstance(email["templates"], dict) or any(not isinstance(key, str) or not isinstance(value, str) for key, value in email["templates"].items()):
            raise InvalidConfigurationError("email.templates must be a mapping of string names to string templates.")


def _validate_rule_list(value: object, label: str) -> None:
    if not isinstance(value, list):
        raise InvalidConfigurationError(f"{label} must be a list.")
    for rule in value:
        _require_mapping(rule, label)
        if "rule_type" in rule and (not isinstance(rule["rule_type"], str) or not rule["rule_type"].strip()):
            raise InvalidConfigurationError(f"{label} rule_type must be a non-empty string.")
