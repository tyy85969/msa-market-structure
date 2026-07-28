"""Error hierarchy for frozen C-008C experiment authority contracts."""


class ExperimentValidationError(ValueError):
    """Base error for C-008C authority validation."""


class ExperimentConfigurationError(ExperimentValidationError):
    """Raised when an experiment authority configuration is invalid."""


class ExperimentInputError(ExperimentValidationError):
    """Raised when an experiment authority input is invalid."""


class ExperimentDatasetError(ExperimentValidationError):
    """Raised when a dataset case or manifest is invalid."""


class ExperimentPlanError(ExperimentValidationError):
    """Raised when a predeclared experiment plan is invalid."""


class ExperimentGateError(ExperimentValidationError):
    """Raised when a gate definition is invalid."""


class ExperimentProtectedSourceError(ExperimentValidationError):
    """Raised when protected source evidence is invalid."""


class ExperimentEvidenceError(ExperimentValidationError):
    """Raised when generated evidence is missing or differs."""


class ExperimentSerializationError(ExperimentValidationError):
    """Raised when strict serialization fails."""
