from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from msa.data import (
    AlignmentConfigurationError,
    CanonicalBar,
    CompletedBarPolicy,
    ContractValidationError,
    CoveragePolicy,
    DataLoadError,
    ExplicitBoundary,
    ExplicitBoundarySchedule,
    ExplicitFixedAnchorPolicy,
    ResampleConfig,
    ResampleConfigurationError,
    ResampleError,
    SessionIdPolicy,
    SourceConfigurationError,
    Timeframe,
    TimestampSemantics,
    VolumeType,
    load_csv,
    load_records,
    resample_load_result,
)

from tests.audit.fixtures import (
    START,
    UTC,
    fixed_config,
    load_indices,
    records_for_indices,
    source_config,
    utc_text,
)


def canonical_bar(**overrides: object) -> CanonicalBar:
    values: dict[str, object] = {
        "symbol": "XAUUSD",
        "timeframe": Timeframe.M15,
        "timestamp": START,
        "end_time": START + timedelta(minutes=15),
        "open": Decimal("2000"),
        "high": Decimal("2003"),
        "low": Decimal("1998"),
        "close": Decimal("2001"),
        "volume": Decimal("0"),
        "volume_type": VolumeType.TICK,
        "source": "c001d-audit-feed",
        "source_timezone": "UTC",
        "session_id": "audit-session",
        "boundary_policy": None,
        "is_complete": True,
        "available_time": START + timedelta(minutes=15),
    }
    values.update(overrides)
    return CanonicalBar(**values)


@pytest.mark.parametrize("actual_minutes", [10, 20])
def test_fixed_canonical_bar_rejects_declared_m15_interval_mismatch(
    actual_minutes: int,
) -> None:
    with pytest.raises(ContractValidationError, match="end_time must equal"):
        canonical_bar(end_time=START + timedelta(minutes=actual_minutes))


@pytest.mark.parametrize("field", ["timestamp", "end_time", "available_time"])
def test_canonical_time_fields_reject_naive_values(field: str) -> None:
    naive = datetime(2026, 2, 2, 8, 0)
    with pytest.raises(ContractValidationError, match="timezone-aware"):
        canonical_bar(**{field: naive})


def test_canonical_normalizes_utc_without_conflating_three_times() -> None:
    plus_two = timezone(timedelta(hours=2))
    bar = canonical_bar(
        timestamp=datetime(2026, 2, 2, 10, 0, tzinfo=plus_two),
        end_time=datetime(2026, 2, 2, 10, 15, tzinfo=plus_two),
        available_time=datetime(2026, 2, 2, 10, 17, tzinfo=plus_two),
        source_timezone="+02:00",
    )

    assert bar.timestamp == START
    assert bar.end_time == START + timedelta(minutes=15)
    assert bar.available_time == START + timedelta(minutes=17)
    assert len({bar.timestamp, bar.end_time, bar.available_time}) == 3


@pytest.mark.parametrize(
    "overrides",
    [
        {"open": Decimal("NaN")},
        {"high": Decimal("Infinity")},
        {"low": Decimal("-Infinity")},
        {"high": Decimal("1999")},
        {"volume": Decimal("NaN")},
        {"volume": Decimal("-1")},
    ],
)
def test_canonical_rejects_nonfinite_or_illegal_ohlcv(
    overrides: dict[str, Decimal],
) -> None:
    with pytest.raises(ContractValidationError):
        canonical_bar(**overrides)


def test_incomplete_snapshot_is_observable_but_never_confirmed() -> None:
    forming = canonical_bar(
        is_complete=False,
        available_time=START + timedelta(minutes=5),
    )

    assert forming.available_time < forming.end_time
    assert not forming.is_confirmed_at(START + timedelta(days=1))


