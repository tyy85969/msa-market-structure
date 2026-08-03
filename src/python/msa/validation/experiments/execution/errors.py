"""Fail-closed errors for frozen C-008C-B execution."""

from __future__ import annotations

from ..errors import ExperimentValidationError


class C008CBExecutionError(ExperimentValidationError):
    """Base error for C-008C-B execution and evidence validation."""


class C008CBManifestError(C008CBExecutionError):
    """Raised when the outcome-free execution manifest is invalid."""


class C008CBCaseError(C008CBExecutionError):
    """Raised when an execution case result is invalid."""


class C008CBComparisonError(C008CBExecutionError):
    """Raised when a delta, replay, cutoff, or repeat result is invalid."""


class C008CBDegenerationError(C008CBExecutionError):
    """Raised when degeneration evidence is invalid."""


class C008CBGateError(C008CBExecutionError):
    """Raised when a B-stage gate result is invalid."""


class C008CBReportError(C008CBExecutionError):
    """Raised when the compact B-stage report is invalid."""


class C008CBEvidenceError(C008CBExecutionError):
    """Raised when generated B evidence is missing or byte-different."""


class C008CBPreflightError(C008CBExecutionError):
    """Raised before any outcome when frozen authority does not validate."""


class C008CBCausalAuditFailure(C008CBExecutionError):
    """Names a formal non-passing CausalAuditReport without raising it."""
