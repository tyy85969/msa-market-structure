from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest

from msa.research.active_box import (
    ActiveBoxConfigurationError,
    ActiveBoxReplacementDistanceMode,
    ActiveBoxSelectionConfig,
    ActiveBoxSerializationError,
)
from msa.research.resonance import ResonanceClass

from .fixtures import config


def test_config_round_trip_frozen_slots_and_absolute_margin() -> None:
    value=config()
    assert ActiveBoxSelectionConfig.from_dict(value.to_dict())==value
    assert not hasattr(value,"__dict__")
    assert value.effective_distance_margin(Decimal("100"))==Decimal("1")
    with pytest.raises(FrozenInstanceError): value.strict=False  # type: ignore[misc]


def test_reference_fraction_mode_is_decimal_exact() -> None:
    value=config(replacement_distance_mode=ActiveBoxReplacementDistanceMode.REFERENCE_FRACTION,
        absolute_replacement_distance_margin=None,reference_replacement_distance_fraction=Decimal("0.01"))
    assert value.effective_distance_margin(Decimal("123.45"))==Decimal("1.2345")


@pytest.mark.parametrize("overrides",[
    {"allowed_resonance_classes":()},
    {"allowed_resonance_classes":(ResonanceClass.SINGLE,ResonanceClass.SINGLE)},
    {"allowed_resonance_classes":(ResonanceClass.SINGLE,ResonanceClass.LOCAL_CLUSTER)},
    {"minimum_quality_score":Decimal("-1")},
    {"minimum_selection_score":Decimal("NaN")},
    {"strict":False},{"require_expected_side":False},{"require_positive_distance_factor":False},
    {"reference_replacement_distance_fraction":Decimal("0.1")},
    {"replacement_distance_mode":ActiveBoxReplacementDistanceMode.REFERENCE_FRACTION,"absolute_replacement_distance_margin":Decimal("1"),"reference_replacement_distance_fraction":Decimal("0.1")},
])
def test_invalid_config_fails_closed(overrides) -> None:
    with pytest.raises(ActiveBoxConfigurationError): config(**overrides)


@pytest.mark.parametrize(("field","value"),[("schema_version",2),("future",True)])
def test_unknown_schema_or_field_fails_closed(field,value) -> None:
    payload=config().to_dict(); payload[field]=value
    with pytest.raises(ActiveBoxSerializationError): ActiveBoxSelectionConfig.from_dict(payload)


def test_decimal_and_tuple_wire_types_are_strict() -> None:
    payload=config().to_dict(); payload["minimum_quality_score"]=0.0
    with pytest.raises(ActiveBoxSerializationError): ActiveBoxSelectionConfig.from_dict(payload)
    payload=config().to_dict(); payload["allowed_resonance_classes"]=tuple(payload["allowed_resonance_classes"])
    with pytest.raises(ActiveBoxSerializationError,match="ordered list"): ActiveBoxSelectionConfig.from_dict(payload)
