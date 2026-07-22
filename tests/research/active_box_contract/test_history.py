from datetime import timedelta
from decimal import Decimal

import pytest

from msa.research.active_box import (
    ActiveBoxEventReason,
    ActiveBoxEventType,
    ActiveBoxSelectionHistory,
    build_active_box_event,
    build_selection_frame,
    build_side_decision,
    create_active_box_snapshot,
    freeze_active_box_snapshot,
    observe_active_box_snapshot,
    project_zone,
)
from msa.domain import BoundarySide
from msa.research.resonance import ResonanceClass, ResonanceScorer
from tests.research.resonance.fixtures import H4_PRIMARY, T2, bar, custom_bundle, subject
from tests.research.resonance_scoring.fixtures import scorer, scoring_config, source_history

from .fixtures import config, selection_history


def _policy_history(cfg, source=None) -> ActiveBoxSelectionHistory:
    source=source or scorer().build_batch(source_history()); frames=[]; previous=None
    for score in source.frames:
        lower=build_side_decision(score,cfg,score.lower_zones[0].side,None if previous is None else previous.observed_lower_zone_key_id)
        upper=build_side_decision(score,cfg,score.upper_zones[0].side,None if previous is None else previous.observed_upper_zone_key_id)
        selected=(lower.selected_zone_key_id,upper.selected_zone_key_id)
        complete=all(item is not None for item in selected)
        if previous is None:
            if complete:
                lower_zone=next(item for item in score.lower_zones if item.zone_key_id==selected[0])
                upper_zone=next(item for item in score.upper_zones if item.zone_key_id==selected[1])
                box=create_active_box_snapshot(score,project_zone(score,lower_zone,cfg,score.as_of_time),project_zone(score,upper_zone,cfg,score.as_of_time),cfg)
                events=(build_active_box_event(event_type=ActiveBoxEventType.CREATED,event_reason=ActiveBoxEventReason.INITIAL_PAIR,resulting_snapshot=box),)
            else: box=None; events=()
        elif not complete:
            frozen=freeze_active_box_snapshot(score,previous); box=None
            events=(build_active_box_event(event_type=ActiveBoxEventType.FROZEN,event_reason=ActiveBoxEventReason.PAIR_UNAVAILABLE,previous_snapshot=previous,resulting_snapshot=frozen),)
        elif selected==(previous.observed_lower_zone_key_id,previous.observed_upper_zone_key_id):
            box=observe_active_box_snapshot(score,previous,lower.selected_zone_snapshot_id,upper.selected_zone_snapshot_id); events=()
        else:
            frozen=freeze_active_box_snapshot(score,previous)
            lower_zone=next(item for item in score.lower_zones if item.zone_key_id==selected[0])
            upper_zone=next(item for item in score.upper_zones if item.zone_key_id==selected[1])
            box=create_active_box_snapshot(score,project_zone(score,lower_zone,cfg,score.as_of_time),project_zone(score,upper_zone,cfg,score.as_of_time),cfg)
            events=(
                build_active_box_event(event_type=ActiveBoxEventType.FROZEN,event_reason=ActiveBoxEventReason.PAIR_CHANGED,previous_snapshot=previous,resulting_snapshot=frozen),
                build_active_box_event(event_type=ActiveBoxEventType.CREATED,event_reason=ActiveBoxEventReason.PAIR_CHANGED,resulting_snapshot=box),
            )
        frames.append(build_selection_frame(source_score_frame=score,lower_decision=lower,upper_decision=upper,active_box_snapshot=box,emitted_events=events,config=cfg))
        previous=box
    values=tuple(frames); events=tuple(event for frame in values for event in frame.emitted_events)
    frozen=tuple(event.resulting_box_snapshot for event in events if event.event_type is ActiveBoxEventType.FROZEN)
    return ActiveBoxSelectionHistory(frames=values,final_frame=values[-1],events=events,frozen_boxes=frozen,source_score_history=source,config_snapshot=cfg)


def test_history_contract_source_mapping_and_prefix_stability() -> None:
    history=selection_history(); prefix=tuple(frame.to_dict() for frame in history.frames[:-1])
    assert history.final_frame==history.frames[-1]
    assert tuple(frame.source_score_frame for frame in history.frames)==history.source_score_history.frames
    assert tuple(frame.to_dict() for frame in history.frames[:-1])==prefix
    assert len(history.events)==1 and history.frozen_boxes==()


def test_history_round_trip_is_exact_and_frozen() -> None:
    history=selection_history(); restored=ActiveBoxSelectionHistory.from_dict(history.to_dict())
    assert restored==history and restored.to_dict()==history.to_dict()
    assert not hasattr(history,"__dict__")


@pytest.mark.parametrize("attack",["final","events","source"])
def test_history_ledger_attacks_fail_closed(attack) -> None:
    payload=selection_history().to_dict()
    if attack=="final": payload["final_frame"]=payload["frames"][0]
    elif attack=="events": payload["events"]=[]
    else: payload["frames"][0]["source_score_frame_id"]="changed"
    with pytest.raises(Exception): ActiveBoxSelectionHistory.from_dict(payload)


def test_zone_snapshot_updates_keep_box_key_and_projections() -> None:
    history=selection_history(); keys={frame.active_box_snapshot.box_key_id for frame in history.frames}
    projections={(frame.active_box_snapshot.lower_projection.projection_id,frame.active_box_snapshot.upper_projection.projection_id) for frame in history.frames}
    snapshots={frame.active_box_snapshot.box_snapshot_id for frame in history.frames}
    assert len(keys)==len(projections)==1
    assert len(snapshots)==len(history.frames)
    assert all(not frame.emitted_events for frame in history.frames[1:])


