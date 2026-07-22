from decimal import Decimal

import pytest

from msa.domain import BoundarySide, StructureSourceType
from msa.research.resonance import (
    ResonanceClass,
    ResonancePriceRelation,
    ResonanceScorer,
    ResonanceScoringConfigurationError,
    ResonanceScoringEngineError,
    ResonanceToleranceMode,
)
from msa.research.resonance.scoring import _ZoneDraft
from tests.research.resonance.fixtures import (
    H4_PRIMARY,
    H12_MACRO,
    MACRO,
    START,
    bar,
    custom_bundle,
    subject,
)
from msa.data import Timeframe

from .fixtures import scoring_config


def _score(subjects, contexts=(H4_PRIMARY,), *, close="100", **overrides):
    close_value = Decimal(close)
    engine, data = custom_bundle(
        tuple(subjects),
        (
            bar(
                -1,
                high=str(max(Decimal("105"), close_value)),
                low=str(min(Decimal("95"), close_value)),
                close=close,
            ),
        ),
        contexts,
    )
    scorer = ResonanceScorer(scoring_config(contexts=contexts, **overrides))
    return scorer.score_frame(engine.build_as_of(data, START))


def test_dependency_base_source_and_context_diversity_bonuses_are_exact() -> None:
    subjects = (
        subject(
            "h4", BoundarySide.UPPER, "110", "111",
            source_types=(StructureSourceType.SWING,), families=("a",),
        ),
        subject(
            "h12", BoundarySide.UPPER, "110.5", "111.5",
            timeframe=Timeframe.H12, scale=MACRO,
            source_types=(StructureSourceType.PERIODIC_EXTREME,), families=("b",),
        ),
    )
    zone = _score(subjects, (H4_PRIMARY, H12_MACRO)).upper_zones[0]
    assert zone.dependency_adjusted_base_score == sum(
        (item.adjusted_component_score for item in zone.dependency_components),
        Decimal("0"),
    )
    assert zone.source_diversity_bonus == Decimal("0.2")
    assert zone.context_diversity_bonus == Decimal("0.3")
    assert zone.quality_score == zone.dependency_adjusted_base_score + Decimal("0.5")


def test_source_and_context_bonus_caps_apply() -> None:
    subjects = (
        subject(
            "h4", BoundarySide.UPPER, "110", "111",
            source_types=(StructureSourceType.SWING, StructureSourceType.HISTORICAL_REACTION),
            families=("a",),
        ),
        subject(
            "h12", BoundarySide.UPPER, "110.5", "111.5",
            timeframe=Timeframe.H12, scale=MACRO,
            source_types=(StructureSourceType.PERIODIC_EXTREME,), families=("b",),
        ),
    )
    zone = _score(
        subjects,
        (H4_PRIMARY, H12_MACRO),
        source_diversity_bonus_per_extra=Decimal("1"),
        source_diversity_bonus_cap=Decimal("0.4"),
        context_diversity_bonus_per_extra=Decimal("1"),
        context_diversity_bonus_cap=Decimal("0.2"),
    ).upper_zones[0]
    assert zone.source_diversity_bonus == Decimal("0.4")
    assert zone.context_diversity_bonus == Decimal("0.2")


def test_quality_score_excludes_price_distance() -> None:
    subjects = (subject("upper", BoundarySide.UPPER, "110", "111", families=("a",)),)
    near = _score(subjects, close="100").upper_zones[0]
    far = _score(subjects, close="50").upper_zones[0]
    assert near.quality_score == far.quality_score
    assert near.distance != far.distance
    assert near.selection_score != far.selection_score


def test_contains_expected_and_opposite_price_relations() -> None:
    contains = _score((subject("contains", BoundarySide.UPPER, "99", "101"),)).upper_zones[0]
    expected = _score((subject("expected", BoundarySide.UPPER, "110", "111"),)).upper_zones[0]
    opposite = _score((subject("opposite", BoundarySide.UPPER, "90", "91"),)).upper_zones[0]
    assert contains.price_relation is ResonancePriceRelation.CONTAINS_PRICE
    assert contains.distance == 0
    assert expected.price_relation is ResonancePriceRelation.EXPECTED_SIDE
    assert opposite.price_relation is ResonancePriceRelation.OPPOSITE_SIDE


