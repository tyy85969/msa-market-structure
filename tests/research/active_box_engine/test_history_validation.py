from copy import deepcopy

import pytest

from msa.research.active_box import (
    ActiveBoxEngineError,
    ActiveBoxReplayError,
    replay_active_box_history,
)
from tests.research.resonance_scoring.fixtures import scorer

from .fixtures import score_history, selector


def _corrupt_history(case: str):
    history = deepcopy(score_history())
    if case == "frames-string":
        object.__setattr__(history, "frames", "invalid")
    elif case == "non-frame-member":
        object.__setattr__(
            history, "frames", ("invalid", *history.frames[1:])
        )
    elif case == "wrong-final-frame":
        object.__setattr__(history, "final_frame", history.frames[0])
    elif case == "inconsistent-config":
        object.__setattr__(
            history,
            "config_snapshot",
            scorer(candidate_tier_weight=__import__(
                "decimal"
            ).Decimal("0.6")).config,
        )
    elif case == "invalid-source-history":
        object.__setattr__(history, "source_history", "invalid")
    elif case == "source-mapping-conflict":
        object.__setattr__(
            history.frames[0],
            "source_frame",
            history.frames[1].source_frame,
        )
    elif case == "score-frame-id-list":
        object.__setattr__(history.frames[0], "score_frame_id", [])
    elif case == "score-frame-id-none":
        object.__setattr__(history.frames[0], "score_frame_id", None)
    elif case == "time-reversal":
        object.__setattr__(
            history.frames[1], "as_of_time", history.frames[0].as_of_time
        )
    elif case == "duplicate-frame-id":
        object.__setattr__(
            history.frames[1],
            "score_frame_id",
            history.frames[0].score_frame_id,
        )
    else:  # pragma: no cover - test helper guard
        raise AssertionError(case)
    return history


@pytest.mark.parametrize(
    "case",
    [
        "frames-string",
        "non-frame-member",
        "wrong-final-frame",
        "inconsistent-config",
        "invalid-source-history",
        "source-mapping-conflict",
        "score-frame-id-list",
        "score-frame-id-none",
        "time-reversal",
        "duplicate-frame-id",
    ],
)
def test_batch_rejects_corrupted_authoritative_score_history(case) -> None:
    with pytest.raises(ActiveBoxEngineError):
        selector().build_batch(_corrupt_history(case))


@pytest.mark.parametrize(
    "case",
    [
        "frames-string",
        "non-frame-member",
        "wrong-final-frame",
        "inconsistent-config",
        "invalid-source-history",
        "source-mapping-conflict",
        "score-frame-id-list",
        "score-frame-id-none",
        "time-reversal",
        "duplicate-frame-id",
    ],
)
def test_replay_rejects_corrupted_authoritative_score_history(case) -> None:
    with pytest.raises(ActiveBoxReplayError):
        replay_active_box_history(selector(), _corrupt_history(case))


@pytest.mark.parametrize("bad", ["config", [], None])
def test_mutated_selector_config_fails_closed_in_batch_and_replay(bad) -> None:
    value = selector()
    object.__setattr__(value, "config", bad)
    with pytest.raises(ActiveBoxEngineError):
        value.build_batch(score_history())
    with pytest.raises(ActiveBoxReplayError):
        replay_active_box_history(value, score_history())
