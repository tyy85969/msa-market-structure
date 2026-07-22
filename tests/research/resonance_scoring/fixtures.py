from __future__ import annotations

from decimal import Decimal

from msa.research.resonance import (
    ResonanceClusteringPolicy,
    ResonanceContext,
    ResonanceContextWeight,
    ResonanceScorer,
    ResonanceScoringConfig,
    ResonanceToleranceMode,
)

from tests.research.resonance.fixtures import (
    H4_PRIMARY,
    H12_MACRO,
    T1,
    assembler,
    frame_input,
)


def scoring_config(
    *,
    contexts: tuple[ResonanceContext, ...] = (H4_PRIMARY, H12_MACRO),
    **overrides: object,
) -> ResonanceScoringConfig:
    values: dict[str, object] = {
        "engine_id": "c007b-resonance-scoring",
        "engine_version": "1.0.0",
        "policy_id": "side-separated-single-link-v1",
        "clustering_policy": ResonanceClusteringPolicy.SIDE_SEPARATED_SINGLE_LINK,
        "tolerance_mode": ResonanceToleranceMode.ABSOLUTE,
        "absolute_tolerance": Decimal("1"),
        "reference_tolerance_fraction": None,
        "context_weights": tuple(
            ResonanceContextWeight(context, Decimal(index + 1))
            for index, context in enumerate(contexts)
        ),
        "candidate_tier_weight": Decimal("0.5"),
        "confirmed_tier_weight": Decimal("1"),
        "fresh_lifecycle_weight": Decimal("1"),
        "tested_lifecycle_weight": Decimal("0.9"),
        "weakened_lifecycle_weight": Decimal("0.8"),
        "flipped_lifecycle_weight": Decimal("0.7"),
        "freshness_horizon_seconds": Decimal("86400"),
        "freshness_floor": Decimal("0.2"),
        "touch_penalty_per_extra": Decimal("0.1"),
        "touch_floor": Decimal("0.5"),
        "aligned_direction_factor": Decimal("1"),
        "neutral_direction_factor": Decimal("0.8"),
        "turning_direction_factor": Decimal("0.7"),
        "opposed_direction_factor": Decimal("0.5"),
        "unknown_direction_factor": Decimal("0.6"),
        "dependency_repeat_credit": Decimal("0.25"),
        "source_diversity_bonus_per_extra": Decimal("0.2"),
        "source_diversity_bonus_cap": Decimal("1"),
        "context_diversity_bonus_per_extra": Decimal("0.3"),
        "context_diversity_bonus_cap": Decimal("1"),
        "distance_horizon_mode": ResonanceToleranceMode.ABSOLUTE,
        "absolute_distance_horizon": Decimal("50"),
        "reference_distance_fraction": None,
        "expected_side_factor": Decimal("1"),
        "contains_price_factor": Decimal("0.8"),
        "opposite_side_factor": Decimal("0.2"),
        "minimum_resonant_evidence_count": 2,
        "minimum_resonant_context_count": 2,
        "strict": True,
    }
    values.update(overrides)
    return ResonanceScoringConfig(**values)  # type: ignore[arg-type]


def scorer(**overrides: object) -> ResonanceScorer:
    return ResonanceScorer(scoring_config(**overrides))


def source_frame(*, at=T1):
    return assembler().build_as_of(frame_input(), at)


def score_frame(*, at=T1, **overrides: object):
    return scorer(**overrides).score_frame(source_frame(at=at))


def source_history():
    return assembler().build_batch(frame_input())
