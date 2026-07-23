from datetime import timedelta
from decimal import Decimal

from msa.domain import BoundarySide
from msa.research.active_box import (
    ActiveBoxEventReason,
    create_active_box_snapshot,
    observe_active_box_snapshot,
    replay_active_box_history,
)
from msa.research.active_box.projection import project_zone
from msa.research.resonance import (
    ResonanceFrameHistory,
    ResonanceScoreHistory,
    ResonanceScorer,
)
from tests.research.active_box_engine.fixtures import (
    PAIR_CHANGED_THRESHOLD,
    PAIR_UNAVAILABLE_THRESHOLD,
    score_history,
    selector,
)
from tests.research.resonance.fixtures import (
    H4_PRIMARY,
    T1,
    T2,
    assembler,
    bar,
    custom_bundle,
    frame_input,
    subject,
)
from tests.research.resonance_scoring.fixtures import scorer, scoring_config


def _prefix(source: ResonanceScoreHistory, stop: int) -> ResonanceScoreHistory:
    source_frames = source.source_history.frames[: stop + 1]
    return ResonanceScoreHistory(
        frames=source.frames[: stop + 1],
        final_frame=source.frames[stop],
        source_history=ResonanceFrameHistory(
            frames=source_frames,
            final_frame=source_frames[-1],
            config_snapshot=source.source_history.config_snapshot,
        ),
        config_snapshot=source.config_snapshot,
    )


def _assert_frame_prefix_stable(
    source: ResonanceScoreHistory, stop: int, value=None
) -> None:
    active_selector = selector() if value is None else value
    complete = active_selector.build_batch(source)
    prefix = active_selector.build_batch(_prefix(source, stop))
    assert prefix.frames[-1].to_dict() == complete.frames[stop].to_dict()


def _delayed_zone_history() -> ResonanceScoreHistory:
    subjects = (
        subject("lower", BoundarySide.LOWER, "90", "91"),
        subject(
            "future-upper",
            BoundarySide.UPPER,
            "110",
            "111",
            confirm_time=T2,
        ),
    )
    engine, data = custom_bundle(
        subjects, (bar(-1), bar(0), bar(1), bar(2)), (H4_PRIMARY,)
    )
    return ResonanceScorer(
        scoring_config(contexts=(H4_PRIMARY,))
    ).build_batch(engine.build_batch(data))


def _broken_history() -> ResonanceScoreHistory:
    subjects = (
        subject("break-upper", BoundarySide.UPPER, "110", "111"),
        subject("stable-lower", BoundarySide.LOWER, "90", "91"),
    )
    bars = (
        bar(-1),
        bar(0, high="113", low="110", close="112"),
        bar(1, high="110", low="108", close="109"),
    )
    engine, data = custom_bundle(
        subjects,
        bars,
        (H4_PRIMARY,),
        break_buffer=Decimal("1"),
    )
    return ResonanceScorer(
        scoring_config(contexts=(H4_PRIMARY,))
    ).build_batch(engine.build_batch(data))


def _reappearance_history():
    subjects = (
        subject("old-upper", BoundarySide.UPPER, "110", "111"),
        subject("old-lower", BoundarySide.LOWER, "90", "91"),
        subject(
            "new-upper",
            BoundarySide.UPPER,
            "108",
            "109",
            confirm_time=T2 + timedelta(minutes=30),
        ),
        subject(
            "new-lower",
            BoundarySide.LOWER,
            "92",
            "93",
            confirm_time=T2 + timedelta(minutes=30),
        ),
    )
    engine, data = custom_bundle(
        subjects, (bar(-1), bar(0), bar(1), bar(2)), (H4_PRIMARY,)
    )
    source = ResonanceScorer(
        scoring_config(contexts=(H4_PRIMARY,))
    ).build_batch(engine.build_batch(data))
    value = selector(minimum_quality_score=Decimal("0.28"))
    return source, value, value.build_batch(source)


def test_01_future_zone_does_not_create_box_early() -> None:
    source = _delayed_zone_history()
    complete = selector().build_batch(source)
    assert complete.frames[0].active_box_snapshot is None
    _assert_frame_prefix_stable(source, 0)


