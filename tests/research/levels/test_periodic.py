from dataclasses import replace
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from msa.data import Timeframe
from msa.domain import (
    BoundarySide,
    ConfirmationStatus,
    LifecycleState,
    MarketRole,
    StructureSourceType,
)
from msa.research.levels import LevelGenerationInput, LevelInputError
from tests.research.levels.fixtures import (
    SCALE,
    START,
    bar,
    load_result,
    periodic_generator,
    periodic_input,
    source_config,
)


def test_complete_bar_emits_high_and_low_candidates() -> None:
    source_bar = bar(0, high="105.1250", low="95.2500")
    result = periodic_generator().generate_batch(periodic_input((source_bar,)))
    assert len(result.candidates) == 2
    assert {item.price_range.low for item in result.candidates} == {
        Decimal("105.1250"),
        Decimal("95.2500"),
    }


def test_high_maps_to_upper_resistance_periodic_extreme() -> None:
    candidate = next(
        item
        for item in periodic_generator().generate_batch(periodic_input((bar(0),))).candidates
        if item.boundary_side is BoundarySide.UPPER
    )
    assert candidate.source_type is StructureSourceType.PERIODIC_EXTREME
    assert candidate.market_role is MarketRole.RESISTANCE


def test_low_maps_to_lower_support_periodic_extreme() -> None:
    candidate = next(
        item
        for item in periodic_generator().generate_batch(periodic_input((bar(0),))).candidates
        if item.boundary_side is BoundarySide.LOWER
    )
    assert candidate.source_type is StructureSourceType.PERIODIC_EXTREME
    assert candidate.market_role is MarketRole.SUPPORT


def test_periodic_candidate_time_and_state_mapping() -> None:
    source_bar = bar(0)
    for candidate in periodic_generator().generate_batch(periodic_input((source_bar,))).candidates:
        assert candidate.origin_time == source_bar.timestamp
        assert candidate.confirm_time == source_bar.available_time
        assert candidate.confirmation_status is ConfirmationStatus.CONFIRMED
        assert candidate.lifecycle_state is LifecycleState.CONFIRMED
        assert candidate.touch_count == 0
        assert candidate.last_touch_time is None
        assert candidate.break_time is None


def test_candidate_not_visible_before_confirm_time_and_visible_at_equality() -> None:
    source_bar = bar(0, available_time=START + timedelta(hours=2))
    data = periodic_input((source_bar,))
    generator = periodic_generator()
    assert generator.generate_as_of(
        data, source_bar.available_time - timedelta(microseconds=1)
    ).candidates == ()
    assert generator.generate_as_of(
        data, source_bar.available_time
    ).candidates == generator.generate_batch(data).candidates


def test_incomplete_tail_is_ignored_and_reported() -> None:
    bars = (bar(0), bar(1, is_complete=False))
    result = periodic_generator().generate_batch(periodic_input(bars))
    assert len(result.candidates) == 2
    assert result.report.ignored_incomplete_count == 1
    assert any("incomplete periodic" in item for item in result.report.warnings)


def test_complete_after_incomplete_fails_closed() -> None:
    data = periodic_input((bar(0, is_complete=False), bar(1)))
    with pytest.raises(LevelInputError, match="complete bar cannot follow"):
        periodic_generator().generate_batch(data)


@pytest.mark.parametrize(
    ("flag", "expected_side"),
    [("emit_high", BoundarySide.LOWER), ("emit_low", BoundarySide.UPPER)],
)
def test_single_side_emission(flag: str, expected_side: BoundarySide) -> None:
    result = periodic_generator(**{flag: False}).generate_batch(periodic_input((bar(0),)))
    assert len(result.candidates) == 1
    assert result.candidates[0].boundary_side is expected_side


def test_equal_high_low_still_has_distinct_side_ids() -> None:
    flat = bar(0, open="100", high="100", low="100", close="100")
    candidates = periodic_generator().generate_batch(periodic_input((flat,))).candidates
    assert len(candidates) == 2
    assert candidates[0].candidate_id != candidates[1].candidate_id


@pytest.mark.parametrize("timeframe", [Timeframe.D, Timeframe.W])
def test_calendar_boundary_policy_is_preserved(timeframe: Timeframe) -> None:
    source_bar = bar(
        0,
        timeframe=timeframe,
        boundary_policy="xau-session-v1",
    )
    config = source_config(
        timeframe=timeframe, boundary_policy="xau-session-v1"
    )
    data = LevelGenerationInput(load_result((source_bar,), config=config), ())
    candidates = periodic_generator(period_timeframe=timeframe).generate_batch(data).candidates
    assert all(
        "boundary_policy=xau-session-v1" in item.provenance.notes
        for item in candidates
    )


def test_mixed_boundary_policy_is_rejected() -> None:
    first = bar(0, boundary_policy="anchor-a")
    second = bar(1, boundary_policy="anchor-b")
    config = source_config(boundary_policy="anchor-a")
    data = LevelGenerationInput(load_result((first, second), config=config), ())
    with pytest.raises(LevelInputError, match="boundary policy"):
        periodic_generator().generate_batch(data)


