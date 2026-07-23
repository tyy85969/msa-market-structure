from msa.research.active_box import replay_active_box_history
from msa.research.active_box.identity import digest

from .fixtures import (
    PAIR_CHANGED_THRESHOLD,
    PAIR_UNAVAILABLE_THRESHOLD,
    replay_with_extra,
    score_history,
    selector,
)


def test_pre_fix_selection_event_and_history_golden_values_are_unchanged() -> None:
    source = score_history()
    default = selector().build_batch(source)
    changed = selector(
        minimum_selection_score=PAIR_CHANGED_THRESHOLD
    ).build_batch(source)
    unavailable_selector = selector(
        minimum_quality_score=PAIR_UNAVAILABLE_THRESHOLD
    )
    unavailable_previous = unavailable_selector.select_frame(
        source.frames[0]
    ).active_box_snapshot
    unavailable = unavailable_selector.select_frame(
        source.frames[2], unavailable_previous
    )
    pair_change = next(
        frame for frame in changed.frames if len(frame.emitted_events) == 2
    )
    assert default.frames[0].selection_frame_id == (
        "active-box-selection-frame-v1-"
        "8b15a5dc3b6faae327f8a558d8967906c6ee12f3e533b18fe0116a70d6be8cd2"
    )
    assert default.frames[1].selection_frame_id == (
        "active-box-selection-frame-v1-"
        "7a892ea205faeaf5f389ea81f959a9f318926feabba398ec69accc3b13a1dbf5"
    )
    assert next(
        event
        for event in unavailable.emitted_events
        if event.event_reason.value == "PAIR_UNAVAILABLE"
    ).event_id == (
        "active-box-event-v1-"
        "2f7fe93d57986e33c2b16115fb388532f5797cfd548ccf6a10f34f033e02b404"
    )
    frozen, created = pair_change.emitted_events
    assert frozen.event_id == (
        "active-box-event-v1-"
        "7a82874bf1a200e6d1f54b722d7065de524b977701a601aa6928b3266b592d6f"
    )
    assert created.event_id == (
        "active-box-event-v1-"
        "cc08c8469e837450521444c9e69887a118b95a817c5e55355e4f062cbae813f2"
    )
    assert frozen.box_key_id == (
        "active-box-key-v1-"
        "da66761b00c9f58c124a6e2150adad20cc597fdc4f197fde422c54b47d9f1dde"
    )
    assert created.box_key_id == (
        "active-box-key-v1-"
        "9fb1aec9ab2d67ba562ccc73713d09d21cedc9d8f0dbe1fb9999098517891586"
    )
    assert digest(default.to_dict()) == (
        "0b07c4510669aa6e777e375eb3e5e661d3b205cc3522257c45550620c66c2dbc"
    )
    assert digest(replay_active_box_history(selector(), source).to_dict()) == (
        "0b07c4510669aa6e777e375eb3e5e661d3b205cc3522257c45550620c66c2dbc"
    )
    assert digest(
        replay_active_box_history(
            selector(), source, replay_with_extra()
        ).to_dict()
    ) == (
        "1074b7112fddff4531df7b0ebf193cc18c0aeda4c875b4e0571c308fd294f7ef"
    )
