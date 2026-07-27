from decimal import getcontext

from .fixtures import touch_run, metric_config
from msa.validation import evaluate_structural_metrics


def test_repeated_complete_payload_is_identical() -> None:
    run = touch_run()
    first = evaluate_structural_metrics(run, metric_config()).to_dict()
    second = evaluate_structural_metrics(run, metric_config()).to_dict()
    assert first == second


def test_global_decimal_context_does_not_change_complete_report() -> None:
    run = touch_run()
    baseline = evaluate_structural_metrics(run, metric_config()).to_dict()
    old_precision = getcontext().prec
    old_rounding = getcontext().rounding
    try:
        getcontext().prec = 4
        getcontext().rounding = "ROUND_DOWN"
        assert (
            evaluate_structural_metrics(run, metric_config()).to_dict()
            == baseline
        )
    finally:
        getcontext().prec = old_precision
        getcontext().rounding = old_rounding
