"""Shared strict input checks for C-004 generators."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from msa.data import CanonicalBar, LoadResult

from .contracts import LevelGenerationInput
from .errors import LevelInputError


def normalize_processing_time(value: object) -> datetime:
    if not isinstance(value, datetime):
        raise LevelInputError("processing_time must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise LevelInputError("processing_time must be timezone-aware")
    return value.astimezone(timezone.utc)


def validate_source(data: LevelGenerationInput) -> tuple[CanonicalBar, ...]:
    if not isinstance(data, LevelGenerationInput):
        raise LevelInputError("generation requires a LevelGenerationInput")
    source = data.source
    if not isinstance(source, LoadResult):
        raise LevelInputError("source must be a C-001 LoadResult")
    if source.quality_report.has_errors:
        raise LevelInputError(
            "LoadResult.quality_report contains errors and is not eligible"
        )
    bars = source.bars
    if not isinstance(bars, tuple) or any(
        not isinstance(bar, CanonicalBar) for bar in bars
    ):
        raise LevelInputError("LoadResult.bars must be a CanonicalBar tuple")
    if source.accepted_row_count != len(bars):
        raise LevelInputError("LoadResult counts do not match canonical bars")

    config = source.source_config
    report = source.quality_report
    if report.source != config.source or report.timeframe is not config.timeframe:
        raise LevelInputError(
            "C-001 quality report identity does not match source configuration"
        )

    seen: set[tuple[str, object, datetime]] = set()
    previous: CanonicalBar | None = None
    for bar in bars:
        if bar.symbol != config.canonical_symbol:
            raise LevelInputError("mixed symbol or symbol/config mismatch")
        if bar.timeframe is not config.timeframe:
            raise LevelInputError("mixed timeframe or timeframe/config mismatch")
        if bar.source != config.source:
            raise LevelInputError("mixed source or source/config mismatch")
        if bar.source_timezone != config.source_timezone:
            raise LevelInputError("mixed source_timezone or timezone/config mismatch")
        if bar.boundary_policy != config.boundary_policy:
            raise LevelInputError(
                "mixed boundary policy or boundary_policy/config mismatch"
            )
        if not _valid_ohlc(bar):
            raise LevelInputError("invalid OHLC entered level generation")
        key = (bar.symbol, bar.timeframe, bar.timestamp)
        if key in seen:
            raise LevelInputError("duplicate canonical bar key")
        seen.add(key)
        if previous is not None:
            if bar.timestamp < previous.timestamp:
                raise LevelInputError("canonical bars are out of order")
            if bar.timestamp == previous.timestamp:
                raise LevelInputError("duplicate canonical bar timestamp")
            if bar.timestamp < previous.end_time:
                raise LevelInputError("canonical bar intervals overlap")
        previous = bar
    return bars


def validate_no_complete_after_incomplete(bars: tuple[CanonicalBar, ...]) -> None:
    incomplete_seen = False
    for bar in bars:
        if not bar.is_complete:
            incomplete_seen = True
        elif incomplete_seen:
            raise LevelInputError(
                "complete bar cannot follow an incomplete bar in the fixed sequence"
            )


def causal_prefix(
    bars: tuple[CanonicalBar, ...], processing_time: datetime | None
) -> tuple[CanonicalBar, ...]:
    visible: list[CanonicalBar] = []
    for bar in bars:
        if not bar.is_complete:
            break
        if processing_time is not None and bar.available_time > processing_time:
            break
        visible.append(bar)
    return tuple(visible)


def prefix_available_times(
    bars: tuple[CanonicalBar, ...],
) -> tuple[datetime, ...]:
    maximum: datetime | None = None
    values: list[datetime] = []
    for bar in bars:
        maximum = (
            bar.available_time
            if maximum is None
            else max(maximum, bar.available_time)
        )
        values.append(maximum)
    return tuple(values)


def _valid_ohlc(bar: CanonicalBar) -> bool:
    values = (bar.open, bar.high, bar.low, bar.close)
    return (
        all(isinstance(item, Decimal) and item.is_finite() for item in values)
        and bar.high >= bar.low
        and bar.high >= bar.open
        and bar.high >= bar.close
        and bar.low <= bar.open
        and bar.low <= bar.close
    )
