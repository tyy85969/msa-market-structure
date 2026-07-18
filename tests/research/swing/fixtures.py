from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Sequence

from msa.data import (
    CanonicalBar,
    CompletedBarPolicy,
    LoadResult,
    SourceDataConfig,
    Timeframe,
    TimestampSemantics,
    VolumeType,
    validate_bar_sequence,
)
from msa.domain import ScaleDescriptor
from msa.research.swing import (
    PivotDetector,
    PivotDetectorConfig,
    TiePolicy,
)


UTC = timezone.utc
START = datetime(2026, 7, 1, 0, 0, tzinfo=UTC)
SCALE = ScaleDescriptor("experiment-swing-h1", 1)


def pivot_config(
    *,
    left_bars: int = 1,
    right_bars: int = 1,
    detector_id: str = "confirmed-pivot",
    detector_version: str = "1.0.0",
    policy_id: str = "pivot-strict-v1",
    scale: ScaleDescriptor = SCALE,
    strict: bool = True,
) -> PivotDetectorConfig:
    return PivotDetectorConfig(
        detector_id=detector_id,
        detector_version=detector_version,
        left_bars=left_bars,
        right_bars=right_bars,
        tie_policy=TiePolicy.STRICT,
        scale=scale,
        policy_id=policy_id,
        strict=strict,
    )


def detector(**overrides: object) -> PivotDetector:
    return PivotDetector(pivot_config(**overrides))  # type: ignore[arg-type]


def bar(
    index: int,
    *,
    high: Decimal | str = "20",
    low: Decimal | str = "10",
    timestamp: datetime | None = None,
    available_time: datetime | None = None,
    symbol: str = "XAUUSD",
    timeframe: Timeframe = Timeframe.H1,
    source: str = "synthetic-feed",
    is_complete: bool = True,
) -> CanonicalBar:
    high_value = high if isinstance(high, Decimal) else Decimal(high)
    low_value = low if isinstance(low, Decimal) else Decimal(low)
    opening = (high_value + low_value) / Decimal(2)
    start = timestamp or START + index * timedelta(hours=1)
    duration = timeframe.fixed_duration
    if duration is None:
        raise AssertionError("synthetic fixture uses fixed-duration bars")
    end = start + duration
    return CanonicalBar(
        symbol=symbol,
        timeframe=timeframe,
        timestamp=start,
        end_time=end,
        open=opening,
        high=high_value,
        low=low_value,
        close=opening,
        volume=None,
        volume_type=VolumeType.UNAVAILABLE,
        source=source,
        source_timezone="UTC",
        session_id="synthetic-session",
        boundary_policy=None,
        is_complete=is_complete,
        available_time=available_time or end,
    )


def bars_from_extrema(
    highs: Sequence[Decimal | str],
    lows: Sequence[Decimal | str],
    *,
    delays: Sequence[timedelta] | None = None,
    start: datetime = START,
) -> tuple[CanonicalBar, ...]:
    if len(highs) != len(lows):
        raise ValueError("high and low lengths must match")
    delay_values = delays or tuple(timedelta(0) for _ in highs)
    if len(delay_values) != len(highs):
        raise ValueError("delay length must match bars")
    result = []
    for index, (high, low, delay) in enumerate(zip(highs, lows, delay_values)):
        timestamp = start + index * timedelta(hours=1)
        result.append(
            bar(
                index,
                high=high,
                low=low,
                timestamp=timestamp,
                available_time=timestamp + timedelta(hours=1) + delay,
            )
        )
    return tuple(result)


def source_config(
    *,
    timeframe: Timeframe = Timeframe.H1,
    source: str = "synthetic-feed",
) -> SourceDataConfig:
    return SourceDataConfig(
        source=source,
        source_timezone="UTC",
        source_symbol="GOLD",
        canonical_symbol="XAUUSD",
        timeframe=timeframe,
        timestamp_column="time",
        timestamp_semantics=TimestampSemantics.OPEN_TIME,
        timestamp_format="%Y-%m-%dT%H:%M:%S%z",
        open_column="open",
        high_column="high",
        low_column="low",
        close_column="close",
        volume_column=None,
        volume_type=VolumeType.UNAVAILABLE,
        completed_bar_policy=CompletedBarPolicy.ALL_ROWS_ARE_CLOSED,
        availability_lag=timedelta(0),
        session_id="synthetic-session",
        boundary_policy=None,
        end_time_column=None,
    )


def load_result(
    bars: tuple[CanonicalBar, ...],
    *,
    config: SourceDataConfig | None = None,
) -> LoadResult:
    actual_config = config or source_config()
    report = validate_bar_sequence(
        bars,
        source=actual_config.source,
        timeframe=actual_config.timeframe,
        assumptions=actual_config.assumptions(),
    )
    return LoadResult(
        bars=bars,
        quality_report=report,
        source_config=actual_config,
        loaded_row_count=len(bars),
        accepted_row_count=len(bars),
        rejected_row_count=0,
    )


def high_pivot_bars() -> tuple[CanonicalBar, ...]:
    return bars_from_extrema(
        ("15", "17", "30.1250", "18", "16"),
        ("10", "11", "12", "11", "10"),
    )


def low_pivot_bars() -> tuple[CanonicalBar, ...]:
    return bars_from_extrema(
        ("30", "29", "28", "29", "30"),
        ("20", "18", "5.2500", "17", "19"),
    )


def dual_pivot_bars() -> tuple[CanonicalBar, ...]:
    return bars_from_extrema(
        ("20", "40.00", "21"),
        ("10", "1.00", "9"),
    )
