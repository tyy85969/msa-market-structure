from msa.research.active_box import (
    ActiveBoxEventReason,
    ActiveBoxEventType,
    build_active_box_event,
    create_active_box_snapshot,
    freeze_active_box_snapshot,
)
from msa.research.active_box.projection import project_zone
import pytest

from .fixtures import PAIR_CHANGED_THRESHOLD, score_history, selector


@pytest.mark.parametrize(
    ("lower_index", "upper_index", "expected_actions"),
    [
        (0, 1, ("REPLACE", "RETAIN")),
        (1, 0, ("RETAIN", "REPLACE")),
        (0, 0, ("REPLACE", "REPLACE")),
    ],
    ids=["lower-only", "upper-only", "both-sides"],
)
def test_pair_change_atomically_freezes_then_reprojects_both_sides(
    lower_index, upper_index, expected_actions
) -> None:
    value = selector(minimum_selection_score=PAIR_CHANGED_THRESHOLD)
    source = score_history()
    creation, current = source.frames[:2]
    previous = create_active_box_snapshot(
        creation,
        project_zone(
            creation,
            creation.lower_zones[lower_index],
            value.config,
            creation.as_of_time,
        ),
        project_zone(
            creation,
            creation.upper_zones[upper_index],
            value.config,
            creation.as_of_time,
        ),
        value.config,
    )
    changed = value.select_frame(current, previous)
    assert (
        changed.lower_decision.action.value,
        changed.upper_decision.action.value,
    ) == expected_actions
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
    expected_frozen = freeze_active_box_snapshot(current, previous)
    expected_created = create_active_box_snapshot(
        current,
        project_zone(
            current,
            next(
                zone
                for zone in current.lower_zones
                if zone.zone_key_id
                == changed.lower_decision.selected_zone_key_id
            ),
            value.config,
            current.as_of_time,
        ),
        project_zone(
            current,
            next(
                zone
                for zone in current.upper_zones
                if zone.zone_key_id
                == changed.upper_decision.selected_zone_key_id
            ),
            value.config,
            current.as_of_time,
        ),
        value.config,
    )
    assert old.to_dict() == build_active_box_event(
        event_type=ActiveBoxEventType.FROZEN,
        event_reason=ActiveBoxEventReason.PAIR_CHANGED,
        previous_snapshot=previous,
        resulting_snapshot=expected_frozen,
    ).to_dict()
    assert new.to_dict() == build_active_box_event(
        event_type=ActiveBoxEventType.CREATED,
        event_reason=ActiveBoxEventReason.PAIR_CHANGED,
        resulting_snapshot=expected_created,
    ).to_dict()
    assert changed.active_box_snapshot.to_dict() == expected_created.to_dict()
    assert old.box_key_id != new.box_key_id
    assert old.previous_box_snapshot.to_dict() == previous.to_dict()
    assert old.resulting_box_snapshot.lower_projection == previous.lower_projection
    assert old.resulting_box_snapshot.upper_projection == previous.upper_projection
    assert old.resulting_box_snapshot.active_box.selection_price == (
        previous.active_box.selection_price
    )
    assert changed.active_box_snapshot.lower_projection != previous.lower_projection
    assert changed.active_box_snapshot.upper_projection != previous.upper_projection
    assert changed.active_box_snapshot.lower_projection.source_score_frame_id == (
        current.score_frame_id
    )
    assert changed.active_box_snapshot.upper_projection.source_score_frame_id == (
        current.score_frame_id
    )
    assert (
        changed.active_box_snapshot.active_box.selection_price
        == current.source_frame.reference_price.price
    )
