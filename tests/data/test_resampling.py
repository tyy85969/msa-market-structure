from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from msa.data import (
    AlignmentConfigurationError,
    BucketStatus,
    CanonicalBar,
    CompletedBarPolicy,
    CoveragePolicy,
    ExplicitBoundary,
    ExplicitBoundarySchedule,
    ExplicitFixedAnchorPolicy,
    LoadResult,
    ResampleConfig,
    ResampleConfigurationError,
    ResampleError,
    SessionIdPolicy,
    SourceDataConfig,
    Timeframe,
    TimestampSemantics,
    VolumeType,
    resample_as_of,
    resample_load_result,
    validate_bar_sequence,
)


UTC = timezone.utc
START = datetime(2026, 1, 2, 8, 0, tzinfo=UTC)


def source_bar(
    index: int,
    *,
    start: datetime = START,
    timeframe: Timeframe = Timeframe.M15,
    volume_type: VolumeType = VolumeType.TICK,
    available_time: datetime | None = None,
    is_complete: bool = True,
    source: str = "synthetic-feed",
    source_timezone: str = "UTC",
    session_id: str | None = "session-a",
    price_offset: Decimal = Decimal(0),
) -> CanonicalBar:
    duration = timeframe.fixed_duration
    assert duration is not None
    timestamp = start + index * duration
    end_time = timestamp + duration
    opening = Decimal(2000 + index) + price_offset
    volume = None if volume_type is VolumeType.UNAVAILABLE else Decimal(index + 1)
    return CanonicalBar(
        symbol="XAUUSD",
        timeframe=timeframe,
        timestamp=timestamp,
        end_time=end_time,
        open=opening,
        high=opening + Decimal(3),
        low=opening - Decimal(2),
        close=opening + Decimal(1),
        volume=volume,
        volume_type=volume_type,
        source=source,
        source_timezone=source_timezone,
        session_id=session_id,
        boundary_policy=None,
        is_complete=is_complete,
        available_time=available_time or end_time,
    )


def source_bars(count: int, **kwargs: object) -> tuple[CanonicalBar, ...]:
    return tuple(source_bar(index, **kwargs) for index in range(count))


def source_config_for(
    bars: tuple[CanonicalBar, ...], *, strict: bool = True
) -> SourceDataConfig:
    first = bars[0]
    volume_column = (
        None if first.volume_type is VolumeType.UNAVAILABLE else "volume"
    )
    return SourceDataConfig(
        source=first.source,
        source_timezone=first.source_timezone,
        source_symbol="GOLD",
        canonical_symbol=first.symbol,
        timeframe=first.timeframe,
        timestamp_column="time",
        timestamp_semantics=TimestampSemantics.OPEN_TIME,
        timestamp_format="%Y-%m-%dT%H:%M:%S%z",
        open_column="open",
        high_column="high",
        low_column="low",
        close_column="close",
        volume_column=volume_column,
        volume_type=first.volume_type,
        completed_bar_policy=CompletedBarPolicy.ALL_ROWS_ARE_CLOSED,
        availability_lag=timedelta(0),
        session_id=None,
        boundary_policy=None,
        end_time_column=None,
        strict=strict,
    )


def load_result_for(
    bars: tuple[CanonicalBar, ...], *, strict_config: bool = True
) -> LoadResult:
    first = bars[0]
    report = validate_bar_sequence(
        bars,
        source=first.source,
        timeframe=first.timeframe,
    )
    return LoadResult(
        bars=bars,
        quality_report=report,
        source_config=source_config_for(bars, strict=strict_config),
        loaded_row_count=len(bars),
        accepted_row_count=len(bars),
        rejected_row_count=0,
    )


def fixed_config(
    target: Timeframe = Timeframe.H1,
    *,
    source: Timeframe = Timeframe.M15,
    anchor: datetime = START,
    publication_lag: timedelta = timedelta(0),
    strict: bool = True,
    session_id_policy: SessionIdPolicy = (
        SessionIdPolicy.INHERIT_IF_UNANIMOUS_ELSE_NONE
    ),
    output_session_id: str | None = None,
) -> ResampleConfig:
    policy_id = f"fixed-{target.value.lower()}-test-v1"
    policy = ExplicitFixedAnchorPolicy(
        policy_id=policy_id,
        anchor=anchor,
        target_timeframe=target,
    )
    return ResampleConfig(
        source_timeframe=source,
        target_timeframe=target,
        alignment_policy=policy,
        coverage_policy=CoveragePolicy.CONTIGUOUS_FIXED,
        publication_lag=publication_lag,
        policy_id=policy_id,
        session_id_policy=session_id_policy,
        output_session_id=output_session_id,
        strict=strict,
    )


