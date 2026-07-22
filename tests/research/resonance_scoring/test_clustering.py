from decimal import Decimal

from msa.domain import BoundarySide
from msa.research.resonance import ResonanceScorer, ResonanceToleranceMode
from tests.research.resonance.fixtures import (
    H4_PRIMARY,
    START,
    bar,
    custom_bundle,
    subject,
)

from .fixtures import scoring_config


def _score(subjects, *, tolerance="1", reference_fraction=None):
    engine, data = custom_bundle(tuple(subjects), (bar(-1),), (H4_PRIMARY,))
    overrides = {}
    if reference_fraction is None:
        overrides.update(absolute_tolerance=Decimal(tolerance))
    else:
        overrides.update(
            tolerance_mode=ResonanceToleranceMode.REFERENCE_FRACTION,
            absolute_tolerance=None,
            reference_tolerance_fraction=Decimal(reference_fraction),
        )
    scorer = ResonanceScorer(scoring_config(contexts=(H4_PRIMARY,), **overrides))
    return scorer.score_frame(engine.build_as_of(data, START))


def test_overlap_touch_and_equal_tolerance_cluster() -> None:
    for ranges in (
        (("110", "111"), ("110.5", "112")),
        (("110", "111"), ("111", "112")),
        (("110", "111"), ("112", "113")),
    ):
        frame = _score(
            (
                subject("a", BoundarySide.UPPER, *ranges[0]),
                subject("b", BoundarySide.UPPER, *ranges[1]),
            )
        )
        assert len(frame.upper_zones) == 1
        assert frame.upper_zones[0].member_evidence_ids == tuple(
            sorted(item.evidence_id for item in frame.source_frame.evidence)
        )


def test_gap_above_tolerance_separates_and_singletons_are_retained() -> None:
    frame = _score(
        (
            subject("a", BoundarySide.UPPER, "110", "111"),
            subject("b", BoundarySide.UPPER, "112.0001", "113"),
        )
    )
    assert len(frame.upper_zones) == 2
    assert all(zone.resonance_class.value == "SINGLE" for zone in frame.upper_zones)


def test_upper_and_lower_never_cluster_even_when_ranges_overlap() -> None:
    frame = _score(
        (
            subject("upper", BoundarySide.UPPER, "100", "101"),
            subject("lower", BoundarySide.LOWER, "100", "101"),
        )
    )
    assert len(frame.upper_zones) == 1
    assert len(frame.lower_zones) == 1
    assert all(len(zone.member_evidence_ids) == 1 for zone in frame.zones)


def test_single_link_chain_bridging_and_envelope_are_explicit() -> None:
    frame = _score(
        (
            subject("a", BoundarySide.UPPER, "110", "111"),
            subject("b", BoundarySide.UPPER, "112", "113"),
            subject("c", BoundarySide.UPPER, "114", "115"),
        )
    )
    zone = frame.upper_zones[0]
    assert len(frame.upper_zones) == 1
    assert zone.price_range.low == Decimal("110")
    assert zone.price_range.high == Decimal("115")
    assert zone.explanation.chain_bridged is True
    assert any(not item.directly_connected for item in zone.explanation.direct_member_gaps)


def test_every_input_evidence_is_partitioned_exactly_once() -> None:
    frame = _score(
        (
            subject("u1", BoundarySide.UPPER, "110", "111"),
            subject("u2", BoundarySide.UPPER, "115", "116"),
            subject("l1", BoundarySide.LOWER, "90", "91"),
        )
    )
    flattened = [item for zone in frame.zones for item in zone.member_evidence_ids]
    assert sorted(flattened) == sorted(item.evidence_id for item in frame.source_frame.evidence)
    assert len(flattened) == len(set(flattened))


def test_reference_fraction_tolerance_is_exact_decimal() -> None:
    frame = _score(
        (
            subject("a", BoundarySide.UPPER, "110", "111"),
            subject("b", BoundarySide.UPPER, "112", "113"),
        ),
        reference_fraction="0.01",
    )
    assert frame.source_frame.reference_price.price == Decimal("100")
    assert frame.upper_zones[0].explanation.effective_clustering_tolerance == Decimal("1.00")


def test_subject_input_permutation_does_not_change_full_payload() -> None:
    subjects = (
        subject("a", BoundarySide.UPPER, "110", "111"),
        subject("b", BoundarySide.UPPER, "112", "113"),
        subject("c", BoundarySide.LOWER, "90", "91"),
    )
    first = _score(subjects).to_dict()
    second = _score(tuple(reversed(subjects))).to_dict()
    assert second == first