def test_volume_none_zero_roundtrip_and_canonical_immutability() -> None:
    unavailable = canonical_bar(volume=None, volume_type=VolumeType.UNAVAILABLE)
    observed_zero = canonical_bar(volume=Decimal("0"), volume_type=VolumeType.REAL)

    assert CanonicalBar.from_dict(unavailable.to_dict()) == unavailable
    assert CanonicalBar.from_dict(observed_zero.to_dict()) == observed_zero
    assert unavailable.volume is None
    assert observed_zero.volume == Decimal("0")
    with pytest.raises(FrozenInstanceError):
        observed_zero.close = Decimal("9999")  # type: ignore[misc]


@pytest.mark.parametrize("timeframe", [Timeframe.D, Timeframe.W])
def test_calendar_canonical_bar_requires_named_boundary_policy(
    timeframe: Timeframe,
) -> None:
    with pytest.raises(ContractValidationError, match="boundary_policy"):
        canonical_bar(
            timeframe=timeframe,
            end_time=START + timedelta(hours=23),
            available_time=START + timedelta(hours=23),
        )


def test_loader_open_and_close_semantics_produce_same_utc_interval() -> None:
    open_result = load_indices(range(1))
    close_result = load_indices(
        range(1), timestamp_semantics=TimestampSemantics.CLOSE_TIME
    )

    assert open_result.bars[0].timestamp == close_result.bars[0].timestamp == START
    assert open_result.bars[0].end_time == close_result.bars[0].end_time


def test_loader_close_time_accepts_matching_fixed_utc_offset() -> None:
    config = source_config(
        timestamp_semantics=TimestampSemantics.CLOSE_TIME,
        source_timezone="+02:00",
    )
    record = records_for_indices(range(1))[0]
    record["time"] = "2026-02-02T10:15:00+0200"
    record["observed"] = "2026-02-02T10:15:00+0200"

    bar = load_records([record], config).bars[0]

    assert bar.timestamp == START
    assert bar.end_time == START + timedelta(minutes=15)


def test_loader_localizes_iana_zone_and_validates_embedded_offset() -> None:
    local_config = replace(
        source_config(source_timezone="America/New_York"),
        timestamp_format="%Y-%m-%d %H:%M:%S",
    )
    local_record = records_for_indices(range(1))[0]
    local_record["time"] = "2026-02-02 03:00:00"
    local_record["observed"] = "2026-02-02 03:15:00"

    loaded = load_records([local_record], local_config)
    assert loaded.bars[0].timestamp == START

    offset_config = replace(
        local_config,
        timestamp_format="%Y-%m-%d %H:%M:%S%z",
    )
    local_record["time"] = "2026-02-02 03:00:00+0200"
    with pytest.raises(DataLoadError, match="conflicts"):
        load_records([local_record], offset_config)


@pytest.mark.parametrize(
    ("raw_time", "reason"),
    [
        ("2026-11-01 01:30:00", "ambiguous"),
        ("2026-03-08 02:30:00", "does not exist"),
    ],
)
def test_loader_rejects_dst_ambiguity_and_nonexistence(
    raw_time: str, reason: str
) -> None:
    config = replace(
        source_config(source_timezone="America/New_York"),
        timestamp_format="%Y-%m-%d %H:%M:%S",
    )
    record = records_for_indices(range(1))[0]
    record["time"] = raw_time
    record["observed"] = "2026-11-01 03:00:00"

    with pytest.raises(DataLoadError, match=reason):
        load_records([record], config)


def test_loader_requires_observed_time_and_nonnegative_lag() -> None:
    with pytest.raises(SourceConfigurationError, match="observed_time_column"):
        replace(source_config(), observed_time_column=None)
    with pytest.raises(SourceConfigurationError, match="greater than or equal"):
        replace(source_config(), availability_lag=timedelta(microseconds=-1))


