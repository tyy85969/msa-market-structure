from decimal import Decimal

import pytest

from msa.domain import PriceRange
from msa.research.pool import LevelPoolInputError, range_gap


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [
        (("100", "102"), ("101", "103"), "0"),
        (("100", "101"), ("101", "102"), "0"),
        (("100", "100"), ("102.25", "102.25"), "2.25"),
        (("100", "101"), ("102.5", "104"), "1.5"),
        (("100", "100"), ("99.25", "99.75"), "0.25"),
        (("0.1234567890123456789", "0.1234567890123456789"),
         ("0.1234567890123456790", "0.1234567890123456790"),
         "0.0000000000000000001"),
    ],
)
def test_range_gap_exact_decimal_cases(left, right, expected: str) -> None:
    first = PriceRange(Decimal(left[0]), Decimal(left[1]))
    second = PriceRange(Decimal(right[0]), Decimal(right[1]))
    assert range_gap(first, second) == Decimal(expected)
    assert range_gap(second, first) == Decimal(expected)


def test_range_gap_rejects_non_price_range() -> None:
    with pytest.raises(LevelPoolInputError, match="PriceRange"):
        range_gap(Decimal("1"), PriceRange(Decimal("1"), Decimal("1")))  # type: ignore[arg-type]
