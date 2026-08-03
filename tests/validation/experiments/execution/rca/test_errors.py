from msa.validation.experiments.execution.rca.errors import (
    C008CBRCADiagnosticError,
    C008CBRCAError,
    C008CBRCAEvidenceError,
    C008CBRCAManifestError,
    C008CBRCAReportError,
)


def test_all_rca_errors_share_one_domain_boundary():
    assert all(issubclass(x, C008CBRCAError) for x in (
        C008CBRCADiagnosticError,
        C008CBRCAEvidenceError,
        C008CBRCAManifestError,
        C008CBRCAReportError,
    ))
