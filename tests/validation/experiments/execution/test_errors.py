from msa.validation.experiments import ExperimentValidationError
from msa.validation.experiments.execution.errors import (
    C008CBCaseError,
    C008CBComparisonError,
    C008CBEvidenceError,
    C008CBExecutionError,
    C008CBManifestError,
    C008CBReportError,
)


def test_execution_errors_share_bounded_domain_base() -> None:
    for error_type in (
        C008CBCaseError,
        C008CBComparisonError,
        C008CBEvidenceError,
        C008CBManifestError,
        C008CBReportError,
    ):
        assert issubclass(error_type, C008CBExecutionError)
        assert issubclass(error_type, ExperimentValidationError)
