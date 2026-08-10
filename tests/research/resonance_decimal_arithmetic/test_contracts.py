from copy import deepcopy
from decimal import Context, Inexact, ROUND_FLOOR, localcontext

import pytest

from msa.research.resonance import ResonanceScoreFrame, ResonanceScorer
from msa.research.resonance.errors import ResonanceScoringSerializationError
from msa.research.resonance.scoring_contracts import (
    ResonanceEvidenceContribution,
    _contribution_id,
)

from .test_context import snapshot


def test_altered_context_round_trip_uses_canonical_recomputation(
    arithmetic_score_frame,
) -> None:
    payload = arithmetic_score_frame.to_dict()
    altered = Context(prec=7, rounding=ROUND_FLOOR)
    with localcontext(altered) as caller:
        before = snapshot(caller)
        restored = ResonanceScoreFrame.from_dict(payload)
        assert snapshot(caller) == before
    assert restored.to_dict() == payload


def test_low_precision_cannot_change_engine_freshness_or_distance(
    arithmetic_score_frame,
) -> None:
    frame = arithmetic_score_frame.source_frame
    scorer = ResonanceScorer(arithmetic_score_frame.config_snapshot)
    context = Context(prec=7, rounding=ROUND_FLOOR)
    context.traps[Inexact] = True
    with localcontext(context) as caller:
        before = snapshot(caller)
        altered = scorer.score_frame(frame)
        assert snapshot(caller) == before
    assert altered.to_dict() == arithmetic_score_frame.to_dict()
    assert tuple(
        (
            item.distance_factor,
            tuple(value.freshness_factor for value in item.contributions),
        )
        for item in altered.zones
    ) == tuple(
        (
            item.distance_factor,
            tuple(value.freshness_factor for value in item.contributions),
        )
        for item in arithmetic_score_frame.zones
    )


def test_resigned_low_precision_contribution_is_rejected(
    arithmetic_score_frame,
) -> None:
    zone = arithmetic_score_frame.zones[0]
    payload = deepcopy(zone.contributions[0].to_dict())
    payload["freshness_factor"] = "0.9583333"
    payload["raw_contribution"] = "0.5749999"
    payload["contribution_id"] = _contribution_id(
        config=arithmetic_score_frame.config_snapshot.to_dict(),
        evidence_id=payload["evidence_id"],
        subject_id=payload["subject_id"],
        lifecycle_state_id=payload["lifecycle_state_id"],
        context=payload["context"],
        side=payload["side"],
        tier=payload["tier"],
        lifecycle_state=payload["lifecycle_state"],
        direction=payload["direction"],
        direction_relation=payload["direction_relation"],
        context_weight=payload["context_weight"],
        tier_weight=payload["tier_weight"],
        lifecycle_weight=payload["lifecycle_weight"],
        age_seconds=payload["age_seconds"],
        freshness_factor=payload["freshness_factor"],
        touch_count=payload["touch_count"],
        extra_touches=payload["extra_touches"],
        touch_factor=payload["touch_factor"],
        direction_factor=payload["direction_factor"],
        raw_contribution=payload["raw_contribution"],
        dependency_component_id=payload["dependency_component_id"],
        schema_version=payload["schema_version"],
    )
    with localcontext(Context(prec=7, rounding=ROUND_FLOOR)):
        with pytest.raises(ResonanceScoringSerializationError):
            ResonanceEvidenceContribution.from_dict(payload)
