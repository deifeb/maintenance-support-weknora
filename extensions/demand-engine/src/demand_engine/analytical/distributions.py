from __future__ import annotations

from dataclasses import dataclass
from math import exp, sqrt

from scipy.stats import binom, nbinom, poisson


@dataclass(frozen=True, slots=True)
class DistributionStats:
    mean: float
    variance: float
    standard_deviation: float
    quantiles: dict[float, float]
    approximation: str | None = None
    warnings: tuple[str, ...] = ()


def _stats(mean: float, variance: float, distribution, quantiles, approximation=None, warnings=()):
    values = {float(q): float(max(0.0, distribution.ppf(q))) for q in quantiles}
    return DistributionStats(float(mean), float(variance), sqrt(max(0.0, variance)), values, approximation, tuple(warnings))


def poisson_stats(mean: float, quantiles: tuple[float, ...]) -> DistributionStats:
    mean = max(0.0, float(mean))
    return _stats(mean, mean, poisson(mean), quantiles)


def binomial_stats(n: int, p: float, quantiles: tuple[float, ...]) -> DistributionStats:
    n = max(0, int(n))
    p = min(1.0, max(0.0, float(p)))
    mean = n * p
    variance = n * p * (1 - p)
    return _stats(mean, variance, binom(n, p), quantiles)


def negative_binomial_stats(r: float, p: float, quantiles: tuple[float, ...]) -> DistributionStats:
    r = float(r)
    p = float(p)
    mean = r * (1 - p) / p
    variance = r * (1 - p) / (p * p)
    return _stats(mean, variance, nbinom(r, p), quantiles)


def exponential_renewal_stats(installed_positions, failure_rate, duration_hours, adjustment_factor, replacement_ratio, quantiles):
    mean = max(0.0, float(installed_positions) * float(failure_rate) * float(duration_hours) * float(adjustment_factor) * float(replacement_ratio))
    return poisson_stats(mean, tuple(quantiles))


def exponential_single_failure_stats(installed_positions, failure_rate, duration_hours, adjustment_factor, replacement_ratio, quantiles):
    n_float = max(0.0, float(installed_positions))
    p = (1 - exp(-float(failure_rate) * float(duration_hours) * float(adjustment_factor))) * float(replacement_ratio)
    if n_float.is_integer():
        return binomial_stats(int(n_float), p, tuple(quantiles))
    result = poisson_stats(n_float * p, tuple(quantiles))
    return DistributionStats(result.mean, result.variance, result.standard_deviation, result.quantiles, "POISSON", ("NON_INTEGER_INSTALL_QUANTITY_APPROXIMATED",))


def empirical_stats(mean: float, variance: float, quantiles: tuple[float, ...]) -> DistributionStats:
    mean = max(0.0, float(mean))
    variance = max(0.0, float(variance))
    if abs(variance - mean) <= max(1e-12, 0.05 * max(1.0, mean)):
        result = poisson_stats(mean, quantiles)
        return DistributionStats(*result.__getstate__()[:4], approximation="POISSON", warnings=("EMPIRICAL_DISTRIBUTION_APPROXIMATED",))
    if variance > mean and mean > 0:
        p = mean / variance
        r = mean * p / (1 - p)
        result = negative_binomial_stats(r, p, quantiles)
        return DistributionStats(result.mean, result.variance, result.standard_deviation, result.quantiles, "NEGATIVE_BINOMIAL", ("EMPIRICAL_DISTRIBUTION_APPROXIMATED",))
    if mean <= 0:
        return poisson_stats(0, quantiles)
    p = max(1e-12, min(1.0, 1 - variance / mean))
    n = max(1, round(mean / p))
    result = binomial_stats(n, min(1.0, mean / n), quantiles)
    return DistributionStats(result.mean, result.variance, result.standard_deviation, result.quantiles, "BINOMIAL", ("EMPIRICAL_DISTRIBUTION_APPROXIMATED",))
