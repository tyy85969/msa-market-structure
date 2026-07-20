from dataclasses import FrozenInstanceError
from datetime import datetime
from decimal import Decimal
import json

import pytest

from msa.data import Timeframe
from msa.domain import ScaleDescriptor
from msa.research.levels import (
    HistoricalReactionConfig,
    LevelConfigurationError,
    LevelGenerationEvent,
    LevelGenerationError,
    LevelGenerationInput,
    LevelGenerationReport,
    LevelGenerationResult,
    LevelGenerator,
    PeriodicExtremeConfig,
)
from tests.research.levels.fixtures import (
    bar,
    periodic_config,
    periodic_generator,
    periodic_input,
    reaction_config,
)


def test_periodic_config_round_trip_is_exact_and_deterministic() -> None:
    config = periodic_config()
    restored = PeriodicExtremeConfig.from_dict(config.to_dict())
    assert restored == config
    assert json.dumps(config.to_dict(), sort_keys=True) == json.dumps(
        restored.to_dict(), sort_keys=True
    )


def test_reaction_config_round_trip_preserves_decimal_strings() -> None:
    config = reaction_config(
        touch_tolerance=Decimal("0.1250"),
        min_reaction_distance=Decimal("2.500"),
    )
    payload = config.to_dict()
    assert payload["touch_tolerance"] == "0.1250"
    assert payload["min_reaction_distance"] == "2.500"
    assert HistoricalReactionConfig.from_dict(payload) == config


@pytest.mark.parametrize("kind", ["periodic", "reaction"])
def test_config_is_immutable(kind: str) -> None:
    config = periodic_config() if kind == "periodic" else reaction_config()
    with pytest.raises(FrozenInstanceError):
        config.strict = False  # type: ignore[misc]


@pytest.mark.parametrize("kind", ["periodic", "reaction"])
def test_strict_false_is_rejected(kind: str) -> None:
    with pytest.raises(LevelConfigurationError, match="strict must be True"):
        (periodic_config if kind == "periodic" else reaction_config)(strict=False)


@pytest.mark.parametrize("kind", ["periodic", "reaction"])
def test_unknown_config_field_is_rejected(kind: str) -> None:
    config = periodic_config() if kind == "periodic" else reaction_config()
    payload = config.to_dict()
    payload["automatic_mode"] = True
    cls = PeriodicExtremeConfig if kind == "periodic" else HistoricalReactionConfig
    with pytest.raises(LevelConfigurationError, match="unknown fields"):
        cls.from_dict(payload)


@pytest.mark.parametrize("kind", ["periodic", "reaction"])
def test_unknown_schema_is_rejected(kind: str) -> None:
    config = periodic_config() if kind == "periodic" else reaction_config()
    payload = config.to_dict()
    payload["schema_version"] = 2
    cls = PeriodicExtremeConfig if kind == "periodic" else HistoricalReactionConfig
    with pytest.raises(LevelConfigurationError, match="schema_version"):
        cls.from_dict(payload)


@pytest.mark.parametrize("kind", ["periodic", "reaction"])
def test_missing_config_field_is_rejected(kind: str) -> None:
    config = periodic_config() if kind == "periodic" else reaction_config()
    payload = config.to_dict()
    del payload["policy_id"]
    cls = PeriodicExtremeConfig if kind == "periodic" else HistoricalReactionConfig
    with pytest.raises(LevelConfigurationError, match="missing fields"):
        cls.from_dict(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("touch_tolerance", Decimal("-0.1")),
        ("touch_tolerance", Decimal("NaN")),
        ("min_reactions", 1),
        ("min_reactions", True),
        ("min_separation_bars", 0),
        ("confirmation_horizon_bars", 0),
        ("min_reaction_distance", Decimal("0")),
        ("min_reaction_distance", Decimal("Infinity")),
        ("max_penetration", Decimal("-1")),
    ],
)
def test_invalid_reaction_parameters_are_rejected(field: str, value: object) -> None:
    with pytest.raises(LevelConfigurationError, match=field):
        reaction_config(**{field: value})


