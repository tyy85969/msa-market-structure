from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from msa.data.contracts import Timeframe
from msa.domain import (
    BoundaryRef,
    BoundarySide,
    DomainValidationError,
    LifecycleState,
    MarketRole,
    PriceRange,
    ProvenanceRef,
    ScaleDescriptor,
    StructureCluster,
    StructureObjectKind,
    StructureSourceType,
)


UTC = timezone.utc
ORIGIN = datetime(2026, 2, 1, 8, 0, tzinfo=UTC)
CONFIRM = datetime(2026, 2, 1, 10, 0, tzinfo=UTC)


def provenance(object_id: str) -> ProvenanceRef:
    return ProvenanceRef("tests.cluster", "1", object_id, None, (), ())


def member(**overrides: object) -> BoundaryRef:
    values: dict[str, object] = {
        "object_kind": StructureObjectKind.LEVEL_CANDIDATE,
        "object_id": "member-1",
        "symbol": "XAUUSD",
        "timeframe": Timeframe.H1,
        "scale": ScaleDescriptor("configured-primary", 1),
        "price_range": PriceRange(Decimal("2300"), Decimal("2301")),
        "boundary_side": BoundarySide.LOWER,
        "market_role": MarketRole.SUPPORT,
        "lifecycle_state": LifecycleState.FRESH,
        "origin_time": ORIGIN,
        "confirm_time": CONFIRM,
        "source_types": (StructureSourceType.SWING,),
        "structure_families": ("shared-family",),
        "provenance": provenance("member-source"),
    }
    values.update(overrides)
    return BoundaryRef(**values)  # type: ignore[arg-type]


def cluster(**overrides: object) -> StructureCluster:
    values: dict[str, object] = {
        "cluster_id": "cluster-1",
        "symbol": "XAUUSD",
        "timeframe": Timeframe.H1,
        "scale": ScaleDescriptor("configured-primary", 1),
        "price_range": PriceRange(Decimal("2299.5"), Decimal("2301.5")),
        "boundary_side": BoundarySide.LOWER,
        "market_role": MarketRole.SUPPORT,
        "lifecycle_state": LifecycleState.CONFIRMED,
        "origin_time": ORIGIN,
        "confirm_time": CONFIRM + timedelta(minutes=5),
        "member_refs": (member(),),
        "cluster_family": "price-overlap-cluster",
        "provenance": provenance("cluster-source"),
    }
    values.update(overrides)
    return StructureCluster(**values)  # type: ignore[arg-type]


def test_cluster_accepts_members_from_same_or_different_timeframes() -> None:
    members = (
        member(),
        member(object_id="member-2", timeframe=Timeframe.H4),
        member(object_id="member-3", timeframe=Timeframe.H1),
    )
    result = cluster(member_refs=members)
    assert result.timeframes == (Timeframe.H1, Timeframe.H4)
    assert len(result.member_refs) == 3


def test_cluster_rejects_empty_members() -> None:
    with pytest.raises(DomainValidationError, match="must not be empty"):
        cluster(member_refs=())


def test_cluster_rejects_duplicate_member_ids_without_deduplication() -> None:
    duplicate = member(object_id="member-1", timeframe=Timeframe.H4)
    with pytest.raises(DomainValidationError, match="unique object_id"):
        cluster(member_refs=(member(), duplicate))


def test_cluster_rejects_mixed_symbol_members() -> None:
    with pytest.raises(DomainValidationError, match="symbol"):
        cluster(member_refs=(member(symbol="EURUSD"),))


def test_cluster_rejects_mixed_boundary_side_members() -> None:
    with pytest.raises(DomainValidationError, match="boundary_side"):
        cluster(member_refs=(member(boundary_side=BoundarySide.UPPER),))


def test_cluster_cannot_confirm_before_latest_member() -> None:
    late = member(
        object_id="late-member",
        confirm_time=CONFIRM + timedelta(hours=2),
    )
    with pytest.raises(DomainValidationError, match="every member"):
        cluster(member_refs=(member(), late))


def test_cluster_confirm_time_cannot_precede_origin() -> None:
    with pytest.raises(DomainValidationError, match="confirm_time"):
        cluster(confirm_time=ORIGIN - timedelta(seconds=1))


def test_cluster_rejects_candidate_lifecycle() -> None:
    with pytest.raises(DomainValidationError, match="CANDIDATE"):
        cluster(lifecycle_state=LifecycleState.CANDIDATE)


def test_cluster_derived_properties_are_deterministic() -> None:
    members = (
        member(
            object_id="member-b",
            timeframe=Timeframe.H4,
            source_types=(
                StructureSourceType.PERIODIC_EXTREME,
                StructureSourceType.SWING,
            ),
            structure_families=("z-family", "shared-family"),
        ),
        member(
            object_id="member-a",
            timeframe=Timeframe.H1,
            source_types=(StructureSourceType.HISTORICAL_REACTION,),
            structure_families=("shared-family",),
        ),
    )
    result = cluster(member_refs=members)
    assert result.source_types == (
        StructureSourceType.HISTORICAL_REACTION,
        StructureSourceType.PERIODIC_EXTREME,
        StructureSourceType.SWING,
    )
    assert result.timeframes == (Timeframe.H1, Timeframe.H4)
    assert result.structure_families == ("shared-family", "z-family")


def test_same_family_members_remain_distinct_evidence_records() -> None:
    members = (member(), member(object_id="member-2", timeframe=Timeframe.H4))
    result = cluster(member_refs=members)
    assert len(result.member_refs) == 2
    assert all(
        item.structure_families == ("shared-family",)
        for item in result.member_refs
    )


def test_cluster_converts_to_boundary_snapshot() -> None:
    result = cluster()
    boundary = result.to_boundary_ref()
    assert boundary.object_kind is StructureObjectKind.STRUCTURE_CLUSTER
    assert boundary.object_id == result.cluster_id
    assert boundary.timeframe is result.timeframe
    assert boundary.source_types == result.source_types
    assert set(boundary.structure_families) == {
        "price-overlap-cluster",
        "shared-family",
    }


def test_cluster_availability_uses_its_confirm_time() -> None:
    result = cluster()
    assert not result.is_confirmed_at(result.confirm_time - timedelta(microseconds=1))
    assert result.is_confirmed_at(result.confirm_time)
