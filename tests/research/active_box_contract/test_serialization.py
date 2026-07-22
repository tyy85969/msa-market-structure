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
