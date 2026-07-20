import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from msa.data.contracts import Timeframe
from msa.domain import (
    ActiveBox,
    ActiveBoxStatus,
    BoundaryRef,
    BoundarySide,
    ConfirmationStatus,
    Direction,
    DomainSerializationError,
    LevelCandidate,
    LifecycleState,
    MarketRole,
    PriceRange,
    ProvenanceRef,
    ScaleDescriptor,
    StructureCluster,
    StructureObjectKind,
    StructureSourceType,
    TimeframeState,
)


UTC = timezone.utc
ORIGIN = datetime(2026, 5, 1, 8, 0, 0, 123456, tzinfo=UTC)
CONFIRM = datetime(2026, 5, 1, 12, 0, 0, 654321, tzinfo=UTC)


def build_objects() -> list[tuple[type[object], object]]:
    scale = ScaleDescriptor("configured-primary", 1)
    price_range = PriceRange(
        Decimal("2300.12345678901234567890"),
        Decimal("2301.98765432109876543210"),
    )
    provenance = ProvenanceRef(
        "tests.serialization",
        "1.0.0",
        "source-object",
        "policy-1",
        ("parent-b", "parent-a"),
        ("finite note",),
    )
    lower = BoundaryRef(
        StructureObjectKind.LEVEL_CANDIDATE,
        "candidate-lower",
        "XAUUSD",
        Timeframe.H1,
        scale,
        price_range,
        BoundarySide.LOWER,
        MarketRole.SUPPORT,
        LifecycleState.FRESH,
        ORIGIN,
        CONFIRM,
        (StructureSourceType.SWING,),
        ("confirmed-swing",),
        provenance,
    )
    upper = BoundaryRef(
        StructureObjectKind.LEVEL_CANDIDATE,
        "candidate-upper",
        "XAUUSD",
        Timeframe.H4,
        scale,
        PriceRange(Decimal("2400"), Decimal("2401")),
        BoundarySide.UPPER,
        MarketRole.RESISTANCE,
        LifecycleState.TESTED,
        ORIGIN,
        CONFIRM,
        (StructureSourceType.PERIODIC_EXTREME,),
        ("periodic-high",),
        provenance,
    )
    candidate = LevelCandidate(
        "candidate-lower",
        "XAUUSD",
        Timeframe.H1,
        scale,
        price_range,
        StructureSourceType.SWING,
        BoundarySide.LOWER,
        MarketRole.SUPPORT,
        ConfirmationStatus.CONFIRMED,
        LifecycleState.FRESH,
        ORIGIN,
        CONFIRM,
        1,
        CONFIRM - timedelta(minutes=2),
        CONFIRM - timedelta(minutes=1),
        None,
        None,
        "confirmed-swing",
        provenance,
    )
    cluster = StructureCluster(
        "cluster-lower",
        "XAUUSD",
        Timeframe.H1,
        scale,
        PriceRange(Decimal("2299"), Decimal("2302")),
        BoundarySide.LOWER,
        MarketRole.SUPPORT,
        LifecycleState.CONFIRMED,
        ORIGIN,
        CONFIRM + timedelta(minutes=5),
        (lower,),
        "price-cluster",
        provenance,
    )
    state = TimeframeState(
        state_id="state-1",
        state_version="v2",
        symbol="XAUUSD",
        timeframe=Timeframe.H1,
        scale=scale,
        direction=Direction.RANGE,
        origin_time=ORIGIN,
        confirm_time=CONFIRM,
        as_of_time=CONFIRM + timedelta(minutes=10),
        candidate_upper_boundary=upper,
        candidate_lower_boundary=lower,
        confirmed_upper_boundary=upper,
        confirmed_lower_boundary=None,
        forming_candidate_ids=("forming-b", "forming-a"),
        provenance=provenance,
    )
    box = ActiveBox(
        "box-1",
        "XAUUSD",
        Timeframe.H1,
        scale,
        lower,
        upper,
        Decimal("2350.00000000000000000001"),
        ActiveBoxStatus.FROZEN,
        ORIGIN,
        CONFIRM,
        CONFIRM + timedelta(minutes=10),
        CONFIRM - timedelta(minutes=3),
        None,
        provenance,
    )
    return [
        (PriceRange, price_range),
        (ScaleDescriptor, scale),
        (ProvenanceRef, provenance),
        (BoundaryRef, lower),
        (LevelCandidate, candidate),
        (StructureCluster, cluster),
        (TimeframeState, state),
        (ActiveBox, box),
    ]


@pytest.mark.parametrize(
    ("model_type", "instance"),
    build_objects(),
    ids=lambda value: value.__name__ if isinstance(value, type) else None,
)
def test_all_public_value_and_domain_objects_round_trip(
    model_type: type[object], instance: object
) -> None:
    payload = instance.to_dict()  # type: ignore[attr-defined]
    expected_schema = 2 if model_type is TimeframeState else 1
    assert payload["schema_version"] == expected_schema
    assert model_type.from_dict(payload) == instance  # type: ignore[attr-defined]


