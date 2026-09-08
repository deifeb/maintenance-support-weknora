class DemandEngineError(Exception):
    """Base demand engine error."""


class EngineValidationError(DemandEngineError):
    """Raised when a calculation input is invalid."""


class CalculationCancelledError(DemandEngineError):
    """Raised at a safe cancellation checkpoint."""
