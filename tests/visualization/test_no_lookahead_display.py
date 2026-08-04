from dataclasses import replace
from datetime import timedelta

import pytest

from msa.visualization import VisualContractError, VisualScene, render_svg


def test_confirmed_state_cannot_be_visible_before_confirm_time(scene: VisualScene) -> None:
    boundary = scene.confirmed_boundaries[0]
    future = replace(
        boundary,
        confirm_time=scene.as_of_time + timedelta(minutes=1),
        display_end_time=scene.as_of_time + timedelta(minutes=1),
    )
    with pytest.raises(VisualContractError, match="future boundary"):
        replace(scene, confirmed_boundaries=(future,))


def test_origin_time_only_creates_neutral_visual_extension(scene: VisualScene) -> None:
    boundary = scene.confirmed_boundaries[0]
    assert boundary.origin_time < boundary.confirm_time
    payload = render_svg(scene)
    assert 'stroke="#a4adba"' in payload
    assert 'stroke="#f2d34f"' in payload


def test_future_candle_is_rejected(scene: VisualScene) -> None:
    candle = replace(
        scene.candles[0],
        available_time=scene.as_of_time + timedelta(minutes=1),
    )
    with pytest.raises(VisualContractError, match="future candle"):
        replace(scene, candles=(candle,))
