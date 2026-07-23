from .fixtures import score_history, selector


def test_unchanged_pair_observes_without_reprojection_or_event() -> None:
    value = selector()
    history = score_history()
    first = value.select_frame(history.frames[0])
    previous = first.active_box_snapshot
    retained = value.select_frame(history.frames[1], previous)
    current = retained.active_box_snapshot
    assert retained.emitted_events == ()
    assert current.box_key_id == previous.box_key_id
    assert current.lower_projection == previous.lower_projection
    assert current.upper_projection == previous.upper_projection
    assert current.created_time == previous.created_time
    assert (
        current.active_box.selection_price
        == previous.active_box.selection_price
    )
    assert current.active_box.as_of_time == history.frames[1].as_of_time
    assert (
        current.observed_lower_zone_snapshot_id
        == retained.lower_decision.selected_zone_snapshot_id
    )
    assert (
        current.observed_upper_zone_snapshot_id
        == retained.upper_decision.selected_zone_snapshot_id
    )
