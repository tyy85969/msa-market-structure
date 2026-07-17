from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from msa.data.contracts import Timeframe
from msa.domain import (
    ActiveBox,
    ActiveBoxStatus,
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
)


UTC = timezone.utc
ORIGIN = datetime(2026, 4, 1, 8, 0, tzinfo=UTC)
CONFIRM = datetime(2026, 4, 1, 12, 0, tzinfo=UTC)


def provenance(object_id: str) -> ProvenanceRef:
    return ProvenanceRef("tests.box", "1", object_id, None, (), ())


def boundary(side: BoundarySide, **overrides: object) -> BoundaryRef:
    default_range = (
        PriceRange(Decimal("2400"), Decimal("2401"))
        if side is BoundarySide.UPPER
        else PriceRange(Decimal("2300"), Decimal("2301"))
    )
    values: dict[str, object] = {
        "object_kind": StructureObjectKind.STRUCTURE_CLUSTER,
        "object_id": f"{side.value.lower()}-cluster",
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
        "structure_families": ("cluster",),
        "provenance": provenance(f"{side.value.lower()}-source"),
    }
    values.update(overrides)
    return BoundaryRef(**values)  # type: ignore[arg-type]


def active_box(**overrides: object) -> ActiveBox:
    values: dict[str, object] = {
        "box_id": "box-1",
        "symbol": "XAUUSD",
        "timeframe": Timeframe.H1,
        "scale": ScaleDescriptor("configured-primary", 1),
        "lower_boundary": boundary(BoundarySide.LOWER),
        "upper_boundary": boundary(BoundarySide.UPPER),
        "selection_price": Decimal("2350"),
        "status": ActiveBoxStatus.ACTIVE,
        "origin_time": ORIGIN,
        "confirm_time": CONFIRM,
        "as_of_time": CONFIRM + timedelta(minutes=1),
        "frozen_time": None,
        "retired_time": None,
        "provenance": provenance("box-source"),
    }
    values.update(overrides)
    return ActiveBox(**values)  # type: ignore[arg-type]


def test_active_box_accepts_valid_boundaries_and_inner_edge_prices() -> None:
    assert active_box(selection_price=Decimal("2301")).selection_price == Decimal(
        "2301"
    )
    assert active_box(selection_price=Decimal("2400")).selection_price == Decimal(
        "2400"
    )


def test_active_box_rejects_reversed_boundary_sides() -> None:
    with pytest.raises(DomainValidationError, match="lower_boundary"):
        active_box(
            lower_boundary=boundary(BoundarySide.UPPER),
            upper_boundary=boundary(BoundarySide.LOWER),
        )


@pytest.mark.parametrize("price", [Decimal("2300.99"), Decimal("2400.01")])
def test_active_box_rejects_selection_price_outside_inner_edges(
    price: Decimal,
) -> None:
    with pytest.raises(DomainValidationError, match="selection_price"):
        active_box(selection_price=price)


def test_active_box_rejects_float_selection_price() -> None:
    with pytest.raises(DomainValidationError, match="must be a Decimal"):
        active_box(selection_price=2350.0)


def test_active_box_rejects_future_boundary() -> None:
    with pytest.raises(DomainValidationError, match="confirmed no later"):
        active_box(
            upper_boundary=boundary(
                BoundarySide.UPPER,
                confirm_time=CONFIRM + timedelta(seconds=1),
            )
        )


def test_active_box_rejects_mixed_symbol() -> None:
    with pytest.raises(DomainValidationError, match="symbols"):
        active_box(lower_boundary=boundary(BoundarySide.LOWER, symbol="EURUSD"))


def test_active_box_rejects_crossed_boundaries() -> None:
    lower = boundary(
        BoundarySide.LOWER,
        price_range=PriceRange(Decimal("2401"), Decimal("2402")),
    )
    with pytest.raises(DomainValidationError, match="lower boundary"):
        active_box(lower_boundary=lower)


def test_retired_box_requires_retired_time() -> None:
    with pytest.raises(DomainValidationError, match="retired_time is required"):
        active_box(status=ActiveBoxStatus.RETIRED)


def test_non_retired_box_rejects_retired_time() -> None:
    with pytest.raises(DomainValidationError, match="unless status is RETIRED"):
        active_box(retired_time=CONFIRM + timedelta(hours=1))


def test_retired_box_accepts_explicit_retired_time() -> None:
    result = active_box(
        status=ActiveBoxStatus.RETIRED,
        retired_time=CONFIRM,
    )
    assert result.retired_time == CONFIRM


def test_frozen_box_requires_frozen_time() -> None:
    with pytest.raises(DomainValidationError, match="frozen_time is required"):
        active_box(status=ActiveBoxStatus.FROZEN)


def test_active_box_rejects_frozen_time_after_confirm() -> None:
    with pytest.raises(DomainValidationError, match="frozen_time"):
        active_box(frozen_time=CONFIRM + timedelta(microseconds=1))


def test_frozen_time_may_equal_confirm_time() -> None:
    result = active_box(
        status=ActiveBoxStatus.FROZEN,
        frozen_time=CONFIRM,
    )
    assert result.frozen_time == CONFIRM


def test_active_box_rejects_retired_time_after_confirm() -> None:
    with pytest.raises(DomainValidationError, match="retired_time"):
        active_box(
            status=ActiveBoxStatus.RETIRED,
            retired_time=CONFIRM + timedelta(microseconds=1),
        )


def test_retired_time_may_equal_confirm_time() -> None:
    result = active_box(
        status=ActiveBoxStatus.RETIRED,
        retired_time=CONFIRM,
    )
    assert result.retired_time == CONFIRM


def test_active_box_rejects_frozen_time_after_retired_time() -> None:
    with pytest.raises(DomainValidationError, match="frozen_time"):
        active_box(
            status=ActiveBoxStatus.RETIRED,
            frozen_time=CONFIRM,
            retired_time=CONFIRM - timedelta(microseconds=1),
        )


def test_active_box_rejects_as_of_before_confirm() -> None:
    with pytest.raises(DomainValidationError, match="as_of_time"):
        active_box(as_of_time=CONFIRM - timedelta(seconds=1))


def test_active_box_availability_starts_at_confirm_time() -> None:
    result = active_box(
        status=ActiveBoxStatus.RETIRED,
        frozen_time=CONFIRM - timedelta(minutes=1),
        retired_time=CONFIRM,
    )
    assert not result.is_available_at(CONFIRM - timedelta(microseconds=1))
    with pytest.raises(DomainAvailabilityError):
        result.require_available_at(CONFIRM - timedelta(microseconds=1))
    assert result.is_available_at(CONFIRM)
    assert result.require_available_at(CONFIRM) is result
    assert result.frozen_time <= result.retired_time <= result.confirm_time
