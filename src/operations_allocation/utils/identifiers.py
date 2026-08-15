"""Primary identifier normalization shared by validation, sampling, allocation,
consolidation, QC, and error matching.

Per PROJECT_SPEC.md section 7 / ARCHITECTURE.md section 7.2: identifiers are
treated as strings internally, whitespace is trimmed, leading zeros and
scientific notation must never be silently altered, and matching is
case-sensitive unless a program explicitly configures otherwise.

This module only normalizes values it is given as strings. Preserving leading
zeros and avoiding scientific-notation coercion is the responsibility of the
File Processing engine that reads the original cell value -- by the time a
value reaches here it must already be a string.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from operations_allocation.domain.exceptions import IdentifierNormalizationError


@dataclass(frozen=True, slots=True)
class NormalizationPolicy:
    trim_whitespace: bool = True
    case_sensitive: bool = True

    @classmethod
    def from_configuration(cls, primary_identifier: Mapping[str, Any]) -> "NormalizationPolicy":
        normalization = primary_identifier.get("normalization", {})
        return cls(
            trim_whitespace=bool(normalization.get("trim_whitespace", True)),
            case_sensitive=bool(primary_identifier.get("case_sensitive", True)),
        )


def normalize_identifier(value: Any, policy: NormalizationPolicy) -> str:
    """Normalize a primary identifier value for matching.

    Returns the normalized value. Never returns the original value unchanged
    when a policy option requires modification, and never silently drops
    information the policy did not ask to remove.
    """
    if not isinstance(value, str):
        raise IdentifierNormalizationError(
            "Primary identifier values must be provided as strings before normalization."
        )
    normalized = value.strip() if policy.trim_whitespace else value
    if not normalized:
        raise IdentifierNormalizationError("Primary identifier value is blank after normalization.")
    return normalized if policy.case_sensitive else normalized.casefold()