@pytest.mark.parametrize("field", ["generator_id", "generator_version", "policy_id"])
def test_empty_public_identifiers_are_rejected(field: str) -> None:
    with pytest.raises(LevelConfigurationError, match=field):
        periodic_config(**{field: ""})


def test_periodic_requires_explicit_timeframe_enum() -> None:
    with pytest.raises(LevelConfigurationError, match="period_timeframe"):
        periodic_config(period_timeframe="H1")


def test_periodic_requires_explicit_scale() -> None:
    with pytest.raises(LevelConfigurationError, match="scale"):
        periodic_config(scale=None)


def test_both_periodic_emission_flags_false_is_rejected() -> None:
    with pytest.raises(LevelConfigurationError, match="at least one"):
        periodic_config(emit_high=False, emit_low=False)


def test_non_bool_periodic_emission_flag_is_rejected() -> None:
    with pytest.raises(LevelConfigurationError, match="must be bool"):
        periodic_config(emit_high=1)


def test_result_report_and_event_round_trip() -> None:
    result = periodic_generator().generate_batch(periodic_input((bar(0),)))
    event = tuple(periodic_generator().iter_events(periodic_input((bar(0),))))[0]
    assert LevelGenerationResult.from_dict(result.to_dict()) == result
    assert LevelGenerationReport.from_dict(result.report.to_dict()) == result.report
    assert LevelGenerationEvent.from_dict(event.to_dict()) == event


@pytest.mark.parametrize("kind", ["result", "report", "event"])
def test_public_payload_unknown_field_is_rejected(kind: str) -> None:
    result = periodic_generator().generate_batch(periodic_input((bar(0),)))
    if kind == "result":
        payload = result.to_dict()
        factory = LevelGenerationResult.from_dict
    elif kind == "report":
        payload = result.report.to_dict()
        factory = LevelGenerationReport.from_dict
    else:
        payload = tuple(periodic_generator().iter_events(periodic_input((bar(0),))))[0].to_dict()
        factory = LevelGenerationEvent.from_dict
    payload["future_field"] = "forbidden"
    with pytest.raises(LevelConfigurationError, match="unknown fields"):
        factory(payload)


def test_event_first_seen_must_equal_candidate_confirm_time() -> None:
    candidate = periodic_generator().generate_batch(periodic_input((bar(0),))).candidates[0]
    assert candidate.confirm_time is not None
    with pytest.raises(LevelGenerationError, match="first_seen_time"):
        LevelGenerationEvent(candidate.confirm_time.replace(hour=3), candidate)


def test_naive_event_time_is_rejected() -> None:
    candidate = periodic_generator().generate_batch(periodic_input((bar(0),))).candidates[0]
    with pytest.raises(LevelGenerationError, match="timezone-aware"):
        LevelGenerationEvent(datetime(2026, 7, 1, 1), candidate)


@pytest.mark.parametrize("kind", ["result", "report", "event"])
def test_public_payload_unknown_schema_is_rejected(kind: str) -> None:
    result = periodic_generator().generate_batch(periodic_input((bar(0),)))
    if kind == "result":
        payload = result.to_dict()
        factory = LevelGenerationResult.from_dict
    elif kind == "report":
        payload = result.report.to_dict()
        factory = LevelGenerationReport.from_dict
    else:
        payload = tuple(
            periodic_generator().iter_events(periodic_input((bar(0),)))
        )[0].to_dict()
        factory = LevelGenerationEvent.from_dict
    payload["schema_version"] = 2
    with pytest.raises(LevelConfigurationError, match="schema_version"):
        factory(payload)


def test_level_generation_input_is_frozen() -> None:
    data = periodic_input((bar(0),))
    with pytest.raises(FrozenInstanceError):
        data.seed_candidates = ()  # type: ignore[misc]


def test_generator_implements_public_protocol() -> None:
    assert isinstance(periodic_generator(), LevelGenerator)


def test_scale_round_trip_remains_authoritative_domain_object() -> None:
    scale = ScaleDescriptor("explicit-c004-scale", None)
    config = periodic_config(scale=scale, period_timeframe=Timeframe.H4)
    assert PeriodicExtremeConfig.from_dict(config.to_dict()).scale == scale