@pytest.mark.parametrize(
    ("target", "member_count"),
    [
        (Timeframe.M30, 2),
        (Timeframe.H1, 4),
        (Timeframe.H2, 8),
        (Timeframe.H4, 16),
        (Timeframe.H12, 48),
    ],
)
def test_m15_fixed_target_ohlc_is_aggregated_correctly(
    target: Timeframe, member_count: int
) -> None:
    bars = source_bars(member_count)

    result = resample_load_result(load_result_for(bars), fixed_config(target))

    target_bar = result.bars[0]
    assert target_bar.timestamp == START
    assert target_bar.end_time == START + target.fixed_duration
    assert target_bar.open == bars[0].open
    assert target_bar.close == bars[-1].close
    assert target_bar.high == max(bar.high for bar in bars)
    assert target_bar.low == min(bar.low for bar in bars)
    assert all(isinstance(value, Decimal) for value in (
        target_bar.open,
        target_bar.high,
        target_bar.low,
        target_bar.close,
    ))


def test_fixed_resampling_is_not_hard_coded_to_m15_source() -> None:
    bars = source_bars(2, timeframe=Timeframe.H1)

    result = resample_load_result(
        load_result_for(bars),
        fixed_config(Timeframe.H2, source=Timeframe.H1),
    )

    assert len(result.bars) == 1
    assert result.bars[0].timeframe is Timeframe.H2


@pytest.mark.parametrize("volume_type", [VolumeType.REAL, VolumeType.TICK])
def test_real_and_tick_volume_are_summed_without_relabeling(
    volume_type: VolumeType,
) -> None:
    bars = source_bars(4, volume_type=volume_type)

    target = resample_load_result(
        load_result_for(bars), fixed_config()
    ).bars[0]

    assert target.volume == Decimal(10)
    assert target.volume_type is volume_type


def test_unavailable_volume_remains_none_not_zero() -> None:
    bars = source_bars(4, volume_type=VolumeType.UNAVAILABLE)

    target = resample_load_result(
        load_result_for(bars), fixed_config()
    ).bars[0]

    assert target.volume is None
    assert target.volume_type is VolumeType.UNAVAILABLE


def test_explicit_anchor_controls_bucket_boundaries() -> None:
    bars = source_bars(8)
    midnight_independent = fixed_config(anchor=START)
    shifted = fixed_config(
        anchor=START + timedelta(minutes=30), strict=False
    )

    first = resample_load_result(load_result_for(bars), midnight_independent)
    second = resample_load_result(load_result_for(bars), shifted)

    assert {bar.timestamp for bar in first.bars} == {
        START,
        START + timedelta(hours=1),
    }
    assert {bar.timestamp for bar in second.bars} == {
        START + timedelta(minutes=30)
    }


def test_non_midnight_anchor_is_preserved_and_recorded() -> None:
    anchor = datetime(2026, 1, 2, 8, 30, tzinfo=UTC)
    config = fixed_config(anchor=anchor)
    bars = source_bars(4, start=anchor)

    result = resample_load_result(load_result_for(bars), config)

    assert config.alignment_policy.anchor == anchor
    assert result.bars[0].timestamp == anchor
    assert result.bars[0].boundary_policy == config.policy_id


def test_first_source_bar_is_not_used_as_an_implicit_anchor() -> None:
    bars = source_bars(3, start=START + timedelta(minutes=15))
    config = fixed_config(anchor=START, strict=False)

    result = resample_load_result(load_result_for(bars), config)

    audit = result.report.bucket_audits[0]
    assert audit.start_time == START
    assert audit.status is BucketStatus.INCOMPLETE
    assert result.bars == ()


