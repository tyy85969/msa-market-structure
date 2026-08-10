"""Canonical Decimal arithmetic authority for Resonance calculations."""

from __future__ import annotations

from contextlib import contextmanager
from decimal import (
    Clamped,
    Context,
    DecimalException,
    DivisionByZero,
    FloatOperation,
    Inexact,
    InvalidOperation,
    Overflow,
    ROUND_HALF_EVEN,
    Rounded,
    Subnormal,
    Underflow,
    localcontext,
)
from functools import wraps
from typing import Callable, Iterator, ParamSpec, TypeVar


CANONICAL_DECIMAL_PRECISION = 28
CANONICAL_DECIMAL_ROUNDING = ROUND_HALF_EVEN
CANONICAL_DECIMAL_EMIN = -999_999
CANONICAL_DECIMAL_EMAX = 999_999
CANONICAL_DECIMAL_CAPITALS = 1
CANONICAL_DECIMAL_CLAMP = 0

_DECIMAL_SIGNALS: tuple[type[DecimalException], ...] = (
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
_CANONICAL_TRAPS = frozenset({InvalidOperation, DivisionByZero, Overflow})

_P = ParamSpec("_P")
_R = TypeVar("_R")


def canonical_decimal_context() -> Context:
    """Return a fresh, fully specified Context with clear mutable flags."""

    context = Context(
        prec=CANONICAL_DECIMAL_PRECISION,
        rounding=CANONICAL_DECIMAL_ROUNDING,
        Emin=CANONICAL_DECIMAL_EMIN,
        Emax=CANONICAL_DECIMAL_EMAX,
        capitals=CANONICAL_DECIMAL_CAPITALS,
        clamp=CANONICAL_DECIMAL_CLAMP,
        flags=[],
        traps=[],
    )
    for signal in _DECIMAL_SIGNALS:
        context.traps[signal] = signal in _CANONICAL_TRAPS
        context.flags[signal] = False
    return context


@contextmanager
def resonance_decimal_context() -> Iterator[Context]:
    """Run Resonance arithmetic without reading or mutating caller Context."""

    with localcontext(canonical_decimal_context()) as context:
        yield context


def canonical_decimal_boundary(
    function: Callable[_P, _R],
) -> Callable[_P, _R]:
    """Execute one complete formal arithmetic path in the canonical Context."""

    @wraps(function)
    def wrapped(*args: _P.args, **kwargs: _P.kwargs) -> _R:
        with resonance_decimal_context():
            return function(*args, **kwargs)

    return wrapped


__all__ = [
    "CANONICAL_DECIMAL_CAPITALS",
    "CANONICAL_DECIMAL_CLAMP",
    "CANONICAL_DECIMAL_EMAX",
    "CANONICAL_DECIMAL_EMIN",
    "CANONICAL_DECIMAL_PRECISION",
    "CANONICAL_DECIMAL_ROUNDING",
    "canonical_decimal_boundary",
    "canonical_decimal_context",
    "resonance_decimal_context",
]
