from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from msa.data.contracts import Timeframe
from msa.domain import (
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
    StructureObjectKind,
    StructureSourceType,
)


UTC = timezone.utc
ORIGIN = datetime(2026, 1, 5, 10, 0, tzinfo=UTC)
CONFIRM = datetime(2026, 1, 5, 11, 0, tzinfo=UTC)


def provenance() -> ProvenanceRef:
    return ProvenanceRef("tests.candidate", "1", "event-1", None, (), ())


def candidate(**overrides: object) -> LevelCandidate:
    values: dict[str, object] = {
        "candidate_id": "candidate-1",
        "symbol": "XAUUSD",
        "timeframe": Timeframe.H1,
        "scale": ScaleDescriptor("configured-primary", 1),
        "price_range": PriceRange(Decimal("2300.10"), Decimal("2301.20")),
        "source_type": StructureSourceType.SWING,
        "boundary_side": BoundarySide.LOWER,
        "market_role": MarketRole.SUPPORT,
        "confirmation_status": ConfirmationStatus.CONFIRMED,
        "lifecycle_state": LifecycleState.FRESH,
        "origin_time": ORIGIN,
        "confirm_time": CONFIRM,
        "touch_count": 0,
        "last_touch_time": None,
        "last_touch_confirm_time": None,
        "break_time": None,
        "break_confirm_time": None,
        "structure_family": "confirmed-swing",
        "provenance": provenance(),
    }
    values.update(overrides)
    return LevelCandidate(**values)  # type: ignore[arg-type]


def test_forming_candidate_is_valid_and_never_confirmed() -> None:
    forming = candidate(
        confirmation_status=ConfirmationStatus.FORMING,
        lifecycle_state=LifecycleState.CANDIDATE,
        confirm_time=None,
    )
    assert not forming.is_confirmed_at(CONFIRM + timedelta(days=10))


def test_forming_candidate_rejects_confirm_time() -> None:
    with pytest.raises(DomainValidationError, match="confirm_time must be None"):
        candidate(
            confirmation_status=ConfirmationStatus.FORMING,
            lifecycle_state=LifecycleState.CANDIDATE,
        )


def test_forming_candidate_requires_candidate_lifecycle() -> None:
    with pytest.raises(DomainValidationError, match="lifecycle_state"):
        candidate(
            confirmation_status=ConfirmationStatus.FORMING,
            confirm_time=None,
            lifecycle_state=LifecycleState.FRESH,
        )


def test_forming_candidate_cannot_become_boundary_ref() -> None:
    forming = candidate(
        confirmation_status=ConfirmationStatus.FORMING,
        lifecycle_state=LifecycleState.CANDIDATE,
        confirm_time=None,
    )
    with pytest.raises(DomainAvailabilityError, match="FORMING"):
        forming.to_boundary_ref()


def test_confirmed_candidate_requires_confirm_time() -> None:
    with pytest.raises(DomainValidationError, match="confirm_time is required"):
        candidate(confirm_time=None)


def test_confirmed_candidate_rejects_candidate_lifecycle() -> None:
    with pytest.raises(DomainValidationError, match="cannot be CANDIDATE"):
        candidate(lifecycle_state=LifecycleState.CANDIDATE)


def test_confirm_time_may_equal_origin_time() -> None:
    result = candidate(confirm_time=ORIGIN)
    assert result.confirm_time == result.origin_time


def test_confirm_time_cannot_precede_origin_time() -> None:
    with pytest.raises(DomainValidationError, match="confirm_time"):
        candidate(confirm_time=ORIGIN - timedelta(seconds=1))


@pytest.mark.parametrize("field_name", ["origin_time", "confirm_time"])
def test_candidate_rejects_naive_event_times(field_name: str) -> None:
    with pytest.raises(DomainValidationError, match="timezone-aware"):
        candidate(**{field_name: datetime(2026, 1, 5, 10, 0)})