def test_naive_fixed_anchor_is_rejected() -> None:
    with pytest.raises(AlignmentConfigurationError, match="timezone-aware UTC"):
        ExplicitFixedAnchorPolicy(
            policy_id="naive-anchor",
            anchor=datetime(2026, 1, 2, 8, 0),
            target_timeframe=Timeframe.H1,
        )


def test_non_utc_fixed_anchor_is_rejected() -> None:
    with pytest.raises(AlignmentConfigurationError, match="must be UTC"):
        ExplicitFixedAnchorPolicy(
            policy_id="non-utc-anchor",
            anchor=datetime(
                2026, 1, 2, 8, 0, tzinfo=timezone(timedelta(hours=2))
            ),
            target_timeframe=Timeframe.H1,
        )


def test_missing_alignment_policy_is_rejected() -> None:
    with pytest.raises(ResampleConfigurationError, match="explicit"):
        ResampleConfig(
            source_timeframe=Timeframe.M15,
            target_timeframe=Timeframe.H1,
            alignment_policy=None,  # type: ignore[arg-type]
            coverage_policy=CoveragePolicy.CONTIGUOUS_FIXED,
            publication_lag=timedelta(0),
            policy_id="missing",
            session_id_policy=SessionIdPolicy.EXPLICIT,
        )


def test_target_must_be_strictly_greater_than_source() -> None:
    policy = ExplicitFixedAnchorPolicy(
        policy_id="same-timeframe",
        anchor=START,
        target_timeframe=Timeframe.M30,
    )
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


def test_policy_id_must_match_alignment_provenance() -> None:
    policy = ExplicitFixedAnchorPolicy(
        policy_id="alignment-v1",
        anchor=START,
        target_timeframe=Timeframe.H1,
    )
    with pytest.raises(ResampleConfigurationError, match="policy_id"):
        ResampleConfig(
            source_timeframe=Timeframe.M15,
            target_timeframe=Timeframe.H1,
            alignment_policy=policy,
            coverage_policy=CoveragePolicy.CONTIGUOUS_FIXED,
            publication_lag=timedelta(0),
            policy_id="different-v1",
            session_id_policy=SessionIdPolicy.EXPLICIT,
        )


def test_cross_boundary_source_bar_is_rejected() -> None:
    config = fixed_config(anchor=START + timedelta(minutes=5))

    with pytest.raises(ResampleError) as exc_info:
        resample_load_result(load_result_for((source_bar(0),)), config)

    assert exc_info.value.report.cross_boundary_count == 1
    assert exc_info.value.report.rejected_bucket_count == 1


def test_complete_bucket_is_emitted_and_audited() -> None:
    result = resample_load_result(
        load_result_for(source_bars(4)), fixed_config()
    )

    assert result.report.complete_bucket_count == 1
    assert result.report.incomplete_bucket_count == 0
    assert result.report.rejected_bucket_count == 0
    assert result.report.bucket_audits[0].source_member_count == 4
    assert result.report.bucket_audits[0].status is BucketStatus.COMPLETE


def test_internal_missing_slot_fails_strict_coverage_and_is_reported() -> None:
    bars = tuple(source_bar(index) for index in (0, 1, 3))

    with pytest.raises(ResampleError) as exc_info:
        resample_load_result(load_result_for(bars), fixed_config())

    report = exc_info.value.report
    assert report.incomplete_bucket_count == 1
    assert report.missing_slot_count == 1
    assert report.output_bar_count == 0


def test_terminal_trailing_incomplete_bucket_is_not_emitted() -> None:
    result = resample_load_result(
        load_result_for(source_bars(2)), fixed_config()
    )

    assert result.bars == ()
    assert result.report.incomplete_bucket_count == 1
    assert result.report.missing_slot_count == 2
    assert result.report.warnings
    assert not result.report.errors


def test_gap_is_never_forward_filled_or_synthesized() -> None:
    bars = tuple(source_bar(index) for index in (0, 2, 3, 4, 5, 6, 7))

    with pytest.raises(ResampleError) as exc_info:
        resample_load_result(load_result_for(bars), fixed_config())

    assert exc_info.value.report.missing_slot_count == 1
    assert exc_info.value.report.complete_bucket_count == 1