def test_source_timeframe_mismatch_is_rejected() -> None:
    with pytest.raises(LevelInputError, match="source timeframe"):
        periodic_generator(period_timeframe=Timeframe.H4).generate_batch(
            periodic_input((bar(0),))
        )


@pytest.mark.parametrize("identity", ["symbol", "timeframe", "source"])
def test_mixed_source_identity_is_rejected(identity: str) -> None:
    first = bar(0)
    if identity == "symbol":
        second = bar(1, symbol="EURUSD")
        message = "mixed symbol"
    elif identity == "timeframe":
        second = bar(1, timeframe=Timeframe.H2)
        message = "mixed timeframe"
    else:
        second = bar(1, source="other-feed")
        message = "mixed source"
    data = LevelGenerationInput(load_result((first, second)), ())
    with pytest.raises(LevelInputError, match=message):
        periodic_generator().generate_batch(data)


def test_nonempty_seeds_are_rejected() -> None:
    from tests.research.levels.fixtures import seed

    data = LevelGenerationInput(load_result((bar(0),)), (seed(),))
    with pytest.raises(LevelInputError, match="seed_candidates"):
        periodic_generator().generate_batch(data)


def test_candidate_id_is_deterministic_and_config_sensitive() -> None:
    data = periodic_input((bar(0),))
    first = periodic_generator().generate_batch(data).candidates
    second = periodic_generator().generate_batch(data).candidates
    changed = periodic_generator(policy_id="periodic-v2").generate_batch(data).candidates
    assert [item.candidate_id for item in first] == [item.candidate_id for item in second]
    assert {item.candidate_id for item in first}.isdisjoint(
        {item.candidate_id for item in changed}
    )


def test_future_bar_does_not_change_existing_candidate() -> None:
    original_data = periodic_input((bar(0),))
    original = periodic_generator().generate_batch(original_data).candidates
    extended = periodic_generator().generate_batch(periodic_input((bar(0), bar(1)))).candidates
    assert all(item in extended for item in original)


def test_delayed_earlier_bar_does_not_block_independent_later_periodic_bar() -> None:
    earlier = bar(0, available_time=START + timedelta(hours=5))
    later = bar(1, available_time=START + timedelta(hours=2))
    result = periodic_generator().generate_as_of(
        periodic_input((earlier, later)), START + timedelta(hours=2)
    )
    assert len(result.candidates) == 2
    assert all(item.origin_time == later.timestamp for item in result.candidates)


def test_report_counts_and_structure_family_are_explicit() -> None:
    result = periodic_generator().generate_batch(periodic_input((bar(0), bar(1))))
    assert result.report.input_bar_count == 2
    assert result.report.visible_bar_count == 2
    assert result.report.periodic_high_count == 2
    assert result.report.periodic_low_count == 2
    assert result.report.reaction_candidate_count == 0
    assert all(item.structure_family == "periodic-extreme-h1-v1" for item in result.candidates)


def test_gap_is_reported_without_synthetic_bar() -> None:
    bars = (bar(0), bar(3, timestamp=START + timedelta(hours=3)))
    result = periodic_generator().generate_batch(periodic_input(bars))
    assert len(result.candidates) == 4
    assert result.report.gap_count == 1


@pytest.mark.parametrize("case", ["duplicate", "overlap", "out_of_order"])
def test_invalid_sequence_is_rejected_without_repair(case: str) -> None:
    first = bar(0)
    if case == "duplicate":
        bars = (first, first)
    elif case == "overlap":
        bars = (first, bar(1, timestamp=START + timedelta(minutes=30)))
    else:
        bars = (first, bar(1, timestamp=START - timedelta(hours=2)))
    with pytest.raises(LevelInputError, match="quality_report"):
        periodic_generator().generate_batch(periodic_input(bars))


def test_invalid_ohlc_is_rejected_even_if_corrupted_after_construction() -> None:
    source_bar = bar(0)
    object.__setattr__(source_bar, "high", Decimal("1"))
    with pytest.raises(LevelInputError, match="invalid OHLC"):
        periodic_generator().generate_batch(periodic_input((source_bar,)))


def test_naive_processing_time_is_rejected() -> None:
    with pytest.raises(LevelInputError, match="timezone-aware"):
        periodic_generator().generate_as_of(
            periodic_input((bar(0),)), datetime(2026, 7, 1, 1)
        )


def test_generator_source_contains_no_resampling_implementation() -> None:
    source = Path("src/python/msa/research/levels/periodic.py").read_text(encoding="utf-8")
    lowered = source.lower()
    assert "resample_" not in lowered
    assert "targetbucket" not in lowered
    assert "uuid4" not in source
    assert "datetime.now" not in source
    assert "sha256" in source


def test_source_objects_are_not_modified() -> None:
    bars = (bar(0), bar(1))
    before = tuple(item.to_dict() for item in bars)
    periodic_generator().generate_batch(periodic_input(bars))
    assert tuple(item.to_dict() for item in bars) == before
    assert periodic_generator().config.scale == SCALE
