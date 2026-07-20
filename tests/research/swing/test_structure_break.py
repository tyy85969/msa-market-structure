from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

import pytest

from msa.domain import (
    BoundarySide,
    ConfirmationStatus,
    LifecycleState,
    MarketRole,
    StructureSourceType,
)
from msa.research.swing import SwingDetector
from msa.research.swing.structure_break import STRUCTURE_FAMILY
from tests.research.swing.c003b_fixtures import (
    pivot_lower_break_bars,
    pivot_replacement_bars,
    pivot_upper_break_bars,
    structure_detector,
)
from tests.research.swing.fixtures import load_result


def test_seed_origin_time_does_not_make_structure_candidate_visible() -> None:
    bars = pivot_upper_break_bars()
    source = load_result(bars)
    result = structure_detector().detect_as_of(source, bars[3].available_time)
    assert result.candidates == ()


def test_no_opposing_reference_produces_no_output() -> None:
    bars = pivot_upper_break_bars()[2:]
    shifted = tuple(
        replace(bar, timestamp=bars[0].timestamp + index * timedelta(hours=1),
                end_time=bars[0].timestamp + (index + 1) * timedelta(hours=1),
                available_time=bars[0].timestamp + (index + 1) * timedelta(hours=1))
        for index, bar in enumerate(bars)
    )
    assert structure_detector().detect_batch(
        load_result(shifted)
    ).candidates == ()


def test_wick_cross_without_close_does_not_confirm() -> None:
    bars = pivot_upper_break_bars(break_close="6")
    assert structure_detector().detect_batch(
        load_result(bars)
    ).candidates == ()


def test_close_break_confirms_upper_seed() -> None:
    bars = pivot_upper_break_bars()
    candidate = structure_detector().detect_batch(load_result(bars)).candidates[0]
    assert candidate.boundary_side is BoundarySide.UPPER
    assert candidate.price_range.low == Decimal("20")
    assert candidate.origin_time == bars[3].timestamp


def test_break_buffer_is_applied_exactly() -> None:
    bars = pivot_upper_break_bars(break_close="4")
    assert structure_detector(break_buffer=Decimal("1")).detect_batch(
        load_result(bars)
    ).candidates
    assert structure_detector(break_buffer=Decimal("2")).detect_batch(
        load_result(bars)
    ).candidates == ()


def test_latest_confirmed_pending_replaces_older_upper() -> None:
    bars = pivot_replacement_bars()
    candidate = structure_detector().detect_batch(load_result(bars)).candidates[0]
    assert candidate.origin_time == bars[5].timestamp
    assert candidate.price_range.low == Decimal("22")


def test_upper_confirms_below_earlier_lower_reference() -> None:
    candidate = structure_detector().detect_batch(
        load_result(pivot_upper_break_bars())
    ).candidates[0]
    assert candidate.boundary_side is BoundarySide.UPPER
    assert candidate.market_role is MarketRole.RESISTANCE


def test_lower_confirms_above_earlier_upper_reference() -> None:
    bars = pivot_lower_break_bars()
    candidate = structure_detector().detect_batch(load_result(bars)).candidates[0]
    assert candidate.boundary_side is BoundarySide.LOWER
    assert candidate.market_role is MarketRole.SUPPORT
    assert candidate.price_range.low == Decimal("4")


def test_confirm_time_is_not_earlier_than_seeds_or_break_prefix() -> None:
    bars = list(pivot_upper_break_bars())
    bars[0] = replace(
        bars[0], available_time=bars[-1].available_time + timedelta(hours=4)
    )
    source = load_result(tuple(bars))
    candidate = structure_detector().detect_batch(source).candidates[0]
    assert candidate.confirm_time == bars[0].available_time


def test_break_bar_inside_seed_confirmation_window_cannot_confirm() -> None:
    bars = pivot_upper_break_bars()[:5]
    assert structure_detector().detect_batch(
        load_result(bars)
    ).candidates == ()


def test_provenance_contains_both_seed_ids_and_break_bar() -> None:
    candidate = structure_detector().detect_batch(
        load_result(pivot_upper_break_bars())
    ).candidates[0]
    parents = candidate.provenance.parent_object_ids
    assert len(parents) == 3
    assert sum(parent.startswith("swing-pivot-v1-") for parent in parents) == 2
    assert sum(parent.startswith("bar:v1:") for parent in parents) == 1
    assert any("break_close=" in note for note in candidate.provenance.notes)


def test_output_mapping_and_family_are_distinct_from_seed() -> None:
    candidate = structure_detector().detect_batch(
        load_result(pivot_upper_break_bars())
    ).candidates[0]
    assert candidate.source_type is StructureSourceType.SWING
    assert candidate.confirmation_status is ConfirmationStatus.CONFIRMED
    assert candidate.lifecycle_state is LifecycleState.CONFIRMED
    assert candidate.structure_family == STRUCTURE_FAMILY
    assert candidate.candidate_id.startswith("swing-pivot-structure-v1-")
    assert candidate.break_time is None
    assert candidate.break_confirm_time is None


def test_future_append_does_not_change_existing_structure_candidate() -> None:
    prefix = pivot_upper_break_bars()
    original = structure_detector().detect_batch(
        load_result(prefix)
    ).candidates[0]
    future = replace(
        prefix[-1],
        timestamp=prefix[-1].timestamp + timedelta(hours=1),
        end_time=prefix[-1].end_time + timedelta(hours=1),
        available_time=prefix[-1].available_time + timedelta(hours=1),
        high=Decimal("30"),
        open=Decimal("20"),
        close=Decimal("20"),
    )
    later = structure_detector().detect_batch(
        load_result(prefix + (future,))
    ).candidates
    assert original in later


def test_detector_implements_protocol_and_report_is_explainable() -> None:
    detector = structure_detector()
    result = detector.detect_batch(load_result(pivot_upper_break_bars()))
    assert isinstance(detector, SwingDetector)
    assert result.report.confirmed_high_count == 1
    assert any("close" in item for item in result.report.assumptions)


def test_same_input_is_deterministic_and_buffer_changes_id() -> None:
    source = load_result(pivot_upper_break_bars())
    first = structure_detector().detect_batch(source).candidates[0]
    second = structure_detector().detect_batch(source).candidates[0]
    changed = structure_detector(break_buffer=Decimal("1")).detect_batch(
        source
    ).candidates[0]
    assert first.candidate_id == second.candidate_id
    assert first.candidate_id != changed.candidate_id
