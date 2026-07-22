from dataclasses import FrozenInstanceError
from datetime import datetime

import pytest

from msa.data import Timeframe
from msa.domain import ScaleDescriptor
from msa.research.timeframe_state import (
    BoundarySelectionKey,
    TimeframeSelectionPolicy,
    TimeframeStateConfig,
    TimeframeStateConfigurationError,
    TimeframeStateEngine,
    TimeframeStateInput,
    TimeframeStateInputError,
    TimeframeStateSerializationError,
)
from tests.research.timeframe_state.fixtures import (
    PRIMARY,
    START,
    base_pair,
    bar,
    lifecycle_history,
    timeframe_config,
    timeframe_engine,
    timeframe_input,
)


def test_config_round_trip_is_exact_frozen_and_slotted() -> None:
    config = timeframe_config()
    assert TimeframeStateConfig.from_dict(config.to_dict()) == config
    assert not hasattr(config, "__dict__")
    with pytest.raises(FrozenInstanceError):
        config.symbol = "EURUSD"  # type: ignore[misc]


def test_engine_round_trip_is_exact() -> None:
    engine = timeframe_engine()
    assert TimeframeStateEngine.from_dict(engine.to_dict()) == engine


def test_config_rejects_strict_false_and_unknown_policy() -> None:
    with pytest.raises(TimeframeStateConfigurationError, match="strict"):
        timeframe_config(strict=False)
    payload = timeframe_config().to_dict()
    payload["selection_policy"] = "WEIGHTED"
    with pytest.raises(TimeframeStateSerializationError, match="invalid serialized"):
        TimeframeStateConfig.from_dict(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("symbol", ""),
        ("target_timeframe", "H4"),
        ("target_scale", "primary"),
    ],
)
def test_config_requires_explicit_valid_context(field: str, value: object) -> None:
    with pytest.raises(TimeframeStateConfigurationError):
        timeframe_config(**{field: value})


def test_config_rejects_unknown_field_and_schema() -> None:
    payload = timeframe_config().to_dict()
    payload["score"] = 1
    with pytest.raises(TimeframeStateSerializationError, match="unknown fields"):
        TimeframeStateConfig.from_dict(payload)
    payload = timeframe_config().to_dict()
    payload["schema_version"] = 2
    with pytest.raises(TimeframeStateSerializationError, match="must be 1"):
        TimeframeStateConfig.from_dict(payload)


def test_input_requires_lifecycle_history_and_round_trips() -> None:
    data = timeframe_input(base_pair(), (bar(0),))
    assert TimeframeStateInput.from_dict(data.to_dict()) == data
    with pytest.raises(TimeframeStateInputError, match="LifecycleHistory"):
        TimeframeStateInput("history")  # type: ignore[arg-type]


def test_engine_rejects_non_timeframe_state_input() -> None:
    history = lifecycle_history(base_pair(), (bar(0),))
    with pytest.raises(TimeframeStateInputError, match="TimeframeStateInput"):
        timeframe_engine().build_batch(history)  # type: ignore[arg-type]


def test_naive_and_early_processing_times_fail_closed() -> None:
    data = timeframe_input(base_pair(), (bar(0),))
    with pytest.raises(TimeframeStateInputError, match="timezone-aware"):
        timeframe_engine().build_as_of(data, datetime(2026, 7, 10))
    with pytest.raises(TimeframeStateInputError, match="precede"):
        timeframe_engine().build_as_of(data, START.replace(year=2025))


def test_selection_key_round_trip_and_full_comparison_tuple() -> None:
    key = BoundarySelectionKey(START, START, "subject", "state")
    assert BoundarySelectionKey.from_dict(key.to_dict()) == key
    assert key.comparison_tuple == (START, START, "subject", "state")


def test_selection_key_normalizes_aware_time_and_rejects_bad_order() -> None:
    key = BoundarySelectionKey(START, START, "subject", "state")
    assert key.state_confirm_time.tzinfo is not None
    with pytest.raises(Exception, match="cannot precede"):
        BoundarySelectionKey(START, START.replace(year=2027), "subject", "state")


def test_config_does_not_infer_xauusd_or_scale_from_history() -> None:
    config = timeframe_config(
        symbol="EURUSD",
        target_timeframe=Timeframe.H2,
        target_scale=ScaleDescriptor("explicit", None),
    )
    assert config.symbol == "EURUSD"
    assert config.target_timeframe is Timeframe.H2
    assert config.target_scale.scale_id == "explicit"


def test_only_latest_causal_policy_is_public() -> None:
    assert tuple(TimeframeSelectionPolicy) == (
        TimeframeSelectionPolicy.LATEST_CAUSAL,
    )


def test_engine_does_not_mutate_input_payload() -> None:
    data = timeframe_input(base_pair(), (bar(0),))
    before = data.to_dict()
    timeframe_engine().build_batch(data)
    assert data.to_dict() == before
