from decimal import Decimal

import pytest

from msa.domain import BoundarySide, Direction, LifecycleState
from msa.research.resonance import ResonanceDirectionRelation, ResonanceEvidenceTier
from msa.research.resonance.scoring_contracts import (
    _direction_relation,
    _lifecycle_weight,
)
from tests.research.resonance.fixtures import START, T1, T2

from .fixtures import score_frame, scoring_config


def _contribution(frame, subject_id="upper-a-old"):
    return next(
        contribution
        for zone in frame.zones
        for contribution in zone.contributions
        if contribution.subject_id == subject_id
    )


def test_candidate_confirmed_and_context_weights_are_explicit() -> None:
    candidate = _contribution(score_frame(at=START))
    confirmed = _contribution(score_frame(at=T1))
    assert candidate.tier is ResonanceEvidenceTier.CANDIDATE
    assert candidate.tier_weight == Decimal("0.5")
    assert confirmed.tier is ResonanceEvidenceTier.CONFIRMED
    assert confirmed.tier_weight == Decimal("1")
    assert candidate.context_weight == Decimal("1")


def test_four_lifecycle_weights_are_configured() -> None:
    config = scoring_config()
    assert _lifecycle_weight(LifecycleState.FRESH, config) == Decimal("1")
    assert _lifecycle_weight(LifecycleState.TESTED, config) == Decimal("0.9")
    assert _lifecycle_weight(LifecycleState.WEAKENED, config) == Decimal("0.8")
    assert _lifecycle_weight(LifecycleState.FLIPPED, config) == Decimal("0.7")


@pytest.mark.parametrize(
    ("side", "direction", "expected"),
    [
        (BoundarySide.UPPER, Direction.DOWN, ResonanceDirectionRelation.ALIGNED),
        (BoundarySide.UPPER, Direction.RANGE, ResonanceDirectionRelation.NEUTRAL),
        (BoundarySide.UPPER, Direction.TURNING, ResonanceDirectionRelation.TURNING),
        (BoundarySide.UPPER, Direction.UP, ResonanceDirectionRelation.OPPOSED),
        (BoundarySide.UPPER, Direction.UNKNOWN, ResonanceDirectionRelation.UNKNOWN),
        (BoundarySide.LOWER, Direction.UP, ResonanceDirectionRelation.ALIGNED),
        (BoundarySide.LOWER, Direction.DOWN, ResonanceDirectionRelation.OPPOSED),
    ],
)
def test_direction_relation_is_fixed(side, direction, expected) -> None:
    assert _direction_relation(side, direction) is expected


def test_freshness_uses_frame_as_of_minus_state_confirm_time_exactly() -> None:
    at_activation = _contribution(score_frame(at=START))
    at_test = _contribution(score_frame(at=T1))
    assert at_activation.age_seconds == Decimal("0")
    assert at_activation.freshness_factor == Decimal("1")
    assert at_test.age_seconds == Decimal("0")
    assert at_test.freshness_factor == Decimal("1")


def test_freshness_linear_decay_and_floor() -> None:
    linear = _contribution(
        score_frame(at=T1, freshness_horizon_seconds=Decimal("7200")),
        "upper-macro",
    )
    floored = _contribution(
        score_frame(
            at=T2,
            freshness_horizon_seconds=Decimal("10"),
            freshness_floor=Decimal("0.3"),
        ),
        "upper-macro",
    )
    assert linear.age_seconds == Decimal("3600")
    assert linear.freshness_factor == Decimal("0.5")
    assert floored.freshness_factor == Decimal("0.3")


def test_touch_zero_and_one_are_unpenalized_then_extra_touches_penalize() -> None:
    fresh = _contribution(score_frame(at=START))
    tested = _contribution(score_frame(at=T1))
    weakened = _contribution(score_frame(at=T2))
    assert (fresh.touch_count, fresh.extra_touches, fresh.touch_factor) == (0, 0, Decimal("1"))
    assert (tested.touch_count, tested.extra_touches, tested.touch_factor) == (1, 0, Decimal("1"))
    assert (weakened.touch_count, weakened.extra_touches, weakened.touch_factor) == (2, 1, Decimal("0.9"))


def test_touch_floor_and_raw_contribution_exact_product() -> None:
    contribution = _contribution(
        score_frame(
            at=T2,
            touch_penalty_per_extra=Decimal("1"),
            touch_floor=Decimal("0.4"),
        )
    )
    assert contribution.touch_factor == Decimal("0.4")
    expected = (
        contribution.context_weight
        * contribution.tier_weight
        * contribution.lifecycle_weight
        * contribution.freshness_factor
        * contribution.touch_factor
        * contribution.direction_factor
    )
    assert contribution.raw_contribution == expected
    assert isinstance(contribution.raw_contribution, Decimal)
