from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

from msa.domain import BoundarySide
from msa.research.swing import replay_events
from msa.research.swing.atr_reversal import AtrReversalDetector
from msa.research.swing.combined import STRUCTURE_FAMILY
from msa.research.swing.structure_break import (
    STRUCTURE_FAMILY as PIVOT_STRUCTURE_FAMILY,
)
from tests.research.swing.c003b_fixtures import (
    atr_combination_bars,
    atr_turn_bars,
    combined_detector,
)
from tests.research.swing.fixtures import load_result


def test_no_output_before_any_atr_seed() -> None:
    bars = atr_turn_bars()[:2]
    assert combined_detector().detect_batch(
        load_result(bars)
    ).candidates == ()


def test_atr_turns_without_structure_close_break_do_not_output() -> None:
    bars = atr_turn_bars()
    assert combined_detector().detect_batch(
        load_result(bars)
    ).candidates == ()


def test_close_break_after_atr_seeds_outputs_combined_candidate() -> None:
    bars = atr_combination_bars()
    candidate = combined_detector().detect_batch(load_result(bars)).candidates[0]
    assert candidate.boundary_side is BoundarySide.UPPER
    assert candidate.price_range.low == Decimal("15")
    assert candidate.origin_time == bars[3].timestamp


def test_wick_without_close_break_does_not_output() -> None:
    bars = atr_combination_bars(break_close="9")
    assert combined_detector().detect_batch(
        load_result(bars)
    ).candidates == ()


def test_break_buffer_applies_to_combination() -> None:
    bars = atr_combination_bars(break_close="7")
    assert combined_detector(break_buffer=Decimal("1")).detect_batch(
        load_result(bars)
    ).candidates
    assert combined_detector(break_buffer=Decimal("2")).detect_batch(
        load_result(bars)
    ).candidates == ()


def test_confirm_time_equals_break_prefix_maximum() -> None:
    bars = list(atr_combination_bars())
    bars[0] = replace(
        bars[0], available_time=bars[-1].available_time + timedelta(hours=3)
    )
    candidate = combined_detector().detect_batch(
        load_result(tuple(bars))
    ).candidates[0]
    assert candidate.confirm_time == bars[0].available_time


def test_output_identity_differs_from_plain_atr_seed() -> None:
    bars = atr_combination_bars()
    source = load_result(bars)
    combined = combined_detector().detect_batch(source).candidates[0]
    atr_seeds = AtrReversalDetector(
        combined_detector().config.seed_atr_config
    ).detect_batch(source).candidates
    assert combined.candidate_id not in {
        candidate.candidate_id for candidate in atr_seeds
    }
    assert combined.candidate_id.startswith("swing-atr-structure-v1-")


def test_family_is_distinct_from_plain_atr_and_pivot_structure() -> None:
    candidate = combined_detector().detect_batch(
        load_result(atr_combination_bars())
    ).candidates[0]
    assert candidate.structure_family == STRUCTURE_FAMILY
    assert candidate.structure_family != PIVOT_STRUCTURE_FAMILY
    assert candidate.structure_family != AtrReversalDetector(
        combined_detector().config.seed_atr_config
    ).detect_batch(load_result(atr_turn_bars())).candidates[0].structure_family


def test_provenance_references_two_atr_seeds_and_break_bar() -> None:
    candidate = combined_detector().detect_batch(
        load_result(atr_combination_bars())
    ).candidates[0]
    parents = candidate.provenance.parent_object_ids
    assert sum(parent.startswith("swing-atr-v1-") for parent in parents) == 2
    assert sum(parent.startswith("bar:v1:") for parent in parents) == 1
    assert candidate.provenance.source_module.endswith("combined")


def test_batch_iter_events_and_replay_are_fully_equal() -> None:
    source = load_result(atr_combination_bars())
    detector = combined_detector()
    assert replay_events(detector, source) == tuple(detector.iter_events(source))


def test_future_append_does_not_rewrite_combined_candidate() -> None:
    prefix = atr_combination_bars()
    original = combined_detector().detect_batch(
        load_result(prefix)
    ).candidates[0]
    future = replace(
        prefix[-1],
        timestamp=prefix[-1].timestamp + timedelta(hours=1),
        end_time=prefix[-1].end_time + timedelta(hours=1),
        available_time=prefix[-1].available_time + timedelta(hours=1),
        open=Decimal("20"),
        high=Decimal("22"),
        low=Decimal("18"),
        close=Decimal("21"),
    )
    later = combined_detector().detect_batch(
        load_result(prefix + (future,))
    ).candidates
    assert original in later


def test_as_of_before_break_bar_availability_has_no_output() -> None:
    bars = list(atr_combination_bars())
    bars[-1] = replace(
        bars[-1], available_time=bars[-1].available_time + timedelta(minutes=17)
    )
    source = load_result(tuple(bars))
    before = bars[-1].available_time - timedelta(microseconds=1)
    assert combined_detector().detect_as_of(source, before).candidates == ()
    assert combined_detector().detect_as_of(
        source, bars[-1].available_time
    ).candidates
