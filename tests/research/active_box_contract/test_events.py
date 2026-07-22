import pytest

from msa.research.active_box import (
    ActiveBoxEventReason,
    ActiveBoxEventType,
    build_active_box_event,
    freeze_active_box_snapshot,
)
from tests.research.resonance.fixtures import T2

from .fixtures import initial_frame, score_frame


def test_initial_created_event_contract() -> None:
    event=initial_frame().emitted_events[0]
    assert event.event_type is ActiveBoxEventType.CREATED
    assert event.event_reason is ActiveBoxEventReason.INITIAL_PAIR
    assert event.previous_box_snapshot_id is None
    assert event.event_confirm_time==initial_frame().as_of_time


@pytest.mark.parametrize("reason",[ActiveBoxEventReason.PAIR_CHANGED,ActiveBoxEventReason.PAIR_UNAVAILABLE])
def test_frozen_event_contract(reason) -> None:
    previous=initial_frame().active_box_snapshot; frozen=freeze_active_box_snapshot(score_frame(at=T2),previous)
    event=build_active_box_event(event_type=ActiveBoxEventType.FROZEN,event_reason=reason,previous_snapshot=previous,resulting_snapshot=frozen)
    assert event.box_key_id==previous.box_key_id==frozen.box_key_id
    assert event.previous_box_snapshot_id==previous.box_snapshot_id
    assert event.event_confirm_time==score_frame(at=T2).as_of_time


def test_created_with_previous_snapshot_fails_closed() -> None:
    snapshot=initial_frame().active_box_snapshot
    with pytest.raises(Exception): build_active_box_event(event_type=ActiveBoxEventType.CREATED,event_reason=ActiveBoxEventReason.INITIAL_PAIR,previous_snapshot=snapshot,resulting_snapshot=snapshot)
