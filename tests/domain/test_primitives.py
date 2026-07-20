from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest

from msa.domain import (
    ActiveBoxStatus,
    BoundarySide,
    ConfirmationStatus,
    Direction,
    DomainSerializationError,
    DomainValidationError,
    LifecycleState,
    MarketRole,
    PriceRange,
    ProvenanceRef,
    ScaleDescriptor,
    StructureObjectKind,
    StructureSourceType,
)


def test_price_range_accepts_single_price_level() -> None:
    price_range = PriceRange(Decimal("2350.10"), Decimal("2350.10"))
    assert price_range.width == Decimal("0.00")
    assert price_range.midpoint == Decimal("2350.10")


def test_price_range_decimal_math_and_interval_operations() -> None:
    price_range = PriceRange(Decimal("2300.10"), Decimal("2301.30"))
    assert price_range.width == Decimal("1.20")
    assert price_range.midpoint == Decimal("2300.70")
    assert price_range.contains(Decimal("2300.10"))
    assert price_range.contains(Decimal("2301.30"))
    assert not price_range.contains(Decimal("2302"))
    assert price_range.overlaps(
        PriceRange(Decimal("2301.30"), Decimal("2302.00"))
    )
    assert not price_range.overlaps(
        PriceRange(Decimal("2301.31"), Decimal("2302.00"))
    )


def test_price_range_rejects_reversed_bounds() -> None:
    with pytest.raises(DomainValidationError, match="PriceRange.low"):
        PriceRange(Decimal("2"), Decimal("1"))


@pytest.mark.parametrize(
    ("low", "high"),
    [(1.0, Decimal("2")), (Decimal("1"), 2.0)],
)
def test_price_range_rejects_float_inputs(low: object, high: object) -> None:
    with pytest.raises(DomainValidationError, match="must be a Decimal"):
        PriceRange(low, high)  # type: ignore[arg-type]


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity"])
def test_price_range_rejects_non_finite_decimals(value: str) -> None:
    with pytest.raises(DomainValidationError, match="finite"):
        PriceRange(Decimal(value), Decimal("2"))


def test_price_range_contains_rejects_non_decimal() -> None:
    with pytest.raises(DomainValidationError, match="PriceRange.price"):
        PriceRange(Decimal("1"), Decimal("2")).contains(1.5)  # type: ignore[arg-type]


def test_price_range_is_immutable() -> None:
    price_range = PriceRange(Decimal("1"), Decimal("2"))
    with pytest.raises(FrozenInstanceError):
        price_range.low = Decimal("0")  # type: ignore[misc]


def test_scale_descriptor_accepts_explicit_id_and_optional_rank() -> None:
    assert ScaleDescriptor("configured-primary", 2).rank == 2
    assert ScaleDescriptor("unranked", None).rank is None


@pytest.mark.parametrize(
    ("scale_id", "rank"),
    [("", 0), ("x", -1), ("x", True), ("x", 1.5)],
)
def test_scale_descriptor_rejects_invalid_values(
    scale_id: str, rank: object
) -> None:
    with pytest.raises(DomainValidationError, match="ScaleDescriptor"):
        ScaleDescriptor(scale_id, rank)  # type: ignore[arg-type]


def test_provenance_canonicalizes_parent_order_without_mutating_input() -> None:
    parents = ("parent-b", "parent-a")
    provenance = ProvenanceRef(
        source_module="tests.factory",
        source_version="1",
        source_object_id="source-1",
        policy_id="policy-1",
        parent_object_ids=parents,
        notes=("first", "second"),
    )
    assert parents == ("parent-b", "parent-a")
    assert provenance.parent_object_ids == ("parent-a", "parent-b")
    assert provenance.notes == ("first", "second")


def test_provenance_rejects_duplicate_parent_ids() -> None:
    with pytest.raises(DomainValidationError, match="unique"):
        ProvenanceRef(
            "module",
            "1",
            "source",
            None,
            ("same", "same"),
            (),
        )


def test_provenance_rejects_mutable_mapping_metadata() -> None:
    with pytest.raises(DomainValidationError, match="notes must be a tuple"):
        ProvenanceRef(
            "module",
            "1",
            "source",
            None,
            (),
            {"note": "mutable"},  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    "enum_value",
    [
        StructureSourceType.SWING,
        BoundarySide.UPPER,
        MarketRole.SUPPORT,
        ConfirmationStatus.FORMING,
        Direction.TURNING,
        LifecycleState.FRESH,
        StructureObjectKind.LEVEL_CANDIDATE,
        ActiveBoxStatus.ACTIVE,
    ],
)
def test_enums_support_versioned_round_trip(enum_value: object) -> None:
    enum_type = type(enum_value)
    assert enum_type.from_dict(enum_value.to_dict()) is enum_value


def test_enum_deserialization_rejects_unknown_value() -> None:
    with pytest.raises(DomainSerializationError, match="unknown"):
        BoundarySide.from_dict({"schema_version": 1, "value": "MIDDLE"})


def test_enum_deserialization_rejects_unknown_field() -> None:
    with pytest.raises(DomainSerializationError, match="unknown fields"):
        BoundarySide.from_dict(
            {"schema_version": 1, "value": "UPPER", "future": True}
        )


def test_direction_has_the_complete_stable_value_set() -> None:
    assert tuple(item.value for item in Direction) == (
        "UNKNOWN",
        "UP",
        "DOWN",
        "RANGE",
        "TURNING",
    )


def test_direction_is_exported_and_supports_standalone_round_trip() -> None:
    assert Direction.from_dict(Direction.UP.to_dict()) is Direction.UP


def test_direction_rejects_unknown_value_field_and_schema() -> None:
    with pytest.raises(DomainSerializationError, match="unknown"):
        Direction.from_dict({"schema_version": 1, "value": "SIDEWAYS"})
    with pytest.raises(DomainSerializationError, match="unknown fields"):
        Direction.from_dict(
            {"schema_version": 1, "value": "UP", "score": 1}
        )
    with pytest.raises(DomainSerializationError, match="schema_version"):
        Direction.from_dict({"schema_version": 2, "value": "UP"})
