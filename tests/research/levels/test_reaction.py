from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

import pytest

from msa.data import Timeframe
from msa.domain import (
    BoundarySide,
    ConfirmationStatus,
    LifecycleState,
    MarketRole,
    PriceRange,
    StructureSourceType,
)
from msa.research.levels import LevelGenerationInput, LevelInputError
from tests.research.levels.fixtures import (
    START,
    bar,
    load_result,
    lower_success_bars,
    reaction_generator,
    reaction_input,
    seed,
    upper_success_bars,
)


def test_valid_upper_seed_emits_historical_reaction_candidate() -> None:
    candidate = reaction_generator().generate_batch(
        reaction_input(upper_success_bars())
    ).candidates[0]
    assert candidate.source_type is StructureSourceType.HISTORICAL_REACTION
    assert candidate.boundary_side is BoundarySide.UPPER
    assert candidate.market_role is MarketRole.RESISTANCE
    assert candidate.price_range == PriceRange(Decimal("99"), Decimal("101"))


def test_valid_lower_seed_is_symmetric() -> None:
    lower_seed = seed(
        candidate_id="swing-seed-lower",
        side=BoundarySide.LOWER,
    )
    candidate = reaction_generator().generate_batch(
        reaction_input(lower_success_bars(), (lower_seed,))
    ).candidates[0]
    assert candidate.boundary_side is BoundarySide.LOWER
    assert candidate.market_role is MarketRole.SUPPORT
    assert candidate.price_range == PriceRange(Decimal("99"), Decimal("101"))


@pytest.mark.parametrize(
    ("candidate", "message"),
    [
        (
            seed(
                confirmation_status=ConfirmationStatus.FORMING,
                lifecycle_state=LifecycleState.CANDIDATE,
            ),
            "CONFIRMED",
        ),
        (
            seed(source_type=StructureSourceType.PERIODIC_EXTREME),
            "must be SWING",
        ),
        (seed(symbol="EURUSD"), "symbol"),
        (seed(timeframe=Timeframe.H2), "timeframe"),
        (seed(price_high="101"), "point price"),
    ],
)
def test_invalid_seed_contracts_are_rejected(candidate: object, message: str) -> None:
    data = reaction_input(upper_success_bars(), (candidate,))  # type: ignore[arg-type]
    with pytest.raises(LevelInputError, match=message):
        reaction_generator().generate_batch(data)


def test_upper_seed_requires_resistance_role() -> None:
    invalid = replace(seed(), market_role=MarketRole.SUPPORT)
    with pytest.raises(LevelInputError, match="RESISTANCE"):
        reaction_generator().generate_batch(
            reaction_input(upper_success_bars(), (invalid,))
        )


def test_lower_seed_requires_support_role() -> None:
    invalid = replace(
        seed(candidate_id="lower", side=BoundarySide.LOWER),
        market_role=MarketRole.RESISTANCE,
    )
    with pytest.raises(LevelInputError, match="SUPPORT"):
        reaction_generator().generate_batch(
            reaction_input(lower_success_bars(), (invalid,))
        )


def test_empty_seed_tuple_is_rejected() -> None:
    data = LevelGenerationInput(load_result(upper_success_bars()), ())
    with pytest.raises(LevelInputError, match="non-empty"):
        reaction_generator().generate_batch(data)


def test_duplicate_seed_id_is_rejected() -> None:
    duplicate = seed()
    data = reaction_input(upper_success_bars(), (duplicate, duplicate))
    with pytest.raises(LevelInputError, match="unique"):
        reaction_generator().generate_batch(data)


def test_unsorted_seed_tuple_is_rejected_without_sorting() -> None:
    later = seed(
        candidate_id="later",
        confirm_time=START + timedelta(hours=2),
    )
    earlier = seed(candidate_id="earlier")
    data = reaction_input(upper_success_bars(), (later, earlier))
    with pytest.raises(LevelInputError, match="ordered"):
        reaction_generator().generate_batch(data)


def test_negative_zone_lower_bound_is_rejected_without_clipping() -> None:
    low_price_seed = seed(price="0.5")
    with pytest.raises(LevelInputError, match="must not be negative"):
        reaction_generator().generate_batch(
            reaction_input(upper_success_bars(), (low_price_seed,))
        )


def test_first_success_is_insufficient_for_min_reactions() -> None:
    result = reaction_generator().generate_batch(
        reaction_input(upper_success_bars()[:3])
    )
    assert result.candidates == ()
    assert result.report.successful_reaction_count == 1


