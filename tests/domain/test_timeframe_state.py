from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from msa.data.contracts import Timeframe
from msa.domain import (
    BoundaryRef,
    BoundarySide,
    Direction,
    DomainAvailabilityError,
    DomainSerializationError,
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
    return ProvenanceRef("tests.state", "2", object_id, None, (), ())


def boundary(
    side: BoundarySide,
    *,
    lifecycle_state: LifecycleState = LifecycleState.FRESH,
    suffix: str = "1",
    **overrides: object,
) -> BoundaryRef:
    default_range = (
        PriceRange(Decimal("2400"), Decimal("2401"))
        if side is BoundarySide.UPPER
        else PriceRange(Decimal("2300"), Decimal("2301"))
    )
    values: dict[str, object] = {
        "object_kind": StructureObjectKind.LEVEL_CANDIDATE,
        "object_id": f"{side.value.lower()}-{suffix}",
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
        "lifecycle_state": lifecycle_state,
        "origin_time": ORIGIN,
        "confirm_time": CONFIRM - timedelta(hours=1),
        "source_types": (StructureSourceType.SWING,),
        "structure_families": ("confirmed-swing",),
        "provenance": provenance(f"{side.value.lower()}-{suffix}-source"),
    }
    values.update(overrides)
    return BoundaryRef(**values)  # type: ignore[arg-type]


def state(**overrides: object) -> TimeframeState:
    values: dict[str, object] = {
        "state_id": "state-1",
        "state_version": "v2",
        "symbol": "XAUUSD",
        "timeframe": Timeframe.H1,
        "scale": ScaleDescriptor("configured-primary", 1),
        "direction": Direction.UNKNOWN,
        "origin_time": ORIGIN,
        "confirm_time": CONFIRM,
        "as_of_time": CONFIRM + timedelta(minutes=1),
        "candidate_upper_boundary": boundary(BoundarySide.UPPER),
        "candidate_lower_boundary": boundary(BoundarySide.LOWER),
        "confirmed_upper_boundary": boundary(
            BoundarySide.UPPER,
            lifecycle_state=LifecycleState.TESTED,
            suffix="confirmed",
        ),
        "confirmed_lower_boundary": boundary(
            BoundarySide.LOWER,
            lifecycle_state=LifecycleState.TESTED,
            suffix="confirmed",
        ),
        "forming_candidate_ids": ("forming-b", "forming-a"),
        "provenance": provenance("state-source"),
    }
    values.update(overrides)
    return TimeframeState(**values)  # type: ignore[arg-type]


def empty_state(**overrides: object) -> TimeframeState:
    values: dict[str, object] = {
        "candidate_upper_boundary": None,
        "candidate_lower_boundary": None,
        "confirmed_upper_boundary": None,
        "confirmed_lower_boundary": None,
        "forming_candidate_ids": (),
    }
    values.update(overrides)
    return state(**values)


def test_empty_state_with_unknown_direction_is_valid() -> None:
    result = empty_state()
    assert result.direction is Direction.UNKNOWN
    assert result.candidate_upper_boundary is None
    assert result.candidate_lower_boundary is None
    assert result.confirmed_upper_boundary is None
    assert result.confirmed_lower_boundary is None


@pytest.mark.parametrize("direction", tuple(Direction))
def test_state_stores_every_direction_without_inference(direction: Direction) -> None:
    assert empty_state(direction=direction).direction is direction


def test_state_is_frozen_and_slotted() -> None:
    result = empty_state()
    assert not hasattr(result, "__dict__")
    with pytest.raises(FrozenInstanceError):
        result.direction = Direction.UP  # type: ignore[misc]


def test_state_normalizes_aware_times_to_utc() -> None:
    offset = timezone(timedelta(hours=8))
    result = empty_state(
        origin_time=datetime(2026, 3, 1, 16, 0, tzinfo=offset),
        confirm_time=datetime(2026, 3, 1, 20, 0, tzinfo=offset),
        as_of_time=datetime(2026, 3, 1, 20, 1, tzinfo=offset),
    )
    assert result.origin_time == ORIGIN
    assert result.confirm_time == CONFIRM
    assert result.as_of_time == CONFIRM + timedelta(minutes=1)
    assert result.origin_time.tzinfo is UTC


def test_state_accepts_equal_origin_confirm_and_as_of_times() -> None:
    result = empty_state(origin_time=CONFIRM, confirm_time=CONFIRM, as_of_time=CONFIRM)
    assert result.origin_time == result.confirm_time == result.as_of_time


def test_state_rejects_as_of_before_confirm() -> None:
    with pytest.raises(DomainValidationError, match="as_of_time"):
        empty_state(as_of_time=CONFIRM - timedelta(seconds=1))


def test_state_rejects_confirm_before_origin() -> None:
    with pytest.raises(DomainValidationError, match="confirm_time"):
        empty_state(confirm_time=ORIGIN - timedelta(seconds=1))


@pytest.mark.parametrize("field_name", ["origin_time", "confirm_time", "as_of_time"])
def test_state_rejects_naive_times(field_name: str) -> None:
    with pytest.raises(DomainValidationError, match="timezone-aware"):
        empty_state(**{field_name: datetime(2026, 3, 1, 12, 0)})


def test_forming_ids_are_canonical_without_mutating_input() -> None:
    forming_ids = ("forming-b", "forming-a")
    result = empty_state(forming_candidate_ids=forming_ids)
    assert forming_ids == ("forming-b", "forming-a")
    assert result.forming_candidate_ids == ("forming-a", "forming-b")


def test_state_rejects_duplicate_forming_candidate_ids() -> None:
    with pytest.raises(DomainValidationError, match="unique"):
        empty_state(forming_candidate_ids=("duplicate", "duplicate"))


def test_state_rejects_non_tuple_forming_candidate_ids() -> None:
    with pytest.raises(DomainValidationError, match="must be a tuple"):
        empty_state(forming_candidate_ids=[])  # type: ignore[arg-type]


def test_state_requires_direction_and_provenance_types() -> None:
    with pytest.raises(DomainValidationError, match="direction"):
        empty_state(direction="UNKNOWN")  # type: ignore[arg-type]
    with pytest.raises(DomainValidationError, match="provenance"):
        empty_state(provenance="source")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "lifecycle_state",
    [
        LifecycleState.FRESH,
        LifecycleState.TESTED,
        LifecycleState.WEAKENED,
        LifecycleState.FLIPPED,
    ],
)
@pytest.mark.parametrize("side", [BoundarySide.UPPER, BoundarySide.LOWER])
def test_candidate_slots_accept_eligible_states(
    side: BoundarySide, lifecycle_state: LifecycleState
) -> None:
    field_name = (
        "candidate_upper_boundary"
        if side is BoundarySide.UPPER
        else "candidate_lower_boundary"
    )
    result = empty_state(
        **{field_name: boundary(side, lifecycle_state=lifecycle_state)}
    )
    assert getattr(result, field_name).lifecycle_state is lifecycle_state


