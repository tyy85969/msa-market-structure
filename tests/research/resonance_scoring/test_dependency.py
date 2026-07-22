from decimal import Decimal

from msa.domain import BoundarySide
from msa.research.resonance import ResonanceScorer
from tests.research.resonance.fixtures import H4_PRIMARY, START, bar, custom_bundle, subject

from .fixtures import scoring_config


def _score(subjects, *, repeat_credit="0.25", tolerance="5"):
    engine, data = custom_bundle(tuple(subjects), (bar(-1),), (H4_PRIMARY,))
    scorer = ResonanceScorer(
        scoring_config(
            contexts=(H4_PRIMARY,),
            dependency_repeat_credit=Decimal(repeat_credit),
            absolute_tolerance=Decimal(tolerance),
        )
    )
    return scorer.score_frame(engine.build_as_of(data, START))


def test_no_shared_family_creates_independent_components() -> None:
    frame = _score(
        (
            subject("a", BoundarySide.UPPER, "110", "111", families=("a",)),
            subject("b", BoundarySide.UPPER, "112", "113", families=("b",)),
        )
    )
    assert len(frame.upper_zones[0].dependency_components) == 2
    assert all(len(item.member_evidence_ids) == 1 for item in frame.upper_zones[0].dependency_components)


def test_direct_and_transitive_family_sharing_form_one_component() -> None:
    frame = _score(
        (
            subject("a", BoundarySide.UPPER, "110", "111", families=("family-1",)),
            subject("b", BoundarySide.UPPER, "112", "113", families=("family-1", "family-2")),
            subject("c", BoundarySide.UPPER, "114", "115", families=("family-2",)),
        )
    )
    component = frame.upper_zones[0].dependency_components[0]
    assert len(component.member_evidence_ids) == 3
    assert component.shared_family_ids == ("family-1", "family-2")
    assert len(frame.upper_zones[0].explanation.dependency_family_edges) == 2


def test_repeat_credit_zero_one_and_midpoint_are_exact() -> None:
    subjects = (
        subject("a", BoundarySide.UPPER, "110", "111", families=("same",)),
        subject("b", BoundarySide.UPPER, "112", "113", families=("same",)),
    )
    zero = _score(subjects, repeat_credit="0").upper_zones[0].dependency_components[0]
    one = _score(subjects, repeat_credit="1").upper_zones[0].dependency_components[0]
    mid = _score(subjects, repeat_credit="0.25").upper_zones[0].dependency_components[0]
    assert zero.adjusted_component_score == zero.primary_raw_contribution
    assert one.adjusted_component_score == one.primary_raw_contribution + one.repeated_raw_contribution
    assert mid.adjusted_component_score == mid.primary_raw_contribution + Decimal("0.25") * mid.repeated_raw_contribution


def test_primary_tie_uses_evidence_id() -> None:
    subjects = (
        subject("a", BoundarySide.UPPER, "110", "111", families=("same",)),
        subject("b", BoundarySide.UPPER, "112", "113", families=("same",)),
    )
    frame = _score(subjects)
    zone = frame.upper_zones[0]
    component = zone.dependency_components[0]
    tied = sorted(zone.contributions, key=lambda item: item.evidence_id)
    assert len({item.raw_contribution for item in tied}) == 1
    assert component.primary_evidence_id == tied[0].evidence_id


def test_dependency_graph_does_not_cross_zone_or_side() -> None:
    frame = _score(
        (
            subject("u-near", BoundarySide.UPPER, "110", "111", families=("same",)),
            subject("u-far", BoundarySide.UPPER, "130", "131", families=("same",)),
            subject("lower", BoundarySide.LOWER, "110", "111", families=("same",)),
        ),
        tolerance="1",
    )
    assert len(frame.upper_zones) == 2
    assert len(frame.lower_zones) == 1
    assert all(len(component.member_evidence_ids) == 1 for zone in frame.zones for component in zone.dependency_components)
