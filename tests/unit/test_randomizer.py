from __future__ import annotations

import unittest
from decimal import Decimal

from operations_allocation.core.randomizer import calculate_sample_size, draw_sample, generate_random_seed, half_up_round
from operations_allocation.domain.exceptions import SamplingConfigurationError


class GenerateRandomSeedTestCase(unittest.TestCase):
    def test_returns_a_non_empty_string(self) -> None:
        self.assertTrue(generate_random_seed())

    def test_successive_calls_are_effectively_unique(self) -> None:
        self.assertNotEqual(generate_random_seed(), generate_random_seed())


class HalfUpRoundTestCase(unittest.TestCase):
    def test_spec_worked_examples(self) -> None:
        self.assertEqual(half_up_round(Decimal("1692.96")), 1693)
        self.assertEqual(half_up_round(Decimal("1692.5")), 1693)
        self.assertEqual(half_up_round(Decimal("1692.4")), 1692)

    def test_differs_from_bankers_rounding_at_half(self) -> None:
        # Python's built-in round() would produce 1692 (round-half-to-even);
        # the spec requires HALF-UP, i.e. 1693.
        self.assertNotEqual(round(1692.5), half_up_round(Decimal("1692.5")))


class CalculateSampleSizeTestCase(unittest.TestCase):
    def test_percentage_matches_spec_example(self) -> None:
        size = calculate_sample_size(method="percentage", value="3", eligible_count=56432)
        self.assertEqual(size.calculated_before_rounding, Decimal("1692.96"))
        self.assertEqual(size.actual, 1693)

    def test_percentage_accepts_numeric_types(self) -> None:
        self.assertEqual(calculate_sample_size(method="percentage", value=3, eligible_count=100).actual, 3)
        self.assertEqual(calculate_sample_size(method="percentage", value=3.0, eligible_count=100).actual, 3)

    def test_percentage_rejects_out_of_range(self) -> None:
        with self.assertRaises(SamplingConfigurationError):
            calculate_sample_size(method="percentage", value="0", eligible_count=100)
        with self.assertRaises(SamplingConfigurationError):
            calculate_sample_size(method="percentage", value="101", eligible_count=100)

    def test_percentage_never_exceeds_eligible_count(self) -> None:
        size = calculate_sample_size(method="percentage", value="100", eligible_count=10)
        self.assertEqual(size.actual, 10)

    def test_count_method_requires_positive_integer(self) -> None:
        with self.assertRaises(SamplingConfigurationError):
            calculate_sample_size(method="count", value="0", eligible_count=10)
        with self.assertRaises(SamplingConfigurationError):
            calculate_sample_size(method="count", value="3.5", eligible_count=10)
        with self.assertRaises(SamplingConfigurationError):
            calculate_sample_size(method="count", value=True, eligible_count=10)

    def test_count_method_rejects_more_than_eligible(self) -> None:
        with self.assertRaises(SamplingConfigurationError):
            calculate_sample_size(method="count", value=11, eligible_count=10)

    def test_count_method_accepts_string_digits(self) -> None:
        self.assertEqual(calculate_sample_size(method="count", value="7", eligible_count=10).actual, 7)

    def test_unsupported_method_rejected(self) -> None:
        with self.assertRaises(SamplingConfigurationError):
            calculate_sample_size(method="stratified", value=1, eligible_count=10)


class DrawSampleTestCase(unittest.TestCase):
    POPULATION = tuple(f"P{i:03d}" for i in range(1, 101))

    def test_same_seed_produces_same_sample(self) -> None:
        first = draw_sample(self.POPULATION, method="count", value=10, seed="seed-1")
        second = draw_sample(self.POPULATION, method="count", value=10, seed="seed-1")
        self.assertEqual(first.selected_identifiers, second.selected_identifiers)

    def test_different_seed_can_produce_different_sample(self) -> None:
        first = draw_sample(self.POPULATION, method="count", value=10, seed="seed-1")
        second = draw_sample(self.POPULATION, method="count", value=10, seed="seed-2")
        self.assertNotEqual(first.selected_identifiers, second.selected_identifiers)

    def test_selection_is_unique_and_subset_of_population(self) -> None:
        outcome = draw_sample(self.POPULATION, method="percentage", value="25", seed="seed-3")
        self.assertEqual(len(outcome.selected_identifiers), len(set(outcome.selected_identifiers)))
        self.assertTrue(set(outcome.selected_identifiers).issubset(set(self.POPULATION)))
        self.assertEqual(len(outcome.selected_identifiers), 25)

    def test_selection_order_is_input_independent(self) -> None:
        shuffled = tuple(reversed(self.POPULATION))
        outcome_a = draw_sample(self.POPULATION, method="count", value=5, seed="seed-4")
        outcome_b = draw_sample(shuffled, method="count", value=5, seed="seed-4")
        self.assertEqual(outcome_a.selected_identifiers, outcome_b.selected_identifiers)

    def test_missing_seed_rejected(self) -> None:
        with self.assertRaises(SamplingConfigurationError):
            draw_sample(self.POPULATION, method="count", value=5, seed="")
