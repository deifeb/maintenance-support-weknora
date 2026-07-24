import math

from demand_engine.weibull import weibull_conditional_failure_probability, weibull_renewal_mean


def test_weibull_conditional_probability_matches_formula():
    value = weibull_conditional_failure_probability(500, 100, 2, 1000, 1)
    expected = 1 - math.exp(-((600 / 1000) ** 2) + ((500 / 1000) ** 2))
    assert math.isclose(value, expected, rel_tol=1e-12)


def test_shape_one_matches_exponential_probability():
    value = weibull_conditional_failure_probability(500, 100, 1, 1000, 1)
    assert math.isclose(value, 1 - math.exp(-0.1), rel_tol=1e-12)


def test_weibull_renewal_shape_one_matches_poisson_mean():
    mean = weibull_renewal_mean(duration_hours=1000, shape=1, scale=1000, step_hours=2)
    assert math.isclose(mean, 1.0, rel_tol=0.03)
