from dataclasses import FrozenInstanceError, fields
from decimal import Decimal

import pytest

from msa.research.resonance import (
    ResonanceContextWeight,
    ResonanceScorer,
    ResonanceScoringConfig,
    ResonanceScoringConfigurationError,
    ResonanceScoringSerializationError,
    ResonanceToleranceMode,
)
from tests.research.resonance.fixtures import H4_PRIMARY, H12_MACRO

from .fixtures import scoring_config


def test_config_round_trip_is_strict_and_context_weights_are_canonical() -> None:
    value = scoring_config(
        context_weights=(
            ResonanceContextWeight(H4_PRIMARY, Decimal("1")),
            ResonanceContextWeight(H12_MACRO, Decimal("2")),
        )
    )
    restored = ResonanceScoringConfig.from_dict(value.to_dict())
    assert restored == value
    assert restored.to_dict() == value.to_dict()
    assert tuple(item.context for item in value.context_weights) == (H12_MACRO, H4_PRIMARY)


def test_public_config_objects_are_frozen_slotted_and_mapping_free() -> None:
    value = scoring_config()
    objects = (value, value.context_weights[0], value.factor_table, ResonanceScorer(value))
    for item in objects:
        assert not hasattr(item, "__dict__")
        assert all(not isinstance(getattr(item, field.name), dict) for field in fields(item))
        with pytest.raises(FrozenInstanceError):
            item.schema_version = 2  # type: ignore[misc]


def test_context_weight_duplicate_and_missing_frame_context_fail() -> None:
    duplicate = (
        ResonanceContextWeight(H4_PRIMARY, Decimal("1")),
        ResonanceContextWeight(H4_PRIMARY, Decimal("2")),
    )
    with pytest.raises(ResonanceScoringConfigurationError, match="exactly once"):
        scoring_config(context_weights=duplicate)


@pytest.mark.parametrize(
    "changes",
    [
        {"tolerance_mode": ResonanceToleranceMode.ABSOLUTE, "absolute_tolerance": None},
        {"tolerance_mode": ResonanceToleranceMode.ABSOLUTE, "reference_tolerance_fraction": Decimal("0.01")},
        {"tolerance_mode": ResonanceToleranceMode.REFERENCE_FRACTION, "absolute_tolerance": Decimal("1"), "reference_tolerance_fraction": Decimal("0.01")},
        {"distance_horizon_mode": ResonanceToleranceMode.REFERENCE_FRACTION, "absolute_distance_horizon": Decimal("1"), "reference_distance_fraction": Decimal("0.1")},
    ],
)
def test_tolerance_and_distance_modes_are_mutually_exclusive(changes) -> None:
    with pytest.raises(ResonanceScoringConfigurationError):
        scoring_config(**changes)


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("freshness_floor", Decimal("NaN")),
        ("touch_floor", Decimal("Infinity")),
        ("dependency_repeat_credit", Decimal("1.1")),
        ("aligned_direction_factor", Decimal("-0.1")),
        ("freshness_horizon_seconds", Decimal("0")),
    ],
)
def test_invalid_decimal_values_fail(field_name: str, value: Decimal) -> None:
    with pytest.raises(ResonanceScoringConfigurationError):
        scoring_config(**{field_name: value})


def test_strict_false_unknown_field_schema_and_non_string_decimal_fail() -> None:
    with pytest.raises(ResonanceScoringConfigurationError, match="strict"):
        scoring_config(strict=False)
    payload = scoring_config().to_dict()
    payload["future"] = True
    with pytest.raises(ResonanceScoringSerializationError):
        ResonanceScoringConfig.from_dict(payload)
    payload = scoring_config().to_dict()
    payload["schema_version"] = 2
    with pytest.raises(ResonanceScoringSerializationError):
        ResonanceScoringConfig.from_dict(payload)
    payload = scoring_config().to_dict()
    payload["candidate_tier_weight"] = 1.0
    with pytest.raises(ResonanceScoringSerializationError, match="Decimal string"):
        ResonanceScoringConfig.from_dict(payload)


def test_tuple_contract_requires_ordered_list() -> None:
    payload = scoring_config().to_dict()
    payload["context_weights"] = tuple(payload["context_weights"])
    with pytest.raises(ResonanceScoringSerializationError, match="ordered list"):
        ResonanceScoringConfig.from_dict(payload)


def test_reference_fraction_modes_use_exact_decimal() -> None:
    value = scoring_config(
        tolerance_mode=ResonanceToleranceMode.REFERENCE_FRACTION,
        absolute_tolerance=None,
        reference_tolerance_fraction=Decimal("0.01"),
        distance_horizon_mode=ResonanceToleranceMode.REFERENCE_FRACTION,
        absolute_distance_horizon=None,
        reference_distance_fraction=Decimal("0.2"),
    )
    assert value.effective_tolerance(Decimal("100")) == Decimal("1.00")
    assert value.distance_horizon(Decimal("100")) == Decimal("20.0")
