from copy import deepcopy
from decimal import Decimal

import pytest

from msa.research.active_box import (
    ActiveBoxEngineError,
    ActiveBoxReplayError,
    ActiveBoxSelector,
    build_active_box_history,
    freeze_active_box_snapshot,
    replay_active_box_history,
)

from .fixtures import score_history, selector


@pytest.mark.parametrize("bad", [None, "config", [], 1])
def test_selector_rejects_non_config_without_attribute_leak(bad) -> None:
    with pytest.raises(ActiveBoxEngineError):
        ActiveBoxSelector(bad)


@pytest.mark.parametrize("bad", [None, "frame", [], 1])
def test_select_rejects_non_score_frame_without_attribute_leak(bad) -> None:
    with pytest.raises(ActiveBoxEngineError):
        selector().select_frame(bad)


@pytest.mark.parametrize("bad", ["snapshot", [], 1])
def test_select_rejects_non_snapshot_previous_without_attribute_leak(bad) -> None:
    with pytest.raises(ActiveBoxEngineError):
        selector().select_frame(score_history().frames[1], bad)


def test_previous_must_be_active_exact_config_and_strictly_earlier() -> None:
    value = selector()
    source = score_history()
    first = value.select_frame(source.frames[0]).active_box_snapshot
    frozen = freeze_active_box_snapshot(source.frames[1], first)
    with pytest.raises(ActiveBoxEngineError, match="ACTIVE"):
        value.select_frame(source.frames[2], frozen)
    with pytest.raises(ActiveBoxEngineError, match="config"):
        selector(minimum_quality_score=Decimal("0.1")).select_frame(
            source.frames[1], first
        )
    with pytest.raises(ActiveBoxEngineError, match="strictly earlier"):
        value.select_frame(source.frames[0], first)


def test_mutated_formal_objects_fail_without_attribute_leak() -> None:
    source = score_history()
    frame = deepcopy(source.frames[1])
    object.__setattr__(frame, "source_frame", "invalid")
    with pytest.raises(ActiveBoxEngineError):
        selector().select_frame(frame)
    previous = deepcopy(
        selector().select_frame(source.frames[0]).active_box_snapshot
    )
    object.__setattr__(previous, "active_box", "invalid")
    with pytest.raises(ActiveBoxEngineError):
        selector().select_frame(source.frames[1], previous)


@pytest.mark.parametrize("bad", [None, "history", [], 1])
def test_batch_and_module_entry_reject_non_history(bad) -> None:
    value = selector()
    with pytest.raises(ActiveBoxEngineError):
        value.build_batch(bad)
    with pytest.raises(ActiveBoxEngineError):
        build_active_box_history(value, bad)


def test_replay_public_type_errors_use_replay_error() -> None:
    source = score_history()
    with pytest.raises(ActiveBoxReplayError):
        replay_active_box_history("selector", source)
    with pytest.raises(ActiveBoxReplayError):
        replay_active_box_history(selector(), "history")
    with pytest.raises(ActiveBoxReplayError):
        replay_active_box_history(selector(), source, "replay")