def test_candidate_appears_on_nth_success_with_exact_touch_fields() -> None:
    bars = upper_success_bars()
    candidate = reaction_generator().generate_batch(reaction_input(bars)).candidates[0]
    assert candidate.confirm_time == bars[4].available_time
    assert candidate.touch_count == 2
    assert candidate.last_touch_time == bars[3].timestamp
    assert candidate.last_touch_confirm_time == bars[4].available_time
    assert candidate.break_time is None
    assert candidate.break_confirm_time is None
    assert candidate.confirmation_status is ConfirmationStatus.CONFIRMED
    assert candidate.lifecycle_state is LifecycleState.CONFIRMED


def test_touch_bar_cannot_confirm_rejection_on_same_bar() -> None:
    bars = (
        bar(0, high="90", low="88", open="89", close="89"),
        bar(1, high="101", low="95", open="100", close="96"),
        bar(2, high="98", low="95", open="97", close="96"),
    )
    result = reaction_generator(min_reactions=2).generate_batch(reaction_input(bars))
    assert result.report.successful_reaction_count == 1
    assert result.candidates == ()


def test_only_close_away_confirms_not_wick_away() -> None:
    bars = (
        bar(0, high="90", low="88", open="89", close="89"),
        bar(1, high="101", low="99", open="100", close="100"),
        bar(2, high="100", low="95", open="99", close="100"),
        bar(3, high="98", low="95", open="97", close="96"),
    )
    result = reaction_generator(min_reactions=2, confirmation_horizon_bars=2).generate_batch(
        reaction_input(bars)
    )
    assert result.report.successful_reaction_count == 1


def test_penetration_rejects_attempt_before_close_away() -> None:
    bars = (
        bar(0, high="90", low="88", open="89", close="89"),
        bar(1, high="101", low="99", open="100", close="100"),
        bar(2, high="104", low="95", open="100", close="96"),
    )
    result = reaction_generator().generate_batch(reaction_input(bars))
    assert result.report.successful_reaction_count == 0
    assert result.report.rejected_reaction_attempt_count == 1


def test_horizon_expiry_rejects_attempt() -> None:
    bars = (
        bar(0, high="90", low="88", open="89", close="89"),
        bar(1, high="101", low="99", open="100", close="100"),
        bar(2, high="101", low="98", open="100", close="100"),
        bar(3, high="101", low="98", open="100", close="100"),
    )
    result = reaction_generator(confirmation_horizon_bars=2).generate_batch(
        reaction_input(bars)
    )
    assert result.report.rejected_reaction_attempt_count == 1
    assert result.report.successful_reaction_count == 0


def test_separation_blocks_too_close_second_touch() -> None:
    result = reaction_generator(min_separation_bars=3).generate_batch(
        reaction_input(upper_success_bars())
    )
    assert result.candidates == ()
    assert result.report.successful_reaction_count == 1


def test_failed_attempt_does_not_increment_reaction_count() -> None:
    bars = (
        bar(0, high="90", low="88", open="89", close="89"),
        bar(1, high="101", low="99", open="100", close="100"),
        bar(2, high="104", low="99", open="100", close="100"),
        bar(3, high="101", low="99", open="100", close="100"),
        bar(4, high="100", low="95", open="99", close="96"),
    )
    result = reaction_generator().generate_batch(reaction_input(bars))
    assert result.report.successful_reaction_count == 1
    assert result.report.rejected_reaction_attempt_count == 1
    assert result.candidates == ()


def test_seed_confirm_time_blocks_earlier_monitoring() -> None:
    late_seed = seed(confirm_time=START + timedelta(hours=3))
    result = reaction_generator().generate_batch(
        reaction_input(upper_success_bars(), (late_seed,))
    )
    assert result.candidates == ()
    assert result.report.successful_reaction_count == 1


def test_delayed_early_bar_blocks_later_bars_and_sets_prefix_confirm_time() -> None:
    bars = list(upper_success_bars())
    bars[0] = replace(
        bars[0], available_time=START + timedelta(hours=10)
    )
    data = reaction_input(tuple(bars))
    generator = reaction_generator()
    assert generator.generate_as_of(
        data, START + timedelta(hours=5)
    ).candidates == ()
    batch_candidate = generator.generate_batch(data).candidates[0]
    assert batch_candidate.confirm_time == START + timedelta(hours=10)
    assert generator.generate_as_of(
        data, START + timedelta(hours=10)
    ).candidates == (batch_candidate,)


