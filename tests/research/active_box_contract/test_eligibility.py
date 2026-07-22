from decimal import Decimal

from msa.research.active_box import ZoneEligibilityReason, evaluate_zone
from msa.domain import BoundarySide
from msa.research.resonance import ResonanceClass, ResonanceScorer
from tests.research.resonance.fixtures import H4_PRIMARY, START, bar, custom_bundle, subject
from tests.research.resonance_scoring.fixtures import scoring_config

from .fixtures import config, score_frame


def test_expected_side_threshold_equality_and_single_are_eligible() -> None:
    zone=score_frame().upper_zones[0]
    result=evaluate_zone(zone,config(minimum_quality_score=zone.quality_score,minimum_selection_score=zone.selection_score,
        allowed_resonance_classes=(zone.resonance_class,)))
    assert result.eligible and result.reasons==()


def test_class_quality_and_selection_failures_use_fixed_order() -> None:
    zone=score_frame().upper_zones[0]
    excluded=next(item for item in ResonanceClass if item is not zone.resonance_class)
    result=evaluate_zone(zone,config(minimum_quality_score=zone.quality_score+Decimal("1"),minimum_selection_score=zone.selection_score+Decimal("1"),
        allowed_resonance_classes=(excluded,)))
    assert result.reasons==(
        ZoneEligibilityReason.RESONANCE_CLASS_NOT_ALLOWED,
        ZoneEligibilityReason.QUALITY_BELOW_MINIMUM,
        ZoneEligibilityReason.SELECTION_BELOW_MINIMUM,
    )
    assert not result.eligible


def test_each_zone_produces_one_auditable_evaluation() -> None:
    frame=score_frame(); results=tuple(evaluate_zone(zone,config()) for zone in frame.zones)
    assert len(results)==len(frame.zones)
    assert {item.zone_snapshot_id for item in results}=={item.zone_snapshot_id for item in frame.zones}


def _upper_at(close: str):
    upper=subject("upper",BoundarySide.UPPER,"110","111")
    engine,data=custom_bundle((upper,),(bar(-1,high="125",low="50",close=close),),(H4_PRIMARY,))
    return ResonanceScorer(scoring_config(contexts=(H4_PRIMARY,))).score_frame(engine.build_as_of(data,START)).upper_zones[0]


def test_contains_and_opposite_price_relations_are_ineligible() -> None:
    contains=evaluate_zone(_upper_at("110.5"),config())
    opposite=evaluate_zone(_upper_at("120"),config())
    assert contains.reasons[0] is ZoneEligibilityReason.PRICE_RELATION_NOT_EXPECTED
    assert opposite.reasons[0] is ZoneEligibilityReason.PRICE_RELATION_NOT_EXPECTED


def test_zero_distance_factor_is_ineligible() -> None:
    result=evaluate_zone(_upper_at("60"),config())
    assert result.distance_factor==0
    assert ZoneEligibilityReason.DISTANCE_FACTOR_NOT_POSITIVE in result.reasons