@pytest.mark.parametrize(
    "lifecycle_state",
    [LifecycleState.CONFIRMED, LifecycleState.BROKEN, LifecycleState.RETIRED],
)
def test_candidate_slot_rejects_ineligible_states(
    lifecycle_state: LifecycleState,
) -> None:
    with pytest.raises(DomainValidationError, match="lifecycle_state"):
        empty_state(
            candidate_upper_boundary=boundary(
                BoundarySide.UPPER, lifecycle_state=lifecycle_state
            )
        )


@pytest.mark.parametrize(
    "lifecycle_state",
    [LifecycleState.TESTED, LifecycleState.WEAKENED, LifecycleState.FLIPPED],
)
@pytest.mark.parametrize("side", [BoundarySide.UPPER, BoundarySide.LOWER])
def test_confirmed_slots_accept_eligible_states(
    side: BoundarySide, lifecycle_state: LifecycleState
) -> None:
    field_name = (
        "confirmed_upper_boundary"
        if side is BoundarySide.UPPER
        else "confirmed_lower_boundary"
    )
    result = empty_state(
        **{field_name: boundary(side, lifecycle_state=lifecycle_state)}
    )
    assert getattr(result, field_name).lifecycle_state is lifecycle_state


@pytest.mark.parametrize(
    "lifecycle_state",
    [
        LifecycleState.FRESH,
        LifecycleState.CONFIRMED,
        LifecycleState.BROKEN,
        LifecycleState.RETIRED,
    ],
)
def test_confirmed_slot_rejects_ineligible_states(
    lifecycle_state: LifecycleState,
) -> None:
    with pytest.raises(DomainValidationError, match="lifecycle_state"):
        empty_state(
            confirmed_upper_boundary=boundary(
                BoundarySide.UPPER, lifecycle_state=lifecycle_state
            )
        )