def test_incomplete_bar_blocks_every_later_bar() -> None:
    bars = list(upper_success_bars())
    bars[2] = replace(bars[2], is_complete=False)
    result = reaction_generator().generate_batch(reaction_input(tuple(bars)))
    assert result.candidates == ()
    assert result.report.visible_bar_count == 2
    assert result.report.ignored_incomplete_count == 1


def test_two_overlapping_seeds_are_not_merged() -> None:
    seeds = (
        seed(candidate_id="a-seed"),
        seed(candidate_id="b-seed"),
    )
    candidates = reaction_generator().generate_batch(
        reaction_input(upper_success_bars(), seeds)
    ).candidates
    assert len(candidates) == 2
    assert candidates[0].candidate_id != candidates[1].candidate_id
    assert all(
        item.price_range == PriceRange(Decimal("99"), Decimal("101"))
        for item in candidates
    )


def test_candidate_id_is_deterministic_and_config_sensitive() -> None:
    data = reaction_input(upper_success_bars())
    first = reaction_generator().generate_batch(data).candidates[0]
    second = reaction_generator().generate_batch(data).candidates[0]
    changed = reaction_generator(max_penetration=Decimal("3")).generate_batch(data).candidates[0]
    assert first.candidate_id == second.candidate_id
    assert changed.candidate_id != first.candidate_id


def test_provenance_contains_bounded_seed_and_reaction_evidence() -> None:
    candidate = reaction_generator().generate_batch(
        reaction_input(upper_success_bars())
    ).candidates[0]
    provenance = candidate.provenance
    assert provenance.source_module == "msa.research.levels.reaction"
    assert "swing-seed-upper" in provenance.parent_object_ids
    assert sum(note.startswith("reaction[") for note in provenance.notes) == 2
    assert any("touch_bar_key" in note for note in provenance.notes)
    assert len(provenance.parent_object_ids) <= 6


def test_future_bars_do_not_rewrite_emitted_candidate() -> None:
    bars = upper_success_bars()
    original = reaction_generator().generate_batch(reaction_input(bars)).candidates[0]
    extended = bars + (
        bar(5, high="150", low="80", open="100", close="120"),
        bar(6, high="200", low="50", open="100", close="90"),
    )
    later = reaction_generator().generate_batch(reaction_input(extended)).candidates[0]
    assert later == original


def test_modifying_prices_after_confirmation_does_not_change_candidate() -> None:
    bars = upper_success_bars()
    original = reaction_generator().generate_batch(reaction_input(bars)).candidates[0]
    changed = bars + (bar(5, high="300", low="10", open="100", close="200"),)
    assert reaction_generator().generate_batch(reaction_input(changed)).candidates[0] == original


def test_gap_counts_actual_bars_without_filling() -> None:
    bars = list(upper_success_bars())
    for index in range(3, len(bars)):
        bars[index] = replace(
            bars[index],
            timestamp=bars[index].timestamp + timedelta(hours=1),
            end_time=bars[index].end_time + timedelta(hours=1),
            available_time=bars[index].available_time + timedelta(hours=1),
        )
    result = reaction_generator(min_separation_bars=2).generate_batch(
        reaction_input(tuple(bars))
    )
    assert result.report.gap_count == 1
    assert any("actual bars only" in warning for warning in result.report.warnings)


def test_source_and_seed_objects_are_not_modified() -> None:
    bars = upper_success_bars()
    source_seed = seed()
    before_bars = tuple(item.to_dict() for item in bars)
    before_seed = source_seed.to_dict()
    reaction_generator().generate_batch(reaction_input(bars, (source_seed,)))
    assert tuple(item.to_dict() for item in bars) == before_bars
    assert source_seed.to_dict() == before_seed


def test_actual_c003a_pivot_candidate_is_accepted_as_seed() -> None:
    from tests.research.swing.fixtures import (
        detector,
        high_pivot_bars,
        load_result as swing_load_result,
    )

    pivot_seed = detector().detect_batch(swing_load_result(high_pivot_bars())).candidates[0]
    bars = tuple(
        bar(index, high="20", low="10", open="15", close="15")
        for index in range(4)
    ) + (
        bar(4, high="31", low="29", open="30", close="30"),
        bar(5, high="30", low="25", open="29", close="26"),
        bar(6, high="31", low="29", open="30", close="30"),
        bar(7, high="30", low="25", open="29", close="26"),
    )
    result = reaction_generator(
        touch_tolerance=Decimal("1"),
        min_reaction_distance=Decimal("2"),
    ).generate_batch(reaction_input(bars, (pivot_seed,)))
    assert len(result.candidates) == 1
    assert pivot_seed.candidate_id in result.candidates[0].provenance.parent_object_ids
