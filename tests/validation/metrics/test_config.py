from dataclasses import fields
from decimal import Decimal

import pytest

from msa.validation import (
    MetricConfigurationError,
    StructuralMetricConfig,
    StructuralMetricEvaluator,
)


def test_config_is_frozen_slotted_and_round_trips() -> None:
    config = StructuralMetricConfig()
    assert config == StructuralMetricConfig.from_dict(config.to_dict())
    assert config.__dataclass_params__.frozen
    assert "__dict__" not in config.__slots__
    assert tuple(item.name for item in fields(config))[-1] == "schema_version"


@pytest.mark.parametrize(
    "overrides",
    (
        {"strict": False},
        {"atr_period": 0},
        {"turn_resolution_bars": 0},
        {"break_observation_bars": "8"},
        {"break_continuation_atr": 1.0},
        {"resonance_match_max_distance_atr": Decimal("-1")},
        {"resonance_min_pair_count": 0},
    ),
)
def test_config_rejects_invalid_values(overrides) -> None:
    with pytest.raises(MetricConfigurationError):
        StructuralMetricConfig(**overrides)


def test_falsy_non_config_is_not_replaced_by_default() -> None:
    with pytest.raises(MetricConfigurationError):
        StructuralMetricEvaluator(0)  # type: ignore[arg-type]


def test_mutated_config_fails_closed() -> None:
    config = StructuralMetricConfig()
    object.__setattr__(config, "atr_period", 0)
    with pytest.raises(MetricConfigurationError):
        StructuralMetricEvaluator(config)
