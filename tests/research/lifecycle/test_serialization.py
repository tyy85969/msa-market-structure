from dataclasses import FrozenInstanceError

import pytest

from msa.research.lifecycle import (
    LifecycleConfig, LifecycleEngine, LifecycleEvent, LifecycleHistory,
    LifecycleInput, LifecycleReport, LifecycleSerializationError,
    LifecycleSnapshot, LifecycleSubjectState,
)
from tests.research.lifecycle.fixtures import (
    T2, T3, bar, engine, lifecycle_input, upper_break_bars,
)


def objects():
    data = lifecycle_input(upper_break_bars())
    lifecycle_engine = engine()
    history = lifecycle_engine.build_batch(data)
    snapshot = history.final_snapshot
    return {
        "config": (lifecycle_engine.config, LifecycleConfig.from_dict),
        "input": (data, LifecycleInput.from_dict),
        "engine": (lifecycle_engine, LifecycleEngine.from_dict),
        "event": (snapshot.events[-1], LifecycleEvent.from_dict),
        "state": (snapshot.states[0], LifecycleSubjectState.from_dict),
        "report": (snapshot.report, LifecycleReport.from_dict),
        "snapshot": (snapshot, LifecycleSnapshot.from_dict),
        "history": (history, LifecycleHistory.from_dict),
    }


@pytest.mark.parametrize("kind", list(objects()))
def test_all_public_objects_round_trip(kind: str) -> None:
    value, factory = objects()[kind]
    assert factory(value.to_dict()) == value


@pytest.mark.parametrize("kind", list(objects()))
def test_unknown_field_and_schema_fail_closed(kind: str) -> None:
    value, factory = objects()[kind]
    payload = value.to_dict()
    payload["future"] = True
    with pytest.raises(LifecycleSerializationError, match="unknown fields"):
        factory(payload)
    del payload["future"]
    payload["schema_version"] = 999
    with pytest.raises(LifecycleSerializationError, match="schema_version"):
        factory(payload)


@pytest.mark.parametrize(("kind", "field"), [
    ("input", "subjects"), ("event", "evidence"), ("state", "event_ids"),
    ("report", "assumptions"), ("snapshot", "events"), ("history", "snapshots"),
])
def test_tuple_serialization_requires_ordered_lists(kind: str, field: str) -> None:
    value, factory = objects()[kind]
    payload = value.to_dict()
    payload[field] = tuple(payload[field])
    with pytest.raises(LifecycleSerializationError, match="ordered list"):
        factory(payload)


def test_unknown_nested_field_is_rejected() -> None:
    payload = objects()["input"][0].to_dict()
    payload["source"]["bars"][0]["future"] = True
    with pytest.raises(LifecycleSerializationError, match="CanonicalBar fields"):
        LifecycleInput.from_dict(payload)


def test_nested_bar_decimal_float_is_rejected() -> None:
    payload = objects()["input"][0].to_dict()
    payload["source"]["bars"][0]["close"] = 96.0
    with pytest.raises(LifecycleSerializationError, match="Decimal string"):
        LifecycleInput.from_dict(payload)


def test_contradictory_state_and_snapshot_payloads_are_rejected() -> None:
    state_payload = objects()["state"][0].to_dict()
    state_payload["lifecycle_state"] = "FRESH"
    with pytest.raises(LifecycleSerializationError):
        LifecycleSubjectState.from_dict(state_payload)
    snapshot_payload = objects()["snapshot"][0].to_dict()
    snapshot_payload["events"] = snapshot_payload["events"][:-1]
    with pytest.raises(LifecycleSerializationError):
        LifecycleSnapshot.from_dict(snapshot_payload)


def test_public_values_are_frozen_and_mapping_free() -> None:
    history = objects()["history"][0]
    with pytest.raises(FrozenInstanceError):
        history.final_snapshot = None  # type: ignore[misc]
    assert isinstance(history.events, tuple)
    assert isinstance(history.final_snapshot.states, tuple)
    assert not hasattr(history.final_snapshot.states[0], "__dict__")


def test_snapshot_payload_wraps_ghost_prior_event_as_serialization_error() -> None:
    payload = objects()["snapshot"][0].to_dict()
    payload["events"][-1]["prior_event_ids"] = ["ghost-event"]
    with pytest.raises(LifecycleSerializationError, match="immediate predecessor"):
        LifecycleSnapshot.from_dict(payload)


def test_snapshot_payload_wraps_missing_activation_as_serialization_error() -> None:
    payload = objects()["snapshot"][0].to_dict()
    removed = payload["events"].pop(0)
    payload["states"][0]["event_ids"].remove(removed["event_id"])
    with pytest.raises(LifecycleSerializationError, match="exact ACTIVATED"):
        LifecycleSnapshot.from_dict(payload)


@pytest.mark.parametrize("target", ["event", "state"])
def test_snapshot_payload_wraps_provenance_conflict_as_serialization_error(
    target: str,
) -> None:
    payload = objects()["snapshot"][0].to_dict()
    if target == "event":
        payload["events"][0]["provenance"]["source_object_id"] = "wrong"
    else:
        payload["states"][0]["provenance"]["policy_id"] = "wrong"
    with pytest.raises(LifecycleSerializationError, match="provenance"):
        LifecycleSnapshot.from_dict(payload)


def test_history_payload_wraps_snapshot_config_change_as_serialization_error() -> None:
    payload = objects()["history"][0].to_dict()
    payload["snapshots"][-1]["config_snapshot"]["break_buffer"] = "2"
    payload["final_snapshot"]["config_snapshot"]["break_buffer"] = "2"
    with pytest.raises(LifecycleSerializationError, match="configurations"):
        LifecycleHistory.from_dict(payload)


def test_history_payload_wraps_state_change_without_event_as_serialization_error() -> None:
    data = lifecycle_input((
        bar(0),
        bar(1, open="101", high="103", low="100", close="102"),
        bar(2, open="103", high="104", low="103", close="103"),
    ))
    first = engine().build_as_of(data, T2)
    later = engine().build_as_of(data, T3)
    payload = {
        "schema_version": 1,
        "events": [event.to_dict() for event in later.events],
        "snapshots": [first.to_dict(), later.to_dict()],
        "final_snapshot": later.to_dict(),
    }
    payload["snapshots"][-1]["states"][0]["break_threshold"] = "999"
    payload["final_snapshot"]["states"][0]["break_threshold"] = "999"
    with pytest.raises(LifecycleSerializationError, match="without a new event"):
        LifecycleHistory.from_dict(payload)