def test_incomplete_availability_uses_only_its_explicit_observation() -> None:
    records = records_for_indices(
        range(2),
        delays=(timedelta(minutes=5), timedelta(minutes=3)),
        complete="forming",
    )
    result = load_records(records, source_config())

    assert result.bars[0].available_time == START + timedelta(minutes=5)
    assert result.bars[0].available_time != result.bars[1].timestamp
    assert result.bars[0].available_time != result.bars[-1].end_time
    assert not result.bars[0].is_complete


def test_loader_rejects_explicit_fixed_interval_mismatch_with_row_context() -> None:
    config = replace(source_config(), end_time_column="end")
    record = records_for_indices(range(1))[0]
    record["end"] = utc_text(START + timedelta(minutes=10))

    with pytest.raises(DataLoadError) as exc_info:
        load_records([record], config)

    issue = exc_info.value.report.errors[0]
    assert issue.row_number == 1
    assert issue.field == "time"
    assert "end_time must equal" in issue.reason


def test_loader_calendar_bar_requires_and_preserves_explicit_boundary() -> None:
    with pytest.raises(SourceConfigurationError, match="boundary_policy"):
        replace(source_config(), timeframe=Timeframe.D)

    config = replace(
        source_config(),
        timeframe=Timeframe.D,
        end_time_column="end",
        boundary_policy="c001d-dst-session-v1",
    )
    record = records_for_indices(range(1))[0]
    record["end"] = utc_text(START + timedelta(hours=23))
    record["observed"] = record["end"]
    bar = load_records([record], config).bars[0]

    assert bar.end_time - bar.timestamp == timedelta(hours=23)
    assert bar.boundary_policy == "c001d-dst-session-v1"


@pytest.mark.parametrize(
    ("attack", "expected_code"),
    [
        ("duplicate", "duplicate"),
        ("conflict", "conflicting_duplicate"),
        ("out_of_order", "out_of_order"),
        ("overlap", "interval_overlap"),
    ],
)
def test_loader_quality_attacks_fail_closed_without_repair(
    attack: str, expected_code: str
) -> None:
    records = records_for_indices(range(2))
    if attack == "duplicate":
        records = [records[0], dict(records[0])]
    elif attack == "conflict":
        conflict = dict(records[0])
        conflict["high"] = Decimal("2100")
        records = [records[0], conflict]
    elif attack == "out_of_order":
        records.reverse()
    else:
        records[1]["time"] = utc_text(START + timedelta(minutes=5))
        records[1]["observed"] = utc_text(START + timedelta(minutes=20))

    with pytest.raises(DataLoadError) as exc_info:
        load_records(records, source_config())

    assert expected_code in {issue.code for issue in exc_info.value.report.errors}
    assert exc_info.value.report.errors[0].row_number >= 1
    assert exc_info.value.report.errors[0].field


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("high", Decimal("NaN")),
        ("volume", Decimal("Infinity")),
        ("time", "not-a-time"),
        ("symbol", "XAUUSD"),
    ],
)
def test_loader_invalid_fields_are_rejected_with_field_context(
    field: str, value: object
) -> None:
    record = records_for_indices(range(1))[0]
    record[field] = value

    with pytest.raises(DataLoadError) as exc_info:
        load_records([record], source_config())

    issue = exc_info.value.report.errors[0]
    assert issue.row_number == 1
    assert issue.field
    assert issue.reason


def test_loader_reports_gap_but_never_synthesizes_missing_bar() -> None:
    result = load_indices((0, 2))

    assert result.quality_report.gap_count == 1
    assert len(result.bars) == 2
    assert [bar.timestamp for bar in result.bars] == [
        START,
        START + timedelta(minutes=30),
    ]


def test_report_only_errors_cannot_enter_resampling() -> None:
    record = records_for_indices(range(1))[0]
    record["high"] = Decimal("NaN")
    report_only = load_records([record], source_config(strict=False))

    assert report_only.quality_report.has_errors
    with pytest.raises(ResampleError, match="quality_report"):
        resample_load_result(report_only, fixed_config(Timeframe.H1))


