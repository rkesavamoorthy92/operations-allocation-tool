from __future__ import annotations

import unittest

from operations_allocation.domain.exceptions import IdentifierNormalizationError
from operations_allocation.utils.identifiers import NormalizationPolicy, normalize_identifier


class NormalizeIdentifierTestCase(unittest.TestCase):
    def test_trims_whitespace_by_default(self) -> None:
        self.assertEqual(normalize_identifier("  ABC123  ", NormalizationPolicy()), "ABC123")

    def test_preserves_leading_zeros(self) -> None:
        self.assertEqual(normalize_identifier("00042", NormalizationPolicy()), "00042")

    def test_does_not_trim_when_disabled(self) -> None:
        self.assertEqual(normalize_identifier(" ABC ", NormalizationPolicy(trim_whitespace=False)), " ABC ")

    def test_case_sensitive_by_default(self) -> None:
        self.assertEqual(normalize_identifier("AbC", NormalizationPolicy()), "AbC")

    def test_case_insensitive_when_configured(self) -> None:
        self.assertEqual(normalize_identifier("AbC", NormalizationPolicy(case_sensitive=False)), "abc")

    def test_rejects_non_string_values(self) -> None:
        with self.assertRaises(IdentifierNormalizationError):
            normalize_identifier(42, NormalizationPolicy())

    def test_rejects_blank_after_trim(self) -> None:
        with self.assertRaises(IdentifierNormalizationError):
            normalize_identifier("   ", NormalizationPolicy())

    def test_from_configuration_reads_normalization_block(self) -> None:
        policy = NormalizationPolicy.from_configuration({"case_sensitive": False, "normalization": {"trim_whitespace": False}})
        self.assertEqual(policy, NormalizationPolicy(trim_whitespace=False, case_sensitive=False))

    def test_from_configuration_defaults_to_strict(self) -> None:
        policy = NormalizationPolicy.from_configuration({"normalization": {}})
        self.assertEqual(policy, NormalizationPolicy(trim_whitespace=True, case_sensitive=True))
