"""Replay helpers for the causal C-007C Active Box selector."""

from __future__ import annotations

from collections.abc import Iterator

from msa.research.resonance import ResonanceScoreHistory

from .contracts import ActiveBoxSelectionFrame, ActiveBoxSelectionHistory
from .engine import ActiveBoxSelector, _selector_config
from .errors import (
    ActiveBoxContractError,
    ActiveBoxEngineError,
    ActiveBoxReplayError,
)


def _validate_formal_replay_history(
    value: object,
    field_name: str,
) -> ResonanceScoreHistory:
    if not isinstance(value, ResonanceScoreHistory):
        raise ActiveBoxReplayError(
            f"{field_name} must be a ResonanceScoreHistory"
        )
    try:
        restored = ResonanceScoreHistory.from_dict(value.to_dict())
    except (
        AttributeError,
        KeyError,
        AssertionError,
        TypeError,
        ValueError,
        RuntimeError,
    ) as exc:
        raise ActiveBoxReplayError(
            f"{field_name} is not a formally valid ResonanceScoreHistory"
        ) from exc
    if restored != value:
        raise ActiveBoxReplayError(
            f"{field_name} payload is not formally self-consistent"
        )
    return value


def _validate_replay_schedule(
    source: ResonanceScoreHistory,
    replay: ResonanceScoreHistory,
) -> ResonanceScoreHistory:
    if replay.config_snapshot != source.config_snapshot:
        raise ActiveBoxReplayError(
            "Replay scoring config must exactly equal source scoring config"
        )
    replay_ids = tuple(frame.score_frame_id for frame in replay.frames)
    if len(set(replay_ids)) != len(replay_ids):
        raise ActiveBoxReplayError("Replay ScoreFrame IDs must be unique")
    if any(
        current.as_of_time <= previous.as_of_time
        for previous, current in zip(replay.frames, replay.frames[1:])
    ):
        raise ActiveBoxReplayError(
            "Replay ScoreFrame times must be strictly increasing"
        )
    positions = {frame_id: index for index, frame_id in enumerate(replay_ids)}
    originals = {
        frame.score_frame_id: frame for frame in source.frames
    }
    missing = tuple(
        frame_id for frame_id in originals if frame_id not in positions
    )
    if missing:
        raise ActiveBoxReplayError(
            "Replay cannot omit an original ScoreFrame"
        )
    for frame_id, original in originals.items():
        replayed = replay.frames[positions[frame_id]]
        if replayed.to_dict() != original.to_dict():
            raise ActiveBoxReplayError(
                "Replay changed an original ScoreFrame payload"
            )
    original_positions = tuple(
        positions[frame.score_frame_id] for frame in source.frames
    )
    if any(
        current <= previous
        for previous, current in zip(
            original_positions, original_positions[1:]
        )
    ):
        raise ActiveBoxReplayError(
            "Replay changed original ScoreFrame relative order"
        )
    return replay


def replay_active_box_history(
    selector: ActiveBoxSelector,
    source_score_history: ResonanceScoreHistory,
    replay_score_history: ResonanceScoreHistory | None = None,
) -> ActiveBoxSelectionHistory:
    if not isinstance(selector, ActiveBoxSelector):
        raise ActiveBoxReplayError("selector must be an ActiveBoxSelector")
    try:
        config = _selector_config(selector)
    except ActiveBoxEngineError as exc:
        raise ActiveBoxReplayError(
            "selector config is not formally valid"
        ) from exc
    source = _validate_formal_replay_history(
        source_score_history, "source_score_history"
    )
    explicit = (
        None
        if replay_score_history is None
        else _validate_formal_replay_history(
            replay_score_history, "replay_score_history"
        )
    )
    if any(
        frame.source_frame.config_snapshot.symbol
        != config.symbol
        for frame in source.frames
    ):
        raise ActiveBoxReplayError(
            "selector symbol conflicts with source ScoreHistory"
        )
    schedule = (
        source
        if explicit is None
        else _validate_replay_schedule(source, explicit)
    )
    if any(
        frame.source_frame.config_snapshot.symbol
        != config.symbol
        for frame in schedule.frames
    ):
        raise ActiveBoxReplayError(
            "selector symbol conflicts with Replay ScoreHistory"
        )
    try:
        result = selector.build_batch(schedule)
        baseline = (
            None if explicit is not None else selector.build_batch(source)
        )
    except ActiveBoxContractError as exc:
        raise ActiveBoxReplayError(
            "Replay schedule failed Active Box validation"
        ) from exc
    if (
        explicit is None
        and result.to_dict()
        != baseline.to_dict()
    ):
        raise ActiveBoxReplayError(
            "default Replay must be byte-equivalent to Batch"
        )
    return result


def iter_replay_active_box_frames(
    selector: ActiveBoxSelector,
    source_score_history: ResonanceScoreHistory,
    replay_score_history: ResonanceScoreHistory | None = None,
) -> Iterator[ActiveBoxSelectionFrame]:
    yield from replay_active_box_history(
        selector, source_score_history, replay_score_history
    ).frames
