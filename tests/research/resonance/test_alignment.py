from dataclasses import replace

import pytest

from msa.domain import BoundarySide
from msa.research.resonance import (
    ResonanceFrameInput,
    ResonanceFrameInputError,
)

from .fixtures import (
    H4_PRIMARY,
    H12_MACRO,
    START,
    T1,
    assembler,
    bar,
    base_subjects,
    frame_input,
    lifecycle_history,
    subject,
    timeframe_history,
)


def test_one_and_multiple_context_inputs_are_valid() -> None:
    multi = frame_input()
    assert len(assembler().build_as_of(multi, START).context_states) == 2
    history = lifecycle_history()
    one = ResonanceFrameInput(
        history,
        (timeframe_history(history, H4_PRIMARY),),
        multi.reference_price_data,
    )
    assert len(assembler(contexts=(H4_PRIMARY,)).build_as_of(one, START).context_states) == 1


def test_history_input_reversal_does_not_change_frame_payload() -> None:
    normal = assembler().build_batch(frame_input()).to_dict()
    reversed_value = assembler().build_batch(
        frame_input(reverse_histories=True)
    ).to_dict()
    assert reversed_value == normal


def test_missing_and_duplicate_context_histories_are_rejected() -> None:
    value = frame_input()
    missing = ResonanceFrameInput(
        value.lifecycle_history,
        value.timeframe_state_histories[:1],
        value.reference_price_data,
    )
    with pytest.raises(ResonanceFrameInputError, match="count"):
        assembler().build_as_of(missing, START)
    duplicate = ResonanceFrameInput(
        value.lifecycle_history,
        (value.timeframe_state_histories[0], value.timeframe_state_histories[0]),
        value.reference_price_data,
    )
    with pytest.raises(ResonanceFrameInputError, match="duplicate"):
        assembler().build_as_of(duplicate, START)


def test_context_scale_or_timeframe_mismatch_is_rejected() -> None:
    value = frame_input()
    only_h4 = ResonanceFrameInput(
        value.lifecycle_history,
        (value.timeframe_state_histories[0],),
        value.reference_price_data,
    )
    with pytest.raises(ResonanceFrameInputError, match="timeframe/scale"):
        assembler(contexts=(H12_MACRO,)).build_as_of(only_h4, START)


def test_lifecycle_source_id_mismatch_fails_closed() -> None:
    value = frame_input()
    alternate = lifecycle_history(
        base_subjects()
        + (subject("alternate", BoundarySide.UPPER, "140", "141"),)
    )
    mismatched = ResonanceFrameInput(
        value.lifecycle_history,
        (
            timeframe_history(alternate, H4_PRIMARY),
            value.timeframe_state_histories[1],
        ),
        value.reference_price_data,
    )
    with pytest.raises(ResonanceFrameInputError, match="aligned"):
        assembler().build_as_of(mismatched, T1)


def test_missing_exact_as_of_alignment_fails_without_older_fallback() -> None:
    value = frame_input()
    history = value.timeframe_state_histories[0]
    truncated = replace(
        history,
        snapshots=history.snapshots[:1],
        final_snapshot=history.snapshots[0],
        events=history.snapshots[0].events,
    )
    mismatched = ResonanceFrameInput(
        value.lifecycle_history,
        (truncated, value.timeframe_state_histories[1]),
        value.reference_price_data,
    )
    with pytest.raises(ResonanceFrameInputError, match="aligned"):
        assembler().build_as_of(mismatched, T1)


def test_non_config_lifecycle_context_is_excluded_from_structural_payload() -> None:
    base = assembler().build_as_of(frame_input(), T1)
    extra = assembler().build_as_of(frame_input(include_extra=True), T1)
    assert [item.subject_id for item in extra.evidence] == [
        item.subject_id for item in base.evidence
    ]
    assert [item.context for item in extra.context_states] == [
        item.context for item in base.context_states
    ]


def test_inputs_are_not_mutated() -> None:
    value = frame_input()
    before = value.to_dict()
    assembler().build_batch(value)
    assert value.to_dict() == before


def test_processing_time_must_be_aware() -> None:
    with pytest.raises(ResonanceFrameInputError, match="timezone-aware"):
        assembler().build_as_of(frame_input(), START.replace(tzinfo=None))
