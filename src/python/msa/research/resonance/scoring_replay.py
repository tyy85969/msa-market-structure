"""Batch and replay helpers for immutable C-007B score histories."""

from __future__ import annotations

from typing import Iterable, Iterator

from .contracts import ResonanceFrame, ResonanceFrameHistory
from .errors import ResonanceScoringInputError
from .scoring import ResonanceScorer
from .scoring_contracts import ResonanceScoreFrame, ResonanceScoreHistory


def _normalize_frames(
    source_history: ResonanceFrameHistory,
    frames: Iterable[ResonanceFrame] | None,
) -> tuple[ResonanceFrame, ...]:
    if frames is None:
        return source_history.frames
    normalized = tuple(frames)
    if not normalized or any(not isinstance(item, ResonanceFrame) for item in normalized):
        raise ResonanceScoringInputError(
            "explicit scoring replay must contain ResonanceFrame values"
        )
    if any(current.as_of_time <= previous.as_of_time for previous, current in zip(normalized, normalized[1:])):
        raise ResonanceScoringInputError(
            "explicit scoring replay Frame times must be strictly increasing"
        )
    if len({item.frame_id for item in normalized}) != len(normalized):
        raise ResonanceScoringInputError(
            "explicit scoring replay Frame IDs must be unique"
        )
    if any(item.config_snapshot != source_history.config_snapshot for item in normalized):
        raise ResonanceScoringInputError(
            "explicit scoring replay Frames must use the source History config"
        )
    original_ids = {item.frame_id for item in source_history.frames}
    replay_ids = {item.frame_id for item in normalized}
    if not original_ids.issubset(replay_ids):
        raise ResonanceScoringInputError(
            "explicit scoring replay cannot omit an original History Frame"
        )
    originals = {item.frame_id: item for item in source_history.frames}
    if any(
        item.frame_id in originals and item != originals[item.frame_id]
        for item in normalized
    ):
        raise ResonanceScoringInputError(
            "explicit scoring replay changed an original History Frame"
        )
    return normalized


def replay_score_history(
    scorer: ResonanceScorer,
    source_history: ResonanceFrameHistory,
    frames: Iterable[ResonanceFrame] | None = None,
) -> ResonanceScoreHistory:
    if not isinstance(scorer, ResonanceScorer):
        raise ResonanceScoringInputError("scorer must be a ResonanceScorer")
    if not isinstance(source_history, ResonanceFrameHistory):
        raise ResonanceScoringInputError(
            "source_history must be a ResonanceFrameHistory"
        )
    schedule = _normalize_frames(source_history, frames)
    scored = tuple(scorer.score_frame(item) for item in schedule)
    history = ResonanceScoreHistory(
        frames=scored,
        final_frame=scored[-1],
        source_history=source_history,
        config_snapshot=scorer.config,
    )
    if frames is None and history.to_dict() != scorer.build_batch(source_history).to_dict():
        raise ResonanceScoringInputError(
            "default scoring Replay must be byte-equivalent to Batch"
        )
    return history


def iter_replay_score_frames(
    scorer: ResonanceScorer,
    source_history: ResonanceFrameHistory,
    frames: Iterable[ResonanceFrame] | None = None,
) -> Iterator[ResonanceScoreFrame]:
    yield from replay_score_history(scorer, source_history, frames).frames


def build_score_history(
    scorer: ResonanceScorer, source_history: ResonanceFrameHistory
) -> ResonanceScoreHistory:
    return scorer.build_batch(source_history)