def test_report_only_mode_retains_valid_buckets_and_errors() -> None:
    bars = tuple(source_bar(index) for index in (0, 1, 3, 4, 5, 6, 7))

    result = resample_load_result(
        load_result_for(bars), fixed_config(strict=False)
    )

    assert len(result.bars) == 1
    assert result.report.has_errors
    assert result.bars[0].timestamp == START + timedelta(hours=1)


def daily_schedule_config(
    boundaries: tuple[ExplicitBoundary, ...],
    *,
    target: Timeframe = Timeframe.D,
    strict: bool = True,
) -> ResampleConfig:
    policy_id = f"synthetic-{target.value.lower()}-schedule-v1"
    schedule = ExplicitBoundarySchedule(
        policy_id=policy_id,
        target_timeframe=target,
        boundaries=boundaries,
    )
    return ResampleConfig(
        source_timeframe=Timeframe.M15,
        target_timeframe=target,
        alignment_policy=schedule,
        coverage_policy=CoveragePolicy.EXPLICIT_EXPECTED_SLOTS,
        publication_lag=timedelta(0),
        policy_id=policy_id,
        session_id_policy=SessionIdPolicy.INHERIT_IF_UNANIMOUS_ELSE_NONE,
        strict=strict,
    )


@pytest.mark.parametrize(
    ("target", "duration"),
    [
        (Timeframe.D, timedelta(hours=23)),
        (Timeframe.W, timedelta(days=5, hours=12)),
    ],
)
def test_synthetic_calendar_boundary_aggregates_without_24x7_assumption(
    target: Timeframe, duration: timedelta
) -> None:
    expected = (START, START + timedelta(minutes=15), START + timedelta(minutes=45))
    boundary = ExplicitBoundary(
        start_time=START,
        end_time=START + duration,
        expected_source_timestamps=expected,
    )
    bars = tuple(source_bar(index) for index in (0, 1, 3))

    result = resample_load_result(
        load_result_for(bars),
        daily_schedule_config((boundary,), target=target),
    )

    target_bar = result.bars[0]
    assert target_bar.timeframe is target
    assert target_bar.end_time == START + duration
    assert target_bar.close == bars[-1].close
    assert target_bar.boundary_policy == result.config.policy_id


def test_explicit_expected_slots_can_model_a_planned_session_break() -> None:
    expected = (START, START + timedelta(minutes=15), START + timedelta(minutes=45))
    boundary = ExplicitBoundary(
        start_time=START,
        end_time=START + timedelta(hours=2),
        expected_source_timestamps=expected,
    )
    bars = tuple(source_bar(index) for index in (0, 1, 3))

    result = resample_load_result(
        load_result_for(bars), daily_schedule_config((boundary,))
    )

    assert result.report.missing_slot_count == 0
    assert result.report.complete_bucket_count == 1


def test_calendar_extra_slot_is_rejected_not_inferred_into_schedule() -> None:
    boundary = ExplicitBoundary(
        start_time=START,
        end_time=START + timedelta(hours=2),
        expected_source_timestamps=(START, START + timedelta(minutes=30)),
    )
    bars = tuple(source_bar(index) for index in (0, 1, 2))

    with pytest.raises(ResampleError) as exc_info:
        resample_load_result(
            load_result_for(bars), daily_schedule_config((boundary,))
        )

    report = exc_info.value.report
    assert report.rejected_bucket_count == 1
    assert report.misaligned_bar_count == 1


def test_calendar_missing_internal_expected_slot_fails_strict_coverage() -> None:
    boundary = ExplicitBoundary(
        start_time=START,
        end_time=START + timedelta(hours=1),
        expected_source_timestamps=(
            START,
            START + timedelta(minutes=15),
            START + timedelta(minutes=30),
            START + timedelta(minutes=45),
        ),
    )
    bars = tuple(source_bar(index) for index in (0, 2, 3))

    with pytest.raises(ResampleError) as exc_info:
        resample_load_result(
            load_result_for(bars), daily_schedule_config((boundary,))
        )

    assert exc_info.value.report.missing_slot_count == 1


