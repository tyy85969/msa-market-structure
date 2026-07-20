"""Chronological replay helpers shared by C-004 level generators."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Iterator

from .contracts import (
    LevelGenerationEvent,
    LevelGenerationInput,
    LevelGenerator,
)
from .errors import LevelGenerationError, LevelInputError


def _normalize_schedule(
    data: LevelGenerationInput,
    processing_times: Iterable[datetime] | None,
) -> tuple[datetime, ...]:
    if processing_times is None:
        values = {bar.available_time for bar in data.source.bars}
        values.update(
            seed.confirm_time
            for seed in data.seed_candidates
            if seed.confirm_time is not None
        )
        return tuple(sorted(values))

    normalized: list[datetime] = []
    for value in processing_times:
        if not isinstance(value, datetime):
            raise LevelInputError("replay processing times must be datetimes")
        if value.tzinfo is None or value.utcoffset() is None:
            raise LevelInputError(
                "replay processing times must be timezone-aware"
            )
        normalized.append(value.astimezone(timezone.utc))
    if any(
        current <= previous
        for previous, current in zip(normalized, normalized[1:])
    ):
        raise LevelInputError(
            "replay processing times must be strictly ascending and unique"
        )
    return tuple(normalized)


def iter_replay_events(
    generator: LevelGenerator,
    data: LevelGenerationInput,
    processing_times: Iterable[datetime] | None = None,
) -> Iterator[LevelGenerationEvent]:
    """Yield each generated candidate at its first exact As-Of appearance."""

    if not isinstance(data, LevelGenerationInput):
        raise LevelInputError("replay requires a LevelGenerationInput")
    if not isinstance(generator, LevelGenerator):
        raise LevelInputError("generator must implement LevelGenerator")
    schedule = _normalize_schedule(data, processing_times)
    seen: set[str] = set()
    for processing_time in schedule:
        result = generator.generate_as_of(data, processing_time)
        for candidate in result.candidates:
            if candidate.candidate_id in seen:
                continue
            if candidate.confirm_time != processing_time:
                raise LevelGenerationError(
                    "replay first appearance did not equal candidate.confirm_time; "
                    "the schedule must include every causal availability event"
                )
            seen.add(candidate.candidate_id)
            yield LevelGenerationEvent(processing_time, candidate)


def replay_events(
    generator: LevelGenerator,
    data: LevelGenerationInput,
    processing_times: Iterable[datetime] | None = None,
) -> tuple[LevelGenerationEvent, ...]:
    """Materialize deterministic first-appearance replay events."""

    return tuple(iter_replay_events(generator, data, processing_times))
