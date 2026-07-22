from dataclasses import replace
from decimal import Decimal

from msa.domain import BoundarySide, LifecycleState
from msa.research.lifecycle import LifecycleHistory
from msa.research.resonance import ResonanceFrameInput

from tests.research.resonance.fixtures import (
    H4_PRIMARY,
    PRIMARY,
    START,
    T1,
    T2,
    T3,
    assembler,
    bar,
    base_subjects,
    custom_bundle,
    frame_input,
    config,
    lifecycle_history,
    load_result,
    subject,
    timeframe_history,
)


def test_future_lifecycle_append_does_not_change_old_full_frame_payload() -> None:
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
        + tuple(item for item in extended_history.snapshots if item.as_of_time > T1),
        final_snapshot=extended_history.final_snapshot,
    )
    prefix_data = ResonanceFrameInput(
        prefix_history,
        (timeframe_history(prefix_history, H4_PRIMARY),),
        load_result(prefix_bars),
    )
    future_data = ResonanceFrameInput(
        appended_history,
        (timeframe_history(appended_history, H4_PRIMARY),),
        load_result(future_bars),
    )
    engine = assembler(contexts=(H4_PRIMARY,))
    assert engine.build_as_of(future_data, T1).to_dict() == engine.build_as_of(
        prefix_data, T1
    ).to_dict()


def test_future_test_does_not_promote_fresh_evidence_early() -> None:
    value = frame_input()
    before = assembler().build_as_of(value, START)
    at_test = assembler().build_as_of(value, T1)
    before_item = next(item for item in before.evidence if item.subject_id == "upper-a-old")
    at_test_item = next(item for item in at_test.evidence if item.subject_id == "upper-a-old")
    assert before_item.lifecycle_state is LifecycleState.FRESH
    assert before_item.to_dict()["tier"] == "CANDIDATE"
    assert at_test_item.lifecycle_state is LifecycleState.TESTED
    assert at_test_item.to_dict()["tier"] == "CONFIRMED"


def test_future_broken_does_not_remove_evidence_early() -> None:
    upper = subject("break-upper", BoundarySide.UPPER, "110", "111")
    bars = (bar(-1), bar(0, high="113", low="110", close="112"))
    engine, data = custom_bundle(
        (upper,), bars, (H4_PRIMARY,), break_buffer=Decimal("1")
    )
    before = engine.build_as_of(data, START)
    at_break = engine.build_as_of(data, T1)
    assert [item.subject_id for item in before.evidence] == ["break-upper"]
    assert at_break.evidence == ()
    assert at_break.excluded_broken_subject_ids == ("break-upper",)


def test_future_flipped_does_not_change_side_or_role_early() -> None:
    upper = subject("flip-upper", BoundarySide.UPPER, "110", "111")
    bars = (
        bar(-1),
        bar(0, high="113", low="110", close="112"),
        bar(1, high="111", low="110", close="110"),
        bar(2, high="113", low="112", close="112"),
    )
    engine, data = custom_bundle(
        (upper,), bars, (H4_PRIMARY,), break_buffer=Decimal("1")
    )
    before = engine.build_as_of(data, START)
    after = engine.build_as_of(data, T3)
    assert before.evidence[0].boundary.boundary_side is BoundarySide.UPPER
    assert after.evidence[0].boundary.boundary_side is BoundarySide.LOWER
    assert after.evidence[0].lifecycle_state is LifecycleState.FLIPPED


def test_future_retired_does_not_remove_history_early() -> None:
    upper = subject("retire-upper", BoundarySide.UPPER, "110", "111")
    bars = (
        bar(-1),
        bar(0, high="113", low="110", close="112"),
        bar(1, high="110", low="108", close="109"),
    )
    engine, data = custom_bundle(
        (upper,), bars, (H4_PRIMARY,), break_buffer=Decimal("1")
    )
    before = engine.build_as_of(data, START)
    after = engine.build_as_of(data, T2)
    assert before.evidence[0].subject_id == "retire-upper"
    assert after.evidence == ()
    assert after.excluded_retired_subject_ids == ("retire-upper",)


