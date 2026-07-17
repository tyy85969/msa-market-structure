from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from msa.data.contracts import Timeframe
from msa.domain import (
    BoundaryRef,
    BoundarySide,
    DomainAvailabilityError,
    DomainValidationError,
    LifecycleState,
    MarketRole,
    PriceRange,
    ProvenanceRef,
    ScaleDescriptor,
    StructureObjectKind,
    StructureSourceType,
    TimeframeState,
)


UTC = timezone.utc
ORIGIN = datetime(2026, 3, 1, 8, 0, tzinfo=UTC)
CONFIRM = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)


def provenance(object_id: str) -> ProvenanceRef:
    return ProvenanceRef("tests.state", "1", object_id, None, (), ())


def boundary(side: BoundarySide, **overrides: object) -> BoundaryRef:
    default_range = (
        PriceRange(Decimal("2400"), Decimal("2401"))
        if side is BoundarySide.UPPER
        else PriceRange(Decimal("2300"), Decimal("2301"))
    )
    values: dict[str, object] = {
        "object_kind": StructureObjectKind.LEVEL_CANDIDATE,
        "object_id": f"{side.value.lower()}-1",
        "symbol": "XAUUSD",
        "timeframe": Timeframe.H1,
        "scale": ScaleDescriptor("configured-primary", 1),
        "price_range": default_range,
        "boundary_side": side,
        "market_role": (
            MarketRole.RESISTANCE
            if side is BoundarySide.UPPER
            else MarketRole.SUPPORT
        ),
        "lifecycle_state": LifecycleState.FRESH,
        "origin_time": ORIGIN,
        "confirm_time": CONFIRM - timedelta(hours=1),
        "source_types": (StructureSourceType.SWING,),
        "structure_families": ("confirmed-swing",),
        "provenance": provenance(f"{side.value.lower()}-source"),
    }
    values.update(overrides)
    return BoundaryRef(**values)  # type: ignore[arg-type]


def state(**overrides: object) -> TimeframeState:
    values: dict[str, object] = {
        "state_id": "state-1",
        "state_version": "v1",
        "symbol": "XAUUSD",
        "timeframe": Timeframe.H1,
        "scale": ScaleDescriptor("configured-primary", 1),
        "origin_time": ORIGIN,
        "confirm_time": CONFIRM,
        "as_of_time": CONFIRM + timedelta(minutes=1),
        "upper_boundary": boundary(BoundarySide.UPPER),
        "lower_boundary": boundary(BoundarySide.LOWER),
        "forming_candidate_ids": ("forming-b", "forming-a"),
        "provenance": provenance("state-source"),
    }
    values.update(overrides)
    return TimeframeState(**values)  # type: ignore[arg-type]


def test_state_accepts_both_boundaries_and_canonicalizes_forming_ids() -> None:
    result = state()
    assert result.forming_candidate_ids == ("forming-a", "forming-b")


def test_state_accepts_only_upper_boundary() -> None:
    result = state(lower_boundary=None)
    assert result.upper_boundary is not None
    assert result.lower_boundary is None


def test_state_accepts_only_lower_boundary() -> None:
    result = state(upper_boundary=None)
    assert result.lower_boundary is not None
    assert result.upper_boundary is None


def test_empty_state_is_explicitly_valid() -> None:
    result = state(upper_boundary=None, lower_boundary=None)
    assert result.upper_boundary is result.lower_boundary is None


def test_state_rejects_as_of_before_confirm() -> None:
    with pytest.raises(DomainValidationError, match="as_of_time"):
        state(as_of_time=CONFIRM - timedelta(seconds=1))


def test_state_rejects_confirm_before_origin() -> None:
    with pytest.raises(DomainValidationError, match="confirm_time"):
        state(confirm_time=ORIGIN - timedelta(seconds=1))


@pytest.mark.parametrize("field_name", ["origin_time", "confirm_time", "as_of_time"])
def test_state_rejects_naive_times(field_name: str) -> None:
    with pytest.raises(DomainValidationError, match="timezone-aware"):
        state(**{field_name: datetime(2026, 3, 1, 12, 0)})


def test_state_rejects_future_boundary() -> None:
    future_upper = boundary(
        BoundarySide.UPPER,
        confirm_time=CONFIRM + timedelta(seconds=1),
    )
    with pytest.raises(DomainValidationError, match="cannot be later"):
        state(upper_boundary=future_upper)


def test_state_rejects_wrong_upper_side() -> None:
    with pytest.raises(DomainValidationError, match="must be UPPER"):
        state(upper_boundary=boundary(BoundarySide.LOWER))


def test_state_rejects_wrong_lower_side() -> None:
    with pytest.raises(DomainValidationError, match="must be LOWER"):
        state(lower_boundary=boundary(BoundarySide.UPPER))


def test_state_rejects_mixed_symbol() -> None:
    with pytest.raises(DomainValidationError, match="symbol"):
        state(upper_boundary=boundary(BoundarySide.UPPER, symbol="EURUSD"))


def test_state_rejects_crossed_boundaries() -> None:
    lower = boundary(
        BoundarySide.LOWER,
        price_range=PriceRange(Decimal("2401"), Decimal("2402")),
    )
    upper = boundary(
        BoundarySide.UPPER,
        price_range=PriceRange(Decimal("2400"), Decimal("2400.5")),
    )
    with pytest.raises(DomainValidationError, match="lower boundary"):
        state(lower_boundary=lower, upper_boundary=upper)


def test_state_rejects_duplicate_forming_candidate_ids() -> None:
    with pytest.raises(DomainValidationError, match="unique"):
        state(forming_candidate_ids=("duplicate", "duplicate"))


def test_state_availability_starts_at_confirm_time() -> None:
    result = state()
    assert not result.is_available_at(CONFIRM - timedelta(microseconds=1))
    with pytest.raises(DomainAvailabilityError):
        result.require_available_at(CONFIRM - timedelta(microseconds=1))
    assert result.is_available_at(CONFIRM)
    assert result.require_available_at(CONFIRM) is result
