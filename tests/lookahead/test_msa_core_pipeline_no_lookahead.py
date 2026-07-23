from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

from msa.research.lifecycle import LifecycleHistory
from msa.research.msa_core import (
    MSACoreConfig,
    MSACorePipeline,
    replay_msa_core_run,
)
from msa.research.resonance import ResonanceFrameInput
from tests.research.active_box_contract.fixtures import config as active_config
from tests.research.msa_core.fixtures import (
    config as core_config,
    extra_schedule,
    pipeline,
)
from tests.research.resonance.fixtures import (
    H4_PRIMARY,
    T1,
    T2,
    bar,
    base_subjects,
    config as frame_config,
    frame_input,
    lifecycle_history,
    load_result,
    reference_data,
    subject,
    timeframe_history,
)
from tests.research.resonance_scoring.fixtures import scoring_config


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