def test_loader_input_and_earlier_bars_are_invariant_to_future_append() -> None:
    records = records_for_indices(range(8))
    before = deepcopy(records)

    prefix = load_records(records[:4], source_config())
    extended = load_records(records, source_config())

    assert records == before
    assert prefix.bars == extended.bars[:4]


def test_csv_input_is_read_only_and_header_errors_are_explicit(
    tmp_path: Path,
) -> None:
    valid = tmp_path / "audit-valid.csv"
    valid.write_text(
        "time,symbol,open,high,low,close,volume,complete,observed\n"
        "2026-02-02T08:00:00+0000,GOLD,2000,2003,1998,2001,1,closed,"
        "2026-02-02T08:15:00+0000\n",
        encoding="utf-8",
    )
    before = valid.read_bytes()

    result = load_csv(valid, source_config())

    assert result.accepted_row_count == 1
    assert valid.read_bytes() == before

    missing = tmp_path / "audit-missing-high.csv"
    missing.write_text(
        "time,symbol,open,low,close,volume,complete,observed\n",
        encoding="utf-8",
    )
    with pytest.raises(DataLoadError) as exc_info:
        load_csv(missing, source_config())
    assert exc_info.value.report.errors[0].field == "header"
    assert "high" in exc_info.value.report.errors[0].reason


@pytest.mark.parametrize(
    ("source", "target", "member_count"),
    [
        (Timeframe.M15, Timeframe.M30, 2),
        (Timeframe.M15, Timeframe.H1, 4),
        (Timeframe.M15, Timeframe.H2, 8),
        (Timeframe.M15, Timeframe.H4, 16),
        (Timeframe.M15, Timeframe.H12, 48),
        (Timeframe.H1, Timeframe.H2, 2),
        (Timeframe.H1, Timeframe.H4, 4),
    ],
)
def test_fixed_resampling_matrix_is_complete_and_decimal(
    source: Timeframe, target: Timeframe, member_count: int
) -> None:
    loaded = load_indices(range(member_count), timeframe=source)
    result = resample_load_result(
        loaded, fixed_config(target, source=source)
    )
    bar = result.bars[0]

    assert bar.timestamp == START
    assert bar.end_time == START + target.fixed_duration
    assert bar.open == loaded.bars[0].open
    assert bar.close == loaded.bars[-1].close
    assert bar.high == max(item.high for item in loaded.bars)
    assert bar.low == min(item.low for item in loaded.bars)
    assert bar.volume == sum(
        (item.volume for item in loaded.bars if item.volume is not None),
        Decimal(0),
    )
    assert all(
        isinstance(value, Decimal)
        for value in (bar.open, bar.high, bar.low, bar.close, bar.volume)
    )


def test_resample_config_rejects_implicit_or_contradictory_boundaries() -> None:
    policy = ExplicitFixedAnchorPolicy("audit-m30", START, Timeframe.M30)
    with pytest.raises(ResampleConfigurationError, match="strictly greater"):
        ResampleConfig(
            source_timeframe=Timeframe.M30,
            target_timeframe=Timeframe.M30,
            alignment_policy=policy,
            coverage_policy=CoveragePolicy.CONTIGUOUS_FIXED,
            publication_lag=timedelta(0),
            policy_id=policy.policy_id,
            session_id_policy=SessionIdPolicy.EXPLICIT,
        )
    with pytest.raises(ResampleConfigurationError, match="explicit"):
        replace(fixed_config(Timeframe.H1), alignment_policy=None)
    with pytest.raises(ResampleConfigurationError, match="policy_id"):
        replace(fixed_config(Timeframe.H1), policy_id="different-policy")


