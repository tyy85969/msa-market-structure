from dataclasses import FrozenInstanceError

import pytest

from msa.research.active_box import ActiveBoxSelector

from .fixtures import score_history, selector


def test_selector_is_frozen_slotted_and_stateless() -> None:
    value = selector()
    assert not hasattr(value, "__dict__")
    assert tuple(value.__slots__) == ("config",)
    with pytest.raises(FrozenInstanceError):
        value.config = value.config  # type: ignore[misc]


def test_same_frame_and_previous_input_is_exactly_deterministic() -> None:
    value = selector()
    history = value.build_batch(score_history())
    frame = history.source_score_history.frames[1]
    previous = history.frames[0].active_box_snapshot
    assert (
        value.select_frame(frame, previous).to_dict()
        == value.select_frame(frame, previous).to_dict()
    )


def test_selector_public_type_is_exported() -> None:
    assert isinstance(selector(), ActiveBoxSelector)
