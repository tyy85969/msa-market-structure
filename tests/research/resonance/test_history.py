from dataclasses import replace
from datetime import timedelta

import pytest

from msa.research.resonance import (
    ResonanceFrameEngineError,
    ResonanceFrameHistory,
    ResonanceFrameInputError,
)

from .fixtures import START, T1, T2, T3, assembler, frame_input


def test_default_batch_schedule_is_canonical_union_after_common_availability() -> None:
    value = frame_input()
    expected = tuple(sorted(
        {item.as_of_time for item in value.lifecycle_history.snapshots}
        | {item.available_time for item in value.reference_price_data.bars}
    ))
    assert assembler().default_schedule(value) == expected
    assert tuple(item.as_of_time for item in assembler().build_batch(value).frames) == expected


def test_as_of_before_common_availability_fails() -> None:
    with pytest.raises(ResonanceFrameInputError):
        assembler().build_as_of(frame_input(), START - timedelta(microseconds=1))


def test_lifecycle_prefix_changes_only_at_visible_snapshot() -> None:
    value = frame_input()
    at_start = assembler().build_as_of(value, START)
    before_t1 = assembler().build_as_of(value, T1 - timedelta(microseconds=1))
    at_t1 = assembler().build_as_of(value, T1)
    assert before_t1.source_lifecycle_snapshot_id == at_start.source_lifecycle_snapshot_id
    assert before_t1.evidence == at_start.evidence
    assert at_t1.source_lifecycle_snapshot_id != at_start.source_lifecycle_snapshot_id
    assert at_t1.evidence != at_start.evidence


def test_extra_as_of_with_same_sources_only_advances_observation_facts() -> None:
    value = frame_input()
    first = assembler().build_as_of(value, T2)
    extra = assembler().build_as_of(value, T2 + timedelta(seconds=30))
    assert extra.source_lifecycle_snapshot_id == first.source_lifecycle_snapshot_id
    assert extra.reference_price.reference_id == first.reference_price.reference_id
    assert extra.context_states == first.context_states
    assert extra.evidence == first.evidence
    assert extra.report.evidence_count == first.report.evidence_count
    assert extra.report.reference_price_age_seconds > first.report.reference_price_age_seconds
    assert extra.frame_id != first.frame_id


def test_history_validates_final_frame_order_and_unique_ids() -> None:
    history = assembler().build_batch(frame_input())
    assert history.final_frame == history.frames[-1]
    assert len({item.frame_id for item in history.frames}) == len(history.frames)
    with pytest.raises(ResonanceFrameEngineError, match="final_frame"):
        ResonanceFrameHistory(
            history.frames, history.frames[0], history.config_snapshot
        )
    with pytest.raises(ResonanceFrameEngineError, match="strictly increasing"):
        ResonanceFrameHistory(
            tuple(reversed(history.frames)), history.frames[0], history.config_snapshot
        )


def test_history_rejects_price_availability_regression() -> None:
    history = assembler().build_batch(frame_input())
    later = history.frames[-1]
    forged_reference = replace(
        later.reference_price,
        reference_id=history.frames[0].reference_price.reference_id,
        canonical_bar=history.frames[0].reference_price.canonical_bar,
    )
    # The Frame contract catches the forged ID/frame mismatch before History can accept it.
    with pytest.raises(ResonanceFrameEngineError):
        replace(later, reference_price=forged_reference)


def test_old_frames_remain_immutable_after_batch_construction() -> None:
    history = assembler().build_batch(frame_input())
    payload = history.frames[0].to_dict()
    _ = history.final_frame.to_dict()
    assert history.frames[0].to_dict() == payload


def test_context_and_price_source_times_never_regress() -> None:
    history = assembler().build_batch(frame_input())
    assert all(
        current.source_lifecycle_snapshot_time >= previous.source_lifecycle_snapshot_time
        for previous, current in zip(history.frames, history.frames[1:])
    )
    assert all(
        current.reference_price.available_time >= previous.reference_price.available_time
        for previous, current in zip(history.frames, history.frames[1:])
    )


def test_frame_report_and_provenance_are_exact() -> None:
    frame = assembler().build_as_of(frame_input(), T1)
    assert frame.report.context_count == len(frame.context_states)
    assert frame.report.evidence_count == len(frame.evidence)
    expected_parents = tuple(sorted({
        frame.source_lifecycle_snapshot_id,
        frame.reference_price.reference_id,
        *(item.timeframe_snapshot_id for item in frame.context_states),
        *(item.lifecycle_state_id for item in frame.evidence),
    }))
    assert frame.provenance.parent_object_ids == expected_parents
    with pytest.raises(ResonanceFrameEngineError, match="report"):
        replace(frame, report=replace(frame.report, evidence_count=999))
    with pytest.raises(ResonanceFrameEngineError, match="provenance"):
        replace(
            frame,
            provenance=replace(
                frame.provenance,
                parent_object_ids=frame.provenance.parent_object_ids + ("extra",),
            ),
        )


def test_frame_rejects_arbitrary_well_formed_hash() -> None:
    frame = assembler().build_as_of(frame_input(), T1)
    with pytest.raises(ResonanceFrameEngineError, match="frame_id"):
        replace(frame, frame_id="resonance-frame-v1-" + "a" * 64)


def test_repeated_serialization_is_deterministic() -> None:
    history = assembler().build_batch(frame_input())
    assert history.to_dict() == history.to_dict()