def test_anchor_and_nonintegral_source_duration_attacks_are_rejected() -> None:
    with pytest.raises(AlignmentConfigurationError, match="timezone-aware"):
        ExplicitFixedAnchorPolicy(
            "naive", datetime(2026, 2, 2, 8), Timeframe.H1
        )
    with pytest.raises(AlignmentConfigurationError, match="must be UTC"):
        ExplicitFixedAnchorPolicy(
            "non-utc",
            datetime(2026, 2, 2, 8, tzinfo=timezone(timedelta(hours=1))),
            Timeframe.H1,
        )
    policy = ExplicitFixedAnchorPolicy("audit-h1", START, Timeframe.H1)
    with pytest.raises(AlignmentConfigurationError, match="integer multiple"):
        policy.bucket_for(START, timedelta(minutes=40))


@pytest.mark.parametrize(
    "indices",
    [
        (0, 1, 3, 4, 5, 6, 7),
        (1, 2, 3, 4, 5, 6, 7),
        (0, 1, 2, 3, 8, 9, 10, 11),
    ],
)
def test_internal_leading_and_empty_bucket_gaps_fail_strict_coverage(
    indices: tuple[int, ...],
) -> None:
    with pytest.raises(ResampleError) as exc_info:
        resample_load_result(
            load_indices(indices), fixed_config(Timeframe.H1)
        )

    assert exc_info.value.report.missing_slot_count > 0
    assert exc_info.value.report.output_bar_count >= 0


def test_terminal_trailing_bucket_is_warning_and_never_emitted() -> None:
    result = resample_load_result(
        load_indices((0, 1)), fixed_config(Timeframe.H1)
    )

    assert result.bars == ()
    assert result.report.incomplete_bucket_count == 1
    assert result.report.warnings
    assert not result.report.errors


def test_misaligned_source_slots_and_crossing_interval_are_rejected() -> None:
    shifted_start = START + timedelta(minutes=5)
    with pytest.raises(ResampleError) as exc_info:
        resample_load_result(
            load_indices(range(4), start=shifted_start),
            fixed_config(Timeframe.H1),
        )

    report = exc_info.value.report
    assert report.misaligned_bar_count > 0
    assert report.cross_boundary_count > 0


@pytest.mark.parametrize("field", ["symbol", "source", "source_timezone", "volume_type"])
def test_mixed_source_identity_is_rejected(field: str) -> None:
    loaded = load_indices(range(4))
    bars = list(loaded.bars)
    value: object = {
        "symbol": "XAGUSD",
        "source": "other-feed",
        "source_timezone": "+02:00",
        "volume_type": VolumeType.REAL,
    }[field]
    bars[2] = replace(bars[2], **{field: value})
    forged = replace(loaded, bars=tuple(bars))

    with pytest.raises(ResampleError, match=field):
        resample_load_result(forged, fixed_config(Timeframe.H1))


def test_mixed_source_timeframe_is_rejected() -> None:
    loaded = load_indices(range(4))
    bars = list(loaded.bars)
    original = bars[2]
    bars[2] = CanonicalBar(
        symbol=original.symbol,
        timeframe=Timeframe.M30,
        timestamp=original.timestamp,
        end_time=original.timestamp + timedelta(minutes=30),
        open=original.open,
        high=original.high,
        low=original.low,
        close=original.close,
        volume=original.volume,
        volume_type=original.volume_type,
        source=original.source,
        source_timezone=original.source_timezone,
        session_id=original.session_id,
        boundary_policy=None,
        is_complete=True,
        available_time=original.timestamp + timedelta(minutes=30),
    )

    with pytest.raises(ResampleError, match="timeframe"):
        resample_load_result(
            replace(loaded, bars=tuple(bars)), fixed_config(Timeframe.H1)
        )


def test_incomplete_source_bar_is_rejected_from_confirmed_resampling() -> None:
    loaded = load_indices(range(4))
    bars = list(loaded.bars)
    bars[2] = replace(
        bars[2],
        is_complete=False,
        available_time=bars[2].timestamp + timedelta(minutes=5),
    )

    with pytest.raises(ResampleError, match="incomplete"):
        resample_load_result(
            replace(loaded, bars=tuple(bars)), fixed_config(Timeframe.H1)
        )