@pytest.mark.parametrize(
    ("field_name", "boundary_value", "message"),
    [
        (
            "candidate_upper_boundary",
            boundary(BoundarySide.LOWER),
            "must be UPPER",
        ),
        (
            "candidate_lower_boundary",
            boundary(BoundarySide.UPPER),
            "must be LOWER",
        ),
        (
            "candidate_upper_boundary",
            boundary(BoundarySide.UPPER, market_role=MarketRole.SUPPORT),
            "must be RESISTANCE",
        ),
        (
            "candidate_lower_boundary",
            boundary(BoundarySide.LOWER, market_role=MarketRole.RESISTANCE),
            "must be SUPPORT",
        ),
        (
            "candidate_upper_boundary",
            boundary(BoundarySide.UPPER, symbol="EURUSD"),
            "symbol",
        ),
        (
            "candidate_upper_boundary",
            boundary(
                BoundarySide.UPPER,
                confirm_time=CONFIRM + timedelta(microseconds=1),
            ),
            "cannot be later",
        ),
        (
            "confirmed_upper_boundary",
            boundary(
                BoundarySide.LOWER,
                lifecycle_state=LifecycleState.TESTED,
            ),
            "must be UPPER",
        ),
        (
            "confirmed_lower_boundary",
            boundary(
                BoundarySide.LOWER,
                lifecycle_state=LifecycleState.TESTED,
                market_role=MarketRole.RESISTANCE,
            ),
            "must be SUPPORT",
        ),
        (
            "confirmed_upper_boundary",
            boundary(
                BoundarySide.UPPER,
                lifecycle_state=LifecycleState.TESTED,
                symbol="EURUSD",
            ),
            "symbol",
        ),
        (
            "confirmed_upper_boundary",
            boundary(
                BoundarySide.UPPER,
                lifecycle_state=LifecycleState.TESTED,
                confirm_time=CONFIRM + timedelta(microseconds=1),
            ),
            "cannot be later",
        ),
    ],
)
def test_slots_reject_wrong_side_role_symbol_or_time(
    field_name: str, boundary_value: BoundaryRef, message: str
) -> None:
    with pytest.raises(DomainValidationError, match=message):
        empty_state(**{field_name: boundary_value})


@pytest.mark.parametrize(
    "lifecycle_state",
    [LifecycleState.TESTED, LifecycleState.WEAKENED, LifecycleState.FLIPPED],
)
def test_same_boundary_may_fill_candidate_and_confirmed_slot(
    lifecycle_state: LifecycleState,
) -> None:
    selected = boundary(BoundarySide.UPPER, lifecycle_state=lifecycle_state)
    result = empty_state(
        candidate_upper_boundary=selected,
        confirmed_upper_boundary=selected,
    )
    assert result.candidate_upper_boundary is selected
    assert result.confirmed_upper_boundary is selected


def test_candidate_and_confirmed_slots_may_use_different_boundaries() -> None:
    candidate = boundary(BoundarySide.UPPER, suffix="candidate")
    confirmed = boundary(
        BoundarySide.UPPER,
        lifecycle_state=LifecycleState.TESTED,
        suffix="confirmed",
    )
    result = empty_state(
        candidate_upper_boundary=candidate,
        confirmed_upper_boundary=confirmed,
    )
    assert result.candidate_upper_boundary is candidate
    assert result.confirmed_upper_boundary is confirmed


