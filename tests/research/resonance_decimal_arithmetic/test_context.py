from decimal import (
    Clamped,
    Context,
    DivisionByZero,
    FloatOperation,
    Inexact,
    InvalidOperation,
    Overflow,
    ROUND_FLOOR,
    ROUND_HALF_EVEN,
    Rounded,
    Subnormal,
    Underflow,
    localcontext,
)

from msa.research.resonance.decimal_arithmetic import (
    CANONICAL_DECIMAL_CAPITALS,
    CANONICAL_DECIMAL_CLAMP,
    CANONICAL_DECIMAL_EMAX,
    CANONICAL_DECIMAL_EMIN,
    CANONICAL_DECIMAL_PRECISION,
    CANONICAL_DECIMAL_ROUNDING,
    canonical_decimal_context,
    resonance_decimal_context,
)


SIGNALS = (
    Clamped,
    InvalidOperation,
    DivisionByZero,
    Inexact,
    Rounded,
    Subnormal,
    Overflow,
    Underflow,
    FloatOperation,
)


def snapshot(context: Context) -> tuple[object, ...]:
    return (
        context.prec,
        context.rounding,
        context.Emin,
        context.Emax,
        context.capitals,
        context.clamp,
        tuple((signal, context.traps[signal]) for signal in SIGNALS),
        tuple((signal, context.flags[signal]) for signal in SIGNALS),
    )


def test_canonical_context_is_complete_and_fresh() -> None:
    left = canonical_decimal_context()
    right = canonical_decimal_context()
    assert left is not right
    assert (
        left.prec,
        left.rounding,
        left.Emin,
        left.Emax,
        left.capitals,
        left.clamp,
    ) == (
        CANONICAL_DECIMAL_PRECISION,
        CANONICAL_DECIMAL_ROUNDING,
        CANONICAL_DECIMAL_EMIN,
        CANONICAL_DECIMAL_EMAX,
        CANONICAL_DECIMAL_CAPITALS,
        CANONICAL_DECIMAL_CLAMP,
    ) == (28, ROUND_HALF_EVEN, -999999, 999999, 1, 0)
    assert {signal for signal in SIGNALS if left.traps[signal]} == {
        InvalidOperation,
        DivisionByZero,
        Overflow,
    }
    assert not any(left.flags[signal] for signal in SIGNALS)
    left.flags[Inexact] = True
    assert right.flags[Inexact] is False


def test_boundary_restores_every_caller_context_field() -> None:
    altered = Context(
        prec=7,
        rounding=ROUND_FLOOR,
        Emin=-95,
        Emax=96,
        capitals=0,
        clamp=1,
        flags=[Rounded],
        traps=[InvalidOperation, DivisionByZero, Overflow, FloatOperation],
    )
    with localcontext(altered) as caller:
        before = snapshot(caller)
        with resonance_decimal_context() as active:
            assert active.prec == 28
            assert active.rounding == ROUND_HALF_EVEN
            _ = active.divide(1, 7)
        assert snapshot(caller) == before