@pytest.mark.parametrize("target", [Timeframe.D, Timeframe.W])
def test_calendar_target_without_explicit_schedule_is_rejected(
    target: Timeframe,
) -> None:
    with pytest.raises(AlignmentConfigurationError, match="fixed target"):
        ExplicitFixedAnchorPolicy(
            policy_id="invalid-calendar",
            anchor=START,
            target_timeframe=target,
        )


def test_calendar_schedule_rejects_naive_boundary() -> None:
    with pytest.raises(AlignmentConfigurationError, match="timezone-aware UTC"):
        ExplicitBoundary(
            start_time=datetime(2026, 1, 2, 8, 0),
            end_time=START + timedelta(hours=1),
            expected_source_timestamps=(START,),
        )


def test_calendar_schedule_rejects_overlapping_boundaries() -> None:
    first = ExplicitBoundary(
        START,
        START + timedelta(hours=2),
        (START,),
    )
    second = ExplicitBoundary(
        START + timedelta(hours=1),
        START + timedelta(hours=3),
        (START + timedelta(hours=1),),
    )
    with pytest.raises(AlignmentConfigurationError, match="overlap"):
        ExplicitBoundarySchedule(
            "overlap-v1", Timeframe.D, (first, second)
        )


def test_calendar_target_rejects_fixed_coverage_policy() -> None:
    boundary = ExplicitBoundary(
        START,
        START + timedelta(hours=1),
        (START,),
    )
    schedule = ExplicitBoundarySchedule(
        "calendar-coverage-v1", Timeframe.D, (boundary,)
    )
    with pytest.raises(ResampleConfigurationError, match="EXPLICIT_EXPECTED_SLOTS"):
        ResampleConfig(
            source_timeframe=Timeframe.M15,
            target_timeframe=Timeframe.D,
            alignment_policy=schedule,
            coverage_policy=CoveragePolicy.CONTIGUOUS_FIXED,
            publication_lag=timedelta(0),
            policy_id=schedule.policy_id,
            session_id_policy=SessionIdPolicy.EXPLICIT,
        )


def test_source_bar_outside_calendar_schedule_is_rejected() -> None:
    boundary = ExplicitBoundary(
        START,
        START + timedelta(hours=1),
        (START,),
    )
    outside = source_bar(8)

    with pytest.raises(ResampleError) as exc_info:
        resample_load_result(
            load_result_for((outside,)), daily_schedule_config((boundary,))
        )

    assert exc_info.value.report.misaligned_bar_count == 1


def test_target_available_time_is_not_earlier_than_bucket_end() -> None:
    target = resample_load_result(
        load_result_for(source_bars(4)), fixed_config()
    ).bars[0]

    assert target.available_time == START + timedelta(hours=1)
    assert target.available_time >= target.end_time


def test_maximum_available_time_uses_every_source_member() -> None:
    delayed = START + timedelta(hours=1, minutes=10)
    bars = list(source_bars(4))
    bars[0] = source_bar(0, available_time=delayed)

    target = resample_load_result(
        load_result_for(tuple(bars)), fixed_config()
    ).bars[0]

    assert target.available_time == delayed


def test_publication_lag_is_added_after_base_available_time() -> None:
    lag = timedelta(seconds=17)

    target = resample_load_result(
        load_result_for(source_bars(4)),
        fixed_config(publication_lag=lag),
    ).bars[0]

    assert target.available_time == START + timedelta(hours=1, seconds=17)


def test_negative_publication_lag_is_rejected() -> None:
    with pytest.raises(ResampleConfigurationError, match="greater than or equal"):
        fixed_config(publication_lag=timedelta(microseconds=-1))


def test_available_time_does_not_use_next_bucket_or_file_end() -> None:
    result = resample_load_result(
        load_result_for(source_bars(8)), fixed_config()
    )

    assert result.bars[0].available_time == START + timedelta(hours=1)
    assert result.bars[0].available_time != result.bars[-1].end_time


def test_target_provenance_preserves_source_identity_and_volume_type() -> None:
    bars = source_bars(4, volume_type=VolumeType.REAL)

    target = resample_load_result(
        load_result_for(bars), fixed_config()
    ).bars[0]

    assert target.symbol == "XAUUSD"
    assert target.source == "synthetic-feed"
    assert target.source_timezone == "UTC"
    assert target.volume_type is VolumeType.REAL
    assert target.boundary_policy == "fixed-h1-test-v1"
    assert target.is_complete


