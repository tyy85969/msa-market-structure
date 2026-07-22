from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

import pytest

from msa.data import DataQualityIssue, IssueSeverity, Timeframe
from msa.research.resonance import ResonanceFrameInput, ResonanceFrameInputError

from .fixtures import START, T1, T2, T3, T4, assembler, frame_input, load_result


def test_reference_price_uses_exact_decimal_close() -> None:
    frame = assembler().build_as_of(frame_input(), T1)
    assert frame.reference_price.price == Decimal("101")
    assert isinstance(frame.reference_price.price, Decimal)


def test_available_time_not_end_time_grants_visibility() -> None:
    value = frame_input()
    bars = list(value.reference_price_data.bars)
    bars[-1] = replace(bars[-1], available_time=T4)
    delayed = load_result(
        tuple(bars), config=value.reference_price_data.source_config
    )
    data = ResonanceFrameInput(
        value.lifecycle_history, value.timeframe_state_histories, delayed
    )
    before = assembler().build_as_of(data, T3)
    at_available = assembler().build_as_of(data, T4)
    assert bars[-1].end_time == T3
    assert before.reference_price.price == Decimal("102")
    assert at_available.reference_price.price == Decimal("103")


def test_future_reference_bar_does_not_appear_early() -> None:
    value = frame_input()
    before = assembler().build_as_of(value, T2)
    after = assembler().build_as_of(value, T3)
    assert before.reference_price.price == Decimal("102")
    assert after.reference_price.price == Decimal("103")


def test_price_only_update_creates_new_frame_without_evidence_change() -> None:
    history = assembler().build_batch(frame_input())
    at_t2 = next(item for item in history.frames if item.as_of_time == T2)
    at_t3 = next(item for item in history.frames if item.as_of_time == T3)
    assert at_t3.frame_id != at_t2.frame_id
    assert at_t3.reference_price.reference_id != at_t2.reference_price.reference_id
    assert at_t3.evidence == at_t2.evidence
    assert at_t3.context_states == at_t2.context_states


def test_between_price_availability_times_uses_previous_bar() -> None:
    frame = assembler().build_as_of(frame_input(), T2 + timedelta(minutes=30))
    assert frame.reference_price.price == Decimal("102")
    assert frame.reference_price.available_time == T2


def test_reference_identity_is_deterministic_and_sensitive_to_causal_bar() -> None:
    value = frame_input()
    first = assembler().build_as_of(value, T2).reference_price
    second = assembler().build_as_of(value, T2).reference_price
    future = assembler().build_as_of(value, T3).reference_price
    assert first == second
    assert first.reference_id == second.reference_id
    assert future.reference_id != first.reference_id


def test_reference_price_age_is_exact() -> None:
    frame = assembler().build_as_of(frame_input(), T2 + timedelta(seconds=30))
    assert frame.report.reference_price_age_seconds == Decimal("30.0")


def test_incomplete_reference_bar_is_rejected() -> None:
    value = frame_input()
    bars = list(value.reference_price_data.bars)
    bars[-1] = replace(bars[-1], is_complete=False)
    incomplete = replace(value.reference_price_data, bars=tuple(bars))
    with pytest.raises(ResonanceFrameInputError, match="completed"):
        ResonanceFrameInput(
            value.lifecycle_history, value.timeframe_state_histories, incomplete
        )


def test_reference_load_result_errors_are_rejected() -> None:
    value = frame_input()
    issue = DataQualityIssue(
        "fixture_error", IssueSeverity.ERROR, 1, "close", "bad", "fixture"
    )
    report = replace(value.reference_price_data.quality_report, errors=(issue,))
    bad = replace(value.reference_price_data, quality_report=report)
    with pytest.raises(ResonanceFrameInputError, match="error-free"):
        ResonanceFrameInput(
            value.lifecycle_history, value.timeframe_state_histories, bad
        )


def test_reference_symbol_and_timeframe_mismatch_are_rejected() -> None:
    value = frame_input()
    bars = list(value.reference_price_data.bars)
    bars[0] = replace(bars[0], symbol="OTHER")
    bad_symbol = replace(value.reference_price_data, bars=tuple(bars))
    with pytest.raises(ResonanceFrameInputError, match="symbol/timeframe"):
        assembler().build_as_of(
            ResonanceFrameInput(
                value.lifecycle_history, value.timeframe_state_histories, bad_symbol
            ),
            START,
        )
    wrong_config = replace(
        value.reference_price_data.source_config, timeframe=Timeframe.H2
    )
    bad_timeframe = replace(value.reference_price_data, source_config=wrong_config)
    with pytest.raises(ResonanceFrameInputError, match="source config"):
        assembler().build_as_of(
            ResonanceFrameInput(
                value.lifecycle_history,
                value.timeframe_state_histories,
                bad_timeframe,
            ),
            START,
        )
