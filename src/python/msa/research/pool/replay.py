"""Chronological Level Pool history and replay helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Iterator

from .clustering import LevelPoolClusterer
from .contracts import ClusterFormationEvent, LevelPoolHistory, LevelPoolInput
from .errors import LevelPoolInputError


def _normalize_schedule(
    data: LevelPoolInput,
    processing_times: Iterable[datetime] | None,
) -> tuple[datetime, ...]:
    if processing_times is None:
        return tuple(
            sorted(
                {
                    item.confirm_time
                    for item in data.candidates
                    if item.confirm_time is not None
                }
            )
        )
    normalized: list[datetime] = []
    for value in processing_times:
        if not isinstance(value, datetime):
            raise LevelPoolInputError("replay processing times must be datetimes")
        if value.tzinfo is None or value.utcoffset() is None:
            raise LevelPoolInputError(
                "replay processing times must be timezone-aware"
            )
        normalized.append(value.astimezone(timezone.utc))
    if any(
        current <= previous
        for previous, current in zip(normalized, normalized[1:])
    ):
        raise LevelPoolInputError(
            "replay processing times must be strictly ascending and unique"
        )
    return tuple(normalized)


def replay_history(
    clusterer: LevelPoolClusterer,
    data: LevelPoolInput,
    processing_times: Iterable[datetime] | None = None,
) -> LevelPoolHistory:
    """Rebuild exact first formations; sparse late-discovery schedules fail."""

    if not isinstance(clusterer, LevelPoolClusterer):
        raise LevelPoolInputError("clusterer must be a LevelPoolClusterer")
    if not isinstance(data, LevelPoolInput):
        raise LevelPoolInputError("replay requires a LevelPoolInput")
    schedule = _normalize_schedule(data, processing_times)
    if processing_times is not None:
        expected_times = {
            item.first_seen_time
            for item in clusterer.build_batch(data).formation_events
        }
        if not expected_times.issubset(set(schedule)):
            raise LevelPoolInputError(
                "replay schedule must include every cluster first_seen_time"
            )
    return clusterer._history_for_schedule(data, schedule)


def iter_replay_events(
    clusterer: LevelPoolClusterer,
    data: LevelPoolInput,
    processing_times: Iterable[datetime] | None = None,
) -> Iterator[ClusterFormationEvent]:
    """Yield deterministic cluster first-formation events."""

    yield from replay_history(clusterer, data, processing_times).formation_events


def build_history(
    clusterer: LevelPoolClusterer, data: LevelPoolInput
) -> LevelPoolHistory:
    """Named Batch-history helper equivalent to clusterer.build_batch."""

    return clusterer.build_batch(data)
