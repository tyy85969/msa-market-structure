from dataclasses import FrozenInstanceError, fields, replace
from datetime import datetime

import pytest

from msa.domain import TimeframeState
from msa.research.timeframe_state import (
    BoundarySelectionExplanation,
    BoundarySelectionKey,
    TimeframeStateEvent,
    TimeframeStateConfig,
    TimeframeStateHistory,
    TimeframeStateEngineError,
    TimeframeStateReport,
    TimeframeStateSerializationError,
    TimeframeStateSnapshot,
)
from msa.research.timeframe_state.identity import (
    _event_id,
    _snapshot_id,
    _state_id,
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


def _replace_engine_note(notes: list[str], engine_id: str) -> list[str]:
    return [
        f"engine_id={engine_id}" if item.startswith("engine_id=") else item
        for item in notes
    ]


def _resign_payload(
    payload: dict[str, object],
    *,
    state_engine_id: str | None = None,
    event_engine_id: str | None = None,
    snapshot_source_id: str | None = None,
) -> dict[str, object]:
    config = payload["config_snapshot"]
    state = payload["state"]
    event = payload["events"][-1]
    old_event_id = event["event_id"]
    if state_engine_id is not None:
        state["provenance"]["notes"] = _replace_engine_note(
            state["provenance"]["notes"], state_engine_id
        )
        state["state_id"] = _state_id(
            engine_id=state_engine_id,
            engine_version=config["engine_version"],
            policy_id=config["policy_id"],
            symbol=config["symbol"],
            target_timeframe=config["target_timeframe"],
            target_scale=config["target_scale"],
            selection_policy=config["selection_policy"],
            direction=state["direction"],
            candidate_upper_boundary=state["candidate_upper_boundary"],
            candidate_lower_boundary=state["candidate_lower_boundary"],
            confirmed_upper_boundary=state["confirmed_upper_boundary"],
            confirmed_lower_boundary=state["confirmed_lower_boundary"],
            forming_candidate_ids=state["forming_candidate_ids"],
            origin_time=datetime.fromisoformat(state["origin_time"]),
            confirm_time=datetime.fromisoformat(state["confirm_time"]),
            domain_schema_version=state["schema_version"],
            engine_schema_version=payload["schema_version"],
        )
        state["provenance"]["source_object_id"] = state["state_id"]
        event["current_state_id"] = state["state_id"]
    identity_engine_id = event_engine_id or config["engine_id"]
    if event_engine_id is not None:
        event["provenance"]["notes"] = _replace_engine_note(
            event["provenance"]["notes"], event_engine_id
        )
    event["event_id"] = _event_id(
        engine_id=identity_engine_id,
        engine_version=config["engine_version"],
        policy_id=config["policy_id"],
        previous_state_id=event["previous_state_id"],
        current_state_id=event["current_state_id"],
        event_type=event["event_type"],
        event_confirm_time=datetime.fromisoformat(event["event_confirm_time"]),
        previous_direction=event["previous_direction"],
        current_direction=event["current_direction"],
        changed_fields=event["changed_fields"],
        source_lifecycle_snapshot_id=event["source_lifecycle_snapshot_id"],
        source_lifecycle_event_ids=event["source_lifecycle_event_ids"],
        prior_event_id=event["prior_event_id"],
        schema_version=event["schema_version"],
    )
    event["provenance"]["source_object_id"] = event["event_id"]
    state["provenance"]["parent_object_ids"] = [
        event["event_id"] if item == old_event_id else item
        for item in state["provenance"]["parent_object_ids"]
    ]
    if snapshot_source_id is not None:
        payload["source_lifecycle_snapshot_id"] = snapshot_source_id
    payload["snapshot_id"] = _snapshot_id(
        config=config,
        source_lifecycle_snapshot_id=payload["source_lifecycle_snapshot_id"],
        as_of_time=datetime.fromisoformat(payload["as_of_time"]),
        state=state,
        explanation=payload["explanation"],
        events=payload["events"],
        report=payload["report"],
        schema_version=payload["schema_version"],
    )
    return payload


def _construct_snapshot(payload: dict[str, object]) -> TimeframeStateSnapshot:
    return TimeframeStateSnapshot(
        snapshot_id=payload["snapshot_id"],
        as_of_time=datetime.fromisoformat(payload["as_of_time"]),
        source_lifecycle_snapshot_id=payload["source_lifecycle_snapshot_id"],
        state=TimeframeState.from_dict(payload["state"]),
        explanation=BoundarySelectionExplanation.from_dict(payload["explanation"]),
        events=tuple(
            TimeframeStateEvent.from_dict(item) for item in payload["events"]
        ),
        report=TimeframeStateReport.from_dict(payload["report"]),
        config_snapshot=TimeframeStateConfig.from_dict(
            payload["config_snapshot"]
        ),
        schema_version=payload["schema_version"],
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


def test_direct_event_rejects_arbitrary_well_formed_hash() -> None:
    event = timeframe_engine().build_batch(direction_sequence_input()).events[-1]
    forged_id = event.event_id.rsplit("-", 1)[0] + "-" + "a" * 64
    forged_provenance = replace(event.provenance, source_object_id=forged_id)
    with pytest.raises(TimeframeStateEngineError, match="recomputed"):
        replace(event, event_id=forged_id, provenance=forged_provenance)


def test_direct_snapshot_rejects_arbitrary_well_formed_hash() -> None:
    snapshot = timeframe_engine().build_batch(direction_sequence_input()).final_snapshot
    forged_id = "timeframe-state-snapshot-v1-" + "a" * 64
    with pytest.raises(TimeframeStateEngineError, match="snapshot_id"):
        replace(snapshot, snapshot_id=forged_id)


def test_direct_snapshot_rejects_forged_nested_state_id() -> None:
    snapshot = timeframe_engine().build_batch(direction_sequence_input()).final_snapshot
    forged_state_id = "timeframe-state-v1-" + "a" * 64
    forged_state = replace(
        snapshot.state,
        state_id=forged_state_id,
        provenance=replace(
            snapshot.state.provenance, source_object_id=forged_state_id
        ),
    )
    with pytest.raises(TimeframeStateEngineError, match="state_id"):
        replace(snapshot, state=forged_state)


@pytest.mark.parametrize("target", ["state", "event", "snapshot"])
def test_serialized_identity_substitution_fails_closed(target: str) -> None:
    payload = timeframe_engine().build_batch(direction_sequence_input()).final_snapshot.to_dict()
    if target == "state":
        payload["state"]["state_id"] = "timeframe-state-v1-" + "b" * 64
        payload["state"]["provenance"]["source_object_id"] = payload["state"]["state_id"]
    elif target == "event":
        payload["events"][-1]["event_id"] = (
            payload["events"][-1]["event_id"].rsplit("-", 1)[0] + "-" + "b" * 64
        )
        payload["events"][-1]["provenance"]["source_object_id"] = payload["events"][-1]["event_id"]
    else:
        payload["snapshot_id"] = "timeframe-state-snapshot-v1-" + "b" * 64
    with pytest.raises(TimeframeStateSerializationError):
        TimeframeStateSnapshot.from_dict(payload)


@pytest.mark.parametrize("target", ["state", "event"])
def test_serialized_extra_provenance_parent_fails_closed(target: str) -> None:
    payload = timeframe_engine().build_batch(direction_sequence_input()).final_snapshot.to_dict()
    item = payload["state"] if target == "state" else payload["events"][-1]
    item["provenance"]["parent_object_ids"].append("forged-extra-parent")
    with pytest.raises(TimeframeStateSerializationError, match="provenance"):
        TimeframeStateSnapshot.from_dict(payload)


@pytest.mark.parametrize(
    ("state_engine_id", "event_engine_id"),
    [
        ("forged-state-engine", None),
        (None, "forged-event-engine"),
        ("forged-engine", "forged-engine"),
    ],
)
def test_fully_resigned_engine_identity_attack_fails_against_snapshot_config(
    state_engine_id: str | None, event_engine_id: str | None
) -> None:
    snapshot = timeframe_engine().build_batch(
        timeframe_input(base_pair(), (bar(0),))
    ).snapshots[0]
    payload = _resign_payload(
        snapshot.to_dict(),
        state_engine_id=state_engine_id,
        event_engine_id=event_engine_id,
    )
    with pytest.raises(TimeframeStateEngineError, match="snapshot config"):
        _construct_snapshot(payload)


@pytest.mark.parametrize(
    ("state_engine_id", "event_engine_id"),
    [
        ("forged-state-engine", None),
        (None, "forged-event-engine"),
        ("forged-engine", "forged-engine"),
    ],
)
def test_serialized_fully_resigned_engine_identity_attack_fails_closed(
    state_engine_id: str | None, event_engine_id: str | None
) -> None:
    snapshot = timeframe_engine().build_batch(
        timeframe_input(base_pair(), (bar(0),))
    ).snapshots[0]
    payload = _resign_payload(
        snapshot.to_dict(),
        state_engine_id=state_engine_id,
        event_engine_id=event_engine_id,
    )
    with pytest.raises(TimeframeStateSerializationError, match="snapshot config"):
        TimeframeStateSnapshot.from_dict(payload)


@pytest.mark.parametrize("snapshot_index", [0, -1])
def test_semantic_snapshot_rejects_resigned_source_mismatch(
    snapshot_index: int,
) -> None:
    snapshot = timeframe_engine().build_batch(
        direction_sequence_input()
    ).snapshots[snapshot_index]
    payload = _resign_payload(
        snapshot.to_dict(), snapshot_source_id="forged-lifecycle-snapshot"
    )
    with pytest.raises(TimeframeStateEngineError, match="snapshot source"):
        _construct_snapshot(payload)


def test_serialized_initialized_snapshot_source_mismatch_fails_closed() -> None:
    snapshot = timeframe_engine().build_batch(
        direction_sequence_input()
    ).snapshots[0]
    payload = _resign_payload(
        snapshot.to_dict(), snapshot_source_id="forged-lifecycle-snapshot"
    )
    with pytest.raises(TimeframeStateSerializationError, match="snapshot source"):
        TimeframeStateSnapshot.from_dict(payload)
