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
