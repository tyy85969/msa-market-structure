from msa.research.active_box import (
    ActiveBoxEventReason,
    ActiveBoxEventType,
)

from .fixtures import PAIR_CHANGED_THRESHOLD, score_history, selector


def test_pair_change_atomically_freezes_then_creates() -> None:
    value = selector(minimum_selection_score=PAIR_CHANGED_THRESHOLD)
    history = value.build_batch(score_history())
    changed = next(
        frame for frame in history.frames if len(frame.emitted_events) == 2
    )
    old, new = changed.emitted_events
    assert (old.event_type, new.event_type) == (
        ActiveBoxEventType.FROZEN,
        ActiveBoxEventType.CREATED,
    )
    assert (
        old.event_reason
        is new.event_reason
        is ActiveBoxEventReason.PAIR_CHANGED
    )
    assert old.box_key_id != new.box_key_id
    assert old.previous_box_snapshot is not None
    assert old.resulting_box_snapshot.lower_projection == (
        old.previous_box_snapshot.lower_projection
    )
    assert old.resulting_box_snapshot.upper_projection == (
        old.previous_box_snapshot.upper_projection
    )
    assert (
        changed.active_box_snapshot.lower_projection.source_score_frame_id
        == changed.source_score_frame_id
    )
    assert (
        changed.active_box_snapshot.upper_projection.source_score_frame_id
        == changed.source_score_frame_id
    )
    assert (
        changed.active_box_snapshot.active_box.selection_price
        == changed.source_score_frame.source_frame.reference_price.price
    )
