"""Chronological replay helpers for causal C-006B timeframe state."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Iterator

from .contracts import (
    TimeframeStateEvent,
    TimeframeStateHistory,
    TimeframeStateInput,
)
from .engine import TimeframeStateEngine
from .errors import TimeframeStateInputError


def _normalize_schedule(
    data: TimeframeStateInput,
    processing_times: Iterable[datetime] | None,
) -> tuple[datetime, ...]:
    if processing_times is None:
        return tuple(
            item.as_of_time for item in data.lifecycle_history.snapshots
        )
    normalized: list[datetime] = []
    for value in processing_times:
        if not isinstance(value, datetime):
            raise TimeframeStateInputError(
                "replay processing times must be datetimes"
            )
        if value.tzinfo is None or value.utcoffset() is None:
            raise TimeframeStateInputError(
                "replay processing times must be timezone-aware"
            )
        normalized.append(value.astimezone(timezone.utc))
    if any(
        current <= previous
        for previous, current in zip(normalized, normalized[1:])
    ):
        raise TimeframeStateInputError(
            "replay processing times must be strictly ascending and unique"
        )
    return tuple(normalized)


def replay_history(
    engine: TimeframeStateEngine,
    data: TimeframeStateInput,
    processing_times: Iterable[datetime] | None = None,
) -> TimeframeStateHistory:
    """Rebuild exact first-seen state events from an explicit as-of schedule."""
    if not isinstance(engine, TimeframeStateEngine):
        raise TimeframeStateInputError("engine must be a TimeframeStateEngine")
    if not isinstance(data, TimeframeStateInput):
        raise TimeframeStateInputError("replay requires TimeframeStateInput")
    schedule = _normalize_schedule(data, processing_times)
    if not schedule:
        raise TimeframeStateInputError("replay schedule must not be empty")
    first_source_time = data.lifecycle_history.snapshots[0].as_of_time
    if schedule[0] < first_source_time:
        raise TimeframeStateInputError(
            "replay schedule cannot precede the first LifecycleSnapshot"
        )
    batch = engine.build_batch(data)
    if processing_times is not None:
        true_event_times = {item.first_seen_time for item in batch.events}
        if not true_event_times.issubset(set(schedule)):
            raise TimeframeStateInputError(
                "replay schedule must include every true Event first_seen_time"
            )
        if schedule[-1] < data.lifecycle_history.final_snapshot.as_of_time:
            raise TimeframeStateInputError(
                "replay schedule must reach the final LifecycleSnapshot"
            )
    snapshots = tuple(engine.build_as_of(data, item) for item in schedule)
    history = TimeframeStateHistory(
        events=snapshots[-1].events,
        snapshots=snapshots,
        final_snapshot=snapshots[-1],
        config_snapshot=engine.config,
    )
    if history.events != batch.events:
        raise TimeframeStateInputError(
            "replay schedule does not preserve the Batch event ledger"
        )
    if any(item.first_seen_time != item.event_confirm_time for item in history.events):
        raise TimeframeStateInputError(
            "replay discovered an event after its true first-seen time"
        )
    return history


def iter_replay_events(
    engine: TimeframeStateEngine,
    data: TimeframeStateInput,
    processing_times: Iterable[datetime] | None = None,
) -> Iterator[TimeframeStateEvent]:
    yield from replay_history(engine, data, processing_times).events


def build_history(
    engine: TimeframeStateEngine, data: TimeframeStateInput
) -> TimeframeStateHistory:
    return engine.build_batch(data)
