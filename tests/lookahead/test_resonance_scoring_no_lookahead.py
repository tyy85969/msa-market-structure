from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

from msa.domain import BoundarySide
from msa.research.resonance import ResonanceFrameInput, ResonanceScorer
from tests.research.resonance.fixtures import (
    H4_PRIMARY,
    START,
    T1,
    T2,
    T3,
    assembler,
    bar,
    custom_bundle,
    frame_input,
    load_result,
    subject,
)
from tests.research.resonance_scoring.fixtures import scoring_config, scorer, source_history


def test_future_frame_append_does_not_change_old_complete_score_payloads() -> None:
    source = source_history()
    full = scorer().build_batch(source)
    for source_frame, scored in zip(source.frames, full.frames):
        assert scorer().score_frame(source_frame).to_dict() == scored.to_dict()


def test_future_test_and_weakened_do_not_change_prior_tier_contribution_or_score() -> None:
    history = scorer().build_batch(source_history())
    start, tested, weakened = history.frames[:3]
    start_item = next(item for zone in start.zones for item in zone.contributions if item.subject_id == "upper-a-old")
    tested_item = next(item for zone in tested.zones for item in zone.contributions if item.subject_id == "upper-a-old")
    weakened_item = next(item for zone in weakened.zones for item in zone.contributions if item.subject_id == "upper-a-old")
    assert start_item.tier.value == "CANDIDATE"
    assert tested_item.tier.value == "CONFIRMED"
    assert start_item.to_dict() == next(
        item for zone in scorer().score_frame(source_history().frames[0]).zones for item in zone.contributions if item.subject_id == "upper-a-old"
    ).to_dict()
    assert tested_item.touch_factor == Decimal("1")
    assert weakened_item.touch_factor < tested_item.touch_factor


def test_future_broken_retired_and_flipped_do_not_change_past_zone() -> None:
    upper = subject("future-lifecycle", BoundarySide.UPPER, "110", "111")
    bars = (
        bar(-1),
        bar(0, high="113", low="110", close="112"),
        bar(1, high="110", low="108", close="109"),
    )
    engine, data = custom_bundle((upper,), bars, (H4_PRIMARY,), break_buffer=Decimal("1"))
    score_engine = ResonanceScorer(scoring_config(contexts=(H4_PRIMARY,)))
    before = score_engine.score_frame(engine.build_as_of(data, START))
    assert len(before.zones) == 1
    assert score_engine.score_frame(engine.build_as_of(data, START)).to_dict() == before.to_dict()
    assert score_engine.score_frame(engine.build_as_of(data, T1)).zones == ()
    assert score_engine.score_frame(engine.build_as_of(data, T2)).zones == ()


def test_future_flipped_changes_side_only_at_the_causal_frame() -> None:
    upper = subject("future-flip", BoundarySide.UPPER, "110", "111")
    bars = (
        bar(-1),
        bar(0, high="113", low="110", close="112"),
        bar(1, high="111", low="110", close="110"),
        bar(2, high="113", low="112", close="112"),
    )
    engine, data = custom_bundle(
        (upper,), bars, (H4_PRIMARY,), break_buffer=Decimal("1")
    )
    score_engine = ResonanceScorer(scoring_config(contexts=(H4_PRIMARY,)))
    before = score_engine.score_frame(engine.build_as_of(data, START))
    after = score_engine.score_frame(engine.build_as_of(data, T3))
    assert before.upper_zones and not before.lower_zones
    assert after.lower_zones and not after.upper_zones
    assert score_engine.score_frame(engine.build_as_of(data, START)).to_dict() == before.to_dict()


def test_future_price_changes_only_current_distance_selection_and_snapshot() -> None:
    history = scorer().build_batch(source_history())
    at_t2 = next(item for item in history.frames if item.as_of_time == T2)
    at_t3 = next(item for item in history.frames if item.as_of_time == T3)
    first = {item.member_subject_ids: item for item in at_t2.zones}
    second = {item.member_subject_ids: item for item in at_t3.zones}
    assert set(first) == set(second)
    for key in first:
        assert first[key].member_evidence_ids == second[key].member_evidence_ids
        assert first[key].zone_key_id == second[key].zone_key_id
        assert first[key].zone_snapshot_id != second[key].zone_snapshot_id


def test_bar_end_time_does_not_grant_future_reference_price() -> None:
    value = frame_input()
    bars = list(value.reference_price_data.bars)
    bars[-1] = replace(bars[-1], available_time=T3 + timedelta(hours=1))
    delayed = load_result(tuple(bars), config=value.reference_price_data.source_config)
    data = ResonanceFrameInput(value.lifecycle_history, value.timeframe_state_histories, delayed)
    source = assembler().build_as_of(data, T3)
    score = scorer().score_frame(source)
    assert source.reference_price.price == Decimal("102")
    assert all(zone.reference_price == Decimal("102") for zone in score.zones)


def test_origin_time_never_participates_in_freshness() -> None:
    frame = scorer().score_frame(source_history().frames[1])
    evidence = {item.evidence_id: item for item in frame.source_frame.evidence}
    for zone in frame.zones:
        for contribution in zone.contributions:
            upstream = evidence[contribution.evidence_id]
            delta = frame.as_of_time - upstream.state_confirm_time
            microseconds = (
                delta.days * 86_400_000_000
                + delta.seconds * 1_000_000
                + delta.microseconds
            )
            expected = Decimal(microseconds) / Decimal("1000000")
            assert contribution.age_seconds == expected
            assert upstream.boundary.origin_time != upstream.state_confirm_time


def test_modifying_future_evidence_does_not_change_past_complete_score() -> None:
    base = (subject("base", BoundarySide.UPPER, "110", "111"),)
    future_a = subject("future", BoundarySide.UPPER, "115", "116", confirm_time=T2)
    future_b = subject("future", BoundarySide.UPPER, "125", "126", confirm_time=T2)
    bars = (bar(-1), bar(0), bar(1))
    engine_a, data_a = custom_bundle(base + (future_a,), bars, (H4_PRIMARY,))
    engine_b, data_b = custom_bundle(base + (future_b,), bars, (H4_PRIMARY,))
    score_engine = ResonanceScorer(scoring_config(contexts=(H4_PRIMARY,)))
    assert score_engine.score_frame(engine_a.build_as_of(data_a, T1)).to_dict() == score_engine.score_frame(engine_b.build_as_of(data_b, T1)).to_dict()


def test_context_history_and_subject_input_permutations_do_not_change_output() -> None:
    normal = scorer().score_frame(assembler().build_as_of(frame_input(), T1))
    reversed_contexts = scorer().score_frame(assembler().build_as_of(frame_input(reverse_histories=True), T1))
    assert reversed_contexts.to_dict() == normal.to_dict()


def test_single_side_evidence_never_crosses_side_partition() -> None:
    frame = scorer().score_frame(assembler().build_as_of(frame_input(), T1))
    evidence_side = {item.evidence_id: item.boundary.boundary_side for item in frame.source_frame.evidence}
    assert all(all(evidence_side[item_id] is zone.side for item_id in zone.member_evidence_ids) for zone in frame.zones)


def test_c006b_unselected_old_evidence_still_strengthens_zone() -> None:
    frame = scorer().score_frame(assembler().build_as_of(frame_input(), T1))
    zone = next(item for item in frame.upper_zones if {"upper-a-old", "upper-z-new"}.issubset(item.member_subject_ids))
    assert len(zone.member_evidence_ids) == 2