def calendar_config(
    target: Timeframe,
    boundaries: tuple[ExplicitBoundary, ...],
) -> ResampleConfig:
    policy_id = f"c001d-{target.value.lower()}-synthetic-v1"
    schedule = ExplicitBoundarySchedule(policy_id, target, boundaries)
    return ResampleConfig(
        source_timeframe=Timeframe.M15,
        target_timeframe=target,
        alignment_policy=schedule,
        coverage_policy=CoveragePolicy.EXPLICIT_EXPECTED_SLOTS,
        publication_lag=timedelta(seconds=7),
        policy_id=policy_id,
        session_id_policy=SessionIdPolicy.INHERIT_IF_UNANIMOUS_ELSE_NONE,
    )


@pytest.mark.parametrize(
    ("target", "duration"),
    [
        (Timeframe.D, timedelta(hours=23)),
        (Timeframe.W, timedelta(days=5, hours=12)),
    ],
)
def test_calendar_schedule_does_not_assume_24_hour_day_or_7_day_week(
    target: Timeframe, duration: timedelta
) -> None:
    expected = (START, START + timedelta(minutes=15), START + timedelta(minutes=45))
    boundary = ExplicitBoundary(START, START + duration, expected)
    result = resample_load_result(
        load_indices((0, 1, 3)), calendar_config(target, (boundary,))
    )

    assert result.bars[0].end_time == START + duration
    assert result.bars[0].boundary_policy == result.config.policy_id
    assert result.bars[0].available_time == START + duration + timedelta(seconds=7)


def test_calendar_schedule_rejects_duplicate_unordered_and_overlapping_rules() -> None:
    with pytest.raises(AlignmentConfigurationError, match="ascending and unique"):
        ExplicitBoundary(
            START,
            START + timedelta(hours=1),
            (START, START),
        )
    first = ExplicitBoundary(START, START + timedelta(hours=2), (START,))
    second = ExplicitBoundary(
        START + timedelta(hours=1),
        START + timedelta(hours=3),
        (START + timedelta(hours=1),),
    )
    with pytest.raises(AlignmentConfigurationError, match="overlap"):
        ExplicitBoundarySchedule("overlap", Timeframe.D, (first, second))
    later = ExplicitBoundary(
        START + timedelta(hours=3),
        START + timedelta(hours=4),
        (START + timedelta(hours=3),),
    )
    with pytest.raises(AlignmentConfigurationError, match="ordered"):
        ExplicitBoundarySchedule("unordered", Timeframe.D, (later, first))


def test_calendar_cross_boundary_member_and_outside_member_are_rejected() -> None:
    boundary = ExplicitBoundary(
        START,
        START + timedelta(minutes=50),
        (START, START + timedelta(minutes=15), START + timedelta(minutes=30)),
    )
    config = calendar_config(Timeframe.D, (boundary,))

    with pytest.raises(ResampleError) as crossing:
        resample_load_result(load_indices(range(4)), config)
    assert crossing.value.report.cross_boundary_count == 1

    with pytest.raises(ResampleError, match="outside"):
        resample_load_result(load_indices((8,)), config)


def test_session_conflict_is_explicitly_cleared_and_input_is_immutable() -> None:
    loaded = load_indices(range(4))
    bars = list(loaded.bars)
    bars[1] = replace(bars[1], session_id="other-session")
    forged = replace(loaded, bars=tuple(bars))
    before = tuple(bar.to_dict() for bar in forged.bars)

    result = resample_load_result(forged, fixed_config(Timeframe.H1))

    assert result.bars[0].session_id is None
    assert any("explicitly cleared" in item for item in result.report.warnings)
    assert tuple(bar.to_dict() for bar in forged.bars) == before
    assert result.bars[0].boundary_policy == result.config.policy_id
