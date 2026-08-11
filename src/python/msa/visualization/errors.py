"""Errors for the bounded, non-trading MSA visual preview."""


class MSAVisualizationError(ValueError):
    """Base error for preview contracts, projection, and rendering."""


class VisualContractError(MSAVisualizationError):
    """Raised when a visual-scene payload is invalid or non-causal."""


class VisualSceneBuildError(MSAVisualizationError):
    """Raised when public Core output cannot be safely projected."""


class VisualRenderError(MSAVisualizationError):
    """Raised when a scene cannot be rendered deterministically."""


class VisualPreviewScopeError(MSAVisualizationError):
    """Raised when a request escapes VALIDATION seed 2 preview scope."""