def test_02_future_score_does_not_replace_box_early() -> None:
    source = score_history()
    value = selector(minimum_selection_score=PAIR_CHANGED_THRESHOLD)
    assert source.frames[0].zones[0].selection_score != (
        source.frames[1].zones[0].selection_score
    )
    _assert_frame_prefix_stable(source, 0, value)


def test_03_future_price_does_not_freeze_box_early() -> None:
    source = _broken_history()
    assert source.frames[0].source_frame.reference_price.to_dict() != (
        source.frames[1].source_frame.reference_price.to_dict()
    )
    _assert_frame_prefix_stable(source, 0)


def test_04_future_direction_does_not_change_side_decision_early() -> None:
    source = score_history()
    assert [
        item.to_dict() for item in source.frames[0].source_frame.context_states
    ] != [
        item.to_dict() for item in source.frames[1].source_frame.context_states
    ]
    _assert_frame_prefix_stable(source, 0)


def test_05_future_lifecycle_change_does_not_change_selection_early() -> None:
    source = score_history()
    assert [
        item.lifecycle_state for item in source.frames[0].source_frame.evidence
    ] != [
        item.lifecycle_state for item in source.frames[1].source_frame.evidence
    ]
    _assert_frame_prefix_stable(source, 0)


def test_06_future_broken_does_not_clear_box_early() -> None:
    source = _broken_history()
    assert source.frames[1].source_frame.excluded_broken_subject_ids == (
        "break-upper",
    )
    _assert_frame_prefix_stable(source, 0)


def test_07_future_retired_does_not_clear_box_early() -> None:
    source = _broken_history()
    assert source.frames[2].source_frame.excluded_retired_subject_ids == (
        "break-upper",
    )
    _assert_frame_prefix_stable(source, 0)


def test_08_origin_time_does_not_grant_zone_visibility() -> None:
    source = _delayed_zone_history()
    assert all(
        item.subject_id != "future-upper"
        for item in source.frames[0].source_frame.evidence
    )
    assert any(
        item.subject_id == "future-upper"
        for item in source.frames[2].source_frame.evidence
    )
    _assert_frame_prefix_stable(source, 0)


def test_09_price_crossing_only_applies_on_its_score_frame() -> None:
    source = _broken_history()
    result = selector().build_batch(source)
    assert result.frames[0].active_box_snapshot is not None
    assert result.frames[1].emitted_events[0].event_reason is (
        ActiveBoxEventReason.PAIR_UNAVAILABLE
    )
    _assert_frame_prefix_stable(source, 0)


def test_10_future_append_preserves_old_selection_frame_payload() -> None:
    source = score_history()
    for index in range(len(source.frames)):
        _assert_frame_prefix_stable(source, index)


def test_11_future_append_preserves_old_event_payload() -> None:
    source = score_history()
    value = selector(minimum_selection_score=PAIR_CHANGED_THRESHOLD)
    complete = value.build_batch(source)
    prefix = value.build_batch(_prefix(source, 1))
    assert [item.to_dict() for item in prefix.events] == [
        item.to_dict()
        for item in complete.events
        if item.event_confirm_time <= source.frames[1].as_of_time
    ]


def test_12_future_append_preserves_frozen_box_payload() -> None:
    source = score_history()
    value = selector(minimum_selection_score=PAIR_CHANGED_THRESHOLD)
    complete = value.build_batch(source)
    prefix = value.build_batch(_prefix(source, 1))
    assert [item.to_dict() for item in prefix.frozen_boxes] == [
        item.to_dict()
        for item in complete.frozen_boxes
        if item.active_box.confirm_time <= source.frames[1].as_of_time
    ]


def test_13_retain_uses_old_projection_complete_payload() -> None:
    source = score_history()
    value = selector()
    first = value.select_frame(source.frames[0])
    retained = value.select_frame(source.frames[1], first.active_box_snapshot)
    expected = observe_active_box_snapshot(
        source.frames[1],
        first.active_box_snapshot,
        retained.lower_decision.selected_zone_snapshot_id,
        retained.upper_decision.selected_zone_snapshot_id,
    )
    assert retained.active_box_snapshot.to_dict() == expected.to_dict()


