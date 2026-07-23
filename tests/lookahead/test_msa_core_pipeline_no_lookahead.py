from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

import pytest

from msa.domain import BoundarySide, Direction, LifecycleState
from msa.research.active_box import (
    ActiveBoxEventReason,
    ActiveBoxEventType,
    freeze_active_box_snapshot,
)
from msa.research.lifecycle import LifecycleHistory
from msa.research.msa_core import (
    MSACoreConfig,
    MSACorePipeline,
    replay_msa_core_run,
)
from msa.research.resonance import ResonanceFrameInput
from msa.research.timeframe_state import TimeframeStateHistory
from tests.research.active_box_contract.fixtures import config as active_config
from tests.research.msa_core.fixtures import (
    config as core_config,
    extra_schedule,
    pipeline,
)
from tests.research.resonance.fixtures import (
    H4_PRIMARY,
    START,
    T1,
    T2,
    T3,
    bar,
    base_subjects,
    config as frame_config,
    custom_bundle,
    frame_input,
    lifecycle_history,
    load_result,
    reference_data,
    subject,
    timeframe_history,
)
from tests.research.resonance_scoring.fixtures import scoring_config
from tests.research.timeframe_state.fixtures import (
    T2 as DIRECTION_T2,
    bar as direction_bar,
    direction_sequence_input,
    load_result as direction_load_result,
    timeframe_engine as direction_engine,
)


def _single_context_pipeline() -> MSACorePipeline:
    return MSACorePipeline(
        MSACoreConfig(
            engine_id="c007d-msa-core",
            engine_version="1.0.0",
            policy_id="causal-msa-core-alpha-v1",
            frame_config=frame_config(contexts=(H4_PRIMARY,)),
            scoring_config=scoring_config(contexts=(H4_PRIMARY,)),
            active_box_config=active_config(),
        )
    )


def _custom_core(
    subjects,
    bars,
    *,
    active_overrides: dict[str, object] | None = None,
    **lifecycle_overrides: object,
):
    assembler, source = custom_bundle(
        subjects,
        bars,
        (H4_PRIMARY,),
        **lifecycle_overrides,
    )
    value = MSACorePipeline(
        MSACoreConfig(
            engine_id="c007d-msa-core",
            engine_version="1.0.0",
            policy_id="causal-msa-core-alpha-v1",
            frame_config=assembler.config,
            scoring_config=scoring_config(
                contexts=assembler.config.contexts
            ),
            active_box_config=active_config(
                **(active_overrides or {})
            ),
        )
    )
    return value, source, value.run(source)


def _truncate_source(
    source: ResonanceFrameInput, cutoff
) -> ResonanceFrameInput:
    lifecycle_snapshots = tuple(
        item
        for item in source.lifecycle_history.snapshots
        if item.as_of_time <= cutoff
    )
    lifecycle = LifecycleHistory(
        events=lifecycle_snapshots[-1].events,
        snapshots=lifecycle_snapshots,
        final_snapshot=lifecycle_snapshots[-1],
    )
    timeframe_histories = []
    for history in source.timeframe_state_histories:
        snapshots = tuple(
            item for item in history.snapshots if item.as_of_time <= cutoff
        )
        timeframe_histories.append(
            TimeframeStateHistory(
                events=snapshots[-1].events,
                snapshots=snapshots,
                final_snapshot=snapshots[-1],
                config_snapshot=history.config_snapshot,
            )
        )
    bars = tuple(
        item
        for item in source.reference_price_data.bars
        if item.available_time <= cutoff
    )
    return ResonanceFrameInput(
        lifecycle,
        tuple(timeframe_histories),
        load_result(
            bars, config=source.reference_price_data.source_config
        ),
    )


