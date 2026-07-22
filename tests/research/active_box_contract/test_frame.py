from copy import deepcopy
from decimal import Decimal

import pytest

from msa.domain import BoundarySide
from msa.research.active_box import (
    ActiveBoxContractError,
    ActiveBoxSelectionFrame,
    ActiveBoxSideAction,
    build_selection_frame,
    build_side_decision,
)
from msa.research.active_box.identity import semantic_id
from msa.research.active_box.policy import validate_side_decision

from .fixtures import config, initial_frame, score_frame


def _fully_resign_created_selection_price(frame, selection_price: Decimal):
    payload=deepcopy(frame.to_dict()); snapshot=payload["active_box_snapshot"]; cfg=payload["config_snapshot"]
    snapshot["active_box"]["selection_price"]=str(selection_price)
    box_key_payload={"engine_id":cfg["engine_id"],"engine_version":cfg["engine_version"],"policy_id":cfg["policy_id"],
        "created_time":snapshot["created_time"],"symbol":cfg["symbol"],"output_timeframe":cfg["output_timeframe"],
        "output_scale":cfg["output_scale"],"lower_zone_key_id":snapshot["lower_projection"]["source_zone_key_id"],
        "upper_zone_key_id":snapshot["upper_projection"]["source_zone_key_id"],
        "lower_projection_id":snapshot["lower_projection"]["projection_id"],"upper_projection_id":snapshot["upper_projection"]["projection_id"],
        "selection_price":str(selection_price),"schema_version":1}
    snapshot["box_key_id"]=semantic_id("active-box-key-v1-",box_key_payload)
    snapshot["active_box"]["box_id"]=snapshot["box_key_id"]
    snapshot["active_box"]["provenance"]["source_object_id"]=snapshot["box_key_id"]
    snapshot_identity={"box_key_id":snapshot["box_key_id"],"source_score_frame_id":snapshot["source_score_frame_id"],
        "active_box":snapshot["active_box"],"observed_lower_zone_key_id":snapshot["observed_lower_zone_key_id"],
        "observed_lower_zone_snapshot_id":snapshot["observed_lower_zone_snapshot_id"],
        "observed_upper_zone_key_id":snapshot["observed_upper_zone_key_id"],
        "observed_upper_zone_snapshot_id":snapshot["observed_upper_zone_snapshot_id"],
        "status":snapshot["active_box"]["status"],"schema_version":1}
    snapshot["box_snapshot_id"]=semantic_id("active-box-snapshot-v1-",snapshot_identity)
    snapshot["provenance"]["source_object_id"]=snapshot["box_snapshot_id"]
    snapshot["provenance"]["parent_object_ids"]=sorted((snapshot["source_score_frame_id"],snapshot["box_key_id"],
        snapshot["lower_projection"]["projection_id"],snapshot["upper_projection"]["projection_id"]))
    payload["active_box_snapshot"]=snapshot
    created=next(item for item in payload["emitted_events"] if item["event_type"]=="CREATED")
    created["box_key_id"]=snapshot["box_key_id"]; created["resulting_box_snapshot_id"]=snapshot["box_snapshot_id"]
    created["resulting_box_snapshot"]=deepcopy(snapshot)
    event_identity={"event_type":created["event_type"],"event_reason":created["event_reason"],
        "event_confirm_time":created["event_confirm_time"],"source_score_frame_id":created["source_score_frame_id"],
        "box_key_id":created["box_key_id"],"previous_box_snapshot_id":created["previous_box_snapshot_id"],
        "resulting_box_snapshot_id":created["resulting_box_snapshot_id"],"lower_zone_key_id":created["lower_zone_key_id"],
        "upper_zone_key_id":created["upper_zone_key_id"],"schema_version":1}
    created["event_id"]=semantic_id("active-box-event-v1-",event_identity)
    created["provenance"]["source_object_id"]=created["event_id"]
    created["provenance"]["parent_object_ids"]=sorted((created["source_score_frame_id"],created["resulting_box_snapshot_id"]))
    payload["report"]["active_box_key_id"]=snapshot["box_key_id"]
    frame_identity={"as_of_time":payload["as_of_time"],"source_score_frame_id":payload["source_score_frame_id"],
        "source_score_frame":payload["source_score_frame"],"lower_decision":payload["lower_decision"],"upper_decision":payload["upper_decision"],
        "active_box_snapshot":payload["active_box_snapshot"],"emitted_events":payload["emitted_events"],"report":payload["report"],
        "config_snapshot":payload["config_snapshot"],"schema_version":1}
    payload["selection_frame_id"]=semantic_id("active-box-selection-frame-v1-",frame_identity)
    payload["provenance"]["source_object_id"]=payload["selection_frame_id"]
    payload["provenance"]["parent_object_ids"]=sorted((payload["source_score_frame_id"],payload["lower_decision"]["decision_id"],
        payload["upper_decision"]["decision_id"],*(item["event_id"] for item in payload["emitted_events"]),snapshot["box_snapshot_id"]))
    return payload


