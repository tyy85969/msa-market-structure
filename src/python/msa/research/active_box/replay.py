"""Replay helpers for the causal C-007C Active Box selector."""

from __future__ import annotations

from collections.abc import Iterator

from msa.research.resonance import ResonanceScoreHistory

from .contracts import ActiveBoxSelectionFrame, ActiveBoxSelectionHistory
from .engine import ActiveBoxSelector
from .errors import ActiveBoxReplayError


def _validate_replay_history(
    source: ResonanceScoreHistory,
    replay: object,
) -> ResonanceScoreHistory:
    if not isinstance(replay, ResonanceScoreHistory):
        raise ActiveBoxReplayError(
            "replay_score_history must be a ResonanceScoreHistory"
        )
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
    if not isinstance(source_score_history, ResonanceScoreHistory):
        raise ActiveBoxReplayError(
            "source_score_history must be a ResonanceScoreHistory"
        )
    if any(
        frame.source_frame.config_snapshot.symbol
        != selector.config.symbol
        for frame in source_score_history.frames
    ):
        raise ActiveBoxReplayError(
            "selector symbol conflicts with source ScoreHistory"
        )
    schedule = (
        source_score_history
        if replay_score_history is None
        else _validate_replay_history(
            source_score_history, replay_score_history
        )
    )
    if any(
        frame.source_frame.config_snapshot.symbol
        != selector.config.symbol
        for frame in schedule.frames
    ):
        raise ActiveBoxReplayError(
            "selector symbol conflicts with Replay ScoreHistory"
        )
    result = selector.build_batch(schedule)
    if (
        replay_score_history is None
        and result.to_dict()
        != selector.build_batch(source_score_history).to_dict()
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
