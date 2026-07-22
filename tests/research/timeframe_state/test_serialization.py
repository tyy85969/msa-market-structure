from dataclasses import FrozenInstanceError, fields

import pytest

from msa.research.timeframe_state import (
    BoundarySelectionExplanation,
    BoundarySelectionKey,
    TimeframeStateEvent,
    TimeframeStateHistory,
    TimeframeStateReport,
    TimeframeStateSerializationError,
    TimeframeStateSnapshot,
)
from tests.research.timeframe_state.fixtures import (
    base_pair,
    bar,
    direction_sequence_input,
    timeframe_engine,
    timeframe_input,
)


def public_objects():
    history = timeframe_engine().build_batch(direction_sequence_input())
    snapshot = history.final_snapshot
    return (
        snapshot.explanation.stable_comparison_keys[0],
        snapshot.explanation,
        snapshot.events[-1],
        snapshot.report,
        snapshot,
        history,
    )


@pytest.mark.parametrize(
    ("object_type", "index"),
    [
        (BoundarySelectionKey, 0),
        (BoundarySelectionExplanation, 1),
        (TimeframeStateEvent, 2),
        (TimeframeStateReport, 3),
        (TimeframeStateSnapshot, 4),
        (TimeframeStateHistory, 5),
    ],
)
def test_all_public_objects_round_trip_exactly(object_type, index: int) -> None:
    value = public_objects()[index]
    payload = value.to_dict()
    restored = object_type.from_dict(payload)
    assert restored == value
    assert restored.to_dict() == payload


def test_nested_timeframe_state_remains_schema_version_two() -> None:
    snapshot = timeframe_engine().build_batch(direction_sequence_input()).final_snapshot
    assert snapshot.to_dict()["state"]["schema_version"] == 2


@pytest.mark.parametrize("index", range(6))
def test_public_values_are_frozen_slotted_and_mapping_free(index: int) -> None:
    value = public_objects()[index]
    assert not hasattr(value, "__dict__")
    assert all(not isinstance(getattr(value, item.name), dict) for item in fields(value))
    with pytest.raises(FrozenInstanceError):
        value.schema_version = 2  # type: ignore[misc]


@pytest.mark.parametrize("object_type,index", [
    (BoundarySelectionKey, 0),
    (BoundarySelectionExplanation, 1),
    (TimeframeStateEvent, 2),
    (TimeframeStateReport, 3),
    (TimeframeStateSnapshot, 4),
    (TimeframeStateHistory, 5),
])
def test_unknown_field_and_schema_fail_closed(object_type, index: int) -> None:
    payload = public_objects()[index].to_dict()
    payload["future"] = True
    with pytest.raises(TimeframeStateSerializationError, match="unknown fields"):
        object_type.from_dict(payload)
    payload = public_objects()[index].to_dict()
    payload["schema_version"] = 2
    with pytest.raises(TimeframeStateSerializationError, match="must be 1"):
        object_type.from_dict(payload)


def test_tuple_serialization_requires_ordered_lists() -> None:
    snapshot = timeframe_engine().build_batch(direction_sequence_input()).final_snapshot
    event_payload = snapshot.events[-1].to_dict()
    event_payload["changed_fields"] = tuple(event_payload["changed_fields"])
    with pytest.raises(TimeframeStateSerializationError, match="ordered list"):
        TimeframeStateEvent.from_dict(event_payload)
    explanation_payload = snapshot.explanation.to_dict()
    explanation_payload["relevant_subject_ids"] = tuple(explanation_payload["relevant_subject_ids"])
    with pytest.raises(TimeframeStateSerializationError, match="ordered list"):
        BoundarySelectionExplanation.from_dict(explanation_payload)


def test_unknown_nested_field_is_rejected() -> None:
    payload = timeframe_engine().build_batch(direction_sequence_input()).to_dict()
    payload["final_snapshot"]["state"]["future"] = True
    with pytest.raises(TimeframeStateSerializationError, match="invalid serialized"):
        TimeframeStateHistory.from_dict(payload)


def test_explanation_state_contradiction_is_rejected_on_deserialization() -> None:
    payload = timeframe_engine().build_batch(direction_sequence_input()).final_snapshot.to_dict()
    payload["explanation"]["selected_confirmed_upper_id"] = "wrong"
    with pytest.raises(TimeframeStateSerializationError, match="contradict"):
        TimeframeStateSnapshot.from_dict(payload)


def test_report_state_contradiction_is_rejected_on_deserialization() -> None:
    payload = timeframe_engine().build_batch(direction_sequence_input()).final_snapshot.to_dict()
    payload["report"]["direction"] = "UNKNOWN"
    with pytest.raises(TimeframeStateSerializationError, match="contradict"):
        TimeframeStateSnapshot.from_dict(payload)


def test_event_chain_break_is_rejected_on_deserialization() -> None:
    payload = timeframe_engine().build_batch(direction_sequence_input()).to_dict()
    payload["events"][-1]["prior_event_id"] = "wrong"
    payload["final_snapshot"]["events"][-1]["prior_event_id"] = "wrong"
    payload["snapshots"][-1]["events"][-1]["prior_event_id"] = "wrong"
    with pytest.raises(TimeframeStateSerializationError):
        TimeframeStateHistory.from_dict(payload)


def test_repeated_serialization_is_deterministic() -> None:
    history = timeframe_engine().build_batch(timeframe_input(base_pair(), (bar(0),)))
    assert history.to_dict() == history.to_dict()