def test_candidate_pair_accepts_ordered_ranges() -> None:
    result = empty_state(
        candidate_lower_boundary=boundary(BoundarySide.LOWER),
        candidate_upper_boundary=boundary(BoundarySide.UPPER),
    )
    assert (
        result.candidate_lower_boundary.price_range.high
        <= result.candidate_upper_boundary.price_range.low
    )


def test_candidate_pair_rejects_crossed_ranges() -> None:
    lower = boundary(
        BoundarySide.LOWER,
        price_range=PriceRange(Decimal("2401"), Decimal("2402")),
    )
    upper = boundary(
        BoundarySide.UPPER,
        price_range=PriceRange(Decimal("2400"), Decimal("2400.5")),
    )
    with pytest.raises(DomainValidationError, match="candidate lower boundary"):
        empty_state(
            candidate_lower_boundary=lower,
            candidate_upper_boundary=upper,
        )


def test_confirmed_pair_accepts_ordered_ranges() -> None:
    result = empty_state(
        confirmed_lower_boundary=boundary(
            BoundarySide.LOWER, lifecycle_state=LifecycleState.TESTED
        ),
        confirmed_upper_boundary=boundary(
            BoundarySide.UPPER, lifecycle_state=LifecycleState.TESTED
        ),
    )
    assert (
        result.confirmed_lower_boundary.price_range.high
        <= result.confirmed_upper_boundary.price_range.low
    )


def test_confirmed_pair_rejects_crossed_ranges() -> None:
    lower = boundary(
        BoundarySide.LOWER,
        lifecycle_state=LifecycleState.TESTED,
        price_range=PriceRange(Decimal("2401"), Decimal("2402")),
    )
    upper = boundary(
        BoundarySide.UPPER,
        lifecycle_state=LifecycleState.TESTED,
        price_range=PriceRange(Decimal("2400"), Decimal("2400.5")),
    )
    with pytest.raises(DomainValidationError, match="confirmed lower boundary"):
        empty_state(
            confirmed_lower_boundary=lower,
            confirmed_upper_boundary=upper,
        )


def test_candidate_and_confirmed_pairs_have_no_cross_group_range_constraint() -> None:
    result = state(
        candidate_lower_boundary=boundary(
            BoundarySide.LOWER,
            price_range=PriceRange(Decimal("300"), Decimal("301")),
        ),
        candidate_upper_boundary=boundary(
            BoundarySide.UPPER,
            price_range=PriceRange(Decimal("400"), Decimal("401")),
        ),
        confirmed_lower_boundary=boundary(
            BoundarySide.LOWER,
            lifecycle_state=LifecycleState.TESTED,
            price_range=PriceRange(Decimal("100"), Decimal("101")),
        ),
        confirmed_upper_boundary=boundary(
            BoundarySide.UPPER,
            lifecycle_state=LifecycleState.TESTED,
            price_range=PriceRange(Decimal("200"), Decimal("201")),
        ),
    )
    assert result.candidate_lower_boundary.price_range.low == Decimal("300")
    assert result.confirmed_upper_boundary.price_range.high == Decimal("201")


def test_boundary_timeframe_and_scale_may_differ_from_state_context() -> None:
    selected = boundary(
        BoundarySide.UPPER,
        timeframe=Timeframe.H4,
        scale=ScaleDescriptor("higher-context", 4),
    )
    result = empty_state(candidate_upper_boundary=selected)
    assert result.timeframe is Timeframe.H1
    assert result.candidate_upper_boundary.timeframe is Timeframe.H4
    assert result.candidate_upper_boundary.scale.scale_id == "higher-context"


def test_state_availability_starts_at_confirm_time() -> None:
    result = empty_state()
    assert not result.is_available_at(CONFIRM - timedelta(microseconds=1))
    with pytest.raises(DomainAvailabilityError):
        result.require_available_at(CONFIRM - timedelta(microseconds=1))
    assert result.is_available_at(CONFIRM)
    assert result.require_available_at(CONFIRM) is result


def test_timeframe_state_serializes_as_schema_version_2() -> None:
    assert state().to_dict()["schema_version"] == 2


