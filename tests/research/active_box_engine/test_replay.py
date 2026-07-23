import pytest

from msa.research.active_box import (
    ActiveBoxReplayError,
    iter_replay_active_box_frames,
    replay_active_box_history,
)
from msa.research.resonance import ResonanceFrameHistory, ResonanceScoreHistory
from tests.research.resonance_scoring.fixtures import scorer

from .fixtures import replay_with_extra, score_history, selector


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
