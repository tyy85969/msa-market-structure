"""Chronological replay helpers for the C-006A lifecycle event ledger."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Iterator

from .contracts import LifecycleEvent, LifecycleHistory, LifecycleInput
from .engine import LifecycleEngine
from .errors import LifecycleInputError


def _normalize_schedule(data: LifecycleInput, processing_times: Iterable[datetime] | None) -> tuple[datetime, ...]:
    if processing_times is None:
        return tuple(sorted({item.confirm_time for item in data.subjects} | {bar.available_time for bar in data.source.bars}))
    normalized: list[datetime] = []
    for value in processing_times:
        if not isinstance(value, datetime):
            raise LifecycleInputError("replay processing times must be datetimes")
        if value.tzinfo is None or value.utcoffset() is None:
            raise LifecycleInputError("replay processing times must be timezone-aware")
        normalized.append(value.astimezone(timezone.utc))
    if any(current <= previous for previous, current in zip(normalized, normalized[1:])):
        raise LifecycleInputError("replay processing times must be strictly ascending and unique")
    return tuple(normalized)


def replay_history(engine: LifecycleEngine, data: LifecycleInput, processing_times: Iterable[datetime] | None = None) -> LifecycleHistory:
    """Rebuild exact first-seen lifecycle events from an explicit schedule."""
    if not isinstance(engine, LifecycleEngine):
        raise LifecycleInputError("engine must be a LifecycleEngine")
    if not isinstance(data, LifecycleInput):
        raise LifecycleInputError("replay requires LifecycleInput")
    schedule = _normalize_schedule(data, processing_times)
    if not schedule:
        raise LifecycleInputError("replay schedule must not be empty")
    if processing_times is not None:
        true_event_times = {item.first_seen_time for item in engine.build_batch(data).events}
        if not true_event_times.issubset(set(schedule)):
            raise LifecycleInputError("replay schedule must include every true Event first_seen_time")
    history = engine._history_for_schedule(data, schedule)
    if any(item.first_seen_time != item.event_confirm_time for item in history.events):
        raise LifecycleInputError("replay discovered an event after its true first-seen time")
    return history


def iter_replay_events(engine: LifecycleEngine, data: LifecycleInput, processing_times: Iterable[datetime] | None = None) -> Iterator[LifecycleEvent]:
    yield from replay_history(engine, data, processing_times).events


def build_history(engine: LifecycleEngine, data: LifecycleInput) -> LifecycleHistory:
    return engine.build_batch(data)