def test_timeframe_state_v2_round_trip_is_exact() -> None:
    result = state(direction=Direction.TURNING)
    payload = result.to_dict()
    assert payload["direction"] == "TURNING"
    assert TimeframeState.from_dict(payload) == result
    assert TimeframeState.from_dict(payload).to_dict() == payload


@pytest.mark.parametrize(
    "field_name",
    [
        "direction",
        "candidate_upper_boundary",
        "candidate_lower_boundary",
        "confirmed_upper_boundary",
        "confirmed_lower_boundary",
    ],
)
def test_v2_payload_rejects_missing_state_fields(field_name: str) -> None:
    payload = state().to_dict()
    del payload[field_name]
    with pytest.raises(DomainSerializationError, match="missing fields"):
        TimeframeState.from_dict(payload)


def test_v2_payload_rejects_legacy_boundary_fields() -> None:
    payload = state().to_dict()
    payload["upper_boundary"] = None
    payload["lower_boundary"] = None
    with pytest.raises(DomainSerializationError, match="unknown fields"):
        TimeframeState.from_dict(payload)


def test_v1_payload_is_rejected_without_silent_migration() -> None:
    candidate_upper = boundary(BoundarySide.UPPER)
    candidate_lower = boundary(BoundarySide.LOWER)
    payload = {
        "schema_version": 1,
        "state_id": "legacy-state",
        "state_version": "v1",
        "symbol": "XAUUSD",
        "timeframe": Timeframe.H1.value,
        "scale": ScaleDescriptor("configured-primary", 1).to_dict(),
        "origin_time": ORIGIN.isoformat(),
        "confirm_time": CONFIRM.isoformat(),
        "as_of_time": CONFIRM.isoformat(),
        "upper_boundary": candidate_upper.to_dict(),
        "lower_boundary": candidate_lower.to_dict(),
        "forming_candidate_ids": [],
        "provenance": provenance("legacy-state").to_dict(),
    }
    with pytest.raises(
        DomainSerializationError,
        match="cannot be migrated safely.*Candidate versus Confirmed.*Direction",
    ):
        TimeframeState.from_dict(payload)


def test_unknown_timeframe_state_schema_is_rejected() -> None:
    payload = state().to_dict()
    payload["schema_version"] = 3
    with pytest.raises(DomainSerializationError, match="must be 2"):
        TimeframeState.from_dict(payload)


def test_unknown_direction_payload_is_rejected() -> None:
    payload = state().to_dict()
    payload["direction"] = "SIDEWAYS"
    with pytest.raises(DomainSerializationError, match="Direction"):
        TimeframeState.from_dict(payload)


def test_invalid_nested_boundary_payload_is_wrapped() -> None:
    payload = state().to_dict()
    nested = payload["candidate_upper_boundary"]
    assert isinstance(nested, dict)
    nested["future_field"] = True
    with pytest.raises(DomainSerializationError, match="unknown fields"):
        TimeframeState.from_dict(payload)


def test_serialized_forming_ids_require_ordered_list() -> None:
    payload = state().to_dict()
    payload["forming_candidate_ids"] = ("forming-a", "forming-b")
    with pytest.raises(DomainSerializationError, match="ordered list"):
        TimeframeState.from_dict(payload)


def test_boundary_decimal_and_state_time_precision_round_trip_without_loss() -> None:
    precise_time = CONFIRM + timedelta(microseconds=123456)
    precise = boundary(
        BoundarySide.UPPER,
        price_range=PriceRange(
            Decimal("2400.12345678901234567890"),
            Decimal("2401.98765432109876543210"),
        ),
    )
    result = empty_state(
        as_of_time=precise_time,
        candidate_upper_boundary=precise,
    )
    restored = TimeframeState.from_dict(result.to_dict())
    assert restored.as_of_time == precise_time
    assert restored.candidate_upper_boundary.price_range == precise.price_range


def test_repeated_timeframe_state_serialization_is_deterministic() -> None:
    result = state()
    assert result.to_dict() == result.to_dict()


def test_timeframe_state_has_no_legacy_boundary_aliases() -> None:
    result = state()
    assert not hasattr(result, "upper_boundary")
    assert not hasattr(result, "lower_boundary")