def test_14_retain_updates_current_zone_observation_complete_payload() -> None:
    source = score_history()
    value = selector()
    first = value.select_frame(source.frames[0])
    retained = value.select_frame(source.frames[1], first.active_box_snapshot)
    expected = observe_active_box_snapshot(
        source.frames[1],
        first.active_box_snapshot,
        retained.lower_decision.selected_zone_snapshot_id,
        retained.upper_decision.selected_zone_snapshot_id,
    )
    assert retained.active_box_snapshot.to_dict() == expected.to_dict()


def test_15_pair_changed_projections_use_only_current_frame_evidence() -> None:
    source = score_history()
    value = selector(minimum_selection_score=PAIR_CHANGED_THRESHOLD)
    previous = value.select_frame(source.frames[0]).active_box_snapshot
    changed = value.select_frame(source.frames[1], previous)
    lower = next(
        zone
        for zone in source.frames[1].lower_zones
        if zone.zone_key_id == changed.lower_decision.selected_zone_key_id
    )
    upper = next(
        zone
        for zone in source.frames[1].upper_zones
        if zone.zone_key_id == changed.upper_decision.selected_zone_key_id
    )
    expected = create_active_box_snapshot(
        source.frames[1],
        project_zone(
            source.frames[1], lower, value.config, source.frames[1].as_of_time
        ),
        project_zone(
            source.frames[1], upper, value.config, source.frames[1].as_of_time
        ),
        value.config,
    )
    assert changed.active_box_snapshot.to_dict() == expected.to_dict()


def test_16_pair_unavailable_leaves_current_box_empty() -> None:
    source = score_history()
    value = selector(minimum_quality_score=PAIR_UNAVAILABLE_THRESHOLD)
    complete = value.build_batch(source)
    assert complete.frames[2].active_box_snapshot is None
    _assert_frame_prefix_stable(source, 2, value)


def test_17_pair_unavailable_does_not_repeat_freeze() -> None:
    source = score_history()
    value = selector(minimum_quality_score=PAIR_UNAVAILABLE_THRESHOLD)
    complete = value.build_batch(source)
    expected = value.select_frame(source.frames[3], None)
    assert complete.frames[3].to_dict() == expected.to_dict()


def test_18_pair_reappearance_creates_new_episode_only_when_visible() -> None:
    source, value, complete = _reappearance_history()
    unavailable = next(
        index
        for index, frame in enumerate(complete.frames)
        if frame.emitted_events
        and frame.emitted_events[0].event_reason
        is ActiveBoxEventReason.PAIR_UNAVAILABLE
    )
    recreated = complete.frames[unavailable + 1]
    expected = value.select_frame(source.frames[unavailable + 1], None)
    assert recreated.to_dict() == expected.to_dict()


def test_19_modifying_future_frame_does_not_change_historical_prefix() -> None:
    source = score_history()
    score_engine = scorer()
    extra_30 = score_engine.score_frame(
        assembler().build_as_of(frame_input(), T1 + timedelta(minutes=30))
    )
    extra_45 = score_engine.score_frame(
        assembler().build_as_of(frame_input(), T1 + timedelta(minutes=45))
    )

    def replay(extra) -> ResonanceScoreHistory:
        frames = (source.frames[0], source.frames[1], extra, *source.frames[2:])
        return ResonanceScoreHistory(
            frames=frames,
            final_frame=frames[-1],
            source_history=source.source_history,
            config_snapshot=source.config_snapshot,
        )

    first = replay_active_box_history(selector(), source, replay(extra_30))
    second = replay_active_box_history(selector(), source, replay(extra_45))
    assert [item.to_dict() for item in first.frames[:2]] == [
        item.to_dict() for item in second.frames[:2]
    ]


def test_20_c007c_can_select_nearest_zone_not_ranked_first_by_c007b() -> None:
    source = score_history()
    selected = selector().build_batch(source).frames[0]
    upper = next(
        zone
        for zone in source.frames[0].upper_zones
        if zone.zone_key_id == selected.upper_decision.selected_zone_key_id
    )
    assert upper.side_rank == 2
    _assert_frame_prefix_stable(source, 0)
