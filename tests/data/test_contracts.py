from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from msa.data import (
    CanonicalBar,
    ContractValidationError,
    IncompleteBarError,
    Timeframe,
    VolumeType,
)


UTC = timezone.utc


def make_bar(**overrides: object) -> CanonicalBar:
    values: dict[str, object] = {
        "symbol": "XAUUSD",
        "timeframe": Timeframe.M15,
        "timestamp": datetime(2026, 1, 2, 8, 0, tzinfo=UTC),
        "end_time": datetime(2026, 1, 2, 8, 15, tzinfo=UTC),
        "open": Decimal("2000.0"),
        "high": Decimal("2002.0"),
        "low": Decimal("1998.0"),
        "close": Decimal("2001.0"),
        "volume": Decimal("125"),
        "volume_type": VolumeType.TICK,
        "source": "test-feed",
        "source_timezone": "America/New_York",
        "session_id": "test-session",
        "is_complete": True,
        "available_time": datetime(2026, 1, 2, 8, 15, tzinfo=UTC),
        "boundary_policy": None,
    }
    values.update(overrides)
    return CanonicalBar(**values)


def test_valid_completed_bar_can_be_created() -> None:
    bar = make_bar()

    assert bar.symbol == "XAUUSD"
    assert bar.timestamp.tzinfo is UTC
    assert bar.is_confirmed_at(bar.available_time)


@pytest.mark.parametrize("field_name", ["timestamp", "end_time", "available_time"])
def test_timezone_naive_time_is_rejected(field_name: str) -> None:
    with pytest.raises(ContractValidationError, match="timezone-aware"):
        make_bar(**{field_name: datetime(2026, 1, 2, 8, 0)})


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"high": Decimal("1999"), "close": Decimal("1999")}, "high.*open"),
        (
            {
                "open": Decimal("1998"),
                "high": Decimal("2000"),
                "close": Decimal("2001"),
                "low": Decimal("1997"),
            },
            "high.*close",
        ),
        ({"low": Decimal("2000.5")}, "low.*open"),
        (
            {
                "open": Decimal("2001"),
                "high": Decimal("2002"),
                "low": Decimal("2000"),
                "close": Decimal("1999"),
            },
            "low.*close",
        ),
        (
            {
                "open": Decimal("2000"),
                "high": Decimal("1999"),
                "low": Decimal("2001"),
                "close": Decimal("2000"),
            },
            "high.*low",
        ),
    ],
)
def test_invalid_ohlc_relationship_is_rejected(
    overrides: dict[str, Decimal], message: str
) -> None:
    with pytest.raises(ContractValidationError, match=message):
        make_bar(**overrides)


@pytest.mark.parametrize("field_name", ["open", "high", "low", "close"])
def test_nan_price_is_rejected(field_name: str) -> None:
    with pytest.raises(ContractValidationError, match=f"{field_name} must be finite"):
        make_bar(**{field_name: Decimal("NaN")})


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("open", Decimal("Infinity")),
        ("high", Decimal("-Infinity")),
        ("low", Decimal("Infinity")),
        ("close", Decimal("-Infinity")),
    ],
)
def test_infinite_price_is_rejected(field_name: str, value: Decimal) -> None:
    with pytest.raises(ContractValidationError, match=f"{field_name} must be finite"):
        make_bar(**{field_name: value})


def test_negative_volume_is_rejected() -> None:
    with pytest.raises(ContractValidationError, match="greater than or equal to 0"):
        make_bar(volume=Decimal("-1"))


def test_volume_none_is_allowed_when_unavailable() -> None:
    bar = make_bar(volume=None, volume_type=VolumeType.UNAVAILABLE)

    assert bar.volume is None
    assert bar.volume_type is VolumeType.UNAVAILABLE


def test_volume_zero_is_an_observed_value() -> None:
    bar = make_bar(volume=Decimal("0"), volume_type=VolumeType.REAL)

    assert bar.volume == Decimal("0")
    assert bar.volume is not None


def test_real_and_tick_volume_remain_distinct() -> None:
    real = make_bar(volume_type=VolumeType.REAL)
    tick = make_bar(volume_type=VolumeType.TICK)

    assert real.volume_type is VolumeType.REAL
    assert tick.volume_type is VolumeType.TICK
    assert real != tick


def test_none_volume_requires_unavailable_type() -> None:
    with pytest.raises(ContractValidationError, match="requires"):
        make_bar(volume=None, volume_type=VolumeType.TICK)


def test_unavailable_type_requires_none_volume() -> None:
    with pytest.raises(ContractValidationError, match="requires volume=None"):
        make_bar(volume=Decimal("0"), volume_type=VolumeType.UNAVAILABLE)


def test_incomplete_bar_cannot_be_confirmed() -> None:
    bar = make_bar(
        is_complete=False,
        available_time=datetime(2026, 1, 2, 8, 7, tzinfo=UTC),
    )

    assert not bar.is_confirmed_at(datetime(2026, 1, 2, 9, 0, tzinfo=UTC))
    with pytest.raises(IncompleteBarError, match="incomplete"):
        bar.require_confirmed(datetime(2026, 1, 2, 9, 0, tzinfo=UTC))


