from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from msa.data import Timeframe
from msa.domain import (
    BoundarySide,
    ConfirmationStatus,
    LevelCandidate,
    LifecycleState,
    MarketRole,
    PriceRange,
    ProvenanceRef,
    ScaleDescriptor,
    StructureSourceType,
)
from msa.research.pool import (
    DependencyFamilyAssignment,
    LevelPoolClusterer,
    LevelPoolConfig,
    LevelPoolInput,
    LinkageMode,
    ToleranceMode,
)


UTC = timezone.utc
T0 = datetime(2026, 7, 1, 0, 0, tzinfo=UTC)
T1 = T0 + timedelta(hours=1)
T2 = T0 + timedelta(hours=2)
T3 = T0 + timedelta(hours=3)
T4 = T0 + timedelta(hours=4)
SCALE = ScaleDescriptor("c005-member", 1)
CLUSTER_SCALE = ScaleDescriptor("c005-cluster-context", 5)


def candidate(
    candidate_id: str = "candidate-a",
    *,
    low: str = "100",
    high: str | None = None,
    side: BoundarySide = BoundarySide.UPPER,
    role: MarketRole | None = None,
    source_type: StructureSourceType = StructureSourceType.SWING,
    symbol: str = "XAUUSD",
    timeframe: Timeframe = Timeframe.H1,
    scale: ScaleDescriptor = SCALE,
    origin_time: datetime = T0,
    confirm_time: datetime | None = T1,
    confirmation_status: ConfirmationStatus = ConfirmationStatus.CONFIRMED,
    lifecycle_state: LifecycleState = LifecycleState.CONFIRMED,
    structure_family: str = "confirmed-pivot-strict-v1",
) -> LevelCandidate:
    market_role = role or (
        MarketRole.RESISTANCE
        if side is BoundarySide.UPPER
        else MarketRole.SUPPORT
    )
    actual_confirm = (
        None if confirmation_status is ConfirmationStatus.FORMING else confirm_time
    )
    return LevelCandidate(
        candidate_id=candidate_id,
        symbol=symbol,
        timeframe=timeframe,
        scale=scale,
        price_range=PriceRange(Decimal(low), Decimal(high or low)),
        source_type=source_type,
        boundary_side=side,
        market_role=market_role,
        confirmation_status=confirmation_status,
        lifecycle_state=lifecycle_state,
        origin_time=origin_time,
        confirm_time=actual_confirm,
        touch_count=0,
        last_touch_time=None,
        last_touch_confirm_time=None,
        break_time=None,
        break_confirm_time=None,
        structure_family=structure_family,
        provenance=ProvenanceRef(
            source_module="tests.research.pool",
            source_version="1.0.0",
            source_object_id=f"source-{candidate_id}",
            policy_id="fixture-policy",
            parent_object_ids=(f"parent-{candidate_id}",),
            notes=(f"fixture={candidate_id}",),
        ),
    )


def assignment(
    candidate_id: str,
    family_id: str = "real-extreme-family-1",
    rationale: str = "caller documented shared real extreme",
) -> DependencyFamilyAssignment:
    return DependencyFamilyAssignment(candidate_id, family_id, rationale)


def absolute_config(**overrides: object) -> LevelPoolConfig:
    values: dict[str, object] = {
        "pool_id": "c005-level-pool",
        "pool_version": "1.0.0",
        "policy_id": "range-gap-single-link-v1",
        "cluster_timeframe": Timeframe.H4,
        "cluster_scale": CLUSTER_SCALE,
        "tolerance_mode": ToleranceMode.ABSOLUTE,
        "absolute_tolerance": Decimal("1"),
        "normalization_unit": None,
        "normalized_tolerance": None,
        "linkage_mode": LinkageMode.SINGLE_LINK,
        "strict": True,
    }
    values.update(overrides)
    return LevelPoolConfig(**values)  # type: ignore[arg-type]


def normalized_config(**overrides: object) -> LevelPoolConfig:
    values: dict[str, object] = {
        "pool_id": "c005-level-pool",
        "pool_version": "1.0.0",
        "policy_id": "range-gap-single-link-v1",
        "cluster_timeframe": Timeframe.H4,
        "cluster_scale": CLUSTER_SCALE,
        "tolerance_mode": ToleranceMode.NORMALIZED,
        "absolute_tolerance": None,
        "normalization_unit": Decimal("10"),
        "normalized_tolerance": Decimal("0.1"),
        "linkage_mode": LinkageMode.SINGLE_LINK,
        "strict": True,
    }
    values.update(overrides)
    return LevelPoolConfig(**values)  # type: ignore[arg-type]


def pool_input(
    candidates: tuple[LevelCandidate, ...],
    assignments: tuple[DependencyFamilyAssignment, ...] = (),
) -> LevelPoolInput:
    return LevelPoolInput(candidates, assignments)


def clusterer(**overrides: object) -> LevelPoolClusterer:
    return LevelPoolClusterer(absolute_config(**overrides))
