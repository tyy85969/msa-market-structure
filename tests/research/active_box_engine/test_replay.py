from copy import deepcopy

import pytest

from msa.research.active_box import (
    ActiveBoxReplayError,
    iter_replay_active_box_frames,
    replay_active_box_history,
)
from msa.research.resonance import ResonanceFrameHistory, ResonanceScoreHistory
from tests.research.resonance_scoring.fixtures import scorer

from .fixtures import replay_with_extra, score_history, selector


def _corrupt_explicit_replay(case: str) -> ResonanceScoreHistory:
    replay = deepcopy(replay_with_extra())
    if case == "frames-string":
        object.__setattr__(replay, "frames", "invalid")
    elif case == "original-payload":
        object.__setattr__(
            replay.frames[0], "report", replay.frames[1].report
        )
    elif case == "relative-order":
        object.__setattr__(
            replay,
            "frames",
            (replay.frames[1], replay.frames[0], *replay.frames[2:]),
        )
    elif case == "time-reversal":
        object.__setattr__(
            replay.frames[1], "as_of_time", replay.frames[0].as_of_time
        )
    elif case == "duplicate-id":
        object.__setattr__(
            replay.frames[1],
            "score_frame_id",
            replay.frames[0].score_frame_id,
        )
    elif case == "unhashable-id":
        object.__setattr__(replay.frames[0], "score_frame_id", [])
    elif case == "source-mapping-conflict":
        object.__setattr__(
            replay.frames[0],
            "source_frame",
            replay.frames[1].source_frame,
        )
    else:  # pragma: no cover - helper guard
        raise AssertionError(case)
    return replay


def test_default_replay_is_byte_equivalent_to_batch() -> None:
    value = selector()
    source = score_history()
    assert (
        replay_active_box_history(value, source).to_dict()
        == value.build_batch(source).to_dict()
    )


def test_explicit_extra_frame_is_preserved_and_prefix_before_it_is_stable() -> None:
    value = selector()
    source = score_history()
    replay = replay_with_extra()
    baseline = value.build_batch(source)
    result = replay_active_box_history(value, source, replay)
    assert result.source_score_history == replay
    assert len(result.frames) == len(source.frames) + 1
    assert result.frames[0].to_dict() == baseline.frames[0].to_dict()
    assert result.frames[1].to_dict() == baseline.frames[1].to_dict()
    assert tuple(iter_replay_active_box_frames(value, source, replay)) == (
        result.frames
    )


def test_explicit_replay_cannot_omit_original_frame() -> None:
    source = score_history()
    scoring = scorer()
    source_frames = source.source_history.frames[:-1]
    shortened_source = ResonanceFrameHistory(
        frames=source_frames,
        final_frame=source_frames[-1],
        config_snapshot=source.source_history.config_snapshot,
    )
    shortened = scoring.build_batch(shortened_source)
    with pytest.raises(ActiveBoxReplayError, match="omit"):
        replay_active_box_history(selector(), source, shortened)


def test_explicit_replay_scoring_config_must_match() -> None:
    source = score_history()
    different = scorer(candidate_tier_weight=__import__(
        "decimal"
    ).Decimal("0.6")).build_batch(source.source_history)
    assert isinstance(different, ResonanceScoreHistory)
    with pytest.raises(ActiveBoxReplayError, match="config"):
        replay_active_box_history(selector(), source, different)


@pytest.mark.parametrize(
    "case",
    [
        "frames-string",
        "original-payload",
        "relative-order",
        "time-reversal",
        "duplicate-id",
        "unhashable-id",
        "source-mapping-conflict",
    ],
)
def test_explicit_replay_corruption_fails_closed(case) -> None:
    with pytest.raises(ActiveBoxReplayError):
        replay_active_box_history(
            selector(), score_history(), _corrupt_explicit_replay(case)
        )


def test_extra_frame_acceptance_preserves_full_prefix_order_and_source() -> None:
    value = selector()
    source = score_history()
    replay = replay_with_extra()
    baseline = value.build_batch(source)
    result = replay_active_box_history(value, source, replay)
    assert [frame.to_dict() for frame in result.frames[:2]] == [
        frame.to_dict() for frame in baseline.frames[:2]
    ]
    assert tuple(iter_replay_active_box_frames(value, source, replay)) == (
        result.frames
    )
    assert result.source_score_history.to_dict() == replay.to_dict()
    assert result.frames[2].source_score_frame.to_dict() == (
        replay.frames[2].to_dict()
    )
