import random
from decimal import ROUND_DOWN, ROUND_UP, getcontext

from msa.validation.experiments import (
    build_c008c_synthetic_dataset,
    build_protected_source_manifest,
    core_experiment_baseline,
    default_c008c_experiment_plan,
)


def _payloads() -> tuple[dict[str, object], ...]:
    return (
        core_experiment_baseline().to_dict(),
        build_c008c_synthetic_dataset().to_dict(),
        default_c008c_experiment_plan().to_dict(),
        build_protected_source_manifest().to_dict(),
    )


def test_global_random_and_decimal_context_do_not_change_payloads() -> None:
    original_precision = getcontext().prec
    original_rounding = getcontext().rounding
    try:
        first = _payloads()
        random.seed(123456789)
        getcontext().prec = 6
        getcontext().rounding = ROUND_DOWN
        second = _payloads()
        random.seed(1)
        getcontext().prec = 50
        getcontext().rounding = ROUND_UP
        third = _payloads()
        assert first == second == third
    finally:
        getcontext().prec = original_precision
        getcontext().rounding = original_rounding