def test_candidate_normalizes_aware_non_utc_times() -> None:
    offset = timezone(timedelta(hours=8))
    result = candidate(
        origin_time=datetime(2026, 1, 5, 18, 0, tzinfo=offset),
        confirm_time=datetime(2026, 1, 5, 19, 0, tzinfo=offset),
    )
    assert result.origin_time == ORIGIN
    assert result.confirm_time == CONFIRM
    assert result.origin_time.tzinfo is UTC


def test_candidate_first_becomes_available_at_confirm_time() -> None:
    result = candidate()
    assert not result.is_confirmed_at(CONFIRM - timedelta(microseconds=1))
    assert result.is_confirmed_at(CONFIRM)
    with pytest.raises(DomainAvailabilityError):
        result.require_confirmed_at(CONFIRM - timedelta(microseconds=1))
    assert result.require_confirmed_at(CONFIRM) is result


def test_candidate_rejects_naive_processing_time() -> None:
    with pytest.raises(DomainValidationError, match="processing_time"):
        candidate().is_confirmed_at(datetime(2026, 1, 5, 11, 0))


@pytest.mark.parametrize(
    "overrides",
    [
        {"touch_count": 0, "last_touch_time": CONFIRM},
        {"touch_count": 0, "last_touch_confirm_time": CONFIRM},
        {"touch_count": 1, "last_touch_time": CONFIRM},
        {"touch_count": 1, "last_touch_confirm_time": CONFIRM},
        {"touch_count": -1},
    ],
)
def test_touch_fields_must_match_touch_count(overrides: dict[str, object]) -> None:
    with pytest.raises(DomainValidationError, match="touch"):
        candidate(**overrides)


def test_touch_confirm_time_cannot_precede_touch_origin() -> None:
    with pytest.raises(DomainValidationError, match="last_touch_confirm_time"):
        candidate(
            touch_count=1,
            last_touch_time=CONFIRM,
            last_touch_confirm_time=CONFIRM - timedelta(seconds=1),
        )


def test_valid_touch_facts_are_preserved() -> None:
    result = candidate(
        touch_count=2,
        last_touch_time=CONFIRM,
        last_touch_confirm_time=CONFIRM + timedelta(minutes=15),
    )
    assert result.touch_count == 2
    assert result.last_touch_confirm_time == CONFIRM + timedelta(minutes=15)


@pytest.mark.parametrize(
    "overrides",
    [
        {"break_time": CONFIRM},
        {"break_confirm_time": CONFIRM},
    ],
)
def test_break_fields_must_be_present_as_a_pair(
    overrides: dict[str, object],
) -> None:
    with pytest.raises(DomainValidationError, match="break_time"):
        candidate(**overrides)


def test_break_confirm_time_cannot_precede_break_origin() -> None:
    with pytest.raises(DomainValidationError, match="break_confirm_time"):
        candidate(
            break_time=CONFIRM,
            break_confirm_time=CONFIRM - timedelta(seconds=1),
        )


def test_break_facts_do_not_automatically_change_lifecycle() -> None:
    result = candidate(
        lifecycle_state=LifecycleState.FRESH,
        break_time=CONFIRM,
        break_confirm_time=CONFIRM + timedelta(minutes=1),
    )
    assert result.lifecycle_state is LifecycleState.FRESH


def test_confirmed_candidate_converts_to_complete_boundary_snapshot() -> None:
    result = candidate()
    boundary = result.to_boundary_ref()
    assert boundary.object_kind is StructureObjectKind.LEVEL_CANDIDATE
    assert boundary.object_id == result.candidate_id
    assert boundary.confirm_time == result.confirm_time
    assert boundary.source_types == (result.source_type,)
    assert boundary.structure_families == (result.structure_family,)
    assert boundary.provenance is result.provenance


def test_candidate_is_immutable_and_keeps_provenance() -> None:
    result = candidate()
    assert result.provenance.source_object_id == "event-1"
    with pytest.raises(FrozenInstanceError):
        result.touch_count = 5  # type: ignore[misc]
