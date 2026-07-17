from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from msa.data.contracts import Timeframe
from msa.domain import (
    ActiveBox,
    ActiveBoxStatus,
    BoundaryRef,
    BoundarySide,
    ConfirmationStatus,
    DomainAvailabilityError,
    DomainValidationError,
    LevelCandidate,
    LifecycleState,
    MarketRole,
    PriceRange,
    ProvenanceRef,
    ScaleDescriptor,
    StructureCluster,
    StructureObjectKind,
    StructureSourceType,
    TimeframeState,
)


UTC = timezone.utc
BASE = datetime(2026, 6, 1, 0, 0, tzinfo=UTC)
SCALE = ScaleDescriptor("configured-primary", 1)


def provenance(object_id: str) -> ProvenanceRef:
    return ProvenanceRef("tests.lookahead", "1", object_id, None, (), ())


def candidate(candidate_id: str, confirm_offset: int) -> LevelCandidate:
    return LevelCandidate(
        candidate_id,
        "XAUUSD",
        Timeframe.H1,
        SCALE,
        PriceRange(Decimal("2300"), Decimal("2301")),
        StructureSourceType.SWING,
        BoundarySide.LOWER,
        MarketRole.SUPPORT,
        ConfirmationStatus.CONFIRMED,
        LifecycleState.FRESH,
        BASE,
        BASE + timedelta(hours=confirm_offset),
        0,
        None,
        None,
        None,
        None,
        "confirmed-swing",
        provenance(candidate_id),
    )


def boundary(side: BoundarySide, confirm_offset: int) -> BoundaryRef:
    price_range = (
        PriceRange(Decimal("2400"), Decimal("2401"))
        if side is BoundarySide.UPPER
        else PriceRange(Decimal("2300"), Decimal("2301"))
    )
    return BoundaryRef(
        StructureObjectKind.LEVEL_CANDIDATE,
        f"{side.value.lower()}-{confirm_offset}",
        "XAUUSD",
        Timeframe.H1,
        SCALE,
        price_range,
        side,
        MarketRole.RESISTANCE if side is BoundarySide.UPPER else MarketRole.SUPPORT,
        LifecycleState.FRESH,
        BASE,
        BASE + timedelta(hours=confirm_offset),
        (StructureSourceType.SWING,),
        ("confirmed-swing",),
        provenance(f"{side.value.lower()}-{confirm_offset}"),
    )


def test_candidate_cannot_be_consumed_before_confirm_time() -> None:
    result = candidate("candidate-1", 2)
    processing_time = result.confirm_time - timedelta(microseconds=1)
    assert not result.is_confirmed_at(processing_time)
    with pytest.raises(DomainAvailabilityError):
        result.require_confirmed_at(processing_time)


def test_candidate_first_becomes_consumable_exactly_at_confirm_time() -> None:
    result = candidate("candidate-1", 2)
    assert result.is_confirmed_at(result.confirm_time)
    assert result.require_confirmed_at(result.confirm_time) is result


def test_candidate_rejects_touch_fact_confirmed_after_snapshot() -> None:
    result = candidate("candidate-1", 2)
    with pytest.raises(DomainValidationError, match="last_touch_confirm_time"):
        replace(
            result,
            touch_count=1,
            last_touch_time=result.confirm_time,
            last_touch_confirm_time=result.confirm_time + timedelta(microseconds=1),
        )


def test_candidate_rejects_break_fact_confirmed_after_snapshot() -> None:
    result = candidate("candidate-1", 2)
    with pytest.raises(DomainValidationError, match="break_confirm_time"):
        replace(
            result,
            break_time=result.confirm_time,
            break_confirm_time=result.confirm_time + timedelta(microseconds=1),
        )


def test_candidate_with_stored_event_is_unavailable_before_snapshot_confirm() -> None:
    result = replace(
        candidate("candidate-1", 2),
        touch_count=1,
        last_touch_time=BASE + timedelta(hours=1),
        last_touch_confirm_time=BASE + timedelta(hours=1, minutes=30),
    )
    processing_time = result.confirm_time - timedelta(microseconds=1)
    assert not result.is_confirmed_at(processing_time)
    with pytest.raises(DomainAvailabilityError):
        result.require_confirmed_at(processing_time)


def test_cluster_cannot_confirm_before_latest_member() -> None:
    early = candidate("early", 1).to_boundary_ref()
    late = candidate("late", 3).to_boundary_ref()
    with pytest.raises(DomainValidationError, match="every member"):
        StructureCluster(
            "cluster-1",
            "XAUUSD",
            Timeframe.H1,
            SCALE,
            PriceRange(Decimal("2299"), Decimal("2302")),
            BoundarySide.LOWER,
            MarketRole.SUPPORT,
            LifecycleState.CONFIRMED,
            BASE,
            BASE + timedelta(hours=2),
            (early, late),
            "cluster-family",
            provenance("cluster-1"),
        )


def test_state_cannot_reference_future_boundary() -> None:
    future_upper = boundary(BoundarySide.UPPER, 4)
    with pytest.raises(DomainValidationError, match="cannot be later"):
        TimeframeState(
            "state-1",
            "v1",
            "XAUUSD",
            Timeframe.H1,
            SCALE,
            BASE,
            BASE + timedelta(hours=3),
            BASE + timedelta(hours=3),
            future_upper,
            None,
            (),
            provenance("state-1"),
        )


