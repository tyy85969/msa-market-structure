from dataclasses import FrozenInstanceError, fields

import pytest

from msa.research.resonance import (
    ReferencePriceField,
    ResonanceContext,
    ResonanceEvidencePolicy,
    ResonanceFrameAssembler,
    ResonanceFrameConfig,
    ResonanceFrameConfigurationError,
    ResonanceFrameInput,
    ResonanceFrameInputError,
    ResonanceFrameSerializationError,
)

from .fixtures import H4_PRIMARY, H12_MACRO, assembler, config, frame_input


def test_config_round_trip_and_contexts_are_canonical() -> None:
    value = config(contexts=(H12_MACRO, H4_PRIMARY))
    assert value.contexts == (H12_MACRO, H4_PRIMARY)
    restored = ResonanceFrameConfig.from_dict(value.to_dict())
    assert restored == value
    assert restored.to_dict() == value.to_dict()


def test_duplicate_and_empty_contexts_are_rejected() -> None:
    with pytest.raises(ResonanceFrameConfigurationError, match="non-empty"):
        config(contexts=())
    with pytest.raises(ResonanceFrameConfigurationError, match="unique"):
        config(contexts=(H4_PRIMARY, H4_PRIMARY))


def test_strict_false_is_rejected() -> None:
    with pytest.raises(ResonanceFrameConfigurationError, match="strict"):
        config(strict=False)


@pytest.mark.parametrize(
    ("field_name", "bad_value"),
    [("reference_price_field", "OPEN"), ("evidence_policy", "TOP_N")],
)
def test_only_c007a_price_field_and_evidence_policy_are_accepted(
    field_name: str, bad_value: str
) -> None:
    payload = config().to_dict()
    payload[field_name] = bad_value
    with pytest.raises(ResonanceFrameSerializationError):
        ResonanceFrameConfig.from_dict(payload)


def test_same_timeframe_may_have_multiple_scales_and_scale_may_span_timeframes() -> None:
    other_scale = ResonanceContext(H4_PRIMARY.timeframe, H12_MACRO.scale)
    other_timeframe = ResonanceContext(H12_MACRO.timeframe, H4_PRIMARY.scale)
    value = config(contexts=(H4_PRIMARY, other_scale, H12_MACRO, other_timeframe))
    assert len(value.contexts) == 4


def test_public_objects_are_frozen_slotted_and_mapping_free() -> None:
    frame = assembler().build_as_of(frame_input(), frame_input().lifecycle_history.final_snapshot.as_of_time)
    values = (
        H4_PRIMARY,
        config(),
        frame.reference_price,
        frame.context_states[0],
        frame.evidence[0],
        frame.report,
        frame,
        assembler().build_batch(frame_input()),
        frame_input(),
        assembler(),
    )
    for value in values:
        assert not hasattr(value, "__dict__")
        assert all(not isinstance(getattr(value, item.name), dict) for item in fields(value))
        with pytest.raises(FrozenInstanceError):
            value.schema_version = 2  # type: ignore[misc]


@pytest.mark.parametrize(
    "factory",
    [
        lambda: H4_PRIMARY,
        config,
        lambda: assembler().build_batch(frame_input()).final_frame.reference_price,
        lambda: assembler().build_batch(frame_input()).final_frame.context_states[0],
        lambda: assembler().build_batch(frame_input()).final_frame.evidence[0],
        lambda: assembler().build_batch(frame_input()).final_frame.report,
        lambda: assembler().build_batch(frame_input()).final_frame,
        lambda: assembler().build_batch(frame_input()),
        frame_input,
        assembler,
    ],
)
def test_unknown_fields_and_schema_fail_closed(factory) -> None:
    value = factory()
    payload = value.to_dict()
    payload["future"] = True
    with pytest.raises(ResonanceFrameSerializationError):
        type(value).from_dict(payload)
    payload = value.to_dict()
    payload["schema_version"] = 2
    with pytest.raises(ResonanceFrameSerializationError):
        type(value).from_dict(payload)


def test_tuple_contract_requires_ordered_list() -> None:
    payload = config().to_dict()
    payload["contexts"] = tuple(payload["contexts"])
    with pytest.raises(ResonanceFrameSerializationError, match="ordered list"):
        ResonanceFrameConfig.from_dict(payload)


def test_assembler_round_trip_is_strict() -> None:
    value = assembler()
    assert ResonanceFrameAssembler.from_dict(value.to_dict()) == value


def test_input_requires_authoritative_history_types() -> None:
    good = frame_input()
    with pytest.raises(ResonanceFrameInputError, match="LifecycleHistory"):
        ResonanceFrameInput(
            object(), good.timeframe_state_histories, good.reference_price_data
        )  # type: ignore[arg-type]


def test_enum_round_trips_are_strict() -> None:
    assert ReferencePriceField.from_dict(ReferencePriceField.CLOSE.to_dict()) is ReferencePriceField.CLOSE
    assert ResonanceEvidencePolicy.from_dict(
        ResonanceEvidencePolicy.ALL_EFFECTIVE_LIFECYCLE_STATES.to_dict()
    ) is ResonanceEvidencePolicy.ALL_EFFECTIVE_LIFECYCLE_STATES
