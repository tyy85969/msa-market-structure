from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Iterable, Sequence

from msa.data import (
    CompletedBarPolicy,
    CoveragePolicy,
    ExplicitFixedAnchorPolicy,
    LoadResult,
    ResampleConfig,
    SessionIdPolicy,
    SourceDataConfig,
    Timeframe,
    TimestampSemantics,
    VolumeType,
    load_records,
)


UTC = timezone.utc
START = datetime(2026, 2, 2, 8, 0, tzinfo=UTC)
TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%S%z"


def utc_text(value: datetime) -> str:
    return value.strftime(TIMESTAMP_FORMAT)


def source_config(
    *,
    timeframe: Timeframe = Timeframe.M15,
    timestamp_semantics: TimestampSemantics = TimestampSemantics.OPEN_TIME,
    volume_type: VolumeType = VolumeType.TICK,
    strict: bool = True,
    source_timezone: str = "UTC",
) -> SourceDataConfig:
    volume_column = None if volume_type is VolumeType.UNAVAILABLE else "volume"
    return SourceDataConfig(
        source="c001d-audit-feed",
        source_timezone=source_timezone,
        source_symbol="GOLD",
        canonical_symbol="XAUUSD",
        timeframe=timeframe,
        timestamp_column="time",
        timestamp_semantics=timestamp_semantics,
        timestamp_format=TIMESTAMP_FORMAT,
        open_column="open",
        high_column="high",
        low_column="low",
        close_column="close",
        volume_column=volume_column,
        volume_type=volume_type,
        completed_bar_policy=CompletedBarPolicy.EXPLICIT_COLUMN,
        availability_lag=timedelta(0),
        session_id="c001d-session",
        boundary_policy=None,
        end_time_column=None,
        symbol_column="symbol",
        complete_column="complete",
        observed_time_column="observed",
        complete_true_values=("closed",),
        complete_false_values=("forming",),
        strict=strict,
    )


def records_for_indices(
    indices: Iterable[int],
    *,
    timeframe: Timeframe = Timeframe.M15,
    start: datetime = START,
    delays: Sequence[timedelta] | None = None,
    price_offsets: dict[int, Decimal] | None = None,
    timestamp_semantics: TimestampSemantics = TimestampSemantics.OPEN_TIME,
    complete: str = "closed",
) -> list[dict[str, object]]:
    duration = timeframe.fixed_duration
    assert duration is not None
    offsets = price_offsets or {}
    records: list[dict[str, object]] = []
    for index in indices:
        timestamp = start + index * duration
        end_time = timestamp + duration
        delay = delays[index] if delays is not None else timedelta(0)
        observed = end_time + delay if complete == "closed" else timestamp + delay
        opening = Decimal("2000") + Decimal(index) + offsets.get(index, Decimal(0))
        source_timestamp = (
            timestamp
            if timestamp_semantics is TimestampSemantics.OPEN_TIME
            else end_time
        )
        records.append(
            {
                "time": utc_text(source_timestamp),
                "symbol": "GOLD",
                "open": opening,
                "high": opening + Decimal("3"),
                "low": opening - Decimal("2"),
                "close": opening + Decimal("1"),
                "volume": Decimal(index + 1),
                "complete": complete,
                "observed": utc_text(observed),
            }
        )
    return records


def load_indices(
    indices: Iterable[int],
    *,
    timeframe: Timeframe = Timeframe.M15,
    start: datetime = START,
    delays: Sequence[timedelta] | None = None,
    price_offsets: dict[int, Decimal] | None = None,
    timestamp_semantics: TimestampSemantics = TimestampSemantics.OPEN_TIME,
    complete: str = "closed",
    strict: bool = True,
) -> LoadResult:
    records = records_for_indices(
        indices,
        timeframe=timeframe,
        start=start,
        delays=delays,
        price_offsets=price_offsets,
        timestamp_semantics=timestamp_semantics,
        complete=complete,
    )
    config = source_config(
        timeframe=timeframe,
        timestamp_semantics=timestamp_semantics,
        strict=strict,
    )
    return load_records(records, config)


def fixed_config(
    target: Timeframe,
    *,
    source: Timeframe = Timeframe.M15,
    anchor: datetime = START,
    publication_lag: timedelta = timedelta(0),
    strict: bool = True,
) -> ResampleConfig:
    policy_id = f"c001d-{source.value.lower()}-{target.value.lower()}-anchor-v1"
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
        session_id_policy=SessionIdPolicy.INHERIT_IF_UNANIMOUS_ELSE_NONE,
        strict=strict,
    )
