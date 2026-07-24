import numpy as np

from demand_engine.models import SimulationConfig
from demand_engine.simulation import (
    ConvergenceTracker,
    RandomSource,
    RepairPipeline,
    effective_minimum_runs,
)


def test_random_source_is_reproducible():
    left = RandomSource(20260723).poisson(2.5, size=20)
    right = RandomSource(20260723).poisson(2.5, size=20)
    assert left.tolist() == right.tolist()


def test_p99_requires_at_least_ten_thousand_runs():
    config = SimulationConfig(quantiles=(0.5, 0.8, 0.9, 0.95, 0.99))
    assert effective_minimum_runs(config) == 10000


def test_repair_pipeline_releases_in_time_order():
    pipeline = RepairPipeline()
    pipeline.schedule(20, 1, True)
    pipeline.schedule(10, 2, True)
    assert pipeline.release_until(10).returned_quantity == 2
    assert pipeline.release_until(20).returned_quantity == 1


def test_convergence_tracker_stops_after_stable_batches():
    tracker = ConvergenceTracker(
        min_runs=400,
        max_runs=2000,
        required_stable_batches=2,
        mean_relative_tolerance=0.01,
        quantile_absolute_tolerance=1,
    )
    rng = np.random.default_rng(1)
    stop = False
    for _ in range(4):
        sample = rng.poisson(4, size=(200, 2))
        stop = tracker.update(sample, target_quantile=0.95)
    assert stop is True