def test_frame_binds_two_exact_decisions_box_event_report_and_provenance() -> None:
    frame=initial_frame()
    assert frame.lower_decision.side is BoundarySide.LOWER
    assert frame.upper_decision.side is BoundarySide.UPPER
    assert frame.active_box_snapshot.observed_lower_zone_key_id==frame.lower_decision.selected_zone_key_id
    assert frame.active_box_snapshot.observed_upper_zone_key_id==frame.upper_decision.selected_zone_key_id
    assert frame.report.created_event_count==1 and frame.report.frozen_event_count==0
    assert frame.report.warnings==frame.report.errors==()
    assert ActiveBoxSelectionFrame.from_dict(frame.to_dict())==frame


def test_no_pair_means_no_active_box() -> None:
    source=score_frame(); cfg=config(minimum_quality_score=Decimal("999"))
    lower=build_side_decision(source,cfg,BoundarySide.LOWER)
    upper=build_side_decision(source,cfg,BoundarySide.UPPER)
    frame=build_selection_frame(source_score_frame=source,lower_decision=lower,upper_decision=upper,active_box_snapshot=None,emitted_events=(),config=cfg)
    assert lower.action is upper.action is ActiveBoxSideAction.NONE
    assert frame.active_box_snapshot is None and not frame.report.has_active_box


def test_arbitrary_frame_id_and_report_attack_fail_closed() -> None:
    payload=initial_frame().to_dict(); payload["selection_frame_id"]="active-box-selection-frame-v1-"+"1"*64; payload["provenance"]["source_object_id"]=payload["selection_frame_id"]
    with pytest.raises(Exception,match="selection_frame_id"): ActiveBoxSelectionFrame.from_dict(payload)
    payload=initial_frame().to_dict(); payload["report"]["upper_zone_count"]+=1
    with pytest.raises(Exception,match="report"): ActiveBoxSelectionFrame.from_dict(payload)


def test_active_geometry_uses_current_reference_price() -> None:
    frame=initial_frame(); price=frame.source_score_frame.source_frame.reference_price.price
    assert frame.active_box_snapshot.active_box.lower_boundary.price_range.high<=price<=frame.active_box_snapshot.active_box.upper_boundary.price_range.low


def test_initial_pair_without_created_event_fails_closed() -> None:
    frame=initial_frame()
    with pytest.raises(Exception,match="event pattern"):
        build_selection_frame(source_score_frame=frame.source_score_frame,lower_decision=frame.lower_decision,upper_decision=frame.upper_decision,
            active_box_snapshot=frame.active_box_snapshot,emitted_events=(),config=frame.config_snapshot)


def test_fully_resigned_initial_pair_selection_price_attack_is_rejected() -> None:
    frame=initial_frame(); reference=frame.source_score_frame.source_frame.reference_price.price
    payload=_fully_resign_created_selection_price(frame,reference-Decimal("1"))
    with pytest.raises(Exception,match="formal creation result including selection price"):
        ActiveBoxSelectionFrame.from_dict(payload)


@pytest.mark.parametrize("field,bad",[
    ("source_score_frame",None),("source_score_frame","bad"),("source_score_frame",[]),
    ("lower_decision",None),("lower_decision","bad"),("lower_decision",[]),
    ("upper_decision",None),("upper_decision","bad"),("upper_decision",[]),
    ("active_box_snapshot","bad"),("active_box_snapshot",1),("active_box_snapshot",[]),
    ("emitted_events",None),("emitted_events","bad"),("emitted_events",[]),("emitted_events",(None,)),
    ("config",None),("config","bad"),("config",[]),
])
def test_frame_builder_rejects_invalid_public_input_types(field,bad) -> None:
    frame=initial_frame(); values={"source_score_frame":frame.source_score_frame,"lower_decision":frame.lower_decision,
        "upper_decision":frame.upper_decision,"active_box_snapshot":frame.active_box_snapshot,
        "emitted_events":frame.emitted_events,"config":frame.config_snapshot}
    values[field]=bad
    with pytest.raises(ActiveBoxContractError):
        build_selection_frame(**values)


@pytest.mark.parametrize("field,bad",[
    ("source_score_frame",None),("source_score_frame","bad"),("source_score_frame",[]),
    ("config",None),("config","bad"),("config",[]),
    ("decision",None),("decision","bad"),("decision",[]),
])
def test_validate_side_decision_rejects_invalid_public_input_types(field,bad) -> None:
    frame=initial_frame(); values={"source_score_frame":frame.source_score_frame,"config":frame.config_snapshot,"decision":frame.lower_decision}
    values[field]=bad
    with pytest.raises(ActiveBoxContractError):
        validate_side_decision(**values)
