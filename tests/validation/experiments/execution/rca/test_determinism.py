from decimal import ROUND_FLOOR, getcontext
from types import SimpleNamespace

from msa.validation.experiments.execution.rca import determinism
from msa.validation.experiments.execution.rca.contracts import (
    DeterminismDiagnosticKind,
)


class _Payload:
    def __init__(self, value):
        self.value = value

    def to_dict(self):
        return self.value


def test_same_context_and_decimal_runs_are_behaviorally_independent(monkeypatch):
    contexts = []

    def execute(*_args):
        contexts.append((getcontext().prec, getcontext().rounding))
        return SimpleNamespace(
            run=None,
            audit=None,
            metric_report=None,
            result=_Payload({"case_result_id": "case-a", "status": "PASSED"}),
        )

    monkeypatch.setattr(determinism, "_execute_pair", execute)
    config = _Payload({"strict": True})
    variant = SimpleNamespace(
        core_config_snapshot=config,
        metric_config_snapshot=config,
    )
    same, decimal = determinism._run_item(
        (object(), object(), variant, "pair-a")
    )
    assert [same.diagnostic_kind, decimal.diagnostic_kind] == [
        DeterminismDiagnosticKind.SAME_CONTEXT_REPEAT,
        DeterminismDiagnosticKind.DECIMAL_CONTEXT_PERTURBATION,
    ]
    assert len(contexts) == 3
    assert contexts[0] == contexts[1]
    assert contexts[2] == (7, ROUND_FLOOR)
