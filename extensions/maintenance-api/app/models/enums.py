from enum import StrEnum


class ConfigurationStatus(StrEnum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    RETIRED = "RETIRED"


class CriticalityLevel(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ReliabilityModelType(StrEnum):
    EXPONENTIAL = "EXPONENTIAL"
    WEIBULL = "WEIBULL"
    BINOMIAL = "BINOMIAL"
    NEGATIVE_BINOMIAL = "NEGATIVE_BINOMIAL"
    EMPIRICAL = "EMPIRICAL"


class DataSourceType(StrEnum):
    DESIGN_PARAMETER = "DESIGN_PARAMETER"
    MAINTENANCE_RECORD = "MAINTENANCE_RECORD"
    TEST_DATA = "TEST_DATA"
    MANUAL_ESTIMATE = "MANUAL_ESTIMATE"
    LITERATURE = "LITERATURE"
    EXPERT_JUDGMENT = "EXPERT_JUDGMENT"


class WarehouseStatus(StrEnum):
    NORMAL = "NORMAL"
    FROZEN = "FROZEN"
    COUNTING = "COUNTING"


class ImportOperation(StrEnum):
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    UPSERT = "UPSERT"


class ScenarioVersionStatus(StrEnum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    RETIRED = "RETIRED"


class MissingParameterPolicy(StrEnum):
    STRICT = "STRICT"
    WARN_AND_SKIP = "WARN_AND_SKIP"
    FALLBACK = "FALLBACK"


class DemandExecutionMode(StrEnum):
    AUTO = "AUTO"
    ANALYTICAL = "ANALYTICAL"
    MONTE_CARLO = "MONTE_CARLO"
    COMPARE = "COMPARE"


class CalculationExecutionType(StrEnum):
    SYNCHRONOUS = "SYNCHRONOUS"
    ASYNCHRONOUS = "ASYNCHRONOUS"


class CalculationStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    INTERRUPTED = "INTERRUPTED"


class RerunMode(StrEnum):
    NEW = "NEW"
    REPLAY_SNAPSHOT = "REPLAY_SNAPSHOT"
    RERUN_LATEST = "RERUN_LATEST"


class AgeDistributionType(StrEnum):
    FIXED = "FIXED"
    UNIFORM = "UNIFORM"
    NORMAL = "NORMAL"
    TRIANGULAR = "TRIANGULAR"


class FailureProcessMode(StrEnum):
    AUTO = "AUTO"
    SINGLE_FAILURE = "SINGLE_FAILURE"
    RENEWAL = "RENEWAL"
    COUNT_DISTRIBUTION = "COUNT_DISTRIBUTION"


class ShockApplicationMode(StrEnum):
    FAILURE_RATE = "FAILURE_RATE"
    FAILURE_PROBABILITY = "FAILURE_PROBABILITY"
    EQUIVALENT_AGE = "EQUIVALENT_AGE"


class ItemCalculationStatus(StrEnum):
    CALCULATED = "CALCULATED"
    SKIPPED = "SKIPPED"
    FALLBACK = "FALLBACK"


class ShortageRiskLevel(StrEnum):
    NONE = "NONE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ComparisonConsistencyLevel(StrEnum):
    CONSISTENT = "CONSISTENT"
    MINOR_DEVIATION = "MINOR_DEVIATION"
    MAJOR_DEVIATION = "MAJOR_DEVIATION"
