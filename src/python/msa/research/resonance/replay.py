"""Batch/replay helpers for causal C-007A resonance frames."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Iterator

from .assembler import ResonanceFrameAssembler
from .contracts import ResonanceFrame, ResonanceFrameHistory, ResonanceFrameInput
from .errors import ResonanceFrameInputError


def _normalize_schedule(
    assembler: ResonanceFrameAssembler,
    data: ResonanceFrameInput,
    processing_times: Iterable[datetime] | None,
) -> tuple[datetime, ...]:
    default = assembler.default_schedule(data)
    if processing_times is None:
        return default
    normalized: list[datetime] = []
    for value in processing_times:
        if not isinstance(value, datetime):
            raise ResonanceFrameInputError(
                "replay processing times must be datetimes"
            )
        if value.tzinfo is None or value.utcoffset() is None:
            raise ResonanceFrameInputError(
                "replay processing times must be timezone-aware"
            )
        normalized.append(value.astimezone(timezone.utc))
    if not normalized:
        raise ResonanceFrameInputError("replay schedule must not be empty")
    if any(
        current <= previous
        for previous, current in zip(normalized, normalized[1:])
    ):
        raise ResonanceFrameInputError(
            "replay processing times must be strictly ascending and unique"
        )
    if normalized[0] < default[0]:
        raise ResonanceFrameInputError(
            "replay schedule cannot precede common causal availability"
        )
    if not set(default).issubset(normalized):
        raise ResonanceFrameInputError(
            "replay schedule must contain every default Frame time"
        )
    return tuple(normalized)


def replay_history(
    assembler: ResonanceFrameAssembler,
    data: ResonanceFrameInput,
    processing_times: Iterable[datetime] | None = None,
) -> ResonanceFrameHistory:
    if not isinstance(assembler, ResonanceFrameAssembler):
        raise ResonanceFrameInputError(
            "assembler must be a ResonanceFrameAssembler"
        )
    if not isinstance(data, ResonanceFrameInput):
        raise ResonanceFrameInputError("replay requires ResonanceFrameInput")
    schedule = _normalize_schedule(assembler, data, processing_times)
    frames = tuple(assembler.build_as_of(data, item) for item in schedule)
    history = ResonanceFrameHistory(
        frames=frames,
        final_frame=frames[-1],
        config_snapshot=assembler.config,
    )
    if processing_times is None and history.to_dict() != assembler.build_batch(data).to_dict():
        raise ResonanceFrameInputError(
            "default Replay must be byte-equivalent to Batch"
        )
    return history


def iter_replay_frames(
    assembler: ResonanceFrameAssembler,
    data: ResonanceFrameInput,
    processing_times: Iterable[datetime] | None = None,
) -> Iterator[ResonanceFrame]:
    yield from replay_history(assembler, data, processing_times).frames


def build_history(
    assembler: ResonanceFrameAssembler, data: ResonanceFrameInput
) -> ResonanceFrameHistory:
    return assembler.build_batch(data)
