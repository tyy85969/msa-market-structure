from msa.validation import MetricEventKind

from .fixtures import base_report, touch_report


def test_structure_and_box_events_are_deterministic_and_unique() -> None:
    first = base_report()
    second = base_report()
    assert first.events == second.events
    assert len({item.metric_event_id for item in first.events}) == len(
        first.events
    )
    assert any(
        item.kind is MetricEventKind.STRUCTURE_CONFIRMATION
        for item in first.events
    )
    assert any(
        item.kind is MetricEventKind.BOX_EPISODE_CREATED
        for item in first.events
    )


def test_first_touch_event_binds_creation_zone_and_touch_bar() -> None:
    events = tuple(
        item
        for item in touch_report().events
        if item.kind is MetricEventKind.BOUNDARY_FIRST_TOUCH
    )
    assert len(events) == 2
    assert {item.boundary_side.value for item in events} == {
        "LOWER",
        "UPPER",
    }
    assert all(item.zone_key and item.zone_snapshot_id for item in events)
    assert all(item.anchor_price is not None for item in events)