def test_active_box_cannot_reference_future_boundary() -> None:
    lower = boundary(BoundarySide.LOWER, 2)
    upper = boundary(BoundarySide.UPPER, 4)
    with pytest.raises(DomainValidationError, match="confirmed no later"):
        ActiveBox(
            "box-1",
            "XAUUSD",
            Timeframe.H1,
            SCALE,
            lower,
            upper,
            Decimal("2350"),
            ActiveBoxStatus.ACTIVE,
            BASE,
            BASE + timedelta(hours=3),
            BASE + timedelta(hours=3),
            None,
            None,
            provenance("box-1"),
        )


def test_active_box_rejects_freeze_fact_after_snapshot_confirm() -> None:
    lower = boundary(BoundarySide.LOWER, 2)
    upper = boundary(BoundarySide.UPPER, 2)
    with pytest.raises(DomainValidationError, match="frozen_time"):
        ActiveBox(
            "box-1",
            "XAUUSD",
            Timeframe.H1,
            SCALE,
            lower,
            upper,
            Decimal("2350"),
            ActiveBoxStatus.FROZEN,
            BASE,
            BASE + timedelta(hours=3),
            BASE + timedelta(hours=3),
            BASE + timedelta(hours=4),
            None,
            provenance("box-1"),
        )


def test_active_box_rejects_retire_fact_after_snapshot_confirm() -> None:
    lower = boundary(BoundarySide.LOWER, 2)
    upper = boundary(BoundarySide.UPPER, 2)
    with pytest.raises(DomainValidationError, match="retired_time"):
        ActiveBox(
            "box-1",
            "XAUUSD",
            Timeframe.H1,
            SCALE,
            lower,
            upper,
            Decimal("2350"),
            ActiveBoxStatus.RETIRED,
            BASE,
            BASE + timedelta(hours=3),
            BASE + timedelta(hours=3),
            None,
            BASE + timedelta(hours=4),
            provenance("box-1"),
        )


def test_active_box_state_facts_first_become_available_at_snapshot_confirm() -> None:
    lower = boundary(BoundarySide.LOWER, 2)
    upper = boundary(BoundarySide.UPPER, 2)
    confirm_time = BASE + timedelta(hours=3)
    result = ActiveBox(
        "box-1",
        "XAUUSD",
        Timeframe.H1,
        SCALE,
        lower,
        upper,
        Decimal("2350"),
        ActiveBoxStatus.RETIRED,
        BASE,
        confirm_time,
        confirm_time,
        BASE + timedelta(hours=2, minutes=30),
        confirm_time,
        provenance("box-1"),
    )
    assert not result.is_available_at(confirm_time - timedelta(microseconds=1))
    assert result.is_available_at(confirm_time)
    assert result.frozen_time <= result.retired_time <= result.confirm_time


def test_backplot_origin_change_does_not_change_confirm_time() -> None:
    result = candidate("candidate-1", 2)
    backplotted = replace(result, origin_time=BASE - timedelta(days=5))
    assert backplotted.origin_time < result.origin_time
    assert backplotted.confirm_time == result.confirm_time
    assert not backplotted.is_confirmed_at(
        result.confirm_time - timedelta(microseconds=1)
    )


def test_future_replacement_object_does_not_rewrite_boundary_snapshot() -> None:
    original = candidate("candidate-1", 2)
    snapshot = original.to_boundary_ref()
    future_version = replace(
        original,
        price_range=PriceRange(Decimal("2200"), Decimal("2201")),
        confirm_time=BASE + timedelta(hours=5),
    )
    assert future_version.price_range != snapshot.price_range
    assert snapshot.price_range == PriceRange(Decimal("2300"), Decimal("2301"))
    assert snapshot.confirm_time == BASE + timedelta(hours=2)


def test_batch_filter_matches_chronological_confirm_time_consumption() -> None:
    items = (
        candidate("late", 3),
        candidate("early", 1),
        candidate("middle", 2),
    )
    processing_times = tuple(BASE + timedelta(hours=value) for value in range(4))
    batch = {
        processing_time: tuple(
            sorted(
                item.candidate_id
                for item in items
                if item.is_confirmed_at(processing_time)
            )
        )
        for processing_time in processing_times
    }
    chronological: dict[datetime, tuple[str, ...]] = {}
    visible: list[str] = []
    ordered = sorted(items, key=lambda item: (item.confirm_time, item.candidate_id))
    for processing_time in processing_times:
        for item in ordered:
            if (
                item.confirm_time == processing_time
                and item.candidate_id not in visible
            ):
                visible.append(item.candidate_id)
        chronological[processing_time] = tuple(sorted(visible))
    assert chronological == batch


def test_domain_construction_does_not_mutate_input_snapshots() -> None:
    lower = boundary(BoundarySide.LOWER, 1)
    upper = boundary(BoundarySide.UPPER, 1)
    lower_before = lower.to_dict()
    upper_before = upper.to_dict()
    TimeframeState(
        "state-1",
        "v1",
        "XAUUSD",
        Timeframe.H1,
        SCALE,
        BASE,
        BASE + timedelta(hours=2),
        BASE + timedelta(hours=2),
        upper,
        lower,
        ("forming-b", "forming-a"),
        provenance("state-1"),
    )
    assert lower.to_dict() == lower_before
    assert upper.to_dict() == upper_before
