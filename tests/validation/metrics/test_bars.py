from decimal import Decimal, getcontext

from msa.validation.metrics import causal_wilder_atr, true_ranges
from tests.research.timeframe_state.fixtures import bar


def explicit_bars():
    return (
        bar(0, high="11", low="9", close="10"),
        bar(1, high="14", low="10", close="13"),
        bar(2, high="13", low="8", close="9"),
    )


def test_true_range_and_wilder_atr_are_exact() -> None:
    bars = explicit_bars()
    assert true_ranges(bars) == (
        Decimal("2"),
        Decimal("4"),
        Decimal("5"),
    )
    assert causal_wilder_atr(bars, 2) == (
        None,
        Decimal("3"),
        Decimal("4"),
    )


def test_atr_does_not_depend_on_global_decimal_context() -> None:
    bars = explicit_bars()
    baseline = causal_wilder_atr(bars, 2)
    old_precision = getcontext().prec
    old_rounding = getcontext().rounding
    try:
        getcontext().prec = 3
        getcontext().rounding = "ROUND_DOWN"
        assert causal_wilder_atr(bars, 2) == baseline
    finally:
        getcontext().prec = old_precision
        getcontext().rounding = old_rounding