def _assert_complete_prefix(prefix, complete) -> None:
    count = len(prefix.frame_bundles)
    assert [item.to_dict() for item in prefix.resonance_history.frames] == [
        item.to_dict()
        for item in complete.resonance_history.frames[:count]
    ]
    assert [item.to_dict() for item in prefix.score_history.frames] == [
        item.to_dict() for item in complete.score_history.frames[:count]
    ]
    assert [
        item.to_dict() for item in prefix.active_box_history.frames
    ] == [
        item.to_dict()
        for item in complete.active_box_history.frames[:count]
    ]
    assert [item.to_dict() for item in prefix.frame_bundles] == [
        item.to_dict() for item in complete.frame_bundles[:count]
    ]
    cutoff = prefix.processing_times[-1]
    assert [
        item.to_dict() for item in prefix.active_box_history.events
    ] == [
        item.to_dict()
        for item in complete.active_box_history.events
        if item.event_confirm_time <= cutoff
    ]
    assert [
        item.to_dict() for item in prefix.active_box_history.frozen_boxes
    ] == [
        item.to_dict()
        for item in complete.active_box_history.frozen_boxes
        if item.active_box.confirm_time <= cutoff
    ]


def _pair_subjects():
    return (
        subject("upper", BoundarySide.UPPER, "110", "111"),
        subject("lower", BoundarySide.LOWER, "90", "91"),
    )


def _state_at(run, as_of_time, subject_id):
    frame = next(
        item
        for item in run.frame_bundles
        if item.as_of_time == as_of_time
    )
    return next(
        (
            item.lifecycle_state
            for item in frame.resonance_frame.evidence
            if item.subject_id == subject_id
        ),
        None,
    )


@pytest.mark.parametrize(
    ("cutoff", "future_time", "before_state", "future_state"),
    (
        (START, T1, LifecycleState.FRESH, LifecycleState.TESTED),
        (T1, T2, LifecycleState.TESTED, LifecycleState.WEAKENED),
    ),
)
def test_future_fresh_tested_weakened_transitions_preserve_full_prefix(
    cutoff,
    future_time,
    before_state,
    future_state,
) -> None:
    bars = (
        bar(-1),
        bar(0, high="111", low="90", close="100"),
        bar(1, high="111", low="90", close="100"),
        bar(2, high="111", low="90", close="100"),
    )
    value, source, complete = _custom_core(_pair_subjects(), bars)
    prefix = value.run(_truncate_source(source, cutoff))
    _assert_complete_prefix(prefix, complete)
    assert _state_at(prefix, cutoff, "upper") is before_state
    assert _state_at(complete, future_time, "upper") is future_state


@pytest.mark.parametrize(
    ("bars", "cutoff", "future_time", "future_state"),
    (
        (
            (
                bar(-1),
                bar(0, high="111", low="90", close="100"),
                bar(1, high="113", low="90", close="112"),
                bar(2, high="111", low="90", close="100"),
            ),
            T1,
            T2,
            LifecycleState.BROKEN,
        ),
        (
            (
                bar(-1),
                bar(0, high="113", low="110", close="112"),
                bar(1, high="111", low="110", close="110"),
                bar(2, high="113", low="112", close="112"),
            ),
            T2,
            T3,
            LifecycleState.FLIPPED,
        ),
        (
            (
                bar(-1),
                bar(0, high="113", low="110", close="112"),
                bar(1, high="110", low="108", close="109"),
            ),
            T1,
            T2,
            LifecycleState.RETIRED,
        ),
    ),
)
def test_future_broken_flipped_retired_preserve_every_old_payload(
    bars,
    cutoff,
    future_time,
    future_state,
) -> None:
    value, source, complete = _custom_core(
        _pair_subjects(), bars, break_buffer=Decimal("1")
    )
    prefix = value.run(_truncate_source(source, cutoff))
    _assert_complete_prefix(prefix, complete)
    future = next(
        item
        for item in complete.frame_bundles
        if item.as_of_time == future_time
    )
    if future_state is LifecycleState.FLIPPED:
        assert _state_at(complete, future_time, "upper") is future_state
    elif future_state is LifecycleState.BROKEN:
        assert future.resonance_frame.excluded_broken_subject_ids == (
            "upper",
        )
    else:
        assert future.resonance_frame.excluded_retired_subject_ids == (
            "upper",
        )