def test_legal_pair_changed_history_has_atomic_freeze_create() -> None:
    history=_policy_history(config(minimum_selection_score=Decimal("0.25")))
    changed=next(frame for frame in history.frames if len(frame.emitted_events)==2)
    assert tuple(event.event_type for event in changed.emitted_events)==(ActiveBoxEventType.FROZEN,ActiveBoxEventType.CREATED)
    assert changed.emitted_events[0].event_reason is changed.emitted_events[1].event_reason is ActiveBoxEventReason.PAIR_CHANGED
    assert changed.emitted_events[0].box_key_id!=changed.emitted_events[1].box_key_id


def test_legal_pair_unavailable_history_freezes_once() -> None:
    history=_policy_history(config(minimum_quality_score=Decimal("0.59"),allowed_resonance_classes=(ResonanceClass.SINGLE,)))
    unavailable=next(frame for frame in history.frames if frame.emitted_events and frame.emitted_events[0].event_reason is ActiveBoxEventReason.PAIR_UNAVAILABLE)
    assert unavailable.active_box_snapshot is None and len(unavailable.emitted_events)==1
    assert unavailable.emitted_events[0].event_type is ActiveBoxEventType.FROZEN


def test_pair_can_reappear_after_formal_unavailable_freeze() -> None:
    subjects=(
        subject("old-upper",BoundarySide.UPPER,"110","111"),subject("old-lower",BoundarySide.LOWER,"90","91"),
        subject("new-upper",BoundarySide.UPPER,"108","109",confirm_time=T2+timedelta(minutes=30)),
        subject("new-lower",BoundarySide.LOWER,"92","93",confirm_time=T2+timedelta(minutes=30)),
    )
    assembler,data=custom_bundle(subjects,(bar(-1),bar(0),bar(1),bar(2)),(H4_PRIMARY,))
    source=ResonanceScorer(scoring_config(contexts=(H4_PRIMARY,))).build_batch(assembler.build_batch(data))
    history=_policy_history(config(minimum_quality_score=Decimal("0.28")),source)
    unavailable_index=next(index for index,frame in enumerate(history.frames) if frame.emitted_events and frame.emitted_events[0].event_reason is ActiveBoxEventReason.PAIR_UNAVAILABLE)
    recreated=history.frames[unavailable_index+1]
    assert recreated.emitted_events[0].event_type is ActiveBoxEventType.CREATED
    assert recreated.emitted_events[0].event_reason is ActiveBoxEventReason.INITIAL_PAIR
    assert recreated.lower_decision.current_zone_key_id is None and recreated.upper_decision.current_zone_key_id is None


def test_history_rejects_reset_current_keys_and_unfrozen_new_episode() -> None:
    valid=selection_history(); score=valid.source_score_history.frames[1]; cfg=valid.config_snapshot
    lower=build_side_decision(score,cfg,score.lower_zones[0].side); upper=build_side_decision(score,cfg,score.upper_zones[0].side)
    lower_zone=next(item for item in score.lower_zones if item.zone_key_id==lower.selected_zone_key_id)
    upper_zone=next(item for item in score.upper_zones if item.zone_key_id==upper.selected_zone_key_id)
    box=create_active_box_snapshot(score,project_zone(score,lower_zone,cfg,score.as_of_time),project_zone(score,upper_zone,cfg,score.as_of_time),cfg)
    event=build_active_box_event(event_type=ActiveBoxEventType.CREATED,event_reason=ActiveBoxEventReason.INITIAL_PAIR,resulting_snapshot=box)
    malicious=build_selection_frame(source_score_frame=score,lower_decision=lower,upper_decision=upper,active_box_snapshot=box,emitted_events=(event,),config=cfg)
    frames=(valid.frames[0],malicious,*valid.frames[2:]); events=tuple(item for frame in frames for item in frame.emitted_events)
    with pytest.raises(Exception,match="current keys"):
        ActiveBoxSelectionHistory(frames=frames,final_frame=frames[-1],events=events,frozen_boxes=(),source_score_history=valid.source_score_history,config_snapshot=cfg)


def test_history_rejects_unchanged_pair_with_replaced_box_identity() -> None:
    valid=selection_history(); score=valid.source_score_history.frames[1]; previous=valid.frames[0].active_box_snapshot; cfg=valid.config_snapshot
    lower=build_side_decision(score,cfg,score.lower_zones[0].side,previous.observed_lower_zone_key_id)
    upper=build_side_decision(score,cfg,score.upper_zones[0].side,previous.observed_upper_zone_key_id)
    lower_zone=next(item for item in score.lower_zones if item.zone_key_id==lower.selected_zone_key_id)
    upper_zone=next(item for item in score.upper_zones if item.zone_key_id==upper.selected_zone_key_id)
    replacement=create_active_box_snapshot(score,project_zone(score,lower_zone,cfg,score.as_of_time),project_zone(score,upper_zone,cfg,score.as_of_time),cfg)
    malicious=build_selection_frame(source_score_frame=score,lower_decision=lower,upper_decision=upper,active_box_snapshot=replacement,emitted_events=(),config=cfg)
    frames=(valid.frames[0],malicious,*valid.frames[2:]); events=tuple(item for frame in frames for item in frame.emitted_events)
    with pytest.raises(Exception,match="event ledger|formal observe"):
        ActiveBoxSelectionHistory(frames=frames,final_frame=frames[-1],events=events,frozen_boxes=(),source_score_history=valid.source_score_history,config_snapshot=cfg)
