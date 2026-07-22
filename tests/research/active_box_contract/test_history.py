import pytest

from msa.research.active_box import ActiveBoxSelectionHistory

from .fixtures import selection_history


def test_history_contract_source_mapping_and_prefix_stability() -> None:
    history=selection_history(); prefix=tuple(frame.to_dict() for frame in history.frames[:-1])
    assert history.final_frame==history.frames[-1]
    assert tuple(frame.source_score_frame for frame in history.frames)==history.source_score_history.frames
    assert tuple(frame.to_dict() for frame in history.frames[:-1])==prefix
    assert len(history.events)==1 and history.frozen_boxes==()


def test_history_round_trip_is_exact_and_frozen() -> None:
    history=selection_history(); restored=ActiveBoxSelectionHistory.from_dict(history.to_dict())
    assert restored==history and restored.to_dict()==history.to_dict()
    assert not hasattr(history,"__dict__")


@pytest.mark.parametrize("attack",["final","events","source"])
def test_history_ledger_attacks_fail_closed(attack) -> None:
    payload=selection_history().to_dict()
    if attack=="final": payload["final_frame"]=payload["frames"][0]
    elif attack=="events": payload["events"]=[]
    else: payload["frames"][0]["source_score_frame_id"]="changed"
    with pytest.raises(Exception): ActiveBoxSelectionHistory.from_dict(payload)


def test_zone_snapshot_updates_keep_box_key_and_projections() -> None:
    history=selection_history(); keys={frame.active_box_snapshot.box_key_id for frame in history.frames}
    projections={(frame.active_box_snapshot.lower_projection.projection_id,frame.active_box_snapshot.upper_projection.projection_id) for frame in history.frames}
    snapshots={frame.active_box_snapshot.box_snapshot_id for frame in history.frames}
    assert len(keys)==len(projections)==1
    assert len(snapshots)==len(history.frames)
    assert all(not frame.emitted_events for frame in history.frames[1:])