def test_unanimous_session_id_is_inherited() -> None:
    target = resample_load_result(
        load_result_for(source_bars(4, session_id="session-z")),
        fixed_config(),
    ).bars[0]

    assert target.session_id == "session-z"


def test_conflicting_session_ids_are_deterministically_cleared() -> None:
    bars = list(source_bars(4))
    bars[2] = replace(bars[2], session_id="session-b")

    result = resample_load_result(load_result_for(tuple(bars)), fixed_config())

    assert result.bars[0].session_id is None
    assert any("explicitly cleared" in warning for warning in result.report.warnings)


def test_explicit_output_session_id_overrides_member_conflict() -> None:
    bars = list(source_bars(4))
    bars[2] = replace(bars[2], session_id="session-b")
    config = fixed_config(
        session_id_policy=SessionIdPolicy.EXPLICIT,
        output_session_id="resampled-session",
    )

    result = resample_load_result(load_result_for(tuple(bars)), config)

    assert result.bars[0].session_id == "resampled-session"


def test_result_retains_config_snapshot_and_report_fields() -> None:
    config = fixed_config()
    result = resample_load_result(load_result_for(source_bars(4)), config)

    assert result.config_snapshot is config
    assert result.config is config
    assert result.source_timeframe is Timeframe.M15
    assert result.target_timeframe is Timeframe.H1
    assert result.input_bar_count == 4
    assert result.output_bar_count == 1
    assert result.report.policy_id == config.policy_id
    assert result.report.earliest_target_timestamp == START
    assert result.report.latest_target_timestamp == START
    assert result.report.assumptions
    with pytest.raises(FrozenInstanceError):
        result.report.output_bar_count = 2  # type: ignore[misc]


def test_public_interface_rejects_raw_canonical_bar_sequence() -> None:
    with pytest.raises(TypeError, match="LoadResult"):
        resample_load_result(source_bars(4), fixed_config())  # type: ignore[arg-type]


def test_report_only_load_result_with_errors_is_rejected() -> None:
    bar = source_bar(0)
    bad_load = load_result_for((bar, bar), strict_config=False)
    assert bad_load.quality_report.has_errors

    with pytest.raises(ResampleError, match="quality_report"):
        resample_load_result(bad_load, fixed_config())


def test_incomplete_source_bar_is_rejected() -> None:
    incomplete = source_bar(
        0,
        is_complete=False,
        available_time=START + timedelta(minutes=5),
    )

    with pytest.raises(ResampleError, match="incomplete"):
        resample_load_result(load_result_for((incomplete,)), fixed_config())


def test_mixed_source_identity_is_rejected_without_grouping() -> None:
    bars = list(source_bars(4))
    bars[2] = replace(bars[2], source="different-feed")

    with pytest.raises(ResampleError) as exc_info:
        resample_load_result(load_result_for(tuple(bars)), fixed_config())

    assert exc_info.value.report.source_identity_error_count == 1


def test_load_result_source_config_identity_mismatch_is_rejected() -> None:
    load_result = load_result_for(source_bars(4))
    mismatched_config = replace(
        load_result.source_config,
        timeframe=Timeframe.M30,
    )
    forged = replace(load_result, source_config=mismatched_config)

    with pytest.raises(ResampleError, match="source_config timeframe"):
        resample_load_result(forged, fixed_config())


def test_mixed_volume_type_is_rejected() -> None:
    bars = list(source_bars(4, volume_type=VolumeType.TICK))
    bars[2] = source_bar(2, volume_type=VolumeType.REAL)

    with pytest.raises(ResampleError, match="volume_type"):
        resample_load_result(load_result_for(tuple(bars)), fixed_config())


def test_resampling_does_not_mutate_input_objects() -> None:
    load_result = load_result_for(source_bars(4))
    before = tuple(bar.to_dict() for bar in load_result.bars)

    resample_load_result(load_result, fixed_config())

    assert tuple(bar.to_dict() for bar in load_result.bars) == before


def test_as_of_rejects_naive_processing_time() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        resample_as_of(
            load_result_for(source_bars(4)),
            fixed_config(),
            datetime(2026, 1, 2, 9, 0),
        )
