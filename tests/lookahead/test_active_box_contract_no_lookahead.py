import pytest

from msa.research.active_box import project_zone
from tests.research.active_box_contract.fixtures import config, initial_frame, score_frame, selection_history
from tests.research.resonance.fixtures import T2


def test_future_score_history_append_does_not_change_old_full_payload() -> None:
    old=initial_frame().to_dict(); history=selection_history()
    assert history.frames[1].as_of_time>T2.replace(hour=0)
    assert initial_frame().to_dict()==old


def test_future_zone_cannot_enter_current_projection() -> None:
    current=score_frame(); future=score_frame(at=T2); future_zone=future.upper_zones[0]
    with pytest.raises(Exception,match="not the exact"): project_zone(current,future_zone,config(),current.as_of_time)


def test_origin_time_does_not_grant_visibility_before_member_confirm_time() -> None:
    projection=initial_frame().active_box_snapshot.upper_projection
    assert all(member.confirm_time<=projection.selection_confirm_time for member in projection.cluster.member_refs)
    assert min(member.origin_time for member in projection.cluster.member_refs)<=projection.selection_confirm_time


def test_retained_box_never_uses_future_projection_and_old_payload_is_stable() -> None:
    history=selection_history(); first=history.frames[0].active_box_snapshot
    payload=first.to_dict()
    for frame in history.frames[1:]:
        assert frame.active_box_snapshot.lower_projection==first.lower_projection
        assert frame.active_box_snapshot.upper_projection==first.upper_projection
    assert first.to_dict()==payload


def test_zone_snapshot_change_does_not_change_stable_zone_or_box_key() -> None:
    history=selection_history(); lower_keys={frame.active_box_snapshot.observed_lower_zone_key_id for frame in history.frames}
    lower_snapshots={frame.active_box_snapshot.observed_lower_zone_snapshot_id for frame in history.frames}
    box_keys={frame.active_box_snapshot.box_key_id for frame in history.frames}
    assert len(lower_keys)==len(box_keys)==1 and len(lower_snapshots)>1
