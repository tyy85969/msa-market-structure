from types import SimpleNamespace

import pytest

from msa.domain import BoundarySide
from msa.research.active_box import ActiveBoxEngineError
from msa.research.active_box.engine import _resolve_selected_zone

from .fixtures import score_history


def _decision(zone, *, side=None, key=..., snapshot=...):
    return SimpleNamespace(
        side=zone.side if side is None else side,
        selected_zone_key_id=zone.zone_key_id if key is ... else key,
        selected_zone_snapshot_id=(
            zone.zone_snapshot_id if snapshot is ... else snapshot
        ),
    )


def test_zone_resolution_rejects_missing_stable_key() -> None:
    frame = score_history().frames[0]
    with pytest.raises(ActiveBoxEngineError):
        _resolve_selected_zone(
            frame, _decision(frame.lower_zones[0], key="missing")
        )


def test_zone_resolution_rejects_snapshot_mismatch() -> None:
    frame = score_history().frames[0]
    with pytest.raises(ActiveBoxEngineError):
        _resolve_selected_zone(
            frame, _decision(frame.lower_zones[0], snapshot="wrong")
        )


def test_zone_resolution_rejects_wrong_side() -> None:
    frame = score_history().frames[0]
    with pytest.raises(ActiveBoxEngineError):
        _resolve_selected_zone(
            frame,
            _decision(frame.lower_zones[0], side=BoundarySide.UPPER),
        )


def test_zone_resolution_rejects_duplicate_stable_key() -> None:
    frame = score_history().frames[0]
    zone = frame.lower_zones[0]
    forged = SimpleNamespace(
        lower_zones=(zone, zone),
        upper_zones=frame.upper_zones,
        zones=frame.zones,
    )
    with pytest.raises(ActiveBoxEngineError):
        _resolve_selected_zone(forged, _decision(zone))


@pytest.mark.parametrize(
    ("key", "snapshot"),
    [(..., None), (None, ...)],
)
def test_zone_resolution_rejects_half_present_identity(
    key, snapshot
) -> None:
    frame = score_history().frames[0]
    with pytest.raises(ActiveBoxEngineError):
        _resolve_selected_zone(
            frame,
            _decision(frame.lower_zones[0], key=key, snapshot=snapshot),
        )


def test_zone_resolution_requires_current_score_frame_membership() -> None:
    frame = score_history().frames[0]
    zone = frame.lower_zones[0]
    forged = SimpleNamespace(
        lower_zones=(zone,),
        upper_zones=frame.upper_zones,
        zones=tuple(item for item in frame.zones if item != zone),
    )
    with pytest.raises(ActiveBoxEngineError):
        _resolve_selected_zone(forged, _decision(zone))
