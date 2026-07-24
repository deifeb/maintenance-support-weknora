from enum import StrEnum


class ExecutionMode(StrEnum):
    AUTO = "AUTO"
    ANALYTICAL = "ANALYTICAL"
    MONTE_CARLO = "MONTE_CARLO"
    COMPARE = "COMPARE"


class FailureProcessMode(StrEnum):
    AUTO = "AUTO"
    SINGLE_FAILURE = "SINGLE_FAILURE"
    RENEWAL = "RENEWAL"
    COUNT_DISTRIBUTION = "COUNT_DISTRIBUTION"


class ReliabilityModelType(StrEnum):
    EXPONENTIAL = "EXPONENTIAL"
    WEIBULL = "WEIBULL"
    BINOMIAL = "BINOMIAL"
    NEGATIVE_BINOMIAL = "NEGATIVE_BINOMIAL"
    EMPIRICAL = "EMPIRICAL"


class MissingParameterPolicy(StrEnum):
    STRICT = "STRICT"
    WARN_AND_SKIP = "WARN_AND_SKIP"
    FALLBACK = "FALLBACK"


class AgeDistributionType(StrEnum):
    FIXED = "FIXED"
    UNIFORM = "UNIFORM"
    NORMAL = "NORMAL"
    TRIANGULAR = "TRIANGULAR"


class ShockApplicationMode(StrEnum):
    FAILURE_RATE = "FAILURE_RATE"
    FAILURE_PROBABILITY = "FAILURE_PROBABILITY"
    EQUIVALENT_AGE = "EQUIVALENT_AGE"