def test_future_direction_subjects_do_not_change_past_full_frame() -> None:
    base = base_subjects()[:3]
    futures = (
        subject(
            "future-upper", BoundarySide.UPPER, "115", "116", confirm_time=T2
        ),
        subject(
            "future-lower", BoundarySide.LOWER, "95", "96", confirm_time=T2
        ),
    )
    bars = (
        bar(-1),
        bar(0, high="105", low="95", close="100"),
        bar(1, high="105", low="95", close="100"),
    )
    base_history = lifecycle_history(base, bars)
    extended_history = lifecycle_history(base + futures, bars)
    appended_history = LifecycleHistory(
        events=extended_history.events,
        snapshots=tuple(
            item for item in base_history.snapshots if item.as_of_time < T2
        )
        + tuple(
            item for item in extended_history.snapshots if item.as_of_time >= T2
        ),
        final_snapshot=extended_history.final_snapshot,
    )
    base_data = ResonanceFrameInput(
        base_history,
        (timeframe_history(base_history, H4_PRIMARY),),
        load_result(bars),
    )
    future_data = ResonanceFrameInput(
        appended_history,
        (timeframe_history(appended_history, H4_PRIMARY),),
        load_result(bars),
    )
    engine = assembler(contexts=(H4_PRIMARY,))
    assert engine.build_as_of(future_data, T1).to_dict() == engine.build_as_of(
        base_data, T1
    ).to_dict()


def test_future_reference_bar_does_not_change_past_full_frame() -> None:
    value = frame_input()
    old_payload = assembler().build_as_of(value, T2).to_dict()
    assert assembler().build_as_of(value, T2).to_dict() == old_payload
    assert assembler().build_as_of(value, T3).reference_price.price != (
        assembler().build_as_of(value, T2).reference_price.price
    )


def test_bar_end_time_does_not_grant_visibility_before_available_time() -> None:
    value = frame_input()
    bars = list(value.reference_price_data.bars)
    bars[-1] = replace(bars[-1], available_time=T3.replace(hour=4))
    delayed = load_result(
        tuple(bars), config=value.reference_price_data.source_config
    )
    data = ResonanceFrameInput(
        value.lifecycle_history, value.timeframe_state_histories, delayed
    )
    at_end = assembler().build_as_of(data, T3)
    assert bars[-1].end_time == T3
    assert at_end.reference_price.price == Decimal("102")


def test_origin_time_does_not_grant_evidence_visibility() -> None:
    future = subject(
        "future-origin", BoundarySide.UPPER, "140", "141", confirm_time=T2
    )
    base = base_subjects()[:3]
    bars = (bar(-1), bar(0), bar(1))
    engine, data = custom_bundle(base + (future,), bars, (H4_PRIMARY,))
    assert "future-origin" not in {
        item.subject_id for item in engine.build_as_of(data, T1).evidence
    }
    assert "future-origin" in {
        item.subject_id for item in engine.build_as_of(data, T2).evidence
    }


def test_modifying_future_fact_does_not_change_past_full_frame() -> None:
    base = base_subjects()[:3]
    future_a = subject(
        "future", BoundarySide.UPPER, "115", "116", confirm_time=T2
    )
    future_b = subject(
        "future", BoundarySide.UPPER, "125", "126", confirm_time=T2
    )
    bars = (bar(-1), bar(0), bar(1))
    engine_a, data_a = custom_bundle(base + (future_a,), bars, (H4_PRIMARY,))
    engine_b, data_b = custom_bundle(base + (future_b,), bars, (H4_PRIMARY,))
    assert engine_a.build_as_of(data_a, T1).to_dict() == (
        engine_b.build_as_of(data_b, T1).to_dict()
    )


def test_input_permutation_does_not_change_full_frame_payload() -> None:
    assert assembler().build_batch(frame_input()).to_dict() == (
        assembler().build_batch(frame_input(reverse_histories=True)).to_dict()
    )


def test_price_only_update_does_not_change_evidence_payload() -> None:
    value = frame_input()
    at_t2 = assembler().build_as_of(value, T2)
    at_t3 = assembler().build_as_of(value, T3)
    assert at_t3.evidence == at_t2.evidence
    assert at_t3.context_states == at_t2.context_states
    assert at_t3.reference_price != at_t2.reference_price


def test_non_config_context_changes_lineage_not_scoring_facts() -> None:
    baseline = assembler().build_as_of(frame_input(), T1)
    extra = assembler().build_as_of(frame_input(include_extra=True), T1)
    assert "non-config" not in {item.subject_id for item in extra.evidence}
    assert extra.evidence == baseline.evidence
    assert extra.excluded_broken_subject_ids == baseline.excluded_broken_subject_ids
    assert extra.excluded_retired_subject_ids == baseline.excluded_retired_subject_ids
    assert extra.report == baseline.report
    assert tuple(item.timeframe_state_id for item in extra.context_states) == tuple(
        item.timeframe_state_id for item in baseline.context_states
    )
    assert extra.source_lifecycle_snapshot_id != baseline.source_lifecycle_snapshot_id
    assert tuple(item.context_state_id for item in extra.context_states) != tuple(
        item.context_state_id for item in baseline.context_states
    )
    assert extra.frame_id != baseline.frame_id


def test_c006b_unselected_effective_structure_remains_visible() -> None:
    frame = assembler().build_as_of(frame_input(), T1)
    assert {item.subject_id for item in frame.evidence} >= {
        "upper-a-old", "upper-z-new"
    }
