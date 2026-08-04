"""Failure-closed errors for C-008C-B root-cause evidence."""


class C008CBRCAError(ValueError):
    """Base RCA contract or execution failure."""


class C008CBRCAManifestError(C008CBRCAError):
    """The outcome-independent RCA schedule is invalid."""


class C008CBRCADiagnosticError(C008CBRCAError):
    """A bounded RCA diagnostic could not be completed safely."""


class C008CBRCAEvidenceError(C008CBRCAError):
    """Committed RCA evidence is invalid or not canonical."""


class C008CBRCAReportError(C008CBRCAError):
    """The RCA report is inconsistent with its frozen sources."""


__all__ = [
    "C008CBRCAError",
    "C008CBRCADiagnosticError",
    "C008CBRCAEvidenceError",
    "C008CBRCAManifestError",
    "C008CBRCAReportError",
]
