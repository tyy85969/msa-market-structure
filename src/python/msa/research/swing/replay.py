"""Chronological replay helpers for causal Swing detector experiments."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Iterator

from msa.data import LoadResult

from .contracts import SwingDetectionEvent, SwingDetector
from .errors import SwingDetectionError, SwingInputError


def _normalize_schedule(
    source: LoadResult, processing_times: Iterable[datetime] | None
) -> tuple[datetime, ...]:
    if processing_times is None:
        return tuple(sorted({bar.available_time for bar in source.bars}))

    normalized: list[datetime] = []
    for value in processing_times:
        if not isinstance(value, datetime):
            raise SwingInputError("replay processing times must be datetimes")
        if value.tzinfo is None or value.utcoffset() is None:
            raise SwingInputError(
                "replay processing times must be timezone-aware"
            )
        normalized.append(value.astimezone(timezone.utc))
    if any(
        current <= previous
        for previous, current in zip(normalized, normalized[1:])
    ):
        raise SwingInputError(
            "replay processing times must be strictly ascending and unique"
        )
    return tuple(normalized)


def iter_replay_events(
    detector: SwingDetector,
    source: LoadResult,
    processing_times: Iterable[datetime] | None = None,
) -> Iterator[SwingDetectionEvent]:
    """Yield each candidate at its first As-Of appearance during replay."""

    if not isinstance(source, LoadResult):
        raise SwingInputError("replay requires a C-001 LoadResult")
    schedule = _normalize_schedule(source, processing_times)
    seen: set[str] = set()
    for processing_time in schedule:
        result = detector.detect_as_of(source, processing_time)
        for candidate in result.candidates:
            if candidate.candidate_id in seen:
                continue
            if candidate.confirm_time != processing_time:
                raise SwingDetectionError(
                    "replay first appearance did not equal candidate.confirm_time; "
                    "the schedule must include every causal availability event"
                )
            seen.add(candidate.candidate_id)
            yield SwingDetectionEvent(processing_time, candidate)


def replay_events(
    detector: SwingDetector,
    source: LoadResult,
    processing_times: Iterable[datetime] | None = None,
) -> tuple[SwingDetectionEvent, ...]:
    """Materialize deterministic first-appearance replay events."""

    return tuple(iter_replay_events(detector, source, processing_times))
