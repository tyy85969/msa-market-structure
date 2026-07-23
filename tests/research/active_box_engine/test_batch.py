from msa.research.active_box import (
    ActiveBoxEventType,
    build_active_box_history,
)

from .fixtures import PAIR_CHANGED_THRESHOLD, score_history, selector


def test_batch_preserves_every_score_frame_and_flattens_ledgers() -> None:
    source = score_history()
    result = selector(
        minimum_selection_score=PAIR_CHANGED_THRESHOLD
    ).build_batch(source)
    assert len(result.frames) == len(source.frames)
    assert tuple(frame.source_score_frame for frame in result.frames) == (
        source.frames
    )
    assert result.final_frame == result.frames[-1]
    assert result.events == tuple(
        event for frame in result.frames for event in frame.emitted_events
    )
    assert result.frozen_boxes == tuple(
        event.resulting_box_snapshot
        for event in result.events
        if event.event_type is ActiveBoxEventType.FROZEN
    )


def test_module_batch_function_is_exactly_equivalent() -> None:
    value = selector()
    source = score_history()
    assert (
        build_active_box_history(value, source).to_dict()
        == value.build_batch(source).to_dict()
    )