def test_future_timeframe_direction_preserves_full_pipeline_prefix() -> None:
    timeframe_input = direction_sequence_input()
    lifecycle = timeframe_input.lifecycle_history
    timeframe = direction_engine().build_batch(timeframe_input)
    bars = (
        direction_bar(0, high="111", low="90", close="100"),
        direction_bar(1, high="116", low="95", close="105"),
        direction_bar(2, high="106", low="85", close="95"),
        direction_bar(3, high="101", low="80", close="90"),
    )
    source = ResonanceFrameInput(
        lifecycle,
        (timeframe,),
        direction_load_result(bars),
    )
    value = _single_context_pipeline()
    complete = value.run(source)
    prefix = value.run(_truncate_source(source, DIRECTION_T2))
    _assert_complete_prefix(prefix, complete)
    assert (
        prefix.final_bundle.resonance_frame.context_states[0].state.direction
        is Direction.UP
    )
    assert [
        item.resonance_frame.context_states[0].state.direction
        for item in complete.frame_bundles[-2:]
    ] == [Direction.TURNING, Direction.DOWN]


def _appended_lifecycle_inputs():
    subjects = base_subjects()[:3]
    prefix_bars = (bar(-1), bar(0, high="111", low="90", close="101"))
    future_bars = prefix_bars + (
        bar(1, high="111", low="90", close="102"),
    )
    prefix_history = lifecycle_history(subjects, prefix_bars)
    extended_history = lifecycle_history(subjects, future_bars)
    appended_history = LifecycleHistory(
        events=extended_history.events,
        snapshots=prefix_history.snapshots
        + tuple(
            item for item in extended_history.snapshots if item.as_of_time > T1
        ),
        final_snapshot=extended_history.final_snapshot,
    )
    return (
        ResonanceFrameInput(
            prefix_history,
            (timeframe_history(prefix_history, H4_PRIMARY),),
            load_result(prefix_bars),
        ),
        ResonanceFrameInput(
            appended_history,
            (timeframe_history(appended_history, H4_PRIMARY),),
            load_result(future_bars),
        ),
    )


def test_future_lifecycle_and_timeframe_append_preserves_old_full_bundle() -> None:
    prefix, extended = _appended_lifecycle_inputs()
    value = _single_context_pipeline()
    before = value.run(prefix)
    after = value.run(extended)
    assert after.frame_bundles[0].to_dict() == before.frame_bundles[
        0
    ].to_dict()


def test_future_reference_bar_append_preserves_every_old_full_bundle() -> None:
    full = frame_input()
    prefix = replace(
        full, reference_price_data=reference_data(include_future=False)
    )
    before = pipeline().run(prefix)
    after = pipeline().run(full)
    assert tuple(
        item.to_dict() for item in after.frame_bundles[: len(before.frame_bundles)]
    ) == tuple(item.to_dict() for item in before.frame_bundles)


def test_future_zone_score_selection_event_and_frozen_box_do_not_backfill() -> None:
    prefix, extended = _appended_lifecycle_inputs()
    value = _single_context_pipeline()
    old = value.run(prefix).frame_bundles[0]
    new = value.run(extended).frame_bundles[0]
    assert new.resonance_frame.to_dict() == old.resonance_frame.to_dict()
    assert new.score_frame.to_dict() == old.score_frame.to_dict()
    assert new.selection_frame.to_dict() == old.selection_frame.to_dict()
    assert [
        item.to_dict() for item in new.selection_frame.emitted_events
    ] == [item.to_dict() for item in old.selection_frame.emitted_events]