def test_completed_bar_available_before_end_is_rejected() -> None:
    with pytest.raises(ContractValidationError, match="available_time"):
        make_bar(available_time=datetime(2026, 1, 2, 8, 14, tzinfo=UTC))


def test_completed_bar_is_not_confirmed_before_available_time() -> None:
    bar = make_bar(available_time=datetime(2026, 1, 2, 8, 16, tzinfo=UTC))

    assert not bar.is_confirmed_at(datetime(2026, 1, 2, 8, 15, tzinfo=UTC))
    with pytest.raises(ContractValidationError, match="not available"):
        bar.require_confirmed(datetime(2026, 1, 2, 8, 15, tzinfo=UTC))


def test_timezone_aware_non_utc_input_is_normalized_to_utc() -> None:
    plus_two = timezone(timedelta(hours=2))
    bar = make_bar(
        timestamp=datetime(2026, 1, 2, 10, 0, tzinfo=plus_two),
        end_time=datetime(2026, 1, 2, 10, 15, tzinfo=plus_two),
        available_time=datetime(2026, 1, 2, 10, 15, tzinfo=plus_two),
    )

    assert bar.timestamp == datetime(2026, 1, 2, 8, 0, tzinfo=UTC)
    assert bar.source_timezone == "America/New_York"


def test_supported_timeframe_enum_is_stable() -> None:
    assert [timeframe.value for timeframe in Timeframe] == [
        "M15",
        "M30",
        "H1",
        "H2",
        "H4",
        "H12",
        "D",
        "W",
    ]


@pytest.mark.parametrize(
    ("timeframe", "duration"),
    [
        (Timeframe.M15, timedelta(minutes=15)),
        (Timeframe.M30, timedelta(minutes=30)),
        (Timeframe.H1, timedelta(hours=1)),
        (Timeframe.H2, timedelta(hours=2)),
        (Timeframe.H4, timedelta(hours=4)),
        (Timeframe.H12, timedelta(hours=12)),
    ],
)
def test_fixed_timeframe_duration_is_correct(
    timeframe: Timeframe, duration: timedelta
) -> None:
    assert timeframe.is_fixed_duration
    assert timeframe.fixed_duration == duration
    assert not timeframe.requires_boundary_policy


@pytest.mark.parametrize("timeframe", [Timeframe.D, Timeframe.W])
def test_daily_and_weekly_require_boundary_policy(timeframe: Timeframe) -> None:
    assert not timeframe.is_fixed_duration
    assert timeframe.fixed_duration is None
    assert timeframe.requires_boundary_policy


@pytest.mark.parametrize("timeframe", [Timeframe.D, Timeframe.W])
def test_calendar_bar_without_boundary_policy_is_rejected(
    timeframe: Timeframe,
) -> None:
    with pytest.raises(ContractValidationError, match="boundary_policy"):
        make_bar(
            timeframe=timeframe,
            end_time=datetime(2026, 1, 3, 8, 0, tzinfo=UTC),
            available_time=datetime(2026, 1, 3, 8, 0, tzinfo=UTC),
        )


def test_calendar_bar_accepts_explicit_external_boundary() -> None:
    bar = make_bar(
        timeframe=Timeframe.D,
        end_time=datetime(2026, 1, 3, 7, 0, tzinfo=UTC),
        available_time=datetime(2026, 1, 3, 7, 1, tzinfo=UTC),
        boundary_policy="broker-session-v1",
    )

    assert bar.end_time == datetime(2026, 1, 3, 7, 0, tzinfo=UTC)
    assert bar.boundary_policy == "broker-session-v1"


def test_fixed_timeframe_rejects_inconsistent_end_time() -> None:
    with pytest.raises(ContractValidationError, match="end_time must equal"):
        make_bar(end_time=datetime(2026, 1, 2, 8, 16, tzinfo=UTC))


def test_serialization_round_trip_preserves_contract() -> None:
    original = make_bar(
        volume=None,
        volume_type=VolumeType.UNAVAILABLE,
        is_complete=False,
        available_time=datetime(2026, 1, 2, 8, 7, tzinfo=UTC),
    )

    restored = CanonicalBar.from_dict(original.to_dict())

    assert restored == original
    assert restored.timestamp.tzinfo is UTC
    assert restored.available_time.tzinfo is UTC
    assert restored.timeframe is Timeframe.M15
    assert restored.volume_type is VolumeType.UNAVAILABLE
    assert not restored.is_complete
    assert restored.source_timezone == "America/New_York"


def test_canonical_bar_is_immutable() -> None:
    bar = make_bar()

    with pytest.raises(FrozenInstanceError):
        bar.close = Decimal("2100")  # type: ignore[misc]


@pytest.mark.parametrize("field_name", ["symbol", "source", "source_timezone"])
def test_required_text_field_cannot_be_empty(field_name: str) -> None:
    with pytest.raises(ContractValidationError, match=field_name):
        make_bar(**{field_name: "  "})
