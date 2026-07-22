from dataclasses import fields

import pytest

from msa.research.active_box import (
    ActiveBoxEvent,
    ActiveBoxSelectionConfig,
    ActiveBoxSelectionFrame,
    ActiveBoxSelectionHistory,
    ActiveBoxSelectionKey,
    ActiveBoxSelectionReport,
    ActiveBoxSideDecision,
    ActiveBoxSnapshot,
    ActiveBoxZoneProjection,
    ZoneEligibility,
    selection_key,
)

from .fixtures import config, initial_frame, selection_history


def public_objects():
    frame=initial_frame(); history=selection_history()
    return (
        config(), frame.lower_decision.zone_evaluations[0], selection_key(frame.source_score_frame.lower_zones[0]),
        frame.lower_decision, frame.active_box_snapshot.lower_projection, frame.active_box_snapshot,
        frame.emitted_events[0], frame.report, frame, history,
    )


@pytest.mark.parametrize("index",range(10))
def test_public_objects_round_trip_exactly(index) -> None:
    value=public_objects()[index]; restored=type(value).from_dict(value.to_dict())
    assert restored==value and restored.to_dict()==value.to_dict()
    assert not hasattr(value,"__dict__")
    assert all(not isinstance(getattr(value,item.name),dict) for item in fields(value))


@pytest.mark.parametrize("index",range(10))
def test_unknown_field_and_schema_fail_closed(index) -> None:
    value=public_objects()[index]; payload=value.to_dict(); payload["future"]=True
    with pytest.raises(Exception): type(value).from_dict(payload)
    payload=value.to_dict(); payload["schema_version"]=2
    with pytest.raises(Exception): type(value).from_dict(payload)


@pytest.mark.parametrize(("object_type","field"),[
    (ActiveBoxSelectionConfig,"allowed_resonance_classes"),(ActiveBoxSideDecision,"zone_evaluations"),
    (ActiveBoxZoneProjection,"member_evidence_ids"),(ActiveBoxSelectionFrame,"emitted_events"),
    (ActiveBoxSelectionHistory,"frames"),
])
def test_tuple_wire_contract_requires_ordered_list(object_type,field) -> None:
    value=next(item for item in public_objects() if isinstance(item,object_type)); payload=value.to_dict(); payload[field]=tuple(payload[field])
    with pytest.raises(Exception,match="ordered list"): object_type.from_dict(payload)


def test_nested_decimal_float_attack_fails_closed() -> None:
    payload=initial_frame().to_dict(); payload["lower_decision"]["zone_evaluations"][0]["distance"]=1.0
    with pytest.raises(Exception,match="Decimal string"): ActiveBoxSelectionFrame.from_dict(payload)


def test_existing_normal_identity_outputs_remain_byte_for_byte_stable() -> None:
    frame=initial_frame(); box=frame.active_box_snapshot; event=frame.emitted_events[0]
    assert box.lower_projection.projection_id=="active-box-projection-v1-9740ff5ed41b56c4ca3853f71bef18cc65112b548587d6cc4dbf2beba087ca83"
    assert box.box_key_id=="active-box-key-v1-3e270226efe5e2afd81044ea8fb85c5dd9fe5cf9a68b16c909a74aa2403224fb"
    assert box.box_snapshot_id=="active-box-snapshot-v1-0b5be6dbff43c270e4a8e47863a2f2c421b6f8c1db06a93ddc829b544422ecd8"
    assert event.event_id=="active-box-event-v1-a01bdd8922265498bca64568afadac1ece3af1efc1eeef937527a3adb2abba3a"
    assert frame.selection_frame_id=="active-box-selection-frame-v1-f9392727f7c7ff08f74a78c1900f544ec2742a449f84097fa0be9048fc4117d1"