def test_active_box_round_trip_preserves_lifecycle_event_bounds() -> None:
    box = build_objects()[7][1]
    payload = box.to_dict()  # type: ignore[attr-defined]
    payload["status"] = ActiveBoxStatus.RETIRED.value
    payload["retired_time"] = payload["confirm_time"]
    restored = ActiveBox.from_dict(payload)
    assert (
        restored.origin_time
        <= restored.frozen_time
        <= restored.retired_time
        <= restored.confirm_time
        <= restored.as_of_time
    )
    assert restored.to_dict() == payload


@pytest.mark.parametrize(
    ("model_type", "instance"),
    build_objects(),
    ids=lambda value: value.__name__ if isinstance(value, type) else None,
)
def test_repeated_serialization_is_deterministic(
    model_type: type[object], instance: object
) -> None:
    del model_type
    first = instance.to_dict()  # type: ignore[attr-defined]
    second = instance.to_dict()  # type: ignore[attr-defined]
    assert first == second
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_decimal_precision_is_serialized_as_string_without_loss() -> None:
    price_range = build_objects()[0][1]
    payload = price_range.to_dict()  # type: ignore[attr-defined]
    assert payload["low"] == "2300.12345678901234567890"
    assert PriceRange.from_dict(payload).low == Decimal(
        "2300.12345678901234567890"
    )


def test_utc_event_times_are_explicit_and_preserved() -> None:
    candidate = build_objects()[4][1]
    payload = candidate.to_dict()  # type: ignore[attr-defined]
    assert payload["origin_time"].endswith("+00:00")
    restored = LevelCandidate.from_dict(payload)
    assert restored.origin_time == ORIGIN
    assert restored.confirm_time == CONFIRM
    assert restored.origin_time.tzinfo is UTC


def test_tuple_fields_serialize_as_ordered_lists() -> None:
    objects = build_objects()
    provenance_payload = objects[2][1].to_dict()  # type: ignore[attr-defined]
    cluster_payload = objects[5][1].to_dict()  # type: ignore[attr-defined]
    assert provenance_payload["parent_object_ids"] == ["parent-a", "parent-b"]
    assert isinstance(cluster_payload["member_refs"], list)


@pytest.mark.parametrize(
    ("model_type", "instance"),
    build_objects(),
    ids=lambda value: value.__name__ if isinstance(value, type) else None,
)
def test_unknown_schema_version_is_rejected(
    model_type: type[object], instance: object
) -> None:
    payload = instance.to_dict()  # type: ignore[attr-defined]
    payload["schema_version"] = 999
    with pytest.raises(DomainSerializationError, match="schema_version"):
        model_type.from_dict(payload)  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    ("model_type", "instance"),
    build_objects(),
    ids=lambda value: value.__name__ if isinstance(value, type) else None,
)
def test_missing_required_field_is_rejected(
    model_type: type[object], instance: object
) -> None:
    payload = instance.to_dict()  # type: ignore[attr-defined]
    required_key = next(key for key in payload if key != "schema_version")
    del payload[required_key]
    with pytest.raises(DomainSerializationError, match="missing fields"):
        model_type.from_dict(payload)  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    ("model_type", "instance"),
    build_objects(),
    ids=lambda value: value.__name__ if isinstance(value, type) else None,
)
def test_unknown_payload_field_is_rejected(
    model_type: type[object], instance: object
) -> None:
    payload = instance.to_dict()  # type: ignore[attr-defined]
    payload["future_field"] = "not silently ignored"
    with pytest.raises(DomainSerializationError, match="unknown fields"):
        model_type.from_dict(payload)  # type: ignore[attr-defined]


def test_unknown_nested_enum_is_rejected() -> None:
    boundary = build_objects()[3][1]
    payload = boundary.to_dict()  # type: ignore[attr-defined]
    payload["boundary_side"] = "MIDDLE"
    with pytest.raises(DomainSerializationError, match="BoundarySide"):
        BoundaryRef.from_dict(payload)


def test_invalid_serialized_time_relationship_is_rejected() -> None:
    candidate = build_objects()[4][1]
    payload = candidate.to_dict()  # type: ignore[attr-defined]
    payload["confirm_time"] = (ORIGIN - timedelta(seconds=1)).isoformat()
    with pytest.raises(DomainSerializationError, match="confirm_time"):
        LevelCandidate.from_dict(payload)


def test_naive_serialized_datetime_is_rejected() -> None:
    candidate = build_objects()[4][1]
    payload = candidate.to_dict()  # type: ignore[attr-defined]
    payload["origin_time"] = "2026-05-01T08:00:00"
    with pytest.raises(DomainSerializationError, match="aware ISO-8601"):
        LevelCandidate.from_dict(payload)


def test_numeric_json_value_is_not_accepted_as_decimal_string() -> None:
    payload = PriceRange(Decimal("1"), Decimal("2")).to_dict()
    payload["low"] = 1
    with pytest.raises(DomainSerializationError, match="Decimal string"):
        PriceRange.from_dict(payload)
