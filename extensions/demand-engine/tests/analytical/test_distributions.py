import math

from demand_engine.analytical.distributions import (
    binomial_stats,
    exponential_renewal_stats,
    exponential_single_failure_stats,
    negative_binomial_stats,
)


def test_exponential_renewal_matches_poisson_mean_and_variance():
    stats = exponential_renewal_stats(100, 0.001, 100, 1.0, 1.0, (0.5, 0.95))
    assert math.isclose(stats.mean, 10.0, rel_tol=1e-12)
    assert math.isclose(stats.variance, 10.0, rel_tol=1e-12)


def test_exponential_single_failure_matches_formula():
    stats = exponential_single_failure_stats(100, 0.001, 100, 1.0, 1.0, (0.95,))
    p = 1 - math.exp(-0.1)
    assert math.isclose(stats.mean, 100 * p, rel_tol=1e-12)
    assert math.isclose(stats.variance, 100 * p * (1 - p), rel_tol=1e-12)


def test_binomial_boundaries():
    assert binomial_stats(10, 0, (0.95,)).quantiles[0.95] == 0
    assert binomial_stats(10, 1, (0.95,)).quantiles[0.95] == 10


def test_negative_binomial_mean_parameterization():
    stats = negative_binomial_stats(r=5, p=0.5, quantiles=(0.95,))
    assert math.isclose(stats.mean, 5.0, rel_tol=1e-12)
    assert math.isclose(stats.variance, 10.0, rel_tol=1e-12)
