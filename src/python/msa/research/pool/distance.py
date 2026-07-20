"""Exact Decimal PriceRange distance for C-005."""

from __future__ import annotations

from decimal import Decimal

from msa.domain import PriceRange

from .errors import LevelPoolInputError


def range_gap(left: PriceRange, right: PriceRange) -> Decimal:
    """Return the inclusive interval gap; overlap and endpoint touch equal zero."""

    if not isinstance(left, PriceRange) or not isinstance(right, PriceRange):
        raise LevelPoolInputError("range_gap operands must be PriceRange values")
    if left.high < right.low:
        return right.low - left.high
    if right.high < left.low:
        return left.low - right.high
    return Decimal(0)
