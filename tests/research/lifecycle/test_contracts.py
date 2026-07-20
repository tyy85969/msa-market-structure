from dataclasses import FrozenInstanceError, replace
from datetime import datetime
from decimal import Decimal

import pytest

from msa.data import Timeframe
from msa.domain import BoundarySide, LifecycleState, MarketRole, StructureObjectKind
from msa.research.lifecycle import (
    LifecycleConfig, LifecycleConfigurationError, LifecycleInput,
    LifecycleInputError, LifecycleSerializationError,
)
from tests.research.lifecycle.fixtures import (
    T1, bar, config, lifecycle_input, load_result, subject,
)


def test_config_round_trip_and_frozen() -> None:
    value = config()
    assert LifecycleConfig.from_dict(value.to_dict()) == value
    with pytest.raises(FrozenInstanceError):
        value.strict = False  # type: ignore[misc]


@pytest.mark.parametrize("field", [
    "test_tolerance", "break_buffer", "flip_tolerance",
    "flip_confirmation_distance", "failed_break_retirement_buffer",
])
def test_config_rejects_float_decimal(field: str) -> None:
    with pytest.raises(LifecycleConfigurationError, match="Decimal"):
        config(**{field: 1.0})


@pytest.mark.parametrize("field", [
    "test_tolerance", "break_buffer", "flip_tolerance",
    "flip_confirmation_distance", "failed_break_retirement_buffer",
])
def test_config_rejects_negative_or_nonfinite_decimal(field: str) -> None:
    with pytest.raises(LifecycleConfigurationError):
        config(**{field: Decimal("-0.1")})
    with pytest.raises(LifecycleConfigurationError):
        config(**{field: Decimal("NaN")})


@pytest.mark.parametrize(("field", "value"), [
    ("weakening_test_count", 1), ("minimum_test_separation_bars", 0),
    ("flip_horizon_bars", 0),
])
def test_config_rejects_invalid_integer_limits(field: str, value: int) -> None:
    with pytest.raises(LifecycleConfigurationError, match=field):
        config(**{field: value})


def test_strict_false_and_implicit_timeframe_are_rejected() -> None:
    with pytest.raises(LifecycleConfigurationError, match="strict must be True"):
        config(strict=False)
    with pytest.raises(LifecycleConfigurationError, match="observation_timeframe"):
        config(observation_timeframe="H1")


def test_config_unknown_schema_field_and_numeric_decimal_fail_closed() -> None:
    payload = config().to_dict()
    payload["future"] = True
    with pytest.raises(LifecycleSerializationError, match="unknown fields"):
        LifecycleConfig.from_dict(payload)
    del payload["future"]
    payload["schema_version"] = 2
    with pytest.raises(LifecycleSerializationError, match="schema_version"):
        LifecycleConfig.from_dict(payload)
    payload = config().to_dict()
    payload["test_tolerance"] = 1
    with pytest.raises(LifecycleSerializationError, match="Decimal string"):
        LifecycleConfig.from_dict(payload)


def test_candidate_and_cluster_refs_are_valid_inputs() -> None:
    value = lifecycle_input((bar(0),), (
        subject("candidate", kind=StructureObjectKind.LEVEL_CANDIDATE),
        subject("cluster", kind=StructureObjectKind.STRUCTURE_CLUSTER),
    ))
    assert len(value.subjects) == 2


def test_input_round_trip_is_exact_and_ordered() -> None:
    value = lifecycle_input((bar(0), bar(1)))
    assert LifecycleInput.from_dict(value.to_dict()) == value
    payload = value.to_dict()
    payload["subjects"] = tuple(payload["subjects"])
    with pytest.raises(LifecycleSerializationError, match="ordered list"):
        LifecycleInput.from_dict(payload)


def test_input_rejects_empty_duplicate_mixed_or_post_lifecycle_subjects() -> None:
    with pytest.raises(LifecycleInputError, match="non-empty"):
        LifecycleInput(load_result((bar(0),)), ())
    with pytest.raises(LifecycleInputError, match="unique"):
        LifecycleInput(load_result((bar(0),)), (subject("same"), subject("same")))
    with pytest.raises(LifecycleInputError, match="exactly CONFIRMED"):
        lifecycle_input((bar(0),), (subject(lifecycle_state=LifecycleState.FRESH),))


@pytest.mark.parametrize(("side", "role"), [
    (BoundarySide.UPPER, MarketRole.SUPPORT),
    (BoundarySide.LOWER, MarketRole.RESISTANCE),
])
def test_input_rejects_invalid_side_role(side: BoundarySide, role: MarketRole) -> None:
    with pytest.raises(LifecycleInputError, match="side/role"):
        lifecycle_input((bar(0),), (subject(side=side, role=role),))


def test_engine_rejects_mixed_symbol_timeframe_and_non_strict_source() -> None:
    from tests.research.lifecycle.fixtures import engine, source_config
    with pytest.raises(LifecycleInputError, match="symbol"):
        engine().build_batch(lifecycle_input((bar(0),), (subject(symbol="EURUSD"),)))
    wrong = LifecycleInput(load_result((bar(0),), config=source_config(timeframe=Timeframe.M30)), (subject(),))
    with pytest.raises(LifecycleInputError, match="timeframe"):
        engine().build_batch(wrong)
    report_only = LifecycleInput(load_result((bar(0),), config=source_config(strict=False)), (subject(),))
    with pytest.raises(LifecycleInputError, match="strict=True"):
        engine().build_batch(report_only)


def test_input_objects_are_not_modified() -> None:
    bars = (bar(0), bar(1))
    refs = (subject(),)
    before_bars = tuple(item.to_dict() for item in bars)
    before_refs = tuple(item.to_dict() for item in refs)
    from tests.research.lifecycle.fixtures import engine
    engine().build_batch(lifecycle_input(bars, refs))
    assert tuple(item.to_dict() for item in bars) == before_bars
    assert tuple(item.to_dict() for item in refs) == before_refs


def test_naive_subject_confirm_time_is_rejected_upstream() -> None:
    payload = subject().to_dict()
    payload["confirm_time"] = datetime(2026, 7, 1, 1).isoformat()
    from msa.domain import BoundaryRef, DomainSerializationError
    with pytest.raises(DomainSerializationError):
        BoundaryRef.from_dict(payload)