def test_future_evidence_zone_contribution_and_rank_preserve_old_selection() -> None:
    future_subject_id = "future-ranked-upper"
    subjects = _pair_subjects() + (
        subject(
            future_subject_id,
            BoundarySide.UPPER,
            "104",
            "105",
            confirm_time=T2,
        ),
    )
    value, source, complete = _custom_core(
        subjects, (bar(-1), bar(0), bar(1), bar(2))
    )
    prefix = value.run(_truncate_source(source, T1))
    _assert_complete_prefix(prefix, complete)
    old = prefix.final_bundle
    assert future_subject_id not in {
        item.subject_id for item in old.resonance_frame.evidence
    }
    assert all(
        future_subject_id not in zone.member_subject_ids
        for zone in old.score_frame.zones
    )
    future = next(
        item for item in complete.frame_bundles if item.as_of_time == T2
    )
    assert future_subject_id in {
        item.subject_id for item in future.resonance_frame.evidence
    }
    assert any(
        future_subject_id in zone.member_subject_ids
        for zone in future.score_frame.zones
    )
    assert old.score_frame.to_dict() == (
        complete.frame_bundles[1].score_frame.to_dict()
    )
    assert old.selection_frame.to_dict() == (
        complete.frame_bundles[1].selection_frame.to_dict()
    )


def test_c007c_uses_nearest_qualified_zone_not_side_rank() -> None:
    first = pipeline().run(frame_input()).frame_bundles[0]
    decision = first.selection_frame.upper_decision
    selected = next(
        item
        for item in decision.zone_evaluations
        if item.zone_key_id == decision.selected_zone_key_id
    )
    rank_one = next(
        item for item in decision.zone_evaluations if item.side_rank == 1
    )
    assert selected.eligible and rank_one.eligible
    assert selected.side_rank == 2
    assert selected.distance < rank_one.distance


def test_origin_time_does_not_grant_end_to_end_visibility() -> None:
    base = base_subjects()[:3]
    future = subject(
        "future-origin-upper",
        side=base[0].boundary_side,
        low="140",
        high="141",
        confirm_time=T2,
    )
    bars = (bar(-1), bar(0), bar(1))
    history = lifecycle_history(base + (future,), bars)
    data = ResonanceFrameInput(
        history,
        (timeframe_history(history, H4_PRIMARY),),
        load_result(bars),
    )
    run = _single_context_pipeline().run(data)
    before = next(item for item in run.frame_bundles if item.as_of_time < T2)
    at_confirm = next(
        item for item in run.frame_bundles if item.as_of_time == T2
    )
    assert "future-origin-upper" not in {
        item.subject_id for item in before.resonance_frame.evidence
    }
    assert "future-origin-upper" in {
        item.subject_id for item in at_confirm.resonance_frame.evidence
    }


def test_reference_bar_is_invisible_until_available_time_end_to_end() -> None:
    source = frame_input()
    bars = list(source.reference_price_data.bars)
    delayed_time = bars[-1].available_time + timedelta(hours=1)
    bars[-1] = replace(bars[-1], available_time=delayed_time)
    delayed = replace(
        source,
        reference_price_data=load_result(
            tuple(bars), config=source.reference_price_data.source_config
        ),
    )
    default = pipeline().run(delayed).processing_times
    schedule = tuple(sorted({*default, bars[-1].end_time}))
    run = replay_msa_core_run(pipeline(), delayed, schedule)
    at_end = next(
        item
        for item in run.frame_bundles
        if item.as_of_time == bars[-1].end_time
    )
    assert at_end.resonance_frame.reference_price.canonical_bar != bars[-1]


def test_price_crossing_pair_change_and_freeze_only_apply_at_current_asof() -> None:
    run = pipeline().run(frame_input())
    replacement = next(
        item
        for item in run.frame_bundles
        if len(item.selection_frame.emitted_events) == 2
    )
    previous = run.frame_bundles[
        run.frame_bundles.index(replacement) - 1
    ]
    assert previous.selection_frame.active_box_snapshot is not None
    assert all(
        event.event_type.value != "FROZEN"
        for event in previous.selection_frame.emitted_events
    )
    assert all(
        event.event_confirm_time == replacement.as_of_time
        for event in replacement.selection_frame.emitted_events
    )


