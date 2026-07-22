from datetime import timedelta

import pytest

from msa.research.resonance import (
    ResonanceFrameInputError,
    iter_replay_frames,
    replay_history,
)

from .fixtures import START, T1, T2, T3, assembler, frame_input


def test_default_batch_and_replay_are_full_payload_equivalent() -> None:
    engine = assembler()
    value = frame_input()
    batch = engine.build_batch(value)
    replay = replay_history(engine, value)
    assert replay.to_dict() == batch.to_dict()
    assert replay.final_frame.to_dict() == batch.final_frame.to_dict()


def test_explicit_schedule_requires_aware_strict_unique_times() -> None:
    engine = assembler()
    value = frame_input()
    with pytest.raises(ResonanceFrameInputError, match="timezone-aware"):
        replay_history(
            engine, value,
            (START.replace(tzinfo=None), T1, T2, T3),
        )
    with pytest.raises(ResonanceFrameInputError, match="strictly"):
        replay_history(engine, value, (START, T1, T1, T2, T3))
    with pytest.raises(ResonanceFrameInputError, match="strictly"):
        replay_history(engine, value, (START, T2, T1, T3))


def test_sparse_schedule_is_rejected() -> None:
    with pytest.raises(ResonanceFrameInputError, match="every default"):
        replay_history(assembler(), frame_input(), (START, T1, T3))


def test_schedule_cannot_precede_common_availability() -> None:
    value = frame_input()
    schedule = (
        START - timedelta(microseconds=1), START, T1, T2, T3
    )
    with pytest.raises(ResonanceFrameInputError, match="precede"):
        replay_history(assembler(), value, schedule)


def test_extra_as_of_schedule_is_valid_and_future_safe() -> None:
    value = frame_input()
    extra_time = T2 + timedelta(seconds=30)
    schedule = (START, T1, T2, extra_time, T3)
    replay = replay_history(assembler(), value, schedule)
    assert tuple(item.as_of_time for item in replay.frames) == schedule
    before = replay.frames[2]
    extra = replay.frames[3]
    assert extra.evidence == before.evidence
    assert extra.context_states == before.context_states
    assert extra.reference_price == before.reference_price


def test_iter_replay_frames_matches_history() -> None:
    engine = assembler()
    value = frame_input()
    assert tuple(iter_replay_frames(engine, value)) == replay_history(
        engine, value
    ).frames
