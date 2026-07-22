from msa.domain import ActiveBoxStatus
from msa.research.active_box import freeze_active_box_snapshot, observe_active_box_snapshot
from tests.research.resonance.fixtures import T2

from .fixtures import initial_frame, score_frame


def test_active_box_domain_mapping_and_original_selection_price() -> None:
    frame=initial_frame(); snapshot=frame.active_box_snapshot; box=snapshot.active_box
    assert box.box_id==snapshot.box_key_id
    assert box.status is ActiveBoxStatus.ACTIVE
    assert box.selection_price==frame.source_score_frame.source_frame.reference_price.price
    assert box.origin_time==min(box.lower_boundary.origin_time,box.upper_boundary.origin_time)
    assert box.confirm_time==snapshot.created_time and box.frozen_time is None and box.retired_time is None


def test_key_stable_but_snapshot_changes_asof_and_zone_snapshots() -> None:
    first=initial_frame().active_box_snapshot; later_score=score_frame(at=T2)
    lower=next(item for item in later_score.lower_zones if item.zone_key_id==first.observed_lower_zone_key_id)
    upper=next(item for item in later_score.upper_zones if item.zone_key_id==first.observed_upper_zone_key_id)
    later=observe_active_box_snapshot(later_score,first,lower.zone_snapshot_id,upper.zone_snapshot_id)
    assert later.box_key_id==first.box_key_id
    assert later.box_snapshot_id!=first.box_snapshot_id
    assert later.lower_projection==first.lower_projection and later.upper_projection==first.upper_projection
    assert later.active_box.selection_price==first.active_box.selection_price


def test_frozen_snapshot_is_terminal_and_keeps_episode_identity() -> None:
    first=initial_frame().active_box_snapshot; frozen=freeze_active_box_snapshot(score_frame(at=T2),first)
    assert frozen.active_box.status is ActiveBoxStatus.FROZEN
    assert frozen.box_key_id==first.box_key_id and frozen.box_snapshot_id!=first.box_snapshot_id
    assert frozen.active_box.confirm_time==frozen.active_box.frozen_time==frozen.active_box.as_of_time
    assert frozen.active_box.selection_price==first.active_box.selection_price
