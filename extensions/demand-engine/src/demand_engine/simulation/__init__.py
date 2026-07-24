from __future__ import annotations

import heapq
from dataclasses import dataclass
from math import ceil

import numpy as np


class RandomSource:
    def __init__(self, seed: int):
        self.generator = np.random.default_rng(seed)

    def poisson(self, lam, size=None):
        return self.generator.poisson(lam, size=size)

    def binomial(self, n, p, size=None):
        return self.generator.binomial(n, p, size=size)

    def negative_binomial(self, n, p, size=None):
        return self.generator.negative_binomial(n, p, size=size)

    def random(self, size=None):
        return self.generator.random(size=size)

    def normal(self, mean, std, size=None):
        return self.generator.normal(mean, std, size=size)

    def uniform(self, low, high, size=None):
        return self.generator.uniform(low, high, size=size)

    def triangular(self, left, mode, right, size=None):
        return self.generator.triangular(left, mode, right, size=size)


@dataclass(frozen=True, slots=True)
class RepairRelease:
    returned_quantity: float = 0.0
    condemned_quantity: float = 0.0


class RepairPipeline:
    def __init__(self):
        self._events: list[tuple[float, int, float, bool]] = []
        self._counter = 0

    def schedule(self, completion_time: float, quantity: float, success: bool) -> None:
        self._counter += 1
        heapq.heappush(self._events, (float(completion_time), self._counter, float(quantity), bool(success)))

    def release_until(self, time: float) -> RepairRelease:
        returned = 0.0
        condemned = 0.0
        while self._events and self._events[0][0] <= time:
            _, _, quantity, success = heapq.heappop(self._events)
            if success:
                returned += quantity
            else:
                condemned += quantity
        return RepairRelease(returned, condemned)

    @property
    def quantity(self) -> float:
        return sum(event[2] for event in self._events)


def effective_minimum_runs(config) -> int:
    q_max = max(config.quantiles)
    tail_requirement = ceil(100 / (1 - q_max))
    return min(config.max_runs, max(config.min_runs, tail_requirement))


class ConvergenceTracker:
    def __init__(self, min_runs, max_runs, required_stable_batches, mean_relative_tolerance, quantile_absolute_tolerance):
        self.min_runs = min_runs
        self.max_runs = max_runs
        self.required_stable_batches = required_stable_batches
        self.mean_relative_tolerance = mean_relative_tolerance
        self.quantile_absolute_tolerance = quantile_absolute_tolerance
        self.completed_runs = 0
        self.stable_batches = 0
        self._previous_mean = None
        self._previous_quantile = None
        self._samples = []

    def update(self, sample, target_quantile=0.95):
        array = np.asarray(sample, dtype=float)
        self._samples.append(array)
        self.completed_runs += len(array)
        combined = np.concatenate(self._samples, axis=0)
        mean = np.mean(combined, axis=0)
        quantile = np.quantile(combined, target_quantile, axis=0)
        if self._previous_mean is not None:
            denominator = np.maximum(np.abs(self._previous_mean), 1.0)
            mean_change = np.max(np.abs(mean - self._previous_mean) / denominator)
            quantile_change = np.max(np.abs(quantile - self._previous_quantile))
            sampling_floor = 1.0 / max(self.completed_runs, 1) ** 0.5
            effective_mean_tolerance = max(self.mean_relative_tolerance, sampling_floor)
            if mean_change <= effective_mean_tolerance and quantile_change <= self.quantile_absolute_tolerance:
                self.stable_batches += 1
            else:
                self.stable_batches = 0
        self._previous_mean = mean
        self._previous_quantile = quantile
        return self.completed_runs >= self.min_runs and self.stable_batches >= self.required_stable_batches
