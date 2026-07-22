import pytest

from msa.domain import ActiveBoxStatus
from msa.research.active_box import (
    ActiveBoxContractError,
    ActiveBoxSnapshot,
    build_selection_frame,
    build_side_decision,
    freeze_active_box_snapshot,
    observe_active_box_snapshot,
)
from msa.research.active_box.identity import semantic_id
from tests.research.resonance.fixtures import START, T1, T2, T3

from .fixtures import config, initial_frame, score_frame


def test_active_box_domain_mapping_and_original_selection_price() -> None:
    frame=initial_frame(); snapshot=frame.active_box_snapshot; box=snapshot.active_box
    assert box.box_id==snapshot.box_key_id
    assert box.status is ActiveBoxStatus.ACTIVE
    assert box.selection_price==frame.source_score_frame.source_frame.reference_price.price
    assert box.origin_time==min(box.lower_boundary.origin_time,box.upper_boundary.origin_time)
    assert box.confirm_time==snapshot.created_time and box.frozen_time is None and box.retired_time is None


def test_key_stable_but_snapshot_changes_asof_and_zone_snapshots() -> None:
    first=initial_frame().active_box_snapshot; later_score=score_frame(at=T2)
    lower=next(item for item in later_score.lower_zones if item.zone_key_id==first.observed_lower_zone_key_id)
    upper=next(item for item in later_score.upper_zones if item.zone_key_id==first.observed_upper_zone_key_id)
    later=observe_active_box_snapshot(later_score,first,lower.zone_snapshot_id,upper.zone_snapshot_id)
    assert later.box_key_id==first.box_key_id
    assert later.box_snapshot_id!=first.box_snapshot_id
    assert later.lower_projection==first.lower_projection and later.upper_projection==first.upper_projection
    assert later.active_box.selection_price==first.active_box.selection_price


def test_frozen_snapshot_is_terminal_and_keeps_episode_identity() -> None:
    first=initial_frame().active_box_snapshot; frozen=freeze_active_box_snapshot(score_frame(at=T2),first)
    assert frozen.active_box.status is ActiveBoxStatus.FROZEN
    assert frozen.box_key_id==first.box_key_id and frozen.box_snapshot_id!=first.box_snapshot_id
    assert frozen.active_box.confirm_time==frozen.active_box.frozen_time==frozen.active_box.as_of_time
    assert frozen.active_box.selection_price==first.active_box.selection_price


def _snapshot_with_as_of(snapshot: ActiveBoxSnapshot, value) -> ActiveBoxSnapshot:
    payload=snapshot.to_dict(); payload["active_box"]["as_of_time"]=value.isoformat()
    identity={"box_key_id":payload["box_key_id"],"source_score_frame_id":payload["source_score_frame_id"],
        "active_box":payload["active_box"],"observed_lower_zone_key_id":payload["observed_lower_zone_key_id"],
        "observed_lower_zone_snapshot_id":payload["observed_lower_zone_snapshot_id"],
        "observed_upper_zone_key_id":payload["observed_upper_zone_key_id"],
        "observed_upper_zone_snapshot_id":payload["observed_upper_zone_snapshot_id"],
        "status":payload["active_box"]["status"],"schema_version":1}
    payload["box_snapshot_id"]=semantic_id("active-box-snapshot-v1-",identity)
    payload["provenance"]["source_object_id"]=payload["box_snapshot_id"]
    return ActiveBoxSnapshot.from_dict(payload)


@pytest.mark.parametrize("wrong_as_of",[T1,T3])
def test_fully_resigned_active_as_of_must_equal_current_score_frame(wrong_as_of) -> None:
    previous=initial_frame().active_box_snapshot; current=score_frame(at=T2)
    lower=build_side_decision(current,config(),current.lower_zones[0].side,previous.observed_lower_zone_key_id)
    upper=build_side_decision(current,config(),current.upper_zones[0].side,previous.observed_upper_zone_key_id)
    observed=observe_active_box_snapshot(current,previous,lower.selected_zone_snapshot_id,upper.selected_zone_snapshot_id)
    forged=_snapshot_with_as_of(observed,wrong_as_of)
    with pytest.raises(Exception,match="AsOf"):
        build_selection_frame(source_score_frame=current,lower_decision=lower,upper_decision=upper,
            active_box_snapshot=forged,emitted_events=(),config=config())


def test_observe_rejects_forged_current_zone_snapshots_and_time_reversal() -> None:
    previous=initial_frame().active_box_snapshot; current=score_frame(at=T2)
    with pytest.raises(Exception,match="authoritative"):
        observe_active_box_snapshot(current,previous,"fake-lower","fake-upper")
    with pytest.raises(Exception,match="strictly advance"):
        observe_active_box_snapshot(score_frame(at=START),previous,
            previous.observed_lower_zone_snapshot_id,previous.observed_upper_zone_snapshot_id)


def test_freeze_rejects_time_reversal() -> None:
    with pytest.raises(Exception,match="backward"):
        freeze_active_box_snapshot(score_frame(at=START),initial_frame().active_box_snapshot)


@pytest.mark.parametrize("bad",[None,"bad",[]])
def test_observe_rejects_invalid_source_type_without_leaking_attribute_error(bad) -> None:
    previous=initial_frame().active_box_snapshot
    with pytest.raises(ActiveBoxContractError):
        observe_active_box_snapshot(bad,previous,previous.observed_lower_zone_snapshot_id,previous.observed_upper_zone_snapshot_id)


@pytest.mark.parametrize("bad",[None,"bad",[]])
def test_observe_rejects_invalid_previous_type_without_leaking_attribute_error(bad) -> None:
    with pytest.raises(ActiveBoxContractError):
        observe_active_box_snapshot(score_frame(at=T2),bad,"lower","upper")


@pytest.mark.parametrize("bad",[None,1,[]])
def test_observe_rejects_invalid_zone_snapshot_id_types(bad) -> None:
    previous=initial_frame().active_box_snapshot; current=score_frame(at=T2)
    with pytest.raises(ActiveBoxContractError):
        observe_active_box_snapshot(current,previous,bad,previous.observed_upper_zone_snapshot_id)
    with pytest.raises(ActiveBoxContractError):
        observe_active_box_snapshot(current,previous,previous.observed_lower_zone_snapshot_id,bad)


@pytest.mark.parametrize("field,bad",[("source",None),("source","bad"),("source",[]),("previous",None),("previous","bad"),("previous",[])])
def test_freeze_rejects_invalid_public_input_types(field,bad) -> None:
    source=score_frame(at=T2); previous=initial_frame().active_box_snapshot
    with pytest.raises(ActiveBoxContractError):
        freeze_active_box_snapshot(bad if field=="source" else source,bad if field=="previous" else previous)