def test_pair_unavailable_freezes_once_and_later_absence_keeps_ledger() -> None:
    bars = (
        bar(-1),
        bar(0, high="111", low="90", close="100"),
        bar(1, high="113", low="90", close="112"),
        bar(2, high="111", low="90", close="100"),
    )
    value, source, run = _custom_core(
        _pair_subjects(), bars, break_buffer=Decimal("1")
    )
    unavailable_index = next(
        index
        for index, item in enumerate(run.frame_bundles)
        if item.selection_frame.emitted_events
        and item.selection_frame.emitted_events[0].event_reason
        is ActiveBoxEventReason.PAIR_UNAVAILABLE
    )
    previous = run.frame_bundles[
        unavailable_index - 1
    ].selection_frame.active_box_snapshot
    unavailable = run.frame_bundles[unavailable_index]
    event = unavailable.selection_frame.emitted_events[0]
    assert previous is not None
    assert unavailable.selection_frame.active_box_snapshot is None
    assert event.event_type is ActiveBoxEventType.FROZEN
    assert event.event_reason is ActiveBoxEventReason.PAIR_UNAVAILABLE
    assert event.resulting_box_snapshot.to_dict() == (
        freeze_active_box_snapshot(
            unavailable.score_frame, previous
        ).to_dict()
    )
    later = run.frame_bundles[unavailable_index + 1]
    assert later.selection_frame.active_box_snapshot is None
    assert later.selection_frame.emitted_events == ()
    through_freeze = value.run(
        _truncate_source(source, unavailable.as_of_time)
    )
    assert [
        item.to_dict() for item in through_freeze.active_box_history.events
    ] == [item.to_dict() for item in run.active_box_history.events]
    assert [
        item.to_dict()
        for item in through_freeze.active_box_history.frozen_boxes
    ] == [
        item.to_dict() for item in run.active_box_history.frozen_boxes
    ]


def test_pair_reappearance_starts_new_episode_without_mutating_frozen_box() -> None:
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
    _, _, run = _custom_core(
        subjects,
        (bar(-1), bar(0), bar(1), bar(2)),
        active_overrides={"minimum_quality_score": Decimal("0.28")},
    )
    unavailable_index = next(
        index
        for index, frame in enumerate(run.frame_bundles)
        if frame.selection_frame.emitted_events
        and frame.selection_frame.emitted_events[0].event_reason
        is ActiveBoxEventReason.PAIR_UNAVAILABLE
    )
    frozen_event = run.frame_bundles[
        unavailable_index
    ].selection_frame.emitted_events[0]
    recreated = next(
        frame
        for frame in run.frame_bundles[unavailable_index + 1 :]
        if frame.selection_frame.emitted_events
    )
    created_event = recreated.selection_frame.emitted_events[0]
    assert created_event.event_type is ActiveBoxEventType.CREATED
    assert created_event.event_reason is ActiveBoxEventReason.INITIAL_PAIR
    assert (
        recreated.selection_frame.active_box_snapshot.box_key_id
        != frozen_event.box_key_id
    )
    assert frozen_event.resulting_box_snapshot.to_dict() in [
        item.to_dict() for item in run.active_box_history.frozen_boxes
    ]


def test_retain_keeps_creation_projections_and_pair_change_reprojects_both() -> None:
    run = pipeline().run(frame_input())
    changed_frame = next(
        frame
        for frame in run.active_box_history.frames
        if len(frame.emitted_events) == 2
    )
    changed = changed_frame.active_box_snapshot
    changed_index = run.active_box_history.frames.index(changed_frame)
    retained = run.active_box_history.frames[
        changed_index + 1
    ].active_box_snapshot
    assert changed is not None and retained is not None
    assert retained.lower_projection == changed.lower_projection
    assert retained.upper_projection == changed.upper_projection
    assert changed.lower_projection.selection_confirm_time == changed.active_box.as_of_time
    assert changed.upper_projection.selection_confirm_time == changed.active_box.as_of_time


