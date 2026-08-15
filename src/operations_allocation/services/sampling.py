"""Coordinates the Randomizer against a Run's frozen Eligible Population and
Run Configuration Snapshot (PROJECT_SPEC.md section 9-10).

The random seed is a frozen part of the snapshot (ARCHITECTURE.md section
4.5); an "automatic seed" choice must already have been resolved to a
concrete value by Run setup before the snapshot was frozen, so this service
requires a non-empty seed and never invents one silently.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from operations_allocation.core.randomizer import (
    RNG_ALGORITHM,
    RNG_ALGORITHM_VERSION,
    SAMPLING_ALGORITHM,
    SAMPLING_ALGORITHM_VERSION,
    draw_sample,
)
from operations_allocation.domain.exceptions import SamplingConfigurationError
from operations_allocation.domain.models import RunState, SamplingResult
from operations_allocation.domain.state_machine import ensure_transition


class SamplingService:
    def __init__(self, *, runs: Any, snapshots: Any, populations: Any, sampling_results: Any, audit: Any) -> None:
        self.runs, self.snapshots, self.populations = runs, snapshots, populations
        self.sampling_results, self.audit = sampling_results, audit

    def sample(self, *, run_id: str) -> SamplingResult:
        run = self.runs.get(run_id)
        ensure_transition(run.state, RunState.SAMPLED)

        snapshot = self.snapshots.get(run_id)
        configuration = snapshot.configuration
        sampling_config = configuration["sampling"]
        seed = configuration.get("random_seed")
        if not seed:
            raise SamplingConfigurationError("Run Configuration Snapshot does not contain a random seed.")
        method = sampling_config.get("method")
        value = sampling_config.get("value")
        if not method:
            raise SamplingConfigurationError("Run Configuration Snapshot sampling configuration is missing a method.")

        population = self.populations.get(run_id)
        outcome = draw_sample(population.member_identifiers, method=method, value=value, seed=seed)

        result = SamplingResult(
            run_id=run_id,
            sampling_method=method,
            requested_value=str(value),
            eligible_population_count=len(population.member_identifiers),
            calculated_sample_count=(str(outcome.sample_size.calculated_before_rounding) if outcome.sample_size.calculated_before_rounding is not None else None),
            actual_sample_count=outcome.sample_size.actual,
            random_seed=str(seed),
            rng_algorithm=RNG_ALGORITHM,
            rng_algorithm_version=RNG_ALGORITHM_VERSION,
            sampling_algorithm=SAMPLING_ALGORITHM,
            sampling_algorithm_version=SAMPLING_ALGORITHM_VERSION,
            selected_identifiers=outcome.selected_identifiers,
            sampled_at=datetime.now(timezone.utc),
        )

        with self.runs.database.transaction() as connection:
            self.sampling_results.add(result, connection=connection)
            self.runs.update_state(run_id, RunState.SAMPLED, connection=connection)
            self.audit.record(
                run_id=run_id,
                program_id=run.program_id,
                action="RUN_SAMPLED",
                previous_state=run.state,
                new_state=RunState.SAMPLED,
                metadata={
                    "sampling_method": method,
                    "requested_value": str(value),
                    "eligible_population_count": result.eligible_population_count,
                    "calculated_sample_count": result.calculated_sample_count,
                    "actual_sample_count": result.actual_sample_count,
                    "rng_algorithm": RNG_ALGORITHM,
                    "sampling_algorithm": SAMPLING_ALGORITHM,
                },
                connection=connection,
            )
        return result