def test_absolute_distance_factor_floor_placement_and_selection_are_exact() -> None:
    zone = _score(
        (subject("upper", BoundarySide.UPPER, "110", "111"),),
        absolute_distance_horizon=Decimal("20"),
    ).upper_zones[0]
    assert zone.distance == Decimal("10")
    assert zone.distance_factor == Decimal("0.5")
    assert zone.placement_factor == Decimal("1")
    assert zone.selection_score == zone.quality_score * Decimal("0.5")
    far = _score(
        (subject("upper", BoundarySide.UPPER, "130", "131"),),
        absolute_distance_horizon=Decimal("20"),
    ).upper_zones[0]
    assert far.distance_factor == Decimal("0")
    assert far.selection_score == Decimal("0")


def test_reference_fraction_distance_horizon_is_exact() -> None:
    zone = _score(
        (subject("upper", BoundarySide.UPPER, "110", "111"),),
        distance_horizon_mode=ResonanceToleranceMode.REFERENCE_FRACTION,
        absolute_distance_horizon=None,
        reference_distance_fraction=Decimal("0.2"),
    ).upper_zones[0]
    assert zone.explanation.distance_horizon == Decimal("20.0")
    assert zone.distance_factor == Decimal("0.5")


def test_resonance_classes_and_subthreshold_retention() -> None:
    single = _score((subject("a", BoundarySide.UPPER, "110", "111"),)).upper_zones[0]
    local = _score(
        (
            subject("a", BoundarySide.UPPER, "110", "111"),
            subject("b", BoundarySide.UPPER, "111", "112"),
        ),
        minimum_resonant_context_count=2,
    ).upper_zones[0]
    multi = _score(
        (
            subject("h4", BoundarySide.UPPER, "110", "111"),
            subject("h12", BoundarySide.UPPER, "110.5", "111.5", timeframe=Timeframe.H12, scale=MACRO),
        ),
        (H4_PRIMARY, H12_MACRO),
    ).upper_zones[0]
    assert single.resonance_class is ResonanceClass.SINGLE
    assert local.resonance_class is ResonanceClass.LOCAL_CLUSTER
    assert multi.resonance_class is ResonanceClass.MULTI_CONTEXT_RESONANCE
    assert local in _score(
        (
            subject("a", BoundarySide.UPPER, "110", "111"),
            subject("b", BoundarySide.UPPER, "111", "112"),
        ),
        minimum_resonant_context_count=2,
    ).zones


def test_impossible_tolerance_mode_field_mismatches_fail_explicitly() -> None:
    tolerance = scoring_config()
    object.__setattr__(tolerance, "absolute_tolerance", None)
    with pytest.raises(ResonanceScoringConfigurationError, match="inconsistent"):
        tolerance.effective_tolerance(Decimal("100"))

    tolerance_fraction = scoring_config(
        tolerance_mode=ResonanceToleranceMode.REFERENCE_FRACTION,
        absolute_tolerance=None,
        reference_tolerance_fraction=Decimal("0.01"),
    )
    object.__setattr__(tolerance_fraction, "reference_tolerance_fraction", None)
    with pytest.raises(ResonanceScoringConfigurationError, match="inconsistent"):
        tolerance_fraction.effective_tolerance(Decimal("100"))

    horizon = scoring_config()
    object.__setattr__(horizon, "absolute_distance_horizon", None)
    with pytest.raises(ResonanceScoringConfigurationError, match="inconsistent"):
        horizon.distance_horizon(Decimal("100"))

    horizon_fraction = scoring_config(
        distance_horizon_mode=ResonanceToleranceMode.REFERENCE_FRACTION,
        absolute_distance_horizon=None,
        reference_distance_fraction=Decimal("0.2"),
    )
    object.__setattr__(horizon_fraction, "reference_distance_fraction", None)
    with pytest.raises(ResonanceScoringConfigurationError, match="inconsistent"):
        horizon_fraction.distance_horizon(Decimal("100"))


def test_invalid_draft_rank_time_fails_with_engine_error() -> None:
    draft = _ZoneDraft((("latest_evidence_confirm_time", "not-a-datetime"),))
    with pytest.raises(ResonanceScoringEngineError, match="datetime"):
        ResonanceScorer._draft_rank_key(draft)