def test_pair_change_orders_freeze_create_and_preserves_old_frozen_payload() -> None:
    run = pipeline().run(frame_input())
    index = next(
        index
        for index, frame in enumerate(run.frame_bundles)
        if len(frame.selection_frame.emitted_events) == 2
    )
    previous = run.frame_bundles[
        index - 1
    ].selection_frame.active_box_snapshot
    changed = run.frame_bundles[index]
    frozen_event, created_event = changed.selection_frame.emitted_events
    assert previous is not None
    assert [
        frozen_event.event_type,
        created_event.event_type,
    ] == [ActiveBoxEventType.FROZEN, ActiveBoxEventType.CREATED]
    assert (
        frozen_event.event_reason
        is ActiveBoxEventReason.PAIR_CHANGED
    )
    assert (
        created_event.event_reason
        is ActiveBoxEventReason.PAIR_CHANGED
    )
    assert frozen_event.resulting_box_snapshot.to_dict() == (
        freeze_active_box_snapshot(
            changed.score_frame, previous
        ).to_dict()
    )
    current = changed.selection_frame.active_box_snapshot
    assert current is not None
    assert current.lower_projection.selection_confirm_time == changed.as_of_time
    assert current.upper_projection.selection_confirm_time == changed.as_of_time
    assert frozen_event.resulting_box_snapshot.to_dict() in [
        item.to_dict() for item in run.active_box_history.frozen_boxes
    ]


def test_extra_asof_preserves_complete_prefix_and_creates_one_bundle_per_time() -> None:
    value = pipeline()
    source = frame_input()
    batch = value.run(source)
    replayed = replay_msa_core_run(value, source, extra_schedule())
    assert replayed.frame_bundles[0].to_dict() == batch.frame_bundles[
        0
    ].to_dict()
    assert len(replayed.frame_bundles) == len(
        {item.as_of_time for item in replayed.frame_bundles}
    )
    assert tuple(
        item.as_of_time for item in replayed.frame_bundles
    ) == replayed.processing_times


def test_modifying_data_after_extra_asof_preserves_earlier_prefix() -> None:
    source_a = frame_input()
    bars = list(source_a.reference_price_data.bars)
    bars[-1] = replace(
        bars[-1],
        high=bars[-1].high + 10,
        close=bars[-1].close + 10,
    )
    source_b = replace(
        source_a,
        reference_price_data=load_result(
            tuple(bars), config=source_a.reference_price_data.source_config
        ),
    )
    schedule = extra_schedule()
    run_a = replay_msa_core_run(pipeline(), source_a, schedule)
    run_b = replay_msa_core_run(pipeline(), source_b, schedule)
    cutoff = bars[-1].available_time
    assert tuple(
        item.to_dict()
        for item in run_a.frame_bundles
        if item.as_of_time < cutoff
    ) == tuple(
        item.to_dict()
        for item in run_b.frame_bundles
        if item.as_of_time < cutoff
    )


def test_default_replay_stage_replay_and_context_permutation_are_exact() -> None:
    value = pipeline()
    source = frame_input()
    batch = value.run(source)
    replayed = replay_msa_core_run(value, source)
    permuted = value.run(frame_input(reverse_histories=True))
    assert replayed.to_dict() == batch.to_dict()
    assert permuted.to_dict() == batch.to_dict()
    assert tuple(
        item.score_frame.to_dict() for item in replayed.frame_bundles
    ) == tuple(item.to_dict() for item in replayed.score_history.frames)
    assert tuple(
        item.selection_frame.to_dict() for item in replayed.frame_bundles
    ) == tuple(item.to_dict() for item in replayed.active_box_history.frames)
