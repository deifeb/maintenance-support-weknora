class MaintenanceAIError(Exception):
    code = "MAINTENANCE_AI_ERROR"


class ProviderError(MaintenanceAIError):
    code = "PROVIDER_ERROR"


class ProviderUnavailableError(ProviderError):
    code = "PROVIDER_UNAVAILABLE"


class ProviderTimeoutError(ProviderError):
    code = "PROVIDER_TIMEOUT"


class ProviderRateLimitError(ProviderError):
    code = "PROVIDER_RATE_LIMITED"


class StructuredOutputError(MaintenanceAIError):
    code = "MODEL_INVALID_STRUCTURED_OUTPUT"


class SensitiveRemoteCallBlockedError(MaintenanceAIError):
    code = "SENSITIVE_REMOTE_CALL_BLOCKED"


class PlanValidationError(MaintenanceAIError):
    code = "PLAN_VALIDATION_FAILED"


class EvidenceError(MaintenanceAIError):
    code = "EVIDENCE_ERROR"


class ReportValidationError(MaintenanceAIError):
    code = "REPORT_VALIDATION_FAILED"
