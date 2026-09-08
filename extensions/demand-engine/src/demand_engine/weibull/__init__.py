from __future__ import annotations

from math import exp

import numpy as np

from demand_engine.exceptions import EngineValidationError


def weibull_conditional_failure_probability(initial_age_hours, duration_hours, shape, scale, adjustment_factor=1.0):
    age = float(initial_age_hours)
    duration = float(duration_hours) * float(adjustment_factor)
    shape = float(shape)
    scale = float(scale)
    if age < 0 or duration < 0 or shape <= 0 or scale <= 0:
        raise EngineValidationError("invalid Weibull inputs")
    exponent = -((age + duration) / scale) ** shape + (age / scale) ** shape
    return min(1.0, max(0.0, 1 - exp(exponent)))


def weibull_renewal_mean(duration_hours, shape, scale, step_hours=1.0):
    duration = float(duration_hours)
    shape = float(shape)
    scale = float(scale)
    step = float(step_hours)
    if duration <= 0:
        return 0.0
    if shape <= 0 or scale <= 0 or step <= 0:
        raise EngineValidationError("invalid Weibull renewal inputs")
    n = max(1, int(np.ceil(duration / step)))
    grid = np.linspace(0.0, duration, n + 1)
    cdf = 1 - np.exp(-((grid / scale) ** shape))
    increments = np.diff(cdf, prepend=0.0)
    renewal = np.zeros_like(grid)
    for i in range(1, len(grid)):
        renewal[i] = cdf[i] + np.dot(renewal[1:i][::-1], increments[1:i])
    return float(renewal[-1])
