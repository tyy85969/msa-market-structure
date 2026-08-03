import inspect

from msa.validation.experiments.execution.rca import determinism
from msa.validation.experiments.execution.rca.contracts import DeterminismDiagnosticKind


def test_same_context_and_decimal_are_independent_kinds():
    assert DeterminismDiagnosticKind.SAME_CONTEXT_REPEAT is not DeterminismDiagnosticKind.DECIMAL_CONTEXT_PERTURBATION
    source = inspect.getsource(determinism._run_item)
    assert "normal_a" in source and "normal_b" in source and "altered" in source
    assert source.count("_result(") == 2


def test_decimal_context_matches_frozen_b_perturbation():
    source = inspect.getsource(determinism._run_item)
    assert "prec = 7" in source
    assert "ROUND_FLOOR" in source
