from dataclasses import FrozenInstanceError, replace
from datetime import timedelta
from decimal import Decimal

import pytest

from msa.domain import (
    BoundarySide,
    ConfirmationStatus,
    LifecycleState,
    MarketRole,
    PriceRange,
    StructureSourceType,
)
from msa.research.swing import SwingDetector, SwingInputError
from msa.research.swing.atr_reversal import (
    SAME_BAR_POLICY,
    STRUCTURE_FAMILY,
    _atr_values,
    _true_ranges,
)
from tests.research.swing.c003b_fixtures import (
    atr_config,
    atr_detector,
    atr_turn_bars,
    ohlc_bar,
)
from tests.research.swing.fixtures import load_result


def test_true_range_first_bar_is_high_minus_low() -> None:
    bars = (ohlc_bar(0, open="10", high="15", low="8", close="12"),)
    assert _true_ranges(bars) == (Decimal("7"),)


def test_true_range_includes_gap_from_previous_close() -> None:
    bars = (
        ohlc_bar(0, open="10", high="11", low="9", close="10"),
        ohlc_bar(1, open="20", high="21", low="19", close="20"),
    )
    assert _true_ranges(bars)[1] == Decimal("11")


def test_sma_atr_uses_exact_decimal_mean() -> None:
    assert _atr_values(
        (Decimal("1"), Decimal("2"), Decimal("4")), 3
    ) == (None, None, Decimal("7") / Decimal("3"))


def test_warmup_before_full_atr_window_emits_nothing() -> None:
    bars = atr_turn_bars()[:2]
    result = atr_detector(atr_period=3).detect_batch(load_result(bars))
    assert result.candidates == ()
    assert result.report.leading_incomplete_count == 2


def test_unknown_to_up_eventually_confirms_upper() -> None:
    bars = (
        ohlc_bar(0, open="10", high="11", low="9", close="10"),
        ohlc_bar(1, open="11", high="12", low="10", close="11"),
        ohlc_bar(2, open="9", high="11", low="8", close="9"),
    )
    candidate = atr_detector().detect_batch(load_result(bars)).candidates[0]
    assert candidate.boundary_side is BoundarySide.UPPER


def test_unknown_to_down_eventually_confirms_lower() -> None:
    bars = atr_turn_bars()[:3]
    candidate = atr_detector().detect_batch(load_result(bars)).candidates[0]
    assert candidate.boundary_side is BoundarySide.LOWER


def test_equal_close_keeps_unknown_and_emits_nothing() -> None:
    bars = tuple(
        ohlc_bar(
            index,
            open="10",
            high="11",
            low="9",
            close="10",
        )
        for index in range(4)
    )
    result = atr_detector().detect_batch(load_result(bars))
    assert result.candidates == ()
    assert any("UNKNOWN" in warning for warning in result.report.warnings)


def test_uptrend_updates_high_extreme_before_later_reversal() -> None:
    bars = (
        ohlc_bar(0, open="10", high="11", low="9", close="10"),
        ohlc_bar(1, open="11", high="12", low="10", close="11"),
        ohlc_bar(2, open="14", high="16", low="13", close="15"),
        ohlc_bar(3, open="12", high="14", low="10", close="11"),
    )
    candidate = atr_detector().detect_batch(load_result(bars)).candidates[0]
    assert candidate.price_range == PriceRange(Decimal("16"), Decimal("16"))
    assert candidate.origin_time == bars[2].timestamp


def test_downtrend_updates_low_extreme_before_later_reversal() -> None:
    bars = (
        ohlc_bar(0, open="10", high="11", low="9", close="10"),
        ohlc_bar(1, open="9", high="10", low="8", close="9"),
        ohlc_bar(2, open="7", high="8", low="5", close="6"),
        ohlc_bar(3, open="9", high="11", low="7", close="10"),
    )
    candidate = atr_detector().detect_batch(load_result(bars)).candidates[0]
    assert candidate.price_range == PriceRange(Decimal("5"), Decimal("5"))
    assert candidate.origin_time == bars[2].timestamp


def test_exact_reversal_threshold_confirms() -> None:
    bars = (
        ohlc_bar(0, open="10", high="11", low="9", close="10"),
        ohlc_bar(1, open="11", high="12", low="10", close="11"),
        ohlc_bar(2, open="10", high="12", low="9", close="10"),
    )
    candidate = atr_detector().detect_batch(load_result(bars)).candidates[0]
    assert candidate.boundary_side is BoundarySide.UPPER
    assert candidate.price_range.low == Decimal("12")


def test_below_reversal_threshold_does_not_confirm() -> None:
    bars = (
        ohlc_bar(0, open="10", high="11", low="9", close="10"),
        ohlc_bar(1, open="11", high="12", low="10", close="11"),
        ohlc_bar(2, open="12", high="14", low="11", close="13"),
    )
    assert atr_detector().detect_batch(load_result(bars)).candidates == ()


def test_same_bar_policy_checks_pre_bar_extreme_before_update() -> None:
    bars = (
        ohlc_bar(0, open="10", high="11", low="9", close="10"),
        ohlc_bar(1, open="11", high="12", low="10", close="11"),
        ohlc_bar(2, open="17", high="20", low="15", close="18"),
    )
    result = atr_detector().detect_batch(load_result(bars))
    assert result.candidates == ()
    assert any(SAME_BAR_POLICY in item for item in result.report.assumptions)


def test_upper_mapping_is_confirmed_resistance_swing() -> None:
    upper = atr_detector().detect_batch(load_result(atr_turn_bars())).candidates[1]
    assert upper.source_type is StructureSourceType.SWING
    assert upper.boundary_side is BoundarySide.UPPER
    assert upper.market_role is MarketRole.RESISTANCE
    assert upper.confirmation_status is ConfirmationStatus.CONFIRMED
    assert upper.lifecycle_state is LifecycleState.CONFIRMED
    assert upper.structure_family == STRUCTURE_FAMILY


def test_lower_mapping_is_confirmed_support_swing() -> None:
    lower = atr_detector().detect_batch(load_result(atr_turn_bars())).candidates[0]
    assert lower.source_type is StructureSourceType.SWING
    assert lower.boundary_side is BoundarySide.LOWER
    assert lower.market_role is MarketRole.SUPPORT
    assert lower.break_time is None
    assert lower.break_confirm_time is None


def test_confirm_time_uses_prefix_maximum_availability() -> None:
    bars = list(atr_turn_bars()[:3])
    bars[0] = replace(
        bars[0], available_time=bars[2].available_time + timedelta(hours=4)
    )
    candidate = atr_detector().detect_batch(load_result(tuple(bars))).candidates[0]
    assert candidate.confirm_time == bars[0].available_time


def test_delayed_early_bar_blocks_as_of_causal_prefix() -> None:
    bars = list(atr_turn_bars())
    bars[0] = replace(
        bars[0], available_time=bars[-1].available_time + timedelta(hours=1)
    )
    source = load_result(tuple(bars))
    result = atr_detector().detect_as_of(source, bars[-1].available_time)
    assert result.candidates == ()
    assert result.report.input_bar_count == 0


def test_incomplete_bar_blocks_as_of_but_batch_rejects() -> None:
    bars = list(atr_turn_bars())
    bars[2] = replace(bars[2], is_complete=False)
    source = load_result(tuple(bars))
    as_of = atr_detector().detect_as_of(source, bars[-1].available_time)
    assert as_of.report.input_bar_count == 2
    with pytest.raises(SwingInputError, match="incomplete"):
        atr_detector().detect_batch(source)


def test_future_append_does_not_rewrite_old_candidate() -> None:
    prefix = atr_turn_bars()[:3]
    original = atr_detector().detect_batch(load_result(prefix)).candidates[0]
    extended = prefix + (
        ohlc_bar(3, open="20", high="25", low="18", close="24"),
    )
    later = atr_detector().detect_batch(load_result(extended)).candidates
    assert original in later


def test_same_input_produces_same_id_and_config_change_changes_it() -> None:
    source = load_result(atr_turn_bars()[:3])
    first = atr_detector().detect_batch(source).candidates[0]
    second = atr_detector().detect_batch(source).candidates[0]
    changed = atr_detector(reversal_multiplier=Decimal("0.5")).detect_batch(
        source
    ).candidates[0]
    assert first.candidate_id == second.candidate_id
    assert first.candidate_id != changed.candidate_id


def test_candidate_provenance_contains_atr_window_and_confirmation_bar() -> None:
    candidate = atr_detector().detect_batch(
        load_result(atr_turn_bars()[:3])
    ).candidates[0]
    assert candidate.provenance.source_module.endswith("atr_reversal")
    assert len(candidate.provenance.parent_object_ids) >= 2
    assert any("atr_value=" in note for note in candidate.provenance.notes)
    assert any(
        "confirmation_bar_key=" in note for note in candidate.provenance.notes
    )


def test_config_and_detector_are_immutable_protocol_values() -> None:
    config = atr_config()
    assert isinstance(atr_detector(), SwingDetector)
    with pytest.raises(FrozenInstanceError):
        config.atr_period = 3  # type: ignore[misc]
